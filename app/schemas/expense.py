from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.production import _coerce_number
from app.utils.time import iso_timestamp

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNSET = object()


def _received_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _positive_category_id(value: Any) -> int:
    number = _coerce_number(value)
    if not number.is_integer():
        raise ValueError("Invalid input: expected int, received number")
    category_id = int(number)
    if category_id <= 0:
        raise ValueError("category_id must be a positive integer")
    return category_id


def _date_text(value: Any, message: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    if not DATE_PATTERN.match(value):
        raise ValueError(message)
    return value


def _positive_amount(value: Any) -> float:
    number = _coerce_number(value)
    if number <= 0:
        raise ValueError("amount must be greater than zero")
    if number > 999999999.99:
        raise ValueError("amount exceeds maximum allowable threshold")
    return number


def _optional_note(value: Any) -> Any:
    if value is UNSET:
        return value
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    if len(value) > 1000:
        raise ValueError("Too big: expected string to have <=1000 characters")
    text = value.strip()
    return text or None


class CreateExpenseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category_id: Any
    expense_date: Any
    amount: Any
    note: Any = Field(default_factory=lambda: UNSET)

    @field_validator("category_id")
    @classmethod
    def _category_id(cls, value: Any) -> int:
        return _positive_category_id(value)

    @field_validator("expense_date")
    @classmethod
    def _expense_date(cls, value: Any) -> str:
        return _date_text(value, "expense_date must be in YYYY-MM-DD format")

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: Any) -> float:
        return _positive_amount(value)

    @field_validator("note")
    @classmethod
    def _note(cls, value: Any) -> Any:
        checked = _optional_note(value)
        return None if checked is UNSET else checked


class UpdateExpenseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category_id: Any = Field(default_factory=lambda: UNSET)
    expense_date: Any = Field(default_factory=lambda: UNSET)
    amount: Any = Field(default_factory=lambda: UNSET)
    note: Any = Field(default_factory=lambda: UNSET)

    @field_validator("category_id")
    @classmethod
    def _category_id(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _positive_category_id(value)

    @field_validator("expense_date")
    @classmethod
    def _expense_date(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _date_text(value, "expense_date must be in YYYY-MM-DD format")

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _positive_amount(value)

    @field_validator("note")
    @classmethod
    def _note(cls, value: Any) -> Any:
        return _optional_note(value)


class ExpenseQuery:
    def __init__(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        category_id: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.category_id = category_id
        self.from_date = from_date
        self.to_date = to_date


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _decimal_string(value: Any) -> str:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return f"{float(value):.2f}"


def serialize_expense_category_ref(category: Any) -> dict[str, Any]:
    return {"id": category.id, "name": category.name}


def serialize_expense_recorder(recorder: Any) -> dict[str, Any]:
    return {
        "id": recorder.id,
        "full_name": recorder.full_name,
        "username": recorder.username,
    }


def serialize_expense(expense: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": expense.id,
        "category_id": expense.category_id,
        "expense_date": _date_string(expense.expense_date),
        "amount": _decimal_string(expense.amount),
        "note": expense.note,
        "recorded_by": expense.recorded_by,
        "is_deleted": bool(expense.is_deleted),
        "createdAt": iso_timestamp(expense.created_at),
        "updatedAt": iso_timestamp(expense.updated_at),
    }
    category = getattr(expense, "category", None)
    if category is not None:
        data["category"] = serialize_expense_category_ref(category)
    recorder = getattr(expense, "recorder", None)
    data["recorder"] = (
        serialize_expense_recorder(recorder) if recorder is not None else None
    )
    return data
