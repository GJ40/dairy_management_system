from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.email_config_resolver import EmailConfigResolver
from app.services.email_settings_crypto import EmailSettingsCrypto
from app.services.order_email_service import OrderEmailNotifier
from app.services.order_email_templates import (
    ORDER_EVENT_KEYS,
    OrderEmailContext,
    build_order_email,
)
from tests.test_email_settings import (
    KEY,
    FakeRepository,
    make_profile,
    make_sender,
    make_settings,
)

ORDER_NO = "ORD-20261106-AB12"


def make_context(**overrides) -> OrderEmailContext:
    values = {
        "order_no": ORDER_NO,
        "customer_name": "Asha Patel",
        "recipient_email": "asha@example.com",
        "requested_date": date(2026, 11, 7),
        "quantity_litres": Decimal("12.50"),
        "rate": Decimal("60.00"),
        "estimated_total": Decimal("750.00"),
        "note": "Leave at the gate",
        "reason": "Stock reserved for another route",
        "previous_status": "approved",
        "invoice_no": "INV-2026-0007",
        "balance": Decimal("750.00"),
    }
    values.update(overrides)
    return OrderEmailContext(**values)


class OrderEmailTemplateTests(unittest.TestCase):
    def test_every_order_event_renders_subject_html_and_text(self) -> None:
        context = make_context()

        for event_key in ORDER_EVENT_KEYS:
            with self.subTest(event_key=event_key):
                content = build_order_email(event_key, context)
                self.assertIn(ORDER_NO, content.subject)
                self.assertIn("AmritDhara Dairy", content.subject)
                self.assertIn("<html", content.html)
                self.assertIn(ORDER_NO, content.html)
                self.assertIn(ORDER_NO, content.text)
                self.assertNotIn("<html", content.text)
                self.assertIn("12.50 L", content.html)
                self.assertIn("12.50 L", content.text)

    def test_rejected_email_shows_the_reason(self) -> None:
        content = build_order_email(
            "order.rejected",
            make_context(reason="No stock for that route"),
        )

        self.assertIn("No stock for that route", content.html)
        self.assertIn("No stock for that route", content.text)

    def test_cancelled_email_shows_the_previous_status(self) -> None:
        content = build_order_email(
            "order.cancelled",
            make_context(previous_status="approved", reason="Customer called"),
        )

        self.assertIn("Approved", content.html)
        self.assertIn("Customer called", content.text)

    def test_fulfilled_email_shows_invoice_and_balance(self) -> None:
        content = build_order_email("order.fulfilled", make_context())

        self.assertIn("Rs. 750.00", content.html)
        self.assertIn("INV-2026-0007", content.html)
        self.assertIn("INV-2026-0007", content.text)
        self.assertIn("Rs. 750.00", content.text)

    def test_customer_text_is_escaped(self) -> None:
        content = build_order_email(
            "order.submitted",
            make_context(customer_name="<script>alert(1)</script>"),
        )

        self.assertNotIn("<script>alert(1)</script>", content.html)
        self.assertIn("&lt;script&gt;", content.html)

    def test_unknown_event_key_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            build_order_email("order.unknown", make_context())


class FakeEmailService:
    def __init__(self, *, result: bool = True) -> None:
        self.result = result
        self.sent: list[dict[str, object]] = []

    async def send_with_config(
        self,
        config,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> bool:
        self.sent.append(
            {
                "config": config,
                "to": to,
                "subject": subject,
                "html": html,
                "text": text,
            }
        )
        return self.result


class FakeOrderRepository:
    def __init__(
        self,
        order,
        account,
        *,
        sale=None,
        invoice=None,
        events=None,
    ) -> None:
        self.order = order
        self.account = account
        self.sale = sale
        self.invoice = invoice
        self.events = events or []

    async def get_by_id(self, order_id: int):
        if self.order is None or self.order.id != order_id:
            return None
        return self.order

    async def get_account(self, account_id: int):
        return self.account

    async def get_sale_by_order_id(self, order_id: int):
        return self.sale

    async def get_invoice_for_sale(self, sale_id: int):
        return self.invoice

    async def list_events(self, order_id: int):
        return self.events


class FakeCustomerRepository:
    def __init__(self, customer) -> None:
        self.customer = customer

    async def get_by_id(self, customer_id: int):
        return self.customer


def make_order_row(**overrides) -> SimpleNamespace:
    values = {
        "id": 7,
        "order_no": ORDER_NO,
        "account_id": 1,
        "customer_id": 4,
        "requested_date": date(2026, 11, 7),
        "quantity_litres": Decimal("12.50"),
        "rate_snapshot": Decimal("60.00"),
        "estimated_total": Decimal("750.00"),
        "note": "Leave at the gate",
        "reason": "Stock reserved for another route",
        "status": "submitted",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class OrderEmailNotifierTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.email_service = FakeEmailService()
        self.order = make_order_row()
        self.account = SimpleNamespace(id=1, email="Asha@Example.com")
        self.customer = SimpleNamespace(id=4, name="Asha Patel")
        self.invoice = SimpleNamespace(
            id=3,
            invoice_no="INV-2026-0007",
            total_amount=Decimal("750.00"),
            paid_amount=Decimal("0.00"),
        )
        self.notifier = self._notifier()

    def _notifier(self, **kwargs) -> OrderEmailNotifier:
        resolver = EmailConfigResolver(
            self.repository,
            crypto=kwargs.pop("crypto", EmailSettingsCrypto(KEY)),
            settings_obj=make_settings(),
        )
        return OrderEmailNotifier(
            settings_repository=self.repository,
            order_repository=FakeOrderRepository(
                self.order,
                self.account,
                sale=SimpleNamespace(id=2, amount=Decimal("750.00")),
                invoice=self.invoice,
                events=kwargs.pop("events", []),
            ),
            customer_repository=FakeCustomerRepository(self.customer),
            resolver=resolver,
            email_service=self.email_service,
        )

    async def test_environment_sender_used_without_a_mapping(self) -> None:
        sent = await self.notifier.notify("order.submitted", 7)

        self.assertTrue(sent)
        self.assertEqual(len(self.email_service.sent), 1)
        message = self.email_service.sent[0]
        self.assertEqual(message["to"], "asha@example.com")
        self.assertIn(ORDER_NO, str(message["subject"]))
        self.assertEqual(message["config"].source, "environment")
        self.assertEqual(message["config"].from_email, "no-reply@dairyfarm.com")

    async def test_mapping_sender_is_used(self) -> None:
        self.repository.identities = {
            2: make_sender(
                id=2,
                display_name="Orders",
                email="orders@example.com",
                reply_to_email=None,
            )
        }
        self.repository.mappings = {
            "event:order.approved": SimpleNamespace(
                sender_identity_id=2,
                reply_to_sender_identity_id=None,
                is_enabled=True,
            )
        }

        sent = await self.notifier.notify("order.approved", 7)

        self.assertTrue(sent)
        config = self.email_service.sent[0]["config"]
        self.assertEqual(config.from_email, "orders@example.com")
        self.assertIsNone(config.reply_to_email)

    async def test_disabled_event_sends_nothing(self) -> None:
        self.repository.mappings = {
            "event:order.submitted": SimpleNamespace(
                sender_identity_id=None,
                reply_to_sender_identity_id=None,
                is_enabled=False,
            )
        }

        sent = await self.notifier.notify("order.submitted", 7)

        self.assertFalse(sent)
        self.assertEqual(self.email_service.sent, [])

    async def test_missing_order_sends_nothing(self) -> None:
        sent = await self.notifier.notify("order.submitted", 999)

        self.assertFalse(sent)
        self.assertEqual(self.email_service.sent, [])

    async def test_missing_recipient_sends_nothing(self) -> None:
        self.account.email = "   "

        sent = await self.notifier.notify("order.submitted", 7)

        self.assertFalse(sent)
        self.assertEqual(self.email_service.sent, [])

    async def test_unknown_event_sends_nothing(self) -> None:
        sent = await self.notifier.notify("order.unknown", 7)

        self.assertFalse(sent)
        self.assertEqual(self.email_service.sent, [])

    async def test_send_failure_is_swallowed(self) -> None:
        self.email_service.result = False

        sent = await self.notifier.notify("order.submitted", 7)

        self.assertFalse(sent)
        self.assertEqual(len(self.email_service.sent), 1)

    async def test_unreadable_credentials_skip_the_send(self) -> None:
        self.repository.profiles[1] = make_profile(
            status="active",
            active_slot=1,
            auth_enabled=True,
            username_encrypted="user-cipher",
            password_encrypted="pass-cipher",
        )
        notifier = self._notifier(crypto=EmailSettingsCrypto(None))

        sent = await notifier.notify("order.submitted", 7)

        self.assertFalse(sent)
        self.assertEqual(self.email_service.sent, [])

    async def test_cancelled_notification_carries_the_previous_status(self) -> None:
        previous = SimpleNamespace(id=11, from_status="approved", to_status="cancelled")
        notifier = self._notifier(events=[previous])

        sent = await notifier.notify("order.cancelled", 7)

        self.assertTrue(sent)
        message = self.email_service.sent[0]
        self.assertIn("Approved", str(message["html"]))


if __name__ == "__main__":
    unittest.main()
