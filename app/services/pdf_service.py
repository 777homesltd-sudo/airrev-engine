"""
AirRev Engine — PDF Report Generator
Produces print/email-ready reports using ReportLab.

Two report types:
  1. Property Investment Report  — full LTR + STR analysis for a single listing
  2. CREB Monthly Market Report  — Calgary market summary, print/email-ready
"""

import io
from datetime import datetime
from typing import Optional, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF

# ── Brand colours ──────────────────────────────────────────────
AIRREV_NAVY    = colors.HexColor("#0F172A")
AIRREV_BLUE    = colors.HexColor("#2563EB")
AIRREV_TEAL    = colors.HexColor("#0EA5E9")
AIRREV_GREEN   = colors.HexColor("#10B981")
AIRREV_RED     = colors.HexColor("#EF4444")
AIRREV_AMBER   = colors.HexColor("#F59E0B")
AIRREV_GRAY    = colors.HexColor("#64748B")
AIRREV_LIGHT   = colors.HexColor("#F1F5F9")
AIRREV_WHITE   = colors.white
AIRREV_BORDER  = colors.HexColor("#E2E8F0")


def _build_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "AirRevTitle",
            fontSize=22, fontName="Helvetica-Bold",
            textColor=AIRREV_NAVY, spaceAfter=4, leading=26,
        ),
        "subtitle": ParagraphStyle(
            "AirRevSubtitle",
            fontSize=11, fontName="Helvetica",
            textColor=AIRREV_GRAY, spaceAfter=16,
        ),
        "section_heading": ParagraphStyle(
            "AirRevSection",
            fontSize=13, fontName="Helvetica-Bold",
            textColor=AIRREV_NAVY, spaceBefore=14, spaceAfter=6,
        ),
        "label": ParagraphStyle(
            "AirRevLabel",
            fontSize=8, fontName="Helvetica",
            textColor=AIRREV_GRAY, spaceAfter=1,
        ),
        "value": ParagraphStyle(
            "AirRevValue",
            fontSize=14, fontName="Helvetica-Bold",
            textColor=AIRREV_NAVY, spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "AirRevBody",
            fontSize=9, fontName="Helvetica",
            textColor=AIRREV_NAVY, leading=14, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "AirRevSmall",
            fontSize=7.5, fontName="Helvetica",
            textColor=AIRREV_GRAY, leading=11,
        ),
        "positive": ParagraphStyle(
            "AirRevPos",
            fontSize=13, fontName="Helvetica-Bold",
            textColor=AIRREV_GREEN,
        ),
        "negative": ParagraphStyle(
            "AirRevNeg",
            fontSize=13, fontName="Helvetica-Bold",
            textColor=AIRREV_RED,
        ),
        "tag_green": ParagraphStyle(
            "TagGreen",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=AIRREV_GREEN,
        ),
        "tag_red": ParagraphStyle(
            "TagRed",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=AIRREV_RED,
        ),
        "tag_amber": ParagraphStyle(
            "TagAmber",
            fontSize=8, fontName="Helvetica-Bold",
            textColor=AIRREV_AMBER,
        ),
    }
    return styles


def _cad(value: float) -> str:
    """Format as Canadian dollars."""
    if value < 0:
        return f"-C${abs(value):,.0f}"
    return f"C${value:,.0f}"


def _pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:.{decimals}f}%"


def _metric_table(data: list, col_widths=None) -> Table:
    """
    Render a clean 2-column label/value metrics block.
    data = [("Label", "Value"), ...]
    """
    col_widths = col_widths or [2.8 * inch, 2.8 * inch]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), AIRREV_LIGHT),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [AIRREV_WHITE, AIRREV_LIGHT]),
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica"),
        ("FONTNAME",    (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 0), (0, -1), AIRREV_GRAY),
        ("TEXTCOLOR",   (1, 0), (1, -1), AIRREV_NAVY),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.5, AIRREV_BORDER),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _kpi_row(items: list) -> Table:
    """
    Big KPI cards in a horizontal row.
    items = [{"label": "Cap Rate", "value": "4.2%", "positive": True}, ...]
    """
    styles = _build_styles()
    cells = []
    for item in items:
        val_style = styles["positive"] if item.get("positive") else (
            styles["negative"] if item.get("positive") is False else styles["value"]
        )
        cell = [
            Paragraph(item["label"], styles["label"]),
            Paragraph(item["value"], val_style),
        ]
        if item.get("sub"):
            cell.append(Paragraph(item["sub"], styles["small"]))
        cells.append(cell)

    col_width = (7.5 * inch) / len(items)
    t = Table([cells], colWidths=[col_width] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AIRREV_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, -1), AIRREV_WHITE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.5, colors.HexColor("#1E293B")),
    ]))
    return t


def _header_bar(story, styles, title: str, subtitle: str, tag: str = "", tag_color=None):
    """Top header with AirRev branding."""
    story.append(Paragraph("AirRev.io", ParagraphStyle(
        "brand", fontSize=9, fontName="Helvetica-Bold",
        textColor=AIRREV_BLUE, spaceAfter=2,
    )))
    story.append(Paragraph(title, styles["title"]))
    story.append(Paragraph(subtitle, styles["subtitle"]))
    if tag:
        tag_style = ParagraphStyle("tag", fontSize=8, fontName="Helvetica-Bold",
                                    textColor=tag_color or AIRREV_BLUE)
        story.append(Paragraph(f"● {tag}", tag_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=AIRREV_BLUE, spaceAfter=14))


# ══════════════════════════════════════════════════════════════
# 1. PROPERTY INVESTMENT REPORT
# ══════════════════════════════════════════════════════════════

def generate_property_report(data: Dict[str, Any]) -> bytes:
    """
    Full investment analysis PDF for a single MLS listing.
    Accepts the AnalyzeListingResponse dict.
    Returns PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = _build_styles()
    story = []
    prop = data.get("property", {})
    mortgage = data.get("mortgage", {})
    ltr = data.get("ltr")
    str_d = data.get("str_analysis")
    summary = data.get("summary", {})

    # ── Header ────────────────────────────────────────────────
    rec = summary.get("recommendation", "")
    rec_color = {
        "Strong Buy": AIRREV_GREEN,
        "Buy": AIRREV_TEAL,
        "Hold": AIRREV_AMBER,
        "Avoid": AIRREV_RED,
    }.get(rec, AIRREV_BLUE)

    _header_bar(
        story, styles,
        title=prop.get("address", "Investment Property Analysis"),
        subtitle=f"{prop.get('community', '')}, {prop.get('city', 'Calgary')} · MLS® {prop.get('mls_number', '')} · Generated {datetime.now().strftime('%B %d, %Y')}",
        tag=f"{rec} — Best Strategy: {summary.get('best_strategy', '')}",
        tag_color=rec_color,
    )

    # ── KPI Row ───────────────────────────────────────────────
    kpis = []
    if ltr:
        coc_val = ltr.get("cash_on_cash_return", 0)
        kpis += [
            {"label": "LTR Cap Rate",      "value": ltr.get("cap_rate_display", "—"),    "positive": ltr.get("cap_rate", 0) >= 0.04},
            {"label": "LTR Cash-on-Cash",  "value": ltr.get("cash_on_cash_display", "—"), "positive": coc_val >= 0},
            {"label": "LTR Monthly Flow",  "value": _cad(ltr.get("monthly_cash_flow", 0)), "positive": ltr.get("monthly_cash_flow", 0) >= 0},
        ]
    if str_d:
        kpis += [
            {"label": "STR Cap Rate",      "value": str_d.get("cap_rate_display", "—"),    "positive": str_d.get("cap_rate", 0) >= 0.04},
            {"label": "STR Cash-on-Cash",  "value": str_d.get("cash_on_cash_display", "—"), "positive": str_d.get("cash_on_cash_return", 0) >= 0},
        ]
    if kpis:
        story.append(_kpi_row(kpis[:5]))
        story.append(Spacer(1, 14))

    # ── Property Details + Mortgage side by side ───────────────
    story.append(Paragraph("Property Details", styles["section_heading"]))

    left_data = [
        ("List Price",      _cad(prop.get("list_price", 0))),
        ("Bedrooms",        str(prop.get("bedrooms", "—"))),
        ("Bathrooms",       str(prop.get("bathrooms", "—"))),
        ("Property Type",   prop.get("property_type", "—")),
        ("Sq Footage",      f"{prop.get('square_footage', 0):,.0f} sqft" if prop.get("square_footage") else "—"),
        ("Year Built",      str(prop.get("year_built", "—")) if prop.get("year_built") else "—"),
        ("Community",       prop.get("community", "—")),
        ("Parking",         str(prop.get("parking", "—")) if prop.get("parking") else "—"),
    ]
    right_data = [
        ("Down Payment",    _cad(mortgage.get("down_payment", 0))),
        ("Down Payment %",  _pct(mortgage.get("down_payment_pct", 0.20))),
        ("Loan Amount",     _cad(mortgage.get("loan_amount", 0))),
        ("Interest Rate",   _pct(mortgage.get("interest_rate", 0))),
        ("Amortization",    f"{mortgage.get('amortization_years', 25)} years"),
        ("Monthly Payment", _cad(mortgage.get("monthly_payment", 0))),
        ("Annual Payment",  _cad(mortgage.get("annual_payment", 0))),
        ("", ""),
    ]

    combined = [[
        _metric_table(left_data,  col_widths=[1.6*inch, 1.85*inch]),
        _metric_table(right_data, col_widths=[1.6*inch, 1.85*inch]),
    ]]
    side_table = Table(combined, colWidths=[3.6*inch, 3.9*inch])
    side_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 10),
    ]))
    story.append(side_table)
    story.append(Spacer(1, 14))

    # ── LTR Analysis ──────────────────────────────────────────
    if ltr:
        story.append(Paragraph("Long-Term Rental (LTR) Analysis", styles["section_heading"]))
        ltr_data = [
            ("Estimated Monthly Rent",    _cad(ltr.get("estimated_monthly_rent", 0))),
            ("Annual Gross Revenue",      _cad(ltr.get("annual_gross_revenue", 0))),
            ("Vacancy Allowance (4%)",    f"-{_cad(ltr.get('vacancy_allowance', 0))}"),
            ("Effective Gross Income",    _cad(ltr.get("effective_gross_income", 0))),
            ("── Expenses ──",            ""),
            ("Property Tax",              _cad(ltr.get("property_tax_annual", 0))),
            ("Insurance",                 _cad(ltr.get("insurance_annual", 0))),
            ("Maintenance Reserve",       _cad(ltr.get("maintenance_annual", 0))),
            ("Property Management (10%)", _cad(ltr.get("management_fee_annual", 0))),
            ("Total Expenses",            _cad(ltr.get("total_annual_expenses", 0))),
            ("── Returns ──",             ""),
            ("Net Operating Income (NOI)",_cad(ltr.get("noi", 0))),
            ("Annual Mortgage",           f"-{_cad(mortgage.get('annual_payment', 0))}"),
            ("Annual Cash Flow",          _cad(ltr.get("annual_cash_flow", 0))),
            ("Monthly Cash Flow",         _cad(ltr.get("monthly_cash_flow", 0))),
            ("Cap Rate",                  ltr.get("cap_rate_display", "—")),
            ("Cash-on-Cash Return",       ltr.get("cash_on_cash_display", "—")),
            ("Gross Rent Multiplier",     f"{ltr.get('gross_rent_multiplier', 0):.1f}x"),
        ]
        story.append(_metric_table(ltr_data, col_widths=[3.4*inch, 4.1*inch]))
        story.append(Spacer(1, 14))

    # ── STR Analysis ──────────────────────────────────────────
    if str_d:
        story.append(Paragraph("Short-Term Rental / Airbnb (STR) Analysis", styles["section_heading"]))
        str_data = [
            ("Estimated Nightly Rate",    _cad(str_d.get("estimated_nightly_rate", 0))),
            ("Estimated Occupancy",       _pct(str_d.get("estimated_occupancy_rate", 0))),
            ("Annual Gross Revenue",      _cad(str_d.get("annual_gross_revenue", 0))),
            ("── Expenses ──",            ""),
            ("Airbnb Host Fee (3%)",      _cad(str_d.get("airbnb_host_fee_annual", 0))),
            ("Cleaning Costs",            _cad(str_d.get("cleaning_costs_annual", 0))),
            ("Property Tax",              _cad(str_d.get("property_tax_annual", 0))),
            ("Insurance (STR)",           _cad(str_d.get("insurance_annual", 0))),
            ("Maintenance Reserve",       _cad(str_d.get("maintenance_annual", 0))),
            ("Property Management (20%)", _cad(str_d.get("management_fee_annual", 0))),
            ("Supplies",                  _cad(str_d.get("supplies_annual", 0))),
            ("Total Expenses",            _cad(str_d.get("total_annual_expenses", 0))),
            ("── Returns ──",             ""),
            ("Net Operating Income (NOI)",_cad(str_d.get("noi", 0))),
            ("Annual Cash Flow",          _cad(str_d.get("annual_cash_flow", 0))),
            ("Monthly Cash Flow",         _cad(str_d.get("monthly_cash_flow", 0))),
            ("Cap Rate",                  str_d.get("cap_rate_display", "—")),
            ("Cash-on-Cash Return",       str_d.get("cash_on_cash_display", "—")),
        ]
        if str_d.get("is_turnkey_active"):
            str_data.append(("🏠 Turnkey Active", "Listing found on Airbnb — verify before purchase"))
        if str_d.get("avg_neighbourhood_nightly_rate"):
            str_data.append(("Neighbourhood Avg Nightly", _cad(str_d["avg_neighbourhood_nightly_rate"])))
        if str_d.get("avg_neighbourhood_occupancy"):
            str_data.append(("Neighbourhood Avg Occ.", _pct(str_d["avg_neighbourhood_occupancy"])))

        story.append(_metric_table(str_data, col_widths=[3.4*inch, 4.1*inch]))
        story.append(Spacer(1, 14))

    # ── STR Comps table ───────────────────────────────────────
    if str_d and str_d.get("nearby_airbnbs"):
        comps = str_d["nearby_airbnbs"][:6]
        story.append(Paragraph("Nearby Airbnb Comps", styles["section_heading"]))
        comp_header = [["#", "Nightly Rate", "Occupancy", "Annual Revenue", "Status"]]
        comp_rows = []
        for i, c in enumerate(comps, 1):
            status = "✓ Active" if c.get("is_active_airbnb") else "Estimate"
            comp_rows.append([
                str(i),
                _cad(c.get("nightly_rate", 0)),
                _pct(c.get("occupancy_rate", 0)),
                _cad(c.get("annual_revenue", 0)),
                status,
            ])
        comp_table = Table(comp_header + comp_rows,
                           colWidths=[0.4*inch, 1.4*inch, 1.2*inch, 1.6*inch, 1.2*inch])
        comp_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), AIRREV_NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0), AIRREV_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [AIRREV_WHITE, AIRREV_LIGHT]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("LINEBELOW",     (0, 0), (-1, -2), 0.5, AIRREV_BORDER),
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(comp_table)
        story.append(Spacer(1, 14))

    # ── AI Insight / Summary ──────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=AIRREV_BORDER, spaceAfter=10))
    story.append(Paragraph("Investment Summary", styles["section_heading"]))

    insight_text = summary.get("ai_narrative") or summary.get("key_insight", "")
    if insight_text:
        story.append(Paragraph(insight_text, styles["body"]))

    # Recommendation badge
    rec_data = [[
        Paragraph("RECOMMENDATION", styles["label"]),
        Paragraph("CONFIDENCE", styles["label"]),
        Paragraph("BEST STRATEGY", styles["label"]),
    ], [
        Paragraph(rec, ParagraphStyle("rec", fontSize=16, fontName="Helvetica-Bold", textColor=rec_color)),
        Paragraph(summary.get("confidence", "—"), styles["value"]),
        Paragraph(summary.get("best_strategy", "—"), styles["value"]),
    ]]
    rec_table = Table(rec_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
    rec_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AIRREV_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.5, AIRREV_BORDER),
    ]))
    story.append(rec_table)

    # ── Footer ────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=AIRREV_BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generated by AirRev.io · {datetime.now().strftime('%B %d, %Y at %I:%M %p')} · "
        "This report is for informational purposes only and does not constitute financial advice. "
        "Always consult a licensed REALTOR® and financial advisor before making investment decisions.",
        styles["small"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ══════════════════════════════════════════════════════════════
# 2. CREB MONTHLY MARKET REPORT
# ══════════════════════════════════════════════════════════════

def generate_creb_report(data: Dict[str, Any]) -> bytes:
    """
    CREB-style monthly market summary PDF.
    Print-ready, email-ready.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = _build_styles()
    story = []

    month_name = datetime(data.get("report_year", 2025), data.get("report_month", 1), 1).strftime("%B %Y")
    community = data.get("community", "Calgary")
    market = data.get("market_summary", {})
    by_type = data.get("by_property_type", {})
    rental = data.get("rental_market", {})
    invest = data.get("investment_metrics", {})

    # ── Header ────────────────────────────────────────────────
    _header_bar(
        story, styles,
        title=f"{community} Real Estate Market Report",
        subtitle=f"{month_name} · Powered by AirRev.io · Data Source: CREB®",
        tag=f"Market Condition: {market.get('market_condition', '—')}",
        tag_color=AIRREV_AMBER,
    )

    # ── Market Overview KPIs ──────────────────────────────────
    kpis = [
        {"label": "Benchmark Price",    "value": _cad(market.get("benchmark_price", 0))},
        {"label": "YoY Price Change",   "value": _pct(market.get("benchmark_price_yoy_change", 0)), "positive": market.get("benchmark_price_yoy_change", 0) >= 0},
        {"label": "Total Sales",        "value": f"{market.get('total_sales', 0):,}"},
        {"label": "Months of Supply",   "value": str(market.get("months_of_supply", 0))},
        {"label": "Avg Days on Market", "value": str(market.get("days_on_market_avg", 0))},
    ]
    story.append(_kpi_row(kpis))
    story.append(Spacer(1, 16))

    # ── Narrative ─────────────────────────────────────────────
    if data.get("narrative"):
        story.append(Paragraph("Market Overview", styles["section_heading"]))
        story.append(Paragraph(data["narrative"], styles["body"]))
        story.append(Spacer(1, 10))

    # ── By Property Type ──────────────────────────────────────
    if by_type:
        story.append(Paragraph("Sales by Property Type", styles["section_heading"]))
        type_header = [["Property Type", "Sales", "Benchmark Price", "YoY Change", "Avg DOM"]]
        type_rows = []
        for ptype, stats in by_type.items():
            type_rows.append([
                ptype,
                f"{stats.get('sales', 0):,}",
                _cad(stats.get("benchmark_price", 0)),
                _pct(stats.get("yoy_change", 0)),
                f"{stats.get('dom', 0)} days",
            ])
        type_table = Table(
            type_header + type_rows,
            colWidths=[1.8*inch, 0.9*inch, 1.6*inch, 1.2*inch, 1.2*inch]
        )
        type_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), AIRREV_NAVY),
            ("TEXTCOLOR",     (0, 0), (-1, 0), AIRREV_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [AIRREV_WHITE, AIRREV_LIGHT]),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW",     (0, 0), (-1, -2), 0.5, AIRREV_BORDER),
        ]))
        story.append(type_table)
        story.append(Spacer(1, 14))

    # ── Rental Market ─────────────────────────────────────────
    if rental:
        story.append(Paragraph("Rental Market Snapshot", styles["section_heading"]))
        rental_data = [
            ("Average Rent — 1 Bedroom",  _cad(rental.get("avg_ltr_1bed", 0)) + "/mo"),
            ("Average Rent — 2 Bedroom",  _cad(rental.get("avg_ltr_2bed", 0)) + "/mo"),
            ("Average Rent — 3 Bedroom",  _cad(rental.get("avg_ltr_3bed", 0)) + "/mo"),
            ("Rental Vacancy Rate",        _pct(rental.get("vacancy_rate", 0))),
            ("YoY Rent Change",            _pct(rental.get("yoy_rent_change", 0))),
        ]
        story.append(_metric_table(rental_data, col_widths=[3.4*inch, 4.1*inch]))
        story.append(Spacer(1, 14))

    # ── Investment Metrics ────────────────────────────────────
    if invest:
        story.append(Paragraph("Investment Metrics", styles["section_heading"]))
        invest_data = [
            ("Average Cap Rate",         _pct(invest.get("avg_cap_rate", 0))),
            ("Average Gross Yield",      _pct(invest.get("avg_gross_yield", 0))),
            ("Price-to-Rent Ratio",      f"{invest.get('price_to_rent_ratio', 0):.1f}x"),
        ]
        story.append(_metric_table(invest_data, col_widths=[3.4*inch, 4.1*inch]))
        story.append(Spacer(1, 14))

    # ── Footer ────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=AIRREV_BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"AirRev.io · {community} Market Report · {month_name} · "
        "Data sourced from CREB® and public records. "
        "This report is for informational purposes only.",
        styles["small"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
