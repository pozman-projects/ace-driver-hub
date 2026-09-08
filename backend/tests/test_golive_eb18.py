"""EB-18 — Controlled Go-Live framework tests. Local-only. No live network."""
from __future__ import annotations
import os
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API = "http://localhost:8001/api"


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, pw):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_headers(): return _login("admin@acedriverhub.com", "Admin@123")
@pytest.fixture(scope="module")
def ro_headers(): return _login("readonly.qa@acedriverhub.com", "ReadOnly@123")


@pytest.fixture(autouse=True)
def _wipe():
    d = _db()
    from golive_module import (RUN_C, STEP_C, EVT_C, APR_C, ABORT_C,
                                 MON_C, EVID_C, DEC_C, PRE_C, AUTH_C)
    for c in (RUN_C, STEP_C, EVT_C, APR_C, ABORT_C, MON_C, EVID_C, DEC_C,
               PRE_C, AUTH_C):
        try: d[c].delete_many({"_source": "seed-eb18"})
        except Exception: pass
    yield
    for c in (RUN_C, STEP_C, EVT_C, APR_C, ABORT_C, MON_C, EVID_C, DEC_C,
               PRE_C, AUTH_C):
        try: d[c].delete_many({"_source": "seed-eb18"})
        except Exception: pass


def _create_run(headers, mode="DRY_RUN"):
    return requests.post(f"{API}/go-live/runs", headers=headers,
                          json={"mode": mode}, timeout=15).json()


def _approve_all(headers, rid, production_mode=False):
    for layer in ("Business", "Technical", "Security", "Release"):
        requests.post(f"{API}/go-live/runs/{rid}/approve", headers=headers,
                       json={"approver": "admin", "approval_layer": layer,
                              "production_mode_explicit_marker": production_mode},
                       timeout=15).raise_for_status()


# ─── PART 1 — prerequisites ─────────────────────────────────────
class TestPrerequisites:
    def test_prereq_snapshot(self, admin_headers):
        r = requests.get(f"{API}/go-live/prerequisites",
                          headers=admin_headers, timeout=15).json()
        assert r["state"] in ("PASS", "CONDITIONAL", "BLOCKED")
        assert "prerequisite_snapshot_id" in r


# ─── PART 2 — run lifecycle ─────────────────────────────────────
class TestRunLifecycle:
    def test_create_run_seeds_all_steps(self, admin_headers):
        r = _create_run(admin_headers)
        assert r["status"] == "Draft"
        assert r["execution_mode"] == "DRY_RUN"
        got = requests.get(f"{API}/go-live/runs/{r['go_live_run_id']}",
                            headers=admin_headers, timeout=15).json()
        assert len([s for s in got["steps"] if s["kind"] == "cutover"]) == 33
        assert len([s for s in got["steps"] if s["kind"] == "rollback"]) == 18

    def test_start_denied_without_approval(self, admin_headers):
        r = _create_run(admin_headers)
        r2 = requests.post(f"{API}/go-live/runs/{r['go_live_run_id']}/start",
                            headers=admin_headers, timeout=15)
        assert r2.status_code == 400

    def test_approve_then_start(self, admin_headers):
        r = _create_run(admin_headers)
        _approve_all(admin_headers, r["go_live_run_id"])
        started = requests.post(f"{API}/go-live/runs/{r['go_live_run_id']}/start",
                                 headers=admin_headers, timeout=15).json()
        assert started["status"] == "Running"

    def test_production_denied_without_marker(self, admin_headers):
        r = _create_run(admin_headers, mode="PRODUCTION")
        _approve_all(admin_headers, r["go_live_run_id"], production_mode=False)
        r2 = requests.post(f"{API}/go-live/runs/{r['go_live_run_id']}/start",
                            headers=admin_headers, timeout=15)
        assert r2.status_code == 400
        assert "production" in r2.text.lower()


# ─── PART 3 — migration authorisation ───────────────────────────
class TestMigrationAuth:
    def _body(self, **overrides):
        base = {
            "workbook_identified": True,
            "workbook_checksum": "sha256-fictional",
            "workbook_owner": "ops",
            "import_scope_approved": True, "mapping_approved": True,
            "dry_run_completed": True, "issues_resolved": True,
            "go_decision": "GO", "commit_pkg_checksum": "sha256-fictional-2",
            "rollback_pkg_generated": True, "rollback_pkg_validated": True,
            "operators_assigned": ["op1"], "final_approval": True,
            "explicit_real_data_marker": True,
        }
        base.update(overrides); return base

    def test_no_go_yields_not_authorised(self, admin_headers):
        r = requests.post(f"{API}/go-live/migration-authorisation",
                          headers=admin_headers,
                          json=self._body(go_decision="NO_GO"), timeout=15).json()
        assert r["status"] == "NOT_AUTHORISED"

    def test_full_yields_authorised(self, admin_headers):
        r = requests.post(f"{API}/go-live/migration-authorisation",
                          headers=admin_headers,
                          json=self._body(), timeout=15).json()
        assert r["status"] == "AUTHORISED"

    def test_missing_marker_yields_ready_for_approval(self, admin_headers):
        r = requests.post(f"{API}/go-live/migration-authorisation",
                          headers=admin_headers,
                          json=self._body(explicit_real_data_marker=False),
                          timeout=15).json()
        assert r["status"] == "READY_FOR_APPROVAL"

    def test_revoke(self, admin_headers):
        r = requests.post(f"{API}/go-live/migration-authorisation",
                          headers=admin_headers,
                          json=self._body(), timeout=15).json()
        rv = requests.post(f"{API}/go-live/migration-authorisation/revoke",
                            headers=admin_headers,
                            json={"auth_id": r["go_live_migration_authorisation_id"]},
                            timeout=15).json()
        assert rv["status"] == "REVOKED"


# ─── PART 4 — cutover step + abort + rollback ───────────────────
class TestCutoverAndAbort:
    def _run(self, headers):
        r = _create_run(headers); _approve_all(headers, r["go_live_run_id"])
        requests.post(f"{API}/go-live/runs/{r['go_live_run_id']}/start",
                       headers=headers, timeout=15).raise_for_status()
        return r["go_live_run_id"]

    def test_step_completed(self, admin_headers):
        rid = self._run(admin_headers)
        detail = requests.get(f"{API}/go-live/runs/{rid}",
                               headers=admin_headers, timeout=15).json()
        step = [s for s in detail["steps"] if s["step_key"] == "freeze_change"][0]
        r = requests.post(
            f"{API}/go-live/runs/{rid}/steps/{step['go_live_step_id']}/complete",
            headers=admin_headers,
            json={"result": "Passed", "operator": "admin"},
            timeout=15).json()
        assert r["status"] == "Running"

    def test_critical_step_skip_requires_reason(self, admin_headers):
        rid = self._run(admin_headers)
        detail = requests.get(f"{API}/go-live/runs/{rid}",
                               headers=admin_headers, timeout=15).json()
        step = [s for s in detail["steps"] if s["step_key"] == "freeze_change"][0]
        r = requests.post(
            f"{API}/go-live/runs/{rid}/steps/{step['go_live_step_id']}/complete",
            headers=admin_headers,
            json={"result": "Skipped", "operator": "admin"}, timeout=15)
        assert r.status_code == 400

    def test_abort_stops_pending_steps(self, admin_headers):
        rid = self._run(admin_headers)
        r = requests.post(f"{API}/go-live/runs/{rid}/abort", headers=admin_headers,
                          json={"reason": "integrity_fail",
                                 "authority": "Head of Engineering"},
                          timeout=15).json()
        assert r["status"] == "Aborted"
        detail = requests.get(f"{API}/go-live/runs/{rid}",
                               headers=admin_headers, timeout=15).json()
        pending = [s for s in detail["steps"]
                    if s["kind"] == "cutover" and s["status"] == "Pending"]
        blocked = [s for s in detail["steps"]
                    if s["kind"] == "cutover" and s["status"] == "Blocked"]
        assert pending == [] and blocked  # all cutover pending → blocked

    def test_integrity_fail_abort_reason(self, admin_headers):
        rid = self._run(admin_headers)
        requests.post(f"{API}/go-live/runs/{rid}/abort", headers=admin_headers,
                       json={"reason": "integrity_fail",
                              "authority": "Head of Engineering"},
                       timeout=15).raise_for_status()
        # No further step can be completed
        detail = requests.get(f"{API}/go-live/runs/{rid}",
                               headers=admin_headers, timeout=15).json()
        step = detail["steps"][0]
        r = requests.post(
            f"{API}/go-live/runs/{rid}/steps/{step['go_live_step_id']}/complete",
            headers=admin_headers,
            json={"result": "Passed", "operator": "x"}, timeout=15)
        assert r.status_code == 400

    def test_rollback_after_abort(self, admin_headers):
        rid = self._run(admin_headers)
        requests.post(f"{API}/go-live/runs/{rid}/abort", headers=admin_headers,
                       json={"reason": "security_fail", "authority": "Sec"},
                       timeout=15).raise_for_status()
        r = requests.post(f"{API}/go-live/runs/{rid}/rollback",
                          headers=admin_headers, timeout=15).json()
        assert r["status"] == "Rolled Back"


# ─── PART 5 — monitoring ────────────────────────────────────────
class TestMonitoring:
    def _run(self, headers):
        r = _create_run(headers); _approve_all(headers, r["go_live_run_id"])
        requests.post(f"{API}/go-live/runs/{r['go_live_run_id']}/start",
                       headers=headers, timeout=15).raise_for_status()
        return r["go_live_run_id"]

    def test_healthy(self, admin_headers):
        rid = self._run(admin_headers)
        r = requests.post(f"{API}/go-live/runs/{rid}/monitoring",
                          headers=admin_headers, json={}, timeout=15).json()
        assert r["overall_state"] == "Healthy"

    def test_warning(self, admin_headers):
        rid = self._run(admin_headers)
        r = requests.post(f"{API}/go-live/runs/{rid}/monitoring",
                          headers=admin_headers,
                          json={"failed_jobs": 1}, timeout=15).json()
        assert r["overall_state"] == "Warning"

    def test_critical(self, admin_headers):
        rid = self._run(admin_headers)
        r = requests.post(f"{API}/go-live/runs/{rid}/monitoring",
                          headers=admin_headers,
                          json={"integrity_findings": 3}, timeout=15).json()
        assert r["overall_state"] == "Critical"


# ─── PART 6 — release decision ──────────────────────────────────
class TestReleaseDecision:
    def _finish_run(self, headers, monitoring):
        r = _create_run(headers); rid = r["go_live_run_id"]
        _approve_all(headers, rid)
        requests.post(f"{API}/go-live/runs/{rid}/start",
                       headers=headers, timeout=15).raise_for_status()
        detail = requests.get(f"{API}/go-live/runs/{rid}",
                               headers=headers, timeout=15).json()
        for s in detail["steps"]:
            if s["kind"] != "cutover" or not s["critical"]: continue
            requests.post(
                f"{API}/go-live/runs/{rid}/steps/{s['go_live_step_id']}/complete",
                headers=headers,
                json={"result": "Passed", "operator": "admin"},
                timeout=15).raise_for_status()
        requests.post(f"{API}/go-live/runs/{rid}/monitoring",
                       headers=headers, json=monitoring, timeout=15)
        return rid

    def test_released(self, admin_headers):
        rid = self._finish_run(admin_headers, {})
        r = requests.get(f"{API}/go-live/release-decision?rid={rid}",
                          headers=admin_headers, timeout=15).json()
        assert r["result"] == "RELEASED", r

    def test_released_with_conditions(self, admin_headers):
        rid = self._finish_run(admin_headers, {"failed_jobs": 1})
        r = requests.get(f"{API}/go-live/release-decision?rid={rid}",
                          headers=admin_headers, timeout=15).json()
        assert r["result"] == "RELEASED_WITH_CONDITIONS", r

    def test_aborted_decision(self, admin_headers):
        r = _create_run(admin_headers); rid = r["go_live_run_id"]
        _approve_all(admin_headers, rid)
        requests.post(f"{API}/go-live/runs/{rid}/start", headers=admin_headers,
                       timeout=15).raise_for_status()
        requests.post(f"{API}/go-live/runs/{rid}/abort", headers=admin_headers,
                       json={"reason": "recovery_fail", "authority": "Rec"},
                       timeout=15).raise_for_status()
        r2 = requests.get(f"{API}/go-live/release-decision?rid={rid}",
                           headers=admin_headers, timeout=15).json()
        assert r2["result"] == "ABORTED"

    def test_rolled_back_decision(self, admin_headers):
        r = _create_run(admin_headers); rid = r["go_live_run_id"]
        _approve_all(admin_headers, rid)
        requests.post(f"{API}/go-live/runs/{rid}/start", headers=admin_headers,
                       timeout=15).raise_for_status()
        requests.post(f"{API}/go-live/runs/{rid}/rollback", headers=admin_headers,
                       timeout=15).raise_for_status()
        r2 = requests.get(f"{API}/go-live/release-decision?rid={rid}",
                           headers=admin_headers, timeout=15).json()
        assert r2["result"] == "ROLLED_BACK"

    def test_no_forced_release_without_criticals(self, admin_headers):
        r = _create_run(admin_headers); rid = r["go_live_run_id"]
        _approve_all(admin_headers, rid)
        requests.post(f"{API}/go-live/runs/{rid}/start", headers=admin_headers,
                       timeout=15).raise_for_status()
        # No steps completed → critical_step_pending > 0 → NOT_READY_TO_RELEASE
        r2 = requests.get(f"{API}/go-live/release-decision?rid={rid}",
                           headers=admin_headers, timeout=15).json()
        assert r2["result"] == "NOT_READY_TO_RELEASE"


# ─── PART 7 — RBAC ──────────────────────────────────────────────
class TestRBAC:
    def test_readonly_cannot_create_run(self, ro_headers):
        r = requests.post(f"{API}/go-live/runs", headers=ro_headers,
                          json={"mode": "DRY_RUN"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_can_view_status(self, ro_headers):
        r = requests.get(f"{API}/go-live/status", headers=ro_headers, timeout=15)
        assert r.status_code == 200

    def test_readonly_cannot_abort(self, admin_headers, ro_headers):
        r = _create_run(admin_headers)
        r2 = requests.post(f"{API}/go-live/runs/{r['go_live_run_id']}/abort",
                            headers=ro_headers,
                            json={"reason": "integrity_fail",
                                   "authority": "x"}, timeout=15)
        assert r2.status_code == 403

    def test_readonly_cannot_create_mig_auth(self, ro_headers):
        r = requests.post(f"{API}/go-live/migration-authorisation",
                          headers=ro_headers, json={}, timeout=15)
        assert r.status_code == 403

    def test_deployment_package_no_secrets(self, admin_headers):
        r = requests.get(f"{API}/go-live/deployment-package",
                          headers=admin_headers, timeout=15).json()
        # No secret VALUES leaked — just names
        for name in r["required_secrets"]:
            assert isinstance(name, str)
        assert "MONGO_URL" in r["required_secrets"]
        assert r.get("environment_name")
