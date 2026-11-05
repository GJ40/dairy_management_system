from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

Severity = Literal["info", "warning", "critical"]
Outcome = Literal["success", "failure", "denied"]
ActorType = Literal["staff", "customer", "system", "anonymous"]

ANONYMOUS = frozenset({"anonymous"})
STAFF = frozenset({"staff"})
CUSTOMER = frozenset({"customer"})
SYSTEM = frozenset({"system"})
HUMAN = frozenset({"staff", "customer"})
STAFF_OR_ANONYMOUS = frozenset({"staff", "anonymous"})
ANY_ACTOR = frozenset({"staff", "customer", "system", "anonymous"})


@dataclass(frozen=True)
class AuditEventDefinition:
    severity: Severity
    outcome: Outcome
    actor_types: frozenset[str]
    allowed_metadata: frozenset[str]


def _event(
    severity: Severity,
    outcome: Outcome,
    actor_types: frozenset[str],
    metadata: tuple[str, ...] = (),
) -> AuditEventDefinition:
    return AuditEventDefinition(
        severity=severity,
        outcome=outcome,
        actor_types=actor_types,
        allowed_metadata=frozenset(metadata),
    )


EVENT_DEFINITIONS: Mapping[str, AuditEventDefinition] = MappingProxyType(
    {
        "auth.login.succeeded": _event(
            "info", "success", HUMAN, ("scope", "role")
        ),
        "auth.login.failed": _event(
            "warning",
            "failure",
            frozenset({"anonymous", "staff", "customer"}),
            ("scope", "reason_code", "account_resolved"),
        ),
        "auth.login.throttled": _event(
            "warning", "failure", ANONYMOUS, ("scope", "retry_after_seconds")
        ),
        "auth.refresh.failed": _event(
            "info",
            "failure",
            frozenset({"anonymous", "staff", "customer"}),
            ("scope", "reason_code"),
        ),
        "auth.logout": _event(
            "info",
            "success",
            frozenset({"anonymous", "staff", "customer"}),
            ("scope",),
        ),
        "auth.password.reset.requested": _event(
            "info",
            "success",
            frozenset({"anonymous", "staff", "customer"}),
            ("scope", "account_resolved"),
        ),
        "auth.password.reset.completed": _event(
            "warning", "success", HUMAN, ("scope",)
        ),
        "auth.password.changed": _event(
            "warning", "success", STAFF, ("target_user_id", "target_role")
        ),
        "auth.account.activated": _event(
            "info", "success", CUSTOMER, ("account_id", "customer_id")
        ),
        "auth.account.locked": _event(
            "critical",
            "success",
            SYSTEM,
            ("scope", "failure_count", "window_minutes"),
        ),
        "auth.alert.failed_login.sent": _event(
            "info", "success", SYSTEM, ("scope", "failure_count", "window_minutes")
        ),
        "auth.alert.failed_login.suppressed": _event(
            "info",
            "success",
            SYSTEM,
            ("scope", "failure_count", "cooldown_minutes"),
        ),
        "auth.alert.failed_login.delivery_failed": _event(
            "warning", "failure", SYSTEM, ("scope", "reason_code")
        ),
        "user.created": _event(
            "warning", "success", STAFF, ("target_user_id", "target_role")
        ),
        "user.updated": _event(
            "warning", "success", STAFF, ("target_user_id", "changed_fields")
        ),
        "user.role.changed": _event(
            "critical",
            "success",
            STAFF,
            ("target_user_id", "old_role", "new_role"),
        ),
        "user.deactivated": _event(
            "warning", "success", STAFF, ("target_user_id", "target_role")
        ),
        "user.reactivated": _event(
            "warning", "success", STAFF, ("target_user_id", "target_role")
        ),
        "user.unlocked": _event(
            "warning", "success", STAFF, ("target_user_id", "target_role")
        ),
        "user.deleted": _event(
            "critical", "success", STAFF, ("target_user_id", "target_role")
        ),
        "portal_account.provisioned": _event(
            "warning", "success", STAFF, ("account_id", "customer_id")
        ),
        "portal_account.reactivated": _event(
            "warning", "success", STAFF, ("account_id", "customer_id")
        ),
        "portal_account.deactivated": _event(
            "warning",
            "success",
            STAFF,
            ("account_id", "customer_id", "reason_present"),
        ),
        "portal_account.activation.reset": _event(
            "warning", "success", STAFF, ("account_id", "customer_id")
        ),
        "portal_account.unlocked": _event(
            "warning", "success", STAFF, ("account_id", "customer_id")
        ),
        "customer.created": _event("info", "success", STAFF, ("customer_id",)),
        "customer.updated": _event(
            "info", "success", STAFF, ("customer_id", "changed_fields")
        ),
        "query.created": _event(
            "info", "success", CUSTOMER, ("query_id", "query_no", "category")
        ),
        "query.customer_message": _event(
            "info", "success", CUSTOMER, ("query_id", "message_id")
        ),
        "query.staff_message": _event(
            "info", "success", STAFF, ("query_id", "message_id", "is_internal")
        ),
        "query.internal_note": _event(
            "warning", "success", STAFF, ("query_id", "message_id", "is_internal")
        ),
        "query.status.changed": _event(
            "info", "success", STAFF, ("query_id", "from_status", "to_status")
        ),
        "query.assigned": _event(
            "warning",
            "success",
            STAFF,
            ("query_id", "from_user_id", "to_user_id"),
        ),
        "query.unassigned": _event(
            "warning", "success", STAFF, ("query_id", "from_user_id")
        ),
        "query.access.denied": _event(
            "warning",
            "denied",
            STAFF,
            ("query_id", "assigned_to_user_id", "attempted_action"),
        ),
        "sale.created": _event(
            "info",
            "success",
            STAFF,
            ("sale_id", "customer_id", "sale_date", "litres", "amount"),
        ),
        "sale.updated": _event(
            "warning", "success", STAFF, ("sale_id", "customer_id", "changed_fields")
        ),
        "invoice.created": _event(
            "info",
            "success",
            STAFF,
            ("invoice_id", "invoice_no", "customer_id", "sale_count", "total_amount"),
        ),
        "invoice.payment.updated": _event(
            "warning",
            "success",
            STAFF,
            ("invoice_id", "from_status", "to_status", "amount_paid"),
        ),
        "expense.created": _event(
            "info",
            "success",
            STAFF,
            ("expense_id", "category_id", "expense_date", "amount"),
        ),
        "expense.updated": _event(
            "warning", "success", STAFF, ("expense_id", "changed_fields")
        ),
        "expense_category.created": _event(
            "info", "success", STAFF, ("category_id",)
        ),
        "order.created": _event(
            "info",
            "success",
            CUSTOMER,
            ("order_id", "order_no", "customer_id", "requested_date", "quantity_litres"),
        ),
        "order.approved": _event(
            "info", "success", STAFF, ("order_id", "from_status", "to_status")
        ),
        "order.rejected": _event(
            "warning", "success", STAFF, ("order_id", "from_status", "to_status")
        ),
        "order.fulfilled": _event(
            "warning",
            "success",
            STAFF,
            ("order_id", "sale_id", "invoice_id", "amount"),
        ),
        "order.cancelled": _event(
            "warning", "success", HUMAN, ("order_id", "from_status", "to_status")
        ),
        "buffalo.created": _event(
            "info", "success", STAFF, ("buffalo_id", "status")
        ),
        "buffalo.updated": _event(
            "info", "success", STAFF, ("buffalo_id", "changed_fields")
        ),
        "buffalo.status.changed": _event(
            "warning", "success", STAFF, ("buffalo_id", "from_status", "to_status")
        ),
        "production.recorded": _event(
            "info",
            "success",
            STAFF,
            ("production_id", "buffalo_id", "prod_date", "session_name", "litres"),
        ),
        "production.updated": _event(
            "warning",
            "success",
            STAFF,
            ("production_id", "buffalo_id", "prod_date", "session_name", "litres"),
        ),
        "production.bulk_recorded": _event(
            "info",
            "success",
            STAFF,
            ("prod_date", "entry_count", "created_count", "updated_count"),
        ),
        "wastage.recorded": _event(
            "warning",
            "success",
            STAFF,
            ("wastage_id", "waste_date", "litres", "reason"),
        ),
        "record.soft_deleted": _event(
            "critical", "success", STAFF, ("resource", "record_id")
        ),
        "report.exported": _event(
            "info",
            "success",
            STAFF,
            ("report_type", "period_start", "period_end", "role"),
        ),
        "invoice.pdf.downloaded": _event(
            "info", "success", HUMAN, ("invoice_id", "scope")
        ),
        "security.authorization.denied": _event(
            "warning",
            "denied",
            HUMAN,
            ("required_roles", "actual_role", "scope"),
        ),
        "security.rate_limit.triggered": _event(
            "warning",
            "denied",
            ANY_ACTOR,
            ("endpoint", "retry_after_seconds"),
        ),
        "security.audit.write_failed": _event(
            "critical", "failure", SYSTEM, ("attempted_event_type", "error_class")
        ),
    }
)


def get_event_definition(event_type: str) -> AuditEventDefinition:
    try:
        return EVENT_DEFINITIONS[event_type]
    except KeyError as exc:
        raise ValueError(f"Unknown security audit event type: {event_type}") from exc
