from __future__ import annotations

import random
import unittest
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import app.models  # noqa: F401
from app.models.buffalo import Buffalo
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.expense_category import ExpenseCategory
from app.models.invoice import Invoice
from app.models.invoice_sale import InvoiceSale
from app.models.milk_production import MilkProduction
from app.models.milk_wastage import MilkWastage
from app.models.sale import Sale
from app.models.user import User
from app.seeders.base_seed import PRD_EXPENSE_CATEGORIES, seed_database
from app.seeders.fake_indian_data import (
    BUFFALO_NAMES,
    EXPENSE_NOTES,
    OPERATORS,
    seed_fake_indian_data,
)
from app.utils.time import get_business_date

TODAY = date.fromisoformat(get_business_date())


class MemoryStore:
    """In-memory stand-in for SeedStore; never touches the database."""

    def __init__(self) -> None:
        self.rows: dict[str, list[Any]] = {}
        self.commits = 0
        self.rollbacks = 0

    def _bucket(self, model: Any) -> list[Any]:
        return self.rows.setdefault(model.__name__, [])

    def all(self, model: Any) -> list[Any]:
        return list(self._bucket(model))

    async def find(self, model: Any, **conditions: Any) -> Any | None:
        for row in self._bucket(model):
            if all(getattr(row, key) == value for key, value in conditions.items()):
                return row
        return None

    async def find_all(self, model: Any) -> list[Any]:
        return list(self._bucket(model))

    async def create(self, model: Any, **values: Any) -> Any:
        instance = model(**values)
        if getattr(instance, "id", None) is None:
            instance.id = len(self._bucket(model)) + 1
        self._bucket(model).append(instance)
        return instance

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakePerson:
    def __init__(self) -> None:
        self._counter = 0

    def full_name(self) -> str:
        self._counter += 1
        return f"Customer {self._counter}"


class FakeFaker:
    def __init__(self) -> None:
        self.person = FakePerson()
        self._counter = 0

    def phone_number(self) -> str:
        self._counter += 1
        return f"+91-90000{self._counter:05d}"

    def street_address(self) -> str:
        return "12 Dairy Lane"

    def city(self) -> str:
        return "Anand"


class LegacyFakeFaker:
    """Old Faker releases expose name/phone/address instead of person/phone_number."""

    def __init__(self) -> None:
        self._counter = 0

    def name(self) -> str:
        self._counter += 1
        return f"Legacy Customer {self._counter}"

    def phone(self) -> str:
        return "+91-9000099999"

    def address(self) -> str:
        return "45 Farm Road"


class BaseSeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_categories_and_admin(self) -> None:
        store = MemoryStore()
        summary = await seed_database(store)  # type: ignore[arg-type]

        self.assertEqual(
            summary["categories_created"], list(PRD_EXPENSE_CATEGORIES)
        )
        self.assertTrue(summary["admin_created"])
        self.assertEqual(summary["admin_email"], "admin@dairyfarm.com")

        categories = store.all(ExpenseCategory)
        self.assertEqual(len(categories), 6)
        self.assertEqual(
            sorted(category.name for category in categories),
            sorted(PRD_EXPENSE_CATEGORIES),
        )

        admins = store.all(User)
        self.assertEqual(len(admins), 1)
        self.assertEqual(admins[0].role, "admin")
        self.assertTrue(admins[0].is_active)
        self.assertNotEqual(admins[0].password_hash, "")

    async def test_second_run_is_idempotent(self) -> None:
        store = MemoryStore()
        await seed_database(store)  # type: ignore[arg-type]
        summary = await seed_database(store)  # type: ignore[arg-type]

        self.assertEqual(summary["categories_created"], [])
        self.assertFalse(summary["admin_created"])
        self.assertEqual(len(store.all(ExpenseCategory)), 6)
        self.assertEqual(len(store.all(User)), 1)


class LegacyFakerTests(unittest.IsolatedAsyncioTestCase):
    async def test_seeds_with_legacy_faker_api(self) -> None:
        store = MemoryStore()
        summary = await seed_fake_indian_data(
            store,  # type: ignore[arg-type]
            faker=LegacyFakeFaker(),
            rng=random.Random(11),
        )
        self.assertEqual(summary["created"]["customers"], 8)

        customers = store.all(Customer)
        self.assertEqual(len(customers), 8)
        self.assertTrue(customers[0].name.startswith("Legacy Customer "))
        self.assertEqual(customers[0].phone, "+91-9000099999")
        self.assertIn("45 Farm Road", customers[0].address or "")
        self.assertIn("Gujarat", customers[0].address or "")


class FakeDataSeedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = MemoryStore()
        self.rng = random.Random(2026)
        self.summary = await seed_fake_indian_data(
            self.store,  # type: ignore[arg-type]
            faker=FakeFaker(),
            rng=self.rng,
        )
        self.created = self.summary["created"]

    async def test_base_seed_runs_first(self) -> None:
        self.assertEqual(
            self.summary["base"]["categories_created"],
            list(PRD_EXPENSE_CATEGORIES),
        )
        self.assertTrue(self.summary["base"]["admin_created"])

    async def test_users(self) -> None:
        users = self.store.all(User)
        self.assertEqual(len(users), 4)
        operators = [user for user in users if user.role == "operator"]
        self.assertEqual(len(operators), len(OPERATORS))
        self.assertEqual(
            sorted(user.username for user in operators),
            sorted(spec["username"] for spec in OPERATORS),
        )
        self.assertEqual(self.created["operators"], len(OPERATORS))

    async def test_buffaloes(self) -> None:
        buffaloes = self.store.all(Buffalo)
        self.assertEqual(len(buffaloes), len(BUFFALO_NAMES))
        self.assertEqual(buffaloes[0].tag_no, "TAG-0101")
        self.assertEqual(buffaloes[-1].tag_no, "TAG-0112")
        statuses = [buffalo.status for buffalo in buffaloes]
        self.assertEqual(statuses.count("active"), 9)
        self.assertEqual(statuses.count("dry"), 1)
        self.assertEqual(statuses.count("sold"), 1)
        self.assertEqual(statuses.count("dead"), 1)
        self.assertEqual(buffaloes[0].breed, "Murrah")

    async def test_customers(self) -> None:
        customers = self.store.all(Customer)
        self.assertEqual(len(customers), 8)
        self.assertTrue(all(customer.name.startswith("Customer ") for customer in customers))
        self.assertFalse(customers[7].is_active)
        self.assertTrue(all(customer.is_active for customer in customers[:7]))
        self.assertEqual(customers[0].rate_per_litre, Decimal("60.00"))
        self.assertEqual(customers[4].rate_per_litre, Decimal("70.00"))
        self.assertIn("Gujarat", customers[0].address or "")

    async def test_production_grid(self) -> None:
        records = self.store.all(MilkProduction)
        self.assertEqual(len(records), 9 * 6 * 2)
        dates = sorted({record.prod_date for record in records})
        self.assertEqual(len(dates), 6)
        self.assertEqual(dates[-1], TODAY)
        self.assertEqual(dates[0], TODAY - timedelta(days=5))
        self.assertEqual(
            {record.session for record in records},
            {"morning", "evening"},
        )
        for record in records:
            litres = Decimal(str(record.litres))
            self.assertGreaterEqual(litres, Decimal("4.00"))
            self.assertLessEqual(litres, Decimal("9.00"))

    async def test_wastage(self) -> None:
        records = self.store.all(MilkWastage)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].reason, "spilled")
        self.assertEqual(records[0].litres, Decimal("2.50"))
        self.assertEqual(records[0].waste_date, TODAY - timedelta(days=1))

    async def test_sales_and_invoice(self) -> None:
        sales = self.store.all(Sale)
        self.assertEqual(len(sales), 16)
        self.assertTrue(all(sale.payment_status == "unpaid" for sale in sales))
        for sale in sales:
            expected = (
                Decimal(str(sale.litres)) * Decimal(str(sale.rate))
            ).quantize(Decimal("0.01"))
            self.assertEqual(sale.amount, expected)

        invoices = self.store.all(Invoice)
        self.assertEqual(len(invoices), 1)
        invoice = invoices[0]
        self.assertEqual(invoice.invoice_no, f"INV-{TODAY:%Y%m}-0001")
        self.assertEqual(invoice.status, "partial")

        target_sales = [
            sale for sale in sales if sale.customer_id == invoice.customer_id
        ]
        self.assertEqual(len(target_sales), 4)
        total = sum((sale.amount for sale in target_sales), Decimal("0"))
        self.assertEqual(invoice.total_amount, total.quantize(Decimal("0.01")))
        self.assertEqual(
            invoice.paid_amount,
            (total / 2).quantize(Decimal("0.01")),
        )
        self.assertEqual(invoice.period_start, min(s.sale_date for s in target_sales))
        self.assertEqual(invoice.period_end, max(s.sale_date for s in target_sales))

        links = self.store.all(InvoiceSale)
        self.assertEqual(len(links), 4)
        self.assertEqual(
            sorted(link.sale_id for link in links),
            sorted(sale.id for sale in target_sales),
        )

    async def test_expenses(self) -> None:
        expenses = self.store.all(Expense)
        self.assertEqual(len(expenses), 6)
        categories = {
            category.id: category.name
            for category in self.store.all(ExpenseCategory)
        }
        for expense in expenses:
            self.assertIsNotNone(expense.note)
            self.assertGreaterEqual(expense.amount, Decimal("250.00"))
            self.assertLessEqual(expense.amount, Decimal("1450.00"))
            self.assertIn(expense.category_id, categories)
            self.assertGreaterEqual(
                expense.expense_date,
                TODAY - timedelta(days=4),
            )
            self.assertLessEqual(expense.expense_date, TODAY)

        for expense in expenses:
            category_name = categories[expense.category_id]
            self.assertIn(
                expense.note,
                EXPENSE_NOTES.get(category_name, ()),
            )

    async def test_total_rows(self) -> None:
        self.assertEqual(self.created["operators"], 3)
        self.assertEqual(self.created["buffaloes"], 12)
        self.assertEqual(self.created["customers"], 8)
        self.assertEqual(self.created["production"], 108)
        self.assertEqual(self.created["wastage"], 1)
        self.assertEqual(self.created["sales"], 16)
        self.assertEqual(self.created["invoices"], 1)
        self.assertEqual(self.created["invoice_links"], 4)
        self.assertEqual(self.created["expenses"], 6)
        self.assertEqual(self.store.commits, 2)
        self.assertEqual(self.store.rollbacks, 0)

    async def test_is_idempotent(self) -> None:
        before = {name: len(rows) for name, rows in self.store.rows.items()}
        summary = await seed_fake_indian_data(
            self.store,  # type: ignore[arg-type]
            faker=FakeFaker(),
            rng=random.Random(7),
        )

        self.assertEqual(summary["base"]["categories_created"], [])
        self.assertFalse(summary["base"]["admin_created"])

        stable = (
            "User",
            "Buffalo",
            "Customer",
            "MilkProduction",
            "MilkWastage",
            "Invoice",
            "InvoiceSale",
        )
        for model_name in stable:
            self.assertEqual(
                len(self.store.rows[model_name]),
                before[model_name],
                msg=model_name,
            )

        # Node keys sales by (customer, date, litres) and expenses by
        # (category, date, amount), so a re-run with fresh random values adds
        # new rows for those two tables; nothing else is duplicated.
        self.assertEqual(summary["created"]["operators"], 0)
        self.assertEqual(summary["created"]["buffaloes"], 0)
        self.assertEqual(summary["created"]["customers"], 0)
        self.assertEqual(summary["created"]["production"], 0)
        self.assertEqual(summary["created"]["wastage"], 0)
        self.assertEqual(summary["created"]["invoices"], 0)
        self.assertEqual(summary["created"]["invoice_links"], 0)


if __name__ == "__main__":
    unittest.main()
