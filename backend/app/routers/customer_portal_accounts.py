from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from app.core.dependencies import (
    get_customer_portal_account_service,
    require_admin,
    require_roles,
)
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.customer_portal_auth import (
    CreatePortalAccountRequest,
    DeactivatePortalAccountRequest,
    PortalAccountQuery,
)
from app.services.customer_portal_auth_service import CustomerPortalAccountService

router = APIRouter(
    prefix="/customer-portal-accounts",
    tags=["customer-portal-accounts"],
)


@router.get("")
async def list_accounts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    customer_id: int | None = None,
    is_active: bool | None = None,
    is_locked: bool | None = None,
    _user: User = Depends(require_roles("admin", "operator")),
    service: CustomerPortalAccountService = Depends(
        get_customer_portal_account_service
    ),
) -> dict[str, Any]:
    return await service.list_accounts(
        PortalAccountQuery(
            page=page,
            page_size=page_size,
            customer_id=customer_id,
            is_active=is_active,
            is_locked=is_locked,
        )
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def provision_account(
    payload: CreatePortalAccountRequest,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_admin),
    service: CustomerPortalAccountService = Depends(
        get_customer_portal_account_service
    ),
) -> dict[str, Any]:
    return await service.provision(
        payload,
        user.id,
        background=background,
        context=get_request_context(request),
    )


@router.get("/{account_id}")
async def get_account(
    account_id: int,
    _user: User = Depends(require_roles("admin", "operator")),
    service: CustomerPortalAccountService = Depends(
        get_customer_portal_account_service
    ),
) -> dict[str, Any]:
    return await service.get_account(account_id)


@router.post("/{account_id}/reactivate")
async def reactivate_account(
    account_id: int,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_admin),
    service: CustomerPortalAccountService = Depends(
        get_customer_portal_account_service
    ),
) -> dict[str, Any]:
    return await service.reactivate(
        account_id,
        user.id,
        background=background,
        context=get_request_context(request),
    )


@router.post("/{account_id}/unlock")
async def unlock_account(
    account_id: int,
    request: Request,
    user: User = Depends(require_admin),
    service: CustomerPortalAccountService = Depends(
        get_customer_portal_account_service
    ),
) -> dict[str, Any]:
    return await service.unlock(
        account_id,
        user.id,
        context=get_request_context(request),
    )


@router.post("/{account_id}/deactivate")
async def deactivate_account(
    account_id: int,
    payload: DeactivatePortalAccountRequest,
    request: Request,
    user: User = Depends(require_admin),
    service: CustomerPortalAccountService = Depends(
        get_customer_portal_account_service
    ),
) -> dict[str, Any]:
    return await service.deactivate(
        account_id,
        payload.reason,
        user.id,
        context=get_request_context(request),
    )


@router.post("/{account_id}/reset-activation")
async def reset_activation(
    account_id: int,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_admin),
    service: CustomerPortalAccountService = Depends(
        get_customer_portal_account_service
    ),
) -> dict[str, Any]:
    return await service.reset_activation(
        account_id,
        user.id,
        background=background,
        context=get_request_context(request),
    )
