from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

INVOICE_STATUSES = ("unpaid", "partial", "paid")


@dataclass(slots=True)
class PortalInvoiceQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None
    from_date: date | None = None
    to_date: date | None = None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _decimal_string(value: Any) -> str:
    return f"{Decimal(str(value or 0)):.2f}"


def _balance(invoice: Any) -> str:
    total = Decimal(str(invoice.total_amount or 0))
    paid = Decimal(str(invoice.paid_amount or 0))
    return f"{max(Decimal('0'), total - paid):.2f}"


def serialize_portal_invoice(invoice: Any) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "invoice_no": invoice.invoice_no,
        "period_start": _date_string(invoice.period_start),
        "period_end": _date_string(invoice.period_end),
        "total_amount": _decimal_string(invoice.total_amount),
        "paid_amount": _decimal_string(invoice.paid_amount),
        "status": invoice.status,
        "balance": _balance(invoice),
    }


def serialize_portal_invoice_detail(invoice: Any) -> dict[str, Any]:
    data = serialize_portal_invoice(invoice)
    customer = getattr(invoice, "customer", None)
    data["customer"] = (
        {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "address": customer.address,
        }
        if customer is not None
        else None
    )
    sales = [
        link.sale
        for link in (getattr(invoice, "sale_links", None) or [])
        if link.sale is not None
    ]
    sales.sort(key=lambda sale: (_date_string(sale.sale_date) or "", sale.id))
    data["sales"] = [
        {
            "id": sale.id,
            "sale_date": _date_string(sale.sale_date),
            "litres": _decimal_string(sale.litres),
            "rate": _decimal_string(sale.rate),
            "amount": _decimal_string(sale.amount),
            "payment_status": sale.payment_status,
        }
        for sale in sales
    ]
    return data


def serialize_portal_balance(
    total_sales: Decimal,
    total_paid: Decimal,
    outstanding: Decimal,
) -> dict[str, Any]:
    return {
        "total_sales_amount": f"{total_sales:.2f}",
        "total_paid_amount": f"{total_paid:.2f}",
        "outstanding_balance": f"{outstanding:.2f}",
    }
