from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.production import _coerce_number
from app.utils.time import iso_timestamp

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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


def _date_text(value: Any, message: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    if not DATE_PATTERN.match(value):
        raise ValueError(message)
    return value


def _positive_int(value: Any, message: str) -> int:
    number = _coerce_number(value)
    if not number.is_integer():
        raise ValueError("Invalid input: expected int, received number")
    result = int(number)
    if result <= 0:
        raise ValueError(message)
    return result


def _positive_number(value: Any, message: str) -> float:
    number = _coerce_number(value)
    if number <= 0:
        raise ValueError(message)
    return number


class CreateSaleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_id: Any
    sale_date: Any
    litres: Any
    rate: Any = Field(default_factory=lambda: UNSET)

    @field_validator("customer_id")
    @classmethod
    def _customer_id(cls, value: Any) -> int:
        return _positive_int(value, "Valid customer ID is required")

    @field_validator("sale_date")
    @classmethod
    def _sale_date(cls, value: Any) -> str:
        return _date_text(value, "Sale date must be in YYYY-MM-DD format")

    @field_validator("litres")
    @classmethod
    def _litres(cls, value: Any) -> float:
        return _positive_number(value, "Litres sold must be greater than zero")

    @field_validator("rate")
    @classmethod
    def _rate(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _positive_number(value, "Rate must be greater than zero")


class UpdateSaleRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    litres: Any = Field(default_factory=lambda: UNSET)
    rate: Any = Field(default_factory=lambda: UNSET)
    sale_date: Any = Field(default_factory=lambda: UNSET)

    @field_validator("litres")
    @classmethod
    def _litres(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _positive_number(value, "Litres must be greater than zero")

    @field_validator("rate")
    @classmethod
    def _rate(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _positive_number(value, "Rate must be greater than zero")

    @field_validator("sale_date")
    @classmethod
    def _sale_date(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _date_text(
            value,
            "Invalid string: must match pattern /^\\d{4}-\\d{2}-\\d{2}$/",
        )


@dataclass(slots=True)
class SaleQuery:
    page: int = 1
    page_size: int = 20
    customer_id: int | None = None
    sale_date: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    payment_status: str | None = None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _decimal_string(value: Any) -> str:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return f"{float(value):.2f}"


def serialize_sale(sale: Any) -> dict[str, Any]:
    return {
        "id": sale.id,
        "customer_id": sale.customer_id,
        "sale_date": _date_string(sale.sale_date),
        "litres": _decimal_string(sale.litres),
        "rate": _decimal_string(sale.rate),
        "amount": _decimal_string(sale.amount),
        "payment_status": sale.payment_status,
        "recorded_by": sale.recorded_by,
        "is_deleted": bool(sale.is_deleted),
        "createdAt": iso_timestamp(sale.created_at),
        "updatedAt": iso_timestamp(sale.updated_at),
    }


def serialize_sale_customer(customer: Any, *, include_address: bool) -> dict[str, Any]:
    data = {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "rate_per_litre": _decimal_string(customer.rate_per_litre),
        "is_active": bool(customer.is_active),
    }
    if include_address:
        data["address"] = customer.address
    return data


def serialize_sale_recorder(recorder: Any) -> dict[str, Any] | None:
    if recorder is None:
        return None
    return {
        "id": recorder.id,
        "full_name": recorder.full_name,
        "username": recorder.username,
    }


def serialize_sale_detail(sale: Any, *, include_address: bool) -> dict[str, Any]:
    data = serialize_sale(sale)
    data["customer"] = (
        serialize_sale_customer(sale.customer, include_address=include_address)
        if sale.customer is not None
        else None
    )
    data["recorder"] = serialize_sale_recorder(sale.recorder)
    return data
