from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.production import _coerce_number
from app.utils.time import iso_timestamp

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REASONS = {"spoiled", "spilled", "returned"}
REASON_MESSAGE = 'Invalid option: expected one of "spoiled"|"spilled"|"returned"'


class RecordWastageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    waste_date: str
    litres: Any
    reason: Any

    @field_validator("waste_date")
    @classmethod
    def _waste_date(cls, value: str) -> str:
        if not DATE_PATTERN.match(value):
            raise ValueError("Waste date must be in YYYY-MM-DD format")
        return value

    @field_validator("litres")
    @classmethod
    def _litres(cls, value: Any) -> float:
        number = _coerce_number(value)
        if number <= 0:
            raise ValueError("Litres must be greater than zero")
        return number

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: Any) -> str:
        if not isinstance(value, str) or value not in REASONS:
            raise ValueError(REASON_MESSAGE)
        return value


@dataclass(slots=True)
class WastageQuery:
    page: int = 1
    page_size: int = 20
    waste_date: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    reason: str | None = None


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


def serialize_wastage(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "waste_date": _date_string(record.waste_date),
        "litres": _litres_string(record.litres),
        "reason": record.reason,
        "recorded_by": record.recorded_by,
        "is_deleted": bool(record.is_deleted),
        "createdAt": iso_timestamp(record.created_at),
        "updatedAt": iso_timestamp(record.updated_at),
    }


def serialize_wastage_detail(record: Any) -> dict[str, Any]:
    data = serialize_wastage(record)
    recorder = record.recorder
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
