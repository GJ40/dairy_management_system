from __future__ import annotations

import unittest
from collections import Counter
from datetime import date, datetime

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_buffalo_repository,
    get_delete_repository,
    get_security_audit_service,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.buffalo import Buffalo
from app.models.user import User
from app.repositories.buffalo_repository import BuffaloRepository
from app.repositories.delete_repository import DeleteRepository
from app.schemas.buffalo import (
    BuffaloQuery,
    CreateBuffaloRequest,
    UpdateBuffaloRequest,
    serialize_buffalo,
)
from app.services.buffalo_service import BuffaloService
from app.services.delete_service import DeleteService
from tests.audit_helpers import FakeAuditService

CREATED = datetime(2026, 10, 28, 12, 10, 23, 123000)


def make_user(
    user_id: int = 1,
    *,
    email: str = "admin@example.com",
    username: str = "admin",
    role: str = "admin",
) -> User:
    return User(
        id=user_id,
        full_name="System Admin",
        username=username,
        email=email,
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
    name: str = "Lakshmi",
    breed: str = "Murrah",
    dob: date | None = date(2021, 4, 10),
    purchase_date: date | None = date(2023, 1, 15),
    status: str = "active",
    is_deleted: bool = False,
    created_at: datetime = CREATED,
) -> Buffalo:
    return Buffalo(
        id=buffalo_id,
        tag_no=tag_no,
        name=name,
        breed=breed,
        dob=dob,
        purchase_date=purchase_date,
        status=status,
        is_deleted=is_deleted,
        created_at=created_at,
        updated_at=created_at,
    )


class FakeBuffaloRepository:
    def __init__(self, buffaloes: list[Buffalo] | None = None) -> None:
        self.buffaloes = list(buffaloes or [])
        self.commits = 0
        self.rollbacks = 0
        self._next_id = max((item.id for item in self.buffaloes), default=0) + 1

    async def get_by_id(
        self,
        buffalo_id: int,
        *,
        include_deleted: bool = False,
    ) -> Buffalo | None:
        for buffalo in self.buffaloes:
            if buffalo.id == buffalo_id and (include_deleted or not buffalo.is_deleted):
                return buffalo
        return None

    async def get_by_tag_no(
        self,
        tag_no: str,
        *,
        exclude_id: int | None = None,
        include_deleted: bool = False,
    ) -> Buffalo | None:
        normalized = tag_no.strip().upper()
        for buffalo in self.buffaloes:
            if exclude_id is not None and buffalo.id == exclude_id:
                continue
            if (
                buffalo.tag_no == normalized
                and (include_deleted or not buffalo.is_deleted)
            ):
                return buffalo
        return None

    async def list_buffaloes(self, query: BuffaloQuery) -> tuple[list[Buffalo], int]:
        rows = [buffalo for buffalo in self.buffaloes if not buffalo.is_deleted]
        if query.status:
            rows = [buffalo for buffalo in rows if buffalo.status == query.status]
        if query.search:
            term = query.search.lower()
            rows = [
                buffalo
                for buffalo in rows
                if term in buffalo.name.lower()
                or term in buffalo.tag_no.lower()
                or term in buffalo.breed.lower()
            ]
        rows.sort(key=lambda buffalo: buffalo.created_at, reverse=True)
        total = len(rows)
        start = (query.page - 1) * query.page_size
        return rows[start : start + query.page_size], total

    async def count_by_status(self) -> list[tuple[str, int]]:
        counts = Counter(
            buffalo.status for buffalo in self.buffaloes if not buffalo.is_deleted
        )
        return list(counts.items())

    async def create(
        self,
        *,
        tag_no: str,
        name: str,
        breed: str,
        dob: date | None,
        purchase_date: date | None,
        status: str,
    ) -> Buffalo:
        buffalo = Buffalo(
            id=self._next_id,
            tag_no=tag_no,
            name=name,
            breed=breed,
            dob=dob,
            purchase_date=purchase_date,
            status=status,
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        self._next_id += 1
        self.buffaloes.append(buffalo)
        return buffalo

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, buffalo: Buffalo) -> None:
        return None


class FakeDeleteRepository:
    def __init__(self, record: Buffalo | None = None) -> None:
        self.record = record
        self.calls: list[tuple[type[object], int]] = []

    async def soft_delete(self, model: type[object], record_id: int) -> object | None:
        self.calls.append((model, record_id))
        if (
            self.record is not None
            and model is type(self.record)
            and self.record.id == record_id
            and not self.record.is_deleted
        ):
            self.record.is_deleted = True
            return self.record
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class SerializationTests(unittest.TestCase):
    def test_buffalo_serialization(self) -> None:
        data = serialize_buffalo(make_buffalo())
        self.assertEqual(
            list(data),
            [
                "id",
                "tag_no",
                "name",
                "breed",
                "dob",
                "purchase_date",
                "status",
                "is_deleted",
                "createdAt",
                "updatedAt",
            ],
        )
        self.assertEqual(data["dob"], "2021-04-10")
        self.assertEqual(data["purchase_date"], "2023-01-15")
        self.assertEqual(data["createdAt"], "2026-10-28T06:40:23.123Z")
        self.assertEqual(data["updatedAt"], "2026-10-28T06:40:23.123Z")

    def test_null_dates(self) -> None:
        data = serialize_buffalo(make_buffalo(dob=None, purchase_date=None))
        self.assertIsNone(data["dob"])
        self.assertIsNone(data["purchase_date"])

    def test_create_defaults_and_normalization(self) -> None:
        payload = CreateBuffaloRequest(
            tag_no=" tag-9 ",
            name=" Nandi ",
            breed=" Surti ",
        )
        self.assertEqual(payload.tag_no, "tag-9")
        self.assertEqual(payload.name, "Nandi")
        self.assertEqual(payload.breed, "Surti")
        self.assertEqual(payload.status, "active")

    def test_create_validation_messages(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Tag number cannot be empty"):
            CreateBuffaloRequest(tag_no=" ", name="Nandi", breed="Surti")
        with self.assertRaisesRegex(ValidationError, "Date of birth must be YYYY-MM-DD"):
            CreateBuffaloRequest(
                tag_no="TAG-9",
                name="Nandi",
                breed="Surti",
                dob="10-04-2021",
            )
        with self.assertRaisesRegex(
            ValidationError,
            'Invalid option: expected one of "active"\\|"sold"\\|"dry"\\|"dead"',
        ):
            CreateBuffaloRequest(
                tag_no="TAG-9",
                name="Nandi",
                breed="Surti",
                status="pregnant",
            )

    def test_update_accepts_explicit_null_dates(self) -> None:
        payload = UpdateBuffaloRequest(dob=None, purchase_date=None)
        self.assertEqual(
            payload.model_dump(exclude_unset=True),
            {"dob": None, "purchase_date": None},
        )

    def test_update_validation_messages(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Date of birth must be YYYY-MM-DD"):
            UpdateBuffaloRequest(dob="2021/04/10")
        with self.assertRaisesRegex(
            ValidationError,
            'Invalid option: expected one of "active"\\|"sold"\\|"dry"\\|"dead"',
        ):
            UpdateBuffaloRequest(status="pregnant")


class BuffaloServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.first = make_buffalo()
        self.second = make_buffalo(
            buffalo_id=2,
            tag_no="TAG-002",
            name="Nandi",
            breed="Surti",
            status="dry",
        )
        self.repository = FakeBuffaloRepository([self.first, self.second])
        self.service = BuffaloService(self.repository)  # type: ignore[arg-type]

    async def test_list_and_filter(self) -> None:
        result = await self.service.list_buffaloes(
            BuffaloQuery(status="active", search="murrah")
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["tag_no"], "TAG-001")

    async def test_list_pagination(self) -> None:
        result = await self.service.list_buffaloes(BuffaloQuery(page=2, page_size=1))
        self.assertEqual(result["page"], 2)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["total"], 2)

    async def test_get_missing(self) -> None:
        with self.assertRaisesRegex(HTTPException, "Buffalo with id 999 not found"):
            await self.service.get_buffalo("999")

    async def test_create_normalizes_tag_and_dates(self) -> None:
        result = await self.service.create_buffalo(
            CreateBuffaloRequest(
                tag_no=" tag-100 ",
                name=" Kalyani ",
                breed=" Murrah ",
                dob="2021-04-10",
                purchase_date="2023-01-15",
            )
        )
        self.assertEqual(result["tag_no"], "TAG-100")
        self.assertEqual(result["name"], "Kalyani")
        self.assertEqual(result["dob"], "2021-04-10")
        self.assertEqual(result["status"], "active")
        self.assertEqual(self.repository.commits, 1)

    async def test_create_duplicate_is_case_insensitive(self) -> None:
        with self.assertRaisesRegex(
            HTTPException,
            "Buffalo with tag number 'TAG-001' already exists",
        ):
            await self.service.create_buffalo(
                CreateBuffaloRequest(tag_no="tag-001", name="Other", breed="Surti")
            )

    async def test_update_fields_and_clear_dates(self) -> None:
        result = await self.service.update_buffalo(
            "1",
            UpdateBuffaloRequest(
                tag_no=" tag-777 ",
                name=" Updated ",
                breed=" Mehsana ",
                dob=None,
                purchase_date="2022-02-02",
                status="sold",
            ),
        )
        self.assertEqual(result["tag_no"], "TAG-777")
        self.assertEqual(result["name"], "Updated")
        self.assertEqual(result["breed"], "Mehsana")
        self.assertIsNone(result["dob"])
        self.assertEqual(result["purchase_date"], "2022-02-02")
        self.assertEqual(result["status"], "sold")

    async def test_update_duplicate_tag(self) -> None:
        with self.assertRaisesRegex(
            HTTPException,
            "Tag number 'TAG-002' is already assigned to another buffalo",
        ):
            await self.service.update_buffalo(
                "1",
                UpdateBuffaloRequest(tag_no="tag-002"),
            )

    async def test_update_missing(self) -> None:
        with self.assertRaisesRegex(HTTPException, "Buffalo with id 999 not found"):
            await self.service.update_buffalo("999", UpdateBuffaloRequest(name="X"))

    async def test_counts(self) -> None:
        self.repository.buffaloes.append(
            make_buffalo(buffalo_id=3, tag_no="TAG-003", status="active")
        )
        result = await self.service.get_counts()
        self.assertEqual(
            result,
            {"total": 3, "active": 2, "dry": 1, "sold": 0, "dead": 0},
        )

    async def test_buffalo_audit_events(self) -> None:
        audit = FakeAuditService()
        service = BuffaloService(  # type: ignore[arg-type]
            self.repository,
            audit=audit,
        )
        created = await service.create_buffalo(
            CreateBuffaloRequest(tag_no="tag-300", name="Gauri", breed="Murrah"),
            actor_user_id=1,
        )
        self.assertEqual(audit.records[-1]["event_type"], "buffalo.created")
        self.assertEqual(
            audit.records[-1]["metadata"]["buffalo_id"], created["id"]
        )

        await service.update_buffalo(
            str(created["id"]),
            UpdateBuffaloRequest(name="Gauri Updated", status="sold"),
            actor_user_id=1,
        )
        event_types = [record["event_type"] for record in audit.records]
        self.assertIn("buffalo.status.changed", event_types)
        self.assertIn("buffalo.updated", event_types)
        self.assertEqual(
            audit.records[-1]["metadata"]["changed_fields"], ["name"]
        )


class DeleteServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_soft_delete(self) -> None:
        buffalo = make_buffalo()
        repository = FakeDeleteRepository(buffalo)
        result = await DeleteService(repository).soft_delete_resource(  # type: ignore[arg-type]
            "Buffaloes",
            "1",
        )
        self.assertTrue(buffalo.is_deleted)
        self.assertEqual(result["resource"], "buffaloes")
        self.assertEqual(result["id"], 1)
        self.assertEqual(
            result["message"],
            "buffaloes record #1 soft-deleted successfully",
        )
        self.assertTrue(result["deleted_at"].endswith("Z"))

    async def test_soft_delete_audit_event(self) -> None:
        buffalo = make_buffalo()
        repository = FakeDeleteRepository(buffalo)
        audit = FakeAuditService()
        await DeleteService(repository, audit).soft_delete_resource(  # type: ignore[arg-type]
            "buffaloes",
            "1",
            actor_user_id=1,
        )
        self.assertEqual(audit.records[-1]["event_type"], "record.soft_deleted")
        self.assertEqual(audit.records[-1]["metadata"]["resource"], "buffaloes")
        self.assertEqual(audit.records[-1]["metadata"]["record_id"], 1)

    async def test_unsupported_resource(self) -> None:
        repository = FakeDeleteRepository()
        with self.assertRaisesRegex(
            HTTPException,
            r"Unsupported resource 'cows' for deletion\. Allowed resources: "
            r"\[buffaloes, customers, sales, invoices, expenses, production, wastage\]",
        ):
            await DeleteService(repository).soft_delete_resource(  # type: ignore[arg-type]
                "cows",
                "1",
            )

    async def test_not_found_or_already_deleted(self) -> None:
        repository = FakeDeleteRepository()
        with self.assertRaisesRegex(
            HTTPException,
            "buffaloe with id 1 not found or has already been deleted",
        ):
            await DeleteService(repository).soft_delete_resource(  # type: ignore[arg-type]
                "buffaloes",
                "1",
            )


class FakeSession:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def get(self, model: type[User], user_id: int) -> User | None:
        if model is User:
            return self.users.get(user_id)
        return None


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(
            user_id=2,
            email="operator@example.com",
            username="operator",
            role="operator",
        )
        self.buffalo = make_buffalo()
        self.buffalo_repository = FakeBuffaloRepository(
            [self.buffalo, make_buffalo(buffalo_id=2, tag_no="TAG-002", status="dry")]
        )
        self.delete_repository = FakeDeleteRepository(self.buffalo)

        self.audit = FakeAuditService()

        async def override_get_db():
            yield FakeSession(self.admin, self.operator)

        def override_buffalo_repository() -> BuffaloRepository:
            return self.buffalo_repository  # type: ignore[return-value]

        def override_delete_repository() -> DeleteRepository:
            return self.delete_repository  # type: ignore[return-value]

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit
        app.dependency_overrides[get_buffalo_repository] = override_buffalo_repository
        app.dependency_overrides[get_delete_repository] = override_delete_repository
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

    async def test_operator_can_list_buffaloes(self) -> None:
        response = await self.client.get(
            "/api/v1/buffaloes",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 2)

    async def test_counts_route(self) -> None:
        response = await self.client.get(
            "/api/v1/buffaloes/count",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"total": 2, "active": 1, "dry": 1, "sold": 0, "dead": 0},
        )

    async def test_create_buffalo(self) -> None:
        response = await self.client.post(
            "/api/v1/buffaloes",
            headers=self._auth(self.operator),
            json={
                "tag_no": " tag-300 ",
                "name": " Kalyani ",
                "breed": " Murrah ",
                "dob": "2021-04-10",
            },
        )
        self.assertEqual(response.status_code, 201)
        buffalo = response.json()["buffalo"]
        self.assertEqual(buffalo["tag_no"], "TAG-300")
        self.assertEqual(buffalo["status"], "active")
        self.assertNotIn("created_at", buffalo)

    async def test_create_duplicate(self) -> None:
        response = await self.client.post(
            "/api/v1/buffaloes",
            headers=self._auth(),
            json={"tag_no": "tag-001", "name": "Other", "breed": "Surti"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"],
            {
                "code": "DUPLICATE_ENTRY",
                "message": "Buffalo with tag number 'TAG-001' already exists",
            },
        )

    async def test_create_validation(self) -> None:
        response = await self.client.post(
            "/api/v1/buffaloes",
            headers=self._auth(),
            json={"name": "Nandi", "breed": "Surti"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            "tag_no: Invalid input: expected string, received undefined",
        )

    async def test_invalid_status_query(self) -> None:
        response = await self.client.get(
            "/api/v1/buffaloes?status=pregnant",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            'status: Invalid option: expected one of "active"|"sold"|"dry"|"dead"',
        )

    async def test_get_by_id(self) -> None:
        response = await self.client.get(
            "/api/v1/buffaloes/1",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["buffalo"]["tag_no"], "TAG-001")

    async def test_get_missing(self) -> None:
        response = await self.client.get(
            "/api/v1/buffaloes/999",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["message"],
            "Buffalo with id 999 not found",
        )

    async def test_update_buffalo(self) -> None:
        response = await self.client.put(
            "/api/v1/buffaloes/1",
            headers=self._auth(self.operator),
            json={"name": "Updated Lakshmi", "status": "dry", "dob": None},
        )
        self.assertEqual(response.status_code, 200)
        buffalo = response.json()["buffalo"]
        self.assertEqual(buffalo["name"], "Updated Lakshmi")
        self.assertEqual(buffalo["status"], "dry")
        self.assertIsNone(buffalo["dob"])

    async def test_operator_cannot_delete(self) -> None:
        response = await self.client.delete(
            "/api/v1/buffaloes/1",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "FORBIDDEN")

    async def test_unauthenticated_delete(self) -> None:
        response = await self.client.delete("/api/v1/buffaloes/1")
        self.assertEqual(response.status_code, 401)

    async def test_unsupported_delete_resource(self) -> None:
        response = await self.client.delete(
            "/api/v1/cows/1",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "UNSUPPORTED_RESOURCE",
        )

    async def test_admin_soft_delete_and_repeat(self) -> None:
        response = await self.client.delete(
            "/api/v1/buffaloes/1",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["resource"], "buffaloes")
        self.assertEqual(body["id"], 1)
        self.assertIn("soft-deleted successfully", body["message"])

        repeat = await self.client.delete(
            "/api/v1/buffaloes/1",
            headers=self._auth(),
        )
        self.assertEqual(repeat.status_code, 404)
        self.assertIn("already been deleted", repeat.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
