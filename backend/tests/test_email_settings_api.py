from __future__ import annotations

import unittest
from types import SimpleNamespace

import httpx

from app.core.config import settings
from app.core.dependencies import get_email_settings_service, get_security_audit_service
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.schemas.email_settings import CreateSmtpProfileRequest
from app.services.email_settings_crypto import EmailSettingsCrypto
from app.services.email_settings_service import EmailSettingsService
from tests.audit_helpers import FakeAuditService
from tests.test_email_settings import (
    KEY,
    FakeRepository,
    FakeSmtpClient,
    make_settings,
)


def make_user(user_id: int, *, role: str, username: str) -> User:
    return User(
        id=user_id,
        full_name="Admin" if role == "admin" else "Operator",
        username=username,
        email=f"{username}@example.com",
        password_hash="not-used",
        role=role,
        is_active=True,
        is_deleted=False,
    )


class FakeSession:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def get(self, model, primary_key):
        if model is User:
            return self.users.get(primary_key)
        return None


class ApiTests(unittest.IsolatedAsyncioTestCase):
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

    def _auth(self, user: User | None = None) -> dict[str, str]:
        target = user or self.admin
        token = create_access_token(
            user_id=target.id,
            email=target.email,
            username=target.username,
            role=target.role,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}=test-session",
        }

    async def test_admin_can_read_overview(self) -> None:
        response = await self.client.get(
            "/api/v1/email-settings/smtp", headers=self._auth()
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "environment")
        self.assertIn("mailpit_preset", body)
        self.assertNotIn("password", str(body["environment"]))
        self.assertNotIn("username", body["environment"])

    async def test_create_and_patch_draft(self) -> None:
        created = await self.client.post(
            "/api/v1/email-settings/smtp/profiles",
            headers=self._auth(),
            json={
                "name": "Production SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 587,
                "auth_enabled": True,
                "username": "mailer@example.com",
                "password": "super-secret",
                "encryption_mode": "starttls",
            },
        )
        self.assertEqual(created.status_code, 201)
        profile = created.json()["profile"]
        self.assertEqual(profile["status"], "draft")
        self.assertTrue(profile["username_configured"])
        self.assertTrue(profile["password_configured"])
        self.assertNotIn("super-secret", created.text)

        updated = await self.client.patch(
            f"/api/v1/email-settings/smtp/profiles/{profile['id']}",
            headers=self._auth(),
            json={"port": 465, "encryption_mode": "ssl"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["profile"]["port"], 465)

        fetched = await self.client.get(
            f"/api/v1/email-settings/smtp/profiles/{profile['id']}",
            headers=self._auth(),
        )
        self.assertEqual(fetched.status_code, 200)

    async def test_operator_is_forbidden_everywhere(self) -> None:
        headers = self._auth(self.operator)
        reads = await self.client.get(
            "/api/v1/email-settings/smtp", headers=headers
        )
        writes = await self.client.post(
            "/api/v1/email-settings/smtp/profiles",
            headers=headers,
            json={
                "name": "SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 587,
            },
        )
        self.assertEqual(reads.status_code, 403)
        self.assertEqual(writes.status_code, 403)

    async def test_anonymous_is_unauthorized(self) -> None:
        response = await self.client.get("/api/v1/email-settings/smtp")
        self.assertEqual(response.status_code, 401)

    async def test_validation_error_envelope(self) -> None:
        response = await self.client.post(
            "/api/v1/email-settings/smtp/profiles",
            headers=self._auth(),
            json={
                "name": "SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 70000,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertNotIn("stack", response.text.lower())

    async def test_unknown_profile_is_404(self) -> None:
        response = await self.client.get(
            "/api/v1/email-settings/smtp/profiles/999", headers=self._auth()
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    async def _mailpit_draft(self) -> int:
        payload = CreateSmtpProfileRequest.model_validate(
            {
                "name": "Local Mailpit",
                "provider_mode": "mailpit",
                "host": "127.0.0.1",
                "port": 1025,
            }
        )
        created = await self.service.create_draft(
            payload, actor_user_id=self.admin.id
        )
        return created["profile"]["id"]

    async def test_test_connection_route(self) -> None:
        profile_id = await self._mailpit_draft()

        response = await self.client.post(
            f"/api/v1/email-settings/smtp/profiles/{profile_id}/test-connection",
            headers=self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["test_kind"], "connection")
        self.assertEqual(body["test_status"], "success")
        self.assertIsNone(body["reason_code"])
        self.assertNotIn("password", response.text)
        self.assertNotIn("encrypted", response.text)

    async def test_test_email_route_validates_the_recipient(self) -> None:
        profile_id = await self._mailpit_draft()

        response = await self.client.post(
            f"/api/v1/email-settings/smtp/profiles/{profile_id}/test-email",
            headers=self._auth(),
            json={"recipient_email": "not-an-email"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(self.smtp_client.emails, [])

    async def test_test_email_route_sends_to_the_supplied_address(self) -> None:
        profile_id = await self._mailpit_draft()

        response = await self.client.post(
            f"/api/v1/email-settings/smtp/profiles/{profile_id}/test-email",
            headers=self._auth(),
            json={"recipient_email": "Admin@Example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["test_status"], "success")
        self.assertEqual(
            self.smtp_client.emails[0]["recipient"], "admin@example.com"
        )

    async def test_activation_requires_a_test_through_the_api(self) -> None:
        profile_id = await self._mailpit_draft()

        response = await self.client.post(
            f"/api/v1/email-settings/smtp/profiles/{profile_id}/activate",
            headers=self._auth(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "SMTP_TEST_REQUIRED")

    async def test_activation_succeeds_after_a_successful_test(self) -> None:
        profile_id = await self._mailpit_draft()
        tested = await self.client.post(
            f"/api/v1/email-settings/smtp/profiles/{profile_id}/test-connection",
            headers=self._auth(),
        )
        self.assertEqual(tested.status_code, 200)

        response = await self.client.post(
            f"/api/v1/email-settings/smtp/profiles/{profile_id}/activate",
            headers=self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "database")
        self.assertEqual(body["active_profile"]["id"], profile_id)

    async def test_use_environment_route_returns_the_overview(self) -> None:
        response = await self.client.post(
            "/api/v1/email-settings/smtp/use-environment",
            headers=self._auth(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "environment")

    async def test_phase_four_routes_are_admin_only(self) -> None:
        profile_id = await self._mailpit_draft()
        headers = self._auth(self.operator)
        requests: list[tuple[str, object]] = [
            (
                f"/api/v1/email-settings/smtp/profiles/{profile_id}/test-connection",
                None,
            ),
            (
                f"/api/v1/email-settings/smtp/profiles/{profile_id}/test-email",
                {"recipient_email": "admin@example.com"},
            ),
            (
                f"/api/v1/email-settings/smtp/profiles/{profile_id}/activate",
                None,
            ),
            ("/api/v1/email-settings/smtp/use-environment", None),
        ]

        for path, body in requests:
            kwargs = {"headers": headers}
            if body is not None:
                kwargs["json"] = body
            response = await self.client.post(path, **kwargs)
            self.assertEqual(response.status_code, 403, path)

        self.assertEqual(self.smtp_client.connection_targets, [])
        self.assertEqual(self.smtp_client.emails, [])
        self.assertEqual(self.repository.profiles[profile_id].status, "draft")


    async def _create_sender(self, **overrides) -> dict:
        body = {
            "display_name": "Dairy No Reply",
            "email": "no-reply@dairyfarm.in",
            "reply_to_email": "support@dairyfarm.in",
            "description": "Transactional mail",
        }
        body.update(overrides)
        response = await self.client.post(
            "/api/v1/email-settings/senders",
            headers=self._auth(),
            json=body,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["sender"]

    async def test_sender_crud_routes(self) -> None:
        created = await self.client.post(
            "/api/v1/email-settings/senders",
            headers=self._auth(),
            json={
                "display_name": "Dairy No Reply",
                "email": " No-Reply@DairyFarm.IN ",
                "reply_to_email": "Support@DairyFarm.IN",
                "description": "Transactional mail",
            },
        )
        self.assertEqual(created.status_code, 201)
        sender = created.json()["sender"]
        self.assertEqual(sender["email"], "no-reply@dairyfarm.in")
        self.assertEqual(sender["reply_to_email"], "support@dairyfarm.in")
        self.assertTrue(sender["is_active"])
        self.assertEqual(sender["usage_count"], 0)

        listing = await self.client.get(
            "/api/v1/email-settings/senders", headers=self._auth()
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([item["id"] for item in listing.json()["items"]], [sender["id"]])

        fetched = await self.client.get(
            f"/api/v1/email-settings/senders/{sender['id']}",
            headers=self._auth(),
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["sender"]["display_name"], "Dairy No Reply")

        updated = await self.client.patch(
            f"/api/v1/email-settings/senders/{sender['id']}",
            headers=self._auth(),
            json={"display_name": "Farm No Reply"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["sender"]["display_name"], "Farm No Reply")

    async def test_sender_activate_and_deactivate_routes(self) -> None:
        sender = await self._create_sender()
        path = f"/api/v1/email-settings/senders/{sender['id']}"

        deactivated = await self.client.post(
            f"{path}/deactivate", headers=self._auth()
        )
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["sender"]["is_active"])

        activated = await self.client.post(f"{path}/activate", headers=self._auth())
        self.assertEqual(activated.status_code, 200)
        self.assertTrue(activated.json()["sender"]["is_active"])

    async def test_sender_validation_and_duplicate_email(self) -> None:
        invalid = await self.client.post(
            "/api/v1/email-settings/senders",
            headers=self._auth(),
            json={"display_name": "Bad", "email": "not-an-email"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "VALIDATION_ERROR")

        identical = await self.client.post(
            "/api/v1/email-settings/senders",
            headers=self._auth(),
            json={
                "display_name": "Same",
                "email": "same@example.com",
                "reply_to_email": "Same@Example.com",
            },
        )
        self.assertEqual(identical.status_code, 400)

        await self._create_sender(email="dup@example.com", reply_to_email=None)
        duplicate = await self.client.post(
            "/api/v1/email-settings/senders",
            headers=self._auth(),
            json={"display_name": "Other", "email": "DUP@example.com"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"]["code"], "SENDER_EMAIL_EXISTS")

    async def test_sender_delete_is_reference_safe(self) -> None:
        sender = await self._create_sender()
        path = f"/api/v1/email-settings/senders/{sender['id']}"
        self.repository.mappings = {
            "order.submitted": SimpleNamespace(
                sender_identity_id=sender["id"],
                reply_to_sender_identity_id=None,
            )
        }

        blocked = await self.client.delete(path, headers=self._auth())
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"]["code"], "SENDER_IN_USE")
        self.assertIn(sender["id"], self.repository.identities)

        self.repository.mappings = {}
        removed = await self.client.delete(path, headers=self._auth())
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(removed.content, b"")
        self.assertEqual(self.repository.identities, {})

        missing = await self.client.get(path, headers=self._auth())
        self.assertEqual(missing.status_code, 404)

    async def test_sender_routes_are_admin_only(self) -> None:
        sender = await self._create_sender()
        path = f"/api/v1/email-settings/senders/{sender['id']}"
        headers = self._auth(self.operator)

        get_list = await self.client.get(
            "/api/v1/email-settings/senders", headers=headers
        )
        get_one = await self.client.get(path, headers=headers)
        create = await self.client.post(
            "/api/v1/email-settings/senders",
            headers=headers,
            json={"display_name": "Nope", "email": "nope@example.com"},
        )
        patch = await self.client.patch(
            path, headers=headers, json={"display_name": "Nope"}
        )
        activate = await self.client.post(f"{path}/activate", headers=headers)
        deactivate = await self.client.post(f"{path}/deactivate", headers=headers)
        delete = await self.client.delete(path, headers=headers)

        for response in (
            get_list,
            get_one,
            create,
            patch,
            activate,
            deactivate,
            delete,
        ):
            self.assertEqual(response.status_code, 403, response.request.url)

        self.assertIn(sender["id"], self.repository.identities)


    async def test_workflow_catalogue_route(self) -> None:
        response = await self.client.get(
            "/api/v1/email-settings/workflows", headers=self._auth()
        )

        self.assertEqual(response.status_code, 200)
        categories = response.json()["categories"]
        self.assertEqual(len(categories), 6)
        events = {
            event["key"]
            for category in categories
            for event in category["events"]
        }
        self.assertIn("order.submitted", events)
        self.assertIn("account.staff_password_reset", events)

    async def test_workflow_mappings_round_trip(self) -> None:
        sender = await self._create_sender()
        initial = await self.client.get(
            "/api/v1/email-settings/workflow-mappings", headers=self._auth()
        )
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(
            [row["id"] for row in initial.json()["senders"]], [sender["id"]]
        )
        self.assertIsNone(initial.json()["application"]["sender_identity_id"])

        updated = await self.client.put(
            "/api/v1/email-settings/workflow-mappings",
            headers=self._auth(),
            json={
                "application": {"sender_identity_id": sender["id"]},
                "categories": [
                    {
                        "category_key": "customer_orders",
                        "sender_identity_id": sender["id"],
                    }
                ],
                "events": [
                    {"event_key": "order.submitted", "sender_identity_id": sender["id"]}
                ],
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()
        self.assertEqual(body["application"]["sender_identity_id"], sender["id"])
        categories = {row["category_key"]: row for row in body["categories"]}
        self.assertEqual(
            categories["customer_orders"]["sender_identity_id"], sender["id"]
        )
        events = {row["event_key"]: row for row in body["events"]}
        self.assertEqual(events["order.submitted"]["sender_identity_id"], sender["id"])

        reread = await self.client.get(
            "/api/v1/email-settings/workflow-mappings", headers=self._auth()
        )
        self.assertEqual(
            reread.json()["application"]["sender_identity_id"], sender["id"]
        )

    async def test_workflow_mapping_errors(self) -> None:
        unknown = await self.client.put(
            "/api/v1/email-settings/workflow-mappings",
            headers=self._auth(),
            json={"events": [{"event_key": "order.pending"}]},
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.json()["error"]["code"], "VALIDATION_ERROR")

        disabled = await self.client.put(
            "/api/v1/email-settings/workflow-mappings",
            headers=self._auth(),
            json={
                "events": [
                    {"event_key": "account.staff_password_reset", "is_enabled": False}
                ]
            },
        )
        self.assertEqual(disabled.status_code, 409)
        self.assertEqual(disabled.json()["error"]["code"], "WORKFLOW_NOT_DISABLEABLE")

        identical = await self.client.put(
            "/api/v1/email-settings/workflow-mappings",
            headers=self._auth(),
            json={
                "application": {
                    "sender_identity_id": 1,
                    "reply_to_sender_identity_id": 1,
                }
            },
        )
        self.assertEqual(identical.status_code, 400)
        self.assertEqual(identical.json()["error"]["code"], "VALIDATION_ERROR")

        sender = await self._create_sender()
        await self.client.post(
            f"/api/v1/email-settings/senders/{sender['id']}/deactivate",
            headers=self._auth(),
        )
        inactive = await self.client.put(
            "/api/v1/email-settings/workflow-mappings",
            headers=self._auth(),
            json={"application": {"sender_identity_id": sender["id"]}},
        )
        self.assertEqual(inactive.status_code, 409)
        self.assertEqual(inactive.json()["error"]["code"], "SENDER_INACTIVE")

    async def test_workflow_routes_are_admin_only(self) -> None:
        headers = self._auth(self.operator)

        responses = [
            await self.client.get(
                "/api/v1/email-settings/workflows", headers=headers
            ),
            await self.client.get(
                "/api/v1/email-settings/workflow-mappings", headers=headers
            ),
            await self.client.put(
                "/api/v1/email-settings/workflow-mappings",
                headers=headers,
                json={"application": {"sender_identity_id": 1}},
            ),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 403, response.request.url)
        self.assertEqual(self.repository.mappings, {})


class NotificationRecipientApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user(1, role="admin", username="admin")
        self.operator = make_user(2, role="operator", username="operator")
        self.repository = FakeRepository()
        self.audit = FakeAuditService()
        self.service = EmailSettingsService(
            self.repository,
            crypto=EmailSettingsCrypto(KEY),
            audit=self.audit,
            settings_obj=make_settings(),
            smtp_client=FakeSmtpClient(),
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

    def _auth(self, user: User | None = None) -> dict[str, str]:
        target = user or self.admin
        token = create_access_token(
            user_id=target.id,
            email=target.email,
            username=target.username,
            role=target.role,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}=test-session",
        }

    async def _create_recipient(self, **overrides) -> dict:
        body = {
            "scope": "event",
            "mapping_key": "order.submitted",
            "email": "ops@dairyfarm.in",
        }
        body.update(overrides)
        created = await self.client.post(
            "/api/v1/email-settings/recipients",
            headers=self._auth(),
            json=body,
        )
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()["recipient"]

    async def test_recipient_crud_routes(self) -> None:
        recipient = await self._create_recipient(email=" Ops@DairyFarm.IN ")
        self.assertEqual(recipient["email"], "ops@dairyfarm.in")
        self.assertEqual(recipient["scope"], "event")
        self.assertEqual(recipient["mapping_key"], "order.submitted")
        self.assertEqual(recipient["label"], "Order submitted")
        self.assertTrue(recipient["is_active"])
        path = f"/api/v1/email-settings/recipients/{recipient['id']}"

        listing = await self.client.get(
            "/api/v1/email-settings/recipients", headers=self._auth()
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listing.json()["items"]], [recipient["id"]]
        )

        patched = await self.client.patch(
            path,
            headers=self._auth(),
            json={"email": "ops2@dairyfarm.in"},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["recipient"]["email"], "ops2@dairyfarm.in")

        deactivated = await self.client.post(
            f"{path}/deactivate", headers=self._auth()
        )
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["recipient"]["is_active"])

        activated = await self.client.post(f"{path}/activate", headers=self._auth())
        self.assertEqual(activated.status_code, 200)
        self.assertTrue(activated.json()["recipient"]["is_active"])

        removed = await self.client.delete(path, headers=self._auth())
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(removed.content, b"")
        self.assertEqual(self.repository.recipients, {})

    async def test_recipient_can_target_a_category(self) -> None:
        recipient = await self._create_recipient(
            scope="category",
            mapping_key="customer_orders",
        )

        self.assertEqual(recipient["label"], "Customer Orders")
        self.assertEqual(
            self.repository.recipients[recipient["id"]].mapping_key,
            "category:customer_orders",
        )

    async def test_recipient_validation_and_duplicates(self) -> None:
        bad_scope = await self.client.post(
            "/api/v1/email-settings/recipients",
            headers=self._auth(),
            json={
                "scope": "global",
                "mapping_key": "order.submitted",
                "email": "ops@dairyfarm.in",
            },
        )
        self.assertEqual(bad_scope.status_code, 400)
        self.assertEqual(bad_scope.json()["error"]["code"], "VALIDATION_ERROR")

        bad_email = await self.client.post(
            "/api/v1/email-settings/recipients",
            headers=self._auth(),
            json={
                "scope": "event",
                "mapping_key": "order.submitted",
                "email": "not-an-address",
            },
        )
        self.assertEqual(bad_email.status_code, 400)

        unknown_key = await self.client.post(
            "/api/v1/email-settings/recipients",
            headers=self._auth(),
            json={
                "scope": "event",
                "mapping_key": "order.pending",
                "email": "ops@dairyfarm.in",
            },
        )
        self.assertEqual(unknown_key.status_code, 400)
        self.assertEqual(unknown_key.json()["error"]["code"], "VALIDATION_ERROR")

        await self._create_recipient()
        duplicate = await self.client.post(
            "/api/v1/email-settings/recipients",
            headers=self._auth(),
            json={
                "scope": "event",
                "mapping_key": "order.submitted",
                "email": "OPS@dairyfarm.in",
            },
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"]["code"], "RECIPIENT_EXISTS")

        missing = await self.client.patch(
            "/api/v1/email-settings/recipients/999",
            headers=self._auth(),
            json={},
        )
        self.assertEqual(missing.status_code, 404)

    async def test_recipient_routes_are_admin_only(self) -> None:
        recipient = await self._create_recipient()
        path = f"/api/v1/email-settings/recipients/{recipient['id']}"
        headers = self._auth(self.operator)

        responses = [
            await self.client.get(
                "/api/v1/email-settings/recipients", headers=headers
            ),
            await self.client.post(
                "/api/v1/email-settings/recipients",
                headers=headers,
                json={
                    "scope": "event",
                    "mapping_key": "order.approved",
                    "email": "nope@example.com",
                },
            ),
            await self.client.patch(path, headers=headers, json={"email": "x@y.co"}),
            await self.client.post(f"{path}/activate", headers=headers),
            await self.client.post(f"{path}/deactivate", headers=headers),
            await self.client.delete(path, headers=headers),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 403, response.request.url)
        self.assertEqual(len(self.repository.recipients), 1)


if __name__ == "__main__":
    unittest.main()
