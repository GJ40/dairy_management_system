from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx

import app.models  # noqa: F401
from app.core.dependencies import (
    get_customer_portal_account_repository,
    get_customer_query_repository,
    get_customer_repository,
    get_security_audit_service,
    get_user_repository,
)
from app.core.security import create_access_token, create_customer_access_token
from app.db.session import get_db
from app.main import app
from app.schemas.customer_queries import (
    CustomerQueryListQuery,
    StaffQueryListQuery,
)
from app.services.customer_query_service import CustomerQueryService
from tests.test_customer_portal_auth import (
    CUSTOMER_COOKIE,
    FakeCustomerRepository,
    FakePortalAccountRepository,
    FakeSession,
    make_account,
    make_customer,
)
from tests.test_customers_and_sales import make_user

BASE = datetime(2026, 10, 30, 9, 0, 0)


def make_query(
    query_id: int = 1,
    *,
    customer_id: int = 4,
    account_id: int = 1,
    query_no: str = "QRY-20261030-1A2B",
    category: str = "billing",
    subject: str = "Invoice question",
    status: str = "open",
    assigned_to: int | None = None,
    is_deleted: bool = False,
) -> SimpleNamespace:
    stamp = BASE + timedelta(minutes=query_id)
    return SimpleNamespace(
        id=query_id,
        query_no=query_no,
        customer_id=customer_id,
        account_id=account_id,
        category=category,
        subject=subject,
        status=status,
        assigned_to=assigned_to,
        last_message_at=stamp,
        created_at=stamp,
        updated_at=stamp,
        is_deleted=is_deleted,
    )


def make_message(
    message_id: int = 1,
    *,
    query_id: int = 1,
    body: str = "Please check my invoice",
    sender_type: str = "customer",
    sender_account_id: int | None = 1,
    sender_user_id: int | None = None,
    is_internal: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=message_id,
        query_id=query_id,
        body=body,
        sender_type=sender_type,
        sender_account_id=sender_account_id,
        sender_user_id=sender_user_id,
        is_internal=is_internal,
        created_at=BASE + timedelta(seconds=message_id),
    )


class FakeQueryRepository:
    def __init__(self) -> None:
        self.queries: list[SimpleNamespace] = []
        self.messages: list[SimpleNamespace] = []
        self.commits = 0
        self.rollbacks = 0
        self._query_id = 1
        self._message_id = 1

    async def get_by_id(self, query_id: int):
        return next((row for row in self.queries if row.id == query_id), None)

    async def get_owned(self, query_id: int, customer_id: int):
        return next(
            (
                row
                for row in self.queries
                if row.id == query_id
                and row.customer_id == customer_id
                and not row.is_deleted
            ),
            None,
        )

    async def find_by_query_no(self, query_no: str):
        return next((row for row in self.queries if row.query_no == query_no), None)

    async def _filtered(
        self,
        *,
        customer_id: int | None = None,
        status: str | None = None,
        assigned_to: int | None = None,
        category: str | None = None,
    ):
        rows = [row for row in self.queries if not row.is_deleted]
        if customer_id is not None:
            rows = [row for row in rows if row.customer_id == customer_id]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if assigned_to is not None:
            rows = [row for row in rows if row.assigned_to == assigned_to]
        if category is not None:
            rows = [row for row in rows if row.category == category]
        rows.sort(key=lambda row: (row.updated_at, row.id), reverse=True)
        return rows

    async def list_own_and_count(
        self,
        *,
        customer_id: int,
        page: int,
        page_size: int,
        status: str | None = None,
    ):
        rows = await self._filtered(customer_id=customer_id, status=status)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    async def list_all_and_count(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        assigned_to: int | None = None,
        customer_id: int | None = None,
        category: str | None = None,
    ):
        rows = await self._filtered(
            customer_id=customer_id,
            status=status,
            assigned_to=assigned_to,
            category=category,
        )
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    async def create(
        self,
        *,
        query_no: str,
        customer_id: int,
        account_id: int,
        category: str,
        subject: str,
        last_message_at: datetime,
    ):
        self._query_id = max((row.id for row in self.queries), default=0) + 1
        query = make_query(
            self._query_id,
            customer_id=customer_id,
            account_id=account_id,
            query_no=query_no,
            category=category,
            subject=subject,
        )
        query.last_message_at = last_message_at
        self._query_id += 1
        self.queries.append(query)
        return query

    async def add_message(
        self,
        *,
        query_id: int,
        body: str,
        sender_type: str,
        sender_account_id: int | None = None,
        sender_user_id: int | None = None,
        is_internal: bool = False,
    ):
        self._message_id = max((row.id for row in self.messages), default=0) + 1
        message = make_message(
            self._message_id,
            query_id=query_id,
            body=body,
            sender_type=sender_type,
            sender_account_id=sender_account_id,
            sender_user_id=sender_user_id,
            is_internal=is_internal,
        )
        self._message_id += 1
        self.messages.append(message)
        return message

    async def list_messages(self, query_id: int, *, include_internal: bool):
        rows = [
            row
            for row in self.messages
            if row.query_id == query_id
            and (include_internal or not row.is_internal)
        ]
        rows.sort(key=lambda row: (row.created_at, row.id))
        return rows

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, row: Any) -> None:
        return None


class FakeUserRepository:
    def __init__(self, users: list[Any]) -> None:
        self.users = list(users)

    async def get_by_id(self, user_id: int, *, include_deleted: bool = False):
        return next((row for row in self.users if row.id == user_id), None)


class FakeAuditService:
    def __init__(self) -> None:
        self.denials: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.events.append(kwargs)

    async def record_standalone(self, **kwargs: Any) -> bool:
        self.denials.append(kwargs)
        return True


class QueryServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.other_customer = make_customer(99, name="Other Dairy")
        self.customers = FakeCustomerRepository(
            [self.customer, self.other_customer]
        )
        self.account = make_account(password="x", activated=True)
        self.other_account = make_account(
            2,
            customer_id=99,
            email="other@example.com",
            password="x",
            activated=True,
        )
        self.accounts = FakePortalAccountRepository(
            [self.account, self.other_account]
        )
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")
        self.users = FakeUserRepository([self.admin, self.operator])
        self.repository = FakeQueryRepository()
        self.audit = FakeAuditService()
        self.service = CustomerQueryService(
            self.repository,
            self.customers,
            self.accounts,
            self.users,
            self.audit,
        )

    async def test_create_query(self) -> None:
        result = await self.service.create(
            self.account,
            category="billing",
            subject="Invoice question",
            message="Please check my invoice",
        )
        query = result["query"]
        self.assertTrue(query["query_no"].startswith("QRY-"))
        self.assertEqual(query["status"], "open")
        self.assertEqual(query["subject"], "Invoice question")
        self.assertEqual(len(query["messages"]), 1)
        self.assertEqual(query["messages"][0]["sender_type"], "customer")
        self.assertEqual(self.repository.commits, 1)
        self.assertEqual(self.audit.events[-1]["event_type"], "query.created")
        self.assertEqual(
            self.audit.events[-1]["actor_account_id"], self.account.id
        )
        self.assertEqual(
            self.audit.events[-1]["metadata"]["query_no"], query["query_no"]
        )
        self.assertNotIn("subject", self.audit.events[-1]["metadata"])

        self.repository.queries[0].status = "answered"
        self.repository.messages.append(
            make_message(2, body="internal", sender_type="staff", is_internal=True)
        )
        detail = await self.service.get_query(self.account, 1)
        self.assertEqual(len(detail["query"]["messages"]), 1)

    async def test_create_requires_active_customer(self) -> None:
        self.customer.is_active = False
        with self.assertRaises(Exception) as caught:
            await self.service.create(
                self.account,
                category="order",
                subject="Help",
                message="Body",
            )
        self.assertEqual(caught.exception.detail["code"], "CUSTOMER_INACTIVE")

    async def test_list_own_queries_and_validation(self) -> None:
        self.repository.queries.extend(
            [
                make_query(1),
                make_query(2, status="answered"),
                make_query(3, customer_id=99),
            ]
        )
        result = await self.service.list_queries(
            self.account,
            CustomerQueryListQuery(),
        )
        self.assertEqual(result["total"], 2)

        answered = await self.service.list_queries(
            self.account,
            CustomerQueryListQuery(status="answered"),
        )
        self.assertEqual([row["id"] for row in answered["items"]], [2])

        with self.assertRaises(Exception) as caught:
            await self.service.list_queries(
                self.account,
                CustomerQueryListQuery(status="bad"),
            )
        self.assertEqual(caught.exception.detail["code"], "VALIDATION_ERROR")

    async def test_ownership(self) -> None:
        self.repository.queries.append(make_query(1))
        with self.assertRaises(Exception) as caught:
            await self.service.get_query(self.other_account, 1)
        self.assertEqual(caught.exception.status_code, 404)

    async def test_customer_follow_up_reopens_answered(self) -> None:
        self.repository.queries.append(make_query(1, status="answered"))
        result = await self.service.add_customer_message(
            self.account,
            1,
            "Any update?",
        )
        self.assertEqual(result["message"]["body"], "Any update?")
        self.assertEqual(self.repository.queries[0].status, "open")
        history = self.repository.messages[-1]
        self.assertEqual(history.sender_type, "system")
        self.assertIn("answered", history.body)
        self.assertIn("open", history.body)
        self.assertEqual(
            self.audit.events[-1]["event_type"], "query.customer_message"
        )
        self.assertEqual(
            self.audit.events[-1]["metadata"]["message_id"],
            result["message"]["id"],
        )

    async def test_customer_follow_up_blocked_when_closed(self) -> None:
        self.repository.queries.append(make_query(1, status="closed"))
        with self.assertRaises(Exception) as caught:
            await self.service.add_customer_message(self.account, 1, "Hello")
        self.assertEqual(caught.exception.detail["code"], "QUERY_CLOSED")
        self.assertEqual(self.repository.messages, [])

    async def test_staff_list_and_internal_visibility(self) -> None:
        self.repository.queries.extend(
            [
                make_query(1, assigned_to=self.operator.id),
                make_query(2, category="delivery"),
            ]
        )
        self.repository.messages.append(make_message(1, is_internal=False))
        self.repository.messages.append(
            make_message(2, body="internal note", is_internal=True)
        )
        result = await self.service.staff_list_queries(StaffQueryListQuery())
        self.assertEqual(result["total"], 2)
        self.assertEqual(
            result["items"][0]["account_email"],
            self.account.email,
        )

        filtered = await self.service.staff_list_queries(
            StaffQueryListQuery(assigned_to=self.operator.id)
        )
        self.assertEqual([row["id"] for row in filtered["items"]], [1])

        detail = await self.service.staff_get_query(1)
        self.assertEqual(len(detail["query"]["messages"]), 2)
        self.assertTrue(detail["query"]["messages"][1]["is_internal"])

        customer_detail = await self.service.get_query(self.account, 1)
        self.assertEqual(len(customer_detail["query"]["messages"]), 1)

    async def test_staff_message(self) -> None:
        self.repository.queries.append(
            make_query(1, assigned_to=self.operator.id)
        )
        result = await self.service.add_staff_message(
            self.operator,
            1,
            "We are checking",
            is_internal=False,
        )
        self.assertEqual(result["message"]["sender_type"], "staff")
        self.assertFalse(result["message"]["is_internal"])
        self.assertEqual(
            self.audit.events[-1]["event_type"], "query.staff_message"
        )
        self.assertEqual(
            self.audit.events[-1]["metadata"]["message_id"],
            result["message"]["id"],
        )

    async def test_staff_message_blocked_when_closed(self) -> None:
        self.repository.queries.append(
            make_query(1, status="closed", assigned_to=self.operator.id)
        )
        with self.assertRaises(Exception) as caught:
            await self.service.add_staff_message(
                self.operator,
                1,
                "One more thing",
                is_internal=False,
            )
        self.assertEqual(caught.exception.detail["code"], "QUERY_CLOSED")

    async def test_status_transitions(self) -> None:
        self.repository.queries.append(
            make_query(1, assigned_to=self.operator.id)
        )
        result = await self.service.change_status(
            self.operator,
            1,
            "in_progress",
        )
        self.assertEqual(result["query"]["status"], "in_progress")
        self.assertEqual(
            self.audit.events[-1]["event_type"], "query.status.changed"
        )
        history = self.repository.messages[-1]
        self.assertEqual(history.sender_type, "system")
        self.assertFalse(history.is_internal)
        self.assertIn("in_progress", history.body)

        with self.assertRaises(Exception) as invalid:
            await self.service.change_status(self.operator, 1, "closed")
        self.assertEqual(invalid.exception.detail["code"], "INVALID_QUERY_TRANSITION")

        await self.service.change_status(self.operator, 1, "answered")
        idempotent = await self.service.change_status(self.operator, 1, "answered")
        self.assertEqual(idempotent["query"]["status"], "answered")

        with self.assertRaises(Exception) as reopen:
            await self.service.change_status(self.operator, 1, "open")
        self.assertEqual(reopen.exception.status_code, 409)

        closed = await self.service.change_status(self.admin, 1, "closed")
        self.assertEqual(closed["query"]["status"], "closed")
        reopened = await self.service.change_status(self.admin, 1, "open")
        self.assertEqual(reopened["query"]["status"], "open")

    async def test_assignment(self) -> None:
        self.repository.queries.append(make_query(1))
        result = await self.service.assign(self.admin, 1, self.operator.id)
        self.assertEqual(result["query"]["assigned_to"]["id"], self.operator.id)
        self.assertEqual(
            self.audit.events[-1]["event_type"], "query.assigned"
        )
        self.assertEqual(
            self.audit.events[-1]["metadata"]["to_user_id"],
            self.operator.id,
        )
        note = self.repository.messages[-1]
        self.assertEqual(note.sender_type, "system")
        self.assertTrue(note.is_internal)
        self.assertIn(self.operator.full_name, note.body)

        cleared = await self.service.assign(self.admin, 1, None)
        self.assertIsNone(cleared["query"]["assigned_to"])
        self.assertEqual(
            self.audit.events[-1]["event_type"], "query.unassigned"
        )
        self.assertEqual(self.repository.messages[-1].body, "Unassigned")

        with self.assertRaises(Exception) as invalid:
            await self.service.assign(self.admin, 1, 999)
        self.assertEqual(invalid.exception.detail["code"], "VALIDATION_ERROR")

    async def test_operator_cannot_mutate_unassigned_query(self) -> None:
        self.repository.queries.append(make_query(1))

        with self.assertRaises(Exception) as message:
            await self.service.add_staff_message(
                self.operator,
                1,
                "Trying to reply",
                is_internal=False,
            )
        self.assertEqual(message.exception.status_code, 403)
        self.assertEqual(
            message.exception.detail["code"],
            "QUERY_NOT_ASSIGNED",
        )

        with self.assertRaises(Exception) as status_change:
            await self.service.change_status(self.operator, 1, "in_progress")
        self.assertEqual(status_change.exception.status_code, 403)

        self.assertEqual(len(self.audit.denials), 2)
        first = self.audit.denials[0]
        self.assertEqual(first["event_type"], "query.access.denied")
        self.assertEqual(first["actor_user_id"], self.operator.id)
        self.assertEqual(first["resource_type"], "customer_query")
        self.assertEqual(first["resource_id"], 1)
        self.assertEqual(first["metadata"]["query_id"], 1)
        self.assertIsNone(first["metadata"]["assigned_to_user_id"])
        self.assertEqual(first["metadata"]["attempted_action"], "message")
        self.assertEqual(
            self.audit.denials[1]["metadata"]["attempted_action"],
            "status_change",
        )

    async def test_operator_cannot_mutate_another_operators_query(self) -> None:
        self.repository.queries.append(make_query(1, assigned_to=99))

        with self.assertRaises(Exception) as internal_note:
            await self.service.add_staff_message(
                self.operator,
                1,
                "Internal note",
                is_internal=True,
            )
        self.assertEqual(internal_note.exception.status_code, 403)
        self.assertEqual(
            self.audit.denials[-1]["metadata"]["assigned_to_user_id"],
            99,
        )
        self.assertEqual(
            self.audit.denials[-1]["metadata"]["attempted_action"],
            "internal_note",
        )

    async def test_admin_can_mutate_unassigned_query(self) -> None:
        self.repository.queries.append(make_query(1))

        message = await self.service.add_staff_message(
            self.admin,
            1,
            "Admin reply",
            is_internal=False,
        )
        self.assertEqual(message["message"]["sender_type"], "staff")

        changed = await self.service.change_status(self.admin, 1, "in_progress")
        self.assertEqual(changed["query"]["status"], "in_progress")
        self.assertEqual(self.audit.denials, [])

    async def test_operator_can_mutate_assigned_query(self) -> None:
        self.repository.queries.append(
            make_query(1, assigned_to=self.operator.id)
        )

        message = await self.service.add_staff_message(
            self.operator,
            1,
            "Assigned reply",
            is_internal=False,
        )
        self.assertEqual(message["message"]["sender_type"], "staff")

        changed = await self.service.change_status(
            self.operator,
            1,
            "in_progress",
        )
        self.assertEqual(changed["query"]["status"], "in_progress")
        self.assertEqual(self.audit.denials, [])

    async def test_missing_query(self) -> None:
        with self.assertRaises(Exception) as caught:
            await self.service.staff_get_query(999)
        self.assertEqual(caught.exception.status_code, 404)


class QueryApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.customer = make_customer()
        self.other_customer = make_customer(99, name="Other Dairy")
        self.account = make_account(password="x", activated=True)
        self.other_account = make_account(
            2,
            customer_id=99,
            email="other@example.com",
            password="x",
            activated=True,
        )
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")
        self.customers = FakeCustomerRepository(
            [self.customer, self.other_customer]
        )
        self.accounts = FakePortalAccountRepository(
            [self.account, self.other_account]
        )
        self.users = FakeUserRepository([self.admin, self.operator])
        self.audit = FakeAuditService()
        self.repository = FakeQueryRepository()
        self.repository.queries.append(make_query(1))
        self.repository.queries.append(make_query(2, customer_id=99))
        self.repository.messages.append(make_message(1))
        self.repository.messages.append(
            make_message(2, body="internal note", is_internal=True)
        )

        async def override_get_db():
            yield FakeSession(
                [self.account, self.other_account],
                [self.customer, self.other_customer],
                [self.admin, self.operator],
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_customer_query_repository] = (
            lambda: self.repository
        )
        app.dependency_overrides[get_customer_repository] = lambda: self.customers
        app.dependency_overrides[get_customer_portal_account_repository] = (
            lambda: self.accounts
        )
        app.dependency_overrides[get_user_repository] = lambda: self.users
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _customer_auth(self, account: Any | None = None) -> dict[str, str]:
        target = account or self.account
        token = create_customer_access_token(
            account_id=target.id,
            customer_id=target.customer_id,
            email=target.email,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{CUSTOMER_COOKIE}={token}",
        }

    def _staff_auth(self, user: Any) -> dict[str, str]:
        from app.core.config import settings

        token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            username=user.username,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}={token}",
        }

    async def test_customer_create_list_detail_and_follow_up(self) -> None:
        created = await self.client.post(
            "/api/v1/customer-portal/queries",
            headers=self._customer_auth(),
            json={
                "category": "order",
                "subject": "Delivery time",
                "message": "Can you deliver earlier?",
            },
        )
        self.assertEqual(created.status_code, 201)
        query = created.json()["query"]
        self.assertTrue(query["query_no"].startswith("QRY-"))
        self.assertEqual(query["messages"][0]["sender_type"], "customer")

        listed = await self.client.get(
            "/api/v1/customer-portal/queries",
            headers=self._customer_auth(),
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 2)

        detail = await self.client.get(
            "/api/v1/customer-portal/queries/1",
            headers=self._customer_auth(),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()["query"]["messages"]), 1)

        other = await self.client.get(
            "/api/v1/customer-portal/queries/2",
            headers=self._customer_auth(),
        )
        self.assertEqual(other.status_code, 404)

        self.repository.queries[0].status = "answered"
        follow_up = await self.client.post(
            "/api/v1/customer-portal/queries/1/messages",
            headers=self._customer_auth(),
            json={"message": "Any update?"},
        )
        self.assertEqual(follow_up.status_code, 201)
        self.assertEqual(self.repository.queries[0].status, "open")

        self.repository.queries[0].status = "closed"
        closed = await self.client.post(
            "/api/v1/customer-portal/queries/1/messages",
            headers=self._customer_auth(),
            json={"message": "Hello again"},
        )
        self.assertEqual(closed.status_code, 409)
        self.assertEqual(closed.json()["error"]["code"], "QUERY_CLOSED")

    async def test_customer_validation_and_staff_token_rejection(self) -> None:
        bad_category = await self.client.post(
            "/api/v1/customer-portal/queries",
            headers=self._customer_auth(),
            json={"category": "nope", "subject": "Hi", "message": "Body"},
        )
        self.assertEqual(bad_category.status_code, 400)

        empty_message = await self.client.post(
            "/api/v1/customer-portal/queries",
            headers=self._customer_auth(),
            json={"category": "other", "subject": "Hi", "message": "  "},
        )
        self.assertEqual(empty_message.status_code, 400)

        staff_token = self._staff_auth(self.admin)["Authorization"]
        staff = await self.client.get(
            "/api/v1/customer-portal/queries",
            headers={
                "Authorization": staff_token,
                "Cookie": self._customer_auth()["Cookie"],
            },
        )
        self.assertEqual(staff.status_code, 401)

    async def test_staff_list_detail_and_internal_note(self) -> None:
        listed = await self.client.get(
            "/api/v1/customer-queries",
            headers=self._staff_auth(self.operator),
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 2)

        detail = await self.client.get(
            "/api/v1/customer-queries/1",
            headers=self._staff_auth(self.operator),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()["query"]["messages"]), 2)

        self.repository.queries[0].assigned_to = self.operator.id
        note = await self.client.post(
            "/api/v1/customer-queries/1/messages",
            headers=self._staff_auth(self.operator),
            json={"message": "Customer called", "is_internal": True},
        )
        self.assertEqual(note.status_code, 201)
        self.assertTrue(note.json()["message"]["is_internal"])

        bad_flag = await self.client.post(
            "/api/v1/customer-queries/1/messages",
            headers=self._staff_auth(self.operator),
            json={"message": "x", "is_internal": "yes"},
        )
        self.assertEqual(bad_flag.status_code, 400)

    async def test_staff_status_and_assign_permissions(self) -> None:
        self.repository.queries[0].assigned_to = self.operator.id
        moved = await self.client.post(
            "/api/v1/customer-queries/1/status",
            headers=self._staff_auth(self.operator),
            json={"status": "in_progress"},
        )
        self.assertEqual(moved.status_code, 200)

        customer_detail = await self.client.get(
            "/api/v1/customer-portal/queries/1",
            headers=self._customer_auth(),
        )
        self.assertEqual(customer_detail.status_code, 200)
        visible = customer_detail.json()["query"]["messages"]
        self.assertEqual(visible[-1]["sender_type"], "system")
        self.assertNotIn("is_internal", visible[-1])

        forbidden = await self.client.post(
            "/api/v1/customer-queries/1/status",
            headers=self._staff_auth(self.operator),
            json={"status": "closed"},
        )
        self.assertEqual(forbidden.status_code, 409)

        assigned = await self.client.post(
            "/api/v1/customer-queries/1/assign",
            headers=self._staff_auth(self.admin),
            json={"assigned_to": self.operator.id},
        )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(
            assigned.json()["query"]["assigned_to"]["id"],
            self.operator.id,
        )

        operator_assign = await self.client.post(
            "/api/v1/customer-queries/1/assign",
            headers=self._staff_auth(self.operator),
            json={"assigned_to": self.operator.id},
        )
        self.assertEqual(operator_assign.status_code, 403)

    async def test_operator_assignment_enforcement_and_admin_bypass(self) -> None:
        denied_message = await self.client.post(
            "/api/v1/customer-queries/1/messages",
            headers=self._staff_auth(self.operator),
            json={"message": "Let me help", "is_internal": False},
        )
        self.assertEqual(denied_message.status_code, 403)
        self.assertEqual(
            denied_message.json()["error"]["code"],
            "QUERY_NOT_ASSIGNED",
        )

        denied_status = await self.client.post(
            "/api/v1/customer-queries/1/status",
            headers=self._staff_auth(self.operator),
            json={"status": "in_progress"},
        )
        self.assertEqual(denied_status.status_code, 403)
        self.assertEqual(len(self.audit.denials), 2)
        self.assertEqual(
            self.audit.denials[0]["metadata"]["attempted_action"],
            "message",
        )
        self.assertIsNone(
            self.audit.denials[0]["metadata"]["assigned_to_user_id"]
        )
        self.assertEqual(
            self.audit.denials[1]["metadata"]["attempted_action"],
            "status_change",
        )

        admin_message = await self.client.post(
            "/api/v1/customer-queries/1/messages",
            headers=self._staff_auth(self.admin),
            json={"message": "Admin reply", "is_internal": False},
        )
        self.assertEqual(admin_message.status_code, 201)

        admin_status = await self.client.post(
            "/api/v1/customer-queries/1/status",
            headers=self._staff_auth(self.admin),
            json={"status": "in_progress"},
        )
        self.assertEqual(admin_status.status_code, 200)

        assigned = await self.client.post(
            "/api/v1/customer-queries/1/assign",
            headers=self._staff_auth(self.admin),
            json={"assigned_to": self.operator.id},
        )
        self.assertEqual(assigned.status_code, 200)

        operator_message = await self.client.post(
            "/api/v1/customer-queries/1/messages",
            headers=self._staff_auth(self.operator),
            json={"message": "Now assigned", "is_internal": False},
        )
        self.assertEqual(operator_message.status_code, 201)

        operator_status = await self.client.post(
            "/api/v1/customer-queries/1/status",
            headers=self._staff_auth(self.operator),
            json={"status": "answered"},
        )
        self.assertEqual(operator_status.status_code, 200)

    async def test_staff_access_required_and_openapi(self) -> None:
        anonymous = await self.client.get("/api/v1/customer-queries")
        self.assertEqual(anonymous.status_code, 401)

        customer_token = self._customer_auth()["Authorization"]
        customer = await self.client.get(
            "/api/v1/customer-queries",
            headers={"Authorization": customer_token},
        )
        self.assertEqual(customer.status_code, 401)

        response = await self.client.get("/api/v1/docs/openapi.json")
        paths = response.json()["paths"]
        for path in (
            "/api/v1/customer-portal/queries",
            "/api/v1/customer-portal/queries/{query_id}",
            "/api/v1/customer-portal/queries/{query_id}/messages",
            "/api/v1/customer-queries",
            "/api/v1/customer-queries/{query_id}",
            "/api/v1/customer-queries/{query_id}/messages",
            "/api/v1/customer-queries/{query_id}/status",
            "/api/v1/customer-queries/{query_id}/assign",
        ):
            self.assertIn(path, paths)
