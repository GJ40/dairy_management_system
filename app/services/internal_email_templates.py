"""Staff-facing summaries for internal notification recipients.

Internal observers are additional observers only: they never receive the
customer's own message. Nothing here renders a reset link, a token, a password
or bill details, so an internal copy can never be used to take over an account.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.email_service import (
    _callout,
    _details_table,
    _escape,
    _layout,
    _paragraph,
    _section_label,
)
from app.services.email_workflow_catalogue import get_event
from app.utils.time import business_timezone

ORDER_SUBMITTED = "order.submitted"
SUPPORT_QUERY_RECEIVED = "support.query_received"

STAFF_FAILED_LOGIN_ALERT = "account.staff_failed_login_alert"
CUSTOMER_FAILED_LOGIN_ALERT = "account.customer_failed_login_alert"
STAFF_ACCOUNT_LOCKED = "account.staff_account_locked"
CUSTOMER_ACCOUNT_LOCKED = "account.customer_account_locked"

INTERNAL_EVENT_KEYS = (
    STAFF_FAILED_LOGIN_ALERT,
    CUSTOMER_FAILED_LOGIN_ALERT,
    STAFF_ACCOUNT_LOCKED,
    CUSTOMER_ACCOUNT_LOCKED,
    ORDER_SUBMITTED,
    SUPPORT_QUERY_RECEIVED,
)

SECURITY_EVENT_KEYS = (
    STAFF_FAILED_LOGIN_ALERT,
    CUSTOMER_FAILED_LOGIN_ALERT,
    STAFF_ACCOUNT_LOCKED,
    CUSTOMER_ACCOUNT_LOCKED,
)


@dataclass(frozen=True)
class InternalEmailContext:
    """Plain values captured before the background task is queued."""

    event_key: str
    label: str
    occurred_at: datetime | None = None
    account_email: str | None = None
    account_name: str | None = None
    failure_count: int | None = None
    window_minutes: int | None = None
    order_no: str | None = None
    customer_name: str | None = None
    requested_date: date | None = None
    quantity_litres: Decimal | None = None
    note: str | None = None
    query_no: str | None = None
    query_subject: str | None = None
    query_category: str | None = None

    @classmethod
    def from_payload(
        cls,
        event_key: str,
        payload: dict[str, Any] | None,
    ) -> InternalEmailContext | None:
        """Rebuild the context from the queued payload.

        Returns ``None`` when the payload lacks the facts the message needs, so
        a partial dispatch sends nothing instead of a misleading summary.
        """
        data = dict(payload or {})
        event = get_event(event_key)
        if event is None:
            return None
        context = cls(
            event_key=event_key,
            label=event.name,
            occurred_at=_parse_datetime(data.get("occurred_at")),
            account_email=_text(data.get("account_email")),
            account_name=_text(data.get("account_name")),
            failure_count=_int(data.get("failure_count")),
            window_minutes=_int(data.get("window_minutes")),
            order_no=_text(data.get("order_no")),
            customer_name=_text(data.get("customer_name")),
            requested_date=_parse_date(data.get("requested_date")),
            quantity_litres=_decimal(data.get("quantity_litres")),
            note=_text(data.get("note")),
            query_no=_text(data.get("query_no")),
            query_subject=_text(data.get("query_subject")),
            query_category=_text(data.get("query_category")),
        )
        if event_key == ORDER_SUBMITTED:
            return context if context.order_no else None
        if event_key == SUPPORT_QUERY_RECEIVED:
            # A support copy without the query number would be untraceable, so
            # a partial payload sends nothing instead of a vague summary.
            return context if context.query_no else None
        return context if context.account_email else None


@dataclass(frozen=True)
class InternalEmailContent:
    subject: str
    html: str
    text: str


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _litres(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f} L"


def _date_text(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value is not None else "-"


def _moment_text(value: datetime | None) -> str:
    if value is None:
        return "-"
    # The dispatchers queue naive UTC, so a naive value is UTC, not local.
    moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return moment.astimezone(business_timezone()).strftime("%d %b %Y %H:%M %Z")


def _subject(context: InternalEmailContext) -> str:
    suffix = context.query_no or context.order_no or context.account_email
    if suffix:
        return f"[Internal] {context.label} · {suffix}"
    return f"[Internal] {context.label}"


def _rows(context: InternalEmailContext) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("Workflow", _escape(context.label)),
        ("Detected", _escape(_moment_text(context.occurred_at))),
    ]
    if context.account_email:
        rows.append(("Account", _escape(context.account_email)))
    if context.account_name:
        rows.append(("Name", _escape(context.account_name)))
    if context.failure_count is not None:
        rows.append(("Failed attempts", str(context.failure_count)))
    if context.window_minutes is not None:
        rows.append(("Window", f"{context.window_minutes} minutes"))
    if context.order_no:
        rows.append(("Order", _escape(context.order_no)))
    if context.customer_name:
        rows.append(("Customer", _escape(context.customer_name)))
    if context.requested_date is not None:
        rows.append(("Delivery date", _escape(_date_text(context.requested_date))))
    if context.quantity_litres is not None:
        rows.append(("Quantity", _escape(_litres(context.quantity_litres))))
    if context.note:
        rows.append(("Customer note", _escape(context.note)))
    if context.query_no:
        rows.append(("Query", _escape(context.query_no)))
    if context.query_subject:
        rows.append(("Subject", _escape(context.query_subject)))
    if context.query_category:
        rows.append(
            (
                "Category",
                _escape(context.query_category.replace("_", " ").capitalize()),
            )
        )
    return rows


def _intro(context: InternalEmailContext) -> str:
    if context.event_key in SECURITY_EVENT_KEYS:
        account = context.account_email or "an account"
        return (
            f"Security monitoring recorded activity for {account}. This copy "
            "exists so the dairy can react even when the account owner does "
            "not."
        )
    if context.event_key == SUPPORT_QUERY_RECEIVED:
        return (
            "A customer raised a new support query in the portal. This copy "
            "exists so the dairy can assign and answer it without waiting for "
            "the customer to call."
        )
    return (
        "A customer placed a new order in the portal. This copy exists so the "
        "dairy can plan stock and delivery without waiting for the customer to "
        "call."
    )


def _text_body(context: InternalEmailContext) -> str:
    lines = [
        f"INTERNAL NOTIFICATION - {context.label.upper()}",
        "",
        _intro(context),
        "",
    ]
    for label, value in _rows(context):
        lines.append(f"  {label}: {_unbold(_unescape(value))}")
    lines.extend(
        [
            "",
            "Internal only: this summary contains no sign-in links, passwords",
            "or bill details. Change these recipients in Admin > Email &",
            "Notifications > Internal recipients.",
            "",
        ]
    )
    return "\n".join(lines)


def _unescape(value: str) -> str:
    # Rows carry pre-escaped HTML; the text body must stay plain.
    return (
        value.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&amp;", "&")
    )


def _unbold(value: str) -> str:
    return value.replace("<strong>", "").replace("</strong>", "")


def build_internal_email(context: InternalEmailContext) -> InternalEmailContent:
    """Render one internal summary for a workflow event."""
    body = (
        _paragraph(_escape(_intro(context)))
        + _section_label("Details")
        + _details_table(_rows(context))
        + _callout(
            "Internal only",
            "This summary contains no sign-in links, passwords or bill details. "
            "The affected person received their own message.",
            tone="info",
        )
    )
    return InternalEmailContent(
        subject=_subject(context),
        html=_layout(
            heading=f"Internal notification · {context.label}",
            body_html=body,
            preheader=_intro(context),
            status_label="Internal",
            tone="info",
            footer_note=(
                "You receive this because this address is configured as an "
                "internal recipient for this workflow."
            ),
            footer_disclaimer="Internal notification",
        ),
        text=_text_body(context),
    )
