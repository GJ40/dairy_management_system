from __future__ import annotations

import unittest
from datetime import timedelta
from typing import Any

import httpx

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_customer_order_repository,
    get_customer_portal_account_repository,
    get_customer_query_repository,
    get_customer_repository,
    get_invoice_repository,
    get_user_repository,
)
from app.core.security import create_access_token, create_customer_access_token
from app.db.session import get_db
from app.main import app
from app.utils.time import business_now
from tests.test_auth_and_users import FakeUserRepository
from tests.test_customer_portal_auth import (
    CUSTOMER_COOKIE,
    FakeCustomerRepository,
    FakePortalAccountRepository,
    FakeSession,
    make_account,
    make_customer,
)
from tests.test_customer_portal_invoices import (
    FakeInvoiceRepository,
    make_invoice,
)
from tests.test_customer_portal_orders import FakeOrderRepository
from tests.test_customer_portal_queries import (
    FakeQueryRepository,
    make_message,
    make_query,
)
from tests.test_customers_and_sales import make_user


class SecurityProbeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.customer = make_customer()
        self.account = make_account(password="x", activated=True)
        self.customers = FakeCustomerRepository([self.customer])
        self.accounts = FakePortalAccountRepository([self.account])
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")
        self.users = FakeUserRepository([self.admin, self.operator])
        self.orders = FakeOrderRepository()
        self.invoices = FakeInvoiceRepository([make_invoice(1)])
        self.queries = FakeQueryRepository()
        self.queries.queries.append(make_query(1, status="open"))
        self.queries.messages.append(make_message(1))

        async def override_get_db():
            yield FakeSession(
                [self.account],
                [self.customer],
                [self.admin, self.operator],
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_customer_repository] = lambda: self.customers
        app.dependency_overrides[get_customer_order_repository] = lambda: self.orders
        app.dependency_overrides[get_invoice_repository] = lambda: self.invoices
        app.dependency_overrides[get_customer_query_repository] = lambda: self.queries
        app.dependency_overrides[get_customer_portal_account_repository] = (
            lambda: self.accounts
        )
        app.dependency_overrides[get_user_repository] = lambda: self.users
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _customer_auth(self) -> dict[str, str]:
        token = create_customer_access_token(
            account_id=self.account.id,
            customer_id=self.account.customer_id,
            email=self.account.email,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{CUSTOMER_COOKIE}={token}",
        }

    def _staff_auth(self, user: Any) -> dict[str, str]:
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

    async def test_customer_token_is_rejected_on_staff_surfaces(self) -> None:
        headers = self._customer_auth()
        probes = (
            ("get", "/api/v1/customers", None),
            ("get", "/api/v1/customer-orders", None),
            ("get", "/api/v1/customer-queries", None),
            ("get", "/api/v1/users", None),
            ("get", "/api/v1/expenses", None),
            ("patch", "/api/v1/invoices/1/payment", {"amount": "10.00"}),
        )
        for method, path, body in probes:
            with self.subTest(path=path):
                kwargs: dict[str, Any] = {"headers": headers}
                if body is not None:
                    kwargs["json"] = body
                response = await getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401, response.text)

    async def test_staff_token_is_rejected_on_customer_surfaces(self) -> None:
        headers = self._staff_auth(self.admin)
        probes = (
            ("get", "/api/v1/customer-portal/dashboard"),
            ("get", "/api/v1/customer-portal/profile"),
            ("get", "/api/v1/customer-portal/orders"),
            ("get", "/api/v1/customer-portal/queries/1"),
            ("get", "/api/v1/customer-portal/invoices/1/pdf"),
        )
        for method, path in probes:
            with self.subTest(path=path):
                response = await getattr(self.client, method)(path, headers=headers)
                self.assertEqual(response.status_code, 401, response.text)

    async def test_operator_is_blocked_from_admin_only_surfaces(self) -> None:
        headers = self._staff_auth(self.operator)
        probes = (
            ("get", "/api/v1/users"),
            ("get", "/api/v1/expenses"),
            ("get", "/api/v1/reports/profit"),
            (
                "post",
                "/api/v1/customer-portal-accounts",
                {"customer_id": 4, "email": "new@example.com"},
            ),
        )
        for probe in probes:
            method, path = probe[0], probe[1]
            body = probe[2] if len(probe) > 2 else None
            with self.subTest(path=path):
                kwargs: dict[str, Any] = {"headers": headers}
                if body is not None:
                    kwargs["json"] = body
                response = await getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 403, response.text)

    async def test_customer_cannot_inject_query_or_message_fields(self) -> None:
        created = await self.client.post(
            "/api/v1/customer-portal/queries",
            headers=self._customer_auth(),
            json={
                "category": "billing",
                "subject": "Invoice question",
                "message": "Please explain the charges.",
                "status": "closed",
                "assigned_to": 1,
                "customer_id": 99,
                "query_no": "QRY-INJECTED",
                "is_internal": True,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        query = created.json()["query"]
        self.assertEqual(query["status"], "open")
        self.assertTrue(query["query_no"].startswith("QRY-"))
        self.assertNotIn("assigned_to", query)
        self.assertNotIn("is_internal", query)

        replied = await self.client.post(
            f"/api/v1/customer-portal/queries/{query['id']}/messages",
            headers=self._customer_auth(),
            json={
                "message": "Follow-up",
                "is_internal": True,
                "sender_type": "staff",
                "sender_user_id": 1,
                "status": "closed",
            },
        )
        self.assertEqual(replied.status_code, 201, replied.text)
        message = replied.json()["message"]
        self.assertEqual(message["sender_type"], "customer")
        self.assertNotIn("is_internal", message)
        self.assertNotIn("sender_user_id", message)

    async def test_customer_order_mass_assignment_is_ignored(self) -> None:
        target = (business_now().date() + timedelta(days=1)).isoformat()
        created = await self.client.post(
            "/api/v1/customer-portal/orders",
            headers=self._customer_auth(),
            json={
                "quantity_litres": "5.00",
                "requested_date": target,
                "customer_id": 99,
                "rate_snapshot": "1.00",
                "estimated_total": "5.00",
                "status": "fulfilled",
                "reviewed_by": 1,
                "reason": "injected",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        order = created.json()["order"]
        self.assertEqual(order["status"], "submitted")
        self.assertEqual(order["rate_snapshot"], "60.00")
        self.assertEqual(order["estimated_total"], "300.00")
        self.assertIsNone(order["reason"])

    async def test_profile_exposes_no_mutation_route(self) -> None:
        response = await self.client.patch(
            "/api/v1/customer-portal/profile",
            headers=self._customer_auth(),
            json={"phone": "9999999999"},
        )
        # The API maps 405 to 404 NOT_FOUND by convention (app/core/errors.py).
        self.assertEqual(response.status_code, 404)

    async def test_deleted_and_foreign_records_stay_hidden(self) -> None:
        self.invoices.invoices[0].is_deleted = True
        invoice = await self.client.get(
            "/api/v1/customer-portal/invoices/1",
            headers=self._customer_auth(),
        )
        self.assertEqual(invoice.status_code, 404)

        foreign_query = await self.client.get(
            f"/api/v1/customer-portal/queries/{self.queries.queries[0].id}",
            headers=self._customer_auth(),
        )
        self.assertEqual(foreign_query.status_code, 200)

        self.queries.queries[0].customer_id = 99
        hidden = await self.client.get(
            f"/api/v1/customer-portal/queries/{self.queries.queries[0].id}",
            headers=self._customer_auth(),
        )
        self.assertEqual(hidden.status_code, 404)


if __name__ == "__main__":
    unittest.main()
