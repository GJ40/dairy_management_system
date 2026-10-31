from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.customer_portal_auth import (
    MAX_ACTIVATION_TOKEN_LENGTH,
    normalize_email,
)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str
    password: str

    @field_validator("token")
    @classmethod
    def _token(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Password reset token is required")
        if len(normalized) > MAX_ACTIVATION_TOKEN_LENGTH:
            raise ValueError(
                f"Password reset token must be at most "
                f"{MAX_ACTIVATION_TOKEN_LENGTH} characters"
            )
        return normalized

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("Password cannot be empty")
        return value
