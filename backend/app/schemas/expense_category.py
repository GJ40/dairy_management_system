from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.utils.time import iso_timestamp


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


class CreateExpenseCategoryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Any

    @field_validator("name")
    @classmethod
    def _name(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"Invalid input: expected string, received {_received_type(value)}"
            )
        text = value.strip()
        if len(text) < 2:
            raise ValueError("Category name must be at least 2 characters long")
        if len(text) > 80:
            raise ValueError("Category name cannot exceed 80 characters")
        return text.lower()


def serialize_expense_category(category: Any) -> dict[str, Any]:
    return {
        "id": category.id,
        "name": category.name,
        "is_deleted": bool(category.is_deleted),
        "createdAt": iso_timestamp(category.created_at),
        "updatedAt": iso_timestamp(category.updated_at),
    }
