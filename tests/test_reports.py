from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_buffalo_service,
    get_production_service,
    get_report_repository,
    get_security_audit_service,
    get_stock_service,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.schemas.report import (
    DashboardQuery,
    ProductionReportQuery,
    ProfitReportQuery,
    ReportExportQuery,
)
from app.services.production_service import ProductionService
from app.services.report_service import ReportService, resolve_date_range
from app.utils.report_pdf import build_report_pdf
from app.utils.time import get_business_date
from tests.audit_helpers import FakeAuditService

CREATED = datetime(2026, 10, 28, 12, 10, 23, 123000)
TODAY = get_business_date()


def make_user(
    user_id: int = 1,
    *,
    role: str = "admin",
    username: str = "admin",
) -> User:
    return User(
        id=user_id,
        full_name="System Admin" if role == "admin" else "Ramesh Patel",
        username=username,
        email=f"{username}@example.com",
        password_hash="not-used",
        role=role,
        is_active=True,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


class FakeReportRepository:
    def __init__(self) -> None:
        self.sales: list[tuple[date, Decimal, Decimal]] = []
        self.expenses: list[tuple[date, Decimal, str | None]] = []
        self.production: list[tuple[str, Decimal]] = []
        self.sales_today: tuple[int, Decimal, Decimal] = (
            0,
            Decimal("0"),
            Decimal("0"),
        )
        self.sales_totals: dict[tuple[str, str], Decimal] = {}
        self.expense_totals: dict[tuple[str, str], Decimal] = {}
        self.expense_totals_calls: list[tuple[str, str]] = []

    async def sales_in_range(
        self,
        from_date: date,
        to_date: date,
    ) -> list[tuple[date, Decimal, Decimal]]:
        return [
            row
            for row in self.sales
            if from_date <= row[0] <= to_date
        ]

    async def expense_rows_in_range(
        self,
        from_date: date,
        to_date: date,
    ) -> list[tuple[date, Decimal, str | None]]:
        return [
            row
            for row in self.expenses
            if from_date <= row[0] <= to_date
        ]

    async def sales_totals_for_date(
        self,
        sale_date: date,
    ) -> tuple[int, Decimal, Decimal]:
        return self.sales_today

    async def sales_amount_total(
        self,
        from_date: date,
        to_date: date,
    ) -> Decimal:
        return self.sales_totals.get(
            (from_date.isoformat(), to_date.isoformat()),
            Decimal("0"),
        )

    async def expense_amount_total(
        self,
        from_date: date,
        to_date: date,
    ) -> Decimal:
        key = (from_date.isoformat(), to_date.isoformat())
        self.expense_totals_calls.append(key)
        return self.expense_totals.get(key, Decimal("0"))

    async def production_totals_for_date(
        self,
        prod_date: date,
    ) -> list[tuple[str, Decimal]]:
        return self.production


class FakeBuffaloService:
    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self.counts = counts or {
            "total": 6,
            "active": 5,
            "dry": 1,
            "sold": 0,
            "dead": 0,
        }

    async def get_counts(self) -> dict[str, int]:
        return dict(self.counts)


class FakeStockService:
    async def get_stock_for_date(self, raw_date: str | None = None) -> dict[str, str]:
        return {
            "date": raw_date,
            "opening_stock": "1.00",
            "produced": "10.00",
            "sold": "5.00",
            "wasted": "0.00",
            "closing_stock": "6.00",
        }


class FakeProductionRepository:
    def __init__(self) -> None:
        self.rows: list[tuple[date, str, Decimal]] = []

    async def aggregated_totals(
        self,
        from_date: date,
        to_date: date,
    ) -> list[tuple[date, str, Decimal]]:
        return [
            row
            for row in self.rows
            if from_date <= row[0] <= to_date
        ]


class FakeSession:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def get(self, model: type[User], user_id: int) -> User | None:
        if model is User:
            return self.users.get(user_id)
        return None


def build_profit_repository() -> FakeReportRepository:
    repository = FakeReportRepository()
    repository.sales = [
        (date(2026, 10, 5), Decimal("500.00"), Decimal("10.00")),
        (date(2026, 10, 5), Decimal("250.00"), Decimal("5.00")),
        (date(2026, 10, 7), Decimal("1250.00"), Decimal("25.00")),
    ]
    repository.expenses = [
        (date(2026, 10, 5), Decimal("300.00"), "feed"),
        (date(2026, 10, 6), Decimal("100.00"), "fuel"),
        (date(2026, 10, 5), Decimal("100.00"), "feed"),
    ]
    return repository


class FakeBuffaloRepository:
    async def get_by_id(self, buffalo_id: int):
        return None


def build_production_service(rows: list[tuple[date, str, Decimal]] | None = None):
    repository = FakeProductionRepository()
    repository.rows = rows or []
    return ProductionService(  # type: ignore[arg-type]
        repository,
        FakeBuffaloRepository(),
    )


def build_report_service(
    repository: FakeReportRepository | None = None,
    counts: dict[str, int] | None = None,
    production_rows: list[tuple[date, str, Decimal]] | None = None,
    audit: FakeAuditService | None = None,
) -> ReportService:
    return ReportService(
        repository or FakeReportRepository(),  # type: ignore[arg-type]
        FakeBuffaloService(counts),  # type: ignore[arg-type]
        build_production_service(production_rows),  # type: ignore[arg-type]
        FakeStockService(),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
    )


class DateRangeTests(unittest.TestCase):
    def test_date_takes_precedence(self) -> None:
        resolved = resolve_date_range(
            ProfitReportQuery(
                period="monthly",
                date="2026-10-09",
                month="2026-08",
                from_date="2026-01-01",
                to_date="2026-01-31",
            )
        )
        self.assertEqual(resolved, ("2026-10-09", "2026-10-09"))

    def test_month_uses_calendar_bounds(self) -> None:
        self.assertEqual(
            resolve_date_range(ProfitReportQuery(month="2026-02")),
            ("2026-02-01", "2026-02-28"),
        )
        self.assertEqual(
            resolve_date_range(ProfitReportQuery(month="2024-02")),
            ("2024-02-01", "2024-02-29"),
        )

    def test_from_to_range(self) -> None:
        self.assertEqual(
            resolve_date_range(
                ProfitReportQuery(from_date="2026-10-01", to_date="2026-10-31")
            ),
            ("2026-10-01", "2026-10-31"),
        )

    def test_invalid_range(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            resolve_date_range(
                ProfitReportQuery(from_date="2026-10-31", to_date="2026-10-01")
            )
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail["code"], "INVALID_DATE_RANGE")

    def test_defaults_to_current_month(self) -> None:
        period_from, period_to = resolve_date_range(ProfitReportQuery())
        self.assertEqual(period_from, f"{TODAY[:7]}-01")
        self.assertEqual(period_to[:7], TODAY[:7])

    def test_one_sided_range_falls_back_to_current_month(self) -> None:
        period_from, _ = resolve_date_range(
            ProfitReportQuery(from_date="2026-01-01")
        )
        self.assertEqual(period_from, f"{TODAY[:7]}-01")


class ProfitReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = build_profit_repository()
        self.service = build_report_service(self.repository)

    async def test_month_report(self) -> None:
        report = await self.service.get_profit_report(
            ProfitReportQuery(month="2026-10")
        )
        self.assertEqual(report["period"], {"from": "2026-10-01", "to": "2026-10-31"})
        self.assertEqual(
            report["summary"],
            {
                "total_revenue": "2000.00",
                "total_expenses": "500.00",
                "net_profit": "1500.00",
                "total_litres_sold": "40.00",
            },
        )
        self.assertEqual(
            report["daily_breakdown"],
            [
                {
                    "date": "2026-10-05",
                    "revenue": "750.00",
                    "expenses": "400.00",
                    "profit": "350.00",
                    "litres_sold": "15.00",
                },
                {
                    "date": "2026-10-06",
                    "revenue": "0.00",
                    "expenses": "100.00",
                    "profit": "-100.00",
                    "litres_sold": "0.00",
                },
                {
                    "date": "2026-10-07",
                    "revenue": "1250.00",
                    "expenses": "0.00",
                    "profit": "1250.00",
                    "litres_sold": "25.00",
                },
            ],
        )
        self.assertEqual(
            report["category_breakdown"],
            [
                {
                    "category": "feed",
                    "total_amount": "400.00",
                    "percentage": "80.0%",
                },
                {
                    "category": "fuel",
                    "total_amount": "100.00",
                    "percentage": "20.0%",
                },
            ],
        )

    async def test_single_day_report(self) -> None:
        report = await self.service.get_profit_report(
            ProfitReportQuery(date="2026-10-05")
        )
        self.assertEqual(report["period"], {"from": "2026-10-05", "to": "2026-10-05"})
        self.assertEqual(report["summary"]["total_revenue"], "750.00")
        self.assertEqual(report["summary"]["net_profit"], "350.00")
        self.assertEqual(len(report["daily_breakdown"]), 1)

    async def test_uncategorized_expenses(self) -> None:
        self.repository.expenses.append(
            (date(2026, 10, 8), Decimal("50.00"), None)
        )
        report = await self.service.get_profit_report(
            ProfitReportQuery(month="2026-10")
        )
        categories = [row["category"] for row in report["category_breakdown"]]
        self.assertIn("uncategorized", categories)
        self.assertEqual(report["summary"]["total_expenses"], "550.00")

    async def test_empty_period(self) -> None:
        report = await self.service.get_profit_report(
            ProfitReportQuery(month="2025-01")
        )
        self.assertEqual(report["summary"]["total_revenue"], "0.00")
        self.assertEqual(report["summary"]["net_profit"], "0.00")
        self.assertEqual(report["daily_breakdown"], [])
        self.assertEqual(report["category_breakdown"], [])


class ProductionReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service = build_report_service(
            production_rows=[
                (date(2026, 10, 1), "morning", Decimal("10.00")),
                (date(2026, 10, 1), "evening", Decimal("5.00")),
                (date(2026, 10, 2), "morning", Decimal("8.00")),
            ]
        )

    async def test_summary_delegation(self) -> None:
        report = await self.service.get_production_report(
            ProductionReportQuery(from_date="2026-10-01", to_date="2026-10-02")
        )
        self.assertEqual(report["days_recorded"], 2)
        self.assertEqual(report["grand_total_litres"], "23.00")
        self.assertEqual(report["average_daily_litres"], "11.50")
        self.assertEqual(
            report["daily_summaries"],
            [
                {
                    "prod_date": "2026-10-01",
                    "morning_litres": "10.00",
                    "evening_litres": "5.00",
                    "total_litres": "15.00",
                },
                {
                    "prod_date": "2026-10-02",
                    "morning_litres": "8.00",
                    "evening_litres": "0.00",
                    "total_litres": "8.00",
                },
            ],
        )

    async def test_missing_dates_returns_empty_summary(self) -> None:
        report = await self.service.get_production_report(ProductionReportQuery())
        self.assertEqual(report["days_recorded"], 0)
        self.assertEqual(report["grand_total_litres"], "0.00")
        self.assertEqual(report["daily_summaries"], [])

    async def test_invalid_range(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.get_production_report(
                ProductionReportQuery(
                    from_date="2026-10-31",
                    to_date="2026-10-01",
                )
            )
        self.assertEqual(caught.exception.detail["code"], "INVALID_DATE_RANGE")


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeReportRepository()
        self.repository.production = [
            ("morning", Decimal("10.00")),
            ("evening", Decimal("5.50")),
        ]
        self.repository.sales_today = (
            3,
            Decimal("12.50"),
            Decimal("625.00"),
        )
        self.repository.sales_totals[("2026-10-01", "2026-10-29")] = Decimal(
            "5000.00"
        )
        self.repository.expense_totals[("2026-10-29", "2026-10-29")] = Decimal(
            "75.00"
        )
        self.repository.expense_totals[("2026-10-01", "2026-10-29")] = Decimal(
            "400.00"
        )
        self.service = build_report_service(self.repository)
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")

    async def test_admin_dashboard(self) -> None:
        report = await self.service.get_dashboard(
            DashboardQuery(date="2026-10-29"),
            self.admin,
        )
        self.assertEqual(report["date"], "2026-10-29")
        self.assertEqual(
            report["buffaloes"],
            {"active": 5, "sold": 0, "dry": 1, "dead": 0, "total": 6},
        )
        self.assertEqual(
            report["production"],
            {
                "date": "2026-10-29",
                "morning_litres": "10.00",
                "evening_litres": "5.50",
                "grand_total_litres": "15.50",
            },
        )
        self.assertEqual(report["stock"]["closing_stock"], "6.00")
        self.assertEqual(
            report["sales"], {"sales_count": 3, "litres_sold": "12.50"}
        )
        self.assertEqual(
            report["financials"],
            {
                "today": {
                    "revenue": "625.00",
                    "expenses": "75.00",
                    "profit": "550.00",
                },
                "month_to_date": {
                    "from": "2026-10-01",
                    "to": "2026-10-29",
                    "revenue": "5000.00",
                    "expenses": "400.00",
                    "profit": "4600.00",
                },
            },
        )

    async def test_operator_dashboard_has_no_financials(self) -> None:
        report = await self.service.get_dashboard(
            DashboardQuery(date="2026-10-29"),
            self.operator,
        )
        self.assertIsNone(report["financials"])
        self.assertEqual(self.repository.expense_totals_calls, [])
        self.assertEqual(report["sales"]["sales_count"], 3)

    async def test_defaults_to_business_date(self) -> None:
        report = await self.service.get_dashboard(DashboardQuery(), self.operator)
        self.assertEqual(report["date"], TODAY)


class ReportPdfTests(unittest.IsolatedAsyncioTestCase):
    async def test_profit_report_pdf(self) -> None:
        service = build_report_service(build_profit_repository())
        admin = make_user()
        content, filename = await service.generate_report_pdf(
            ReportExportQuery(report_type="profit", month="2026-10"),
            admin,
        )
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content), 2000)
        self.assertTrue(content.rstrip().endswith(b"%%EOF"))
        self.assertEqual(
            filename,
            "dairy-profit-report-2026-10-01_to_2026-10-31.pdf",
        )

    async def test_production_report_pdf(self) -> None:
        service = build_report_service(
            production_rows=[
                (date(2026, 10, 1), "morning", Decimal("10.00")),
                (date(2026, 10, 1), "evening", Decimal("5.00")),
                (date(2026, 10, 2), "morning", Decimal("8.00")),
            ]
        )
        operator = make_user(2, role="operator", username="ramesh_operator")
        content, filename = await service.generate_report_pdf(
            ReportExportQuery(
                report_type="production",
                from_date="2026-10-01",
                to_date="2026-10-02",
            ),
            operator,
        )
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content), 1500)
        self.assertTrue(content.rstrip().endswith(b"%%EOF"))
        self.assertEqual(
            filename,
            "dairy-production-report-2026-10-01_to_2026-10-02.pdf",
        )

    async def test_dashboard_report_pdf(self) -> None:
        repository = FakeReportRepository()
        repository.production = [
            ("morning", Decimal("10.00")),
            ("evening", Decimal("5.50")),
        ]
        repository.sales_today = (
            3,
            Decimal("12.50"),
            Decimal("625.00"),
        )
        service = build_report_service(repository)
        admin = make_user()
        content, filename = await service.generate_report_pdf(
            ReportExportQuery(report_type="dashboard", date="2026-10-29"),
            admin,
        )
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content), 1200)
        self.assertEqual(filename, "dairy-dashboard-report-2026-10-29.pdf")

    async def test_report_export_audit_event(self) -> None:
        audit = FakeAuditService()
        service = build_report_service(
            build_profit_repository(),
            audit=audit,
        )
        await service.generate_report_pdf(
            ReportExportQuery(report_type="profit", month="2026-10"),
            make_user(),
        )
        event = audit.standalone_records[-1]
        self.assertEqual(event["event_type"], "report.exported")
        self.assertEqual(event["metadata"]["report_type"], "profit")
        self.assertEqual(event["metadata"]["period_start"], "2026-10-01")
        self.assertEqual(event["metadata"]["period_end"], "2026-10-31")

    async def test_production_pdf_without_data_still_builds(self) -> None:
        service = build_report_service()
        content, _ = await service.generate_report_pdf(
            ReportExportQuery(
                report_type="production",
                from_date="2025-01-01",
                to_date="2025-01-31",
            ),
            make_user(),
        )
        self.assertTrue(content.startswith(b"%PDF-"))

    def test_empty_period_pdf_states_no_data(self) -> None:
        report = {
            "period": {"from": "2025-01-01", "to": "2025-01-31"},
            "summary": {
                "total_revenue": "0.00",
                "total_expenses": "0.00",
                "net_profit": "0.00",
                "total_litres_sold": "0.00",
            },
            "category_breakdown": [],
            "daily_breakdown": [],
        }
        content = build_report_pdf(
            report_type="profit",
            report=report,
            period_from="2025-01-01",
            period_to="2025-01-31",
            generated_at=datetime(2026, 10, 29, 14, 5),
            prepared_by="System Admin (admin)",
            compress=False,
        )
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertIn(b"No data", content)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = build_profit_repository()
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")

        self.audit = FakeAuditService()

        async def override_get_db():
            yield FakeSession(self.admin, self.operator)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit
        app.dependency_overrides[get_report_repository] = lambda: self.repository
        app.dependency_overrides[get_buffalo_service] = lambda: FakeBuffaloService()
        app.dependency_overrides[get_stock_service] = lambda: FakeStockService()
        app.dependency_overrides[get_production_service] = (
            lambda: build_production_service()
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self, user: User | None = None) -> dict[str, str]:
        target = user or self.admin
        token = create_access_token(
            user_id=target.id,
            email=target.email,
            username=target.username,
            role=target.role,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}=test-session",
        }

    async def test_profit_report_is_admin_only(self) -> None:
        forbidden = await self.client.get(
            "/api/v1/reports/profit?month=2026-10",
            headers=self._auth(self.operator),
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(
            forbidden.json()["error"]["message"],
            "Access denied: Requires one of [admin] role",
        )

        response = await self.client.get(
            "/api/v1/reports/profit?month=2026-10",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["period"], {"from": "2026-10-01", "to": "2026-10-31"})
        self.assertEqual(body["summary"]["net_profit"], "1500.00")
        self.assertEqual(len(body["daily_breakdown"]), 3)

        unauthenticated = await self.client.get("/api/v1/reports/profit")
        self.assertEqual(unauthenticated.status_code, 401)

    async def test_dashboard_roles(self) -> None:
        response = await self.client.get(
            "/api/v1/reports/dashboard?date=2026-10-29",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["financials"])
        self.assertEqual(response.json()["date"], "2026-10-29")

        admin_response = await self.client.get(
            "/api/v1/reports/dashboard?date=2026-10-29",
            headers=self._auth(),
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertIsNotNone(admin_response.json()["financials"])

    async def test_production_report(self) -> None:
        response = await self.client.get(
            "/api/v1/reports/production?from=2026-10-01&to=2026-10-02",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["days_recorded"], 0)
        self.assertEqual(
            response.json()["period"], {"from": "2026-10-01", "to": "2026-10-02"}
        )

    async def test_validation_messages(self) -> None:
        cases = [
            (
                "/api/v1/reports/profit?from=bad",
                "from: from must be in 'YYYY-MM-DD' format",
            ),
            (
                "/api/v1/reports/profit?to=bad",
                "to: to must be in 'YYYY-MM-DD' format",
            ),
            (
                "/api/v1/reports/profit?month=2026-1",
                "month: month must be in 'YYYY-MM' format",
            ),
            (
                "/api/v1/reports/profit?period=weekly",
                'period: Invalid option: expected one of '
                '"daily"|"monthly"|"custom"',
            ),
            (
                "/api/v1/reports/dashboard?date=bad",
                "date: date must be in 'YYYY-MM-DD' format",
            ),
            (
                "/api/v1/reports/production?from=bad",
                "from: from must be in 'YYYY-MM-DD' format",
            ),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                response = await self.client.get(url, headers=self._auth())
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"], expected
                )

    async def test_invalid_range(self) -> None:
        response = await self.client.get(
            "/api/v1/reports/profit?from=2026-10-31&to=2026-10-01",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"], "INVALID_DATE_RANGE"
        )

    async def test_report_pdf_download(self) -> None:
        response = await self.client.get(
            "/api/v1/reports/pdf?type=profit&month=2026-10",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn(
            "dairy-profit-report-2026-10-01_to_2026-10-31.pdf",
            response.headers["content-disposition"],
        )
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertGreater(len(response.content), 2000)

    async def test_report_pdf_roles_and_validation(self) -> None:
        forbidden = await self.client.get(
            "/api/v1/reports/pdf?type=profit&month=2026-10",
            headers=self._auth(self.operator),
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(
            forbidden.json()["error"]["message"],
            "Access denied: Requires one of [admin] role",
        )

        production = await self.client.get(
            "/api/v1/reports/pdf?type=production&from=2026-10-01&to=2026-10-02",
            headers=self._auth(self.operator),
        )
        self.assertEqual(production.status_code, 200)
        self.assertTrue(production.content.startswith(b"%PDF-"))

        dashboard = await self.client.get(
            "/api/v1/reports/pdf?type=dashboard&date=2026-10-29",
            headers=self._auth(self.operator),
        )
        self.assertEqual(dashboard.status_code, 200)

        bad_type = await self.client.get(
            "/api/v1/reports/pdf?type=weekly",
            headers=self._auth(),
        )
        self.assertEqual(bad_type.status_code, 400)
        self.assertEqual(
            bad_type.json()["error"]["message"],
            'type: Invalid option: expected one of '
            '"profit"|"production"|"dashboard"',
        )

        bad_date = await self.client.get(
            "/api/v1/reports/pdf?type=profit&from=bad",
            headers=self._auth(),
        )
        self.assertEqual(bad_date.status_code, 400)

        unauthenticated = await self.client.get(
            "/api/v1/reports/pdf?type=production"
        )
        self.assertEqual(unauthenticated.status_code, 401)


if __name__ == "__main__":
    unittest.main()
