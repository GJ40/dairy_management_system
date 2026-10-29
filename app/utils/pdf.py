from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PRIMARY = HexColor("#1e3a8a")
SECONDARY = HexColor("#475569")
DARK = HexColor("#0f172a")
ROW_TEXT = HexColor("#1e293b")
LIGHT_BG = HexColor("#f8fafc")
BORDER = HexColor("#cbd5e1")
GREEN = HexColor("#15803d")
RED = HexColor("#b91c1c")
WHITE = HexColor("#ffffff")


def _number(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _money(value: Any) -> str:
    return f"{_number(value):.2f}"


def _customer_value(customer: Any, key: str, default: Any = None) -> Any:
    if isinstance(customer, dict):
        return customer.get(key, default)
    return getattr(customer, key, default)


def _invoice_value(invoice: Any, key: str, default: Any = None) -> Any:
    if isinstance(invoice, dict):
        return invoice.get(key, default)
    return getattr(invoice, key, default)


def build_invoice_pdf(
    *,
    invoice: Any,
    customer: Any,
    sales: list[Any],
) -> bytes:
    buffer = BytesIO()
    doc = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 40
    right = width - 40

    invoice_no = _invoice_value(invoice, "invoice_no", "")
    doc.setTitle(f"Invoice {invoice_no}")
    doc.setAuthor("Dairy Management System")
    doc.setSubject("Milk Delivery Invoice")

    y = height - 40
    doc.setFillColor(PRIMARY)
    doc.setFont("Helvetica-Bold", 22)
    doc.drawString(left, y - 12, "DAIRY MANAGEMENT SYSTEM")

    doc.setFillColor(SECONDARY)
    doc.setFont("Helvetica", 9)
    doc.drawString(left, y - 30, "Fresh Buffalo Milk & Dairy Products")
    doc.drawString(
        left,
        y - 42,
        "Farm Operations: Anand / Kheda District, Gujarat, India",
    )
    doc.drawString(left, y - 54, "Timezone: Asia/Kolkata (IST) | Currency: INR")

    doc.setFillColor(PRIMARY)
    doc.setFont("Helvetica-Bold", 18)
    doc.drawRightString(right, y - 12, "TAX INVOICE")

    doc.setFillColor(DARK)
    doc.setFont("Helvetica-Bold", 10)
    doc.drawRightString(right, y - 30, f"Invoice No: {invoice_no}")

    doc.setFillColor(SECONDARY)
    doc.setFont("Helvetica", 9)
    doc.drawRightString(
        right,
        y - 44,
        f"Period: {_invoice_value(invoice, 'period_start')} to "
        f"{_invoice_value(invoice, 'period_end')}",
    )
    doc.drawRightString(
        right,
        y - 58,
        f"Status: {str(_invoice_value(invoice, 'status', '')).upper()}",
    )

    divider_y = y - 75
    doc.setStrokeColor(BORDER)
    doc.setLineWidth(1)
    doc.line(left, divider_y, right, divider_y)

    card_top = y - 95
    doc.setFillColor(LIGHT_BG)
    doc.setStrokeColor(BORDER)
    doc.roundRect(left, card_top - 65, right - left, 65, 4, fill=1, stroke=1)

    doc.setFillColor(PRIMARY)
    doc.setFont("Helvetica-Bold", 10)
    doc.drawString(left + 15, card_top - 20, "BILL TO:")

    doc.setFillColor(DARK)
    doc.setFont("Helvetica-Bold", 11)
    doc.drawString(
        left + 15,
        card_top - 35,
        str(_customer_value(customer, "name", "Customer")),
    )

    contact = " | ".join(
        part
        for part in (
            f"Phone: {_customer_value(customer, 'phone')}"
            if _customer_value(customer, "phone")
            else None,
            f"Address: {_customer_value(customer, 'address')}"
            if _customer_value(customer, "address")
            else None,
        )
        if part
    )
    doc.setFillColor(SECONDARY)
    doc.setFont("Helvetica", 9)
    doc.drawString(
        left + 15,
        card_top - 55,
        contact or "No additional contact information",
    )

    table_top = card_top - 100
    table_height = 24
    doc.setFillColor(PRIMARY)
    doc.rect(left, table_top, right - left, table_height, fill=1, stroke=0)

    headers = (
        ("DATE", left + 10),
        ("QUANTITY (LITRES)", 220),
        ("RATE (INR / L)", 350),
        ("AMOUNT (INR)", 470),
    )
    doc.setFillColor(WHITE)
    doc.setFont("Helvetica-Bold", 9)
    for label, x in headers:
        if label.startswith("AMOUNT"):
            doc.drawRightString(right - 10, table_top + 7, label)
        else:
            doc.drawString(x, table_top + 7, label)

    row_y = table_top - 20
    row_height = 20
    total_litres = Decimal("0")

    for index, sale in enumerate(sales):
        if row_y < 110:
            doc.showPage()
            row_y = height - 50
        if index % 2 == 0:
            doc.setFillColor(LIGHT_BG)
            doc.rect(left, row_y, right - left, row_height, fill=1, stroke=0)

        sale_date = _invoice_value(sale, "sale_date", "")
        litres = _number(_invoice_value(sale, "litres"))
        rate = _number(_invoice_value(sale, "rate"))
        amount = _number(_invoice_value(sale, "amount"))
        total_litres += litres

        doc.setFillColor(ROW_TEXT)
        doc.setFont("Helvetica", 9)
        doc.drawString(left + 10, row_y + 5, str(sale_date))
        doc.drawString(220, row_y + 5, f"{litres:.2f} L")
        doc.drawString(350, row_y + 5, f"Rs. {rate:.2f}")
        doc.drawRightString(right - 10, row_y + 5, f"Rs. {amount:.2f}")
        row_y -= row_height

    doc.setStrokeColor(BORDER)
    doc.setLineWidth(1)
    doc.line(left, row_y, right, row_y)
    row_y -= 15

    total = _number(_invoice_value(invoice, "total_amount"))
    paid = _number(_invoice_value(invoice, "paid_amount"))
    balance = max(Decimal("0"), total - paid)

    card_x = 310
    card_width = right - card_x
    doc.setFillColor(LIGHT_BG)
    doc.setStrokeColor(BORDER)
    doc.roundRect(card_x, row_y - 90, card_width, 90, 4, fill=1, stroke=1)

    label_x = card_x + 15
    value_x = right - 15
    doc.setFillColor(SECONDARY)
    doc.setFont("Helvetica", 9)
    doc.drawString(label_x, row_y - 22, "Total Milk Supplied:")
    doc.drawString(label_x, row_y - 38, "Total Bill Amount:")
    doc.drawString(label_x, row_y - 54, "Amount Paid:")
    doc.drawRightString(value_x, row_y - 22, f"{total_litres:.2f} L")

    doc.setFillColor(DARK)
    doc.setFont("Helvetica-Bold", 9)
    doc.drawRightString(value_x, row_y - 38, f"Rs. {total:.2f}")

    doc.setFillColor(GREEN)
    doc.drawRightString(value_x, row_y - 54, f"Rs. {paid:.2f}")

    doc.setStrokeColor(BORDER)
    doc.setLineWidth(0.5)
    doc.line(label_x, row_y - 62, right - 15, row_y - 62)

    doc.setFillColor(RED if balance > 0 else GREEN)
    doc.setFont("Helvetica-Bold", 10)
    doc.drawString(label_x, row_y - 82, "Outstanding Balance:")
    doc.drawRightString(value_x, row_y - 82, f"Rs. {balance:.2f}")

    footer_y = 60
    doc.setStrokeColor(BORDER)
    doc.setLineWidth(0.5)
    doc.line(left, footer_y + 30, right, footer_y + 30)

    doc.setFillColor(SECONDARY)
    doc.setFont("Helvetica", 8)
    doc.drawCentredString(
        width / 2,
        footer_y + 15,
        "Thank you for choosing our dairy farm! Payment is due upon receipt.",
    )
    doc.drawCentredString(
        width / 2,
        footer_y + 3,
        "Computer-generated tax invoice. No signature required.",
    )

    doc.showPage()
    doc.save()
    return buffer.getvalue()
