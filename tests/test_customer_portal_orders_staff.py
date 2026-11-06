from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import status

import app.models  # noqa: F401
from app.core.dependencies import (
    get_customer_order_repository,
    get_customer_repository,
    get_db,
    get_invoice_service,
    get_order_email_dispatch,
    get_sale_repository,
    get_security_audit_service,
    get_stock_lock_service,
    get_stock_service,
)
from app.core.errors import api_error
from app.core.security import create_access_token
from app.main import app
from app.schemas.customer_orders_staff import StaffOrderQuery
from app.services.customer_order_service import CustomerOrderService
from app.utils.time import business_now
from tests.audit_helpers import FakeAuditService
from tests.test_customer_portal_auth import FakeCustomerRepository, FakeSession
from tests.test_customer_portal_orders import (
    FakeOrderRepository,
    make_account,
    make_customer,
    make_order,
)
from tests.test_customers_and_sales import make_user

TODAY = business_now().date()


class FakeStockService:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls: list[tuple[str, Decimal, Any]] = []

    async def assert_available_stock(
        self,
        raw_date: str,
        litres: Decimal,
        *,
        reserved_lookup: Any = None,
    ) -> None:
        self.calls.append((raw_date, litres, reserved_lookup))
        if not self.available:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "STOCK_INSUFFICIENT",
                "Insufficient stock",
            )


class FakeStockLock:
    def __init__(self) -> None:
        self.entries = 0

    def lock(self) -> FakeStockLock:
        return self

    async def __aenter__(self) -> None:
        self.entries += 1

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeSaleRepository:
    def __init__(self, orders: FakeOrderRepository) -> None:
        self.orders = orders
        self.created: list[dict[str, Any]] = []
        self.flushes = 0
        self._sale_id = 1

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.created.append(kwargs)
        sale = SimpleNamespace(
            id=self._sale_id,
            sale_date=kwargs["sale_date"],
            litres=kwargs["litres"],
            rate=kwargs["rate"],
            amount=kwargs["amount"],
            payment_status="unpaid",
        )
        self._sale_id += 1
        self.orders.sales[kwargs["source_order_id"]] = sale
        return sale

    async def flush(self) -> None:
        self.flushes += 1


class FakeInvoiceService:
    def __init__(self, orders: FakeOrderRepository) -> None:
        self.orders = orders
        self.created: list[dict[str, Any]] = []
        self._invoice_id = 1

    async def create_invoice_for_sale(
        self,
        *,
        customer_id: int,
        sale_id: int,
        period_start: date,
        period_end: date,
        total_amount: Decimal,
    ) -> SimpleNamespace:
        self.created.append(
            {
                "customer_id": customer_id,
                "sale_id": sale_id,
                "period_start": period_start,
                "period_end": period_end,
                "total_amount": total_amount,
            }
        )
        invoice = SimpleNamespace(
            id=self._invoice_id,
            invoice_no=f"INV-20261030-{self._invoice_id:04d}",
            status="unpaid",
            total_amount=total_amount,
            paid_amount=Decimal("0.00"),
        )
        self._invoice_id += 1
        self.orders.invoices[sale_id] = invoice
        return invoice


class StaffOrderServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.customers = FakeCustomerRepository([self.customer])
        self.orders = FakeOrderRepository()
        self.stock = FakeStockService()
        self.sales = FakeSaleRepository(self.orders)
        self.invoices = FakeInvoiceService(self.orders)
        self.lock = FakeStockLock()
        self.service = CustomerOrderService(
            self.orders,
            self.customers,
            stock_service=self.stock,
            sale_repository=self.sales,
            invoice_service=self.invoices,
            stock_lock=self.lock,
        )
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")

    def _add(
        self,
        *,
        status_: str = "submitted",
        requested_date: date | None = None,
        quantity: str = "12.50",
    ) -> Any:
        order = make_order(
            len(self.orders.orders) + 1,
            status=status_,
            requested_date=requested_date or TODAY,
            quantity=quantity,
            customer_id=self.customer.id,
            account_id=1,
        )
        self.orders.orders.append(order)
        return order

    async def test_approve_success_records_event_and_review(self) -> None:
        order = self._add()

        result = await self.service.approve(self.admin, order.id, "Looks fine")

        self.assertEqual(result["order"]["status"], "approved")
        self.assertEqual(order.reviewed_by, self.admin.id)
        self.assertIsNotNone(order.reviewed_at)
        self.assertEqual(order.status, "approved")
        self.assertEqual(len(self.orders.events), 1)
        self.assertEqual(self.orders.events[0].to_status, "approved")
        self.assertEqual(self.orders.events[0].reason, "Looks fine")
        self.assertEqual(self.orders.commits, 1)
        self.assertEqual(self.lock.entries, 1)
        self.assertEqual(self.stock.calls[0][0], order.requested_date.isoformat())
        self.assertEqual(self.stock.calls[0][1], order.quantity_litres)
        self.assertIsNotNone(self.stock.calls[0][2])

    async def test_staff_order_audit_events(self) -> None:
        audit = FakeAuditService()
        service = CustomerOrderService(  # type: ignore[arg-type]
            self.orders,
            self.customers,
            stock_service=self.stock,
            sale_repository=self.sales,
            invoice_service=self.invoices,
            stock_lock=self.lock,
            audit=audit,
        )
        order = self._add()
        await service.approve(self.admin, order.id, None)
        self.assertEqual(audit.records[-1]["event_type"], "order.approved")

        approved = self._add(status_="approved")
        await service.fulfil(self.admin, approved.id)
        self.assertEqual(audit.records[-1]["event_type"], "order.fulfilled")
        self.assertEqual(
            audit.records[-1]["metadata"]["order_id"], approved.id
        )
        self.assertIn("sale_id", audit.records[-1]["metadata"])

    async def test_approve_insufficient_stock_keeps_submitted(self) -> None:
        self.stock.available = False
        order = self._add()

        with self.assertRaises(Exception) as caught:
            await self.service.approve(self.admin, order.id, None)

        self.assertEqual(caught.exception.detail["code"], "STOCK_INSUFFICIENT")
        self.assertEqual(order.status, "submitted")
        self.assertEqual(self.orders.events, [])
        self.assertEqual(self.orders.commits, 0)

    async def test_approve_rejects_invalid_transition(self) -> None:
        order = self._add(status_="approved")

        with self.assertRaises(Exception) as caught:
            await self.service.approve(self.admin, order.id, None)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "INVALID_ORDER_TRANSITION")

    async def test_reject_records_reason(self) -> None:
        order = self._add()

        result = await self.service.reject(
            self.admin,
            order.id,
            "No production planned",
        )

        self.assertEqual(result["order"]["status"], "rejected")
        self.assertEqual(order.status, "rejected")
        self.assertEqual(order.reason, "No production planned")
        self.assertEqual(order.reviewed_by, self.admin.id)
        self.assertEqual(self.orders.events[0].to_status, "rejected")
        self.assertEqual(self.orders.events[0].reason, "No production planned")

    async def test_reject_requires_submitted(self) -> None:
        order = self._add(status_="cancelled")

        with self.assertRaises(Exception) as caught:
            await self.service.reject(self.admin, order.id, "Too late")

        self.assertEqual(caught.exception.status_code, 409)

    async def test_fulfil_creates_sale_and_invoice(self) -> None:
        order = self._add(status_="approved", requested_date=TODAY)

        result = await self.service.fulfil(self.admin, order.id)

        self.assertEqual(result["order"]["status"], "fulfilled")
        self.assertEqual(result["sale"]["sale_date"], TODAY.isoformat())
        self.assertEqual(result["invoice"]["status"], "unpaid")
        self.assertEqual(order.status, "fulfilled")
        self.assertEqual(self.sales.created[0]["source_order_id"], order.id)
        self.assertEqual(self.sales.created[0]["sale_date"], TODAY)
        self.assertEqual(self.sales.created[0]["litres"], order.quantity_litres)
        self.assertEqual(self.sales.flushes, 1)
        self.assertEqual(self.invoices.created[0]["sale_id"], 1)
        self.assertEqual(self.invoices.created[0]["period_start"], TODAY)
        self.assertEqual(self.invoices.created[0]["period_end"], TODAY)
        self.assertEqual(
            self.invoices.created[0]["total_amount"],
            order.estimated_total,
        )
        self.assertEqual(self.orders.events[0].to_status, "fulfilled")
        self.assertEqual(self.lock.entries, 1)

    async def test_operator_fulfil_rules(self) -> None:
        today_order = self._add(status_="approved", requested_date=TODAY)
        past_order = self._add(
            status_="approved",
            requested_date=TODAY - timedelta(days=1),
        )
        future_order = self._add(
            status_="approved",
            requested_date=TODAY + timedelta(days=1),
        )

        await self.service.fulfil(self.operator, today_order.id)

        with self.assertRaises(Exception) as past:
            await self.service.fulfil(self.operator, past_order.id)
        self.assertEqual(past.exception.detail["code"], "INVALID_FULFILMENT_DATE")

        with self.assertRaises(Exception) as future:
            await self.service.fulfil(self.operator, future_order.id)
        self.assertEqual(future.exception.detail["code"], "INVALID_FULFILMENT_DATE")

        await self.service.fulfil(self.admin, past_order.id)

    async def test_fulfil_requires_approved(self) -> None:
        order = self._add(status_="submitted")

        with self.assertRaises(Exception) as caught:
            await self.service.fulfil(self.admin, order.id)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "INVALID_ORDER_TRANSITION")

    async def test_staff_cancel_submitted_and_approved(self) -> None:
        first = self._add(status_="submitted")
        second = self._add(status_="approved")
        done = self._add(status_="fulfilled")

        await self.service.staff_cancel(self.admin, first.id, "Duplicate order")
        result = await self.service.staff_cancel(
            self.operator,
            second.id,
            "Customer request",
        )

        self.assertEqual(result["order"]["status"], "cancelled")
        self.assertEqual(second.reason, "Customer request")
        self.assertEqual(self.orders.events[-1].from_status, "approved")

        with self.assertRaises(Exception) as caught:
            await self.service.staff_cancel(self.admin, done.id, "Too late now")
        self.assertEqual(caught.exception.status_code, 409)

    async def test_staff_list_filters_and_search(self) -> None:
        self.orders.orders.extend(
            [
                make_order(1, status="submitted", order_no="ORD-20261030-AAAA"),
                make_order(2, status="approved", order_no="ORD-20261030-BBBB"),
                make_order(3, status="cancelled", order_no="ORD-20261029-CCCC"),
            ]
        )

        result = await self.service.staff_list_orders(StaffOrderQuery())

        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["items"][0]["customer"]["id"], 4)
        self.assertEqual(result["items"][0]["account_email"], "customer@example.com")

        filtered = await self.service.staff_list_orders(
            StaffOrderQuery(status="approved")
        )
        self.assertEqual([row["id"] for row in filtered["items"]], [2])

        searched = await self.service.staff_list_orders(
            StaffOrderQuery(search="cccc")
        )
        self.assertEqual([row["id"] for row in searched["items"]], [3])

    async def test_staff_list_validates_query(self) -> None:
        with self.assertRaises(Exception) as bad_status:
            await self.service.staff_list_orders(StaffOrderQuery(status="unknown"))
        self.assertEqual(bad_status.exception.detail["code"], "VALIDATION_ERROR")

        with self.assertRaises(Exception) as bad_range:
            await self.service.staff_list_orders(
                StaffOrderQuery(
                    from_date=TODAY,
                    to_date=TODAY - timedelta(days=1),
                )
            )
        self.assertEqual(bad_range.exception.detail["code"], "VALIDATION_ERROR")

    async def test_staff_detail_and_missing_order(self) -> None:
        order = self._add()

        result = await self.service.staff_get_order(order.id)
        self.assertEqual(result["order"]["id"], order.id)
        self.assertEqual(result["order"]["customer"]["name"], self.customer.name)

        with self.assertRaises(Exception) as caught:
            await self.service.staff_get_order(999)
        self.assertEqual(caught.exception.status_code, 404)


class StaffOrderApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.admin = make_user()
        self.operator = make_user(2, role="operator", username="ramesh_operator")
        self.customer = make_customer()
        self.customers = FakeCustomerRepository([self.customer])
        self.orders = FakeOrderRepository()
        self.orders.orders.append(
            make_order(
                1,
                status="submitted",
                requested_date=TODAY,
                customer_id=self.customer.id,
                account_id=1,
            )
        )
        self.orders.orders.append(
            make_order(
                2,
                status="approved",
                requested_date=TODAY,
                customer_id=self.customer.id,
                account_id=1,
            )
        )
        self.stock = FakeStockService()
        self.sales = FakeSaleRepository(self.orders)
        self.invoices = FakeInvoiceService(self.orders)

        async def override_get_db():
            yield FakeSession(
                [make_account(activated=True)],
                [self.customer],
                [self.admin, self.operator],
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_customer_order_repository] = (
            lambda: self.orders
        )
        app.dependency_overrides[get_customer_repository] = (
            lambda: self.customers
        )
        app.dependency_overrides[get_stock_service] = lambda: self.stock
        app.dependency_overrides[get_stock_lock_service] = FakeStockLock
        self.audit = FakeAuditService()
        app.dependency_overrides[get_security_audit_service] = lambda: self.audit
        app.dependency_overrides[get_sale_repository] = lambda: self.sales
        app.dependency_overrides[get_invoice_service] = lambda: self.invoices

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

    def _auth(self, user: Any) -> dict[str, str]:
        token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            username=user.username,
        )
        from app.core.config import settings

        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{settings.refresh_cookie_name}={token}",
        }

    async def test_list_and_detail(self) -> None:
        listed = await self.client.get(
            "/api/v1/customer-orders",
            headers=self._auth(self.operator),
            params={"status": "submitted"},
        )
        self.assertEqual(listed.status_code, 200)
        body = listed.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["customer"]["phone"], "9876543210")

        detail = await self.client.get(
            "/api/v1/customer-orders/2",
            headers=self._auth(self.operator),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["order"]["status"], "approved")

        missing = await self.client.get(
            "/api/v1/customer-orders/999",
            headers=self._auth(self.admin),
        )
        self.assertEqual(missing.status_code, 404)

    async def test_staff_only_access(self) -> None:
        from app.core.security import create_customer_access_token

        customer_token = create_customer_access_token(
            account_id=1,
            customer_id=self.customer.id,
            email="customer@example.com",
        )
        response = await self.client.get(
            "/api/v1/customer-orders",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        self.assertEqual(response.status_code, 401)

        anonymous = await self.client.get("/api/v1/customer-orders")
        self.assertEqual(anonymous.status_code, 401)

    async def test_approve_reject_fulfil_and_cancel(self) -> None:
        approved = await self.client.post(
            "/api/v1/customer-orders/1/approve",
            headers=self._auth(self.operator),
            json={"note": "Confirmed"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["order"]["status"], "approved")

        rejected = await self.client.post(
            "/api/v1/customer-orders/1/reject",
            headers=self._auth(self.admin),
            json={"reason": "Already approved"},
        )
        self.assertEqual(rejected.status_code, 409)

        fulfilled = await self.client.post(
            "/api/v1/customer-orders/2/fulfil",
            headers=self._auth(self.admin),
        )
        self.assertEqual(fulfilled.status_code, 200)
        body = fulfilled.json()
        self.assertEqual(body["order"]["status"], "fulfilled")
        self.assertEqual(body["sale"]["sale_date"], TODAY.isoformat())
        self.assertEqual(body["invoice"]["status"], "unpaid")

        cancel_target = make_order(3, status="submitted", requested_date=TODAY)
        self.orders.orders.append(cancel_target)
        cancelled = await self.client.post(
            "/api/v1/customer-orders/3/cancel",
            headers=self._auth(self.admin),
            json={"reason": "Customer called"},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["order"]["status"], "cancelled")
        # One staff cancellation queues exactly one customer email.
        self.assertEqual(self.dispatched.count(("order.cancelled", 3)), 1)

    async def test_validation_and_permission_errors(self) -> None:
        bad_reason = await self.client.post(
            "/api/v1/customer-orders/1/reject",
            headers=self._auth(self.admin),
            json={"reason": "x"},
        )
        self.assertIn(bad_reason.status_code, (400, 422))

        bad_status = await self.client.get(
            "/api/v1/customer-orders",
            headers=self._auth(self.admin),
            params={"status": "unknown"},
        )
        self.assertEqual(bad_status.status_code, 400)

        invalid_transition = await self.client.post(
            "/api/v1/customer-orders/2/approve",
            headers=self._auth(self.admin),
            json={},
        )
        self.assertEqual(invalid_transition.status_code, 409)
        self.assertEqual(
            invalid_transition.json()["error"]["code"],
            "INVALID_ORDER_TRANSITION",
        )

    async def test_order_notification_is_dispatched_after_commit(self) -> None:
        approved = await self.client.post(
            "/api/v1/customer-orders/1/approve",
            headers=self._auth(self.operator),
            json={},
        )

        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(self.dispatched, [("order.approved", 1)])

    async def test_openapi_documents_staff_routes(self) -> None:
        response = await self.client.get("/api/v1/docs/openapi.json")
        paths = response.json()["paths"]
        self.assertIn("/api/v1/customer-orders", paths)
        self.assertIn("/api/v1/customer-orders/{order_id}/approve", paths)
        self.assertIn("/api/v1/customer-orders/{order_id}/reject", paths)
        self.assertIn("/api/v1/customer-orders/{order_id}/fulfil", paths)
        self.assertIn("/api/v1/customer-orders/{order_id}/cancel", paths)
