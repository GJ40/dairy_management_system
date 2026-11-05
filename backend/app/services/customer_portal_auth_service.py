from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.core.security import (
    create_customer_access_token,
    create_customer_refresh_token,
    decode_customer_refresh_token,
    hash_password,
    verify_password,
)
from app.models.customer_portal_account import CustomerPortalAccount
from app.repositories.customer_portal_account_repository import (
    CustomerPortalAccountRepository,
)
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer_portal_auth import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    CreatePortalAccountRequest,
    PortalAccountQuery,
    serialize_account_event,
    serialize_activation,
    serialize_portal_account,
)
from app.services.email_service import EmailService
from app.services.login_lockout import (
    FailureOutcome,
    clear_lock,
    cooldown_error,
    cooldown_remaining_seconds,
    is_locked,
    locked_error,
    register_failed_attempt,
    reset_failed_attempts,
)
from app.services.login_security_service import CUSTOMER_SCOPE, LoginSecurityService
from app.services.security_audit_service import SecurityAuditService
from app.utils.tasks import deliver_or_queue
from app.utils.time import business_now_naive


def hash_activation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_activation_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = business_now_naive() + timedelta(
        hours=settings.customer_activation_ttl_hours
    )
    return token, hash_activation_token(token), expires_at


def _validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "WEAK_PASSWORD",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "WEAK_PASSWORD",
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes",
        )


def _invalid_login() -> Exception:
    return api_error(
        status.HTTP_401_UNAUTHORIZED,
        "UNAUTHORIZED",
        "Invalid email or password",
    )


class CustomerPortalAuthService:
    def __init__(
        self,
        repository: CustomerPortalAccountRepository,
        customer_repository: CustomerRepository,
        login_security: LoginSecurityService | None = None,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository
        self.login_security = login_security
        self.audit = audit

    async def activate(
        self,
        token: str,
        password: str,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        account = await self.repository.get_by_activation_hash(
            hash_activation_token(token)
        )
        if account is None:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_ACTIVATION_TOKEN",
                "Activation token is invalid or has already been used",
            )

        if account.password_hash is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "ALREADY_ACTIVATED",
                "This portal account is already activated",
            )

        if (
            account.activation_expires_at is None
            or account.activation_expires_at <= business_now_naive()
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "ACTIVATION_TOKEN_EXPIRED",
                "Activation token has expired; ask the dairy to reissue it",
            )

        if not account.is_active:
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "ACCOUNT_INACTIVE",
                "This portal account is deactivated",
            )

        _validate_new_password(password)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "ACCOUNT_INACTIVE",
                "The linked customer account is inactive",
            )

        account.password_hash = hash_password(password)
        account.activated_at = business_now_naive()
        account.activation_token_hash = None
        account.activation_expires_at = None
        await self.repository.add_event(
            account_id=account.id,
            action="activated",
            actor_user_id=None,
            note="Self-service activation",
        )
        if self.audit is not None:
            await self.audit.record(
                event_type="auth.account.activated",
                context=context,
                actor_account_id=account.id,
                resource_type="customer_portal_account",
                resource_id=account.id,
                metadata={
                    "account_id": account.id,
                    "customer_id": account.customer_id,
                },
            )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        return {
            "message": "Portal account activated. Sign in to continue.",
            "account": serialize_portal_account(account, customer),
        }

    async def login(
        self,
        email: str,
        password: str,
        *,
        background: BackgroundTasks | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        account = await self.repository.get_by_email(email, include_deleted=True)
        if account is None:
            await self._record_failure(
                reason_code="unknown_email",
                context=context,
                background=background,
            )
            raise _invalid_login()

        if account.is_deleted:
            await self._record_failure(
                reason_code="deleted",
                context=context,
                background=background,
                account=account,
                alertable=False,
            )
            raise _invalid_login()

        if is_locked(account):
            await self._record_failure(
                reason_code="account_locked",
                context=context,
                background=background,
                account=account,
                alertable=False,
            )
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "ACCOUNT_LOCKED",
                "This portal account is locked. Contact the dairy to unlock it.",
            )

        cooldown_seconds = cooldown_remaining_seconds(account)
        if cooldown_seconds:
            # Refused without checking the password and without counting: the
            # cooldown is a pause, so repeated attempts during it cannot
            # escalate into a hard lock.
            await self._record_failure(
                reason_code="cooldown",
                context=context,
                background=background,
                account=account,
                alertable=False,
            )
            raise cooldown_error(cooldown_seconds)

        if not account.password_hash:
            await self._record_failure(
                reason_code="not_activated",
                context=context,
                background=background,
                account=account,
                alertable=True,
            )
            raise _invalid_login()

        if not verify_password(password, account.password_hash):
            outcome = register_failed_attempt(account)
            await self._commit_lockout_state()
            await self._record_failure(
                reason_code="bad_password",
                context=context,
                background=background,
                account=account,
                alertable=True,
            )
            if outcome.locked:
                await self._notify_locked(outcome, account, context, background)
                raise locked_error()
            raise _invalid_login()

        if account.activated_at is None:
            await self._record_failure(
                reason_code="not_activated",
                context=context,
                background=background,
                account=account,
                alertable=True,
            )
            raise _invalid_login()

        if not account.is_active:
            await self._record_failure(
                reason_code="inactive",
                context=context,
                background=background,
                account=account,
                alertable=True,
            )
            raise _invalid_login()

        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            await self._record_failure(
                reason_code="inactive",
                context=context,
                background=background,
                account=account,
                name=customer.name if customer is not None else None,
                alertable=True,
            )
            raise _invalid_login()

        account.last_login_at = business_now_naive()
        reset_failed_attempts(account)
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self._record_success(account, context, background)
        return {
            "access_token": self._access_token(account),
            "refresh_token": self._refresh_token(account),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "account": serialize_portal_account(account, customer),
        }

    async def _commit_lockout_state(self) -> None:
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

    async def _notify_locked(
        self,
        outcome: FailureOutcome,
        account: CustomerPortalAccount,
        context: RequestContext | None,
        background: BackgroundTasks | None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_account_locked(
            scope=CUSTOMER_SCOPE,
            failure_count=outcome.count,
            context=context,
            actor_account_id=account.id,
            email=account.email,
            name=None,
            background=background,
        )

    async def _record_failure(
        self,
        *,
        reason_code: str,
        context: RequestContext | None,
        background: BackgroundTasks | None,
        account: CustomerPortalAccount | None = None,
        name: str | None = None,
        alertable: bool = False,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_failure(
            scope=CUSTOMER_SCOPE,
            reason_code=reason_code,
            context=context,
            actor_account_id=account.id if account is not None else None,
            email=account.email if account is not None else None,
            name=name,
            alertable=alertable,
            background=background,
        )

    async def _record_success(
        self,
        account: CustomerPortalAccount,
        context: RequestContext | None,
        background: BackgroundTasks | None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_success(
            scope=CUSTOMER_SCOPE,
            context=context,
            actor_account_id=account.id,
            background=background,
        )

    async def refresh(
        self,
        refresh_token: str,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        try:
            payload = decode_customer_refresh_token(refresh_token)
        except jwt.ExpiredSignatureError as exc:
            await self.record_refresh_failure("expired", context)
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Refresh token has expired",
            ) from exc
        except jwt.InvalidTokenError as exc:
            await self.record_refresh_failure("invalid", context)
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Invalid refresh token",
            ) from exc

        try:
            account_id = int(payload.get("account_id"))
            customer_id = int(payload.get("customer_id"))
        except (TypeError, ValueError) as exc:
            await self.record_refresh_failure("subject_missing", context)
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account not found",
            ) from exc

        account = await self.repository.get_by_id(account_id, include_deleted=True)
        if (
            account is None
            or account.is_deleted
            or account.customer_id != customer_id
            or not account.is_active
            or account.activated_at is None
            or not account.password_hash
        ):
            await self.record_refresh_failure(
                "inactive" if account is not None else "subject_missing",
                context,
                account_id=account_id if account is not None else None,
            )
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account is not available",
            )

        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            await self.record_refresh_failure(
                "inactive", context, account_id=account.id
            )
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Account is not available",
            )
        try:
            self._assert_session_current(payload, account)
        except HTTPException:
            await self.record_refresh_failure(
                "version_mismatch", context, account_id=account.id
            )
            raise

        return {
            "access_token": self._access_token(account),
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "account": serialize_portal_account(account, customer),
        }

    async def record_refresh_failure(
        self,
        reason_code: str,
        context: RequestContext | None,
        *,
        account_id: int | None = None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_refresh_failure(
            scope=CUSTOMER_SCOPE,
            reason_code=reason_code,
            context=context,
            actor_account_id=account_id,
        )

    async def record_logout(
        self,
        context: RequestContext | None = None,
        *,
        background: BackgroundTasks | None = None,
    ) -> None:
        if self.login_security is None:
            return
        await self.login_security.record_logout(
            scope=CUSTOMER_SCOPE,
            context=context,
            background=background,
        )

    async def get_me(self, account: CustomerPortalAccount) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(account.customer_id)
        return {"account": serialize_portal_account(account, customer)}

    @staticmethod
    def _assert_session_current(
        payload: dict[str, Any],
        account: CustomerPortalAccount,
    ) -> None:
        """Reject tokens issued before the last password change/deactivation."""
        try:
            issued_version = int(payload.get("ver", 0))
        except (TypeError, ValueError):
            issued_version = -1
        if issued_version != (account.token_version or 0):
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Session has expired; sign in again",
            )

    @staticmethod
    def _access_token(account: CustomerPortalAccount) -> str:
        return create_customer_access_token(
            account_id=account.id,
            customer_id=account.customer_id,
            email=account.email,
            token_version=account.token_version or 0,
        )

    @staticmethod
    def _refresh_token(account: CustomerPortalAccount) -> str:
        return create_customer_refresh_token(
            account_id=account.id,
            customer_id=account.customer_id,
            email=account.email,
            token_version=account.token_version or 0,
        )


class CustomerPortalAccountService:
    def __init__(
        self,
        repository: CustomerPortalAccountRepository,
        customer_repository: CustomerRepository,
        email_service: EmailService | None = None,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository
        # Optional so existing callers/tests can build the service without mail.
        self.email_service = email_service
        self.audit = audit

    async def _record(
        self,
        *,
        event_type: str,
        actor_user_id: int,
        context: RequestContext | None,
        account: CustomerPortalAccount,
        metadata: dict[str, object],
    ) -> None:
        if self.audit is None:
            return
        await self.audit.record(
            event_type=event_type,
            context=context,
            actor_user_id=actor_user_id,
            resource_type="customer_portal_account",
            resource_id=account.id,
            metadata=metadata,
        )

    async def list_accounts(self, query: PortalAccountQuery) -> dict[str, Any]:
        rows, total = await self.repository.list_and_count(query)
        items = []
        for account in rows:
            customer = await self.customer_repository.get_by_id(account.customer_id)
            items.append(serialize_portal_account(account, customer))
        return {
            "items": items,
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        }

    async def get_account(self, account_id: int) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        customer = await self.customer_repository.get_by_id(account.customer_id)
        events = await self.repository.list_events(account.id)
        return {
            "account": serialize_portal_account(account, customer),
            "events": [serialize_account_event(event) for event in events],
        }

    async def provision(
        self,
        payload: CreatePortalAccountRequest,
        actor_user_id: int,
        *,
        background: BackgroundTasks | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(payload.customer_id)
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {payload.customer_id} not found",
            )
        if not customer.is_active:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "CUSTOMER_INACTIVE",
                "Cannot provision a portal account for an inactive customer",
            )

        if (
            await self.repository.get_by_customer_id(
                payload.customer_id, include_deleted=True
            )
            is not None
        ):
            raise api_error(
                status.HTTP_409_CONFLICT,
                "ACCOUNT_EXISTS",
                "This customer already has a portal account",
            )

        if (
            await self.repository.get_by_email(payload.email, include_deleted=True)
            is not None
        ):
            raise api_error(
                status.HTTP_409_CONFLICT,
                "EMAIL_IN_USE",
                "That email is already used by another portal account",
            )

        token, token_hash, expires_at = issue_activation_token()
        account = await self.repository.create(
            customer_id=payload.customer_id,
            email=payload.email,
            activation_token_hash=token_hash,
            activation_expires_at=expires_at,
        )
        await self.repository.add_event(
            account_id=account.id,
            action="provisioned",
            actor_user_id=actor_user_id,
            note=None,
        )
        await self._record(
            event_type="portal_account.provisioned",
            actor_user_id=actor_user_id,
            context=context,
            account=account,
            metadata={
                "account_id": account.id,
                "customer_id": account.customer_id,
            },
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)
        await self._send_activation_email(
            account, customer, token, background=background
        )

        return {
            "account": serialize_portal_account(account, customer),
            "activation": serialize_activation(token, expires_at),
        }

    async def reactivate(
        self,
        account_id: int,
        actor_user_id: int,
        *,
        background: BackgroundTasks | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        token, token_hash, expires_at = issue_activation_token()

        account.is_active = True
        account.password_hash = None
        account.activated_at = None
        clear_lock(account)
        # Any session from before the deactivation must not come back to life.
        account.token_version = (account.token_version or 0) + 1
        account.activation_token_hash = token_hash
        account.activation_expires_at = expires_at
        await self.repository.add_event(
            account_id=account.id,
            action="reactivated",
            actor_user_id=actor_user_id,
            note="Fresh activation token issued; new password required",
        )
        await self._record(
            event_type="portal_account.reactivated",
            actor_user_id=actor_user_id,
            context=context,
            account=account,
            metadata={
                "account_id": account.id,
                "customer_id": account.customer_id,
            },
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        await self._send_activation_email(
            account, customer, token, background=background
        )
        return {
            "account": serialize_portal_account(account, customer),
            "activation": serialize_activation(token, expires_at),
        }

    async def deactivate(
        self,
        account_id: int,
        reason: str,
        actor_user_id: int,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        account.is_active = False
        account.activation_token_hash = None
        account.activation_expires_at = None
        # Sign every existing device out immediately, not just on its next
        # refresh after the account is flipped back on.
        account.token_version = (account.token_version or 0) + 1
        await self.repository.add_event(
            account_id=account.id,
            action="deactivated",
            actor_user_id=actor_user_id,
            note=reason,
        )
        await self._record(
            event_type="portal_account.deactivated",
            actor_user_id=actor_user_id,
            context=context,
            account=account,
            metadata={
                "account_id": account.id,
                "customer_id": account.customer_id,
                "reason_present": bool(reason),
            },
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        return {"account": serialize_portal_account(account, customer)}

    async def unlock(
        self,
        account_id: int,
        actor_user_id: int,
        *,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        """Lift an automatic or administrative lock without resetting the password.

        Used after the failed-attempt lock so the customer can sign in again
        with the password they already know.
        """
        account = await self._get_or_404(account_id)
        if account.locked_at is None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "NOT_LOCKED",
                "This portal account is not locked",
            )

        account.is_active = True
        clear_lock(account)
        # Tokens issued before the lock must not be replayed now that the
        # account is usable again.
        account.token_version = (account.token_version or 0) + 1
        await self.repository.add_event(
            account_id=account.id,
            action="unlocked",
            actor_user_id=actor_user_id,
            note="Administrator unlock",
        )
        await self._record(
            event_type="portal_account.unlocked",
            actor_user_id=actor_user_id,
            context=context,
            account=account,
            metadata={
                "account_id": account.id,
                "customer_id": account.customer_id,
            },
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        return {"account": serialize_portal_account(account, customer)}

    async def reset_activation(
        self,
        account_id: int,
        actor_user_id: int,
        *,
        background: BackgroundTasks | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        account = await self._get_or_404(account_id)
        if account.activated_at is not None or account.password_hash is not None:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "ALREADY_ACTIVATED",
                "This portal account is already activated",
            )

        token, token_hash, expires_at = issue_activation_token()
        account.activation_token_hash = token_hash
        account.activation_expires_at = expires_at
        await self.repository.add_event(
            account_id=account.id,
            action="password_reset",
            actor_user_id=actor_user_id,
            note="Activation token reissued",
        )
        await self._record(
            event_type="portal_account.activation.reset",
            actor_user_id=actor_user_id,
            context=context,
            account=account,
            metadata={
                "account_id": account.id,
                "customer_id": account.customer_id,
            },
        )

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.repository.refresh(account)

        customer = await self.customer_repository.get_by_id(account.customer_id)
        await self._send_activation_email(
            account, customer, token, background=background
        )
        return {
            "account": serialize_portal_account(account, customer),
            "activation": serialize_activation(token, expires_at),
        }

    async def _send_activation_email(
        self,
        account: CustomerPortalAccount,
        customer: Any | None,
        token: str,
        *,
        background: BackgroundTasks | None = None,
    ) -> None:
        if self.email_service is None:
            return
        await deliver_or_queue(
            background,
            self.email_service.send_portal_activation,
            to=account.email,
            name=customer.name if customer is not None else "there",
            activation_url=(
                f"{settings.frontend_base_url}/portal/activate?token={token}"
            ),
            expires_hours=settings.customer_activation_ttl_hours,
        )

    async def _get_or_404(self, account_id: int) -> CustomerPortalAccount:
        account = await self.repository.get_by_id(account_id)
        if account is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Portal account with id {account_id} not found",
            )
        return account
