from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.services.email_config_resolver import EmailMessageConfig, EmailTransportConfig
from app.services.payment_email_templates import (
    PaymentReceiptContext,
    build_payment_receipt,
)
from app.services.payment_receipt_service import PaymentReceiptNotifier

CONFIG = EmailMessageConfig(
    source="database",
    transport=EmailTransportConfig(
        host="smtp.example.com",
        port=587,
        auth_enabled=False,
        encryption_mode="starttls",
        timeout_seconds=10,
    ),
    from_name="Accounts",
    from_email="accounts@example.com",
    reply_to_email=None,
)


def make_invoice(**overrides: Any) -> SimpleNamespace:
    invoice = SimpleNamespace(
        id=7,
        invoice_no="INV-20261106-AB12",
        customer_id=4,
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 5),
        total_amount=Decimal("500.00"),
        paid_amount=Decimal("200.00"),
        status="partial",
    )
    for key, value in overrides.items():
        setattr(invoice, key, value)
    return invoice


def make_customer() -> SimpleNamespace:
    return SimpleNamespace(id=4, name="Ramesh Patil")


def make_account(**overrides: Any) -> SimpleNamespace:
    account = SimpleNamespace(
        id=1,
        customer_id=4,
        email="customer@example.com",
        is_active=True,
    )
    for key, value in overrides.items():
        setattr(account, key, value)
    return account


class FakeSettingsRepository:
    def __init__(self, enabled: bool | None = None) -> None:
        self.enabled = enabled
        self.keys: list[str] = []

    async def get_mapping(self, key: str):
        self.keys.append(key)
        if self.enabled is None:
            return None
        return SimpleNamespace(is_enabled=self.enabled)


class FakeInvoiceRepository:
    def __init__(self, invoice: SimpleNamespace | None) -> None:
        self.invoice = invoice
        self.requested: list[int] = []

    async def get_by_id(self, invoice_id: int):
        self.requested.append(invoice_id)
        return self.invoice


class FakeCustomerRepository:
    def __init__(self, customer: SimpleNamespace | None) -> None:
        self.customer = customer

    async def get_by_id(self, customer_id: int):
        return self.customer


class FakePortalAccountRepository:
    def __init__(self, account: SimpleNamespace | None) -> None:
        self.account = account
        self.requested: list[int] = []

    async def get_by_customer_id(self, customer_id: int):
        self.requested.append(customer_id)
        return self.account


class RecordingResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def resolve(self, event_key: str, *, category_key: str | None = None):
        self.calls.append((event_key, category_key))
        return CONFIG


class RecordingEmailService:
    def __init__(self, sent: bool = True) -> None:
        self.sent = sent
        self.calls: list[dict[str, Any]] = []

    async def send_with_config(self, config: Any, **kwargs: Any) -> bool:
        self.calls.append({"config": config, **kwargs})
        return self.sent


_UNSET = object()


class PaymentReceiptNotifierTests(unittest.IsolatedAsyncioTestCase):
    def _build(
        self,
        *,
        invoice: SimpleNamespace | None = _UNSET,  # type: ignore[assignment]
        customer: SimpleNamespace | None = _UNSET,  # type: ignore[assignment]
        account: SimpleNamespace | None = _UNSET,  # type: ignore[assignment]
        enabled: bool | None = None,
        sent: bool = True,
    ) -> PaymentReceiptNotifier:
        self.settings = FakeSettingsRepository(enabled)
        self.invoices = FakeInvoiceRepository(
            make_invoice() if invoice is _UNSET else invoice
        )
        self.customers = FakeCustomerRepository(
            make_customer() if customer is _UNSET else customer
        )
        self.accounts = FakePortalAccountRepository(
            make_account() if account is _UNSET else account
        )
        self.resolver = RecordingResolver()
        self.email = RecordingEmailService(sent=sent)
        return PaymentReceiptNotifier(
            settings_repository=self.settings,  # type: ignore[arg-type]
            invoice_repository=self.invoices,  # type: ignore[arg-type]
            customer_repository=self.customers,  # type: ignore[arg-type]
            account_repository=self.accounts,  # type: ignore[arg-type]
            resolver=self.resolver,  # type: ignore[arg-type]
            email_service=self.email,  # type: ignore[arg-type]
        )

    async def test_receipt_goes_to_the_portal_address(self) -> None:
        notifier = self._build()

        sent = await notifier.notify(7, "200.00")

        self.assertTrue(sent)
        self.assertEqual(len(self.email.calls), 1)
        call = self.email.calls[0]
        self.assertEqual(call["to"], "customer@example.com")
        self.assertIn("INV-20261106-AB12", call["subject"])
        self.assertIn("Rs. 200.00", call["html"])
        self.assertIn("Rs. 300.00", call["html"])
        self.assertEqual(
            self.resolver.calls,
            [("billing.payment_received", "billing_payments")],
        )

    async def test_no_portal_account_means_no_message(self) -> None:
        notifier = self._build(account=None)

        sent = await notifier.notify(7, "200.00")

        self.assertFalse(sent)
        self.assertEqual(self.email.calls, [])
        self.assertEqual(self.resolver.calls, [])

    async def test_inactive_account_means_no_message(self) -> None:
        notifier = self._build(account=make_account(is_active=False))

        sent = await notifier.notify(7, "200.00")

        self.assertFalse(sent)
        self.assertEqual(self.email.calls, [])

    async def test_disabled_mapping_skips_the_receipt(self) -> None:
        notifier = self._build(enabled=False)

        sent = await notifier.notify(7, "200.00")

        self.assertFalse(sent)
        self.assertEqual(self.email.calls, [])
        self.assertEqual(
            self.settings.keys, ["event:billing.payment_received"]
        )

    async def test_missing_invoice_means_no_message(self) -> None:
        notifier = self._build(invoice=None)

        sent = await notifier.notify(7, "200.00")

        self.assertFalse(sent)
        self.assertEqual(self.email.calls, [])

    async def test_delivery_failure_is_reported_not_raised(self) -> None:
        notifier = self._build(sent=False)

        sent = await notifier.notify(7, "200.00")

        self.assertFalse(sent)


class PaymentReceiptTemplateTests(unittest.TestCase):
    def _context(self, **overrides: Any) -> PaymentReceiptContext:
        values: dict[str, Any] = {
            "invoice_no": "INV-20261106-AB12",
            "customer_name": "Ramesh Patil",
            "payment_amount": Decimal("500.00"),
            "paid_amount": Decimal("500.00"),
            "total_amount": Decimal("500.00"),
            "balance": Decimal("0.00"),
            "status": "paid",
            "period_start": date(2026, 11, 1),
            "period_end": date(2026, 11, 5),
        }
        values.update(overrides)
        return PaymentReceiptContext(**values)

    def test_settled_invoice_says_so(self) -> None:
        content = build_payment_receipt(self._context())

        self.assertIn("Paid in full", content.html)
        self.assertIn("Paid in full", content.text)
        self.assertIn("INV-20261106-AB12", content.subject)
        self.assertIn("Rs. 500.00", content.text)
        self.assertIn("01 Nov 2026 - 05 Nov 2026", content.text)
        self.assertNotIn("token", content.text.lower())
        self.assertNotIn("password", content.text.lower())

    def test_partial_payment_states_the_balance(self) -> None:
        content = build_payment_receipt(
            self._context(
                payment_amount=Decimal("200.00"),
                paid_amount=Decimal("200.00"),
                balance=Decimal("300.00"),
                status="partial",
            )
        )

        self.assertIn("Partly paid", content.html)
        self.assertIn("Rs. 300.00", content.text)
        self.assertNotIn("nothing further is needed", content.text.lower())

    def test_customer_name_is_escaped(self) -> None:
        content = build_payment_receipt(
            self._context(customer_name="<script>alert(1)</script>")
        )

        self.assertNotIn("<script>alert(1)</script>", content.html)
        self.assertIn("&lt;script&gt;", content.html)
