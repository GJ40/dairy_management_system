from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.request_context import RequestContext
from app.services.email_service import EmailService
from app.services.security_audit_service import SecurityAuditService
from app.utils.time import utc_now_naive

logger = logging.getLogger("app.security.login")

STAFF_SCOPE = "staff"
CUSTOMER_SCOPE = "customer"

STAFF_RESOURCE = "staff_user"
CUSTOMER_RESOURCE = "customer_portal_account"


class LoginSecurityService:
    """Best-effort login auditing and failed-login alerting.

    Audit writes and mail delivery are queued behind the response whenever a
    FastAPI `BackgroundTasks` object is supplied, so neither can change the
    login response body or its latency. Failures are logged and swallowed.
    """

    def __init__(
        self,
        audit: SecurityAuditService,
        email_service: EmailService | None = None,
    ) -> None:
        self.audit = audit
        self.email_service = email_service

    async def record_success(
        self,
        *,
        scope: str,
        context: RequestContext | None,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        role: str | None = None,
        background: BackgroundTasks | None = None,
    ) -> None:
        metadata: dict[str, object] = {"scope": scope}
        if scope == STAFF_SCOPE and role:
            metadata["role"] = role

        async def record() -> None:
            await self.audit.record_standalone(
                event_type="auth.login.succeeded",
                context=context,
                actor_user_id=actor_user_id,
                actor_account_id=actor_account_id,
                metadata=metadata,
            )

        await self._run_or_queue(record, background)

    async def record_refresh_failure(
        self,
        *,
        scope: str,
        reason_code: str,
        context: RequestContext | None,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
    ) -> None:
        """Best-effort audit for a rejected refresh, never changing the 401."""
        await self.audit.record_standalone(
            event_type="auth.refresh.failed",
            context=context,
            actor_user_id=actor_user_id,
            actor_account_id=actor_account_id,
            reason_code=reason_code,
            metadata={"scope": scope, "reason_code": reason_code},
        )

    async def record_logout(
        self,
        *,
        scope: str,
        context: RequestContext | None,
        background: BackgroundTasks | None = None,
    ) -> None:
        """Logout is unauthenticated by design, so the actor is anonymous.

        Queued behind the response when possible so a slow audit database can
        never delay clearing the session cookies.
        """

        async def record() -> None:
            await self.audit.record_standalone(
                event_type="auth.logout",
                context=context,
                metadata={"scope": scope},
            )

        await self._run_or_queue(record, background)

    async def record_failure(
        self,
        *,
        scope: str,
        reason_code: str,
        context: RequestContext | None,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        email: str | None = None,
        name: str | None = None,
        alertable: bool = False,
        background: BackgroundTasks | None = None,
    ) -> None:
        async def process() -> None:
            await self._process_failure(
                scope=scope,
                reason_code=reason_code,
                context=context,
                actor_user_id=actor_user_id,
                actor_account_id=actor_account_id,
                email=email,
                name=name,
                alertable=alertable,
            )

        await self._run_or_queue(process, background)

    async def _process_failure(
        self,
        *,
        scope: str,
        reason_code: str,
        context: RequestContext | None,
        actor_user_id: int | None,
        actor_account_id: int | None,
        email: str | None,
        name: str | None,
        alertable: bool,
    ) -> None:
        account_resolved = actor_user_id is not None or actor_account_id is not None
        recorded = await self.audit.record_standalone(
            event_type="auth.login.failed",
            context=context,
            actor_user_id=actor_user_id,
            actor_account_id=actor_account_id,
            reason_code=reason_code,
            metadata={
                "scope": scope,
                "reason_code": reason_code,
                "account_resolved": account_resolved,
            },
        )
        if not recorded:
            return
        if not alertable or not email or not settings.failed_login_alert_enabled:
            return

        resource_type, resource_id = self._resource(scope, actor_user_id, actor_account_id)
        if resource_type is None or resource_id is None:
            return

        now = utc_now_naive()
        failure_count = await self.audit.count_recent(
            event_type="auth.login.failed",
            since=now
            - timedelta(minutes=settings.failed_login_alert_window_minutes),
            actor_user_id=actor_user_id,
            actor_account_id=actor_account_id,
        )
        if failure_count < settings.failed_login_alert_threshold:
            return

        recent_alerts = await self.audit.count_recent(
            event_type="auth.alert.failed_login.sent",
            since=now
            - timedelta(minutes=settings.failed_login_alert_cooldown_minutes),
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if recent_alerts:
            await self.audit.record_standalone(
                event_type="auth.alert.failed_login.suppressed",
                actor_type="system",
                resource_type=resource_type,
                resource_id=resource_id,
                metadata={
                    "scope": scope,
                    "failure_count": failure_count,
                    "cooldown_minutes": settings.failed_login_alert_cooldown_minutes,
                },
            )
            return

        # Record the dispatch before handing the message to SMTP so a slow or
        # failing mail server cannot bypass the cooldown.
        sent_recorded = await self.audit.record_standalone(
            event_type="auth.alert.failed_login.sent",
            actor_type="system",
            resource_type=resource_type,
            resource_id=resource_id,
            metadata={
                "scope": scope,
                "failure_count": failure_count,
                "window_minutes": settings.failed_login_alert_window_minutes,
            },
        )
        if not sent_recorded:
            return

        await self._deliver_alert(
            scope=scope,
            to=email,
            name=name,
            failure_count=failure_count,
            resource_type=resource_type,
            resource_id=resource_id,
            occurred_at_utc=now,
            context=context,
        )

    async def _deliver_alert(
        self,
        *,
        scope: str,
        to: str,
        name: str | None,
        failure_count: int,
        resource_type: str,
        resource_id: str,
        occurred_at_utc: datetime,
        context: RequestContext | None,
    ) -> None:
        if self.email_service is None:
            await self._record_delivery_failed(
                scope=scope,
                resource_type=resource_type,
                resource_id=resource_id,
                reason_code="email_not_configured",
            )
            return

        try:
            delivered = await self.email_service.send_failed_login_alert(
                to=to,
                name=name or "there",
                scope=scope,
                failure_count=failure_count,
                window_minutes=settings.failed_login_alert_window_minutes,
                occurred_at_utc=occurred_at_utc,
                ip_address=context.ip_address if context is not None else None,
                user_agent=context.user_agent if context is not None else None,
                # Only claim a block when this many failures also starts the
                # cooldown; the alert threshold is independently configurable.
                cooldown_minutes=(
                    settings.login_cooldown_minutes
                    if failure_count >= settings.login_cooldown_threshold
                    else None
                ),
            )
        except Exception:
            logger.exception("Failed-login alert delivery raised")
            delivered = False

        if not delivered:
            await self._record_delivery_failed(
                scope=scope,
                resource_type=resource_type,
                resource_id=resource_id,
                reason_code="delivery_failed",
            )

    async def record_account_locked(
        self,
        *,
        scope: str,
        failure_count: int,
        context: RequestContext | None,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        email: str | None = None,
        name: str | None = None,
        background: BackgroundTasks | None = None,
    ) -> None:
        """Audit an automatic lock and warn the owner that it happened.

        The lock itself is already committed by the caller; this notification
        is best-effort and can never change the sign-in response.
        """
        resource_type, resource_id = self._resource(
            scope, actor_user_id, actor_account_id
        )
        if resource_type is None or resource_id is None:
            return

        async def process() -> None:
            recorded = await self.audit.record_standalone(
                event_type="auth.account.locked",
                actor_type="system",
                resource_type=resource_type,
                resource_id=resource_id,
                metadata={
                    "scope": scope,
                    "failure_count": failure_count,
                    "window_minutes": settings.login_lockout_window_minutes,
                },
            )
            if not recorded:
                return
            if not email or not settings.failed_login_alert_enabled:
                return

            delivered = False
            if self.email_service is not None:
                try:
                    delivered = await self.email_service.send_account_locked_notice(
                        to=email,
                        name=name or "there",
                        scope=scope,
                        failure_count=failure_count,
                        window_minutes=settings.login_lockout_window_minutes,
                        locked_at_utc=utc_now_naive(),
                        ip_address=(
                            context.ip_address if context is not None else None
                        ),
                        user_agent=(
                            context.user_agent if context is not None else None
                        ),
                    )
                except Exception:
                    logger.exception("Account-locked notice delivery raised")
                    delivered = False

            if not delivered:
                await self._record_delivery_failed(
                    scope=scope,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    reason_code=(
                        "delivery_failed"
                        if self.email_service is not None
                        else "email_not_configured"
                    ),
                )

        await self._run_or_queue(process, background)

    async def _record_delivery_failed(
        self,
        *,
        scope: str,
        resource_type: str,
        resource_id: str,
        reason_code: str,
    ) -> None:
        await self.audit.record_standalone(
            event_type="auth.alert.failed_login.delivery_failed",
            actor_type="system",
            resource_type=resource_type,
            resource_id=resource_id,
            reason_code=reason_code,
            metadata={"scope": scope, "reason_code": reason_code},
        )

    @staticmethod
    def _resource(
        scope: str,
        actor_user_id: int | None,
        actor_account_id: int | None,
    ) -> tuple[str | None, str | None]:
        if scope == STAFF_SCOPE and actor_user_id is not None:
            return STAFF_RESOURCE, str(actor_user_id)
        if scope == CUSTOMER_SCOPE and actor_account_id is not None:
            return CUSTOMER_RESOURCE, str(actor_account_id)
        return None, None

    @staticmethod
    async def _run_or_queue(task, background: BackgroundTasks | None) -> None:
        if background is None:
            await task()
            return
        background.add_task(task)
