from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_security_audit_service,
    get_stock_repository,
    get_wastage_repository,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.milk_wastage import MilkWastage
from app.models.user import User
from app.schemas.wastage import RecordWastageRequest
from app.services.stock_service import StockService
from app.services.wastage_service import WastageService
from app.utils.time import get_business_date
from tests.audit_helpers import FakeAuditService

CREATED = datetime(2026, 10, 28, 12, 10, 23, 123000)


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


class FakeStockRepository:
    def __init__(self) -> None:
        self.production: list[tuple[date, Decimal]] = []
        self.sales: list[tuple[date, Decimal]] = []
        self.wastage: list[tuple[date, Decimal]] = []

    async def _sum(
        self,
        values: list[tuple[date, Decimal]],
        stock_date: date,
        *,
        before: bool,
    ) -> Decimal:
        return sum(
            (
                value
                for entry_date, value in values
                if (entry_date < stock_date if before else entry_date == stock_date)
            ),
            Decimal("0"),
        )

    async def sum_prior_quantities(
        self,
        stock_date: date,
    ) -> tuple[Decimal, Decimal, Decimal]:
        return (
            await self._sum(self.production, stock_date, before=True),
            await self._sum(self.sales, stock_date, before=True),
            await self._sum(self.wastage, stock_date, before=True),
        )

    async def sum_current_quantities(
        self,
        stock_date: date,
    ) -> tuple[Decimal, Decimal, Decimal]:
        return (
            await self._sum(self.production, stock_date, before=False),
            await self._sum(self.sales, stock_date, before=False),
            await self._sum(self.wastage, stock_date, before=False),
        )

    async def get_future_active_dates(self, stock_date: date) -> list[date]:
        dates = {
            entry_date
            for collection in (self.production, self.sales, self.wastage)
            for entry_date, _ in collection
            if entry_date > stock_date
        }
        return sorted(dates)


class FakeWastageRepository:
    def __init__(self, stock_repository: FakeStockRepository) -> None:
        self.stock_repository = stock_repository
        self.records: list[MilkWastage] = []
        self.recorder = make_user(2, role="operator", username="ramesh_operator")
        self.commits = 0
        self.rollbacks = 0

    async def create(
        self,
        *,
        waste_date: date,
        litres: Decimal,
        reason: str,
        recorded_by: int,
    ) -> MilkWastage:
        record = MilkWastage(
            id=len(self.records) + 1,
            waste_date=waste_date,
            litres=litres,
            reason=reason,
            recorded_by=recorded_by,
            is_deleted=False,
            created_at=CREATED + timedelta(minutes=len(self.records)),
            updated_at=CREATED + timedelta(minutes=len(self.records)),
        )
        record.recorder = self.recorder
        self.records.append(record)
        self.stock_repository.wastage.append((waste_date, litres))
        return record

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        waste_date: date | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        reason: str | None = None,
    ) -> tuple[int, list[MilkWastage]]:
        rows = [record for record in self.records if not record.is_deleted]
        if waste_date is not None:
            rows = [record for record in rows if record.waste_date == waste_date]
        elif from_date is not None and to_date is not None:
            rows = [
                record
                for record in rows
                if from_date <= record.waste_date <= to_date
            ]
        elif from_date is not None:
            rows = [record for record in rows if record.waste_date >= from_date]
        elif to_date is not None:
            rows = [record for record in rows if record.waste_date <= to_date]
        if reason is not None:
            rows = [record for record in rows if record.reason == reason]
        rows.sort(
            key=lambda record: (record.waste_date, record.created_at),
            reverse=True,
        )
        total = len(rows)
        start = (page - 1) * page_size
        return total, rows[start : start + page_size]

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSession:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def get(self, model: type[User], user_id: int) -> User | None:
        if model is User:
            return self.users.get(user_id)
        return None


class SchemaTests(unittest.TestCase):
    def test_valid_payload(self) -> None:
        payload = RecordWastageRequest.model_validate(
            {
                "waste_date": "2024-01-11",
                "litres": "2.5",
                "reason": "spilled",
            }
        )
        self.assertEqual(payload.litres, 2.5)
        self.assertEqual(payload.reason, "spilled")

    def test_missing_fields(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            RecordWastageRequest.model_validate({})
        self.assertEqual(
            [(error["loc"], error["type"]) for error in caught.exception.errors()],
            [
                (("waste_date",), "missing"),
                (("litres",), "missing"),
                (("reason",), "missing"),
            ],
        )

    def test_invalid_values(self) -> None:
        cases = [
            (
                {
                    "waste_date": "11-01-2024",
                    "litres": 1,
                    "reason": "spoiled",
                },
                "Waste date must be in YYYY-MM-DD format",
            ),
            (
                {
                    "waste_date": "2024-01-11",
                    "litres": 0,
                    "reason": "spoiled",
                },
                "Litres must be greater than zero",
            ),
            (
                {
                    "waste_date": "2024-01-11",
                    "litres": 1,
                    "reason": "expired",
                },
                'Invalid option: expected one of "spoiled"|"spilled"|"returned"',
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError) as caught:
                    RecordWastageRequest.model_validate(payload)
                self.assertIn(expected, str(caught.exception))


class StockServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = FakeStockRepository()
        self.service = StockService(self.repository)  # type: ignore[arg-type]

    async def test_worked_example(self) -> None:
        self.repository.production.extend(
            [
                (date(2024, 1, 10), Decimal("20.00")),
                (date(2024, 1, 11), Decimal("16.50")),
                (date(2024, 1, 11), Decimal("15.00")),
            ]
        )
        self.repository.sales.append((date(2024, 1, 11), Decimal("40.00")))
        self.repository.wastage.append((date(2024, 1, 11), Decimal("2.00")))

        stock = await self.service.get_stock_for_date("2024-01-11")
        self.assertEqual(
            stock,
            {
                "date": "2024-01-11",
                "opening_stock": "20.00",
                "produced": "31.50",
                "sold": "40.00",
                "wasted": "2.00",
                "closing_stock": "9.50",
            },
        )

    async def test_current_and_future_insufficient(self) -> None:
        self.repository.production.append((date(2024, 1, 10), Decimal("100")))
        self.repository.sales.append((date(2024, 1, 11), Decimal("95")))

        with self.assertRaises(HTTPException) as caught:
            await self.service.assert_available_stock("2024-01-10", 200)
        self.assertEqual(caught.exception.detail["code"], "STOCK_INSUFFICIENT")
        self.assertEqual(caught.exception.detail["message"], "Only 100.00 L available")

        with self.assertRaises(HTTPException) as caught:
            await self.service.assert_available_stock("2024-01-10", 10)
        self.assertEqual(
            caught.exception.detail["message"],
            "Insufficient stock: Deducting 10.00 L on 2024-01-10 would "
            "result in negative closing stock on 2024-01-11 "
            "(only 5.00 L margin)",
        )

    async def test_invalid_quantity_and_history_range(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.assert_available_stock("2024-01-10", 0)
        self.assertEqual(caught.exception.detail["code"], "INVALID_QUANTITY")

        with self.assertRaises(HTTPException) as caught:
            await self.service.get_stock_history("2024-01-12", "2024-01-10")
        self.assertEqual(caught.exception.detail["code"], "INVALID_DATE_RANGE")


class WastageServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")
        self.stock_repository = FakeStockRepository()
        self.wastage_repository = FakeWastageRepository(self.stock_repository)
        self.stock_service = StockService(self.stock_repository)  # type: ignore[arg-type]
        self.service = WastageService(
            self.wastage_repository,  # type: ignore[arg-type]
            self.stock_service,
        )

    async def test_record_and_list(self) -> None:
        today = get_business_date()
        self.stock_repository.production.append(
            (date.fromisoformat(today), Decimal("15.00"))
        )
        payload = RecordWastageRequest.model_validate(
            {"waste_date": today, "litres": 2.5, "reason": "spoiled"}
        )
        result = await self.service.record_wastage(payload, self.operator)
        self.assertEqual(result["wastage"]["litres"], "2.50")
        self.assertEqual(result["stock_remaining"], "12.50")
        self.assertEqual(self.wastage_repository.commits, 1)

        from app.schemas.wastage import WastageQuery

        listing = await self.service.list_wastage(
            WastageQuery(page=1, page_size=10, reason="spoiled")
        )
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["recorder"]["username"], "ramesh_operator")

    async def test_wastage_audit_event(self) -> None:
        today = get_business_date()
        self.stock_repository.production.append(
            (date.fromisoformat(today), Decimal("15.00"))
        )
        audit = FakeAuditService()
        service = WastageService(  # type: ignore[arg-type]
            self.wastage_repository,
            self.stock_service,
            audit=audit,
        )
        payload = RecordWastageRequest.model_validate(
            {"waste_date": today, "litres": 2.5, "reason": "spoiled"}
        )
        await service.record_wastage(payload, self.operator)
        event = audit.records[-1]
        self.assertEqual(event["event_type"], "wastage.recorded")
        self.assertEqual(event["metadata"]["waste_date"], today)
        self.assertEqual(event["metadata"]["reason"], "spoiled")

    async def test_permissions_and_quantity(self) -> None:
        payload = RecordWastageRequest.model_validate(
            {"waste_date": "2099-01-01", "litres": 1, "reason": "spilled"}
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_wastage(payload, self.admin)
        self.assertEqual(caught.exception.detail["code"], "INVALID_WASTAGE_DATE")

        payload = RecordWastageRequest.model_validate(
            {"waste_date": "2023-05-10", "litres": 1, "reason": "spilled"}
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_wastage(payload, self.operator)
        self.assertEqual(
            caught.exception.detail["code"],
            "OPERATOR_DATE_RESTRICTION",
        )

    async def test_range_filter_is_ignored_when_exact_date_present(self) -> None:
        from app.schemas.wastage import WastageQuery

        result = await self.service.list_wastage(
            WastageQuery(
                waste_date="2024-01-10",
                from_date="2024-02-01",
                to_date="2024-01-01",
            )
        )
        self.assertEqual(result["total"], 0)

        with self.assertRaises(HTTPException) as caught:
            await self.service.list_wastage(
                WastageQuery(from_date="2024-02-01", to_date="2024-01-01")
            )
        self.assertEqual(caught.exception.detail["code"], "INVALID_DATE_RANGE")


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")
        self.stock_repository = FakeStockRepository()
        self.wastage_repository = FakeWastageRepository(self.stock_repository)
        self.wastage_repository.recorder = self.operator
        self.stock_repository.production.extend(
            [
                (date(2024, 1, 10), Decimal("20.00")),
                (date(2024, 1, 11), Decimal("16.50")),
                (date(2024, 1, 11), Decimal("15.00")),
            ]
        )
        self.stock_repository.sales.append((date(2024, 1, 11), Decimal("40.00")))
        self.stock_repository.wastage.append((date(2024, 1, 11), Decimal("2.00")))

        async def override_get_db():
            yield FakeSession(self.admin, self.operator)

        def override_stock_repository() -> Any:
            return self.stock_repository

        def override_wastage_repository() -> Any:
            return self.wastage_repository

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_stock_repository] = override_stock_repository
        app.dependency_overrides[get_wastage_repository] = override_wastage_repository
        self.audit = FakeAuditService()
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit
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

    async def test_stock_and_history(self) -> None:
        response = await self.client.get(
            "/api/v1/stock?date=2024-01-11",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "date": "2024-01-11",
                "opening_stock": "20.00",
                "produced": "31.50",
                "sold": "40.00",
                "wasted": "2.00",
                "closing_stock": "9.50",
            },
        )

        history = await self.client.get(
            "/api/v1/stock/history?from=2024-01-10&to=2024-01-12",
            headers=self._auth(self.operator),
        )
        self.assertEqual(history.status_code, 200)
        body = history.json()
        self.assertEqual(body["period"], {"from": "2024-01-10", "to": "2024-01-12"})
        self.assertEqual(len(body["history"]), 3)
        self.assertEqual(
            body["history"][1]["opening_stock"],
            body["history"][0]["closing_stock"],
        )

    async def test_record_list_and_insufficient(self) -> None:
        today = get_business_date()
        self.stock_repository.production.append(
            (date.fromisoformat(today), Decimal("15.00"))
        )
        created = await self.client.post(
            "/api/v1/wastage",
            headers=self._auth(self.operator),
            json={"waste_date": today, "litres": 2.5, "reason": "spoiled"},
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["wastage"]["reason"], "spoiled")
        self.assertEqual(body["wastage"]["litres"], "2.50")
        self.assertEqual(body["stock_remaining"], "22.00")

        listing = await self.client.get(
            "/api/v1/wastage?page=1&page_size=10&reason=spoiled",
            headers=self._auth(self.operator),
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(
            listing.json()["items"][0]["recorder"]["username"],
            "ramesh_operator",
        )

    async def test_business_errors(self) -> None:
        insufficient = await self.client.post(
            "/api/v1/wastage",
            headers=self._auth(),
            json={"waste_date": "2024-01-11", "litres": 10, "reason": "spoiled"},
        )
        self.assertEqual(insufficient.status_code, 400)
        self.assertEqual(
            insufficient.json()["error"]["code"],
            "STOCK_INSUFFICIENT",
        )
        self.assertIn("9.50", insufficient.json()["error"]["message"])

        future = await self.client.post(
            "/api/v1/wastage",
            headers=self._auth(),
            json={"waste_date": "2099-01-01", "litres": 1, "reason": "spilled"},
        )
        self.assertEqual(future.status_code, 400)
        self.assertEqual(
            future.json()["error"]["code"],
            "INVALID_WASTAGE_DATE",
        )

        past = await self.client.post(
            "/api/v1/wastage",
            headers=self._auth(self.operator),
            json={"waste_date": "2023-05-10", "litres": 1, "reason": "spilled"},
        )
        self.assertEqual(past.status_code, 403)
        self.assertEqual(
            past.json()["error"]["code"],
            "OPERATOR_DATE_RESTRICTION",
        )

        invalid_range = await self.client.get(
            "/api/v1/wastage?from=2024-02-01&to=2024-01-01",
            headers=self._auth(),
        )
        self.assertEqual(invalid_range.status_code, 400)
        self.assertEqual(
            invalid_range.json()["error"]["code"],
            "INVALID_DATE_RANGE",
        )

    async def test_body_validation_messages(self) -> None:
        cases = [
            (
                {},
                "waste_date: Invalid input: expected string, received undefined",
            ),
            (
                {"waste_date": "2024-01-11", "reason": "spoiled"},
                "litres: Invalid input: expected number, received NaN",
            ),
            (
                {"waste_date": "2024-01-11", "litres": 1},
                'reason: Invalid option: expected one of '
                '"spoiled"|"spilled"|"returned"',
            ),
            (
                {"waste_date": "11-01-2024", "litres": 1, "reason": "spoiled"},
                "waste_date: Waste date must be in YYYY-MM-DD format",
            ),
            (
                {"waste_date": "2024-01-11", "litres": 0, "reason": "spoiled"},
                "litres: Litres must be greater than zero",
            ),
            (
                {"waste_date": "2024-01-11", "litres": 1, "reason": "expired"},
                'reason: Invalid option: expected one of '
                '"spoiled"|"spilled"|"returned"',
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                response = await self.client.post(
                    "/api/v1/wastage",
                    headers=self._auth(),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )

    async def test_query_validation_messages(self) -> None:
        cases = [
            (
                "/api/v1/wastage?page=0",
                "page: Too small: expected number to be >=1",
            ),
            (
                "/api/v1/wastage?page_size=101",
                "page_size: Too big: expected number to be <=100",
            ),
            (
                "/api/v1/wastage?page=1.5",
                "page: Invalid input: expected int, received number",
            ),
            (
                "/api/v1/wastage?page=abc",
                "page: Invalid input: expected number, received NaN",
            ),
            (
                "/api/v1/wastage?waste_date=bad",
                "waste_date: Invalid string: must match pattern "
                "/^\\d{4}-\\d{2}-\\d{2}$/",
            ),
            (
                "/api/v1/wastage?reason=expired",
                'reason: Invalid option: expected one of '
                '"spoiled"|"spilled"|"returned"',
            ),
            (
                "/api/v1/stock?date=bad",
                "date: Date must be in YYYY-MM-DD format",
            ),
            (
                "/api/v1/stock/history?from=2024-01-01",
                "to: Invalid input: expected string, received undefined",
            ),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                response = await self.client.get(url, headers=self._auth())
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
