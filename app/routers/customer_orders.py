from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Query,
    Request,
    status,
)

from app.core.dependencies import (
    get_customer_order_service,
    require_roles,
)
from app.core.errors import api_error
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.customer_orders_staff import (
    ApproveOrderRequest,
    RejectOrderRequest,
    StaffCancelOrderRequest,
    StaffOrderQuery,
)
from app.services.customer_order_service import CustomerOrderService

router = APIRouter(
    prefix="/customer-orders",
    tags=["customer-orders"],
    dependencies=[Depends(require_roles("admin", "operator"))],
)


def _query_date(value: str | None, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            f"{field_name}: Invalid date, expected YYYY-MM-DD",
        ) from exc


@router.get("")
async def list_customer_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    customer_id: int | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.staff_list_orders(
        StaffOrderQuery(
            page=page,
            page_size=page_size,
            status=status_filter or None,
            customer_id=customer_id,
            from_date=_query_date(from_, "from"),
            to_date=_query_date(to, "to"),
            search=search or None,
        )
    )


@router.get("/{order_id}")
async def get_customer_order(
    order_id: int,
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.staff_get_order(order_id)


@router.post("/{order_id}/approve")
async def approve_customer_order(
    order_id: int,
    request: Request,
    background: BackgroundTasks,
    payload: ApproveOrderRequest | None = Body(default=None),
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.approve(
        user,
        order_id,
        payload.note if payload is not None else None,
        context=get_request_context(request),
        background=background,
    )


@router.post("/{order_id}/reject")
async def reject_customer_order(
    order_id: int,
    request: Request,
    payload: RejectOrderRequest,
    background: BackgroundTasks,
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.reject(
        user,
        order_id,
        payload.reason,
        context=get_request_context(request),
        background=background,
    )


@router.post("/{order_id}/fulfil")
async def fulfil_customer_order(
    order_id: int,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.fulfil(
        user,
        order_id,
        context=get_request_context(request),
        background=background,
    )


@router.post("/{order_id}/cancel")
async def cancel_customer_order(
    order_id: int,
    request: Request,
    payload: StaffCancelOrderRequest,
    background: BackgroundTasks,
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerOrderService = Depends(get_customer_order_service),
) -> dict[str, Any]:
    return await service.staff_cancel(
        user,
        order_id,
        payload.reason,
        context=get_request_context(request),
        background=background,
    )
