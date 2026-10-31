from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi import status as http_status

from app.core.dependencies import (
    get_current_customer_account,
    get_customer_dashboard_service,
    get_customer_invoice_service,
    get_customer_order_service,
    get_customer_query_service,
)
from app.core.errors import api_error
from app.models.customer_portal_account import CustomerPortalAccount
from app.schemas.customer_invoices import PortalInvoiceQuery
from app.schemas.customer_orders import (
    CancelCustomerOrderRequest,
    CreateCustomerOrderRequest,
    CustomerOrderQuery,
)
from app.schemas.customer_queries import (
    AddCustomerQueryMessageRequest,
    CreateCustomerQueryRequest,
    CustomerQueryListQuery,
)
from app.services.customer_dashboard_service import CustomerDashboardService
from app.services.customer_invoice_service import CustomerInvoiceService
from app.services.customer_order_service import CustomerOrderService
from app.services.customer_query_service import CustomerQueryService

router = APIRouter(prefix="/customer-portal", tags=["customer-portal"])


def _query_date(value: str | None, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise api_error(
            http_status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            f"{field_name}: Invalid date, expected YYYY-MM-DD",
        ) from exc


@router.get("/dashboard")
async def get_dashboard(
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerDashboardService = Depends(get_customer_dashboard_service),
) -> dict[str, Any]:
    return await service.get_dashboard(account)


@router.get("/profile")
async def get_profile(
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerDashboardService = Depends(get_customer_dashboard_service),
) -> dict[str, Any]:
    return await service.get_profile(account)


@router.post("/orders", status_code=http_status.HTTP_201_CREATED)
async def create_order(
    payload: CreateCustomerOrderRequest,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.create(
        account,
        quantity_litres=payload.quantity_litres,
        requested_date=payload.requested_date,
        note=payload.note,
    )


@router.get("/orders")
async def list_orders(
    status: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.list_orders(
        account,
        CustomerOrderQuery(
            page=page,
            page_size=page_size,
            status=status or None,
            from_date=_query_date(from_, "from"),
            to_date=_query_date(to, "to"),
        ),
    )


@router.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.get_order(account, order_id)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    payload: CancelCustomerOrderRequest | None = None,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.cancel(
        account,
        order_id,
        payload.reason if payload is not None else None,
    )


@router.get("/invoices")
async def list_invoices(
    status: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerInvoiceService = Depends(get_customer_invoice_service),
) -> dict[str, Any]:
    return await service.list_invoices(
        account,
        PortalInvoiceQuery(
            page=page,
            page_size=page_size,
            status=status or None,
            from_date=_query_date(from_, "from"),
            to_date=_query_date(to, "to"),
        ),
    )


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerInvoiceService = Depends(get_customer_invoice_service),
) -> dict[str, Any]:
    return await service.get_invoice(account, invoice_id)


@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: int,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerInvoiceService = Depends(get_customer_invoice_service),
) -> Response:
    content, filename = await service.generate_invoice_pdf(account, invoice_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/balance")
async def get_balance(
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerInvoiceService = Depends(get_customer_invoice_service),
) -> dict[str, Any]:
    return await service.get_balance(account)


@router.post("/queries", status_code=http_status.HTTP_201_CREATED)
async def create_query(
    payload: CreateCustomerQueryRequest,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.create(
        account,
        category=payload.category,
        subject=payload.subject,
        message=payload.message,
    )


@router.get("/queries")
async def list_queries(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.list_queries(
        account,
        CustomerQueryListQuery(
            page=page,
            page_size=page_size,
            status=status_filter or None,
        ),
    )


@router.get("/queries/{query_id}")
async def get_query(
    query_id: int,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.get_query(account, query_id)


@router.post(
    "/queries/{query_id}/messages",
    status_code=http_status.HTTP_201_CREATED,
)
async def add_query_message(
    query_id: int,
    payload: AddCustomerQueryMessageRequest,
    account: CustomerPortalAccount = Depends(get_current_customer_account),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.add_customer_message(account, query_id, payload.message)
