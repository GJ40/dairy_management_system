from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.time import iso_timestamp

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
ORDER_STATUSES = (
    "submitted",
    "approved",
    "rejected",
    "cancelled",
    "fulfilled",
)
MAX_NOTE_LENGTH = 1000
MAX_CANCEL_REASON_LENGTH = 500


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


def parse_order_quantity(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(
            "Invalid input: expected number, received "
            f"{_received_type(value)}"
        )
    if isinstance(value, (int, float)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise ValueError(
            "Invalid input: expected number, received "
            f"{_received_type(value)}"
        )
    if not NUMBER_PATTERN.match(text):
        raise ValueError("Invalid input: expected number, received NaN")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Invalid input: expected number, received NaN") from exc
    if not number.is_finite():
        raise ValueError("Invalid input: expected number, received NaN")
    if number.as_tuple().exponent < -2:
        raise ValueError("Quantity must have at most 2 decimal places")
    return number.quantize(Decimal("0.01"))


def parse_order_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError(
            "Invalid input: expected string, received "
            f"{_received_type(value)}"
        )
    text = value.strip()
    if not DATE_PATTERN.match(text):
        raise ValueError("Requested date must be in YYYY-MM-DD format")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Requested date must be a valid calendar date") from exc


class CreateCustomerOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quantity_litres: Any
    requested_date: Any
    note: Any = None

    @field_validator("quantity_litres")
    @classmethod
    def _quantity(cls, value: Any) -> Decimal:
        return parse_order_quantity(value)

    @field_validator("requested_date")
    @classmethod
    def _requested_date(cls, value: Any) -> date:
        return parse_order_date(value)

    @field_validator("note")
    @classmethod
    def _note(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(
                "Invalid input: expected string, received "
                f"{_received_type(value)}"
            )
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > MAX_NOTE_LENGTH:
            raise ValueError(
                f"Note must be at most {MAX_NOTE_LENGTH} characters"
            )
        return normalized


class CancelCustomerOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: Any = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(
                "Invalid input: expected string, received "
                f"{_received_type(value)}"
            )
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > MAX_CANCEL_REASON_LENGTH:
            raise ValueError(
                f"Reason must be at most {MAX_CANCEL_REASON_LENGTH} characters"
            )
        return normalized


@dataclass(slots=True)
class CustomerOrderQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None
    from_date: date | None = None
    to_date: date | None = None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    return f"{Decimal(value):.2f}"


def serialize_order_summary(order: Any) -> dict[str, Any]:
    return {
        "id": order.id,
        "order_no": order.order_no,
        "status": order.status,
        "requested_date": _date_string(order.requested_date),
        "quantity_litres": _decimal_string(order.quantity_litres),
        "rate_snapshot": _decimal_string(order.rate_snapshot),
        "estimated_total": _decimal_string(order.estimated_total),
        "note": order.note,
        "reviewed_at": iso_timestamp(order.reviewed_at),
        "reason": order.reason,
        "created_at": iso_timestamp(order.created_at),
        "updated_at": iso_timestamp(order.updated_at),
    }


def serialize_order_event(event: Any) -> dict[str, Any]:
    return {
        "from_status": event.from_status,
        "to_status": event.to_status,
        "actor_type": event.actor_type,
        "reason": event.reason,
        "created_at": iso_timestamp(event.created_at),
    }


def serialize_order_sale(sale: Any | None) -> dict[str, Any] | None:
    if sale is None:
        return None
    return {
        "id": sale.id,
        "sale_date": _date_string(sale.sale_date),
        "litres": _decimal_string(sale.litres),
        "rate": _decimal_string(sale.rate),
        "amount": _decimal_string(sale.amount),
        "payment_status": sale.payment_status,
    }


def serialize_order_invoice(invoice: Any | None) -> dict[str, Any] | None:
    if invoice is None:
        return None
    total = Decimal(invoice.total_amount or 0)
    paid = Decimal(invoice.paid_amount or 0)
    return {
        "id": invoice.id,
        "invoice_no": invoice.invoice_no,
        "status": invoice.status,
        "total_amount": _decimal_string(total),
        "paid_amount": _decimal_string(paid),
        "balance": _decimal_string(total - paid),
    }


def serialize_order_detail(
    order: Any,
    *,
    events: list[Any],
    sale: Any | None,
    invoice: Any | None,
) -> dict[str, Any]:
    data = serialize_order_summary(order)
    data["events"] = [serialize_order_event(event) for event in events]
    data["sale"] = serialize_order_sale(sale)
    data["invoice"] = serialize_order_invoice(invoice)
    return data
