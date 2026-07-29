"""EB-10 · Driver Activation & Onboarding Gate — canonical readiness engine.

Six new canonical collections:
  * activation_templates
  * activation_template_items
  * driver_activation_records
  * driver_activation_items
  * driver_activation_overrides
  * driver_activation_events (append-only)

Design rules (enforced in code, not just docs):
  1. Checklist items *validate* canonical sources; they never *become* the
     source. Automatic items read from Driver / Owner / Vehicle / Equipment /
     Licence / Registration / Insurance / Documents / Defects / Maintenance /
     Numbering. Their `source_status` and `source_explanation` are recomputed
     on every recalculate — the item never stores a stale duplicate.
  2. Automatic items cannot be manually marked Complete or Reopen.
  3. An override never changes the underlying source compliance. It only
     changes the item's `completion_status` to `Override Active`.
  4. Critical vehicle defects are non-overridable blockers.
  5. "Ready" NEVER automatically activates a driver — activation is an
     explicit authorised action.
  6. Manager + Admin only for override approve / activate / deactivate /
     reactivate / run jobs. Allocator may complete permitted operational
     manual items and request overrides. Compliance may complete/override
     compliance-category items but never approve its own request.
  7. History is append-only in `driver_activation_events`. Deactivation
     preserves records; it never deletes checklist history.
  8. `Under Review` documents do not count as accepted evidence in the ACE
     default template.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

# ─── Collection names ────────────────────────────────────────────────────────
TPL_COLL = "activation_templates"
TPL_ITEM_COLL = "activation_template_items"
REC_COLL = "driver_activation_records"
ITEM_COLL = "driver_activation_items"
OVR_COLL = "driver_activation_overrides"
EVT_COLL = "driver_activation_events"
JOB_COLL = "activation_job_runs"

# canonical source collections we read from
DRIVERS_COLL = "drivers"
OWNERS_COLL = "owners"
VEHICLES_COLL = "vehicles"
EQUIPMENT_COLL = "equipment"
DOR_COLL = "driver_owner_relationships"
DVA_COLL = "driver_vehicle_assignments"
DEA_COLL = "driver_equipment_assignments"
LICENCES_COLL = "driver_licences"
REGISTRATIONS_COLL = "vehicle_registrations"
INSURANCE_COLL = "vehicle_insurance_policies"
DEFECTS_COLL = "vehicle_defects"
MAINTENANCE_COLL = "vehicle_maintenance_tasks"
EQUIP_COMPL_COLL = "equipment_compliance_records"
DOCUMENTS_COLL = "documents"
DOC_LINKS_COLL = "document_links"
NOTIFS_COLL = "notifications"
COMMS_COLL = "driver_communication_preferences"

SEED_TAG = "seed-eb10"

# ─── Enumerated values ───────────────────────────────────────────────────────
DRIVER_TYPES = ["Employee Driver", "Contractor Driver", "Owner Driver",
                "Relief Driver", "Trainee Driver", "Other"]
CATEGORIES = ["Driver Identity", "Account Setup", "Driver Setup", "Communication",
              "Vehicle Assignment", "Equipment Assignment", "Owner Relationship",
              "Licence and Compliance", "Documents", "System Access", "Training",
              "Administration", "Other"]
COMPLETION_TYPES = ["Automatic", "Manual", "Conditional Automatic",
                    "Conditional Manual", "Informational"]
COMPLETION_STATUSES = ["Not Assessed", "Complete", "Incomplete", "Missing",
                       "Expired", "Due Soon", "Under Review", "Not Applicable",
                       "Override Active", "Override Expired", "Blocked"]
RECORD_STATUSES = ["Not Started", "In Progress", "Ready", "Activated",
                   "Activation Blocked", "Deactivated", "Archived"]
READINESS_STATUSES = ["Not Assessed", "Incomplete", "Ready",
                      "Ready with Override", "Blocked", "Activated", "Deactivated"]
OVERRIDE_STATUSES = ["Requested", "Approved", "Active", "Expired",
                     "Revoked", "Rejected", "Archived"]
EVENT_TYPES = ["Activation Started", "Item Assessed", "Item Completed",
               "Item Became Incomplete", "Item Became Missing",
               "Item Became Expired", "Item Became Not Applicable",
               "Override Requested", "Override Approved", "Override Rejected",
               "Override Expired", "Override Revoked",
               "Driver Became Ready", "Activation Blocked",
               "Driver Activated", "Driver Deactivated", "Driver Reactivated",
               "Recalculated", "Template Applied"]

# Role gates
ROLE_ACTIVATE = {"Admin", "Manager"}
ROLE_APPROVE_OVERRIDE = {"Admin", "Manager"}
ROLE_MANAGE_TEMPLATES = {"Admin", "Manager"}
ROLE_RUN_JOBS = {"Admin", "Manager"}
ROLE_MANUAL_COMPLETE = {"Admin", "Manager", "Allocator", "Compliance"}
ROLE_REQUEST_OVERRIDE = {"Admin", "Manager", "Allocator", "Compliance"}
# Compliance-category items may be completed only by Compliance/Manager/Admin
CATEGORY_ROLE_MANUAL = {
    "Licence and Compliance": {"Compliance", "Manager", "Admin"},
    "Account Setup": {"Manager", "Admin"},
}

# ─── Helpers ─────────────────────────────────────────────────────────────────
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _uuid() -> str:
    return str(uuid.uuid4())

def _require(role: str, allowed: set, msg="Insufficient permissions"):
    if role not in allowed:
        raise HTTPException(status_code=403, detail=msg)

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _parse_iso(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ─── Pydantic payloads ───────────────────────────────────────────────────────
class TemplatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    description: Optional[str] = None
    company_ref: Optional[str] = None
    driver_type: str = "Employee Driver"
    is_default: bool = False
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None

class TemplateItemPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_key: str
    label: str
    description: Optional[str] = None
    category: str
    completion_type: str = "Manual"
    source_entity_type: Optional[str] = None
    source_field: Optional[str] = None
    source_rule: Optional[str] = None
    mandatory: bool = True
    conditional: bool = False
    condition_rule: Optional[Dict[str, Any]] = None
    display_order: int = 0
    evidence_required: bool = False
    evidence_category: Optional[str] = None
    override_allowed: bool = False
    override_max_days: int = 30

class ManualCompletePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    manual_note: Optional[str] = None
    evidence_document_id: Optional[str] = None

class OverrideRequestPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reason: str = Field(min_length=6)
    risk_acknowledgement: bool
    requested_expiry_days: int = Field(ge=1)

class ActivatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reason: Optional[str] = None
    set_driver_status_active: bool = True

class DeactivatePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reason: str = Field(min_length=3)


# ═══════════════════════════════════════════════════════════════════════════
# Startup / seed
# ═══════════════════════════════════════════════════════════════════════════
async def ensure_indexes(db):
    for coll, keys in [
        (TPL_COLL, ["activation_template_id"]),
        (TPL_ITEM_COLL, ["activation_template_item_id"]),
        (REC_COLL, ["driver_activation_id"]),
        (ITEM_COLL, ["driver_activation_item_id"]),
        (OVR_COLL, ["activation_override_id"]),
        (EVT_COLL, ["activation_event_id"]),
        (JOB_COLL, ["job_id"]),
    ]:
        for k in keys:
            await db[coll].create_index(k, unique=True)
    await db[TPL_ITEM_COLL].create_index("activation_template_id")
    await db[ITEM_COLL].create_index([("driver_activation_id", 1), ("display_order", 1)])
    await db[ITEM_COLL].create_index("driver_id")
    await db[OVR_COLL].create_index([("driver_activation_id", 1), ("status", 1)])
    await db[EVT_COLL].create_index([("driver_activation_id", 1), ("performed_at", -1)])


# ─── Default ACE template definition (fictional, dev-only) ───────────────────
DEFAULT_ITEMS: List[Dict[str, Any]] = [
    # Driver Identity ---------------------------------------------------------
    dict(item_key="drv.full_name", label="Full Name",
         category="Driver Identity", completion_type="Automatic",
         source_entity_type="driver", source_field="full_name",
         mandatory=True, evidence_required=False, override_allowed=False),
    dict(item_key="drv.residential_address", label="Residential Address",
         category="Driver Identity", completion_type="Automatic",
         source_entity_type="driver", source_field="residential_address",
         mandatory=True, override_allowed=False),
    dict(item_key="drv.mobile", label="Mobile Number",
         category="Driver Identity", completion_type="Automatic",
         source_entity_type="driver", source_field="mobile_number",
         mandatory=True, override_allowed=False),
    dict(item_key="drv.email", label="Email Address",
         category="Driver Identity", completion_type="Automatic",
         source_entity_type="driver", source_field="email",
         mandatory=True, override_allowed=False),
    dict(item_key="drv.emergency_name", label="Emergency Contact Name",
         category="Driver Identity", completion_type="Automatic",
         source_entity_type="driver", source_field="emergency_contact_name",
         mandatory=False, override_allowed=True, override_max_days=30),
    dict(item_key="drv.emergency_phone", label="Emergency Contact Phone",
         category="Driver Identity", completion_type="Automatic",
         source_entity_type="driver", source_field="emergency_contact_phone",
         mandatory=False, override_allowed=True, override_max_days=30),
    dict(item_key="drv.profile_photo", label="Profile Photo",
         category="Documents", completion_type="Automatic",
         source_entity_type="document", source_field="Profile Photo",
         mandatory=False, evidence_required=True, override_allowed=True, override_max_days=60),
    # Account Setup ----------------------------------------------------------
    dict(item_key="acc.business_name", label="Business Name (contractor)",
         category="Account Setup", completion_type="Conditional Automatic",
         source_entity_type="driver", source_field="business_name",
         conditional=True, condition_rule={"driver_type_in": ["Contractor Driver", "Owner Driver"]},
         mandatory=True, override_allowed=True, override_max_days=30),
    dict(item_key="acc.abn", label="ABN (contractor)",
         category="Account Setup", completion_type="Conditional Automatic",
         source_entity_type="driver", source_field="abn",
         conditional=True, condition_rule={"driver_type_in": ["Contractor Driver", "Owner Driver"]},
         mandatory=True, override_allowed=True, override_max_days=30),
    dict(item_key="acc.payroll_number", label="Payroll Number",
         category="Account Setup", completion_type="Automatic",
         source_entity_type="driver", source_field="payroll_number",
         mandatory=False, override_allowed=True, override_max_days=30),
    dict(item_key="acc.payment_percentage", label="Payment Percentage",
         category="Account Setup", completion_type="Automatic",
         source_entity_type="driver", source_field="payment_percentage",
         mandatory=True, override_allowed=True, override_max_days=30),
    # Driver Setup -----------------------------------------------------------
    dict(item_key="setup.driver_code", label="Driver Code allocated",
         category="Driver Setup", completion_type="Automatic",
         source_entity_type="driver", source_field="driver_code",
         mandatory=True, override_allowed=False),
    dict(item_key="setup.dispatch_number", label="Dispatch Number allocated",
         category="Driver Setup", completion_type="Automatic",
         source_entity_type="driver", source_field="dispatch_number",
         mandatory=True, override_allowed=False),
    dict(item_key="setup.start_date", label="Start Date",
         category="Driver Setup", completion_type="Automatic",
         source_entity_type="driver", source_field="start_date",
         mandatory=True, override_allowed=True, override_max_days=14),
    dict(item_key="setup.contract", label="Driver Contract on file",
         category="Documents", completion_type="Automatic",
         source_entity_type="document", source_field="Driver Contract",
         mandatory=True, evidence_required=True, override_allowed=True, override_max_days=14),
    # Communication & Assignment --------------------------------------------
    dict(item_key="comm.preferences", label="Communication Preferences reviewed",
         category="Communication", completion_type="Automatic",
         source_entity_type="comms", source_field="exists",
         mandatory=False, override_allowed=True, override_max_days=30),
    dict(item_key="rel.owner", label="Current Owner relationship",
         category="Owner Relationship", completion_type="Automatic",
         source_entity_type="owner_relationship", source_field="exists",
         mandatory=True, override_allowed=True, override_max_days=30),
    dict(item_key="rel.vehicle", label="Current Primary Vehicle",
         category="Vehicle Assignment", completion_type="Automatic",
         source_entity_type="vehicle_assignment", source_field="exists",
         mandatory=True, override_allowed=True, override_max_days=30),
    # Compliance -------------------------------------------------------------
    dict(item_key="cmp.licence_exists", label="Primary Driver Licence exists",
         category="Licence and Compliance", completion_type="Automatic",
         source_entity_type="licence", source_field="exists",
         mandatory=True, override_allowed=False),
    dict(item_key="cmp.licence_not_expired", label="Driver Licence is not Expired",
         category="Licence and Compliance", completion_type="Automatic",
         source_entity_type="licence", source_field="not_expired",
         mandatory=True, override_allowed=False),
    dict(item_key="cmp.licence_evidence", label="Licence Evidence attached",
         category="Documents", completion_type="Automatic",
         source_entity_type="document", source_field="Driver Licence",
         mandatory=True, evidence_required=True, override_allowed=True, override_max_days=14),
    dict(item_key="cmp.vehicle_rego", label="Vehicle Registration is current",
         category="Licence and Compliance", completion_type="Automatic",
         source_entity_type="vehicle_registration", source_field="current",
         mandatory=True, override_allowed=True, override_max_days=7),
    dict(item_key="cmp.vehicle_insurance", label="Vehicle Insurance is current",
         category="Licence and Compliance", completion_type="Automatic",
         source_entity_type="vehicle_insurance", source_field="current",
         mandatory=True, override_allowed=True, override_max_days=7),
    dict(item_key="cmp.no_critical_defect", label="No unresolved Critical Vehicle defect",
         category="Licence and Compliance", completion_type="Automatic",
         source_entity_type="vehicle_defect", source_field="none_critical",
         mandatory=True, override_allowed=False),  # non-overridable blocker
    dict(item_key="cmp.no_overdue_maintenance", label="No Overdue Vehicle maintenance",
         category="Licence and Compliance", completion_type="Automatic",
         source_entity_type="vehicle_maintenance", source_field="none_overdue",
         mandatory=True, override_allowed=True, override_max_days=7),
    # Training / manual ------------------------------------------------------
    dict(item_key="trn.induction", label="Induction completed",
         category="Training", completion_type="Manual",
         mandatory=True, override_allowed=True, override_max_days=14),
    dict(item_key="trn.safety_briefing", label="Safety briefing completed",
         category="Training", completion_type="Manual",
         mandatory=True, override_allowed=True, override_max_days=14),
    dict(item_key="sys.dispatch_login", label="Dispatch system login issued",
         category="System Access", completion_type="Manual",
         mandatory=False, override_allowed=True, override_max_days=30),
]


async def seed_default_template(db):
    """Idempotent: creates the ACE default Employee-Driver template if missing."""
    existing = await db[TPL_COLL].find_one({"_source": SEED_TAG, "is_default": True, "driver_type": "Employee Driver"})
    if existing:
        return existing["activation_template_id"]
    tpl_id = _uuid()
    now = _iso()
    await db[TPL_COLL].insert_one({
        "activation_template_id": tpl_id,
        "name": "ACE default onboarding — Employee Driver",
        "description": "Fictional development template (EB-10 seed).",
        "company_ref": "ACE",
        "driver_type": "Employee Driver",
        "version": 1,
        "is_default": True,
        "is_active": True,
        "effective_from": now,
        "effective_to": None,
        "created_at": now, "updated_at": now,
        "created_by": "system-seed", "updated_by": "system-seed",
        "is_archived": False,
        "_source": SEED_TAG,
    })
    for order, spec in enumerate(DEFAULT_ITEMS):
        await db[TPL_ITEM_COLL].insert_one({
            "activation_template_item_id": _uuid(),
            "activation_template_id": tpl_id,
            "item_key": spec["item_key"],
            "label": spec["label"],
            "description": spec.get("description"),
            "category": spec["category"],
            "completion_type": spec["completion_type"],
            "source_entity_type": spec.get("source_entity_type"),
            "source_field": spec.get("source_field"),
            "source_rule": spec.get("source_rule"),
            "mandatory": spec["mandatory"],
            "conditional": spec.get("conditional", False),
            "condition_rule": spec.get("condition_rule"),
            "display_order": order,
            "evidence_required": spec.get("evidence_required", False),
            "evidence_category": spec.get("source_field") if spec.get("evidence_required") else None,
            "override_allowed": spec.get("override_allowed", False),
            "override_max_days": spec.get("override_max_days", 30),
            "is_active": True,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "is_archived": False,
            "_source": SEED_TAG,
        })
    return tpl_id


# ═══════════════════════════════════════════════════════════════════════════
# ACTIVATION SERVICE (readiness engine)
# ═══════════════════════════════════════════════════════════════════════════
class ActivationService:
    def __init__(self, db):
        self.db = db

    # ── Template selection ───────────────────────────────────────────────
    async def select_template_for_driver(self, driver: dict) -> Optional[dict]:
        company = driver.get("company_ref") or "ACE"
        driver_type = driver.get("driver_type") or "Employee Driver"
        tpl = await self.db[TPL_COLL].find_one(
            {"company_ref": company, "driver_type": driver_type, "is_default": True,
             "is_active": True, "is_archived": {"$ne": True}},
            {"_id": 0},
            sort=[("version", -1)],
        )
        if not tpl:
            tpl = await self.db[TPL_COLL].find_one(
                {"driver_type": driver_type, "is_default": True, "is_active": True, "is_archived": {"$ne": True}},
                {"_id": 0}, sort=[("version", -1)],
            )
        if not tpl:
            tpl = await self.db[TPL_COLL].find_one(
                {"driver_type": "Employee Driver", "is_default": True, "is_active": True, "is_archived": {"$ne": True}},
                {"_id": 0}, sort=[("version", -1)],
            )
        return tpl

    # ── Applicability ────────────────────────────────────────────────────
    @staticmethod
    def _is_applicable(spec: dict, driver: dict) -> bool:
        if not spec.get("conditional"):
            return True
        cond = spec.get("condition_rule") or {}
        types = cond.get("driver_type_in")
        if types is not None:
            return (driver.get("driver_type") or "Employee Driver") in types
        return True

    # ── Automatic source resolvers ───────────────────────────────────────
    async def _resolve_automatic(self, item: dict, driver: dict) -> Tuple[str, str, Optional[str], Optional[str]]:
        """Return (completion_status, source_explanation, source_record_id, evidence_doc_id)."""
        s_type = item.get("source_entity_type")
        field = item.get("source_field")
        driver_id = driver["id"]

        if s_type == "driver":
            v = driver.get(field)
            if v is None or v == "":
                return "Missing", f"Driver.{field} is missing", driver_id, None
            return "Complete", f"Driver.{field}={v}", driver_id, None

        if s_type == "document":
            # Evidence: locate a linked document with the category
            links = await self.db[DOC_LINKS_COLL].find(
                {"entity_type": "Driver", "entity_id": driver_id},
                {"_id": 0, "document_id": 1},
            ).to_list(2000)
            doc_ids = [l["document_id"] for l in links if l.get("document_id")]
            if not doc_ids:
                return "Missing", f"No documents linked to Driver for {field}", None, None
            docs = await self.db[DOCUMENTS_COLL].find(
                {"id": {"$in": doc_ids}, "is_archived": {"$ne": True}}, {"_id": 0},
            ).to_list(2000)
            matches = [d for d in docs if (d.get("category") or "").lower() == field.lower()]
            if not matches:
                return "Missing", f"No {field} document attached", None, None
            # ACE policy: Under Review does not count; Rejected fails
            active = [d for d in matches if d.get("status") == "Active"]
            if active:
                return "Complete", f"{field} document on file", matches[0].get("id"), active[0].get("id")
            under = [d for d in matches if d.get("status") == "Under Review"]
            if under:
                return "Under Review", f"{field} document is Under Review", matches[0].get("id"), under[0].get("id")
            rejected = [d for d in matches if d.get("status") == "Rejected"]
            if rejected:
                return "Missing", f"{field} document rejected", matches[0].get("id"), None
            return "Missing", f"No accepted {field} document", None, None

        if s_type == "comms":
            row = await self.db[COMMS_COLL].find_one(
                {"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0},
            )
            if row:
                return "Complete", "Communication preferences on file", row.get("communication_preference_id"), None
            return "Missing", "No communication preferences set", None, None

        if s_type == "owner_relationship":
            rel = await self.db[DOR_COLL].find_one(
                {"driver_id": driver_id, "is_current": True, "is_archived": {"$ne": True}}, {"_id": 0},
            )
            if rel:
                return "Complete", f"Current owner relationship {rel.get('id')}", rel.get("id"), None
            return "Missing", "No current owner relationship", None, None

        if s_type == "vehicle_assignment":
            dva = await self.db[DVA_COLL].find_one(
                {"driver_id": driver_id, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}}, {"_id": 0},
            )
            if dva:
                return "Complete", f"Primary vehicle assignment {dva.get('id')}", dva.get("id"), None
            return "Missing", "No primary vehicle assignment", None, None

        if s_type == "licence":
            lic = await self.db[LICENCES_COLL].find_one(
                {"driver_id": driver_id, "is_primary": True, "is_archived": {"$ne": True}},
                {"_id": 0}, sort=[("created_at", -1)],
            )
            if not lic:
                return "Missing", "No primary driver licence", None, None
            if field == "exists":
                return "Complete", f"Primary licence {lic.get('licence_number')}", lic.get("id"), None
            if field == "not_expired":
                exp = _parse_iso(lic.get("expiry_date"))
                if not exp:
                    return "Missing", "Licence expiry unknown", lic.get("id"), None
                now = _now()
                if exp < now:
                    return "Expired", f"Licence expired on {lic.get('expiry_date')}", lic.get("id"), None
                if exp < now + timedelta(days=30):
                    return "Due Soon", f"Licence expires on {lic.get('expiry_date')} (soon)", lic.get("id"), None
                return "Complete", f"Licence valid until {lic.get('expiry_date')}", lic.get("id"), None

        if s_type in ("vehicle_registration", "vehicle_insurance"):
            dva = await self.db[DVA_COLL].find_one(
                {"driver_id": driver_id, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}}, {"_id": 0},
            )
            if not dva:
                return "Missing", "No primary vehicle to inspect", None, None
            vid = dva.get("vehicle_id")
            coll = REGISTRATIONS_COLL if s_type == "vehicle_registration" else INSURANCE_COLL
            row = await self.db[coll].find_one(
                {"vehicle_id": vid, "is_current": True, "is_archived": {"$ne": True}},
                {"_id": 0}, sort=[("created_at", -1)],
            )
            if not row:
                return "Missing", f"No current {s_type.replace('_', ' ')}", None, None
            exp = _parse_iso(row.get("expiry_date"))
            if exp and exp < _now():
                return "Expired", f"Expired on {row.get('expiry_date')}", row.get("id"), None
            if exp and exp < _now() + timedelta(days=30):
                return "Due Soon", f"Expires on {row.get('expiry_date')} (soon)", row.get("id"), None
            return "Complete", f"Valid until {row.get('expiry_date')}", row.get("id"), None

        if s_type == "vehicle_defect":
            dva = await self.db[DVA_COLL].find_one(
                {"driver_id": driver_id, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}}, {"_id": 0},
            )
            if not dva:
                return "Complete", "No primary vehicle — nothing to check", None, None
            crit = await self.db[DEFECTS_COLL].find_one(
                {"vehicle_id": dva.get("vehicle_id"), "severity": "Critical",
                 "status": {"$in": ["Open", "In Progress"]}, "is_archived": {"$ne": True}},
                {"_id": 0},
            )
            if crit:
                return "Blocked", f"Critical defect open: {crit.get('description', crit.get('id'))}", crit.get("id"), None
            return "Complete", "No critical defects", None, None

        if s_type == "vehicle_maintenance":
            dva = await self.db[DVA_COLL].find_one(
                {"driver_id": driver_id, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}}, {"_id": 0},
            )
            if not dva:
                return "Complete", "No primary vehicle — nothing to check", None, None
            overdue = await self.db[MAINTENANCE_COLL].find_one(
                {"vehicle_id": dva.get("vehicle_id"), "status": {"$in": ["Overdue"]}, "is_archived": {"$ne": True}}, {"_id": 0},
            )
            if overdue:
                return "Incomplete", "Overdue maintenance outstanding", overdue.get("id"), None
            return "Complete", "No overdue maintenance", None, None

        # Fallback
        return "Not Assessed", f"Unknown source {s_type}", None, None

    # ── Ensure record + items exist ──────────────────────────────────────
    async def get_or_start(self, driver_id: str, actor_email: str) -> Tuple[dict, str]:
        """Return (record, created_flag_str). Does NOT recalculate."""
        driver = await self.db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        rec = await self.db[REC_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        if rec:
            return rec, "existing"
        tpl = await self.select_template_for_driver(driver)
        if not tpl:
            raise HTTPException(status_code=500, detail="No activation template available")
        rec_id = _uuid()
        now = _iso()
        rec = {
            "driver_activation_id": rec_id,
            "driver_id": driver_id,
            "activation_template_id": tpl["activation_template_id"],
            "template_version": tpl["version"],
            "status": "In Progress",
            "readiness_status": "Not Assessed",
            "applicable_item_count": 0,
            "completed_item_count": 0,
            "mandatory_item_count": 0,
            "mandatory_completed_count": 0,
            "outstanding_mandatory_count": 0,
            "override_count": 0,
            "started_at": now,
            "ready_at": None,
            "activated_at": None, "activated_by": None,
            "deactivated_at": None, "deactivated_by": None,
            "activation_reason": None, "deactivation_reason": None,
            "last_calculated_at": None,
            "created_at": now, "updated_at": now,
            "created_by": actor_email, "updated_by": actor_email,
            "is_archived": False,
        }
        await self.db[REC_COLL].insert_one(rec)
        # Instantiate items
        specs = await self.db[TPL_ITEM_COLL].find(
            {"activation_template_id": tpl["activation_template_id"], "is_active": True, "is_archived": {"$ne": True}},
            {"_id": 0},
        ).sort("display_order", 1).to_list(1000)
        for spec in specs:
            applicable = self._is_applicable(spec, driver)
            await self.db[ITEM_COLL].insert_one({
                "driver_activation_item_id": _uuid(),
                "driver_activation_id": rec_id,
                "driver_id": driver_id,
                "activation_template_item_id": spec["activation_template_item_id"],
                "item_key": spec["item_key"],
                "label_snapshot": spec["label"],
                "category": spec["category"],
                "completion_type": spec["completion_type"],
                "mandatory": spec["mandatory"],
                "applicable": applicable,
                "completion_status": "Not Applicable" if not applicable else "Not Assessed",
                "source_entity_type": spec.get("source_entity_type"),
                "source_entity_id": None,
                "source_record_id": None,
                "source_status": None,
                "source_explanation": None,
                "evidence_document_id": None,
                "completed_at": None, "completed_by": None,
                "manual_note": None,
                "last_checked_at": None,
                "created_at": now, "updated_at": now,
                "is_archived": False,
            })
        await self._event(rec_id, driver_id, "Activation Started",
                           None, "In Progress", actor_email, "Template applied", None, None, {"template_id": tpl["activation_template_id"]})
        return rec, "created"

    # ── Event append-only ────────────────────────────────────────────────
    async def _event(self, rec_id, driver_id, event_type, prev_status, new_status,
                       actor, reason=None, item_id=None, override_id=None, payload=None):
        await self.db[EVT_COLL].insert_one({
            "activation_event_id": _uuid(),
            "driver_activation_id": rec_id,
            "driver_id": driver_id,
            "event_type": event_type,
            "previous_status": prev_status,
            "new_status": new_status,
            "item_id": item_id,
            "override_id": override_id,
            "reason": reason,
            "performed_by": actor,
            "performed_at": _iso(),
            "correlation_id": _uuid(),
            "payload": payload or {},
            "created_at": _iso(),
        })

    # ── Recalculate all items + readiness ────────────────────────────────
    async def recalculate(self, driver_id: str, actor_email: str) -> dict:
        rec, _ = await self.get_or_start(driver_id, actor_email)
        driver = await self.db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        items = await self.db[ITEM_COLL].find(
            {"driver_activation_id": rec["driver_activation_id"], "is_archived": {"$ne": True}}, {"_id": 0},
        ).to_list(1000)
        # Load active overrides indexed by item id
        overrides = await self.db[OVR_COLL].find(
            {"driver_activation_id": rec["driver_activation_id"],
             "status": {"$in": ["Approved", "Active"]},
             "is_archived": {"$ne": True}}, {"_id": 0},
        ).to_list(500)
        # Expire overrides past their expiry
        now = _now()
        expired_ids = []
        for ov in overrides:
            exp = _parse_iso(ov.get("expires_at"))
            if exp and exp < now:
                await self.db[OVR_COLL].update_one(
                    {"activation_override_id": ov["activation_override_id"]},
                    {"$set": {"status": "Expired", "updated_at": _iso()}},
                )
                expired_ids.append(ov["activation_override_id"])
                await self._event(rec["driver_activation_id"], driver_id, "Override Expired",
                                   ov.get("status"), "Expired", actor_email, "Auto-expired on recalculate",
                                   ov.get("driver_activation_item_id"), ov["activation_override_id"])
        overrides = [o for o in overrides if o["activation_override_id"] not in expired_ids]
        ov_by_item = {o["driver_activation_item_id"]: o for o in overrides}

        # Cache template items (for override_allowed policy per item)
        tpl_items = await self.db[TPL_ITEM_COLL].find(
            {"activation_template_id": rec["activation_template_id"]}, {"_id": 0},
        ).to_list(1000)
        tpl_map = {t["activation_template_item_id"]: t for t in tpl_items}

        applicable_total = 0
        mandatory_total = 0
        completed_total = 0
        mandatory_completed = 0
        outstanding_mandatory: List[dict] = []
        blocking: List[dict] = []
        override_active_count = 0

        for it in items:
            spec = tpl_map.get(it["activation_template_item_id"], {})
            prev_status = it.get("completion_status")
            if not it["applicable"]:
                new_status = "Not Applicable"
                explanation = "Not applicable to this driver"
                src_id = None
                ev_id = None
            elif it["completion_type"] in ("Manual", "Conditional Manual"):
                # Manual items — respect prior completion
                if it.get("completed_at"):
                    new_status = "Complete"
                    explanation = it.get("source_explanation") or "Manually completed"
                    src_id = it.get("source_record_id")
                    ev_id = it.get("evidence_document_id")
                else:
                    new_status = "Missing" if it["mandatory"] else "Incomplete"
                    explanation = "Awaiting manual completion"
                    src_id = None
                    ev_id = None
            elif it["completion_type"] in ("Informational",):
                new_status = "Complete"
                explanation = "Informational only"
                src_id = None
                ev_id = None
            else:  # Automatic / Conditional Automatic
                new_status, explanation, src_id, ev_id = await self._resolve_automatic(spec or it, driver)

            # Apply overrides last — never for Critical blockers
            override_active_here = False
            if it["driver_activation_item_id"] in ov_by_item and new_status not in ("Complete", "Not Applicable"):
                if spec.get("override_allowed") and new_status != "Blocked":
                    new_status = "Override Active"
                    explanation = f"OVERRIDE: {explanation}"
                    override_active_here = True

            await self.db[ITEM_COLL].update_one(
                {"driver_activation_item_id": it["driver_activation_item_id"]},
                {"$set": {
                    "completion_status": new_status,
                    "source_status": explanation,
                    "source_explanation": explanation,
                    "source_record_id": src_id,
                    "evidence_document_id": ev_id if ev_id else it.get("evidence_document_id"),
                    "last_checked_at": _iso(),
                    "updated_at": _iso(),
                }},
            )
            if prev_status != new_status:
                event = {
                    "Complete": "Item Completed",
                    "Missing": "Item Became Missing",
                    "Expired": "Item Became Expired",
                    "Incomplete": "Item Became Incomplete",
                    "Not Applicable": "Item Became Not Applicable",
                }.get(new_status, "Item Assessed")
                await self._event(rec["driver_activation_id"], driver_id, event,
                                   prev_status, new_status, actor_email, explanation,
                                   it["driver_activation_item_id"], None)

            # Counters
            if it["applicable"]:
                applicable_total += 1
                if it["mandatory"]:
                    mandatory_total += 1
                if new_status in ("Complete", "Override Active"):
                    completed_total += 1
                    if it["mandatory"]:
                        mandatory_completed += 1
                if override_active_here:
                    override_active_count += 1
                if it["mandatory"] and new_status not in ("Complete", "Override Active"):
                    outstanding_mandatory.append({
                        "driver_activation_item_id": it["driver_activation_item_id"],
                        "item_key": it["item_key"],
                        "label": it["label_snapshot"],
                        "status": new_status,
                    })
                if new_status == "Blocked":
                    blocking.append({
                        "driver_activation_item_id": it["driver_activation_item_id"],
                        "item_key": it["item_key"],
                        "label": it["label_snapshot"],
                        "reason": explanation,
                    })

        # Determine readiness
        rec_status_prev = rec.get("readiness_status")
        driver_now = await self.db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if driver_now.get("is_archived"):
            readiness = "Blocked"
            record_status = "Activation Blocked"
        elif blocking:
            readiness = "Blocked"
            record_status = "Activation Blocked"
        elif not outstanding_mandatory:
            readiness = "Ready with Override" if override_active_count > 0 else "Ready"
            record_status = rec.get("status") if rec.get("status") in ("Activated",) else "Ready"
        else:
            readiness = "Incomplete"
            record_status = "In Progress"

        # Preserve Activated status if driver still active + no blockers
        if rec.get("status") == "Activated" and readiness in ("Ready", "Ready with Override"):
            record_status = "Activated"
            readiness = "Activated"
        elif rec.get("status") == "Activated" and readiness == "Blocked":
            record_status = "Activation Blocked"

        await self.db[REC_COLL].update_one(
            {"driver_activation_id": rec["driver_activation_id"]},
            {"$set": {
                "status": record_status,
                "readiness_status": readiness,
                "applicable_item_count": applicable_total,
                "completed_item_count": completed_total,
                "mandatory_item_count": mandatory_total,
                "mandatory_completed_count": mandatory_completed,
                "outstanding_mandatory_count": len(outstanding_mandatory),
                "override_count": override_active_count,
                "last_calculated_at": _iso(),
                "updated_at": _iso(),
                "updated_by": actor_email,
                "ready_at": _iso() if readiness in ("Ready", "Ready with Override") and rec.get("ready_at") is None else rec.get("ready_at"),
            }},
        )
        if rec_status_prev != readiness:
            if readiness in ("Ready", "Ready with Override"):
                await self._event(rec["driver_activation_id"], driver_id, "Driver Became Ready",
                                   rec_status_prev, readiness, actor_email)
                await _emit_notification(self.db, "activation.ready", driver_id, rec["driver_activation_id"], f"Driver ready: {readiness}")
            elif readiness == "Blocked":
                await self._event(rec["driver_activation_id"], driver_id, "Activation Blocked",
                                   rec_status_prev, readiness, actor_email)
                await _emit_notification(self.db, "activation.blocked", driver_id, rec["driver_activation_id"], "Activation blocked")
            elif readiness == "Incomplete":
                await _emit_notification(self.db, "activation.incomplete", driver_id, rec["driver_activation_id"], "Activation incomplete")

        await self._event(rec["driver_activation_id"], driver_id, "Recalculated",
                           rec_status_prev, readiness, actor_email)

        return await self.get_full(driver_id)

    # ── Full read ────────────────────────────────────────────────────────
    async def get_full(self, driver_id: str) -> dict:
        rec = await self.db[REC_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        if not rec:
            return {"record": None, "items": [], "overrides": [], "blocking": [], "outstanding_mandatory": []}
        items = await self.db[ITEM_COLL].find(
            {"driver_activation_id": rec["driver_activation_id"]}, {"_id": 0},
        ).to_list(1000)
        # Sort by category then original display_order via join to templates
        tpl_items = await self.db[TPL_ITEM_COLL].find(
            {"activation_template_id": rec["activation_template_id"]}, {"_id": 0, "activation_template_item_id": 1, "display_order": 1, "override_allowed": 1, "override_max_days": 1, "evidence_required": 1},
        ).to_list(1000)
        tpl_map = {t["activation_template_item_id"]: t for t in tpl_items}
        for it in items:
            spec = tpl_map.get(it["activation_template_item_id"], {})
            it["display_order"] = spec.get("display_order", 999)
            it["override_allowed"] = spec.get("override_allowed", False)
            it["override_max_days"] = spec.get("override_max_days", 30)
            it["evidence_required"] = spec.get("evidence_required", False)
        items.sort(key=lambda x: (x["category"], x.get("display_order", 999)))
        overrides = await self.db[OVR_COLL].find(
            {"driver_activation_id": rec["driver_activation_id"], "is_archived": {"$ne": True}}, {"_id": 0},
        ).sort("created_at", -1).to_list(500)
        blocking = [i for i in items if i["completion_status"] == "Blocked"]
        outstanding_mandatory = [i for i in items if i["mandatory"] and i["applicable"] and i["completion_status"] not in ("Complete", "Override Active", "Not Applicable")]
        return {"record": rec, "items": items, "overrides": overrides,
                "blocking": blocking, "outstanding_mandatory": outstanding_mandatory}


# ─── Notification helper (dedup by dedup_key + entity) ───────────────────────
async def _emit_notification(db, rule_key: str, driver_id: str, activation_id: str, message: str):
    dedup = f"{rule_key}:{driver_id}:{activation_id}"
    existing = await db[NOTIFS_COLL].find_one({"dedup_key": dedup, "status": {"$in": ["Active", "Acknowledged"]}})
    if existing:
        await db[NOTIFS_COLL].update_one(
            {"id": existing["id"]},
            {"$set": {"last_triggered_at": _iso(), "message": message}},
        )
        return
    await db[NOTIFS_COLL].insert_one({
        "id": _uuid(),
        "notification_id": _uuid(),
        "dedup_key": dedup,
        "entity_type": "Driver",
        "entity_id": driver_id,
        "rule_key": rule_key,
        "severity": "warning" if rule_key != "activation.ready" else "info",
        "status": "Active",
        "title": message,
        "message": message,
        "last_triggered_at": _iso(),
        "created_at": _iso(),
        "updated_at": _iso(),
        "is_archived": False,
        "_source": SEED_TAG,
    })


# ═══════════════════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════════════════
def build_activation_router(db, get_current_user):
    router = APIRouter(prefix="/api")
    svc = ActivationService(db)

    # ---- Templates ---------------------------------------------------------
    @router.get("/activation/templates")
    async def list_templates(include_archived: bool = False, current=Depends(get_current_user)):
        q = {} if include_archived else {"is_archived": {"$ne": True}}
        rows = await db[TPL_COLL].find(q, {"_id": 0}).sort("version", -1).to_list(500)
        for t in rows:
            t["item_count"] = await db[TPL_ITEM_COLL].count_documents(
                {"activation_template_id": t["activation_template_id"], "is_active": True, "is_archived": {"$ne": True}}
            )
            t["mandatory_count"] = await db[TPL_ITEM_COLL].count_documents(
                {"activation_template_id": t["activation_template_id"], "is_active": True, "mandatory": True, "is_archived": {"$ne": True}}
            )
        return rows

    @router.post("/activation/templates")
    async def create_template(payload: TemplatePayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        if payload.driver_type not in DRIVER_TYPES:
            raise HTTPException(status_code=400, detail=f"driver_type must be one of {DRIVER_TYPES}")
        now = _iso()
        # If is_default, unset previous default in that company/type
        if payload.is_default:
            await db[TPL_COLL].update_many(
                {"company_ref": payload.company_ref, "driver_type": payload.driver_type,
                 "is_default": True, "is_archived": {"$ne": True}},
                {"$set": {"is_default": False, "updated_at": now}},
            )
        doc = {
            "activation_template_id": _uuid(),
            **payload.model_dump(),
            "version": 1,
            "is_active": True,
            "created_at": now, "updated_at": now,
            "created_by": current["email"], "updated_by": current["email"],
            "is_archived": False,
        }
        await db[TPL_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.get("/activation/templates/{tpl_id}")
    async def get_template(tpl_id: str, current=Depends(get_current_user)):
        t = await db[TPL_COLL].find_one({"activation_template_id": tpl_id}, {"_id": 0})
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        return t

    @router.put("/activation/templates/{tpl_id}")
    async def update_template(tpl_id: str, payload: TemplatePayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        t = await db[TPL_COLL].find_one({"activation_template_id": tpl_id}, {"_id": 0})
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        now = _iso()
        if payload.is_default and not t.get("is_default"):
            await db[TPL_COLL].update_many(
                {"company_ref": payload.company_ref, "driver_type": payload.driver_type,
                 "is_default": True, "is_archived": {"$ne": True},
                 "activation_template_id": {"$ne": tpl_id}},
                {"$set": {"is_default": False, "updated_at": now}},
            )
        await db[TPL_COLL].update_one(
            {"activation_template_id": tpl_id},
            {"$set": {**payload.model_dump(), "updated_at": now, "updated_by": current["email"]}},
        )
        return await db[TPL_COLL].find_one({"activation_template_id": tpl_id}, {"_id": 0})

    @router.delete("/activation/templates/{tpl_id}")
    async def archive_template(tpl_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        r = await db[TPL_COLL].update_one(
            {"activation_template_id": tpl_id},
            {"$set": {"is_archived": True, "is_active": False, "is_default": False, "updated_at": _iso(), "updated_by": current["email"]}},
        )
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"status": "archived"}

    @router.post("/activation/templates/{tpl_id}/clone")
    async def clone_template(tpl_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        src = await db[TPL_COLL].find_one({"activation_template_id": tpl_id}, {"_id": 0})
        if not src:
            raise HTTPException(status_code=404, detail="Template not found")
        max_ver = await db[TPL_COLL].find_one(
            {"company_ref": src["company_ref"], "driver_type": src["driver_type"]},
            {"_id": 0, "version": 1}, sort=[("version", -1)],
        )
        new_ver = (max_ver.get("version", 1) if max_ver else 1) + 1
        new_id = _uuid()
        now = _iso()
        new_tpl = {**src, "activation_template_id": new_id,
                    "version": new_ver, "is_default": False, "is_active": True,
                    "created_at": now, "updated_at": now,
                    "created_by": current["email"], "updated_by": current["email"],
                    "is_archived": False,
                    "name": f"{src['name']} v{new_ver}"}
        new_tpl.pop("_id", None)
        await db[TPL_COLL].insert_one(new_tpl)
        # Deep-clone items
        specs = await db[TPL_ITEM_COLL].find(
            {"activation_template_id": tpl_id, "is_archived": {"$ne": True}}, {"_id": 0},
        ).to_list(1000)
        for s in specs:
            s2 = {**s, "activation_template_item_id": _uuid(),
                   "activation_template_id": new_id,
                   "created_at": now, "updated_at": now,
                   "created_by": current["email"], "updated_by": current["email"]}
            s2.pop("_id", None)
            await db[TPL_ITEM_COLL].insert_one(s2)
        return await db[TPL_COLL].find_one({"activation_template_id": new_id}, {"_id": 0})

    # ---- Template items ----------------------------------------------------
    @router.get("/activation/templates/{tpl_id}/items")
    async def list_items(tpl_id: str, include_archived: bool = False, current=Depends(get_current_user)):
        q = {"activation_template_id": tpl_id}
        if not include_archived:
            q["is_archived"] = {"$ne": True}
        rows = await db[TPL_ITEM_COLL].find(q, {"_id": 0}).sort("display_order", 1).to_list(1000)
        return rows

    @router.post("/activation/templates/{tpl_id}/items")
    async def add_item(tpl_id: str, payload: TemplateItemPayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        if payload.category not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"category must be one of {CATEGORIES}")
        if payload.completion_type not in COMPLETION_TYPES:
            raise HTTPException(status_code=400, detail=f"completion_type must be one of {COMPLETION_TYPES}")
        if payload.override_allowed and payload.override_max_days < 1:
            raise HTTPException(status_code=400, detail="Override maximum days must be > 0")
        if payload.conditional and not payload.condition_rule:
            raise HTTPException(status_code=400, detail="Conditional items require condition_rule")
        # Item key uniqueness within template
        existing_key = await db[TPL_ITEM_COLL].find_one(
            {"activation_template_id": tpl_id, "item_key": payload.item_key,
             "is_archived": {"$ne": True}},
        )
        if existing_key:
            raise HTTPException(status_code=400, detail=f"Item key '{payload.item_key}' already exists in this template")
        now = _iso()
        doc = {
            "activation_template_item_id": _uuid(),
            "activation_template_id": tpl_id,
            **payload.model_dump(),
            "is_active": True,
            "created_at": now, "updated_at": now,
            "created_by": current["email"], "updated_by": current["email"],
            "is_archived": False,
        }
        await db[TPL_ITEM_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.put("/activation/template-items/{item_id}")
    async def update_item(item_id: str, payload: TemplateItemPayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        existing = await db[TPL_ITEM_COLL].find_one({"activation_template_item_id": item_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Item not found")
        if payload.category not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"category must be one of {CATEGORIES}")
        if payload.completion_type not in COMPLETION_TYPES:
            raise HTTPException(status_code=400, detail=f"completion_type must be one of {COMPLETION_TYPES}")
        if payload.override_allowed and payload.override_max_days < 1:
            raise HTTPException(status_code=400, detail="Override maximum days must be > 0")
        if payload.conditional and not payload.condition_rule:
            raise HTTPException(status_code=400, detail="Conditional items require condition_rule")
        # Critical-defect protection: source_entity_type=vehicle_defect can never become overrideable
        if payload.source_entity_type == "vehicle_defect" and payload.override_allowed:
            raise HTTPException(status_code=400, detail="Critical-defect items cannot be overrideable")
        # Item key uniqueness within template (excluding self)
        if payload.item_key != existing["item_key"]:
            dup = await db[TPL_ITEM_COLL].find_one(
                {"activation_template_id": existing["activation_template_id"],
                 "item_key": payload.item_key,
                 "activation_template_item_id": {"$ne": item_id},
                 "is_archived": {"$ne": True}},
            )
            if dup:
                raise HTTPException(status_code=400, detail=f"Item key '{payload.item_key}' already exists in this template")
            # If the template is locked (has driver activation records), item_key changes are structural
            locked_count = await db[REC_COLL].count_documents(
                {"activation_template_id": existing["activation_template_id"], "is_archived": {"$ne": True}}
            )
            if locked_count > 0:
                raise HTTPException(status_code=400, detail="Template is locked (in use by Drivers) — clone a new version to change item keys")
        await db[TPL_ITEM_COLL].update_one(
            {"activation_template_item_id": item_id},
            {"$set": {**payload.model_dump(), "updated_at": _iso(), "updated_by": current["email"]}},
        )
        return await db[TPL_ITEM_COLL].find_one({"activation_template_item_id": item_id}, {"_id": 0})

    @router.delete("/activation/template-items/{item_id}")
    async def archive_item(item_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        r = await db[TPL_ITEM_COLL].update_one(
            {"activation_template_item_id": item_id},
            {"$set": {"is_archived": True, "is_active": False, "updated_at": _iso(), "updated_by": current["email"]}},
        )
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"status": "archived"}

    @router.post("/activation/template-items/{item_id}/restore")
    async def restore_item(item_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        r = await db[TPL_ITEM_COLL].update_one(
            {"activation_template_item_id": item_id},
            {"$set": {"is_archived": False, "is_active": True, "updated_at": _iso(), "updated_by": current["email"]}},
        )
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Item not found")
        return await db[TPL_ITEM_COLL].find_one({"activation_template_item_id": item_id}, {"_id": 0})

    @router.post("/activation/template-items/{item_id}/duplicate")
    async def duplicate_item(item_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        src = await db[TPL_ITEM_COLL].find_one({"activation_template_item_id": item_id}, {"_id": 0})
        if not src:
            raise HTTPException(status_code=404, detail="Item not found")
        # Unique key
        base_key = src["item_key"]
        suffix = 1
        new_key = f"{base_key}.copy{suffix}"
        while await db[TPL_ITEM_COLL].find_one(
            {"activation_template_id": src["activation_template_id"], "item_key": new_key}
        ):
            suffix += 1
            new_key = f"{base_key}.copy{suffix}"
        now = _iso()
        new_item = {**src, "activation_template_item_id": _uuid(),
                     "item_key": new_key, "label": f"{src['label']} (Copy)",
                     "display_order": src.get("display_order", 0) + 1,
                     "created_at": now, "updated_at": now,
                     "created_by": current["email"], "updated_by": current["email"],
                     "is_archived": False, "is_active": True}
        new_item.pop("_id", None)
        # Shift subsequent items to make room
        await db[TPL_ITEM_COLL].update_many(
            {"activation_template_id": src["activation_template_id"],
             "display_order": {"$gt": src.get("display_order", 0)}},
            {"$inc": {"display_order": 1}},
        )
        await db[TPL_ITEM_COLL].insert_one(new_item)
        new_item.pop("_id", None)
        return new_item

    @router.post("/activation/templates/{tpl_id}/items/reorder")
    async def reorder_items(tpl_id: str, payload: Dict[str, Any], current=Depends(get_current_user)):
        _require(current["role"], ROLE_MANAGE_TEMPLATES)
        order = payload.get("order") or []
        if not isinstance(order, list) or not order:
            raise HTTPException(status_code=400, detail="order must be a non-empty list of item ids")
        # Load existing items in this template to validate
        rows = await db[TPL_ITEM_COLL].find(
            {"activation_template_id": tpl_id}, {"_id": 0, "activation_template_item_id": 1},
        ).to_list(1000)
        valid_ids = {r["activation_template_item_id"] for r in rows}
        for i, iid in enumerate(order):
            if iid not in valid_ids:
                raise HTTPException(status_code=400, detail=f"Unknown item id in order: {iid}")
            await db[TPL_ITEM_COLL].update_one(
                {"activation_template_item_id": iid},
                {"$set": {"display_order": i, "updated_at": _iso(), "updated_by": current["email"]}},
            )
        return {"status": "ok", "count": len(order)}

    @router.get("/activation/templates/{tpl_id}/usage")
    async def template_usage(tpl_id: str, current=Depends(get_current_user)):
        """Report how many Driver activation records reference this template."""
        used_by = await db[REC_COLL].count_documents({"activation_template_id": tpl_id})
        # Locked = at least one non-archived driver activation uses this template.
        locked = await db[REC_COLL].count_documents(
            {"activation_template_id": tpl_id, "is_archived": {"$ne": True}}
        ) > 0
        latest_version = await db[TPL_COLL].find_one(
            {"activation_template_id": tpl_id}, {"_id": 0, "version": 1},
        )
        return {"activation_template_id": tpl_id,
                "used_by_activation_records": used_by,
                "locked": locked,
                "version": (latest_version or {}).get("version", 1)}

    # ---- Driver activation -------------------------------------------------
    @router.get("/drivers/{driver_id}/activation")
    async def get_driver_activation(driver_id: str, current=Depends(get_current_user)):
        drv = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0, "id": 1})
        if not drv:
            raise HTTPException(status_code=404, detail="Driver not found")
        return await svc.get_full(driver_id)

    @router.post("/drivers/{driver_id}/activation/start")
    async def start(driver_id: str, current=Depends(get_current_user)):
        _require(current["role"], {"Admin", "Manager", "Allocator"})
        rec, created = await svc.get_or_start(driver_id, current["email"])
        return await svc.recalculate(driver_id, current["email"])

    @router.post("/drivers/{driver_id}/activation/recalculate")
    async def recalc(driver_id: str, current=Depends(get_current_user)):
        return await svc.recalculate(driver_id, current["email"])

    @router.post("/drivers/{driver_id}/activation/activate")
    async def activate(driver_id: str, payload: ActivatePayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_ACTIVATE, "Only Manager or Admin may activate a driver")
        drv = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not drv:
            raise HTTPException(status_code=404, detail="Driver not found")
        if drv.get("is_archived"):
            raise HTTPException(status_code=400, detail="Archived driver cannot be activated")
        full = await svc.recalculate(driver_id, current["email"])
        rec = full["record"]
        if rec["readiness_status"] not in ("Ready", "Ready with Override", "Activated"):
            raise HTTPException(status_code=400, detail=f"Driver not ready: {rec['readiness_status']}")
        if not drv.get("driver_code"):
            raise HTTPException(status_code=400, detail="Driver Code missing — cannot activate")
        now = _iso()
        await db[REC_COLL].update_one(
            {"driver_activation_id": rec["driver_activation_id"]},
            {"$set": {"status": "Activated", "readiness_status": "Activated",
                      "activated_at": now, "activated_by": current["email"],
                      "activation_reason": payload.reason, "updated_at": now}},
        )
        if payload.set_driver_status_active:
            await db[DRIVERS_COLL].update_one(
                {"id": driver_id},
                {"$set": {"driver_status": "Active", "updated_at": now}},
            )
        await svc._event(rec["driver_activation_id"], driver_id, "Driver Activated",
                          rec["readiness_status"], "Activated", current["email"], payload.reason)
        await _emit_notification(db, "activation.activated", driver_id, rec["driver_activation_id"], "Driver activated")
        return await svc.get_full(driver_id)

    @router.post("/drivers/{driver_id}/activation/deactivate")
    async def deactivate(driver_id: str, payload: DeactivatePayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_ACTIVATE, "Only Manager or Admin may deactivate a driver")
        rec = await db[REC_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="No activation record")
        now = _iso()
        await db[REC_COLL].update_one(
            {"driver_activation_id": rec["driver_activation_id"]},
            {"$set": {"status": "Deactivated", "readiness_status": "Deactivated",
                      "deactivated_at": now, "deactivated_by": current["email"],
                      "deactivation_reason": payload.reason, "updated_at": now}},
        )
        await db[DRIVERS_COLL].update_one(
            {"id": driver_id},
            {"$set": {"driver_status": "Inactive", "updated_at": now}},
        )
        await svc._event(rec["driver_activation_id"], driver_id, "Driver Deactivated",
                          rec["readiness_status"], "Deactivated", current["email"], payload.reason)
        await _emit_notification(db, "activation.deactivated", driver_id, rec["driver_activation_id"], "Driver deactivated")
        return await svc.get_full(driver_id)

    @router.post("/drivers/{driver_id}/activation/reactivate")
    async def reactivate(driver_id: str, payload: ActivatePayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_ACTIVATE)
        rec = await db[REC_COLL].find_one({"driver_id": driver_id, "is_archived": {"$ne": True}}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="No activation record")
        if rec["status"] != "Deactivated":
            raise HTTPException(status_code=400, detail="Driver is not deactivated")
        now = _iso()
        # Reset activation-facing fields but keep history events
        await db[REC_COLL].update_one(
            {"driver_activation_id": rec["driver_activation_id"]},
            {"$set": {"status": "In Progress", "readiness_status": "Not Assessed",
                      "deactivated_at": None, "deactivated_by": None,
                      "deactivation_reason": None, "updated_at": now}},
        )
        await svc._event(rec["driver_activation_id"], driver_id, "Driver Reactivated",
                          "Deactivated", "In Progress", current["email"], payload.reason)
        return await svc.recalculate(driver_id, current["email"])

    @router.get("/drivers/{driver_id}/activation/history")
    async def history(driver_id: str, current=Depends(get_current_user)):
        rec = await db[REC_COLL].find_one({"driver_id": driver_id}, {"_id": 0})
        if not rec:
            return {"events": []}
        events = await db[EVT_COLL].find(
            {"driver_activation_id": rec["driver_activation_id"]}, {"_id": 0},
        ).sort("performed_at", -1).to_list(1000)
        return {"events": events}

    @router.get("/drivers/{driver_id}/activation/items")
    async def list_driver_items(driver_id: str, current=Depends(get_current_user)):
        full = await svc.get_full(driver_id)
        return full["items"]

    # ---- Manual complete / reopen -----------------------------------------
    @router.put("/driver-activation-items/{item_id}/manual-complete")
    async def manual_complete(item_id: str, payload: ManualCompletePayload, current=Depends(get_current_user)):
        role = current["role"]
        _require(role, ROLE_MANUAL_COMPLETE)
        it = await db[ITEM_COLL].find_one({"driver_activation_item_id": item_id}, {"_id": 0})
        if not it:
            raise HTTPException(status_code=404, detail="Item not found")
        if it["completion_type"] not in ("Manual", "Conditional Manual"):
            raise HTTPException(status_code=400, detail="Automatic items cannot be manually completed")
        cat = it.get("category")
        gate = CATEGORY_ROLE_MANUAL.get(cat)
        if gate and role not in gate:
            raise HTTPException(status_code=403, detail=f"Insufficient permissions for {cat} items")
        now = _iso()
        await db[ITEM_COLL].update_one(
            {"driver_activation_item_id": item_id},
            {"$set": {"completed_at": now, "completed_by": current["email"],
                      "manual_note": payload.manual_note,
                      "evidence_document_id": payload.evidence_document_id,
                      "completion_status": "Complete",
                      "source_explanation": payload.manual_note or "Manually completed",
                      "updated_at": now}},
        )
        rec = await db[REC_COLL].find_one({"driver_activation_id": it["driver_activation_id"]}, {"_id": 0})
        await svc._event(it["driver_activation_id"], it["driver_id"], "Item Completed",
                          it["completion_status"], "Complete", current["email"],
                          payload.manual_note or "manual", item_id, None)
        return await svc.recalculate(it["driver_id"], current["email"])

    @router.put("/driver-activation-items/{item_id}/manual-reopen")
    async def manual_reopen(item_id: str, current=Depends(get_current_user)):
        role = current["role"]
        _require(role, ROLE_MANUAL_COMPLETE)
        it = await db[ITEM_COLL].find_one({"driver_activation_item_id": item_id}, {"_id": 0})
        if not it:
            raise HTTPException(status_code=404, detail="Item not found")
        if it["completion_type"] not in ("Manual", "Conditional Manual"):
            raise HTTPException(status_code=400, detail="Automatic items cannot be manually reopened")
        cat = it.get("category")
        gate = CATEGORY_ROLE_MANUAL.get(cat)
        if gate and role not in gate:
            raise HTTPException(status_code=403, detail=f"Insufficient permissions for {cat} items")
        now = _iso()
        await db[ITEM_COLL].update_one(
            {"driver_activation_item_id": item_id},
            {"$set": {"completed_at": None, "completed_by": None,
                      "manual_note": None, "completion_status": "Incomplete",
                      "source_explanation": "Manually reopened", "updated_at": now}},
        )
        await svc._event(it["driver_activation_id"], it["driver_id"], "Item Became Incomplete",
                          "Complete", "Incomplete", current["email"], "manual reopen", item_id, None)
        return await svc.recalculate(it["driver_id"], current["email"])

    # ---- Overrides ---------------------------------------------------------
    @router.post("/driver-activation-items/{item_id}/override-request")
    async def override_request(item_id: str, payload: OverrideRequestPayload, current=Depends(get_current_user)):
        _require(current["role"], ROLE_REQUEST_OVERRIDE)
        if not payload.risk_acknowledgement:
            raise HTTPException(status_code=400, detail="Risk acknowledgement required")
        it = await db[ITEM_COLL].find_one({"driver_activation_item_id": item_id}, {"_id": 0})
        if not it:
            raise HTTPException(status_code=404, detail="Item not found")
        tpl_item = await db[TPL_ITEM_COLL].find_one(
            {"activation_template_item_id": it["activation_template_item_id"]}, {"_id": 0},
        )
        if not tpl_item or not tpl_item.get("override_allowed"):
            raise HTTPException(status_code=400, detail="This item cannot be overridden")
        if it["completion_status"] == "Blocked":
            raise HTTPException(status_code=400, detail="Critical blockers cannot be overridden")
        max_days = int(tpl_item.get("override_max_days", 30))
        if payload.requested_expiry_days > max_days:
            raise HTTPException(status_code=400, detail=f"Expiry cannot exceed {max_days} days")
        now = _now()
        expiry = now + timedelta(days=payload.requested_expiry_days)
        ovr = {
            "activation_override_id": _uuid(),
            "driver_activation_id": it["driver_activation_id"],
            "driver_activation_item_id": item_id,
            "driver_id": it["driver_id"],
            "reason": payload.reason,
            "risk_acknowledgement": True,
            "approved_by": None, "approved_at": None,
            "requested_by": current["email"],
            "expires_at": expiry.isoformat(),
            "status": "Requested",
            "revoked_by": None, "revoked_at": None, "revocation_reason": None,
            "created_at": _iso(), "updated_at": _iso(),
            "is_archived": False,
        }
        await db[OVR_COLL].insert_one(ovr)
        ovr.pop("_id", None)
        await svc._event(it["driver_activation_id"], it["driver_id"], "Override Requested",
                          None, "Requested", current["email"], payload.reason, item_id, ovr["activation_override_id"])
        return ovr

    @router.post("/activation-overrides/{ovr_id}/approve")
    async def approve_override(ovr_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_APPROVE_OVERRIDE, "Only Manager or Admin may approve overrides")
        ovr = await db[OVR_COLL].find_one({"activation_override_id": ovr_id}, {"_id": 0})
        if not ovr:
            raise HTTPException(status_code=404, detail="Override not found")
        if ovr["status"] != "Requested":
            raise HTTPException(status_code=400, detail=f"Cannot approve override in status {ovr['status']}")
        if ovr.get("requested_by") == current["email"] and current["role"] != "Admin":
            raise HTTPException(status_code=403, detail="Users cannot approve their own override request")
        now = _iso()
        await db[OVR_COLL].update_one(
            {"activation_override_id": ovr_id},
            {"$set": {"status": "Active", "approved_by": current["email"],
                      "approved_at": now, "updated_at": now}},
        )
        await svc._event(ovr["driver_activation_id"], ovr["driver_id"], "Override Approved",
                          "Requested", "Active", current["email"], ovr["reason"],
                          ovr["driver_activation_item_id"], ovr_id)
        await _emit_notification(db, "activation.override.approved", ovr["driver_id"], ovr["driver_activation_id"], "Override approved")
        return await svc.recalculate(ovr["driver_id"], current["email"])

    @router.post("/activation-overrides/{ovr_id}/reject")
    async def reject_override(ovr_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_APPROVE_OVERRIDE)
        ovr = await db[OVR_COLL].find_one({"activation_override_id": ovr_id}, {"_id": 0})
        if not ovr:
            raise HTTPException(status_code=404, detail="Override not found")
        if ovr["status"] != "Requested":
            raise HTTPException(status_code=400, detail=f"Cannot reject override in status {ovr['status']}")
        await db[OVR_COLL].update_one(
            {"activation_override_id": ovr_id},
            {"$set": {"status": "Rejected", "approved_by": current["email"],
                      "approved_at": _iso(), "updated_at": _iso()}},
        )
        await svc._event(ovr["driver_activation_id"], ovr["driver_id"], "Override Rejected",
                          "Requested", "Rejected", current["email"], ovr["reason"],
                          ovr["driver_activation_item_id"], ovr_id)
        return await svc.recalculate(ovr["driver_id"], current["email"])

    @router.post("/activation-overrides/{ovr_id}/revoke")
    async def revoke_override(ovr_id: str, current=Depends(get_current_user)):
        _require(current["role"], ROLE_APPROVE_OVERRIDE)
        ovr = await db[OVR_COLL].find_one({"activation_override_id": ovr_id}, {"_id": 0})
        if not ovr:
            raise HTTPException(status_code=404, detail="Override not found")
        if ovr["status"] not in ("Active", "Approved"):
            raise HTTPException(status_code=400, detail="Only active overrides can be revoked")
        await db[OVR_COLL].update_one(
            {"activation_override_id": ovr_id},
            {"$set": {"status": "Revoked", "revoked_by": current["email"],
                      "revoked_at": _iso(), "updated_at": _iso()}},
        )
        await svc._event(ovr["driver_activation_id"], ovr["driver_id"], "Override Revoked",
                          "Active", "Revoked", current["email"], "revoked",
                          ovr["driver_activation_item_id"], ovr_id)
        return await svc.recalculate(ovr["driver_id"], current["email"])

    @router.get("/drivers/{driver_id}/activation/overrides")
    async def list_driver_overrides(driver_id: str, current=Depends(get_current_user)):
        rec = await db[REC_COLL].find_one({"driver_id": driver_id}, {"_id": 0})
        if not rec:
            return []
        return await db[OVR_COLL].find(
            {"driver_activation_id": rec["driver_activation_id"], "is_archived": {"$ne": True}},
            {"_id": 0},
        ).sort("created_at", -1).to_list(500)

    # ---- Jobs -------------------------------------------------------------
    async def _record_job(job_type: str, actor: str, counts: dict, failures: List[str]):
        doc = {
            "job_id": _uuid(),
            "job_type": job_type,
            "started_at": _iso(),
            "completed_at": _iso(),
            "counts": counts,
            "failures": failures,
            "performed_by": actor,
            "correlation_id": _uuid(),
        }
        await db[JOB_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.post("/activation/jobs/recalculate-all")
    async def job_recalc_all(current=Depends(get_current_user)):
        _require(current["role"], ROLE_RUN_JOBS)
        recs = await db[REC_COLL].find({"is_archived": {"$ne": True}}, {"_id": 0, "driver_id": 1}).to_list(2000)
        ok, fail = 0, []
        for r in recs:
            try:
                await svc.recalculate(r["driver_id"], current["email"])
                ok += 1
            except Exception as e:
                fail.append(f"{r['driver_id']}: {e}")
        return await _record_job("recalculate-all", current["email"], {"processed": len(recs), "ok": ok}, fail)

    @router.post("/activation/jobs/expire-overrides")
    async def job_expire(current=Depends(get_current_user)):
        _require(current["role"], ROLE_RUN_JOBS)
        now = _now().isoformat()
        cursor = db[OVR_COLL].find(
            {"status": {"$in": ["Active", "Approved"]}, "expires_at": {"$lt": now},
             "is_archived": {"$ne": True}}, {"_id": 0},
        )
        touched = 0
        async for ovr in cursor:
            await db[OVR_COLL].update_one(
                {"activation_override_id": ovr["activation_override_id"]},
                {"$set": {"status": "Expired", "updated_at": _iso()}},
            )
            await svc._event(ovr["driver_activation_id"], ovr["driver_id"], "Override Expired",
                              ovr["status"], "Expired", current["email"], "Job expiry",
                              ovr["driver_activation_item_id"], ovr["activation_override_id"])
            await svc.recalculate(ovr["driver_id"], current["email"])
            touched += 1
        return await _record_job("expire-overrides", current["email"], {"expired": touched}, [])

    @router.post("/activation/jobs/reconcile")
    async def job_reconcile(current=Depends(get_current_user)):
        _require(current["role"], ROLE_RUN_JOBS)
        # Ensure every non-archived driver has a record (idempotent).
        drivers = await db[DRIVERS_COLL].find(
            {"is_archived": {"$ne": True}}, {"_id": 0, "id": 1},
        ).to_list(5000)
        created = 0
        for d in drivers:
            rec = await db[REC_COLL].find_one({"driver_id": d["id"]})
            if not rec:
                await svc.get_or_start(d["id"], current["email"])
                created += 1
        return await _record_job("reconcile", current["email"], {"drivers": len(drivers), "created": created}, [])

    @router.get("/activation/jobs")
    async def list_jobs(current=Depends(get_current_user)):
        return await db[JOB_COLL].find({}, {"_id": 0}).sort("started_at", -1).to_list(200)

    return router
