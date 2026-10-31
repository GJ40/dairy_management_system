from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas.customer_invoices import serialize_portal_invoice
from app.schemas.customer_orders import serialize_order_summary
from app.schemas.customer_portal_auth import (
    serialize_customer_public,
    serialize_portal_account,
)


def serialize_dashboard_customer(customer: Any) -> dict[str, Any]:
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address,
        "rate_per_litre": f"{Decimal(str(customer.rate_per_litre or 0)):.2f}",
    }


def serialize_dashboard(
    *,
    customer: Any,
    total_sales: Decimal,
    total_paid: Decimal,
    outstanding: Decimal,
    orders: list[Any],
    invoices: list[Any],
    open_queries: int,
) -> dict[str, Any]:
    return {
        "customer": serialize_dashboard_customer(customer),
        "balance": {
            "total_sales_amount": f"{total_sales:.2f}",
            "total_paid_amount": f"{total_paid:.2f}",
            "outstanding_balance": f"{outstanding:.2f}",
        },
        "recent_orders": [serialize_order_summary(row) for row in orders],
        "recent_invoices": [serialize_portal_invoice(row) for row in invoices],
        "open_queries": open_queries,
    }


def serialize_profile(account: Any, customer: Any) -> dict[str, Any]:
    return {
        "account": serialize_portal_account(account, customer),
        "customer": serialize_customer_public(customer),
    }
