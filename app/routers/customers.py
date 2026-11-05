from __future__ import annotations

import math
from typing import Any, NoReturn

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import get_customer_service, require_roles
from app.core.errors import api_error
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.customer import (
    CreateCustomerRequest,
    CustomerQuery,
    UpdateCustomerRequest,
)
from app.services.customer_service import CustomerService

router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(require_roles("admin", "operator"))],
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


def parse_customer_query(request: Request) -> CustomerQuery:
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

    search = params.get("search")
    if search is not None:
        search = search.strip()
        if not search:
            search = None

    is_active = None
    is_active_raw = params.get("is_active")
    if is_active_raw is not None:
        if is_active_raw not in ("true", "false"):
            _validation_error(
                'is_active: Invalid option: expected one of "true"|"false"'
            )
        is_active = is_active_raw == "true"

    return CustomerQuery(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )


@router.get("")
async def list_customers(
    query: CustomerQuery = Depends(parse_customer_query),
    service: CustomerService = Depends(get_customer_service),
) -> dict[str, Any]:
    return await service.list_customers(query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerService = Depends(get_customer_service),
) -> dict[str, Any]:
    try:
        payload = CreateCustomerRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return {
        "customer": await service.create_customer(
            payload,
            actor_user_id=user.id,
            context=get_request_context(request),
        )
    }


@router.get("/{customer_id}/balance")
async def customer_balance(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
) -> dict[str, Any]:
    return await service.get_customer_balance(customer_id)


@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
) -> dict[str, Any]:
    return {"customer": await service.get_customer(customer_id)}


@router.put("/{customer_id}")
async def update_customer(
    customer_id: str,
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: CustomerService = Depends(get_customer_service),
) -> dict[str, Any]:
    try:
        payload = UpdateCustomerRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return {
        "customer": await service.update_customer(
            customer_id,
            payload,
            actor_user_id=user.id,
            context=get_request_context(request),
        )
    }
