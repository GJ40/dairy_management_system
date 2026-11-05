from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import get_production_service, require_roles
from app.core.errors import api_error
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.production import (
    DATE_PATTERN,
    BulkProductionRequest,
    SingleProductionRequest,
)
from app.services.production_service import ProductionService

router = APIRouter(
    prefix="/production",
    tags=["production"],
    dependencies=[Depends(require_roles("admin", "operator"))],
)


def _validation_error(message: str) -> None:
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


@router.get("/grid")
async def production_grid(
    request: Request,
    service: ProductionService = Depends(get_production_service),
) -> dict[str, Any]:
    raw_date = _optional_date(
        request,
        "date",
        "Date query must be in YYYY-MM-DD format",
    )
    return await service.get_grid(raw_date)


@router.get("/summary")
async def production_summary(
    request: Request,
    service: ProductionService = Depends(get_production_service),
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
    return await service.get_summary(from_date, to_date)


@router.get("/buffalo/{buffalo_id}")
async def buffalo_production_history(
    buffalo_id: str,
    request: Request,
    service: ProductionService = Depends(get_production_service),
) -> dict[str, Any]:
    from_date = _optional_date(
        request,
        "from",
        "'from' date must be in YYYY-MM-DD format",
    )
    to_date = _optional_date(
        request,
        "to",
        "'to' date must be in YYYY-MM-DD format",
    )
    return await service.get_buffalo_history(buffalo_id, from_date, to_date)


@router.get("")
async def production_by_date(
    request: Request,
    service: ProductionService = Depends(get_production_service),
) -> dict[str, Any]:
    raw_date = _optional_date(
        request,
        "date",
        "Date query must be in YYYY-MM-DD format",
    )
    return await service.get_production_by_date(raw_date)


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_production(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(require_roles("admin", "operator")),
    service: ProductionService = Depends(get_production_service),
) -> dict[str, Any]:
    context = get_request_context(request)
    if isinstance(body.get("entries"), list):
        try:
            payload = BulkProductionRequest.model_validate(body)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_url=False)) from exc
        records = await service.record_bulk_production(
            payload,
            user,
            context=context,
        )
        return {
            "message": f"Successfully saved {len(records)} production entries",
            "records": records,
        }

    try:
        single = SingleProductionRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    record = await service.record_production(
        single,
        user,
        context=context,
    )
    return {"record": record}
