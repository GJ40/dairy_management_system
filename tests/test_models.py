from __future__ import annotations

import unittest
from decimal import Decimal

from sqlalchemy import Numeric
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.base import Base
from app.models import (
    Buffalo,
    EmailNotificationRecipient,
    EmailSenderIdentity,
    ExpenseCategory,
    User,
)

EXPECTED_TABLES = {
    "buffaloes",
    "customer_order_events",
    "customer_orders",
    "customer_portal_account_events",
    "customer_portal_accounts",
    "customer_queries",
    "customer_query_messages",
    "customers",
    "email_notification_recipients",
    "email_sender_identities",
    "email_smtp_profiles",
    "email_workflow_mappings",
    "expense_categories",
    "expenses",
    "invoice_sales",
    "invoices",
    "milk_production",
    "milk_wastage",
    "password_reset_tokens",
    "sales",
    "security_audit_events",
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
    "fk_email_notification_recipients_created_by",
    "fk_email_notification_recipients_updated_by",
    "fk_email_sender_identities_created_by",
    "fk_email_sender_identities_updated_by",
    "fk_email_smtp_profiles_created_by",
    "fk_email_smtp_profiles_updated_by",
    "fk_email_workflow_mappings_created_by",
    "fk_email_workflow_mappings_reply_to_sender_identity_id",
    "fk_email_workflow_mappings_sender_identity_id",
    "fk_email_workflow_mappings_updated_by",
    "fk_sales_source_order_id",
    "fk_security_audit_events_actor_account_id",
    "fk_security_audit_events_actor_user_id",
}

NO_UPDATED_AT_TABLES = {
    "customer_order_events",
    "customer_portal_account_events",
    "customer_query_messages",
    # Token rows are written once and only ever flipped to used; like the
    # event tables above they are append-only and carry no updated_at.
    "password_reset_tokens",
    "security_audit_events",
}


class ModelSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configure_mappers()

    def test_all_tables_present(self) -> None:
        self.assertEqual(set(Base.metadata.tables), EXPECTED_TABLES)

    def test_users_duplicate_unique_indexes_preserved(self) -> None:
        names = {index.name for index in Base.metadata.tables["users"].indexes}
        self.assertEqual(
            names,
            {
                "email",
                "username",
                "users_email",
                "users_username",
                "users_lock_reason",
            },
        )

    def test_login_lockout_columns_on_both_account_tables(self) -> None:
        for name in ("users", "customer_portal_accounts"):
            columns = Base.metadata.tables[name].c
            for column in (
                "failed_login_count",
                "failed_login_first_at",
                "locked_at",
                "lock_reason",
            ):
                self.assertIn(column, columns, name)

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
        self.assertEqual(len(foreign_keys), 38)
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

    def test_security_audit_event_is_append_only(self) -> None:
        table = Base.metadata.tables["security_audit_events"]
        self.assertIn("metadata", table.c)
        self.assertNotIn("updated_at", table.c)
        self.assertNotIn("is_deleted", table.c)
        self.assertIsNotNone(table.c.created_at.default)
        self.assertEqual(
            {index.name for index in table.indexes},
            {
                "security_audit_events_actor_account_id_created_at",
                "security_audit_events_actor_user_id_created_at",
                "security_audit_events_created_at",
                "security_audit_events_event_type_created_at",
                "security_audit_events_ip_created_at",
                "security_audit_events_request_id",
                "security_audit_events_resource_created_at",
            },
        )

    def test_email_normalization(self) -> None:
        user = User(email="  Admin@Example.COM ")
        self.assertEqual(user.email, "admin@example.com")

    def test_email_settings_tables_are_additive(self) -> None:
        profiles = Base.metadata.tables["email_smtp_profiles"]
        self.assertIn("active_slot", profiles.c)
        self.assertIn("config_fingerprint", profiles.c)
        self.assertIn("username_encrypted", profiles.c)
        self.assertIn("password_encrypted", profiles.c)
        # Only ciphertext columns may exist; no plaintext credential column.
        self.assertNotIn("username", profiles.c)
        self.assertNotIn("password", profiles.c)

        active_slot = {
            index.name: index for index in profiles.indexes
        }["email_smtp_profiles_active_slot"]
        self.assertTrue(active_slot.unique)
        self.assertEqual([column.name for column in active_slot.columns], ["active_slot"])

        senders = Base.metadata.tables["email_sender_identities"]
        sender_email = {
            index.name: index for index in senders.indexes
        }["email_sender_identities_email"]
        self.assertTrue(sender_email.unique)

        mappings = Base.metadata.tables["email_workflow_mappings"]
        mapping_key = {
            index.name: index for index in mappings.indexes
        }["email_workflow_mappings_mapping_key"]
        self.assertTrue(mapping_key.unique)

        recipients = Base.metadata.tables["email_notification_recipients"]
        recipient_key = {
            index.name: index for index in recipients.indexes
        }["email_notification_recipients_mapping_key_email"]
        self.assertTrue(recipient_key.unique)
        self.assertEqual(
            [column.name for column in recipient_key.columns],
            ["mapping_key", "email"],
        )

    def test_email_settings_email_normalization(self) -> None:
        sender = EmailSenderIdentity(
            display_name="Operations",
            email="  Ops@Example.COM ",
            reply_to_email=" Support@Example.COM ",
        )
        self.assertEqual(sender.email, "ops@example.com")
        self.assertEqual(sender.reply_to_email, "support@example.com")

        recipient = EmailNotificationRecipient(
            scope="event",
            mapping_key="order.submitted",
            email=" OPS@Example.COM ",
        )
        self.assertEqual(recipient.email, "ops@example.com")

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
