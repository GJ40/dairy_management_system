"""Customer receipt for a payment recorded against an invoice.

The receipt reuses the layout primitives in :mod:`app.services.email_service`
so it looks like the rest of the transactional mail (same shell, palette and
detail tables). It carries amounts only - no invoice PDF, because the SMTP
layer has no attachment support - and points at the portal for the document.
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

PAYMENT_RECEIVED = "billing.payment_received"

BRAND = "AmritDhara Dairy"

_STATUS_TEXT = {
    "paid": "Paid in full",
    "partial": "Partly paid",
    "unpaid": "Unpaid",
}


@dataclass(frozen=True)
class PaymentReceiptContext:
    """Everything a receipt needs, loaded once per send."""

    invoice_no: str
    customer_name: str
    payment_amount: Decimal
    paid_amount: Decimal
    total_amount: Decimal
    balance: Decimal
    status: str
    period_start: date | None = None
    period_end: date | None = None


@dataclass(frozen=True)
class PaymentReceiptContent:
    subject: str
    html: str
    text: str


def _money(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"Rs. {Decimal(value):,.2f}"


def _date_text(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value is not None else "-"


def _period_text(context: PaymentReceiptContext) -> str:
    if context.period_start is None and context.period_end is None:
        return "-"
    if context.period_start == context.period_end:
        return _date_text(context.period_start)
    return f"{_date_text(context.period_start)} - {_date_text(context.period_end)}"


def _status_text(context: PaymentReceiptContext) -> str:
    return _STATUS_TEXT.get(context.status, context.status.capitalize() or "-")


def build_payment_receipt(context: PaymentReceiptContext) -> PaymentReceiptContent:
    """Render the receipt for one recorded payment."""
    settled = context.balance <= Decimal("0")
    rows = [
        ("Invoice", f"<strong>{_escape(context.invoice_no)}</strong>"),
        ("Billing period", _escape(_period_text(context))),
        ("Amount received", f"<strong>{_escape(_money(context.payment_amount))}</strong>"),
        ("Total paid", _escape(_money(context.paid_amount))),
        ("Invoice total", _escape(_money(context.total_amount))),
        ("Balance due", _escape(_money(context.balance))),
        ("Status", _escape(_status_text(context))),
    ]

    body = (
        _paragraph(f"Hello {_escape(context.customer_name or 'there')},")
        + _paragraph(
            "We have recorded your payment of "
            f"<strong>{_escape(_money(context.payment_amount))}</strong> against "
            "invoice "
            f"<strong>{_escape(context.invoice_no)}</strong>. Thank you."
        )
        + _section_label("Payment summary")
        + _details_table(rows)
        + _steps(
            [
                "Open the customer portal to see the invoice and its payment "
                "history.",
                (
                    "Nothing further is needed - this invoice is settled."
                    if settled
                    else "The remaining balance is shown above and is payable "
                    "as usual."
                ),
                "Raise a support query from the portal if a figure looks wrong.",
            ]
        )
        + _callout(
            "This is a receipt, not an invoice",
            "The invoice itself stays in the customer portal; this email only "
            "confirms the payment we recorded.",
            tone="success" if settled else "info",
        )
    )

    text = (
        f"Hello {context.customer_name or 'there'},\n\n"
        "PAYMENT RECEIVED\n\n"
        f"We have recorded your payment of {_money(context.payment_amount)} "
        f"against invoice {context.invoice_no}. Thank you.\n\n"
        "Payment summary\n"
        f"  Invoice:         {context.invoice_no}\n"
        f"  Billing period:  {_period_text(context)}\n"
        f"  Amount received: {_money(context.payment_amount)}\n"
        f"  Total paid:      {_money(context.paid_amount)}\n"
        f"  Invoice total:   {_money(context.total_amount)}\n"
        f"  Balance due:     {_money(context.balance)}\n"
        f"  Status:          {_status_text(context)}\n\n"
        + (
            "This invoice is settled - nothing further is needed.\n\n"
            if settled
            else "The remaining balance above is payable as usual.\n\n"
        )
        + "The invoice stays in the customer portal; this email only confirms "
        "the payment we recorded.\n"
    )

    return PaymentReceiptContent(
        subject=f"Payment received · {context.invoice_no} — {BRAND}",
        html=_layout(
            heading="Payment received",
            body_html=body,
            preheader=(
                f"{_money(context.payment_amount)} recorded against invoice "
                f"{context.invoice_no}."
            ),
            status_label=_status_text(context),
            tone="success" if settled else "info",
            footer_note=(
                "You are receiving this because a payment was recorded against "
                "your invoice."
            ),
        ),
        text=text,
    )
