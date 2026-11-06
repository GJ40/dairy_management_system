from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings
from app.models.email_notification_recipient import EmailNotificationRecipient
from app.models.email_sender_identity import EmailSenderIdentity
from app.models.email_smtp_profile import EmailSmtpProfile
from app.models.email_workflow_mapping import EmailWorkflowMapping
from app.schemas.email_settings import (
    UNSET,
    CreateNotificationRecipientRequest,
    CreateSenderIdentityRequest,
    CreateSmtpProfileRequest,
    ReplaceWorkflowMappingsRequest,
    SmtpTestEmailRequest,
    UpdateNotificationRecipientRequest,
    UpdateSenderIdentityRequest,
    UpdateSmtpProfileRequest,
    serialize_smtp_profile,
)
from app.services.email_config_resolver import (
    EmailConfigResolver,
    EmailConfigurationError,
)
from app.services.email_settings_crypto import (
    CredentialDecryptionFailed,
    EmailSettingsCrypto,
    EncryptionKeyUnavailable,
    compute_config_fingerprint,
)
from app.services.email_settings_service import (
    DAILY_TEST_LIMIT,
    EmailSettingsService,
)
from app.services.email_workflow_catalogue import (
    APPLICATION_MAPPING_KEY,
    CATEGORIES,
    EVENT_BY_KEY,
    EVENTS,
    mapping_key,
)
from app.services.smtp_test_client import SmtpProbeError, SmtpProbeTarget
from tests.audit_helpers import FakeAuditService

KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()


class FakeRepository:
    def __init__(self) -> None:
        self.profiles: dict[int, EmailSmtpProfile] = {}
        self.mappings: dict[str, object] = {}
        self.identities: dict[int, EmailSenderIdentity] = {}
        self.recipients: dict[int, EmailNotificationRecipient] = {}
        self.next_id = 1
        self.commits = 0
        # (actor_user_id, profile_id, naive UTC moment) test actions
        self.test_actions: list[tuple[int, int, datetime]] = []

    def add(self, instance) -> None:
        if instance.id is None:
            instance.id = self.next_id
            self.next_id += 1
        if isinstance(instance, EmailSenderIdentity):
            self.identities[instance.id] = instance
        elif isinstance(instance, EmailWorkflowMapping):
            self.mappings[instance.mapping_key] = instance
        elif isinstance(instance, EmailNotificationRecipient):
            self.recipients[instance.id] = instance
        else:
            self.profiles[instance.id] = instance

    async def delete(self, instance) -> None:
        if isinstance(instance, EmailSenderIdentity):
            self.identities.pop(instance.id, None)
        elif isinstance(instance, EmailWorkflowMapping):
            self.mappings.pop(instance.mapping_key, None)
        elif isinstance(instance, EmailNotificationRecipient):
            self.recipients.pop(instance.id, None)
        else:
            self.profiles.pop(instance.id, None)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None

    async def refresh(self, profile: EmailSmtpProfile) -> None:
        return None

    async def get_profile(self, profile_id: int) -> EmailSmtpProfile | None:
        return self.profiles.get(profile_id)

    async def list_profiles(self) -> list[EmailSmtpProfile]:
        return list(self.profiles.values())

    async def get_active_profile(self) -> EmailSmtpProfile | None:
        return next(
            (row for row in self.profiles.values() if row.active_slot == 1),
            None,
        )

    async def get_profile_for_update(
        self, profile_id: int
    ) -> EmailSmtpProfile | None:
        return self.profiles.get(profile_id)

    async def get_active_profile_for_update(self) -> EmailSmtpProfile | None:
        return await self.get_active_profile()

    async def latest_test_action_at(
        self,
        *,
        actor_user_id: int,
        profile_id: int,
        event_types,
        cutoff: datetime,
    ) -> datetime | None:
        moments = [
            moment
            for uid, pid, moment in self.test_actions
            if uid == actor_user_id and pid == profile_id and moment >= cutoff
        ]
        return max(moments) if moments else None

    async def count_test_actions(
        self,
        *,
        actor_user_id: int,
        since: datetime,
        event_types,
    ) -> int:
        return sum(
            1
            for uid, _pid, moment in self.test_actions
            if uid == actor_user_id and moment >= since
        )

    async def get_mapping(self, mapping_key: str):
        return self.mappings.get(mapping_key)

    async def list_mappings(self):
        return sorted(self.mappings.values(), key=lambda row: row.mapping_key)

    async def list_mappings_for_update(self):
        return await self.list_mappings()

    async def get_sender_identity(self, identity_id: int):
        return self.identities.get(identity_id)

    async def get_sender_identity_for_update(self, identity_id: int):
        return self.identities.get(identity_id)

    async def get_sender_identity_by_email(self, email: str):
        normalized = email.strip().lower()
        return next(
            (row for row in self.identities.values() if row.email == normalized),
            None,
        )

    async def list_senders(self):
        return sorted(
            self.identities.values(),
            key=lambda row: (row.display_name.lower(), row.id),
        )

    async def list_recipients(self):
        return sorted(
            self.recipients.values(),
            key=lambda row: (row.mapping_key, row.email),
        )

    async def get_recipient(self, recipient_id: int):
        return self.recipients.get(recipient_id)

    async def get_recipient_for_update(self, recipient_id: int):
        return self.recipients.get(recipient_id)

    async def list_active_recipients_for_keys(self, mapping_keys):
        keys = set(mapping_keys)
        return sorted(
            (
                row
                for row in self.recipients.values()
                if row.mapping_key in keys and row.is_active
            ),
            key=lambda row: row.email,
        )

    async def get_recipient_by_key_email(self, mapping_key: str, email: str):
        normalized = email.strip().lower()
        return next(
            (
                row
                for row in self.recipients.values()
                if row.mapping_key == mapping_key and row.email == normalized
            ),
            None,
        )

    async def sender_usage_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for mapping in self.mappings.values():
            for value in (
                getattr(mapping, "sender_identity_id", None),
                getattr(mapping, "reply_to_sender_identity_id", None),
            ):
                if value is not None:
                    counts[value] = counts.get(value, 0) + 1
        return counts


def make_profile(**overrides) -> EmailSmtpProfile:
    values = {
        "id": 1,
        "name": "Local Mailpit",
        "provider_mode": "mailpit",
        "host": "127.0.0.1",
        "port": 1025,
        "auth_enabled": False,
        "encryption_mode": "none",
        "timeout_seconds": 10,
        "status": "draft",
        "active_slot": None,
        "config_fingerprint": "f" * 64,
        "tested_fingerprint": None,
        "last_test_status": "never",
        "created_by": 1,
        "updated_by": 1,
    }
    values.update(overrides)
    return EmailSmtpProfile(**values)


def make_sender(**overrides) -> EmailSenderIdentity:
    values = {
        "id": 1,
        "display_name": "Ops",
        "email": "ops@example.com",
        "reply_to_email": "support@example.com",
        "is_active": True,
    }
    values.update(overrides)
    return EmailSenderIdentity(**values)


def make_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "smtp_host": "127.0.0.1",
        "smtp_port": 1025,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_use_tls": False,
        "smtp_use_ssl": False,
        "mail_from_email": "no-reply@dairyfarm.com",
        "mail_from_name": "Dairy",
    }
    values.update(overrides)
    return Settings(**values)


class FakeSmtpClient:
    """Replays a configured probe failure and records what was probed."""

    def __init__(self, *, failure: str | None = None) -> None:
        self.failure = failure
        self.connection_targets: list[SmtpProbeTarget] = []
        self.emails: list[dict[str, object]] = []

    async def test_connection(self, target: SmtpProbeTarget) -> None:
        self.connection_targets.append(target)
        if self.failure is not None:
            raise SmtpProbeError(self.failure)

    async def send_test_email(
        self,
        target: SmtpProbeTarget,
        *,
        recipient: str,
        mail_from: tuple[str, str],
    ) -> None:
        self.emails.append(
            {"target": target, "recipient": recipient, "mail_from": mail_from}
        )
        if self.failure is not None:
            raise SmtpProbeError(self.failure)


class CryptoUnitTests(unittest.TestCase):
    def test_roundtrip_and_ciphertext(self) -> None:
        crypto = EmailSettingsCrypto(KEY)
        ciphertext = crypto.encrypt("smtp-secret")
        self.assertNotEqual(ciphertext, "smtp-secret")
        self.assertNotIn("smtp-secret", ciphertext)
        self.assertEqual(crypto.decrypt(ciphertext), "smtp-secret")

    def test_missing_and_invalid_key(self) -> None:
        missing = EmailSettingsCrypto(None)
        self.assertFalse(missing.is_configured)
        with self.assertRaises(EncryptionKeyUnavailable):
            missing.encrypt("x")

        # A malformed key is handled like a missing one, so read endpoints
        # still answer; writes fail with the same safe code.
        invalid = EmailSettingsCrypto("not-a-fernet-key")
        self.assertFalse(invalid.is_configured)
        with self.assertRaises(EncryptionKeyUnavailable):
            invalid.encrypt("x")

    def test_wrong_key_raises_safe_error(self) -> None:
        ciphertext = EmailSettingsCrypto(KEY).encrypt("secret")
        with self.assertRaises(CredentialDecryptionFailed):
            EmailSettingsCrypto(OTHER_KEY).decrypt(ciphertext)

    def test_previous_key_rotation(self) -> None:
        old = EmailSettingsCrypto(KEY)
        ciphertext = old.encrypt("secret")

        rotated = EmailSettingsCrypto(OTHER_KEY, previous_key=KEY)
        self.assertEqual(rotated.decrypt(ciphertext), "secret")

        new_ciphertext = rotated.encrypt("secret")
        # New writes use the primary key, so the old key alone cannot read them.
        with self.assertRaises(CredentialDecryptionFailed):
            old.decrypt(new_ciphertext)

    def test_fingerprint_sensitivity(self) -> None:
        base = dict(
            provider_mode="custom",
            host="smtp.example.com",
            port=587,
            auth_enabled=True,
            encryption_mode="starttls",
            timeout_seconds=10,
            username_encrypted="user-cipher",
            password_encrypted="pass-cipher",
        )
        first = compute_config_fingerprint(**base)
        self.assertEqual(first, compute_config_fingerprint(**base))
        changed = dict(base, password_encrypted="new-pass-cipher")
        self.assertNotEqual(first, compute_config_fingerprint(**changed))
        self.assertNotEqual(
            first, compute_config_fingerprint(**dict(base, port=465))
        )


class SchemaTests(unittest.TestCase):
    def test_mailpit_valid(self) -> None:
        payload = CreateSmtpProfileRequest.model_validate(
            {
                "name": "Local Mailpit",
                "provider_mode": "mailpit",
                "host": "127.0.0.1",
                "port": 1025,
            }
        )
        self.assertFalse(payload.auth_enabled)
        self.assertEqual(payload.encryption_mode, "none")

    def test_mailpit_rejects_auth_and_tls(self) -> None:
        with self.assertRaises(ValueError):
            CreateSmtpProfileRequest.model_validate(
                {
                    "name": "Mailpit",
                    "provider_mode": "mailpit",
                    "host": "127.0.0.1",
                    "port": 1025,
                    "auth_enabled": True,
                }
            )
        with self.assertRaises(ValueError):
            CreateSmtpProfileRequest.model_validate(
                {
                    "name": "Mailpit",
                    "provider_mode": "mailpit",
                    "host": "127.0.0.1",
                    "port": 1025,
                    "encryption_mode": "starttls",
                }
            )

    def test_auth_requires_credentials(self) -> None:
        with self.assertRaises(ValueError):
            CreateSmtpProfileRequest.model_validate(
                {
                    "name": "SMTP",
                    "provider_mode": "custom",
                    "host": "smtp.example.com",
                    "port": 587,
                    "auth_enabled": True,
                    "username": "user",
                    "encryption_mode": "starttls",
                }
            )

    def test_auth_disabled_rejects_credentials(self) -> None:
        with self.assertRaises(ValueError):
            CreateSmtpProfileRequest.model_validate(
                {
                    "name": "SMTP",
                    "provider_mode": "custom",
                    "host": "smtp.example.com",
                    "port": 587,
                    "username": "user",
                    "password": "secret",
                }
            )

    def test_invalid_host_and_port(self) -> None:
        with self.assertRaises(ValueError):
            CreateSmtpProfileRequest.model_validate(
                {
                    "name": "SMTP",
                    "provider_mode": "custom",
                    "host": "smtp://example.com",
                    "port": 587,
                }
            )
        with self.assertRaises(ValueError):
            CreateSmtpProfileRequest.model_validate(
                {
                    "name": "SMTP",
                    "provider_mode": "custom",
                    "host": "smtp.example.com",
                    "port": 70000,
                }
            )

    def test_update_keeps_unset_and_null(self) -> None:
        payload = UpdateSmtpProfileRequest.model_validate({"username": None})
        self.assertIs(payload.username, None)
        self.assertIs(payload.password, UNSET)
        self.assertIs(payload.name, UNSET)

    def test_test_email_recipient_validation(self) -> None:
        payload = SmtpTestEmailRequest.model_validate(
            {"recipient_email": " Admin@Example.COM "}
        )
        self.assertEqual(payload.recipient_email, "admin@example.com")
        for body in (
            {},
            {"recipient_email": "not-an-email"},
            {"recipient_email": 5},
            {"recipient_email": "admin@example"},
        ):
            with self.assertRaises(ValueError):
                SmtpTestEmailRequest.model_validate(body)

    def test_serializer_hides_credentials(self) -> None:
        profile = make_profile()
        profile.username_encrypted = "user-cipher"
        profile.password_encrypted = "pass-cipher"
        data = serialize_smtp_profile(profile)
        self.assertTrue(data["username_configured"])
        self.assertTrue(data["password_configured"])
        self.assertNotIn("user-cipher", str(data))
        self.assertNotIn("pass-cipher", str(data))
        self.assertNotIn("username_encrypted", data)
        self.assertNotIn("password_encrypted", data)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.audit = FakeAuditService()
        self.crypto = EmailSettingsCrypto(KEY)
        self.service = EmailSettingsService(
            self.repository,
            crypto=self.crypto,
            audit=self.audit,
            settings_obj=make_settings(),
        )

    async def test_create_draft_encrypts_and_audits(self) -> None:
        payload = CreateSmtpProfileRequest.model_validate(
            {
                "name": "Production SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 587,
                "auth_enabled": True,
                "username": "mailer@example.com",
                "password": "smtp-secret",
                "encryption_mode": "starttls",
            }
        )
        result = await self.service.create_draft(payload, actor_user_id=7)
        profile = result["profile"]
        stored = self.repository.profiles[profile["id"]]

        self.assertEqual(stored.status, "draft")
        self.assertIsNone(stored.active_slot)
        self.assertNotEqual(stored.password_encrypted, "smtp-secret")
        self.assertNotIn("smtp-secret", str(profile))
        self.assertTrue(profile["username_configured"])
        self.assertTrue(profile["password_configured"])
        self.assertEqual(len(stored.config_fingerprint), 64)
        self.assertEqual(self.audit.records[-1]["event_type"], "email.smtp_draft_created")
        self.assertNotIn("smtp-secret", str(self.audit.records))

    async def test_create_auth_draft_requires_key(self) -> None:
        service = EmailSettingsService(
            self.repository,
            crypto=EmailSettingsCrypto(None),
            audit=self.audit,
            settings_obj=make_settings(),
        )
        payload = CreateSmtpProfileRequest.model_validate(
            {
                "name": "SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 587,
                "auth_enabled": True,
                "username": "user",
                "password": "secret",
                "encryption_mode": "starttls",
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await service.create_draft(payload, actor_user_id=7)
        self.assertEqual(caught.exception.detail["code"], "ENCRYPTION_KEY_UNAVAILABLE")

    async def test_update_reencrypts_and_invalidates_test(self) -> None:
        payload = CreateSmtpProfileRequest.model_validate(
            {
                "name": "SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 587,
                "auth_enabled": True,
                "username": "user",
                "password": "secret",
                "encryption_mode": "starttls",
            }
        )
        created = await self.service.create_draft(payload, actor_user_id=7)
        profile_id = created["profile"]["id"]
        profile = self.repository.profiles[profile_id]
        profile.tested_fingerprint = profile.config_fingerprint
        profile.last_test_status = "success"
        old_fingerprint = profile.config_fingerprint

        update = UpdateSmtpProfileRequest.model_validate(
            {"port": 465, "encryption_mode": "ssl", "password": "new-secret"}
        )
        updated = await self.service.update_draft(
            profile_id, update, actor_user_id=7
        )
        profile = self.repository.profiles[profile_id]

        self.assertEqual(profile.port, 465)
        self.assertEqual(profile.encryption_mode, "ssl")
        self.assertNotIn("new-secret", str(updated))
        self.assertNotEqual(profile.config_fingerprint, old_fingerprint)
        self.assertIsNone(profile.tested_fingerprint)
        self.assertEqual(self.audit.records[-1]["event_type"], "email.smtp_draft_updated")
        self.assertEqual(
            self.audit.records[-1]["metadata"]["changed_fields"],
            ["port", "encryption_mode", "credentials"],
        )

    async def test_non_draft_not_editable(self) -> None:
        self.repository.profiles[1] = make_profile(status="active", active_slot=1)
        with self.assertRaises(HTTPException) as caught:
            await self.service.update_draft(
                1,
                UpdateSmtpProfileRequest.model_validate({"name": "New"}),
                actor_user_id=7,
            )
        self.assertEqual(caught.exception.detail["code"], "PROFILE_NOT_EDITABLE")

    async def test_disabling_auth_clears_credentials(self) -> None:
        payload = CreateSmtpProfileRequest.model_validate(
            {
                "name": "SMTP",
                "provider_mode": "custom",
                "host": "smtp.example.com",
                "port": 587,
                "auth_enabled": True,
                "username": "user",
                "password": "secret",
            }
        )
        created = await self.service.create_draft(payload, actor_user_id=7)
        profile_id = created["profile"]["id"]
        await self.service.update_draft(
            profile_id,
            UpdateSmtpProfileRequest.model_validate({"auth_enabled": False}),
            actor_user_id=7,
        )
        profile = self.repository.profiles[profile_id]
        self.assertIsNone(profile.username_encrypted)
        self.assertIsNone(profile.password_encrypted)

    async def test_multiple_drafts_allowed_and_none_active(self) -> None:
        payload = CreateSmtpProfileRequest.model_validate(
            {
                "name": "Local Mailpit",
                "provider_mode": "mailpit",
                "host": "127.0.0.1",
                "port": 1025,
            }
        )
        first = await self.service.create_draft(payload, actor_user_id=7)
        second = await self.service.create_draft(payload, actor_user_id=7)
        self.assertNotEqual(first["profile"]["id"], second["profile"]["id"])

        overview = await self.service.get_overview()
        self.assertEqual(len(overview["profiles"]), 2)
        self.assertIsNone(overview["active_profile"])
        self.assertEqual(overview["source"], "environment")
        self.assertTrue(all(p["status"] == "draft" for p in overview["profiles"]))

    async def test_overview_source_and_profiles(self) -> None:
        overview = await self.service.get_overview()
        self.assertEqual(overview["source"], "environment")
        self.assertEqual(overview["profiles"], [])
        self.assertIn("environment", overview)
        self.assertNotIn("password", overview["environment"])


class ResolverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.crypto = EmailSettingsCrypto(KEY)

    async def test_environment_fallback(self) -> None:
        resolver = EmailConfigResolver(
            self.repository,
            crypto=self.crypto,
            settings_obj=make_settings(),
        )
        config = await resolver.resolve()
        self.assertEqual(config.source, "environment")
        self.assertEqual(config.transport.host, "127.0.0.1")
        self.assertEqual(config.from_email, "no-reply@dairyfarm.com")
        self.assertIsNone(config.reply_to_email)

    async def test_missing_environment_configuration(self) -> None:
        resolver = EmailConfigResolver(
            self.repository,
            crypto=self.crypto,
            settings_obj=make_settings(smtp_host=""),
        )
        with self.assertRaises(EmailConfigurationError) as caught:
            await resolver.resolve()
        self.assertEqual(caught.exception.code, "EMAIL_NOT_CONFIGURED")

    async def test_active_database_profile_decrypts(self) -> None:
        profile = make_profile(
            provider_mode="custom",
            host="smtp.example.com",
            port=587,
            auth_enabled=True,
            encryption_mode="starttls",
            status="active",
            active_slot=1,
            username_encrypted=self.crypto.encrypt("user"),
            password_encrypted=self.crypto.encrypt("secret"),
        )
        self.repository.profiles[1] = profile
        resolver = EmailConfigResolver(
            self.repository,
            crypto=self.crypto,
            settings_obj=make_settings(),
        )
        config = await resolver.resolve()
        self.assertEqual(config.source, "database")
        self.assertEqual(config.transport.username, "user")
        self.assertEqual(config.transport.password, "secret")
        self.assertNotIn("user", repr(config.transport))
        self.assertNotIn("secret", repr(config.transport))
        self.assertEqual(config.transport.encryption_mode, "starttls")

    async def test_active_profile_without_key_does_not_fall_back(self) -> None:
        profile = make_profile(
            provider_mode="custom",
            host="smtp.example.com",
            port=587,
            auth_enabled=True,
            status="active",
            active_slot=1,
            username_encrypted="user-cipher",
            password_encrypted="pass-cipher",
        )
        self.repository.profiles[1] = profile
        resolver = EmailConfigResolver(
            self.repository,
            crypto=EmailSettingsCrypto(None),
            settings_obj=make_settings(),
        )
        with self.assertRaises(EmailConfigurationError) as caught:
            await resolver.resolve()
        self.assertEqual(caught.exception.code, "ENCRYPTION_KEY_UNAVAILABLE")

    async def test_sender_precedence_and_reply_to(self) -> None:
        event_sender = make_sender(id=2, display_name="Orders", email="orders@example.com")
        reply_identity = make_sender(
            id=3,
            display_name="Support",
            email="support@example.com",
            reply_to_email="help@example.com",
        )
        self.repository.identities = {2: event_sender, 3: reply_identity}
        self.repository.mappings = {
            "event:order.submitted": SimpleNamespace(
                sender_identity_id=2,
                reply_to_sender_identity_id=3,
            ),
            "category:customer_orders": SimpleNamespace(
                sender_identity_id=None,
                reply_to_sender_identity_id=None,
            ),
            "application:default": SimpleNamespace(
                sender_identity_id=None,
                reply_to_sender_identity_id=None,
            ),
        }
        resolver = EmailConfigResolver(
            self.repository,
            crypto=self.crypto,
            settings_obj=make_settings(),
        )
        config = await resolver.resolve(
            "order.submitted", category_key="customer_orders"
        )
        self.assertEqual(config.from_email, "orders@example.com")
        self.assertEqual(config.from_name, "Orders")
        self.assertEqual(config.reply_to_email, "help@example.com")

    async def test_category_reply_to_applies_when_event_has_sender(self) -> None:
        event_sender = make_sender(
            id=2, display_name="Orders", email="orders@example.com"
        )
        category_reply = make_sender(
            id=4,
            display_name="Category support",
            email="cat-support@example.com",
            reply_to_email="cat-reply@example.com",
        )
        self.repository.identities = {2: event_sender, 4: category_reply}
        self.repository.mappings = {
            "event:order.submitted": SimpleNamespace(
                sender_identity_id=2,
                reply_to_sender_identity_id=None,
            ),
            "category:customer_orders": SimpleNamespace(
                sender_identity_id=None,
                reply_to_sender_identity_id=4,
            ),
        }
        resolver = EmailConfigResolver(
            self.repository,
            crypto=self.crypto,
            settings_obj=make_settings(),
        )
        config = await resolver.resolve(
            "order.submitted", category_key="customer_orders"
        )
        self.assertEqual(config.from_email, "orders@example.com")
        self.assertEqual(config.reply_to_email, "cat-reply@example.com")

    async def test_inactive_sender_falls_through(self) -> None:
        self.repository.identities = {
            2: make_sender(id=2, is_active=False, email="inactive@example.com")
        }
        self.repository.mappings = {
            "event:order.submitted": SimpleNamespace(
                sender_identity_id=2,
                reply_to_sender_identity_id=None,
            )
        }
        resolver = EmailConfigResolver(
            self.repository,
            crypto=self.crypto,
            settings_obj=make_settings(),
        )
        config = await resolver.resolve("order.submitted")
        self.assertEqual(config.from_email, "no-reply@dairyfarm.com")
        self.assertIn("EVENT_SENDER_INACTIVE", config.diagnostics)


NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


class SmtpTestAndActivationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.audit = FakeAuditService()
        self.crypto = EmailSettingsCrypto(KEY)
        self.smtp_client = FakeSmtpClient()
        self.service = EmailSettingsService(
            self.repository,
            crypto=self.crypto,
            audit=self.audit,
            settings_obj=make_settings(),
            smtp_client=self.smtp_client,
            clock=lambda: NOW,
        )

    def _auth_draft(self, **overrides) -> EmailSmtpProfile:
        values = dict(
            provider_mode="custom",
            host="smtp.example.com",
            port=587,
            auth_enabled=True,
            encryption_mode="starttls",
            username_encrypted=self.crypto.encrypt("mailer@example.com"),
            password_encrypted=self.crypto.encrypt("smtp-secret"),
        )
        values.update(overrides)
        profile = make_profile(**values)
        self.repository.profiles[profile.id] = profile
        return profile

    async def test_connection_success_persists_verification(self) -> None:
        self._auth_draft()

        result = await self.service.test_connection(1, actor_user_id=11)

        self.assertEqual(result["test_kind"], "connection")
        self.assertEqual(result["test_status"], "success")
        self.assertIsNone(result["reason_code"])
        self.assertEqual(result["tested_at"], "2026-11-06T12:00:00.000Z")
        stored = self.repository.profiles[1]
        self.assertEqual(stored.last_test_status, "success")
        self.assertEqual(stored.last_test_kind, "connection")
        self.assertEqual(stored.tested_fingerprint, stored.config_fingerprint)
        self.assertIsNotNone(stored.last_tested_at)
        self.assertEqual(
            self.audit.records[-1]["event_type"], "email.smtp_connection_tested"
        )
        self.assertNotIn("smtp-secret", str(result))
        self.assertNotIn("smtp-secret", str(self.audit.records))
        # The probe receives the decrypted credentials in memory only.
        self.assertEqual(self.smtp_client.connection_targets[0].password, "smtp-secret")
        self.assertNotIn("smtp-secret", repr(self.smtp_client.connection_targets[0]))

    async def test_connection_failure_is_reported_without_secrets(self) -> None:
        self._auth_draft()
        self.smtp_client.failure = "AUTH_FAILED"

        result = await self.service.test_connection(1, actor_user_id=11)

        self.assertEqual(result["test_status"], "failure")
        self.assertEqual(result["reason_code"], "AUTH_FAILED")
        self.assertIn("rejected the login", result["message"])
        stored = self.repository.profiles[1]
        self.assertEqual(stored.last_test_status, "failure")
        self.assertIsNone(stored.tested_fingerprint)
        record = self.audit.records[-1]
        self.assertEqual(
            record["event_type"], "email.smtp_connection_test_failed"
        )
        self.assertEqual(record["metadata"]["reason_code"], "AUTH_FAILED")
        self.assertEqual(record["reason_code"], "AUTH_FAILED")
        self.assertNotIn("smtp-secret", str(record))

    async def test_test_email_uses_explicit_recipient_and_environment_from(self) -> None:
        self._auth_draft()

        result = await self.service.test_email(
            1, recipient_email="admin@example.com", actor_user_id=11
        )

        self.assertEqual(result["test_kind"], "email")
        self.assertEqual(result["test_status"], "success")
        sent = self.smtp_client.emails[0]
        self.assertEqual(sent["recipient"], "admin@example.com")
        self.assertEqual(sent["mail_from"], ("Dairy", "no-reply@dairyfarm.com"))
        self.assertEqual(
            self.audit.records[-1]["event_type"], "email.smtp_test_email_sent"
        )
        self.assertNotIn("smtp-secret", str(self.audit.records))

    async def test_test_email_failure_is_reported(self) -> None:
        self._auth_draft()
        self.smtp_client.failure = "SERVER_REJECTED"

        result = await self.service.test_email(
            1, recipient_email="admin@example.com", actor_user_id=11
        )

        self.assertEqual(result["test_status"], "failure")
        self.assertEqual(result["reason_code"], "SERVER_REJECTED")
        self.assertEqual(
            self.audit.records[-1]["event_type"], "email.smtp_test_email_failed"
        )

    async def test_activation_requires_a_successful_test(self) -> None:
        self.repository.profiles[1] = make_profile()

        with self.assertRaises(HTTPException) as caught:
            await self.service.activate(1, actor_user_id=11)

        self.assertEqual(caught.exception.detail["code"], "SMTP_TEST_REQUIRED")
        self.assertIsNone(self.repository.profiles[1].active_slot)

    async def test_activation_rejects_configuration_changed_after_the_test(self) -> None:
        self.repository.profiles[1] = make_profile(
            last_test_status="success", tested_fingerprint="0" * 64
        )

        with self.assertRaises(HTTPException) as caught:
            await self.service.activate(1, actor_user_id=11)

        self.assertEqual(
            caught.exception.detail["code"], "SMTP_CONFIG_CHANGED_SINCE_TEST"
        )

    async def test_activation_archives_the_previous_profile(self) -> None:
        previous = make_profile(id=2, name="Old SMTP", status="active", active_slot=1)
        self.repository.profiles[2] = previous
        self.repository.profiles[1] = make_profile(
            last_test_status="success", tested_fingerprint="f" * 64
        )

        overview = await self.service.activate(1, actor_user_id=11)

        self.assertEqual(overview["source"], "database")
        self.assertEqual(overview["active_profile"]["id"], 1)
        self.assertEqual(self.repository.profiles[1].status, "active")
        self.assertEqual(self.repository.profiles[1].active_slot, 1)
        self.assertIsNotNone(self.repository.profiles[1].activated_at)
        self.assertEqual(previous.status, "archived")
        self.assertIsNone(previous.active_slot)
        record = self.audit.records[-1]
        self.assertEqual(record["event_type"], "email.smtp_activated")
        self.assertEqual(record["metadata"]["previous_profile_id"], 2)
        self.assertEqual(record["metadata"]["previous_source"], "database")

    async def test_activation_without_the_encryption_key_is_blocked(self) -> None:
        self.repository.profiles[1] = make_profile(
            auth_enabled=True,
            username_encrypted="user-cipher",
            password_encrypted="pass-cipher",
            last_test_status="success",
            tested_fingerprint="f" * 64,
        )
        service = EmailSettingsService(
            self.repository,
            crypto=EmailSettingsCrypto(None),
            audit=self.audit,
            settings_obj=make_settings(),
            smtp_client=self.smtp_client,
            clock=lambda: NOW,
        )

        with self.assertRaises(HTTPException) as caught:
            await service.activate(1, actor_user_id=11)

        self.assertEqual(
            caught.exception.detail["code"], "ENCRYPTION_KEY_UNAVAILABLE"
        )
        self.assertIsNone(self.repository.profiles[1].active_slot)

    async def test_use_environment_archives_once_and_is_idempotent(self) -> None:
        self.repository.profiles[2] = make_profile(
            id=2, status="active", active_slot=1
        )

        overview = await self.service.use_environment(actor_user_id=11)

        self.assertEqual(overview["source"], "environment")
        self.assertIsNone(overview["active_profile"])
        self.assertEqual(self.repository.profiles[2].status, "archived")
        self.assertEqual(
            self.audit.records[-1]["event_type"],
            "email.smtp_environment_fallback_enabled",
        )
        recorded = len(self.audit.records)

        await self.service.use_environment(actor_user_id=11)

        self.assertEqual(len(self.audit.records), recorded)

    async def test_repeated_tests_are_rate_limited_per_admin_and_profile(self) -> None:
        self.repository.profiles[1] = make_profile()
        self.repository.test_actions.append((11, 1, NOW.replace(tzinfo=None)))

        with self.assertRaises(HTTPException) as caught:
            await self.service.test_connection(1, actor_user_id=11)

        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.detail["code"], "RATE_LIMITED")
        self.assertGreaterEqual(caught.exception.detail["retry_after_seconds"], 1)
        self.assertEqual(self.smtp_client.connection_targets, [])

    async def test_cooldown_is_per_admin(self) -> None:
        self.repository.profiles[1] = make_profile()
        self.repository.test_actions.append((99, 1, NOW.replace(tzinfo=None)))

        result = await self.service.test_connection(1, actor_user_id=11)

        self.assertEqual(result["test_status"], "success")

    async def test_daily_test_limit_is_enforced(self) -> None:
        self.repository.profiles[1] = make_profile()
        moment = NOW.replace(tzinfo=None)
        self.repository.test_actions.extend(
            (11, 99, moment) for _ in range(DAILY_TEST_LIMIT)
        )

        with self.assertRaises(HTTPException) as caught:
            await self.service.test_connection(1, actor_user_id=11)

        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.detail["code"], "RATE_LIMITED")
        self.assertGreaterEqual(caught.exception.detail["retry_after_seconds"], 1)

    async def test_testing_a_draft_leaves_the_active_profile_alone(self) -> None:
        active = make_profile(id=2, status="active", active_slot=1)
        self.repository.profiles[2] = active
        draft = self._auth_draft()

        await self.service.test_connection(1, actor_user_id=11)

        self.assertEqual(active.status, "active")
        self.assertEqual(active.active_slot, 1)
        self.assertEqual(active.last_test_status, "never")
        self.assertIsNone(active.tested_fingerprint)
        self.assertEqual(draft.tested_fingerprint, draft.config_fingerprint)


class SenderIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.audit = FakeAuditService()
        self.service = EmailSettingsService(
            self.repository,
            crypto=EmailSettingsCrypto(KEY),
            audit=self.audit,
            settings_obj=make_settings(),
        )

    def _payload(self, **overrides) -> CreateSenderIdentityRequest:
        body = {
            "display_name": "Dairy No Reply",
            "email": " No-Reply@DairyFarm.IN ",
            "reply_to_email": "Support@DairyFarm.IN",
            "description": "Automated transactional mail",
        }
        body.update(overrides)
        return CreateSenderIdentityRequest.model_validate(body)

    async def test_create_normalizes_email_and_audits(self) -> None:
        created = await self.service.create_sender(self._payload(), actor_user_id=7)

        sender = created["sender"]
        self.assertEqual(sender["email"], "no-reply@dairyfarm.in")
        self.assertEqual(sender["reply_to_email"], "support@dairyfarm.in")
        self.assertTrue(sender["is_active"])
        self.assertEqual(sender["usage_count"], 0)

        record = self.audit.records[-1]
        self.assertEqual(record["event_type"], "email.sender_created")
        self.assertEqual(record["resource_type"], "email_sender_identity")
        self.assertEqual(record["resource_id"], sender["id"])
        self.assertEqual(
            record["metadata"],
            {"sender_id": sender["id"], "is_active": True},
        )

    async def test_duplicate_email_rejected(self) -> None:
        await self.service.create_sender(self._payload(), actor_user_id=7)

        with self.assertRaises(HTTPException) as caught:
            await self.service.create_sender(
                self._payload(display_name="Second", reply_to_email=None),
                actor_user_id=7,
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "SENDER_EMAIL_EXISTS")

    async def test_identical_reply_to_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CreateSenderIdentityRequest.model_validate(
                {
                    "display_name": "Same",
                    "email": "same@example.com",
                    "reply_to_email": "same@example.com",
                }
            )

    async def test_update_changes_fields_and_audits(self) -> None:
        created = await self.service.create_sender(self._payload(), actor_user_id=7)
        sender_id = created["sender"]["id"]

        updated = await self.service.update_sender(
            sender_id,
            UpdateSenderIdentityRequest.model_validate(
                {"display_name": "Farm Support", "reply_to_email": None}
            ),
            actor_user_id=7,
        )

        self.assertEqual(updated["sender"]["display_name"], "Farm Support")
        self.assertIsNone(updated["sender"]["reply_to_email"])
        self.assertEqual(
            self.audit.records[-1]["metadata"]["changed_fields"],
            ["display_name", "reply_to_email"],
        )

    async def test_update_to_existing_email_rejected(self) -> None:
        await self.service.create_sender(self._payload(), actor_user_id=7)
        second = await self.service.create_sender(
            self._payload(email="orders@dairyfarm.in", reply_to_email=None),
            actor_user_id=7,
        )

        with self.assertRaises(HTTPException) as caught:
            await self.service.update_sender(
                second["sender"]["id"],
                UpdateSenderIdentityRequest.model_validate(
                    {"email": "no-reply@dairyfarm.in"}
                ),
                actor_user_id=7,
            )

        self.assertEqual(caught.exception.detail["code"], "SENDER_EMAIL_EXISTS")

    async def test_merged_reply_to_equal_to_email_rejected(self) -> None:
        await self.service.create_sender(self._payload(), actor_user_id=7)

        with self.assertRaises(HTTPException) as caught:
            await self.service.update_sender(
                1,
                UpdateSenderIdentityRequest.model_validate(
                    {"email": "support@dairyfarm.in"}
                ),
                actor_user_id=7,
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail["code"], "VALIDATION_ERROR")

    async def test_noop_update_writes_no_audit(self) -> None:
        created = await self.service.create_sender(self._payload(), actor_user_id=7)
        recorded = len(self.audit.records)

        await self.service.update_sender(
            created["sender"]["id"],
            UpdateSenderIdentityRequest.model_validate(
                {"display_name": "Dairy No Reply"}
            ),
            actor_user_id=7,
        )

        self.assertEqual(len(self.audit.records), recorded)

    async def test_activate_and_deactivate_are_audited_and_idempotent(self) -> None:
        created = await self.service.create_sender(self._payload(), actor_user_id=7)
        sender_id = created["sender"]["id"]

        deactivated = await self.service.deactivate_sender(sender_id, actor_user_id=7)
        self.assertFalse(deactivated["sender"]["is_active"])
        self.assertEqual(self.audit.records[-1]["event_type"], "email.sender_deactivated")

        recorded = len(self.audit.records)
        await self.service.deactivate_sender(sender_id, actor_user_id=7)
        self.assertEqual(len(self.audit.records), recorded)

        reactivated = await self.service.activate_sender(sender_id, actor_user_id=7)
        self.assertTrue(reactivated["sender"]["is_active"])
        self.assertEqual(self.audit.records[-1]["event_type"], "email.sender_activated")

    async def test_list_orders_by_display_name_and_counts_usage(self) -> None:
        self.repository.identities = {
            1: make_sender(id=1),
            2: make_sender(
                id=2,
                display_name="Orders",
                email="orders@example.com",
                reply_to_email=None,
            ),
        }
        self.repository.mappings = {
            "event:order.submitted": SimpleNamespace(
                sender_identity_id=1,
                reply_to_sender_identity_id=2,
            ),
            "application:default": SimpleNamespace(
                sender_identity_id=1,
                reply_to_sender_identity_id=None,
            ),
        }

        listing = await self.service.list_senders()

        self.assertEqual(
            [item["display_name"] for item in listing["items"]],
            ["Ops", "Orders"],
        )
        by_id = {item["id"]: item for item in listing["items"]}
        self.assertEqual(by_id[1]["usage_count"], 2)
        self.assertEqual(by_id[2]["usage_count"], 1)

    async def test_delete_blocked_when_referenced(self) -> None:
        self.repository.identities = {1: make_sender(id=1)}
        self.repository.mappings = {
            "event:order.submitted": SimpleNamespace(
                sender_identity_id=1,
                reply_to_sender_identity_id=None,
            )
        }

        with self.assertRaises(HTTPException) as caught:
            await self.service.delete_sender(1, actor_user_id=7)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "SENDER_IN_USE")
        self.assertIn(1, self.repository.identities)

    async def test_delete_removes_unused_sender_and_audits(self) -> None:
        self.repository.identities = {1: make_sender(id=1)}

        await self.service.delete_sender(1, actor_user_id=7)

        self.assertEqual(self.repository.identities, {})
        record = self.audit.records[-1]
        self.assertEqual(record["event_type"], "email.sender_removed")
        self.assertEqual(record["resource_type"], "email_sender_identity")
        self.assertEqual(record["metadata"], {"sender_id": 1})

    async def test_missing_sender_is_404(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.get_sender(99)

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail["code"], "NOT_FOUND")


class WorkflowCatalogueTests(unittest.TestCase):
    def test_every_event_belongs_to_a_known_category(self) -> None:
        category_keys = {category.key for category in CATEGORIES}

        for event in EVENTS:
            self.assertIn(event.category_key, category_keys)

    def test_security_and_onboarding_events_cannot_be_disabled(self) -> None:
        required = {
            key for key, event in EVENT_BY_KEY.items() if not event.allow_disable
        }

        self.assertIn("account.staff_password_reset", required)
        self.assertIn("account.customer_account_locked", required)
        self.assertIn("portal.customer_activation", required)
        self.assertNotIn("order.submitted", required)

    def test_support_and_billing_events_are_targetable(self) -> None:
        received = EVENT_BY_KEY["support.query_received"]
        self.assertEqual(received.category_key, "customer_support")
        self.assertEqual(received.audience, "staff")
        self.assertTrue(received.implemented)
        self.assertTrue(received.allow_disable)

        answered = EVENT_BY_KEY["support.query_answered"]
        self.assertEqual(answered.audience, "customer")
        self.assertTrue(answered.implemented)

        payment = EVENT_BY_KEY["billing.payment_received"]
        self.assertEqual(payment.category_key, "billing_payments")
        self.assertEqual(payment.audience, "customer")
        self.assertTrue(payment.implemented)

    def test_only_the_reserved_category_is_empty(self) -> None:
        """Customer Support and Billing now deliver; one category stays reserved.

        ``internal_administration`` is deliberately without events until a real
        admin-facing trigger exists (PROGRESS 12). Asserting the exact empty set
        still catches a category added later without a workflow behind it.
        """
        filled = {event.category_key for event in EVENTS}
        empty = {category.key for category in CATEGORIES} - filled

        self.assertEqual(empty, {"internal_administration"})
        self.assertIn("customer_support", filled)
        self.assertIn("billing_payments", filled)

    def test_order_events_are_implemented_and_disableable(self) -> None:
        for key in (
            "order.submitted",
            "order.approved",
            "order.rejected",
            "order.cancelled",
            "order.fulfilled",
        ):
            self.assertTrue(EVENT_BY_KEY[key].implemented)
            self.assertTrue(EVENT_BY_KEY[key].allow_disable)
            self.assertEqual(EVENT_BY_KEY[key].audience, "customer")

    def test_mapping_keys_are_scoped(self) -> None:
        self.assertEqual(
            mapping_key("event", "order.submitted"), "event:order.submitted"
        )
        self.assertEqual(
            mapping_key("category", "customer_orders"), "category:customer_orders"
        )
        self.assertEqual(APPLICATION_MAPPING_KEY, "application:default")


class WorkflowMappingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.audit = FakeAuditService()
        self.service = EmailSettingsService(
            self.repository,
            crypto=EmailSettingsCrypto(KEY),
            audit=self.audit,
            settings_obj=make_settings(),
        )

    def _payload(self, **overrides) -> ReplaceWorkflowMappingsRequest:
        body = {"application": {"sender_identity_id": 1}}
        body.update(overrides)
        return ReplaceWorkflowMappingsRequest.model_validate(body)

    async def _sender(self, **overrides) -> int:
        body = {"display_name": "Ops", "email": "ops@example.com"}
        body.update(overrides)
        created = await self.service.create_sender(
            CreateSenderIdentityRequest.model_validate(body),
            actor_user_id=7,
        )
        return created["sender"]["id"]

    async def test_catalogue_lists_every_category_and_event(self) -> None:
        catalogue = await self.service.get_workflow_catalogue()

        self.assertEqual(
            [row["key"] for row in catalogue["categories"]],
            [category.key for category in CATEGORIES],
        )
        first_event = catalogue["categories"][0]["events"][0]
        self.assertEqual(
            set(first_event),
            {
                "key",
                "name",
                "description",
                "audience",
                "implemented",
                "allow_disable",
                "default_sender_identity_id",
            },
        )
        listed = sum(len(row["events"]) for row in catalogue["categories"])
        self.assertEqual(listed, len(EVENTS))

    async def test_mappings_start_without_overrides(self) -> None:
        mappings = await self.service.get_workflow_mappings()

        self.assertEqual(mappings["senders"], [])
        self.assertIsNone(mappings["application"]["sender_identity_id"])
        self.assertEqual(
            [row["category_key"] for row in mappings["categories"]],
            [category.key for category in CATEGORIES],
        )
        events = {row["event_key"]: row for row in mappings["events"]}
        self.assertIsNone(events["order.submitted"]["sender_identity_id"])
        self.assertTrue(events["order.submitted"]["is_enabled"])

    async def test_replace_creates_rows_and_audits_each_one(self) -> None:
        sender_id = await self._sender()
        payload = self._payload(
            categories=[
                {"category_key": "customer_orders", "sender_identity_id": sender_id}
            ],
            events=[
                {
                    "event_key": "order.submitted",
                    "sender_identity_id": sender_id,
                    "is_enabled": True,
                }
            ],
        )

        result = await self.service.replace_workflow_mappings(
            payload, actor_user_id=7
        )

        self.assertEqual(result["application"]["sender_identity_id"], sender_id)
        self.assertEqual(
            set(self.repository.mappings),
            {
                APPLICATION_MAPPING_KEY,
                "category:customer_orders",
                "event:order.submitted",
            },
        )
        events = {row["event_key"]: row for row in result["events"]}
        self.assertEqual(events["order.submitted"]["sender_identity_id"], sender_id)
        audits = [
            record
            for record in self.audit.records
            if record["event_type"] == "email.workflow_mapping_updated"
        ]
        self.assertEqual(len(audits), 3)
        self.assertEqual(audits[0]["metadata"]["scope"], "application")
        self.assertEqual(
            audits[0]["metadata"]["changed_fields"], ["created"]
        )
        self.assertTrue(
            all(
                record["resource_type"] == "email_workflow_mapping"
                for record in audits
            )
        )

    async def test_replace_is_idempotent(self) -> None:
        sender_id = await self._sender()
        payload = self._payload(application={"sender_identity_id": sender_id})

        await self.service.replace_workflow_mappings(payload, actor_user_id=7)
        before = len(self.audit.records)
        await self.service.replace_workflow_mappings(payload, actor_user_id=7)

        self.assertEqual(len(self.audit.records), before)
        self.assertEqual(set(self.repository.mappings), {APPLICATION_MAPPING_KEY})

    async def test_replace_removes_rows_left_out_of_the_set(self) -> None:
        sender_id = await self._sender()
        await self.service.replace_workflow_mappings(
            self._payload(
                events=[{"event_key": "order.submitted", "sender_identity_id": sender_id}]
            ),
            actor_user_id=7,
        )

        result = await self.service.replace_workflow_mappings(
            self._payload(), actor_user_id=7
        )

        self.assertEqual(set(self.repository.mappings), {APPLICATION_MAPPING_KEY})
        events = {row["event_key"]: row for row in result["events"]}
        self.assertIsNone(events["order.submitted"]["sender_identity_id"])
        removed = [
            record["metadata"]["mapping_key"]
            for record in self.audit.records
            if record["event_type"] == "email.workflow_mapping_updated"
            and record["metadata"]["changed_fields"] == ["removed"]
        ]
        self.assertEqual(removed, ["event:order.submitted"])

    async def test_disabled_event_without_sender_is_stored(self) -> None:
        payload = self._payload(
            application=None,
            events=[{"event_key": "order.submitted", "is_enabled": False}],
        )

        result = await self.service.replace_workflow_mappings(
            payload, actor_user_id=7
        )

        row = self.repository.mappings["event:order.submitted"]
        self.assertFalse(row.is_enabled)
        self.assertIsNone(row.sender_identity_id)
        events = {item["event_key"]: item for item in result["events"]}
        self.assertFalse(events["order.submitted"]["is_enabled"])

    async def test_inactive_sender_rejected(self) -> None:
        self.repository.identities = {1: make_sender(id=1, is_active=False)}

        with self.assertRaises(HTTPException) as caught:
            await self.service.replace_workflow_mappings(
                self._payload(), actor_user_id=7
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "SENDER_INACTIVE")
        self.assertEqual(self.repository.mappings, {})

    async def test_unknown_sender_rejected(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.replace_workflow_mappings(
                self._payload(application={"sender_identity_id": 99}),
                actor_user_id=7,
            )

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail["code"], "NOT_FOUND")

    async def test_unknown_keys_rejected(self) -> None:
        with self.assertRaises(HTTPException) as event_error:
            await self.service.replace_workflow_mappings(
                self._payload(events=[{"event_key": "order.pending"}]),
                actor_user_id=7,
            )
        self.assertEqual(event_error.exception.status_code, 400)
        self.assertEqual(event_error.exception.detail["code"], "VALIDATION_ERROR")

        with self.assertRaises(HTTPException) as category_error:
            await self.service.replace_workflow_mappings(
                self._payload(categories=[{"category_key": "unknown_category"}]),
                actor_user_id=7,
            )
        self.assertEqual(category_error.exception.status_code, 400)

    async def test_required_event_cannot_be_disabled(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.replace_workflow_mappings(
                self._payload(
                    application=None,
                    events=[
                        {
                            "event_key": "account.staff_password_reset",
                            "is_enabled": False,
                        }
                    ],
                ),
                actor_user_id=7,
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "WORKFLOW_NOT_DISABLEABLE")
        self.assertEqual(self.repository.mappings, {})

    async def test_mapping_rejects_identical_sender_and_reply_to(self) -> None:
        with self.assertRaises(ValidationError):
            ReplaceWorkflowMappingsRequest.model_validate(
                {
                    "application": {
                        "sender_identity_id": 3,
                        "reply_to_sender_identity_id": 3,
                    }
                }
            )

    async def test_mapping_rejects_repeated_keys(self) -> None:
        with self.assertRaises(ValidationError):
            ReplaceWorkflowMappingsRequest.model_validate(
                {
                    "events": [
                        {"event_key": "order.submitted"},
                        {"event_key": "order.submitted"},
                    ]
                }
            )


class NotificationRecipientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeRepository()
        self.audit = FakeAuditService()
        self.service = EmailSettingsService(
            self.repository,
            crypto=EmailSettingsCrypto(KEY),
            audit=self.audit,
            settings_obj=make_settings(),
        )

    def _payload(self, **overrides) -> CreateNotificationRecipientRequest:
        body = {
            "scope": "event",
            "mapping_key": "order.submitted",
            "email": "ops@dairyfarm.in",
        }
        body.update(overrides)
        return CreateNotificationRecipientRequest.model_validate(body)

    def _audit_event(self) -> dict:
        return self.audit.records[-1]

    async def test_no_recipients_exist_by_default(self) -> None:
        listed = await self.service.list_recipients()

        self.assertEqual(listed, {"items": []})
        self.assertEqual(self.audit.records, [])

    async def test_create_normalizes_stores_scoped_key_and_audits(self) -> None:
        created = await self.service.create_recipient(
            self._payload(email=" Ops@DairyFarm.IN "),
            actor_user_id=7,
        )

        recipient = created["recipient"]
        self.assertEqual(recipient["email"], "ops@dairyfarm.in")
        self.assertEqual(recipient["scope"], "event")
        self.assertEqual(recipient["mapping_key"], "order.submitted")
        self.assertEqual(recipient["label"], "Order submitted")
        self.assertTrue(recipient["is_active"])
        self.assertIn("created_at", recipient)
        self.assertIn("updated_at", recipient)

        row = self.repository.recipients[recipient["id"]]
        self.assertEqual(row.mapping_key, "event:order.submitted")
        self.assertEqual(row.scope, "event")
        self.assertEqual(row.created_by, 7)

        record = self._audit_event()
        self.assertEqual(record["event_type"], "email.notification_recipient_created")
        self.assertEqual(record["resource_type"], "email_notification_recipient")
        self.assertEqual(record["resource_id"], recipient["id"])
        self.assertEqual(
            record["metadata"],
            {
                "recipient_id": recipient["id"],
                "scope": "event",
                "mapping_key": "event:order.submitted",
            },
        )
        self.assertNotIn("ops@dairyfarm.in", repr(record["metadata"]))

    async def test_create_for_a_category_uses_the_category_label(self) -> None:
        created = await self.service.create_recipient(
            self._payload(scope="category", mapping_key="customer_orders"),
            actor_user_id=7,
        )

        self.assertEqual(created["recipient"]["label"], "Customer Orders")
        self.assertEqual(
            self.repository.recipients[created["recipient"]["id"]].mapping_key,
            "category:customer_orders",
        )

    async def test_duplicate_recipient_is_rejected(self) -> None:
        await self.service.create_recipient(self._payload(), actor_user_id=7)

        with self.assertRaises(HTTPException) as caught:
            await self.service.create_recipient(
                self._payload(email="OPS@dairyfarm.in"),
                actor_user_id=7,
            )

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "RECIPIENT_EXISTS")
        self.assertEqual(len(self.repository.recipients), 1)

    async def test_same_address_may_follow_two_workflows(self) -> None:
        await self.service.create_recipient(self._payload(), actor_user_id=7)

        await self.service.create_recipient(
            self._payload(mapping_key="order.approved"),
            actor_user_id=7,
        )

        self.assertEqual(len(self.repository.recipients), 2)

    async def test_unknown_workflow_key_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as event_error:
            await self.service.create_recipient(
                self._payload(mapping_key="order.pending"),
                actor_user_id=7,
            )

        self.assertEqual(event_error.exception.status_code, 400)
        self.assertEqual(event_error.exception.detail["code"], "VALIDATION_ERROR")

        with self.assertRaises(HTTPException) as category_error:
            await self.service.create_recipient(
                self._payload(scope="category", mapping_key="unknown_category"),
                actor_user_id=7,
            )

        self.assertEqual(category_error.exception.status_code, 400)
        self.assertEqual(self.repository.recipients, {})

    async def test_invalid_scope_and_email_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CreateNotificationRecipientRequest.model_validate(
                {"scope": "global", "mapping_key": "x", "email": "a@b.co"}
            )
        with self.assertRaises(ValidationError):
            self._payload(email="not-an-address")

    async def test_update_changes_and_normalizes_the_email(self) -> None:
        created = await self.service.create_recipient(self._payload(), actor_user_id=7)
        recipient_id = created["recipient"]["id"]

        updated = await self.service.update_recipient(
            recipient_id,
            UpdateNotificationRecipientRequest.model_validate(
                {"email": "New.Ops@DairyFarm.IN"}
            ),
            actor_user_id=9,
        )

        self.assertEqual(updated["recipient"]["email"], "new.ops@dairyfarm.in")
        self.assertEqual(self.repository.recipients[recipient_id].updated_by, 9)
        record = self._audit_event()
        self.assertEqual(record["event_type"], "email.notification_recipient_updated")
        self.assertEqual(record["metadata"]["changed_fields"], ["email"])
        self.assertNotIn("new.ops@dairyfarm.in", repr(record["metadata"]))

    async def test_update_to_a_duplicate_email_is_rejected(self) -> None:
        await self.service.create_recipient(self._payload(), actor_user_id=7)
        second = await self.service.create_recipient(
            self._payload(email="other@dairyfarm.in"),
            actor_user_id=7,
        )

        with self.assertRaises(HTTPException) as caught:
            await self.service.update_recipient(
                second["recipient"]["id"],
                UpdateNotificationRecipientRequest.model_validate(
                    {"email": "ops@dairyfarm.in"}
                ),
                actor_user_id=7,
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "RECIPIENT_EXISTS")
        self.assertEqual(
            self.repository.recipients[second["recipient"]["id"]].email,
            "other@dairyfarm.in",
        )

        # Re-saving the unchanged address is a no-op, not a conflict.
        unchanged = await self.service.update_recipient(
            second["recipient"]["id"],
            UpdateNotificationRecipientRequest.model_validate(
                {"email": "other@dairyfarm.in"}
            ),
            actor_user_id=7,
        )
        self.assertEqual(unchanged["recipient"]["email"], "other@dairyfarm.in")

    async def test_update_without_changes_writes_no_audit_row(self) -> None:
        created = await self.service.create_recipient(self._payload(), actor_user_id=7)
        self.audit.records.clear()

        await self.service.update_recipient(
            created["recipient"]["id"],
            UpdateNotificationRecipientRequest.model_validate({}),
            actor_user_id=7,
        )

        self.assertEqual(self.audit.records, [])

    async def test_deactivate_activate_and_idempotence(self) -> None:
        created = await self.service.create_recipient(self._payload(), actor_user_id=7)
        recipient_id = created["recipient"]["id"]

        deactivated = await self.service.deactivate_recipient(
            recipient_id,
            actor_user_id=7,
        )
        self.assertFalse(deactivated["recipient"]["is_active"])
        self.assertEqual(
            self._audit_event()["event_type"],
            "email.notification_recipient_deactivated",
        )

        self.audit.records.clear()
        again = await self.service.deactivate_recipient(
            recipient_id,
            actor_user_id=7,
        )
        self.assertFalse(again["recipient"]["is_active"])
        self.assertEqual(self.audit.records, [])

        activated = await self.service.activate_recipient(
            recipient_id,
            actor_user_id=7,
        )
        self.assertTrue(activated["recipient"]["is_active"])
        record = self._audit_event()
        self.assertEqual(record["event_type"], "email.notification_recipient_updated")
        self.assertEqual(record["metadata"]["changed_fields"], ["is_active"])

    async def test_patch_can_toggle_is_active(self) -> None:
        created = await self.service.create_recipient(self._payload(), actor_user_id=7)

        updated = await self.service.update_recipient(
            created["recipient"]["id"],
            UpdateNotificationRecipientRequest.model_validate({"is_active": False}),
            actor_user_id=7,
        )

        self.assertFalse(updated["recipient"]["is_active"])
        self.assertEqual(
            self._audit_event()["metadata"]["changed_fields"],
            ["is_active"],
        )

    async def test_delete_removes_the_row_and_keeps_the_audit_trail(self) -> None:
        created = await self.service.create_recipient(self._payload(), actor_user_id=7)
        recipient_id = created["recipient"]["id"]

        await self.service.delete_recipient(recipient_id, actor_user_id=7)

        self.assertEqual(self.repository.recipients, {})
        record = self._audit_event()
        self.assertEqual(record["event_type"], "email.notification_recipient_removed")
        self.assertEqual(record["metadata"], {"recipient_id": recipient_id})

        listed = await self.service.list_recipients()
        self.assertEqual(listed, {"items": []})

    async def test_missing_recipient_is_404_everywhere(self) -> None:
        calls = (
            lambda: self.service.update_recipient(
                99,
                UpdateNotificationRecipientRequest.model_validate({}),
                actor_user_id=7,
            ),
            lambda: self.service.activate_recipient(99, actor_user_id=7),
            lambda: self.service.deactivate_recipient(99, actor_user_id=7),
            lambda: self.service.delete_recipient(99, actor_user_id=7),
        )
        for call in calls:
            with self.assertRaises(HTTPException) as caught:
                await call()
            self.assertEqual(caught.exception.status_code, 404)
            self.assertEqual(caught.exception.detail["code"], "NOT_FOUND")

    async def test_activate_toggle_does_not_touch_the_customer_recipient(self) -> None:
        created = await self.service.create_recipient(self._payload(), actor_user_id=7)

        await self.service.deactivate_recipient(
            created["recipient"]["id"],
            actor_user_id=7,
        )

        # Internal recipients live in their own table; the mapping rows that
        # decide the customer's own email are untouched.
        self.assertEqual(self.repository.mappings, {})
        self.assertEqual(self.repository.identities, {})

    async def test_list_orders_by_workflow_then_address(self) -> None:
        await self.service.create_recipient(
            self._payload(mapping_key="order.submitted", email="b@dairyfarm.in"),
            actor_user_id=7,
        )
        await self.service.create_recipient(
            self._payload(mapping_key="order.submitted", email="a@dairyfarm.in"),
            actor_user_id=7,
        )
        await self.service.create_recipient(
            self._payload(mapping_key="order.approved", email="z@dairyfarm.in"),
            actor_user_id=7,
        )

        listed = await self.service.list_recipients()

        self.assertEqual(
            [(row["mapping_key"], row["email"]) for row in listed["items"]],
            [
                ("order.approved", "z@dairyfarm.in"),
                ("order.submitted", "a@dairyfarm.in"),
                ("order.submitted", "b@dairyfarm.in"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
