"""Code-owned workflow catalogue for the email & notification settings module.

The backend catalogue is the single source of truth: the Admin UI renders
whatever ``GET /api/v1/email-settings/workflows`` returns and can never invent
an event key. Mapping rows store a scoped ``mapping_key`` (``application:…``,
``category:…``, ``event:…``) so a category and an event that happen to share a
short name can never collide on the unique column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

APPLICATION_SCOPE = "application"
CATEGORY_SCOPE = "category"
EVENT_SCOPE = "event"

APPLICATION_MAPPING_KEY = "application:default"

AUDIENCE_STAFF = "staff"
AUDIENCE_CUSTOMER = "customer"


@dataclass(frozen=True)
class WorkflowCategory:
    key: str
    label: str


@dataclass(frozen=True)
class WorkflowEvent:
    key: str
    name: str
    category_key: str
    description: str
    audience: str
    # ``implemented`` is false while no code path can send the event yet, so the
    # UI can label the event instead of promising a notification that will not
    # arrive. ``allow_disable`` is false for events whose silence would break
    # security or onboarding.
    implemented: bool = True
    allow_disable: bool = False


CATEGORIES: tuple[WorkflowCategory, ...] = (
    WorkflowCategory("account_security", "Account & Security"),
    WorkflowCategory("customer_portal", "Customer Portal"),
    WorkflowCategory("customer_orders", "Customer Orders"),
    WorkflowCategory("billing_payments", "Billing & Payments"),
    WorkflowCategory("customer_support", "Customer Support"),
    WorkflowCategory("internal_administration", "Internal Administration"),
)

EVENTS: tuple[WorkflowEvent, ...] = (
    WorkflowEvent(
        "account.staff_password_reset",
        "Staff password reset",
        "account_security",
        "Password reset link for staff users.",
        AUDIENCE_STAFF,
    ),
    WorkflowEvent(
        "account.customer_password_reset",
        "Customer password reset",
        "account_security",
        "Password reset link for customer portal accounts.",
        AUDIENCE_CUSTOMER,
    ),
    WorkflowEvent(
        "account.staff_password_changed",
        "Staff password changed",
        "account_security",
        "Confirmation after a staff password change.",
        AUDIENCE_STAFF,
    ),
    WorkflowEvent(
        "account.customer_password_changed",
        "Customer password changed",
        "account_security",
        "Confirmation after a customer portal password change.",
        AUDIENCE_CUSTOMER,
    ),
    WorkflowEvent(
        "account.staff_failed_login_alert",
        "Staff failed-login alert",
        "account_security",
        "Alert after repeated failed staff logins.",
        AUDIENCE_STAFF,
    ),
    WorkflowEvent(
        "account.customer_failed_login_alert",
        "Customer failed-login alert",
        "account_security",
        "Alert after repeated failed customer portal logins.",
        AUDIENCE_CUSTOMER,
    ),
    WorkflowEvent(
        "account.staff_account_locked",
        "Staff account locked",
        "account_security",
        "Notice that a staff account was locked.",
        AUDIENCE_STAFF,
    ),
    WorkflowEvent(
        "account.customer_account_locked",
        "Customer account locked",
        "account_security",
        "Notice that a customer portal account was locked.",
        AUDIENCE_CUSTOMER,
    ),
    WorkflowEvent(
        "portal.customer_activation",
        "Customer portal activation",
        "customer_portal",
        "Activation link for a new customer portal account.",
        AUDIENCE_CUSTOMER,
    ),
    # Order notifications are sent by `OrderEmailNotifier` after each order
    # transition commits. They are the only events an Admin may disable.
    WorkflowEvent(
        "order.submitted",
        "Order submitted",
        "customer_orders",
        "Confirmation that a customer order was received.",
        AUDIENCE_CUSTOMER,
        allow_disable=True,
    ),
    WorkflowEvent(
        "order.approved",
        "Order approved",
        "customer_orders",
        "Confirmation that a customer order was approved.",
        AUDIENCE_CUSTOMER,
        allow_disable=True,
    ),
    WorkflowEvent(
        "order.rejected",
        "Order rejected",
        "customer_orders",
        "Notice that a customer order was rejected, with the reason.",
        AUDIENCE_CUSTOMER,
        allow_disable=True,
    ),
    WorkflowEvent(
        "order.cancelled",
        "Order cancelled",
        "customer_orders",
        "Notice that a customer order was cancelled.",
        AUDIENCE_CUSTOMER,
        allow_disable=True,
    ),
    WorkflowEvent(
        "order.fulfilled",
        "Order fulfilled",
        "customer_orders",
        "Notice that a customer order was fulfilled.",
        AUDIENCE_CUSTOMER,
        allow_disable=True,
    ),
    # Support queries: the customer never receives a receipt for raising a
    # query (the portal shows it immediately), so the create event is an
    # internal copy only. The answered event tells the customer to come back
    # and read the reply.
    WorkflowEvent(
        "support.query_received",
        "Support query received",
        "customer_support",
        "Internal copy when a customer raises a support query.",
        AUDIENCE_STAFF,
        allow_disable=True,
    ),
    WorkflowEvent(
        "support.query_answered",
        "Support query answered",
        "customer_support",
        "Notice that the dairy replied to a support query.",
        AUDIENCE_CUSTOMER,
        allow_disable=True,
    ),
    # Billing: a receipt for a payment recorded against a customer invoice.
    # Only sent when the customer has an active portal account.
    WorkflowEvent(
        "billing.payment_received",
        "Payment received",
        "billing_payments",
        "Receipt when a payment is recorded against a customer invoice.",
        AUDIENCE_CUSTOMER,
        allow_disable=True,
    ),
)

CATEGORY_BY_KEY: dict[str, WorkflowCategory] = {
    category.key: category for category in CATEGORIES
}
EVENT_BY_KEY: dict[str, WorkflowEvent] = {event.key: event for event in EVENTS}


def mapping_key(scope: str, key: str) -> str:
    """Scoped storage key for a mapping row."""
    return f"{scope}:{key}"


def get_category(category_key: str) -> WorkflowCategory | None:
    return CATEGORY_BY_KEY.get(category_key)


def get_event(event_key: str) -> WorkflowEvent | None:
    return EVENT_BY_KEY.get(event_key)


def category_of_event(event_key: str) -> str | None:
    event = EVENT_BY_KEY.get(event_key)
    return event.category_key if event is not None else None


def scope_label(scope: str, key: str) -> str | None:
    """Human label for one ``category:<key>`` / ``event:<key>`` target."""
    if scope == CATEGORY_SCOPE:
        category = CATEGORY_BY_KEY.get(key)
        return category.label if category is not None else None
    event = EVENT_BY_KEY.get(key)
    return event.name if event is not None else None


def serialize_workflow_catalogue() -> dict[str, Any]:
    """The catalogue exactly as ``GET /workflows`` returns it."""
    categories: list[dict[str, Any]] = []
    for category in CATEGORIES:
        events = [
            {
                "key": event.key,
                "name": event.name,
                "description": event.description,
                "audience": event.audience,
                "implemented": event.implemented,
                "allow_disable": event.allow_disable,
                # A code-level default does not exist yet; the effective sender
                # always comes from the mapping rows.
                "default_sender_identity_id": None,
            }
            for event in EVENTS
            if event.category_key == category.key
        ]
        categories.append(
            {"key": category.key, "label": category.label, "events": events}
        )
    return {"categories": categories}
