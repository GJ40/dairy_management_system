from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import HTTPException

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_customer_order_repository,
    get_customer_repository,
    get_order_email_dispatch,
    get_security_audit_service,
)
from app.core.security import create_customer_access_token
from app.db.session import get_db
from app.main import app
from app.models.customer_portal_account import CustomerPortalAccount
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer_orders import (
    CustomerOrderQuery,
    parse_order_quantity,
)
from app.services.customer_order_service import CustomerOrderService
from app.utils.time import business_now
from tests.audit_helpers import FakeAuditService
from tests.test_customer_portal_auth import (
    CUSTOMER_COOKIE,
    FakeCustomerRepository,
    FakeSession,
    make_account,
    make_customer,
)

CREATED = datetime(2026, 10, 30, 12, 0, 0)
TODAY = business_now().date()


def make_order(
    order_id: int = 1,
    *,
    customer_id: int = 4,
    account_id: int = 1,
    order_no: str = "ORD-20261030-1A2B",
    status: str = "submitted",
    requested_date: date | None = None,
    quantity: str = "12.50",
    rate: str = "60.00",
    total: str = "750.00",
    note: str | None = None,
    reason: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=order_id,
        order_no=order_no,
        customer_id=customer_id,
        account_id=account_id,
        requested_date=requested_date or TODAY + timedelta(days=1),
        quantity_litres=Decimal(quantity),
        rate_snapshot=Decimal(rate),
        estimated_total=Decimal(total),
        note=note,
        status=status,
        reviewed_by=None,
        reviewed_at=None,
        reason=reason,
        is_deleted=False,
        created_at=CREATED + timedelta(minutes=order_id),
        updated_at=CREATED + timedelta(minutes=order_id),
    )


class FakeOrderRepository:
    def __init__(self) -> None:
        self.orders: list[SimpleNamespace] = []
        self.events: list[SimpleNamespace] = []
        self.sales: dict[int, Any] = {}
        self.invoices: dict[int, Any] = {}
        self.commits = 0
        self.rollbacks = 0
        self._order_id = 1
        self._event_id = 1

    async def get_by_id(self, order_id: int, *, include_deleted: bool = False):
        return next((row for row in self.orders if row.id == order_id), None)

    async def get_owned(self, order_id: int, customer_id: int):
        return next(
            (
                row
                for row in self.orders
                if row.id == order_id and row.customer_id == customer_id
            ),
            None,
        )

    async def find_by_order_no(self, order_no: str):
        return next((row for row in self.orders if row.order_no == order_no), None)

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
        rows = [row for row in self.orders if row.customer_id == customer_id]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if from_date is not None:
            rows = [row for row in rows if row.requested_date >= from_date]
        if to_date is not None:
            rows = [row for row in rows if row.requested_date <= to_date]
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    async def reserved_litres(self, *, customer_id: int, requested_date: date):
        total = sum(
            (
                row.quantity_litres
                for row in self.orders
                if row.customer_id == customer_id
                and row.requested_date == requested_date
                and row.status in ("submitted", "approved")
            ),
            Decimal("0.00"),
        )
        return total

    async def total_approved_litres(self, requested_date: date):
        return sum(
            (
                row.quantity_litres
                for row in self.orders
                if row.requested_date == requested_date
                and row.status == "approved"
                and not row.is_deleted
            ),
            Decimal("0.00"),
        )

    async def list_all_and_count(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        customer_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ):
        rows = [row for row in self.orders if not row.is_deleted]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if customer_id is not None:
            rows = [row for row in rows if row.customer_id == customer_id]
        if from_date is not None:
            rows = [row for row in rows if row.requested_date >= from_date]
        if to_date is not None:
            rows = [row for row in rows if row.requested_date <= to_date]
        if search is not None:
            needle = search.strip().lower()
            rows = [row for row in rows if needle in row.order_no.lower()]
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    async def get_account(self, account_id: int):
        return SimpleNamespace(id=account_id, email="customer@example.com")

    async def create(
        self,
        *,
        order_no: str,
        customer_id: int,
        account_id: int,
        requested_date: date,
        quantity_litres: Decimal,
        rate_snapshot: Decimal,
        estimated_total: Decimal,
        note: str | None,
    ):
        order = make_order(
            self._order_id,
            customer_id=customer_id,
            account_id=account_id,
            order_no=order_no,
            requested_date=requested_date,
            quantity=str(quantity_litres),
            rate=str(rate_snapshot),
            total=str(estimated_total),
            note=note,
        )
        self._order_id += 1
        self.orders.append(order)
        return order

    async def add_event(
        self,
        *,
        order_id: int,
        from_status: str | None,
        to_status: str,
        actor_type: str,
        actor_account_id: int | None = None,
        actor_user_id: int | None = None,
        reason: str | None = None,
    ):
        event = SimpleNamespace(
            id=self._event_id,
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            actor_account_id=actor_account_id,
            actor_user_id=actor_user_id,
            reason=reason,
            created_at=CREATED + timedelta(seconds=self._event_id),
        )
        self._event_id += 1
        self.events.append(event)
        return event

    async def list_events(self, order_id: int):
        return [event for event in self.events if event.order_id == order_id]

    async def get_sale_by_order_id(self, order_id: int):
        return self.sales.get(order_id)

    async def get_invoice_for_sale(self, sale_id: int):
        return self.invoices.get(sale_id)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, order: Any) -> None:
        return None


def tomorrow() -> date:
    return TODAY + timedelta(days=1)


class OrderServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.customers = FakeCustomerRepository([self.customer])
        self.repository = FakeOrderRepository()
        self.service = CustomerOrderService(self.repository, self.customers)
        self.account = make_account(password="x", activated=True)

    async def _create(self, quantity: str = "12.50", **kwargs):
        return await self.service.create(
            self.account,
            quantity_litres=Decimal(quantity),
            requested_date=kwargs.pop("requested_date", tomorrow()),
            note=kwargs.pop("note", "Evening pickup"),
        )

    async def test_create_snapshots_rate_and_total(self) -> None:
        result = await self._create()
        order = self.repository.orders[0]
        self.assertRegex(order.order_no, r"^ORD-\d{8}-[0-9A-F]{4}$")
        self.assertEqual(order.status, "submitted")
        self.assertEqual(order.rate_snapshot, Decimal("60.00"))
        self.assertEqual(order.estimated_total, Decimal("750.00"))
        self.assertEqual(order.note, "Evening pickup")
        self.assertEqual(result["order"]["quantity_litres"], "12.50")
        self.assertNotIn("customer_id", result["order"])
        self.assertNotIn("account_id", result["order"])
        self.assertEqual(self.repository.events[0].actor_type, "customer")
        self.assertEqual(self.repository.events[0].to_status, "submitted")

    async def test_rate_change_does_not_alter_existing_order(self) -> None:
        await self._create()
        self.customer.rate_per_litre = Decimal("75.00")
        await self._create("2.00")
        self.assertEqual(self.repository.orders[0].rate_snapshot, Decimal("60.00"))
        self.assertEqual(self.repository.orders[1].rate_snapshot, Decimal("75.00"))

    async def test_order_create_and_cancel_audit_events(self) -> None:
        audit = FakeAuditService()
        service = CustomerOrderService(  # type: ignore[arg-type]
            self.repository,
            self.customers,
            audit=audit,
        )
        await service.create(
            self.account,
            quantity_litres=Decimal("12.50"),
            requested_date=tomorrow(),
            note=None,
        )
        order_id = self.repository.orders[0].id
        self.assertEqual(audit.records[-1]["event_type"], "order.created")
        self.assertEqual(audit.records[-1]["metadata"]["order_id"], order_id)
        self.assertEqual(audit.records[-1]["actor_account_id"], self.account.id)

        await service.cancel(self.account, order_id, "changed mind")
        self.assertEqual(audit.records[-1]["event_type"], "order.cancelled")
        self.assertEqual(
            audit.records[-1]["metadata"]["from_status"], "submitted"
        )

    async def test_quantity_limits(self) -> None:
        for quantity, code in (
            ("0.00", "INVALID_QUANTITY"),
            ("0.50", "ORDER_LIMIT_EXCEEDED"),
            ("500.01", "ORDER_LIMIT_EXCEEDED"),
        ):
            with self.subTest(quantity=quantity):
                with self.assertRaises(HTTPException) as error:
                    await self._create(quantity)
                self.assertEqual(error.exception.detail["code"], code)
        for index, quantity in enumerate(("1.00", "500.00")):
            with self.subTest(quantity=quantity):
                await self._create(
                    quantity,
                    requested_date=TODAY + timedelta(days=index + 2),
                )

    async def test_quantity_must_have_at_most_two_decimals(self) -> None:
        for value in ("1.001", 1.234, True, None, "abc", "NaN"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_order_quantity(value)
        self.assertEqual(parse_order_quantity("12.5"), Decimal("12.50"))
        self.assertEqual(parse_order_quantity(12), Decimal("12.00"))

    async def test_requested_date_window_is_today_to_today_plus_14(self) -> None:
        await self._create(requested_date=TODAY)
        await self._create(
            requested_date=TODAY + timedelta(days=settings.customer_order_window_days)
        )
        for requested in (
            TODAY - timedelta(days=1),
            TODAY + timedelta(days=settings.customer_order_window_days + 1),
        ):
            with self.subTest(requested=requested):
                with self.assertRaises(HTTPException) as error:
                    await self._create(requested_date=requested)
                self.assertEqual(
                    error.exception.detail["code"], "INVALID_REQUESTED_DATE"
                )

    async def test_daily_cap_counts_submitted_and_approved(self) -> None:
        self.repository.orders.append(
            make_order(90, status="approved", quantity="495.00", total="29700.00")
        )
        with self.assertRaises(HTTPException) as error:
            await self._create("6.00")
        self.assertEqual(
            error.exception.detail["code"], "ORDER_DAILY_LIMIT_EXCEEDED"
        )

        await self._create("5.00", requested_date=make_order().requested_date)
        self.assertEqual(len(self.repository.orders), 2)

    async def test_cancelled_orders_do_not_consume_daily_cap(self) -> None:
        self.repository.orders.append(
            make_order(90, status="cancelled", quantity="495.00")
        )
        await self._create("500.00")
        self.assertEqual(len(self.repository.orders), 2)

    async def test_inactive_customer_or_missing_rate_is_rejected(self) -> None:
        self.customer.is_active = False
        with self.assertRaises(HTTPException) as error:
            await self._create()
        self.assertEqual(error.exception.detail["code"], "CUSTOMER_INACTIVE")

        self.customer.is_active = True
        self.customer.rate_per_litre = Decimal("0.00")
        with self.assertRaises(HTTPException) as zero_rate:
            await self._create()
        self.assertEqual(zero_rate.exception.detail["code"], "VALIDATION_ERROR")

    async def test_list_filters_and_pagination(self) -> None:
        for index, status in enumerate(
            ("submitted", "approved", "rejected", "submitted"), start=1
        ):
            self.repository.orders.append(make_order(index, status=status))

        result = await self.service.list_orders(
            self.account,
            CustomerOrderQuery(page=1, page_size=2, status="submitted"),
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["total_pages"], 1)
        self.assertEqual(len(result["items"]), 2)

        with self.assertRaises(HTTPException) as error:
            await self.service.list_orders(
                self.account, CustomerOrderQuery(status="unknown")
            )
        self.assertEqual(error.exception.detail["code"], "VALIDATION_ERROR")

        with self.assertRaises(HTTPException) as reversed_dates:
            await self.service.list_orders(
                self.account,
                CustomerOrderQuery(from_date=tomorrow(), to_date=TODAY),
            )
        self.assertEqual(
            reversed_dates.exception.detail["code"], "VALIDATION_ERROR"
        )

    async def test_detail_ownership_and_links(self) -> None:
        order = make_order(1)
        self.repository.orders.append(order)
        sale = SimpleNamespace(
            id=7,
            sale_date=order.requested_date,
            litres=Decimal("12.50"),
            rate=Decimal("60.00"),
            amount=Decimal("750.00"),
            payment_status="unpaid",
            is_deleted=False,
        )
        invoice = SimpleNamespace(
            id=3,
            invoice_no="INV-20261031-ABCD",
            status="unpaid",
            total_amount=Decimal("750.00"),
            paid_amount=Decimal("250.00"),
        )
        self.repository.sales[order.id] = sale
        self.repository.invoices[sale.id] = invoice
        await self.repository.add_event(
            order_id=order.id,
            from_status=None,
            to_status="submitted",
            actor_type="customer",
            actor_account_id=self.account.id,
        )

        detail = await self.service.get_order(self.account, order.id)
        self.assertEqual(detail["order"]["events"][0]["to_status"], "submitted")
        self.assertEqual(detail["order"]["sale"]["id"], 7)
        self.assertEqual(detail["order"]["invoice"]["balance"], "500.00")

        other = make_account(account_id=2, customer_id=5, activated=True, password="x")
        with self.assertRaises(HTTPException) as error:
            await self.service.get_order(other, order.id)
        self.assertEqual(error.exception.status_code, 404)

    async def test_cancel_rules(self) -> None:
        order = make_order(1)
        self.repository.orders.append(order)
        result = await self.service.cancel(self.account, order.id, "Changed plans")
        self.assertEqual(result["order"]["status"], "cancelled")
        self.assertEqual(result["order"]["reason"], "Changed plans")
        self.assertEqual(self.repository.events[-1].to_status, "cancelled")

        approved = make_order(2, status="approved")
        self.repository.orders.append(approved)
        with self.assertRaises(HTTPException) as error:
            await self.service.cancel(self.account, approved.id, None)
        self.assertEqual(error.exception.detail["code"], "INVALID_ORDER_TRANSITION")

        with self.assertRaises(HTTPException) as missing:
            await self.service.cancel(self.account, 999, None)
        self.assertEqual(missing.exception.status_code, 404)


class OrderApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.customer = make_customer()
        self.account = make_account(activated=True, password="x")
        self.other_customer = make_customer(5, name="Second Customer")
        self.other_account = make_account(
            account_id=2,
            customer_id=5,
            email="second@example.com",
            activated=True,
            password="x",
        )
        self.customers = FakeCustomerRepository(
            [self.customer, self.other_customer]
        )
        self.orders = FakeOrderRepository()

        async def override_get_db():
            yield FakeSession(
                [self.account, self.other_account],
                self.customers.customers,
            )

        def override_order_repository() -> Any:
            return self.orders

        def override_customer_repository() -> CustomerRepository:
            return self.customers  # type: ignore[return-value]

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_customer_order_repository] = (
            override_order_repository
        )
        app.dependency_overrides[get_customer_repository] = (
            override_customer_repository
        )
        self.audit = FakeAuditService()
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit

        # Order notifications are dispatched after the response; the fake keeps
        # the test off a real database session and records what was queued.
        self.dispatched: list[tuple[str, int]] = []

        async def fake_dispatch(*, event_key: str, order_id: int) -> None:
            self.dispatched.append((event_key, order_id))

        app.dependency_overrides[get_order_email_dispatch] = (
            lambda: fake_dispatch
        )

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self, account: CustomerPortalAccount) -> dict[str, str]:
        token = create_customer_access_token(
            account_id=account.id,
            customer_id=account.customer_id,
            email=account.email,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{CUSTOMER_COOKIE}=customer-session",
        }

    async def _create(self, **overrides) -> httpx.Response:
        body = {
            "quantity_litres": "12.50",
            "requested_date": tomorrow().isoformat(),
            "note": "Evening pickup",
            "customer_id": 999,
            "rate_snapshot": "1.00",
            "estimated_total": "1.00",
            "status": "approved",
            "reason": "injected",
        }
        body.update(overrides)
        return await self.client.post(
            "/api/v1/customer-portal/orders",
            json=body,
            headers=self._auth(self.account),
        )

    async def test_create_and_list_own_orders(self) -> None:
        created = await self._create()
        self.assertEqual(created.status_code, 201, created.text)
        order = created.json()["order"]
        self.assertEqual(order["status"], "submitted")
        self.assertEqual(order["rate_snapshot"], "60.00")
        self.assertNotIn("customer_id", order)
        self.assertEqual(self.customers.customers[0].id, 4)

        listing = await self.client.get(
            "/api/v1/customer-portal/orders",
            headers=self._auth(self.account),
        )
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["items"][0]["id"], order["id"])

    async def test_create_and_cancel_dispatch_order_notifications(self) -> None:
        created = await self._create()
        self.assertEqual(created.status_code, 201, created.text)
        order_id = created.json()["order"]["id"]
        self.assertEqual(self.dispatched, [("order.submitted", order_id)])

        cancelled = await self.client.post(
            f"/api/v1/customer-portal/orders/{order_id}/cancel",
            json={},
            headers=self._auth(self.account),
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(
            self.dispatched,
            [("order.submitted", order_id), ("order.cancelled", order_id)],
        )

    async def test_validation_errors(self) -> None:
        cases = (
            ({"quantity_litres": "1.001"}, "VALIDATION_ERROR"),
            ({"quantity_litres": "0"}, "INVALID_QUANTITY"),
            ({"quantity_litres": "501"}, "ORDER_LIMIT_EXCEEDED"),
            (
                {"requested_date": (TODAY - timedelta(days=1)).isoformat()},
                "INVALID_REQUESTED_DATE",
            ),
        )
        for body, code in cases:
            with self.subTest(body=body):
                response = await self._create(**body)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()["error"]["code"], code)

        invalid_date = await self._create(requested_date="31-10-2026")
        self.assertEqual(invalid_date.status_code, 400)

    async def test_customer_cannot_reach_another_customers_order(self) -> None:
        created = await self._create()
        order_id = created.json()["order"]["id"]

        detail = await self.client.get(
            f"/api/v1/customer-portal/orders/{order_id}",
            headers=self._auth(self.other_account),
        )
        self.assertEqual(detail.status_code, 404)

        cancel = await self.client.post(
            f"/api/v1/customer-portal/orders/{order_id}/cancel",
            json={},
            headers=self._auth(self.other_account),
        )
        self.assertEqual(cancel.status_code, 404)

    async def test_cancel_without_body_and_reject_approved(self) -> None:
        created = await self._create()
        order_id = created.json()["order"]["id"]

        cancelled = await self.client.post(
            f"/api/v1/customer-portal/orders/{order_id}/cancel",
            headers=self._auth(self.account),
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["order"]["status"], "cancelled")

        self.orders.orders.append(make_order(50, status="approved"))
        blocked = await self.client.post(
            "/api/v1/customer-portal/orders/50/cancel",
            json={"reason": "too late"},
            headers=self._auth(self.account),
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(
            blocked.json()["error"]["code"], "INVALID_ORDER_TRANSITION"
        )

    async def test_staff_token_is_rejected(self) -> None:
        from app.core.security import create_access_token

        staff = create_access_token(
            user_id=1,
            email="admin@example.com",
            username="admin",
            role="admin",
        )
        response = await self.client.get(
            "/api/v1/customer-portal/orders",
            headers={
                "Authorization": f"Bearer {staff}",
                "Cookie": f"{CUSTOMER_COOKIE}=customer-session",
            },
        )
        self.assertEqual(response.status_code, 401)

    async def test_list_validates_range_and_status(self) -> None:
        for query in (
            "from=2026-11-05&to=2026-11-01",
            "status=unknown",
            "from=not-a-date",
        ):
            with self.subTest(query=query):
                response = await self.client.get(
                    f"/api/v1/customer-portal/orders?{query}",
                    headers=self._auth(self.account),
                )
                self.assertEqual(response.status_code, 400, response.text)


class OpenApiOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_routes_documented(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            spec = (await client.get("/api/v1/docs/openapi.json")).json()
        paths = spec["paths"]
        for path, method in (
            ("/api/v1/customer-portal/orders", "post"),
            ("/api/v1/customer-portal/orders", "get"),
            ("/api/v1/customer-portal/orders/{order_id}", "get"),
            ("/api/v1/customer-portal/orders/{order_id}/cancel", "post"),
        ):
            with self.subTest(path=path, method=method):
                self.assertIn(method, paths[path])


if __name__ == "__main__":
    unittest.main()
