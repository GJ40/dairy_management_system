from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.customer_orders import (
    MAX_CANCEL_REASON_LENGTH,
    serialize_order_event,
    serialize_order_invoice,
    serialize_order_sale,
    serialize_order_summary,
)

MIN_REASON_LENGTH = 3


def _reason(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Reason is required")
    normalized = value.strip()
    if len(normalized) < MIN_REASON_LENGTH:
        raise ValueError(
            f"Reason must be at least {MIN_REASON_LENGTH} characters"
        )
    if len(normalized) > MAX_CANCEL_REASON_LENGTH:
        raise ValueError(
            f"Reason must be at most {MAX_CANCEL_REASON_LENGTH} characters"
        )
    return normalized


class ApproveOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    note: Any = None

    @field_validator("note")
    @classmethod
    def _note(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Note must be a string")
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 500:
            raise ValueError("Note must be at most 500 characters")
        return normalized


class RejectOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: Any

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: Any) -> str:
        return _reason(value)


class StaffCancelOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: Any

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: Any) -> str:
        return _reason(value)


@dataclass(slots=True)
class StaffOrderQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None
    customer_id: int | None = None
    from_date: date | None = None
    to_date: date | None = None
    search: str | None = None


def _customer_payload(customer: Any) -> dict[str, Any] | None:
    if customer is None:
        return None
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
    }


def _account_payload(account: Any) -> dict[str, Any] | None:
    if account is None:
        return None
    return {"id": account.id, "email": account.email}


def serialize_staff_order_summary(
    order: Any,
    *,
    customer: Any,
    account: Any,
) -> dict[str, Any]:
    data = serialize_order_summary(order)
    data["customer"] = _customer_payload(customer)
    data["account"] = _account_payload(account)
    data["account_email"] = account.email if account is not None else None
    return data


def serialize_staff_order_detail(
    order: Any,
    *,
    customer: Any,
    account: Any,
    events: list[Any],
    sale: Any | None,
    invoice: Any | None,
) -> dict[str, Any]:
    data = serialize_staff_order_summary(
        order,
        customer=customer,
        account=account,
    )
    data["events"] = [serialize_order_event(event) for event in events]
    data["sale"] = serialize_order_sale(sale)
    data["invoice"] = serialize_order_invoice(invoice)
    return data
