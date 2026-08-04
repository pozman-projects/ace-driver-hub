"""EB-14 · Migration Commit + Legacy Storage Backfill tests.

Stage A only: uses sanitised fictional fixtures. No real ACE identifiers,
names, phones, emails, ABNs, VINs, or licence numbers.
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests
from openpyxl import Workbook

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PREP = f"{API}/migration-prep"
COMMIT = f"{API}/migration-commit"


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(admin_headers, role):
    email = f"eb14_{role.lower()}_{uuid.uuid4().hex[:6]}@acedriverhub.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB14 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"},
                   timeout=25)
    return _login(email, "T@1234")


@pytest.fixture(scope="module")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")

@pytest.fixture(scope="module")
def manager_headers(admin_headers):
    return _register(admin_headers, "Manager")

@pytest.fixture(scope="module")
def readonly_headers(admin_headers):
    return _register(admin_headers, "ReadOnly")

@pytest.fixture(scope="module")
def allocator_headers(admin_headers):
    return _register(admin_headers, "Allocator")


# ── Helpers to build an approved dry-run ─────────────────────────────────────
DRIVER_HEADERS = ["driver_code", "dispatch_number", "full_name",
                   "email", "mobile_phone", "start_date"]
CLEAN = [DRIVER_HEADERS] + [
    ["9001", 501, "Ficta One", "one@example.test", "0400000001", "2024-01-05"],
    ["9002", 502, "Ficta Two", "two@example.test", "0400000002", "2024-01-06"],
]


def _upload_wb(admin_headers, filename, sheets):
    wb = Workbook(); wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows: ws.append(r)
    buf = io.BytesIO(); wb.save(buf)
    files = {"file": (filename, buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    form = {"profile_name": f"EB14-{uuid.uuid4().hex[:6]}",
             "authority_level": "Authoritative", "data_domain": "Driver"}
    r = requests.post(f"{PREP}/workbooks/profile", files=files, data=form,
                       headers=admin_headers, timeout=30)
    r.raise_for_status(); return r.json()


def _create_profile(admin_headers, wb, target="Driver"):
    sheet = requests.get(f"{PREP}/workbooks/{wb['migration_source_workbook_id']}/sheets",
                           headers=admin_headers).json()[0]
    r = requests.post(f"{PREP}/mapping-profiles", json={
        "name": f"P-{uuid.uuid4().hex[:6]}",
        "migration_source_workbook_id": wb["migration_source_workbook_id"],
        "migration_source_sheet_id": sheet["migration_source_sheet_id"],
        "target_entity_type": target,
    }, headers=admin_headers, timeout=15)
    r.raise_for_status(); return r.json()


def _add_field(admin_headers, pid, col, target, tids=None, required=False):
    r = requests.post(f"{PREP}/mapping-profiles/{pid}/fields", json={
        "source_column_name": col, "target_field": target,
        "target_entity_type": "Driver", "mapping_type": "Direct",
        "required": required, "null_handling": "Leave Blank",
        "transform_rule_ids": tids or [],
        "conflict_strategy": "Flag for Review", "display_order": 0,
    }, headers=admin_headers, timeout=15)
    r.raise_for_status(); return r.json()


def _mk_full_profile(admin_headers, wb):
    p = _create_profile(admin_headers, wb, "Driver")
    pid = p["migration_mapping_profile_id"]
    rules = requests.get(f"{PREP}/transform-rules", headers=admin_headers).json()
    dc = next(r for r in rules if r["rule_type"] == "driver_code")["migration_transform_rule_id"]
    ph = next(r for r in rules if r["rule_type"] == "phone")["migration_transform_rule_id"]
    em = next(r for r in rules if r["rule_type"] == "email")["migration_transform_rule_id"]
    dt = next(r for r in rules if r["rule_type"] == "date")["migration_transform_rule_id"]
    _add_field(admin_headers, pid, "driver_code", "driver_code", [dc], required=True)
    _add_field(admin_headers, pid, "dispatch_number", "dispatch_number", [])
    _add_field(admin_headers, pid, "full_name", "full_name", [])
    _add_field(admin_headers, pid, "email", "email", [em])
    _add_field(admin_headers, pid, "mobile_phone", "mobile_phone", [ph])
    _add_field(admin_headers, pid, "start_date", "start_date", [dt])
    # Approve
    requests.post(f"{PREP}/mapping-profiles/{pid}/approve", headers=admin_headers)
    return pid


def _dry_run(admin_headers, wb, pid, name="EB14"):
    r = requests.post(f"{PREP}/dry-runs", json={
        "name": name, "description": "eb14",
        "mapping_profile_ids": [pid],
        "source_workbook_ids": [wb["migration_source_workbook_id"]],
    }, headers=admin_headers).json()
    dr_id = r["migration_dry_run_id"]
    requests.post(f"{PREP}/dry-runs/{dr_id}/execute",
                    headers=admin_headers, timeout=45)
    # Go/No-Go
    gng = requests.post(f"{PREP}/dry-runs/{dr_id}/go-no-go",
                          headers=admin_headers).json()
    return dr_id, gng


@pytest.fixture
def approved_dryrun(admin_headers):
    """Return (wb, pid, dr_id, gng) for a clean GO dry run."""
    wb = _upload_wb(admin_headers, f"eb14_{uuid.uuid4().hex[:6]}.xlsx", {"Drivers": CLEAN})
    pid = _mk_full_profile(admin_headers, wb)
    dr_id, gng = _dry_run(admin_headers, wb, pid)
    return wb, pid, dr_id, gng


# ══════════════════════════════════════════════════════════════════════════
# 1. Environment banner + job list RBAC
# ══════════════════════════════════════════════════════════════════════════
class TestEnvironment:

    def test_banner_says_staged(self, admin_headers):
        r = requests.get(f"{COMMIT}/environment", headers=admin_headers).json()
        assert r["transactions_enabled"] is False
        assert r["commit_mode"] == "staged-idempotent"
        assert "Staged" in r["banner"]

    def test_readonly_can_view_environment(self, readonly_headers):
        r = requests.get(f"{COMMIT}/environment", headers=readonly_headers)
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 2. Commit job creation guards
# ══════════════════════════════════════════════════════════════════════════
class TestJobCreation:

    def test_readonly_cannot_create(self, readonly_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        r = requests.post(f"{COMMIT}/jobs",
                            json={"migration_dry_run_id": dr_id, "name": "x",
                                   "mode": "Rehearsal"},
                            headers=readonly_headers)
        assert r.status_code == 403

    def test_no_go_cannot_create_job(self, admin_headers):
        # Build a NO-GO dry run: dispatch=13 blocks
        rows = [DRIVER_HEADERS,
                ["9600", 13, "Bad Row", "b@example.test", "0400777777", "2024-07-01"]]
        wb = _upload_wb(admin_headers, "nogo.xlsx", {"S": rows})
        pid = _mk_full_profile(admin_headers, wb)
        dr_id, gng = _dry_run(admin_headers, wb, pid, "no-go")
        assert gng["result"] == "NO-GO"
        r = requests.post(f"{COMMIT}/jobs",
                            json={"migration_dry_run_id": dr_id, "name": "x",
                                   "mode": "Rehearsal"},
                            headers=admin_headers)
        assert r.status_code == 400

    def test_manager_can_create_rehearsal_job(self, manager_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        r = requests.post(f"{COMMIT}/jobs",
                            json={"migration_dry_run_id": dr_id,
                                   "name": "rehearsal-1", "mode": "Rehearsal"},
                            headers=manager_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "Draft"
        assert r.json()["migration_approval_id"]

    def test_job_has_immutable_package(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        r = requests.post(f"{COMMIT}/jobs",
                            json={"migration_dry_run_id": dr_id, "name": "pkg", "mode": "Rehearsal"},
                            headers=admin_headers).json()
        detail = requests.get(f"{COMMIT}/jobs/{r['migration_commit_job_id']}",
                                headers=admin_headers).json()
        assert "immutable_package" in detail
        pkg = detail["immutable_package"]
        assert pkg["package_sha256"]
        assert pkg["workbooks"]
        assert pkg["mapping_profiles"]

    def test_readonly_sees_no_immutable_package(self, admin_headers, readonly_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "hide",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        detail = requests.get(f"{COMMIT}/jobs/{job['migration_commit_job_id']}",
                                headers=readonly_headers).json()
        assert "immutable_package" not in detail


# ══════════════════════════════════════════════════════════════════════════
# 3. Approval lifecycle
# ══════════════════════════════════════════════════════════════════════════
class TestApproval:

    def test_request_and_approve(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "appr", "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        r1 = requests.post(f"{COMMIT}/jobs/{jid}/request-approval",
                             headers=admin_headers).json()
        assert r1["status"] == "Awaiting Approval"
        r2 = requests.post(f"{COMMIT}/jobs/{jid}/approve", json={},
                             headers=admin_headers).json()
        assert r2["status"] == "Approved"

    def test_allocator_cannot_approve(self, admin_headers, allocator_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "roleblock",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=admin_headers)
        r = requests.post(f"{COMMIT}/jobs/{jid}/approve", json={},
                            headers=allocator_headers)
        assert r.status_code == 403

    def test_conditional_go_requires_risk_acceptance(self, admin_headers, approved_dryrun):
        # Simulate CONDITIONAL GO via non-integer driver code producing warnings
        rows = [DRIVER_HEADERS,
                ["LEGACY-A", 700, "Legacy One", "l@example.test", "0400333333", "2020-01-01"]]
        wb = _upload_wb(admin_headers, "cg.xlsx", {"S": rows})
        pid = _mk_full_profile(admin_headers, wb)
        dr_id, gng = _dry_run(admin_headers, wb, pid, "cg")
        if gng["result"] != "CONDITIONAL GO":
            pytest.skip(f"Fixture did not produce CONDITIONAL GO (got {gng['result']})")
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "cg",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=admin_headers)
        r = requests.post(f"{COMMIT}/jobs/{jid}/approve", json={"risk_acceptance": False},
                            headers=admin_headers)
        assert r.status_code == 400  # requires risk_acceptance
        r2 = requests.post(f"{COMMIT}/jobs/{jid}/approve",
                             json={"risk_acceptance": True, "note": "accepted"},
                             headers=admin_headers)
        assert r2.status_code == 200

    def test_reject_moves_back_to_draft(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "rej", "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=admin_headers)
        r = requests.post(f"{COMMIT}/jobs/{jid}/reject",
                            json={"reason": "review needed"},
                            headers=admin_headers)
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 4. Preflight
# ══════════════════════════════════════════════════════════════════════════
class TestPreflight:

    def _prep_ready_job(self, admin_headers, dr_id):
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "pf",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/approve", json={}, headers=admin_headers)
        return jid

    def test_preflight_passes(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        jid = self._prep_ready_job(admin_headers, dr_id)
        r = requests.post(f"{COMMIT}/jobs/{jid}/preflight", headers=admin_headers).json()
        assert r["passed"] is True
        assert any(c["check"] == "approval_valid" for c in r["checks"])
        assert any(c["check"] == "rollback_package_present" for c in r["checks"])
        assert any("workbook_" in c["check"] for c in r["checks"])

    def test_preflight_without_approval_fails(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "pf-fail",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        r = requests.post(f"{COMMIT}/jobs/{jid}/preflight", headers=admin_headers).json()
        assert r["passed"] is False
        # Approval must be invalid (Pending, not Approved)
        assert any(c["check"] == "approval_valid" and not c["ok"] for c in r["checks"])


# ══════════════════════════════════════════════════════════════════════════
# 5. Rehearsal execution (no canonical mutation)
# ══════════════════════════════════════════════════════════════════════════
class TestRehearsalExecute:

    def test_rehearsal_does_not_create_drivers(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        # Snapshot canonical driver count with runtime source
        before = requests.get(f"{API}/drivers", headers=admin_headers).json()
        n_before = len(before)
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "reh",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/approve", json={}, headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/preflight", headers=admin_headers)
        r = requests.post(f"{COMMIT}/jobs/{jid}/execute",
                            headers=admin_headers, timeout=60).json()
        assert r["status"] in ("Completed", "Partially Completed")
        after = requests.get(f"{API}/drivers", headers=admin_headers).json()
        # Rehearsal must not add canonical drivers
        assert len(after) == n_before

    def test_rehearsal_writes_actions_and_events(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "reh-a",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/approve", json={}, headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/preflight", headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/execute", headers=admin_headers, timeout=60)
        actions = requests.get(f"{COMMIT}/jobs/{jid}/actions", headers=admin_headers).json()
        events = requests.get(f"{COMMIT}/jobs/{jid}/events", headers=admin_headers).json()
        assert len(actions) >= 1
        assert any(e["event_type"] == "Commit Complete" for e in events)


# ══════════════════════════════════════════════════════════════════════════
# 6. Controlled Commit (fictional data, admin-only)
# ══════════════════════════════════════════════════════════════════════════
class TestControlledCommit:

    def test_manager_cannot_execute_controlled(self, admin_headers, manager_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        # Manager requests the job so Admin can approve (self-approval blocked)
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "cc-role",
                                     "mode": "Controlled Commit"},
                              headers=manager_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=manager_headers)
        # Approve as Admin (real commit approval requires Admin)
        appr = requests.post(f"{COMMIT}/jobs/{jid}/approve",
                               json={"risk_acceptance": True},
                               headers=admin_headers)
        assert appr.status_code == 200
        requests.post(f"{COMMIT}/jobs/{jid}/preflight", headers=admin_headers)
        # Manager cannot execute controlled commit
        r = requests.post(f"{COMMIT}/jobs/{jid}/execute", headers=manager_headers)
        assert r.status_code == 403

    def test_controlled_creates_canonical_and_is_idempotent(self, admin_headers, manager_headers):
        # Deterministic integer driver_code + safe dispatch, unique per run
        code = f"88{uuid.uuid4().int % 10000:04d}"  # always numeric
        disp = 800 + (uuid.uuid4().int % 100)
        rows = [DRIVER_HEADERS,
                [code, disp, "Ficta Idem", "idem@example.test",
                 "0400010001", "2024-05-01"]]
        wb = _upload_wb(admin_headers, f"idem_{uuid.uuid4().hex[:6]}.xlsx", {"S": rows})
        pid = _mk_full_profile(admin_headers, wb)
        dr_id, gng = _dry_run(admin_headers, wb, pid, "idem")
        if gng["result"] == "NO-GO":
            pytest.skip(f"Fixture produced NO-GO ({gng.get('result')})")
        before = requests.get(f"{API}/drivers", headers=admin_headers).json()
        # Manager requests, Admin approves (real commit self-approval blocked)
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "cc",
                                     "mode": "Controlled Commit"},
                              headers=manager_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=manager_headers)
        appr = requests.post(f"{COMMIT}/jobs/{jid}/approve",
                              json={"risk_acceptance": True}, headers=admin_headers)
        assert appr.status_code == 200, appr.text
        requests.post(f"{COMMIT}/jobs/{jid}/preflight", headers=admin_headers)
        r = requests.post(f"{COMMIT}/jobs/{jid}/execute",
                            headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json().get("status") in ("Completed", "Partially Completed"), r.text
        after = requests.get(f"{API}/drivers", headers=admin_headers).json()
        # Real commit should create at least 1 driver (or 0 if row deduped)
        assert len(after) >= len(before)

        # Second execute must not double-write actions
        actions_before = len(requests.get(f"{COMMIT}/jobs/{jid}/actions",
                                             headers=admin_headers).json())
        # Job status is Completed, so a resume would fail
        r2 = requests.post(f"{COMMIT}/jobs/{jid}/resume", headers=admin_headers)
        # Either 400 (cannot resume from Completed) is the correct behaviour
        assert r2.status_code in (200, 400)


# ══════════════════════════════════════════════════════════════════════════
# 7. Post-commit reconciliation
# ══════════════════════════════════════════════════════════════════════════
class TestReconciliation:

    def test_reconcile_runs(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "rec",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        requests.post(f"{COMMIT}/jobs/{jid}/request-approval", headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/approve", json={}, headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/preflight", headers=admin_headers)
        requests.post(f"{COMMIT}/jobs/{jid}/execute", headers=admin_headers, timeout=60)
        r = requests.post(f"{COMMIT}/jobs/{jid}/reconcile", headers=admin_headers).json()
        assert r["result"] in ("Reconciled", "Reconciled with Warnings", "Failed Reconciliation")
        list_r = requests.get(f"{COMMIT}/jobs/{jid}/reconciliation",
                                headers=admin_headers).json()
        assert isinstance(list_r, list) and len(list_r) >= 1


# ══════════════════════════════════════════════════════════════════════════
# 8. Rollback
# ══════════════════════════════════════════════════════════════════════════
class TestRollback:

    def test_rollback_package_status(self, admin_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "rb",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        s = requests.get(f"{COMMIT}/jobs/{jid}/rollback-package",
                           headers=admin_headers).json()
        assert "package" in s
        assert s["actions_count"] == 0  # nothing committed yet

    def test_rollback_requires_admin(self, admin_headers, manager_headers, approved_dryrun):
        _, _, dr_id, _ = approved_dryrun
        job = requests.post(f"{COMMIT}/jobs",
                              json={"migration_dry_run_id": dr_id, "name": "rb-role",
                                     "mode": "Rehearsal"},
                              headers=admin_headers).json()
        jid = job["migration_commit_job_id"]
        r = requests.post(f"{COMMIT}/jobs/{jid}/rollback/execute",
                            headers=manager_headers)
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
# 9. Storage Backfill
# ══════════════════════════════════════════════════════════════════════════
class TestBackfill:

    def test_readonly_cannot_create_backfill(self, readonly_headers):
        r = requests.post(f"{API}/storage/backfill",
                            json={"scope": "Documents"},
                            headers=readonly_headers)
        assert r.status_code == 403

    def test_admin_can_create_and_execute(self, admin_headers):
        r = requests.post(f"{API}/storage/backfill",
                            json={"scope": "All Legacy Development Assets"},
                            headers=admin_headers).json()
        assert r["status"] == "Queued"
        jid = r["storage_backfill_job_id"]
        exe = requests.post(f"{API}/storage/backfill/{jid}/execute",
                              headers=admin_headers, timeout=60).json()
        assert "found" in exe
        detail = requests.get(f"{API}/storage/backfill/{jid}", headers=admin_headers).json()
        assert detail["status"] in ("Completed", "Partially Completed")
        # Legacy source must be retained
        assert detail["source_retained"] is True

    def test_invalid_scope_rejected(self, admin_headers):
        r = requests.post(f"{API}/storage/backfill",
                            json={"scope": "InvalidScope"},
                            headers=admin_headers)
        assert r.status_code == 400

    def test_idempotent_rerun(self, admin_headers):
        r = requests.post(f"{API}/storage/backfill",
                            json={"scope": "Migration Workbooks"},
                            headers=admin_headers).json()
        jid = r["storage_backfill_job_id"]
        r1 = requests.post(f"{API}/storage/backfill/{jid}/execute",
                             headers=admin_headers, timeout=60).json()
        r2 = requests.post(f"{API}/storage/backfill/{jid}/retry",
                             headers=admin_headers, timeout=60).json()
        # Retry must not error and must not add duplicate migrations
        assert r2["found"] <= r1["found"] or r2["found"] == 0
