"""EB-09 · Final Three-Row DCC Driver Profile — aggregator + supporting canonicals.

This module DOES NOT own operational data. It:
  1. Aggregates canonical Driver + relationships + compliance + documents + alerts +
     activation summary + notes into ONE read-only endpoint for the front-end.
  2. Owns two brand-new (previously missing) canonical collections:
        - driver_communication_preferences  (one active row per driver)
        - driver_notes / driver_note_versions (append-only versioning)
  3. Exposes an activation-summary ADAPTER that computes readiness truthfully from
     existing onboarding + compliance + documents. It never falsifies completion.

Business rules
--------------
* Compliance modules monitor data. This module also monitors — it does not update
  any operational source through the aggregator.
* Sensitive Account Details fields (business_name, abn, payroll_number,
  payment_percentage) are STRIPPED from the aggregator response for
  ReadOnly / Allocator / Compliance roles.
* Notes categories `Compliance` and `Accounts` are BACKEND-enforced:
    - Compliance -> Compliance / Manager / Admin
    - Accounts   -> Manager / Admin
  Restricted notes are removed from the response and cannot be created / edited
  by unauthorised roles.
* Communication preferences store OVERRIDES only. Canonical driver.email and
  canonical owner.email remain the source of truth.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

# ─── Constants ────────────────────────────────────────────────────────────────
COMMS_COLL = "driver_communication_preferences"
NOTES_COLL = "driver_notes"
NOTE_VERSIONS_COLL = "driver_note_versions"

DRIVERS_COLL = "drivers"
OWNERS_COLL = "owners"
VEHICLES_COLL = "vehicles_register"
EQUIPMENT_COLL = "equipment_register"

DOR_COLL = "driver_owner_relationships"
DVA_COLL = "driver_vehicle_assignments"
DEA_COLL = "driver_equipment_assignments"

LICENCES_COLL = "driver_licences"
REGISTRATIONS_COLL = "vehicle_registrations"
INSURANCE_COLL = "vehicle_insurance_policies"
INSPECTIONS_COLL = "vehicle_inspections"
DEFECTS_COLL = "vehicle_defects"
MAINTENANCE_COLL = "vehicle_maintenance_tasks"
EQUIPMENT_COMPLIANCE_COLL = "equipment_compliance_records"

DOCUMENTS_COLL = "documents"
DOCUMENT_LINKS_COLL = "document_links"

NOTIFS_COLL = "notifications"
ALLOCATION_EVENTS_COLL = "number_allocation_events"

ONBOARDING_COLL = "onboarding"

SENSITIVE_ACCOUNT_FIELDS = {"business_name", "abn", "payroll_number", "payment_percentage"}
ACCOUNT_READ_ROLES = {"Manager", "Admin"}

NOTE_CATEGORIES = ["General", "Operations", "Compliance", "Accounts", "Incident", "Management", "Other"]
NOTE_STATUSES = ["Active", "Superseded", "Archived"]

CATEGORY_ROLE_GATE = {
    "Compliance": {"Compliance", "Manager", "Admin"},
    "Accounts": {"Manager", "Admin"},
}

SEED_TAG = "seed-eb09"


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _visible_note(role: str, category: str) -> bool:
    gate = CATEGORY_ROLE_GATE.get(category)
    return True if not gate else role in gate


def _require_role(current: dict, allowed: set, err="Insufficient permissions"):
    if current.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=err)


def _strip_account_fields(driver: Optional[dict], role: str) -> Optional[dict]:
    if not driver:
        return driver
    if role in ACCOUNT_READ_ROLES:
        return driver
    out = dict(driver)
    for f in SENSITIVE_ACCOUNT_FIELDS:
        out.pop(f, None)
    return out


# ─── Pydantic models ──────────────────────────────────────────────────────────
class CommsPreferencesPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    owner_report_email_override: Optional[str] = None
    driver_report_email_override: Optional[str] = None
    send_daily_report_owner: bool = False
    send_daily_report_driver: bool = False
    display_on_dispatch: bool = True


class NoteCreatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    note_type: str = Field(default="General")
    title: Optional[str] = None
    content: str = Field(min_length=1)
    is_pinned: bool = False


class NoteUpdatePayload(BaseModel):
    """Editing a note produces a NEW version. Title/content required."""
    model_config = ConfigDict(extra="ignore")
    note_type: Optional[str] = None
    title: Optional[str] = None
    content: str = Field(min_length=1)
    is_pinned: Optional[bool] = None


# ─── Startup ──────────────────────────────────────────────────────────────────
async def ensure_indexes(db):
    await db[COMMS_COLL].create_index("communication_preference_id", unique=True)
    await db[COMMS_COLL].create_index("driver_id")
    await db[NOTES_COLL].create_index("driver_note_id", unique=True)
    await db[NOTES_COLL].create_index([("driver_id", 1), ("is_archived", 1), ("is_pinned", -1), ("updated_at", -1)])
    await db[NOTE_VERSIONS_COLL].create_index("driver_note_version_id", unique=True)
    await db[NOTE_VERSIONS_COLL].create_index([("driver_note_id", 1), ("version", -1)])


async def seed_eb09(db):
    """Idempotent EB-09 seed. Adds ONE communication-preference row and TWO notes
    (General + Compliance) to the first available seed driver ONLY IF no EB-09
    seed exists yet.  Never touches real driver data."""
    if await db[COMMS_COLL].count_documents({"_source": SEED_TAG}) > 0:
        return
    driver = await db[DRIVERS_COLL].find_one({"_source": {"$in": ["seed", "seed-eb02"]}, "is_archived": {"$ne": True}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})
    if not driver:
        driver = await db[DRIVERS_COLL].find_one({"is_archived": {"$ne": True}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})
    if not driver:
        return
    now = _iso()
    # Comms pref
    await db[COMMS_COLL].insert_one({
        "communication_preference_id": _uuid(),
        "driver_id": driver["id"],
        "owner_report_email_override": None,
        "driver_report_email_override": None,
        "send_daily_report_owner": True,
        "send_daily_report_driver": False,
        "display_on_dispatch": True,
        "created_at": now,
        "updated_at": now,
        "created_by": "system-seed",
        "updated_by": "system-seed",
        "is_archived": False,
        "_source": SEED_TAG,
    })
    # Notes — one General, one Compliance
    for note_type, title, content, is_pinned in [
        ("General", "Preferred loading yard", "Prefers late shifts; loads from Yard 3 whenever possible.", True),
        ("Compliance", "Recent fatigue diary review", "Fatigue diary reviewed on schedule; no action required.", False),
    ]:
        nid = _uuid()
        vid = _uuid()
        await db[NOTES_COLL].insert_one({
            "driver_note_id": nid,
            "driver_id": driver["id"],
            "note_type": note_type,
            "title": title,
            "content": content,
            "is_pinned": is_pinned,
            "status": "Active",
            "current_version_id": vid,
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "is_archived": False,
            "_source": SEED_TAG,
        })
        await db[NOTE_VERSIONS_COLL].insert_one({
            "driver_note_version_id": vid,
            "driver_note_id": nid,
            "version": 1,
            "note_type": note_type,
            "title": title,
            "content": content,
            "created_at": now,
            "created_by": "system-seed",
        })


# ─── Aggregator ───────────────────────────────────────────────────────────────
async def _aggregate_driver(db, driver_id: str, role: str) -> Dict[str, Any]:
    driver_raw = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
    if not driver_raw:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver = _strip_account_fields(driver_raw, role)

    # -- Relationships ----------------------------------------------------------
    dor = await db[DOR_COLL].find_one({"driver_id": driver_id, "is_current": True, "is_archived": {"$ne": True}}, {"_id": 0})
    owner = None
    if dor and dor.get("owner_id"):
        owner = await db[OWNERS_COLL].find_one({"id": dor["owner_id"]}, {"_id": 0})

    dva = await db[DVA_COLL].find_one({"driver_id": driver_id, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}}, {"_id": 0})
    vehicle = None
    if dva and dva.get("vehicle_id"):
        vehicle = await db[VEHICLES_COLL].find_one({"id": dva["vehicle_id"]}, {"_id": 0})

    dea_docs = await db[DEA_COLL].find({"driver_id": driver_id, "is_active": True, "is_archived": {"$ne": True}}, {"_id": 0}).to_list(200)
    eq_ids = [a["equipment_id"] for a in dea_docs if a.get("equipment_id")]
    eq_by_id: Dict[str, dict] = {}
    if eq_ids:
        async for e in db[EQUIPMENT_COLL].find({"id": {"$in": eq_ids}}, {"_id": 0}):
            eq_by_id[e["id"]] = e
    equipment_assignments = [
        {"assignment": a, "equipment": eq_by_id.get(a.get("equipment_id"))}
        for a in dea_docs
    ]

    # -- Communication preferences ---------------------------------------------
    comms = await db[COMMS_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})

    # -- Compliance summaries --------------------------------------------------
    from compliance_records import _ComplianceService as ComplianceService  # local import to avoid cycles
    svc = ComplianceService(db)
    try:
        driver_summary = await svc.driver_summary(driver_id)
    except HTTPException:
        driver_summary = None
    vehicle_summary = None
    equipment_summary = None
    if vehicle:
        try:
            vehicle_summary = await svc.vehicle_summary(vehicle["id"])
        except HTTPException:
            vehicle_summary = None
    if equipment_assignments:
        # Compute worst status across all currently-assigned equipment
        components = []
        for row in equipment_assignments:
            eq = row["equipment"]
            if not eq:
                continue
            try:
                s = await svc.equipment_summary(eq["id"])
                components.append(s)
            except HTTPException:
                continue
        if components:
            worst = max(components, key=lambda c: c.get("severity", 0))
            equipment_summary = {
                "overall_status": worst.get("overall_status"),
                "severity": worst.get("severity", 0),
                "worst_equipment_id": worst.get("equipment_id"),
                "components": components,
            }

    # Aggregate worst status across driver + vehicle + equipment (Worst Status Wins)
    tuples = [
        ("driver", driver_summary),
        ("vehicle", vehicle_summary),
        ("equipment", equipment_summary),
    ]
    worst_scope, worst_status, worst_severity = None, None, 0
    for scope, s in tuples:
        if not s:
            continue
        sev = s.get("severity", 0)
        if sev > worst_severity:
            worst_scope, worst_status, worst_severity = scope, s.get("overall_status"), sev
    compliance_intelligence = {
        "driver_summary": driver_summary,
        "vehicle_summary": vehicle_summary,
        "equipment_summary": equipment_summary,
        "worst_scope": worst_scope,
        "worst_status": worst_status,
        "worst_severity": worst_severity,
        "explanation": "Worst Status Wins — the highest-severity component across Driver, assigned Vehicle and Equipment sets the overall figure.",
        "calculated_at": _iso(),
    }

    # -- Primary compliance records --------------------------------------------
    primary_licence = await db[LICENCES_COLL].find_one(
        {"driver_id": driver_id, "is_primary": True, "is_archived": {"$ne": True}},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    primary_registration = None
    primary_insurance = None
    latest_inspection = None
    open_defects = []
    overdue_maintenance = []
    if vehicle:
        vid = vehicle["id"]
        primary_registration = await db[REGISTRATIONS_COLL].find_one(
            {"vehicle_id": vid, "is_current": True, "is_archived": {"$ne": True}},
            {"_id": 0}, sort=[("created_at", -1)],
        )
        primary_insurance = await db[INSURANCE_COLL].find_one(
            {"vehicle_id": vid, "is_current": True, "is_archived": {"$ne": True}},
            {"_id": 0}, sort=[("created_at", -1)],
        )
        latest_inspection = await db[INSPECTIONS_COLL].find_one(
            {"vehicle_id": vid, "is_archived": {"$ne": True}},
            {"_id": 0}, sort=[("inspection_date", -1), ("created_at", -1)],
        )
        open_defects = await db[DEFECTS_COLL].find(
            {"vehicle_id": vid, "is_archived": {"$ne": True}, "status": {"$in": ["Open", "In Progress"]}},
            {"_id": 0},
        ).sort("severity", -1).to_list(50)
        overdue_maintenance = await db[MAINTENANCE_COLL].find(
            {"vehicle_id": vid, "is_archived": {"$ne": True}, "status": {"$in": ["Overdue", "Due"]}},
            {"_id": 0},
        ).to_list(50)

    # -- Notifications ---------------------------------------------------------
    alerts = await db[NOTIFS_COLL].find(
        {"entity_type": "Driver", "entity_id": driver_id, "is_archived": {"$ne": True}},
        {"_id": 0},
    ).sort("last_triggered_at", -1).to_list(200)
    if vehicle:
        vehicle_alerts = await db[NOTIFS_COLL].find(
            {"entity_type": "Vehicle", "entity_id": vehicle["id"], "is_archived": {"$ne": True}},
            {"_id": 0},
        ).sort("last_triggered_at", -1).to_list(200)
    else:
        vehicle_alerts = []

    def _count_by(rows, field, values):
        return sum(1 for r in rows if r.get(field) in values)

    alert_counts = {
        "active": _count_by(alerts, "status", {"Active"}),
        "acknowledged": _count_by(alerts, "status", {"Acknowledged"}),
        "snoozed": _count_by(alerts, "status", {"Snoozed"}),
        "resolved": _count_by(alerts, "status", {"Resolved"}),
        "vehicle_active": _count_by(vehicle_alerts, "status", {"Active"}),
    }

    # -- Documents linked to Driver -------------------------------------------
    dlinks = await db[DOCUMENT_LINKS_COLL].find(
        {"entity_type": "Driver", "entity_id": driver_id}, {"_id": 0, "document_id": 1},
    ).to_list(2000)
    doc_ids = list({l["document_id"] for l in dlinks if l.get("document_id")})
    documents = []
    if doc_ids:
        documents = await db[DOCUMENTS_COLL].find(
            {"id": {"$in": doc_ids}, "is_archived": {"$ne": True}},
            {"_id": 0},
        ).sort("created_at", -1).to_list(1000)

    def _docs_where(**where):
        out = []
        for d in documents:
            if all(d.get(k) == v for k, v in where.items()):
                out.append(d)
        return out

    doc_stats = {
        "total": len(documents),
        "active": len(_docs_where(status="Active")),
        "under_review": len(_docs_where(status="Under Review")),
        "rejected": len(_docs_where(status="Rejected")),
        "recent": documents[:5],
    }

    profile_photo = next((d for d in documents if (d.get("category") or "").lower() == "profile photo"), None)
    driver_contract = next((d for d in documents if (d.get("category") or "").lower() == "driver contract"), None)
    driver_licence_evidence = None
    if primary_licence:
        # Link licence to any Documents tagged to that Licence entity
        lic_links = await db[DOCUMENT_LINKS_COLL].find(
            {"entity_type": "DriverLicence", "entity_id": primary_licence["id"]},
            {"_id": 0, "document_id": 1},
        ).to_list(50)
        if lic_links:
            driver_licence_evidence = await db[DOCUMENTS_COLL].find_one(
                {"id": lic_links[0]["document_id"], "is_archived": {"$ne": True}}, {"_id": 0},
            )

    # -- Numbering / allocation history ----------------------------------------
    allocation_events = await db[ALLOCATION_EVENTS_COLL].find(
        {"driver_id": driver_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)

    # -- Notes -----------------------------------------------------------------
    notes_raw = await db[NOTES_COLL].find(
        {"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0},
    ).sort([("is_pinned", -1), ("updated_at", -1)]).to_list(100)
    notes = [n for n in notes_raw if _visible_note(role, n.get("note_type", "General"))]

    # -- Activation summary (adapter) ------------------------------------------
    activation = await _compute_activation_summary(
        db, driver_raw, primary_licence, dor, dva, driver_contract, comms,
    )

    return {
        "driver": driver,
        "role": role,
        "restricted_fields": sorted(SENSITIVE_ACCOUNT_FIELDS) if role not in ACCOUNT_READ_ROLES else [],
        "owner": owner,
        "owner_relationship": dor,
        "vehicle": vehicle,
        "vehicle_assignment": dva,
        "equipment_assignments": equipment_assignments,
        "communication_preferences": comms,
        "compliance_intelligence": compliance_intelligence,
        "primary_licence": primary_licence,
        "primary_registration": primary_registration,
        "primary_insurance": primary_insurance,
        "vehicle_compliance_extras": {
            "latest_inspection": latest_inspection,
            "open_defects": open_defects,
            "overdue_maintenance": overdue_maintenance,
        },
        "alerts": alerts,
        "vehicle_alerts": vehicle_alerts,
        "alert_counts": alert_counts,
        "documents": {
            "profile_photo": profile_photo,
            "driver_contract": driver_contract,
            "driver_licence_evidence": driver_licence_evidence,
            "stats": doc_stats,
        },
        "allocation_events": allocation_events,
        "notes": notes,
        "activation": activation,
        "generated_at": _iso(),
    }


async def _compute_activation_summary(
    db, driver: dict, primary_licence: Optional[dict], dor: Optional[dict],
    dva: Optional[dict], contract: Optional[dict], comms: Optional[dict],
) -> Dict[str, Any]:
    """Truthful activation adapter. Legacy onboarding checkbox alone is NOT enough
    to mark an item complete — evidence must exist in the canonical source.
    """
    driver_id = driver["id"]
    onboarding = await db[ONBOARDING_COLL].find_one({"driver_id": driver_id}, {"_id": 0})

    items: List[Dict[str, Any]] = []

    def _item(key, label, complete, mandatory, source, reason=None):
        items.append({
            "item_key": key,
            "label": label,
            "complete": bool(complete),
            "mandatory": bool(mandatory),
            "source": source,
            "reason": reason or ("Complete" if complete else "Missing"),
        })

    # Mandatory items
    _item("driver_details", "Driver contact details on file",
          bool(driver.get("mobile_number") and driver.get("email")),
          True, "canonical:drivers",
          "Mobile & email required")
    _item("driver_code", "Driver Code allocated",
          bool(driver.get("driver_code")),
          True, "canonical:drivers/EB-08",
          "Automatic or manual allocation via EB-08")
    _item("dispatch_number", "Dispatch Number allocated",
          bool(driver.get("dispatch_number")),
          True, "canonical:drivers/EB-08")
    _item("primary_licence", "Primary Driver Licence recorded",
          bool(primary_licence),
          True, "canonical:driver_licences")
    _item("owner_relationship", "Current Owner assigned",
          bool(dor),
          True, "canonical:driver_owner_relationships")
    _item("vehicle_assignment", "Primary Vehicle assignment",
          bool(dva),
          True, "canonical:driver_vehicle_assignments")
    _item("driver_contract", "Driver Contract on file",
          bool(contract),
          True, "canonical:documents (Driver Contract)")

    # Automatic/environmental items
    _item("communication_preferences", "Communication preferences set",
          bool(comms),
          False, "canonical:driver_communication_preferences")
    _item("onboarding_record", "Onboarding record present",
          bool(onboarding),
          False, "legacy:onboarding")

    # Legacy onboarding checklist honour: only mark COMPLETE_SUPPORT if evidence
    if onboarding and onboarding.get("legacy_activation_ready") is True:
        # Cross-validate: legacy claim + no primary licence => flag as unverified
        source_ok = bool(primary_licence and driver.get("driver_code") and dor and dva)
        _item("legacy_activation_ready", "Legacy activation flag",
              source_ok, False,
              "legacy:onboarding + canonical cross-check",
              "Legacy flag confirmed by source records" if source_ok
              else "Legacy flag claims ready but source records are missing — flagged")

    mandatory_missing = [i for i in items if i["mandatory"] and not i["complete"]]
    mandatory_total = sum(1 for i in items if i["mandatory"])
    mandatory_done = mandatory_total - len(mandatory_missing)
    completed_all = sum(1 for i in items if i["complete"])

    if mandatory_missing:
        readiness = "Not Ready"
    elif mandatory_total == mandatory_done:
        readiness = "Ready"
    else:
        readiness = "Partial"

    override = onboarding.get("activation_override") if onboarding else None

    return {
        "readiness": readiness,
        "mandatory_total": mandatory_total,
        "mandatory_done": mandatory_done,
        "total_items": len(items),
        "completed_items": completed_all,
        "mandatory_missing_items": mandatory_missing,
        "override": override,
        "items": items,
    }


# ─── Router builder ───────────────────────────────────────────────────────────
def build_driver_profile_router(db, get_current_user):
    router = APIRouter(prefix="/api")

    # ---- Aggregator --------------------------------------------------------
    @router.get("/drivers/{driver_id}/command-centre-profile")
    async def command_centre_profile(driver_id: str, current=Depends(get_current_user)):
        role = current.get("role", "ReadOnly")
        return await _aggregate_driver(db, driver_id, role)

    # ---- Activation summary (adapter, read-only) ---------------------------
    @router.get("/drivers/{driver_id}/activation-summary")
    async def activation_summary(driver_id: str, current=Depends(get_current_user)):
        driver = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        primary_licence = await db[LICENCES_COLL].find_one(
            {"driver_id": driver_id, "is_primary": True, "is_archived": {"$ne": True}},
            {"_id": 0}, sort=[("created_at", -1)],
        )
        dor = await db[DOR_COLL].find_one({"driver_id": driver_id, "is_current": True, "is_archived": {"$ne": True}}, {"_id": 0})
        dva = await db[DVA_COLL].find_one({"driver_id": driver_id, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}}, {"_id": 0})
        dlinks = await db[DOCUMENT_LINKS_COLL].find(
            {"entity_type": "Driver", "entity_id": driver_id}, {"_id": 0, "document_id": 1},
        ).to_list(2000)
        contract = None
        if dlinks:
            doc_ids = [l["document_id"] for l in dlinks if l.get("document_id")]
            contract = await db[DOCUMENTS_COLL].find_one(
                {"id": {"$in": doc_ids}, "category": "Driver Contract", "is_archived": {"$ne": True}},
                {"_id": 0},
            )
        comms = await db[COMMS_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        return await _compute_activation_summary(db, driver, primary_licence, dor, dva, contract, comms)

    # ---- Communication preferences ----------------------------------------
    @router.get("/drivers/{driver_id}/communication-preferences")
    async def get_comms(driver_id: str, current=Depends(get_current_user)):
        driver = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0, "id": 1})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        pref = await db[COMMS_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        return pref  # may be None

    @router.put("/drivers/{driver_id}/communication-preferences")
    async def upsert_comms(driver_id: str, payload: CommsPreferencesPayload,
                            current=Depends(get_current_user)):
        _require_role(current, {"Admin", "Manager", "Allocator"})
        driver = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0, "id": 1})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        now = _iso()
        data = payload.model_dump()
        existing = await db[COMMS_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        if existing:
            await db[COMMS_COLL].update_one(
                {"communication_preference_id": existing["communication_preference_id"]},
                {"$set": {**data, "updated_at": now, "updated_by": current["email"]}},
            )
            return await db[COMMS_COLL].find_one(
                {"communication_preference_id": existing["communication_preference_id"]},
                {"_id": 0},
            )
        doc = {
            "communication_preference_id": _uuid(),
            "driver_id": driver_id,
            **data,
            "created_at": now,
            "updated_at": now,
            "created_by": current["email"],
            "updated_by": current["email"],
            "is_archived": False,
        }
        await db[COMMS_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # ---- Notes ------------------------------------------------------------
    def _can_read_category(role: str, category: str) -> bool:
        return _visible_note(role, category)

    def _can_write_category(role: str, category: str) -> bool:
        if role == "ReadOnly":
            return False
        return _visible_note(role, category)

    @router.get("/drivers/{driver_id}/notes")
    async def list_notes(driver_id: str, include_archived: bool = False,
                          current=Depends(get_current_user)):
        role = current.get("role", "ReadOnly")
        q = {"driver_id": driver_id}
        if not include_archived:
            q["is_archived"] = {"$ne": True}
        rows = await db[NOTES_COLL].find(q, {"_id": 0}).sort([("is_pinned", -1), ("updated_at", -1)]).to_list(500)
        return [n for n in rows if _can_read_category(role, n.get("note_type", "General"))]

    @router.get("/drivers/{driver_id}/notes/{note_id}")
    async def get_note(driver_id: str, note_id: str, current=Depends(get_current_user)):
        role = current.get("role", "ReadOnly")
        n = await db[NOTES_COLL].find_one({"driver_note_id": note_id, "driver_id": driver_id}, {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="Note not found")
        if not _can_read_category(role, n.get("note_type", "General")):
            raise HTTPException(status_code=403, detail="Insufficient permissions for this note category")
        versions = await db[NOTE_VERSIONS_COLL].find({"driver_note_id": note_id}, {"_id": 0}).sort("version", -1).to_list(200)
        return {"note": n, "versions": versions}

    @router.post("/drivers/{driver_id}/notes")
    async def create_note(driver_id: str, payload: NoteCreatePayload,
                           current=Depends(get_current_user)):
        role = current.get("role", "ReadOnly")
        if role == "ReadOnly":
            raise HTTPException(status_code=403, detail="ReadOnly cannot create notes")
        if payload.note_type not in NOTE_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"note_type must be one of {NOTE_CATEGORIES}")
        if not _can_write_category(role, payload.note_type):
            raise HTTPException(status_code=403, detail=f"Insufficient permissions for {payload.note_type} notes")
        driver = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0, "id": 1})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        now = _iso()
        note_id = _uuid()
        version_id = _uuid()
        note = {
            "driver_note_id": note_id,
            "driver_id": driver_id,
            "note_type": payload.note_type,
            "title": payload.title,
            "content": payload.content,
            "is_pinned": payload.is_pinned,
            "status": "Active",
            "current_version_id": version_id,
            "created_at": now,
            "updated_at": now,
            "created_by": current["email"],
            "updated_by": current["email"],
            "is_archived": False,
        }
        version = {
            "driver_note_version_id": version_id,
            "driver_note_id": note_id,
            "version": 1,
            "note_type": payload.note_type,
            "title": payload.title,
            "content": payload.content,
            "created_at": now,
            "created_by": current["email"],
        }
        await db[NOTES_COLL].insert_one(note)
        await db[NOTE_VERSIONS_COLL].insert_one(version)
        note.pop("_id", None)
        return note

    @router.put("/drivers/{driver_id}/notes/{note_id}")
    async def update_note(driver_id: str, note_id: str, payload: NoteUpdatePayload,
                           current=Depends(get_current_user)):
        role = current.get("role", "ReadOnly")
        if role == "ReadOnly":
            raise HTTPException(status_code=403, detail="ReadOnly cannot edit notes")
        existing = await db[NOTES_COLL].find_one({"driver_note_id": note_id, "driver_id": driver_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Note not found")
        target_type = payload.note_type or existing.get("note_type", "General")
        if target_type not in NOTE_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"note_type must be one of {NOTE_CATEGORIES}")
        # User must have read AND write permission for BOTH old and new category
        if not _can_read_category(role, existing.get("note_type", "General")):
            raise HTTPException(status_code=403, detail="Insufficient permissions for this note category")
        if not _can_write_category(role, target_type):
            raise HTTPException(status_code=403, detail=f"Insufficient permissions for {target_type} notes")

        # Append-only versioning
        prior_versions = await db[NOTE_VERSIONS_COLL].count_documents({"driver_note_id": note_id})
        now = _iso()
        version_id = _uuid()
        version = {
            "driver_note_version_id": version_id,
            "driver_note_id": note_id,
            "version": prior_versions + 1,
            "note_type": target_type,
            "title": payload.title if payload.title is not None else existing.get("title"),
            "content": payload.content,
            "created_at": now,
            "created_by": current["email"],
        }
        await db[NOTE_VERSIONS_COLL].insert_one(version)
        update = {
            "note_type": target_type,
            "title": payload.title if payload.title is not None else existing.get("title"),
            "content": payload.content,
            "current_version_id": version_id,
            "updated_at": now,
            "updated_by": current["email"],
        }
        if payload.is_pinned is not None:
            update["is_pinned"] = payload.is_pinned
        await db[NOTES_COLL].update_one({"driver_note_id": note_id}, {"$set": update})
        return await db[NOTES_COLL].find_one({"driver_note_id": note_id}, {"_id": 0})

    @router.delete("/drivers/{driver_id}/notes/{note_id}")
    async def archive_note(driver_id: str, note_id: str, current=Depends(get_current_user)):
        role = current.get("role", "ReadOnly")
        if role not in {"Admin", "Manager"}:
            raise HTTPException(status_code=403, detail="Only Admin/Manager can archive notes")
        n = await db[NOTES_COLL].find_one({"driver_note_id": note_id, "driver_id": driver_id}, {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="Note not found")
        await db[NOTES_COLL].update_one(
            {"driver_note_id": note_id},
            {"$set": {"is_archived": True, "status": "Archived", "updated_at": _iso(), "updated_by": current["email"]}},
        )
        return {"status": "archived", "driver_note_id": note_id}

    return router
