from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.request_context import RequestContext
from app.services.email_service import EmailService
from app.services.login_security_service import LoginSecurityService


def context() -> RequestContext:
    return RequestContext(
        request_id="c" * 32,
        ip_address="203.0.113.9",
        user_agent="pytest-agent",
        http_method="POST",
        path="/api/v1/auth/login",
    )


class FakeAuditService:
    def __init__(
        self,
        *,
        failure_count: int = 0,
        sent_count: int = 0,
        record_result: bool = True,
    ) -> None:
        self.failure_count = failure_count
        self.sent_count = sent_count
        self.record_result = record_result
        self.records: list[dict[str, object]] = []
        self.counts: list[dict[str, object]] = []

    async def record_standalone(self, **kwargs: object) -> bool:
        self.records.append(kwargs)
        if not self.record_result:
            return False
        event_type = kwargs["event_type"]
        if event_type == "auth.login.failed":
            self.failure_count += 1
        if event_type == "auth.alert.failed_login.sent":
            self.sent_count += 1
        return True

    async def count_recent(self, **kwargs: object) -> int:
        self.counts.append(kwargs)
        if kwargs["event_type"] == "auth.login.failed":
            return self.failure_count
        if kwargs["event_type"] == "auth.alert.failed_login.sent":
            return self.sent_count
        return 0


class FakeEmailService:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def send_failed_login_alert(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        return self.result


class LoginSecurityServiceTests(unittest.IsolatedAsyncioTestCase):
    def _service(
        self,
        audit: FakeAuditService,
        email: FakeEmailService | None = None,
    ) -> LoginSecurityService:
        return LoginSecurityService(audit, email)  # type: ignore[arg-type]

    async def test_failure_is_recorded_below_threshold_without_email(self) -> None:
        audit = FakeAuditService()
        email = FakeEmailService()
        service = self._service(audit, email)

        await service.record_failure(
            scope="staff",
            reason_code="bad_password",
            context=context(),
            actor_user_id=7,
            email="staff@example.com",
            name="Staff User",
            alertable=True,
        )

        self.assertEqual(audit.records[0]["event_type"], "auth.login.failed")
        self.assertEqual(audit.records[0]["actor_user_id"], 7)
        self.assertEqual(
            audit.records[0]["metadata"],
            {"scope": "staff", "reason_code": "bad_password", "account_resolved": True},
        )
        self.assertEqual(email.calls, [])

    async def test_threshold_sends_one_alert_and_records_dispatch(self) -> None:
        audit = FakeAuditService(failure_count=4)
        email = FakeEmailService()
        service = self._service(audit, email)

        await service.record_failure(
            scope="staff",
            reason_code="bad_password",
            context=context(),
            actor_user_id=7,
            email="staff@example.com",
            name="Staff User",
            alertable=True,
        )

        self.assertEqual(len(email.calls), 1)
        call = email.calls[0]
        self.assertEqual(call["to"], "staff@example.com")
        self.assertEqual(call["scope"], "staff")
        self.assertEqual(call["failure_count"], 5)
        self.assertEqual(call["window_minutes"], settings.failed_login_alert_window_minutes)
        self.assertEqual(call["ip_address"], "203.0.113.9")
        self.assertEqual(call["user_agent"], "pytest-agent")
        event_types = [record["event_type"] for record in audit.records]
        self.assertEqual(
            event_types,
            ["auth.login.failed", "auth.alert.failed_login.sent"],
        )
        sent = audit.records[-1]
        self.assertEqual(sent["actor_type"], "system")
        self.assertEqual(sent["resource_type"], "staff_user")
        self.assertEqual(sent["resource_id"], "7")

    async def test_cooldown_suppresses_a_duplicate_alert(self) -> None:
        audit = FakeAuditService(failure_count=4, sent_count=1)
        email = FakeEmailService()
        service = self._service(audit, email)

        await service.record_failure(
            scope="staff",
            reason_code="bad_password",
            context=context(),
            actor_user_id=7,
            email="staff@example.com",
            alertable=True,
        )

        self.assertEqual(email.calls, [])
        self.assertEqual(
            audit.records[-1]["event_type"],
            "auth.alert.failed_login.suppressed",
        )
        self.assertEqual(
            audit.records[-1]["metadata"],
            {
                "scope": "staff",
                "failure_count": 5,
                "cooldown_minutes": settings.failed_login_alert_cooldown_minutes,
            },
        )

    async def test_unresolved_or_disabled_alert_never_sends_email(self) -> None:
        audit = FakeAuditService(failure_count=100)
        email = FakeEmailService()
        service = self._service(audit, email)

        await service.record_failure(
            scope="staff",
            reason_code="unknown_email",
            context=context(),
            alertable=False,
        )
        self.assertEqual(email.calls, [])

        with patch.object(settings, "failed_login_alert_enabled", False):
            await service.record_failure(
                scope="staff",
                reason_code="bad_password",
                context=context(),
                actor_user_id=7,
                email="staff@example.com",
                alertable=True,
            )
        self.assertEqual(email.calls, [])

    async def test_delivery_failure_is_recorded(self) -> None:
        audit = FakeAuditService(failure_count=4)
        email = FakeEmailService(result=False)
        service = self._service(audit, email)

        await service.record_failure(
            scope="customer",
            reason_code="bad_password",
            context=context(),
            actor_account_id=9,
            email="customer@example.com",
            alertable=True,
        )

        self.assertEqual(len(email.calls), 1)
        self.assertEqual(
            audit.records[-1]["event_type"],
            "auth.alert.failed_login.delivery_failed",
        )
        self.assertEqual(audit.records[-1]["reason_code"], "delivery_failed")
        self.assertEqual(audit.records[-1]["resource_type"], "customer_portal_account")

    async def test_background_defers_audit_and_email(self) -> None:
        audit = FakeAuditService(failure_count=4)
        email = FakeEmailService()
        service = self._service(audit, email)
        background = BackgroundTasks()

        await service.record_failure(
            scope="staff",
            reason_code="bad_password",
            context=context(),
            actor_user_id=7,
            email="staff@example.com",
            alertable=True,
            background=background,
        )

        self.assertEqual(audit.records, [])
        self.assertEqual(email.calls, [])
        await background()
        self.assertEqual(len(email.calls), 1)

    async def test_success_is_recorded_with_scope_metadata(self) -> None:
        audit = FakeAuditService()
        service = self._service(audit)

        await service.record_success(
            scope="staff",
            context=context(),
            actor_user_id=7,
            role="admin",
        )

        self.assertEqual(audit.records[0]["event_type"], "auth.login.succeeded")
        self.assertEqual(
            audit.records[0]["metadata"],
            {"scope": "staff", "role": "admin"},
        )


class CapturingEmailService(EmailService):
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    async def _deliver(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        link: str | None = None,
        event_key: str | None = None,
    ) -> bool:
        self.payload = {
            "to": to,
            "subject": subject,
            "html": html,
            "text": text,
            "link": link,
            "event_key": event_key,
        }
        return True


class FailedLoginAlertEmailTests(unittest.IsolatedAsyncioTestCase):
    async def test_template_escapes_values_and_includes_times_without_a_link(self) -> None:
        service = CapturingEmailService()
        delivered = await service.send_failed_login_alert(
            to="staff@example.com",
            name="<script>alert(1)</script>",
            scope="staff",
            failure_count=5,
            window_minutes=15,
            occurred_at_utc=datetime(2026, 11, 4, 10, 30, tzinfo=timezone.utc),
            ip_address="<b>203.0.113.9</b>",
            user_agent="<script>bad()</script>",
        )

        self.assertTrue(delivered)
        assert service.payload is not None
        html = str(service.payload["html"])
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>203.0.113.9</b>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;203.0.113.9&lt;/b&gt;", html)
        # 10:30 UTC must be shown in both zones (Asia/Kolkata is UTC+05:30).
        self.assertIn("16:00:00 IST", html)
        self.assertIn("10:30:00 UTC", html)
        self.assertIsNone(service.payload["link"])
        self.assertIn("Security alert", str(service.payload["subject"]))


if __name__ == "__main__":
    unittest.main()
