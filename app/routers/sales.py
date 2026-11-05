from __future__ import annotations

import math
from typing import Any, NoReturn

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import get_sale_service, require_roles
from app.core.errors import api_error
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.sale import (
    DATE_PATTERN,
    CreateSaleRequest,
    SaleQuery,
    UpdateSaleRequest,
)
from app.services.sale_service import SaleService

router = APIRouter(
    prefix="/sales",
    tags=["sales"],
    dependencies=[Depends(require_roles("admin", "operator"))],
)

DATE_MESSAGE = "Invalid string: must match pattern /^\\d{4}-\\d{2}-\\d{2}$/"


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


def _optional_positive_int(params: Any, name: str) -> int | None:
    raw = params.get(name)
    if raw is None:
        return None
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
    if value <= 0:
        _validation_error(f"{name}: Too small: expected number to be >0")
    return value


def _optional_date(params: Any, name: str) -> str | None:
    value = params.get(name)
    if value is not None and not DATE_PATTERN.match(value):
        _validation_error(f"{name}: {DATE_MESSAGE}")
    return value


def parse_sale_query(request: Request) -> SaleQuery:
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
    customer_id = _optional_positive_int(params, "customer_id")
    sale_date = _optional_date(params, "sale_date")
    from_date = _optional_date(params, "from")
    to_date = _optional_date(params, "to")

    payment_status = params.get("payment_status")
    if payment_status is not None and payment_status not in ("unpaid", "paid"):
        _validation_error(
            'payment_status: Invalid option: expected one of "unpaid"|"paid"'
        )

    return SaleQuery(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        sale_date=sale_date,
        from_date=from_date,
        to_date=to_date,
        payment_status=payment_status,
    )


@router.get("")
async def list_sales(
    query: SaleQuery = Depends(parse_sale_query),
    service: SaleService = Depends(get_sale_service),
) -> dict[str, Any]:
    return await service.list_sales(query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_sale(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: SaleService = Depends(get_sale_service),
) -> dict[str, Any]:
    try:
        payload = CreateSaleRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.record_sale(
        payload,
        user,
        context=get_request_context(request),
    )


@router.get("/{sale_id}")
async def get_sale(
    sale_id: str,
    service: SaleService = Depends(get_sale_service),
) -> dict[str, Any]:
    return {"sale": await service.get_sale(sale_id)}


@router.put("/{sale_id}")
async def update_sale(
    sale_id: str,
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: SaleService = Depends(get_sale_service),
) -> dict[str, Any]:
    try:
        payload = UpdateSaleRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return {
        "sale": await service.update_sale(
            sale_id,
            payload,
            user,
            context=get_request_context(request),
        )
    }
