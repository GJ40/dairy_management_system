from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException

import app.models  # noqa: F401
from app.core.config import settings
from app.core.dependencies import (
    get_customer_repository,
    get_invoice_repository,
    get_sale_repository,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.invoice_sale import InvoiceSale
from app.models.sale import Sale
from app.models.user import User
from app.schemas.invoice import (
    CreateInvoiceRequest,
    InvoiceQuery,
    RecordPaymentRequest,
)
from app.services.invoice_service import InvoiceService
from app.utils.pdf import build_invoice_pdf

CREATED = datetime(2026, 10, 28, 12, 10, 23, 123000)


def make_user(
    user_id: int = 1,
    *,
    role: str = "admin",
    username: str = "admin",
) -> User:
    return User(
        id=user_id,
        full_name="System Admin" if role == "admin" else "Ramesh Patel",
        username=username,
        email=f"{username}@example.com",
        password_hash="not-used",
        role=role,
        is_active=True,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


def make_customer(
    customer_id: int = 1,
    *,
    name: str = "Ramesh Dairy",
    phone: str | None = "9876543210",
    address: str | None = "Main Road",
    rate: str = "50.00",
    is_active: bool = True,
) -> Customer:
    return Customer(
        id=customer_id,
        name=name,
        phone=phone,
        address=address,
        rate_per_litre=Decimal(rate),
        is_active=is_active,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


def make_sale(
    sale_id: int,
    *,
    customer_id: int = 1,
    sale_date: str = "2026-10-28",
    litres: str = "10.00",
    rate: str = "50.00",
    amount: str = "500.00",
    payment_status: str = "unpaid",
) -> Sale:
    return Sale(
        id=sale_id,
        customer_id=customer_id,
        sale_date=date.fromisoformat(sale_date),
        litres=Decimal(litres),
        rate=Decimal(rate),
        amount=Decimal(amount),
        payment_status=payment_status,
        recorded_by=1,
        is_deleted=False,
        created_at=CREATED,
        updated_at=CREATED,
    )


class FakeCustomerRepository:
    def __init__(self, customers: list[Customer]) -> None:
        self.customers = {customer.id: customer for customer in customers}

    async def get_by_id(self, customer_id: int) -> Customer | None:
        return self.customers.get(customer_id)


class FakeSaleRepository:
    def __init__(self, sales: list[Sale]) -> None:
        self.sales = sales

    async def find_by_ids_for_customer(
        self,
        customer_id: int,
        sale_ids: list[int],
    ) -> list[Sale]:
        return [
            sale
            for sale in self.sales
            if sale.id in sale_ids
            and sale.customer_id == customer_id
            and not sale.is_deleted
        ]

    async def find_for_period(
        self,
        *,
        customer_id: int,
        period_start: date,
        period_end: date,
    ) -> list[Sale]:
        rows = [
            sale
            for sale in self.sales
            if sale.customer_id == customer_id
            and not sale.is_deleted
            and period_start <= sale.sale_date <= period_end
        ]
        rows.sort(key=lambda sale: (sale.sale_date, sale.id))
        return rows


class FakeInvoiceRepository:
    def __init__(
        self,
        customers: FakeCustomerRepository,
        sales: FakeSaleRepository,
    ) -> None:
        self.customers = customers
        self.sales = sales
        self.invoices: list[Invoice] = []
        self.links: list[InvoiceSale] = []
        self.next_id = 1
        self.commits = 0
        self.rollbacks = 0

    async def get_by_id(self, invoice_id: int) -> Invoice | None:
        invoice = next(
            (
                row
                for row in self.invoices
                if row.id == invoice_id and not row.is_deleted
            ),
            None,
        )
        if invoice is not None:
            invoice.customer = self.customers.customers.get(invoice.customer_id)
            invoice.sale_links = [
                link for link in self.links if link.invoice_id == invoice.id
            ]
            for link in invoice.sale_links:
                link.sale = next(
                    (
                        sale
                        for sale in self.sales.sales
                        if sale.id == link.sale_id
                    ),
                    None,
                )
        return invoice

    async def find_by_invoice_no(self, invoice_no: str) -> Invoice | None:
        return next(
            (
                invoice
                for invoice in self.invoices
                if invoice.invoice_no == invoice_no
            ),
            None,
        )

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        customer_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[Invoice], int]:
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
        for row in rows:
            row.customer = self.customers.customers.get(row.customer_id)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    async def create(
        self,
        *,
        invoice_no: str,
        customer_id: int,
        period_start: date,
        period_end: date,
        total_amount: Decimal,
    ) -> Invoice:
        invoice = Invoice(
            id=self.next_id,
            invoice_no=invoice_no,
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            total_amount=total_amount,
            paid_amount=Decimal("0.00"),
            status="unpaid",
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        invoice.sale_links = []
        self.next_id += 1
        self.invoices.append(invoice)
        return invoice

    async def create_invoice_sales(
        self,
        invoice_id: int,
        sale_ids: list[int],
    ) -> None:
        for sale_id in sale_ids:
            link = InvoiceSale(
                id=len(self.links) + 1,
                invoice_id=invoice_id,
                sale_id=sale_id,
                created_at=CREATED,
                updated_at=CREATED,
            )
            self.links.append(link)

    async def find_invoice_sales_by_sale_ids(
        self,
        sale_ids: list[int],
    ) -> list[InvoiceSale]:
        return [link for link in self.links if link.sale_id in sale_ids]

    async def mark_sales_paid(self, sale_ids: list[int]) -> None:
        for sale in self.sales.sales:
            if sale.id in sale_ids:
                sale.payment_status = "paid"

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSession:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def get(self, model: type[User], user_id: int) -> User | None:
        if model is User:
            return self.users.get(user_id)
        return None


def build_services() -> tuple[
    FakeCustomerRepository,
    FakeSaleRepository,
    FakeInvoiceRepository,
    InvoiceService,
    User,
]:
    admin = make_user()
    customer_repository = FakeCustomerRepository(
        [
            make_customer(1),
            make_customer(2, name="Other Dairy", address="Other Road"),
        ]
    )
    sale_repository = FakeSaleRepository(
        [
            make_sale(1, sale_date="2026-10-27", amount="500.00"),
            make_sale(2, sale_date="2026-10-28", amount="300.00"),
            make_sale(3, customer_id=2, sale_date="2026-10-28"),
            make_sale(
                4,
                sale_date="2026-10-29",
                litres="20.00",
                rate="50.00",
                amount="1000.00",
            ),
        ]
    )
    invoice_repository = FakeInvoiceRepository(
        customer_repository,
        sale_repository,
    )
    service = InvoiceService(
        invoice_repository,  # type: ignore[arg-type]
        customer_repository,  # type: ignore[arg-type]
        sale_repository,  # type: ignore[arg-type]
    )
    return (
        customer_repository,
        sale_repository,
        invoice_repository,
        service,
        admin,
    )


class SchemaTests(unittest.TestCase):
    def test_create_invoice_validation(self) -> None:
        cases = [
            (
                {},
                "Field required",
            ),
            (
                {
                    "customer_id": 0,
                    "period_start": "2026-10-01",
                    "period_end": "2026-10-31",
                },
                "customer_id must be a positive integer",
            ),
            (
                {
                    "customer_id": 1,
                    "period_start": "01-10-2026",
                    "period_end": "2026-10-31",
                },
                "period_start must be in YYYY-MM-DD format",
            ),
            (
                {
                    "customer_id": 1,
                    "period_start": "2026-10-01",
                    "period_end": "31-10-2026",
                },
                "period_end must be in YYYY-MM-DD format",
            ),
            (
                {
                    "customer_id": 1,
                    "period_start": "2026-10-31",
                    "period_end": "2026-10-01",
                },
                "'period_start' cannot be after 'period_end'",
            ),
            (
                {
                    "customer_id": 1,
                    "period_start": "2026-10-01",
                    "period_end": "2026-10-31",
                    "sale_ids": [0],
                },
                "Too small: expected number to be >0",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(Exception) as caught:
                    CreateInvoiceRequest.model_validate(payload)
                self.assertIn(expected, str(caught.exception))

    def test_payment_validation(self) -> None:
        cases = [
            ({}, "Field required"),
            ({"amount": 0}, "Payment amount must be greater than zero"),
            (
                {"amount": 1000000000},
                "Amount exceeds maximum allowable threshold",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(Exception) as caught:
                    RecordPaymentRequest.model_validate(payload)
                self.assertIn(expected, str(caught.exception))


class InvoiceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            self.customer_repository,
            self.sale_repository,
            self.invoice_repository,
            self.service,
            self.admin,
        ) = build_services()

    async def test_create_implicit_invoice(self) -> None:
        payload = CreateInvoiceRequest.model_validate(
            {
                "customer_id": 1,
                "period_start": "2026-10-27",
                "period_end": "2026-10-29",
            }
        )
        invoice = await self.service.create_invoice(payload)
        self.assertRegex(invoice["invoice_no"], r"^INV-\d{8}-[A-F0-9]+$")
        self.assertEqual(invoice["customer_id"], 1)
        self.assertEqual(invoice["total_amount"], "1800.00")
        self.assertEqual(invoice["paid_amount"], "0.00")
        self.assertEqual(invoice["balance"], "1800.00")
        self.assertEqual(invoice["status"], "unpaid")
        self.assertEqual([sale["id"] for sale in invoice["sales"]], [1, 2, 4])
        self.assertIn("address", invoice["customer"])
        self.assertEqual(self.invoice_repository.commits, 1)

    async def test_explicit_sales_and_conflict(self) -> None:
        payload = CreateInvoiceRequest.model_validate(
            {
                "customer_id": 1,
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
                "sale_ids": [1, 2],
            }
        )
        invoice = await self.service.create_invoice(payload)
        self.assertEqual(invoice["total_amount"], "800.00")

        with self.assertRaises(HTTPException) as caught:
            await self.service.create_invoice(payload)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(
            caught.exception.detail["code"],
            "SALE_ALREADY_INVOICED",
        )
        self.assertIn("IDs: 1, 2", caught.exception.detail["message"])

        invalid = CreateInvoiceRequest.model_validate(
            {
                "customer_id": 1,
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
                "sale_ids": [1, 3],
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.create_invoice(invalid)
        self.assertEqual(
            caught.exception.detail["code"],
            "INVALID_SALES_SELECTION",
        )

    async def test_no_sales(self) -> None:
        payload = CreateInvoiceRequest.model_validate(
            {
                "customer_id": 1,
                "period_start": "2025-01-01",
                "period_end": "2025-01-31",
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.create_invoice(payload)
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(
            caught.exception.detail["code"],
            "NO_SALES_TO_INVOICE",
        )
        self.assertIn("Ramesh Dairy", caught.exception.detail["message"])

    async def test_payment_tracking(self) -> None:
        payload = CreateInvoiceRequest.model_validate(
            {
                "customer_id": 1,
                "period_start": "2026-10-27",
                "period_end": "2026-10-27",
            }
        )
        invoice = await self.service.create_invoice(payload)
        invoice_id = str(invoice["id"])

        partial = await self.service.record_payment(
            invoice_id,
            RecordPaymentRequest.model_validate({"amount": 200}),
        )
        self.assertEqual(partial["paid_amount"], "200.00")
        self.assertEqual(partial["balance"], "300.00")
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["sales"][0]["payment_status"], "unpaid")

        paid = await self.service.record_payment(
            invoice_id,
            RecordPaymentRequest.model_validate({"amount": 300}),
        )
        self.assertEqual(paid["paid_amount"], "500.00")
        self.assertEqual(paid["balance"], "0.00")
        self.assertEqual(paid["status"], "paid")
        self.assertEqual(paid["sales"][0]["payment_status"], "paid")
        self.assertEqual(self.sale_repository.sales[0].payment_status, "paid")

        overpaid = await self.service.record_payment(
            invoice_id,
            RecordPaymentRequest.model_validate({"amount": 100}),
        )
        self.assertEqual(overpaid["paid_amount"], "600.00")
        self.assertEqual(overpaid["balance"], "0.00")
        self.assertEqual(overpaid["status"], "paid")

    async def test_list_and_pdf(self) -> None:
        payload = CreateInvoiceRequest.model_validate(
            {
                "customer_id": 1,
                "period_start": "2026-10-27",
                "period_end": "2026-10-28",
            }
        )
        invoice = await self.service.create_invoice(payload)

        listing = await self.service.list_invoices(
            InvoiceQuery(page=1, page_size=10)
        )
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["total_pages"], 1)
        item = listing["items"][0]
        self.assertNotIn("address", item["customer"])
        self.assertNotIn("rate_per_litre", item["customer"])
        self.assertNotIn("sales", item)
        self.assertEqual(item["balance"], "800.00")

        content, filename = await self.service.generate_invoice_pdf(
            str(invoice["id"])
        )
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content), 500)
        self.assertEqual(filename, f"invoice-{invoice['invoice_no']}.pdf")


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            self.customer_repository,
            self.sale_repository,
            self.invoice_repository,
            _,
            self.admin,
        ) = build_services()
        self.operator = make_user(
            2,
            role="operator",
            username="ramesh_operator",
        )

        async def override_get_db():
            yield FakeSession(self.admin, self.operator)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_customer_repository] = (
            lambda: self.customer_repository
        )
        app.dependency_overrides[get_sale_repository] = (
            lambda: self.sale_repository
        )
        app.dependency_overrides[get_invoice_repository] = (
            lambda: self.invoice_repository
        )
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

    async def test_invoice_endpoints_and_pdf(self) -> None:
        created = await self.client.post(
            "/api/v1/invoices",
            headers=self._auth(self.operator),
            json={
                "customer_id": 1,
                "period_start": "2026-10-27",
                "period_end": "2026-10-28",
            },
        )
        self.assertEqual(created.status_code, 201)
        invoice = created.json()["invoice"]
        self.assertEqual(invoice["total_amount"], "800.00")
        self.assertEqual(len(invoice["sales"]), 2)
        self.assertEqual(invoice["sales"][0]["id"], 1)

        listing = await self.client.get(
            "/api/v1/invoices?page=1&page_size=10&customer_id=1",
            headers=self._auth(),
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["total_pages"], 1)

        detail = await self.client.get(
            f"/api/v1/invoices/{invoice['id']}",
            headers=self._auth(),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["invoice"]["balance"], "800.00")

        payment = await self.client.patch(
            f"/api/v1/invoices/{invoice['id']}/payment",
            headers=self._auth(self.operator),
            json={"amount": 800},
        )
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(payment.json()["invoice"]["status"], "paid")

        pdf = await self.client.get(
            f"/api/v1/invoices/{invoice['id']}/pdf",
            headers=self._auth(self.operator),
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.headers["content-type"].startswith("application/pdf"))
        self.assertIn(
            f"invoice-{invoice['invoice_no']}.pdf",
            pdf.headers["content-disposition"],
        )
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        self.assertGreater(len(pdf.content), 500)

        missing = await self.client.get(
            "/api/v1/invoices/999",
            headers=self._auth(),
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            missing.json()["error"]["message"],
            "Invoice with id 999 not found",
        )

    async def test_validation_messages(self) -> None:
        body_cases = [
            (
                {},
                "customer_id: Invalid input: expected number, received NaN",
            ),
            (
                {
                    "customer_id": 1,
                    "period_start": "2026-10-01",
                    "period_end": "2026-10-31",
                    "sale_ids": [0],
                },
                "sale_ids.0: Too small: expected number to be >0",
            ),
            (
                {
                    "customer_id": 1,
                    "period_start": "2026-10-31",
                    "period_end": "2026-10-01",
                },
                "period_end: 'period_start' cannot be after 'period_end'",
            ),
        ]
        for payload, expected in body_cases:
            with self.subTest(payload=payload):
                response = await self.client.post(
                    "/api/v1/invoices",
                    headers=self._auth(),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )

        payment_cases = [
            ({}, "amount: Invalid input: expected number, received NaN"),
            (
                {"amount": 0},
                "amount: Payment amount must be greater than zero",
            ),
            (
                {"amount": 1000000000},
                "amount: Amount exceeds maximum allowable threshold",
            ),
        ]
        for payload, expected in payment_cases:
            with self.subTest(payload=payload):
                response = await self.client.patch(
                    "/api/v1/invoices/1/payment",
                    headers=self._auth(),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )

        query_cases = [
            (
                "/api/v1/invoices?status=unknown",
                'status: Invalid option: expected one of '
                '"unpaid"|"partial"|"paid"',
            ),
            (
                "/api/v1/invoices?from=bad",
                "from: from must be in 'YYYY-MM-DD' format",
            ),
            (
                "/api/v1/invoices?to=bad",
                "to: to must be in 'YYYY-MM-DD' format",
            ),
            (
                "/api/v1/invoices?customer_id=0",
                "customer_id: Too small: expected number to be >0",
            ),
            (
                "/api/v1/invoices?page_size=101",
                "page_size: Too big: expected number to be <=100",
            ),
        ]
        for url, expected in query_cases:
            with self.subTest(url=url):
                response = await self.client.get(url, headers=self._auth())
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )


class InvoicePdfLayoutTests(unittest.TestCase):
    """Rendering smoke tests for the redesigned invoice document."""

    @staticmethod
    def _invoice(**overrides: str) -> dict:
        invoice = {
            "id": 1,
            "invoice_no": "INV-20261028-AB12",
            "customer_id": 1,
            "period_start": "2026-10-01",
            "period_end": "2026-10-28",
            "total_amount": "1200.00",
            "paid_amount": "500.00",
            "status": "partial",
            "balance": "700.00",
            "createdAt": "2026-10-28T06:40:23.000Z",
        }
        invoice.update(overrides)
        return invoice

    @staticmethod
    def _sales(count: int) -> list[dict]:
        rows = []
        for index in range(1, count + 1):
            rows.append(
                {
                    "id": index,
                    "sale_date": f"2026-10-{(index % 28) + 1:02d}",
                    "litres": "12.50",
                    "rate": "60.00",
                    "amount": "750.00",
                    "payment_status": "unpaid",
                }
            )
        return rows

    @staticmethod
    def _customer(**overrides: object) -> dict:
        customer: dict = {
            "id": 1,
            "name": "Ramesh Dairy",
            "phone": "9876543210",
            "address": "Main Road, Anand",
            "rate_per_litre": "60.00",
            "is_active": True,
        }
        customer.update(overrides)
        return customer

    def _assert_pdf(self, content: bytes, minimum: int = 1000) -> None:
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content), minimum)
        self.assertTrue(content.rstrip().endswith(b"%%EOF"))

    def test_partial_payment_invoice(self) -> None:
        content = build_invoice_pdf(
            invoice=self._invoice(),
            customer=self._customer(),
            sales=self._sales(2),
        )
        self._assert_pdf(content)

    def test_fully_paid_and_overpaid_invoice(self) -> None:
        for paid in ("1200.00", "1500.00"):
            with self.subTest(paid=paid):
                content = build_invoice_pdf(
                    invoice=self._invoice(paid_amount=paid, status="paid"),
                    customer=self._customer(),
                    sales=self._sales(2),
                )
                self._assert_pdf(content)

    def test_long_customer_and_many_rows_paginate(self) -> None:
        content = build_invoice_pdf(
            invoice=self._invoice(),
            customer=self._customer(
                name="Shri Krishna Cooperative Milk & Dairy Farm <Unit 2> " * 2,
                address="Plot 12, Industrial Estate, " * 12,
            ),
            sales=self._sales(60),
        )
        self._assert_pdf(content, minimum=2500)

    def test_missing_optional_customer_fields(self) -> None:
        content = build_invoice_pdf(
            invoice=self._invoice(paid_amount="0.00", status="unpaid"),
            customer=self._customer(phone=None, address=None),
            sales=self._sales(1),
        )
        self._assert_pdf(content)

    def test_invoice_without_linked_sales(self) -> None:
        content = build_invoice_pdf(
            invoice=self._invoice(total_amount="0.00", paid_amount="0.00"),
            customer=self._customer(),
            sales=[],
        )
        self._assert_pdf(content)

    def test_invoice_accepts_orm_like_objects(self) -> None:
        customer = make_customer()
        sale = Sale(
            id=1,
            customer_id=1,
            sale_date=date(2026, 10, 5),
            litres=Decimal("12.50"),
            rate=Decimal("50.00"),
            amount=Decimal("625.00"),
            payment_status="unpaid",
            recorded_by=1,
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        invoice = Invoice(
            id=1,
            invoice_no="INV-20261028-AB12",
            customer_id=1,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 28),
            total_amount=Decimal("625.00"),
            paid_amount=Decimal("0.00"),
            status="unpaid",
            is_deleted=False,
            created_at=CREATED,
            updated_at=CREATED,
        )
        content = build_invoice_pdf(
            invoice=invoice,
            customer=customer,
            sales=[sale],
        )
        self._assert_pdf(content)


if __name__ == "__main__":
    unittest.main()
