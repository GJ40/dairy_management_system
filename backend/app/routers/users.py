from __future__ import annotations

import math
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import (
    get_user_service,
    require_admin,
)
from app.core.errors import api_error
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.user import (
    CreateUserRequest,
    UpdateUserRequest,
    UpdateUserStatusRequest,
    UserQuery,
)
from app.services.user_service import UserService

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


def _validation_error(message: str) -> NoReturn:
    raise api_error(
        status.HTTP_400_BAD_REQUEST,
        "VALIDATION_ERROR",
        message,
    )


def _parse_int_param(
    raw: str | None,
    *,
    name: str,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if raw is None:
        return default
    text = raw.strip()
    try:
        number = 0.0 if text == "" else float(text)
    except ValueError:
        _validation_error(f"{name}: Invalid input: expected number, received NaN")
    if math.isnan(number) or math.isinf(number):
        _validation_error(f"{name}: Invalid input: expected number, received NaN")
    if not number.is_integer():
        _validation_error(f"{name}: Invalid input: expected int, received number")
    value = int(number)
    if value < minimum:
        _validation_error(f"{name}: Too small: expected number to be >={minimum}")
    if maximum is not None and value > maximum:
        _validation_error(f"{name}: Too big: expected number to be <={maximum}")
    return value


def parse_user_query(request: Request) -> UserQuery:
    params = request.query_params
    page = _parse_int_param(
        params.get("page"),
        name="page",
        default=1,
        minimum=1,
    )
    page_size = _parse_int_param(
        params.get("page_size"),
        name="page_size",
        default=20,
        minimum=1,
        maximum=100,
    )

    role = params.get("role")
    if role is not None and role not in ("admin", "operator"):
        _validation_error('role: Invalid option: expected one of "admin"|"operator"')

    is_active_raw = params.get("is_active")
    if is_active_raw is not None and is_active_raw not in ("true", "false"):
        _validation_error(
            'is_active: Invalid option: expected one of "true"|"false"'
        )
    is_active = None if is_active_raw is None else is_active_raw == "true"

    is_locked_raw = params.get("is_locked")
    if is_locked_raw is not None and is_locked_raw not in ("true", "false"):
        _validation_error(
            'is_locked: Invalid option: expected one of "true"|"false"'
        )
    is_locked = None if is_locked_raw is None else is_locked_raw == "true"

    search_raw = params.get("search")
    search = search_raw.strip() if search_raw is not None else None
    if not search:
        search = None

    return UserQuery(
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
        is_locked=is_locked,
        search=search,
    )


@router.get("")
async def list_users(
    query: UserQuery = Depends(parse_user_query),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    return await service.list_users(query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    return {
        "user": await service.create_user(
            payload,
            actor_user_id=current_user.id,
            context=get_request_context(request),
        )
    }


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    return {"user": await service.get_user(user_id)}


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    return {
        "user": await service.update_user(
            user_id,
            payload,
            actor_user_id=current_user.id,
            context=get_request_context(request),
        )
    }


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: str,
    payload: UpdateUserStatusRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    return {
        "user": await service.update_status(
            user_id,
            payload.is_active,
            current_user.id,
            context=get_request_context(request),
        )
    }


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    current_user: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> dict[str, Any]:
    """Soft-delete an operator user. Admin-only; target role is re-checked here."""
    return await service.delete_user(
        user_id,
        current_user.id,
        context=get_request_context(request),
    )
