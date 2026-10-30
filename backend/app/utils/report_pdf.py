"""Server-side analytical report PDFs (ReportLab platypus + vector charts).

Only ReportLab (already a project dependency) is used: the charts are drawn as
vector graphics through ``reportlab.graphics`` so they stay sharp when printed
on A4 and read well in grayscale. Every figure shown in a report comes from the
same report payload the JSON endpoints return.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Sequence
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.report import REPORT_TYPE_LABELS

# Restrained, grayscale-safe palette shared with the invoice template.
INK = HexColor("#111827")
BODY = HexColor("#1f2937")
MUTED = HexColor("#5b6472")
RULE = HexColor("#c7ccd4")
LIGHT = HexColor("#f3f4f6")
HEADER_FILL = HexColor("#111827")
ACCENT = HexColor("#1f6f5c")
ACCENT_LIGHT = HexColor("#8fb9ae")
NEGATIVE = HexColor("#9a3412")
WHITE = HexColor("#ffffff")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)

MAX_CHART_BARS = 12

_REPORT_SUBTITLES = {
    "profit": "Revenue, expenses and net profit for the selected period",
    "production": "Morning and evening milk collection for the selected period",
    "dashboard": "Herd, production, stock and sales snapshot for the selected day",
}


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _esc(value: Any) -> str:
    return escape(str(value if value is not None else ""))


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _money(value: Any) -> str:
    amount = _decimal(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,.2f}"


def _litres(value: Any) -> str:
    return f"{_decimal(value):,.2f}"


def _date_label(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    text = str(value)
    try:
        return date.fromisoformat(text[:10]).strftime("%d %b %Y")
    except ValueError:
        return text


def _percent(part: Decimal, whole: Decimal) -> str:
    if whole == 0:
        return "0.0%"
    return f"{(part / whole * 100):.1f}%"


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "brand": ParagraphStyle(
            "brand",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=INK,
        ),
        "brand_sub": ParagraphStyle(
            "brand_sub",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "title": ParagraphStyle(
            "report_title",
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=23,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "report_subtitle",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=MUTED,
        ),
        "meta": ParagraphStyle(
            "meta",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "section",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=INK,
            spaceBefore=14,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=8.8,
            leading=12.5,
            textColor=BODY,
        ),
        "note": ParagraphStyle(
            "note",
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=MUTED,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=INK,
        ),
        "kpi_caption": ParagraphStyle(
            "kpi_caption",
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=MUTED,
        ),
        "empty": ParagraphStyle(
            "empty",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=INK,
        ),
    }


# --------------------------------------------------------------------------- #
# Page chrome
# --------------------------------------------------------------------------- #
def numbered_canvas(
    footer_left: str,
    *,
    margin: float | None = None,
) -> type[canvas.Canvas]:
    """Canvas factory that stamps "Page X of Y" once the page count is known."""
    side = MARGIN if margin is None else margin

    class _NumberedCanvas(canvas.Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states: list[dict[str, Any]] = []

        def showPage(self) -> None:  # noqa: N802 - ReportLab API
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(total)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def _draw_footer(self, total: int) -> None:
            self.saveState()
            self.setStrokeColor(RULE)
            self.setLineWidth(0.5)
            self.line(side, 15 * mm, PAGE_WIDTH - side, 15 * mm)
            self.setFillColor(MUTED)
            self.setFont("Helvetica", 7.5)
            self.drawString(side, 10.5 * mm, footer_left)
            self.drawRightString(
                PAGE_WIDTH - side,
                10.5 * mm,
                f"Page {self._pageNumber} of {total}",
            )
            self.restoreState()

    return _NumberedCanvas


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def _axis_step(top: float) -> float:
    if top <= 0:
        return 1.0
    raw = top / 5
    magnitude = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * magnitude:
            return max(float(factor * magnitude), 1.0)
    return max(float(10 * magnitude), 1.0)


def _bucket_series(
    points: Sequence[tuple[str, Decimal, Decimal]],
) -> tuple[list[str], list[list[float]], str]:
    """Group per-day values so a chart never carries more than 12 categories."""
    if not points:
        return [], [], ""
    group = max(1, math.ceil(len(points) / MAX_CHART_BARS))
    labels: list[str] = []
    first: list[float] = []
    second: list[float] = []
    for index in range(0, len(points), group):
        chunk = points[index : index + group]
        labels.append(_short_label(chunk[0][0]))
        first.append(float(sum((row[1] for row in chunk), Decimal("0"))))
        second.append(float(sum((row[2] for row in chunk), Decimal("0"))))
    caption = (
        "Each bar covers one day."
        if group == 1
        else f"Each bar covers {group} days to keep the axis readable."
    )
    return labels, [first, second], caption


def _short_label(value: str) -> str:
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)[:10]
    return parsed.strftime("%d %b")


def _grouped_bar_chart(
    *,
    labels: Sequence[str],
    series: Sequence[Sequence[float]],
    colors: Sequence[HexColor],
    height: float = 168,
) -> Drawing:
    drawing = Drawing(CONTENT_WIDTH, height + 26)
    chart = VerticalBarChart()
    chart.x = 34
    chart.y = 20
    chart.width = CONTENT_WIDTH - 48
    chart.height = height
    chart.data = [list(values) for values in series]
    chart.categoryAxis.categoryNames = list(labels)
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.boxAnchor = "n"
    chart.categoryAxis.labels.dy = -4
    chart.categoryAxis.strokeColor = RULE
    chart.valueAxis.valueMin = min(0.0, min((min(v) for v in series if v), default=0.0))
    top = max((max(v) for v in series if v), default=0.0)
    chart.valueAxis.valueMax = top if top > 0 else 1
    chart.valueAxis.valueStep = _axis_step(chart.valueAxis.valueMax)
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labelTextFormat = "%d"
    chart.valueAxis.strokeColor = RULE
    chart.bars.strokeColor = WHITE
    for index, color in enumerate(colors):
        chart.bars[index].fillColor = color
    drawing.add(chart)
    return drawing


def _horizontal_bar_chart(
    *,
    labels: Sequence[str],
    values: Sequence[float],
    height: float = 150,
) -> Drawing:
    drawing = Drawing(CONTENT_WIDTH, height + 24)
    chart = HorizontalBarChart()
    chart.x = 96
    chart.y = 16
    chart.width = CONTENT_WIDTH - 110
    chart.height = height
    chart.data = [list(values)]
    chart.categoryAxis.categoryNames = list(labels)
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 7.5
    chart.categoryAxis.labels.boxAnchor = "e"
    chart.categoryAxis.labels.dx = -4
    chart.categoryAxis.strokeColor = RULE
    top = max(values) if values else 0.0
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = top if top > 0 else 1
    chart.valueAxis.valueStep = _axis_step(chart.valueAxis.valueMax)
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labelTextFormat = "%d"
    chart.valueAxis.strokeColor = RULE
    chart.bars.strokeColor = WHITE
    for index in range(len(values)):
        chart.bars[index].fillColor = ACCENT
    drawing.add(chart)
    return drawing


def _legend(entries: Sequence[tuple[str, HexColor]]) -> Table:
    """One-row legend: a filled swatch cell followed by the series label."""
    styles = _styles()
    row: list[Any] = []
    widths: list[float] = []
    style: list[tuple[Any, ...]] = []
    for position, (label, color) in enumerate(entries):
        column = position * 2
        row.append("")
        row.append(Paragraph(_esc(label), styles["body"]))
        widths.extend([10, 132])
        style.append(("BACKGROUND", (column, 0), (column, 0), color))
        style.append(("BOX", (column, 0), (column, 0), 0.4, RULE))
    return Table(
        [row],
        colWidths=widths,
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                *style,
            ]
        ),
        hAlign="LEFT",
    )


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def _table(
    rows: list[list[Any]],
    col_widths: Sequence[float],
    *,
    numeric_from: int = 1,
    total_row: bool = False,
) -> Table:
    table = Table(
        rows,
        colWidths=list(col_widths),
        repeatRows=1,
        hAlign="LEFT",
    )
    last = len(rows) - 1
    style: list[tuple[Any, ...]] = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.2),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), BODY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            style.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), LIGHT)
            )
    if total_row and len(rows) > 1:
        style.extend(
            [
                ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
                ("BACKGROUND", (0, last), (-1, last), LIGHT),
                ("LINEABOVE", (0, last), (-1, last), 0.8, HEADER_FILL),
                ("TEXTCOLOR", (0, last), (-1, last), INK),
            ]
        )
    table.setStyle(TableStyle(style))
    return table


def _kpi_row(items: Sequence[tuple[str, str, str]]) -> Table:
    styles = _styles()
    cells = [
        [
            Paragraph(_esc(label), styles["kpi_label"]),
            Paragraph(_esc(value), styles["kpi_value"]),
            (
                Paragraph(_esc(caption), styles["kpi_caption"])
                if caption
                else Spacer(1, 1)
            ),
        ]
        for label, value, caption in items
    ]
    width = CONTENT_WIDTH / len(cells)
    table = Table(
        [cells],
        colWidths=[width] * len(cells),
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
        hAlign="LEFT",
    )
    return table


def _empty_notice(message: str) -> Table:
    styles = _styles()
    table = Table(
        [[Paragraph(_esc(message), styles["empty"])]],
        colWidths=[CONTENT_WIDTH],
        style=TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        ),
        hAlign="LEFT",
    )
    return table


# --------------------------------------------------------------------------- #
# Story sections
# --------------------------------------------------------------------------- #
def _header(report_type: str, period_label: str, generated_at: datetime, prepared_by: str) -> list[Any]:
    styles = _styles()
    title = REPORT_TYPE_LABELS.get(report_type, "Report")
    subtitle = _REPORT_SUBTITLES.get(report_type, "")
    brand = Table(
        [
            [
                [
                    Paragraph("Dairy Management System", styles["brand"]),
                    Paragraph(
                        "Milk production, sales and billing records",
                        styles["brand_sub"],
                    ),
                ],
                [
                    Paragraph(f"<b>{_esc(title)}</b>", styles["meta"]),
                    Paragraph(_esc(period_label), styles["meta"]),
                ],
            ]
        ],
        colWidths=[CONTENT_WIDTH * 0.56, CONTENT_WIDTH * 0.44],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
        hAlign="LEFT",
    )
    rule = Table(
        [[""]],
        colWidths=[CONTENT_WIDTH],
        rowHeights=[1],
        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), HEADER_FILL)]),
        hAlign="LEFT",
    )
    meta_line = (
        f"Generated {generated_at.strftime('%d %b %Y, %H:%M')} IST"
        f" | Prepared by {_esc(prepared_by)} | Currency: INR"
    )
    return [
        brand,
        rule,
        Paragraph(_esc(title), styles["title"]),
        Paragraph(_esc(subtitle), styles["subtitle"]),
        Spacer(1, 4),
        Paragraph(meta_line, styles["meta"]),
        Spacer(1, 10),
    ]


def _profit_story(report: dict[str, Any]) -> list[Any]:
    styles = _styles()
    summary = report.get("summary") or {}
    daily = report.get("daily_breakdown") or []
    categories = report.get("category_breakdown") or []

    revenue = _decimal(summary.get("total_revenue"))
    expenses = _decimal(summary.get("total_expenses"))
    profit = _decimal(summary.get("net_profit"))
    litres = _decimal(summary.get("total_litres_sold"))
    margin = _percent(profit, revenue) if revenue else "0.0%"
    avg_rate = (revenue / litres) if litres else Decimal("0")

    story: list[Any] = [
        _kpi_row(
            [
                ("TOTAL REVENUE", f"Rs. {_money(revenue)}", f"{_litres(litres)} L sold"),
                ("TOTAL EXPENSES", f"Rs. {_money(expenses)}", f"{len(categories)} categories"),
                (
                    "NET PROFIT",
                    f"Rs. {_money(profit)}",
                    f"{margin} of revenue",
                ),
                (
                    "AVG. REALISED RATE",
                    f"Rs. {_money(avg_rate)}",
                    "Revenue per litre sold",
                ),
            ]
        ),
        Spacer(1, 10),
        Paragraph("Executive summary", styles["section"]),
    ]

    if not daily and not categories:
        story.append(
            _empty_notice(
                "No data for the selected period. No sales or expenses were "
                "recorded in this date range."
            )
        )
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                "Widen the date range or record sales and expenses first, then "
                "generate the report again.",
                styles["note"],
            )
        )
        return story

    busiest = max(daily, key=lambda row: _decimal(row.get("revenue"))) if daily else None
    weakest = min(daily, key=lambda row: _decimal(row.get("profit"))) if daily else None
    top_category = (
        max(categories, key=lambda row: _decimal(row.get("total_amount")))
        if categories
        else None
    )
    parts = [
        f"Revenue of Rs. {_money(revenue)} was recorded from {_litres(litres)} litres "
        f"supplied, against expenses of Rs. {_money(expenses)}.",
        (
            f"Net profit was Rs. {_money(profit)} ({margin} of revenue)."
            if profit >= 0
            else f"The period closed with a net loss of Rs. {_money(abs(profit))}."
        ),
    ]
    if top_category is not None:
        parts.append(
            f"The largest expense category was {_esc(top_category.get('category'))} at "
            f"Rs. {_money(top_category.get('total_amount'))} "
            f"({_esc(top_category.get('percentage'))} of expenses)."
        )
    if busiest is not None:
        parts.append(
            f"The strongest sales day was {_date_label(busiest.get('date'))} with "
            f"Rs. {_money(busiest.get('revenue'))}."
        )
    if weakest is not None and _decimal(weakest.get("profit")) < 0:
        parts.append(
            f"The weakest day was {_date_label(weakest.get('date'))} at "
            f"Rs. {_money(weakest.get('profit'))}."
        )
    story.append(Paragraph(" ".join(parts), styles["body"]))

    if daily:
        points = [
            (
                str(row.get("date")),
                _decimal(row.get("revenue")),
                _decimal(row.get("expenses")),
            )
            for row in daily
        ]
        labels, series, caption = _bucket_series(points)
        story.append(Paragraph("Revenue vs. expenses", styles["section"]))
        story.append(
            _grouped_bar_chart(
                labels=labels,
                series=series,
                colors=[ACCENT, ACCENT_LIGHT],
            )
        )
        story.append(_legend([("Revenue (Rs.)", ACCENT), ("Expenses (Rs.)", ACCENT_LIGHT)]))
        story.append(Paragraph(_esc(caption), styles["note"]))

    if categories:
        ordered = sorted(
            categories,
            key=lambda row: _decimal(row.get("total_amount")),
        )
        trimmed = ordered[-8:] if len(ordered) > 8 else ordered
        omitted = len(ordered) - len(trimmed)
        chart_labels = [
            (str(row.get("category"))[:16]) for row in trimmed
        ]
        values = [float(_decimal(row.get("total_amount"))) for row in trimmed]
        story.append(Paragraph("Expense distribution", styles["section"]))
        story.append(_horizontal_bar_chart(labels=chart_labels, values=values))
        category_caption = "Largest categories are shown at the top."
        if omitted == 1:
            category_caption += (
                " 1 smaller category is listed in the table only."
            )
        elif omitted:
            category_caption += (
                f" {omitted} smaller categories are listed in the table only."
            )
        story.append(Paragraph(_esc(category_caption), styles["note"]))

    story.append(Paragraph("Daily breakdown", styles["section"]))
    rows: list[list[Any]] = [
        ["Date", "Revenue (Rs.)", "Expenses (Rs.)", "Net (Rs.)", "Litres sold"]
    ]
    for row in daily:
        rows.append(
            [
                _date_label(row.get("date")),
                _money(row.get("revenue")),
                _money(row.get("expenses")),
                _money(row.get("profit")),
                _litres(row.get("litres_sold")),
            ]
        )
    rows.append(
        [
            "Total",
            _money(revenue),
            _money(expenses),
            _money(profit),
            _litres(litres),
        ]
    )
    story.append(
        _table(
            rows,
            [CONTENT_WIDTH * 0.22, CONTENT_WIDTH * 0.2, CONTENT_WIDTH * 0.2,
             CONTENT_WIDTH * 0.19, CONTENT_WIDTH * 0.19],
            total_row=True,
        )
    )

    if categories:
        story.append(Paragraph("Expense categories", styles["section"]))
        cat_rows: list[list[Any]] = [["Category", "Amount (Rs.)", "Share of expenses"]]
        for row in categories:
            cat_rows.append(
                [
                    str(row.get("category")),
                    _money(row.get("total_amount")),
                    str(row.get("percentage")),
                ]
            )
        cat_rows.append(["Total", _money(expenses), "100.0%" if expenses else "0.0%"])
        story.append(
            _table(
                cat_rows,
                [CONTENT_WIDTH * 0.46, CONTENT_WIDTH * 0.27, CONTENT_WIDTH * 0.27],
                total_row=True,
            )
        )
    return story


def _production_story(report: dict[str, Any]) -> list[Any]:
    styles = _styles()
    daily = report.get("daily_summaries") or []
    total = _decimal(report.get("grand_total_litres"))
    days = int(report.get("days_recorded") or 0)
    average = _decimal(report.get("average_daily_litres"))
    morning = sum((_decimal(row.get("morning_litres")) for row in daily), Decimal("0"))
    evening = sum((_decimal(row.get("evening_litres")) for row in daily), Decimal("0"))
    morning_rate = _percent(morning, total)
    evening_rate = _percent(evening, total)
    best = max(daily, key=lambda row: _decimal(row.get("total_litres"))) if daily else None

    story: list[Any] = [
        _kpi_row(
            [
                ("DAYS RECORDED", str(days), "Days with at least one entry"),
                ("TOTAL PRODUCTION", f"{_litres(total)} L", "Morning plus evening"),
                ("AVERAGE PER DAY", f"{_litres(average)} L", "Herd daily average"),
                (
                    "SESSION SPLIT",
                    f"{_litres(morning)} / {_litres(evening)}",
                    f"Morning {morning_rate} / evening {evening_rate}",
                ),
            ]
        ),
        Spacer(1, 10),
        Paragraph("Executive summary", styles["section"]),
    ]

    if not daily:
        story.append(
            _empty_notice(
                "No data for the selected period. No milk production was "
                "recorded in this date range."
            )
        )
        return story

    parts = [
        f"The herd produced {_litres(total)} litres over {days} recorded "
        f"day{'s' if days != 1 else ''}, an average of {_litres(average)} litres per day.",
        f"Morning sessions contributed {_litres(morning)} litres ({morning_rate}) and "
        f"evening sessions {_litres(evening)} litres ({evening_rate}).",
    ]
    if best is not None:
        parts.append(
            f"The highest collection day was {_date_label(best.get('prod_date'))} with "
            f"{_litres(best.get('total_litres'))} litres."
        )
    story.append(Paragraph(" ".join(parts), styles["body"]))

    points = [
        (
            str(row.get("prod_date")),
            _decimal(row.get("morning_litres")),
            _decimal(row.get("evening_litres")),
        )
        for row in daily
    ]
    labels, series, caption = _bucket_series(points)
    story.append(Paragraph("Morning vs. evening collection", styles["section"]))
    story.append(
        _grouped_bar_chart(labels=labels, series=series, colors=[ACCENT, ACCENT_LIGHT])
    )
    story.append(
        _legend([("Morning (L)", ACCENT), ("Evening (L)", ACCENT_LIGHT)])
    )
    story.append(Paragraph(_esc(caption), styles["note"]))

    story.append(Paragraph("Daily production", styles["section"]))
    rows: list[list[Any]] = [["Date", "Morning (L)", "Evening (L)", "Total (L)"]]
    for row in daily:
        rows.append(
            [
                _date_label(row.get("prod_date")),
                _litres(row.get("morning_litres")),
                _litres(row.get("evening_litres")),
                _litres(row.get("total_litres")),
            ]
        )
    rows.append(["Total", _litres(morning), _litres(evening), _litres(total)])
    story.append(
        _table(
            rows,
            [CONTENT_WIDTH * 0.28, CONTENT_WIDTH * 0.24, CONTENT_WIDTH * 0.24,
             CONTENT_WIDTH * 0.24],
            total_row=True,
        )
    )
    return story


def _dashboard_story(report: dict[str, Any]) -> list[Any]:
    styles = _styles()
    herd = report.get("buffaloes") or {}
    production = report.get("production") or {}
    stock = report.get("stock") or {}
    sales = report.get("sales") or {}
    financials = report.get("financials")

    produced = _decimal(production.get("grand_total_litres"))
    sold = _decimal(sales.get("litres_sold"))
    closing = _decimal(stock.get("closing_stock"))

    story: list[Any] = [
        _kpi_row(
            [
                ("ACTIVE BUFFALOES", str(herd.get("active", 0)), f"{herd.get('total', 0)} in herd"),
                ("MILK PRODUCED", f"{_litres(produced)} L", "Morning plus evening"),
                ("MILK SOLD", f"{_litres(sold)} L", f"{sales.get('sales_count', 0)} sales"),
                ("CLOSING STOCK", f"{_litres(closing)} L", "End of the day"),
            ]
        ),
        Spacer(1, 10),
        Paragraph("Executive summary", styles["section"]),
    ]

    has_data = any(
        _decimal(production.get(key)) for key in ("morning_litres", "evening_litres")
    ) or bool(sales.get("sales_count")) or closing != 0
    if not has_data:
        story.append(
            _empty_notice(
                "No data for the selected period. No production, sales or stock "
                "movement was recorded on this day."
            )
        )

    parts = [
        f"On {_date_label(report.get('date'))} the herd produced {_litres(produced)} litres "
        f"({_litres(production.get('morning_litres'))} L morning, "
        f"{_litres(production.get('evening_litres'))} L evening).",
        f"{_litres(sold)} litres were sold across {sales.get('sales_count', 0)} sales, "
        f"leaving a closing stock of {_litres(closing)} litres.",
    ]
    if financials:
        today = financials.get("today") or {}
        parts.append(
            f"Today's revenue was Rs. {_money(today.get('revenue'))} and expenses "
            f"Rs. {_money(today.get('expenses'))}, a profit of "
            f"Rs. {_money(today.get('profit'))}."
        )
    story.append(Paragraph(" ".join(parts), styles["body"]))

    story.append(Paragraph("Herd and stock position", styles["section"]))
    rows: list[list[Any]] = [["Measure", "Value"]]
    rows.extend(
        [
            ["Active buffaloes", str(herd.get("active", 0))],
            ["Dry buffaloes", str(herd.get("dry", 0))],
            ["Sold buffaloes", str(herd.get("sold", 0))],
            ["Dead buffaloes", str(herd.get("dead", 0))],
            ["Total herd", str(herd.get("total", 0))],
            ["Opening stock (L)", _litres(stock.get("opening_stock"))],
            ["Produced (L)", _litres(stock.get("produced"))],
            ["Sold (L)", _litres(stock.get("sold"))],
            ["Wasted (L)", _litres(stock.get("wasted"))],
            ["Closing stock (L)", _litres(stock.get("closing_stock"))],
        ]
    )
    story.append(_table(rows, [CONTENT_WIDTH * 0.6, CONTENT_WIDTH * 0.4]))

    if financials:
        today = financials.get("today") or {}
        month = financials.get("month_to_date") or {}
        story.append(Paragraph("Financial position", styles["section"]))
        fin_rows: list[list[Any]] = [["Period", "Revenue (Rs.)", "Expenses (Rs.)", "Profit (Rs.)"]]
        fin_rows.append(
            [
                "Selected day",
                _money(today.get("revenue")),
                _money(today.get("expenses")),
                _money(today.get("profit")),
            ]
        )
        fin_rows.append(
            [
                f"Month to date ({_date_label(month.get('from'))} - {_date_label(month.get('to'))})",
                _money(month.get("revenue")),
                _money(month.get("expenses")),
                _money(month.get("profit")),
            ]
        )
        story.append(
            _table(
                fin_rows,
                [CONTENT_WIDTH * 0.4, CONTENT_WIDTH * 0.2, CONTENT_WIDTH * 0.2,
                 CONTENT_WIDTH * 0.2],
            )
        )
    else:
        story.append(
            Paragraph(
                "Financial figures are visible to Admin users only.",
                styles["note"],
            )
        )
    return story


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def build_report_pdf(
    *,
    report_type: str,
    report: dict[str, Any],
    period_from: str,
    period_to: str,
    generated_at: datetime,
    prepared_by: str,
    compress: bool = True,
) -> bytes:
    buffer = BytesIO()
    title = REPORT_TYPE_LABELS.get(report_type, "Report")
    period_label = (
        f"Period: {_date_label(period_from)}"
        if period_from == period_to
        else f"Period: {_date_label(period_from)} - {_date_label(period_to)}"
    )
    footer = (
        f"Dairy Management System - {title} - "
        f"{_date_label(period_from)} to {_date_label(period_to)}"
    )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=22 * mm,
        title=f"{title} ({period_from} to {period_to})",
        author="Dairy Management System",
        subject=title,
        creator="Dairy Management System",
        pageCompression=1 if compress else 0,
    )

    story = _header(report_type, period_label, generated_at, prepared_by)
    if report_type == "profit":
        story.extend(_profit_story(report))
    elif report_type == "production":
        story.extend(_production_story(report))
    else:
        story.extend(_dashboard_story(report))

    story.extend(
        [
            Spacer(1, 14),
            Paragraph(
                "Figures are computed from recorded production, sales, wastage "
                "and expense entries. Soft-deleted records are excluded.",
                _styles()["note"],
            ),
        ]
    )

    doc.build(story, canvasmaker=numbered_canvas(footer))
    return buffer.getvalue()


def report_filename(report_type: str, period_from: str, period_to: str) -> str:
    suffix = (
        period_from
        if period_from == period_to
        else f"{period_from}_to_{period_to}"
    )
    safe = "".join(
        char for char in f"dairy-{report_type}-report-{suffix}" if char.isalnum() or char in "-_"
    )
    return f"{safe}.pdf"

