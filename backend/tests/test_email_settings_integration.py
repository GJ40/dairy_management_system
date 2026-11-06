"""Cross-cutting checks for the email settings feature (Phase 10).

The per-phase modules cover each surface in depth; this module covers the rows
that belong to no single phase: the authorization matrix across every
email-settings route, the values handed to the MIME builder (From/Reply-To), and
log/audit hygiene for credentials and recipient addresses.
"""

from __future__ import annotations

import logging
import re
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx

from app.core.config import settings
from app.core.dependencies import get_email_settings_service, get_security_audit_service
from app.core.security import create_access_token, create_customer_access_token
from app.db.session import get_db
from app.main import app
from app.routers import email_settings as email_settings_router
from app.schemas.email_settings import CreateSenderIdentityRequest
from app.services.email_config_resolver import EmailMessageConfig, EmailTransportConfig
from app.services.email_service import EmailService
from app.services.email_settings_crypto import EmailSettingsCrypto
from app.services.email_settings_service import EmailSettingsService
from tests.audit_helpers import FakeAuditService
from tests.test_email_settings import KEY, FakeRepository, FakeSmtpClient, make_settings
from tests.test_email_settings_api import FakeSession, make_user

SEGMENT = "/email-settings"
PREFIX = f"{settings.api_v1_prefix.rstrip('/')}{SEGMENT}"
PATH_PARAM = re.compile(r"\{[^}]+\}")
BODY_METHODS = {"POST", "PUT", "PATCH"}
EXPECTED_ROUTE_COUNT = 24
PASSWORD = "super-secret-smtp-password"
USERNAME = "mailer@example.com"


def email_settings_routes() -> list[tuple[str, str]]:
    """Every (method, url) the email-settings router exposes.

    The list comes from the router definition rather than from ``app.routes``:
    in this suite the app object does not expose its mounted routes through
    that attribute, and a lookup that silently finds nothing would let the
    authorization sweeps pass without sending a single request. The sweeps
    themselves prove each URL resolves, because an unmounted path answers 404
    and the assertions only accept 401/403.
    """
    base = f"{settings.api_v1_prefix.rstrip('/')}{SEGMENT}"
    found: set[tuple[str, str]] = set()
    for route in email_settings_router.router.routes:
        path = route.path
        if not path.startswith(base):
            path = f"{base}{path.removeprefix(SEGMENT)}"
        for method in route.methods or set():
            if method in {"HEAD", "OPTIONS"}:
                continue
            found.add((method, PATH_PARAM.sub("1", path)))
    return sorted(found)


def email_settings_route_sweep() -> list[tuple[str, str]]:
    """The route list, or a failure: an empty list must never pass a sweep."""
    routes = email_settings_routes()
    if not routes:
        raise AssertionError(
            f"the email-settings router exposed no routes (api_v1_prefix="
            f"{settings.api_v1_prefix!r})"
        )
    return routes


def make_config(**overrides: object) -> EmailMessageConfig:
    values: dict[str, object] = {
        "source": "database",
        "transport": EmailTransportConfig(
            host="smtp.example.com",
            port=587,
            auth_enabled=True,
            encryption_mode="starttls",
            timeout_seconds=10,
            username=USERNAME,
            password=PASSWORD,
        ),
        "from_name": "Dairy Ops",
        "from_email": "ops@example.com",
        "reply_to_email": "support@example.com",
    }
    values.update(overrides)
    return EmailMessageConfig(**values)  # type: ignore[arg-type]


class LogCapture(logging.Handler):
    """Collects formatted records from every logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if record.exc_info:
            formatter = logging.Formatter()
            message = f"{message} {formatter.formatException(record.exc_info)}"
        self.messages.append(message)

    def text(self) -> str:
        return "\n".join(self.messages)


class SettingsApiHarness(unittest.IsolatedAsyncioTestCase):
    """The API harness used by the route-authorization and audit sweeps."""

    async def asyncSetUp(self) -> None:
        self.admin = make_user(1, role="admin", username="admin")
        self.operator = make_user(2, role="operator", username="operator")
        self.repository = FakeRepository()
        self.audit = FakeAuditService()
        self.smtp_client = FakeSmtpClient()
        self.service = EmailSettingsService(
            self.repository,
            crypto=EmailSettingsCrypto(KEY),
            audit=self.audit,
            settings_obj=make_settings(),
            smtp_client=self.smtp_client,
        )

        async def override_get_db():
            yield FakeSession(self.admin, self.operator)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit
        app.dependency_overrides[get_email_settings_service] = lambda: self.service
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self, user=None) -> dict[str, str]:
        user = user or self.admin
        token = create_access_token(
            user_id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}=test-session",
        }

    async def _call(self, method: str, path: str, *, headers=None):
        payload = {} if method in BODY_METHODS else None
        return await self.client.request(method, path, headers=headers, json=payload)


class RouteAuthorizationTests(SettingsApiHarness):
    async def test_route_inventory_matches_the_documented_surface(self) -> None:
        routes = email_settings_route_sweep()

        self.assertEqual(len(routes), EXPECTED_ROUTE_COUNT)
        self.assertEqual(len(set(routes)), len(routes))
        for method, path in routes:
            with self.subTest(method=method, path=path):
                self.assertTrue(
                    path.startswith(f"{PREFIX}/"), f"{path} does not sit under {PREFIX}"
                )
                self.assertNotIn("{", path)

    async def test_every_route_rejects_an_anonymous_caller(self) -> None:
        for method, path in email_settings_route_sweep():
            with self.subTest(method=method, path=path):
                response = await self._call(method, path)
                self.assertEqual(response.status_code, 401, response.text)

    async def test_every_route_rejects_an_operator(self) -> None:
        headers = self._auth(self.operator)
        for method, path in email_settings_route_sweep():
            with self.subTest(method=method, path=path):
                response = await self._call(method, path, headers=headers)
                self.assertEqual(response.status_code, 403, response.text)

    async def test_every_route_rejects_a_customer_token(self) -> None:
        token = create_customer_access_token(
            account_id=1,
            customer_id=1,
            email="customer@example.com",
        )
        headers = {"Authorization": f"Bearer {token}"}
        for method, path in email_settings_route_sweep():
            with self.subTest(method=method, path=path):
                response = await self._call(method, path, headers=headers)
                self.assertIn(response.status_code, (401, 403), response.text)

    async def test_role_claims_in_the_body_are_ignored(self) -> None:
        response = await self.client.post(
            f"{PREFIX}/senders",
            headers=self._auth(self.operator),
            json={
                "display_name": "Ops",
                "email": "ops@example.com",
                "role": "admin",
                "user_id": self.admin.id,
            },
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.repository.identities, {})
        self.assertEqual(self.audit.records, [])


class SentMessageTests(unittest.IsolatedAsyncioTestCase):
    """From/Reply-To/To are decided per send, so they are asserted here."""

    async def asyncSetUp(self) -> None:
        self.created: list[dict[str, object]] = []
        self.sent: list[dict[str, object]] = []
        created, sent = self.created, self.sent

        class FakeMessage:
            def __init__(self, **kwargs: object) -> None:
                self.kwargs = kwargs
                created.append(kwargs)

            def send(self, *, to: str, smtp: dict[str, object]) -> SimpleNamespace:
                sent.append({"to": to, "smtp": smtp})
                return SimpleNamespace(status_code=250)

        module = SimpleNamespace(html=lambda **kwargs: FakeMessage(**kwargs))
        patcher = mock.patch("app.services.email_service.emails", new=module)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = EmailService()

        self.logs = LogCapture()
        root = logging.getLogger()
        self.previous_level = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(self.logs)

        def cleanup_logging() -> None:
            root.removeHandler(self.logs)
            root.setLevel(self.previous_level)

        self.addCleanup(cleanup_logging)

    async def _send(self, config: EmailMessageConfig) -> bool:
        return await self.service.send_with_config(
            config,
            to="asha@example.com",
            subject="Order submitted — ORD-20261106-AB12",
            html="<p>Hello Asha</p>",
            text="Hello Asha",
        )

    async def test_from_and_reply_to_reach_the_message_builder(self) -> None:
        sent = await self._send(make_config())

        self.assertTrue(sent)
        self.assertEqual(len(self.created), 1)
        kwargs = self.created[0]
        self.assertEqual(kwargs["mail_from"], ("Dairy Ops", "ops@example.com"))
        self.assertEqual(kwargs["headers"], {"Reply-To": "support@example.com"})
        self.assertEqual(
            kwargs["subject"], "Order submitted — ORD-20261106-AB12"
        )
        self.assertEqual(kwargs["html"], "<p>Hello Asha</p>")
        self.assertEqual(kwargs["text"], "Hello Asha")

        self.assertEqual(self.sent[0]["to"], "asha@example.com")
        smtp = self.sent[0]["smtp"]
        self.assertEqual(smtp["host"], "smtp.example.com")
        self.assertEqual(smtp["port"], 587)
        self.assertTrue(smtp["tls"])
        self.assertFalse(smtp["ssl"])
        self.assertTrue(smtp["user"])
        self.assertEqual(smtp["timeout"], 10)

    async def test_no_reply_to_header_when_none_is_configured(self) -> None:
        sent = await self._send(make_config(reply_to_email=None))

        self.assertTrue(sent)
        self.assertIsNone(self.created[0]["headers"])

    async def test_reply_to_never_replaces_the_recipient(self) -> None:
        await self._send(make_config(reply_to_email="billing@example.com"))

        self.assertEqual(self.sent[0]["to"], "asha@example.com")
        self.assertEqual(
            self.created[0]["headers"], {"Reply-To": "billing@example.com"}
        )

    async def test_credentials_never_reach_the_log(self) -> None:
        sent = await self._send(make_config())

        self.assertTrue(sent)
        captured = self.logs.text()
        self.assertIn("Order submitted", captured)
        self.assertNotIn(PASSWORD, captured)
        self.assertNotIn(USERNAME, captured)
        # The message itself only carries the From pair and Reply-To.
        self.assertNotIn(PASSWORD, repr(self.created[0]))
        self.assertNotIn(USERNAME, repr(self.created[0]))

    async def test_a_delivery_failure_is_swallowed(self) -> None:
        class ExplodingMessage:
            def __init__(self, **_kwargs: object) -> None:
                pass

            def send(self, *, to: str, smtp: dict[str, object]) -> SimpleNamespace:
                raise RuntimeError("connection refused")

        with mock.patch(
            "app.services.email_service.emails",
            new=SimpleNamespace(html=lambda **kwargs: ExplodingMessage(**kwargs)),
        ):
            sent = await self._send(make_config())

        self.assertFalse(sent)
        self.assertNotIn(PASSWORD, self.logs.text())


class AuditHygieneTests(SettingsApiHarness):
    async def test_audit_metadata_never_carries_secrets_or_addresses(self) -> None:
        created = await self.client.post(
            f"{PREFIX}/smtp/profiles",
            headers=self._auth(self.admin),
            json={
                "name": "Production SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 587,
                "auth_enabled": True,
                "username": USERNAME,
                "password": PASSWORD,
                "encryption_mode": "starttls",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        profile_id = created.json()["profile"]["id"]

        tested = await self.client.post(
            f"{PREFIX}/smtp/profiles/{profile_id}/test-connection",
            headers=self._auth(self.admin),
        )
        self.assertEqual(tested.status_code, 200, tested.text)

        sender = await self.client.post(
            f"{PREFIX}/senders",
            headers=self._auth(self.admin),
            json={
                "display_name": "Ops",
                "email": "ops@example.com",
                "reply_to_email": "support@example.com",
            },
        )
        self.assertEqual(sender.status_code, 201, sender.text)

        recipient = await self.client.post(
            f"{PREFIX}/recipients",
            headers=self._auth(self.admin),
            json={
                "scope": "event",
                "mapping_key": "order.submitted",
                "email": "alerts@example.com",
            },
        )
        self.assertEqual(recipient.status_code, 201, recipient.text)

        self.assertTrue(self.audit.records)
        for record in self.audit.records:
            rendered = repr(record)
            for forbidden in (
                PASSWORD,
                USERNAME,
                "ops@example.com",
                "support@example.com",
                "alerts@example.com",
                "password_configured",
                "username_configured",
            ):
                self.assertNotIn(forbidden, rendered)


class AuditFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_failed_audit_write_aborts_the_mutation(self) -> None:
        class ExplodingAudit(FakeAuditService):
            async def record(self, **_kwargs: object) -> object:
                raise RuntimeError("audit ledger unavailable")

        repository = FakeRepository()
        service = EmailSettingsService(
            repository,
            crypto=EmailSettingsCrypto(KEY),
            audit=ExplodingAudit(),
            settings_obj=make_settings(),
            smtp_client=FakeSmtpClient(),
        )

        with self.assertRaises(RuntimeError):
            await service.create_sender(
                CreateSenderIdentityRequest(
                    display_name="Ops",
                    email="ops@example.com",
                ),
                actor_user_id=1,
            )

        self.assertEqual(repository.commits, 0)
