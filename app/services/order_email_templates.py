"""Customer order notification templates.

The five order emails reuse the layout primitives in
:mod:`app.services.email_service` so they look like the existing transactional
mail (same shell, palette and detail tables). Each builder returns the subject,
HTML body and plain-text body for one event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.email_service import (
    _callout,
    _details_table,
    _escape,
    _layout,
    _paragraph,
    _section_label,
    _steps,
)

ORDER_SUBMITTED = "order.submitted"
ORDER_APPROVED = "order.approved"
ORDER_REJECTED = "order.rejected"
ORDER_CANCELLED = "order.cancelled"
ORDER_FULFILLED = "order.fulfilled"

ORDER_EVENT_KEYS = (
    ORDER_SUBMITTED,
    ORDER_APPROVED,
    ORDER_REJECTED,
    ORDER_CANCELLED,
    ORDER_FULFILLED,
)

# Short, customer-facing subject lines. The order number is appended so a
# customer with several open orders can tell the emails apart in a list.
_SUBJECTS = {
    ORDER_SUBMITTED: "Order received",
    ORDER_APPROVED: "Order approved",
    ORDER_REJECTED: "Order could not be approved",
    ORDER_CANCELLED: "Order cancelled",
    ORDER_FULFILLED: "Order delivered",
}

BRAND = "AmritDhara Dairy"


@dataclass(frozen=True)
class OrderEmailContext:
    """Everything a notification needs, loaded once per send."""

    order_no: str
    customer_name: str
    recipient_email: str
    requested_date: date
    quantity_litres: Decimal
    rate: Decimal
    estimated_total: Decimal
    note: str | None = None
    reason: str | None = None
    previous_status: str | None = None
    invoice_no: str | None = None
    balance: Decimal | None = None


@dataclass(frozen=True)
class OrderEmailContent:
    subject: str
    html: str
    text: str


def _money(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"Rs. {Decimal(value):,.2f}"


def _litres(value: Decimal) -> str:
    return f"{Decimal(value):,.2f} L"


def _date_text(value: date) -> str:
    return value.strftime("%d %b %Y")


def _status_text(value: str | None) -> str:
    if not value:
        return "-"
    return value.replace("_", " ").strip().capitalize()


def build_order_email(
    event_key: str,
    context: OrderEmailContext,
) -> OrderEmailContent:
    """Render one order notification; unknown keys raise ``KeyError``."""
    builders = {
        ORDER_SUBMITTED: _submitted,
        ORDER_APPROVED: _approved,
        ORDER_REJECTED: _rejected,
        ORDER_CANCELLED: _cancelled,
        ORDER_FULFILLED: _fulfilled,
    }
    try:
        build = builders[event_key]
    except KeyError as exc:  # pragma: no cover - guarded by the catalogue
        raise KeyError(f"No order email template for {event_key!r}") from exc
    return build(context)


def _subject(event_key: str, context: OrderEmailContext) -> str:
    return f"{_SUBJECTS[event_key]} · {context.order_no} — {BRAND}"


def _greeting(context: OrderEmailContext) -> str:
    return _paragraph(
        f"Hello {_escape(context.customer_name or 'there')},"
    )


def _money_row(label: str, value: Decimal | None) -> tuple[str, str]:
    return (label, f"<strong>{_escape(_money(value))}</strong>")


def _submitted(context: OrderEmailContext) -> OrderEmailContent:
    rows = [
        ("Order number", f"<strong>{_escape(context.order_no)}</strong>"),
        ("Delivery date", _escape(_date_text(context.requested_date))),
        ("Quantity", _escape(_litres(context.quantity_litres))),
        ("Your rate", _escape(f"{_money(context.rate)} per litre")),
        _money_row("Estimated total", context.estimated_total),
    ]
    if context.note:
        rows.append(("Your note", _escape(context.note)))

    body = (
        _greeting(context)
        + _paragraph(
            "Thank you - we have received your milk order and it is waiting "
            "for the dairy to review it."
        )
        + _section_label("Order summary")
        + _details_table(rows)
        + _steps(
            [
                "We check available stock for your delivery date.",
                "You get another email as soon as the order is approved or "
                "rejected.",
                "While it is still submitted you can cancel it from the "
                "customer portal.",
            ]
        )
        + _callout(
            "This is an estimate",
            "The final amount is confirmed after delivery and appears on your "
            "next bill; the rate can change with the dairy's monthly rate.",
            tone="info",
        )
    )

    text = (
        f"Hello {context.customer_name or 'there'},\n\n"
        "ORDER RECEIVED\n\n"
        "Thank you - we have received your milk order and it is waiting for "
        "the dairy to review it.\n\n"
        "Order summary\n"
        f"  Order number:     {context.order_no}\n"
        f"  Delivery date:    {_date_text(context.requested_date)}\n"
        f"  Quantity:         {_litres(context.quantity_litres)}\n"
        f"  Your rate:        {_money(context.rate)} per litre\n"
        f"  Estimated total:  {_money(context.estimated_total)}\n"
        + (f"  Your note:        {context.note}\n" if context.note else "")
        + "\nWhat happens next\n"
        "  1. We check available stock for your delivery date.\n"
        "  2. You get another email once it is approved or rejected.\n"
        "  3. You can still cancel it from the customer portal.\n\n"
        "This is an estimate: the final amount is confirmed after delivery "
        "and appears on your next bill.\n"
    )

    return OrderEmailContent(
        subject=_subject(ORDER_SUBMITTED, context),
        html=_layout(
            heading="We received your order",
            body_html=body,
            preheader=(
                f"Order {context.order_no} for {_date_text(context.requested_date)} "
                "is waiting for review."
            ),
            status_label="Awaiting review",
            tone="info",
            footer_note=(
                "You are receiving this because you placed an order in the "
                "customer portal."
            ),
        ),
        text=text,
    )


def _approved(context: OrderEmailContext) -> OrderEmailContent:
    rows = [
        ("Order number", f"<strong>{_escape(context.order_no)}</strong>"),
        ("Delivery date", _escape(_date_text(context.requested_date))),
        ("Reserved quantity", _escape(_litres(context.quantity_litres))),
        ("Your rate", _escape(f"{_money(context.rate)} per litre")),
        _money_row("Estimated total", context.estimated_total),
    ]
    body = (
        _greeting(context)
        + _paragraph(
            "Your milk order has been <strong>approved</strong>. The quantity "
            "below is reserved for your delivery date."
        )
        + _section_label("Approved order")
        + _details_table(rows)
        + _steps(
            [
                f"Your milk is reserved for {_date_text(context.requested_date)}.",
                "Delivery timing follows your usual route; contact the dairy if "
                "you need a different slot.",
                "The bill is raised after delivery and appears in the customer "
                "portal.",
            ]
        )
        + _callout(
            "Estimates, not a bill",
            "The amount above is based on your current rate. The invoice is "
            "issued after delivery.",
            tone="success",
        )
    )
    text = (
        f"Hello {context.customer_name or 'there'},\n\n"
        "ORDER APPROVED\n\n"
        f"Your milk order has been approved. {_litres(context.quantity_litres)} "
        f"is reserved for {_date_text(context.requested_date)}.\n\n"
        "Approved order\n"
        f"  Order number:      {context.order_no}\n"
        f"  Delivery date:     {_date_text(context.requested_date)}\n"
        f"  Reserved quantity: {_litres(context.quantity_litres)}\n"
        f"  Your rate:         {_money(context.rate)} per litre\n"
        f"  Estimated total:   {_money(context.estimated_total)}\n\n"
        "The final amount is confirmed after delivery and appears on your next "
        "bill.\n"
    )
    return OrderEmailContent(
        subject=_subject(ORDER_APPROVED, context),
        html=_layout(
            heading="Your order is approved",
            body_html=body,
            preheader=(
                f"{_litres(context.quantity_litres)} reserved for "
                f"{_date_text(context.requested_date)}."
            ),
            status_label="Approved",
            tone="success",
            footer_note=(
                "Contact the dairy if anything about this order looks wrong."
            ),
        ),
        text=text,
    )


def _rejected(context: OrderEmailContext) -> OrderEmailContent:
    reason_row = [
        ("Order number", f"<strong>{_escape(context.order_no)}</strong>"),
        ("Requested date", _escape(_date_text(context.requested_date))),
        ("Quantity", _escape(_litres(context.quantity_litres))),
    ]
    body = (
        _greeting(context)
        + _paragraph(
            "We are sorry - the dairy could not approve your order as it was "
            "placed. No milk is reserved for this order."
        )
        + _section_label("Order")
        + _details_table(reason_row)
        + _callout("Reason given", _escape(context.reason or "Not provided"))
        + _section_label("What you can do")
        + _steps(
            [
                "Place a new order for another date or a smaller quantity.",
                "Contact the dairy if you think this was a mistake or want to "
                "ask about availability.",
            ]
        )
    )
    text = (
        f"Hello {context.customer_name or 'there'},\n\n"
        "ORDER NOT APPROVED\n\n"
        "We are sorry - the dairy could not approve your order as it was "
        "placed. No milk is reserved for this order.\n\n"
        f"  Order number:   {context.order_no}\n"
        f"  Requested date: {_date_text(context.requested_date)}\n"
        f"  Quantity:       {_litres(context.quantity_litres)}\n"
        f"  Reason:         {context.reason or 'Not provided'}\n\n"
        "What you can do\n"
        "  1. Place a new order for another date or a smaller quantity.\n"
        "  2. Contact the dairy if you think this was a mistake.\n"
    )
    return OrderEmailContent(
        subject=_subject(ORDER_REJECTED, context),
        html=_layout(
            heading="Your order could not be approved",
            body_html=body,
            preheader=f"Order {context.order_no} was not approved.",
            status_label="Not approved",
            tone="danger",
            footer_note=(
                "Reply to the dairy's usual contact details if you need help "
                "with this order."
            ),
        ),
        text=text,
    )


def _cancelled(context: OrderEmailContext) -> OrderEmailContent:
    body = (
        _greeting(context)
        + _paragraph(
            "This order has been cancelled, so no milk will be delivered for "
            "it. Nothing further is needed from you."
        )
        + _section_label("Cancelled order")
        + _details_table(
            [
                ("Order number", f"<strong>{_escape(context.order_no)}</strong>"),
                ("Requested date", _escape(_date_text(context.requested_date))),
                ("Quantity", _escape(_litres(context.quantity_litres))),
                ("Previous status", _escape(_status_text(context.previous_status))),
            ]
        )
        + _callout("Reason", _escape(context.reason or "Not provided"))
        + _steps(
            [
                "Place a new order from the customer portal if you still need "
                "milk for that date.",
                "Any invoice already issued for this order stays unchanged.",
            ]
        )
    )
    text = (
        f"Hello {context.customer_name or 'there'},\n\n"
        "ORDER CANCELLED\n\n"
        "This order has been cancelled, so no milk will be delivered for it.\n\n"
        f"  Order number:    {context.order_no}\n"
        f"  Requested date:  {_date_text(context.requested_date)}\n"
        f"  Quantity:        {_litres(context.quantity_litres)}\n"
        f"  Previous status: {_status_text(context.previous_status)}\n"
        f"  Reason:          {context.reason or 'Not provided'}\n\n"
        "Place a new order from the customer portal if you still need milk for "
        "that date.\n"
    )
    return OrderEmailContent(
        subject=_subject(ORDER_CANCELLED, context),
        html=_layout(
            heading="Your order was cancelled",
            body_html=body,
            preheader=f"Order {context.order_no} has been cancelled.",
            status_label="Cancelled",
            tone="warning",
            footer_note="You will not receive further emails about this order.",
        ),
        text=text,
    )


def _fulfilled(context: OrderEmailContext) -> OrderEmailContent:
    rows = [
        ("Order number", f"<strong>{_escape(context.order_no)}</strong>"),
        ("Delivered on", _escape(_date_text(context.requested_date))),
        ("Quantity", _escape(_litres(context.quantity_litres))),
        ("Rate", _escape(f"{_money(context.rate)} per litre")),
        _money_row("Amount", context.estimated_total),
    ]
    if context.invoice_no:
        rows.append(("Invoice", f"<strong>{_escape(context.invoice_no)}</strong>"))
    if context.balance is not None:
        rows.append(("Balance due", _escape(_money(context.balance))))

    body = (
        _greeting(context)
        + _paragraph(
            "Your order has been <strong>delivered</strong> and billed. Thank "
            "you for ordering with us."
        )
        + _section_label("Delivery summary")
        + _details_table(rows)
        + _steps(
            [
                "Open the customer portal to view the bill for this delivery.",
                "Settle the balance by your usual payment method.",
                "Raise a support query from the portal if any detail looks "
                "wrong.",
            ]
        )
    )
    text = (
        f"Hello {context.customer_name or 'there'},\n\n"
        "ORDER DELIVERED\n\n"
        "Your order has been delivered and billed. Thank you for ordering with "
        "us.\n\n"
        "Delivery summary\n"
        f"  Order number: {context.order_no}\n"
        f"  Delivered on: {_date_text(context.requested_date)}\n"
        f"  Quantity:     {_litres(context.quantity_litres)}\n"
        f"  Rate:         {_money(context.rate)} per litre\n"
        f"  Amount:       {_money(context.estimated_total)}\n"
        + (f"  Invoice:      {context.invoice_no}\n" if context.invoice_no else "")
        + (
            f"  Balance due:  {_money(context.balance)}\n"
            if context.balance is not None
            else ""
        )
        + "\nView the bill in the customer portal and settle it by your usual "
        "payment method.\n"
    )
    return OrderEmailContent(
        subject=_subject(ORDER_FULFILLED, context),
        html=_layout(
            heading="Your order has been delivered",
            body_html=body,
            preheader=(
                f"Order {context.order_no} was delivered on "
                f"{_date_text(context.requested_date)}."
            ),
            status_label="Delivered",
            tone="success",
            footer_note=(
                "The bill for this delivery is available in the customer portal."
            ),
        ),
        text=text,
    )
