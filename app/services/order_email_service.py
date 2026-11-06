"""Send customer order notifications.

Phase 7 wires the resolver into a real workflow for the first time: after an
order is committed, one of the five catalogue events is dispatched and

1. the event's own mapping row decides whether the notification is enabled,
2. :class:`EmailConfigResolver` picks the transport, From and Reply-To,
3. the message is rendered by :mod:`app.services.order_email_templates`, and
4. :meth:`EmailService.send_with_config` delivers it.

Nothing here may raise into the request: a mail problem must never fail an
order, so every failure is logged and reported as ``False``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
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
from app.services.email_workflow_catalogue import EVENT_SCOPE, get_event, mapping_key
from app.services.internal_notification_service import (
    order_notification_payload,
    send_internal_notification,
)
from app.services.order_email_templates import (
    ORDER_CANCELLED,
    ORDER_EVENT_KEYS,
    ORDER_SUBMITTED,
    OrderEmailContext,
    build_order_email,
)

logger = logging.getLogger(__name__)

# Every order event lives under the Customer Orders category, which is what the
# category-level mapping row applies to when the event row has no sender.
ORDER_EMAIL_CATEGORY = "customer_orders"

OrderEmailDispatch = Callable[..., Awaitable[Any]]


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):  # pragma: no cover - defensive
        return None


class OrderEmailNotifier:
    """Loads one order and sends its notification through the resolver."""

    def __init__(
        self,
        *,
        settings_repository: EmailSettingsRepository,
        order_repository: CustomerOrderRepository,
        customer_repository: CustomerRepository,
        resolver: EmailConfigResolver,
        email_service: EmailService | None = None,
    ) -> None:
        self.settings_repository = settings_repository
        self.order_repository = order_repository
        self.customer_repository = customer_repository
        self.resolver = resolver
        self.email_service = email_service or EmailService()

    async def notify(self, event_key: str, order_id: int) -> bool:
        """Send one order notification; returns whether a message was sent."""
        if event_key not in ORDER_EVENT_KEYS:
            logger.warning(
                "Ignoring unknown order notification %r for order %s",
                event_key,
                order_id,
            )
            return False

        event = get_event(event_key)
        if event is None or not event.implemented:
            logger.warning(
                "Order notification %r is not sendable; nothing sent for order %s",
                event_key,
                order_id,
            )
            return False

        try:
            if not await self._is_enabled(event_key):
                logger.info(
                    "Order notification %r is disabled in the workflow mappings; "
                    "nothing sent for order %s",
                    event_key,
                    order_id,
                )
                return False

            context = await self._load_context(event_key, order_id)
            if context is None:
                return False
            if not context.recipient_email:
                logger.info(
                    "Order %s has no portal email address; %r not sent",
                    context.order_no,
                    event_key,
                )
                return False

            config = await self.resolver.resolve(
                event_key,
                category_key=ORDER_EMAIL_CATEGORY,
            )
            content = build_order_email(event_key, context)
            return await self.email_service.send_with_config(
                config,
                to=context.recipient_email,
                subject=content.subject,
                html=content.html,
                text=content.text,
            )
        except EmailConfigurationError as exc:
            logger.warning(
                "Order notification %r for order %s skipped: %s (%s)",
                event_key,
                order_id,
                exc,
                exc.code,
            )
            return False
        except Exception:
            logger.exception(
                "Order notification %r for order %s failed", event_key, order_id
            )
            return False

    async def _is_enabled(self, event_key: str) -> bool:
        mapping = await self.settings_repository.get_mapping(
            mapping_key(EVENT_SCOPE, event_key)
        )
        if mapping is None:
            # No row means "no override": the notification keeps its default
            # enabled state.
            return True
        return bool(mapping.is_enabled)

    async def _load_context(
        self,
        event_key: str,
        order_id: int,
    ) -> OrderEmailContext | None:
        order = await self.order_repository.get_by_id(order_id)
        if order is None:
            logger.warning("Order %s not found; no notification sent", order_id)
            return None

        account = await self.order_repository.get_account(order.account_id)
        if account is None:
            logger.warning(
                "Order %s has no portal account; no notification sent", order.order_no
            )
            return None

        customer = await self.customer_repository.get_by_id(order.customer_id)
        sale = await self.order_repository.get_sale_by_order_id(order.id)
        invoice = (
            await self.order_repository.get_invoice_for_sale(sale.id)
            if sale is not None
            else None
        )

        previous_status = None
        if event_key == ORDER_CANCELLED:
            events = await self.order_repository.list_events(order.id)
            if events:
                previous_status = getattr(events[-1], "from_status", None)

        balance = None
        if invoice is not None:
            total = _decimal(getattr(invoice, "total_amount", None)) or Decimal("0")
            paid = _decimal(getattr(invoice, "paid_amount", None)) or Decimal("0")
            balance = total - paid

        return OrderEmailContext(
            order_no=order.order_no,
            customer_name=getattr(customer, "name", "") or "",
            recipient_email=(account.email or "").strip().lower(),
            requested_date=order.requested_date,
            quantity_litres=_decimal(order.quantity_litres) or Decimal("0"),
            rate=_decimal(order.rate_snapshot) or Decimal("0"),
            estimated_total=_decimal(order.estimated_total) or Decimal("0"),
            note=order.note,
            reason=order.reason,
            previous_status=previous_status,
            invoice_no=getattr(invoice, "invoice_no", None) if invoice else None,
            balance=balance,
        )


def _crypto_from_settings():
    return crypto_from_settings(app_settings)


async def dispatch_order_email(event_key: str, order_id: int) -> None:
    """Background task entry point: own session, never raises.

    FastAPI runs this after the response, by which time the request's database
    session may already be closed, so the notification reads through its own
    session instead of borrowing the request's.
    """
    try:
        async with SessionLocal() as session:
            settings_repository = EmailSettingsRepository(session)
            notifier = OrderEmailNotifier(
                settings_repository=settings_repository,
                order_repository=CustomerOrderRepository(session),
                customer_repository=CustomerRepository(session),
                resolver=EmailConfigResolver(
                    settings_repository,
                    crypto=_crypto_from_settings(),
                ),
            )
            await notifier.notify(event_key, order_id)

            # Internal observers are additional: they get their own summary
            # even when the customer's own message was skipped.
            if event_key == ORDER_SUBMITTED:
                payload = await order_notification_payload(
                    notifier.order_repository,
                    notifier.customer_repository,
                    order_id,
                )
                if payload is not None:
                    await send_internal_notification(
                        session,
                        ORDER_SUBMITTED,
                        payload,
                    )
    except Exception:
        logger.exception(
            "Dispatching order notification %r for order %s failed",
            event_key,
            order_id,
        )
