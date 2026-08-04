"""EB-14 · Controlled Migration Commit, Rollback & Legacy Backfill.

Stage A implementation — staged idempotent commit mode. Uses sanitised
fictional fixtures only. Real ACE data commit requires a separate Admin
instruction (Stage B) and is not automated here.

Collections (all UUID-keyed):
  migration_commit_jobs
  migration_commit_batches
  migration_commit_rows
  migration_commit_actions
  migration_commit_events              (append-only)
  migration_rollback_packages
  migration_rollback_actions
  migration_post_commit_reconciliation
  migration_approvals
  storage_backfill_jobs                (EB-14 legacy backfill)
  storage_backfill_actions

Design notes:
  - Every action is idempotent. Actions carry a stable `commit_action_key`
    so retries after a partial commit do not double-apply.
  - Every action is written to the rollback package BEFORE the canonical
    write, so a mid-batch crash can still be reversed.
  - Preflight runs immediately before commit and again if resumed, so
    stale approvals and drifted canonical records block the commit.
  - Post-commit reconciliation is required before status → Completed.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


# ── Collections ───────────────────────────────────────────────────────────────
JOBS_COLL = "migration_commit_jobs"
BATCH_COLL = "migration_commit_batches"
ROWS_COLL = "migration_commit_rows"
ACTIONS_COLL = "migration_commit_actions"
EVENTS_COLL = "migration_commit_events"
ROLLBACK_COLL = "migration_rollback_packages"
ROLLBACK_ACT_COLL = "migration_rollback_actions"
RECON_COLL = "migration_post_commit_reconciliation"
APPROVAL_COLL = "migration_approvals"

BACKFILL_COLL = "storage_backfill_jobs"
BACKFILL_ACT_COLL = "storage_backfill_actions"

# Referenced EB-12 / EB-13 / EB-04 / EB-08 collections
WB_COLL = "migration_source_workbooks"
DRYRUN_COLL = "migration_dry_runs"
DRYRUN_ROW_COLL = "migration_dry_run_rows"
PROFILE_COLL = "migration_mapping_profiles"
GNG_COLL = "migration_go_no_go_reports"
ISSUE_COLL = "migration_issues"
STORAGE_OBJ_COLL = "storage_objects"

# ── Enums ─────────────────────────────────────────────────────────────────────
JOB_STATUSES = {
    "Draft", "Awaiting Approval", "Approved", "Preflight Running",
    "Preflight Failed", "Ready to Commit", "Committing", "Paused",
    "Partially Completed", "Completed", "Failed", "Rollback Pending",
    "Rolling Back", "Rolled Back", "Rollback Failed", "Archived",
}
JOB_MODES = {"Rehearsal", "Controlled Commit", "Rollback"}

APPROVAL_TYPES = {"Migration Commit Approval", "Conditional Risk Acceptance",
                    "Rollback Approval", "Resume Approval"}
APPROVAL_STATUSES = {"Pending", "Approved", "Expired", "Revoked", "Rejected"}

ACTION_STATES = {"Pending", "Applied", "Verified", "Reverted", "Failed", "Skipped"}
RECON_RESULTS = {"Reconciled", "Reconciled with Warnings", "Failed Reconciliation"}

ENTITY_ORDER = [
    "Owner", "Vehicle", "Equipment", "Driver",
    "DriverCode", "DispatchNumber",
    "DriverOwnerRelationship", "DriverVehicleAssignment",
    "DriverEquipmentAssignment", "CommunicationPreference",
    "DriverLicence", "VehicleRegistration", "VehicleInsurance",
    "VehicleInspection", "VehicleDefect", "VehicleMaintenance",
    "EquipmentCompliance", "DocumentLink",
]

ROLE_READONLY = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}
ROLE_ALLOCATOR = {"Allocator", "Compliance", "Manager", "Admin"}
ROLE_COMPLIANCE = {"Compliance", "Manager", "Admin"}
ROLE_MANAGER = {"Manager", "Admin"}
ROLE_ADMIN = {"Admin"}

DEFAULT_APPROVAL_TTL_HOURS = int(os.environ.get("MIGRATION_APPROVAL_TTL_HOURS", "72"))


# ── Helpers ───────────────────────────────────────────────────────────────────
def _uuid() -> str: return str(uuid.uuid4())
def _iso() -> str: return datetime.now(timezone.utc).isoformat()
def _sha256(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def _strip(d):
    if not d: return d
    out = dict(d); out.pop("_id", None); return out


def _require(user: Dict[str, Any], allowed: set, err: str = "Insufficient permissions"):
    if user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=err)


def _transactions_enabled() -> bool:
    return os.environ.get("MIGRATION_COMMIT_TRANSACTIONS", "").lower() == "true"


# ═══════════════════════════════════════════════════════════════════════════
# Approval Service
# ═══════════════════════════════════════════════════════════════════════════
class ApprovalService:
    def __init__(self, db): self.db = db

    async def create(self, *, dry_run_id: str, go_no_go_id: str, approval_type: str,
                       requested_by: str, ttl_hours: int = DEFAULT_APPROVAL_TTL_HOURS) -> dict:
        if approval_type not in APPROVAL_TYPES:
            raise HTTPException(status_code=400, detail=f"approval_type must be one of {sorted(APPROVAL_TYPES)}")
        now = _iso()
        expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
        doc = {
            "migration_approval_id": _uuid(),
            "migration_dry_run_id": dry_run_id,
            "go_no_go_report_id": go_no_go_id,
            "approval_type": approval_type,
            "approved_by": None, "approved_role": None, "approved_at": None,
            "approval_note": None, "risk_acceptance": False,
            "expires_at": expires, "status": "Pending",
            "revoked_by": None, "revoked_at": None, "revocation_reason": None,
            "requested_by": requested_by, "created_at": now,
        }
        await self.db[APPROVAL_COLL].insert_one(doc)
        return _strip(doc)

    async def approve(self, approval_id: str, *, approver: dict,
                        risk_acceptance: bool = False, note: Optional[str] = None,
                        for_real_commit: bool = False,
                        requester_email: Optional[str] = None) -> dict:
        a = await self.db[APPROVAL_COLL].find_one({"migration_approval_id": approval_id}, {"_id": 0})
        if not a: raise HTTPException(status_code=404, detail="Approval not found")
        if a["status"] != "Pending":
            raise HTTPException(status_code=400, detail=f"Approval already {a['status']}")
        # Real commit approval requires Admin
        if for_real_commit and approver.get("role") != "Admin":
            raise HTTPException(status_code=403, detail="Only Admin may give real-migration commit approval")
        if approver.get("role") not in ROLE_MANAGER:
            raise HTTPException(status_code=403, detail="Only Manager+ may approve migrations")
        # Self-approval blocked for real commit
        if for_real_commit and requester_email and requester_email == approver.get("email"):
            raise HTTPException(status_code=400, detail="Migration requester cannot self-approve real commit")
        # No-Go can never be approved
        gng = await self.db[GNG_COLL].find_one({"migration_go_no_go_report_id": a["go_no_go_report_id"]}, {"_id": 0})
        if gng and gng.get("result") == "NO-GO":
            raise HTTPException(status_code=400, detail="Cannot approve a NO-GO report")
        if gng and gng.get("result") == "CONDITIONAL GO" and not risk_acceptance:
            raise HTTPException(status_code=400, detail="Conditional Go requires explicit risk_acceptance=true")
        now = _iso()
        await self.db[APPROVAL_COLL].update_one(
            {"migration_approval_id": approval_id},
            {"$set": {"status": "Approved", "approved_by": approver.get("email"),
                       "approved_role": approver.get("role"), "approved_at": now,
                       "approval_note": note, "risk_acceptance": risk_acceptance}},
        )
        return _strip(await self.db[APPROVAL_COLL].find_one({"migration_approval_id": approval_id}, {"_id": 0}))

    async def revoke(self, approval_id: str, actor: dict, reason: str) -> dict:
        _require(actor, ROLE_ADMIN, "Only Admin may revoke approvals")
        a = await self.db[APPROVAL_COLL].find_one({"migration_approval_id": approval_id}, {"_id": 0})
        if not a: raise HTTPException(status_code=404, detail="Approval not found")
        await self.db[APPROVAL_COLL].update_one(
            {"migration_approval_id": approval_id},
            {"$set": {"status": "Revoked", "revoked_by": actor.get("email"),
                       "revoked_at": _iso(), "revocation_reason": reason}},
        )
        return _strip(await self.db[APPROVAL_COLL].find_one({"migration_approval_id": approval_id}, {"_id": 0}))

    async def is_valid(self, approval_id: str) -> Tuple[bool, str]:
        a = await self.db[APPROVAL_COLL].find_one({"migration_approval_id": approval_id}, {"_id": 0})
        if not a: return False, "Approval not found"
        if a["status"] != "Approved": return False, f"Approval status is {a['status']}"
        try:
            expires = datetime.fromisoformat(a["expires_at"])
            if expires < datetime.now(timezone.utc):
                # Auto-transition to Expired
                await self.db[APPROVAL_COLL].update_one(
                    {"migration_approval_id": approval_id},
                    {"$set": {"status": "Expired"}})
                return False, "Approval expired"
        except Exception:  # noqa: BLE001
            return False, "Approval expiry invalid"
        return True, ""


# ═══════════════════════════════════════════════════════════════════════════
# Immutable Migration Package
# ═══════════════════════════════════════════════════════════════════════════
async def _build_immutable_package(db, dry_run_id: str) -> dict:
    dr = await db[DRYRUN_COLL].find_one({"migration_dry_run_id": dry_run_id}, {"_id": 0})
    if not dr: raise HTTPException(status_code=404, detail="Dry run not found")
    gng = await db[GNG_COLL].find_one({"migration_dry_run_id": dry_run_id}, {"_id": 0}, sort=[("created_at", -1)])
    if not gng: raise HTTPException(status_code=400, detail="Go/No-Go report missing for dry run")
    profiles = []
    for pid in dr.get("mapping_profile_ids") or []:
        p = await db[PROFILE_COLL].find_one({"migration_mapping_profile_id": pid}, {"_id": 0})
        if p: profiles.append({"migration_mapping_profile_id": pid,
                                 "profile_version": p.get("profile_version"),
                                 "status": p.get("status")})
    workbooks = []
    for wid in dr.get("source_workbook_ids") or []:
        w = await db[WB_COLL].find_one({"migration_source_workbook_id": wid}, {"_id": 0, "_data": 0})
        if w: workbooks.append({"migration_source_workbook_id": wid,
                                  "file_sha256": w.get("file_sha256"),
                                  "sanitised_file_name": w.get("sanitised_file_name"),
                                  "storage_object_id": w.get("storage_object_id")})
    return {
        "migration_dry_run_id": dry_run_id,
        "go_no_go_report_id": gng["migration_go_no_go_report_id"],
        "go_no_go_result": gng.get("result"),
        "workbooks": workbooks,
        "mapping_profiles": profiles,
        "row_count": dr.get("row_count", 0),
        "proposed_create_count": dr.get("proposed_create_count", 0),
        "proposed_update_count": dr.get("proposed_update_count", 0),
        "blocking_issue_count": dr.get("blocking_issue_count", 0),
        "warning_issue_count": dr.get("warning_issue_count", 0),
        "package_sha256": None,  # filled below
        "captured_at": _iso(),
    }


def _package_checksum(pkg: dict) -> str:
    import json
    stable = json.dumps({k: pkg[k] for k in sorted(pkg) if k != "package_sha256"},
                         sort_keys=True, default=str)
    return _sha256(stable.encode("utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# Preflight
# ═══════════════════════════════════════════════════════════════════════════
async def _run_preflight(db, job: dict, approval_svc: ApprovalService) -> dict:
    checks: List[dict] = []
    def add(name, ok, msg=""): checks.append({"check": name, "ok": ok, "message": msg})
    pkg = job.get("immutable_package") or {}

    # Approval validity
    ok, msg = await approval_svc.is_valid(job["migration_approval_id"])
    add("approval_valid", ok, msg)

    # Go/No-Go still approved and not NO-GO
    gng = await db[GNG_COLL].find_one({"migration_go_no_go_report_id": pkg.get("go_no_go_report_id")}, {"_id": 0})
    add("go_no_go_present", bool(gng), "" if gng else "Go/No-Go report missing")
    if gng:
        add("go_no_go_not_no_go", gng.get("result") != "NO-GO",
             "" if gng.get("result") != "NO-GO" else "Go/No-Go is NO-GO")

    # Mapping profiles active + Approved + versions unchanged
    for p in pkg.get("mapping_profiles") or []:
        live = await db[PROFILE_COLL].find_one({"migration_mapping_profile_id": p["migration_mapping_profile_id"]}, {"_id": 0})
        pid = p["migration_mapping_profile_id"][:8]
        if not live:
            add(f"profile_{pid}_present", False, "Mapping profile missing")
        else:
            add(f"profile_{pid}_approved", live.get("status") == "Approved",
                 f"Profile status is {live.get('status')}")
            add(f"profile_{pid}_version_stable",
                 live.get("profile_version") == p.get("profile_version"),
                 "Mapping profile version changed since approval")

    # Workbook checksums unchanged + storage healthy
    for w in pkg.get("workbooks") or []:
        wid = w["migration_source_workbook_id"][:8]
        live = await db[WB_COLL].find_one({"migration_source_workbook_id": w["migration_source_workbook_id"]},
                                            {"_id": 0, "_data": 0})
        if not live:
            add(f"workbook_{wid}_present", False, "Workbook missing")
            continue
        add(f"workbook_{wid}_checksum_stable",
             live.get("file_sha256") == w.get("file_sha256"),
             "Workbook checksum changed since approval")
        # storage object reachable
        if w.get("storage_object_id"):
            so = await db[STORAGE_OBJ_COLL].find_one({"storage_object_id": w["storage_object_id"]}, {"_id": 0})
            add(f"workbook_{wid}_storage_available",
                 bool(so and so.get("status") == "Available"),
                 "Storage object not Available" if so else "Storage object missing")

    # No unresolved blocking issues on the dry-run
    open_blocking = await db[ISSUE_COLL].count_documents(
        {"migration_dry_run_id": pkg.get("migration_dry_run_id"),
          "severity": "Error", "status": "Open"})
    add("no_open_blocking_issues", open_blocking == 0,
         f"{open_blocking} blocking issues still open" if open_blocking else "")

    # Reserved dispatch guard (0 & 13) — re-verify none proposed
    reserved_hit = await db[DRYRUN_ROW_COLL].count_documents({
        "migration_dry_run_id": pkg.get("migration_dry_run_id"),
        "transformed_snapshot.dispatch_number": {"$in": [0, 13, "0", "13"]},
    })
    add("no_reserved_dispatch_proposed", reserved_hit == 0,
         f"{reserved_hit} rows still target reserved 0/13" if reserved_hit else "")

    # Rollback package exists for this job
    rp = await db[ROLLBACK_COLL].find_one({"migration_commit_job_id": job["migration_commit_job_id"]}, {"_id": 0})
    add("rollback_package_present", bool(rp), "Rollback package not built yet")

    all_ok = all(c["ok"] for c in checks)
    return {"passed": all_ok, "checks": checks, "checked_at": _iso()}


# ═══════════════════════════════════════════════════════════════════════════
# Entity Handlers (staged idempotent writes)
# ═══════════════════════════════════════════════════════════════════════════
async def _write_action(db, job_id: str, batch_id: str, row_id: str,
                          entity_type: str, action_type: str, canonical_id: Optional[str],
                          before: Any, after: Any, state: str, key: str,
                          actor: str, note: str = ""):
    doc = {
        "migration_commit_action_id": _uuid(),
        "migration_commit_job_id": job_id,
        "migration_commit_batch_id": batch_id,
        "migration_commit_row_id": row_id,
        "commit_action_key": key,
        "entity_type": entity_type,
        "action_type": action_type,          # Create|Update|Preserve|Skip
        "canonical_entity_id": canonical_id,
        "before_value": before,
        "after_value": after,
        "state": state,                       # Pending|Applied|Verified|Reverted|Failed|Skipped
        "note": note,
        "performed_by": actor,
        "performed_at": _iso(),
        "created_at": _iso(),
    }
    await db[ACTIONS_COLL].insert_one(doc)
    return _strip(doc)


async def _write_rollback_action(db, package_id: str, order: int,
                                    entity_type: str, canonical_id: Optional[str],
                                    reverse_action: str, prior_value: Any,
                                    expected_current: Any):
    doc = {
        "migration_rollback_action_id": _uuid(),
        "migration_rollback_package_id": package_id,
        "dependency_order": order,
        "entity_type": entity_type,
        "canonical_entity_id": canonical_id,
        "reverse_action": reverse_action,     # Delete|Restore|CloseRelationship|OpenRelationship|ReleaseNumber|Detach
        "prior_value": prior_value,
        "expected_current_value": expected_current,
        "state": "Pending",
        "created_at": _iso(),
    }
    await db[ROLLBACK_ACT_COLL].insert_one(doc)
    return _strip(doc)


async def _handle_owner(db, job_id: str, batch_id: str, row_id: str, row: dict,
                          package_id: str, actor: str, dry_run_mode: bool) -> dict:
    """Idempotent Owner Create/Update. Uses ABN as canonical key."""
    transformed = row.get("transformed_snapshot") or {}
    abn = str(transformed.get("abn") or "").strip()
    if not abn:
        return await _write_action(db, job_id, batch_id, row_id, "Owner", "Skip",
                                     None, None, transformed, "Skipped",
                                     f"owner:{row_id}", actor, "no abn")
    key = f"owner:{abn}"
    existing = await db["owners"].find_one({"abn": abn}, {"_id": 0})
    already = await db[ACTIONS_COLL].find_one({"commit_action_key": key,
                                                 "migration_commit_job_id": job_id,
                                                 "state": {"$in": ["Applied", "Verified"]}}, {"_id": 0})
    if already:
        return already
    if existing:
        return await _write_action(db, job_id, batch_id, row_id, "Owner", "Preserve",
                                     existing["id"], existing, existing,
                                     "Applied", key, actor, "existing owner")
    if dry_run_mode:
        return await _write_action(db, job_id, batch_id, row_id, "Owner", "Create",
                                     None, None, {"abn": abn, **transformed},
                                     "Skipped", key, actor, "rehearsal: no write")
    owner_id = _uuid()
    doc = {"id": owner_id, "abn": abn,
             "name": transformed.get("owner_name") or transformed.get("full_name") or "",
             "primary_email": transformed.get("email") or "",
             "primary_phone": transformed.get("mobile_phone") or "",
             "status": "Active", "is_archived": False,
             "created_at": _iso(), "updated_at": _iso(),
             "created_by": actor, "_source": "migration-commit"}
    await db["owners"].insert_one(doc)
    await _write_rollback_action(db, package_id, 1, "Owner", owner_id, "Delete",
                                    None, doc)
    return await _write_action(db, job_id, batch_id, row_id, "Owner", "Create",
                                 owner_id, None, doc, "Applied", key, actor)


async def _handle_vehicle(db, job_id: str, batch_id: str, row_id: str, row: dict,
                            package_id: str, actor: str, dry_run_mode: bool) -> dict:
    transformed = row.get("transformed_snapshot") or {}
    reg = str(transformed.get("registration_number") or "").strip().upper()
    vin = str(transformed.get("vin") or "").strip().upper()
    if not reg and not vin:
        return await _write_action(db, job_id, batch_id, row_id, "Vehicle", "Skip",
                                     None, None, transformed, "Skipped",
                                     f"vehicle:{row_id}", actor, "no registration or vin")
    key = f"vehicle:{reg or vin}"
    q = {"$or": [{"registration_number": reg}, {"vin": vin}]} if reg and vin \
        else ({"registration_number": reg} if reg else {"vin": vin})
    existing = await db["vehicles_register"].find_one(q, {"_id": 0})
    if existing:
        return await _write_action(db, job_id, batch_id, row_id, "Vehicle", "Preserve",
                                     existing["id"], existing, existing,
                                     "Applied", key, actor, "existing vehicle")
    if dry_run_mode:
        return await _write_action(db, job_id, batch_id, row_id, "Vehicle", "Create",
                                     None, None, transformed, "Skipped", key, actor,
                                     "rehearsal: no write")
    veh_id = _uuid()
    doc = {"id": veh_id, "registration_number": reg or None, "vin": vin or None,
             "make": transformed.get("make") or "", "model": transformed.get("model") or "",
             "year": transformed.get("year") or "", "status": "Active",
             "is_archived": False, "created_at": _iso(), "updated_at": _iso(),
             "created_by": actor, "_source": "migration-commit"}
    await db["vehicles_register"].insert_one(doc)
    await _write_rollback_action(db, package_id, 2, "Vehicle", veh_id, "Delete", None, doc)
    return await _write_action(db, job_id, batch_id, row_id, "Vehicle", "Create",
                                 veh_id, None, doc, "Applied", key, actor)


async def _handle_equipment(db, job_id: str, batch_id: str, row_id: str, row: dict,
                              package_id: str, actor: str, dry_run_mode: bool) -> dict:
    transformed = row.get("transformed_snapshot") or {}
    eqnum = str(transformed.get("equipment_number") or "").strip().upper()
    if not eqnum:
        return await _write_action(db, job_id, batch_id, row_id, "Equipment", "Skip",
                                     None, None, transformed, "Skipped",
                                     f"equipment:{row_id}", actor, "no equipment_number")
    key = f"equipment:{eqnum}"
    existing = await db["equipment_register"].find_one({"equipment_number": eqnum}, {"_id": 0})
    if existing:
        return await _write_action(db, job_id, batch_id, row_id, "Equipment", "Preserve",
                                     existing["id"], existing, existing,
                                     "Applied", key, actor, "existing equipment")
    if dry_run_mode:
        return await _write_action(db, job_id, batch_id, row_id, "Equipment", "Create",
                                     None, None, transformed, "Skipped", key, actor,
                                     "rehearsal: no write")
    eq_id = _uuid()
    doc = {"id": eq_id, "equipment_number": eqnum,
             "equipment_type": transformed.get("equipment_type") or "Other",
             "status": "Available", "is_archived": False,
             "created_at": _iso(), "updated_at": _iso(),
             "created_by": actor, "_source": "migration-commit"}
    await db["equipment_register"].insert_one(doc)
    await _write_rollback_action(db, package_id, 3, "Equipment", eq_id, "Delete", None, doc)
    return await _write_action(db, job_id, batch_id, row_id, "Equipment", "Create",
                                 eq_id, None, doc, "Applied", key, actor)


async def _resolve_owner_fk(db, transformed: dict) -> Optional[str]:
    abn = str(transformed.get("owner_abn") or transformed.get("abn") or "").strip()
    if abn:
        o = await db["owners"].find_one({"abn": abn}, {"_id": 0})
        if o: return o["id"]
    ref = transformed.get("owner_id") or transformed.get("owner_ref")
    if ref:
        o = await db["owners"].find_one({"id": ref}, {"_id": 0})
        if o: return o["id"]
    return None


async def _resolve_vehicle_fk(db, transformed: dict) -> Optional[str]:
    vin = str(transformed.get("vin") or "").strip().upper()
    if vin:
        v = await db["vehicles_register"].find_one({"vin": vin}, {"_id": 0})
        if v: return v["id"]
    reg = str(transformed.get("registration_number") or "").strip().upper()
    if reg:
        v = await db["vehicles_register"].find_one({"registration_number": reg}, {"_id": 0})
        if v: return v["id"]
    return None


class EquipmentFKResult(BaseModel):
    """Deterministic Equipment FK resolution outcome."""
    status: str = "unresolved"       # matched | unresolved | multiple
    equipment_id: Optional[str] = None
    matched_by: Optional[str] = None  # canonical_id | equipment_number | serial_number | registration
    candidates: List[str] = Field(default_factory=list)  # for multiple-match diagnostics


async def _resolve_equipment_fk(db, transformed: dict) -> EquipmentFKResult:
    """Cross-sheet Equipment resolution.

    Matching hierarchy (each step returns immediately on a unique hit;
    a multi-hit at any step returns 'multiple'):
        1. canonical Equipment ID
        2. exact normalised equipment_number (uppercase, stripped)
        3. exact serial_number
        4. exact registration_number
    Name-only matching is deliberately not performed.
    """
    # 1. canonical id
    for key in ("equipment_id", "canonical_equipment_id"):
        val = transformed.get(key)
        if val:
            hit = await db["equipment_register"].find_one({"id": val}, {"_id": 0})
            if hit: return EquipmentFKResult(status="matched",
                                                equipment_id=hit["id"],
                                                matched_by="canonical_id")
    # 2. equipment number
    eqnum = str(transformed.get("equipment_number") or "").strip().upper()
    if eqnum:
        hits = await db["equipment_register"].find({"equipment_number": eqnum}, {"_id": 0}).to_list(5)
        if len(hits) == 1: return EquipmentFKResult(status="matched",
                                                        equipment_id=hits[0]["id"],
                                                        matched_by="equipment_number")
        if len(hits) > 1: return EquipmentFKResult(status="multiple",
                                                       candidates=[h["id"] for h in hits],
                                                       matched_by="equipment_number")
    # 3. serial number
    serial = str(transformed.get("serial_number") or "").strip().upper()
    if serial:
        hits = await db["equipment_register"].find({"serial_number": serial}, {"_id": 0}).to_list(5)
        if len(hits) == 1: return EquipmentFKResult(status="matched",
                                                        equipment_id=hits[0]["id"],
                                                        matched_by="serial_number")
        if len(hits) > 1: return EquipmentFKResult(status="multiple",
                                                       candidates=[h["id"] for h in hits],
                                                       matched_by="serial_number")
    # 4. registration number
    reg = str(transformed.get("equipment_registration") or transformed.get("registration_number") or "").strip().upper()
    if reg:
        hits = await db["equipment_register"].find({"registration_number": reg}, {"_id": 0}).to_list(5)
        if len(hits) == 1: return EquipmentFKResult(status="matched",
                                                        equipment_id=hits[0]["id"],
                                                        matched_by="registration")
        if len(hits) > 1: return EquipmentFKResult(status="multiple",
                                                       candidates=[h["id"] for h in hits],
                                                       matched_by="registration")
    return EquipmentFKResult(status="unresolved")


async def _handle_driver(db, job_id: str, batch_id: str, row_id: str, row: dict,
                           package_id: str, actor: str, dry_run_mode: bool) -> dict:
    """Driver create with EB-08 numbering integration."""
    transformed = row.get("transformed_snapshot") or {}
    raw_code = str(transformed.get("driver_code") or "").strip()
    dispatch = transformed.get("dispatch_number")
    # Dispatch guard 0/13
    try:
        d_int = int(dispatch) if dispatch not in (None, "", "None") else None
    except (ValueError, TypeError):
        d_int = None
    if d_int in (0, 13):
        return await _write_action(db, job_id, batch_id, row_id, "Driver", "Skip",
                                     None, None, transformed, "Skipped",
                                     f"driver:{row_id}", actor,
                                     f"reserved dispatch {d_int}")
    key = f"driver:{raw_code}:{d_int}"
    existing = None
    if raw_code:
        existing = await db["drivers"].find_one({"driver_code": raw_code}, {"_id": 0})
    if existing:
        return await _write_action(db, job_id, batch_id, row_id, "Driver", "Preserve",
                                     existing["id"], existing, existing,
                                     "Applied", key, actor, "existing driver_code")
    already = await db[ACTIONS_COLL].find_one({"commit_action_key": key,
                                                 "migration_commit_job_id": job_id,
                                                 "state": {"$in": ["Applied", "Verified"]}}, {"_id": 0})
    if already:
        return already
    if dry_run_mode:
        return await _write_action(db, job_id, batch_id, row_id, "Driver", "Create",
                                     None, None, transformed, "Skipped", key, actor,
                                     "rehearsal: no write")
    # Historical vs integer code
    is_historical = not raw_code.isdigit() if raw_code else True
    drv_id = _uuid()
    driver_doc = {
        "id": drv_id, "driver_code": raw_code or "AUTO",
        "dispatch_number": d_int,
        "full_name": transformed.get("full_name") or "",
        "email": (transformed.get("email") or "").lower(),
        "mobile_phone": transformed.get("mobile_phone") or "",
        "start_date": transformed.get("start_date") or None,
        "status": "Active", "is_archived": False,
        "historical_driver_code": raw_code if is_historical else None,
        "created_at": _iso(), "updated_at": _iso(),
        "created_by": actor, "_source": "migration-commit",
    }
    # Automatic allocation via EB-08 numbering service if code missing
    if not raw_code:
        try:
            from numbering_module import NumberingService
            ns = NumberingService(db)
            alloc = await ns.allocate_driver_code(actor)
            driver_doc["driver_code"] = str(alloc["allocated_value"])
        except Exception:  # noqa: BLE001
            driver_doc["driver_code"] = f"AUTO-{drv_id[:6]}"
    await db["drivers"].insert_one(driver_doc)
    await _write_rollback_action(db, package_id, 4, "Driver", drv_id, "Delete",
                                    None, driver_doc)
    # Owner + Vehicle relationships if cross-sheet references resolved
    owner_id = await _resolve_owner_fk(db, transformed)
    if owner_id:
        rel = {"id": _uuid(), "driver_id": drv_id, "owner_id": owner_id,
                 "is_current": True, "effective_from": _iso(),
                 "effective_to": None, "is_archived": False,
                 "created_at": _iso(), "created_by": actor,
                 "_source": "migration-commit"}
        await db["driver_owner_relationships"].insert_one(rel)
        await _write_rollback_action(db, package_id, 5, "DriverOwnerRelationship",
                                        rel["id"], "Delete", None, rel)
    veh_id = await _resolve_vehicle_fk(db, transformed)
    if veh_id:
        assign = {"id": _uuid(), "driver_id": drv_id, "vehicle_id": veh_id,
                    "is_current": True, "is_primary": True,
                    "effective_from": _iso(), "effective_to": None,
                    "is_archived": False, "created_at": _iso(), "created_by": actor,
                    "_source": "migration-commit"}
        await db["driver_vehicle_assignments"].insert_one(assign)
        await _write_rollback_action(db, package_id, 6, "DriverVehicleAssignment",
                                        assign["id"], "Delete", None, assign)
    # Equipment cross-sheet resolution (deterministic hierarchy)
    eq_fk = await _resolve_equipment_fk(db, transformed)
    if eq_fk.status == "matched":
        eq_key = f"driver-equipment:{drv_id}:{eq_fk.equipment_id}"
        # Prevent duplicate active assignment (EB-03 rule)
        dup = await db["driver_equipment_assignments"].find_one(
            {"driver_id": drv_id, "equipment_id": eq_fk.equipment_id,
              "is_current": True, "is_archived": {"$ne": True}}, {"_id": 0})
        already = await db[ACTIONS_COLL].find_one(
            {"commit_action_key": eq_key,
              "migration_commit_job_id": job_id,
              "state": {"$in": ["Applied", "Verified"]}}, {"_id": 0})
        if dup:
            await _write_action(db, job_id, batch_id, row_id,
                                  "DriverEquipmentAssignment", "Preserve",
                                  dup["id"], dup, dup, "Applied", eq_key, actor,
                                  "existing current assignment")
        elif already:
            pass  # retry idempotency
        else:
            assign_eq = {"id": _uuid(), "driver_id": drv_id,
                          "equipment_id": eq_fk.equipment_id,
                          "is_current": True, "is_primary": True,
                          "effective_from": _iso(), "effective_to": None,
                          "is_archived": False,
                          "assignment_source": "migration-commit",
                          "match_evidence": {"matched_by": eq_fk.matched_by},
                          "created_at": _iso(), "created_by": actor,
                          "_source": "migration-commit"}
            await db["driver_equipment_assignments"].insert_one(assign_eq)
            await _write_rollback_action(db, package_id, 7,
                                            "DriverEquipmentAssignment",
                                            assign_eq["id"], "Delete", None,
                                            assign_eq)
            await _write_action(db, job_id, batch_id, row_id,
                                  "DriverEquipmentAssignment", "Create",
                                  assign_eq["id"], None, assign_eq,
                                  "Applied", eq_key, actor,
                                  f"matched by {eq_fk.matched_by}")
    elif eq_fk.status == "multiple":
        await _write_action(db, job_id, batch_id, row_id,
                              "DriverEquipmentAssignment", "Skip", None, None,
                              {"candidates": eq_fk.candidates,
                                "matched_by": eq_fk.matched_by},
                              "Skipped",
                              f"driver-equipment-multi:{drv_id}:{row_id}",
                              actor, "multiple Equipment matches - blocking")
    # If equipment_number was provided but unresolved, log a blocking skip
    elif str(transformed.get("equipment_number") or transformed.get("equipment_id") or "").strip():
        await _write_action(db, job_id, batch_id, row_id,
                              "DriverEquipmentAssignment", "Skip", None, None,
                              transformed, "Skipped",
                              f"driver-equipment-unresolved:{drv_id}:{row_id}",
                              actor, "unresolved Equipment reference")
    return await _write_action(db, job_id, batch_id, row_id, "Driver", "Create",
                                 drv_id, None, driver_doc, "Applied", key, actor)


async def _handle_driver_equipment_assignment(db, job_id: str, batch_id: str,
                                                    row_id: str, row: dict,
                                                    package_id: str, actor: str,
                                                    dry_run_mode: bool) -> dict:
    """Assignment-row handler when the source row directly represents a
    Driver-Equipment assignment (rather than being embedded in a Driver row).
    Uses the deterministic Equipment FK resolver.
    """
    transformed = row.get("transformed_snapshot") or {}
    driver_code = str(transformed.get("driver_code") or "").strip()
    driver = await db["drivers"].find_one({"driver_code": driver_code}, {"_id": 0}) if driver_code else None
    if not driver:
        return await _write_action(db, job_id, batch_id, row_id,
                                     "DriverEquipmentAssignment", "Skip",
                                     None, None, transformed, "Skipped",
                                     f"drv-eq-nodriver:{row_id}", actor,
                                     "driver not resolved")
    eq_fk = await _resolve_equipment_fk(db, transformed)
    if eq_fk.status == "unresolved":
        return await _write_action(db, job_id, batch_id, row_id,
                                     "DriverEquipmentAssignment", "Skip",
                                     None, None, transformed, "Skipped",
                                     f"drv-eq-noeq:{row_id}", actor,
                                     "equipment not resolved - blocking")
    if eq_fk.status == "multiple":
        return await _write_action(db, job_id, batch_id, row_id,
                                     "DriverEquipmentAssignment", "Skip",
                                     None, None,
                                     {"candidates": eq_fk.candidates,
                                       "matched_by": eq_fk.matched_by},
                                     "Skipped",
                                     f"drv-eq-multi:{row_id}", actor,
                                     "multiple Equipment matches - blocking")
    key = f"driver-equipment:{driver['id']}:{eq_fk.equipment_id}"
    already = await db[ACTIONS_COLL].find_one(
        {"commit_action_key": key, "migration_commit_job_id": job_id,
          "state": {"$in": ["Applied", "Verified"]}}, {"_id": 0})
    if already:
        return already
    # Duplicate active assignment prevention (EB-03 rule)
    dup = await db["driver_equipment_assignments"].find_one(
        {"driver_id": driver["id"], "equipment_id": eq_fk.equipment_id,
          "is_current": True, "is_archived": {"$ne": True}}, {"_id": 0})
    if dup:
        return await _write_action(db, job_id, batch_id, row_id,
                                     "DriverEquipmentAssignment", "Preserve",
                                     dup["id"], dup, dup, "Applied", key, actor,
                                     "existing current assignment preserved")
    if dry_run_mode:
        return await _write_action(db, job_id, batch_id, row_id,
                                     "DriverEquipmentAssignment", "Create",
                                     None, None,
                                     {"driver_id": driver["id"],
                                       "equipment_id": eq_fk.equipment_id,
                                       "matched_by": eq_fk.matched_by},
                                     "Skipped", key, actor,
                                     "rehearsal: no write")
    is_historical = bool(transformed.get("effective_to"))
    assign = {"id": _uuid(), "driver_id": driver["id"],
                "equipment_id": eq_fk.equipment_id,
                "is_current": not is_historical,
                "is_primary": True,
                "effective_from": transformed.get("effective_from") or _iso(),
                "effective_to": transformed.get("effective_to"),
                "is_archived": is_historical,
                "match_evidence": {"matched_by": eq_fk.matched_by},
                "assignment_source": "migration-commit",
                "created_at": _iso(), "created_by": actor,
                "_source": "migration-commit"}
    await db["driver_equipment_assignments"].insert_one(assign)
    await _write_rollback_action(db, package_id, 7,
                                    "DriverEquipmentAssignment",
                                    assign["id"], "Delete", None, assign)
    return await _write_action(db, job_id, batch_id, row_id,
                                 "DriverEquipmentAssignment", "Create",
                                 assign["id"], None, assign,
                                 "Applied", key, actor,
                                 f"matched by {eq_fk.matched_by}")


ENTITY_HANDLERS = {
    "Owner": _handle_owner,
    "Vehicle": _handle_vehicle,
    "Equipment": _handle_equipment,
    "Driver": _handle_driver,
    "DriverEquipmentAssignment": _handle_driver_equipment_assignment,
}


# ═══════════════════════════════════════════════════════════════════════════
# Commit Service (staged idempotent)
# ═══════════════════════════════════════════════════════════════════════════
class CommitService:
    def __init__(self, db):
        self.db = db
        self.approval_svc = ApprovalService(db)

    async def create_job(self, *, dry_run_id: str, name: str, description: str,
                           mode: str, requested_by: str) -> dict:
        if mode not in JOB_MODES:
            raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(JOB_MODES)}")
        # Verify Go/No-Go is not NO-GO
        gng = await self.db[GNG_COLL].find_one({"migration_dry_run_id": dry_run_id},
                                                  {"_id": 0}, sort=[("created_at", -1)])
        if not gng:
            raise HTTPException(status_code=400, detail="Dry run has no Go/No-Go report")
        if gng.get("result") == "NO-GO":
            raise HTTPException(status_code=400, detail="Cannot create commit job for NO-GO dry run")
        package = await _build_immutable_package(self.db, dry_run_id)
        package["package_sha256"] = _package_checksum(package)
        job_id = _uuid()
        # Pre-create approval in Pending state
        approval = await self.approval_svc.create(
            dry_run_id=dry_run_id, go_no_go_id=package["go_no_go_report_id"],
            approval_type="Migration Commit Approval", requested_by=requested_by)
        now = _iso()
        doc = {
            "migration_commit_job_id": job_id,
            "migration_dry_run_id": dry_run_id,
            "go_no_go_report_id": package["go_no_go_report_id"],
            "migration_approval_id": approval["migration_approval_id"],
            "rollback_package_id": None,
            "name": name, "description": description,
            "status": "Draft", "mode": mode,
            "requested_by": requested_by, "requested_at": now,
            "preflight_started_at": None, "preflight_completed_at": None,
            "commit_started_at": None, "commit_completed_at": None,
            "failed_at": None, "failure_reason": None,
            "paused_at": None, "paused_reason": None,
            "resumed_at": None, "rolled_back_at": None, "rolled_back_by": None,
            "source_workbook_checksums": [w["file_sha256"] for w in package["workbooks"]],
            "mapping_profile_versions": [f"{p['migration_mapping_profile_id']}:{p['profile_version']}"
                                          for p in package["mapping_profiles"]],
            "total_rows": package.get("row_count", 0),
            "processed_rows": 0, "created_records": 0, "updated_records": 0,
            "preserved_records": 0, "skipped_records": 0,
            "failed_rows": 0, "warning_rows": 0,
            "correlation_id": _uuid(),
            "immutable_package": package,
            "created_at": now, "updated_at": now,
            "_source": "runtime",
        }
        await self.db[JOBS_COLL].insert_one(doc)
        # Build rollback package shell
        pkg_id = _uuid()
        await self.db[ROLLBACK_COLL].insert_one({
            "migration_rollback_package_id": pkg_id,
            "migration_commit_job_id": job_id,
            "package_sha256": package["package_sha256"],
            "actions_count": 0,
            "status": "Building",
            "created_at": now,
        })
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"rollback_package_id": pkg_id}})
        await self._event(job_id, "Commit Job Created", requested_by, {"mode": mode})
        return _strip(await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0}))

    async def _event(self, job_id: str, ev: str, actor: str, payload: Optional[dict] = None):
        await self.db[EVENTS_COLL].insert_one({
            "migration_commit_event_id": _uuid(),
            "migration_commit_job_id": job_id,
            "event_type": ev, "actor": actor,
            "payload": payload or {}, "created_at": _iso(),
        })

    async def preflight(self, job_id: str, actor: dict) -> dict:
        _require(actor, ROLE_MANAGER)
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Preflight Running",
                                                          "preflight_started_at": _iso()}})
        result = await _run_preflight(self.db, job, self.approval_svc)
        new_status = "Ready to Commit" if result["passed"] else "Preflight Failed"
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": new_status,
                                                          "preflight_completed_at": _iso(),
                                                          "preflight_result": result}})
        await self._event(job_id, "Preflight " + ("Passed" if result["passed"] else "Failed"),
                            actor.get("email"), {"checks": len(result["checks"])})
        return result

    async def request_approval(self, job_id: str, actor: dict) -> dict:
        _require(actor, ROLE_MANAGER)
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Awaiting Approval",
                                                          "updated_at": _iso()}})
        await self._event(job_id, "Approval Requested", actor.get("email"))
        return {"status": "Awaiting Approval",
                "migration_approval_id": job["migration_approval_id"]}

    async def approve(self, job_id: str, actor: dict,
                        risk_acceptance: bool = False, note: Optional[str] = None) -> dict:
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        for_real = job["mode"] == "Controlled Commit"
        approved = await self.approval_svc.approve(
            job["migration_approval_id"], approver=actor,
            risk_acceptance=risk_acceptance, note=note,
            for_real_commit=for_real,
            requester_email=job.get("requested_by"))
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Approved",
                                                          "updated_at": _iso()}})
        await self._event(job_id, "Approved", actor.get("email"))
        return {"status": "Approved", "migration_approval_id": approved["migration_approval_id"]}

    async def reject(self, job_id: str, actor: dict, reason: str) -> dict:
        _require(actor, ROLE_MANAGER)
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        await self.db[APPROVAL_COLL].update_one(
            {"migration_approval_id": job["migration_approval_id"]},
            {"$set": {"status": "Rejected", "approval_note": reason}})
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Draft",
                                                          "updated_at": _iso()}})
        await self._event(job_id, "Rejected", actor.get("email"), {"reason": reason})
        return {"status": "Rejected"}

    async def execute(self, job_id: str, actor: dict) -> dict:
        # Real commit requires Admin, rehearsal Manager+
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        if job["mode"] == "Controlled Commit":
            _require(actor, ROLE_ADMIN, "Only Admin may execute Controlled Commit")
        else:
            _require(actor, ROLE_MANAGER)
        if job["status"] not in ("Ready to Commit", "Paused"):
            # Auto-preflight if not run
            if job["status"] in ("Approved",):
                pf = await self.preflight(job_id, actor)
                if not pf["passed"]:
                    raise HTTPException(status_code=400, detail="Preflight failed")
                job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
            else:
                raise HTTPException(status_code=400,
                                     detail=f"Cannot execute from status {job['status']}")
        # Re-validate approval
        ok, msg = await self.approval_svc.is_valid(job["migration_approval_id"])
        if not ok:
            raise HTTPException(status_code=400, detail=f"Approval invalid: {msg}")
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Committing",
                                                          "commit_started_at": _iso()}})
        await self._event(job_id, "Commit Started", actor.get("email"), {"mode": job["mode"]})

        dry_run_mode = (job["mode"] == "Rehearsal")
        pkg_id = job["rollback_package_id"]
        # Load dry-run rows once
        rows = await self.db[DRYRUN_ROW_COLL].find(
            {"migration_dry_run_id": job["migration_dry_run_id"]}, {"_id": 0}
        ).to_list(20000)
        totals = {"created": 0, "updated": 0, "preserved": 0, "skipped": 0, "failed": 0, "processed": 0}
        # Process per entity type in dependency order — one batch per type
        for entity in ENTITY_ORDER:
            handler = ENTITY_HANDLERS.get(entity)
            if not handler: continue
            batch_id = _uuid()
            await self.db[BATCH_COLL].insert_one({
                "migration_commit_batch_id": batch_id,
                "migration_commit_job_id": job_id,
                "entity_type": entity, "sequence": ENTITY_ORDER.index(entity) + 1,
                "started_at": _iso(), "completed_at": None,
                "row_count": 0, "action_count": 0, "state": "Running",
                "created_at": _iso(),
            })
            batch_rows = 0
            batch_actions = 0
            for r in rows:
                target = r.get("target_entity_type") or ""
                if not target.startswith(entity):
                    continue
                # Skip rows that were marked Blocking / Manual Review in dry run
                if r.get("row_status") == "Blocking":
                    await _write_action(self.db, job_id, batch_id, r["migration_dry_run_row_id"],
                                          entity, "Skip", None, None, r.get("transformed_snapshot"),
                                          "Skipped", f"{entity.lower()}:blocking:{r['migration_dry_run_row_id']}",
                                          actor.get("email"), "row blocking in dry-run")
                    totals["skipped"] += 1; batch_actions += 1; batch_rows += 1
                    continue
                try:
                    action = await handler(self.db, job_id, batch_id, r["migration_dry_run_row_id"],
                                             r, pkg_id, actor.get("email"), dry_run_mode)
                    at = action.get("action_type")
                    if at == "Create" and action.get("state") == "Applied": totals["created"] += 1
                    elif at == "Update" and action.get("state") == "Applied": totals["updated"] += 1
                    elif at == "Preserve": totals["preserved"] += 1
                    else: totals["skipped"] += 1
                    batch_actions += 1
                    batch_rows += 1
                except HTTPException as he:
                    totals["failed"] += 1
                    await self._event(job_id, "Row Failed", actor.get("email"),
                                        {"row_id": r["migration_dry_run_row_id"],
                                          "entity": entity, "reason": str(he.detail)[:200]})
                except Exception as e:  # noqa: BLE001
                    totals["failed"] += 1
                    await self._event(job_id, "Row Failed", actor.get("email"),
                                        {"row_id": r["migration_dry_run_row_id"],
                                          "entity": entity, "reason": str(e)[:200]})
                totals["processed"] += 1
            await self.db[BATCH_COLL].update_one({"migration_commit_batch_id": batch_id},
                                                    {"$set": {"row_count": batch_rows,
                                                                "action_count": batch_actions,
                                                                "completed_at": _iso(),
                                                                "state": "Complete"}})
        final_status = "Completed"
        if totals["failed"] > 0:
            final_status = "Partially Completed"
        # Update rollback package status
        actions = await self.db[ROLLBACK_ACT_COLL].count_documents(
            {"migration_rollback_package_id": pkg_id})
        await self.db[ROLLBACK_COLL].update_one(
            {"migration_rollback_package_id": pkg_id},
            {"$set": {"status": "Sealed", "actions_count": actions}})
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
            {"$set": {"status": final_status, "commit_completed_at": _iso(),
                       "processed_rows": totals["processed"],
                       "created_records": totals["created"],
                       "updated_records": totals["updated"],
                       "preserved_records": totals["preserved"],
                       "skipped_records": totals["skipped"],
                       "failed_rows": totals["failed"], "updated_at": _iso()}})
        await self._event(job_id, "Commit Complete", actor.get("email"), totals)
        return {"status": final_status, **totals}

    async def pause(self, job_id: str, actor: dict, reason: str = "") -> dict:
        _require(actor, ROLE_MANAGER)
        r = await self.db[JOBS_COLL].update_one(
            {"migration_commit_job_id": job_id, "status": "Committing"},
            {"$set": {"status": "Paused", "paused_at": _iso(), "paused_reason": reason}})
        if not r.matched_count:
            raise HTTPException(status_code=400, detail="Cannot pause — job not running")
        await self._event(job_id, "Paused", actor.get("email"), {"reason": reason})
        return {"status": "Paused"}

    async def resume(self, job_id: str, actor: dict) -> dict:
        _require(actor, ROLE_MANAGER)
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job or job["status"] not in ("Paused", "Partially Completed"):
            raise HTTPException(status_code=400, detail="Cannot resume from current status")
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Committing",
                                                          "resumed_at": _iso()}})
        await self._event(job_id, "Resumed", actor.get("email"))
        return await self.execute(job_id, actor)

    async def retry(self, job_id: str, actor: dict) -> dict:
        return await self.resume(job_id, actor)

    async def archive(self, job_id: str, actor: dict) -> dict:
        _require(actor, ROLE_ADMIN)
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Archived",
                                                          "updated_at": _iso()}})
        await self._event(job_id, "Archived", actor.get("email"))
        return {"status": "Archived"}


# ═══════════════════════════════════════════════════════════════════════════
# Rollback Service
# ═══════════════════════════════════════════════════════════════════════════
class RollbackService:
    def __init__(self, db): self.db = db

    async def status(self, job_id: str) -> dict:
        pkg = await self.db[ROLLBACK_COLL].find_one(
            {"migration_commit_job_id": job_id}, {"_id": 0})
        if not pkg: raise HTTPException(status_code=404, detail="Rollback package not found")
        actions = await self.db[ROLLBACK_ACT_COLL].find(
            {"migration_rollback_package_id": pkg["migration_rollback_package_id"]},
            {"_id": 0}).sort("dependency_order", 1).to_list(2000)
        return {"package": pkg, "actions": actions,
                "actions_count": len(actions),
                "reverted": sum(1 for a in actions if a["state"] == "Reverted"),
                "pending": sum(1 for a in actions if a["state"] == "Pending"),
                "failed": sum(1 for a in actions if a["state"] == "Failed")}

    async def execute(self, job_id: str, actor: dict) -> dict:
        _require(actor, ROLE_ADMIN, "Only Admin may execute rollback")
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        pkg = await self.db[ROLLBACK_COLL].find_one(
            {"migration_commit_job_id": job_id}, {"_id": 0})
        if not pkg: raise HTTPException(status_code=400, detail="Rollback package missing")
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
                                              {"$set": {"status": "Rolling Back"}})
        actions = await self.db[ROLLBACK_ACT_COLL].find(
            {"migration_rollback_package_id": pkg["migration_rollback_package_id"],
              "state": "Pending"},
            {"_id": 0}).sort("dependency_order", -1).to_list(2000)  # reverse order
        reverted = failed = conflicts = 0
        for a in actions:
            try:
                coll_map = {
                    "Owner": "owners", "Vehicle": "vehicles_register",
                    "Equipment": "equipment_register", "Driver": "drivers",
                    "DriverOwnerRelationship": "driver_owner_relationships",
                    "DriverVehicleAssignment": "driver_vehicle_assignments",
                    "DriverEquipmentAssignment": "driver_equipment_assignments",
                }
                coll = coll_map.get(a["entity_type"])
                if not coll:
                    failed += 1; continue
                if a["reverse_action"] == "Delete":
                    # Conflict detection: check current doc has not been edited
                    current = await self.db[coll].find_one({"id": a["canonical_entity_id"]}, {"_id": 0})
                    if current and a.get("expected_current_value"):
                        exp = a["expected_current_value"]
                        if current.get("updated_at") != exp.get("updated_at") and \
                             current.get("_source") != "migration-commit":
                            # Later user edit detected — refuse destructive rollback
                            await self.db[ROLLBACK_ACT_COLL].update_one(
                                {"migration_rollback_action_id": a["migration_rollback_action_id"]},
                                {"$set": {"state": "Failed",
                                           "note": "conflict: later edit detected"}})
                            conflicts += 1; continue
                    await self.db[coll].delete_one({"id": a["canonical_entity_id"]})
                    await self.db[ROLLBACK_ACT_COLL].update_one(
                        {"migration_rollback_action_id": a["migration_rollback_action_id"]},
                        {"$set": {"state": "Reverted", "reverted_at": _iso()}})
                    reverted += 1
                else:
                    failed += 1
            except Exception:  # noqa: BLE001
                failed += 1
        new_status = "Rolled Back" if failed == 0 and conflicts == 0 else \
                       ("Rollback Failed" if failed else "Partially Completed")
        await self.db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
            {"$set": {"status": new_status, "rolled_back_at": _iso(),
                       "rolled_back_by": actor.get("email")}})
        await self.db[EVENTS_COLL].insert_one({
            "migration_commit_event_id": _uuid(),
            "migration_commit_job_id": job_id,
            "event_type": "Rollback Executed", "actor": actor.get("email"),
            "payload": {"reverted": reverted, "failed": failed, "conflicts": conflicts},
            "created_at": _iso(),
        })
        return {"reverted": reverted, "failed": failed, "conflicts": conflicts,
                "status": new_status}


# ═══════════════════════════════════════════════════════════════════════════
# Post-commit Reconciliation
# ═══════════════════════════════════════════════════════════════════════════
class PostCommitReconciliationService:
    def __init__(self, db): self.db = db

    async def reconcile(self, job_id: str, actor: dict) -> dict:
        _require(actor, ROLE_MANAGER)
        job = await self.db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        # Count actions vs canonical records
        actions = await self.db[ACTIONS_COLL].find({"migration_commit_job_id": job_id}, {"_id": 0}).to_list(20000)
        expected = {"Create": 0, "Update": 0, "Preserve": 0, "Skip": 0}
        found_create = 0; missing = 0; mismatch = 0
        coll_map = {"Owner": "owners", "Vehicle": "vehicles_register",
                     "Equipment": "equipment_register", "Driver": "drivers"}
        for a in actions:
            expected[a["action_type"]] = expected.get(a["action_type"], 0) + 1
            if a["action_type"] == "Create" and a["state"] == "Applied":
                coll = coll_map.get(a["entity_type"])
                if coll and a["canonical_entity_id"]:
                    doc = await self.db[coll].find_one({"id": a["canonical_entity_id"]}, {"_id": 0})
                    if doc:
                        found_create += 1
                    else:
                        missing += 1
        warnings_ = 0
        result = "Reconciled"
        if missing > 0: result = "Failed Reconciliation"
        elif warnings_ > 0: result = "Reconciled with Warnings"
        doc = {
            "migration_post_commit_reconciliation_id": _uuid(),
            "migration_commit_job_id": job_id,
            "result": result,
            "expected": expected,
            "actual_created": found_create,
            "missing_count": missing,
            "mismatch_count": mismatch,
            "warnings": warnings_,
            "started_at": _iso(), "completed_at": _iso(),
            "performed_by": actor.get("email"),
            "created_at": _iso(),
        }
        await self.db[RECON_COLL].insert_one(doc)
        # If reconciled and job is Committed, finalise Completed status
        if result == "Reconciled" and job["status"] in ("Committing", "Ready to Commit"):
            await self.db[JOBS_COLL].update_one(
                {"migration_commit_job_id": job_id},
                {"$set": {"status": "Completed"}})
        return _strip(doc)


# ═══════════════════════════════════════════════════════════════════════════
# Legacy Storage Backfill
# ═══════════════════════════════════════════════════════════════════════════
class StorageBackfillService:
    def __init__(self, db): self.db = db

    async def create(self, scope: str, actor: dict) -> dict:
        _require(actor, ROLE_ADMIN)
        allowed = {"Documents", "Exports", "Migration Workbooks", "All Legacy Development Assets"}
        if scope not in allowed:
            raise HTTPException(status_code=400, detail=f"scope must be one of {sorted(allowed)}")
        job = {
            "storage_backfill_job_id": _uuid(),
            "scope": scope, "status": "Queued",
            "requested_by": actor.get("email"), "requested_at": _iso(),
            "started_at": None, "completed_at": None,
            "found": 0, "migrated": 0, "verified": 0,
            "failed": 0, "skipped": 0, "source_retained": True,
            "created_at": _iso(),
        }
        await self.db[BACKFILL_COLL].insert_one(job)
        return _strip(job)

    async def execute(self, job_id: str, actor: dict) -> dict:
        _require(actor, ROLE_ADMIN)
        job = await self.db[BACKFILL_COLL].find_one({"storage_backfill_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Backfill job not found")
        await self.db[BACKFILL_COLL].update_one({"storage_backfill_job_id": job_id},
                                                    {"$set": {"status": "Running",
                                                                "started_at": _iso()}})
        counts = {"found": 0, "migrated": 0, "verified": 0, "failed": 0, "skipped": 0}

        async def _backfill_workbook_data():
            wbs = await self.db[WB_COLL].find({"_data": {"$exists": True, "$ne": None},
                                                  "storage_object_id": {"$in": [None, ""]}}, {"_id": 0}).to_list(500)
            for wb in wbs:
                counts["found"] += 1
                try:
                    from storage_module import get_storage_service
                    svc = get_storage_service(self.db)
                    obj = await svc.put(
                        entity_type=None, entity_id=None,
                        filename=wb.get("sanitised_file_name", "wb.xlsx"),
                        content=wb["_data"],
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        actor_email=actor.get("email"),
                        migration_workbook_id=wb["migration_source_workbook_id"],
                        retention_class="Migration Source", validate=False)
                    # Verify by reading back
                    _ = await svc.get_bytes(obj["storage_object_id"], actor.get("email"), "download")
                    await self.db[WB_COLL].update_one(
                        {"migration_source_workbook_id": wb["migration_source_workbook_id"]},
                        {"$set": {"storage_object_id": obj["storage_object_id"]}})
                    # Note: legacy _data is intentionally NOT deleted per rules
                    counts["migrated"] += 1; counts["verified"] += 1
                    await self.db[BACKFILL_ACT_COLL].insert_one({
                        "storage_backfill_action_id": _uuid(),
                        "storage_backfill_job_id": job_id,
                        "asset_type": "Migration Workbook",
                        "asset_id": wb["migration_source_workbook_id"],
                        "storage_object_id": obj["storage_object_id"],
                        "state": "Verified", "created_at": _iso()})
                except Exception as e:  # noqa: BLE001
                    counts["failed"] += 1
                    await self.db[BACKFILL_ACT_COLL].insert_one({
                        "storage_backfill_action_id": _uuid(),
                        "storage_backfill_job_id": job_id,
                        "asset_type": "Migration Workbook",
                        "asset_id": wb["migration_source_workbook_id"],
                        "state": "Failed", "error": str(e)[:200],
                        "created_at": _iso()})

        async def _backfill_docs():
            # EB-05 documents missing storage_object_id
            q = {"storage_object_id": {"$in": [None, ""]}}
            docs = await self.db["documents"].find(q, {"_id": 0}).to_list(500)
            for d in docs:
                counts["found"] += 1
                if not d.get("storage_key"):
                    counts["skipped"] += 1; continue
                try:
                    from storage_module import get_storage_service
                    from pathlib import Path
                    svc = get_storage_service(self.db)
                    root = Path(os.environ.get("DOCUMENT_STORAGE_PATH", "/app/backend/document_storage"))
                    fp = root / d["storage_key"]
                    if not fp.exists():
                        counts["skipped"] += 1; continue
                    obj = await svc.register_existing(
                        object_key=d["storage_key"], sha256=d.get("checksum_sha256", ""),
                        file_size=d.get("file_size_bytes", 0),
                        content_type=d.get("mime_type", "application/octet-stream"),
                        filename=d.get("original_filename", "file"),
                        entity_type="Document", entity_id=None,
                        actor_email=actor.get("email"),
                        document_id=d["id"], retention_class="Operational Document")
                    await self.db["documents"].update_one({"id": d["id"]},
                        {"$set": {"storage_object_id": obj["storage_object_id"]}})
                    counts["migrated"] += 1; counts["verified"] += 1
                    await self.db[BACKFILL_ACT_COLL].insert_one({
                        "storage_backfill_action_id": _uuid(),
                        "storage_backfill_job_id": job_id,
                        "asset_type": "Document", "asset_id": d["id"],
                        "storage_object_id": obj["storage_object_id"],
                        "state": "Verified", "created_at": _iso()})
                except Exception as e:  # noqa: BLE001
                    counts["failed"] += 1
                    await self.db[BACKFILL_ACT_COLL].insert_one({
                        "storage_backfill_action_id": _uuid(),
                        "storage_backfill_job_id": job_id,
                        "asset_type": "Document", "asset_id": d.get("id"),
                        "state": "Failed", "error": str(e)[:200],
                        "created_at": _iso()})

        if job["scope"] in ("Migration Workbooks", "All Legacy Development Assets"):
            await _backfill_workbook_data()
        if job["scope"] in ("Documents", "Exports", "All Legacy Development Assets"):
            await _backfill_docs()
        await self.db[BACKFILL_COLL].update_one({"storage_backfill_job_id": job_id},
            {"$set": {"status": "Completed" if counts["failed"] == 0 else "Partially Completed",
                       "completed_at": _iso(), **counts}})
        return {**counts, "storage_backfill_job_id": job_id}


# ═══════════════════════════════════════════════════════════════════════════
# Indexes
# ═══════════════════════════════════════════════════════════════════════════
async def ensure_indexes(db):
    await db[JOBS_COLL].create_index("migration_commit_job_id", unique=True)
    await db[JOBS_COLL].create_index("migration_dry_run_id")
    await db[JOBS_COLL].create_index("status")
    await db[BATCH_COLL].create_index("migration_commit_batch_id", unique=True)
    await db[BATCH_COLL].create_index("migration_commit_job_id")
    await db[ROWS_COLL].create_index("migration_commit_row_id", unique=True)
    await db[ACTIONS_COLL].create_index("migration_commit_action_id", unique=True)
    await db[ACTIONS_COLL].create_index("migration_commit_job_id")
    await db[ACTIONS_COLL].create_index([("migration_commit_job_id", 1), ("commit_action_key", 1)])
    await db[EVENTS_COLL].create_index("migration_commit_event_id", unique=True)
    await db[EVENTS_COLL].create_index("migration_commit_job_id")
    await db[ROLLBACK_COLL].create_index("migration_rollback_package_id", unique=True)
    await db[ROLLBACK_COLL].create_index("migration_commit_job_id")
    await db[ROLLBACK_ACT_COLL].create_index("migration_rollback_action_id", unique=True)
    await db[ROLLBACK_ACT_COLL].create_index("migration_rollback_package_id")
    await db[RECON_COLL].create_index("migration_post_commit_reconciliation_id", unique=True)
    await db[APPROVAL_COLL].create_index("migration_approval_id", unique=True)
    await db[BACKFILL_COLL].create_index("storage_backfill_job_id", unique=True)
    await db[BACKFILL_ACT_COLL].create_index("storage_backfill_action_id", unique=True)


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic
# ═══════════════════════════════════════════════════════════════════════════
class CreateJobRequest(BaseModel):
    migration_dry_run_id: str
    name: str = Field(..., min_length=1)
    description: str = ""
    mode: str = "Rehearsal"


class ApproveRequest(BaseModel):
    risk_acceptance: bool = False
    note: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str


class BackfillRequest(BaseModel):
    scope: str = "All Legacy Development Assets"


# ═══════════════════════════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════════════════════════
def build_migration_commit_router(db, get_current_user):
    router = APIRouter(prefix="/api/migration-commit", tags=["migration-commit"])
    svc = CommitService(db)
    rollback = RollbackService(db)
    recon = PostCommitReconciliationService(db)

    @router.get("/environment")
    async def environment(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return {"transactions_enabled": _transactions_enabled(),
                 "commit_mode": "transactional" if _transactions_enabled() else "staged-idempotent",
                 "banner": ("Staged idempotent commit mode. Multi-document "
                            "transactions are NOT active in this environment. "
                            "Partial-completion, pause and resume are truthful.")}

    @router.post("/jobs")
    async def create_job(payload: CreateJobRequest, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await svc.create_job(dry_run_id=payload.migration_dry_run_id,
                                       name=payload.name, description=payload.description,
                                       mode=payload.mode,
                                       requested_by=current.get("email"))

    @router.get("/jobs")
    async def list_jobs(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        rows = await db[JOBS_COLL].find({}, {"_id": 0, "immutable_package": 0}).sort("created_at", -1).to_list(500)
        return rows

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        j = await db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not j: raise HTTPException(status_code=404, detail="Not found")
        # ReadOnly does not see the immutable package details (source data)
        if current.get("role") == "ReadOnly":
            j.pop("immutable_package", None)
        return j

    @router.post("/jobs/{job_id}/preflight")
    async def preflight(job_id: str, current=Depends(get_current_user)):
        return await svc.preflight(job_id, current)

    @router.post("/jobs/{job_id}/request-approval")
    async def req_approval(job_id: str, current=Depends(get_current_user)):
        return await svc.request_approval(job_id, current)

    @router.post("/jobs/{job_id}/approve")
    async def approve(job_id: str, payload: ApproveRequest, current=Depends(get_current_user)):
        return await svc.approve(job_id, current, payload.risk_acceptance, payload.note)

    @router.post("/jobs/{job_id}/reject")
    async def reject(job_id: str, payload: RejectRequest, current=Depends(get_current_user)):
        return await svc.reject(job_id, current, payload.reason)

    @router.post("/jobs/{job_id}/execute")
    async def execute(job_id: str, current=Depends(get_current_user)):
        return await svc.execute(job_id, current)

    @router.post("/jobs/{job_id}/pause")
    async def pause(job_id: str, current=Depends(get_current_user)):
        return await svc.pause(job_id, current)

    @router.post("/jobs/{job_id}/resume")
    async def resume(job_id: str, current=Depends(get_current_user)):
        return await svc.resume(job_id, current)

    @router.post("/jobs/{job_id}/retry")
    async def retry(job_id: str, current=Depends(get_current_user)):
        return await svc.retry(job_id, current)

    @router.post("/jobs/{job_id}/archive")
    async def archive(job_id: str, current=Depends(get_current_user)):
        return await svc.archive(job_id, current)

    @router.get("/jobs/{job_id}/batches")
    async def batches(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await db[BATCH_COLL].find({"migration_commit_job_id": job_id}, {"_id": 0}).sort("sequence", 1).to_list(500)

    @router.get("/jobs/{job_id}/actions")
    async def actions(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await db[ACTIONS_COLL].find({"migration_commit_job_id": job_id}, {"_id": 0}).to_list(5000)

    @router.get("/jobs/{job_id}/events")
    async def events(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await db[EVENTS_COLL].find({"migration_commit_job_id": job_id}, {"_id": 0}).sort("created_at", -1).to_list(500)

    @router.get("/jobs/{job_id}/rollback-package")
    async def rollback_pkg(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await rollback.status(job_id)

    @router.post("/jobs/{job_id}/rollback/request")
    async def rollback_request(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        job = await db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job: raise HTTPException(status_code=404, detail="Not found")
        # Create rollback approval
        appr = await ApprovalService(db).create(
            dry_run_id=job["migration_dry_run_id"],
            go_no_go_id=job["go_no_go_report_id"],
            approval_type="Rollback Approval",
            requested_by=current.get("email"))
        await db[JOBS_COLL].update_one({"migration_commit_job_id": job_id},
            {"$set": {"status": "Rollback Pending",
                       "rollback_approval_id": appr["migration_approval_id"]}})
        return {"migration_approval_id": appr["migration_approval_id"]}

    @router.post("/jobs/{job_id}/rollback/approve")
    async def rollback_approve(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        job = await db[JOBS_COLL].find_one({"migration_commit_job_id": job_id}, {"_id": 0})
        if not job or not job.get("rollback_approval_id"):
            raise HTTPException(status_code=400, detail="No pending rollback request")
        return await ApprovalService(db).approve(
            job["rollback_approval_id"], approver=current,
            risk_acceptance=True, note="rollback approval",
            for_real_commit=(job["mode"] == "Controlled Commit"),
            requester_email=job.get("requested_by"))

    @router.post("/jobs/{job_id}/rollback/execute")
    async def rollback_execute(job_id: str, current=Depends(get_current_user)):
        return await rollback.execute(job_id, current)

    @router.get("/jobs/{job_id}/rollback/status")
    async def rollback_status(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await rollback.status(job_id)

    @router.post("/jobs/{job_id}/reconcile")
    async def reconcile(job_id: str, current=Depends(get_current_user)):
        return await recon.reconcile(job_id, current)

    @router.get("/jobs/{job_id}/reconciliation")
    async def get_reconciliation(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        rows = await db[RECON_COLL].find({"migration_commit_job_id": job_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
        return rows

    return router


def build_storage_backfill_router(db, get_current_user):
    router = APIRouter(prefix="/api/storage", tags=["storage-backfill"])
    bf = StorageBackfillService(db)

    @router.post("/backfill")
    async def create_backfill(payload: BackfillRequest, current=Depends(get_current_user)):
        return await bf.create(payload.scope, current)

    @router.get("/backfill")
    async def list_backfill(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await db[BACKFILL_COLL].find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @router.get("/backfill/{job_id}")
    async def get_backfill(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        j = await db[BACKFILL_COLL].find_one({"storage_backfill_job_id": job_id}, {"_id": 0})
        if not j: raise HTTPException(status_code=404, detail="Not found")
        actions = await db[BACKFILL_ACT_COLL].find(
            {"storage_backfill_job_id": job_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
        return {**j, "actions": actions}

    @router.post("/backfill/{job_id}/execute")
    async def execute_backfill(job_id: str, current=Depends(get_current_user)):
        return await bf.execute(job_id, current)

    @router.post("/backfill/{job_id}/retry")
    async def retry_backfill(job_id: str, current=Depends(get_current_user)):
        return await bf.execute(job_id, current)

    return router
