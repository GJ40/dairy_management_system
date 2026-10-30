from __future__ import annotations

import math
import re
from typing import Any, NoReturn

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import (
    get_expense_category_service,
    get_expense_service,
    require_roles,
)
from app.core.errors import api_error
from app.models.user import User
from app.schemas.expense import (
    CreateExpenseRequest,
    ExpenseQuery,
    UpdateExpenseRequest,
)
from app.schemas.expense_category import CreateExpenseCategoryRequest
from app.services.expense_category_service import ExpenseCategoryService
from app.services.expense_service import ExpenseService

ADMIN = require_roles("admin")

router = APIRouter(
    prefix="/expenses",
    tags=["expenses"],
    dependencies=[Depends(ADMIN)],
)
alias_router = APIRouter(
    prefix="/expense-categories",
    tags=["expenses"],
    dependencies=[Depends(ADMIN)],
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
    if value is not None and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        _validation_error(f"{name}: {name} must be in 'YYYY-MM-DD' format")
    return value


def parse_expense_query(request: Request) -> ExpenseQuery:
    params = request.query_params
    return ExpenseQuery(
        page=_parse_int_param(
            params.get("page"),
            name="page",
            default=1,
            minimum=1,
        ),
        page_size=_parse_int_param(
            params.get("page_size"),
            name="page_size",
            default=20,
            minimum=1,
            maximum=100,
        ),
        category_id=_optional_positive_int(params, "category_id"),
        from_date=_optional_date(params, "from"),
        to_date=_optional_date(params, "to"),
    )


@router.get("/categories")
async def list_categories(
    service: ExpenseCategoryService = Depends(get_expense_category_service),
) -> dict[str, Any]:
    return await service.list_categories()


@alias_router.get("")
async def list_expense_categories_alias(
    service: ExpenseCategoryService = Depends(get_expense_category_service),
) -> dict[str, Any]:
    return await service.list_categories()


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    body: dict[str, Any] = Body(...),
    service: ExpenseCategoryService = Depends(get_expense_category_service),
) -> dict[str, Any]:
    try:
        payload = CreateExpenseCategoryRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.create_category(payload)


@router.get("")
async def list_expenses(
    query: ExpenseQuery = Depends(parse_expense_query),
    service: ExpenseService = Depends(get_expense_service),
) -> dict[str, Any]:
    return await service.list_expenses(query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: ExpenseService = Depends(get_expense_service),
) -> dict[str, Any]:
    try:
        payload = CreateExpenseRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.create_expense(payload, user.id)


@router.get("/{expense_id}")
async def get_expense(
    expense_id: str,
    service: ExpenseService = Depends(get_expense_service),
) -> dict[str, Any]:
    return await service.get_expense(expense_id)


@router.put("/{expense_id}")
async def update_expense(
    expense_id: str,
    body: dict[str, Any] = Body(...),
    service: ExpenseService = Depends(get_expense_service),
) -> dict[str, Any]:
    try:
        payload = UpdateExpenseRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.update_expense(expense_id, payload)
