from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx

import app.models  # noqa: F401
from app.core.dependencies import (
    get_customer_order_repository,
    get_customer_query_repository,
    get_customer_repository,
    get_invoice_repository,
)
from app.core.security import create_access_token, create_customer_access_token
from app.db.session import get_db
from app.main import app
from app.services.customer_dashboard_service import CustomerDashboardService
from tests.test_customer_portal_auth import (
    CUSTOMER_COOKIE,
    FakeSession,
    make_account,
    make_customer,
)
from tests.test_customer_portal_invoices import (
    FakeBillingCustomerRepository,
    FakeInvoiceRepository,
    make_invoice,
)

TODAY = date(2026, 10, 30)
CREATED = datetime(2026, 10, 30, 9, 0, 0)


def make_order(
    order_id: int = 1,
    *,
    customer_id: int = 4,
    order_no: str = "ORD-20261030-1A2B",
    status: str = "submitted",
    quantity: str = "12.50",
    rate: str = "60.00",
    total: str = "750.00",
) -> SimpleNamespace:
    stamp = CREATED + timedelta(minutes=order_id)
    return SimpleNamespace(
        id=order_id,
        order_no=order_no,
        customer_id=customer_id,
        account_id=1,
        status=status,
        requested_date=TODAY + timedelta(days=1),
        quantity_litres=Decimal(quantity),
        rate_snapshot=Decimal(rate),
        estimated_total=Decimal(total),
        note=None,
        reviewed_at=None,
        reason=None,
        created_at=stamp,
        updated_at=stamp,
        is_deleted=False,
    )


class FakeDashboardOrderRepository:
    def __init__(self, orders: list[SimpleNamespace] | None = None) -> None:
        self.orders = list(orders or [])
        self.last_page_size: int | None = None

    async def list_and_count(
        self,
        *,
        customer_id: int,
        page: int,
        page_size: int,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ):
        self.last_page_size = page_size
        rows = [
            row
            for row in self.orders
            if row.customer_id == customer_id and not row.is_deleted
        ]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)


class FakeDashboardQueryRepository:
    def __init__(self, open_queries: int = 0) -> None:
        self.open_queries = open_queries
        self.customer_ids: list[int] = []

    async def count_open_owned(self, customer_id: int) -> int:
        self.customer_ids.append(customer_id)
        return self.open_queries


class CustomerDashboardServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.account = make_account(password="x", activated=True)
        self.customers = FakeBillingCustomerRepository([self.customer])
        self.orders = FakeDashboardOrderRepository(
            [make_order(order_id) for order_id in range(1, 8)]
        )
        self.invoices = FakeInvoiceRepository(
            [make_invoice(invoice_id) for invoice_id in range(1, 8)]
        )
        self.queries = FakeDashboardQueryRepository(open_queries=2)
        self.service = CustomerDashboardService(
            self.customers,
            self.orders,
            self.invoices,
            self.queries,
        )

    async def test_dashboard_shape_and_recent_limits(self) -> None:
        result = await self.service.get_dashboard(self.account)

        self.assertEqual(
            set(result),
            {
                "customer",
                "balance",
                "recent_orders",
                "recent_invoices",
                "open_queries",
            },
        )
        self.assertEqual(
            set(result["customer"]),
            {"id", "name", "phone", "address", "rate_per_litre"},
        )
        self.assertEqual(result["customer"]["rate_per_litre"], "60.00")
        self.assertEqual(
            result["balance"],
            {
                "total_sales_amount": "1500.00",
                "total_paid_amount": "250.00",
                "outstanding_balance": "1250.00",
            },
        )
        self.assertEqual(len(result["recent_orders"]), 5)
        self.assertEqual(len(result["recent_invoices"]), 5)
        self.assertEqual(result["recent_orders"][0]["id"], 7)
        self.assertEqual(result["recent_invoices"][0]["id"], 7)
        self.assertEqual(result["open_queries"], 2)
        self.assertEqual(self.orders.last_page_size, 5)
        self.assertEqual(self.queries.customer_ids, [self.customer.id])
        self.assertNotIn("is_active", result["customer"])

    async def test_dashboard_is_scoped_to_the_account_customer(self) -> None:
        other = make_order(99, customer_id=99, order_no="ORD-OTHER")
        self.orders.orders.append(other)

        result = await self.service.get_dashboard(self.account)

        self.assertNotIn(
            "ORD-OTHER",
            [row["order_no"] for row in result["recent_orders"]],
        )

    async def test_inactive_customer_is_rejected(self) -> None:
        self.customers.customers = [make_customer(is_active=False)]

        with self.assertRaises(Exception) as caught:
            await self.service.get_dashboard(self.account)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["code"], "ACCOUNT_INACTIVE")

        with self.assertRaises(Exception) as profile_error:
            await self.service.get_profile(self.account)
        self.assertEqual(profile_error.exception.status_code, 403)

    async def test_profile_returns_account_and_customer(self) -> None:
        result = await self.service.get_profile(self.account)

        self.assertEqual(set(result), {"account", "customer"})
        self.assertEqual(result["account"]["email"], self.account.email)
        self.assertEqual(result["account"]["customer_id"], self.customer.id)
        self.assertEqual(result["account"]["customer"]["name"], self.customer.name)
        self.assertEqual(result["customer"]["rate_per_litre"], "60.00")
        for forbidden in ("password_hash", "activation_token_hash", "is_deleted"):
            self.assertNotIn(forbidden, result["account"])
            self.assertNotIn(forbidden, result["customer"])


class CustomerDashboardApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.customer = make_customer()
        self.account = make_account(password="x", activated=True)
        self.customers = FakeBillingCustomerRepository([self.customer])
        self.orders = FakeDashboardOrderRepository([make_order(1)])
        self.invoices = FakeInvoiceRepository([make_invoice(1)])
        self.queries = FakeDashboardQueryRepository(open_queries=1)

        async def override_get_db():
            yield FakeSession([self.account], [self.customer])

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_customer_repository] = lambda: self.customers
        app.dependency_overrides[get_customer_order_repository] = lambda: self.orders
        app.dependency_overrides[get_invoice_repository] = lambda: self.invoices
        app.dependency_overrides[get_customer_query_repository] = lambda: self.queries
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self) -> dict[str, str]:
        token = create_customer_access_token(
            account_id=self.account.id,
            customer_id=self.account.customer_id,
            email=self.account.email,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{CUSTOMER_COOKIE}={token}",
        }

    async def test_dashboard_and_profile(self) -> None:
        dashboard = await self.client.get(
            "/api/v1/customer-portal/dashboard",
            headers=self._auth(),
        )
        self.assertEqual(dashboard.status_code, 200)
        body = dashboard.json()
        self.assertEqual(body["customer"]["id"], self.customer.id)
        self.assertEqual(body["recent_orders"][0]["order_no"], "ORD-20261030-1A2B")
        self.assertEqual(body["recent_invoices"][0]["invoice_no"], "INV-20261030-1A2B")
        self.assertEqual(body["open_queries"], 1)

        profile = await self.client.get(
            "/api/v1/customer-portal/profile",
            headers=self._auth(),
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["customer"]["name"], self.customer.name)

    async def test_requires_a_customer_session(self) -> None:
        anonymous = await self.client.get("/api/v1/customer-portal/dashboard")
        self.assertEqual(anonymous.status_code, 401)

        staff_token = create_access_token(
            user_id=1,
            email="admin@example.com",
            role="admin",
            username="admin",
        )
        staff = await self.client.get(
            "/api/v1/customer-portal/profile",
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        self.assertEqual(staff.status_code, 401)

    async def test_openapi_documents_the_routes(self) -> None:
        response = await self.client.get("/api/v1/docs/openapi.json")
        paths = response.json()["paths"]
        self.assertIn("/api/v1/customer-portal/dashboard", paths)
        self.assertIn("/api/v1/customer-portal/profile", paths)


if __name__ == "__main__":
    unittest.main()
