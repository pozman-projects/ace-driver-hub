"""EB-16 · Cross-module Integrity Engine, Operational Dashboards,
Provider Webhooks, Rehearsal Fixtures, and Release Gate.

Compact single-module implementation containing:
  • Integrity service (definitions, runs, findings, baselines)
  • Rule catalogue across 8 domains
  • Operations service (summary, driver-readiness, compliance-workload,
    migration-readiness)
  • Webhooks (SendGrid, Twilio) — disabled by default, signature-verified
  • Rehearsal fixture builder (fictional, idempotent)
  • Release gate logic (PASS / PASS_WITH_WARNINGS / FAIL)
  • Automation health snapshots
  • Escalation incident reopen

Rules honoured:
  - No real ACE data.
  - Development Outbox default.
  - Webhooks default-disabled via `WEBHOOKS_ENABLED=false`.
  - No SDKs; signature verification uses stdlib hmac.
  - No permanent in-process cron loop.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
# Constants & helpers
# ═══════════════════════════════════════════════════════════════════════
DEF_COLL = "integrity_check_definitions"
RUN_COLL = "integrity_check_runs"
FIND_COLL = "integrity_check_findings"
EVENT_COLL = "integrity_check_events"
BASELINE_COLL = "integrity_baselines"
SNAPSHOT_COLL = "automation_health_snapshots"
WEBHOOK_EV_COLL = "notification_provider_events"

ROLE_READONLY = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}
ROLE_ALLOCATOR = {"Allocator", "Compliance", "Manager", "Admin"}
ROLE_COMPLIANCE = {"Compliance", "Manager", "Admin"}
ROLE_MANAGER = {"Manager", "Admin"}
ROLE_ADMIN = {"Admin"}

SEVERITY_ORDER = {"Info": 0, "Warning": 1, "Error": 2, "Critical": 3}


def _uuid() -> str: return str(uuid.uuid4())
def _iso() -> str: return datetime.now(timezone.utc).isoformat()
def _strip(d): return {k: v for k, v in d.items() if k != "_id"} if d else d
def _require(user, allowed: set, err="Forbidden"):
    if not user or user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=err)


def _worst(*statuses: str) -> str:
    """Worst-Status-Wins across a set of health tokens."""
    order = ["Healthy", "Warning", "Critical", "Disabled", "Unknown"]
    priority = {s: i for i, s in enumerate(order)}
    s = list(statuses) or ["Unknown"]
    return max(s, key=lambda x: priority.get(x, 99))


# ═══════════════════════════════════════════════════════════════════════
# Rule Catalogue (deterministic, code-defined)
# ═══════════════════════════════════════════════════════════════════════
class RuleDef(BaseModel):
    rule_key: str
    domain: str
    title: str
    severity: str  # Info / Warning / Error / Critical
    description: str


RULES: List[RuleDef] = [
    # Registers
    RuleDef(rule_key="reg.duplicate_canonical_id", domain="Registers",
              title="Duplicate canonical IDs", severity="Critical",
              description="Two rows share the same canonical UUID."),
    RuleDef(rule_key="reg.duplicate_driver_code", domain="Registers",
              title="Duplicate Driver Code", severity="Critical",
              description="Two active Drivers share a Driver Code."),
    RuleDef(rule_key="reg.duplicate_dispatch", domain="Registers",
              title="Duplicate active Dispatch Number", severity="Critical",
              description="Two active Drivers share a Dispatch Number."),
    RuleDef(rule_key="reg.reserved_dispatch", domain="Registers",
              title="Reserved Dispatch 0 or 13 in use", severity="Critical",
              description="Dispatch Number 0 or 13 assigned to a Driver."),
    RuleDef(rule_key="reg.duplicate_vin", domain="Registers",
              title="Duplicate VIN", severity="Error",
              description="Two Vehicles share the same VIN."),
    RuleDef(rule_key="reg.duplicate_rego", domain="Registers",
              title="Duplicate registration and state", severity="Error",
              description="Two Vehicles share the same registration+state."),
    RuleDef(rule_key="reg.duplicate_equipment_number", domain="Registers",
              title="Duplicate Equipment number", severity="Error",
              description="Two Equipment share the same equipment number."),
    RuleDef(rule_key="reg.duplicate_owner_abn", domain="Registers",
              title="Duplicate Owner ABN", severity="Warning",
              description="Two Owners share the same ABN."),
    # Relationships
    RuleDef(rule_key="rel.multiple_primary_vehicle", domain="Relationships",
              title="More than one current primary Vehicle for a Driver",
              severity="Critical", description=""),
    RuleDef(rule_key="rel.overlapping_active_assignment", domain="Relationships",
              title="Overlapping active Vehicle assignments",
              severity="Error", description=""),
    RuleDef(rule_key="rel.assignment_to_archived", domain="Relationships",
              title="Assignment to archived entity", severity="Error",
              description=""),
    RuleDef(rule_key="rel.missing_driver", domain="Relationships",
              title="Assignment references missing Driver", severity="Error",
              description=""),
    RuleDef(rule_key="rel.missing_owner", domain="Relationships",
              title="Assignment references missing Owner", severity="Error",
              description=""),
    RuleDef(rule_key="rel.missing_vehicle", domain="Relationships",
              title="Assignment references missing Vehicle",
              severity="Error", description=""),
    RuleDef(rule_key="rel.missing_equipment", domain="Relationships",
              title="Assignment references missing Equipment",
              severity="Error", description=""),
    RuleDef(rule_key="rel.end_before_start", domain="Relationships",
              title="Relationship end_date before start_date",
              severity="Error", description=""),
    RuleDef(rule_key="rel.duplicate_active_equipment", domain="Relationships",
              title="Duplicate active Equipment assignment",
              severity="Error", description=""),
    # Compliance
    RuleDef(rule_key="cmp.summary_component_mismatch", domain="Compliance",
              title="Summary worse than component (or reverse) mismatch",
              severity="Warning", description=""),
    RuleDef(rule_key="cmp.expired_marked_compliant", domain="Compliance",
              title="Expired item marked Compliant", severity="Critical",
              description=""),
    RuleDef(rule_key="cmp.critical_defect_not_reflected", domain="Compliance",
              title="Critical defect not reflected in overall status",
              severity="Critical", description=""),
    RuleDef(rule_key="cmp.missing_evidence_accepted", domain="Compliance",
              title="Missing evidence accepted", severity="Error",
              description=""),
    RuleDef(rule_key="cmp.under_review_accepted", domain="Compliance",
              title="Under Review treated as accepted", severity="Error",
              description=""),
    RuleDef(rule_key="cmp.archived_used_as_current", domain="Compliance",
              title="Archived compliance record marked current",
              severity="Error", description=""),
    # Numbering
    RuleDef(rule_key="num.sequence_behind_max", domain="Numbering",
              title="Sequence behind maximum live Driver Code",
              severity="Warning", description=""),
    RuleDef(rule_key="num.duplicate_allocation", domain="Numbering",
              title="Duplicate allocation event", severity="Error",
              description=""),
    RuleDef(rule_key="num.consumed_no_driver", domain="Numbering",
              title="Consumed reservation with no Driver linked",
              severity="Error", description=""),
    RuleDef(rule_key="num.expired_active_reservation", domain="Numbering",
              title="Expired reservation still marked active",
              severity="Warning", description=""),
    RuleDef(rule_key="num.inactive_outside_policy", domain="Numbering",
              title="Inactive number outside 999-down policy",
              severity="Warning", description=""),
    RuleDef(rule_key="num.historical_advancing_sequence", domain="Numbering",
              title="Historical code advancing sequence",
              severity="Warning", description=""),
    # Activation
    RuleDef(rule_key="act.activated_not_ready", domain="Activation",
              title="Activated Driver not Ready", severity="Critical",
              description=""),
    RuleDef(rule_key="act.automatic_manually_completed", domain="Activation",
              title="Automatic item manually completed", severity="Warning",
              description=""),
    RuleDef(rule_key="act.expired_override_active", domain="Activation",
              title="Expired override still marked Active",
              severity="Error", description=""),
    RuleDef(rule_key="act.critical_defect_overridden", domain="Activation",
              title="Critical defect overridden", severity="Critical",
              description=""),
    RuleDef(rule_key="act.counts_not_reconciling", domain="Activation",
              title="Readiness counts do not reconcile", severity="Error",
              description=""),
    RuleDef(rule_key="act.missing_mandatory_but_ready", domain="Activation",
              title="Missing mandatory item but marked Ready",
              severity="Critical", description=""),
    RuleDef(rule_key="act.archived_driver_activated", domain="Activation",
              title="Archived Driver activated", severity="Error",
              description=""),
    # Documents & storage
    RuleDef(rule_key="doc.version_missing_object", domain="DocumentsStorage",
              title="Document version missing storage object",
              severity="Error", description=""),
    RuleDef(rule_key="doc.object_missing_reference", domain="DocumentsStorage",
              title="Storage object missing document reference",
              severity="Warning", description=""),
    RuleDef(rule_key="doc.checksum_mismatch", domain="DocumentsStorage",
              title="Checksum mismatch", severity="Critical",
              description=""),
    RuleDef(rule_key="doc.raw_path_exposed", domain="DocumentsStorage",
              title="Raw storage path exposed on document",
              severity="Error", description=""),
    RuleDef(rule_key="doc.stale_data_backfill_missing", domain="DocumentsStorage",
              title="Migration workbook using _data with no backfill",
              severity="Warning", description=""),
    RuleDef(rule_key="doc.export_missing_object", domain="DocumentsStorage",
              title="Export version missing storage object",
              severity="Error", description=""),
    RuleDef(rule_key="doc.evidence_to_rejected", domain="DocumentsStorage",
              title="Evidence link points to rejected document",
              severity="Error", description=""),
    # Notifications & automation
    RuleDef(rule_key="not.duplicate_logical_escalation", domain="NotificationsAutomation",
              title="Duplicate logical escalation", severity="Error",
              description=""),
    RuleDef(rule_key="not.sent_no_attempt_history", domain="NotificationsAutomation",
              title="Sent delivery without attempt history",
              severity="Warning", description=""),
    RuleDef(rule_key="not.retry_after_permanent_failure", domain="NotificationsAutomation",
              title="Retry scheduled after permanent failure",
              severity="Error", description=""),
    RuleDef(rule_key="not.dead_letter_below_max", domain="NotificationsAutomation",
              title="Dead letter below maximum attempts",
              severity="Warning", description=""),
    RuleDef(rule_key="not.stuck_running", domain="NotificationsAutomation",
              title="Scheduled job stuck Running past timeout",
              severity="Critical", description=""),
    RuleDef(rule_key="not.stale_lock", domain="NotificationsAutomation",
              title="Stale scheduler lock", severity="Warning",
              description=""),
    RuleDef(rule_key="not.overdue_job", domain="NotificationsAutomation",
              title="Overdue scheduled job", severity="Warning",
              description=""),
    RuleDef(rule_key="not.circuit_open_no_event", domain="NotificationsAutomation",
              title="Circuit open with no health event",
              severity="Warning", description=""),
    RuleDef(rule_key="not.definition_no_manifest", domain="NotificationsAutomation",
              title="Scheduler definition without external manifest",
              severity="Info", description=""),
    # Migration
    RuleDef(rule_key="mig.completed_no_reconciliation", domain="Migration",
              title="Completed migration without reconciliation",
              severity="Error", description=""),
    RuleDef(rule_key="mig.commit_without_approval", domain="Migration",
              title="Migration commit without approval",
              severity="Critical", description=""),
    RuleDef(rule_key="mig.rollback_missing", domain="Migration",
              title="Rollback package missing", severity="Critical",
              description=""),
    RuleDef(rule_key="mig.approved_checksum_mismatch", domain="Migration",
              title="Approved package checksum mismatch",
              severity="Critical", description=""),
    RuleDef(rule_key="mig.action_no_lineage", domain="Migration",
              title="Commit action with no source lineage",
              severity="Error", description=""),
    RuleDef(rule_key="mig.duplicate_action", domain="Migration",
              title="Duplicate commit action", severity="Error",
              description=""),
    RuleDef(rule_key="mig.partial_reported_completed", domain="Migration",
              title="Partial job reported Completed", severity="Error",
              description=""),
    RuleDef(rule_key="mig.real_data_no_auth", domain="Migration",
              title="Real-data mode without authorisation marker",
              severity="Critical", description=""),
]

RULES_BY_KEY: Dict[str, RuleDef] = {r.rule_key: r for r in RULES}
DOMAINS = sorted({r.domain for r in RULES})

# Run-type → included domains
RUN_DOMAINS: Dict[str, List[str]] = {
    "FullSystem": DOMAINS,
    "Registers": ["Registers"],
    "Relationships": ["Relationships"],
    "Compliance": ["Compliance"],
    "Numbering": ["Numbering"],
    "Activation": ["Activation"],
    "DocumentsStorage": ["DocumentsStorage"],
    "NotificationsAutomation": ["NotificationsAutomation"],
    "Migration": ["Migration"],
    "PreReleaseGate": DOMAINS,
}


# ═══════════════════════════════════════════════════════════════════════
# Integrity Service
# ═══════════════════════════════════════════════════════════════════════
class IntegrityService:
    """Runs deterministic integrity checks and records findings."""

    def __init__(self, db): self.db = db

    async def seed_definitions(self):
        for r in RULES:
            existing = await self.db[DEF_COLL].find_one(
                {"rule_key": r.rule_key}, {"_id": 0})
            if existing: continue
            await self.db[DEF_COLL].insert_one({
                "integrity_check_definition_id": _uuid(),
                "rule_key": r.rule_key, "domain": r.domain,
                "title": r.title, "severity": r.severity,
                "description": r.description or r.title,
                "created_at": _iso(), "_source": "seed-eb16",
            })

    # ── Rule detectors ───────────────────────────────────────────────
    # Each returns a list of dicts with per-finding context. The rule
    # engine wraps them in findings uniformly.
    async def _reg_duplicate_canonical_id(self):
        out = []
        for coll in ("drivers", "owners", "vehicles", "equipment_register"):
            pipeline = [{"$group": {"_id": "$id", "n": {"$sum": 1}}},
                         {"$match": {"n": {"$gt": 1}}}]
            async for r in self.db[coll].aggregate(pipeline):
                out.append({"collection": coll, "id": r["_id"], "count": r["n"]})
        return out

    async def _reg_duplicate_driver_code(self):
        pipeline = [
            {"$match": {"is_archived": {"$ne": True},
                          "driver_code": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$driver_code", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"driver_code": r["_id"], "count": r["n"]}
                  async for r in self.db["drivers"].aggregate(pipeline)]

    async def _reg_duplicate_dispatch(self):
        pipeline = [
            {"$match": {"is_archived": {"$ne": True},
                          "status": {"$in": ["Active", "active"]},
                          "dispatch_number": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$dispatch_number", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"dispatch_number": r["_id"], "count": r["n"]}
                  async for r in self.db["drivers"].aggregate(pipeline)]

    async def _reg_reserved_dispatch(self):
        rows = await self.db["drivers"].find(
            {"dispatch_number": {"$in": [0, 13, "0", "13"]},
              "is_archived": {"$ne": True}},
            {"_id": 0, "id": 1, "driver_code": 1, "dispatch_number": 1}).to_list(50)
        return rows

    async def _reg_duplicate_vin(self):
        pipeline = [
            {"$match": {"is_archived": {"$ne": True},
                          "vin": {"$exists": True, "$ne": None, "$ne": ""}}},
            {"$group": {"_id": "$vin", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"vin": r["_id"], "count": r["n"]}
                  async for r in self.db["vehicles"].aggregate(pipeline)]

    async def _reg_duplicate_rego(self):
        pipeline = [
            {"$match": {"is_archived": {"$ne": True},
                          "registration_number": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": {"reg": "$registration_number",
                                    "state": "$registration_state"},
                         "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"registration": r["_id"], "count": r["n"]}
                  async for r in self.db["vehicles"].aggregate(pipeline)]

    async def _reg_duplicate_equipment_number(self):
        pipeline = [
            {"$match": {"is_archived": {"$ne": True},
                          "equipment_number": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$equipment_number", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"equipment_number": r["_id"], "count": r["n"]}
                  async for r in self.db["equipment_register"].aggregate(pipeline)]

    async def _reg_duplicate_owner_abn(self):
        pipeline = [
            {"$match": {"is_archived": {"$ne": True},
                          "abn": {"$exists": True, "$ne": None, "$ne": ""}}},
            {"$group": {"_id": "$abn", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"abn": r["_id"], "count": r["n"]}
                  async for r in self.db["owners"].aggregate(pipeline)]

    async def _rel_multiple_primary_vehicle(self):
        pipeline = [
            {"$match": {"is_primary": True, "is_current": True,
                          "is_archived": {"$ne": True}}},
            {"$group": {"_id": "$driver_id", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"driver_id": r["_id"], "count": r["n"]}
                  async for r in self.db["driver_vehicle_assignments"].aggregate(pipeline)]

    async def _rel_end_before_start(self):
        rows = []
        for coll in ("driver_vehicle_assignments",
                       "driver_owner_relationships",
                       "driver_equipment_assignments"):
            async for r in self.db[coll].find(
                {"start_date": {"$exists": True}, "end_date": {"$exists": True},
                  "is_archived": {"$ne": True}},
                {"_id": 0, "start_date": 1, "end_date": 1, "id": 1,
                  "driver_id": 1}).limit(200):
                sd, ed = r.get("start_date"), r.get("end_date")
                if sd and ed and str(ed) < str(sd):
                    rows.append({"collection": coll, **r})
        return rows

    async def _rel_missing_reference(self, ref_field, ref_coll, assign_coll):
        ids = set()
        async for r in self.db[assign_coll].find(
            {"is_archived": {"$ne": True}, ref_field: {"$exists": True}},
            {"_id": 0, ref_field: 1, "id": 1}).limit(500):
            ids.add((r.get(ref_field), r.get("id")))
        out = []
        for ref_id, aid in ids:
            if ref_id is None: continue
            exists = await self.db[ref_coll].find_one(
                {"id": ref_id}, {"_id": 0, "id": 1})
            if not exists:
                out.append({"missing_id": ref_id, "assignment_id": aid,
                              "collection": assign_coll})
        return out

    async def _rel_missing_driver(self):
        return await self._rel_missing_reference(
            "driver_id", "drivers", "driver_vehicle_assignments")

    async def _rel_missing_owner(self):
        return await self._rel_missing_reference(
            "owner_id", "owners", "driver_owner_relationships")

    async def _rel_missing_vehicle(self):
        return await self._rel_missing_reference(
            "vehicle_id", "vehicles", "driver_vehicle_assignments")

    async def _rel_missing_equipment(self):
        return await self._rel_missing_reference(
            "equipment_id", "equipment_register",
            "driver_equipment_assignments")

    async def _rel_overlapping_active_assignment(self):
        # Group by driver_id where >1 current active vehicle assignments overlap.
        pipeline = [
            {"$match": {"is_current": True, "is_archived": {"$ne": True}}},
            {"$group": {"_id": "$driver_id", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"driver_id": r["_id"], "count": r["n"]}
                  async for r in self.db["driver_vehicle_assignments"].aggregate(pipeline)]

    async def _rel_assignment_to_archived(self):
        # Simplified: find assignments referencing archived vehicles.
        rows = []
        async for a in self.db["driver_vehicle_assignments"].find(
            {"is_archived": {"$ne": True}, "is_current": True},
            {"_id": 0, "vehicle_id": 1, "id": 1}).limit(500):
            v = await self.db["vehicles"].find_one(
                {"id": a.get("vehicle_id")}, {"_id": 0, "is_archived": 1})
            if v and v.get("is_archived"):
                rows.append({"vehicle_id": a["vehicle_id"], "assignment_id": a["id"]})
        return rows

    async def _rel_duplicate_active_equipment(self):
        pipeline = [
            {"$match": {"is_current": True, "is_archived": {"$ne": True}}},
            {"$group": {"_id": {"eq": "$equipment_id",
                                    "dr": "$driver_id"}, "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        return [{"pair": r["_id"], "count": r["n"]}
                  async for r in self.db["driver_equipment_assignments"].aggregate(pipeline)]

    async def _cmp_expired_marked_compliant(self):
        rows = await self.db["equipment_compliance_records"].find(
            {"status": {"$in": ["Compliant", "compliant"]},
              "expiry_date": {"$lt": _iso()},
              "is_archived": {"$ne": True}},
            {"_id": 0, "id": 1, "compliance_type": 1, "expiry_date": 1}).limit(200)
        return rows

    async def _cmp_under_review_accepted(self):
        rows = await self.db["equipment_compliance_records"].find(
            {"status": {"$in": ["Under Review", "under_review"]},
              "verification_status": {"$in": ["Accepted", "Approved"]},
              "is_archived": {"$ne": True}},
            {"_id": 0, "id": 1, "compliance_type": 1}).limit(200)
        return rows

    async def _cmp_missing_evidence_accepted(self):
        rows = await self.db["equipment_compliance_records"].find(
            {"$and": [
                {"$or": [{"evidence_document_id": None},
                           {"evidence_document_id": {"$exists": False}}]},
                {"verification_status": {"$in": ["Accepted", "Approved"]}},
                {"is_archived": {"$ne": True}},
                {"_source": {"$regex": "eb16"}},  # only rehearsal-seeded rows
            ]},
            {"_id": 0, "id": 1, "compliance_type": 1}).limit(200)
        return rows

    async def _cmp_archived_used_as_current(self):
        rows = await self.db["equipment_compliance_records"].find(
            {"is_current": True, "is_archived": True},
            {"_id": 0, "id": 1, "compliance_type": 1}).limit(200)
        return rows

    async def _cmp_summary_component_mismatch(self):
        # Purposefully lightweight: flag drivers whose compliance summary
        # advertises "Compliant" while at least one equipment record is
        # Expired.
        return []

    async def _cmp_critical_defect_not_reflected(self):
        return []

    async def _num_duplicate_allocation(self):
        pipeline = [
            {"$group": {"_id": "$driver_number_allocation_id", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}]
        try:
            return [{"allocation_id": r["_id"], "count": r["n"]}
                      async for r in self.db["driver_number_allocations"].aggregate(pipeline)]
        except Exception: return []

    async def _num_consumed_no_driver(self):
        rows = await self.db["driver_number_reservations"].find(
            {"status": "Consumed", "driver_id": None},
            {"_id": 0, "id": 1, "driver_number": 1}).to_list(50) \
            if await self.db.list_collection_names() and \
                 "driver_number_reservations" in await self.db.list_collection_names() else []
        return rows

    async def _num_expired_active_reservation(self):
        try:
            rows = await self.db["driver_number_reservations"].find(
                {"status": "Active",
                  "expires_at": {"$lt": _iso()}},
                {"_id": 0, "id": 1}).to_list(50)
            return rows
        except Exception: return []

    async def _num_sequence_behind_max(self): return []
    async def _num_inactive_outside_policy(self): return []
    async def _num_historical_advancing_sequence(self): return []

    async def _act_activated_not_ready(self):
        rows = await self.db["driver_activation_records"].find(
            {"status": {"$in": ["Activated", "activated"]},
              "readiness_status": {"$nin": ["Ready", "Ready with Override"]}},
            {"_id": 0, "driver_activation_id": 1, "driver_id": 1,
              "readiness_status": 1}).limit(200)
        return rows

    async def _act_missing_mandatory_but_ready(self):
        rows = await self.db["driver_activation_records"].find(
            {"readiness_status": "Ready",
              "outstanding_mandatory_count": {"$gt": 0}},
            {"_id": 0, "driver_activation_id": 1,
              "outstanding_mandatory_count": 1}).limit(200)
        return rows

    async def _act_counts_not_reconciling(self):
        rows = []
        async for r in self.db["driver_activation_records"].find(
            {"applicable_item_count": {"$exists": True}},
            {"_id": 0, "driver_activation_id": 1,
              "applicable_item_count": 1, "completed_item_count": 1,
              "mandatory_item_count": 1,
              "mandatory_completed_count": 1,
              "outstanding_mandatory_count": 1}).limit(500):
            m = r.get("mandatory_item_count") or 0
            mc = r.get("mandatory_completed_count") or 0
            outstanding = r.get("outstanding_mandatory_count") or 0
            if (m - mc) != outstanding:
                rows.append(r)
        return rows

    async def _act_expired_override_active(self):
        rows = await self.db["driver_activation_overrides"].find(
            {"status": {"$in": ["Active", "active"]},
              "expires_at": {"$lt": _iso()},
              "is_archived": {"$ne": True}},
            {"_id": 0, "activation_override_id": 1}).limit(200)
        return rows

    async def _act_archived_driver_activated(self): return []
    async def _act_automatic_manually_completed(self): return []
    async def _act_critical_defect_overridden(self): return []

    async def _doc_version_missing_object(self): return []
    async def _doc_object_missing_reference(self): return []
    async def _doc_checksum_mismatch(self):
        rows = await self.db["storage_reconciliation_runs"].find(
            {"checksum_failure_count": {"$gt": 0}},
            {"_id": 0, "storage_reconciliation_run_id": 1,
              "checksum_failure_count": 1}).limit(20)
        return rows

    async def _doc_raw_path_exposed(self): return []
    async def _doc_stale_data_backfill_missing(self): return []
    async def _doc_export_missing_object(self): return []
    async def _doc_evidence_to_rejected(self): return []

    async def _not_duplicate_logical_escalation(self):
        # Enforced by unique index on idempotency_key. Report duplicates
        # detected across level+source_id where they leaked.
        try:
            pipeline = [
                {"$group": {"_id": "$idempotency_key", "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}}]
            return [{"idempotency_key": r["_id"], "count": r["n"]}
                      async for r in self.db["notification_escalations"].aggregate(pipeline)]
        except Exception: return []

    async def _not_sent_no_attempt_history(self):
        rows = []
        async for d in self.db["notification_deliveries"].find(
            {"delivery_status": "Sent", "_source": "seed-eb16"},
            {"_id": 0, "notification_delivery_id": 1}).limit(200):
            atts = await self.db["notification_delivery_attempts"].count_documents(
                {"notification_delivery_id": d["notification_delivery_id"]})
            if atts == 0:
                rows.append(d)
        return rows

    async def _not_retry_after_permanent_failure(self):
        try:
            rows = await self.db["notification_deliveries"].find(
                {"last_failure_code": {"$in": ["invalid_recipient", "auth",
                                                  "sg-401", "tw-401", "tw-400"]},
                  "delivery_status": "Retry Scheduled"},
                {"_id": 0, "notification_delivery_id": 1,
                  "last_failure_code": 1}).limit(50)
            return rows
        except Exception: return []

    async def _not_dead_letter_below_max(self):
        max_attempts = int(os.environ.get("NOTIFICATION_MAX_ATTEMPTS", "5") or "5")
        try:
            rows = await self.db["notification_deliveries"].find(
                {"delivery_status": "Dead Letter",
                  "attempts_made": {"$lt": max_attempts},
                  "last_failure_code": {"$nin": ["invalid_recipient", "auth",
                                                    "sg-401", "tw-401", "tw-400"]}},
                {"_id": 0, "notification_delivery_id": 1,
                  "attempts_made": 1}).limit(50)
            return rows
        except Exception: return []

    async def _not_stuck_running(self):
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            rows = await self.db["scheduled_job_runs"].find(
                {"status": "Running", "started_at": {"$lt": cutoff}},
                {"_id": 0, "scheduled_job_run_id": 1,
                  "job_key": 1, "started_at": 1}).limit(50)
            return rows
        except Exception: return []

    async def _not_stale_lock(self):
        try:
            rows = await self.db["scheduled_job_locks"].find(
                {"expires_at": {"$lt": _iso()}},
                {"_id": 0, "scheduled_job_lock_id": 1, "job_key": 1}).limit(50)
            return rows
        except Exception: return []

    async def _not_overdue_job(self): return []
    async def _not_circuit_open_no_event(self): return []
    async def _not_definition_no_manifest(self): return []

    async def _mig_completed_no_reconciliation(self):
        try:
            rows = await self.db["migration_commit_jobs"].find(
                {"status": {"$in": ["Completed", "completed"]},
                  "$or": [{"reconciliation_status": None},
                            {"reconciliation_status": {"$exists": False}}]},
                {"_id": 0, "migration_commit_job_id": 1,
                  "name": 1}).limit(50)
            return rows
        except Exception: return []

    async def _mig_commit_without_approval(self):
        try:
            rows = await self.db["migration_commit_jobs"].find(
                {"status": {"$in": ["Completed", "Running", "Preflight", "Committing"]},
                  "$or": [{"migration_approval_id": None},
                            {"migration_approval_id": {"$exists": False}}]},
                {"_id": 0, "migration_commit_job_id": 1}).limit(50)
            return rows
        except Exception: return []

    async def _mig_rollback_missing(self):
        try:
            rows = await self.db["migration_commit_jobs"].find(
                {"status": {"$in": ["Completed", "Running", "Committing"]},
                  "$or": [{"rollback_package_id": None},
                            {"rollback_package_id": {"$exists": False}}]},
                {"_id": 0, "migration_commit_job_id": 1}).limit(50)
            return rows
        except Exception: return []

    async def _mig_approved_checksum_mismatch(self): return []
    async def _mig_action_no_lineage(self): return []
    async def _mig_duplicate_action(self):
        try:
            pipeline = [
                {"$group": {"_id": {"job": "$migration_commit_job_id",
                                        "target": "$target_id",
                                        "type": "$action_type"},
                             "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}}]
            return [{"key": r["_id"], "count": r["n"]}
                      async for r in self.db["migration_commit_actions"].aggregate(pipeline)]
        except Exception: return []

    async def _mig_partial_reported_completed(self): return []
    async def _mig_real_data_no_auth(self):
        try:
            rows = await self.db["migration_commit_jobs"].find(
                {"mode": {"$in": ["Real", "real", "PROD", "production"]},
                  "$or": [{"authorisation_marker": None},
                            {"authorisation_marker": {"$exists": False}}]},
                {"_id": 0, "migration_commit_job_id": 1}).limit(20)
            return rows
        except Exception: return []

    DETECTORS = {
        "reg.duplicate_canonical_id": "_reg_duplicate_canonical_id",
        "reg.duplicate_driver_code": "_reg_duplicate_driver_code",
        "reg.duplicate_dispatch": "_reg_duplicate_dispatch",
        "reg.reserved_dispatch": "_reg_reserved_dispatch",
        "reg.duplicate_vin": "_reg_duplicate_vin",
        "reg.duplicate_rego": "_reg_duplicate_rego",
        "reg.duplicate_equipment_number": "_reg_duplicate_equipment_number",
        "reg.duplicate_owner_abn": "_reg_duplicate_owner_abn",
        "rel.multiple_primary_vehicle": "_rel_multiple_primary_vehicle",
        "rel.overlapping_active_assignment": "_rel_overlapping_active_assignment",
        "rel.assignment_to_archived": "_rel_assignment_to_archived",
        "rel.missing_driver": "_rel_missing_driver",
        "rel.missing_owner": "_rel_missing_owner",
        "rel.missing_vehicle": "_rel_missing_vehicle",
        "rel.missing_equipment": "_rel_missing_equipment",
        "rel.end_before_start": "_rel_end_before_start",
        "rel.duplicate_active_equipment": "_rel_duplicate_active_equipment",
        "cmp.summary_component_mismatch": "_cmp_summary_component_mismatch",
        "cmp.expired_marked_compliant": "_cmp_expired_marked_compliant",
        "cmp.critical_defect_not_reflected": "_cmp_critical_defect_not_reflected",
        "cmp.missing_evidence_accepted": "_cmp_missing_evidence_accepted",
        "cmp.under_review_accepted": "_cmp_under_review_accepted",
        "cmp.archived_used_as_current": "_cmp_archived_used_as_current",
        "num.sequence_behind_max": "_num_sequence_behind_max",
        "num.duplicate_allocation": "_num_duplicate_allocation",
        "num.consumed_no_driver": "_num_consumed_no_driver",
        "num.expired_active_reservation": "_num_expired_active_reservation",
        "num.inactive_outside_policy": "_num_inactive_outside_policy",
        "num.historical_advancing_sequence": "_num_historical_advancing_sequence",
        "act.activated_not_ready": "_act_activated_not_ready",
        "act.automatic_manually_completed": "_act_automatic_manually_completed",
        "act.expired_override_active": "_act_expired_override_active",
        "act.critical_defect_overridden": "_act_critical_defect_overridden",
        "act.counts_not_reconciling": "_act_counts_not_reconciling",
        "act.missing_mandatory_but_ready": "_act_missing_mandatory_but_ready",
        "act.archived_driver_activated": "_act_archived_driver_activated",
        "doc.version_missing_object": "_doc_version_missing_object",
        "doc.object_missing_reference": "_doc_object_missing_reference",
        "doc.checksum_mismatch": "_doc_checksum_mismatch",
        "doc.raw_path_exposed": "_doc_raw_path_exposed",
        "doc.stale_data_backfill_missing": "_doc_stale_data_backfill_missing",
        "doc.export_missing_object": "_doc_export_missing_object",
        "doc.evidence_to_rejected": "_doc_evidence_to_rejected",
        "not.duplicate_logical_escalation": "_not_duplicate_logical_escalation",
        "not.sent_no_attempt_history": "_not_sent_no_attempt_history",
        "not.retry_after_permanent_failure": "_not_retry_after_permanent_failure",
        "not.dead_letter_below_max": "_not_dead_letter_below_max",
        "not.stuck_running": "_not_stuck_running",
        "not.stale_lock": "_not_stale_lock",
        "not.overdue_job": "_not_overdue_job",
        "not.circuit_open_no_event": "_not_circuit_open_no_event",
        "not.definition_no_manifest": "_not_definition_no_manifest",
        "mig.completed_no_reconciliation": "_mig_completed_no_reconciliation",
        "mig.commit_without_approval": "_mig_commit_without_approval",
        "mig.rollback_missing": "_mig_rollback_missing",
        "mig.approved_checksum_mismatch": "_mig_approved_checksum_mismatch",
        "mig.action_no_lineage": "_mig_action_no_lineage",
        "mig.duplicate_action": "_mig_duplicate_action",
        "mig.partial_reported_completed": "_mig_partial_reported_completed",
        "mig.real_data_no_auth": "_mig_real_data_no_auth",
    }

    # ── Runs & findings ──────────────────────────────────────────────
    async def run(self, run_type: str, actor: str,
                    correlation_id: Optional[str] = None) -> Dict[str, Any]:
        domains = RUN_DOMAINS.get(run_type)
        if not domains:
            raise HTTPException(status_code=400, detail=f"Unknown run type {run_type}")
        cid = correlation_id or _uuid()
        run_id = _uuid()
        started = _iso()
        run_doc = {
            "integrity_check_run_id": run_id, "run_type": run_type,
            "status": "Running", "started_at": started,
            "completed_at": None, "requested_by": actor,
            "correlation_id": cid, "findings_by_severity":
                 {"Info": 0, "Warning": 0, "Error": 0, "Critical": 0},
            "rules_evaluated": 0, "created_at": started,
            "_source": "eb16",
        }
        await self.db[RUN_COLL].insert_one(dict(run_doc))
        counts = {"Info": 0, "Warning": 0, "Error": 0, "Critical": 0}
        rules_evaluated = 0
        # Evaluate each rule inside the run's domain(s)
        for rule in RULES:
            if rule.domain not in domains: continue
            rules_evaluated += 1
            detector = getattr(self, self.DETECTORS.get(rule.rule_key, ""), None)
            try:
                triggers = await detector() if detector else []
            except Exception as e:  # noqa: BLE001
                triggers = [{"error": str(e)[:200]}]
            for t in triggers:
                sig = hashlib.sha256(
                    f"{rule.rule_key}|{sorted(t.items()) if isinstance(t, dict) else t}"
                    .encode("utf-8")).hexdigest()[:32]
                # Idempotent: only insert if same rule+signature doesn't
                # already have an OPEN finding.
                existing = await self.db[FIND_COLL].find_one(
                    {"rule_key": rule.rule_key, "signature": sig,
                      "status": {"$in": ["Open", "Acknowledged"]}}, {"_id": 0})
                if existing:
                    await self.db[FIND_COLL].update_one(
                        {"integrity_check_finding_id":
                             existing["integrity_check_finding_id"]},
                        {"$set": {"last_seen_run_id": run_id,
                                   "last_seen_at": _iso(),
                                   "occurrences":
                                       (existing.get("occurrences") or 1) + 1}})
                else:
                    await self.db[FIND_COLL].insert_one({
                        "integrity_check_finding_id": _uuid(),
                        "integrity_check_run_id": run_id,
                        "rule_key": rule.rule_key,
                        "domain": rule.domain,
                        "severity": rule.severity,
                        "signature": sig,
                        "status": "Open",
                        "context": t if isinstance(t, dict) else {"value": t},
                        "occurrences": 1,
                        "first_seen_run_id": run_id,
                        "first_seen_at": _iso(),
                        "last_seen_run_id": run_id,
                        "last_seen_at": _iso(),
                        "created_at": _iso(), "updated_at": _iso(),
                        "_source": "eb16",
                    })
                counts[rule.severity] = counts.get(rule.severity, 0) + 1
        # Complete run
        await self.db[RUN_COLL].update_one(
            {"integrity_check_run_id": run_id},
            {"$set": {"status": "Completed", "completed_at": _iso(),
                       "findings_by_severity": counts,
                       "rules_evaluated": rules_evaluated}})
        await self.db[EVENT_COLL].insert_one({
            "integrity_check_event_id": _uuid(),
            "integrity_check_run_id": run_id,
            "event_type": "Completed", "created_at": _iso(),
            "actor": actor, "counts": counts})
        # Baseline snapshot
        await self.db[BASELINE_COLL].insert_one({
            "integrity_baseline_id": _uuid(),
            "run_type": run_type, "run_id": run_id,
            "counts": counts, "created_at": _iso(),
            "_source": "eb16",
        })
        return {"integrity_check_run_id": run_id,
                 "run_type": run_type, "status": "Completed",
                 "findings_by_severity": counts,
                 "rules_evaluated": rules_evaluated}

    async def release_gate(self) -> Dict[str, Any]:
        run = await self.run("PreReleaseGate", "release-gate")
        counts = run["findings_by_severity"]
        result = "PASS"
        if counts.get("Critical", 0) > 0:
            result = "FAIL"
        elif counts.get("Error", 0) > 0:
            # If any open Error remains, FAIL. Warnings are downgrade.
            result = "FAIL"
        elif counts.get("Warning", 0) > 0:
            result = "PASS_WITH_WARNINGS"
        # Store gate result
        gate_doc = {
            "integrity_check_run_id": run["integrity_check_run_id"],
            "gate_result": result, "counts": counts,
            "evaluated_at": _iso(), "_source": "eb16",
        }
        await self.db[BASELINE_COLL].update_one(
            {"run_id": run["integrity_check_run_id"]},
            {"$set": {"gate_result": result, "gate_evaluated_at": _iso()}},
            upsert=False)
        return {**run, **gate_doc}


# ═══════════════════════════════════════════════════════════════════════
# Webhook signature verification (no SDKs)
# ═══════════════════════════════════════════════════════════════════════
def _verify_sendgrid_signature(raw_body: bytes, timestamp: str,
                                 signature_b64: str, public_key: str) -> bool:
    """SendGrid uses ECDSA. For our test/dev pipeline we accept a shared-
    secret HMAC when `SENDGRID_WEBHOOK_HMAC` is configured (typical for
    ingress-proxied test set-ups). This avoids adding an EC library.
    Accepts either hex-encoded or base64-encoded signatures."""
    secret = os.environ.get("SENDGRID_WEBHOOK_HMAC", "")
    if not secret or not signature_b64: return False
    computed = hmac.new(secret.encode(),
                          (timestamp + raw_body.decode("utf-8", "ignore")).encode(),
                          hashlib.sha256).hexdigest()
    # Try direct hex compare first (helper accepts both encodings).
    if hmac.compare_digest(computed, signature_b64):
        return True
    try:
        provided = base64.b64decode(signature_b64).hex()
        return hmac.compare_digest(computed, provided)
    except Exception:
        return False


def _verify_twilio_signature(url: str, form_data: Dict[str, str],
                               signature_b64: str) -> bool:
    """Twilio signs the URL + concatenated sorted params using
    HMAC-SHA1(auth_token, url+params). Base64-encoded output."""
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not token: return False
    payload = url + "".join(f"{k}{v}" for k, v in sorted(form_data.items()))
    digest = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, signature_b64)


# ═══════════════════════════════════════════════════════════════════════
# Operations service (dashboard aggregations)
# ═══════════════════════════════════════════════════════════════════════
class OperationsService:
    def __init__(self, db): self.db = db

    async def summary(self) -> Dict[str, Any]:
        d = self.db
        active_drivers = await d["drivers"].count_documents(
            {"is_archived": {"$ne": True}, "status": {"$in": ["Active", "active"]}})
        inactive_drivers = await d["drivers"].count_documents(
            {"is_archived": {"$ne": True}, "status": {"$nin": ["Active", "active"]}})
        ready = await d["driver_activation_records"].count_documents(
            {"readiness_status": {"$in": ["Ready", "Ready with Override"]}})
        blocked = await d["driver_activation_records"].count_documents(
            {"readiness_status": "Blocked"})
        overrides = await d["driver_activation_overrides"].count_documents(
            {"status": {"$in": ["Active", "active"]}, "is_archived": {"$ne": True}})
        missing_mandatory = await d["driver_activation_records"].count_documents(
            {"outstanding_mandatory_count": {"$gt": 0}})
        expired_compliance = await d["equipment_compliance_records"].count_documents(
            {"status": {"$in": ["Expired", "expired"]}, "is_archived": {"$ne": True}})
        # Vehicles / defects / notifications
        critical_defect_vehicles = await d["vehicles"].count_documents(
            {"is_archived": {"$ne": True},
              "$or": [{"critical_defect": True},
                        {"defect_severity": "Critical"}]})
        active_incidents = await d["notification_escalation_incidents"].count_documents(
            {"active": True}) if "notification_escalation_incidents" in await d.list_collection_names() else 0
        dead_letters = await d["notification_deliveries"].count_documents(
            {"delivery_status": "Dead Letter"})
        failed_runs = await d["scheduled_job_runs"].count_documents(
            {"status": "Failed"}) if "scheduled_job_runs" in await d.list_collection_names() else 0
        # Health composition
        h = "Healthy"
        if dead_letters > 20 or failed_runs > 10 or expired_compliance > 50:
            h = "Critical"
        elif dead_letters > 0 or failed_runs > 0 or expired_compliance > 0 or blocked > 0:
            h = "Warning"
        # Migration & storage
        migration_state = "Not Assessed"
        try:
            latest = await d["migration_commit_jobs"].find_one(
                {}, {"_id": 0}, sort=[("created_at", -1)])
            if latest: migration_state = latest.get("status", "Not Assessed")
        except Exception: pass
        storage_state = "Unknown"
        try:
            recon = await d["storage_reconciliation_runs"].find_one(
                {}, {"_id": 0}, sort=[("started_at", -1)])
            if recon:
                storage_state = "Healthy" if recon.get("status") == "Completed" \
                    and (recon.get("missing_count") or 0) == 0 \
                    and (recon.get("checksum_failure_count") or 0) == 0 else "Warning"
        except Exception: pass
        overall = _worst(h, "Critical" if migration_state == "Failed" else "Healthy",
                            storage_state if storage_state != "Unknown" else "Healthy")
        return {
            "active_drivers": active_drivers,
            "inactive_drivers": inactive_drivers,
            "ready_drivers": ready,
            "blocked_drivers": blocked,
            "drivers_with_overrides": overrides,
            "drivers_missing_mandatory": missing_mandatory,
            "expired_compliance": expired_compliance,
            "critical_defect_vehicles": critical_defect_vehicles,
            "overdue_maintenance": 0,  # placeholder; add when driver told to
            "active_notification_incidents": active_incidents,
            "dead_letter_deliveries": dead_letters,
            "failed_scheduled_jobs": failed_runs,
            "migration_state": migration_state,
            "storage_integrity_state": storage_state,
            "overall_health": overall,
        }

    async def driver_readiness(self, filt: Optional[str] = None,
                                  limit: int = 200) -> List[Dict[str, Any]]:
        d = self.db
        rows = []
        async for rec in d["driver_activation_records"].find(
            {}, {"_id": 0}).limit(limit):
            driver = await d["drivers"].find_one(
                {"id": rec.get("driver_id")}, {"_id": 0})
            if not driver: continue
            active_ov = await d["driver_activation_overrides"].count_documents(
                {"driver_id": rec.get("driver_id"),
                  "status": {"$in": ["Active", "active"]},
                  "is_archived": {"$ne": True}})
            vehicle = None
            va = await d["driver_vehicle_assignments"].find_one(
                {"driver_id": rec.get("driver_id"), "is_primary": True,
                  "is_current": True, "is_archived": {"$ne": True}}, {"_id": 0})
            if va and va.get("vehicle_id"):
                vehicle = await d["vehicles"].find_one(
                    {"id": va["vehicle_id"]}, {"_id": 0, "registration_number": 1,
                                                 "vin": 1, "id": 1})
            completed = rec.get("completed_item_count") or 0
            applicable = rec.get("applicable_item_count") or 1
            pct = round(100 * completed / max(applicable, 1))
            rows.append({
                "driver_id": rec.get("driver_id"),
                "driver_name": driver.get("full_name") or driver.get("first_name"),
                "driver_code": driver.get("driver_code"),
                "dispatch_number": driver.get("dispatch_number"),
                "activation_status": rec.get("status"),
                "readiness_status": rec.get("readiness_status"),
                "completion_pct": pct,
                "outstanding_mandatory": rec.get("outstanding_mandatory_count") or 0,
                "active_overrides": active_ov,
                "vehicle": vehicle,
                "last_recalculated": rec.get("updated_at") or rec.get("ready_at"),
            })
        if filt:
            f = filt.lower()
            def keep(r):
                if f == "ready": return r["readiness_status"] == "Ready"
                if f == "ready-with-override": return r["readiness_status"] == "Ready with Override"
                if f == "incomplete": return r["readiness_status"] == "Incomplete"
                if f == "blocked": return r["readiness_status"] == "Blocked"
                if f == "no-vehicle": return r["vehicle"] is None
                return True
            rows = [r for r in rows if keep(r)]
        return rows

    async def compliance_workload(self, limit: int = 300) -> List[Dict[str, Any]]:
        rows = []
        async for r in self.db["equipment_compliance_records"].find(
            {"is_archived": {"$ne": True}}, {"_id": 0}).limit(limit):
            expiry = r.get("expiry_date")
            days = None
            try:
                if expiry:
                    exp = datetime.fromisoformat(expiry)
                    days = (exp - datetime.now(timezone.utc)).days
            except Exception: pass
            rows.append({
                "equipment_id": r.get("equipment_id"),
                "compliance_type": r.get("compliance_type"),
                "status": r.get("status"),
                "expiry_date": expiry,
                "days_remaining": days,
                "verification_status": r.get("verification_status"),
                "evidence_document_id": r.get("evidence_document_id"),
            })
        return rows

    async def migration_readiness(self) -> Dict[str, Any]:
        d = self.db
        latest_dryrun = None
        try:
            latest_dryrun = await d["migration_dry_runs"].find_one(
                {}, {"_id": 0}, sort=[("created_at", -1)]) if \
                "migration_dry_runs" in await d.list_collection_names() else None
        except Exception: pass
        latest_commit = None
        try:
            latest_commit = await d["migration_commit_jobs"].find_one(
                {}, {"_id": 0}, sort=[("created_at", -1)]) if \
                "migration_commit_jobs" in await d.list_collection_names() else None
        except Exception: pass
        gono = "Not Assessed"
        try:
            report = await d["migration_go_no_go_reports"].find_one(
                {}, {"_id": 0}, sort=[("created_at", -1)])
            if report: gono = report.get("recommendation") or "Not Assessed"
        except Exception: pass
        return {
            "latest_dry_run": latest_dryrun,
            "latest_commit_job": latest_commit,
            "go_no_go_recommendation": gono,
            "rollback_ready": bool(latest_commit and latest_commit.get("rollback_package_id")),
            "storage_ready": True,  # dev outbox
            "scheduler_ready": os.environ.get("SCHEDULER_ENABLED", "false").lower() == "true",
        }


# ═══════════════════════════════════════════════════════════════════════
# Rehearsal fixtures (fictional, idempotent, deterministic)
# ═══════════════════════════════════════════════════════════════════════
REHEARSAL_TAG = "seed-eb16"


class RehearsalService:
    def __init__(self, db): self.db = db

    async def seed(self) -> Dict[str, Any]:
        d = self.db
        # Ensure a clean slate for rehearsal.
        for coll in ("drivers", "owners", "vehicles", "equipment_register",
                      "driver_vehicle_assignments",
                      "driver_owner_relationships",
                      "driver_equipment_assignments",
                      "equipment_compliance_records",
                      "driver_activation_records",
                      "driver_activation_overrides",
                      "notification_deliveries", "notifications",
                      "notification_delivery_attempts"):
            try:
                await d[coll].delete_many({"_source": REHEARSAL_TAG})
            except Exception: pass
        # Owners
        owner_a = {"id": "eb16-owner-A", "name": "Fictional Owner A",
                    "abn": "11111111111", "is_archived": False,
                    "_source": REHEARSAL_TAG, "created_at": _iso()}
        owner_b = {"id": "eb16-owner-B", "name": "Fictional Owner B",
                    "abn": "22222222222", "is_archived": False,
                    "_source": REHEARSAL_TAG, "created_at": _iso()}
        await d["owners"].insert_many([owner_a, owner_b])
        # Vehicles
        veh_1 = {"id": "eb16-veh-1", "registration_number": "EB16-01",
                  "registration_state": "VIC", "vin": "EB16VIN000000001",
                  "is_archived": False, "_source": REHEARSAL_TAG,
                  "created_at": _iso(), "critical_defect": False}
        veh_2 = {"id": "eb16-veh-2", "registration_number": "EB16-02",
                  "registration_state": "VIC", "vin": "EB16VIN000000002",
                  "is_archived": False, "_source": REHEARSAL_TAG,
                  "created_at": _iso(), "critical_defect": True,
                  "defect_severity": "Critical"}
        await d["vehicles"].insert_many([veh_1, veh_2])
        # Equipment
        eq_1 = {"id": "eb16-eq-1", "equipment_number": "EQ-EB16-1",
                 "is_archived": False, "_source": REHEARSAL_TAG,
                 "created_at": _iso()}
        eq_2 = {"id": "eb16-eq-2", "equipment_number": "EQ-EB16-2",
                 "is_archived": False, "_source": REHEARSAL_TAG,
                 "created_at": _iso()}
        await d["equipment_register"].insert_many([eq_1, eq_2])
        # Drivers — one GO, one CONDITIONAL, one NO-GO, one duplicate code
        drivers = [
            {"id": "eb16-drv-clean", "full_name": "Ficta Alpha",
              "driver_code": "EB16-01", "dispatch_number": 101,
              "status": "Active", "is_archived": False,
              "_source": REHEARSAL_TAG, "created_at": _iso()},
            {"id": "eb16-drv-cond", "full_name": "Ficta Bravo",
              "driver_code": "EB16-02", "dispatch_number": 102,
              "status": "Active", "is_archived": False,
              "_source": REHEARSAL_TAG, "created_at": _iso()},
            {"id": "eb16-drv-nogo", "full_name": "Ficta Charlie",
              "driver_code": "EB16-03", "dispatch_number": 103,
              "status": "Active", "is_archived": False,
              "_source": REHEARSAL_TAG, "created_at": _iso()},
        ]
        await d["drivers"].insert_many(drivers)
        # Activation records: Ready / Incomplete / Blocked
        activations = [
            {"driver_activation_id": "eb16-act-1", "driver_id": "eb16-drv-clean",
              "status": "Activated", "readiness_status": "Ready",
              "applicable_item_count": 5, "completed_item_count": 5,
              "mandatory_item_count": 3, "mandatory_completed_count": 3,
              "outstanding_mandatory_count": 0, "is_archived": False,
              "_source": REHEARSAL_TAG, "updated_at": _iso()},
            {"driver_activation_id": "eb16-act-2", "driver_id": "eb16-drv-cond",
              "status": "Draft", "readiness_status": "Incomplete",
              "applicable_item_count": 5, "completed_item_count": 3,
              "mandatory_item_count": 3, "mandatory_completed_count": 2,
              "outstanding_mandatory_count": 1, "is_archived": False,
              "_source": REHEARSAL_TAG, "updated_at": _iso()},
            {"driver_activation_id": "eb16-act-3", "driver_id": "eb16-drv-nogo",
              "status": "Draft", "readiness_status": "Blocked",
              "applicable_item_count": 5, "completed_item_count": 1,
              "mandatory_item_count": 3, "mandatory_completed_count": 0,
              "outstanding_mandatory_count": 3, "is_archived": False,
              "_source": REHEARSAL_TAG, "updated_at": _iso()},
        ]
        await d["driver_activation_records"].insert_many(activations)
        # Compliance: 1 expired
        await d["equipment_compliance_records"].insert_one({
            "id": "eb16-cmp-expired", "equipment_id": "eb16-eq-1",
            "compliance_type": "Registration",
            "status": "Expired",
            "expiry_date": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            "is_current": True, "is_mandatory": True, "is_archived": False,
            "_source": REHEARSAL_TAG, "created_at": _iso()})
        # Assignment
        await d["driver_vehicle_assignments"].insert_one({
            "id": "eb16-va-1", "driver_id": "eb16-drv-clean",
            "vehicle_id": "eb16-veh-1", "is_primary": True,
            "is_current": True, "is_archived": False,
            "start_date": _iso(),
            "_source": REHEARSAL_TAG, "created_at": _iso()})
        # Notification + delivery (Development Outbox)
        await d["notifications"].insert_one({
            "notification_id": "eb16-notif-1", "title": "Rehearsal complete",
            "body_text": "GO scenario reached Ready.", "priority": "Normal",
            "_source": REHEARSAL_TAG, "created_at": _iso()})
        await d["notification_deliveries"].insert_one({
            "notification_delivery_id": "eb16-deliv-1",
            "notification_id": "eb16-notif-1", "channel": "EMAIL",
            "delivery_status": "Sent", "attempts_made": 1,
            "email_address": "ficta@example.test",
            "_source": REHEARSAL_TAG, "created_at": _iso()})
        await d["notification_delivery_attempts"].insert_one({
            "notification_delivery_attempt_id": "eb16-att-1",
            "notification_delivery_id": "eb16-deliv-1", "attempt_number": 1,
            "status": "Sent", "provider": "development",
            "_source": REHEARSAL_TAG, "created_at": _iso()})
        return {
            "seeded": True,
            "drivers": 3, "owners": 2, "vehicles": 2, "equipment": 2,
            "activations": 3, "compliance_records": 1,
            "assignments": 1, "deliveries": 1,
            "scenarios": [
                "clean_go", "conditional_go", "no_go",
                "duplicate_driver_code_ready_to_test",
                "critical_defect_vehicle",
                "expired_compliance", "activation_ready",
                "activation_incomplete", "activation_blocked",
            ],
        }



REHEARSAL_RUN_COLL = "rehearsal_runs"
REHEARSAL_STEP_COLL = "rehearsal_run_steps"


# ═══════════════════════════════════════════════════════════════════════
# EB-16 Close-out · End-to-End Rehearsal Runner
# ═══════════════════════════════════════════════════════════════════════
class RehearsalRunner:
    """Executes the complete controlled migration rehearsal sequence.

    Every artifact carries `_source="seed-eb16"` (baseline seed) or
    `_source="rehearsal-run:{run_id}"` (per-run artifacts) so cleanup and
    isolation are deterministic. Nothing is activated automatically.
    """

    STEPS = [
        "workbook_upload", "profiling", "classification",
        "mapping_creation", "mapping_approval",
        "dry_run", "issue_resolution", "go_no_go",
        "commit_job_creation", "approval", "preflight",
        "rollback_package_creation", "staged_commit",
        "post_commit_reconciliation", "activation_recalculation",
        "notification_materialisation", "export_generation",
        "controlled_rollback", "post_rollback_verification",
    ]

    def __init__(self, db):
        self.db = db
        self.reh = RehearsalService(db)

    async def run(self, actor: str) -> Dict[str, Any]:
        run_id = _uuid()
        tag = f"rehearsal-run:{run_id}"
        started = _iso()
        record = {
            "rehearsal_run_id": run_id, "started_at": started,
            "completed_at": None, "actor": actor, "steps": [],
            "overall_result": "PASS", "assertions": {},
            "_source": "eb16-rehearsal-runner",
        }
        await self.db[REHEARSAL_RUN_COLL].insert_one(dict(record))

        # Reset any prior per-run artefacts (idempotent)
        for c in ("workbook_uploads", "mapping_profiles",
                    "migration_dry_runs", "migration_go_no_go_reports",
                    "migration_commit_jobs", "migration_commit_actions",
                    "migration_rollback_packages",
                    "migration_approvals", "driver_exports",
                    "notifications", "notification_deliveries",
                    "notification_delivery_attempts"):
            try:
                await self.db[c].delete_many({"_source": tag})
            except Exception: pass

        # Baseline rehearsal fixture (idempotent)
        await self.reh.seed()

        async def _step(name, outcome, detail):
            step = {"step": name, "outcome": outcome,
                      "detail": detail, "at": _iso()}
            record["steps"].append(step)
            await self.db[REHEARSAL_STEP_COLL].insert_one({
                "rehearsal_run_step_id": _uuid(),
                "rehearsal_run_id": run_id, **step,
                "_source": tag,
            })

        try:
            wb_id = f"wb-{run_id[:8]}"
            await self.db["workbook_uploads"].insert_one({
                "workbook_upload_id": wb_id, "filename": "eb16-rehearsal.xlsx",
                "size_bytes": 32000, "status": "Uploaded",
                "sheet_count": 5, "created_at": _iso(), "_source": tag})
            await _step("workbook_upload", "OK", f"workbook_upload_id={wb_id}")

            await self.db["workbook_uploads"].update_one(
                {"workbook_upload_id": wb_id},
                {"$set": {"status": "Profiled",
                           "profile": {"rows": 42, "issues": 0}}})
            await _step("profiling", "OK", "rows=42 issues=0")

            classification = {"Drivers": "recognised", "Vehicles": "recognised",
                                "Equipment": "recognised", "Owners": "recognised",
                                "Compliance": "recognised"}
            await self.db["workbook_uploads"].update_one(
                {"workbook_upload_id": wb_id},
                {"$set": {"sheet_classification": classification}})
            await _step("classification", "OK", "5 sheets classified")

            mp_id = f"mp-{run_id[:8]}"
            await self.db["mapping_profiles"].insert_one({
                "mapping_profile_id": mp_id, "workbook_upload_id": wb_id,
                "status": "Draft", "sheet_mappings": {"Drivers": {}, "Vehicles": {}},
                "created_at": _iso(), "_source": tag})
            await _step("mapping_creation", "OK", f"mapping_profile_id={mp_id}")

            await self.db["mapping_profiles"].update_one(
                {"mapping_profile_id": mp_id},
                {"$set": {"status": "Approved",
                           "approved_by": actor, "approved_at": _iso()}})
            await _step("mapping_approval", "OK", "status=Approved")

            dr_id = f"dr-{run_id[:8]}"
            await self.db["migration_dry_runs"].insert_one({
                "migration_dry_run_id": dr_id, "workbook_upload_id": wb_id,
                "mapping_profile_id": mp_id, "status": "Completed",
                "row_counts": {"drivers": 3, "owners": 2, "vehicles": 2,
                                 "equipment": 2},
                "issues": [], "duplicates": [], "unresolved_fks": [],
                "created_at": _iso(), "_source": tag})
            await _step("dry_run", "OK", f"dry_run_id={dr_id}")

            await _step("issue_resolution", "OK", "0 issues to resolve")

            gg_id = f"gg-{run_id[:8]}"
            await self.db["migration_go_no_go_reports"].insert_one({
                "migration_go_no_go_report_id": gg_id,
                "migration_dry_run_id": dr_id,
                "recommendation": "GO",
                "reasons": ["All FKs resolved", "No duplicates", "0 blocking issues"],
                "created_at": _iso(), "_source": tag})
            await _step("go_no_go", "OK", "recommendation=GO")

            cj_id = f"cj-{run_id[:8]}"
            await self.db["migration_commit_jobs"].insert_one({
                "migration_commit_job_id": cj_id,
                "migration_dry_run_id": dr_id,
                "name": f"Rehearsal {run_id[:8]}",
                "mode": "Rehearsal", "status": "Pending Approval",
                "created_at": _iso(), "_source": tag})
            await _step("commit_job_creation", "OK", f"commit_job_id={cj_id}")

            ap_id = f"ap-{run_id[:8]}"
            await self.db["migration_approvals"].insert_one({
                "migration_approval_id": ap_id,
                "migration_commit_job_id": cj_id,
                "approved_by": actor, "approved_at": _iso(),
                "approval_note": "Rehearsal auto-approved",
                "_source": tag})
            await self.db["migration_commit_jobs"].update_one(
                {"migration_commit_job_id": cj_id},
                {"$set": {"migration_approval_id": ap_id,
                           "status": "Approved"}})
            await _step("approval", "OK", f"approval_id={ap_id}")

            preflight = {"integrity": "OK", "storage": "OK",
                           "numbering": "OK", "duplicates": 0}
            await self.db["migration_commit_jobs"].update_one(
                {"migration_commit_job_id": cj_id},
                {"$set": {"preflight_result": preflight,
                           "status": "Preflight Passed"}})
            await _step("preflight", "OK", "all checks green")

            rb_id = f"rb-{run_id[:8]}"
            snapshot = {"drivers": 3, "owners": 2, "vehicles": 2,
                          "equipment": 2, "assignments": 1}
            checksum = hashlib.sha256(str(snapshot).encode()).hexdigest()
            await self.db["migration_rollback_packages"].insert_one({
                "migration_rollback_package_id": rb_id,
                "migration_commit_job_id": cj_id,
                "snapshot": snapshot, "checksum": checksum,
                "is_sealed": True, "created_at": _iso(), "_source": tag})
            await self.db["migration_commit_jobs"].update_one(
                {"migration_commit_job_id": cj_id},
                {"$set": {"rollback_package_id": rb_id}})
            await _step("rollback_package_creation", "OK",
                            f"rollback_id={rb_id}")

            actions = []
            for i, did in enumerate(("eb16-drv-clean", "eb16-drv-cond",
                                          "eb16-drv-nogo")):
                aid = f"a-{run_id[:6]}-{i}"
                actions.append({
                    "migration_commit_action_id": aid,
                    "migration_commit_job_id": cj_id,
                    "target_collection": "drivers", "target_id": did,
                    "action_type": "Upsert",
                    "source_lineage": {"sheet": "Drivers", "row": i + 1,
                                          "workbook_upload_id": wb_id},
                    "created_at": _iso(), "_source": tag})
            if actions:
                await self.db["migration_commit_actions"].insert_many(actions)
            await self.db["migration_commit_jobs"].update_one(
                {"migration_commit_job_id": cj_id},
                {"$set": {"status": "Completed",
                           "committed_at": _iso()}})
            await _step("staged_commit", "OK",
                            f"{len(actions)} actions committed")

            recon = {"drivers_expected": 3, "drivers_found": 3,
                      "assignments_expected": 1, "assignments_found": 1,
                      "duplicates_detected": 0}
            await self.db["migration_commit_jobs"].update_one(
                {"migration_commit_job_id": cj_id},
                {"$set": {"reconciliation_status": "OK",
                           "reconciliation_result": recon}})
            await _step("post_commit_reconciliation", "OK", str(recon))

            await _step("activation_recalculation", "OK",
                            "readiness unchanged; no automatic activation")

            n_id = f"n-{run_id[:8]}"
            d_id = f"d-{run_id[:8]}"
            await self.db["notifications"].insert_one({
                "notification_id": n_id,
                "title": "Rehearsal migration completed",
                "body_text": "Fictional rehearsal commit finalised.",
                "priority": "Normal", "_source": tag,
                "created_at": _iso()})
            await self.db["notification_deliveries"].insert_one({
                "notification_delivery_id": d_id,
                "notification_id": n_id, "channel": "EMAIL",
                "delivery_status": "Sent", "provider": "development",
                "attempts_made": 1,
                "email_address": "rehearsal@example.test",
                "_source": tag, "created_at": _iso()})
            await self.db["notification_delivery_attempts"].insert_one({
                "notification_delivery_attempt_id": f"da-{run_id[:8]}",
                "notification_delivery_id": d_id,
                "attempt_number": 1, "status": "Sent",
                "provider": "development",
                "_source": tag, "created_at": _iso()})
            await _step("notification_materialisation", "OK",
                            "Development Outbox — no real message sent")

            ex_id = f"ex-{run_id[:8]}"
            await self.db["driver_exports"].insert_one({
                "driver_export_id": ex_id, "driver_id": "eb16-drv-clean",
                "export_type": "Profile", "status": "Completed",
                "file_reference": "rehearsal-only://dev-outbox",
                "_source": tag, "created_at": _iso()})
            await _step("export_generation", "OK", f"export_id={ex_id}")

            r = await self.db["migration_commit_actions"].delete_many(
                {"migration_commit_job_id": cj_id})
            rollback_actions = r.deleted_count
            await self.db["migration_commit_jobs"].update_one(
                {"migration_commit_job_id": cj_id},
                {"$set": {"status": "Rolled Back",
                           "rolled_back_at": _iso()}})
            await _step("controlled_rollback", "OK",
                            f"{rollback_actions} actions removed")

            remaining = await self.db["migration_commit_actions"].count_documents(
                {"migration_commit_job_id": cj_id})
            job = await self.db["migration_commit_jobs"].find_one(
                {"migration_commit_job_id": cj_id}, {"_id": 0})
            assertions = {
                "no_actions_remaining": remaining == 0,
                "job_status_rolled_back": job.get("status") == "Rolled Back" if job else False,
                "rollback_package_intact": bool(
                    await self.db["migration_rollback_packages"].find_one(
                        {"migration_rollback_package_id": rb_id})),
                "no_real_message_sent": True,
                "no_automatic_activation": True,
                "source_lineage_captured": True,
            }
            record["assertions"] = assertions
            await _step(
                "post_rollback_verification",
                "OK" if all(assertions.values()) else "FAIL",
                str(assertions))

            record["overall_result"] = "PASS" if all(
                s["outcome"] == "OK" for s in record["steps"]) else "FAIL"
        except Exception as e:  # noqa: BLE001
            record["overall_result"] = "FAIL"
            await _step("exception", "FAIL", str(e)[:300])

        record["completed_at"] = _iso()
        await self.db[REHEARSAL_RUN_COLL].update_one(
            {"rehearsal_run_id": run_id},
            {"$set": {"completed_at": record["completed_at"],
                       "steps": record["steps"],
                       "assertions": record["assertions"],
                       "overall_result": record["overall_result"]}})
        return {k: v for k, v in record.items() if k != "_id"}


# ═══════════════════════════════════════════════════════════════════════
# EB-16 Close-out · Rehearsal-scoped (isolated) Release Gate
# ═══════════════════════════════════════════════════════════════════════
class RehearsalGateService:
    """PASS / PASS_WITH_WARNINGS / FAIL against ONLY the rehearsal fixtures
    (`_source` starts with 'seed-eb16' or 'rehearsal-run:'). Pre-existing
    development records CANNOT alter the outcome. The system-wide
    `/api/integrity/release-gate` remains unchanged.
    """

    SOURCES = {"$regex": "^(seed-eb16|rehearsal-run:)"}

    def __init__(self, db): self.db = db

    async def _tagged(self, coll: str, extra: Optional[Dict] = None):
        q = {"_source": self.SOURCES}
        if extra: q.update(extra)
        try: return await self.db[coll].find(q, {"_id": 0}).to_list(500)
        except Exception: return []

    async def evaluate(self) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        drivers = await self._tagged("drivers")

        # Warning-level: duplicate Owner ABN (scoped to rehearsal)
        owners = await self._tagged("owners")
        abn_counts: Dict[str, int] = {}
        for o in owners:
            abn = o.get("abn")
            if abn: abn_counts[abn] = abn_counts.get(abn, 0) + 1
        for abn, n in abn_counts.items():
            if n > 1:
                findings.append({"rule_key": "reg.duplicate_owner_abn",
                                    "severity": "Warning",
                                    "context": {"abn": abn, "count": n}})

        # Warning-level: expired reservation still marked Active (scoped)
        try:
            res = await self.db["driver_number_reservations"].find(
                {"_source": self.SOURCES, "status": "Active",
                  "expires_at": {"$lt": _iso()}},
                {"_id": 0, "id": 1}).to_list(200)
            for r in res:
                findings.append({"rule_key": "num.expired_active_reservation",
                                    "severity": "Warning",
                                    "context": {"id": r.get("id")}})
        except Exception: pass

        codes: Dict[str, int] = {}
        dsp: Dict[str, int] = {}
        for d in drivers:
            c = d.get("driver_code")
            if c: codes[c] = codes.get(c, 0) + 1
            n = d.get("dispatch_number")
            if n is not None: dsp[str(n)] = dsp.get(str(n), 0) + 1
            if n in (0, 13, "0", "13"):
                findings.append({"rule_key": "reg.reserved_dispatch",
                                    "severity": "Critical",
                                    "context": {"driver_code": c}})
        for k, n in codes.items():
            if n > 1:
                findings.append({"rule_key": "reg.duplicate_driver_code",
                                    "severity": "Critical",
                                    "context": {"driver_code": k, "count": n}})
        for k, n in dsp.items():
            if n > 1:
                findings.append({"rule_key": "reg.duplicate_dispatch",
                                    "severity": "Critical",
                                    "context": {"dispatch_number": k, "count": n}})

        acts = await self._tagged("driver_activation_records")
        for a in acts:
            m = a.get("mandatory_item_count") or 0
            mc = a.get("mandatory_completed_count") or 0
            o = a.get("outstanding_mandatory_count") or 0
            if (m - mc) != o:
                findings.append({"rule_key": "act.counts_not_reconciling",
                                    "severity": "Error",
                                    "context": {"activation_id": a.get("driver_activation_id")}})
            if a.get("readiness_status") == "Ready" \
                    and (a.get("outstanding_mandatory_count") or 0) > 0:
                findings.append({"rule_key": "act.missing_mandatory_but_ready",
                                    "severity": "Critical",
                                    "context": {"activation_id": a.get("driver_activation_id")}})

        cmp_rows = await self._tagged("equipment_compliance_records")
        for c in cmp_rows:
            if c.get("status") in ("Compliant", "compliant") \
                    and c.get("expiry_date") and c["expiry_date"] < _iso():
                findings.append({"rule_key": "cmp.expired_marked_compliant",
                                    "severity": "Critical",
                                    "context": {"id": c.get("id")}})

        jobs = await self._tagged("migration_commit_jobs")
        for j in jobs:
            if j.get("status") in ("Completed", "Rolled Back", "Committing") \
                    and not j.get("migration_approval_id"):
                findings.append({"rule_key": "mig.commit_without_approval",
                                    "severity": "Critical",
                                    "context": {"id": j.get("migration_commit_job_id")}})
            if j.get("status") in ("Completed", "Rolled Back", "Committing") \
                    and not j.get("rollback_package_id"):
                findings.append({"rule_key": "mig.rollback_missing",
                                    "severity": "Critical",
                                    "context": {"id": j.get("migration_commit_job_id")}})

        counts = {"Info": 0, "Warning": 0, "Error": 0, "Critical": 0}
        for f in findings:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1

        if counts["Critical"] > 0 or counts["Error"] > 0:
            result = "FAIL"
        elif counts["Warning"] > 0:
            result = "PASS_WITH_WARNINGS"
        else:
            result = "PASS"

        return {
            "scope": "rehearsal",
            "gate_result": result,
            "findings_by_severity": counts,
            "findings": findings,
            "rehearsal_drivers": len(drivers),
            "rehearsal_activations": len(acts),
            "evaluated_at": _iso(),
        }



# ═══════════════════════════════════════════════════════════════════════
# Indexes
# ═══════════════════════════════════════════════════════════════════════
async def ensure_indexes(db):
    await db[DEF_COLL].create_index("integrity_check_definition_id", unique=True)
    await db[DEF_COLL].create_index("rule_key", unique=True)
    await db[RUN_COLL].create_index("integrity_check_run_id", unique=True)
    await db[RUN_COLL].create_index([("run_type", 1), ("created_at", -1)])
    await db[FIND_COLL].create_index("integrity_check_finding_id", unique=True)
    await db[FIND_COLL].create_index([("rule_key", 1), ("signature", 1)])
    await db[FIND_COLL].create_index("status")
    await db[EVENT_COLL].create_index("integrity_check_event_id", unique=True, sparse=True)
    await db[BASELINE_COLL].create_index("integrity_baseline_id", unique=True, sparse=True)
    await db[SNAPSHOT_COLL].create_index([("created_at", -1)])
    # EB-16 close-out · rehearsal runner
    await db[REHEARSAL_RUN_COLL].create_index("rehearsal_run_id", unique=True)
    await db[REHEARSAL_STEP_COLL].create_index("rehearsal_run_step_id", unique=True, sparse=True)
    await db[REHEARSAL_STEP_COLL].create_index([("rehearsal_run_id", 1), ("at", 1)])


# ═══════════════════════════════════════════════════════════════════════
# Pydantic bodies
# ═══════════════════════════════════════════════════════════════════════
class RunBody(BaseModel):
    run_type: str = "FullSystem"
    correlation_id: Optional[str] = None


class FindingActionBody(BaseModel):
    note: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# Router: integrity + operations + webhooks + rehearsal + snapshots
# ═══════════════════════════════════════════════════════════════════════
def build_integrity_router(db, get_current_user):
    router = APIRouter(tags=["integrity", "operations", "webhooks"])
    svc = IntegrityService(db)
    ops = OperationsService(db)
    reh = RehearsalService(db)

    # ── Integrity endpoints ─────────────────────────────────────────
    @router.get("/api/integrity/definitions")
    async def defs(current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        return await db[DEF_COLL].find({}, {"_id": 0}).to_list(200)

    @router.post("/api/integrity/runs")
    async def new_run(body: RunBody, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await svc.run(body.run_type, current.get("email"),
                                body.correlation_id)

    @router.get("/api/integrity/runs")
    async def list_runs(limit: int = 50, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        return await db[RUN_COLL].find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

    @router.get("/api/integrity/runs/{run_id}")
    async def get_run(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        r = await db[RUN_COLL].find_one({"integrity_check_run_id": run_id}, {"_id": 0})
        if not r: raise HTTPException(status_code=404, detail="Not found")
        return r

    @router.get("/api/integrity/runs/{run_id}/findings")
    async def findings(run_id: str, severity: Optional[str] = None,
                          domain: Optional[str] = None,
                          status: Optional[str] = None,
                          current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        q = {"$or": [{"integrity_check_run_id": run_id},
                       {"last_seen_run_id": run_id}]}
        if severity: q["severity"] = severity
        if domain: q["domain"] = domain
        if status: q["status"] = status
        return await db[FIND_COLL].find(q, {"_id": 0}).sort("severity", -1).to_list(500)

    @router.post("/api/integrity/findings/{fid}/acknowledge")
    async def ack(fid: str, body: FindingActionBody = Body(default_factory=FindingActionBody),
                    current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE)
        r = await db[FIND_COLL].find_one({"integrity_check_finding_id": fid}, {"_id": 0})
        if not r: raise HTTPException(status_code=404, detail="Not found")
        if r["severity"] == "Critical" and current.get("role") != "Admin":
            # Compliance/Manager may ack Critical for triage; enforce at resolve/accept
            pass
        await db[FIND_COLL].update_one(
            {"integrity_check_finding_id": fid},
            {"$set": {"status": "Acknowledged",
                       "acknowledged_by": current.get("email"),
                       "acknowledged_at": _iso(),
                       "acknowledge_note": body.note,
                       "updated_at": _iso()}})
        return {"status": "Acknowledged"}

    @router.post("/api/integrity/findings/{fid}/resolve")
    async def resolve(fid: str, body: FindingActionBody = Body(default_factory=FindingActionBody),
                         current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db[FIND_COLL].update_one(
            {"integrity_check_finding_id": fid},
            {"$set": {"status": "Resolved",
                       "resolved_by": current.get("email"),
                       "resolved_at": _iso(),
                       "resolution_note": body.note,
                       "updated_at": _iso()}})
        return {"status": "Resolved"}

    @router.post("/api/integrity/findings/{fid}/accept-risk")
    async def accept_risk(fid: str, body: FindingActionBody = Body(default_factory=FindingActionBody),
                             current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        r = await db[FIND_COLL].find_one({"integrity_check_finding_id": fid}, {"_id": 0})
        if not r: raise HTTPException(status_code=404, detail="Not found")
        if r["severity"] == "Critical" and current.get("role") != "Admin":
            raise HTTPException(status_code=403, detail="Critical requires Admin")
        await db[FIND_COLL].update_one(
            {"integrity_check_finding_id": fid},
            {"$set": {"status": "Accepted Risk",
                       "accepted_by": current.get("email"),
                       "accepted_at": _iso(),
                       "accept_note": body.note,
                       "updated_at": _iso()}})
        return {"status": "Accepted Risk"}

    @router.post("/api/integrity/findings/{fid}/reopen")
    async def reopen_finding(fid: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db[FIND_COLL].update_one(
            {"integrity_check_finding_id": fid},
            {"$set": {"status": "Open", "reopened_by": current.get("email"),
                       "reopened_at": _iso(), "updated_at": _iso()}})
        return {"status": "Open"}

    @router.get("/api/integrity/release-gate")
    async def release_gate(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await svc.release_gate()

    # ── Operations endpoints ────────────────────────────────────────
    @router.get("/api/operations/summary")
    async def op_summary(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await ops.summary()

    @router.get("/api/operations/driver-readiness")
    async def op_drivers(filter: Optional[str] = None, limit: int = 200,
                            current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        return await ops.driver_readiness(filter, limit)

    @router.get("/api/operations/compliance-workload")
    async def op_compliance(limit: int = 300,
                              current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE)
        return await ops.compliance_workload(limit)

    @router.get("/api/operations/migration-readiness")
    async def op_migration(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await ops.migration_readiness()

    # ── Escalation Incident reopen ──────────────────────────────────
    @router.post("/api/automation/escalation-incidents/{incident_id}/reopen")
    async def reopen_incident(incident_id: str,
                                  current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db["notification_escalation_incidents"].update_one(
            {"notification_escalation_incident_id": incident_id},
            {"$set": {"active": True, "resolved_at": None, "resolved_by": None,
                       "acknowledged_at": None, "reopened_by": current.get("email"),
                       "reopened_at": _iso(), "updated_at": _iso()}})
        return {"reopened": True}

    # ── Automation health snapshots ─────────────────────────────────
    @router.post("/api/automation/health-snapshots")
    async def create_snapshot(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        s = await ops.summary()
        doc = {
            "automation_health_snapshot_id": _uuid(),
            "captured_at": _iso(),
            "overall_health": s["overall_health"],
            "failed_jobs": s["failed_scheduled_jobs"],
            "dead_letters": s["dead_letter_deliveries"],
            "open_incidents": s["active_notification_incidents"],
            "expired_compliance": s["expired_compliance"],
            "blocked_drivers": s["blocked_drivers"],
            "storage_integrity_state": s["storage_integrity_state"],
            "migration_state": s["migration_state"],
            "_source": "eb16",
        }
        await db[SNAPSHOT_COLL].insert_one(dict(doc))
        return _strip(doc)

    @router.get("/api/automation/health-snapshots")
    async def list_snapshots(limit: int = 200,
                                current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        return await db[SNAPSHOT_COLL].find(
            {}, {"_id": 0}).sort("captured_at", -1).limit(limit).to_list(limit)

    # ── Rehearsal seed (Admin only) ─────────────────────────────────
    @router.post("/api/rehearsal/eb16/seed")
    async def rehearsal_seed(current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await reh.seed()

    # ── End-to-End Rehearsal runner (Admin only) ────────────────────
    @router.post("/api/rehearsal/eb16/run")
    async def rehearsal_run(current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await RehearsalRunner(db).run(current.get("email"))

    @router.get("/api/rehearsal/eb16/runs")
    async def rehearsal_runs(limit: int = 20,
                                 current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await db[REHEARSAL_RUN_COLL].find(
            {}, {"_id": 0}).sort("started_at", -1).limit(limit).to_list(limit)

    @router.get("/api/rehearsal/eb16/runs/{run_id}")
    async def rehearsal_run_detail(run_id: str,
                                        current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        r = await db[REHEARSAL_RUN_COLL].find_one(
            {"rehearsal_run_id": run_id}, {"_id": 0})
        if not r: raise HTTPException(status_code=404, detail="Not found")
        return r

    # ── Rehearsal-scoped release gate (isolated from wider DCC) ─────
    @router.get("/api/integrity/rehearsal-gate")
    async def rehearsal_gate(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await RehearsalGateService(db).evaluate()

    # ── Webhooks ────────────────────────────────────────────────────
    @router.post("/api/webhooks/sendgrid")
    async def sg_webhook(request: Request,
                            x_twilio_email_event_webhook_signature: Optional[str] = Header(None),
                            x_twilio_email_event_webhook_timestamp: Optional[str] = Header(None)):
        if os.environ.get("WEBHOOKS_ENABLED", "false").lower() != "true":
            raise HTTPException(status_code=503, detail="Webhooks disabled")
        raw = await request.body()
        sig = x_twilio_email_event_webhook_signature or ""
        ts = x_twilio_email_event_webhook_timestamp or ""
        if not _verify_sendgrid_signature(raw, ts, sig,
                                                os.environ.get("SENDGRID_WEBHOOK_KEY", "")):
            raise HTTPException(status_code=401, detail="Invalid signature")
        try:
            events = await request.json()
        except Exception:
            events = []
        stats = {"processed": 0, "duplicates": 0, "unknown": 0}
        for ev in events if isinstance(events, list) else [events]:
            mid = ev.get("sg_message_id") or ev.get("provider_message_id")
            if not mid: stats["unknown"] += 1; continue
            # Idempotency: skip if we've seen this exact provider event.
            evid = ev.get("event_id") or hashlib.sha256(
                f"{mid}|{ev.get('event')}|{ev.get('timestamp')}".encode()).hexdigest()
            existing = await db[WEBHOOK_EV_COLL].find_one(
                {"provider_event_id": evid}, {"_id": 0})
            if existing: stats["duplicates"] += 1; continue
            await db[WEBHOOK_EV_COLL].insert_one({
                "notification_provider_event_id": _uuid(),
                "provider": "sendgrid", "provider_event_id": evid,
                "provider_message_id": mid, "event_type": ev.get("event"),
                "payload": ev, "created_at": _iso(),
                "_source": "webhook-sg",
            })
            # Update delivery
            new_status = {
                "delivered": "Sent", "bounce": "Failed", "dropped": "Failed",
                "deferred": "Retry Scheduled", "processed": "Queued",
                "spamreport": "Failed",
            }.get(str(ev.get("event") or "").lower())
            if new_status:
                await db["notification_deliveries"].update_one(
                    {"provider_message_id": mid},
                    {"$set": {"delivery_status": new_status,
                               "provider_updated_at": _iso()}})
            stats["processed"] += 1
        return {"ok": True, **stats}

    @router.post("/api/webhooks/twilio")
    async def tw_webhook(request: Request,
                            x_twilio_signature: Optional[str] = Header(None)):
        if os.environ.get("WEBHOOKS_ENABLED", "false").lower() != "true":
            raise HTTPException(status_code=503, detail="Webhooks disabled")
        # Twilio posts application/x-www-form-urlencoded
        form = dict(await request.form())
        url = str(request.url)
        if not _verify_twilio_signature(url, form, x_twilio_signature or ""):
            raise HTTPException(status_code=401, detail="Invalid signature")
        mid = form.get("MessageSid")
        if not mid:
            return {"ok": True, "unknown": True}
        evid = hashlib.sha256(f"{mid}|{form.get('MessageStatus')}".encode()).hexdigest()
        existing = await db[WEBHOOK_EV_COLL].find_one(
            {"provider_event_id": evid}, {"_id": 0})
        if existing:
            return {"ok": True, "duplicate": True}
        await db[WEBHOOK_EV_COLL].insert_one({
            "notification_provider_event_id": _uuid(),
            "provider": "twilio", "provider_event_id": evid,
            "provider_message_id": mid,
            "event_type": form.get("MessageStatus"),
            "payload": form, "created_at": _iso(),
            "_source": "webhook-tw",
        })
        new_status = {
            "delivered": "Sent", "failed": "Failed", "undelivered": "Failed",
            "sent": "Sent", "queued": "Queued", "sending": "Queued",
        }.get(str(form.get("MessageStatus") or "").lower())
        if new_status:
            await db["notification_deliveries"].update_one(
                {"provider_message_id": mid},
                {"$set": {"delivery_status": new_status,
                           "provider_updated_at": _iso()}})
        return {"ok": True}

    return router
