"""EB-11 · Driver Export PDF Renderer.

Server-side PDF generation via ReportLab (Platypus). Two renderers:
- ``render_start_sheet(snapshot)``: 2-3 page A4 portrait operational handover.
- ``render_profile_pdf(snapshot)``: 4-8 page A4 portrait management review.

Both accept a permission-filtered *snapshot dict* built by
``driver_export_service`` and return raw ``bytes``.

The renderers are deliberately layout-only: they never call the database and
never reason about permissions. Missing values in the snapshot render as
``Not recorded``, ``Not assigned`` or ``No accepted evidence`` — never blank.

Fonts: Helvetica-family only (bundled with ReportLab). All labels use plain
ASCII hyphens for reliable greyscale printability.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)


# ---- constants ---------------------------------------------------------------
PAGE_W, PAGE_H = A4
LEFT_MARGIN = 15 * mm
RIGHT_MARGIN = 15 * mm
TOP_MARGIN = 18 * mm
BOTTOM_MARGIN = 20 * mm
CONTENT_W = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN

BRAND_DARK = colors.HexColor("#0F172A")
BRAND_ACCENT = colors.HexColor("#0EA5E9")
BRAND_MUTED = colors.HexColor("#64748B")
BRAND_LIGHT = colors.HexColor("#F1F5F9")
BRAND_BORDER = colors.HexColor("#CBD5E1")
BRAND_WARN = colors.HexColor("#B45309")
BRAND_OK = colors.HexColor("#047857")
BRAND_BAD = colors.HexColor("#B91C1C")

NOT_RECORDED = "Not recorded"
NOT_ASSIGNED = "Not assigned"
NO_EVIDENCE = "No accepted evidence"
NOT_ASSESSED = "Not assessed"


# ---- styles ------------------------------------------------------------------
_base_styles = getSampleStyleSheet()

STYLES: Dict[str, ParagraphStyle] = {
    "h1": ParagraphStyle(
        "h1", parent=_base_styles["Title"], fontName="Helvetica-Bold",
        fontSize=15, leading=18, textColor=BRAND_DARK, alignment=0, spaceAfter=2,
    ),
    "h2": ParagraphStyle(
        "h2", parent=_base_styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, textColor=BRAND_DARK,
        spaceBefore=6, spaceAfter=3, keepWithNext=True,
    ),
    "body": ParagraphStyle(
        "body", parent=_base_styles["BodyText"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=BRAND_DARK,
    ),
    "muted": ParagraphStyle(
        "muted", parent=_base_styles["BodyText"], fontName="Helvetica",
        fontSize=7.5, leading=10, textColor=BRAND_MUTED,
    ),
    "label": ParagraphStyle(
        "label", parent=_base_styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=7.5, leading=9.5, textColor=BRAND_MUTED,
    ),
    "value": ParagraphStyle(
        "value", parent=_base_styles["BodyText"], fontName="Helvetica",
        fontSize=9, leading=11.5, textColor=BRAND_DARK,
    ),
    "note": ParagraphStyle(
        "note", parent=_base_styles["BodyText"], fontName="Helvetica-Oblique",
        fontSize=7.5, leading=10, textColor=BRAND_MUTED,
    ),
    "warn": ParagraphStyle(
        "warn", parent=_base_styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=8, leading=10.5, textColor=BRAND_WARN,
    ),
    "badge": ParagraphStyle(
        "badge", parent=_base_styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=7, leading=9, textColor=colors.white, alignment=1,
    ),
}


def _esc(v: Any) -> str:
    if v is None or v == "":
        return NOT_RECORDED
    text = str(v)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _p(text: Any, style: str = "value") -> Paragraph:
    return Paragraph(_esc(text) if text not in (None, "") else NOT_RECORDED,
                     STYLES[style])


def _label_value(label: str, value: Any) -> List[Any]:
    return [Paragraph(label.upper(), STYLES["label"]), _p(value)]


# ---- header/footer -----------------------------------------------------------
def _make_page_decorators(snapshot: Dict[str, Any], subtitle: str):
    driver_name = snapshot.get("driver", {}).get("full_name") or NOT_RECORDED
    driver_code = snapshot.get("driver", {}).get("driver_code") or "—"
    verif = snapshot.get("verification_reference") or "—"
    gen_at = snapshot.get("generated_at") or ""
    version_no = snapshot.get("version_number") or 1

    def header_footer(canvas, doc):
        canvas.saveState()
        # Header band
        canvas.setFillColor(BRAND_DARK)
        canvas.rect(0, PAGE_H - 14 * mm, PAGE_W, 14 * mm, fill=1, stroke=0)
        canvas.setFillColor(BRAND_ACCENT)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(LEFT_MARGIN, PAGE_H - 8 * mm, "ACE CAR FREIGHTERS")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(LEFT_MARGIN, PAGE_H - 11.5 * mm, subtitle)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#94A3B8"))
        right_text = f"{driver_name} · {driver_code}"
        canvas.drawRightString(PAGE_W - RIGHT_MARGIN, PAGE_H - 8 * mm, right_text)
        canvas.drawRightString(PAGE_W - RIGHT_MARGIN, PAGE_H - 11.5 * mm,
                                f"Generated {gen_at}")

        # Footer
        canvas.setStrokeColor(BRAND_BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(LEFT_MARGIN, 14 * mm, PAGE_W - RIGHT_MARGIN, 14 * mm)
        canvas.setFillColor(BRAND_MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(LEFT_MARGIN, 10 * mm,
                          f"Driver Command Centre · Version {version_no}")
        canvas.drawCentredString(PAGE_W / 2, 10 * mm,
                                  f"Verification: {verif}")
        canvas.drawRightString(PAGE_W - RIGHT_MARGIN, 10 * mm,
                                f"Page {doc.page}")
        canvas.setFont("Helvetica-Oblique", 6.5)
        canvas.drawString(LEFT_MARGIN, 6 * mm,
                          "Immutable historical snapshot. This document does not update the Driver Command Centre.")
        canvas.restoreState()
    return header_footer


# ---- table helpers -----------------------------------------------------------
def _kv_grid(pairs: List[List[Any]], cols: int = 2, col_widths: Optional[List[float]] = None) -> Table:
    """Render label/value pairs in `cols` columns. `pairs` is a list of
    [label, value] pairs; value may be a str or a Paragraph."""
    rows: List[List[Any]] = []
    cell_pairs = []
    for lbl, val in pairs:
        p_lbl = Paragraph(lbl.upper(), STYLES["label"])
        p_val = val if isinstance(val, Paragraph) else _p(val)
        cell_pairs.append([p_lbl, p_val])
    # arrange into rows of `cols`
    per_row = cols
    for i in range(0, len(cell_pairs), per_row):
        chunk = cell_pairs[i:i + per_row]
        while len(chunk) < per_row:
            chunk.append([Paragraph("", STYLES["label"]), Paragraph("", STYLES["value"])])
        flat = []
        for lbl, val in chunk:
            flat.extend([lbl, val])
        rows.append(flat)
    if col_widths is None:
        col_widths = []
        cell_w = CONTENT_W / (per_row * 2)
        for _ in range(per_row):
            col_widths.append(cell_w * 0.80)
            col_widths.append(cell_w * 1.20)
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
    ])
    t.setStyle(style)
    return t


def _status_badge(text: str, kind: str = "muted") -> Paragraph:
    color_map = {"ok": BRAND_OK, "warn": BRAND_WARN, "bad": BRAND_BAD,
                  "muted": BRAND_MUTED, "info": BRAND_ACCENT}
    c = color_map.get(kind, BRAND_MUTED)
    hex_str = f"#{int(c.red * 255):02X}{int(c.green * 255):02X}{int(c.blue * 255):02X}"
    return Paragraph(
        f'<font backColor="{hex_str}" color="#FFFFFF">&nbsp;{_esc(text)}&nbsp;</font>',
        STYLES["value"],
    )


STATUS_KIND_MAP = {
    "Compliant": "ok",
    "Ready": "ok",
    "Complete": "ok",
    "Active": "ok",
    "Activated": "ok",
    "Due Soon": "warn",
    "Under Review": "warn",
    "Override Active": "warn",
    "Ready with Override": "warn",
    "Incomplete": "warn",
    "Not Applicable": "muted",
    "Not Started": "muted",
    "Missing": "bad",
    "Expired": "bad",
    "Blocked": "bad",
    "Activation Blocked": "bad",
    "Deactivated": "bad",
    "Failed": "bad",
}


def _status_kind(status: Optional[str]) -> str:
    if not status:
        return "muted"
    return STATUS_KIND_MAP.get(status, "muted")


def _section_heading(title: str) -> Table:
    p = Paragraph(f'<font color="#0F172A"><b>{_esc(title)}</b></font>',
                   STYLES["h2"])
    t = Table([[p]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 1.2, BRAND_ACCENT),
    ]))
    return t


def _build_doc(subtitle: str, snapshot: Dict[str, Any]) -> tuple:
    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        title=subtitle,
        author="ACE Car Freighters — Driver Command Centre",
    )
    frame = Frame(
        LEFT_MARGIN, BOTTOM_MARGIN, CONTENT_W,
        PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    header_footer = _make_page_decorators(snapshot, subtitle)
    doc.addPageTemplates([PageTemplate(id="ace", frames=[frame],
                                        onPage=header_footer)])
    return buf, doc


# =============================================================================
# START SHEET
# =============================================================================
def render_start_sheet(snapshot: Dict[str, Any]) -> bytes:
    """Render the Driver Start Sheet (2-3 pages A4 portrait). Returns bytes."""
    buf, doc = _build_doc("Driver Start Sheet", snapshot)
    story: List[Any] = []
    story.append(Spacer(1, 4 * mm))

    driver = snapshot.get("driver", {})
    identity = snapshot.get("identity", {})
    business = snapshot.get("business", {})
    ops = snapshot.get("operational", {})
    compliance = snapshot.get("compliance", {})
    activation = snapshot.get("activation", {})
    documents = snapshot.get("documents", [])
    generated_by = snapshot.get("generated_by") or "—"

    # ---- Driver headline ---------------------------------------------------
    readiness = activation.get("readiness_status") or NOT_ASSESSED
    driver_status = driver.get("status") or NOT_RECORDED
    overall_compliance = compliance.get("driver_overall") or NOT_ASSESSED
    show_compliant = (overall_compliance == "Compliant" and
                       readiness != "Ready with Override")

    headline_data = [[
        Paragraph(f'<b>{_esc(driver.get("full_name"))}</b>',
                    ParagraphStyle("hn", parent=STYLES["h1"], fontSize=14)),
        _status_badge(driver_status, _status_kind(driver_status)),
        _status_badge(readiness, _status_kind(readiness)),
        _status_badge(overall_compliance if show_compliant
                       else (overall_compliance if overall_compliance != "Compliant"
                             else "Override Active"),
                       "ok" if show_compliant else _status_kind(overall_compliance)),
    ]]
    headline = Table(
        headline_data,
        colWidths=[CONTENT_W - 90 * mm, 30 * mm, 30 * mm, 30 * mm],
    )
    headline.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(headline)

    key_bar = _kv_grid([
        ["Driver Code", driver.get("driver_code")],
        ["Dispatch Number", driver.get("dispatch_number")],
        ["Generated By", generated_by],
        ["Version", f"v{snapshot.get('version_number', 1)}"],
    ], cols=2)
    story.append(key_bar)
    story.append(Spacer(1, 2 * mm))

    # ---- Section 1 · Identity ---------------------------------------------
    story.append(_section_heading("1 · Driver Identity"))
    story.append(_kv_grid([
        ["Full Name", identity.get("full_name")],
        ["Driver Type", identity.get("driver_type")],
        ["Residential Address", identity.get("address")],
        ["Company", identity.get("company")],
        ["Mobile", identity.get("mobile")],
        ["Start Date", identity.get("start_date")],
        ["Email", identity.get("email")],
        ["Emergency Contact", identity.get("emergency_contact")],
    ], cols=2))

    # ---- Section 2 · Business / Account -----------------------------------
    story.append(_section_heading("2 · Business & Account Setup"))
    if snapshot.get("permissions", {}).get("account_visible"):
        story.append(_kv_grid([
            ["Business Name", business.get("business_name")],
            ["ABN", business.get("abn")],
            ["Payroll Number", business.get("payroll_number")],
            ["Payment %", business.get("payment_percentage")],
        ], cols=2))
    else:
        story.append(Paragraph(
            "Restricted for your role. Ask a Manager or Admin to regenerate a Start Sheet with financial details visible.",
            STYLES["note"]))

    # ---- Section 3 · Operational Setup ------------------------------------
    story.append(_section_heading("3 · Operational Setup"))
    story.append(_kv_grid([
        ["Driver Code", ops.get("driver_code")],
        ["Dispatch Number", ops.get("dispatch_number")],
        ["Display on Dispatch", ops.get("display_on_dispatch")],
        ["Report Emails", ops.get("report_emails")],
        ["Communication Preferences", ops.get("comm_prefs")],
        ["Current Owner", ops.get("owner_name") or NOT_ASSIGNED],
        ["Ownership Type", ops.get("ownership_type") or NOT_ASSIGNED],
        ["Assignment Start", ops.get("assignment_start") or NOT_ASSIGNED],
        ["Assigned Vehicle", ops.get("vehicle_label") or NOT_ASSIGNED],
        ["Assigned Tray", ops.get("tray_label") or NOT_ASSIGNED],
        ["Assigned Trailer", ops.get("trailer_label") or NOT_ASSIGNED],
        ["Assignment End", ops.get("assignment_end") or "Current"],
    ], cols=2))

    # ---- Section 4 · Compliance -------------------------------------------
    story.append(_section_heading("4 · Compliance Summary"))
    comp_rows = [
        ["Overall Driver Compliance", overall_compliance],
        ["Licence", compliance.get("licence_summary")],
        ["Licence Expiry", compliance.get("licence_expiry")],
        ["Vehicle Registration", compliance.get("registration_summary")],
        ["Registration Expiry", compliance.get("registration_expiry")],
        ["Vehicle Insurance", compliance.get("insurance_summary")],
        ["Insurance Expiry", compliance.get("insurance_expiry")],
        ["Latest Inspection", compliance.get("inspection_summary")],
        ["Critical Defects", compliance.get("critical_defects_summary")],
        ["Overdue Maintenance", compliance.get("overdue_maintenance_summary")],
        ["Equipment Compliance", compliance.get("equipment_summary")],
    ]
    story.append(_kv_grid(comp_rows, cols=2))
    story.append(Paragraph(
        "Worst Status Wins: the overall Driver compliance status inherits the most severe status "
        "from the Driver Licence, assigned Vehicle records, and any assigned Equipment.",
        STYLES["note"]))

    # ---- Section 5 · Activation Readiness ---------------------------------
    story.append(PageBreak())
    story.append(_section_heading("5 · Activation Readiness"))
    story.append(_kv_grid([
        ["Activation Status", activation.get("activation_status")],
        ["Readiness", activation.get("readiness_status")],
        ["Completion", activation.get("completion_display") or NOT_ASSESSED],
        ["Mandatory Completed", activation.get("mandatory_completed_count")],
        ["Outstanding Mandatory", activation.get("outstanding_mandatory_count")],
        ["Active Overrides", activation.get("active_override_count")],
        ["Last Recalculated", activation.get("last_recalculated_at")],
        ["Template", activation.get("template_name")],
    ], cols=2))

    blockers = activation.get("blocking_items") or []
    if blockers:
        story.append(Paragraph("Blocking items", STYLES["h2"]))
        rows = [[
            Paragraph("<b>Item</b>", STYLES["label"]),
            Paragraph("<b>Category</b>", STYLES["label"]),
            Paragraph("<b>Status</b>", STYLES["label"]),
        ]]
        for b in blockers[:20]:
            rows.append([_p(b.get("label")), _p(b.get("category")),
                          _p(b.get("completion_status"))])
        t = Table(rows, colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.25, CONTENT_W * 0.20])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No blocking items.", STYLES["muted"]))

    outstanding = activation.get("outstanding_items") or []
    if outstanding:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Outstanding mandatory items", STYLES["h2"]))
        rows = [[
            Paragraph("<b>Item</b>", STYLES["label"]),
            Paragraph("<b>Status</b>", STYLES["label"]),
        ]]
        for o in outstanding[:20]:
            rows.append([_p(o.get("label")), _p(o.get("completion_status"))])
        t = Table(rows, colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    active_overrides = activation.get("active_overrides") or []
    if active_overrides:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Active overrides", STYLES["h2"]))
        rows = [[
            Paragraph("<b>Item</b>", STYLES["label"]),
            Paragraph("<b>Reason</b>", STYLES["label"]),
            Paragraph("<b>Approver</b>", STYLES["label"]),
            Paragraph("<b>Expiry</b>", STYLES["label"]),
        ]]
        for ov in active_overrides[:15]:
            rows.append([_p(ov.get("item_label")), _p(ov.get("reason_summary")),
                          _p(ov.get("approver")), _p(ov.get("expires_at"))])
        t = Table(rows, colWidths=[CONTENT_W * 0.35, CONTENT_W * 0.30,
                                     CONTENT_W * 0.20, CONTENT_W * 0.15])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    # ---- Section 6 · Documents --------------------------------------------
    story.append(Spacer(1, 3 * mm))
    story.append(_section_heading("6 · Documents & Evidence"))
    if documents:
        rows = [[
            Paragraph("<b>Type</b>", STYLES["label"]),
            Paragraph("<b>Title</b>", STYLES["label"]),
            Paragraph("<b>Status</b>", STYLES["label"]),
            Paragraph("<b>Reference</b>", STYLES["label"]),
        ]]
        for d in documents[:12]:
            rows.append([_p(d.get("document_type")), _p(d.get("title")),
                          _p(d.get("status") or NO_EVIDENCE),
                          _p(d.get("reference") or "—")])
        if len(documents) > 12:
            rows.append([
                Paragraph(f'<i>{len(documents) - 12} more documents in DCC</i>',
                           STYLES["note"]), "", "", ""])
        t = Table(rows, colWidths=[CONTENT_W * 0.25, CONTENT_W * 0.35,
                                     CONTENT_W * 0.20, CONTENT_W * 0.20])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(NO_EVIDENCE, STYLES["muted"]))

    # ---- Section 7 · Manual handover --------------------------------------
    story.append(Spacer(1, 4 * mm))
    signoff_block: List[Any] = [
        _section_heading("7 · Manual Handover Confirmation"),
    ]
    signoff_rows = [[
        Paragraph("Driver signature", STYLES["label"]),
        Paragraph("Driver date", STYLES["label"]),
        Paragraph("Allocator / Manager signature", STYLES["label"]),
        Paragraph("Allocator / Manager date", STYLES["label"]),
    ], [
        Paragraph("&nbsp;", STYLES["value"]),
        Paragraph("&nbsp;", STYLES["value"]),
        Paragraph("&nbsp;", STYLES["value"]),
        Paragraph("&nbsp;", STYLES["value"]),
    ]]
    signoff = Table(signoff_rows, colWidths=[CONTENT_W / 4] * 4, rowHeights=[10, 40])
    signoff.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    signoff_block.append(signoff)
    signoff_block.append(Spacer(1, 3 * mm))
    signoff_block.append(Paragraph("Comments:", STYLES["label"]))
    comments = Table([[""]], colWidths=[CONTENT_W], rowHeights=[26])
    comments.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BRAND_BORDER),
    ]))
    signoff_block.append(comments)
    signoff_block.append(Spacer(1, 2 * mm))
    signoff_block.append(Paragraph(
        "Printed signatures on this Start Sheet are not automatically recorded in the Driver Command Centre. "
        "Complete the corresponding checklist items in DCC to update the canonical activation record.",
        STYLES["note"]))
    story.append(KeepTogether(signoff_block))

    doc.build(story)
    return buf.getvalue()


# =============================================================================
# PROFILE PDF
# =============================================================================
def render_profile_pdf(snapshot: Dict[str, Any]) -> bytes:
    """Render the full Driver Profile PDF (4-8 pages A4 portrait)."""
    buf, doc = _build_doc("Driver Command Centre Profile", snapshot)
    story: List[Any] = []
    story.append(Spacer(1, 4 * mm))

    driver = snapshot.get("driver", {})
    identity = snapshot.get("identity", {})
    business = snapshot.get("business", {})
    ops = snapshot.get("operational", {})
    compliance = snapshot.get("compliance", {})
    activation = snapshot.get("activation", {})
    documents = snapshot.get("documents", [])
    notes = snapshot.get("notes", [])
    history = snapshot.get("history", {})
    perms = snapshot.get("permissions", {})

    readiness = activation.get("readiness_status") or NOT_ASSESSED
    overall = compliance.get("driver_overall") or NOT_ASSESSED
    active_alerts = compliance.get("active_alert_count") or 0

    # ── Summary card ──────────────────────────────────────────────────────
    summary_data = [[
        Paragraph(f'<b>{_esc(driver.get("full_name"))}</b>',
                    ParagraphStyle("hn", parent=STYLES["h1"], fontSize=14)),
        _status_badge(driver.get("status") or NOT_RECORDED,
                       _status_kind(driver.get("status"))),
        _status_badge(readiness, _status_kind(readiness)),
        _status_badge(overall, _status_kind(overall)),
    ]]
    summary = Table(summary_data,
                     colWidths=[CONTENT_W - 90 * mm, 30 * mm, 30 * mm, 30 * mm])
    summary.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary)

    top_stats = _kv_grid([
        ["Driver Code", driver.get("driver_code")],
        ["Dispatch Number", driver.get("dispatch_number")],
        ["Company", identity.get("company")],
        ["Active Alerts", active_alerts],
        ["Generated By", snapshot.get("generated_by")],
        ["Version", f"v{snapshot.get('version_number', 1)}"],
    ], cols=3)
    story.append(top_stats)

    # ── Driver Details ────────────────────────────────────────────────────
    story.append(_section_heading("Driver Details"))
    story.append(_kv_grid([
        ["Residential Address", identity.get("address")],
        ["Mobile", identity.get("mobile")],
        ["Email", identity.get("email")],
        ["Emergency Contact", identity.get("emergency_contact")],
        ["Profile Photo", identity.get("photo_reference") or NOT_RECORDED],
        ["Driver Type", identity.get("driver_type")],
    ], cols=2))

    # ── Account (role-gated) ──────────────────────────────────────────────
    story.append(_section_heading("Account Details"))
    if perms.get("account_visible"):
        story.append(_kv_grid([
            ["Business Name", business.get("business_name")],
            ["ABN", business.get("abn")],
            ["Payroll Number", business.get("payroll_number")],
            ["Payment %", business.get("payment_percentage")],
        ], cols=2))
    else:
        story.append(Paragraph(
            "Restricted for your role. Financial fields (Business Name, ABN, Payroll, Payment %) "
            "are excluded from this export.", STYLES["note"]))

    # ── Setup ─────────────────────────────────────────────────────────────
    story.append(_section_heading("Driver Setup"))
    story.append(_kv_grid([
        ["Start Date", identity.get("start_date")],
        ["Status", driver.get("status")],
        ["Contract Status", identity.get("contract_status")],
        ["Driver Code Source", ops.get("driver_code_source") or NOT_RECORDED],
        ["Driver Code", ops.get("driver_code")],
        ["Dispatch Number", ops.get("dispatch_number")],
    ], cols=2))

    # ── Communication & Integration ───────────────────────────────────────
    story.append(_section_heading("Communication & Integration"))
    story.append(_kv_grid([
        ["Report Emails", ops.get("report_emails")],
        ["Daily Report Preferences", ops.get("daily_report_prefs")],
        ["Display on Dispatch", ops.get("display_on_dispatch")],
        ["Communication Overrides", ops.get("comm_overrides") or "None"],
    ], cols=2))

    # ── Car Carrier & Equipment ───────────────────────────────────────────
    story.append(_section_heading("Car Carrier & Equipment"))
    story.append(_kv_grid([
        ["Current Vehicle", ops.get("vehicle_label") or NOT_ASSIGNED],
        ["Carrier Configuration", ops.get("carrier_config") or NOT_ASSIGNED],
        ["Tray", ops.get("tray_label") or NOT_ASSIGNED],
        ["Trailer", ops.get("trailer_label") or NOT_ASSIGNED],
        ["Assignment Start", ops.get("assignment_start") or NOT_ASSIGNED],
        ["Assignment End", ops.get("assignment_end") or "Current"],
    ], cols=2))
    equipment_list = ops.get("equipment_items") or []
    if equipment_list:
        rows = [[Paragraph("<b>Equipment</b>", STYLES["label"]),
                  Paragraph("<b>Serial / Ref</b>", STYLES["label"]),
                  Paragraph("<b>Status</b>", STYLES["label"])]]
        for eq in equipment_list[:20]:
            rows.append([_p(eq.get("label")), _p(eq.get("serial")),
                          _p(eq.get("status"))])
        t = Table(rows, colWidths=[CONTENT_W * 0.50, CONTENT_W * 0.30,
                                     CONTENT_W * 0.20])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    # ── Owner ─────────────────────────────────────────────────────────────
    story.append(_section_heading("Owner Details"))
    story.append(_kv_grid([
        ["Owner Name", ops.get("owner_name") or NOT_ASSIGNED],
        ["Relationship Type", ops.get("relationship_type") or NOT_ASSIGNED],
        ["Owner Mobile", ops.get("owner_mobile") or NOT_RECORDED],
        ["Owner Email", ops.get("owner_email") or NOT_RECORDED],
        ["Relationship Start", ops.get("relationship_start") or NOT_ASSIGNED],
        ["Relationship End", ops.get("relationship_end") or "Current"],
    ], cols=2))

    # ── Activation ────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_heading("Activation Checklist Summary"))
    story.append(_kv_grid([
        ["Status", activation.get("activation_status")],
        ["Readiness", readiness],
        ["Completion", activation.get("completion_display")],
        ["Applicable Items", activation.get("applicable_item_count")],
        ["Mandatory Items", activation.get("mandatory_item_count")],
        ["Mandatory Completed", activation.get("mandatory_completed_count")],
        ["Outstanding", activation.get("outstanding_mandatory_count")],
        ["Active Overrides", activation.get("active_override_count")],
    ], cols=2))

    def _short_table(title: str, items: List[dict], columns: List[tuple],
                      cap: int = 15) -> None:
        story.append(Paragraph(title, STYLES["h2"]))
        if not items:
            story.append(Paragraph("None.", STYLES["muted"]))
            return
        header = [Paragraph(f"<b>{c[1]}</b>", STYLES["label"]) for c in columns]
        rows = [header]
        for it in items[:cap]:
            rows.append([_p(it.get(c[0])) for c in columns])
        widths = [CONTENT_W * (1.0 / len(columns))] * len(columns)
        t = Table(rows, colWidths=widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        if len(items) > cap:
            story.append(Paragraph(
                f"{len(items) - cap} more items exist in the Driver Command Centre.",
                STYLES["note"]))

    _short_table("Blocking items", activation.get("blocking_items") or [],
                  [("label", "Item"), ("category", "Category"),
                   ("completion_status", "Status")])
    story.append(Spacer(1, 2 * mm))
    _short_table("Outstanding items", activation.get("outstanding_items") or [],
                  [("label", "Item"), ("category", "Category"),
                   ("completion_status", "Status")])
    story.append(Spacer(1, 2 * mm))
    _short_table("Completed manual items",
                  activation.get("completed_manual_items") or [],
                  [("label", "Item"), ("completed_at", "Completed"),
                   ("completed_by", "By")], cap=10)
    story.append(Spacer(1, 2 * mm))
    _short_table("Active overrides", activation.get("active_overrides") or [],
                  [("item_label", "Item"), ("reason_summary", "Reason"),
                   ("approver", "Approver"), ("expires_at", "Expires")])
    _short_table("Historical overrides",
                  activation.get("historical_overrides") or [],
                  [("item_label", "Item"), ("status", "Status"),
                   ("approver", "Approver"), ("expires_at", "Expiry")], cap=8)
    story.append(Spacer(1, 2 * mm))
    _short_table("Recent activation events",
                  activation.get("recent_events") or [],
                  [("event_type", "Event"), ("performed_at", "When"),
                   ("performed_by", "By")], cap=12)

    # ── Compliance ────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_section_heading("Compliance Intelligence"))
    comp_rows = [
        ["Overall Driver Compliance", overall],
        ["Driver Licence", compliance.get("licence_summary")],
        ["Licence Expiry", compliance.get("licence_expiry")],
        ["Vehicle Registration", compliance.get("registration_summary")],
        ["Registration Expiry", compliance.get("registration_expiry")],
        ["Vehicle Insurance", compliance.get("insurance_summary")],
        ["Insurance Expiry", compliance.get("insurance_expiry")],
        ["Vehicle Inspection", compliance.get("inspection_summary")],
        ["Vehicle Defects", compliance.get("critical_defects_summary")],
        ["Maintenance", compliance.get("overdue_maintenance_summary")],
        ["Equipment Compliance", compliance.get("equipment_summary")],
        ["Evidence State", compliance.get("evidence_state")],
        ["Active Alerts", active_alerts],
    ]
    story.append(_kv_grid(comp_rows, cols=2))

    # ── Documents ─────────────────────────────────────────────────────────
    story.append(_section_heading("Documents, Passes & Photos"))
    if documents:
        rows = [[Paragraph("<b>Type</b>", STYLES["label"]),
                  Paragraph("<b>Title</b>", STYLES["label"]),
                  Paragraph("<b>Version</b>", STYLES["label"]),
                  Paragraph("<b>Status</b>", STYLES["label"]),
                  Paragraph("<b>Uploaded</b>", STYLES["label"])]]
        for d in documents[:30]:
            rows.append([_p(d.get("document_type")), _p(d.get("title")),
                          _p(d.get("version")), _p(d.get("status")),
                          _p(d.get("uploaded_at"))])
        t = Table(rows, colWidths=[CONTENT_W * 0.22, CONTENT_W * 0.32,
                                     CONTENT_W * 0.10, CONTENT_W * 0.16,
                                     CONTENT_W * 0.20])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(NO_EVIDENCE, STYLES["muted"]))

    # ── Notes (role-filtered by service) ──────────────────────────────────
    story.append(_section_heading("Notes"))
    if notes:
        rows = [[Paragraph("<b>Category</b>", STYLES["label"]),
                  Paragraph("<b>Author</b>", STYLES["label"]),
                  Paragraph("<b>When</b>", STYLES["label"]),
                  Paragraph("<b>Note</b>", STYLES["label"])]]
        for n in notes[:15]:
            body_text = (n.get("body") or "")[:600]
            rows.append([_p(n.get("category")), _p(n.get("author")),
                          _p(n.get("created_at")), _p(body_text)])
        t = Table(rows, colWidths=[CONTENT_W * 0.15, CONTENT_W * 0.20,
                                     CONTENT_W * 0.15, CONTENT_W * 0.50])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        if snapshot.get("notes_more_exist"):
            story.append(Paragraph(
                "Additional notes exist in the Driver Command Centre and are not shown here.",
                STYLES["note"]))
    else:
        story.append(Paragraph("No permitted notes for this export.",
                                STYLES["muted"]))

    # ── History summary ───────────────────────────────────────────────────
    story.append(_section_heading("History Summary"))
    hist_categories = [
        ("Driver Status", history.get("driver_status") or []),
        ("Owner Relationship", history.get("owner_relationship") or []),
        ("Vehicle Assignment", history.get("vehicle_assignment") or []),
        ("Equipment Assignments", history.get("equipment_assignment") or []),
        ("Number Allocations", history.get("number_allocation") or []),
        ("Activation Lifecycle", history.get("activation_lifecycle") or []),
        ("Document Versions", history.get("document_version") or []),
    ]
    for label, items in hist_categories:
        story.append(Paragraph(label, STYLES["h2"]))
        if not items:
            story.append(Paragraph("No history recorded.", STYLES["muted"]))
            continue
        rows = [[Paragraph("<b>When</b>", STYLES["label"]),
                  Paragraph("<b>Event</b>", STYLES["label"]),
                  Paragraph("<b>Details</b>", STYLES["label"])]]
        for h in items[:8]:
            rows.append([_p(h.get("when")), _p(h.get("event")),
                          _p(h.get("details"))])
        t = Table(rows, colWidths=[CONTENT_W * 0.20, CONTENT_W * 0.25,
                                     CONTENT_W * 0.55])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        story.append(Spacer(1, 1.5 * mm))

    story.append(Paragraph(
        "This export is an immutable snapshot of the Driver Command Centre "
        f"at {snapshot.get('generated_at')}. Any later changes in DCC will not appear here.",
        STYLES["note"]))

    doc.build(story)
    return buf.getvalue()
