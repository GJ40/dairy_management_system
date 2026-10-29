from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.utils.time import iso_timestamp

DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
NUMBER_PATTERN = re.compile(
    r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$"
)
HEX_PATTERN = re.compile(r"^0[xX][0-9a-fA-F]+$")
BINARY_PATTERN = re.compile(r"^0[bB][01]+$")
OCTAL_PATTERN = re.compile(r"^0[oO][0-7]+$")
SESSIONS = {"morning", "evening"}
UNSET = object()


def _coerce_number(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if text == "":
            return 0.0
        if text in ("Infinity", "+Infinity"):
            number = math.inf
        elif text == "-Infinity":
            number = -math.inf
        elif NUMBER_PATTERN.match(text):
            number = float(text)
        elif HEX_PATTERN.match(text):
            number = float(int(text, 16))
        elif BINARY_PATTERN.match(text):
            number = float(int(text, 2))
        elif OCTAL_PATTERN.match(text):
            number = float(int(text, 8))
        else:
            raise ValueError("Invalid input: expected number, received NaN")
    elif isinstance(value, list):
        if not value:
            return 0.0
        if len(value) == 1:
            return _coerce_number(value[0])
        raise ValueError("Invalid input: expected number, received NaN")
    else:
        raise ValueError("Invalid input: expected number, received NaN")
    if math.isnan(number):
        raise ValueError("Invalid input: expected number, received NaN")
    if math.isinf(number):
        label = "Infinity" if number > 0 else "-Infinity"
        raise ValueError(
            f"Invalid input: expected number, received {label}"
        )
    if number == 0:
        return 0.0
    return number


def _positive_int(value: Any) -> int:
    number = _coerce_number(value)
    if not number.is_integer():
        raise ValueError("Invalid input: expected int, received number")
    result = int(number)
    if result <= 0:
        raise ValueError("Valid buffalo ID is required")
    return result


def _non_negative(value: Any, message: str) -> float:
    number = _coerce_number(value)
    if number < 0:
        raise ValueError(message)
    return number


def _enum(value: Any, options: set[str], message: str) -> str:
    if not isinstance(value, str) or value not in options:
        raise ValueError(message)
    return value


def _date_text(value: str, message: str) -> str:
    if not DATE_PATTERN.match(value):
        raise ValueError(message)
    return value


class SingleProductionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    buffalo_id: Any
    prod_date: str
    session: Any
    litres: Any
    overwrite: StrictBool = False

    @field_validator("buffalo_id")
    @classmethod
    def _buffalo_id(cls, value: Any) -> int:
        return _positive_int(value)

    @field_validator("prod_date")
    @classmethod
    def _prod_date(cls, value: str) -> str:
        return _date_text(value, "Production date must be in YYYY-MM-DD format")

    @field_validator("session")
    @classmethod
    def _session(cls, value: Any) -> str:
        return _enum(
            value,
            SESSIONS,
            'Invalid option: expected one of "morning"|"evening"',
        )

    @field_validator("litres")
    @classmethod
    def _litres(cls, value: Any) -> float:
        return _non_negative(value, "Litres must be non-negative (zero or greater)")


class BulkProductionEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    buffalo_id: Any
    morning_litres: Any = Field(default_factory=lambda: UNSET)
    evening_litres: Any = Field(default_factory=lambda: UNSET)
    session: Any = Field(default_factory=lambda: UNSET)
    litres: Any = Field(default_factory=lambda: UNSET)

    @field_validator("buffalo_id")
    @classmethod
    def _buffalo_id(cls, value: Any) -> int:
        return _positive_int(value)

    @field_validator("morning_litres")
    @classmethod
    def _morning_litres(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _non_negative(value, "Morning litres must be non-negative")

    @field_validator("evening_litres")
    @classmethod
    def _evening_litres(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _non_negative(value, "Evening litres must be non-negative")

    @field_validator("session")
    @classmethod
    def _session(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _enum(
            value,
            SESSIONS,
            'Invalid option: expected one of "morning"|"evening"',
        )

    @field_validator("litres")
    @classmethod
    def _litres(cls, value: Any) -> Any:
        if value is UNSET:
            return value
        return _non_negative(value, "Litres must be non-negative")


class BulkProductionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prod_date: str
    entries: list[BulkProductionEntry]
    overwrite: StrictBool = False

    @field_validator("prod_date")
    @classmethod
    def _prod_date(cls, value: str) -> str:
        return _date_text(value, "Production date must be in YYYY-MM-DD format")

    @field_validator("entries")
    @classmethod
    def _entries(
        cls,
        value: list[BulkProductionEntry],
    ) -> list[BulkProductionEntry]:
        if not value:
            raise ValueError(
                "At least one production entry is required in bulk submission"
            )
        return value


@dataclass(slots=True)
class ProductionDateQuery:
    date: str | None = None


@dataclass(slots=True)
class ProductionSummaryQuery:
    from_date: str
    to_date: str


@dataclass(slots=True)
class BuffaloProductionQuery:
    from_date: str | None = None
    to_date: str | None = None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _litres_string(value: Any) -> str:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return f"{float(value):.2f}"


def serialize_production(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "buffalo_id": record.buffalo_id,
        "prod_date": _date_string(record.prod_date),
        "session": record.session,
        "litres": _litres_string(record.litres),
        "recorded_by": record.recorded_by,
        "is_deleted": bool(record.is_deleted),
        "createdAt": iso_timestamp(record.created_at),
        "updatedAt": iso_timestamp(record.updated_at),
    }


def serialize_production_detail(record: Any) -> dict[str, Any]:
    data = serialize_production(record)
    buffalo = record.buffalo
    recorder = record.recorder
    data["buffalo"] = (
        {
            "id": buffalo.id,
            "tag_no": buffalo.tag_no,
            "name": buffalo.name,
            "breed": buffalo.breed,
            "status": buffalo.status,
        }
        if buffalo is not None
        else None
    )
    data["recorder"] = (
        {
            "id": recorder.id,
            "full_name": recorder.full_name,
            "username": recorder.username,
        }
        if recorder is not None
        else None
    )
    return data
