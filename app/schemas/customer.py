from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.production import _coerce_number
from app.utils.time import iso_timestamp

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


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    return value.strip()


def _optional_string(value: Any) -> Any:
    if value is UNSET:
        return value
    if value is None:
        return None
    return _string(value)


def _boolean(value: Any) -> Any:
    if value is UNSET:
        return value
    if not isinstance(value, bool):
        raise ValueError(
            f"Invalid input: expected boolean, received {_received_type(value)}"
        )
    return value


class CreateCustomerRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Any
    phone: Any = Field(default_factory=lambda: UNSET)
    address: Any = Field(default_factory=lambda: UNSET)
    rate_per_litre: Any
    is_active: Any = True

    @field_validator("name")
    @classmethod
    def _name(cls, value: Any) -> str:
        name = _string(value)
        if not name:
            raise ValueError("Name cannot be empty")
        if len(name) > 150:
            raise ValueError("Name cannot exceed 150 characters")
        return name

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: Any) -> Any:
        phone = _optional_string(value)
        if isinstance(phone, str) and len(phone) > 30:
            raise ValueError("Too big: expected string to have <=30 characters")
        return phone

    @field_validator("address")
    @classmethod
    def _address(cls, value: Any) -> Any:
        return _optional_string(value)

    @field_validator("rate_per_litre")
    @classmethod
    def _rate_per_litre(cls, value: Any) -> float:
        rate = _coerce_number(value)
        if rate <= 0:
            raise ValueError("Rate per litre must be greater than zero")
        return rate

    @field_validator("is_active")
    @classmethod
    def _is_active(cls, value: Any) -> bool:
        checked = _boolean(value)
        return True if checked is UNSET else checked


class UpdateCustomerRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Any = Field(default_factory=lambda: UNSET)
    phone: Any = Field(default_factory=lambda: UNSET)
    address: Any = Field(default_factory=lambda: UNSET)
    rate_per_litre: Any = Field(default_factory=lambda: UNSET)
    is_active: Any = Field(default_factory=lambda: UNSET)

    @field_validator("name")
    @classmethod
    def _name(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        name = _string(value)
        if len(name) < 1:
            raise ValueError("Too small: expected string to have >=1 characters")
        if len(name) > 150:
            raise ValueError("Too big: expected string to have <=150 characters")
        return name

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: Any) -> Any:
        phone = _optional_string(value)
        if isinstance(phone, str) and len(phone) > 30:
            raise ValueError("Too big: expected string to have <=30 characters")
        return phone

    @field_validator("address")
    @classmethod
    def _address(cls, value: Any) -> Any:
        return _optional_string(value)

    @field_validator("rate_per_litre")
    @classmethod
    def _rate_per_litre(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        rate = _coerce_number(value)
        if rate <= 0:
            raise ValueError("Too small: expected number to be >0")
        return rate

    @field_validator("is_active")
    @classmethod
    def _is_active(cls, value: Any) -> Any:
        return _boolean(value)


@dataclass(slots=True)
class CustomerQuery:
    page: int = 1
    page_size: int = 20
    search: str | None = None
    is_active: bool | None = None


def _decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return f"{float(value):.2f}"


def serialize_customer(customer: Any) -> dict[str, Any]:
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address,
        "rate_per_litre": _decimal_string(customer.rate_per_litre),
        "is_active": bool(customer.is_active),
        "is_deleted": bool(customer.is_deleted),
        "createdAt": iso_timestamp(customer.created_at),
        "updatedAt": iso_timestamp(customer.updated_at),
    }
