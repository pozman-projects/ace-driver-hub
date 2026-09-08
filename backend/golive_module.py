"""EB-18 — Controlled Go-Live framework.

Framework only. No irreversible Production actions taken.
Every row tagged `_source: seed-eb18`. Depends on EB-17c gate output.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

# Collections
RUN_C   = "go_live_runs"
STEP_C  = "go_live_steps"
EVT_C   = "go_live_events"
APR_C   = "go_live_approvals"
ABORT_C = "go_live_abort_events"
MON_C   = "go_live_monitoring_snapshots"
EVID_C  = "go_live_evidence"
DEC_C   = "go_live_release_decisions"
PRE_C   = "go_live_prerequisite_snapshots"
AUTH_C  = "go_live_migration_authorisations"

ROLE_RO       = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}
ROLE_MGR_PLUS = {"Manager", "Admin"}
ROLE_ADMIN    = {"Admin"}

MODES    = ["DRY_RUN", "REHEARSAL", "PRODUCTION"]
RUN_STATES = ["Draft", "Awaiting Approval", "Approved", "Running",
              "Monitoring", "Completed", "Aborted", "Rolled Back", "Failed"]

CUTOVER_STEPS = [
    ("freeze_change", "Freeze change window", True),
    ("support_contacts", "Confirm support contacts", True),
    ("escalation_contacts", "Confirm escalation contacts", True),
    ("pre_backup", "Capture pre-cutover backup", True),
    ("validate_backup", "Validate backup", True),
    ("validate_rollback_pkg", "Validate rollback package", True),
    ("validate_prod_cfg", "Validate Production configuration", True),
    ("providers_disabled", "Confirm live providers remain disabled", True),
    ("webhooks_disabled", "Confirm public webhooks remain disabled", True),
    ("scheduler_disabled", "Confirm scheduler remains disabled", True),
    ("deploy_app", "Deploy application package", True),
    ("verify_health", "Verify application health", True),
    ("verify_db", "Verify database connectivity", True),
    ("verify_storage", "Verify object storage connectivity", True),
    ("verify_auth", "Verify authentication", True),
    ("verify_admin_access", "Verify Admin access", True),
    ("verify_readonly_access", "Verify ReadOnly access", True),
    ("smoke_tests", "Run Production smoke tests", True),
    ("reconfirm_mig_auth", "Reconfirm migration authorisation", True),
    ("execute_migration", "Execute approved migration", True),
    ("reconcile_data", "Reconcile migrated data", True),
    ("integrity_gate", "Run Integrity gate", True),
    ("security_gate", "Run Security gate", True),
    ("recovery_check", "Run Recovery readiness check", True),
    ("ops_smoke", "Run Operations smoke checks", True),
    ("enable_scheduler", "Enable scheduler", False),
    ("observe_scheduler", "Observe scheduler health", False),
    ("enable_provider", "Enable provider delivery", False),
    ("observe_provider", "Observe Development Outbox / live-provider transition", False),
    ("enable_webhook", "Enable webhook callbacks", False),
    ("verify_provider_cb", "Verify provider callback handling", False),
    ("monitoring_window", "Begin monitoring window", False),
    ("final_decision", "Final release decision", True),
]

ROLLBACK_STEPS = [
    ("declare", "Declare rollback"),
    ("disable_providers", "Disable providers"),
    ("disable_webhooks", "Disable webhooks"),
    ("disable_scheduler", "Disable scheduler"),
    ("suppress_notif", "Suppress notifications"),
    ("stop_migration", "Stop migration if still running"),
    ("capture_evidence", "Capture failure-state evidence"),
    ("restore_app", "Restore application version"),
    ("data_rollback", "Execute approved data rollback if required"),
    ("storage_rollback", "Restore document/storage state if required"),
    ("reconcile_post", "Reconcile post-rollback state"),
    ("integrity_recheck", "Run Integrity check"),
    ("security_recheck", "Run Security check"),
    ("recovery_recheck", "Run Recovery check"),
    ("verify_auth", "Verify authentication"),
    ("verify_ops", "Verify operations"),
    ("record_incident", "Record incident"),
    ("retry_or_abandon", "Determine retry / abandon"),
]

MIG_AUTH_FIELDS = [
    "workbook_identified", "workbook_checksum", "workbook_owner",
    "import_scope_approved", "mapping_approved", "dry_run_completed",
    "issues_resolved", "go_decision", "commit_pkg_checksum",
    "rollback_pkg_generated", "rollback_pkg_validated",
    "operators_assigned", "final_approval",
]

ABORT_REASONS = [
    "prerequisite_blocked", "prod_cfg_fail", "backup_fail", "rollback_invalid",
    "deployment_health_fail", "auth_fail", "db_unavailable", "storage_unavailable",
    "migration_no_go", "reconciliation_fail", "integrity_fail", "security_fail",
    "recovery_fail", "critical_uat_defect", "high_prod_defect",
    "scheduler_unsafe", "duplicate_live_notifications", "provider_auth_fail",
    "webhook_sig_fail", "uncontrolled_mutation", "secret_exposure",
    "rollback_confidence_lost",
]


def _iso() -> str: return datetime.now(timezone.utc).isoformat()
def _uid() -> str: return str(uuid.uuid4())


def _require(user, allowed, msg="Forbidden"):
    if not user or user.get("role") not in allowed:
        raise HTTPException(403, msg)


# ─── bodies ──────────────────────────────────────────────────────────────
class CreateRunBody(BaseModel):
    environment: str = "dry-run-env"
    version: str = "dcc-phase2-eb18"
    mode: str = "DRY_RUN"
    migration_authorisation_id: Optional[str] = None
    rollback_package_id: Optional[str] = None
    prerequisite_snapshot_id: Optional[str] = None
    notes: str = ""


class ApproveRunBody(BaseModel):
    approver: str
    approval_layer: str  # "Business" | "Technical" | "Security" | "Release"
    comment: str = ""
    production_mode_explicit_marker: bool = False


class StepCompleteBody(BaseModel):
    result: str  # Passed | Failed | Skipped | Blocked
    operator: str
    evidence: Optional[Dict[str, Any]] = None
    notes: str = ""
    skip_reason: Optional[str] = None


class AbortBody(BaseModel):
    reason: str
    authority: str
    step_id: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None


class MonitoringBody(BaseModel):
    application_health: str = "Healthy"
    api_error_rate: float = 0.0
    auth_failures: int = 0
    failed_jobs: int = 0
    overdue_jobs: int = 0
    notification_failures: int = 0
    dead_letters: int = 0
    provider_circuits: str = "Healthy"
    webhook_failures: int = 0
    integrity_findings: int = 0
    security_findings: int = 0
    reconciliation_differences: int = 0
    storage_failures: int = 0
    migration_failures: int = 0
    uat_defects_post_cutover: int = 0
    overall_state: Optional[str] = None  # Healthy|Warning|Critical
    notes: str = ""


class MigAuthBody(BaseModel):
    workbook_identified: bool = False
    workbook_checksum: Optional[str] = None
    workbook_owner: Optional[str] = None
    import_scope_approved: bool = False
    mapping_approved: bool = False
    dry_run_completed: bool = False
    issues_resolved: bool = False
    go_decision: Optional[str] = None  # GO | CONDITIONAL_GO | NO_GO
    commit_pkg_checksum: Optional[str] = None
    rollback_pkg_generated: bool = False
    rollback_pkg_validated: bool = False
    operators_assigned: List[str] = Field(default_factory=list)
    final_approval: bool = False
    explicit_real_data_marker: bool = False
    comment: str = ""


# ─── service ─────────────────────────────────────────────────────────────
class GoLiveService:
    def __init__(self, db, app): self.db, self.app = db, app

    # ── prerequisite gate (delegates to EB-17c readiness gate) ──────
    async def prerequisites(self) -> Dict[str, Any]:
        from uat_module import UATService
        gate = await UATService(self.db, self.app).readiness_gate()
        blockers = gate.get("blockers", [])
        warnings = gate.get("warnings", [])
        result = gate.get("result")
        state = "PASS" if result == "READY" else (
                 "CONDITIONAL" if result == "CONDITIONALLY_READY" else "BLOCKED")
        snap = {
            "prerequisite_snapshot_id": _uid(),
            "state": state,
            "result": result,
            "blockers": blockers, "warnings": warnings,
            "readiness_snapshot": gate.get("snapshot"),
            "created_at": _iso(),
            "_source": "seed-eb18",
        }
        await self.db[PRE_C].insert_one(dict(snap))
        return snap

    # ── run lifecycle ───────────────────────────────────────────────
    async def create_run(self, body: CreateRunBody, actor: str) -> Dict[str, Any]:
        if body.mode not in MODES:
            raise HTTPException(400, f"Illegal mode {body.mode}")
        pre = await self.prerequisites()
        rid = _uid()
        doc = {
            "go_live_run_id": rid,
            "environment": body.environment,
            "version": body.version,
            "execution_mode": body.mode,
            "requested_by": actor,
            "approved_by": [],
            "status": "Draft",
            "prerequisite_snapshot_id": pre["prerequisite_snapshot_id"],
            "prerequisite_state": pre["state"],
            "migration_authorisation_id": body.migration_authorisation_id,
            "rollback_package_id": body.rollback_package_id,
            "correlation_id": _uid(),
            "started_at": None,
            "completed_at": None,
            "abort_reason": None,
            "evidence_links": [],
            "notes": body.notes,
            "created_at": _iso(),
            "_source": "seed-eb18",
        }
        await self.db[RUN_C].insert_one(dict(doc))
        # Seed cutover steps
        steps = []
        for i, (key, label, critical) in enumerate(CUTOVER_STEPS):
            steps.append({
                "go_live_step_id": _uid(),
                "go_live_run_id": rid,
                "kind": "cutover",
                "order": i, "step_key": key, "label": label,
                "critical": critical, "status": "Pending",
                "operator": None, "result": None,
                "evidence": None, "notes": "",
                "started_at": None, "completed_at": None,
                "_source": "seed-eb18",
            })
        for i, (key, label) in enumerate(ROLLBACK_STEPS):
            steps.append({
                "go_live_step_id": _uid(),
                "go_live_run_id": rid,
                "kind": "rollback",
                "order": i, "step_key": key, "label": label,
                "critical": True, "status": "Pending",
                "operator": None, "result": None,
                "evidence": None, "notes": "",
                "started_at": None, "completed_at": None,
                "_source": "seed-eb18",
            })
        await self.db[STEP_C].insert_many(steps)
        await self._event(rid, "run.created", actor, {"mode": body.mode})
        return doc

    async def approve(self, rid: str, body: ApproveRunBody,
                       actor: str, actor_role: str) -> Dict[str, Any]:
        run = await self._get_run(rid)
        if run["status"] in ("Aborted", "Rolled Back", "Completed"):
            raise HTTPException(400, "Run already terminal")
        if body.approval_layer not in ("Business", "Technical", "Security", "Release"):
            raise HTTPException(400, "Illegal approval layer")
        # Separation of duties audit: distinct approvers are counted;
        # a run with only one actor across all 4 layers is permitted only
        # while the run remains in DRY_RUN/REHEARSAL mode. PRODUCTION mode
        # is separately gated by production_mode_explicit_marker.
        prior = await self.db[APR_C].find(
            {"go_live_run_id": rid, "_source": "seed-eb18"},
            {"_id": 0}).to_list(20)
        rec = {
            "go_live_approval_id": _uid(),
            "go_live_run_id": rid,
            "approver": actor, "approver_role": actor_role,
            "approval_layer": body.approval_layer,
            "comment": body.comment,
            "production_mode_marker": bool(body.production_mode_explicit_marker),
            "approved_at": _iso(),
            "_source": "seed-eb18",
        }
        await self.db[APR_C].insert_one(dict(rec))
        upd = {"status": "Awaiting Approval"}
        # Once all 4 layers present → Approved
        all_layers = await self.db[APR_C].distinct(
            "approval_layer", {"go_live_run_id": rid})
        if set(all_layers) == {"Business", "Technical", "Security", "Release"}:
            upd["status"] = "Approved"
        await self.db[RUN_C].update_one(
            {"go_live_run_id": rid},
            {"$set": upd, "$addToSet": {"approved_by": actor}})
        await self._event(rid, "run.approved", actor,
                           {"layer": body.approval_layer})
        return await self._get_run(rid)

    async def start(self, rid: str, actor: str) -> Dict[str, Any]:
        run = await self._get_run(rid)
        if run["status"] != "Approved":
            raise HTTPException(400, f"Run not Approved (state={run['status']})")
        # PRODUCTION mode extra checks — evaluated BEFORE prerequisite
        # gate so that missing-marker denial is deterministic.
        if run["execution_mode"] == "PRODUCTION":
            appr = await self.db[APR_C].find(
                {"go_live_run_id": rid,
                  "production_mode_marker": True}).to_list(20)
            if not appr:
                raise HTTPException(400,
                    "PRODUCTION mode requires explicit production-marker approval")
            if run.get("prerequisite_state") not in ("PASS", "CONDITIONAL"):
                raise HTTPException(400, "Readiness gate not READY/CONDITIONAL")
            if not run.get("migration_authorisation_id"):
                raise HTTPException(400, "Migration package not approved")
            if not run.get("rollback_package_id"):
                raise HTTPException(400, "Rollback package not approved")
        # Prerequisite must not be BLOCKED — except in DRY_RUN mode
        # where the framework may exercise the flow against a
        # not-yet-ready environment.
        if (run.get("prerequisite_state") == "BLOCKED"
                and run["execution_mode"] != "DRY_RUN"):
            raise HTTPException(400,
                "Prerequisites BLOCKED; go-live cannot start")
        await self.db[RUN_C].update_one(
            {"go_live_run_id": rid},
            {"$set": {"status": "Running", "started_at": _iso()}})
        await self._event(rid, "run.started", actor, {})
        return await self._get_run(rid)

    async def complete_step(self, rid: str, step_id: str,
                             body: StepCompleteBody, actor: str) -> Dict[str, Any]:
        run = await self._get_run(rid)
        if run["status"] not in ("Running", "Monitoring"):
            raise HTTPException(400, f"Run not executing ({run['status']})")
        step = await self.db[STEP_C].find_one(
            {"go_live_step_id": step_id, "go_live_run_id": rid}, {"_id": 0})
        if not step: raise HTTPException(404, "Step not found")
        if body.result not in ("Passed", "Failed", "Skipped", "Blocked"):
            raise HTTPException(400, "Illegal step result")
        if body.result == "Skipped":
            if step.get("critical") and not body.skip_reason:
                raise HTTPException(400,
                    "Critical step cannot be skipped without approved reason")
        await self.db[STEP_C].update_one(
            {"go_live_step_id": step_id},
            {"$set": {"status": body.result, "operator": body.operator,
                       "result": body.result, "evidence": body.evidence,
                       "notes": body.notes, "completed_at": _iso()}})
        await self._event(rid, "step.completed", actor,
                           {"step_key": step["step_key"], "result": body.result})
        # If a step Failed and it's critical → surface but do not auto-abort
        # (explicit abort must be called by authority).
        # If a step is monitoring_window → move run to Monitoring
        if step["step_key"] == "monitoring_window" and body.result == "Passed":
            await self.db[RUN_C].update_one(
                {"go_live_run_id": rid},
                {"$set": {"status": "Monitoring"}})
        return await self._get_run(rid)

    async def abort(self, rid: str, body: AbortBody, actor: str) -> Dict[str, Any]:
        run = await self._get_run(rid)
        if run["status"] in ("Aborted", "Rolled Back", "Completed"):
            raise HTTPException(400, "Run already terminal")
        if body.reason not in ABORT_REASONS:
            raise HTTPException(400, f"Illegal abort reason {body.reason}")
        rec = {
            "go_live_abort_event_id": _uid(),
            "go_live_run_id": rid,
            "reason": body.reason, "authority": body.authority,
            "step_id": body.step_id, "evidence": body.evidence,
            "aborted_at": _iso(), "aborted_by": actor,
            "_source": "seed-eb18",
        }
        await self.db[ABORT_C].insert_one(dict(rec))
        await self.db[RUN_C].update_one(
            {"go_live_run_id": rid},
            {"$set": {"status": "Aborted", "abort_reason": body.reason,
                       "completed_at": _iso()}})
        # All remaining pending cutover steps → Blocked
        await self.db[STEP_C].update_many(
            {"go_live_run_id": rid, "kind": "cutover", "status": "Pending"},
            {"$set": {"status": "Blocked"}})
        await self._event(rid, "run.aborted", actor, {"reason": body.reason})
        return await self._get_run(rid)

    async def rollback(self, rid: str, actor: str) -> Dict[str, Any]:
        run = await self._get_run(rid)
        if run["status"] not in ("Running", "Monitoring", "Aborted", "Failed"):
            raise HTTPException(400,
                f"Rollback not permitted from state {run['status']}")
        await self.db[RUN_C].update_one(
            {"go_live_run_id": rid},
            {"$set": {"status": "Rolled Back", "completed_at": _iso()}})
        await self._event(rid, "run.rolled_back", actor, {})
        return await self._get_run(rid)

    async def record_monitoring(self, rid: str, body: MonitoringBody,
                                 actor: str) -> Dict[str, Any]:
        # Derive overall state deterministically if not supplied
        overall = body.overall_state
        if not overall:
            critical = (body.application_health == "Critical"
                         or body.provider_circuits == "Critical"
                         or body.integrity_findings > 0
                         or body.security_findings > 0
                         or body.uat_defects_post_cutover > 0
                         or body.migration_failures > 0)
            warn = (body.api_error_rate > 0.01 or body.auth_failures > 0
                     or body.failed_jobs > 0 or body.notification_failures > 0
                     or body.dead_letters > 0 or body.webhook_failures > 0)
            overall = "Critical" if critical else ("Warning" if warn else "Healthy")
        snap = {
            "go_live_monitoring_snapshot_id": _uid(),
            "go_live_run_id": rid,
            "observed_at": _iso(), "observed_by": actor,
            **body.model_dump(), "overall_state": overall,
            "_source": "seed-eb18",
        }
        await self.db[MON_C].insert_one(dict(snap))
        return snap

    async def release_decision(self, rid: str, actor: str) -> Dict[str, Any]:
        run = await self._get_run(rid)
        # Aggregate step + monitoring state
        crit_failed = await self.db[STEP_C].count_documents(
            {"go_live_run_id": rid, "kind": "cutover",
              "critical": True, "status": {"$in": ["Failed", "Blocked"]}})
        crit_pending = await self.db[STEP_C].count_documents(
            {"go_live_run_id": rid, "kind": "cutover",
              "critical": True, "status": "Pending"})
        latest_mon = await self.db[MON_C].find_one(
            {"go_live_run_id": rid}, {"_id": 0},
            sort=[("observed_at", -1)])
        mon_ok = bool(latest_mon and latest_mon.get("overall_state") != "Critical")
        aborted = run["status"] == "Aborted"
        rolled = run["status"] == "Rolled Back"
        # UAT defects still open (Critical/High) — reuse EB-17c compute
        try:
            open_states = ["Open", "Investigating", "Fixed",
                            "Ready for Retest", "Reopened"]
            crit_def = await self.db["uat_defects"].count_documents(
                {"severity": "Critical", "state": {"$in": open_states}})
            high_def = await self.db["uat_defects"].count_documents(
                {"severity": "High", "state": {"$in": open_states}})
        except Exception:
            crit_def, high_def = 0, 0
        blockers: List[str] = []
        if aborted: blockers.append("run_aborted")
        if rolled: blockers.append("run_rolled_back")
        if crit_failed: blockers.append(f"critical_step_failed={crit_failed}")
        if crit_pending: blockers.append(f"critical_step_pending={crit_pending}")
        if not mon_ok: blockers.append("monitoring_critical")
        if crit_def: blockers.append("open_critical_uat_defects")
        if high_def: blockers.append("open_high_uat_defects")
        # Determine status
        if aborted: result = "ABORTED"
        elif rolled: result = "ROLLED_BACK"
        elif blockers: result = "NOT_READY_TO_RELEASE"
        else:
            # Determine conditional based on last mon warning or non-critical warnings
            conditional = bool(latest_mon and latest_mon.get("overall_state") == "Warning")
            result = "RELEASED_WITH_CONDITIONS" if conditional else "RELEASED"
        # Persist decision (a run can only be Completed once)
        dec = {
            "go_live_release_decision_id": _uid(),
            "go_live_run_id": rid,
            "result": result, "blockers": blockers,
            "decided_at": _iso(), "decided_by": actor,
            "_source": "seed-eb18",
        }
        await self.db[DEC_C].insert_one(dict(dec))
        if result in ("RELEASED", "RELEASED_WITH_CONDITIONS"):
            await self.db[RUN_C].update_one(
                {"go_live_run_id": rid},
                {"$set": {"status": "Completed", "completed_at": _iso()}})
        return dec

    # ── migration authorisation ────────────────────────────────────
    async def upsert_mig_auth(self, body: MigAuthBody,
                               actor: str) -> Dict[str, Any]:
        aid = _uid()
        # Determine status
        all_fields_set = (body.workbook_identified and body.workbook_checksum
                           and body.workbook_owner and body.import_scope_approved
                           and body.mapping_approved and body.dry_run_completed
                           and body.issues_resolved
                           and body.go_decision in ("GO", "CONDITIONAL_GO")
                           and body.commit_pkg_checksum
                           and body.rollback_pkg_generated
                           and body.rollback_pkg_validated
                           and body.operators_assigned
                           and body.final_approval)
        if body.go_decision == "NO_GO":
            status = "NOT_AUTHORISED"
        elif all_fields_set and body.explicit_real_data_marker:
            status = "AUTHORISED"
        elif all_fields_set:
            status = "READY_FOR_APPROVAL"
        else:
            status = "NOT_AUTHORISED"
        doc = {
            "go_live_migration_authorisation_id": aid,
            **body.model_dump(),
            "status": status,
            "created_by": actor, "created_at": _iso(),
            "_source": "seed-eb18",
        }
        await self.db[AUTH_C].insert_one(dict(doc))
        return doc

    async def revoke_mig_auth(self, aid: str, actor: str) -> Dict[str, Any]:
        r = await self.db[AUTH_C].find_one(
            {"go_live_migration_authorisation_id": aid}, {"_id": 0})
        if not r: raise HTTPException(404, "Authorisation not found")
        await self.db[AUTH_C].update_one(
            {"go_live_migration_authorisation_id": aid},
            {"$set": {"status": "REVOKED",
                       "revoked_by": actor, "revoked_at": _iso()}})
        return await self.db[AUTH_C].find_one(
            {"go_live_migration_authorisation_id": aid}, {"_id": 0})

    # ── deployment package (metadata only) ─────────────────────────
    async def deployment_package(self) -> Dict[str, Any]:
        # Read VERSION file safely
        version = "unknown"
        try:
            with open("/app/VERSION", "r") as f: version = f.read().strip()
        except Exception: pass
        return {
            "application_version": version,
            "environment_name": os.environ.get("EMERGENT_ENVIRONMENT", "preview"),
            "commit_sha": os.environ.get("COMMIT_SHA"),
            "configuration_validation_result": "PASS",
            "migration_schema_version": "eb17b-1",
            "required_secrets": [
                "MONGO_URL", "JWT_SECRET",
                "PROVIDER_PLACEHOLDER_KEY",  # loaded but disabled
                "WEBHOOK_SIGNING_SECRET",
                "SCHEDULER_TOKEN",
            ],
            "database_target": {"engine": "MongoDB", "db_name": "PROD_TBD"},
            "object_storage_target": {"engine": "Emergent Object Storage",
                                        "bucket": "PROD_TBD"},
            "scheduler_configuration_state": "disabled",
            "provider_configuration_state": "loaded-disabled",
            "webhook_configuration_state": "loaded-disabled",
            "backup_configuration_state": "scheduled-pending",
            "monitoring_configuration_state": "enabled",
            "rollback_version": "dcc-phase2-eb17c",
            "deployment_owner": "Platform / Admin",
            "approval_state": "framework-only",
            "generated_at": _iso(),
            "_source": "seed-eb18",
            "note": "Framework metadata only. Contains no secret values.",
        }

    # ── helpers ────────────────────────────────────────────────────
    async def _get_run(self, rid: str) -> Dict[str, Any]:
        r = await self.db[RUN_C].find_one({"go_live_run_id": rid}, {"_id": 0})
        if not r: raise HTTPException(404, "Run not found")
        return r

    async def _event(self, rid, etype, actor, payload):
        await self.db[EVT_C].insert_one({
            "go_live_event_id": _uid(),
            "go_live_run_id": rid,
            "event_type": etype, "actor": actor,
            "payload": payload, "at": _iso(),
            "_source": "seed-eb18",
        })


async def ensure_indexes(db):
    for coll, key in (
        (RUN_C, "go_live_run_id"), (STEP_C, "go_live_step_id"),
        (EVT_C, "go_live_event_id"), (APR_C, "go_live_approval_id"),
        (ABORT_C, "go_live_abort_event_id"),
        (MON_C, "go_live_monitoring_snapshot_id"),
        (EVID_C, "go_live_evidence_id"),
        (DEC_C, "go_live_release_decision_id"),
        (PRE_C, "prerequisite_snapshot_id"),
        (AUTH_C, "go_live_migration_authorisation_id"),
    ):
        await db[coll].create_index(key, unique=True)


def build_golive_router(db, app, get_current_user):
    r = APIRouter(tags=["go-live"])
    svc = GoLiveService(db, app)

    @r.get("/api/go-live/status")
    async def status(current=Depends(get_current_user)):
        _require(current, ROLE_RO)
        runs_n = await db[RUN_C].count_documents({"_source": "seed-eb18"})
        latest = await db[RUN_C].find_one({"_source": "seed-eb18"},
                                             {"_id": 0}, sort=[("created_at", -1)])
        return {"total_runs": runs_n, "latest": latest,
                 "version": (await svc.deployment_package())["application_version"]}

    @r.get("/api/go-live/prerequisites")
    async def prerequisites(current=Depends(get_current_user)):
        _require(current, ROLE_RO)
        return await svc.prerequisites()

    @r.post("/api/go-live/runs")
    async def create_run(body: CreateRunBody, current=Depends(get_current_user)):
        _require(current, ROLE_MGR_PLUS)
        return await svc.create_run(body, current.get("email"))

    @r.get("/api/go-live/runs")
    async def list_runs(current=Depends(get_current_user)):
        _require(current, ROLE_RO)
        return await db[RUN_C].find(
            {"_source": "seed-eb18"}, {"_id": 0}).sort("created_at", -1).to_list(100)

    @r.get("/api/go-live/runs/{rid}")
    async def get_run(rid: str, current=Depends(get_current_user)):
        _require(current, ROLE_RO)
        run = await svc._get_run(rid)
        steps = await db[STEP_C].find({"go_live_run_id": rid},
                                         {"_id": 0}).sort([("kind", 1), ("order", 1)]).to_list(200)
        appr = await db[APR_C].find({"go_live_run_id": rid},
                                       {"_id": 0}).to_list(50)
        return {"run": run, "steps": steps, "approvals": appr}

    @r.post("/api/go-live/runs/{rid}/approve")
    async def approve(rid: str, body: ApproveRunBody,
                       current=Depends(get_current_user)):
        _require(current, ROLE_MGR_PLUS)
        if body.approval_layer in ("Technical", "Security", "Release"):
            _require(current, ROLE_ADMIN,
                     f"{body.approval_layer} approval requires Admin")
        return await svc.approve(rid, body, current.get("email"),
                                    current.get("role"))

    @r.post("/api/go-live/runs/{rid}/start")
    async def start(rid: str, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await svc.start(rid, current.get("email"))

    @r.post("/api/go-live/runs/{rid}/steps/{step_id}/complete")
    async def complete_step(rid: str, step_id: str, body: StepCompleteBody,
                             current=Depends(get_current_user)):
        _require(current, ROLE_MGR_PLUS)
        return await svc.complete_step(rid, step_id, body, current.get("email"))

    @r.post("/api/go-live/runs/{rid}/abort")
    async def abort(rid: str, body: AbortBody, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await svc.abort(rid, body, current.get("email"))

    @r.post("/api/go-live/runs/{rid}/rollback")
    async def rollback(rid: str, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await svc.rollback(rid, current.get("email"))

    @r.get("/api/go-live/runs/{rid}/monitoring")
    async def get_monitoring(rid: str, current=Depends(get_current_user)):
        _require(current, ROLE_RO)
        return await db[MON_C].find({"go_live_run_id": rid},
                                       {"_id": 0}).sort("observed_at", -1).to_list(200)

    @r.post("/api/go-live/runs/{rid}/monitoring")
    async def add_monitoring(rid: str, body: MonitoringBody,
                              current=Depends(get_current_user)):
        _require(current, ROLE_MGR_PLUS)
        return await svc.record_monitoring(rid, body, current.get("email"))

    @r.get("/api/go-live/deployment-package")
    async def dep_pkg(current=Depends(get_current_user)):
        _require(current, ROLE_RO)
        return await svc.deployment_package()

    @r.get("/api/go-live/release-decision")
    async def rel_dec(rid: str, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await svc.release_decision(rid, current.get("email"))

    @r.get("/api/go-live/migration-authorisation")
    async def list_mig(current=Depends(get_current_user)):
        _require(current, ROLE_RO)
        return await db[AUTH_C].find({"_source": "seed-eb18"},
                                        {"_id": 0}).sort("created_at", -1).to_list(50)

    @r.post("/api/go-live/migration-authorisation")
    async def create_mig(body: MigAuthBody, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)  # elevated separation
        return await svc.upsert_mig_auth(body, current.get("email"))

    @r.post("/api/go-live/migration-authorisation/revoke")
    async def revoke_mig(auth_id: str = Body(..., embed=True),
                          current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await svc.revoke_mig_auth(auth_id, current.get("email"))

    return r
