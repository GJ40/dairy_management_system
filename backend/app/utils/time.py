from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def business_timezone() -> ZoneInfo:
    return ZoneInfo(settings.tz)


def business_now() -> datetime:
    return datetime.now(business_timezone())


def business_now_naive() -> datetime:
    return datetime.now(business_timezone()).replace(tzinfo=None)


def get_business_date(at: datetime | None = None) -> str:
    if at is None:
        return business_now().date().isoformat()
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone(business_timezone()).date().isoformat()


def iso_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=business_timezone())
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def is_future_date(date_str: str) -> bool:
    return date_str > get_business_date()


def is_today(date_str: str) -> bool:
    return date_str == get_business_date()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
