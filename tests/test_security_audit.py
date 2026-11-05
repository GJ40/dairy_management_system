from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from app.core.audit_events import EVENT_DEFINITIONS, get_event_definition
from app.core.request_context import RequestContext
from app.models.security_audit_event import SecurityAuditEvent
from app.services.security_audit_service import (
    SecurityAuditService,
    sanitize_metadata,
)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[SecurityAuditEvent] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = False

    def add(self, event: SecurityAuditEvent) -> None:
        self.events.append(event)

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("database unavailable")

    async def rollback(self) -> None:
        self.rollbacks += 1


def context() -> RequestContext:
    return RequestContext(
        request_id="a" * 32,
        ip_address="203.0.113.9",
        user_agent="pytest",
        http_method="POST",
        path="/api/v1/auth/login",
    )


class AuditEventRegistryTests(unittest.TestCase):
    def test_catalogued_event_has_severity_outcome_and_metadata(self) -> None:
        definition = get_event_definition("auth.login.failed")
        self.assertEqual(definition.severity, "warning")
        self.assertEqual(definition.outcome, "failure")
        self.assertIn("staff", definition.actor_types)
        self.assertIn("scope", definition.allowed_metadata)
        self.assertIn("account_resolved", definition.allowed_metadata)

    def test_unknown_event_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown security audit event"):
            get_event_definition("auth.not_real")

    def test_every_definition_has_valid_fields(self) -> None:
        self.assertTrue(EVENT_DEFINITIONS)
        for event_type, definition in EVENT_DEFINITIONS.items():
            self.assertTrue(event_type)
            self.assertIn(definition.severity, {"info", "warning", "critical"})
            self.assertIn(definition.outcome, {"success", "failure", "denied"})
            self.assertTrue(definition.actor_types)
            self.assertTrue(
                definition.actor_types
                <= {"staff", "customer", "system", "anonymous"}
            )


class MetadataSanitizerTests(unittest.TestCase):
    def test_allowed_metadata_is_kept(self) -> None:
        cleaned = sanitize_metadata(
            {
                "scope": "staff",
                "account_resolved": True,
                "failure_count": 5,
                "changed_fields": ["email", "role"],
            },
            allowed_keys=frozenset(
                {"scope", "account_resolved", "failure_count", "changed_fields"}
            ),
        )
        self.assertEqual(
            cleaned,
            {
                "scope": "staff",
                "account_resolved": True,
                "failure_count": 5,
                "changed_fields": ["email", "role"],
            },
        )

    def test_unknown_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not allowed"):
            sanitize_metadata(
                {"unexpected": "value"},
                allowed_keys=frozenset({"scope"}),
            )

    def test_forbidden_key_is_rejected_even_if_allowlisted(self) -> None:
        with self.assertRaisesRegex(ValueError, "Forbidden"):
            sanitize_metadata(
                {"password": "secret"},
                allowed_keys=frozenset({"password"}),
            )

    def test_nested_forbidden_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden key"):
            sanitize_metadata(
                {"scope": {"access_token": "abc"}},
                allowed_keys=frozenset({"scope"}),
            )

    def test_values_are_json_safe(self) -> None:
        cleaned = sanitize_metadata(
            {
                "amount": Decimal("12.50"),
                "sale_date": date(2026, 11, 4),
                "at": datetime(2026, 11, 4, 10, 30, tzinfo=timezone.utc),
            },
            allowed_keys=frozenset({"amount", "sale_date", "at"}),
        )
        self.assertEqual(cleaned["amount"], "12.50")
        self.assertEqual(cleaned["sale_date"], "2026-11-04")
        self.assertEqual(cleaned["at"], "2026-11-04T10:30:00+00:00")

    def test_non_finite_number_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-finite"):
            sanitize_metadata(
                {"amount": float("inf")},
                allowed_keys=frozenset({"amount"}),
            )

    def test_controls_are_stripped_from_strings(self) -> None:
        cleaned = sanitize_metadata(
            {"scope": "staff\nadmin"},
            allowed_keys=frozenset({"scope"}),
        )
        self.assertEqual(cleaned["scope"], "staff admin")


class AuditServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_record_builds_an_immutable_event(self) -> None:
        repository = FakeAuditRepository()
        service = SecurityAuditService(repository)

        event = await service.record(
            event_type="auth.login.failed",
            context=context(),
            metadata={"scope": "staff", "account_resolved": False},
            reason_code="bad_password",
        )

        self.assertEqual(repository.events, [event])
        self.assertEqual(event.event_type, "auth.login.failed")
        self.assertEqual(event.outcome, "failure")
        self.assertEqual(event.severity, "warning")
        self.assertEqual(event.actor_type, "anonymous")
        self.assertIsNone(event.created_at.tzinfo)
        self.assertEqual(event.ip_address, "203.0.113.9")
        self.assertEqual(event.request_id, "a" * 32)
        self.assertEqual(event.path, "/api/v1/auth/login")
        self.assertEqual(event.reason_code, "bad_password")
        self.assertEqual(
            event.event_metadata,
            {"scope": "staff", "account_resolved": False},
        )

    async def test_actor_is_inferred_from_resolved_identity(self) -> None:
        repository = FakeAuditRepository()
        service = SecurityAuditService(repository)

        staff_event = await service.record(
            event_type="auth.login.failed",
            actor_user_id=7,
            metadata={"scope": "staff", "account_resolved": True},
        )
        customer_event = await service.record(
            event_type="auth.login.failed",
            actor_account_id=9,
            metadata={"scope": "customer", "account_resolved": True},
        )

        self.assertEqual(staff_event.actor_type, "staff")
        self.assertEqual(staff_event.actor_user_id, 7)
        self.assertEqual(customer_event.actor_type, "customer")
        self.assertEqual(customer_event.actor_account_id, 9)

    async def test_system_event_requires_explicit_actor_type(self) -> None:
        repository = FakeAuditRepository()
        service = SecurityAuditService(repository)

        event = await service.record(
            event_type="auth.alert.failed_login.sent",
            actor_type="system",
            metadata={"scope": "staff", "failure_count": 5, "window_minutes": 15},
        )
        self.assertEqual(event.actor_type, "system")

    async def test_unknown_event_is_rejected(self) -> None:
        service = SecurityAuditService(FakeAuditRepository())
        with self.assertRaisesRegex(ValueError, "Unknown security audit event"):
            await service.record(event_type="auth.not_real")

    async def test_actor_type_must_match_the_event_definition(self) -> None:
        service = SecurityAuditService(FakeAuditRepository())
        with self.assertRaisesRegex(ValueError, "not allowed"):
            await service.record(event_type="auth.login.succeeded")

    async def test_two_actor_identities_are_rejected(self) -> None:
        service = SecurityAuditService(FakeAuditRepository())
        with self.assertRaisesRegex(ValueError, "two actor identities"):
            await service.record(
                event_type="security.authorization.denied",
                actor_user_id=1,
                actor_account_id=2,
            )

    async def test_standalone_record_commits(self) -> None:
        repository = FakeAuditRepository()
        service = SecurityAuditService(repository)

        recorded = await service.record_standalone(
            event_type="auth.login.failed",
            context=context(),
        )

        self.assertTrue(recorded)
        self.assertEqual(repository.commits, 1)
        self.assertEqual(len(repository.events), 1)

    async def test_standalone_record_failure_is_swallowed_and_rolled_back(self) -> None:
        repository = FakeAuditRepository()
        repository.fail_commit = True
        service = SecurityAuditService(repository)

        with self.assertLogs("app.security.audit", level="ERROR"):
            recorded = await service.record_standalone(
                event_type="auth.login.failed",
                context=context(),
            )

        self.assertFalse(recorded)
        self.assertEqual(repository.commits, 1)
        self.assertEqual(repository.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
