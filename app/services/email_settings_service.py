from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import status

from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.models.email_notification_recipient import EmailNotificationRecipient
from app.models.email_sender_identity import EmailSenderIdentity
from app.models.email_smtp_profile import EmailSmtpProfile
from app.models.email_workflow_mapping import EmailWorkflowMapping
from app.repositories.email_settings_repository import (
    RECIPIENT_RESOURCE,
    SENDER_IDENTITY_RESOURCE,
    SMTP_PROFILE_RESOURCE,
    WORKFLOW_MAPPING_RESOURCE,
    EmailSettingsRepository,
)
from app.schemas.email_settings import (
    MAILPIT_PRESET,
    UNSET,
    CreateNotificationRecipientRequest,
    CreateSenderIdentityRequest,
    CreateSmtpProfileRequest,
    ReplaceWorkflowMappingsRequest,
    UpdateNotificationRecipientRequest,
    UpdateSenderIdentityRequest,
    UpdateSmtpProfileRequest,
    serialize_environment_settings,
    serialize_notification_recipient,
    serialize_sender_identity,
    serialize_sender_option,
    serialize_smtp_profile,
    serialize_test_result,
    validate_effective_configuration,
)
from app.services.email_settings_crypto import (
    EmailSettingsCrypto,
    EmailSettingsCryptoError,
    compute_config_fingerprint,
)
from app.services.email_workflow_catalogue import (
    APPLICATION_MAPPING_KEY,
    CATEGORIES,
    CATEGORY_SCOPE,
    EVENT_SCOPE,
    EVENTS,
    get_category,
    get_event,
    mapping_key,
    scope_label,
    serialize_workflow_catalogue,
)
from app.services.security_audit_service import SecurityAuditService
from app.services.smtp_test_client import (
    SmtpProbeError,
    SmtpProbeTarget,
    SmtpTestClient,
)
from app.utils.time import business_timezone

# Test endpoints are Admin-only and cheap to spam, so the cooldown and the
# daily cap are enforced from the security audit ledger (shared across workers).
TEST_COOLDOWN_SECONDS = 10
DAILY_TEST_LIMIT = 50
TEST_EVENT_TYPES = (
    "email.smtp_connection_tested",
    "email.smtp_connection_test_failed",
    "email.smtp_test_email_sent",
    "email.smtp_test_email_failed",
)

TEST_CONNECTION_SUCCESS_MESSAGE = "SMTP connection and authentication succeeded."
TEST_CONNECTION_SUCCESS_NO_AUTH_MESSAGE = "SMTP connection succeeded."
TEST_EMAIL_SUCCESS_MESSAGE = "Test email accepted by the SMTP server."


class EmailSettingsService:
    def __init__(
        self,
        repository: EmailSettingsRepository,
        *,
        crypto: EmailSettingsCrypto,
        audit: SecurityAuditService | None = None,
        settings_obj: Settings | None = None,
        smtp_client: SmtpTestClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.crypto = crypto
        self.audit = audit
        self.settings = settings_obj or app_settings
        self.smtp_client = smtp_client or SmtpTestClient()
        # ``clock`` must return a timezone-aware datetime; it exists so tests can
        # fix "now" without sleeping.
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def get_overview(self) -> dict[str, Any]:
        profiles = await self.repository.list_profiles()
        active = next(
            (profile for profile in profiles if profile.active_slot == 1),
            None,
        )
        if active is None:
            active = await self.repository.get_active_profile()

        if active is not None:
            source = "database"
        elif self.settings.mail_enabled:
            source = "environment"
        else:
            source = "unconfigured"

        return {
            "source": source,
            "encryption_key_configured": self.crypto.is_configured,
            "mailpit_preset": dict(MAILPIT_PRESET),
            "environment": serialize_environment_settings(self.settings),
            "active_profile": (
                serialize_smtp_profile(active) if active is not None else None
            ),
            "profiles": [serialize_smtp_profile(profile) for profile in profiles],
        }

    async def get_profile(self, profile_id: int) -> dict[str, Any]:
        return {"profile": serialize_smtp_profile(await self._get_or_404(profile_id))}

    # ------------------------------------------------------------------
    # Drafts
    # ------------------------------------------------------------------
    async def create_draft(
        self,
        payload: CreateSmtpProfileRequest,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        username_encrypted = None
        password_encrypted = None
        if payload.auth_enabled:
            try:
                self.crypto.require_configured()
                assert payload.username is not None
                assert payload.password is not None
                username_encrypted = self.crypto.encrypt(payload.username)
                password_encrypted = self.crypto.encrypt(payload.password)
            except EmailSettingsCryptoError as exc:
                raise self._crypto_error(exc) from exc

        fingerprint = compute_config_fingerprint(
            provider_mode=payload.provider_mode,
            host=payload.host,
            port=payload.port,
            auth_enabled=payload.auth_enabled,
            encryption_mode=payload.encryption_mode,
            timeout_seconds=payload.timeout_seconds,
            username_encrypted=username_encrypted,
            password_encrypted=password_encrypted,
        )

        profile = EmailSmtpProfile(
            name=payload.name,
            provider_mode=payload.provider_mode,
            host=payload.host,
            port=payload.port,
            auth_enabled=payload.auth_enabled,
            username_encrypted=username_encrypted,
            password_encrypted=password_encrypted,
            encryption_mode=payload.encryption_mode,
            timeout_seconds=payload.timeout_seconds,
            status="draft",
            active_slot=None,
            config_fingerprint=fingerprint,
            tested_fingerprint=None,
            last_test_status="never",
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        self.repository.add(profile)
        try:
            await self.repository.flush()
            await self._record(
                event_type="email.smtp_draft_created",
                actor_user_id=actor_user_id,
                context=context,
                resource_id=profile.id,
                metadata={
                    "profile_id": profile.id,
                    "provider_mode": profile.provider_mode,
                },
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(profile)
        return {"profile": serialize_smtp_profile(profile)}

    async def update_draft(
        self,
        profile_id: int,
        payload: UpdateSmtpProfileRequest,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        profile = await self._get_or_404(profile_id)
        if profile.status != "draft":
            raise api_error(
                status.HTTP_409_CONFLICT,
                "PROFILE_NOT_EDITABLE",
                "Only draft SMTP profiles can be edited",
            )

        changed_fields: list[str] = []
        name = profile.name
        provider_mode = profile.provider_mode
        host = profile.host
        port = profile.port
        auth_enabled = bool(profile.auth_enabled)
        encryption_mode = profile.encryption_mode
        timeout_seconds = profile.timeout_seconds
        username_encrypted = profile.username_encrypted
        password_encrypted = profile.password_encrypted

        if payload.name is not UNSET and payload.name != name:
            name = payload.name
            changed_fields.append("name")
        if payload.provider_mode is not UNSET and payload.provider_mode != provider_mode:
            provider_mode = payload.provider_mode
            changed_fields.append("provider_mode")
        if payload.host is not UNSET and payload.host != host:
            host = payload.host
            changed_fields.append("host")
        if payload.port is not UNSET and payload.port != port:
            port = payload.port
            changed_fields.append("port")
        if payload.encryption_mode is not UNSET and payload.encryption_mode != encryption_mode:
            encryption_mode = payload.encryption_mode
            changed_fields.append("encryption_mode")
        if (
            payload.timeout_seconds is not UNSET
            and payload.timeout_seconds != timeout_seconds
        ):
            timeout_seconds = payload.timeout_seconds
            changed_fields.append("timeout_seconds")
        if payload.auth_enabled is not UNSET and payload.auth_enabled != auth_enabled:
            auth_enabled = payload.auth_enabled
            changed_fields.append("auth_enabled")

        username_supplied = payload.username is not UNSET and payload.username is not None
        password_supplied = payload.password is not UNSET and payload.password is not None

        if not auth_enabled:
            if username_supplied or password_supplied:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "credentials are only stored when authentication is enabled",
                )
            if username_encrypted is not None or password_encrypted is not None:
                username_encrypted = None
                password_encrypted = None
                if "credentials" not in changed_fields:
                    changed_fields.append("credentials")
        else:
            try:
                if username_supplied:
                    self.crypto.require_configured()
                    username_encrypted = self.crypto.encrypt(payload.username)
                    changed_fields.append("credentials")
                if password_supplied:
                    self.crypto.require_configured()
                    password_encrypted = self.crypto.encrypt(payload.password)
                    if "credentials" not in changed_fields:
                        changed_fields.append("credentials")
            except EmailSettingsCryptoError as exc:
                raise self._crypto_error(exc) from exc

            if username_encrypted is None:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "username is required when authentication is enabled",
                )
            if password_encrypted is None:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "password is required when authentication is enabled",
                )

        try:
            validate_effective_configuration(
                provider_mode=provider_mode,
                auth_enabled=auth_enabled,
                encryption_mode=encryption_mode,
                has_username=username_encrypted is not None,
                has_password=password_encrypted is not None,
            )
        except ValueError as exc:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                str(exc),
            ) from exc

        profile.provider_mode = provider_mode
        profile.name = name
        profile.host = host
        profile.port = port
        profile.auth_enabled = auth_enabled
        profile.encryption_mode = encryption_mode
        profile.timeout_seconds = timeout_seconds
        profile.username_encrypted = username_encrypted
        profile.password_encrypted = password_encrypted

        fingerprint = compute_config_fingerprint(
            provider_mode=provider_mode,
            host=host,
            port=port,
            auth_enabled=auth_enabled,
            encryption_mode=encryption_mode,
            timeout_seconds=timeout_seconds,
            username_encrypted=username_encrypted,
            password_encrypted=password_encrypted,
        )
        if fingerprint != profile.config_fingerprint:
            profile.config_fingerprint = fingerprint
            profile.tested_fingerprint = None
        profile.updated_by = actor_user_id

        try:
            if changed_fields:
                await self._record(
                    event_type="email.smtp_draft_updated",
                    actor_user_id=actor_user_id,
                    context=context,
                    resource_id=profile.id,
                    metadata={
                        "profile_id": profile.id,
                        "changed_fields": changed_fields,
                    },
                )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(profile)
        return {"profile": serialize_smtp_profile(profile)}

    # ------------------------------------------------------------------
    # SMTP tests
    # ------------------------------------------------------------------
    async def test_connection(
        self,
        profile_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        profile = await self._get_or_404(profile_id)
        await self._enforce_test_rate_limit(
            profile_id=profile.id,
            actor_user_id=actor_user_id,
        )
        target = self._probe_target(profile)
        tested_at = self._now_local()
        try:
            await self.smtp_client.test_connection(target)
        except SmtpProbeError as exc:
            return await self._store_test_result(
                profile,
                test_kind="connection",
                reason_code=exc.reason_code,
                message=str(exc),
                tested_at=tested_at,
                actor_user_id=actor_user_id,
                context=context,
            )
        return await self._store_test_result(
            profile,
            test_kind="connection",
            reason_code=None,
            message=(
                TEST_CONNECTION_SUCCESS_MESSAGE
                if profile.auth_enabled
                else TEST_CONNECTION_SUCCESS_NO_AUTH_MESSAGE
            ),
            tested_at=tested_at,
            actor_user_id=actor_user_id,
            context=context,
        )

    async def test_email(
        self,
        profile_id: int,
        *,
        recipient_email: str,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        profile = await self._get_or_404(profile_id)
        await self._enforce_test_rate_limit(
            profile_id=profile.id,
            actor_user_id=actor_user_id,
        )
        target = self._probe_target(profile)
        mail_from = self._test_mail_from()
        tested_at = self._now_local()
        try:
            await self.smtp_client.send_test_email(
                target,
                recipient=recipient_email,
                mail_from=mail_from,
            )
        except SmtpProbeError as exc:
            return await self._store_test_result(
                profile,
                test_kind="email",
                reason_code=exc.reason_code,
                message=str(exc),
                tested_at=tested_at,
                actor_user_id=actor_user_id,
                context=context,
            )
        return await self._store_test_result(
            profile,
            test_kind="email",
            reason_code=None,
            message=TEST_EMAIL_SUCCESS_MESSAGE,
            tested_at=tested_at,
            actor_user_id=actor_user_id,
            context=context,
        )

    # ------------------------------------------------------------------
    # Activation and environment revert
    # ------------------------------------------------------------------
    async def activate(
        self,
        profile_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        profile = await self.repository.get_profile_for_update(profile_id)
        if profile is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"SMTP profile with id {profile_id} not found",
            )
        if profile.status not in ("draft", "archived"):
            raise api_error(
                status.HTTP_409_CONFLICT,
                "PROFILE_NOT_ACTIVATABLE",
                "Only a draft or archived SMTP profile can be activated",
            )
        if profile.last_test_status != "success":
            raise api_error(
                status.HTTP_409_CONFLICT,
                "SMTP_TEST_REQUIRED",
                "Test this SMTP configuration successfully before activating it",
            )
        if profile.tested_fingerprint != profile.config_fingerprint:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "SMTP_CONFIG_CHANGED_SINCE_TEST",
                "The SMTP configuration changed after its last successful test; "
                "test it again before activating it",
            )
        # Credentials must still be decryptable with the current key ring, and
        # a profile that needs them must still have them.
        self._probe_target(profile)

        previous = await self.repository.get_active_profile_for_update()
        previous_profile_id = previous.id if previous is not None else None
        if previous is not None:
            previous_source = "database"
        elif self.settings.mail_enabled:
            previous_source = "environment"
        else:
            previous_source = "unconfigured"
        activated_at = self._now_local()

        try:
            if previous is not None and previous.id != profile.id:
                previous.active_slot = None
                previous.status = "archived"
                previous.updated_by = actor_user_id
                # Release the unique active slot before claiming it.
                await self.repository.flush()

            profile.status = "active"
            profile.active_slot = 1
            profile.activated_at = activated_at
            profile.updated_by = actor_user_id

            await self._record(
                event_type="email.smtp_activated",
                actor_user_id=actor_user_id,
                context=context,
                resource_id=profile.id,
                metadata={
                    "profile_id": profile.id,
                    "previous_profile_id": previous_profile_id,
                    "previous_source": previous_source,
                },
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return await self.get_overview()

    async def use_environment(
        self,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        previous = await self.repository.get_active_profile_for_update()
        if previous is None:
            # Already environment-managed: idempotent, no audit noise.
            return await self.get_overview()

        previous_profile_id = previous.id
        try:
            previous.active_slot = None
            previous.status = "archived"
            previous.updated_by = actor_user_id
            await self.repository.flush()
            await self._record(
                event_type="email.smtp_environment_fallback_enabled",
                actor_user_id=actor_user_id,
                context=context,
                resource_id=previous_profile_id,
                metadata={"previous_profile_id": previous_profile_id},
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return await self.get_overview()

    # ------------------------------------------------------------------
    # Sender identities
    # ------------------------------------------------------------------
    async def list_senders(self) -> dict[str, Any]:
        senders = await self.repository.list_senders()
        return {"items": await self._serialize_senders(senders)}

    async def get_sender(self, sender_id: int) -> dict[str, Any]:
        sender = await self._sender_or_404(sender_id)
        senders = await self._serialize_senders([sender])
        return {"sender": senders[0]}

    async def create_sender(
        self,
        payload: CreateSenderIdentityRequest,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        await self._ensure_sender_email_available(payload.email)
        sender = EmailSenderIdentity(
            display_name=payload.display_name,
            email=payload.email,
            reply_to_email=payload.reply_to_email,
            description=payload.description,
            is_active=True,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        self.repository.add(sender)
        try:
            await self.repository.flush()
            await self._record(
                event_type="email.sender_created",
                actor_user_id=actor_user_id,
                context=context,
                resource_type=SENDER_IDENTITY_RESOURCE,
                resource_id=sender.id,
                metadata={"sender_id": sender.id, "is_active": True},
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(sender)
        return {"sender": serialize_sender_identity(sender, usage_count=0)}

    async def update_sender(
        self,
        sender_id: int,
        payload: UpdateSenderIdentityRequest,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        sender = await self._sender_or_404(sender_id)

        changed_fields: list[str] = []
        display_name = sender.display_name
        email = sender.email
        reply_to_email = sender.reply_to_email
        description = sender.description

        if payload.display_name is not UNSET and payload.display_name != display_name:
            display_name = payload.display_name
            changed_fields.append("display_name")
        if payload.email is not UNSET and payload.email != email:
            await self._ensure_sender_email_available(
                payload.email,
                exclude_id=sender.id,
            )
            email = payload.email
            changed_fields.append("email")
        if (
            payload.reply_to_email is not UNSET
            and payload.reply_to_email != reply_to_email
        ):
            reply_to_email = payload.reply_to_email
            changed_fields.append("reply_to_email")
        if payload.description is not UNSET and payload.description != description:
            description = payload.description
            changed_fields.append("description")

        # Checked again on the merged values: an email change can collide with
        # the stored Reply-To and vice versa.
        if reply_to_email is not None and reply_to_email == email:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "reply_to_email must differ from email",
            )

        sender.display_name = display_name
        sender.email = email
        sender.reply_to_email = reply_to_email
        sender.description = description
        sender.updated_by = actor_user_id

        try:
            if changed_fields:
                await self._record(
                    event_type="email.sender_updated",
                    actor_user_id=actor_user_id,
                    context=context,
                    resource_type=SENDER_IDENTITY_RESOURCE,
                    resource_id=sender.id,
                    metadata={
                        "sender_id": sender.id,
                        "changed_fields": changed_fields,
                    },
                )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(sender)
        senders = await self._serialize_senders([sender])
        return {"sender": senders[0]}

    async def activate_sender(
        self,
        sender_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        return await self._set_sender_active(
            sender_id,
            is_active=True,
            event_type="email.sender_activated",
            actor_user_id=actor_user_id,
            context=context,
        )

    async def deactivate_sender(
        self,
        sender_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        return await self._set_sender_active(
            sender_id,
            is_active=False,
            event_type="email.sender_deactivated",
            actor_user_id=actor_user_id,
            context=context,
        )

    async def delete_sender(
        self,
        sender_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> None:
        sender = await self.repository.get_sender_identity_for_update(sender_id)
        if sender is None:
            raise self._sender_not_found(sender_id)

        usage = (await self.repository.sender_usage_counts()).get(sender.id, 0)
        if usage:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "SENDER_IN_USE",
                f"This sender identity is referenced by {usage} workflow "
                "mapping(s); deactivate it or point those mappings elsewhere "
                "first",
            )

        try:
            await self._record(
                event_type="email.sender_removed",
                actor_user_id=actor_user_id,
                context=context,
                resource_type=SENDER_IDENTITY_RESOURCE,
                resource_id=sender.id,
                metadata={"sender_id": sender.id},
            )
            await self.repository.delete(sender)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

    async def _set_sender_active(
        self,
        sender_id: int,
        *,
        is_active: bool,
        event_type: str,
        actor_user_id: int,
        context: RequestContext | None,
    ) -> dict[str, Any]:
        sender = await self.repository.get_sender_identity_for_update(sender_id)
        if sender is None:
            raise self._sender_not_found(sender_id)

        if bool(sender.is_active) == is_active:
            # Already in the requested state: no mutation, no audit noise.
            senders = await self._serialize_senders([sender])
            return {"sender": senders[0]}

        sender.is_active = is_active
        sender.updated_by = actor_user_id
        try:
            await self._record(
                event_type=event_type,
                actor_user_id=actor_user_id,
                context=context,
                resource_type=SENDER_IDENTITY_RESOURCE,
                resource_id=sender.id,
                metadata={"sender_id": sender.id},
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(sender)
        senders = await self._serialize_senders([sender])
        return {"sender": senders[0]}

    # ------------------------------------------------------------------
    # Workflow catalogue and mappings
    # ------------------------------------------------------------------
    async def get_workflow_catalogue(self) -> dict[str, Any]:
        return serialize_workflow_catalogue()

    async def get_workflow_mappings(self) -> dict[str, Any]:
        senders = await self.repository.list_senders()
        mappings = await self.repository.list_mappings()
        return self._serialize_workflow_mappings(senders, mappings)

    async def replace_workflow_mappings(
        self,
        payload: ReplaceWorkflowMappingsRequest,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        """Apply the submitted set as the full replacement of stored rows."""
        desired = self._desired_mappings(payload)
        await self._validate_sender_references(desired)

        existing = {
            mapping.mapping_key: mapping
            for mapping in await self.repository.list_mappings_for_update()
        }

        changed_rows: list[tuple[EmailWorkflowMapping, list[str]]] = []
        for key, (sender_id, reply_id, is_enabled) in desired.items():
            mapping = existing.pop(key, None)
            if mapping is None:
                created = EmailWorkflowMapping(
                    scope=key.split(":", 1)[0],
                    mapping_key=key,
                    sender_identity_id=sender_id,
                    reply_to_sender_identity_id=reply_id,
                    is_enabled=is_enabled,
                    created_by=actor_user_id,
                    updated_by=actor_user_id,
                )
                self.repository.add(created)
                changed_rows.append((created, ["created"]))
                continue

            changed: list[str] = []
            if mapping.sender_identity_id != sender_id:
                mapping.sender_identity_id = sender_id
                changed.append("sender_identity_id")
            if mapping.reply_to_sender_identity_id != reply_id:
                mapping.reply_to_sender_identity_id = reply_id
                changed.append("reply_to_sender_identity_id")
            if bool(mapping.is_enabled) != is_enabled:
                mapping.is_enabled = is_enabled
                changed.append("is_enabled")
            if changed:
                mapping.updated_by = actor_user_id
                changed_rows.append((mapping, changed))

        # Whatever is left was not in the replacement set, so it stops being a
        # mapping. The notification itself is unaffected: an absent row only
        # means "no sender override" (or, for a disabled event, no row at all).
        removed_rows = list(existing.values())

        try:
            await self.repository.flush()
            for mapping, changed in changed_rows:
                await self._mapping_audit(
                    mapping,
                    changed_fields=changed,
                    actor_user_id=actor_user_id,
                    context=context,
                )
            for mapping in removed_rows:
                await self._mapping_audit(
                    mapping,
                    changed_fields=["removed"],
                    actor_user_id=actor_user_id,
                    context=context,
                )
                await self.repository.delete(mapping)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return await self.get_workflow_mappings()

    def _serialize_workflow_mappings(
        self,
        senders: list[EmailSenderIdentity],
        mappings: list[EmailWorkflowMapping],
    ) -> dict[str, Any]:
        rows = {mapping.mapping_key: mapping for mapping in mappings}
        application = rows.get(APPLICATION_MAPPING_KEY)
        return {
            "senders": [serialize_sender_option(sender) for sender in senders],
            "application": self._mapping_entry(application),
            "categories": [
                {
                    "category_key": category.key,
                    **self._mapping_entry(
                        rows.get(mapping_key(CATEGORY_SCOPE, category.key))
                    ),
                }
                for category in CATEGORIES
            ],
            "events": [
                self._event_entry(event, rows.get(mapping_key(EVENT_SCOPE, event.key)))
                for event in EVENTS
            ],
        }

    def _event_entry(
        self,
        event: Any,
        mapping: EmailWorkflowMapping | None,
    ) -> dict[str, Any]:
        entry = {"event_key": event.key, **self._mapping_entry(mapping)}
        entry["is_enabled"] = True if mapping is None else bool(mapping.is_enabled)
        return entry

    @staticmethod
    def _mapping_entry(mapping: EmailWorkflowMapping | None) -> dict[str, Any]:
        return {
            "sender_identity_id": getattr(mapping, "sender_identity_id", None),
            "reply_to_sender_identity_id": getattr(
                mapping, "reply_to_sender_identity_id", None
            ),
        }

    def _desired_mappings(
        self,
        payload: ReplaceWorkflowMappingsRequest,
    ) -> dict[str, tuple[int | None, int | None, bool]]:
        desired: dict[str, tuple[int | None, int | None, bool]] = {}

        if payload.application is not None and (
            payload.application.sender_identity_id is not None
            or payload.application.reply_to_sender_identity_id is not None
        ):
            desired[APPLICATION_MAPPING_KEY] = (
                payload.application.sender_identity_id,
                payload.application.reply_to_sender_identity_id,
                True,
            )

        for row in payload.categories:
            if get_category(row.category_key) is None:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    f"Unknown workflow category: {row.category_key}",
                )
            if (
                row.sender_identity_id is None
                and row.reply_to_sender_identity_id is None
            ):
                continue
            desired[mapping_key(CATEGORY_SCOPE, row.category_key)] = (
                row.sender_identity_id,
                row.reply_to_sender_identity_id,
                True,
            )

        for row in payload.events:
            event = get_event(row.event_key)
            if event is None:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    f"Unknown workflow event: {row.event_key}",
                )
            if row.is_enabled is False and not event.allow_disable:
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "WORKFLOW_NOT_DISABLEABLE",
                    f"{event.name} cannot be disabled: it is required for "
                    "account security or onboarding",
                )
            if (
                row.sender_identity_id is None
                and row.reply_to_sender_identity_id is None
                and row.is_enabled
            ):
                continue
            desired[mapping_key(EVENT_SCOPE, row.event_key)] = (
                row.sender_identity_id,
                row.reply_to_sender_identity_id,
                bool(row.is_enabled),
            )

        return desired

    async def _validate_sender_references(
        self,
        desired: dict[str, tuple[int | None, int | None, bool]],
    ) -> None:
        checked: set[int] = set()
        for sender_id, reply_id, _is_enabled in desired.values():
            for value in (sender_id, reply_id):
                if value is None or value in checked:
                    continue
                sender = await self.repository.get_sender_identity(value)
                if sender is None:
                    raise self._sender_not_found(value)
                if not sender.is_active:
                    raise api_error(
                        status.HTTP_409_CONFLICT,
                        "SENDER_INACTIVE",
                        f"Sender identity '{sender.display_name}' is inactive; "
                        "activate it before mapping it to a workflow",
                    )
                checked.add(value)

    async def _mapping_audit(
        self,
        mapping: EmailWorkflowMapping,
        *,
        changed_fields: list[str],
        actor_user_id: int,
        context: RequestContext | None,
    ) -> None:
        await self._record(
            event_type="email.workflow_mapping_updated",
            actor_user_id=actor_user_id,
            context=context,
            resource_type=WORKFLOW_MAPPING_RESOURCE,
            resource_id=mapping.id,
            metadata={
                "scope": mapping.scope,
                "mapping_key": mapping.mapping_key,
                "changed_fields": changed_fields,
            },
        )

    # ------------------------------------------------------------------
    # Internal notification recipients
    # ------------------------------------------------------------------
    async def list_recipients(self) -> dict[str, Any]:
        recipients = await self.repository.list_recipients()
        return {"items": [self._recipient_payload(row) for row in recipients]}

    async def create_recipient(
        self,
        payload: CreateNotificationRecipientRequest,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        scoped_key = self._recipient_mapping_key(payload.scope, payload.mapping_key)
        await self._ensure_recipient_available(scoped_key, payload.email)
        recipient = EmailNotificationRecipient(
            scope=payload.scope,
            mapping_key=scoped_key,
            email=payload.email,
            is_active=True,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        self.repository.add(recipient)
        try:
            await self.repository.flush()
            await self._record(
                event_type="email.notification_recipient_created",
                actor_user_id=actor_user_id,
                context=context,
                resource_type=RECIPIENT_RESOURCE,
                resource_id=recipient.id,
                metadata={
                    "recipient_id": recipient.id,
                    "scope": recipient.scope,
                    "mapping_key": recipient.mapping_key,
                },
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(recipient)
        return {"recipient": self._recipient_payload(recipient)}

    async def update_recipient(
        self,
        recipient_id: int,
        payload: UpdateNotificationRecipientRequest,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        recipient = await self._recipient_or_404(recipient_id, for_update=True)

        changed_fields: list[str] = []
        email = recipient.email
        is_active = bool(recipient.is_active)

        if payload.email is not UNSET and payload.email != email:
            await self._ensure_recipient_available(
                recipient.mapping_key,
                payload.email,
                exclude_id=recipient.id,
            )
            email = payload.email
            changed_fields.append("email")
        if payload.is_active is not UNSET and payload.is_active != is_active:
            is_active = payload.is_active
            changed_fields.append("is_active")

        recipient.email = email
        recipient.is_active = is_active
        recipient.updated_by = actor_user_id

        try:
            if changed_fields:
                await self._record(
                    event_type="email.notification_recipient_updated",
                    actor_user_id=actor_user_id,
                    context=context,
                    resource_type=RECIPIENT_RESOURCE,
                    resource_id=recipient.id,
                    metadata={
                        "recipient_id": recipient.id,
                        "changed_fields": changed_fields,
                    },
                )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(recipient)
        return {"recipient": self._recipient_payload(recipient)}

    async def activate_recipient(
        self,
        recipient_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        return await self._set_recipient_active(
            recipient_id,
            is_active=True,
            actor_user_id=actor_user_id,
            context=context,
        )

    async def deactivate_recipient(
        self,
        recipient_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        return await self._set_recipient_active(
            recipient_id,
            is_active=False,
            actor_user_id=actor_user_id,
            context=context,
        )

    async def _set_recipient_active(
        self,
        recipient_id: int,
        *,
        is_active: bool,
        actor_user_id: int,
        context: RequestContext | None,
    ) -> dict[str, Any]:
        recipient = await self._recipient_or_404(recipient_id, for_update=True)

        if bool(recipient.is_active) == is_active:
            # Already in the requested state: no mutation, no audit noise.
            return {"recipient": self._recipient_payload(recipient)}

        recipient.is_active = is_active
        recipient.updated_by = actor_user_id
        if is_active:
            event_type = "email.notification_recipient_updated"
            metadata: dict[str, object] = {
                "recipient_id": recipient.id,
                "changed_fields": ["is_active"],
            }
        else:
            event_type = "email.notification_recipient_deactivated"
            metadata = {"recipient_id": recipient.id}

        try:
            await self._record(
                event_type=event_type,
                actor_user_id=actor_user_id,
                context=context,
                resource_type=RECIPIENT_RESOURCE,
                resource_id=recipient.id,
                metadata=metadata,
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(recipient)
        return {"recipient": self._recipient_payload(recipient)}

    async def delete_recipient(
        self,
        recipient_id: int,
        *,
        actor_user_id: int,
        context: RequestContext | None = None,
    ) -> None:
        recipient = await self._recipient_or_404(recipient_id, for_update=True)
        try:
            await self._record(
                event_type="email.notification_recipient_removed",
                actor_user_id=actor_user_id,
                context=context,
                resource_type=RECIPIENT_RESOURCE,
                resource_id=recipient.id,
                metadata={"recipient_id": recipient.id},
            )
            await self.repository.delete(recipient)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _recipient_or_404(
        self,
        recipient_id: int,
        *,
        for_update: bool = False,
    ) -> EmailNotificationRecipient:
        if for_update:
            recipient = await self.repository.get_recipient_for_update(recipient_id)
        else:
            recipient = await self.repository.get_recipient(recipient_id)
        if recipient is None:
            raise self._recipient_not_found(recipient_id)
        return recipient

    @staticmethod
    def _recipient_not_found(recipient_id: int):
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Notification recipient with id {recipient_id} not found",
        )

    @staticmethod
    def _recipient_mapping_key(scope: str, key: str) -> str:
        """Validate a scope/key pair and return its stored (scoped) key."""
        if scope_label(scope, key) is None:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                f"Unknown workflow {scope}: {key}",
            )
        return mapping_key(scope, key)

    def _recipient_payload(
        self,
        recipient: EmailNotificationRecipient,
    ) -> dict[str, Any]:
        key = recipient.mapping_key
        if ":" in key:
            key = key.split(":", 1)[1]
        return serialize_notification_recipient(
            recipient,
            label=scope_label(recipient.scope, key),
        )

    async def _ensure_recipient_available(
        self,
        scoped_key: str,
        email: str,
        *,
        exclude_id: int | None = None,
    ) -> None:
        existing = await self.repository.get_recipient_by_key_email(
            scoped_key,
            email,
        )
        if existing is not None and existing.id != exclude_id:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "RECIPIENT_EXISTS",
                "This address already receives notifications for that "
                "workflow",
            )

    async def _serialize_senders(
        self,
        senders: list[EmailSenderIdentity],
    ) -> list[dict[str, Any]]:
        if not senders:
            return []
        counts = await self.repository.sender_usage_counts()
        return [
            serialize_sender_identity(sender, usage_count=counts.get(sender.id, 0))
            for sender in senders
        ]

    async def _sender_or_404(self, sender_id: int) -> EmailSenderIdentity:
        sender = await self.repository.get_sender_identity(sender_id)
        if sender is None:
            raise self._sender_not_found(sender_id)
        return sender

    @staticmethod
    def _sender_not_found(sender_id: int):
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Sender identity with id {sender_id} not found",
        )

    async def _ensure_sender_email_available(
        self,
        email: str,
        *,
        exclude_id: int | None = None,
    ) -> None:
        existing = await self.repository.get_sender_identity_by_email(email)
        if existing is not None and existing.id != exclude_id:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "SENDER_EMAIL_EXISTS",
                "Another sender identity already uses this email address",
            )

    def _probe_target(self, profile: EmailSmtpProfile) -> SmtpProbeTarget:
        username = None
        password = None
        if profile.auth_enabled:
            try:
                self.crypto.require_configured()
                if profile.username_encrypted:
                    username = self.crypto.decrypt(profile.username_encrypted)
                if profile.password_encrypted:
                    password = self.crypto.decrypt(profile.password_encrypted)
            except EmailSettingsCryptoError as exc:
                raise self._crypto_error(exc) from exc
            if not username or not password:
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "SMTP_CREDENTIALS_UNAVAILABLE",
                    "This SMTP profile needs stored credentials before it can be "
                    "tested or activated",
                )
        return SmtpProbeTarget(
            host=profile.host,
            port=profile.port,
            auth_enabled=bool(profile.auth_enabled),
            encryption_mode=profile.encryption_mode,
            timeout_seconds=profile.timeout_seconds,
            username=username,
            password=password,
        )

    def _test_mail_from(self) -> tuple[str, str]:
        email = (self.settings.mail_from_email or "").strip()
        if not email:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "EMAIL_SENDER_NOT_CONFIGURED",
                "MAIL_FROM_EMAIL is not configured, so no From address is "
                "available for the test message",
            )
        return (self.settings.mail_from_name, email)

    async def _enforce_test_rate_limit(
        self,
        *,
        profile_id: int,
        actor_user_id: int,
    ) -> None:
        now_utc = self._now_utc()
        cutoff = now_utc - timedelta(seconds=TEST_COOLDOWN_SECONDS)
        latest = await self.repository.latest_test_action_at(
            actor_user_id=actor_user_id,
            profile_id=profile_id,
            event_types=TEST_EVENT_TYPES,
            cutoff=cutoff,
        )
        if latest is not None:
            remaining = TEST_COOLDOWN_SECONDS - (now_utc - latest).total_seconds()
            retry_after = max(1, math.ceil(remaining))
            raise api_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "RATE_LIMITED",
                "Wait a moment before testing this SMTP profile again",
                headers={"Retry-After": str(retry_after)},
                extra={"retry_after_seconds": retry_after},
            )

        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        used = await self.repository.count_test_actions(
            actor_user_id=actor_user_id,
            since=day_start,
            event_types=TEST_EVENT_TYPES,
        )
        if used >= DAILY_TEST_LIMIT:
            retry_after = max(
                1,
                math.ceil(
                    (day_start + timedelta(days=1) - now_utc).total_seconds()
                ),
            )
            raise api_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "RATE_LIMITED",
                f"Daily SMTP test limit of {DAILY_TEST_LIMIT} actions reached",
                headers={"Retry-After": str(retry_after)},
                extra={"retry_after_seconds": retry_after},
            )

    async def _store_test_result(
        self,
        profile: EmailSmtpProfile,
        *,
        test_kind: str,
        reason_code: str | None,
        message: str,
        tested_at: datetime,
        actor_user_id: int,
        context: RequestContext | None,
    ) -> dict[str, Any]:
        succeeded = reason_code is None
        profile.last_test_status = "success" if succeeded else "failure"
        profile.last_test_kind = test_kind
        profile.last_test_reason = reason_code
        profile.last_tested_at = tested_at
        # A failed test never counts as verification; a later activation must
        # re-test the same configuration.
        profile.tested_fingerprint = (
            profile.config_fingerprint if succeeded else None
        )
        profile.updated_by = actor_user_id

        if succeeded:
            event_type = (
                "email.smtp_connection_tested"
                if test_kind == "connection"
                else "email.smtp_test_email_sent"
            )
            metadata: dict[str, object] = {
                "profile_id": profile.id,
                "test_status": "success",
            }
        else:
            event_type = (
                "email.smtp_connection_test_failed"
                if test_kind == "connection"
                else "email.smtp_test_email_failed"
            )
            metadata = {
                "profile_id": profile.id,
                "reason_code": reason_code,
            }

        try:
            await self._record(
                event_type=event_type,
                actor_user_id=actor_user_id,
                context=context,
                resource_id=profile.id,
                metadata=metadata,
                reason_code=reason_code,
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        await self.repository.refresh(profile)
        return serialize_test_result(
            test_kind=test_kind,
            test_status=profile.last_test_status,
            tested_at=profile.last_tested_at,
            reason_code=profile.last_test_reason,
            message=message,
        )

    def _now_utc(self) -> datetime:
        """Naive UTC, matching the security audit ledger timestamps."""
        return self._clock().astimezone(timezone.utc).replace(tzinfo=None)

    def _now_local(self) -> datetime:
        """Naive business time, matching the profile timestamp columns."""
        return self._clock().astimezone(business_timezone()).replace(tzinfo=None)

    async def _get_or_404(self, profile_id: int) -> EmailSmtpProfile:
        profile = await self.repository.get_profile(profile_id)
        if profile is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"SMTP profile with id {profile_id} not found",
            )
        return profile

    async def _record(
        self,
        *,
        event_type: str,
        actor_user_id: int,
        context: RequestContext | None,
        resource_id: int,
        metadata: dict[str, object],
        resource_type: str = SMTP_PROFILE_RESOURCE,
        reason_code: str | None = None,
    ) -> None:
        if self.audit is None:
            return
        await self.audit.record(
            event_type=event_type,
            context=context,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason_code=reason_code,
            metadata=metadata,
        )

    @staticmethod
    def _crypto_error(exc: EmailSettingsCryptoError):
        return api_error(status.HTTP_409_CONFLICT, exc.code, str(exc))
