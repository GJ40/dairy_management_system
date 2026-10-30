from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.time import iso_timestamp

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUSES = {"active", "sold", "dry", "dead"}
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


def _validate_string(value: Any) -> str:
    if value is UNSET:
        return value  # type: ignore[return-value]
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid input: expected string, received {_received_type(value)}"
        )
    return value


def _validate_optional_date(value: Any, message: str) -> str | None:
    if value is UNSET:
        return value  # type: ignore[return-value]
    if value is None:
        return None
    text = _validate_string(value)
    if not DATE_PATTERN.match(text):
        raise ValueError(message)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(message) from exc
    return text


class CreateBuffaloRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tag_no: str
    name: str
    breed: str
    dob: str | None = None
    purchase_date: str | None = None
    status: Any = "active"

    @field_validator("tag_no")
    @classmethod
    def _tag_no(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Tag number cannot be empty")
        if len(normalized) > 50:
            raise ValueError("Tag number cannot exceed 50 characters")
        return normalized

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be empty")
        if len(normalized) > 100:
            raise ValueError("Name cannot exceed 100 characters")
        return normalized

    @field_validator("breed")
    @classmethod
    def _breed(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Breed cannot be empty")
        if len(normalized) > 80:
            raise ValueError("Breed cannot exceed 80 characters")
        return normalized

    @field_validator("dob")
    @classmethod
    def _dob(cls, value: Any) -> str | None:
        return _validate_optional_date(value, "Date of birth must be YYYY-MM-DD")

    @field_validator("purchase_date")
    @classmethod
    def _purchase_date(cls, value: Any) -> str | None:
        return _validate_optional_date(value, "Purchase date must be YYYY-MM-DD")

    @field_validator("status")
    @classmethod
    def _status(cls, value: Any) -> str:
        if not isinstance(value, str) or value not in STATUSES:
            raise ValueError(
                'Invalid option: expected one of "active"|"sold"|"dry"|"dead"'
            )
        return value


class UpdateBuffaloRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tag_no: Any = Field(default_factory=lambda: UNSET)
    name: Any = Field(default_factory=lambda: UNSET)
    breed: Any = Field(default_factory=lambda: UNSET)
    dob: Any = Field(default_factory=lambda: UNSET)
    purchase_date: Any = Field(default_factory=lambda: UNSET)
    status: Any = Field(default_factory=lambda: UNSET)

    @field_validator("tag_no")
    @classmethod
    def _tag_no(cls, value: Any) -> Any:
        text = _validate_string(value)
        if text is UNSET:
            return text
        normalized = text.strip()
        if len(normalized) < 1:
            raise ValueError("Too small: expected string to have >=1 characters")
        if len(normalized) > 50:
            raise ValueError("Too big: expected string to have <=50 characters")
        return normalized

    @field_validator("name")
    @classmethod
    def _name(cls, value: Any) -> Any:
        text = _validate_string(value)
        if text is UNSET:
            return text
        normalized = text.strip()
        if len(normalized) < 1:
            raise ValueError("Too small: expected string to have >=1 characters")
        if len(normalized) > 100:
            raise ValueError("Too big: expected string to have <=100 characters")
        return normalized

    @field_validator("breed")
    @classmethod
    def _breed(cls, value: Any) -> Any:
        text = _validate_string(value)
        if text is UNSET:
            return text
        normalized = text.strip()
        if len(normalized) < 1:
            raise ValueError("Too small: expected string to have >=1 characters")
        if len(normalized) > 80:
            raise ValueError("Too big: expected string to have <=80 characters")
        return normalized

    @field_validator("dob")
    @classmethod
    def _dob(cls, value: Any) -> Any:
        return _validate_optional_date(value, "Date of birth must be YYYY-MM-DD")

    @field_validator("purchase_date")
    @classmethod
    def _purchase_date(cls, value: Any) -> Any:
        return _validate_optional_date(value, "Purchase date must be YYYY-MM-DD")

    @field_validator("status")
    @classmethod
    def _status(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        if not isinstance(value, str) or value not in STATUSES:
            raise ValueError(
                'Invalid option: expected one of "active"|"sold"|"dry"|"dead"'
            )
        return value


@dataclass(slots=True)
class BuffaloQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None
    search: str | None = None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def serialize_buffalo(buffalo: Any) -> dict[str, Any]:
    return {
        "id": buffalo.id,
        "tag_no": buffalo.tag_no,
        "name": buffalo.name,
        "breed": buffalo.breed,
        "dob": _date_string(buffalo.dob),
        "purchase_date": _date_string(buffalo.purchase_date),
        "status": buffalo.status,
        "is_deleted": bool(buffalo.is_deleted),
        "createdAt": iso_timestamp(buffalo.created_at),
        "updatedAt": iso_timestamp(buffalo.updated_at),
    }
