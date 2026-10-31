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
    "customer_order_events",
    "customer_orders",
    "customer_portal_account_events",
    "customer_portal_accounts",
    "customer_queries",
    "customer_query_messages",
    "customers",
    "expense_categories",
    "expenses",
    "invoice_sales",
    "invoices",
    "milk_production",
    "milk_wastage",
    "password_reset_tokens",
    "sales",
    "users",
}

EXPECTED_SET_NULL_FKS = {
    "fk_customer_order_events_actor_account_id",
    "fk_customer_order_events_actor_user_id",
    "fk_customer_orders_reviewed_by",
    "fk_customer_portal_account_events_actor_user_id",
    "fk_customer_queries_assigned_to",
    "fk_customer_query_messages_sender_account_id",
    "fk_customer_query_messages_sender_user_id",
    "fk_sales_source_order_id",
}

NO_UPDATED_AT_TABLES = {
    "customer_order_events",
    "customer_portal_account_events",
    "customer_query_messages",
    # Token rows are written once and only ever flipped to used; like the
    # event tables above they are append-only and carry no updated_at.
    "password_reset_tokens",
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

    def test_foreign_key_policies(self) -> None:
        foreign_keys = {
            fk.name: fk
            for table in Base.metadata.tables.values()
            for fk in table.foreign_keys
        }
        self.assertEqual(len(foreign_keys), 26)
        for name, fk in foreign_keys.items():
            self.assertEqual(fk.onupdate, "CASCADE", name)
            expected = "SET NULL" if name in EXPECTED_SET_NULL_FKS else "CASCADE"
            self.assertEqual(fk.ondelete, expected, name)

    def test_portal_unique_constraints(self) -> None:
        account_indexes = {
            index.name: index
            for index in Base.metadata.tables["customer_portal_accounts"].indexes
        }
        self.assertTrue(account_indexes["customer_portal_accounts_customer_id"].unique)
        self.assertTrue(account_indexes["customer_portal_accounts_email"].unique)

        sales_indexes = {
            index.name: index for index in Base.metadata.tables["sales"].indexes
        }
        self.assertTrue(sales_indexes["sales_source_order_id"].unique)

    def test_order_decimal_precision(self) -> None:
        orders = Base.metadata.tables["customer_orders"].c
        self.assertEqual(
            (orders.quantity_litres.type.precision, orders.quantity_litres.type.scale),
            (10, 2),
        )
        self.assertEqual(
            (orders.rate_snapshot.type.precision, orders.rate_snapshot.type.scale),
            (10, 2),
        )
        self.assertEqual(
            (orders.estimated_total.type.precision, orders.estimated_total.type.scale),
            (12, 2),
        )

    def test_decimal_precision(self) -> None:
        litres = Base.metadata.tables["milk_production"].c.litres.type
        amount = Base.metadata.tables["sales"].c.amount.type
        self.assertIsInstance(litres, Numeric)
        self.assertIsInstance(amount, Numeric)
        self.assertEqual((litres.precision, litres.scale), (10, 2))
        self.assertEqual((amount.precision, amount.scale), (12, 2))

    def test_timestamps_configured(self) -> None:
        for name, table in Base.metadata.tables.items():
            self.assertIsNotNone(table.c.created_at.default)
            if name in NO_UPDATED_AT_TABLES:
                self.assertNotIn("updated_at", table.c)
                continue
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
