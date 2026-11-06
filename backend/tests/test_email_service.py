from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.services.email_config_resolver import (
    EmailConfigurationError,
    EmailMessageConfig,
    EmailTransportConfig,
)
from app.services.email_service import EmailService


class EmailServiceLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def _send(self) -> tuple[bool, str]:
        url = "http://localhost:5173/reset-password?token=super-secret-token"
        with self.assertLogs("app.services.email_service", level="WARNING") as logs:
            sent = await EmailService().send_password_reset(
                to="asha@example.com",
                name="Asha",
                reset_url=url,
                audience="staff",
            )
        return sent, "\n".join(logs.output)

    async def test_unconfigured_smtp_in_development_logs_the_link(self) -> None:
        with patch.object(settings, "smtp_host", ""), patch.object(
            settings, "node_env", "development"
        ):
            sent, output = await self._send()

        self.assertFalse(sent)
        self.assertIn("SMTP is not configured", output)
        self.assertIn("token=super-secret-token", output)

    async def test_unconfigured_smtp_in_production_hides_the_link(self) -> None:
        with patch.object(settings, "smtp_host", ""), patch.object(
            settings, "node_env", "production"
        ):
            sent, output = await self._send()

        self.assertFalse(sent)
        self.assertIn("SMTP is not configured", output)
        self.assertNotIn("super-secret-token", output)


DATABASE_CONFIG = EmailMessageConfig(
    source="database",
    transport=EmailTransportConfig(
        host="smtp.example.com",
        port=587,
        auth_enabled=False,
        encryption_mode="starttls",
        timeout_seconds=10,
    ),
    from_name="Support Desk",
    from_email="support@example.com",
    reply_to_email=None,
)


class RecordingResolver:
    """Captures what the email service asks the resolver for."""

    def __init__(
        self,
        config: EmailMessageConfig = DATABASE_CONFIG,
        error: Exception | None = None,
    ) -> None:
        self.config = config
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    async def resolve(
        self,
        event_key: str,
        *,
        category_key: str | None = None,
    ) -> EmailMessageConfig:
        self.calls.append((event_key, category_key))
        if self.error is not None:
            raise self.error
        return self.config


def provider_for(resolver: RecordingResolver):
    """Stand-in for the session-scoped provider used in production."""

    @asynccontextmanager
    async def provider():
        yield resolver

    return provider


class WorkflowSenderWiringTests(unittest.IsolatedAsyncioTestCase):
    """The five remaining workflows must resolve their transport and sender."""

    async def test_staff_password_reset_uses_the_event_mapping(self) -> None:
        resolver = RecordingResolver()
        service = EmailService(resolver_provider=provider_for(resolver))
        with patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ) as send:
            sent = await service.send_password_reset(
                to="asha@example.com",
                name="Asha",
                reset_url="http://localhost:5173/reset-password?token=t",
                audience="staff",
            )

        self.assertTrue(sent)
        self.assertEqual(
            resolver.calls, [("account.staff_password_reset", "account_security")]
        )
        self.assertEqual(send.await_args.args[0].from_email, "support@example.com")
        self.assertEqual(send.await_args.kwargs["to"], "asha@example.com")

    async def test_customer_audience_selects_the_customer_key(self) -> None:
        resolver = RecordingResolver()
        service = EmailService(resolver_provider=provider_for(resolver))
        with patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ):
            await service.send_password_changed(
                to="asha@example.com",
                name="Asha",
                audience="customer portal",
            )

        self.assertEqual(
            resolver.calls, [("account.customer_password_changed", "account_security")]
        )

    async def test_alert_and_lock_keys_follow_the_scope(self) -> None:
        resolver = RecordingResolver()
        service = EmailService(resolver_provider=provider_for(resolver))
        occurred_at = datetime(2026, 11, 4, 10, 30, tzinfo=timezone.utc)
        with patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ):
            await service.send_failed_login_alert(
                to="customer@example.com",
                name="Asha",
                scope="customer",
                failure_count=5,
                window_minutes=15,
                occurred_at_utc=occurred_at,
                ip_address=None,
                user_agent=None,
            )
            await service.send_account_locked_notice(
                to="staff@example.com",
                name="Asha",
                scope="staff",
                failure_count=5,
                window_minutes=15,
                locked_at_utc=occurred_at,
                ip_address=None,
                user_agent=None,
            )

        self.assertEqual(
            resolver.calls,
            [
                ("account.customer_failed_login_alert", "account_security"),
                ("account.staff_account_locked", "account_security"),
            ],
        )

    async def test_portal_activation_uses_the_portal_event_key(self) -> None:
        resolver = RecordingResolver()
        service = EmailService(resolver_provider=provider_for(resolver))
        with patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ):
            await service.send_portal_activation(
                to="customer@example.com",
                name="Asha",
                activation_url="http://localhost:5173/portal/activate?token=t",
                expires_hours=48,
            )

        self.assertEqual(
            resolver.calls, [("portal.customer_activation", "customer_portal")]
        )

    async def test_support_reply_uses_the_support_event_key(self) -> None:
        resolver = RecordingResolver()
        service = EmailService(resolver_provider=provider_for(resolver))
        with patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ) as send:
            sent = await service.send_support_query_answered(
                to="customer@example.com",
                name="Asha",
                query_no="QRY-20261106-AB12",
                subject="Invoice question",
                portal_url="http://localhost:5173/portal/queries",
            )

        self.assertTrue(sent)
        self.assertEqual(
            resolver.calls, [("support.query_answered", "customer_support")]
        )
        self.assertIn("QRY-20261106-AB12", send.await_args.kwargs["subject"])
        self.assertIn(
            "http://localhost:5173/portal/queries",
            send.await_args.kwargs["text"],
        )

    async def test_a_resolution_failure_is_logged_and_not_sent(self) -> None:
        resolver = RecordingResolver(
            error=EmailConfigurationError(
                "ENCRYPTION_KEY_UNAVAILABLE",
                "Email settings encryption key is not configured",
            )
        )
        service = EmailService(resolver_provider=provider_for(resolver))
        with patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ) as send:
            with self.assertLogs("app.services.email_service", level="WARNING") as logs:
                sent = await service.send_password_reset(
                    to="asha@example.com",
                    name="Asha",
                    reset_url="http://localhost:5173/reset-password?token=t",
                    audience="staff",
                )

        self.assertFalse(sent)
        send.assert_not_awaited()
        self.assertIn("ENCRYPTION_KEY_UNAVAILABLE", "\n".join(logs.output))

    async def test_an_unexpected_resolution_error_never_reaches_the_caller(self) -> None:
        resolver = RecordingResolver(error=RuntimeError("database is unavailable"))
        service = EmailService(resolver_provider=provider_for(resolver))
        with patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ) as send:
            with self.assertLogs("app.services.email_service", level="ERROR"):
                sent = await service.send_portal_activation(
                    to="customer@example.com",
                    name="Asha",
                    activation_url="http://localhost:5173/portal/activate?token=t",
                    expires_hours=48,
                )

        self.assertFalse(sent)
        send.assert_not_awaited()

    async def test_without_a_resolver_the_environment_path_is_kept(self) -> None:
        with patch.object(settings, "smtp_host", ""), patch.object(
            EmailService, "send_with_config", new=AsyncMock(return_value=True)
        ) as send:
            sent = await EmailService().send_password_reset(
                to="asha@example.com",
                name="Asha",
                reset_url="http://localhost:5173/reset-password?token=t",
                audience="staff",
            )

        self.assertFalse(sent)
        send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
