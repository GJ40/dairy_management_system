"""Authenticated encryption for database-stored SMTP credentials.

Only ``cryptography``'s Fernet (AES-128-CBC + HMAC-SHA256) is used. Keys are
supplied outside the database via ``EMAIL_SETTINGS_ENCRYPTION_KEY`` and an
optional ``EMAIL_SETTINGS_ENCRYPTION_KEY_PREVIOUS`` for rotation.

The module never logs or returns plaintext. Error messages are stable, safe
codes that callers can map to API errors.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

ENCRYPTION_KEY_UNAVAILABLE = "ENCRYPTION_KEY_UNAVAILABLE"
DECRYPTION_FAILED = "DECRYPTION_FAILED"


class EmailSettingsCryptoError(Exception):
    """Base class for safe credential-encryption failures."""

    code = "ENCRYPTION_ERROR"
    message = "Email settings encryption failed"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class EncryptionKeyUnavailable(EmailSettingsCryptoError):
    code = ENCRYPTION_KEY_UNAVAILABLE
    message = (
        "Email settings encryption key is not configured or is invalid; "
        "stored SMTP credentials cannot be used"
    )


class CredentialDecryptionFailed(EmailSettingsCryptoError):
    code = DECRYPTION_FAILED
    message = (
        "Stored SMTP credentials could not be decrypted with the configured "
        "encryption key"
    )


def _load_key(raw: str | None) -> Fernet | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return Fernet(text.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError):
        # A malformed key is treated exactly like a missing key so read
        # endpoints still answer and writes fail with a safe code. Never echo
        # the supplied value.
        return None


def crypto_from_settings(settings_obj: Any) -> EmailSettingsCrypto:
    """Build the key ring from application settings.

    Shared by the background notification dispatchers, which cannot depend on
    the request-scoped FastAPI dependency.
    """
    primary = settings_obj.email_settings_encryption_key
    previous = settings_obj.email_settings_encryption_key_previous
    return EmailSettingsCrypto(
        primary.get_secret_value() if primary is not None else None,
        previous.get_secret_value() if previous is not None else None,
    )


class EmailSettingsCrypto:
    """Encrypt/decrypt SMTP credentials with a primary key and optional previous key."""

    def __init__(
        self,
        primary_key: str | None,
        previous_key: str | None = None,
    ) -> None:
        self._primary = _load_key(primary_key)
        self._previous = _load_key(previous_key)
        keys = [key for key in (self._primary, self._previous) if key is not None]
        # MultiFernet encrypts with the first key and decrypts with any key,
        # which is exactly the rotation contract.
        self._fernet = MultiFernet(keys) if keys else None

    @property
    def is_configured(self) -> bool:
        return self._fernet is not None

    def require_configured(self) -> None:
        if self._fernet is None:
            raise EncryptionKeyUnavailable()

    def encrypt(self, plaintext: str) -> str:
        self.require_configured()
        assert self._fernet is not None
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        self.require_configured()
        assert self._fernet is not None
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError, UnicodeEncodeError) as exc:
            raise CredentialDecryptionFailed() from exc


def compute_config_fingerprint(
    *,
    provider_mode: str,
    host: str,
    port: int,
    auth_enabled: bool,
    encryption_mode: str,
    timeout_seconds: int,
    username_encrypted: str | None,
    password_encrypted: str | None,
) -> str:
    """SHA-256 over the effective transport configuration.

    Credentials participate through their stored ciphertext, so changing a
    password always invalidates an earlier successful test without hashing the
    plaintext password into a brute-forceable value.
    """
    payload: dict[str, Any] = {
        "provider_mode": provider_mode,
        "host": host,
        "port": port,
        "auth_enabled": bool(auth_enabled),
        "encryption_mode": encryption_mode,
        "timeout_seconds": timeout_seconds,
        "username_encrypted": username_encrypted,
        "password_encrypted": password_encrypted,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
