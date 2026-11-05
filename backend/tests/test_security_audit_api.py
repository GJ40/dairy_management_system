from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

import httpx

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import get_security_audit_service
from app.core.security import create_access_token, create_customer_access_token
from app.db.session import get_db
from app.main import app
from app.models.security_audit_event import SecurityAuditEvent
from app.services.security_audit_service import SecurityAuditService
from tests.test_auth_and_users import FakeSession, make_user


class FakeAuditRepository:
    def __init__(self, events: list[SecurityAuditEvent]) -> None:
        self.events = events
        self.last_list_kwargs: dict[str, Any] | None = None

    async def list_and_count(self, **kwargs: Any):
        self.last_list_kwargs = kwargs
        page = int(kwargs["page"])
        page_size = int(kwargs["page_size"])
        start = (page - 1) * page_size
        return self.events[start : start + page_size], len(self.events)

    async def get_by_id(self, event_id: int) -> SecurityAuditEvent | None:
        return next((event for event in self.events if event.id == event_id), None)

    async def resolve_actor_labels(
        self, events: list[SecurityAuditEvent]
    ) -> dict[tuple[str, int], tuple[str | None, str | None]]:
        return {("staff", 2): ("Milk Operator", "operator@example.com")}


def make_event(
    event_id: int = 1,
    *,
    event_type: str = "query.access.denied",
    outcome: str = "denied",
    severity: str = "warning",
    actor_type: str = "staff",
    actor_user_id: int | None = 2,
    actor_account_id: int | None = None,
    ip_address: str | None = "203.0.113.9",
    request_id: str = "a" * 32,
    path: str = "/api/v1/customer-queries/1/messages",
    resource_type: str = "customer_query",
    resource_id: str = "1",
    metadata: dict[str, Any] | None = None,
) -> SecurityAuditEvent:
    return SecurityAuditEvent(
        id=event_id,
        created_at=datetime(2026, 11, 4, 10, 30, tzinfo=timezone.utc).replace(
            tzinfo=None
        ),
        event_type=event_type,
        outcome=outcome,
        severity=severity,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_account_id=actor_account_id,
        ip_address=ip_address,
        user_agent="pytest-agent",
        request_id=request_id,
        http_method="POST",
        path=path,
        resource_type=resource_type,
        resource_id=resource_id,
        reason_code=None,
        event_metadata=metadata
        or {
            "query_id": 1,
            "assigned_to_user_id": None,
            "attempted_action": "message",
        },
    )


class SecurityAuditApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(
            user_id=2,
            email="operator@example.com",
            username="operator",
            full_name="Milk Operator",
            role="operator",
        )
        self.current_user = self.admin
        self.events = [
            make_event(1),
            make_event(
                2,
                event_type="auth.login.failed",
                outcome="failure",
                actor_type="anonymous",
                actor_user_id=None,
                resource_type="staff_user",
                resource_id=None,
                metadata={"scope": "staff", "reason_code": "bad_password"},
            ),
        ]
        self.repository = FakeAuditRepository(self.events)

        async def override_get_db():
            yield FakeSession(self.current_user)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_security_audit_service] = lambda: (
            SecurityAuditService(self.repository)  # type: ignore[arg-type]
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self, user: Any | None = None) -> dict[str, str]:
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

    async def test_admin_lists_and_serializes_events(self) -> None:
        response = await self.client.get(
            "/api/v1/security-audit",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 20)
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["items"]), 2)
        event = body["items"][0]
        self.assertEqual(event["event_type"], "query.access.denied")
        self.assertEqual(event["category"], "query")
        self.assertEqual(event["action"], "/api/v1/customer-queries/1/messages")
        self.assertEqual(event["actor_user_id"], 2)
        self.assertEqual(event["actor_name"], "Milk Operator")
        self.assertEqual(event["actor_email"], "operator@example.com")
        self.assertEqual(event["target_type"], "customer_query")
        self.assertEqual(event["target_id"], "1")
        self.assertEqual(event["ip_address"], "203.0.113.9")
        self.assertEqual(
            event["created_at"],
            "2026-11-04T10:30:00.000Z",
        )
        self.assertNotIn("password", event)
        self.assertNotIn("token", event)

    async def test_admin_filters_are_forwarded_and_normalized(self) -> None:
        response = await self.client.get(
            "/api/v1/security-audit",
            params={
                "event_type": "query.access.denied",
                "category": "query",
                "search": "denied",
                "actor_type": "staff",
                "actor_user_id": 2,
                "severity": "warning",
                "outcome": "denied",
                "target_type": "customer_query",
                "target_id": "1",
                "request_id": "a" * 32,
                "ip_address": "203.0.113.9",
                "from": "2026-11-04T00:00:00Z",
                "to": "2026-11-04T23:59:59Z",
                "page": 1,
                "page_size": 10,
            },
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        kwargs = self.repository.last_list_kwargs
        self.assertIsNotNone(kwargs)
        assert kwargs is not None
        self.assertEqual(kwargs["event_type"], "query.access.denied")
        self.assertEqual(kwargs["category"], "query")
        self.assertEqual(kwargs["search"], "denied")
        self.assertEqual(kwargs["actor_type"], "staff")
        self.assertEqual(kwargs["actor_user_id"], 2)
        self.assertEqual(kwargs["severity"], "warning")
        self.assertEqual(kwargs["outcome"], "denied")
        self.assertEqual(kwargs["resource_type"], "customer_query")
        self.assertEqual(kwargs["resource_id"], "1")
        self.assertEqual(kwargs["request_id"], "a" * 32)
        self.assertEqual(kwargs["ip_address"], "203.0.113.9")
        self.assertEqual(kwargs["page_size"], 10)
        self.assertEqual(
            kwargs["from_created_at"], datetime(2026, 11, 4, 0, 0, 0)
        )
        self.assertEqual(
            kwargs["to_created_at"], datetime(2026, 11, 4, 23, 59, 59)
        )

    async def test_admin_gets_event_detail(self) -> None:
        response = await self.client.get(
            "/api/v1/security-audit/1",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        event = response.json()["event"]
        self.assertEqual(event["id"], 1)
        self.assertEqual(event["metadata"]["attempted_action"], "message")
        self.assertEqual(event["request_id"], "a" * 32)

    async def test_missing_event_returns_404(self) -> None:
        response = await self.client.get(
            "/api/v1/security-audit/999",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["message"],
            "Audit event with id 999 not found",
        )

    async def test_operator_is_forbidden(self) -> None:
        self.current_user = self.operator
        response = await self.client.get(
            "/api/v1/security-audit",
            headers=self._auth(self.operator),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"]["message"],
            "Access denied: Requires one of [admin] role",
        )

    async def test_customer_token_is_rejected(self) -> None:
        token = create_customer_access_token(
            account_id=1,
            customer_id=1,
            email="customer@example.com",
        )
        response = await self.client.get(
            "/api/v1/security-audit",
            headers={
                "Authorization": f"Bearer {token}",
                "Cookie": f"{settings.customer_refresh_cookie_name}=test-session",
            },
        )
        self.assertEqual(response.status_code, 401)

    async def test_page_size_is_bounded(self) -> None:
        response = await self.client.get(
            "/api/v1/security-audit?page_size=101",
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    async def test_reversed_date_range_is_rejected(self) -> None:
        response = await self.client.get(
            "/api/v1/security-audit",
            params={
                "from": "2026-11-05T00:00:00Z",
                "to": "2026-11-04T00:00:00Z",
            },
            headers=self._auth(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["message"],
            "from: Must be before or equal to to",
        )


if __name__ == "__main__":
    unittest.main()
