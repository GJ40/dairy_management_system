from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.user import EMAIL_PATTERN
from app.utils.time import iso_timestamp

UNSET = object()

PROVIDER_MODES = {"mailpit", "custom"}
ENCRYPTION_MODES = {"none", "starttls", "ssl"}

MAILPIT_PRESET = {
    "host": "127.0.0.1",
    "port": 1025,
    "auth_enabled": False,
    "encryption_mode": "none",
}

MAX_PASSWORD_LENGTH = 1024
MAX_USERNAME_LENGTH = 320
MAX_EMAIL_LENGTH = 150
MAX_DISPLAY_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 255


def _received_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _text(value: Any, field: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    text = value.strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_length:
        raise ValueError(
            f"Too big: expected string to have <={max_length} characters"
        )
    return text


def _optional_secret(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    if not value.strip():
        raise ValueError(f"{field} cannot be empty")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"Too big: expected string to have <={MAX_PASSWORD_LENGTH} characters"
        )
    return value


def _email_address(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise ValueError(f"{field_name}: Invalid email address")
    if len(normalized) > MAX_EMAIL_LENGTH:
        raise ValueError(
            f"Too big: expected string to have <={MAX_EMAIL_LENGTH} characters"
        )
    return normalized


def _optional_text(value: Any, field_name: str, *, max_length: int) -> str | None:
    """Optional free text: ``None``/blank become ``None``, never an empty string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(
            f"Too big: expected string to have <={max_length} characters"
        )
    return text


def _port(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        else:
            raise ValueError(
                f"Invalid input: expected number, received {_received_type(value)}"
            )
    if value < 1 or value > 65535:
        raise ValueError("port must be between 1 and 65535")
    return value


def _timeout(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        else:
            raise ValueError(
                f"Invalid input: expected number, received {_received_type(value)}"
            )
    if value < 1 or value > 120:
        raise ValueError("timeout_seconds must be between 1 and 120")
    return value


def _mode(value: Any, *, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    text = value.strip().lower()
    if text not in allowed:
        options = "|".join(sorted(allowed))
        raise ValueError(f"{field}: Invalid option: expected one of {options}")
    return text


def _host(value: Any) -> str:
    text = _text(value, "host", max_length=255)
    if "://" in text or "/" in text or any(character.isspace() for character in text):
        raise ValueError("host must be a hostname or IP address, not a URL")
    return text


def _boolean(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"Invalid input: expected boolean, received {_received_type(value)}"
        )
    return value


def validate_effective_configuration(
    *,
    provider_mode: str,
    auth_enabled: bool,
    encryption_mode: str,
    has_username: bool,
    has_password: bool,
) -> None:
    """Validate a merged create/update SMTP configuration.

    Raises ``ValueError`` with a user-facing, secret-free message.
    """
    if provider_mode not in PROVIDER_MODES:
        raise ValueError(
            "provider_mode: Invalid option: expected one of custom|mailpit"
        )
    if encryption_mode not in ENCRYPTION_MODES:
        raise ValueError(
            "encryption_mode: Invalid option: expected one of none|ssl|starttls"
        )

    if provider_mode == "mailpit":
        if auth_enabled:
            raise ValueError("Mailpit profiles cannot use SMTP authentication")
        if encryption_mode != "none":
            raise ValueError("Mailpit profiles must use encryption_mode none")
        if has_username or has_password:
            raise ValueError(
                "Mailpit profiles cannot store credentials; leave them empty"
            )
        return

    if auth_enabled:
        if not has_username:
            raise ValueError("username is required when authentication is enabled")
        if not has_password:
            raise ValueError("password is required when authentication is enabled")
    elif has_username or has_password:
        raise ValueError(
            "credentials are only stored when authentication is enabled"
        )


class CreateSmtpProfileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Any
    provider_mode: Any = "custom"
    host: Any
    port: Any
    auth_enabled: Any = False
    username: Any = None
    password: Any = None
    encryption_mode: Any = "none"
    timeout_seconds: Any = 10

    @field_validator("name")
    @classmethod
    def _name(cls, value: Any) -> str:
        return _text(value, "name", max_length=100)

    @field_validator("provider_mode")
    @classmethod
    def _provider_mode(cls, value: Any) -> str:
        return _mode(value, field="provider_mode", allowed=PROVIDER_MODES)

    @field_validator("host")
    @classmethod
    def _host(cls, value: Any) -> str:
        return _host(value)

    @field_validator("port")
    @classmethod
    def _port_field(cls, value: Any) -> int:
        return _port(value)

    @field_validator("auth_enabled")
    @classmethod
    def _auth_enabled(cls, value: Any) -> bool:
        return _boolean(value, field="auth_enabled")

    @field_validator("username")
    @classmethod
    def _username(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = _optional_secret(value, "username")
        if len(text) > MAX_USERNAME_LENGTH:
            raise ValueError(
                "Too big: expected string to have "
                f"<={MAX_USERNAME_LENGTH} characters"
            )
        return text

    @field_validator("password")
    @classmethod
    def _password(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _optional_secret(value, "password")

    @field_validator("encryption_mode")
    @classmethod
    def _encryption_mode(cls, value: Any) -> str:
        return _mode(value, field="encryption_mode", allowed=ENCRYPTION_MODES)

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout_field(cls, value: Any) -> int:
        return _timeout(value)

    @model_validator(mode="after")
    def _combination(self) -> "CreateSmtpProfileRequest":
        validate_effective_configuration(
            provider_mode=self.provider_mode,
            auth_enabled=self.auth_enabled,
            encryption_mode=self.encryption_mode,
            has_username=self.username is not None,
            has_password=self.password is not None,
        )
        return self


class UpdateSmtpProfileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Any = Field(default_factory=lambda: UNSET)
    provider_mode: Any = Field(default_factory=lambda: UNSET)
    host: Any = Field(default_factory=lambda: UNSET)
    port: Any = Field(default_factory=lambda: UNSET)
    auth_enabled: Any = Field(default_factory=lambda: UNSET)
    username: Any = Field(default_factory=lambda: UNSET)
    password: Any = Field(default_factory=lambda: UNSET)
    encryption_mode: Any = Field(default_factory=lambda: UNSET)
    timeout_seconds: Any = Field(default_factory=lambda: UNSET)

    @field_validator("name")
    @classmethod
    def _name(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _text(value, "name", max_length=100)

    @field_validator("provider_mode")
    @classmethod
    def _provider_mode(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _mode(value, field="provider_mode", allowed=PROVIDER_MODES)

    @field_validator("host")
    @classmethod
    def _host(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _host(value)

    @field_validator("port")
    @classmethod
    def _port_field(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _port(value)

    @field_validator("auth_enabled")
    @classmethod
    def _auth_enabled(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _boolean(value, field="auth_enabled")

    @field_validator("username")
    @classmethod
    def _username(cls, value: Any) -> Any:
        if value is UNSET or value is None:
            return value
        text = _optional_secret(value, "username")
        if len(text) > MAX_USERNAME_LENGTH:
            raise ValueError(
                "Too big: expected string to have "
                f"<={MAX_USERNAME_LENGTH} characters"
            )
        return text

    @field_validator("password")
    @classmethod
    def _password(cls, value: Any) -> Any:
        if value is UNSET or value is None:
            return value
        return _optional_secret(value, "password")

    @field_validator("encryption_mode")
    @classmethod
    def _encryption_mode(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _mode(value, field="encryption_mode", allowed=ENCRYPTION_MODES)

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout_field(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _timeout(value)


class SmtpTestEmailRequest(BaseModel):
    """Explicit test-email recipient; it is never defaulted to the sender."""

    model_config = ConfigDict(extra="ignore")

    recipient_email: Any

    @field_validator("recipient_email")
    @classmethod
    def _recipient(cls, value: Any) -> str:
        return _email_address(value, "recipient_email")


class CreateSenderIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    display_name: Any
    email: Any
    reply_to_email: Any = None
    description: Any = None

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: Any) -> str:
        return _text(value, "display_name", max_length=MAX_DISPLAY_NAME_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, value: Any) -> str:
        return _email_address(value, "email")

    @field_validator("reply_to_email")
    @classmethod
    def _reply_to_email(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _email_address(value, "reply_to_email")

    @field_validator("description")
    @classmethod
    def _description(cls, value: Any) -> str | None:
        return _optional_text(
            value, "description", max_length=MAX_DESCRIPTION_LENGTH
        )

    @model_validator(mode="after")
    def _reply_to_differs(self) -> "CreateSenderIdentityRequest":
        if self.reply_to_email is not None and self.reply_to_email == self.email:
            raise ValueError("reply_to_email must differ from email")
        return self


class UpdateSenderIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    display_name: Any = Field(default_factory=lambda: UNSET)
    email: Any = Field(default_factory=lambda: UNSET)
    reply_to_email: Any = Field(default_factory=lambda: UNSET)
    description: Any = Field(default_factory=lambda: UNSET)

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _text(value, "display_name", max_length=MAX_DISPLAY_NAME_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _email_address(value, "email")

    @field_validator("reply_to_email")
    @classmethod
    def _reply_to_email(cls, value: Any) -> Any:
        if value is UNSET or value is None:
            return value
        return _email_address(value, "reply_to_email")

    @field_validator("description")
    @classmethod
    def _description(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _optional_text(
            value, "description", max_length=MAX_DESCRIPTION_LENGTH
        )


MAX_MAPPING_KEY_LENGTH = 100


def _sender_reference(value: Any, field_name: str) -> int | None:
    """A nullable sender identity id; ``None`` means "no override"."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        else:
            raise ValueError(
                f"Invalid input: expected number, received {_received_type(value)}"
            )
    if value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


class SenderReferencePayload(BaseModel):
    """Sender/Reply-To references for one mapping row."""

    model_config = ConfigDict(extra="ignore")

    sender_identity_id: Any = None
    reply_to_sender_identity_id: Any = None

    @field_validator("sender_identity_id")
    @classmethod
    def _sender_identity_id(cls, value: Any) -> int | None:
        return _sender_reference(value, "sender_identity_id")

    @field_validator("reply_to_sender_identity_id")
    @classmethod
    def _reply_to_sender_identity_id(cls, value: Any) -> int | None:
        return _sender_reference(value, "reply_to_sender_identity_id")

    @model_validator(mode="after")
    def _reply_to_differs(self) -> "SenderReferencePayload":
        if (
            self.sender_identity_id is not None
            and self.sender_identity_id == self.reply_to_sender_identity_id
        ):
            raise ValueError(
                "reply_to_sender_identity_id must differ from sender_identity_id"
            )
        return self


class ApplicationMappingPayload(SenderReferencePayload):
    """The application-wide default sender."""


class CategoryMappingPayload(SenderReferencePayload):
    category_key: Any = ""

    @field_validator("category_key")
    @classmethod
    def _category_key(cls, value: Any) -> str:
        return _text(value, "category_key", max_length=MAX_MAPPING_KEY_LENGTH)


class EventMappingPayload(SenderReferencePayload):
    event_key: Any = ""
    is_enabled: Any = True

    @field_validator("event_key")
    @classmethod
    def _event_key(cls, value: Any) -> str:
        return _text(value, "event_key", max_length=MAX_MAPPING_KEY_LENGTH)

    @field_validator("is_enabled")
    @classmethod
    def _is_enabled(cls, value: Any) -> bool:
        return _boolean(value, field="is_enabled")


RECIPIENT_SCOPES = {"category", "event"}


class CreateNotificationRecipientRequest(BaseModel):
    """Add one internal recipient to a category or event scope."""

    model_config = ConfigDict(extra="ignore")

    scope: Any
    mapping_key: Any
    email: Any

    @field_validator("scope")
    @classmethod
    def _scope(cls, value: Any) -> str:
        return _mode(value, field="scope", allowed=RECIPIENT_SCOPES)

    @field_validator("mapping_key")
    @classmethod
    def _mapping_key(cls, value: Any) -> str:
        return _text(value, "mapping_key", max_length=MAX_MAPPING_KEY_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, value: Any) -> str:
        return _email_address(value, "email")


class UpdateNotificationRecipientRequest(BaseModel):
    """Edit an existing recipient; the scope and mapping key are immutable."""

    model_config = ConfigDict(extra="ignore")

    email: Any = Field(default_factory=lambda: UNSET)
    is_active: Any = Field(default_factory=lambda: UNSET)

    @field_validator("email")
    @classmethod
    def _email(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _email_address(value, "email")

    @field_validator("is_active")
    @classmethod
    def _is_active(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _boolean(value, field="is_active")


class ReplaceWorkflowMappingsRequest(BaseModel):
    """Full replacement set for ``PUT /workflow-mappings``."""

    model_config = ConfigDict(extra="ignore")

    application: ApplicationMappingPayload | None = None
    categories: list[CategoryMappingPayload] = Field(default_factory=list)
    events: list[EventMappingPayload] = Field(default_factory=list)

    @field_validator("categories", "events", mode="before")
    @classmethod
    def _allow_null_list(cls, value: Any) -> Any:
        if value is None:
            return []
        return value

    @model_validator(mode="after")
    def _unique_keys(self) -> "ReplaceWorkflowMappingsRequest":
        category_keys = [row.category_key for row in self.categories]
        if len(set(category_keys)) != len(category_keys):
            raise ValueError("categories must not repeat a category_key")
        event_keys = [row.event_key for row in self.events]
        if len(set(event_keys)) != len(event_keys):
            raise ValueError("events must not repeat an event_key")
        return self


def serialize_sender_option(sender: Any) -> dict[str, Any]:
    """Compact sender reference shown in the mapping screens."""
    return {
        "id": sender.id,
        "display_name": sender.display_name,
        "email": sender.email,
        "is_active": bool(sender.is_active),
    }


def serialize_sender_identity(
    sender: Any,
    *,
    usage_count: int = 0,
) -> dict[str, Any]:
    """Serialize a sender identity; ``usage_count`` counts mapping references."""
    return {
        "id": sender.id,
        "display_name": sender.display_name,
        "email": sender.email,
        "reply_to_email": sender.reply_to_email,
        "description": sender.description,
        "is_active": bool(sender.is_active),
        "usage_count": usage_count,
        "created_at": iso_timestamp(sender.created_at),
        "updated_at": iso_timestamp(sender.updated_at),
    }


def serialize_notification_recipient(
    recipient: Any,
    *,
    label: str | None = None,
) -> dict[str, Any]:
    """Serialize an internal recipient, exposing the unscoped workflow key."""
    key = recipient.mapping_key
    if ":" in key:
        key = key.split(":", 1)[1]
    return {
        "id": recipient.id,
        "scope": recipient.scope,
        "mapping_key": key,
        "label": label or key,
        "email": recipient.email,
        "is_active": bool(recipient.is_active),
        "created_at": iso_timestamp(recipient.created_at),
        "updated_at": iso_timestamp(recipient.updated_at),
    }


def serialize_test_result(
    *,
    test_kind: str,
    test_status: str,
    tested_at: Any,
    reason_code: str | None,
    message: str,
) -> dict[str, Any]:
    """Serialise one SMTP test outcome without any credential material."""
    return {
        "test_kind": test_kind,
        "test_status": test_status,
        "tested_at": iso_timestamp(tested_at),
        "reason_code": reason_code,
        "message": message,
    }


def serialize_smtp_profile(profile: Any) -> dict[str, Any]:
    """Serialize a profile without ever exposing stored credentials."""
    return {
        "id": profile.id,
        "name": profile.name,
        "provider_mode": profile.provider_mode,
        "host": profile.host,
        "port": profile.port,
        "auth_enabled": bool(profile.auth_enabled),
        "username_configured": bool(profile.username_encrypted),
        "password_configured": bool(profile.password_encrypted),
        "encryption_mode": profile.encryption_mode,
        "timeout_seconds": profile.timeout_seconds,
        "status": profile.status,
        "config_fingerprint": profile.config_fingerprint,
        "tested_fingerprint": profile.tested_fingerprint,
        "last_test_status": profile.last_test_status,
        "last_test_kind": profile.last_test_kind,
        "last_test_reason": profile.last_test_reason,
        "last_tested_at": iso_timestamp(profile.last_tested_at),
        "activated_at": iso_timestamp(profile.activated_at),
        "created_at": iso_timestamp(profile.created_at),
        "updated_at": iso_timestamp(profile.updated_at),
    }


def serialize_environment_settings(settings_obj: Any) -> dict[str, Any]:
    """Describe the environment transport without credentials."""
    if settings_obj.smtp_use_ssl:
        encryption_mode = "ssl"
    elif settings_obj.smtp_use_tls:
        encryption_mode = "starttls"
    else:
        encryption_mode = "none"
    return {
        "configured": bool(settings_obj.mail_enabled),
        "host": (settings_obj.smtp_host or "").strip(),
        "port": settings_obj.smtp_port,
        "auth_enabled": bool((settings_obj.smtp_user or "").strip()),
        "encryption_mode": encryption_mode,
        "timeout_seconds": settings_obj.smtp_timeout_seconds,
        "from_name": settings_obj.mail_from_name,
        "from_email": settings_obj.mail_from_email,
    }
