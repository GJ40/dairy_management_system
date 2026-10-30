from __future__ import annotations

import math
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import get_buffalo_service, require_roles
from app.core.errors import api_error
from app.schemas.buffalo import (
    BuffaloQuery,
    CreateBuffaloRequest,
    UpdateBuffaloRequest,
)
from app.services.buffalo_service import BuffaloService

router = APIRouter(
    prefix="/buffaloes",
    tags=["buffaloes"],
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


def parse_buffalo_query(request: Request) -> BuffaloQuery:
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

    status = params.get("status")
    if status is not None and status not in ("active", "sold", "dry", "dead"):
        _validation_error(
            'status: Invalid option: expected one of "active"|"sold"|"dry"|"dead"'
        )

    search_raw = params.get("search")
    search = search_raw.strip() if search_raw is not None else None
    if not search:
        search = None

    return BuffaloQuery(
        page=page,
        page_size=page_size,
        status=status,
        search=search,
    )


@router.get("/count")
async def get_buffalo_counts(
    service: BuffaloService = Depends(get_buffalo_service),
) -> dict[str, int]:
    return await service.get_counts()


@router.get("")
async def list_buffaloes(
    query: BuffaloQuery = Depends(parse_buffalo_query),
    service: BuffaloService = Depends(get_buffalo_service),
) -> dict[str, Any]:
    return await service.list_buffaloes(query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_buffalo(
    payload: CreateBuffaloRequest,
    service: BuffaloService = Depends(get_buffalo_service),
) -> dict[str, Any]:
    return {"buffalo": await service.create_buffalo(payload)}


@router.get("/{buffalo_id}")
async def get_buffalo(
    buffalo_id: str,
    service: BuffaloService = Depends(get_buffalo_service),
) -> dict[str, Any]:
    return {"buffalo": await service.get_buffalo(buffalo_id)}


@router.put("/{buffalo_id}")
async def update_buffalo(
    buffalo_id: str,
    payload: UpdateBuffaloRequest,
    service: BuffaloService = Depends(get_buffalo_service),
) -> dict[str, Any]:
    return {"buffalo": await service.update_buffalo(buffalo_id, payload)}
