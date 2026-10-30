from __future__ import annotations

from datetime import date
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.dependencies import get_report_service, require_roles
from app.core.errors import api_error
from app.models.user import User
from app.schemas.report import (
    DATE_PATTERN,
    MONTH_PATTERN,
    PERIODS,
    REPORT_TYPES,
    DashboardQuery,
    ProductionReportQuery,
    ProfitReportQuery,
    ReportExportQuery,
)
from app.services.report_service import ReportService

ADMIN = require_roles("admin")
ANY_ROLE = require_roles("admin", "operator")

router = APIRouter(prefix="/reports", tags=["reports"])


def _validation_error(message: str) -> NoReturn:
    raise api_error(
        status.HTTP_400_BAD_REQUEST,
        "VALIDATION_ERROR",
        message,
    )


def _optional_date(params: Any, name: str) -> str | None:
    value = params.get(name)
    if value is None:
        return None
    message = f"{name}: {name} must be in 'YYYY-MM-DD' format"
    if not DATE_PATTERN.match(value):
        _validation_error(message)
    try:
        date.fromisoformat(value)
    except ValueError:
        _validation_error(message)
    return value


def _optional_month(params: Any) -> str | None:
    value = params.get("month")
    if value is None:
        return None
    message = "month: month must be in 'YYYY-MM' format"
    if not MONTH_PATTERN.match(value):
        _validation_error(message)
    if not 1 <= int(value[5:7]) <= 12:
        _validation_error(message)
    return value


def parse_profit_query(request: Request) -> ProfitReportQuery:
    params = request.query_params

    period = params.get("period")
    if period is not None and period not in PERIODS:
        _validation_error(
            'period: Invalid option: expected one of "daily"|"monthly"|"custom"'
        )

    from_date = _optional_date(params, "from")
    to_date = _optional_date(params, "to")
    month = _optional_month(params)
    report_date = _optional_date(params, "date")

    return ProfitReportQuery(
        period=period,
        from_date=from_date,
        to_date=to_date,
        month=month,
        date=report_date,
    )


def parse_production_query(request: Request) -> ProductionReportQuery:
    params = request.query_params
    return ProductionReportQuery(
        from_date=_optional_date(params, "from"),
        to_date=_optional_date(params, "to"),
    )


def parse_dashboard_query(request: Request) -> DashboardQuery:
    params = request.query_params
    return DashboardQuery(date=_optional_date(params, "date"))


def parse_export_query(request: Request) -> ReportExportQuery:
    params = request.query_params

    report_type = params.get("type", "profit")
    if report_type not in REPORT_TYPES:
        _validation_error(
            'type: Invalid option: expected one of '
            '"profit"|"production"|"dashboard"'
        )

    return ReportExportQuery(
        report_type=report_type,
        from_date=_optional_date(params, "from"),
        to_date=_optional_date(params, "to"),
        month=_optional_month(params),
        date=_optional_date(params, "date"),
    )


@router.get("/profit", dependencies=[Depends(ADMIN)])
async def profit_report(
    query: ProfitReportQuery = Depends(parse_profit_query),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    return await service.get_profit_report(query)


@router.get("/production", dependencies=[Depends(ANY_ROLE)])
async def production_report(
    query: ProductionReportQuery = Depends(parse_production_query),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    return await service.get_production_report(query)


@router.get("/dashboard", dependencies=[Depends(ANY_ROLE)])
async def dashboard_overview(
    query: DashboardQuery = Depends(parse_dashboard_query),
    user: User = Depends(ANY_ROLE),
    service: ReportService = Depends(get_report_service),
) -> dict[str, Any]:
    return await service.get_dashboard(query, user)


@router.get("/pdf")
async def report_pdf(
    query: ReportExportQuery = Depends(parse_export_query),
    user: User = Depends(ANY_ROLE),
    service: ReportService = Depends(get_report_service),
) -> Response:
    if query.report_type == "profit" and user.role != "admin":
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "Access denied: Requires one of [admin] role",
        )

    content, filename = await service.generate_report_pdf(query, user)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
