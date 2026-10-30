from __future__ import annotations

import asyncio
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.models  # noqa: F401
from app.schemas.sale import CreateSaleRequest, UpdateSaleRequest
from app.services.customer_order_service import CustomerOrderService
from tests.test_customer_portal_auth import FakeCustomerRepository
from tests.test_customer_portal_orders import (
    FakeOrderRepository,
    make_customer,
    make_order,
)
from tests.test_customer_portal_orders_staff import (
    TODAY,
    FakeInvoiceService,
    FakeSaleRepository,
    FakeStockService,
)
from tests.test_phase7 import TODAY as SALE_DAY
from tests.test_phase7 import build_services, make_user


class SerialLock:
    """Mutual exclusion model of the MySQL advisory lock held per unit of work."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.entries = 0
        self.held = False

    def lock(self) -> SerialLock:
        return self

    async def __aenter__(self) -> SerialLock:
        await self._lock.acquire()
        self.entries += 1
        self.held = True
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.held = False
        self._lock.release()


class CountingStockService(FakeStockService):
    def __init__(self, lock: SerialLock) -> None:
        super().__init__()
        self.lock = lock
        self.lock_states: list[bool] = []
        self.yield_before_check = False

    async def assert_available_stock(
        self,
        raw_date: str,
        litres: Decimal,
        *,
        reserved_lookup=None,
    ) -> None:
        self.lock_states.append(self.lock.held)
        if self.yield_before_check:
            await asyncio.sleep(0)
        await super().assert_available_stock(
            raw_date,
            litres,
            reserved_lookup=reserved_lookup,
        )


class LockAwareOrderRepository(FakeOrderRepository):
    def __init__(self, lock: SerialLock) -> None:
        super().__init__()
        self.lock = lock
        self.commit_lock_states: list[bool] = []

    async def get_by_id(self, order_id: int, *, include_deleted: bool = False):
        await asyncio.sleep(0)
        return await super().get_by_id(order_id, include_deleted=include_deleted)

    async def commit(self) -> None:
        self.commit_lock_states.append(self.lock.held)
        await super().commit()


class FailingInvoiceService(FakeInvoiceService):
    async def create_invoice_for_sale(self, **kwargs):
        raise RuntimeError("invoice generation failed")


class CollidingOrderRepository(FakeOrderRepository):
    def __init__(self, collisions: int) -> None:
        super().__init__()
        self.collisions = collisions
        self.find_calls = 0

    async def find_by_order_no(self, order_no: str):
        self.find_calls += 1
        if self.find_calls <= self.collisions:
            return SimpleNamespace(order_no=order_no)
        return None


class OrderConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.customers = FakeCustomerRepository([self.customer])
        self.lock = SerialLock()
        self.orders = LockAwareOrderRepository(self.lock)
        self.stock = CountingStockService(self.lock)
        self.sales = FakeSaleRepository(self.orders)
        self.invoices = FakeInvoiceService(self.orders)
        self.service = CustomerOrderService(
            self.orders,
            self.customers,
            stock_service=self.stock,
            sale_repository=self.sales,
            invoice_service=self.invoices,
            stock_lock=self.lock,
        )
        self.admin = make_user()

    def _add(self, status: str = "submitted", day: date | None = None):
        order = make_order(
            len(self.orders.orders) + 1,
            status=status,
            requested_date=day or TODAY,
            customer_id=self.customer.id,
            account_id=1,
        )
        self.orders.orders.append(order)
        return order

    async def test_approve_checks_stock_and_commits_inside_the_lock(self) -> None:
        order = self._add()

        await self.service.approve(self.admin, order.id, None)

        self.assertEqual(self.stock.lock_states, [True])
        self.assertEqual(self.orders.commit_lock_states, [True])
        self.assertEqual(self.lock.entries, 1)

    async def test_concurrent_approvals_serialise_and_only_one_wins(self) -> None:
        order = self._add()
        self.stock.yield_before_check = True

        results = await asyncio.gather(
            self.service.approve(self.admin, order.id, None),
            self.service.approve(self.admin, order.id, None),
            return_exceptions=True,
        )

        successes = [row for row in results if isinstance(row, dict)]
        failures = [row for row in results if isinstance(row, Exception)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].status_code, 409)
        self.assertEqual(failures[0].detail["code"], "INVALID_ORDER_TRANSITION")
        self.assertEqual(order.status, "approved")
        self.assertEqual(len(self.orders.events), 1)
        self.assertEqual(self.orders.commits, 1)
        self.assertEqual(self.lock.entries, 2)
        self.assertEqual(self.sales.created, [])

    async def test_approve_never_creates_a_sale_or_invoice(self) -> None:
        order = self._add()

        await self.service.approve(self.admin, order.id, None)

        self.assertEqual(self.sales.created, [])
        self.assertEqual(self.invoices.created, [])

    async def test_double_fulfil_is_rejected_without_a_second_sale(self) -> None:
        order = self._add(status="approved")

        first = await self.service.fulfil(self.admin, order.id)
        self.assertEqual(first["order"]["status"], "fulfilled")

        with self.assertRaises(Exception) as caught:
            await self.service.fulfil(self.admin, order.id)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(len(self.sales.created), 1)
        self.assertEqual(len(self.invoices.created), 1)
        self.assertEqual(self.orders.commits, 1)

    async def test_failed_invoice_leaves_no_commit_and_no_state_change(self) -> None:
        order = self._add(status="approved")
        service = CustomerOrderService(
            self.orders,
            self.customers,
            stock_service=self.stock,
            sale_repository=self.sales,
            invoice_service=FailingInvoiceService(self.orders),
            stock_lock=self.lock,
        )

        with self.assertRaises(RuntimeError):
            await service.fulfil(self.admin, order.id)

        self.assertEqual(order.status, "approved")
        self.assertEqual(self.orders.events, [])
        self.assertEqual(self.orders.commits, 0)
        self.assertEqual(self.orders.commit_lock_states, [])

    async def test_order_number_retries_after_collisions(self) -> None:
        repository = CollidingOrderRepository(collisions=2)
        service = CustomerOrderService(
            repository,
            self.customers,
            stock_lock=self.lock,
        )

        order_no = await service._generate_order_number(TODAY)

        self.assertTrue(order_no.startswith(f"ORD-{TODAY:%Y%m%d}-"))
        self.assertEqual(repository.find_calls, 3)


class SaleLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_sale_create_and_update_hold_the_lock(self) -> None:
        (
            _,
            sale_repository,
            stock_repository,
            _,
            sale_service,
            admin,
            _,
        ) = build_services()
        lock = SerialLock()
        sale_service.stock_lock = lock
        stock_repository.production.append(
            (date.fromisoformat(SALE_DAY), Decimal("100.00"))
        )

        created = await sale_service.record_sale(
            CreateSaleRequest.model_validate(
                {
                    "customer_id": 1,
                    "sale_date": SALE_DAY,
                    "litres": 10,
                    "rate": 50,
                }
            ),
            admin,
        )
        await sale_service.update_sale(
            str(created["id"]),
            UpdateSaleRequest.model_validate({"litres": 12, "rate": 60}),
            admin,
        )

        self.assertEqual(lock.entries, 2)
        self.assertEqual(sale_repository.commits, 2)


if __name__ == "__main__":
    unittest.main()
