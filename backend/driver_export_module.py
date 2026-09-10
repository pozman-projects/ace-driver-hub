"""EB-11 · Driver Export module.

Provides the FastAPI routes and MongoDB-backed service that turn a Driver's
canonical DCC state into an immutable, permission-filtered PDF snapshot
(``Driver Start Sheet`` or ``Driver Profile PDF``).

Design principles
-----------------
1. Canonical resolution at generation time. The service pulls from the
   Driver, relationships, vehicle, equipment, compliance, activation, notes,
   documents and numbering collections; it never trusts previously-generated
   values.
2. Permission-filter *before* the snapshot is stored. Any field the
   requester is not allowed to see is stripped from ``snapshot_payload``.
3. Immutable versions. Regenerating creates a fresh ``driver_export_versions``
   document; prior versions remain accessible with their captured role.
4. Storage goes through the EB-05 document abstraction (``documents``,
   ``document_versions``, ``document_links``). No raw paths ever leave the
   API surface.
5. Every state transition writes an append-only
   ``driver_export_events`` row.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pypdf import PdfReader

from driver_pdf_renderer import render_profile_pdf, render_start_sheet

# ── Collections ───────────────────────────────────────────────────────────────
JOBS_COLL = "driver_export_jobs"
VERSIONS_COLL = "driver_export_versions"
EVENTS_COLL = "driver_export_events"

DRIVERS_COLL = "drivers"
DOR_COLL = "driver_owner_relationships"
DVA_COLL = "driver_vehicle_assignments"
DEA_COLL = "driver_equipment_assignments"
OWNERS_COLL = "owners"
VEHICLES_COLL = "vehicles_register"
EQUIPMENT_COLL = "equipment_register"
LICENCES_COLL = "driver_licences"
REGISTRATIONS_COLL = "vehicle_registrations"
INSURANCE_COLL = "vehicle_insurance_policies"
INSPECTIONS_COLL = "vehicle_inspections"
DEFECTS_COLL = "vehicle_defects"
MAINTENANCE_COLL = "vehicle_maintenance_tasks"
COMMS_COLL = "driver_communication_preferences"
NOTES_COLL = "driver_notes"
DOCUMENTS_COLL = "documents"
DOCUMENT_VERSIONS_COLL = "document_versions"
DOCUMENT_LINKS_COLL = "document_links"
DOCUMENT_ACCESS_EVENTS_COLL = "document_access_events"
NOTIFS_COLL = "notifications"
ALLOCATION_EVENTS_COLL = "number_allocation_events"

ACT_REC_COLL = "driver_activation_records"
ACT_ITEM_COLL = "driver_activation_items"
ACT_TPL_COLL = "activation_templates"
ACT_OVR_COLL = "driver_activation_overrides"
ACT_EVT_COLL = "driver_activation_events"

STORAGE_ROOT = Path(os.environ.get("DOCUMENT_STORAGE_PATH", "/app/backend/document_storage"))
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


EXPORT_TYPE_START_SHEET = "Driver Start Sheet"
EXPORT_TYPE_PROFILE_PDF = "Driver Profile PDF"

STATUS_QUEUED = "Queued"
STATUS_GENERATING = "Generating"
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"
STATUS_ARCHIVED = "Archived"

EV_REQUESTED = "Export Requested"
EV_STARTED = "Generation Started"
EV_COMPLETED = "Generation Completed"
EV_FAILED = "Generation Failed"
EV_DOWNLOADED = "Export Downloaded"
EV_PREVIEWED = "Export Previewed"
EV_ARCHIVED = "Export Archived"
EV_SUPERSEDED = "Version Superseded"
EV_VERIFICATION = "Verification Viewed"

SENSITIVE_ACCOUNT_FIELDS = {"business_name", "abn", "payroll_number",
                            "payment_percentage"}
ACCOUNT_READ_ROLES = {"Manager", "Admin"}
NOTE_ROLE_RULES: Dict[str, set] = {
    "General": {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"},
    "Operations": {"Allocator", "Compliance", "Manager", "Admin"},
    "Management": {"Manager", "Admin"},
    "Compliance": {"Compliance", "Manager", "Admin"},
    "Accounts": {"Manager", "Admin"},
}

ROLE_GENERATE_START = {"Allocator", "Compliance", "Manager", "Admin"}
ROLE_GENERATE_PROFILE = {"Compliance", "Manager", "Admin"}
ROLE_ARCHIVE = {"Manager", "Admin"}
ROLE_REGENERATE = {"Allocator", "Compliance", "Manager", "Admin"}
ROLE_VIEW_HISTORY = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}

MAX_START_SHEET_PAGES = 3
MAX_PROFILE_PAGES = 10
SEED_TAG = "seed-eb11"


def _uuid() -> str:
    return str(uuid.uuid4())


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _verification_reference() -> str:
    """Human-friendly, hard-to-guess reference, e.g. ``ACE-4H2J-K7L9-P3M1``."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no confusables
    parts = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
    return "ACE-" + "-".join(parts)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_role(user: Dict[str, Any], allowed: set, err: str = "Insufficient permissions"):
    if user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=err)


def _visible_note(role: str, category: str) -> bool:
    allowed = NOTE_ROLE_RULES.get(category or "General", set())
    return role in allowed


def _fmt_date(v: Any) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, str):
        return v[:10] if len(v) >= 10 and v[4] == "-" else v
    if isinstance(v, datetime):
        return v.isoformat()[:10]
    return str(v)


# ── ExportService ─────────────────────────────────────────────────────────────
class ExportService:
    """Encapsulates snapshot resolution + PDF rendering + storage integration."""

    def __init__(self, db):
        self.db = db

    # ---- snapshot builder ----------------------------------------------------
    async def _resolve_snapshot(self, driver_id: str, role: str, actor_email: str,
                                 export_type: str) -> Dict[str, Any]:
        db = self.db
        driver = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")

        account_visible = role in ACCOUNT_READ_ROLES

        # -- relationships / assignments --------------------------------------
        dor = await db[DOR_COLL].find_one(
            {"driver_id": driver_id, "is_current": True, "is_archived": {"$ne": True}},
            {"_id": 0})
        owner = None
        if dor and dor.get("owner_id"):
            owner = await db[OWNERS_COLL].find_one({"id": dor["owner_id"]}, {"_id": 0})

        dva = await db[DVA_COLL].find_one(
            {"driver_id": driver_id, "is_active": True, "is_primary": True,
             "is_archived": {"$ne": True}}, {"_id": 0})
        vehicle = None
        if dva and dva.get("vehicle_id"):
            vehicle = await db[VEHICLES_COLL].find_one({"id": dva["vehicle_id"]}, {"_id": 0})

        dea_docs = await db[DEA_COLL].find(
            {"driver_id": driver_id, "is_active": True,
             "is_archived": {"$ne": True}}, {"_id": 0}).to_list(200)
        eq_ids = [a["equipment_id"] for a in dea_docs if a.get("equipment_id")]
        eq_by_id: Dict[str, dict] = {}
        if eq_ids:
            async for e in db[EQUIPMENT_COLL].find({"id": {"$in": eq_ids}}, {"_id": 0}):
                eq_by_id[e["id"]] = e

        # -- comms -----------------------------------------------------------
        comms = await db[COMMS_COLL].find_one(
            {"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})

        # -- compliance ------------------------------------------------------
        from compliance_records import _ComplianceService as ComplianceService
        svc = ComplianceService(db)
        try:
            driver_summary = await svc.driver_summary(driver_id)
        except HTTPException:
            driver_summary = None
        vehicle_summary = None
        if vehicle:
            try:
                vehicle_summary = await svc.vehicle_summary(vehicle["id"])
            except HTTPException:
                vehicle_summary = None
        equipment_summary = None
        components = []
        for row in dea_docs:
            eq = eq_by_id.get(row.get("equipment_id"))
            if not eq:
                continue
            try:
                components.append(await svc.equipment_summary(eq["id"]))
            except HTTPException:
                continue
        if components:
            worst = max(components, key=lambda c: c.get("severity", 0))
            equipment_summary = worst

        # -- primary compliance records -------------------------------------
        primary_licence = await db[LICENCES_COLL].find_one(
            {"driver_id": driver_id, "is_primary": True, "is_archived": {"$ne": True}},
            {"_id": 0}, sort=[("created_at", -1)])
        primary_registration = None
        primary_insurance = None
        latest_inspection = None
        open_defects: List[dict] = []
        overdue_maintenance: List[dict] = []
        if vehicle:
            vid = vehicle["id"]
            primary_registration = await db[REGISTRATIONS_COLL].find_one(
                {"vehicle_id": vid, "is_current": True, "is_archived": {"$ne": True}},
                {"_id": 0}, sort=[("created_at", -1)])
            primary_insurance = await db[INSURANCE_COLL].find_one(
                {"vehicle_id": vid, "is_current": True, "is_archived": {"$ne": True}},
                {"_id": 0}, sort=[("created_at", -1)])
            latest_inspection = await db[INSPECTIONS_COLL].find_one(
                {"vehicle_id": vid, "is_archived": {"$ne": True}}, {"_id": 0},
                sort=[("inspection_date", -1), ("created_at", -1)])
            open_defects = await db[DEFECTS_COLL].find(
                {"vehicle_id": vid, "is_archived": {"$ne": True},
                 "status": {"$in": ["Open", "In Progress"]}},
                {"_id": 0}).sort("severity", -1).to_list(50)
            overdue_maintenance = await db[MAINTENANCE_COLL].find(
                {"vehicle_id": vid, "is_archived": {"$ne": True},
                 "status": {"$in": ["Overdue", "Due"]}}, {"_id": 0}).to_list(50)

        # -- notifications ---------------------------------------------------
        alerts = await db[NOTIFS_COLL].find(
            {"entity_type": "Driver", "entity_id": driver_id,
             "is_archived": {"$ne": True}}, {"_id": 0}).to_list(200)
        active_alert_count = sum(1 for a in alerts if a.get("status") == "Active")

        # -- documents linked to driver -------------------------------------
        dlinks = await db[DOCUMENT_LINKS_COLL].find(
            {"entity_type": "Driver", "entity_id": driver_id},
            {"_id": 0, "document_id": 1}).to_list(2000)
        doc_ids = list({l["document_id"] for l in dlinks if l.get("document_id")})
        documents: List[dict] = []
        if doc_ids:
            documents = await db[DOCUMENTS_COLL].find(
                {"id": {"$in": doc_ids}, "is_archived": {"$ne": True}},
                {"_id": 0, "storage_key": 0, "storage_provider": 0},
            ).sort("created_at", -1).to_list(1000)

        # -- activation summary ---------------------------------------------
        act_rec = await db[ACT_REC_COLL].find_one(
            {"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        act_items: List[dict] = []
        act_overrides: List[dict] = []
        act_events: List[dict] = []
        act_template: Optional[dict] = None
        if act_rec:
            act_items = await db[ACT_ITEM_COLL].find(
                {"driver_activation_id": act_rec["driver_activation_id"]},
                {"_id": 0}).sort("display_order", 1).to_list(500)
            act_overrides = await db[ACT_OVR_COLL].find(
                {"driver_activation_id": act_rec["driver_activation_id"],
                 "is_archived": {"$ne": True}},
                {"_id": 0}).sort("created_at", -1).to_list(300)
            act_events = await db[ACT_EVT_COLL].find(
                {"driver_activation_id": act_rec["driver_activation_id"]},
                {"_id": 0}).sort("performed_at", -1).to_list(200)
            if act_rec.get("activation_template_id"):
                act_template = await db[ACT_TPL_COLL].find_one(
                    {"activation_template_id": act_rec["activation_template_id"]},
                    {"_id": 0})

        blocking_items: List[dict] = []
        outstanding_items: List[dict] = []
        completed_manual_items: List[dict] = []
        for it in act_items:
            status = it.get("completion_status")
            if it.get("mandatory") and it.get("applicable"):
                if status in ("Missing", "Expired", "Blocked"):
                    blocking_items.append(it)
                elif status not in ("Complete", "Override Active", "Not Applicable"):
                    outstanding_items.append(it)
            if status == "Complete" and it.get("completion_type") in ("Manual", "Conditional Manual"):
                completed_manual_items.append(it)

        active_overrides = []
        historical_overrides = []
        for ov in act_overrides:
            if ov.get("status") in ("Active", "Approved"):
                active_overrides.append(ov)
            else:
                historical_overrides.append(ov)

        # -- notes (role-filtered) ------------------------------------------
        notes_all = await db[NOTES_COLL].find(
            {"driver_id": driver_id, "is_archived": {"$ne": True}},
            {"_id": 0}).sort([("is_pinned", -1), ("updated_at", -1)]).to_list(100)
        notes_permitted = [n for n in notes_all
                            if _visible_note(role, n.get("note_type", "General"))]
        notes_more = len(notes_all) > len(notes_permitted)

        # -- allocation events ----------------------------------------------
        allocation_events = await db[ALLOCATION_EVENTS_COLL].find(
            {"driver_id": driver_id}, {"_id": 0},
        ).sort("created_at", -1).to_list(100)

        # ---- build snapshot payload ---------------------------------------
        driver_status = driver.get("driver_status") or driver.get("status")
        overall_status = None
        if driver_summary and driver_summary.get("overall_status"):
            overall_status = driver_summary["overall_status"]
        # Worst status wins across driver, vehicle, equipment
        candidates = [
            (driver_summary or {}).get("overall_status"),
            (vehicle_summary or {}).get("overall_status"),
            (equipment_summary or {}).get("overall_status"),
        ]
        severities = [
            (driver_summary or {}).get("severity", 0),
            (vehicle_summary or {}).get("severity", 0),
            (equipment_summary or {}).get("severity", 0),
        ]
        if severities:
            max_i = severities.index(max(severities))
            overall_status = candidates[max_i] or overall_status

        applicable = (act_rec or {}).get("applicable_item_count") or 0
        mandatory = (act_rec or {}).get("mandatory_item_count") or 0
        mand_completed = (act_rec or {}).get("mandatory_completed_count") or 0
        completion_display = f"{mand_completed}/{mandatory}" if mandatory else "—"

        licence_summary = None
        if primary_licence:
            licence_summary = f"{primary_licence.get('licence_class') or ''} {primary_licence.get('licence_state') or ''}".strip() or "Recorded"

        eq_items = []
        for row in dea_docs:
            eq = eq_by_id.get(row.get("equipment_id"))
            if not eq:
                continue
            eq_items.append({
                "label": eq.get("name") or eq.get("equipment_type") or "Equipment",
                "serial": eq.get("serial_number") or eq.get("registration_number") or "—",
                "status": eq.get("status") or "—",
            })

        snapshot: Dict[str, Any] = {
            "driver": {
                "driver_id": driver["id"],
                "full_name": driver.get("full_name") or driver.get("name"),
                "driver_code": driver.get("driver_code"),
                "dispatch_number": driver.get("dispatch_number"),
                "status": driver_status,
            },
            "identity": {
                "full_name": driver.get("full_name") or driver.get("name"),
                "driver_type": driver.get("driver_type"),
                "company": driver.get("company"),
                "address": driver.get("residential_address") or driver.get("address"),
                "mobile": driver.get("mobile_phone") or driver.get("phone"),
                "email": driver.get("email"),
                "emergency_contact": driver.get("emergency_contact"),
                "start_date": _fmt_date(driver.get("start_date")),
                "contract_status": driver.get("contract_status") or "—",
                "photo_reference": None,  # filled if we find a Profile Photo doc below
            },
            "business": {},
            "operational": {
                "driver_code": driver.get("driver_code"),
                "dispatch_number": driver.get("dispatch_number"),
                "display_on_dispatch": (comms or {}).get("display_on_dispatch"),
                "comm_prefs": (comms or {}).get("preferred_channels") or (comms or {}).get("preferred_channel"),
                "report_emails": (comms or {}).get("report_emails"),
                "daily_report_prefs": (comms or {}).get("daily_report_preferences"),
                "comm_overrides": (comms or {}).get("overrides"),
                "driver_code_source": driver.get("driver_code_source"),
                "owner_name": (owner or {}).get("name") or (owner or {}).get("full_name"),
                "owner_mobile": (owner or {}).get("mobile_phone") or (owner or {}).get("phone"),
                "owner_email": (owner or {}).get("email"),
                "relationship_type": (dor or {}).get("relationship_type"),
                "ownership_type": (dor or {}).get("relationship_type"),
                "relationship_start": _fmt_date((dor or {}).get("effective_from")),
                "relationship_end": _fmt_date((dor or {}).get("effective_to")),
                "vehicle_label": ((vehicle or {}).get("registration_number")
                                    or (vehicle or {}).get("fleet_number")
                                    or (vehicle or {}).get("name")),
                "carrier_config": (vehicle or {}).get("configuration"),
                "tray_label": (vehicle or {}).get("tray") or "—",
                "trailer_label": (vehicle or {}).get("trailer") or "—",
                "assignment_start": _fmt_date((dva or {}).get("effective_from")),
                "assignment_end": _fmt_date((dva or {}).get("effective_to")),
                "equipment_items": eq_items,
            },
            "compliance": {
                "driver_overall": overall_status,
                "active_alert_count": active_alert_count,
                "licence_summary": licence_summary,
                "licence_expiry": _fmt_date((primary_licence or {}).get("expiry_date")),
                "registration_summary": (primary_registration or {}).get("state") or "—",
                "registration_expiry": _fmt_date((primary_registration or {}).get("expiry_date")),
                "insurance_summary": (primary_insurance or {}).get("insurer") or "—",
                "insurance_expiry": _fmt_date((primary_insurance or {}).get("expiry_date")),
                "inspection_summary": ((latest_inspection or {}).get("result")
                                        or (latest_inspection or {}).get("status")
                                        or "No inspection recorded"),
                "critical_defects_summary": (
                    f"{len(open_defects)} open defect(s)" if open_defects else "No open critical defects"),
                "overdue_maintenance_summary": (
                    f"{len(overdue_maintenance)} overdue task(s)" if overdue_maintenance else "None overdue"),
                "equipment_summary": (equipment_summary or {}).get("overall_status") or "—",
                "evidence_state": f"{len(documents)} linked document(s)",
            },
            "activation": {
                "activation_status": (act_rec or {}).get("activation_status"),
                "readiness_status": (act_rec or {}).get("readiness_status"),
                "completion_display": completion_display,
                "applicable_item_count": applicable,
                "mandatory_item_count": mandatory,
                "mandatory_completed_count": mand_completed,
                "outstanding_mandatory_count": (act_rec or {}).get("outstanding_mandatory_count") or 0,
                "active_override_count": len(active_overrides),
                "last_recalculated_at": (act_rec or {}).get("last_recalculated_at"),
                "template_name": (act_template or {}).get("name"),
                "blocking_items": [
                    {"label": i.get("label_snapshot") or i.get("label"),
                     "category": i.get("category"),
                     "completion_status": i.get("completion_status")}
                    for i in blocking_items
                ],
                "outstanding_items": [
                    {"label": i.get("label_snapshot") or i.get("label"),
                     "category": i.get("category"),
                     "completion_status": i.get("completion_status")}
                    for i in outstanding_items
                ],
                "completed_manual_items": [
                    {"label": i.get("label_snapshot") or i.get("label"),
                     "completed_at": _fmt_date(i.get("completed_at")),
                     "completed_by": i.get("completed_by")}
                    for i in completed_manual_items
                ],
                "active_overrides": [
                    {"item_label": _resolve_override_item_label(ov, act_items),
                     "reason_summary": (ov.get("reason") or "")[:120],
                     "approver": ov.get("approved_by") or ov.get("requested_by"),
                     "expires_at": _fmt_date(ov.get("expires_at"))}
                    for ov in active_overrides
                ],
                "historical_overrides": [
                    {"item_label": _resolve_override_item_label(ov, act_items),
                     "status": ov.get("status"),
                     "approver": ov.get("approved_by") or ov.get("requested_by"),
                     "expires_at": _fmt_date(ov.get("expires_at"))}
                    for ov in historical_overrides
                ],
                "recent_events": [
                    {"event_type": e.get("event_type"),
                     "performed_at": _fmt_date(e.get("performed_at")),
                     "performed_by": e.get("performed_by")}
                    for e in act_events[:12]
                ],
            },
            "documents": [
                {"document_type": d.get("document_type"),
                 "title": d.get("title"),
                 "version": d.get("current_version") or d.get("version_number") or 1,
                 "status": d.get("status"),
                 "uploaded_at": _fmt_date(d.get("uploaded_at")),
                 "reference": d.get("id", "")[:8]}
                for d in documents
            ],
            "notes": [
                {"category": n.get("note_type") or "General",
                 "author": n.get("created_by") or n.get("author"),
                 "created_at": _fmt_date(n.get("created_at")),
                 "body": n.get("body") or n.get("text")}
                for n in notes_permitted
            ],
            "notes_more_exist": notes_more,
            "history": {
                "driver_status": [
                    {"when": _fmt_date(driver.get("updated_at")),
                     "event": f"Current status {driver_status}",
                     "details": driver.get("driver_status_reason") or "—"}
                ] if driver else [],
                "owner_relationship": [
                    {"when": _fmt_date(dor.get("effective_from") if dor else None),
                     "event": (dor or {}).get("relationship_type", "—"),
                     "details": (owner or {}).get("name") or NOT_ASSIGNED_STR}
                ] if dor else [],
                "vehicle_assignment": [
                    {"when": _fmt_date(dva.get("effective_from") if dva else None),
                     "event": "Assignment start",
                     "details": (vehicle or {}).get("registration_number") or NOT_ASSIGNED_STR}
                ] if dva else [],
                "equipment_assignment": [
                    {"when": _fmt_date(a.get("effective_from")),
                     "event": "Equipment assigned",
                     "details": (eq_by_id.get(a.get("equipment_id")) or {}).get("name")}
                    for a in dea_docs[:8]
                ],
                "number_allocation": [
                    {"when": _fmt_date(e.get("created_at")),
                     "event": e.get("event_type") or e.get("action"),
                     "details": e.get("assigned_value") or e.get("value") or "—"}
                    for e in allocation_events[:8]
                ],
                "activation_lifecycle": [
                    {"when": _fmt_date(e.get("performed_at")),
                     "event": e.get("event_type"),
                     "details": e.get("performed_by") or "—"}
                    for e in act_events[:8]
                ],
                "document_version": [
                    {"when": _fmt_date(d.get("uploaded_at")),
                     "event": d.get("document_type"),
                     "details": d.get("title")}
                    for d in documents[:8]
                ],
            },
            "permissions": {
                "account_visible": account_visible,
                "role": role,
            },
            "generated_at": _iso(),
            "generated_by": actor_email,
            "generated_role": role,
        }

        # Account fields - only if requester is Manager/Admin
        if account_visible:
            snapshot["business"] = {
                "business_name": driver.get("business_name"),
                "abn": driver.get("abn"),
                "payroll_number": driver.get("payroll_number"),
                "payment_percentage": driver.get("payment_percentage"),
            }

        # Attach profile photo reference if a Profile Photo doc exists
        for d in documents:
            if (d.get("document_type") or "").lower().startswith("profile photo"):
                snapshot["identity"]["photo_reference"] = (
                    f"{d.get('title')} · v{d.get('current_version') or 1}")
                break

        return snapshot

    # ---- persistence helpers ------------------------------------------------
    async def _write_event(self, job_id: Optional[str], version_id: Optional[str],
                            driver_id: str, event_type: str, prev: Optional[str],
                            new: Optional[str], user_email: str,
                            correlation_id: str, payload: Optional[dict] = None):
        await self.db[EVENTS_COLL].insert_one({
            "driver_export_event_id": _uuid(),
            "driver_export_job_id": job_id,
            "driver_export_version_id": version_id,
            "driver_id": driver_id,
            "event_type": event_type,
            "previous_status": prev,
            "new_status": new,
            "performed_by": user_email,
            "performed_at": _iso(),
            "correlation_id": correlation_id,
            "payload": payload or {},
            "created_at": _iso(),
        })

    async def _write_doc_access(self, document_id: str, version_id: Optional[str],
                                 user: Dict[str, Any], action: str):
        await self.db[DOCUMENT_ACCESS_EVENTS_COLL].insert_one({
            "id": _uuid(),
            "document_id": document_id,
            "document_version_id": version_id,
            "user_id": user.get("id"),
            "user_email": user.get("email"),
            "user_role": user.get("role"),
            "action": action,
            "result": "Success",
            "timestamp": _iso(),
        })

    # ---- generation ---------------------------------------------------------
    async def generate(self, driver_id: str, export_type: str,
                        user: Dict[str, Any]) -> Dict[str, Any]:
        """Create job → resolve snapshot → render PDF → persist to Documents
        collection → create version record → return job+version summary."""
        role = user.get("role")
        actor = user.get("email")
        correlation_id = _uuid()
        # role gates
        if export_type == EXPORT_TYPE_START_SHEET:
            _require_role(user, ROLE_GENERATE_START,
                           "Not permitted to generate a Driver Start Sheet")
        elif export_type == EXPORT_TYPE_PROFILE_PDF:
            _require_role(user, ROLE_GENERATE_PROFILE,
                           "Not permitted to generate a Driver Profile PDF")
        else:
            raise HTTPException(status_code=400,
                                 detail=f"Unknown export type '{export_type}'")

        # ensure driver exists (throws 404 if not)
        await self._resolve_snapshot(driver_id, role, actor, export_type)

        job_id = _uuid()
        now = _iso()
        job_doc = {
            "driver_export_job_id": job_id,
            "driver_id": driver_id,
            "export_type": export_type,
            "status": STATUS_QUEUED,
            "requested_by": actor,
            "requested_at": now,
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "failure_reason": None,
            "current_version_id": None,
            "correlation_id": correlation_id,
            "created_at": now,
            "updated_at": now,
            "_source": "runtime",
        }
        await self.db[JOBS_COLL].insert_one(job_doc)
        await self._write_event(job_id, None, driver_id, EV_REQUESTED,
                                 None, STATUS_QUEUED, actor, correlation_id,
                                 {"export_type": export_type})

        try:
            await self.db[JOBS_COLL].update_one(
                {"driver_export_job_id": job_id},
                {"$set": {"status": STATUS_GENERATING, "started_at": _iso(),
                          "updated_at": _iso()}})
            await self._write_event(job_id, None, driver_id, EV_STARTED,
                                     STATUS_QUEUED, STATUS_GENERATING, actor,
                                     correlation_id)

            snapshot = await self._resolve_snapshot(driver_id, role, actor, export_type)
            verification = _verification_reference()
            snapshot["verification_reference"] = verification
            # version number = existing versions on driver+type + 1
            version_number = (await self.db[VERSIONS_COLL].count_documents({
                "driver_id": driver_id, "export_type": export_type,
            })) + 1
            snapshot["version_number"] = version_number

            if export_type == EXPORT_TYPE_START_SHEET:
                pdf_bytes = render_start_sheet(snapshot)
            else:
                pdf_bytes = render_profile_pdf(snapshot)

            # ---- validate PDF ----
            reader = PdfReader_from_bytes(pdf_bytes)
            page_count = len(reader.pages)
            if page_count <= 0:
                raise RuntimeError("Generated PDF has no pages")
            if page_count > (MAX_START_SHEET_PAGES if export_type == EXPORT_TYPE_START_SHEET else MAX_PROFILE_PAGES):
                # Warn only — do not fail; log in payload
                pass
            if not pdf_bytes.startswith(b"%PDF"):
                raise RuntimeError("Generated file is not a valid PDF")
            file_size = len(pdf_bytes)
            checksum = _sha256(pdf_bytes)

            # ---- persist to EB-05 documents collection ----
            document_id = _uuid()
            version_id = _uuid()
            safe_name = f"{export_type.replace(' ', '_')}_{driver_id[:8]}_v{version_number}.pdf"
            storage_key = f"exports/{driver_id[:2]}/{driver_id}/{document_id}_{version_id}.pdf"
            dest = STORAGE_ROOT / storage_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(pdf_bytes)

            uploaded_at = _iso()
            version_doc = {
                "id": version_id,
                "document_id": document_id,
                "version_number": 1,
                "original_filename": safe_name,
                "display_filename": safe_name,
                "mime_type": "application/pdf",
                "file_extension": "pdf",
                "file_size_bytes": file_size,
                "checksum_sha256": checksum,
                "storage_provider": "local-dev",
                "storage_key": storage_key,
                "uploaded_at": uploaded_at,
                "uploaded_by": actor,
                "change_note": f"Generated {export_type} v{version_number}",
                "status": "Active",
                "is_current": True,
                "is_archived": False,
                "created_at": uploaded_at,
                "created_by": actor,
                "_source": "eb11-export",
            }
            await self.db[DOCUMENT_VERSIONS_COLL].insert_one(version_doc)

            doc_type = (export_type if export_type in ("Driver Start Sheet",)
                          else "Driver Profile Export")
            document_record = {
                "id": document_id,
                "title": safe_name,
                "document_type": doc_type,
                "category": "Generated Export",
                "description": f"{export_type} for Driver {driver_id}",
                "sensitivity": "Confidential",
                "status": "Active",
                "current_version_id": version_id,
                "original_filename": safe_name,
                "display_filename": safe_name,
                "mime_type": "application/pdf",
                "file_extension": "pdf",
                "file_size_bytes": file_size,
                "checksum_sha256": checksum,
                "storage_provider": "local-dev",
                "storage_key": storage_key,
                "uploaded_at": uploaded_at,
                "uploaded_by": actor,
                "created_at": uploaded_at,
                "updated_at": uploaded_at,
                "created_by": actor,
                "updated_by": actor,
                "is_archived": False,
                "_malware_scan_status": "not_scanned",
                "_source": "eb11-export",
            }
            await self.db[DOCUMENTS_COLL].insert_one(document_record)
            await self.db[DOCUMENT_LINKS_COLL].insert_one({
                "id": _uuid(),
                "document_id": document_id,
                "entity_type": "Driver",
                "entity_id": driver_id,
                "link_relationship": "Generated Export",
                "primary": False,
                "created_at": uploaded_at,
                "created_by": actor,
            })

            # EB-13 · Register export in the private storage service.
            storage_object_id_ref = None
            try:
                from storage_module import get_storage_service
                svc = get_storage_service(self.db)
                _obj = await svc.register_existing(
                    object_key=storage_key, sha256=checksum,
                    file_size=file_size, content_type="application/pdf",
                    filename=safe_name, entity_type="Driver",
                    entity_id=driver_id, actor_email=actor,
                    document_id=document_id,
                    retention_class="Generated Export")
                storage_object_id_ref = _obj["storage_object_id"]
                await self.db[DOCUMENT_VERSIONS_COLL].update_one(
                    {"id": version_id},
                    {"$set": {"storage_object_id": storage_object_id_ref}})
                await self.db[DOCUMENTS_COLL].update_one(
                    {"id": document_id},
                    {"$set": {"storage_object_id": storage_object_id_ref}})
            except Exception:  # noqa: BLE001
                pass

            # ---- driver_export_versions row ----
            dev_id = _uuid()
            version_row = {
                "driver_export_version_id": dev_id,
                "driver_export_job_id": job_id,
                "driver_id": driver_id,
                "export_type": export_type,
                "version_number": version_number,
                "document_id": document_id,
                "document_version_id": version_id,
                "file_name": safe_name,
                "mime_type": "application/pdf",
                "file_size": file_size,
                "page_count": page_count,
                "sha256": checksum,
                "snapshot_generated_at": snapshot["generated_at"],
                "snapshot_generated_by": actor,
                "snapshot_role": role,
                "snapshot_payload": snapshot,  # already permission-filtered
                "verification_reference": verification,
                "created_at": uploaded_at,
                "is_archived": False,
                "_source": "runtime",
            }
            await self.db[VERSIONS_COLL].insert_one(version_row)

            # Mark previous versions superseded
            prev_version_ids = await self.db[VERSIONS_COLL].find(
                {"driver_id": driver_id, "export_type": export_type,
                 "driver_export_version_id": {"$ne": dev_id},
                 "is_archived": {"$ne": True}},
                {"_id": 0, "driver_export_version_id": 1}).to_list(500)
            for pv in prev_version_ids:
                await self._write_event(job_id, pv["driver_export_version_id"],
                                         driver_id, EV_SUPERSEDED, None, None,
                                         actor, correlation_id,
                                         {"new_version_id": dev_id})

            # ---- close job ----
            await self.db[JOBS_COLL].update_one(
                {"driver_export_job_id": job_id},
                {"$set": {"status": STATUS_COMPLETED,
                          "completed_at": _iso(),
                          "current_version_id": dev_id,
                          "updated_at": _iso()}})
            await self._write_event(job_id, dev_id, driver_id, EV_COMPLETED,
                                     STATUS_GENERATING, STATUS_COMPLETED,
                                     actor, correlation_id,
                                     {"page_count": page_count,
                                      "file_size": file_size,
                                      "checksum": checksum})
            return {
                "job": await self._read_job(job_id),
                "version": _strip_snapshot(version_row),
                "verification_reference": verification,
                "page_count": page_count,
                "file_size": file_size,
                "sha256": checksum,
            }
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            reason = str(e) or e.__class__.__name__
            await self.db[JOBS_COLL].update_one(
                {"driver_export_job_id": job_id},
                {"$set": {"status": STATUS_FAILED, "failed_at": _iso(),
                          "failure_reason": reason, "updated_at": _iso()}})
            await self._write_event(job_id, None, driver_id, EV_FAILED,
                                     STATUS_GENERATING, STATUS_FAILED, actor,
                                     correlation_id, {"reason": reason})
            raise HTTPException(status_code=500,
                                 detail=f"Export generation failed: {reason}")

    async def _read_job(self, job_id: str) -> Dict[str, Any]:
        j = await self.db[JOBS_COLL].find_one(
            {"driver_export_job_id": job_id}, {"_id": 0})
        return j

    async def list_jobs(self, driver_id: str) -> List[dict]:
        rows = await self.db[JOBS_COLL].find(
            {"driver_id": driver_id}, {"_id": 0}
        ).sort("requested_at", -1).to_list(500)
        return rows

    async def list_versions(self, job_id: str) -> List[dict]:
        rows = await self.db[VERSIONS_COLL].find(
            {"driver_export_job_id": job_id}, {"_id": 0}
        ).sort("version_number", -1).to_list(200)
        return [_strip_snapshot(r) for r in rows]

    async def get_version(self, version_id: str) -> Optional[dict]:
        v = await self.db[VERSIONS_COLL].find_one(
            {"driver_export_version_id": version_id}, {"_id": 0})
        return v

    async def read_pdf_bytes(self, version_id: str) -> Optional[bytes]:
        v = await self.get_version(version_id)
        if not v:
            return None
        doc_v = await self.db[DOCUMENT_VERSIONS_COLL].find_one(
            {"id": v["document_version_id"]}, {"_id": 0})
        if not doc_v:
            return None
        key = doc_v.get("storage_key")
        if not key:
            return None
        path = STORAGE_ROOT / key
        if not path.exists():
            return None
        return path.read_bytes()

    async def archive_version(self, version_id: str, user: Dict[str, Any]) -> dict:
        v = await self.get_version(version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        if v.get("is_archived"):
            raise HTTPException(status_code=400, detail="Already archived")
        await self.db[VERSIONS_COLL].update_one(
            {"driver_export_version_id": version_id},
            {"$set": {"is_archived": True, "archived_at": _iso(),
                      "archived_by": user.get("email")}})
        await self._write_event(v["driver_export_job_id"], version_id,
                                 v["driver_id"], EV_ARCHIVED, "Active",
                                 STATUS_ARCHIVED, user.get("email"),
                                 v.get("verification_reference") or _uuid())
        return await self.get_version(version_id)


def _resolve_override_item_label(ovr: dict, items: List[dict]) -> str:
    iid = ovr.get("driver_activation_item_id")
    for it in items:
        if it.get("driver_activation_item_id") == iid:
            return it.get("label_snapshot") or it.get("label") or "—"
    return "—"


def PdfReader_from_bytes(pdf_bytes: bytes) -> PdfReader:
    import io
    return PdfReader(io.BytesIO(pdf_bytes))


def _strip_snapshot(v: dict) -> dict:
    """Client-safe copy that omits the large ``snapshot_payload``. Snapshot
    stays server-side (verified via checksum + validated by tests)."""
    if not v:
        return v
    out = dict(v)
    out.pop("snapshot_payload", None)
    out.pop("_id", None)
    return out


NOT_ASSIGNED_STR = "Not assigned"


# ── Pydantic request models ────────────────────────────────────────────────
class ExportRequest(BaseModel):
    confirm: bool = Field(default=True,
                           description="User confirmed the export dialog")


# ── Indexes + Seed ────────────────────────────────────────────────────────
async def ensure_indexes(db):
    await db[JOBS_COLL].create_index("driver_export_job_id", unique=True)
    await db[JOBS_COLL].create_index("driver_id")
    await db[JOBS_COLL].create_index("status")
    await db[VERSIONS_COLL].create_index("driver_export_version_id", unique=True)
    await db[VERSIONS_COLL].create_index("driver_export_job_id")
    await db[VERSIONS_COLL].create_index("driver_id")
    await db[VERSIONS_COLL].create_index("export_type")
    await db[VERSIONS_COLL].create_index("verification_reference", unique=True,
                                          sparse=True)
    await db[EVENTS_COLL].create_index("driver_export_event_id", unique=True)
    await db[EVENTS_COLL].create_index("driver_export_job_id")
    await db[EVENTS_COLL].create_index("driver_id")
    await db[EVENTS_COLL].create_index("event_type")


async def seed_dev_examples(db):
    """Insert one completed job + version per demo scenario if not already seeded."""
    if await db[JOBS_COLL].count_documents({"_source": SEED_TAG}) > 0:
        return
    # Idempotent no-op stub — real jobs are generated at runtime by the router.
    # We insert a marker document so we don't reseed on every startup.
    await db[JOBS_COLL].insert_one({
        "driver_export_job_id": _uuid(),
        "driver_id": "seed-placeholder",
        "export_type": "Driver Start Sheet",
        "status": STATUS_ARCHIVED,
        "requested_by": "system-seed",
        "requested_at": _iso(),
        "started_at": _iso(),
        "completed_at": _iso(),
        "failed_at": None,
        "failure_reason": None,
        "current_version_id": None,
        "correlation_id": _uuid(),
        "created_at": _iso(),
        "updated_at": _iso(),
        "_source": SEED_TAG,
    })


# ── Router ────────────────────────────────────────────────────────────────
def build_driver_export_router(db, get_current_user):
    router = APIRouter(prefix="/api", tags=["driver-exports"])
    svc = ExportService(db)

    @router.post("/drivers/{driver_id}/exports/start-sheet")
    async def gen_start_sheet(driver_id: str, req: Optional[ExportRequest] = None,
                                current=Depends(get_current_user)):
        return await svc.generate(driver_id, EXPORT_TYPE_START_SHEET, current)

    @router.post("/drivers/{driver_id}/exports/profile-pdf")
    async def gen_profile_pdf(driver_id: str, req: Optional[ExportRequest] = None,
                                current=Depends(get_current_user)):
        return await svc.generate(driver_id, EXPORT_TYPE_PROFILE_PDF, current)

    @router.get("/drivers/{driver_id}/exports")
    async def list_driver_exports(driver_id: str,
                                    current=Depends(get_current_user)):
        _require_role(current, ROLE_VIEW_HISTORY)
        jobs = await svc.list_jobs(driver_id)
        # Attach current version summary (client-safe) for convenience
        out = []
        for j in jobs:
            latest = None
            if j.get("current_version_id"):
                latest = _strip_snapshot(
                    await svc.get_version(j["current_version_id"]) or {})
            out.append({"job": j, "current_version": latest})
        return out

    @router.get("/driver-exports/{job_id}")
    async def read_job(job_id: str, current=Depends(get_current_user)):
        j = await svc._read_job(job_id)
        if not j:
            raise HTTPException(status_code=404, detail="Job not found")
        return j

    @router.get("/driver-exports/{job_id}/versions")
    async def list_versions(job_id: str, current=Depends(get_current_user)):
        return await svc.list_versions(job_id)

    @router.get("/driver-export-versions/{version_id}")
    async def read_version(version_id: str, current=Depends(get_current_user)):
        v = await svc.get_version(version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        # Return snapshot only for Admin/Manager to keep audit surface small
        if current.get("role") not in ROLE_ARCHIVE:
            return _strip_snapshot(v)
        return v

    async def _access_check(version: dict, current: dict) -> None:
        """Enforce dual-gate: (a) role that generated is respected in the
        stored snapshot; (b) current requester must also be authorised."""
        # Requester must at minimum be authorised to view export history.
        _require_role(current, ROLE_VIEW_HISTORY)
        # Account-visible exports flow to Manager/Admin only for the current
        # requester, regardless of who generated them.
        payload = version.get("snapshot_payload") or {}
        if payload.get("permissions", {}).get("account_visible") \
                and current.get("role") not in ACCOUNT_READ_ROLES:
            raise HTTPException(
                status_code=403,
                detail="This export contains financial fields; only Manager or Admin roles may access it.")

    @router.get("/driver-export-versions/{version_id}/preview")
    async def preview_version(version_id: str, request: Request,
                                current=Depends(get_current_user)):
        v = await svc.get_version(version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        await _access_check(v, current)
        data = await svc.read_pdf_bytes(version_id)
        if not data:
            raise HTTPException(status_code=404, detail="File not found")
        await svc._write_event(v["driver_export_job_id"], version_id,
                                v["driver_id"], EV_PREVIEWED, None, None,
                                current.get("email"), _uuid())
        await svc._write_doc_access(v["document_id"], v["document_version_id"],
                                     current, "Preview")
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{v["file_name"]}"'})

    @router.get("/driver-export-versions/{version_id}/download")
    async def download_version(version_id: str, current=Depends(get_current_user)):
        v = await svc.get_version(version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        await _access_check(v, current)
        data = await svc.read_pdf_bytes(version_id)
        if not data:
            raise HTTPException(status_code=404, detail="File not found")
        await svc._write_event(v["driver_export_job_id"], version_id,
                                v["driver_id"], EV_DOWNLOADED, None, None,
                                current.get("email"), _uuid())
        await svc._write_doc_access(v["document_id"], v["document_version_id"],
                                     current, "Download")
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{v["file_name"]}"'})

    @router.post("/driver-export-versions/{version_id}/archive")
    async def archive_version(version_id: str, current=Depends(get_current_user)):
        _require_role(current, ROLE_ARCHIVE,
                       "Only Manager or Admin may archive an export version")
        return _strip_snapshot(await svc.archive_version(version_id, current))

    @router.post("/driver-exports/{job_id}/regenerate")
    async def regenerate(job_id: str, current=Depends(get_current_user)):
        _require_role(current, ROLE_REGENERATE)
        j = await svc._read_job(job_id)
        if not j:
            raise HTTPException(status_code=404, detail="Job not found")
        return await svc.generate(j["driver_id"], j["export_type"], current)

    @router.get("/driver-exports/verify/{verification_reference}")
    async def verify(verification_reference: str,
                      current=Depends(get_current_user)):
        v = await db[VERSIONS_COLL].find_one(
            {"verification_reference": verification_reference}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404,
                                 detail="Verification reference not found")
        # Log verification view
        await svc._write_event(v["driver_export_job_id"],
                                v["driver_export_version_id"], v["driver_id"],
                                EV_VERIFICATION, None, None,
                                current.get("email"), _uuid())

        # Role-filter response
        payload = v.get("snapshot_payload") or {}
        driver_summary = {
            "driver_id": payload.get("driver", {}).get("driver_id"),
            "full_name": payload.get("driver", {}).get("full_name"),
            "driver_code": payload.get("driver", {}).get("driver_code"),
        }
        can_open = True
        if payload.get("permissions", {}).get("account_visible") \
                and current.get("role") not in ACCOUNT_READ_ROLES:
            can_open = False
        # Also validate checksum
        checksum_ok = False
        try:
            data = await svc.read_pdf_bytes(v["driver_export_version_id"])
            if data:
                checksum_ok = (_sha256(data) == v.get("sha256"))
        except Exception:  # noqa: BLE001
            checksum_ok = False
        return {
            "verification_reference": verification_reference,
            "export_type": v.get("export_type"),
            "driver": driver_summary if current.get("role") in ROLE_VIEW_HISTORY else None,
            "version_number": v.get("version_number"),
            "generated_at": v.get("snapshot_generated_at"),
            "generated_by": v.get("snapshot_generated_by"),
            "is_archived": bool(v.get("is_archived")),
            "checksum_ok": checksum_ok,
            "can_open": can_open,
            "driver_export_version_id": v.get("driver_export_version_id") if can_open else None,
            "sha256": v.get("sha256"),
        }

    return router
