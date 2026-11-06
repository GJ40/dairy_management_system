from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.core.config import settings
from app.models.email_notification_recipient import EmailNotificationRecipient
from app.services.email_config_resolver import EmailConfigResolver
from app.services.email_settings_crypto import EmailSettingsCrypto
from app.services.internal_email_templates import (
    InternalEmailContext,
    build_internal_email,
)
from app.services.internal_notification_service import (
    InternalNotificationSender,
    order_notification_payload,
)
from app.services.login_security_service import LoginSecurityService
from tests.test_email_settings import KEY, FakeRepository, make_settings


class FakeEmailService:
    def __init__(self, *, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
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
        if to in self.fail_for:
            raise RuntimeError("smtp exploded")
        self.sent.append(
            {
                "config": config,
                "to": to,
                "subject": subject,
                "html": html,
                "text": text,
            }
        )
        return True

    @property
    def recipients(self) -> list[str]:
        return [str(message["to"]) for message in self.sent]


def make_recipient(
    email: str,
    *,
    mapping_key: str = "event:order.submitted",
    scope: str = "event",
    is_active: bool = True,
) -> EmailNotificationRecipient:
    return EmailNotificationRecipient(
        scope=scope,
        mapping_key=mapping_key,
        email=email,
        is_active=is_active,
    )


def order_payload(**overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "occurred_at": "2026-11-06T09:30:00",
        "account_email": "asha@example.com",
        "account_name": "Asha Patel",
        "order_no": "ORD-20261106-AB12",
        "customer_name": "Asha Patel",
        "requested_date": "2026-11-07",
        "quantity_litres": "12.50",
        "note": "Leave at the gate",
    }
    payload.update(overrides)
    return payload


def alert_payload(**overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "occurred_at": "2026-11-06T09:30:00",
        "account_email": "staff@example.com",
        "account_name": "Staff User",
        "failure_count": 5,
        "window_minutes": 15,
    }
    payload.update(overrides)
    return payload


class InternalTemplateTests(unittest.TestCase):
    def test_order_summary_contains_the_facts_and_no_links(self) -> None:
        context = InternalEmailContext.from_payload(
            "order.submitted", order_payload()
        )
        assert context is not None

        content = build_internal_email(context)

        self.assertIn("[Internal] Order submitted", content.subject)
        self.assertIn("ORD-20261106-AB12", content.subject)
        self.assertIn("ORD-20261106-AB12", content.html)
        self.assertIn("Asha Patel", content.text)
        self.assertIn("12.50 L", content.html)
        self.assertIn("07 Nov 2026", content.text)
        self.assertIn("Internal only", content.html)
        self.assertNotIn("http", content.html.lower())
        self.assertNotIn("token", content.text.lower())
        self.assertIn("ORD-20261106-AB12", content.text)

    def test_security_summary_names_the_attempts(self) -> None:
        context = InternalEmailContext.from_payload(
            "account.staff_failed_login_alert", alert_payload()
        )
        assert context is not None

        content = build_internal_email(context)

        self.assertIn("Staff failed-login alert", content.subject)
        self.assertIn("staff@example.com", content.subject)
        self.assertIn("Failed attempts", content.text)
        self.assertIn("5", content.text)
        self.assertIn("15 minutes", content.html)

    def test_customer_text_is_escaped(self) -> None:
        context = InternalEmailContext.from_payload(
            "order.submitted",
            order_payload(
                customer_name="<script>alert(1)</script>",
                note="<b>x</b>",
            ),
        )
        assert context is not None

        content = build_internal_email(context)

        self.assertNotIn("<script>alert(1)</script>", content.html)
        self.assertIn("&lt;script&gt;", content.html)
        self.assertNotIn("<b>x</b>", content.html)

    def test_payload_needs_the_event_specific_facts(self) -> None:
        self.assertIsNone(
            InternalEmailContext.from_payload(
                "order.submitted", order_payload(order_no=None)
            )
        )
        self.assertIsNone(
            InternalEmailContext.from_payload(
                "account.customer_account_locked", alert_payload(account_email=None)
            )
        )
        self.assertIsNone(
            InternalEmailContext.from_payload("order.unknown", order_payload())
        )

    def test_payload_parses_dates_and_quantity(self) -> None:
        context = InternalEmailContext.from_payload(
            "order.submitted", order_payload()
        )
        assert context is not None

        self.assertEqual(context.requested_date, date(2026, 11, 7))
        self.assertEqual(context.quantity_litres, Decimal("12.50"))
        self.assertEqual(
            context.occurred_at,
            datetime(2026, 11, 6, 9, 30, tzinfo=None),
        )


class SupportQueryInternalTests(unittest.TestCase):
    def _payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "occurred_at": "2026-11-06T09:30:00",
            "account_email": "asha@example.com",
            "account_name": "Asha Patel",
            "query_no": "QRY-20261106-AB12",
            "query_subject": "Invoice question",
            "query_category": "billing",
        }
        payload.update(overrides)
        return payload

    def test_summary_names_the_query(self) -> None:
        context = InternalEmailContext.from_payload(
            "support.query_received", self._payload()
        )
        assert context is not None

        content = build_internal_email(context)

        self.assertIn("[Internal] Support query received", content.subject)
        self.assertIn("QRY-20261106-AB12", content.subject)
        self.assertIn("Invoice question", content.text)
        self.assertIn("Billing", content.text)
        self.assertIn("asha@example.com", content.text)
        self.assertIn("support query", content.text.lower())
        # The order wording must not leak into a support copy.
        self.assertNotIn("placed a new order", content.text.lower())
        self.assertNotIn("http", content.html.lower())

    def test_query_number_is_required(self) -> None:
        self.assertIsNone(
            InternalEmailContext.from_payload(
                "support.query_received", self._payload(query_no=None)
            )
        )

    def test_subject_is_escaped(self) -> None:
        context = InternalEmailContext.from_payload(
            "support.query_received",
            self._payload(query_subject="<script>alert(1)</script>"),
        )
        assert context is not None

        content = build_internal_email(context)

        self.assertNotIn("<script>alert(1)</script>", content.html)
        self.assertIn("&lt;script&gt;", content.html)


class InternalSenderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.email = FakeEmailService()
        self.sender = InternalNotificationSender(
            settings_repository=self.repository,
            resolver=EmailConfigResolver(
                self.repository,
                crypto=EmailSettingsCrypto(KEY),
                settings_obj=make_settings(),
            ),
            email_service=self.email,
        )

    async def _notify(self, event_key: str, payload: dict[str, object]) -> int:
        context = InternalEmailContext.from_payload(event_key, payload)
        assert context is not None
        return await self.sender.notify(event_key, context)

    async def test_no_recipients_means_no_message(self) -> None:
        delivered = await self._notify("order.submitted", order_payload())

        self.assertEqual(delivered, 0)
        self.assertEqual(self.email.sent, [])

    async def test_each_active_recipient_gets_its_own_message(self) -> None:
        self.repository.recipients = {
            1: make_recipient("ops@dairyfarm.in"),
            2: make_recipient("owner@dairyfarm.in"),
        }

        delivered = await self._notify("order.submitted", order_payload())

        self.assertEqual(delivered, 2)
        self.assertEqual(
            sorted(self.email.recipients),
            ["ops@dairyfarm.in", "owner@dairyfarm.in"],
        )
        self.assertEqual(
            [message["to"] for message in self.email.sent],
            sorted(self.email.recipients),
        )

    async def test_category_recipient_covers_the_event_once(self) -> None:
        self.repository.recipients = {
            1: make_recipient("ops@dairyfarm.in"),
            2: make_recipient(
                "ops@dairyfarm.in", mapping_key="category:customer_orders", scope="category"
            ),
            3: make_recipient(
                "manager@dairyfarm.in",
                mapping_key="category:customer_orders",
                scope="category",
            ),
        }

        delivered = await self._notify("order.submitted", order_payload())

        self.assertEqual(delivered, 2)
        self.assertEqual(
            sorted(self.email.recipients),
            ["manager@dairyfarm.in", "ops@dairyfarm.in"],
        )

    async def test_inactive_and_other_workflow_recipients_are_skipped(self) -> None:
        self.repository.recipients = {
            1: make_recipient("ops@dairyfarm.in", is_active=False),
            2: make_recipient("other@dairyfarm.in", mapping_key="event:order.approved"),
            3: make_recipient("ops2@dairyfarm.in"),
        }

        delivered = await self._notify("order.submitted", order_payload())

        self.assertEqual(delivered, 1)
        self.assertEqual(self.email.recipients, ["ops2@dairyfarm.in"])

    async def test_disabled_event_sends_nothing(self) -> None:
        self.repository.recipients = {1: make_recipient("ops@dairyfarm.in")}
        self.repository.mappings = {
            "event:order.submitted": SimpleNamespace(
                sender_identity_id=None,
                reply_to_sender_identity_id=None,
                is_enabled=False,
            )
        }

        delivered = await self._notify("order.submitted", order_payload())

        self.assertEqual(delivered, 0)
        self.assertEqual(self.email.sent, [])

    async def test_one_failing_recipient_does_not_stop_the_others(self) -> None:
        self.repository.recipients = {
            1: make_recipient("broken@dairyfarm.in"),
            2: make_recipient("ops@dairyfarm.in"),
        }
        self.email.fail_for = {"broken@dairyfarm.in"}

        delivered = await self._notify("order.submitted", order_payload())

        self.assertEqual(delivered, 1)
        self.assertEqual(self.email.recipients, ["ops@dairyfarm.in"])

    async def test_sender_uses_the_resolved_configuration(self) -> None:
        self.repository.recipients = {1: make_recipient("ops@dairyfarm.in")}

        await self._notify("order.submitted", order_payload())

        config = self.email.sent[0]["config"]
        self.assertEqual(config.source, "environment")
        self.assertEqual(config.from_email, "no-reply@dairyfarm.com")


class OrderPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_payload_is_built_from_the_order(self) -> None:
        order = SimpleNamespace(
            id=7,
            order_no="ORD-1",
            account_id=1,
            customer_id=4,
            requested_date=date(2026, 11, 7),
            quantity_litres=Decimal("12.50"),
            note="Evening pickup",
        )

        class Orders:
            async def get_by_id(self, order_id):
                return order if order_id == 7 else None

            async def get_account(self, account_id):
                return SimpleNamespace(id=1, email="Asha@Example.com")

        class Customers:
            async def get_by_id(self, customer_id):
                return SimpleNamespace(id=4, name="Asha Patel")

        payload = await order_notification_payload(Orders(), Customers(), 7)

        assert payload is not None
        self.assertEqual(payload["order_no"], "ORD-1")
        self.assertEqual(payload["account_email"], "Asha@Example.com")
        self.assertEqual(payload["customer_name"], "Asha Patel")
        self.assertEqual(payload["requested_date"], "2026-11-07")
        self.assertEqual(payload["quantity_litres"], "12.50")
        self.assertEqual(payload["note"], "Evening pickup")

        self.assertIsNone(await order_notification_payload(Orders(), Customers(), 99))


class RecordingAudit:
    def __init__(self, *, failure_count: int = 5) -> None:
        self.failure_count = failure_count
        self.records: list[dict[str, object]] = []

    async def record_standalone(self, **kwargs: object) -> bool:
        self.records.append(kwargs)
        return True

    async def count_recent(self, **kwargs: object) -> int:
        if kwargs["event_type"] == "auth.login.failed":
            return self.failure_count
        return 0


class RecordingEmail:
    def __init__(self) -> None:
        self.failed_alerts: list[dict[str, object]] = []
        self.locked_notices: list[dict[str, object]] = []

    async def send_failed_login_alert(self, **kwargs: object) -> bool:
        self.failed_alerts.append(kwargs)
        return True

    async def send_account_locked_notice(self, **kwargs: object) -> bool:
        self.locked_notices.append(kwargs)
        return True


class LoginInternalDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_login_alert_notifies_internal_recipients(self) -> None:
        audit = RecordingAudit(failure_count=5)
        email = RecordingEmail()
        dispatched: list[tuple[str, dict[str, object] | None]] = []

        async def fake_dispatch(event_key, payload):
            dispatched.append((event_key, payload))
            return 1

        service = LoginSecurityService(
            audit,  # type: ignore[arg-type]
            email,  # type: ignore[arg-type]
            internal_dispatch=fake_dispatch,
        )

        await service.record_failure(
            scope="customer",
            reason_code="bad_password",
            context=None,
            actor_account_id=11,
            email="Customer@Example.com",
            name="Customer One",
            alertable=True,
        )

        self.assertEqual(len(email.failed_alerts), 1)
        self.assertEqual(len(dispatched), 1)
        event_key, payload = dispatched[0]
        self.assertEqual(event_key, "account.customer_failed_login_alert")
        assert payload is not None
        self.assertEqual(payload["account_email"], "Customer@Example.com")
        self.assertEqual(payload["failure_count"], 5)
        self.assertEqual(
            payload["window_minutes"],
            settings.failed_login_alert_window_minutes,
        )

    async def test_account_locked_notifies_internal_recipients(self) -> None:
        audit = RecordingAudit()
        email = RecordingEmail()
        dispatched: list[tuple[str, dict[str, object] | None]] = []

        async def fake_dispatch(event_key, payload):
            dispatched.append((event_key, payload))
            return 1

        service = LoginSecurityService(
            audit,  # type: ignore[arg-type]
            email,  # type: ignore[arg-type]
            internal_dispatch=fake_dispatch,
        )

        await service.record_account_locked(
            scope="staff",
            failure_count=8,
            context=None,
            actor_user_id=7,
            email="staff@example.com",
            name="Staff User",
        )

        self.assertEqual(len(email.locked_notices), 1)
        self.assertEqual(len(dispatched), 1)
        event_key, payload = dispatched[0]
        self.assertEqual(event_key, "account.staff_account_locked")
        assert payload is not None
        self.assertEqual(payload["account_email"], "staff@example.com")
        self.assertEqual(payload["failure_count"], 8)

    async def test_without_a_dispatcher_nothing_is_sent(self) -> None:
        audit = RecordingAudit()
        email = RecordingEmail()
        service = LoginSecurityService(
            audit,  # type: ignore[arg-type]
            email,  # type: ignore[arg-type]
        )

        await service.record_account_locked(
            scope="staff",
            failure_count=8,
            context=None,
            actor_user_id=7,
            email="staff@example.com",
            name="Staff User",
        )

        self.assertEqual(len(email.locked_notices), 1)
        self.assertIsNone(service.internal_dispatch)

    async def test_internal_failure_never_breaks_the_alert(self) -> None:
        audit = RecordingAudit()
        email = RecordingEmail()

        async def broken_dispatch(event_key, payload):
            raise RuntimeError("database is down")

        service = LoginSecurityService(
            audit,  # type: ignore[arg-type]
            email,  # type: ignore[arg-type]
            internal_dispatch=broken_dispatch,
        )

        await service.record_account_locked(
            scope="staff",
            failure_count=8,
            context=None,
            actor_user_id=7,
            email="staff@example.com",
            name="Staff User",
        )

        self.assertEqual(len(email.locked_notices), 1)
        self.assertEqual(
            [record["event_type"] for record in audit.records],
            ["auth.account.locked"],
        )


if __name__ == "__main__":
    unittest.main()
