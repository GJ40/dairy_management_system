from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
from fastapi import HTTPException

import app.models  # noqa: F401
from app.core.dependencies import (
    get_customer_repository,
    get_sale_repository,
    get_stock_repository,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.customer import Customer
from app.models.sale import Sale
from app.models.user import User
from app.schemas.customer import (
    CreateCustomerRequest,
    CustomerQuery,
    UpdateCustomerRequest,
)
from app.schemas.sale import (
    CreateSaleRequest,
    SaleQuery,
    UpdateSaleRequest,
)
from app.services.customer_service import CustomerService
from app.services.sale_service import SaleService
from app.services.stock_service import StockService
from app.utils.time import get_business_date

CREATED = datetime(2026, 10, 28, 12, 10, 23, 123000)
TODAY = get_business_date()


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


class FakeStockRepository:
    def __init__(self) -> None:
        self.production: list[tuple[date, Decimal]] = []
        self.sales: list[tuple[date, Decimal]] = []
        self.wastage: list[tuple[date, Decimal]] = []

    async def _sum(
        self,
        values: list[tuple[date, Decimal]],
        stock_date: date,
        *,
        before: bool,
    ) -> Decimal:
        return sum(
            (
                value
                for entry_date, value in values
                if (entry_date < stock_date if before else entry_date == stock_date)
            ),
            Decimal("0"),
        )

    async def sum_prior_quantities(
        self,
        stock_date: date,
    ) -> tuple[Decimal, Decimal, Decimal]:
        return (
            await self._sum(self.production, stock_date, before=True),
            await self._sum(self.sales, stock_date, before=True),
            await self._sum(self.wastage, stock_date, before=True),
        )

    async def sum_current_quantities(
        self,
        stock_date: date,
    ) -> tuple[Decimal, Decimal, Decimal]:
        return (
            await self._sum(self.production, stock_date, before=False),
            await self._sum(self.sales, stock_date, before=False),
            await self._sum(self.wastage, stock_date, before=False),
        )

    async def get_future_active_dates(self, stock_date: date) -> list[date]:
        dates = {
            entry_date
            for collection in (self.production, self.sales, self.wastage)
            for entry_date, _ in collection
            if entry_date > stock_date
        }
        return sorted(dates)


class FakeCustomerRepository:
    def __init__(self) -> None:
        self.customers: list[Customer] = []
        self.financials_by_id: dict[int, tuple[Decimal, Decimal]] = {}
        self.next_id = 1
        self.commits = 0
        self.rollbacks = 0

    async def get_by_id(self, customer_id: int) -> Customer | None:
        return next(
            (
                customer
                for customer in self.customers
                if customer.id == customer_id and not customer.is_deleted
            ),
            None,
        )

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Customer], int]:
        rows = [customer for customer in self.customers if not customer.is_deleted]
        if is_active is not None:
            rows = [
                customer
                for customer in rows
                if bool(customer.is_active) is is_active
            ]
        if search:
            term = search.lower()
            rows = [
                customer
                for customer in rows
                if term in customer.name.lower()
                or (customer.phone is not None and term in customer.phone.lower())
            ]
        rows.sort(key=lambda customer: customer.name)
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    async def create(
        self,
        *,
        name: str,
        phone: str | None,
        address: str | None,
        rate_per_litre: Decimal,
        is_active: bool,
    ) -> Customer:
        customer = make_customer(
            self.next_id,
            name=name,
            phone=phone,
            address=address,
            rate=str(rate_per_litre),
            is_active=is_active,
        )
        self.next_id += 1
        self.customers.append(customer)
        return customer

    async def financials(
        self,
        customer_id: int,
    ) -> tuple[Decimal, Decimal, Decimal]:
        total_sales, total_paid = self.financials_by_id.get(
            customer_id,
            (Decimal("0"), Decimal("0")),
        )
        return total_sales, total_paid, max(
            Decimal("0"),
            total_sales - total_paid,
        )

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSaleRepository:
    def __init__(
        self,
        stock_repository: FakeStockRepository,
        customer_repository: FakeCustomerRepository,
        users: dict[int, User],
    ) -> None:
        self.stock_repository = stock_repository
        self.customer_repository = customer_repository
        self.users = users
        self.sales: list[Sale] = []
        self.next_id = 1
        self.commits = 0
        self.rollbacks = 0
        self.pending: Sale | None = None

    async def get_by_id(self, sale_id: int) -> Sale | None:
        return next(
            (
                sale
                for sale in self.sales
                if sale.id == sale_id and not sale.is_deleted
            ),
            None,
        )

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        customer_id: int | None = None,
        sale_date: date | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        payment_status: str | None = None,
    ) -> tuple[list[Sale], int]:
        rows = [sale for sale in self.sales if not sale.is_deleted]
        if customer_id is not None:
            rows = [sale for sale in rows if sale.customer_id == customer_id]
        if sale_date is not None:
            rows = [sale for sale in rows if sale.sale_date == sale_date]
        elif from_date is not None and to_date is not None:
            rows = [
                sale
                for sale in rows
                if from_date <= sale.sale_date <= to_date
            ]
        elif from_date is not None:
            rows = [sale for sale in rows if sale.sale_date >= from_date]
        elif to_date is not None:
            rows = [sale for sale in rows if sale.sale_date <= to_date]
        if payment_status is not None:
            rows = [
                sale
                for sale in rows
                if sale.payment_status == payment_status
            ]
        rows.sort(
            key=lambda sale: (sale.sale_date, sale.created_at),
            reverse=True,
        )
        total = len(rows)
        start = (page - 1) * page_size
        return rows[start : start + page_size], total

    async def create(
        self,
        *,
        customer_id: int,
        sale_date: date,
        litres: Decimal,
        rate: Decimal,
        amount: Decimal,
        recorded_by: int,
    ) -> Sale:
        sale = Sale(
            id=self.next_id,
            customer_id=customer_id,
            sale_date=sale_date,
            litres=litres,
            rate=rate,
            amount=amount,
            payment_status="unpaid",
            recorded_by=recorded_by,
            is_deleted=False,
            created_at=CREATED + timedelta(minutes=self.next_id),
            updated_at=CREATED + timedelta(minutes=self.next_id),
        )
        sale.customer = await self.customer_repository.get_by_id(customer_id)
        sale.recorder = self.users.get(recorded_by)
        self.next_id += 1
        self.sales.append(sale)
        self.pending = sale
        self.stock_repository.sales.append((sale_date, litres))
        return sale

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
        self.pending = None

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.pending is not None:
            if self.pending in self.sales:
                self.sales.remove(self.pending)
            self.stock_repository.sales = [
                entry
                for entry in self.stock_repository.sales
                if entry != (self.pending.sale_date, self.pending.litres)
            ]
            self.pending = None


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
    FakeStockRepository,
    CustomerService,
    SaleService,
    User,
    User,
]:
    admin = make_user()
    operator = make_user(2, role="operator", username="ramesh_operator")
    stock_repository = FakeStockRepository()
    customer_repository = FakeCustomerRepository()
    customer_repository.customers.extend(
        [
            make_customer(1),
            make_customer(
                2,
                name="Inactive Dairy",
                phone=None,
                rate="40.00",
                is_active=False,
            ),
        ]
    )
    sale_repository = FakeSaleRepository(
        stock_repository,
        customer_repository,
        {admin.id: admin, operator.id: operator},
    )
    stock_service = StockService(stock_repository)  # type: ignore[arg-type]
    customer_service = CustomerService(  # type: ignore[arg-type]
        customer_repository
    )
    sale_service = SaleService(  # type: ignore[arg-type]
        sale_repository,
        customer_repository,
        stock_service,
    )
    return (
        customer_repository,
        sale_repository,
        stock_repository,
        customer_service,
        sale_service,
        admin,
        operator,
    )


class SchemaTests(unittest.TestCase):
    def test_customer_validation_messages(self) -> None:
        cases = [
            (
                {},
                "Field required",
            ),
            (
                {"name": "", "rate_per_litre": 50},
                "Name cannot be empty",
            ),
            (
                {"name": "A", "rate_per_litre": 0},
                "Rate per litre must be greater than zero",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(Exception) as caught:
                    CreateCustomerRequest.model_validate(payload)
                self.assertIn(expected, str(caught.exception))

    def test_update_customer_messages(self) -> None:
        with self.assertRaises(Exception) as caught:
            UpdateCustomerRequest.model_validate({"name": ""})
        self.assertIn(
            "Too small: expected string to have >=1 characters",
            str(caught.exception),
        )

        with self.assertRaises(Exception) as caught:
            UpdateCustomerRequest.model_validate({"rate_per_litre": 0})
        self.assertIn(
            "Too small: expected number to be >0",
            str(caught.exception),
        )

    def test_sale_validation_messages(self) -> None:
        cases = [
            (
                {},
                "Field required",
            ),
            (
                {
                    "customer_id": 1,
                    "sale_date": "bad",
                    "litres": 1,
                },
                "Sale date must be in YYYY-MM-DD format",
            ),
            (
                {
                    "customer_id": 1,
                    "sale_date": TODAY,
                    "litres": 0,
                },
                "Litres sold must be greater than zero",
            ),
            (
                {
                    "customer_id": 1,
                    "sale_date": TODAY,
                    "litres": 1,
                    "rate": 0,
                },
                "Rate must be greater than zero",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(Exception) as caught:
                    CreateSaleRequest.model_validate(payload)
                self.assertIn(expected, str(caught.exception))


class CustomerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            self.customer_repository,
            _,
            _,
            self.service,
            _,
            self.admin,
            _,
        ) = build_services()

    async def test_list_search_filter_and_order(self) -> None:
        result = await self.service.list_customers(
            CustomerQuery(page=1, page_size=10)
        )
        self.assertEqual(result["total"], 2)
        self.assertEqual(
            [item["name"] for item in result["items"]],
            ["Inactive Dairy", "Ramesh Dairy"],
        )

        active = await self.service.list_customers(
            CustomerQuery(page=1, page_size=10, is_active=True)
        )
        self.assertEqual(active["total"], 1)
        self.assertEqual(active["items"][0]["id"], 1)

        search = await self.service.list_customers(
            CustomerQuery(page=1, page_size=10, search="9876")
        )
        self.assertEqual(search["total"], 1)

    async def test_create_update_and_balance(self) -> None:
        created = await self.service.create_customer(
            CreateCustomerRequest.model_validate(
                {
                    "name": "  New Dairy  ",
                    "phone": "",
                    "address": "",
                    "rate_per_litre": "55.5",
                }
            )
        )
        self.assertEqual(created["name"], "New Dairy")
        self.assertIsNone(created["phone"])
        self.assertIsNone(created["address"])
        self.assertEqual(created["rate_per_litre"], "55.50")
        self.assertTrue(created["is_active"])
        self.assertEqual(self.customer_repository.commits, 1)

        updated = await self.service.update_customer(
            "1",
            UpdateCustomerRequest.model_validate(
                {"name": "Updated Dairy", "rate_per_litre": "60"}
            ),
        )
        self.assertEqual(updated["name"], "Updated Dairy")
        self.assertEqual(updated["rate_per_litre"], "60.00")

        self.customer_repository.financials_by_id[1] = (
            Decimal("1000.00"),
            Decimal("400.00"),
        )
        balance = await self.service.get_customer_balance("1")
        self.assertEqual(balance["total_sales_amount"], "1000.00")
        self.assertEqual(balance["total_paid_amount"], "400.00")
        self.assertEqual(balance["outstanding_balance"], "600.00")

    async def test_not_found(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.get_customer("99")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(
            caught.exception.detail["message"],
            "Customer with id 99 not found",
        )


class SaleServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            _,
            self.sale_repository,
            self.stock_repository,
            _,
            self.service,
            self.admin,
            self.operator,
        ) = build_services()
        self.stock_repository.production.append(
            (date.fromisoformat(TODAY), Decimal("100.00"))
        )

    async def test_record_list_and_update(self) -> None:
        payload = CreateSaleRequest.model_validate(
            {
                "customer_id": 1,
                "sale_date": TODAY,
                "litres": 10,
                "rate": 50,
            }
        )
        result = await self.service.record_sale(payload, self.operator)
        self.assertEqual(result["litres"], "10.00")
        self.assertEqual(result["rate"], "50.00")
        self.assertEqual(result["amount"], "500.00")
        self.assertEqual(result["payment_status"], "unpaid")
        self.assertEqual(result["stock_remaining"], "90.00")
        self.assertEqual(self.sale_repository.commits, 1)

        listing = await self.service.list_sales(
            SaleQuery(page=1, page_size=10)
        )
        self.assertEqual(listing["total"], 1)
        item = listing["items"][0]
        self.assertNotIn("address", item["customer"])
        self.assertEqual(item["recorder"]["username"], "ramesh_operator")

        detail = await self.service.get_sale("1")
        self.assertIn("address", detail["customer"])

        updated = await self.service.update_sale(
            "1",
            UpdateSaleRequest.model_validate({"litres": 12, "rate": 60}),
            self.admin,
        )
        self.assertEqual(updated["litres"], "12.00")
        self.assertEqual(updated["amount"], "720.00")
        self.assertEqual(updated["recorded_by"], self.admin.id)

    async def test_defaults_rate_and_stock_guard(self) -> None:
        payload = CreateSaleRequest.model_validate(
            {
                "customer_id": 1,
                "sale_date": TODAY,
                "litres": 1,
            }
        )
        result = await self.service.record_sale(payload, self.admin)
        self.assertEqual(result["rate"], "50.00")

        insufficient = CreateSaleRequest.model_validate(
            {
                "customer_id": 1,
                "sale_date": TODAY,
                "litres": 200,
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_sale(insufficient, self.admin)
        self.assertEqual(
            caught.exception.detail["code"],
            "STOCK_INSUFFICIENT",
        )
        self.assertEqual(self.sale_repository.rollbacks, 1)

    async def test_permissions_and_inactive_customer(self) -> None:
        future = CreateSaleRequest.model_validate(
            {
                "customer_id": 1,
                "sale_date": "2999-01-01",
                "litres": 1,
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_sale(future, self.admin)
        self.assertEqual(
            caught.exception.detail["code"],
            "INVALID_SALE_DATE",
        )

        past = CreateSaleRequest.model_validate(
            {
                "customer_id": 1,
                "sale_date": "2020-01-01",
                "litres": 1,
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_sale(past, self.operator)
        self.assertEqual(
            caught.exception.detail["code"],
            "OPERATOR_DATE_RESTRICTION",
        )

        inactive = CreateSaleRequest.model_validate(
            {
                "customer_id": 2,
                "sale_date": TODAY,
                "litres": 1,
            }
        )
        with self.assertRaises(HTTPException) as caught:
            await self.service.record_sale(inactive, self.admin)
        self.assertEqual(
            caught.exception.detail["code"],
            "CUSTOMER_NOT_ACTIVE",
        )

    async def test_list_range_and_validation(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            await self.service.list_sales(
                SaleQuery(
                    page=1,
                    page_size=10,
                    from_date="2024-02-01",
                    to_date="2024-01-01",
                )
            )
        self.assertEqual(
            caught.exception.detail["code"],
            "INVALID_DATE_RANGE",
        )

        result = await self.service.list_sales(
            SaleQuery(
                page=1,
                page_size=10,
                sale_date="2024-01-10",
                from_date="2024-02-01",
                to_date="2024-01-01",
            )
        )
        self.assertEqual(result["total"], 0)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        (
            self.customer_repository,
            self.sale_repository,
            self.stock_repository,
            _,
            _,
            self.admin,
            self.operator,
        ) = build_services()
        self.stock_repository.production.append(
            (date.fromisoformat(TODAY), Decimal("100.00"))
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
        app.dependency_overrides[get_stock_repository] = (
            lambda: self.stock_repository
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
        return {"Authorization": f"Bearer {token}"}

    async def test_customer_endpoints(self) -> None:
        created = await self.client.post(
            "/api/v1/customers",
            headers=self._auth(self.operator),
            json={
                "name": "New Dairy",
                "phone": "12345",
                "address": "Road",
                "rate_per_litre": 55.5,
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["customer"]["rate_per_litre"], "55.50")

        listing = await self.client.get(
            "/api/v1/customers?search=New",
            headers=self._auth(),
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)

        detail = await self.client.get(
            "/api/v1/customers/1",
            headers=self._auth(),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["customer"]["name"], "Ramesh Dairy")

        updated = await self.client.put(
            "/api/v1/customers/1",
            headers=self._auth(),
            json={"name": "Changed"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["customer"]["name"], "Changed")

        self.customer_repository.financials_by_id[1] = (
            Decimal("100.00"),
            Decimal("30.00"),
        )
        balance = await self.client.get(
            "/api/v1/customers/1/balance",
            headers=self._auth(),
        )
        self.assertEqual(balance.status_code, 200)
        self.assertEqual(balance.json()["outstanding_balance"], "70.00")

        missing = await self.client.get(
            "/api/v1/customers/999",
            headers=self._auth(),
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            missing.json()["error"]["message"],
            "Customer with id 999 not found",
        )

    async def test_customer_validation_messages(self) -> None:
        cases = [
            (
                {},
                "name: Invalid input: expected string, received undefined",
            ),
            (
                {"name": "", "rate_per_litre": 1},
                "name: Name cannot be empty",
            ),
            (
                {"name": "A", "rate_per_litre": 0},
                "rate_per_litre: Rate per litre must be greater than zero",
            ),
            (
                {"name": "A", "rate_per_litre": 1, "phone": "1" * 31},
                "phone: Too big: expected string to have <=30 characters",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                response = await self.client.post(
                    "/api/v1/customers",
                    headers=self._auth(),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )

    async def test_sale_endpoints_and_validation(self) -> None:
        created = await self.client.post(
            "/api/v1/sales",
            headers=self._auth(self.operator),
            json={
                "customer_id": 1,
                "sale_date": TODAY,
                "litres": 10,
                "rate": 50,
            },
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["amount"], "500.00")
        self.assertEqual(body["stock_remaining"], "90.00")

        listing = await self.client.get(
            "/api/v1/sales?customer_id=1",
            headers=self._auth(),
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertNotIn("address", listing.json()["items"][0]["customer"])

        detail = await self.client.get(
            "/api/v1/sales/1",
            headers=self._auth(),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertIn("address", detail.json()["sale"]["customer"])

        updated = await self.client.put(
            "/api/v1/sales/1",
            headers=self._auth(),
            json={"litres": 12},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["sale"]["amount"], "600.00")

        cases = [
            (
                {},
                "customer_id: Invalid input: expected number, received NaN",
            ),
            (
                {"customer_id": 1, "litres": 1},
                "sale_date: Invalid input: expected string, received undefined",
            ),
            (
                {"customer_id": 1, "sale_date": TODAY},
                "litres: Invalid input: expected number, received NaN",
            ),
            (
                {"customer_id": 0, "sale_date": TODAY, "litres": 1},
                "customer_id: Valid customer ID is required",
            ),
            (
                {"customer_id": 1, "sale_date": "bad", "litres": 1},
                "sale_date: Sale date must be in YYYY-MM-DD format",
            ),
            (
                {"customer_id": 1, "sale_date": TODAY, "litres": 0},
                "litres: Litres sold must be greater than zero",
            ),
            (
                {
                    "customer_id": 1,
                    "sale_date": TODAY,
                    "litres": 1,
                    "rate": 0,
                },
                "rate: Rate must be greater than zero",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                response = await self.client.post(
                    "/api/v1/sales",
                    headers=self._auth(),
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )

    async def test_sale_query_validation(self) -> None:
        cases = [
            (
                "/api/v1/sales?customer_id=0",
                "customer_id: Too small: expected number to be >0",
            ),
            (
                "/api/v1/sales?customer_id=1.5",
                "customer_id: Invalid input: expected int, received number",
            ),
            (
                "/api/v1/sales?sale_date=bad",
                "sale_date: Invalid string: must match pattern "
                "/^\\d{4}-\\d{2}-\\d{2}$/",
            ),
            (
                "/api/v1/sales?payment_status=partial",
                'payment_status: Invalid option: expected one of '
                '"unpaid"|"paid"',
            ),
            (
                "/api/v1/sales?page=0",
                "page: Too small: expected number to be >=1",
            ),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                response = await self.client.get(url, headers=self._auth())
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["message"],
                    expected,
                )

    async def test_sale_business_errors(self) -> None:
        future = await self.client.post(
            "/api/v1/sales",
            headers=self._auth(),
            json={
                "customer_id": 1,
                "sale_date": "2999-01-01",
                "litres": 1,
            },
        )
        self.assertEqual(future.status_code, 400)
        self.assertEqual(
            future.json()["error"]["code"],
            "INVALID_SALE_DATE",
        )

        inactive = await self.client.post(
            "/api/v1/sales",
            headers=self._auth(),
            json={
                "customer_id": 2,
                "sale_date": TODAY,
                "litres": 1,
            },
        )
        self.assertEqual(inactive.status_code, 400)
        self.assertEqual(
            inactive.json()["error"]["code"],
            "CUSTOMER_NOT_ACTIVE",
        )

        insufficient = await self.client.post(
            "/api/v1/sales",
            headers=self._auth(),
            json={
                "customer_id": 1,
                "sale_date": TODAY,
                "litres": 200,
            },
        )
        self.assertEqual(insufficient.status_code, 400)
        self.assertEqual(
            insufficient.json()["error"]["code"],
            "STOCK_INSUFFICIENT",
        )


if __name__ == "__main__":
    unittest.main()
