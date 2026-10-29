from __future__ import annotations

import unittest
from decimal import Decimal

from sqlalchemy import Numeric
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.base import Base
from app.models import Buffalo, ExpenseCategory, User

EXPECTED_TABLES = {
    "buffaloes",
    "customers",
    "expense_categories",
    "expenses",
    "invoice_sales",
    "invoices",
    "milk_production",
    "milk_wastage",
    "sales",
    "users",
}


class ModelSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configure_mappers()

    def test_all_tables_present(self) -> None:
        self.assertEqual(set(Base.metadata.tables), EXPECTED_TABLES)

    def test_users_duplicate_unique_indexes_preserved(self) -> None:
        names = {index.name for index in Base.metadata.tables["users"].indexes}
        self.assertEqual(names, {"email", "username", "users_email", "users_username"})

    def test_buffalo_duplicate_unique_indexes_preserved(self) -> None:
        names = {index.name for index in Base.metadata.tables["buffaloes"].indexes}
        self.assertEqual(names, {"buffaloes_status", "buffaloes_tag_no", "tag_no"})

    def test_invoice_sales_unique_indexes_preserved(self) -> None:
        names = {index.name for index in Base.metadata.tables["invoice_sales"].indexes}
        self.assertEqual(
            names,
            {
                "invoice_sales_invoice_id",
                "invoice_sales_sale_id",
                "invoice_sales_sale_id_invoice_id_unique",
            },
        )

    def test_all_foreign_keys_cascade(self) -> None:
        foreign_keys = [
            fk
            for table in Base.metadata.tables.values()
            for fk in table.foreign_keys
        ]
        self.assertEqual(len(foreign_keys), 10)
        for fk in foreign_keys:
            self.assertEqual(fk.ondelete, "CASCADE", fk.name)
            self.assertEqual(fk.onupdate, "CASCADE", fk.name)

    def test_decimal_precision(self) -> None:
        litres = Base.metadata.tables["milk_production"].c.litres.type
        amount = Base.metadata.tables["sales"].c.amount.type
        self.assertIsInstance(litres, Numeric)
        self.assertIsInstance(amount, Numeric)
        self.assertEqual((litres.precision, litres.scale), (10, 2))
        self.assertEqual((amount.precision, amount.scale), (12, 2))

    def test_timestamps_configured(self) -> None:
        for table in Base.metadata.tables.values():
            self.assertIsNotNone(table.c.created_at.default)
            self.assertIsNotNone(table.c.updated_at.default)
            self.assertIsNotNone(table.c.updated_at.onupdate)

    def test_table_collation(self) -> None:
        for table in Base.metadata.tables.values():
            self.assertEqual(
                table.dialect_options["mysql"]["collate"],
                "utf8mb4_0900_ai_ci",
            )

    def test_email_normalization(self) -> None:
        user = User(email="  Admin@Example.COM ")
        self.assertEqual(user.email, "admin@example.com")

    def test_tag_normalization(self) -> None:
        buffalo = Buffalo(tag_no="  tag-101 ")
        self.assertEqual(buffalo.tag_no, "TAG-101")

    def test_category_normalization(self) -> None:
        category = ExpenseCategory(name="  Feed ")
        self.assertEqual(category.name, "feed")

    def test_paid_amount_default(self) -> None:
        default = Base.metadata.tables["invoices"].c.paid_amount.default
        self.assertEqual(default.arg, Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
