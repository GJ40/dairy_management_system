"""Deliver the customer receipt for a recorded invoice payment.

Same contract as the order notifications:

1. the event's own mapping row decides whether the receipt is enabled,
2. :class:`EmailConfigResolver` picks the transport, From and Reply-To,
3. the message is rendered by :mod:`app.services.payment_email_templates`,
4. :meth:`EmailService.send_with_config` delivers it.

Nothing here may raise into the request: a mail problem must never fail a
payment being recorded, so every failure is logged and reported as ``False``.
A customer without an active portal account gets no receipt - the invoice is
still visible to staff, and inventing a recipient would leak billing detail.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import settings as app_settings
from app.db.session import SessionLocal
from app.repositories.customer_portal_account_repository import (
    CustomerPortalAccountRepository,
)
from app.repositories.customer_repository import CustomerRepository
from app.repositories.email_settings_repository import EmailSettingsRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.services.email_config_resolver import (
    EmailConfigResolver,
    EmailConfigurationError,
)
from app.services.email_service import EmailService
from app.services.email_settings_crypto import crypto_from_settings
from app.services.email_workflow_catalogue import EVENT_SCOPE, get_event, mapping_key
from app.services.payment_email_templates import (
    PAYMENT_RECEIVED,
    PaymentReceiptContext,
    build_payment_receipt,
)

logger = logging.getLogger(__name__)

# Every billing event lives under the Billing & Payments category, which is
# what the category-level mapping row applies to when the event row has no
# sender.
PAYMENT_EMAIL_CATEGORY = "billing_payments"


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):  # pragma: no cover - defensive
        return Decimal("0")


class PaymentReceiptNotifier:
    """Loads one invoice and sends its receipt through the resolver."""

    def __init__(
        self,
        *,
        settings_repository: EmailSettingsRepository,
        invoice_repository: InvoiceRepository,
        customer_repository: CustomerRepository,
        account_repository: CustomerPortalAccountRepository,
        resolver: EmailConfigResolver,
        email_service: EmailService | None = None,
    ) -> None:
        self.settings_repository = settings_repository
        self.invoice_repository = invoice_repository
        self.customer_repository = customer_repository
        self.account_repository = account_repository
        self.resolver = resolver
        self.email_service = email_service or EmailService()

    async def notify(self, invoice_id: int, payment_amount: Any) -> bool:
        """Send one receipt; returns whether a message was sent."""
        event = get_event(PAYMENT_RECEIVED)
        if event is None or not event.implemented:
            logger.warning(
                "Payment receipt %r is not sendable; nothing sent for invoice %s",
                PAYMENT_RECEIVED,
                invoice_id,
            )
            return False

        try:
            if not await self._is_enabled():
                logger.info(
                    "Payment receipt %r is disabled in the workflow mappings; "
                    "nothing sent for invoice %s",
                    PAYMENT_RECEIVED,
                    invoice_id,
                )
                return False

            invoice = await self.invoice_repository.get_by_id(invoice_id)
            if invoice is None:
                logger.warning(
                    "Invoice %s not found; no receipt sent", invoice_id
                )
                return False

            account = await self.account_repository.get_by_customer_id(
                invoice.customer_id
            )
            recipient = ""
            if account is not None and account.is_active:
                recipient = (account.email or "").strip().lower()
            if not recipient:
                logger.info(
                    "Customer %s has no active portal address; %r not sent for "
                    "invoice %s",
                    invoice.customer_id,
                    PAYMENT_RECEIVED,
                    invoice.invoice_no,
                )
                return False

            customer = await self.customer_repository.get_by_id(
                invoice.customer_id
            )
            total = _decimal(getattr(invoice, "total_amount", None))
            paid = _decimal(getattr(invoice, "paid_amount", None))
            context = PaymentReceiptContext(
                invoice_no=invoice.invoice_no,
                customer_name=getattr(customer, "name", "") or "",
                payment_amount=_decimal(payment_amount),
                paid_amount=paid,
                total_amount=total,
                balance=total - paid,
                status=getattr(invoice, "status", "") or "",
                period_start=getattr(invoice, "period_start", None),
                period_end=getattr(invoice, "period_end", None),
            )

            config = await self.resolver.resolve(
                PAYMENT_RECEIVED,
                category_key=PAYMENT_EMAIL_CATEGORY,
            )
            content = build_payment_receipt(context)
            return await self.email_service.send_with_config(
                config,
                to=recipient,
                subject=content.subject,
                html=content.html,
                text=content.text,
            )
        except EmailConfigurationError as exc:
            logger.warning(
                "Payment receipt for invoice %s skipped: %s (%s)",
                invoice_id,
                exc,
                exc.code,
            )
            return False
        except Exception:
            logger.exception(
                "Payment receipt for invoice %s failed", invoice_id
            )
            return False

    async def _is_enabled(self) -> bool:
        mapping = await self.settings_repository.get_mapping(
            mapping_key(EVENT_SCOPE, PAYMENT_RECEIVED)
        )
        if mapping is None:
            # No row means "no override": the receipt keeps its default
            # enabled state.
            return True
        return bool(mapping.is_enabled)


def _crypto_from_settings():
    return crypto_from_settings(app_settings)


async def dispatch_payment_receipt(
    invoice_id: int,
    payment_amount: str,
) -> None:
    """Background task entry point: own session, never raises.

    FastAPI runs this after the response, by which time the request's database
    session may already be closed, so the receipt reads through its own session
    instead of borrowing the request's.
    """
    try:
        async with SessionLocal() as session:
            settings_repository = EmailSettingsRepository(session)
            notifier = PaymentReceiptNotifier(
                settings_repository=settings_repository,
                invoice_repository=InvoiceRepository(session),
                customer_repository=CustomerRepository(session),
                account_repository=CustomerPortalAccountRepository(session),
                resolver=EmailConfigResolver(
                    settings_repository,
                    crypto=_crypto_from_settings(),
                ),
            )
            await notifier.notify(invoice_id, payment_amount)
    except Exception:
        logger.exception(
            "Dispatching payment receipt for invoice %s failed", invoice_id
        )
