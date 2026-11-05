from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_buffalo_repository,
    get_production_repository,
    get_security_audit_service,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.buffalo import Buffalo
from app.models.milk_production import MilkProduction
from app.models.user import User
from app.models.user import User as UserModel
from app.repositories.buffalo_repository import BuffaloRepository
from app.repositories.production_repository import ProductionRepository
from app.schemas.production import (
    BulkProductionRequest,
    SingleProductionRequest,
)
from app.services.production_service import ProductionService
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
        full_name="System Admin",
        username=username,
        email=f"{username}@example.com",
        password_hash="not-used",
        role=role,
        is_active=True,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


def make_buffalo(
    buffalo_id: int = 1,
    *,
    tag_no: str = "TAG-001",
    status: str = "active",
    is_deleted: bool = False,
) -> Buffalo:
    return Buffalo(
        id=buffalo_id,
        tag_no=tag_no,
        name=f"Buffalo {buffalo_id}",
        breed="Murrah",
        dob=date(2021, 4, 10),
        purchase_date=date(2023, 1, 15),
        status=status,
        is_deleted=is_deleted,
        created_at=CREATED,
        updated_at=CREATED,
    )


def make_record(
    record_id: int,
    buffalo: Buffalo,
    recorder: User,
    prod_date: date,
    session: str,
    litres: str,
) -> MilkProduction:
    record = MilkProduction(
        id=record_id,
        buffalo_id=buffalo.id,
        prod_date=prod_date,
        session=session,
        litres=Decimal(litres),
        recorded_by=recorder.id,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )
    record.buffalo = buffalo
    record.recorder = recorder
    return record


class FakeBuffaloRepository:
    def __init__(self, buffaloes: list[Buffalo]) -> None:
        self.buffaloes = buffaloes

    async def get_by_id(
        self,
        buffalo_id: int,
        *,
        include_deleted: bool = False,
    ) -> Buffalo | None:
        for buffalo in self.buffaloes:
            if buffalo.id == buffalo_id and (
                include_deleted or not buffalo.is_deleted
            ):
                return buffalo
        return None

    async def list_active(self) -> list[Buffalo]:
        return sorted(
            [
                buffalo
                for buffalo in self.buffaloes
                if not buffalo.is_deleted and buffalo.status == "active"
            ],
            key=lambda buffalo: buffalo.tag_no,
        )


class FakeProductionRepository:
    def __init__(
        self,
        buffalo_repository: FakeBuffaloRepository,
        recorder: User,
    ) -> None:
        self.buffalo_repository = buffalo_repository
        self.recorder = recorder
        self.records: list[MilkProduction] = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self._pending_created: list[MilkProduction] = []

    async def find_one(
        self,
        buffalo_id: int,
        prod_date: date,
        session: str,
    ) -> MilkProduction | None:
        for record in self.records:
            if (
                not record.is_deleted
                and record.buffalo_id == buffalo_id
                and record.prod_date == prod_date
                and record.session == session
            ):
                return record
        return None

    async def list_for_date(self, prod_date: date) -> list[MilkProduction]:
        return [
            record
            for record in self.records
            if not record.is_deleted and record.prod_date == prod_date
        ]

    async def list_for_date_with_details(
        self,
        prod_date: date,
    ) -> list[MilkProduction]:
        rows = await self.list_for_date(prod_date)
        return sorted(
            rows,
            key=lambda record: (record.buffalo.tag_no, record.session),
        )

    async def list_for_buffalo(
        self,
        buffalo_id: int,
        from_date: date | None,
        to_date: date | None,
    ) -> list[MilkProduction]:
        rows = [
            record
            for record in self.records
            if not record.is_deleted and record.buffalo_id == buffalo_id
        ]
        if from_date is not None:
            rows = [record for record in rows if record.prod_date >= from_date]
        if to_date is not None:
            rows = [record for record in rows if record.prod_date <= to_date]
        return sorted(
            rows,
            key=lambda record: (record.prod_date, record.session),
            reverse=True,
        )

    async def aggregated_totals(
        self,
        from_date: date,
        to_date: date,
    ) -> list[tuple[date, str, Decimal]]:
        totals: dict[tuple[date, str], Decimal] = {}
        for record in self.records:
            if (
                record.is_deleted
                or record.prod_date < from_date
                or record.prod_date > to_date
            ):
                continue
            key = (record.prod_date, record.session)
            totals[key] = totals.get(key, Decimal("0")) + record.litres
        return [
            (key[0], key[1], value)
            for key, value in sorted(totals.items())
        ]

    async def create(
        self,
        *,
        buffalo_id: int,
        prod_date: date,
        session: str,
        litres: Decimal,
        recorded_by: int,
    ) -> MilkProduction:
        buffalo = await self.buffalo_repository.get_by_id(buffalo_id)
        record = MilkProduction(
            id=max((item.id for item in self.records), default=0) + 1,
            buffalo_id=buffalo_id,
            prod_date=prod_date,
            session=session,
            litres=litres,
            recorded_by=recorded_by,
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        record.buffalo = buffalo
        record.recorder = self.recorder
        self.records.append(record)
        self._pending_created.append(record)
        return record

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1
        self._pending_created.clear()

    async def rollback(self) -> None:
        self.rollbacks += 1
        pending_ids = {record.id for record in self._pending_created}
        self.records = [
            record for record in self.records if record.id not in pending_ids
        ]
        self._pending_created.clear()


class FakeSession:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def get(self, model: type[User], user_id: int) -> User | None:
        if model is User:
            return self.users.get(user_id)
        return None


class SchemaTests(unittest.TestCase):
    def test_single_missing_number(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            SingleProductionRequest.model_validate({})
        errors = caught.exception.errors()
        self.assertEqual(errors[0]["loc"], ("buffalo_id",))
        self.assertEqual(errors[0]["type"], "missing")

    def test_single_missing_session_and_litres(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            SingleProductionRequest.model_validate(
                {"buffalo_id": 1, "prod_date": "2025-01-15"}
            )
        errors = caught.exception.errors()
        self.assertEqual(
            [(error["loc"], error["type"]) for error in errors],
            [(("session",), "missing"), (("litres",), "missing")],
        )

    def test_single_invalid_enum_date_and_negative(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            SingleProductionRequest.model_validate(
                {
                    "buffalo_id": 1,
                    "prod_date": "15-01-2025",
                    "session": "afternoon",
                    "litres": -1,
                }
            )
        messages = [error["msg"] for error in caught.exception.errors()]
        self.assertIn(
            "Value error, Production date must be in YYYY-MM-DD format",
            messages,
        )

    def test_single_coerces_values(self) -> None:
        payload = SingleProductionRequest.model_validate(
            {
                "buffalo_id": "1",
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": "3.456",
            }
        )
        self.assertEqual(payload.buffalo_id, 1)
        self.assertEqual(payload.litres, 3.456)
        self.assertIs(payload.overwrite, False)

    def test_bulk_requires_entries(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            BulkProductionRequest.model_validate(
                {"prod_date": "2025-01-15", "entries": []}
            )
        self.assertIn(
            "At least one production entry is required in bulk submission",
            str(caught.exception),
        )


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="operator")
        self.first = make_buffalo()
        self.second = make_buffalo(2, tag_no="TAG-002")
        self.inactive = make_buffalo(3, tag_no="TAG-003", status="dry")
        self.buffalo_repository = FakeBuffaloRepository(
            [self.first, self.second, self.inactive]
        )
        self.repository = FakeProductionRepository(
            self.buffalo_repository,
            self.admin,
        )
        self.service = ProductionService(  # type: ignore[arg-type]
            self.repository,
            self.buffalo_repository,
        )

    async def test_grid_only_active_sorted_and_totals(self) -> None:
        self.repository.records.append(
            make_record(
                1,
                self.second,
                self.admin,
                date(2025, 1, 15),
                "evening",
                "5.50",
            )
        )
        self.repository.records.append(
            make_record(
                2,
                self.first,
                self.admin,
                date(2025, 1, 15),
                "morning",
                "6.50",
            )
        )
        result = await self.service.get_grid("2025-01-15")
        self.assertEqual(result["active_buffaloes_count"], 2)
        self.assertEqual(
            [row["tag_no"] for row in result["grid"]],
            ["TAG-001", "TAG-002"],
        )
        self.assertEqual(
            result["herd_totals"],
            {"morning": "6.50", "evening": "5.50", "grand_total": "12.00"},
        )
        self.assertEqual(result["grid"][0]["daily_total"], "6.50")
        self.assertIsNone(result["grid"][1]["morning_litres"])

    async def test_future_grid_rejected(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.get_grid("2999-01-01")
        self.assertEqual(caught.exception.detail["code"], "INVALID_PRODUCTION_DATE")

    async def test_single_duplicate_and_overwrite(self) -> None:
        payload = SingleProductionRequest.model_validate(
            {
                "buffalo_id": 1,
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": 6.5,
            }
        )
        created = await self.service.record_production(payload, self.admin)
        self.assertEqual(created["litres"], "6.50")
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_production(payload, self.admin)
        self.assertEqual(caught.exception.detail["code"], "DUPLICATE_PRODUCTION_ENTRY")

        overwrite = SingleProductionRequest.model_validate(
            {
                "buffalo_id": 1,
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": "7.25",
                "overwrite": True,
            }
        )
        updated = await self.service.record_production(overwrite, self.admin)
        self.assertEqual(updated["litres"], "7.25")
        self.assertEqual(updated["recorded_by"], self.admin.id)

    async def test_production_audit_events(self) -> None:
        audit = FakeAuditService()
        service = ProductionService(  # type: ignore[arg-type]
            self.repository,
            self.buffalo_repository,
            audit=audit,
        )
        payload = SingleProductionRequest.model_validate(
            {
                "buffalo_id": 1,
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": 6.5,
            }
        )
        await service.record_production(payload, self.admin)
        self.assertEqual(audit.records[-1]["event_type"], "production.recorded")
        self.assertEqual(
            audit.records[-1]["metadata"]["session_name"], "morning"
        )

        overwrite = SingleProductionRequest.model_validate(
            {
                "buffalo_id": 1,
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": 7.25,
                "overwrite": True,
            }
        )
        await service.record_production(overwrite, self.admin)
        self.assertEqual(audit.records[-1]["event_type"], "production.updated")

    async def test_bulk_production_audit_event(self) -> None:
        audit = FakeAuditService()
        service = ProductionService(  # type: ignore[arg-type]
            self.repository,
            self.buffalo_repository,
            audit=audit,
        )
        payload = BulkProductionRequest.model_validate(
            {
                "prod_date": "2025-01-15",
                "entries": [
                    {"buffalo_id": 1, "morning_litres": 6.5},
                    {"buffalo_id": 2, "evening_litres": 5.0},
                ],
            }
        )
        await service.record_bulk_production(payload, self.admin)
        event = audit.records[-1]
        self.assertEqual(event["event_type"], "production.bulk_recorded")
        self.assertEqual(event["metadata"]["entry_count"], 2)
        self.assertEqual(event["metadata"]["created_count"], 2)

    async def test_operator_only_today(self) -> None:
        payload = SingleProductionRequest.model_validate(
            {
                "buffalo_id": 1,
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": 1,
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_production(payload, self.operator)
        self.assertEqual(caught.exception.detail["code"], "OPERATOR_DATE_RESTRICTION")

        today = get_business_date()
        allowed = SingleProductionRequest.model_validate(
            {
                "buffalo_id": 1,
                "prod_date": today,
                "session": "morning",
                "litres": 1,
            }
        )
        self.assertEqual(
            (await self.service.record_production(allowed, self.operator))[
                "litres"
            ],
            "1.00",
        )

    async def test_inactive_buffalo_rejected(self) -> None:
        payload = SingleProductionRequest.model_validate(
            {
                "buffalo_id": 3,
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": 1,
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_production(payload, self.admin)
        self.assertEqual(caught.exception.detail["code"], "BUFFALO_NOT_ACTIVE")

    async def test_bulk_transaction_conflict_rolls_back(self) -> None:
        self.repository.records.append(
            make_record(
                1,
                self.first,
                self.admin,
                date(2025, 1, 15),
                "morning",
                "1.00",
            )
        )
        payload = BulkProductionRequest.model_validate(
            {
                "prod_date": "2025-01-15",
                "entries": [
                    {"buffalo_id": 2, "morning_litres": 2},
                    {"buffalo_id": 1, "morning_litres": 3},
                ],
            }
        )
        with self.assertRaises(HTTPException):
            await self.service.record_bulk_production(payload, self.admin)
        self.assertEqual(self.repository.rollbacks, 1)
        self.assertEqual(len(self.repository.records), 1)

    async def test_bulk_creates_pairs(self) -> None:
        payload = BulkProductionRequest.model_validate(
            {
                "prod_date": "2025-01-15",
                "entries": [
                    {
                        "buffalo_id": 1,
                        "morning_litres": 2,
                        "evening_litres": 3,
                    }
                ],
            }
        )
        records = await self.service.record_bulk_production(payload, self.admin)
        self.assertEqual([record["session"] for record in records], ["morning", "evening"])
        self.assertEqual([record["litres"] for record in records], ["2.00", "3.00"])

    async def test_summary_groups_days(self) -> None:
        self.repository.records.extend(
            [
                make_record(
                    1,
                    self.first,
                    self.admin,
                    date(2025, 1, 15),
                    "morning",
                    "10.00",
                ),
                make_record(
                    2,
                    self.second,
                    self.admin,
                    date(2025, 1, 15),
                    "evening",
                    "5.00",
                ),
                make_record(
                    3,
                    self.first,
                    self.admin,
                    date(2025, 1, 16),
                    "morning",
                    "4.00",
                ),
            ]
        )
        result = await self.service.get_summary("2025-01-15", "2025-01-16")
        self.assertEqual(result["days_recorded"], 2)
        self.assertEqual(result["grand_total_litres"], "19.00")
        self.assertEqual(result["average_daily_litres"], "9.50")
        self.assertEqual(result["daily_summaries"][0]["total_litres"], "15.00")

    async def test_history_and_range_validation(self) -> None:
        self.repository.records.append(
            make_record(
                1,
                self.first,
                self.admin,
                date(2025, 1, 15),
                "morning",
                "6.50",
            )
        )
        result = await self.service.get_buffalo_history("1", "2025-01-01", "2025-01-31")
        self.assertEqual(result["days_recorded"], 1)
        self.assertEqual(result["total_litres_produced"], "6.50")
        with self.assertRaises(HTTPException) as caught:
            await self.service.get_buffalo_history("1", "2025-02-01", "2025-01-01")
        self.assertEqual(caught.exception.detail["code"], "INVALID_DATE_RANGE")


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="operator")
        self.first = make_buffalo()
        self.second = make_buffalo(2, tag_no="TAG-002")
        self.buffalo_repository = FakeBuffaloRepository([self.first, self.second])
        self.production_repository = FakeProductionRepository(
            self.buffalo_repository,
            self.admin,
        )
        self.production_repository.records.append(
            make_record(
                1,
                self.first,
                self.admin,
                date(2025, 1, 15),
                "morning",
                "6.50",
            )
        )
        self.production_repository.records.append(
            make_record(
                2,
                self.second,
                self.admin,
                date(2025, 1, 15),
                "evening",
                "5.50",
            )
        )

        async def override_get_db():
            yield FakeSession(self.admin, self.operator)

        def override_buffalo_repository() -> BuffaloRepository:
            return self.buffalo_repository  # type: ignore[return-value]

        def override_production_repository() -> ProductionRepository:
            return self.production_repository  # type: ignore[return-value]

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_buffalo_repository] = override_buffalo_repository
        app.dependency_overrides[get_production_repository] = (
            override_production_repository
        )
        self.audit = FakeAuditService()
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self, user: UserModel | None = None) -> dict[str, str]:
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

    async def test_grid(self) -> None:
        response = await self.client.get(
            "/api/v1/production/grid?date=2025-01-15",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_buffaloes_count"], 2)
        self.assertEqual(body["herd_totals"]["grand_total"], "12.00")

    async def test_future_and_operator_restrictions(self) -> None:
        future = await self.client.get(
            "/api/v1/production/grid?date=2999-01-01",
            headers=self._auth(),
        )
        self.assertEqual(future.status_code, 400)
        self.assertEqual(
            future.json()["error"]["code"],
            "INVALID_PRODUCTION_DATE",
        )

        restricted = await self.client.post(
            "/api/v1/production",
            headers=self._auth(self.operator),
            json={
                "buffalo_id": 1,
                "prod_date": "2025-01-15",
                "session": "morning",
                "litres": 1,
            },
        )
        self.assertEqual(restricted.status_code, 403)
        self.assertEqual(
            restricted.json()["error"]["code"],
            "OPERATOR_DATE_RESTRICTION",
        )

    async def test_single_create_conflict_and_overwrite(self) -> None:
        payload = {
            "buffalo_id": 1,
            "prod_date": get_business_date(),
            "session": "evening",
            "litres": "2.5",
        }
        created = await self.client.post(
            "/api/v1/production",
            headers=self._auth(self.operator),
            json=payload,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["record"]["litres"], "2.50")

        duplicate = await self.client.post(
            "/api/v1/production",
            headers=self._auth(self.operator),
            json=payload,
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            duplicate.json()["error"]["code"],
            "DUPLICATE_PRODUCTION_ENTRY",
        )

        overwrite = await self.client.post(
            "/api/v1/production",
            headers=self._auth(self.operator),
            json={**payload, "litres": 9, "overwrite": True},
        )
        self.assertEqual(overwrite.status_code, 201)
        self.assertEqual(overwrite.json()["record"]["litres"], "9.00")

    async def test_bulk_and_validation(self) -> None:
        response = await self.client.post(
            "/api/v1/production",
            headers=self._auth(),
            json={
                "prod_date": "2025-01-16",
                "entries": [
                    {
                        "buffalo_id": 1,
                        "morning_litres": 1,
                        "evening_litres": 2,
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["records"]), 2)
        self.assertEqual(response.json()["message"], "Successfully saved 2 production entries")

        invalid = await self.client.post(
            "/api/v1/production",
            headers=self._auth(),
            json={"prod_date": "2025-01-16", "entries": []},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "VALIDATION_ERROR")

    async def test_by_date_summary_history(self) -> None:
        by_date = await self.client.get(
            "/api/v1/production?date=2025-01-15",
            headers=self._auth(),
        )
        self.assertEqual(by_date.status_code, 200)
        self.assertEqual(len(by_date.json()["entries"]), 2)
        self.assertEqual(
            by_date.json()["entries"][0]["buffalo"]["tag_no"],
            "TAG-001",
        )

        summary = await self.client.get(
            "/api/v1/production/summary?from=2025-01-01&to=2025-01-31",
            headers=self._auth(),
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["grand_total_litres"], "12.00")

        history = await self.client.get(
            "/api/v1/production/buffalo/1?from=2025-01-01&to=2025-01-31",
            headers=self._auth(),
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total_litres_produced"], "6.50")

    async def test_single_missing_fields(self) -> None:
        missing = await self.client.post(
            "/api/v1/production",
            headers=self._auth(),
            json={"prod_date": "2025-01-16"},
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(
            missing.json()["error"]["message"],
            "buffalo_id: Invalid input: expected number, received NaN",
        )

    async def test_validation_messages(self) -> None:
        cases = [
            (
                {
                    "buffalo_id": 0,
                    "prod_date": "2025-01-16",
                    "session": "morning",
                    "litres": 1,
                },
                "buffalo_id: Valid buffalo ID is required",
            ),
            (
                {
                    "buffalo_id": 1,
                    "prod_date": "15-01-2025",
                    "session": "morning",
                    "litres": 1,
                },
                "prod_date: Production date must be in YYYY-MM-DD format",
            ),
            (
                {
                    "buffalo_id": 1,
                    "prod_date": "2025-01-16",
                    "session": "afternoon",
                    "litres": 1,
                },
                'session: Invalid option: expected one of "morning"|"evening"',
            ),
            (
                {
                    "buffalo_id": 1,
                    "prod_date": "2025-01-16",
                    "session": "morning",
                    "litres": -1,
                },
                "litres: Litres must be non-negative (zero or greater)",
            ),
            (
                {
                    "buffalo_id": 1,
                    "prod_date": "2025-01-16",
                    "session": "morning",
                    "litres": 1,
                    "overwrite": "true",
                },
                "overwrite: Invalid input: expected boolean, received string",
            ),
            (
                {
                    "prod_date": "2025-01-16",
                    "entries": [{"morning_litres": 1}],
                },
                "entries.0.buffalo_id: Invalid input: expected number, "
                "received NaN",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                response = await self.client.post(
                    "/api/v1/production",
                    headers=self._auth(),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )

    async def test_missing_and_invalid_query_parameters(self) -> None:
        missing = await self.client.get(
            "/api/v1/production/summary?from=2025-01-01",
            headers=self._auth(),
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(
            missing.json()["error"]["message"],
            "to: Invalid input: expected string, received undefined",
        )

        invalid = await self.client.get(
            "/api/v1/production/grid?date=15-01-2025",
            headers=self._auth(),
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(
            invalid.json()["error"]["code"],
            "VALIDATION_ERROR",
        )


if __name__ == "__main__":
    unittest.main()
