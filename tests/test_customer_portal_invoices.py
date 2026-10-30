from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx

import app.models  # noqa: F401
from app.core.dependencies import (
    get_customer_repository,
    get_invoice_repository,
)
from app.core.security import create_access_token, create_customer_access_token
from app.db.session import get_db
from app.main import app
from app.schemas.customer_invoices import PortalInvoiceQuery
from app.services.customer_invoice_service import CustomerInvoiceService
from tests.test_customer_portal_auth import (
    CREATED,
    CUSTOMER_COOKIE,
    FakeCustomerRepository,
    FakeSession,
    make_account,
    make_customer,
)

TODAY = date(2026, 10, 30)


def make_sale(
    sale_id: int,
    *,
    customer_id: int = 4,
    day: date = TODAY,
    litres: str = "12.50",
    rate: str = "60.00",
    amount: str = "750.00",
    payment_status: str = "unpaid",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=sale_id,
        customer_id=customer_id,
        sale_date=day,
        litres=Decimal(litres),
        rate=Decimal(rate),
        amount=Decimal(amount),
        payment_status=payment_status,
        is_deleted=False,
    )


def make_invoice(
    invoice_id: int = 1,
    *,
    customer_id: int = 4,
    invoice_no: str = "INV-20261030-1A2B",
    period_start: date = TODAY,
    period_end: date = TODAY,
    total: str = "750.00",
    paid: str = "0.00",
    status: str = "unpaid",
    is_deleted: bool = False,
    sales: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    invoice = SimpleNamespace(
        id=invoice_id,
        invoice_no=invoice_no,
        customer_id=customer_id,
        period_start=period_start,
        period_end=period_end,
        total_amount=Decimal(total),
        paid_amount=Decimal(paid),
        status=status,
        is_deleted=is_deleted,
        created_at=CREATED + timedelta(minutes=invoice_id),
        updated_at=CREATED + timedelta(minutes=invoice_id),
        customer=None,
        sale_links=[
            SimpleNamespace(sale=sale) for sale in (sales or [])
        ],
    )
    return invoice


class FakeInvoiceRepository:
    def __init__(self, invoices: list[SimpleNamespace] | None = None) -> None:
        self.invoices = list(invoices or [])

    def _attach(self, invoice: SimpleNamespace) -> SimpleNamespace:
        invoice.customer = None
        for customer in getattr(self, "customers", []):
            if customer.id == invoice.customer_id:
                invoice.customer = customer
                break
        return invoice

    async def get_owned(
        self,
        invoice_id: int,
        customer_id: int,
    ) -> SimpleNamespace | None:
        invoice = next(
            (
                row
                for row in self.invoices
                if row.id == invoice_id
                and row.customer_id == customer_id
                and not row.is_deleted
            ),
            None,
        )
        return self._attach(invoice) if invoice is not None else None

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        customer_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[SimpleNamespace], int]:
        rows = [row for row in self.invoices if not row.is_deleted]
        if customer_id is not None:
            rows = [row for row in rows if row.customer_id == customer_id]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        if from_date is not None and to_date is not None:
            rows = [
                row
                for row in rows
                if row.period_start >= from_date and row.period_end <= to_date
            ]
        elif from_date is not None:
            rows = [row for row in rows if row.period_start >= from_date]
        elif to_date is not None:
            rows = [row for row in rows if row.period_end <= to_date]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        return [self._attach(row) for row in rows[start : start + page_size]], total


class FakeBillingCustomerRepository(FakeCustomerRepository):
    def __init__(
        self,
        customers: list[Any] | None = None,
        *,
        total_sales: str = "1500.00",
        total_paid: str = "250.00",
    ) -> None:
        super().__init__(customers)
        self.total_sales = Decimal(total_sales)
        self.total_paid = Decimal(total_paid)

    async def financials(self, customer_id: int):
        return (
            self.total_sales,
            self.total_paid,
            max(Decimal("0"), self.total_sales - self.total_paid),
        )


class CustomerInvoiceServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.customer = make_customer()
        self.customers = FakeBillingCustomerRepository([self.customer])
        self.invoices = [
            make_invoice(
                1,
                customer_id=self.customer.id,
                sales=[make_sale(1)],
            ),
            make_invoice(
                2,
                customer_id=self.customer.id,
                invoice_no="INV-20261029-CCCC",
                period_start=TODAY - timedelta(days=1),
                period_end=TODAY - timedelta(days=1),
                total="120.00",
                paid="120.00",
                status="paid",
            ),
            make_invoice(
                3,
                customer_id=99,
                invoice_no="INV-OTHER",
                sales=[make_sale(3, customer_id=99)],
            ),
        ]
        self.repository = FakeInvoiceRepository(self.invoices)
        self.repository.customers = [self.customer]
        self.service = CustomerInvoiceService(self.repository, self.customers)
        self.account = make_account(password="x", activated=True)
        self.other_account = make_account(
            2,
            customer_id=99,
            email="other@example.com",
            password="x",
            activated=True,
        )

    async def test_list_only_own_invoices_and_filters(self) -> None:
        result = await self.service.list_invoices(
            self.account,
            PortalInvoiceQuery(),
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual([row["id"] for row in result["items"]], [2, 1])
        summary = result["items"][1]
        self.assertEqual(
            set(summary),
            {
                "id",
                "invoice_no",
                "period_start",
                "period_end",
                "total_amount",
                "paid_amount",
                "status",
                "balance",
            },
        )

        paid = await self.service.list_invoices(
            self.account,
            PortalInvoiceQuery(status="paid"),
        )
        self.assertEqual([row["id"] for row in paid["items"]], [2])

        ranged = await self.service.list_invoices(
            self.account,
            PortalInvoiceQuery(from_date=TODAY, to_date=TODAY),
        )
        self.assertEqual([row["id"] for row in ranged["items"]], [1])

        paged = await self.service.list_invoices(
            self.account,
            PortalInvoiceQuery(page=2, page_size=1),
        )
        self.assertEqual(paged["total"], 2)
        self.assertEqual(paged["total_pages"], 2)
        self.assertEqual(len(paged["items"]), 1)

    async def test_list_validation(self) -> None:
        with self.assertRaises(Exception) as bad_status:
            await self.service.list_invoices(
                self.account,
                PortalInvoiceQuery(status="unknown"),
            )
        self.assertEqual(bad_status.exception.detail["code"], "VALIDATION_ERROR")

        with self.assertRaises(Exception) as bad_range:
            await self.service.list_invoices(
                self.account,
                PortalInvoiceQuery(
                    from_date=TODAY,
                    to_date=TODAY - timedelta(days=1),
                ),
            )
        self.assertEqual(bad_range.exception.detail["code"], "VALIDATION_ERROR")

    async def test_detail_is_scoped_and_customer_safe(self) -> None:
        result = await self.service.get_invoice(self.account, 1)
        invoice = result["invoice"]
        self.assertEqual(invoice["balance"], "750.00")
        self.assertEqual(invoice["customer"]["name"], self.customer.name)
        self.assertEqual(len(invoice["sales"]), 1)
        self.assertEqual(invoice["sales"][0]["litres"], "12.50")
        for forbidden in ("customer_id", "is_deleted", "createdAt", "updatedAt"):
            self.assertNotIn(forbidden, invoice)

        with self.assertRaises(Exception) as missing:
            await self.service.get_invoice(self.account, 3)
        self.assertEqual(missing.exception.status_code, 404)

        with self.assertRaises(Exception) as other:
            await self.service.get_invoice(self.other_account, 1)
        self.assertEqual(other.exception.status_code, 404)

    async def test_pdf_is_scoped_and_valid(self) -> None:
        content, filename = await self.service.generate_invoice_pdf(
            self.account,
            1,
        )
        self.assertEqual(filename, "invoice-INV-20261030-1A2B.pdf")
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content), 500)

        with self.assertRaises(Exception) as caught:
            await self.service.generate_invoice_pdf(self.other_account, 1)
        self.assertEqual(caught.exception.status_code, 404)

    async def test_balance_reuses_customer_financials(self) -> None:
        result = await self.service.get_balance(self.account)
        self.assertEqual(
            result,
            {
                "balance": {
                    "total_sales_amount": "1500.00",
                    "total_paid_amount": "250.00",
                    "outstanding_balance": "1250.00",
                }
            },
        )


class CustomerInvoiceApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.customer = make_customer()
        self.account = make_account(password="x", activated=True)
        self.other_customer = make_customer(99, name="Other Dairy")
        self.other_account = make_account(
            2,
            customer_id=99,
            email="other@example.com",
            password="x",
            activated=True,
        )
        self.customers = FakeBillingCustomerRepository(
            [self.customer, self.other_customer]
        )
        self.invoices = [
            make_invoice(1, sales=[make_sale(1)]),
            make_invoice(
                2,
                customer_id=99,
                invoice_no="INV-OTHER",
                sales=[make_sale(2, customer_id=99)],
            ),
        ]
        self.repository = FakeInvoiceRepository(self.invoices)
        self.repository.customers = [self.customer, self.other_customer]

        async def override_get_db():
            yield FakeSession(
                [self.account, self.other_account],
                [self.customer, self.other_customer],
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_invoice_repository] = lambda: self.repository
        app.dependency_overrides[get_customer_repository] = lambda: self.customers
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    def _auth(self, account: Any) -> dict[str, str]:
        token = create_customer_access_token(
            account_id=account.id,
            customer_id=account.customer_id,
            email=account.email,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Cookie": f"{CUSTOMER_COOKIE}={token}",
        }

    async def test_list_detail_pdf_and_balance(self) -> None:
        listed = await self.client.get(
            "/api/v1/customer-portal/invoices",
            headers=self._auth(self.account),
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)
        self.assertEqual(listed.json()["items"][0]["id"], 1)

        detail = await self.client.get(
            "/api/v1/customer-portal/invoices/1",
            headers=self._auth(self.account),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["invoice"]["sales"][0]["amount"], "750.00")

        pdf = await self.client.get(
            "/api/v1/customer-portal/invoices/1/pdf",
            headers=self._auth(self.account),
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.headers["content-type"].startswith("application/pdf"))
        self.assertEqual(pdf.headers["cache-control"], "no-store")
        self.assertIn(
            'inline; filename="invoice-INV-20261030-1A2B.pdf"',
            pdf.headers["content-disposition"],
        )
        self.assertTrue(pdf.content.startswith(b"%PDF-"))

        balance = await self.client.get(
            "/api/v1/customer-portal/balance",
            headers=self._auth(self.account),
        )
        self.assertEqual(balance.status_code, 200)
        self.assertEqual(
            balance.json()["balance"]["outstanding_balance"],
            "1250.00",
        )

    async def test_ownership_and_session_errors(self) -> None:
        other_detail = await self.client.get(
            "/api/v1/customer-portal/invoices/2",
            headers=self._auth(self.account),
        )
        self.assertEqual(other_detail.status_code, 404)

        other_pdf = await self.client.get(
            "/api/v1/customer-portal/invoices/2/pdf",
            headers=self._auth(self.account),
        )
        self.assertEqual(other_pdf.status_code, 404)

        staff_token = create_access_token(
            user_id=1,
            email="admin@example.com",
            role="admin",
            username="admin",
        )
        staff = await self.client.get(
            "/api/v1/customer-portal/invoices",
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        self.assertEqual(staff.status_code, 401)

        no_cookie = await self.client.get(
            "/api/v1/customer-portal/invoices",
            headers={
                "Authorization": self._auth(self.account)["Authorization"],
            },
        )
        self.assertEqual(no_cookie.status_code, 401)

    async def test_invalid_filters(self) -> None:
        bad_status = await self.client.get(
            "/api/v1/customer-portal/invoices",
            headers=self._auth(self.account),
            params={"status": "unknown"},
        )
        self.assertEqual(bad_status.status_code, 400)
        self.assertEqual(bad_status.json()["error"]["code"], "VALIDATION_ERROR")

        bad_date = await self.client.get(
            "/api/v1/customer-portal/invoices",
            headers=self._auth(self.account),
            params={"from": "not-a-date"},
        )
        self.assertEqual(bad_date.status_code, 400)

        bad_range = await self.client.get(
            "/api/v1/customer-portal/invoices",
            headers=self._auth(self.account),
            params={"from": "2026-10-30", "to": "2026-10-01"},
        )
        self.assertEqual(bad_range.status_code, 400)

    async def test_openapi_documents_billing_routes(self) -> None:
        response = await self.client.get("/api/v1/docs/openapi.json")
        paths = response.json()["paths"]
        self.assertIn("/api/v1/customer-portal/invoices", paths)
        self.assertIn("/api/v1/customer-portal/invoices/{invoice_id}", paths)
        self.assertIn("/api/v1/customer-portal/invoices/{invoice_id}/pdf", paths)
        self.assertIn("/api/v1/customer-portal/balance", paths)
