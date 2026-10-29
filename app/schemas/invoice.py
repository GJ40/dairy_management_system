from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

from app.schemas.production import _coerce_number
from app.utils.time import iso_timestamp

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _positive_customer_id(value: Any) -> int:
    number = _coerce_number(value)
    if not number.is_integer():
        raise ValueError("Invalid input: expected int, received number")
    customer_id = int(number)
    if customer_id <= 0:
        raise ValueError("customer_id must be a positive integer")
    return customer_id


def _positive_sale_id(value: Any) -> int:
    number = _coerce_number(value)
    if not number.is_integer():
        raise ValueError("Invalid input: expected int, received number")
    sale_id = int(number)
    if sale_id <= 0:
        raise ValueError("Too small: expected number to be >0")
    return sale_id


def _date_text(value: Any, message: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    if not DATE_PATTERN.match(value):
        raise ValueError(message)
    return value


SaleId = Annotated[int, BeforeValidator(_positive_sale_id)]


class CreateInvoiceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_id: Any
    period_start: Any
    period_end: Any
    sale_ids: list[SaleId] = Field(default_factory=list)

    @field_validator("customer_id")
    @classmethod
    def _customer_id(cls, value: Any) -> int:
        return _positive_customer_id(value)

    @field_validator("period_start")
    @classmethod
    def _period_start(cls, value: Any) -> str:
        return _date_text(value, "period_start must be in YYYY-MM-DD format")

    @field_validator("period_end")
    @classmethod
    def _period_end(cls, value: Any, info: ValidationInfo) -> str:
        period_end = _date_text(
            value,
            "period_end must be in YYYY-MM-DD format",
        )
        period_start = info.data.get("period_start")
        if isinstance(period_start, str) and period_start > period_end:
            raise ValueError("'period_start' cannot be after 'period_end'")
        return period_end


class RecordPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    amount: Any

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: Any) -> float:
        amount = _coerce_number(value)
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")
        if amount > 999999999.99:
            raise ValueError("Amount exceeds maximum allowable threshold")
        return amount


@dataclass(slots=True)
class InvoiceQuery:
    page: int = 1
    page_size: int = 20
    customer_id: int | None = None
    status: str | None = None
    from_date: str | None = None
    to_date: str | None = None


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


def serialize_invoice_customer(
    customer: Any,
    *,
    include_address: bool,
    include_rate: bool,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
    }
    if include_address:
        data["address"] = customer.address
    if include_rate:
        data["rate_per_litre"] = _decimal_string(customer.rate_per_litre)
    data["is_active"] = bool(customer.is_active)
    return data


def serialize_invoice_sale(sale: Any) -> dict[str, Any]:
    return {
        "id": sale.id,
        "sale_date": _date_string(sale.sale_date),
        "litres": _decimal_string(sale.litres),
        "rate": _decimal_string(sale.rate),
        "amount": _decimal_string(sale.amount),
        "payment_status": sale.payment_status,
    }


def _balance(invoice: Any) -> str:
    total = Decimal(str(invoice.total_amount or 0))
    paid = Decimal(str(invoice.paid_amount or 0))
    return f"{max(Decimal('0'), total - paid):.2f}"


def serialize_invoice(
    invoice: Any,
    *,
    detail: bool,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": invoice.id,
        "invoice_no": invoice.invoice_no,
        "customer_id": invoice.customer_id,
        "period_start": _date_string(invoice.period_start),
        "period_end": _date_string(invoice.period_end),
        "total_amount": _decimal_string(invoice.total_amount),
        "paid_amount": _decimal_string(invoice.paid_amount),
        "status": invoice.status,
        "is_deleted": bool(invoice.is_deleted),
        "createdAt": iso_timestamp(invoice.created_at),
        "updatedAt": iso_timestamp(invoice.updated_at),
        "customer": (
            serialize_invoice_customer(
                invoice.customer,
                include_address=detail,
                include_rate=detail,
            )
            if invoice.customer is not None
            else None
        ),
    }
    if detail:
        sales = [
            link.sale
            for link in (invoice.sale_links or [])
            if link.sale is not None
        ]
        sales.sort(key=lambda sale: _date_string(sale.sale_date) or "")
        data["sales"] = [serialize_invoice_sale(sale) for sale in sales]
    data["balance"] = _balance(invoice)
    return data
