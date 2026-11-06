"""Deliver internal notification copies to the configured recipients.

Rules this module enforces:

* one message per active recipient — never a shared ``To``/``Bcc`` list, so a
  recipient can never learn another recipient's address;
* the customer's own message is not reused: internal copies are summaries with
  no links, tokens, passwords or bill details;
* a category-level recipient covers every event in that category, and a person
  configured at both levels receives **one** message;
* delivery is best effort — every failure is logged and swallowed, because a
  mail problem must never fail a sign-in or an order.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings as app_settings
from app.db.session import SessionLocal
from app.repositories.customer_order_repository import CustomerOrderRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.email_settings_repository import EmailSettingsRepository
from app.services.email_config_resolver import (
    EmailConfigResolver,
    EmailConfigurationError,
)
from app.services.email_service import EmailService
from app.services.email_settings_crypto import crypto_from_settings
from app.services.email_workflow_catalogue import (
    CATEGORY_SCOPE,
    EVENT_SCOPE,
    category_of_event,
    get_event,
    mapping_key,
)
from app.services.internal_email_templates import (
    InternalEmailContext,
    build_internal_email,
)
from app.utils.time import utc_now_naive

logger = logging.getLogger(__name__)


class InternalNotificationSender:
    """Resolve recipients for one event and send each of them a summary."""

    def __init__(
        self,
        *,
        settings_repository: EmailSettingsRepository,
        resolver: EmailConfigResolver,
        email_service: EmailService | None = None,
    ) -> None:
        self.settings_repository = settings_repository
        self.resolver = resolver
        self.email_service = email_service or EmailService()

    async def recipient_emails(self, event_key: str) -> list[str]:
        """Active, de-duplicated addresses for the event and its category."""
        keys = [mapping_key(EVENT_SCOPE, event_key)]
        category_key = category_of_event(event_key)
        if category_key:
            keys.append(mapping_key(CATEGORY_SCOPE, category_key))

        rows = await self.settings_repository.list_active_recipients_for_keys(keys)
        emails: list[str] = []
        seen: set[str] = set()
        for row in rows:
            email = (row.email or "").strip().lower()
            if not email or email in seen:
                continue
            seen.add(email)
            emails.append(email)
        return emails

    async def _is_enabled(self, event_key: str) -> bool:
        mapping = await self.settings_repository.get_mapping(
            mapping_key(EVENT_SCOPE, event_key)
        )
        if mapping is None:
            # No row means "no override": the event keeps its default state.
            return True
        return bool(mapping.is_enabled)

    async def notify(self, event_key: str, context: InternalEmailContext) -> int:
        """Send one summary per recipient; returns how many were delivered."""
        event = get_event(event_key)
        if event is None or not event.implemented:
            logger.warning(
                "Internal notification %r is not sendable; nothing sent", event_key
            )
            return 0

        try:
            if not await self._is_enabled(event_key):
                logger.info(
                    "Internal notification %r is disabled in the workflow "
                    "mappings; nothing sent",
                    event_key,
                )
                return 0

            recipients = await self.recipient_emails(event_key)
            if not recipients:
                logger.info(
                    "No active internal recipients for %r; nothing sent", event_key
                )
                return 0

            config = await self.resolver.resolve(
                event_key,
                category_key=event.category_key,
            )
            content = build_internal_email(context)
            delivered = 0
            for recipient in recipients:
                try:
                    sent = await self.email_service.send_with_config(
                        config,
                        to=recipient,
                        subject=content.subject,
                        html=content.html,
                        text=content.text,
                    )
                except Exception:
                    logger.exception(
                        "Internal notification %r to %s raised", event_key, recipient
                    )
                    sent = False
                if sent:
                    delivered += 1

            logger.info(
                "Internal notification %r delivered to %s of %s recipient(s)",
                event_key,
                delivered,
                len(recipients),
            )
            return delivered
        except EmailConfigurationError as exc:
            logger.warning(
                "Internal notification %r skipped: %s (%s)",
                event_key,
                exc,
                exc.code,
            )
            return 0
        except Exception:
            logger.exception("Internal notification %r failed", event_key)
            return 0


async def send_internal_notification(
    session: Any,
    event_key: str,
    payload: dict[str, Any] | None,
) -> int:
    """Send with a caller-provided session; never raises."""
    try:
        context = InternalEmailContext.from_payload(event_key, payload)
        if context is None:
            logger.warning(
                "Internal notification %r skipped: the payload is incomplete",
                event_key,
            )
            return 0

        settings_repository = EmailSettingsRepository(session)
        sender = InternalNotificationSender(
            settings_repository=settings_repository,
            resolver=EmailConfigResolver(
                settings_repository,
                crypto=crypto_from_settings(app_settings),
            ),
        )
        return await sender.notify(event_key, context)
    except Exception:
        logger.exception("Internal notification %r failed", event_key)
        return 0


async def dispatch_internal_notification(
    event_key: str,
    payload: dict[str, Any] | None,
) -> int:
    """Background entry point with its own session; never raises."""
    try:
        async with SessionLocal() as session:
            return await send_internal_notification(session, event_key, payload)
    except Exception:
        logger.exception(
            "Dispatching internal notification %r failed", event_key
        )
        return 0


async def order_notification_payload(
    order_repository: CustomerOrderRepository,
    customer_repository: CustomerRepository,
    order_id: int,
) -> dict[str, Any] | None:
    """Plain values for the ``order.submitted`` internal summary."""
    order = await order_repository.get_by_id(order_id)
    if order is None:
        return None
    account = await order_repository.get_account(order.account_id)
    customer = await customer_repository.get_by_id(order.customer_id)
    return {
        "occurred_at": utc_now_naive().isoformat(),
        "account_email": getattr(account, "email", None),
        "account_name": getattr(customer, "name", None),
        "order_no": order.order_no,
        "customer_name": getattr(customer, "name", None),
        "requested_date": (
            order.requested_date.isoformat() if order.requested_date else None
        ),
        "quantity_litres": (
            str(order.quantity_litres) if order.quantity_litres is not None else None
        ),
        "note": order.note,
    }
