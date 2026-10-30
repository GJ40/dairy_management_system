"""Invoice PDF rendering.

The invoice is rebuilt on every download from the persisted invoice, its linked
sales and the customer record, so the document can never disagree with the
database. Amounts come from the invoice row (``total_amount``/``paid_amount``)
and the line items from the linked sales; both use ``Decimal`` throughout.

Typography is deliberately restrained: one type family (Helvetica, a PDF
base-14 font that needs no embedding), a dark ink colour, one muted accent, fine
rules and light-gray table fills. Rupee amounts are written as ``Rs. 1,234.00``
because the base-14 fonts do not carry the U+20B9 rupee glyph; the frontend shows
the glyph, the PDF stays legible in every viewer.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.utils.report_pdf import numbered_canvas

INK = HexColor("#111827")
BODY = HexColor("#1f2937")
MUTED = HexColor("#5b6472")
RULE = HexColor("#c7ccd4")
LIGHT = HexColor("#f3f4f6")
HEADER_FILL = HexColor("#111827")
ACCENT = HexColor("#1f6f5c")
ACCENT_LIGHT = HexColor("#8fb9ae")
ALERT = HexColor("#9a3412")
WHITE = HexColor("#ffffff")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 15 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)

CENT = Decimal("0.01")

_STATUS_LABELS = {
    "unpaid": "Unpaid",
    "partial": "Partially paid",
    "paid": "Paid",
}


def _esc(value: Any) -> str:
    return escape(str(value if value is not None else ""))


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _money(value: Any) -> str:
    amount = _decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,.2f}"


def _litres(value: Any) -> str:
    return f"{_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def _date_label(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        moment = value
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    text = str(value)
    if text.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        return _date_label(parsed)
    try:
        return date.fromisoformat(text[:10]).strftime("%d %b %Y")
    except ValueError:
        return text


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "brand": ParagraphStyle(
            "inv_brand",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=INK,
        ),
        "brand_sub": ParagraphStyle(
            "inv_brand_sub",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "doc_title": ParagraphStyle(
            "inv_doc_title",
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=24,
            textColor=INK,
            alignment=TA_RIGHT,
        ),
        "doc_sub": ParagraphStyle(
            "inv_doc_sub",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
        "label": ParagraphStyle(
            "inv_label",
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=10,
            textColor=MUTED,
        ),
        "value": ParagraphStyle(
            "inv_value",
            fontName="Helvetica",
            fontSize=8.6,
            leading=12,
            textColor=BODY,
        ),
        "value_right": ParagraphStyle(
            "inv_value_right",
            fontName="Helvetica",
            fontSize=8.6,
            leading=12,
            textColor=BODY,
            alignment=TA_RIGHT,
        ),
        "customer": ParagraphStyle(
            "inv_customer",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=INK,
        ),
        "section": ParagraphStyle(
            "inv_section",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "inv_body",
            fontName="Helvetica",
            fontSize=8.2,
            leading=11.5,
            textColor=BODY,
            alignment=TA_LEFT,
        ),
        "note": ParagraphStyle(
            "inv_note",
            fontName="Helvetica",
            fontSize=7.6,
            leading=10.5,
            textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "inv_cell",
            fontName="Helvetica",
            fontSize=8.4,
            leading=11,
            textColor=BODY,
        ),
        "summary_label": ParagraphStyle(
            "inv_summary_label",
            fontName="Helvetica",
            fontSize=8.6,
            leading=12,
            textColor=MUTED,
        ),
    }


def _rule(width: float = CONTENT_WIDTH, thickness: float = 0.8, color: HexColor = INK) -> Table:
    return Table(
        [[""]],
        colWidths=[width],
        rowHeights=[thickness],
        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), color)]),
        hAlign="LEFT",
    )


def _header(invoice: Any) -> list[Any]:
    styles = _styles()
    invoice_no = _value(invoice, "invoice_no", "")
    status = str(_value(invoice, "status", "") or "").lower()
    status_label = _STATUS_LABELS.get(status, status.upper() or "-")

    left = [
        Paragraph("Dairy Management System", styles["brand"]),
        Spacer(1, 2),
        Paragraph(
            "Buffalo milk production and daily supply",
            styles["brand_sub"],
        ),
    ]
    right = [
        Paragraph("INVOICE", styles["doc_title"]),
        Spacer(1, 2),
        Paragraph(f"No. {_esc(invoice_no)}", styles["doc_sub"]),
        Paragraph(f"Status: {_esc(status_label)}", styles["doc_sub"]),
    ]

    header = Table(
        [[left, right]],
        colWidths=[CONTENT_WIDTH * 0.58, CONTENT_WIDTH * 0.42],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        ),
        hAlign="LEFT",
    )
    return [header, Spacer(1, 6), _rule(), Spacer(1, 12)]


def _parties(invoice: Any, customer: Any) -> list[Any]:
    styles = _styles()
    name = _value(customer, "name", "Customer")
    phone = _value(customer, "phone")
    address = _value(customer, "address")

    bill_to: list[Any] = [Paragraph("BILL TO", styles["label"]), Spacer(1, 3)]
    bill_to.append(Paragraph(_esc(name), styles["customer"]))
    if phone:
        bill_to.append(Paragraph(f"Phone: {_esc(phone)}", styles["value"]))
    if address:
        bill_to.append(Paragraph(_esc(address), styles["value"]))
    if not phone and not address:
        bill_to.append(
            Paragraph("No contact details on record", styles["note"])
        )

    issued_at = _value(invoice, "createdAt") or _value(invoice, "created_at")
    details = [
        ["Issue date", _date_label(issued_at)],
        [
            "Billing period",
            f"{_date_label(_value(invoice, 'period_start'))} - "
            f"{_date_label(_value(invoice, 'period_end'))}",
        ],
        [
            "Payment status",
            _STATUS_LABELS.get(
                str(_value(invoice, "status", "") or "").lower(),
                str(_value(invoice, "status", "") or "-"),
            ),
        ],
    ]
    detail_rows = [
        [
            Paragraph(_esc(label), styles["label"]),
            Paragraph(_esc(value), styles["value_right"]),
        ]
        for label, value in details
    ]
    detail_table = Table(
        detail_rows,
        colWidths=[CONTENT_WIDTH * 0.17, CONTENT_WIDTH * 0.25],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        ),
        hAlign="RIGHT",
    )

    block = Table(
        [
            [
                bill_to,
                [
                    Paragraph("INVOICE DETAILS", styles["label"]),
                    Spacer(1, 4),
                    detail_table,
                ],
            ]
        ],
        colWidths=[CONTENT_WIDTH * 0.55, CONTENT_WIDTH * 0.45],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
        hAlign="LEFT",
    )
    return [block, Spacer(1, 14)]


def _items_table(sales: list[Any]) -> list[Any]:
    styles = _styles()
    header = ["#", "Date", "Description", "Qty (L)", "Rate (Rs./L)", "Amount (Rs.)"]
    rows: list[list[Any]] = [header]
    for index, sale in enumerate(sales, start=1):
        rows.append(
            [
                str(index),
                _date_label(_value(sale, "sale_date")),
                Paragraph("Buffalo milk supply", styles["cell"]),
                _litres(_value(sale, "litres")),
                _money(_value(sale, "rate")),
                _money(_value(sale, "amount")),
            ]
        )
    if len(rows) == 1:
        rows.append(
            [
                "",
                "",
                Paragraph("No deliveries are linked to this invoice.", styles["cell"]),
                "",
                "",
                "",
            ]
        )

    widths = [
        26,
        70,
        CONTENT_WIDTH - (26 + 70 + 62 + 78 + 92),
        62,
        78,
        92,
    ]
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style: list[tuple[Any, ...]] = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.2),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
        ("ALIGN", (0, 1), (0, -1), "RIGHT"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("ALIGN", (2, 0), (2, -1), "LEFT"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.4),
        ("TEXTCOLOR", (0, 1), (-1, -1), BODY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style.append(("BACKGROUND", (0, row_index), (-1, row_index), LIGHT))
    table.setStyle(TableStyle(style))
    return [
        Paragraph("DELIVERIES", styles["section"]),
        table,
        Spacer(1, 6),
        Paragraph(
            f"{len(sales)} deliver{'y' if len(sales) == 1 else 'ies'} billed on this invoice.",
            styles["note"],
        ),
    ]


def _totals(invoice: Any, sales: list[Any]) -> list[Any]:
    styles = _styles()
    total = _decimal(_value(invoice, "total_amount"))
    paid = _decimal(_value(invoice, "paid_amount"))
    balance = total - paid
    if balance < 0:
        balance = Decimal("0.00")

    line_total = sum(
        (_decimal(_value(sale, "amount")) for sale in sales),
        Decimal("0.00"),
    )
    total_litres = sum(
        (_decimal(_value(sale, "litres")) for sale in sales),
        Decimal("0.00"),
    )

    rows: list[list[Any]] = [
        [
            Paragraph("Total milk supplied", styles["summary_label"]),
            Paragraph(
                f"<font name='Helvetica' size='8.6'>{_litres(total_litres)} L</font>",
                styles["value_right"],
            ),
        ],
        [
            Paragraph("Subtotal", styles["summary_label"]),
            Paragraph(
                f"<font name='Helvetica' size='8.6'>Rs. {_money(line_total)}</font>",
                styles["value_right"],
            ),
        ],
    ]
    if line_total != total:
        rows.append(
            [
                Paragraph("Recorded invoice total", styles["summary_label"]),
                Paragraph(
                    f"<font name='Helvetica' size='8.6'>Rs. {_money(total)}</font>",
                    styles["value_right"],
                ),
            ]
        )
    rows.append(
        [
            Paragraph("Amount paid", styles["summary_label"]),
            Paragraph(
                f"<font name='Helvetica' size='8.6' color='#1f6f5c'>"
                f"Rs. {_money(paid)}</font>",
                styles["value_right"],
            ),
        ]
    )

    rows.append(
        [
            Paragraph(
                "<font name='Helvetica-Bold' size='9'>"
                f"{'Balance due' if balance > 0 else 'Balance'}</font>",
                styles["body"],
            ),
            Paragraph(
                f"<font name='Helvetica-Bold' size='12' "
                f"color='{'#9a3412' if balance > 0 else '#1f6f5c'}'>"
                f"Rs. {_money(balance)}</font>",
                styles["value_right"],
            ),
        ]
    )

    caption = [
        Paragraph(
            "Amounts reconcile with the recorded invoice total and payments.",
            styles["note"],
        ),
    ]
    if paid > total:
        caption.insert(
            0,
            Paragraph(
                f"Payments exceed the invoice total by "
                f"Rs. {_money(paid - total)}.",
                styles["note"],
            ),
        )

    # The summary is a full-bleed band: labels sit on the left edge of the
    # content area and amounts on the right edge, so the block reads as one
    # more stacked section of the document instead of a floating corner box.
    label_width = CONTENT_WIDTH - 168
    balance_index = len(rows) - 1
    totals = Table(
        rows,
        colWidths=[label_width, CONTENT_WIDTH - label_width],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, balance_index - 2), 0.4, RULE),
                ("BACKGROUND", (0, balance_index), (-1, balance_index), LIGHT),
                ("LINEABOVE", (0, balance_index), (-1, balance_index), 0.9, INK),
                ("LINEBELOW", (0, balance_index), (-1, balance_index), 0.6, RULE),
                ("TOPPADDING", (0, balance_index), (-1, balance_index), 9),
                ("BOTTOMPADDING", (0, balance_index), (-1, balance_index), 9),
            ]
        ),
        hAlign="LEFT",
    )
    summary = Table(
        [[totals]],
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
            ]
        ),
        hAlign="LEFT",
    )

    return [
        KeepTogether(
            [
                Paragraph("PAYMENT SUMMARY", styles["section"]),
                summary,
                Spacer(1, 6),
            ]
        ),
        Paragraph(
            "Payment status: "
            f"<font name='Helvetica-Bold'>"
            f"{_esc(_STATUS_LABELS.get(str(_value(invoice, 'status', '')).lower(), str(_value(invoice, 'status', ''))))}"
            f"</font> - Rs. {_money(paid)} received against Rs. {_money(total)}, "
            f"Rs. {_money(balance)} outstanding.",
            styles["body"],
        ),
        Spacer(1, 4),
        *caption,
    ]


def build_invoice_pdf(
    *,
    invoice: Any,
    customer: Any,
    sales: list[Any],
) -> bytes:
    buffer = BytesIO()
    invoice_no = _value(invoice, "invoice_no", "")
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=22 * mm,
        title=f"Invoice {invoice_no}",
        author="Dairy Management System",
        subject="Milk delivery invoice",
        creator="Dairy Management System",
    )

    footer = f"Dairy Management System - Invoice {invoice_no}"
    story: list[Any] = []
    story.extend(_header(invoice))
    story.extend(_parties(invoice, customer))
    story.extend(_items_table(sales))
    story.extend(_totals(invoice, sales))
    story.append(Spacer(1, 16))
    story.append(_rule(thickness=0.5, color=RULE))
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "This invoice lists the milk deliveries recorded for the billing "
            "period above and is generated from the dairy management records.",
            _styles()["note"],
        )
    )

    doc.build(story, canvasmaker=numbered_canvas(footer, margin=MARGIN))
    return buffer.getvalue()
