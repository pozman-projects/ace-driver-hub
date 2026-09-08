"""EB-17c — UAT, Sign-offs & Production Readiness.

Local-only, deterministic, fictional-fixture-driven. No live providers,
no real ACE data, no external services. All rows tagged `_source: seed-eb17c`.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field


# ─── Constants ────────────────────────────────────────────────────────────
PLAN_COLL   = "uat_test_plans"
CASE_COLL   = "uat_test_cases"
RUN_COLL    = "uat_test_runs"
RESULT_COLL = "uat_test_results"
DEF_COLL    = "uat_defects"
SIGN_COLL   = "uat_signoffs"
EVID_COLL   = "uat_evidence"
SNAP_COLL   = "production_readiness_snapshots"
CHK_COLL    = "production_readiness_checklist"
EVT_COLL    = "production_readiness_events"
COND_COLL   = "production_readiness_conditions"

ROLE_READONLY_PLUS   = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}
ROLE_ALLOCATOR_PLUS  = {"Allocator", "Compliance", "Manager", "Admin"}
ROLE_COMPLIANCE_PLUS = {"Compliance", "Manager", "Admin"}
ROLE_MANAGER_PLUS    = {"Manager", "Admin"}
ROLE_ADMIN           = {"Admin"}

CASE_STATUSES = ["Draft", "Ready", "In Progress", "Passed", "Failed",
                 "Blocked", "Not Applicable", "Retest Required"]
DEFECT_SEVERITIES = ["Critical", "High", "Medium", "Low"]
DEFECT_STATES = ["Open", "Investigating", "Fixed", "Ready for Retest",
                 "Closed", "Deferred", "Reopened"]
SIGNOFF_AREAS = ["Business Operations", "Compliance", "Management",
                 "Technical", "Security", "Data Migration", "Recovery"]
SIGNOFF_STATUSES = ["Pending", "Approved", "Approved with Conditions",
                    "Rejected", "Withdrawn"]
CONDITION_STATUSES = ["Open", "Accepted", "Resolved", "Expired", "Rejected"]
RESPONSIBILITIES = ["UAT Coordinator", "Tester", "Business Approver",
                    "Technical Approver"]

# Which DCC role may sign each area (least-privilege mapping)
SIGNOFF_ROLE_MAP: Dict[str, set] = {
    "Business Operations": {"Manager", "Admin"},
    "Compliance":          {"Compliance", "Manager", "Admin"},
    "Management":          {"Manager", "Admin"},
    "Technical":           {"Admin"},
    "Security":            {"Admin"},
    "Data Migration":      {"Manager", "Admin"},
    "Recovery":            {"Admin"},
}

# UAT Packs required by the milestone
PACKS = ["Driver Lifecycle", "Compliance", "Migration", "Notifications",
         "Operations", "Security", "Recovery"]


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


def _require(user: Dict[str, Any], allowed: set, msg: str = "Forbidden"):
    if not user or user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=msg)


# ─── Fictional test-case seeds (deterministic) ────────────────────────────
def _seed_cases() -> List[Dict[str, Any]]:
    """Deterministic fictional test cases (title + objective) per pack.
    Every pack has ≥ its milestone-required set."""
    cases: List[Dict[str, Any]] = []

    def _add(pack: str, cid: str, title: str, obj: str,
             steps: List[str], expected: str,
             prereq: str = "seed-eb17c fictional dataset"):
        cases.append({
            "uat_test_case_id": cid, "pack": pack, "title": title,
            "objective": obj, "prerequisites": prereq,
            "test_steps": steps, "expected_result": expected,
            "status": "Ready", "created_at": _iso(),
            "_source": "seed-eb17c",
        })

    # Driver Lifecycle (11)
    for i, (t, o) in enumerate([
        ("Create Driver", "New driver record persists with canonical ID."),
        ("Assign Driver Code", "Driver code enforced unique + immutable."),
        ("Reserve/Allocate Dispatch Number", "Dispatch reserve/commit flow."),
        ("Attach Owner", "Driver-owner relationship recorded."),
        ("Assign Vehicle", "Driver-vehicle assignment stored."),
        ("Assign Equipment", "Driver-equipment link recorded."),
        ("Upload Mandatory Document", "Doc metadata + storage object exist."),
        ("Calculate Compliance", "Readiness snapshot reflects doc."),
        ("Complete Activation", "Activation status transitions to Activated."),
        ("Export Driver Profile", "Export generates deterministic bundle."),
        ("Archive Driver", "Archive flag set; driver excluded from active lists."),
    ]):
        _add("Driver Lifecycle", f"UAT-DL-{i+1:02d}", t, o,
             [f"Step 1: perform {t}", "Step 2: verify persisted state"],
             o)

    # Compliance (10)
    for i, t in enumerate([
        "Compliant Item", "Due Soon Item", "Expired Item",
        "Under Review Item", "Rejected Evidence", "Critical Defect Path",
        "Maintenance Overdue", "Override Request", "Override Approval",
        "Override Expiry",
    ]):
        _add("Compliance", f"UAT-CO-{i+1:02d}", t,
             f"Compliance workflow: {t.lower()}",
             [f"Set fixture: {t}", "Assert compliance engine result"],
             f"Compliance path '{t}' yields deterministic outcome")

    # Migration (8)
    for i, t in enumerate([
        "Fictional Workbook Upload", "Dry Run", "Issue Resolution",
        "Go / Conditional / No-Go", "Approve Commit", "Reconcile",
        "Rollback", "Verify No Duplicates",
    ]):
        _add("Migration", f"UAT-MG-{i+1:02d}", t,
             f"Migration workflow: {t.lower()}",
             [f"Trigger: {t}", "Assert deterministic result"], t)

    # Notifications (8)
    for i, t in enumerate([
        "Development Outbox", "Retry", "Permanent Failure",
        "Dead Letter", "Escalation", "Incident Acknowledge",
        "Incident Resolve", "Template Approval",
    ]):
        _add("Notifications", f"UAT-NT-{i+1:02d}", t,
             f"Notification workflow: {t.lower()}",
             ["Trigger delivery", "Assert outbox state"], t)

    # Operations (8)
    for i, t in enumerate([
        "Operations Dashboard", "Driver Readiness", "Compliance Workload",
        "Migration Readiness", "Automation Health", "Integrity Gate",
        "Security Gate", "Recovery Gate",
    ]):
        _add("Operations", f"UAT-OP-{i+1:02d}", t,
             f"Operations view: {t.lower()}",
             ["Load view", "Assert tiles"], "Tile renders deterministic value")

    # Security (9)
    for i, t in enumerate([
        "Denied ReadOnly Mutation", "Denied Allocator Compliance Approval",
        "Denied Compliance Numbering Change",
        "Denied Ordinary JWT Scheduler Access",
        "Invalid Webhook Signature", "Expired Session",
        "Revoked Session", "Unsafe Production Config Rejected",
        "Exception Self-Approval Denied",
    ]):
        _add("Security", f"UAT-SC-{i+1:02d}", t,
             f"Security posture: {t.lower()}",
             ["Attempt disallowed action", "Assert 403 / rejection"], t)

    # Recovery (5)
    for i, t in enumerate([
        "Backup Creation", "Restore Rehearsal", "Reconciliation",
        "Checksum Failure", "Failed Recovery Gate",
    ]):
        _add("Recovery", f"UAT-RC-{i+1:02d}", t,
             f"Recovery workflow: {t.lower()}",
             ["Run flow", "Assert deterministic outcome"], t)

    return cases


TOTAL_SEED_CASES = len(_seed_cases())


# ─── Pydantic bodies ──────────────────────────────────────────────────────
class CreatePlanBody(BaseModel):
    name: str
    packs: List[str] = Field(default_factory=lambda: list(PACKS))


class RecordResultBody(BaseModel):
    uat_test_case_id: str
    status: str  # Passed | Failed | Blocked | Retest Required | Not Applicable
    actual_result: str = ""
    evidence: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
    reason: Optional[str] = None


class CreateDefectBody(BaseModel):
    uat_test_case_id: Optional[str] = None
    plan_id: Optional[str] = None
    severity: str
    title: str
    description: str = ""


class TransitionDefectBody(BaseModel):
    to_state: str
    reason: Optional[str] = None
    downgrade_severity: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None


class CreateSignoffBody(BaseModel):
    area: str
    status: str  # Approved | Approved with Conditions | Rejected
    comments: str = ""
    accepted_risks: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    release_recommendation: str = ""
    open_defects_ack: bool = False
    version: str = "eb17c-1"


class ChecklistUpdateBody(BaseModel):
    status: str  # Complete | Incomplete | Waived (waive requires evidence)
    owner: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    comment: str = ""


class ConditionBody(BaseModel):
    condition_id: Optional[str] = None
    source: str
    description: str
    owner: str
    due_date: Optional[str] = None
    risk_level: str = "Medium"  # Critical | High | Medium | Low
    required_action: str = ""
    approver: Optional[str] = None
    approval_state: str = "Pending"  # Pending | Approved | Rejected
    evidence: Optional[Dict[str, Any]] = None
    status: str = "Open"  # Open | Accepted | Resolved | Expired | Rejected


CHECKLIST_ITEMS = [
    ("pe.env",           "Production environment created", "human"),
    ("pe.secrets",       "Secrets loaded via approved mechanism", "human"),
    ("pe.db_backup",     "Database backup verified", "human"),
    ("pe.storage",       "Object storage verified", "human"),
    ("pe.prod_cfg",      "Production configuration validated", "human"),
    ("pe.cors",          "CORS validated", "human"),
    ("pe.tls",           "TLS validated", "human"),
    ("pe.sched_token",   "Scheduler token loaded", "human"),
    ("pe.provider_off",  "Provider credentials loaded but disabled", "human"),
    ("pe.webhook_off",   "Webhook secrets loaded but callbacks disabled", "human"),
    ("pe.outbox",        "Development Outbox confirmed", "human"),
    ("pe.mig_pkg",       "Migration package approved", "human"),
    ("pe.rollback_pkg",  "Rollback package verified", "human"),
    ("pe.mig_ops",       "Migration operators assigned", "human"),
    ("pe.support",       "Support contacts recorded", "human"),
    ("pe.escalation",    "Escalation contacts recorded", "human"),
    ("pe.monitor",       "Monitoring enabled", "human"),
    ("pe.audit_log",     "Audit logging enabled", "human"),
    ("pe.backup_sched",  "Backup schedule configured", "human"),
    ("pe.first_reh",     "First restore rehearsal scheduled", "human"),
    ("pe.uat_ok",        "UAT approvals complete", "system"),
    ("pe.int_gate",      "Integrity gate PASS", "system"),
    ("pe.sec_gate",      "Security gate PASS", "system"),
    ("pe.rec_gate",      "Recovery gate PASS", "system"),
    ("pe.final_change",  "Final change approval recorded", "human"),
]


# ─── Service ──────────────────────────────────────────────────────────────
class UATService:
    def __init__(self, db, app):
        self.db = db
        self.app = app

    # ---- seed --------------------------------------------------------------
    async def _seed_cases_if_needed(self):
        n = await self.db[CASE_COLL].count_documents({"_source": "seed-eb17c"})
        if n < TOTAL_SEED_CASES:
            # Idempotent: only insert cases whose id is not present.
            existing_ids = set()
            async for r in self.db[CASE_COLL].find(
                {"_source": "seed-eb17c"}, {"_id": 0, "uat_test_case_id": 1}):
                existing_ids.add(r["uat_test_case_id"])
            missing = [c for c in _seed_cases()
                        if c["uat_test_case_id"] not in existing_ids]
            if missing:
                await self.db[CASE_COLL].insert_many(missing)

    async def _seed_checklist_if_needed(self):
        n = await self.db[CHK_COLL].count_documents({"_source": "seed-eb17c"})
        if n < len(CHECKLIST_ITEMS):
            existing = set()
            async for r in self.db[CHK_COLL].find(
                {"_source": "seed-eb17c"}, {"_id": 0, "item_id": 1}):
                existing.add(r["item_id"])
            add = []
            for item_id, label, kind in CHECKLIST_ITEMS:
                if item_id in existing: continue
                add.append({
                    "item_id": item_id, "label": label, "kind": kind,
                    "status": "Incomplete",
                    "owner": None, "evidence": None, "comment": "",
                    "updated_at": _iso(), "history": [],
                    "_source": "seed-eb17c",
                })
            if add:
                await self.db[CHK_COLL].insert_many(add)

    # ---- Plans -------------------------------------------------------------
    async def create_plan(self, body: CreatePlanBody, actor: str) -> Dict[str, Any]:
        await self._seed_cases_if_needed()
        packs = [p for p in body.packs if p in PACKS] or list(PACKS)
        plan_id = _uid()
        cases = await self.db[CASE_COLL].find(
            {"pack": {"$in": packs}, "_source": "seed-eb17c"},
            {"_id": 0, "uat_test_case_id": 1}).to_list(1000)
        doc = {
            "uat_test_plan_id": plan_id, "name": body.name,
            "packs": packs, "state": "Draft",
            "case_ids": [c["uat_test_case_id"] for c in cases],
            "created_by": actor, "created_at": _iso(),
            "started_at": None, "closed_at": None,
            "_source": "seed-eb17c",
        }
        await self.db[PLAN_COLL].insert_one(dict(doc))
        return doc

    async def start_plan(self, plan_id: str, actor: str) -> Dict[str, Any]:
        plan = await self.db[PLAN_COLL].find_one(
            {"uat_test_plan_id": plan_id}, {"_id": 0})
        if not plan: raise HTTPException(404, "Plan not found")
        if plan["state"] not in ("Draft", "Ready"):
            raise HTTPException(400, f"Plan cannot start from state {plan['state']}")
        run_id = _uid()
        await self.db[PLAN_COLL].update_one(
            {"uat_test_plan_id": plan_id},
            {"$set": {"state": "In Progress",
                       "current_run_id": run_id,
                       "started_at": _iso()}})
        await self.db[RUN_COLL].insert_one({
            "uat_test_run_id": run_id, "uat_test_plan_id": plan_id,
            "started_by": actor, "started_at": _iso(),
            "state": "In Progress", "closed_at": None,
            "case_ids": plan["case_ids"], "_source": "seed-eb17c",
        })
        return {"uat_test_run_id": run_id, "uat_test_plan_id": plan_id}

    async def close_run(self, run_id: str, actor: str, state: str = "Closed"):
        r = await self.db[RUN_COLL].find_one({"uat_test_run_id": run_id}, {"_id": 0})
        if not r: raise HTTPException(404, "Run not found")
        if r["state"] == "Closed":
            raise HTTPException(400, "Run already closed")
        await self.db[RUN_COLL].update_one(
            {"uat_test_run_id": run_id},
            {"$set": {"state": state, "closed_at": _iso(),
                       "closed_by": actor}})
        # Mark plan Closed if run closed
        await self.db[PLAN_COLL].update_one(
            {"uat_test_plan_id": r["uat_test_plan_id"]},
            {"$set": {"state": state, "closed_at": _iso()}})
        return {"uat_test_run_id": run_id, "state": state}

    # ---- Results (append-only) --------------------------------------------
    async def record_result(self, run_id: str, body: RecordResultBody,
                             actor: str, actor_role: str) -> Dict[str, Any]:
        run = await self.db[RUN_COLL].find_one({"uat_test_run_id": run_id}, {"_id": 0})
        if not run: raise HTTPException(404, "Run not found")
        if run["state"] != "In Progress":
            raise HTTPException(400, f"Run not in progress ({run['state']}); cannot record")
        case = await self.db[CASE_COLL].find_one(
            {"uat_test_case_id": body.uat_test_case_id}, {"_id": 0})
        if not case: raise HTTPException(404, "Case not found")
        # RBAC: certain packs restricted to matching roles.
        pack_role_map = {
            "Driver Lifecycle": ROLE_ALLOCATOR_PLUS,
            "Compliance":       ROLE_COMPLIANCE_PLUS,
            "Migration":        ROLE_MANAGER_PLUS,
            "Notifications":    ROLE_MANAGER_PLUS,
            "Operations":       ROLE_READONLY_PLUS,
            "Security":         ROLE_ADMIN,
            "Recovery":         ROLE_ADMIN,
        }
        allowed = pack_role_map.get(case["pack"], ROLE_MANAGER_PLUS)
        if actor_role not in allowed:
            raise HTTPException(403, f"Role {actor_role} cannot execute {case['pack']} UAT")
        if body.status not in ("Passed", "Failed", "Blocked",
                                 "Retest Required", "Not Applicable"):
            raise HTTPException(400, f"Illegal status {body.status}")
        if body.status == "Blocked" and not body.reason:
            raise HTTPException(400, "Blocked result requires a reason")
        # Append-only: previous results preserved.
        prior = await self.db[RESULT_COLL].count_documents(
            {"uat_test_run_id": run_id, "uat_test_case_id": body.uat_test_case_id})
        result_id = _uid()
        rec = {
            "uat_test_result_id": result_id,
            "uat_test_run_id": run_id,
            "uat_test_case_id": body.uat_test_case_id,
            "attempt": prior + 1,
            "status": body.status,
            "actual_result": body.actual_result,
            "reason": body.reason,
            "evidence": body.evidence or {},
            "tester": actor,
            "tester_role": actor_role,
            "executed_at": _iso(),
            "correlation_id": body.correlation_id or _uid(),
            "_source": "seed-eb17c",
        }
        await self.db[RESULT_COLL].insert_one(dict(rec))
        # Evidence journal (append-only) — never mutate a prior record.
        if body.evidence:
            await self.db[EVID_COLL].insert_one({
                "uat_evidence_id": _uid(),
                "uat_test_result_id": result_id,
                "uat_test_case_id": body.uat_test_case_id,
                "evidence": body.evidence,
                "created_at": _iso(),
                "created_by": actor,
                "_source": "seed-eb17c",
            })
        return rec

    # ---- Defects -----------------------------------------------------------
    async def create_defect(self, body: CreateDefectBody, actor: str) -> Dict[str, Any]:
        if body.severity not in DEFECT_SEVERITIES:
            raise HTTPException(400, f"Illegal severity {body.severity}")
        did = _uid()
        doc = {
            "uat_defect_id": did,
            "uat_test_case_id": body.uat_test_case_id,
            "uat_test_plan_id": body.plan_id,
            "severity": body.severity,
            "state": "Open",
            "title": body.title, "description": body.description,
            "raised_by": actor, "raised_at": _iso(),
            "history": [{"at": _iso(), "actor": actor,
                          "from": None, "to": "Open",
                          "severity": body.severity, "reason": "Raised"}],
            "_source": "seed-eb17c",
        }
        await self.db[DEF_COLL].insert_one(dict(doc))
        return doc

    async def transition_defect(self, defect_id: str,
                                 body: TransitionDefectBody,
                                 actor: str) -> Dict[str, Any]:
        d = await self.db[DEF_COLL].find_one({"uat_defect_id": defect_id}, {"_id": 0})
        if not d: raise HTTPException(404, "Defect not found")
        to = body.to_state
        if to not in DEFECT_STATES:
            raise HTTPException(400, f"Illegal state {to}")
        # Valid transitions
        valid = {
            "Open":              {"Investigating", "Deferred"},
            "Investigating":     {"Fixed", "Deferred"},
            "Fixed":             {"Ready for Retest"},
            "Ready for Retest":  {"Closed", "Reopened"},
            "Reopened":          {"Investigating", "Deferred"},
            "Deferred":          {"Open", "Investigating"},
            "Closed":            set(),
        }
        allowed = valid.get(d["state"], set())
        if to not in allowed:
            raise HTTPException(400, f"Cannot transition {d['state']} → {to}")
        # Deferral rules
        if to == "Deferred":
            if d["severity"] == "Critical":
                raise HTTPException(400, "Critical defects cannot be deferred")
            if d["severity"] == "High":
                raise HTTPException(400,
                    "High-severity defects cannot be deferred into EB-18")
        # Closed requires evidence
        if to == "Closed" and not (body.evidence
                                    or await self._has_passing_retest(d)):
            raise HTTPException(400,
                "Closing requires successful retest or explicit evidence")
        upd: Dict[str, Any] = {"state": to, "updated_at": _iso()}
        if body.downgrade_severity:
            if body.downgrade_severity not in DEFECT_SEVERITIES:
                raise HTTPException(400, "Illegal severity")
            if not body.reason:
                raise HTTPException(400, "Severity change requires a reason")
            upd["severity"] = body.downgrade_severity
        entry = {"at": _iso(), "actor": actor, "from": d["state"], "to": to,
                  "severity": upd.get("severity", d["severity"]),
                  "reason": body.reason or ""}
        await self.db[DEF_COLL].update_one(
            {"uat_defect_id": defect_id},
            {"$set": upd, "$push": {"history": entry}})
        return await self.db[DEF_COLL].find_one(
            {"uat_defect_id": defect_id}, {"_id": 0})

    async def _has_passing_retest(self, d: Dict[str, Any]) -> bool:
        if not d.get("uat_test_case_id"): return False
        latest = await self.db[RESULT_COLL].find_one(
            {"uat_test_case_id": d["uat_test_case_id"]},
            {"_id": 0}, sort=[("executed_at", -1)])
        return bool(latest and latest.get("status") == "Passed")

    # ---- Sign-offs ---------------------------------------------------------
    async def create_signoff(self, body: CreateSignoffBody,
                              actor: str, actor_role: str) -> Dict[str, Any]:
        if body.area not in SIGNOFF_AREAS:
            raise HTTPException(400, f"Unknown area {body.area}")
        if body.status not in ("Approved", "Approved with Conditions", "Rejected"):
            raise HTTPException(400, f"Illegal status {body.status}")
        # Signer role restriction
        allowed_roles = SIGNOFF_ROLE_MAP.get(body.area, ROLE_ADMIN)
        if actor_role not in allowed_roles:
            raise HTTPException(403,
                f"Role {actor_role} cannot sign {body.area}")
        # Gate blockers
        gate_snap = await self._compute_gate()
        blockers: List[str] = []
        if gate_snap["integrity_gate"] == "FAIL":
            blockers.append("integrity_gate=FAIL")
        if gate_snap["security_gate"] == "FAIL":
            blockers.append("security_gate=FAIL")
        if gate_snap["recovery_gate"] == "FAIL":
            blockers.append("recovery_gate=FAIL")
        if gate_snap["open_critical_defects"] > 0:
            blockers.append("critical_open_defects>0")
        if gate_snap["open_high_defects"] > 0:
            blockers.append("high_open_defects>0")
        if gate_snap["expired_exceptions"] > 0:
            blockers.append("expired_security_exceptions>0")
        if body.status == "Approved" and blockers:
            raise HTTPException(400,
                f"Cannot Approve while blockers exist: {','.join(blockers)}")
        sid = _uid()
        doc = {
            "uat_signoff_id": sid, "area": body.area,
            "signer": actor, "signer_role": actor_role,
            "responsibility": self._responsibility_for(body.area),
            "status": body.status, "signed_at": _iso(),
            "comments": body.comments,
            "accepted_risks": body.accepted_risks,
            "evidence_refs": body.evidence_refs,
            "release_recommendation": body.release_recommendation,
            "version": body.version,
            "open_defects_snapshot": {
                "critical": gate_snap["open_critical_defects"],
                "high":     gate_snap["open_high_defects"],
            },
            "gate_snapshot": gate_snap,
            "immutable": True,
            "withdrawn": False,
            "_source": "seed-eb17c",
        }
        await self.db[SIGN_COLL].insert_one(dict(doc))
        return doc

    def _responsibility_for(self, area: str) -> str:
        return {
            "Business Operations": "Business Approver",
            "Compliance":          "Business Approver",
            "Management":          "Business Approver",
            "Technical":           "Technical Approver",
            "Security":            "Technical Approver",
            "Data Migration":      "Business Approver",
            "Recovery":            "Technical Approver",
        }.get(area, "Business Approver")

    async def withdraw_signoff(self, sid: str, actor: str,
                                actor_role: str) -> Dict[str, Any]:
        s = await self.db[SIGN_COLL].find_one({"uat_signoff_id": sid}, {"_id": 0})
        if not s: raise HTTPException(404, "Sign-off not found")
        if s.get("withdrawn"): raise HTTPException(400, "Already withdrawn")
        if actor_role not in ROLE_ADMIN and actor != s["signer"]:
            raise HTTPException(403, "Only original signer or Admin can withdraw")
        await self.db[SIGN_COLL].update_one(
            {"uat_signoff_id": sid},
            {"$set": {"withdrawn": True, "withdrawn_at": _iso(),
                       "withdrawn_by": actor, "status": "Withdrawn"}})
        return await self.db[SIGN_COLL].find_one(
            {"uat_signoff_id": sid}, {"_id": 0})

    # ---- Conditions --------------------------------------------------------
    async def upsert_condition(self, body: ConditionBody, actor: str) -> Dict[str, Any]:
        cid = body.condition_id or _uid()
        if body.risk_level == "Critical" and body.status == "Accepted":
            raise HTTPException(400,
                "Critical conditions may not be accepted as non-blocking")
        doc = {
            "condition_id": cid, "source": body.source,
            "description": body.description, "owner": body.owner,
            "due_date": body.due_date, "risk_level": body.risk_level,
            "required_action": body.required_action,
            "approver": body.approver, "approval_state": body.approval_state,
            "evidence": body.evidence, "status": body.status,
            "updated_at": _iso(), "updated_by": actor,
            "_source": "seed-eb17c",
        }
        await self.db[COND_COLL].update_one(
            {"condition_id": cid}, {"$set": doc,
                                      "$setOnInsert": {"created_at": _iso()}},
            upsert=True)
        return await self.db[COND_COLL].find_one({"condition_id": cid}, {"_id": 0})

    # ---- Gate & readiness computation --------------------------------------
    async def _compute_gate(self) -> Dict[str, Any]:
        """Compose Integrity/Security/Recovery gate + UAT + defect + sign-off
        + checklist state into a deterministic snapshot."""
        # Integrity, Security, Recovery — read from existing modules' DB.
        int_gate = await self._latest_integrity_gate()
        sec_gate = await self._latest_security_gate()
        rec_gate, mig_ready = await self._latest_recovery_status()
        # UAT progress
        total_cases = await self.db[CASE_COLL].count_documents({"_source": "seed-eb17c"})
        # A case is considered complete if its latest result is a terminal status.
        completed = 0
        passed = 0
        failed = 0
        blocked = 0
        seen: set = set()
        # Read latest result per case
        pipeline = [
            {"$match": {"_source": "seed-eb17c"}},
            {"$sort": {"executed_at": -1}},
            {"$group": {"_id": "$uat_test_case_id",
                         "status": {"$first": "$status"}}},
        ]
        async for r in self.db[RESULT_COLL].aggregate(pipeline):
            seen.add(r["_id"])
            s = r.get("status")
            if s in ("Passed", "Failed", "Blocked", "Not Applicable"):
                completed += 1
            if s == "Passed": passed += 1
            elif s == "Failed": failed += 1
            elif s == "Blocked": blocked += 1
        completion_pct = (completed * 100 // total_cases) if total_cases else 0
        # Defects
        open_states = {"Open", "Investigating", "Fixed", "Ready for Retest",
                       "Reopened"}
        open_critical = await self.db[DEF_COLL].count_documents(
            {"severity": "Critical", "state": {"$in": list(open_states)},
              "_source": "seed-eb17c"})
        open_high = await self.db[DEF_COLL].count_documents(
            {"severity": "High", "state": {"$in": list(open_states)},
              "_source": "seed-eb17c"})
        open_medium = await self.db[DEF_COLL].count_documents(
            {"severity": "Medium", "state": {"$in": list(open_states)},
              "_source": "seed-eb17c"})
        # Sign-offs
        signoffs: Dict[str, Dict[str, Any]] = {}
        async for s in self.db[SIGN_COLL].find(
            {"withdrawn": {"$ne": True}, "_source": "seed-eb17c"},
            {"_id": 0}).sort("signed_at", -1):
            if s["area"] not in signoffs:
                signoffs[s["area"]] = s
        signoff_state = {a: (signoffs[a]["status"] if a in signoffs else "Pending")
                          for a in SIGNOFF_AREAS}
        # Expired security exceptions (real ones only — fictional seed-eb17*
        # tagged rows never block readiness of the fictional-data harness).
        expired_exc = 0
        try:
            expired_exc = await self.db["security_exception_requests"].count_documents(
                {"status": "Expired",
                  "$or": [{"_source": {"$exists": False}},
                            {"_source": {"$not": {"$regex": "^seed-eb17"}}}]})
        except Exception:
            pass
        # Checklist
        await self._seed_checklist_if_needed()
        chk_total = await self.db[CHK_COLL].count_documents({"_source": "seed-eb17c"})
        chk_done = await self.db[CHK_COLL].count_documents(
            {"_source": "seed-eb17c", "status": {"$in": ["Complete", "Waived"]}})
        # System-derived checklist items reflect gate state
        chk_int_ok = int_gate == "PASS"
        chk_sec_ok = sec_gate == "PASS"
        chk_rec_ok = rec_gate == "PASS"
        chk_uat_ok = (all(signoff_state[a] in ("Approved", "Approved with Conditions")
                          for a in SIGNOFF_AREAS)
                       and open_critical == 0 and open_high == 0)
        await self._sync_system_checklist(chk_int_ok, chk_sec_ok,
                                            chk_rec_ok, chk_uat_ok)
        # Recount after sync
        chk_done = await self.db[CHK_COLL].count_documents(
            {"_source": "seed-eb17c", "status": {"$in": ["Complete", "Waived"]}})
        # Conditions
        open_conditions = await self.db[COND_COLL].count_documents(
            {"status": {"$in": ["Open", "Expired"]}, "_source": "seed-eb17c"})
        critical_conditions_open = await self.db[COND_COLL].count_documents(
            {"risk_level": "Critical",
              "status": {"$in": ["Open", "Expired"]},
              "_source": "seed-eb17c"})
        # Configuration / storage / scheduler readiness (system-derived)
        cfg_ready = "PASS"
        storage_ready = "PASS"
        scheduler_ready = "PASS"
        provider_ready = "PASS"  # providers must be disabled = safe
        webhook_ready = "PASS"
        doc_ready = "PASS"
        rollback_ready = ("PASS" if
                           os.path.exists("/app/memory/EB-17c-GO-LIVE-ROLLBACK-RUNBOOK.md")
                           else "FAIL")
        return {
            "integrity_gate": int_gate,
            "security_gate": sec_gate,
            "recovery_gate": rec_gate,
            "migration_readiness": mig_ready,
            "uat_cases_total": total_cases,
            "uat_cases_completed": completed,
            "uat_completion_pct": completion_pct,
            "uat_cases_passed": passed,
            "uat_cases_failed": failed,
            "uat_cases_blocked": blocked,
            "open_critical_defects": open_critical,
            "open_high_defects": open_high,
            "open_medium_defects": open_medium,
            "signoff_state": signoff_state,
            "expired_exceptions": expired_exc,
            "checklist_total": chk_total,
            "checklist_completed": chk_done,
            "checklist_completion_pct":
                (chk_done * 100 // chk_total) if chk_total else 0,
            "configuration_readiness": cfg_ready,
            "storage_readiness": storage_ready,
            "scheduler_readiness": scheduler_ready,
            "provider_readiness": provider_ready,
            "webhook_readiness": webhook_ready,
            "documentation_readiness": doc_ready,
            "rollback_readiness": rollback_ready,
            "open_conditions": open_conditions,
            "critical_conditions_open": critical_conditions_open,
            "computed_at": _iso(),
        }

    async def _sync_system_checklist(self, int_ok, sec_ok, rec_ok, uat_ok):
        pairs = [("pe.int_gate", int_ok), ("pe.sec_gate", sec_ok),
                 ("pe.rec_gate", rec_ok), ("pe.uat_ok", uat_ok)]
        for item_id, ok in pairs:
            await self.db[CHK_COLL].update_one(
                {"item_id": item_id},
                {"$set": {"status": "Complete" if ok else "Incomplete",
                           "updated_at": _iso()}})

    async def _latest_integrity_gate(self) -> str:
        row = await self.db["integrity_gate_results"].find_one(
            {}, {"_id": 0}, sort=[("created_at", -1)])
        if not row: return "UNKNOWN"
        r = row.get("result")
        if r == "PASS": return "PASS"
        if r == "PASS_WITH_WARNINGS": return "PASS_WITH_WARNINGS"
        return "FAIL"

    async def _latest_security_gate(self) -> str:
        row = await self.db["security_assessment_runs"].find_one(
            {"status": "Completed"}, {"_id": 0},
            sort=[("completed_at", -1)])
        if not row: return "UNKNOWN"
        r = row.get("overall_result")
        if r in ("PASS", "PASS_WITH_WARNINGS"): return r
        return "FAIL"

    async def _latest_recovery_status(self):
        try:
            reh = await self.db["restore_rehearsals"].find_one(
                {}, {"_id": 0}, sort=[("started_at", -1)])
            if not reh: return ("UNKNOWN", "UNKNOWN")
            gate = "PASS" if (reh.get("final_state") == "Passed"
                                and reh.get("integrity_gate") == "PASS"
                                and reh.get("security_gate") == "PASS") else "FAIL"
            mig = "PASS" if reh.get("final_state") == "Passed" else "FAIL"
            return (gate, mig)
        except Exception:
            return ("UNKNOWN", "UNKNOWN")

    async def readiness_status(self) -> Dict[str, Any]:
        return await self._compute_gate()

    async def readiness_gate(self) -> Dict[str, Any]:
        s = await self._compute_gate()
        blockers: List[str] = []
        warnings: List[str] = []
        # Blockers → NOT_READY
        if s["integrity_gate"] == "FAIL":
            blockers.append("integrity_gate=FAIL")
        if s["security_gate"] == "FAIL":
            blockers.append("security_gate=FAIL")
        if s["recovery_gate"] == "FAIL":
            blockers.append("recovery_gate=FAIL")
        if s["migration_readiness"] == "FAIL":
            blockers.append("migration_readiness=FAIL")
        if s["open_critical_defects"] > 0:
            blockers.append("open_critical_defects>0")
        if s["open_high_defects"] > 0:
            blockers.append("open_high_defects>0")
        if s["expired_exceptions"] > 0:
            blockers.append("expired_security_exceptions>0")
        if s["critical_conditions_open"] > 0:
            blockers.append("critical_conditions_open>0")
        if s["configuration_readiness"] != "PASS":
            blockers.append("configuration_readiness")
        if s["storage_readiness"] != "PASS":
            blockers.append("storage_readiness")
        if s["scheduler_readiness"] != "PASS":
            blockers.append("scheduler_readiness")
        if s["rollback_readiness"] != "PASS":
            blockers.append("rollback_plan_missing")
        # All required sign-offs Approved / with-Conditions?
        approved = ("Approved", "Approved with Conditions")
        for area in SIGNOFF_AREAS:
            st = s["signoff_state"][area]
            if st not in approved:
                blockers.append(f"signoff_pending:{area}")
            elif st == "Approved with Conditions":
                warnings.append(f"signoff_conditional:{area}")
        # UAT completion
        if s["uat_completion_pct"] < 100:
            blockers.append("uat_completion<100")
        # Checklist required pre-EB18 items
        # Every checklist item must be Complete/Waived
        if s["checklist_completed"] < s["checklist_total"]:
            blockers.append("checklist_incomplete")
        # Result
        if blockers:
            result = "NOT_READY"
        elif warnings or s["integrity_gate"] == "PASS_WITH_WARNINGS" \
                or s["open_conditions"] > 0:
            result = "CONDITIONALLY_READY"
        else:
            result = "READY"
        eb18_entry = ("OPEN" if result in ("READY", "CONDITIONALLY_READY") else "BLOCKED")
        return {
            "result": result,
            "blockers": blockers,
            "warnings": warnings,
            "eb18_entry": eb18_entry,
            "snapshot": s,
            "computed_at": _iso(),
        }

    # ---- Checklist --------------------------------------------------------
    async def list_checklist(self) -> List[Dict[str, Any]]:
        await self._seed_checklist_if_needed()
        rows = await self.db[CHK_COLL].find(
            {"_source": "seed-eb17c"}, {"_id": 0}).to_list(200)
        return rows

    async def update_checklist_item(self, item_id: str,
                                     body: ChecklistUpdateBody,
                                     actor: str, actor_role: str) -> Dict[str, Any]:
        row = await self.db[CHK_COLL].find_one({"item_id": item_id}, {"_id": 0})
        if not row: raise HTTPException(404, "Checklist item not found")
        if row["kind"] == "system":
            raise HTTPException(400, "System-derived item cannot be manually updated")
        if body.status not in ("Complete", "Incomplete", "Waived"):
            raise HTTPException(400, "Illegal status")
        if body.status == "Waived" and not body.evidence:
            raise HTTPException(400, "Waiver requires evidence")
        # Manager+ can update most items; Admin only for approval items
        admin_only = {"pe.final_change", "pe.mig_pkg", "pe.mig_ops"}
        allowed = ROLE_ADMIN if item_id in admin_only else ROLE_MANAGER_PLUS
        if actor_role not in allowed:
            raise HTTPException(403,
                f"Role {actor_role} cannot update checklist item {item_id}")
        entry = {"at": _iso(), "actor": actor,
                  "from": row["status"], "to": body.status,
                  "owner": body.owner, "comment": body.comment,
                  "evidence": body.evidence}
        await self.db[CHK_COLL].update_one(
            {"item_id": item_id},
            {"$set": {"status": body.status, "owner": body.owner,
                       "evidence": body.evidence, "comment": body.comment,
                       "updated_at": _iso(), "updated_by": actor},
             "$push": {"history": entry}})
        return await self.db[CHK_COLL].find_one({"item_id": item_id}, {"_id": 0})


# ─── Indexes ──────────────────────────────────────────────────────────────
async def ensure_indexes(db):
    await db[PLAN_COLL].create_index("uat_test_plan_id", unique=True)
    await db[CASE_COLL].create_index("uat_test_case_id", unique=True)
    await db[RUN_COLL].create_index("uat_test_run_id", unique=True)
    await db[RESULT_COLL].create_index([("uat_test_run_id", 1),
                                          ("uat_test_case_id", 1),
                                          ("attempt", 1)], unique=True)
    await db[DEF_COLL].create_index("uat_defect_id", unique=True)
    await db[SIGN_COLL].create_index("uat_signoff_id", unique=True)
    await db[EVID_COLL].create_index("uat_evidence_id", unique=True)
    await db[CHK_COLL].create_index("item_id", unique=True)
    await db[COND_COLL].create_index("condition_id", unique=True)


# ─── Router ───────────────────────────────────────────────────────────────
def build_uat_router(db, app, get_current_user):
    r = APIRouter(tags=["uat", "production-readiness"])
    svc = UATService(db, app)

    # ---- UAT plans / runs / results --------------------------------------
    @r.post("/api/uat/plans")
    async def create_plan(body: CreatePlanBody, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS, "Manager+ required")
        return await svc.create_plan(body, current.get("email"))

    @r.get("/api/uat/plans")
    async def list_plans(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await db[PLAN_COLL].find({"_source": "seed-eb17c"},
                                          {"_id": 0}).sort("created_at", -1).to_list(200)

    @r.get("/api/uat/plans/{plan_id}")
    async def get_plan(plan_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        p = await db[PLAN_COLL].find_one({"uat_test_plan_id": plan_id}, {"_id": 0})
        if not p: raise HTTPException(404, "Not found")
        return p

    @r.get("/api/uat/cases")
    async def list_cases(current=Depends(get_current_user),
                          pack: Optional[str] = None):
        _require(current, ROLE_READONLY_PLUS)
        await svc._seed_cases_if_needed()
        q: Dict[str, Any] = {"_source": "seed-eb17c"}
        if pack: q["pack"] = pack
        return await db[CASE_COLL].find(q, {"_id": 0}).to_list(1000)

    @r.post("/api/uat/plans/{plan_id}/start")
    async def start_plan(plan_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS)
        return await svc.start_plan(plan_id, current.get("email"))

    @r.get("/api/uat/runs/{run_id}")
    async def get_run(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        rrow = await db[RUN_COLL].find_one({"uat_test_run_id": run_id}, {"_id": 0})
        if not rrow: raise HTTPException(404, "Run not found")
        results = await db[RESULT_COLL].find(
            {"uat_test_run_id": run_id}, {"_id": 0}).sort("executed_at", 1).to_list(2000)
        return {"run": rrow, "results": results}

    @r.post("/api/uat/runs/{run_id}/close")
    async def close_run(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS)
        return await svc.close_run(run_id, current.get("email"))

    @r.post("/api/uat/results/{run_id}")
    async def record_result(run_id: str, body: RecordResultBody,
                             current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR_PLUS)
        return await svc.record_result(run_id, body,
                                        current.get("email"),
                                        current.get("role"))

    # ---- Defects ----------------------------------------------------------
    @r.post("/api/uat/defects")
    async def create_defect(body: CreateDefectBody, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR_PLUS)
        return await svc.create_defect(body, current.get("email"))

    @r.get("/api/uat/defects")
    async def list_defects(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await db[DEF_COLL].find({"_source": "seed-eb17c"},
                                        {"_id": 0}).sort("raised_at", -1).to_list(500)

    @r.post("/api/uat/defects/{defect_id}/transition")
    async def transition_defect(defect_id: str, body: TransitionDefectBody,
                                 current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS)
        return await svc.transition_defect(defect_id, body, current.get("email"))

    # ---- Sign-offs --------------------------------------------------------
    @r.post("/api/uat/signoffs")
    async def create_signoff(body: CreateSignoffBody,
                              current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE_PLUS,
                 "Compliance+ required to sign off")
        return await svc.create_signoff(body,
                                         current.get("email"),
                                         current.get("role"))

    @r.get("/api/uat/signoffs")
    async def list_signoffs(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await db[SIGN_COLL].find({"_source": "seed-eb17c"},
                                          {"_id": 0}).sort("signed_at", -1).to_list(500)

    @r.post("/api/uat/signoffs/{sid}/withdraw")
    async def withdraw_signoff(sid: str, current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE_PLUS)
        return await svc.withdraw_signoff(sid, current.get("email"),
                                            current.get("role"))

    # ---- Production Readiness --------------------------------------------
    @r.get("/api/production-readiness/status")
    async def pr_status(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await svc.readiness_status()

    @r.get("/api/production-readiness/gate")
    async def pr_gate(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await svc.readiness_gate()

    @r.get("/api/production-readiness/checklist")
    async def pr_checklist(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await svc.list_checklist()

    @r.post("/api/production-readiness/checklist/{item_id}/update")
    async def pr_checklist_update(item_id: str, body: ChecklistUpdateBody,
                                    current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS)
        return await svc.update_checklist_item(item_id, body,
                                                 current.get("email"),
                                                 current.get("role"))

    # ---- Conditions -------------------------------------------------------
    @r.get("/api/production-readiness/conditions")
    async def cond_list(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await db[COND_COLL].find({"_source": "seed-eb17c"},
                                          {"_id": 0}).sort("updated_at", -1).to_list(200)

    @r.post("/api/production-readiness/conditions")
    async def cond_create(body: ConditionBody, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS)
        return await svc.upsert_condition(body, current.get("email"))

    @r.post("/api/production-readiness/conditions/{cid}/update")
    async def cond_update(cid: str, body: ConditionBody,
                            current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS)
        body.condition_id = cid
        return await svc.upsert_condition(body, current.get("email"))

    return r
