from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.time import iso_timestamp

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROLES = {"admin", "operator"}
UNSET = object()


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


def _validate_string(value: Any) -> str:
    if value is UNSET:
        return value  # type: ignore[return-value]
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    return value


def _normalize_email(value: Any) -> str:
    text = _validate_string(value)
    if text is UNSET:
        return text  # type: ignore[return-value]
    normalized = text.strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise ValueError("Invalid email address")
    return normalized


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if len(value) < 1:
            raise ValueError("Password cannot be empty")
        return value


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str
    username: str
    email: str
    password: str
    role: Any

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name cannot be empty")
        return normalized

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Username must be at least 2 characters")
        if len(normalized) > 80:
            raise ValueError("Username must be at most 80 characters")
        return normalized

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if len(value) < 6:
            raise ValueError("Password must be at least 6 characters")
        return value

    @field_validator("role")
    @classmethod
    def _role(cls, value: Any) -> str:
        if not isinstance(value, str) or value not in ROLES:
            raise ValueError('Invalid option: expected one of "admin"|"operator"')
        return value


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: Any = Field(default_factory=lambda: UNSET)
    username: Any = Field(default_factory=lambda: UNSET)
    email: Any = Field(default_factory=lambda: UNSET)
    password: Any = Field(default_factory=lambda: UNSET)
    role: Any = Field(default_factory=lambda: UNSET)

    @field_validator("full_name")
    @classmethod
    def _full_name(cls, value: Any) -> Any:
        text = _validate_string(value)
        if text is UNSET:
            return text
        normalized = text.strip()
        if not normalized:
            raise ValueError("Too small: expected string to have >=1 characters")
        return normalized

    @field_validator("username")
    @classmethod
    def _username(cls, value: Any) -> Any:
        text = _validate_string(value)
        if text is UNSET:
            return text
        normalized = text.strip()
        if len(normalized) < 2:
            raise ValueError("Too small: expected string to have >=2 characters")
        if len(normalized) > 80:
            raise ValueError("Too big: expected string to have <=80 characters")
        return normalized

    @field_validator("email")
    @classmethod
    def _email(cls, value: Any) -> Any:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: Any) -> Any:
        text = _validate_string(value)
        if text is UNSET:
            return text
        if len(text) < 6:
            raise ValueError("Password must be at least 6 characters")
        return text

    @field_validator("role")
    @classmethod
    def _role(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        if not isinstance(value, str) or value not in ROLES:
            raise ValueError('Invalid option: expected one of "admin"|"operator"')
        return value


class UpdateUserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_active: Any

    @field_validator("is_active")
    @classmethod
    def _is_active(cls, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ValueError(
                f"Invalid input: expected boolean, received {_received_type(value)}"
            )
        return value


@dataclass(slots=True)
class UserQuery:
    page: int = 1
    page_size: int = 20
    role: str | None = None
    is_active: bool | None = None
    is_locked: bool | None = None
    search: str | None = None


def serialize_user(user: Any, *, snake_timestamps: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": bool(user.is_active),
        "is_deleted": bool(user.is_deleted),
        "is_locked": user.locked_at is not None,
        "locked_at": iso_timestamp(user.locked_at),
        "lock_reason": user.lock_reason,
    }
    if snake_timestamps:
        data["created_at"] = iso_timestamp(user.created_at)
        data["updated_at"] = iso_timestamp(user.updated_at)
    else:
        data["createdAt"] = iso_timestamp(user.created_at)
        data["updatedAt"] = iso_timestamp(user.updated_at)
    return data
