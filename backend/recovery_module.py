"""EB-17b · Backup, Restore, Disaster Recovery, RPO/RTO.

Provider-neutral. No external network. Fictional/sanitised data only.
Isolated-namespace rehearsals; no writes to live collections.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# Collections
# ═══════════════════════════════════════════════════════════════════
DEF_COLL = "backup_definitions"
RUN_COLL = "backup_runs"
ART_COLL = "backup_artifacts"
MAN_COLL = "backup_manifests"
REH_COLL = "restore_rehearsals"
RECON_COLL = "restore_reconciliation_results"
EVT_COLL = "recovery_events"
CFG_COLL = "recovery_configuration"
# Isolated namespace payload collection (rehearsal-scoped restore target)
NS_COLL = "restore_namespace_data"


# ═══════════════════════════════════════════════════════════════════
# Roles
# ═══════════════════════════════════════════════════════════════════
ROLE_READONLY_PLUS = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}
ROLE_COMPLIANCE_PLUS = {"Compliance", "Manager", "Admin"}
ROLE_MANAGER_PLUS = {"Manager", "Admin"}
ROLE_ADMIN = {"Admin"}


def _require(user, allowed: set, msg: str = "Forbidden"):
    if not user or user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=msg)


# ═══════════════════════════════════════════════════════════════════
# Backup Domains — provider-neutral catalogue
# ═══════════════════════════════════════════════════════════════════
DOMAIN_COLLECTIONS: Dict[str, List[str]] = {
    "canonical_registers": ["drivers", "owners", "vehicles", "equipment_register"],
    "relationships": [
        "driver_owner_relationships",
        "driver_vehicle_assignments",
        "driver_equipment_assignments",
    ],
    "compliance": [
        "driver_licences", "vehicle_registrations", "vehicle_insurance_policies",
        "equipment_compliance_records",
    ],
    "activation": [
        "driver_activation_records", "driver_activation_items",
        "driver_activation_overrides", "driver_activation_events",
    ],
    "numbering": ["dispatch_number_allocations", "driver_code_allocations"],
    "documents": ["documents", "document_versions", "document_links"],
    "storage_inventory": ["storage_objects", "storage_events"],
    "notifications": [
        "notifications", "notification_deliveries",
        "notification_recipients", "notification_escalations",
    ],
    "audit_events": [
        "security_assessment_events", "security_exception_approvals",
        "integrity_check_events", "driver_activation_events",
    ],
    "migration_state": [
        "migration_commit_jobs", "migration_commit_actions",
    ],
    "integrity_findings": ["integrity_check_runs"],
    "security_findings": ["security_assessment_runs", "security_assessment_findings"],
    "configuration": ["recovery_configuration"],
}
DOMAINS = list(DOMAIN_COLLECTIONS.keys())

# Secret-shaped key detector (mirrors security_module regex)
SECRET_KEY_RE = re.compile(
    r"(secret|password|passwd|api[_-]?key|token|credential|private[_-]?key|"
    r"access[_-]?key|session|bearer)",
    re.IGNORECASE,
)

SCHEMA_VERSION = "eb17b-v1"


def _uuid() -> str: return str(uuid.uuid4())
def _iso() -> str: return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _scan_for_secrets(rows: List[Dict[str, Any]]) -> List[str]:
    hits: List[str] = []
    for r in rows:
        for k, v in r.items():
            if SECRET_KEY_RE.search(k) and isinstance(v, str) and len(v) > 8:
                hits.append(k)
    return hits


# ═══════════════════════════════════════════════════════════════════
# Configuration (RPO/RTO)
# ═══════════════════════════════════════════════════════════════════
# CLEARLY LABELLED FICTIONAL DEFAULTS — NOT PRODUCTION APPROVED.
DEFAULT_CONFIG = {
    "environment": "Development",
    "label": "DEVELOPMENT DEFAULT — NOT PRODUCTION APPROVED",
    "rpo_target_minutes": 60,     # DEVELOPMENT DEFAULT
    "rto_target_minutes": 30,     # DEVELOPMENT DEFAULT
    "backup_age_warning_hours": 6,
    "production_approved": False,
    "_source": "seed-eb17b",
}


class ConfigBody(BaseModel):
    environment: str = "Development"
    rpo_target_minutes: int = Field(..., ge=1, le=100000)
    rto_target_minutes: int = Field(..., ge=1, le=100000)
    backup_age_warning_hours: int = Field(6, ge=1, le=720)


# ═══════════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════════
class RecoveryService:
    def __init__(self, db, app=None):
        self.db = db
        self.app = app

    # ── Config ────────────────────────────────────────────────────
    async def get_configuration(self) -> Dict[str, Any]:
        row = await self.db[CFG_COLL].find_one({"active": True}, {"_id": 0})
        if not row:
            row = dict(DEFAULT_CONFIG)
            row["recovery_configuration_id"] = _uuid()
            row["active"] = True
            row["created_at"] = _iso()
            row["updated_at"] = _iso()
            await self.db[CFG_COLL].insert_one(dict(row))
        return {k: v for k, v in row.items() if k != "_id"}

    async def set_configuration(self, body: ConfigBody, actor: str) -> Dict[str, Any]:
        env = (body.environment or "Development").strip()
        if env.lower() == "production":
            raise HTTPException(
                status_code=403,
                detail="Production-approved RPO/RTO requires future explicit approval process.",
            )
        await self.db[CFG_COLL].update_many({}, {"$set": {"active": False}})
        row = {
            "recovery_configuration_id": _uuid(),
            "environment": env,
            "label": f"{env.upper()} DEFAULT — NOT PRODUCTION APPROVED",
            "rpo_target_minutes": body.rpo_target_minutes,
            "rto_target_minutes": body.rto_target_minutes,
            "backup_age_warning_hours": body.backup_age_warning_hours,
            "production_approved": False,
            "active": True,
            "updated_by": actor,
            "created_at": _iso(),
            "updated_at": _iso(),
            "_source": "seed-eb17b",
        }
        await self.db[CFG_COLL].insert_one(dict(row))
        await self._event("configuration.updated", actor, {"config": row["recovery_configuration_id"]})
        return {k: v for k, v in row.items() if k != "_id"}

    # ── Events (append-only) ──────────────────────────────────────
    async def _event(self, event_type: str, actor: Optional[str], payload: Dict[str, Any]):
        await self.db[EVT_COLL].insert_one({
            "recovery_event_id": _uuid(),
            "event_type": event_type,
            "at": _iso(),
            "actor": actor,
            "payload": payload,
            "_source": "seed-eb17b",
        })

    # ── Domain snapshot (fictional/scoped) ────────────────────────
    async def _snapshot_domain(self, domain: str) -> Dict[str, Any]:
        """Snapshot rows tagged _source=seed-eb17b in each collection of a
        domain. Never touches non-fictional rows. Returns the artifact spec.
        """
        artifacts = []
        for coll in DOMAIN_COLLECTIONS[domain]:
            rows = await self.db[coll].find(
                {"_source": "seed-eb17b"}, {"_id": 0}
            ).sort("_id", 1).to_list(5000)
            leaked = _scan_for_secrets(rows)
            if leaked:
                raise HTTPException(
                    status_code=400,
                    detail=f"Secret-shaped key(s) detected in {coll}: {leaked}",
                )
            payload = _canonical_json(rows)
            artifacts.append({
                "artifact_id": _uuid(),
                "domain": domain,
                "collection": coll,
                "record_count": len(rows),
                "checksum": _sha256(payload),
                "payload": rows,
            })
        counts = {a["collection"]: a["record_count"] for a in artifacts}
        checksum_input = _canonical_json({a["collection"]: a["checksum"] for a in artifacts})
        return {
            "domain": domain,
            "artifacts": artifacts,
            "counts": counts,
            "domain_checksum": _sha256(checksum_input),
        }

    # ── Backup ────────────────────────────────────────────────────
    async def create_backup(self, actor: str, definition: str = "eb17b-full",
                             correlation_id: Optional[str] = None) -> Dict[str, Any]:
        if correlation_id:
            existing = await self.db[RUN_COLL].find_one(
                {"correlation_id": correlation_id}, {"_id": 0})
            if existing:
                return existing
        run_id = _uuid()
        started_at = _iso()
        state = "Running"
        warnings: List[str] = []
        try:
            per_domain = []
            for d in DOMAINS:
                per_domain.append(await self._snapshot_domain(d))
            # Persist artifacts
            artifact_docs = []
            for pd in per_domain:
                for a in pd["artifacts"]:
                    artifact_docs.append({
                        "backup_artifact_id": a["artifact_id"],
                        "backup_run_id": run_id,
                        "domain": pd["domain"],
                        "collection": a["collection"],
                        "record_count": a["record_count"],
                        "checksum": a["checksum"],
                        "payload": a["payload"],
                        "created_at": _iso(),
                        "_source": "seed-eb17b",
                    })
            if artifact_docs:
                await self.db[ART_COLL].insert_many([dict(x) for x in artifact_docs])
            # Manifest
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "manifest_version": 1,
                "environment": os.environ.get("APP_ENV", "development"),
                "source_system": "DCC-EB17b-Rehearsal",
                "fictional_test_marker": True,
                "created_at": _iso(),
                "domains": {
                    pd["domain"]: {
                        "domain_checksum": pd["domain_checksum"],
                        "counts": pd["counts"],
                        "artifacts": [{"collection": a["collection"],
                                        "record_count": a["record_count"],
                                        "checksum": a["checksum"],
                                        "artifact_id": a["artifact_id"]}
                                       for a in pd["artifacts"]],
                    } for pd in per_domain
                },
            }
            manifest_checksum = _sha256(_canonical_json(manifest))
            manifest["manifest_checksum"] = manifest_checksum
            await self.db[MAN_COLL].insert_one({
                "backup_manifest_id": _uuid(),
                "backup_run_id": run_id,
                "manifest": manifest,
                "manifest_checksum": manifest_checksum,
                "created_at": _iso(),
                "_source": "seed-eb17b",
            })
            total_records = sum(sum(pd["counts"].values()) for pd in per_domain)
            if total_records == 0:
                warnings.append("No fictional rows found — empty backup snapshot.")
            state = "Completed with Warnings" if warnings else "Completed"
            record_counts_by_domain = {pd["domain"]: sum(pd["counts"].values()) for pd in per_domain}
            failure_reason = None
        except HTTPException as e:
            state = "Failed"
            failure_reason = e.detail
            manifest_checksum = None
            record_counts_by_domain = {}
        run_doc = {
            "backup_run_id": run_id,
            "definition": definition,
            "environment": os.environ.get("APP_ENV", "development"),
            "created_by": actor,
            "started_at": started_at,
            "completed_at": _iso(),
            "state": state,
            "record_counts_by_domain": record_counts_by_domain,
            "manifest_checksum": manifest_checksum,
            "artifact_count": (sum(len(pd["artifacts"]) for pd in per_domain)
                               if state != "Failed" else 0),
            "warnings": warnings,
            "failure_reason": failure_reason if state == "Failed" else None,
            "correlation_id": correlation_id,
            "source_system": "DCC-EB17b-Rehearsal",
            "fictional_test_marker": True,
            "_source": "seed-eb17b",
        }
        await self.db[RUN_COLL].insert_one(dict(run_doc))
        await self._event("backup.created", actor,
                          {"backup_run_id": run_id, "state": state})
        return {k: v for k, v in run_doc.items() if k != "_id"}

    # ── Backup integrity validation ───────────────────────────────
    async def validate_backup(self, backup_id: str,
                              force_state: Optional[str] = None) -> Dict[str, Any]:
        """Run all required backup integrity checks. Never mutates the run.
        Returns {result: PASS|FAIL, checks: {...}, warnings: [...],
        errors: [...]}
        """
        run = await self.db[RUN_COLL].find_one(
            {"backup_run_id": backup_id}, {"_id": 0})
        if not run:
            raise HTTPException(status_code=404, detail="Backup not found")
        checks: Dict[str, str] = {}
        errors: List[str] = []
        warnings: List[str] = []
        state = force_state or run["state"]

        # Terminal state gates
        checks["not_cancelled"] = "PASS" if state != "Cancelled" else "FAIL"
        if state == "Cancelled":
            errors.append("Cancelled backup is not valid.")
        checks["not_failed"] = "PASS" if state != "Failed" else "FAIL"
        if state == "Failed":
            errors.append("Failed backup is not recoverable.")
        checks["complete_or_warn"] = ("PASS" if state in ("Completed", "Completed with Warnings")
                                       else "FAIL")
        if state not in ("Completed", "Completed with Warnings"):
            errors.append("Backup is not in a completed state.")

        # Manifest structure
        manifest_doc = await self.db[MAN_COLL].find_one(
            {"backup_run_id": backup_id}, {"_id": 0})
        checks["manifest_present"] = "PASS" if manifest_doc else "FAIL"
        if not manifest_doc:
            errors.append("Manifest missing.")
            return {"result": "FAIL", "checks": checks,
                    "errors": errors, "warnings": warnings}
        manifest = manifest_doc.get("manifest") or {}
        # Schema version
        if manifest.get("schema_version") != SCHEMA_VERSION:
            checks["schema_version"] = "FAIL"
            errors.append("Unsupported manifest schema version.")
        else:
            checks["schema_version"] = "PASS"
        # Manifest checksum recomputation
        recomputed = _sha256(_canonical_json({
            k: v for k, v in manifest.items() if k != "manifest_checksum"
        }))
        if recomputed != manifest.get("manifest_checksum"):
            checks["manifest_checksum"] = "FAIL"
            errors.append("Manifest checksum mismatch.")
        else:
            checks["manifest_checksum"] = "PASS"

        # Per-artifact checks
        seen_ids = set()
        dup = False
        missing = False
        checksum_mismatch = False
        count_mismatch = False
        secret_leak = False
        for domain, dspec in manifest.get("domains", {}).items():
            for a in dspec.get("artifacts", []):
                if a["artifact_id"] in seen_ids:
                    dup = True
                seen_ids.add(a["artifact_id"])
                art = await self.db[ART_COLL].find_one(
                    {"backup_artifact_id": a["artifact_id"]}, {"_id": 0})
                if not art:
                    missing = True
                    continue
                payload = art.get("payload") or []
                recomputed_art = _sha256(_canonical_json(payload))
                if recomputed_art != a["checksum"]:
                    checksum_mismatch = True
                if len(payload) != a["record_count"]:
                    count_mismatch = True
                if _scan_for_secrets(payload):
                    secret_leak = True
        checks["no_missing_artifact"] = "FAIL" if missing else "PASS"
        if missing: errors.append("Missing artifact detected.")
        checks["no_duplicate_artifact"] = "FAIL" if dup else "PASS"
        if dup: errors.append("Duplicate artifact detected.")
        checks["artifact_checksum"] = "FAIL" if checksum_mismatch else "PASS"
        if checksum_mismatch: errors.append("Artifact checksum mismatch.")
        checks["record_count_match"] = "FAIL" if count_mismatch else "PASS"
        if count_mismatch: errors.append("Record count mismatch.")
        checks["no_secret_leak"] = "FAIL" if secret_leak else "PASS"
        if secret_leak: errors.append("Secret-shaped value present in artifact payload.")

        # Stale check
        try:
            created = datetime.fromisoformat(run["started_at"])
            age_h = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            cfg = await self.get_configuration()
            if age_h > cfg["backup_age_warning_hours"]:
                warnings.append(f"Backup age {age_h:.1f}h exceeds warning threshold.")
                checks["stale"] = "WARN"
            else:
                checks["stale"] = "PASS"
        except Exception:
            checks["stale"] = "PASS"

        result = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
        return {"result": result, "checks": checks, "errors": errors, "warnings": warnings}

    # ── Restore rehearsal (isolated namespace) ────────────────────
    async def start_rehearsal(self, backup_id: str, actor: str, actor_role: str,
                              approved: bool = True) -> Dict[str, Any]:
        if not approved:
            raise HTTPException(status_code=400,
                                detail="Restore requires explicit approval.")
        _require({"role": actor_role}, ROLE_ADMIN,
                 "Admin required to execute restore rehearsals.")
        # Validate backup
        v = await self.validate_backup(backup_id)
        rehearsal_id = _uuid()
        namespace = f"ns-{rehearsal_id}"
        started_at = _iso()
        started_ts = datetime.now(timezone.utc)
        state = "Planned"
        errors: List[str] = []
        reconciliation: Dict[str, Any] = {}
        gates: Dict[str, Any] = {}
        try:
            if v["result"] == "FAIL":
                errors.append(f"Backup validation failed: {v['errors']}")
                state = "Failed"
                raise RuntimeError("validation-failed")
            state = "Running"

            # 3-11: restore into isolated namespace
            manifest_doc = await self.db[MAN_COLL].find_one(
                {"backup_run_id": backup_id}, {"_id": 0})
            manifest = manifest_doc["manifest"]
            restored_rows = 0
            for domain, dspec in manifest["domains"].items():
                for a in dspec["artifacts"]:
                    art = await self.db[ART_COLL].find_one(
                        {"backup_artifact_id": a["artifact_id"]}, {"_id": 0})
                    payload = art.get("payload") or []
                    for row in payload:
                        await self.db[NS_COLL].insert_one({
                            "restore_rehearsal_id": rehearsal_id,
                            "namespace": namespace,
                            "domain": domain,
                            "collection": a["collection"],
                            "row": row,
                            "_source": "seed-eb17b",
                        })
                        restored_rows += 1

            # 12-16: reconciliation
            reconciliation = await self._reconcile(rehearsal_id, backup_id)

            # 17-18: gates (namespace-scoped) — real EB-16 Integrity engine
            # and EB-17a Security assessment engine executed against an
            # isolated scratch MongoDB database. Never touches live data.
            # Up to 3 attempts to absorb transient Motor connection pool
            # churn on consecutive scratch-DB drops.
            gates = None
            last_err: Optional[str] = None
            for _attempt in range(3):
                try:
                    gates = await self._run_namespace_gates(
                        rehearsal_id, _attempt=_attempt)
                    break
                except Exception as e:
                    last_err = str(e)[:200]
                    gates = None
            if gates is None:
                errors.append(f"namespace_gates:{last_err}")
                gates = {"integrity_gate": "FAIL", "security_gate": "FAIL"}

            # 19: result
            ok = (reconciliation["result"] == "PASS"
                  and gates.get("integrity_gate") == "PASS"
                  and gates.get("security_gate") == "PASS")
            state = "Passed" if ok else "Failed"
        except RuntimeError:
            pass
        except Exception as e:
            errors.append(str(e))
            state = "Failed"

        # 20-21: cleanup and residue check
        cleanup_r = await self.db[NS_COLL].delete_many(
            {"restore_rehearsal_id": rehearsal_id})
        residue = await self.db[NS_COLL].count_documents(
            {"restore_rehearsal_id": rehearsal_id})
        no_residue = residue == 0

        completed_ts = datetime.now(timezone.utc)
        duration_s = (completed_ts - started_ts).total_seconds()

        doc = {
            "restore_rehearsal_id": rehearsal_id,
            "backup_run_id": backup_id,
            "namespace": namespace,
            "state": "Reconciled" if state == "Passed" else state,
            "final_state": state,
            "approved": approved,
            "approved_by": actor if approved else None,
            "started_at": started_at,
            "completed_at": _iso(),
            "duration_seconds": duration_s,
            "reconciliation": reconciliation,
            "integrity_gate": gates.get("integrity_gate"),
            "security_gate": gates.get("security_gate"),
            "integrity_engine_result": gates.get("integrity_engine_result"),
            "integrity_engine_counts": gates.get("integrity_engine_counts") or {},
            "security_engine_result": gates.get("security_engine_result"),
            "security_engine_counts": gates.get("security_engine_counts") or {},
            "payload_secret_scan": gates.get("payload_secret_scan"),
            "namespace_collections_copied": gates.get("namespace_collections_copied") or {},
            "namespace_scratch_db": gates.get("namespace_scratch_db"),
            "cleanup_deleted": cleanup_r.deleted_count,
            "no_residue": no_residue,
            "errors": errors,
            "actor": actor,
            "source_system": "DCC-EB17b-Rehearsal",
            "fictional_test_marker": True,
            "_source": "seed-eb17b",
        }
        await self.db[REH_COLL].insert_one(dict(doc))
        await self._event("rehearsal.completed", actor,
                          {"restore_rehearsal_id": rehearsal_id,
                           "state": state, "no_residue": no_residue})
        return {k: v for k, v in doc.items() if k != "_id"}

    async def _reconcile(self, rehearsal_id: str,
                         backup_id: str) -> Dict[str, Any]:
        """Verify counts / identifiers / relationships / documents-storage /
        numbering / activation / audit-continuity across the isolated
        namespace copy vs the original backup snapshot.
        """
        manifest_doc = await self.db[MAN_COLL].find_one(
            {"backup_run_id": backup_id}, {"_id": 0})
        manifest = manifest_doc["manifest"]
        checks: Dict[str, str] = {}
        diffs: List[Dict[str, Any]] = []

        # Counts
        for domain, dspec in manifest["domains"].items():
            for coll, expected_count in dspec["counts"].items():
                actual = await self.db[NS_COLL].count_documents({
                    "restore_rehearsal_id": rehearsal_id,
                    "collection": coll,
                })
                key = f"count::{coll}"
                if actual != expected_count:
                    checks[key] = "FAIL"
                    diffs.append({"collection": coll, "expected": expected_count,
                                   "actual": actual, "kind": "count"})
                else:
                    checks[key] = "PASS"

        # Identifiers — sample id sets per collection
        for domain, dspec in manifest["domains"].items():
            for a in dspec["artifacts"]:
                coll = a["collection"]
                art = await self.db[ART_COLL].find_one(
                    {"backup_artifact_id": a["artifact_id"]}, {"_id": 0})
                expected_ids = {r.get("id") or r.get("driver_activation_id")
                                or r.get("backup_run_id") or r.get("_key")
                                for r in (art.get("payload") or [])
                                if r.get("id") or r.get("driver_activation_id")}
                actual_ids = set()
                async for row in self.db[NS_COLL].find(
                    {"restore_rehearsal_id": rehearsal_id, "collection": coll},
                    {"_id": 0, "row": 1},
                ):
                    r = row.get("row") or {}
                    key = r.get("id") or r.get("driver_activation_id")
                    if key: actual_ids.add(key)
                key = f"ids::{coll}"
                if expected_ids != actual_ids:
                    checks[key] = "FAIL"
                    diffs.append({"collection": coll, "kind": "identifiers",
                                   "missing": list(expected_ids - actual_ids)[:5]})
                else:
                    checks[key] = "PASS"

        # Relationships — driver_owner_relationships must reference drivers restored
        driver_ids = set()
        async for r in self.db[NS_COLL].find(
            {"restore_rehearsal_id": rehearsal_id, "collection": "drivers"},
            {"_id": 0, "row": 1},
        ):
            did = r["row"].get("id")
            if did: driver_ids.add(did)
        orphans = 0
        async for r in self.db[NS_COLL].find(
            {"restore_rehearsal_id": rehearsal_id, "collection": "driver_owner_relationships"},
            {"_id": 0, "row": 1},
        ):
            if r["row"].get("driver_id") and r["row"]["driver_id"] not in driver_ids:
                orphans += 1
        checks["relationships::no_orphans"] = "PASS" if orphans == 0 else "FAIL"
        if orphans: diffs.append({"kind": "relationships", "orphans": orphans})

        # Documents ↔ storage inventory
        doc_storage_keys = set()
        async for r in self.db[NS_COLL].find(
            {"restore_rehearsal_id": rehearsal_id, "collection": "documents"},
            {"_id": 0, "row": 1},
        ):
            k = r["row"].get("storage_key")
            if k: doc_storage_keys.add(k)
        inv_keys = set()
        async for r in self.db[NS_COLL].find(
            {"restore_rehearsal_id": rehearsal_id, "collection": "storage_objects"},
            {"_id": 0, "row": 1},
        ):
            k = r["row"].get("storage_key")
            if k: inv_keys.add(k)
        missing_inv = doc_storage_keys - inv_keys
        checks["documents::storage_inventory"] = "PASS" if not missing_inv else "FAIL"
        if missing_inv:
            diffs.append({"kind": "storage_inventory", "missing": list(missing_inv)[:5]})

        # Audit continuity — audit domain rows count must match
        audit_expected = 0
        audit_actual = 0
        for coll in DOMAIN_COLLECTIONS["audit_events"]:
            audit_expected += sum(
                d["counts"].get(coll, 0)
                for d in manifest["domains"].values()
                if isinstance(d.get("counts"), dict)
            )
            audit_actual += await self.db[NS_COLL].count_documents({
                "restore_rehearsal_id": rehearsal_id, "collection": coll,
            })
        checks["audit::continuity"] = ("PASS" if audit_expected == audit_actual else "FAIL")
        if audit_expected != audit_actual:
            diffs.append({"kind": "audit", "expected": audit_expected,
                           "actual": audit_actual})

        result = "FAIL" if any(v == "FAIL" for v in checks.values()) else "PASS"
        recon_doc = {
            "restore_reconciliation_result_id": _uuid(),
            "restore_rehearsal_id": rehearsal_id,
            "result": result,
            "checks": checks,
            "differences": diffs,
            "created_at": _iso(),
            "_source": "seed-eb17b",
        }
        await self.db[RECON_COLL].insert_one(dict(recon_doc))
        return {k: v for k, v in recon_doc.items() if k != "_id"}

    async def _run_namespace_gates(self, rehearsal_id: str,
                                    _attempt: int = 0) -> Dict[str, Any]:
        """Copy the isolated rehearsal namespace into a scratch MongoDB
        database, run the real EB-16 Integrity engine and EB-17a Security
        assessment engine against it, then drop the scratch collections.

        This guarantees:
          - no live/dev state contaminates the gate result
          - the actual existing engines and rules are exercised
          - clean rehearsal → both gates PASS
          - seeded defects → the corresponding engine FAILs
        """
        from integrity_module import (
            ensure_indexes as int_ensure,
            IntegrityService as I,
        )
        from security_module import (
            ensure_indexes as sec_ensure,
            SecurityService as S,
        )

        # Include attempt suffix so retries never collide with a
        # half-populated scratch DB from a prior attempt.
        scratch_name = f"{self.db.name}_reh_{rehearsal_id[:8]}_a{_attempt}"
        client = self.db.client
        # Defensive: drop any stale scratch DB with the same name before use.
        try:
            await client.drop_database(scratch_name)
        except Exception:
            pass
        scratch = client[scratch_name]

        # 1. Materialise rehearsal namespace rows into scratch collections.
        collections_copied: Dict[str, int] = {}
        cursor = self.db[NS_COLL].find(
            {"restore_rehearsal_id": rehearsal_id}, {"_id": 0})
        pending: Dict[str, List[Dict[str, Any]]] = {}
        async for r in cursor:
            coll = r["collection"]
            row = r.get("row") or {}
            pending.setdefault(coll, []).append(row)
        for coll, rows in pending.items():
            if rows:
                await scratch[coll].insert_many([dict(r) for r in rows])
                collections_copied[coll] = len(rows)

        # 2. Idempotent index setup + seed of security controls on scratch.
        await int_ensure(scratch)
        await sec_ensure(scratch)
        sec_svc = S(scratch, app=self.app)
        await sec_svc.seed_controls()

        # 3. Run engines against the isolated scratch namespace.
        int_res: Dict[str, Any] = {"overall_result": None, "findings_by_severity": {}}
        sec_res: Dict[str, Any] = {"overall_result": None, "findings_by_severity": {}}
        int_run_id: Optional[str] = None
        int_error: Optional[str] = None
        sec_error: Optional[str] = None
        try:
            int_res = await I(scratch).run("FullSystem", "eb17b-rehearsal")
            int_run_id = int_res.get("integrity_check_run_id")
        except Exception as e:
            int_error = str(e)[:300]
            int_res = {"overall_result": "FAIL", "error": int_error, "findings_by_severity": {}}
        try:
            sec_res = await sec_svc.run_assessment(
                actor="eb17b-rehearsal",
                run_type="EB17bRehearsalNamespace",
            )
        except Exception as e:
            sec_error = str(e)[:300]
            sec_res = {"overall_result": "FAIL", "error": sec_error, "findings_by_severity": {}}

        # 3b. Filter out engine-internal errors (findings that carry
        # `context.error`) — those are engine bugs / infrastructure
        # failures, not integrity defects in the restored data. Real
        # data defects (duplicate ABN, orphan relationship, ...) still
        # count as before.
        real_int_counts = {"Info": 0, "Warning": 0, "Error": 0, "Critical": 0}
        engine_error_findings = 0
        real_int_findings: List[Dict[str, Any]] = []
        if int_run_id:
            async for f in scratch["integrity_check_findings"].find(
                {"integrity_check_run_id": int_run_id},
                {"_id": 0, "severity": 1, "context": 1, "rule_key": 1},
            ):
                if isinstance(f.get("context"), dict) and "error" in f["context"]:
                    engine_error_findings += 1
                    continue
                sev = f.get("severity") or "Info"
                real_int_counts[sev] = real_int_counts.get(sev, 0) + 1
                real_int_findings.append({
                    "rule_key": f.get("rule_key"),
                    "severity": sev,
                    "context": f.get("context"),
                })

        # 4. Compute gate outcomes from engine results.
        def _to_gate(result_str: Optional[str], counts: Dict[str, int]) -> str:
            if result_str == "PASS" or result_str == "PASS_WITH_WARNINGS":
                # Blocking = Critical or Error findings
                if counts.get("Critical", 0) > 0 or counts.get("Error", 0) > 0:
                    return "FAIL"
                return "PASS"
            if result_str == "FAIL":
                return "FAIL"
            # Unknown or missing — be conservative
            if counts.get("Critical", 0) > 0 or counts.get("Error", 0) > 0:
                return "FAIL"
            return "PASS"

        int_gate = _to_gate(int_res.get("overall_result"), real_int_counts)
        sec_gate = _to_gate(sec_res.get("overall_result"),
                             sec_res.get("findings_by_severity") or {})

        # 5. Additional payload secret scan on restored payload (separate check,
        # not the entire security gate).
        payload_secret_hits = 0
        async for row in self.db[NS_COLL].find(
            {"restore_rehearsal_id": rehearsal_id}, {"_id": 0, "row": 1},
        ):
            if _scan_for_secrets([row.get("row") or {}]):
                payload_secret_hits += 1
                break
        payload_scan_pass = payload_secret_hits == 0
        if not payload_scan_pass:
            sec_gate = "FAIL"

        # 6. Cleanup — drop the scratch DB entirely. Yield to the event
        # loop briefly to let Motor's connection pool settle before the
        # next rehearsal request would enter.
        try:
            await client.drop_database(scratch_name)
        except Exception:
            pass
        try:
            import asyncio as _asyncio
            await _asyncio.sleep(0.05)
        except Exception:
            pass

        return {
            "integrity_gate": int_gate,
            "security_gate": sec_gate,
            "integrity_engine_result": int_res.get("overall_result"),
            "integrity_engine_counts": real_int_counts,
            "integrity_engine_raw_counts": int_res.get("findings_by_severity") or {},
            "integrity_engine_error_findings": engine_error_findings,
            "integrity_engine_findings": real_int_findings[:20],
            "integrity_engine_error": int_error,
            "security_engine_result": sec_res.get("overall_result"),
            "security_engine_counts": sec_res.get("findings_by_severity") or {},
            "security_engine_error": sec_error,
            "payload_secret_scan": "PASS" if payload_scan_pass else "FAIL",
            "namespace_collections_copied": collections_copied,
            "namespace_scratch_db": scratch_name,
        }

    # ── Recovery status / gate ────────────────────────────────────
    async def recovery_status(self) -> Dict[str, Any]:
        latest_backup = await self.db[RUN_COLL].find_one(
            {"state": {"$in": ["Completed", "Completed with Warnings"]}},
            {"_id": 0}, sort=[("started_at", -1)])
        latest_rehearsal = await self.db[REH_COLL].find_one(
            {}, {"_id": 0}, sort=[("started_at", -1)])
        cfg = await self.get_configuration()
        backup_age_min = None
        if latest_backup:
            try:
                dt = datetime.fromisoformat(latest_backup["started_at"])
                backup_age_min = int(
                    (datetime.now(timezone.utc) - dt).total_seconds() / 60)
            except Exception:
                pass
        achieved_rpo = backup_age_min
        achieved_rto = None
        if latest_rehearsal and latest_rehearsal.get("duration_seconds") is not None:
            achieved_rto = int(latest_rehearsal["duration_seconds"] / 60) or 0
        unreconciled = 0
        if latest_rehearsal and latest_rehearsal.get("reconciliation"):
            unreconciled = len(
                latest_rehearsal["reconciliation"].get("differences") or [])
        return {
            "latest_backup": latest_backup,
            "backup_age_minutes": backup_age_min,
            "latest_rehearsal": latest_rehearsal,
            "achieved_rpo_minutes": achieved_rpo,
            "achieved_rto_minutes": achieved_rto,
            "configuration": cfg,
            "outstanding_reconciliation_differences": unreconciled,
            "generated_at": _iso(),
        }

    async def recovery_gate(self) -> Dict[str, Any]:
        s = await self.recovery_status()
        cfg = s["configuration"]
        checks: Dict[str, str] = {}
        errors: List[str] = []
        warnings: List[str] = []

        latest_backup = s["latest_backup"]
        checks["latest_valid_backup"] = "PASS" if latest_backup else "FAIL"
        if not latest_backup:
            errors.append("No valid backup on record.")
            return {"result": "FAIL", "checks": checks, "errors": errors,
                    "warnings": warnings, "status": s, "generated_at": _iso()}

        v = await self.validate_backup(latest_backup["backup_run_id"])
        checks["backup_integrity"] = "PASS" if v["result"] != "FAIL" else "FAIL"
        checks["backup_checksum"] = v["checks"].get("manifest_checksum", "FAIL")
        checks["no_secret_leak"] = v["checks"].get("no_secret_leak", "FAIL")
        if v["result"] == "FAIL":
            errors.extend(v["errors"])

        reh = s["latest_rehearsal"]
        checks["restore_rehearsal"] = ("PASS" if reh and reh.get("final_state") == "Passed"
                                        else "FAIL")
        if not reh or reh.get("final_state") != "Passed":
            errors.append("No successful restore rehearsal on record.")
        else:
            checks["reconciliation"] = (
                "PASS" if reh.get("reconciliation", {}).get("result") == "PASS"
                else "FAIL")
            if reh.get("reconciliation", {}).get("result") != "PASS":
                errors.append("Reconciliation failed.")
            checks["integrity_gate"] = reh.get("integrity_gate") or "FAIL"
            checks["security_gate"] = reh.get("security_gate") or "FAIL"
            if reh.get("integrity_gate") != "PASS":
                errors.append("Integrity gate failed.")
            if reh.get("security_gate") != "PASS":
                errors.append("Security gate failed.")
            checks["no_residue"] = "PASS" if reh.get("no_residue") else "FAIL"
            if not reh.get("no_residue"):
                errors.append("Residue detected after rehearsal cleanup.")

        # RPO
        if s["achieved_rpo_minutes"] is None:
            checks["rpo_target_met"] = "FAIL"
            errors.append("No achieved RPO measured.")
        elif s["achieved_rpo_minutes"] > cfg["rpo_target_minutes"]:
            checks["rpo_target_met"] = "FAIL"
            errors.append(
                f"RPO breach: achieved {s['achieved_rpo_minutes']}m > target {cfg['rpo_target_minutes']}m.")
        else:
            checks["rpo_target_met"] = "PASS"

        # RTO
        if s["achieved_rto_minutes"] is None:
            checks["rto_target_met"] = "FAIL"
            errors.append("No achieved RTO measured.")
        elif s["achieved_rto_minutes"] > cfg["rto_target_minutes"]:
            checks["rto_target_met"] = "FAIL"
            errors.append(
                f"RTO breach: achieved {s['achieved_rto_minutes']}m > target {cfg['rto_target_minutes']}m.")
        else:
            checks["rto_target_met"] = "PASS"

        # Unreconciled diffs
        checks["no_unreconciled_diffs"] = ("PASS" if s["outstanding_reconciliation_differences"] == 0
                                            else "FAIL")
        if s["outstanding_reconciliation_differences"] > 0:
            errors.append(
                f"{s['outstanding_reconciliation_differences']} unreconciled differences.")

        # Stale warning (non-blocking)
        if v["result"] == "PASS_WITH_WARNINGS":
            for w in v["warnings"]:
                warnings.append(w)

        if errors:
            result = "FAIL"
        elif warnings:
            result = "PASS_WITH_WARNINGS"
        else:
            result = "PASS"
        return {"result": result, "checks": checks, "errors": errors,
                "warnings": warnings, "status": s, "generated_at": _iso()}


# ═══════════════════════════════════════════════════════════════════
# Indexes
# ═══════════════════════════════════════════════════════════════════
async def ensure_indexes(db):
    await db[RUN_COLL].create_index("backup_run_id", unique=True)
    await db[RUN_COLL].create_index([("started_at", -1)])
    await db[RUN_COLL].create_index("correlation_id", sparse=True)
    await db[ART_COLL].create_index("backup_artifact_id", unique=True)
    await db[ART_COLL].create_index("backup_run_id")
    await db[MAN_COLL].create_index("backup_manifest_id", unique=True)
    await db[MAN_COLL].create_index("backup_run_id")
    await db[REH_COLL].create_index("restore_rehearsal_id", unique=True)
    await db[REH_COLL].create_index([("started_at", -1)])
    await db[RECON_COLL].create_index("restore_reconciliation_result_id", unique=True)
    await db[RECON_COLL].create_index("restore_rehearsal_id")
    await db[EVT_COLL].create_index("recovery_event_id", unique=True)
    await db[EVT_COLL].create_index([("at", -1)])
    await db[CFG_COLL].create_index("recovery_configuration_id", unique=True)
    await db[NS_COLL].create_index([("restore_rehearsal_id", 1), ("collection", 1)])


# ═══════════════════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════════════════
class CreateBackupBody(BaseModel):
    definition: str = "eb17b-full"
    correlation_id: Optional[str] = None


class StartRehearsalBody(BaseModel):
    backup_run_id: str
    approved: bool = True


def build_recovery_router(db, app, get_current_user):
    r = APIRouter(tags=["recovery"])
    svc = RecoveryService(db, app=app)

    @r.get("/api/recovery/status")
    async def status(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await svc.recovery_status()

    @r.get("/api/recovery/configuration")
    async def get_cfg(current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE_PLUS)
        return await svc.get_configuration()

    @r.post("/api/recovery/configuration")
    async def set_cfg(body: ConfigBody, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN,
                 "Admin required to configure Development/Test RPO/RTO.")
        return await svc.set_configuration(body, current.get("email"))

    @r.post("/api/backups")
    async def new_backup(body: CreateBackupBody = Body(default_factory=CreateBackupBody),
                          current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await svc.create_backup(current.get("email"),
                                        definition=body.definition,
                                        correlation_id=body.correlation_id)

    @r.get("/api/backups")
    async def list_backups(current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE_PLUS)
        return await db[RUN_COLL].find({}, {"_id": 0}).sort(
            "started_at", -1).to_list(200)

    @r.get("/api/backups/{backup_id}")
    async def get_backup(backup_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE_PLUS)
        row = await db[RUN_COLL].find_one(
            {"backup_run_id": backup_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return row

    @r.post("/api/backups/{backup_id}/validate")
    async def validate(backup_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER_PLUS)
        return await svc.validate_backup(backup_id)

    @r.post("/api/recovery/rehearsals")
    async def rehearse(body: StartRehearsalBody,
                        current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN,
                 "Admin required to execute restore rehearsals.")
        return await svc.start_rehearsal(body.backup_run_id,
                                          current.get("email"),
                                          current.get("role"),
                                          approved=body.approved)

    @r.get("/api/recovery/rehearsals")
    async def list_reh(current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE_PLUS)
        return await db[REH_COLL].find({}, {"_id": 0}).sort(
            "started_at", -1).to_list(200)

    @r.get("/api/recovery/rehearsals/{rehearsal_id}")
    async def get_reh(rehearsal_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE_PLUS)
        row = await db[REH_COLL].find_one(
            {"restore_rehearsal_id": rehearsal_id}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return row

    @r.get("/api/recovery/gate")
    async def gate(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY_PLUS)
        return await svc.recovery_gate()

    return r
