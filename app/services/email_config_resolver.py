"""Resolve the effective transport, sender and Reply-To for one message.

This module is built and tested from Phase 3; the existing email call sites are
wired to it when those workflows get their own phase (order emails are Phase 7).
Resolution is per send, so every worker sees configuration changes without a
cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import Settings
from app.core.config import settings as app_settings
from app.repositories.email_settings_repository import EmailSettingsRepository
from app.services.email_settings_crypto import (
    EmailSettingsCrypto,
    EmailSettingsCryptoError,
)
from app.services.email_workflow_catalogue import (
    APPLICATION_MAPPING_KEY,
    CATEGORY_SCOPE,
    EVENT_SCOPE,
)
from app.services.email_workflow_catalogue import (
    mapping_key as scoped_mapping_key,
)

EMAIL_NOT_CONFIGURED = "EMAIL_NOT_CONFIGURED"
EMAIL_SENDER_NOT_CONFIGURED = "EMAIL_SENDER_NOT_CONFIGURED"


class EmailConfigurationError(Exception):
    """A safe, code-carrying configuration failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class EmailTransportConfig:
    host: str
    port: int
    auth_enabled: bool
    encryption_mode: str
    timeout_seconds: int
    # Never render credentials if the dataclass is logged or printed.
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class EmailMessageConfig:
    source: str
    transport: EmailTransportConfig
    from_name: str
    from_email: str
    reply_to_email: str | None
    diagnostics: tuple[str, ...] = ()


class EmailConfigResolver:
    def __init__(
        self,
        repository: EmailSettingsRepository,
        *,
        crypto: EmailSettingsCrypto,
        settings_obj: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.crypto = crypto
        self.settings = settings_obj or app_settings

    async def resolve(
        self,
        event_key: str | None = None,
        *,
        category_key: str | None = None,
    ) -> EmailMessageConfig:
        diagnostics: list[str] = []
        transport = await self._resolve_transport(diagnostics)

        # Mapping rows are stored under a scope-prefixed key, so the resolver
        # must look up exactly what the mapping API writes.
        sender, event_reply = await self._resolve_level(
            scoped_mapping_key(EVENT_SCOPE, event_key) if event_key else None,
            diagnostics,
            "event",
        )
        # Reply-To precedence is per level, so the category row is resolved even
        # when the event row already supplied a sender.
        category_sender, category_reply = await self._resolve_level(
            scoped_mapping_key(CATEGORY_SCOPE, category_key) if category_key else None,
            diagnostics,
            "category",
        )
        application_sender = None
        if sender is None and category_sender is None:
            application_sender, _ = await self._resolve_level(
                APPLICATION_MAPPING_KEY, diagnostics, "application"
            )

        selected_sender = sender or category_sender or application_sender
        if selected_sender is not None:
            from_name = selected_sender.display_name
            from_email = selected_sender.email
        else:
            from_name = self.settings.mail_from_name
            from_email = self.settings.mail_from_email

        if not (from_email or "").strip():
            raise EmailConfigurationError(
                EMAIL_SENDER_NOT_CONFIGURED,
                "No sender identity is configured and MAIL_FROM_EMAIL is empty",
            )

        reply_to = event_reply or category_reply
        if reply_to is None and selected_sender is not None:
            reply_to = selected_sender.reply_to_email

        return EmailMessageConfig(
            source=transport[0],
            transport=transport[1],
            from_name=from_name,
            from_email=from_email.strip().lower(),
            reply_to_email=reply_to,
            diagnostics=tuple(diagnostics),
        )

    async def _resolve_transport(
        self, diagnostics: list[str]
    ) -> tuple[str, EmailTransportConfig]:
        active = await self.repository.get_active_profile()
        if active is not None:
            username = None
            password = None
            if active.auth_enabled:
                try:
                    self.crypto.require_configured()
                    if active.username_encrypted:
                        username = self.crypto.decrypt(active.username_encrypted)
                    if active.password_encrypted:
                        password = self.crypto.decrypt(active.password_encrypted)
                except EmailSettingsCryptoError as exc:
                    # No silent environment fallback while a database profile
                    # is active.
                    raise EmailConfigurationError(exc.code, str(exc)) from exc
            return (
                "database",
                EmailTransportConfig(
                    host=active.host,
                    port=active.port,
                    auth_enabled=bool(active.auth_enabled),
                    encryption_mode=active.encryption_mode,
                    timeout_seconds=active.timeout_seconds,
                    username=username,
                    password=password,
                ),
            )

        if not self.settings.mail_enabled:
            raise EmailConfigurationError(
                EMAIL_NOT_CONFIGURED,
                "No active SMTP profile and the environment transport is not configured",
            )

        if self.settings.smtp_use_ssl:
            encryption_mode = "ssl"
        elif self.settings.smtp_use_tls:
            encryption_mode = "starttls"
        else:
            encryption_mode = "none"

        username = (self.settings.smtp_user or "").strip() or None
        password = self.settings.smtp_password.get_secret_value() or None
        if username and password is None:
            diagnostics.append("ENVIRONMENT_CREDENTIALS_INCOMPLETE")

        return (
            "environment",
            EmailTransportConfig(
                host=self.settings.smtp_host.strip(),
                port=self.settings.smtp_port,
                auth_enabled=bool(username),
                encryption_mode=encryption_mode,
                timeout_seconds=self.settings.smtp_timeout_seconds,
                username=username,
                password=password,
            ),
        )

    async def _resolve_level(
        self,
        mapping_key: str | None,
        diagnostics: list[str],
        level: str,
    ) -> tuple[object | None, str | None]:
        if not mapping_key:
            return None, None
        mapping = await self.repository.get_mapping(mapping_key)
        if mapping is None:
            return None, None

        sender = None
        if mapping.sender_identity_id is not None:
            identity = await self.repository.get_sender_identity(
                mapping.sender_identity_id
            )
            if identity is not None and identity.is_active:
                sender = identity
            else:
                diagnostics.append(f"{level.upper()}_SENDER_INACTIVE")

        reply_to = None
        if mapping.reply_to_sender_identity_id is not None:
            identity = await self.repository.get_sender_identity(
                mapping.reply_to_sender_identity_id
            )
            if identity is not None and identity.is_active:
                reply_to = identity.reply_to_email or identity.email
            else:
                diagnostics.append(f"{level.upper()}_REPLY_TO_INACTIVE")

        return sender, reply_to
