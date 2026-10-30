from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import get_stock_service, require_roles
from app.core.errors import api_error
from app.schemas.wastage import DATE_PATTERN
from app.services.stock_service import StockService

router = APIRouter(
    prefix="/stock",
    tags=["stock"],
    dependencies=[Depends(require_roles("admin", "operator"))],
)


def _validation_error(message: str) -> NoReturn:
    raise api_error(
        status.HTTP_400_BAD_REQUEST,
        "VALIDATION_ERROR",
        message,
    )


def _optional_date(
    request: Request,
    parameter: str,
    message: str,
) -> str | None:
    value = request.query_params.get(parameter)
    if value is not None and not DATE_PATTERN.match(value):
        _validation_error(f"{parameter}: {message}")
    return value


def _required_date(
    request: Request,
    parameter: str,
    message: str,
) -> str:
    value = request.query_params.get(parameter)
    if value is None:
        _validation_error(
            f"{parameter}: Invalid input: expected string, received undefined"
        )
    if not DATE_PATTERN.match(value):
        _validation_error(f"{parameter}: {message}")
    return value


@router.get("/history")
async def stock_history(
    request: Request,
    service: StockService = Depends(get_stock_service),
) -> dict[str, Any]:
    from_date = _required_date(
        request,
        "from",
        "'from' date must be in YYYY-MM-DD format",
    )
    to_date = _required_date(
        request,
        "to",
        "'to' date must be in YYYY-MM-DD format",
    )
    return await service.get_stock_history(from_date, to_date)


@router.get("")
async def stock_for_date(
    request: Request,
    service: StockService = Depends(get_stock_service),
) -> dict[str, Any]:
    raw_date = _optional_date(
        request,
        "date",
        "Date must be in YYYY-MM-DD format",
    )
    return await service.get_stock_for_date(raw_date)
