from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.time import iso_timestamp

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72
MAX_ACTIVATION_TOKEN_LENGTH = 200


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.match(normalized):
        raise ValueError("Invalid email address")
    if len(normalized) > 150:
        raise ValueError("Email must be at most 150 characters")
    return normalized


def decimal_string(value: Decimal | int | float | None) -> str | None:
    if value is None:
        return None
    return f"{Decimal(value):.2f}"


class ActivatePortalAccountRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str
    password: str

    @field_validator("token")
    @classmethod
    def _token(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Activation token is required")
        if len(normalized) > MAX_ACTIVATION_TOKEN_LENGTH:
            raise ValueError(
                f"Activation token must be at most {MAX_ACTIVATION_TOKEN_LENGTH} characters"
            )
        return normalized

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Password must be a string")
        return value


class CustomerLoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("Password cannot be empty")
        return value


class CreatePortalAccountRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_id: int
    email: str

    @field_validator("customer_id", mode="before")
    @classmethod
    def _customer_id(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Invalid input: expected int, received non-integer")
        if value < 1:
            raise ValueError("Invalid input: expected a positive customer id")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class DeactivatePortalAccountRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Reason must be at least 3 characters")
        if len(normalized) > 500:
            raise ValueError("Reason must be at most 500 characters")
        return normalized


@dataclass(slots=True)
class PortalAccountQuery:
    page: int = 1
    page_size: int = 20
    customer_id: int | None = None
    is_active: bool | None = None


def serialize_customer_public(customer: Any) -> dict[str, Any]:
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address,
        "rate_per_litre": decimal_string(customer.rate_per_litre),
        "is_active": bool(customer.is_active),
    }


def serialize_portal_account(
    account: Any,
    customer: Any | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": account.id,
        "email": account.email,
        "customer_id": account.customer_id,
        "is_active": bool(account.is_active),
        "activated_at": iso_timestamp(account.activated_at),
        "last_login_at": iso_timestamp(account.last_login_at),
        "created_at": iso_timestamp(account.created_at),
        "updated_at": iso_timestamp(account.updated_at),
    }
    if customer is not None:
        data["customer"] = serialize_customer_public(customer)
    return data


def serialize_account_event(event: Any) -> dict[str, Any]:
    return {
        "id": event.id,
        "action": event.action,
        "actor_user_id": event.actor_user_id,
        "note": event.note,
        "created_at": iso_timestamp(event.created_at),
    }


def serialize_activation(token: str, expires_at: datetime) -> dict[str, Any]:
    return {"token": token, "expires_at": iso_timestamp(expires_at)}
