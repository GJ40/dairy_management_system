from __future__ import annotations

import re
from dataclasses import dataclass

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
PERIODS = {"daily", "monthly", "custom"}


@dataclass(slots=True)
class ProfitReportQuery:
    period: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    month: str | None = None
    date: str | None = None


@dataclass(slots=True)
class ProductionReportQuery:
    from_date: str | None = None
    to_date: str | None = None


@dataclass(slots=True)
class DashboardQuery:
    date: str | None = None
