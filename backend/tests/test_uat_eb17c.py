"""EB-17c — UAT, Sign-offs & Production Readiness — integration tests.

Local-only; no external preview URLs; no live network; no conditional skips.
All rows tagged _source=seed-eb17c."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API = "http://localhost:8001/api"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email: str, pw: str) -> dict:
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")


@pytest.fixture(scope="module")
def readonly_headers():
    return _login("readonly.qa@acedriverhub.com", "ReadOnly@123")


@pytest.fixture(autouse=True)
def _wipe_eb17c():
    d = _db()
    from uat_module import (PLAN_COLL, CASE_COLL, RUN_COLL, RESULT_COLL,
                            DEF_COLL, SIGN_COLL, EVID_COLL, CHK_COLL,
                            COND_COLL)
    for c in (PLAN_COLL, RUN_COLL, RESULT_COLL, DEF_COLL, SIGN_COLL,
               EVID_COLL, COND_COLL):
        try: d[c].delete_many({"_source": "seed-eb17c"})
        except Exception: pass
    # cases + checklist are re-seeded lazily by service on demand; wipe them too
    for c in (CASE_COLL, CHK_COLL):
        try: d[c].delete_many({"_source": "seed-eb17c"})
        except Exception: pass
    # Cross-milestone seeded gate results used only by EB-17c tests
    for c in ("integrity_gate_results", "security_assessment_runs",
               "restore_rehearsals"):
        try: d[c].delete_many({"_source": "seed-eb17c"})
        except Exception: pass
    yield
    for c in (PLAN_COLL, RUN_COLL, RESULT_COLL, DEF_COLL, SIGN_COLL,
               EVID_COLL, COND_COLL, CASE_COLL, CHK_COLL,
               "integrity_gate_results", "security_assessment_runs",
               "restore_rehearsals"):
        try: d[c].delete_many({"_source": "seed-eb17c"})
        except Exception: pass


def _make_plan(headers, name="EB17c UAT") -> dict:
    return requests.post(f"{API}/uat/plans", headers=headers,
                          json={"name": name}, timeout=15).json()


def _start(headers, plan_id) -> dict:
    return requests.post(f"{API}/uat/plans/{plan_id}/start",
                          headers=headers, timeout=15).json()


def _mark(headers, run_id, case_id, status="Passed", reason=None):
    body = {"uat_test_case_id": case_id, "status": status,
             "actual_result": f"auto-{status}",
             "evidence": {"note": "eb17c-fictional"},
             "correlation_id": str(uuid.uuid4())}
    if reason: body["reason"] = reason
    return requests.post(f"{API}/uat/results/{run_id}", headers=headers,
                          json=body, timeout=15)


def _bypass_all_cases(headers, run_id, status="Passed"):
    """Mark every case in the plan's run so completion pct = 100."""
    run = requests.get(f"{API}/uat/runs/{run_id}", headers=headers,
                       timeout=15).json()
    for cid in run["run"]["case_ids"]:
        _mark(headers, run_id, cid, status=status)


# ═══════════════════════════════════════════════════════════════════
# PART 1 — plans / cases / runs / results
# ═══════════════════════════════════════════════════════════════════
class TestPlansAndRuns:
    def test_seed_cases_present_all_packs(self, admin_headers):
        # touching /api/uat/cases lazily seeds fictional cases
        cases = requests.get(f"{API}/uat/cases", headers=admin_headers,
                              timeout=15).json()
        packs = {c["pack"] for c in cases}
        assert packs == {"Driver Lifecycle", "Compliance", "Migration",
                          "Notifications", "Operations", "Security",
                          "Recovery"}, packs
        assert len(cases) >= 59, len(cases)

    def test_create_plan_and_start(self, admin_headers):
        p = _make_plan(admin_headers)
        assert p["state"] == "Draft"
        assert len(p["case_ids"]) >= 59
        s = _start(admin_headers, p["uat_test_plan_id"])
        assert s["uat_test_run_id"]

    def test_record_result_append_only(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        cid = p["case_ids"][0]
        r1 = _mark(admin_headers, s["uat_test_run_id"], cid, "Failed").json()
        r2 = _mark(admin_headers, s["uat_test_run_id"], cid, "Passed").json()
        assert r1["attempt"] == 1 and r2["attempt"] == 2
        assert r1["uat_test_result_id"] != r2["uat_test_result_id"]
        # Both records must persist
        run = requests.get(f"{API}/uat/runs/{s['uat_test_run_id']}",
                           headers=admin_headers, timeout=15).json()
        for_case = [r for r in run["results"] if r["uat_test_case_id"] == cid]
        assert len(for_case) == 2

    def test_blocked_requires_reason(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        cid = p["case_ids"][0]
        r = _mark(admin_headers, s["uat_test_run_id"], cid, "Blocked")
        assert r.status_code == 400
        r2 = _mark(admin_headers, s["uat_test_run_id"], cid, "Blocked",
                   reason="ACE Ops unavailable in fictional env")
        assert r2.status_code == 200

    def test_close_run_and_plan(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        resp = requests.post(f"{API}/uat/runs/{s['uat_test_run_id']}/close",
                              headers=admin_headers, timeout=15).json()
        assert resp["state"] == "Closed"


# ═══════════════════════════════════════════════════════════════════
# PART 2 — Defects
# ═══════════════════════════════════════════════════════════════════
class TestDefects:
    def _open_defect(self, headers, severity="Critical", cid=None):
        body = {"severity": severity, "title": f"UAT {severity} defect",
                 "description": "fictional", "uat_test_case_id": cid}
        return requests.post(f"{API}/uat/defects", headers=headers,
                              json=body, timeout=15).json()

    def test_open_transition_and_history(self, admin_headers):
        d = self._open_defect(admin_headers, "Medium")
        r = requests.post(f"{API}/uat/defects/{d['uat_defect_id']}/transition",
                          headers=admin_headers,
                          json={"to_state": "Investigating",
                                 "reason": "test-run"}, timeout=15).json()
        assert r["state"] == "Investigating"
        assert len(r["history"]) == 2

    def test_critical_cannot_defer(self, admin_headers):
        d = self._open_defect(admin_headers, "Critical")
        r = requests.post(f"{API}/uat/defects/{d['uat_defect_id']}/transition",
                          headers=admin_headers,
                          json={"to_state": "Deferred",
                                 "reason": "attempt"}, timeout=15)
        assert r.status_code == 400 and "Critical" in r.text

    def test_high_cannot_defer(self, admin_headers):
        d = self._open_defect(admin_headers, "High")
        r = requests.post(f"{API}/uat/defects/{d['uat_defect_id']}/transition",
                          headers=admin_headers,
                          json={"to_state": "Deferred",
                                 "reason": "attempt"}, timeout=15)
        assert r.status_code == 400 and "High" in r.text

    def test_medium_defer_permitted(self, admin_headers):
        d = self._open_defect(admin_headers, "Medium")
        r = requests.post(f"{API}/uat/defects/{d['uat_defect_id']}/transition",
                          headers=admin_headers,
                          json={"to_state": "Deferred",
                                 "reason": "post-EB17c"}, timeout=15).json()
        assert r["state"] == "Deferred"

    def test_closed_requires_evidence_or_retest(self, admin_headers):
        d = self._open_defect(admin_headers, "Low")
        # Walk to Ready-for-Retest
        for to in ("Investigating", "Fixed", "Ready for Retest"):
            requests.post(
                f"{API}/uat/defects/{d['uat_defect_id']}/transition",
                headers=admin_headers,
                json={"to_state": to}, timeout=15).raise_for_status()
        # Close without evidence and without passing retest → 400
        r = requests.post(f"{API}/uat/defects/{d['uat_defect_id']}/transition",
                          headers=admin_headers,
                          json={"to_state": "Closed"}, timeout=15)
        assert r.status_code == 400
        # Close with explicit evidence → 200
        r2 = requests.post(f"{API}/uat/defects/{d['uat_defect_id']}/transition",
                           headers=admin_headers,
                           json={"to_state": "Closed",
                                  "evidence": {"link": "eb17c-fictional"}},
                           timeout=15).json()
        assert r2["state"] == "Closed"


# ═══════════════════════════════════════════════════════════════════
# PART 3 — Sign-offs
# ═══════════════════════════════════════════════════════════════════
class TestSignoffs:
    def _prep_ready(self, admin_headers):
        """Make the environment eligible for an Approved sign-off:
        UAT plan started, 0 defects, 0 conditions."""
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        _bypass_all_cases(admin_headers, s["uat_test_run_id"])
        return p, s

    def test_approve_immutable(self, admin_headers):
        self._prep_ready(admin_headers)
        r = requests.post(f"{API}/uat/signoffs", headers=admin_headers,
                          json={"area": "Technical", "status": "Approved",
                                 "comments": "ok"}, timeout=15).json()
        assert r["status"] == "Approved" and r["immutable"] is True
        # No update endpoint exists → immutability is enforced by API surface.

    def test_signer_role_restriction(self, admin_headers, readonly_headers):
        r = requests.post(f"{API}/uat/signoffs", headers=readonly_headers,
                          json={"area": "Technical", "status": "Approved"},
                          timeout=15)
        assert r.status_code == 403

    def test_withdraw(self, admin_headers):
        r = requests.post(f"{API}/uat/signoffs", headers=admin_headers,
                          json={"area": "Security",
                                 "status": "Approved with Conditions",
                                 "comments": "warn"}, timeout=15).json()
        w = requests.post(
            f"{API}/uat/signoffs/{r['uat_signoff_id']}/withdraw",
            headers=admin_headers, timeout=15).json()
        assert w["withdrawn"] is True and w["status"] == "Withdrawn"

    def test_critical_open_blocks_approval(self, admin_headers):
        # Open a Critical defect first
        requests.post(f"{API}/uat/defects", headers=admin_headers,
                       json={"severity": "Critical",
                              "title": "block", "description": ""},
                       timeout=15).raise_for_status()
        r = requests.post(f"{API}/uat/signoffs", headers=admin_headers,
                          json={"area": "Technical",
                                 "status": "Approved"}, timeout=15)
        assert r.status_code == 400 and "critical" in r.text.lower()

    def test_high_open_blocks_approval(self, admin_headers):
        requests.post(f"{API}/uat/defects", headers=admin_headers,
                       json={"severity": "High",
                              "title": "block", "description": ""},
                       timeout=15).raise_for_status()
        r = requests.post(f"{API}/uat/signoffs", headers=admin_headers,
                          json={"area": "Technical",
                                 "status": "Approved"}, timeout=15)
        assert r.status_code == 400 and "high" in r.text.lower()


# ═══════════════════════════════════════════════════════════════════
# PART 4 — Production Readiness gate
# ═══════════════════════════════════════════════════════════════════
class TestReadinessGate:
    def _all_signoffs(self, admin_headers, status="Approved"):
        for area in ("Business Operations", "Compliance", "Management",
                      "Technical", "Security", "Data Migration", "Recovery"):
            requests.post(f"{API}/uat/signoffs", headers=admin_headers,
                           json={"area": area, "status": status},
                           timeout=15).raise_for_status()

    def _complete_checklist(self, admin_headers):
        # Seed PASS gate results so system-derived checklist items complete.
        d = _db()
        now = _iso()
        d["integrity_gate_results"].insert_one({
            "id": str(uuid.uuid4()), "result": "PASS",
            "created_at": now, "_source": "seed-eb17c"})
        d["security_assessment_runs"].insert_one({
            "security_assessment_run_id": str(uuid.uuid4()),
            "status": "Completed", "overall_result": "PASS",
            "completed_at": now,
            "findings_by_severity": {"Info": 0, "Warning": 0,
                                        "Error": 0, "Critical": 0},
            "_source": "seed-eb17c"})
        d["restore_rehearsals"].insert_one({
            "restore_rehearsal_id": str(uuid.uuid4()),
            "final_state": "Passed",
            "integrity_gate": "PASS", "security_gate": "PASS",
            "started_at": now, "completed_at": now,
            "_source": "seed-eb17c"})
        items = requests.get(f"{API}/production-readiness/checklist",
                              headers=admin_headers, timeout=15).json()
        for it in items:
            if it["kind"] != "human": continue
            requests.post(
                f"{API}/production-readiness/checklist/{it['item_id']}/update",
                headers=admin_headers,
                json={"status": "Complete", "owner": "eb17c-fictional",
                       "comment": "auto", "evidence": {"link": "seed"}},
                timeout=15).raise_for_status()

    def test_not_ready_when_no_uat(self, admin_headers):
        g = requests.get(f"{API}/production-readiness/gate",
                          headers=admin_headers, timeout=15).json()
        assert g["result"] == "NOT_READY", g

    def test_ready_requires_all_signoffs_and_uat_completion(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        _bypass_all_cases(admin_headers, s["uat_test_run_id"])
        self._complete_checklist(admin_headers)
        self._all_signoffs(admin_headers, "Approved")
        g = requests.get(f"{API}/production-readiness/gate",
                          headers=admin_headers, timeout=15).json()
        assert g["result"] in ("READY", "CONDITIONALLY_READY"), g
        assert g["eb18_entry"] == "OPEN", g

    def test_conditionally_ready_with_conditions(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        _bypass_all_cases(admin_headers, s["uat_test_run_id"])
        self._complete_checklist(admin_headers)
        self._all_signoffs(admin_headers, "Approved")
        requests.post(f"{API}/production-readiness/conditions",
                       headers=admin_headers,
                       json={"source": "eb17c", "description": "watch item",
                              "owner": "ops", "risk_level": "Medium"},
                       timeout=15).raise_for_status()
        g = requests.get(f"{API}/production-readiness/gate",
                          headers=admin_headers, timeout=15).json()
        assert g["result"] == "CONDITIONALLY_READY", g

    def test_critical_condition_open_blocks(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        _bypass_all_cases(admin_headers, s["uat_test_run_id"])
        self._complete_checklist(admin_headers)
        self._all_signoffs(admin_headers, "Approved")
        requests.post(f"{API}/production-readiness/conditions",
                       headers=admin_headers,
                       json={"source": "eb17c", "description": "critical risk",
                              "owner": "ops", "risk_level": "Critical",
                              "status": "Open"},
                       timeout=15).raise_for_status()
        g = requests.get(f"{API}/production-readiness/gate",
                          headers=admin_headers, timeout=15).json()
        assert g["result"] == "NOT_READY", g
        assert "critical_conditions_open>0" in g["blockers"]

    def test_high_defect_blocks(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        _bypass_all_cases(admin_headers, s["uat_test_run_id"])
        self._complete_checklist(admin_headers)
        self._all_signoffs(admin_headers, "Approved")
        requests.post(f"{API}/uat/defects", headers=admin_headers,
                       json={"severity": "High",
                              "title": "H", "description": ""},
                       timeout=15).raise_for_status()
        g = requests.get(f"{API}/production-readiness/gate",
                          headers=admin_headers, timeout=15).json()
        assert g["result"] == "NOT_READY"
        assert "open_high_defects>0" in g["blockers"]

    def test_checklist_incomplete_blocks(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        _bypass_all_cases(admin_headers, s["uat_test_run_id"])
        self._all_signoffs(admin_headers, "Approved")
        # Do NOT complete checklist
        g = requests.get(f"{API}/production-readiness/gate",
                          headers=admin_headers, timeout=15).json()
        assert g["result"] == "NOT_READY", g
        assert "checklist_incomplete" in g["blockers"]

    def test_uat_completion_below_100_blocks(self, admin_headers):
        p = _make_plan(admin_headers)
        s = _start(admin_headers, p["uat_test_plan_id"])
        # Mark just one case
        _mark(admin_headers, s["uat_test_run_id"], p["case_ids"][0], "Passed")
        self._complete_checklist(admin_headers)
        self._all_signoffs(admin_headers, "Approved")
        g = requests.get(f"{API}/production-readiness/gate",
                          headers=admin_headers, timeout=15).json()
        assert g["result"] == "NOT_READY"
        assert "uat_completion<100" in g["blockers"]


# ═══════════════════════════════════════════════════════════════════
# PART 5 — Checklist RBAC and system items
# ═══════════════════════════════════════════════════════════════════
class TestChecklistAndConditions:
    def test_system_item_cannot_be_manually_updated(self, admin_headers):
        # Ensure checklist seeded
        requests.get(f"{API}/production-readiness/checklist",
                      headers=admin_headers, timeout=15)
        r = requests.post(
            f"{API}/production-readiness/checklist/pe.int_gate/update",
            headers=admin_headers,
            json={"status": "Complete"}, timeout=15)
        assert r.status_code == 400

    def test_waiver_requires_evidence(self, admin_headers):
        requests.get(f"{API}/production-readiness/checklist",
                      headers=admin_headers, timeout=15)
        r = requests.post(
            f"{API}/production-readiness/checklist/pe.env/update",
            headers=admin_headers,
            json={"status": "Waived"}, timeout=15)
        assert r.status_code == 400
        r2 = requests.post(
            f"{API}/production-readiness/checklist/pe.env/update",
            headers=admin_headers,
            json={"status": "Waived",
                   "evidence": {"link": "waiver-eb17c"}},
            timeout=15).json()
        assert r2["status"] == "Waived"

    def test_expired_condition_visible(self, admin_headers):
        c = requests.post(f"{API}/production-readiness/conditions",
                           headers=admin_headers,
                           json={"source": "eb17c",
                                  "description": "expired cond",
                                  "owner": "ops", "risk_level": "Medium",
                                  "status": "Expired"},
                           timeout=15).json()
        lst = requests.get(f"{API}/production-readiness/conditions",
                            headers=admin_headers, timeout=15).json()
        assert any(x["condition_id"] == c["condition_id"] for x in lst)


# ═══════════════════════════════════════════════════════════════════
# PART 6 — RBAC on mutations
# ═══════════════════════════════════════════════════════════════════
class TestRBAC:
    def test_readonly_cannot_create_plan(self, readonly_headers):
        r = requests.post(f"{API}/uat/plans", headers=readonly_headers,
                          json={"name": "x"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_cannot_create_defect(self, readonly_headers):
        r = requests.post(f"{API}/uat/defects", headers=readonly_headers,
                          json={"severity": "Low", "title": "x",
                                 "description": ""}, timeout=15)
        assert r.status_code == 403

    def test_readonly_cannot_update_checklist(self, readonly_headers):
        r = requests.post(
            f"{API}/production-readiness/checklist/pe.env/update",
            headers=readonly_headers,
            json={"status": "Complete"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_can_view_gate(self, readonly_headers):
        r = requests.get(f"{API}/production-readiness/gate",
                          headers=readonly_headers, timeout=15)
        assert r.status_code == 200

    def test_readonly_cannot_signoff(self, readonly_headers):
        r = requests.post(f"{API}/uat/signoffs", headers=readonly_headers,
                          json={"area": "Technical",
                                 "status": "Approved"}, timeout=15)
        assert r.status_code == 403
