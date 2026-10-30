from __future__ import annotations

import math
from typing import Any, NoReturn

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import get_wastage_service, require_roles
from app.core.errors import api_error
from app.models.user import User
from app.schemas.wastage import (
    DATE_PATTERN,
    REASON_MESSAGE,
    REASONS,
    RecordWastageRequest,
    WastageQuery,
)
from app.services.wastage_service import WastageService

router = APIRouter(
    prefix="/wastage",
    tags=["wastage"],
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


def _optional_date(params: Any, name: str) -> str | None:
    value = params.get(name)
    if value is not None and not DATE_PATTERN.match(value):
        _validation_error(f"{name}: {DATE_MESSAGE}")
    return value


def parse_wastage_query(request: Request) -> WastageQuery:
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
    waste_date = _optional_date(params, "waste_date")
    from_date = _optional_date(params, "from")
    to_date = _optional_date(params, "to")

    reason = params.get("reason")
    if reason is not None and reason not in REASONS:
        _validation_error(f"reason: {REASON_MESSAGE}")

    return WastageQuery(
        page=page,
        page_size=page_size,
        waste_date=waste_date,
        from_date=from_date,
        to_date=to_date,
        reason=reason,
    )


@router.get("")
async def list_wastage(
    query: WastageQuery = Depends(parse_wastage_query),
    service: WastageService = Depends(get_wastage_service),
) -> dict[str, Any]:
    return await service.list_wastage(query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_wastage(
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: WastageService = Depends(get_wastage_service),
) -> dict[str, Any]:
    try:
        payload = RecordWastageRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.record_wastage(payload, user)
