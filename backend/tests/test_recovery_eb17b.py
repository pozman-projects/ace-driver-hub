"""EB-17b · Backup / Restore / DR / RPO-RTO tests.

Deterministic. Local-only (http://localhost:8001/api). Fictional/sanitised.
No conditional skips.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import pytest
import requests
from pymongo import MongoClient

API = "http://localhost:8001/api"


def _login(email: str, password: str) -> Dict[str, str]:
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")


@pytest.fixture(scope="module")
def readonly_headers():
    return _login("readonly.qa@acedriverhub.com", "ReadOnly@123")


@pytest.fixture(scope="module")
def manager_headers(admin_headers):
    email = f"eb17b.mgr.{uuid.uuid4().hex[:8]}@acedriverhub.com"
    requests.post(f"{API}/auth/register", headers=admin_headers, json={
        "email": email, "password": "Manager@123",
        "full_name": "EB17b Mgr", "role": "Manager"}, timeout=30).raise_for_status()
    return _login(email, "Manager@123")


@pytest.fixture(scope="module")
def compliance_headers(admin_headers):
    email = f"eb17b.comp.{uuid.uuid4().hex[:8]}@acedriverhub.com"
    requests.post(f"{API}/auth/register", headers=admin_headers, json={
        "email": email, "password": "Compliance@123",
        "full_name": "EB17b Comp", "role": "Compliance"}, timeout=30).raise_for_status()
    return _login(email, "Compliance@123")


@pytest.fixture(autouse=True)
def _clean_eb17b_state():
    """Purge fictional EB-17b rows from every live collection so each test
    starts from a known baseline. NO writes to non-fictional rows.

    Cleans on entry AND on exit so other test files aren't polluted by
    leftover seed-eb17b rows in shared collections (drivers, owners, ...)."""
    d = _db()
    from recovery_module import (
        DOMAIN_COLLECTIONS, DEF_COLL, RUN_COLL, ART_COLL, MAN_COLL,
        REH_COLL, RECON_COLL, EVT_COLL, CFG_COLL, NS_COLL,
    )
    def _wipe():
        for _domain, colls in DOMAIN_COLLECTIONS.items():
            for c in colls:
                try:
                    d[c].delete_many({"_source": "seed-eb17b"})
                except Exception:
                    pass
        for c in (DEF_COLL, RUN_COLL, ART_COLL, MAN_COLL,
                  REH_COLL, RECON_COLL, EVT_COLL, NS_COLL):
            try:
                d[c].delete_many({"_source": "seed-eb17b"})
            except Exception:
                pass
    _wipe()
    yield
    _wipe()


def _seed_fictional_state(db_):
    """Insert a small deterministic fictional dataset into live collections
    tagged _source=seed-eb17b. Includes drivers, owners, a relationship, a
    document with matching storage_object, an audit event, and an activation
    record."""
    d1_id, d2_id, o1_id = _uuid_short(), _uuid_short(), _uuid_short()
    db_["drivers"].insert_many([
        {"id": d1_id, "name": "Fictional Driver 1", "_source": "seed-eb17b"},
        {"id": d2_id, "name": "Fictional Driver 2", "_source": "seed-eb17b"},
    ])
    db_["owners"].insert_one({"id": o1_id, "name": "Fictional Owner", "_source": "seed-eb17b"})
    db_["driver_owner_relationships"].insert_one({
        "id": _uuid_short(), "driver_id": d1_id, "owner_id": o1_id, "_source": "seed-eb17b"})
    storage_key = f"fictional/{_uuid_short()}"
    db_["documents"].insert_one({
        "id": _uuid_short(), "title": "Fictional Doc", "storage_key": storage_key,
        "_source": "seed-eb17b"})
    db_["storage_objects"].insert_one({
        "id": _uuid_short(), "storage_key": storage_key, "_source": "seed-eb17b"})
    db_["driver_activation_records"].insert_one({
        "driver_activation_id": _uuid_short(), "driver_id": d1_id,
        "status": "In Progress", "_source": "seed-eb17b"})
    db_["security_assessment_events"].insert_one({
        "security_assessment_event_id": _uuid_short(),
        "id": _uuid_short(), "event_type": "eb17b.audit", "at": _iso(),
        "_source": "seed-eb17b"})
    return {"driver_ids": [d1_id, d2_id], "owner_id": o1_id, "storage_key": storage_key}


def _uuid_short():
    return str(uuid.uuid4())


def _iso():
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════
# PART 1 & 2 — Backup framework & integrity
# ═══════════════════════════════════════════════════════════════════
class TestBackupFramework:
    def test_backup_creates_manifest_and_artifacts(self, admin_headers):
        _seed_fictional_state(_db())
        r = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert body["state"] in ("Completed", "Completed with Warnings")
        assert body["manifest_checksum"]
        assert body["artifact_count"] >= 1
        assert body["fictional_test_marker"] is True

    def test_backup_idempotent_by_correlation_id(self, admin_headers):
        _seed_fictional_state(_db())
        corr = f"eb17b-{uuid.uuid4()}"
        r1 = requests.post(f"{API}/backups", headers=admin_headers,
                           json={"correlation_id": corr}, timeout=60)
        r2 = requests.post(f"{API}/backups", headers=admin_headers,
                           json={"correlation_id": corr}, timeout=60)
        assert r1.json()["backup_run_id"] == r2.json()["backup_run_id"]

    def test_backup_lists_and_gets(self, admin_headers):
        _seed_fictional_state(_db())
        run = requests.post(f"{API}/backups", headers=admin_headers,
                            json={}, timeout=60).json()
        lst = requests.get(f"{API}/backups", headers=admin_headers, timeout=30).json()
        assert any(x["backup_run_id"] == run["backup_run_id"] for x in lst)
        one = requests.get(f"{API}/backups/{run['backup_run_id']}",
                           headers=admin_headers, timeout=30).json()
        assert one["backup_run_id"] == run["backup_run_id"]


class TestBackupIntegrity:
    def _backup(self, admin_headers):
        _seed_fictional_state(_db())
        return requests.post(f"{API}/backups", headers=admin_headers,
                             json={}, timeout=60).json()

    def test_valid_backup_passes(self, admin_headers):
        b = self._backup(admin_headers)
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["result"] in ("PASS", "PASS_WITH_WARNINGS")
        for k in ("manifest_present", "manifest_checksum",
                  "no_missing_artifact", "no_duplicate_artifact",
                  "artifact_checksum", "record_count_match", "no_secret_leak"):
            assert v["checks"][k] == "PASS", f"{k} not PASS"

    def test_checksum_mismatch_detected(self, admin_headers):
        b = self._backup(admin_headers)
        # Corrupt an artifact payload
        d = _db()
        art = d["backup_artifacts"].find_one({"backup_run_id": b["backup_run_id"]})
        d["backup_artifacts"].update_one(
            {"backup_artifact_id": art["backup_artifact_id"]},
            {"$set": {"payload": [{"id": "tampered"}]}},
        )
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["result"] == "FAIL"
        assert v["checks"]["artifact_checksum"] == "FAIL"

    def test_missing_artifact_detected(self, admin_headers):
        b = self._backup(admin_headers)
        d = _db()
        d["backup_artifacts"].delete_one({"backup_run_id": b["backup_run_id"]})
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["result"] == "FAIL"
        assert v["checks"]["no_missing_artifact"] == "FAIL"

    def test_malformed_manifest_detected(self, admin_headers):
        b = self._backup(admin_headers)
        d = _db()
        d["backup_manifests"].update_one(
            {"backup_run_id": b["backup_run_id"]},
            {"$set": {"manifest.schema_version": "bogus"}},
        )
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["result"] == "FAIL"
        assert v["checks"]["schema_version"] == "FAIL"

    def test_manifest_checksum_tamper_detected(self, admin_headers):
        b = self._backup(admin_headers)
        d = _db()
        d["backup_manifests"].update_one(
            {"backup_run_id": b["backup_run_id"]},
            {"$set": {"manifest.environment": "tampered"}},
        )
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["checks"]["manifest_checksum"] == "FAIL"

    def test_secret_leak_prevented_at_snapshot(self, admin_headers):
        d = _db()
        _seed_fictional_state(d)
        d["drivers"].insert_one({"id": _uuid_short(), "name": "Bad",
                                  "api_key": "verysecretlongvalue123",
                                  "_source": "seed-eb17b"})
        r = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60)
        # Snapshot refuses; the run doc is Failed with reason
        body = r.json()
        assert body["state"] == "Failed"
        assert "Secret" in (body.get("failure_reason") or "")

    def test_failed_backup_not_recoverable(self, admin_headers):
        b = self._backup(admin_headers)
        # Simulate downgrade to Failed state, then re-validate → FAIL
        _db()["backup_runs"].update_one(
            {"backup_run_id": b["backup_run_id"]},
            {"$set": {"state": "Failed"}})
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["result"] == "FAIL"
        assert v["checks"]["not_failed"] == "FAIL"

    def test_cancelled_backup_not_valid(self, admin_headers):
        b = self._backup(admin_headers)
        _db()["backup_runs"].update_one(
            {"backup_run_id": b["backup_run_id"]},
            {"$set": {"state": "Cancelled"}})
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["result"] == "FAIL"
        assert v["checks"]["not_cancelled"] == "FAIL"


# ═══════════════════════════════════════════════════════════════════
# PART 3, 4, 5 — Restore + DR rehearsal + failure scenarios
# ═══════════════════════════════════════════════════════════════════
class TestRestoreAndDRRehearsal:
    def _clean_backup(self, admin_headers):
        _seed_fictional_state(_db())
        return requests.post(f"{API}/backups", headers=admin_headers,
                             json={}, timeout=60).json()

    def test_full_dr_rehearsal_pass(self, admin_headers):
        b = self._clean_backup(admin_headers)
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=120).json()
        assert r["final_state"] == "Passed", r
        assert r["reconciliation"]["result"] == "PASS"
        assert r["integrity_gate"] == "PASS"
        assert r["security_gate"] == "PASS"
        assert r["no_residue"] is True
        assert r["approved"] is True
        # Source system unchanged: live collections still contain
        # exactly the fictional rows we inserted, unchanged.
        d = _db()
        assert d["restore_namespace_data"].count_documents(
            {"restore_rehearsal_id": r["restore_rehearsal_id"]}) == 0

    def test_restore_without_approval_rejected(self, admin_headers):
        b = self._clean_backup(admin_headers)
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": False}, timeout=30)
        assert r.status_code == 400

    def test_restore_from_failed_backup(self, admin_headers):
        b = self._clean_backup(admin_headers)
        _db()["backup_runs"].update_one(
            {"backup_run_id": b["backup_run_id"]},
            {"$set": {"state": "Failed"}})
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=60).json()
        assert r["final_state"] == "Failed"
        assert any("validation" in e.lower() for e in r["errors"])

    def test_record_count_mismatch(self, admin_headers):
        b = self._clean_backup(admin_headers)
        # Tamper: add row to an artifact payload so record_count now differs
        d = _db()
        art = d["backup_artifacts"].find_one({"backup_run_id": b["backup_run_id"]})
        payload = list(art.get("payload") or [])
        payload.append({"id": "bogus", "_source": "seed-eb17b"})
        d["backup_artifacts"].update_one(
            {"backup_artifact_id": art["backup_artifact_id"]},
            {"$set": {"payload": payload}})
        v = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=admin_headers, timeout=30).json()
        assert v["checks"]["record_count_match"] == "FAIL"

    def test_orphan_relationship_after_restore(self, admin_headers):
        d = _db()
        d["driver_owner_relationships"].insert_one({
            "id": _uuid_short(),
            "driver_id": "does-not-exist",
            "owner_id": _uuid_short(),
            "_source": "seed-eb17b",
        })
        b = self._clean_backup(admin_headers)
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=120).json()
        assert r["reconciliation"]["result"] == "FAIL"
        kinds = {diff.get("kind") for diff in r["reconciliation"]["differences"]}
        assert "relationships" in kinds

    def test_document_storage_mismatch(self, admin_headers):
        d = _db()
        _seed_fictional_state(d)
        # Add a document referencing a storage_key with NO storage_object row
        d["documents"].insert_one({
            "id": _uuid_short(), "title": "Orphan Doc",
            "storage_key": "fictional/missing-key",
            "_source": "seed-eb17b",
        })
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=120).json()
        assert r["reconciliation"]["result"] == "FAIL"
        kinds = {diff.get("kind") for diff in r["reconciliation"]["differences"]}
        assert "storage_inventory" in kinds

    def test_rehearsal_cleans_up_no_residue(self, admin_headers):
        b = self._clean_backup(admin_headers)
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=120).json()
        d = _db()
        assert d["restore_namespace_data"].count_documents(
            {"restore_rehearsal_id": r["restore_rehearsal_id"]}) == 0
        assert r["no_residue"] is True


# ═══════════════════════════════════════════════════════════════════
# PART 6 — RPO / RTO
# ═══════════════════════════════════════════════════════════════════
class TestRpoRto:
    def test_configuration_defaults(self, admin_headers):
        r = requests.get(f"{API}/recovery/configuration",
                         headers=admin_headers, timeout=30).json()
        assert r["production_approved"] is False
        assert "NOT PRODUCTION APPROVED" in r["label"]
        assert r["rpo_target_minutes"] > 0
        assert r["rto_target_minutes"] > 0

    def test_config_production_blocked(self, admin_headers):
        r = requests.post(f"{API}/recovery/configuration",
                          headers=admin_headers,
                          json={"environment": "Production",
                                "rpo_target_minutes": 15,
                                "rto_target_minutes": 30,
                                "backup_age_warning_hours": 1}, timeout=30)
        assert r.status_code == 403

    def test_config_update_dev(self, admin_headers):
        r = requests.post(f"{API}/recovery/configuration",
                          headers=admin_headers,
                          json={"environment": "Development",
                                "rpo_target_minutes": 120,
                                "rto_target_minutes": 60,
                                "backup_age_warning_hours": 24}, timeout=30).json()
        assert r["rpo_target_minutes"] == 120
        assert r["production_approved"] is False

    def test_rpo_pass_and_fail(self, admin_headers):
        # PASS: fresh backup, generous RPO
        requests.post(f"{API}/recovery/configuration", headers=admin_headers,
                      json={"environment": "Development",
                            "rpo_target_minutes": 100000,
                            "rto_target_minutes": 100000,
                            "backup_age_warning_hours": 24},
                      timeout=30).raise_for_status()
        _seed_fictional_state(_db())
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        # Need a rehearsal so gate can measure RTO
        requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                      json={"backup_run_id": b["backup_run_id"],
                            "approved": True}, timeout=120).raise_for_status()
        g = requests.get(f"{API}/recovery/gate", headers=admin_headers,
                         timeout=30).json()
        assert g["checks"]["rpo_target_met"] == "PASS"
        assert g["checks"]["rto_target_met"] == "PASS"
        # FAIL: back-date backup + rehearsal
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _db()["backup_runs"].update_one(
            {"backup_run_id": b["backup_run_id"]},
            {"$set": {"started_at": past}})
        requests.post(f"{API}/recovery/configuration", headers=admin_headers,
                      json={"environment": "Development",
                            "rpo_target_minutes": 60,
                            "rto_target_minutes": 100000,
                            "backup_age_warning_hours": 1},
                      timeout=30).raise_for_status()
        g2 = requests.get(f"{API}/recovery/gate", headers=admin_headers,
                          timeout=30).json()
        assert g2["checks"]["rpo_target_met"] == "FAIL"

    def test_rto_fail(self, admin_headers):
        _seed_fictional_state(_db())
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        reh = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                            json={"backup_run_id": b["backup_run_id"],
                                  "approved": True}, timeout=120).json()
        # Inflate duration
        _db()["restore_rehearsals"].update_one(
            {"restore_rehearsal_id": reh["restore_rehearsal_id"]},
            {"$set": {"duration_seconds": 9999999}})
        requests.post(f"{API}/recovery/configuration", headers=admin_headers,
                      json={"environment": "Development",
                            "rpo_target_minutes": 100000,
                            "rto_target_minutes": 1,
                            "backup_age_warning_hours": 240},
                      timeout=30).raise_for_status()
        g = requests.get(f"{API}/recovery/gate", headers=admin_headers,
                         timeout=30).json()
        assert g["checks"]["rto_target_met"] == "FAIL"


# ═══════════════════════════════════════════════════════════════════
# PART 7 — Recovery gate
# ═══════════════════════════════════════════════════════════════════
class TestRecoveryGate:
    def test_gate_fail_without_any_backup(self, admin_headers):
        g = requests.get(f"{API}/recovery/gate", headers=admin_headers,
                         timeout=30).json()
        assert g["result"] == "FAIL"
        assert g["checks"]["latest_valid_backup"] == "FAIL"

    def test_gate_pass_after_full_dr(self, admin_headers):
        requests.post(f"{API}/recovery/configuration", headers=admin_headers,
                      json={"environment": "Development",
                            "rpo_target_minutes": 100000,
                            "rto_target_minutes": 100000,
                            "backup_age_warning_hours": 240},
                      timeout=30).raise_for_status()
        _seed_fictional_state(_db())
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                      json={"backup_run_id": b["backup_run_id"],
                            "approved": True}, timeout=120).raise_for_status()
        g = requests.get(f"{API}/recovery/gate", headers=admin_headers,
                         timeout=30).json()
        assert g["result"] in ("PASS", "PASS_WITH_WARNINGS"), g

    def test_gate_pass_with_warnings_on_stale_backup(self, admin_headers):
        _seed_fictional_state(_db())
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                      json={"backup_run_id": b["backup_run_id"],
                            "approved": True}, timeout=120).raise_for_status()
        # backup age > warning threshold, still under RPO
        past = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        _db()["backup_runs"].update_one(
            {"backup_run_id": b["backup_run_id"]},
            {"$set": {"started_at": past}})
        requests.post(f"{API}/recovery/configuration", headers=admin_headers,
                      json={"environment": "Development",
                            "rpo_target_minutes": 100000,
                            "rto_target_minutes": 100000,
                            "backup_age_warning_hours": 1},
                      timeout=30).raise_for_status()
        g = requests.get(f"{API}/recovery/gate", headers=admin_headers,
                         timeout=30).json()
        assert g["result"] == "PASS_WITH_WARNINGS", g

    def test_gate_fail_on_reconciliation_break(self, admin_headers):
        d = _db()
        d["driver_owner_relationships"].insert_one({
            "id": _uuid_short(),
            "driver_id": "orphan-eb17b",
            "owner_id": "orphan-eb17b-o",
            "_source": "seed-eb17b",
        })
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                      json={"backup_run_id": b["backup_run_id"],
                            "approved": True}, timeout=120).raise_for_status()
        g = requests.get(f"{API}/recovery/gate", headers=admin_headers,
                         timeout=30).json()
        assert g["result"] == "FAIL"


# ═══════════════════════════════════════════════════════════════════
# PART 9 — Permissions / RBAC
# ═══════════════════════════════════════════════════════════════════
class TestRBAC:
    def test_readonly_cannot_create_backup(self, readonly_headers):
        r = requests.post(f"{API}/backups", headers=readonly_headers,
                          json={}, timeout=30)
        assert r.status_code == 403

    def test_readonly_can_view_status(self, readonly_headers):
        r = requests.get(f"{API}/recovery/status", headers=readonly_headers,
                         timeout=30)
        assert r.status_code == 200

    def test_readonly_cannot_view_config(self, readonly_headers):
        r = requests.get(f"{API}/recovery/configuration",
                         headers=readonly_headers, timeout=30)
        assert r.status_code == 403

    def test_compliance_can_view_backups_but_not_mutate(self, compliance_headers):
        r = requests.get(f"{API}/backups", headers=compliance_headers, timeout=30)
        assert r.status_code == 200
        r2 = requests.post(f"{API}/backups", headers=compliance_headers,
                           json={}, timeout=30)
        assert r2.status_code == 403

    def test_manager_can_validate_not_create(self, manager_headers, admin_headers):
        _seed_fictional_state(_db())
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        r = requests.post(f"{API}/backups/{b['backup_run_id']}/validate",
                          headers=manager_headers, timeout=30)
        assert r.status_code == 200
        r2 = requests.post(f"{API}/backups", headers=manager_headers,
                           json={}, timeout=30)
        assert r2.status_code == 403

    def test_manager_cannot_execute_rehearsal(self, manager_headers, admin_headers):
        _seed_fictional_state(_db())
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        r = requests.post(f"{API}/recovery/rehearsals",
                          headers=manager_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=30)
        assert r.status_code == 403

    def test_manager_cannot_configure(self, manager_headers):
        r = requests.post(f"{API}/recovery/configuration",
                          headers=manager_headers,
                          json={"environment": "Development",
                                "rpo_target_minutes": 60,
                                "rto_target_minutes": 30,
                                "backup_age_warning_hours": 6},
                          timeout=30)
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════
# PART 10 — Real EB-16 Integrity + EB-17a Security engines against
# the isolated scratch namespace (no proxy/mock checks)
# ═══════════════════════════════════════════════════════════════════
class TestRealNamespaceEngines:
    def _clean_backup(self, admin_headers):
        _seed_fictional_state(_db())
        return requests.post(f"{API}/backups", headers=admin_headers,
                             json={}, timeout=60).json()

    def test_clean_rehearsal_real_engines_pass(self, admin_headers):
        """Clean fictional dataset → both real engines PASS. Rehearsal
        record must include engine result payloads and the scratch DB
        name proving isolation."""
        b = self._clean_backup(admin_headers)
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=180).json()
        assert r["final_state"] == "Passed", r
        assert r["integrity_gate"] == "PASS"
        assert r["security_gate"] == "PASS"
        # Engine payloads must be populated — proves real engines ran
        assert "integrity_engine_counts" in r
        assert "security_engine_counts" in r
        assert r.get("security_engine_result") in ("PASS", "PASS_WITH_WARNINGS")
        # Scratch DB isolation — must have been named and dropped
        assert r.get("namespace_scratch_db")
        assert r.get("namespace_scratch_db") != _db().name
        # Confirm scratch DB was dropped by mongo client
        client = MongoClient(os.environ["MONGO_URL"])
        assert r["namespace_scratch_db"] not in client.list_database_names()

    def test_security_defect_seeded_in_namespace_fails_security_gate(
        self, admin_headers,
    ):
        """Seed a security_assessment_events row with the mutation marker
        `updated_at` set — the EB-17a `audit.security_events_immutable`
        Critical rule will trigger inside the scratch namespace and force
        security_gate = FAIL. Live DB security posture is untouched."""
        d = _db()
        d["security_assessment_events"].insert_one({
            "security_assessment_event_id": _uuid_short(),
            "id": _uuid_short(),
            "event_type": "eb17b.tampered",
            "at": _iso(),
            "updated_at": _iso(),  # violates immutability rule
            "_source": "seed-eb17b",
        })
        b = self._clean_backup(admin_headers)
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=180).json()
        # Security gate FAIL; other gates untouched
        assert r["security_gate"] == "FAIL", r
        assert r["final_state"] == "Failed"
        # Engine actually flagged Critical
        counts = r.get("security_engine_counts") or {}
        assert counts.get("Critical", 0) >= 1, r

    def test_integrity_defect_seeded_in_namespace_fails_integrity_gate(
        self, admin_headers,
    ):
        """Seed two drivers with the same driver_code in the fictional
        seed → the EB-16 `_reg_duplicate_driver_code` rule (Critical
        severity) will trigger inside the scratch namespace and force
        integrity_gate = FAIL."""
        d = _db()
        _seed_fictional_state(d)
        shared_code = 999999
        d["drivers"].insert_many([
            {"id": _uuid_short(), "name": "DupCode A",
             "driver_code": shared_code, "_source": "seed-eb17b"},
            {"id": _uuid_short(), "name": "DupCode B",
             "driver_code": shared_code, "_source": "seed-eb17b"},
        ])
        b = requests.post(f"{API}/backups", headers=admin_headers,
                          json={}, timeout=60).json()
        r = requests.post(f"{API}/recovery/rehearsals", headers=admin_headers,
                          json={"backup_run_id": b["backup_run_id"],
                                "approved": True}, timeout=180).json()
        assert r["integrity_gate"] == "FAIL", r
        assert r["final_state"] == "Failed"
        counts = r.get("integrity_engine_counts") or {}
        # Duplicate driver_code is severity Critical in the EB-16 catalogue
        assert (counts.get("Error", 0) + counts.get("Critical", 0)) >= 1, r

    def test_live_db_state_does_not_contaminate_rehearsal(self, admin_headers):
        """Live/dev security_assessment_events rows without _source tag
        must NOT flow into the scratch namespace and must NOT cause the
        namespace-scoped security gate to FAIL. Proves the rehearsal
        runs against the isolated copy, not the live DB."""
        d = _db()
        # Inject a tampered event OUTSIDE the fictional _source scope.
        # This must NEVER be picked up because backup snapshot only
        # captures rows tagged _source=seed-eb17b.
        contaminant_id = _uuid_short()
        d["security_assessment_events"].insert_one({
            "security_assessment_event_id": _uuid_short(),
            "id": contaminant_id,
            "event_type": "live.contaminant",
            "at": _iso(),
            "updated_at": _iso(),  # would fail immutability if seen
            "_source": "live-not-eb17b",
        })
        try:
            b = self._clean_backup(admin_headers)
            r = requests.post(f"{API}/recovery/rehearsals",
                              headers=admin_headers,
                              json={"backup_run_id": b["backup_run_id"],
                                    "approved": True}, timeout=180).json()
            assert r["security_gate"] == "PASS", r
            assert r["final_state"] == "Passed"
        finally:
            d["security_assessment_events"].delete_one({"id": contaminant_id})
