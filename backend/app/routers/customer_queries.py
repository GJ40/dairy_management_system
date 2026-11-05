from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import get_customer_query_service, require_roles
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.customer_queries import (
    QueryAssignRequest,
    QueryStatusRequest,
    StaffAddQueryMessageRequest,
    StaffQueryListQuery,
)
from app.services.customer_query_service import CustomerQueryService

router = APIRouter(
    prefix="/customer-queries",
    tags=["customer-queries"],
    dependencies=[Depends(require_roles("admin", "operator"))],
)


@router.get("")
async def list_customer_queries(
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_to: int | None = None,
    customer_id: int | None = None,
    category: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.staff_list_queries(
        StaffQueryListQuery(
            page=page,
            page_size=page_size,
            status=status_filter or None,
            assigned_to=assigned_to,
            customer_id=customer_id,
            category=category or None,
        )
    )


@router.get("/{query_id}")
async def get_customer_query(
    query_id: int,
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.staff_get_query(query_id)


@router.post(
    "/{query_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
async def add_customer_query_message(
    query_id: int,
    payload: StaffAddQueryMessageRequest,
    request: Request,
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.add_staff_message(
        user,
        query_id,
        payload.message,
        is_internal=payload.is_internal,
        context=get_request_context(request),
    )


@router.post("/{query_id}/status")
async def change_customer_query_status(
    query_id: int,
    payload: QueryStatusRequest,
    request: Request,
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.change_status(
        user,
        query_id,
        payload.status,
        context=get_request_context(request),
    )


@router.post("/{query_id}/assign")
async def assign_customer_query(
    query_id: int,
    payload: QueryAssignRequest,
    request: Request,
    user: User = Depends(require_roles("admin")),
    service: CustomerQueryService = Depends(get_customer_query_service),
) -> dict[str, Any]:
    return await service.assign(
        user,
        query_id,
        payload.assigned_to,
        context=get_request_context(request),
    )
