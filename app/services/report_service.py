from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.models.user import User
from app.repositories.report_repository import ReportRepository
from app.schemas.report import (
    DashboardQuery,
    ProductionReportQuery,
    ProfitReportQuery,
    ReportExportQuery,
)
from app.services.buffalo_service import BuffaloService
from app.services.production_service import ProductionService
from app.services.stock_service import StockService
from app.utils.report_pdf import build_report_pdf, report_filename
from app.utils.time import business_now, get_business_date


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _money(value: Any) -> str:
    return f"{_decimal(value):.2f}"


def _month_bounds(month: str) -> tuple[str, str]:
    year = int(month[:4])
    month_number = int(month[5:7])
    last_day = calendar.monthrange(year, month_number)[1]
    return f"{month}-01", f"{month}-{last_day:02d}"


def resolve_date_range(query: ProfitReportQuery) -> tuple[str, str]:
    if query.date:
        return query.date, query.date

    if query.month:
        return _month_bounds(query.month)

    if query.from_date and query.to_date:
        if query.from_date > query.to_date:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_DATE_RANGE",
                "'from' date cannot be after 'to' date",
            )
        return query.from_date, query.to_date

    return _month_bounds(get_business_date()[:7])


class ReportService:
    def __init__(
        self,
        repository: ReportRepository,
        buffalo_service: BuffaloService,
        production_service: ProductionService,
        stock_service: StockService,
    ) -> None:
        self.repository = repository
        self.buffalo_service = buffalo_service
        self.production_service = production_service
        self.stock_service = stock_service

    async def get_profit_report(
        self,
        query: ProfitReportQuery,
    ) -> dict[str, Any]:
        period_from, period_to = resolve_date_range(query)
        start = date.fromisoformat(period_from)
        end = date.fromisoformat(period_to)

        sales = await self.repository.sales_in_range(start, end)
        expenses = await self.repository.expense_rows_in_range(start, end)

        daily: dict[str, dict[str, Decimal]] = {}
        total_revenue = Decimal("0")
        total_litres = Decimal("0")

        for sale_date, amount, litres in sales:
            key = sale_date.isoformat()
            day = daily.setdefault(
                key,
                {
                    "revenue": Decimal("0"),
                    "expenses": Decimal("0"),
                    "litres_sold": Decimal("0"),
                },
            )
            sale_amount = _decimal(amount)
            sale_litres = _decimal(litres)
            day["revenue"] += sale_amount
            day["litres_sold"] += sale_litres
            total_revenue += sale_amount
            total_litres += sale_litres

        categories: dict[str, Decimal] = {}
        total_expenses = Decimal("0")

        for expense_date, amount, category_name in expenses:
            key = expense_date.isoformat()
            day = daily.setdefault(
                key,
                {
                    "revenue": Decimal("0"),
                    "expenses": Decimal("0"),
                    "litres_sold": Decimal("0"),
                },
            )
            expense_amount = _decimal(amount)
            day["expenses"] += expense_amount
            total_expenses += expense_amount
            name = category_name or "uncategorized"
            categories[name] = categories.get(name, Decimal("0")) + expense_amount

        daily_breakdown = [
            {
                "date": key,
                "revenue": _money(day["revenue"]),
                "expenses": _money(day["expenses"]),
                "profit": _money(day["revenue"] - day["expenses"]),
                "litres_sold": _money(day["litres_sold"]),
            }
            for key, day in sorted(daily.items())
        ]

        category_breakdown = []
        for name, amount in categories.items():
            if total_expenses > 0:
                percentage = f"{(amount / total_expenses * 100):.1f}%"
            else:
                percentage = "0.0%"
            category_breakdown.append(
                {
                    "category": name,
                    "total_amount": _money(amount),
                    "percentage": percentage,
                }
            )

        return {
            "period": {"from": period_from, "to": period_to},
            "summary": {
                "total_revenue": _money(total_revenue),
                "total_expenses": _money(total_expenses),
                "net_profit": _money(total_revenue - total_expenses),
                "total_litres_sold": _money(total_litres),
            },
            "category_breakdown": category_breakdown,
            "daily_breakdown": daily_breakdown,
        }

    async def generate_report_pdf(
        self,
        query: ReportExportQuery,
        user: User,
    ) -> tuple[bytes, str]:
        """Build a downloadable analytical PDF for the requested report type.

        The report payload is produced by the same methods the JSON endpoints
        use, so the PDF can never drift from the API numbers.
        """
        report_type = query.report_type
        if report_type == "profit":
            profit_query = ProfitReportQuery(
                from_date=query.from_date,
                to_date=query.to_date,
                month=query.month,
                date=query.date,
            )
            period_from, period_to = resolve_date_range(profit_query)
            report = await self.get_profit_report(profit_query)
        elif report_type == "production":
            period_from, period_to = resolve_date_range(
                ProfitReportQuery(
                    from_date=query.from_date,
                    to_date=query.to_date,
                    month=query.month,
                    date=query.date,
                )
            )
            report = await self.get_production_report(
                ProductionReportQuery(
                    from_date=period_from,
                    to_date=period_to,
                )
            )
        else:
            business_date = query.date or get_business_date()
            period_from = business_date
            period_to = business_date
            report = await self.get_dashboard(
                DashboardQuery(date=business_date),
                user,
            )

        prepared_by = f"{user.full_name} ({user.role})"
        content = build_report_pdf(
            report_type=report_type,
            report=report,
            period_from=period_from,
            period_to=period_to,
            generated_at=business_now(),
            prepared_by=prepared_by,
        )
        return content, report_filename(report_type, period_from, period_to)

    async def get_production_report(
        self,
        query: ProductionReportQuery,
    ) -> dict[str, Any]:
        period_from = query.from_date
        period_to = query.to_date
        if period_from is None or period_to is None:
            return {
                "period": {"from": period_from, "to": period_to},
                "days_recorded": 0,
                "grand_total_litres": "0.00",
                "average_daily_litres": "0.00",
                "daily_summaries": [],
            }
        return await self.production_service.get_summary(period_from, period_to)

    async def get_dashboard(
        self,
        query: DashboardQuery,
        user: User,
    ) -> dict[str, Any]:
        business_date = query.date or get_business_date()
        report_date = date.fromisoformat(business_date)

        counts = await self.buffalo_service.get_counts()
        buffaloes = {
            "active": counts.get("active", 0),
            "sold": counts.get("sold", 0),
            "dry": counts.get("dry", 0),
            "dead": counts.get("dead", 0),
            "total": counts.get("total", 0),
        }

        morning = Decimal("0")
        evening = Decimal("0")
        for session_name, litres in await self.repository.production_totals_for_date(
            report_date
        ):
            if session_name == "morning":
                morning += _decimal(litres)
            elif session_name == "evening":
                evening += _decimal(litres)

        production = {
            "date": business_date,
            "morning_litres": _money(morning),
            "evening_litres": _money(evening),
            "grand_total_litres": _money(morning + evening),
        }

        stock = await self.stock_service.get_stock_for_date(business_date)

        sales_count, litres_sold, revenue = (
            await self.repository.sales_totals_for_date(report_date)
        )
        sales = {
            "sales_count": sales_count,
            "litres_sold": _money(litres_sold),
        }

        financials: dict[str, Any] | None = None
        if user.role == "admin":
            month_start = f"{business_date[:7]}-01"
            today_expenses = await self.repository.expense_amount_total(
                report_date,
                report_date,
            )
            month_revenue = await self.repository.sales_amount_total(
                date.fromisoformat(month_start),
                report_date,
            )
            month_expenses = await self.repository.expense_amount_total(
                date.fromisoformat(month_start),
                report_date,
            )
            financials = {
                "today": {
                    "revenue": _money(revenue),
                    "expenses": _money(today_expenses),
                    "profit": _money(_decimal(revenue) - today_expenses),
                },
                "month_to_date": {
                    "from": month_start,
                    "to": business_date,
                    "revenue": _money(month_revenue),
                    "expenses": _money(month_expenses),
                    "profit": _money(month_revenue - month_expenses),
                },
            }

        return {
            "date": business_date,
            "buffaloes": buffaloes,
            "production": production,
            "stock": stock,
            "sales": sales,
            "financials": financials,
        }
