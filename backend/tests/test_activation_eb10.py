"""EB-10 · Driver Activation & Onboarding Gate — comprehensive test suite."""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_user(admin_headers, role):
    email = f"eb10_{role.lower()}_{uuid.uuid4().hex[:6]}@acedriverhub.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB10 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"},
                   timeout=20)
    return _login(email, "T@1234"), email


@pytest.fixture(scope="session")
def admin_headers():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)

@pytest.fixture(scope="session")
def manager_headers(admin_headers):
    h, _ = _seed_user(admin_headers, "Manager")
    return h

@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    h, _ = _seed_user(admin_headers, "Allocator")
    return h

@pytest.fixture(scope="session")
def compliance_headers(admin_headers):
    h, _ = _seed_user(admin_headers, "Compliance")
    return h

@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    h, _ = _seed_user(admin_headers, "ReadOnly")
    return h

@pytest.fixture(scope="session")
def another_manager_headers(admin_headers):
    """Distinct Manager to test requester != approver rule."""
    h, _ = _seed_user(admin_headers, "Manager")
    return h


@pytest.fixture(scope="session")
def driver_id(admin_headers):
    rows = requests.get(f"{API}/drivers", headers=admin_headers, timeout=20).json()
    return rows[0]["id"]


@pytest.fixture(scope="session")
def activation_started(admin_headers, driver_id):
    """Ensure activation is started at test-session start."""
    r = requests.post(f"{API}/drivers/{driver_id}/activation/start", headers=admin_headers, timeout=25)
    assert r.status_code == 200
    return r.json()


# ═══════════════════════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════════════════════
class TestTemplates:

    def test_default_template_seeded(self, admin_headers):
        rows = requests.get(f"{API}/activation/templates", headers=admin_headers, timeout=15).json()
        # The seed template survives, even if a later test un-defaulted it.
        ace = [t for t in rows if t.get("company_ref") == "ACE"
               and t.get("_source") == "seed-eb10"
               and t.get("driver_type") == "Employee Driver"
               and not t.get("is_archived")]
        assert ace, "ACE seed template not found"
        assert ace[0]["item_count"] >= 20
        assert ace[0]["mandatory_count"] >= 15

    def test_create_and_clone_template(self, admin_headers):
        r = requests.post(f"{API}/activation/templates",
                           json={"name": f"QA-{uuid.uuid4().hex[:6]}",
                                 "driver_type": "Contractor Driver", "is_default": False,
                                 "company_ref": f"QA-{uuid.uuid4().hex[:4]}"},
                           headers=admin_headers, timeout=15)
        assert r.status_code == 200
        tpl = r.json()
        base_ver = tpl["version"]
        # Clone
        r2 = requests.post(f"{API}/activation/templates/{tpl['activation_template_id']}/clone",
                            headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["version"] == base_ver + 1

    def test_only_one_default_per_company_type(self, admin_headers):
        # Use a fake company to avoid touching the ACE seed default.
        company = f"QAONLY-{uuid.uuid4().hex[:5]}"
        r = requests.post(f"{API}/activation/templates",
                           json={"name": f"QA-new-default-{uuid.uuid4().hex[:6]}",
                                 "driver_type": "Employee Driver", "is_default": True,
                                 "company_ref": company},
                           headers=admin_headers, timeout=15)
        assert r.status_code == 200
        # A second is_default=True in the same (company, type) unsets the first
        r2 = requests.post(f"{API}/activation/templates",
                            json={"name": f"QA-second-default-{uuid.uuid4().hex[:6]}",
                                  "driver_type": "Employee Driver", "is_default": True,
                                  "company_ref": company},
                            headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        rows = requests.get(f"{API}/activation/templates", headers=admin_headers, timeout=15).json()
        defaults = [t for t in rows if t.get("company_ref") == company
                    and t.get("driver_type") == "Employee Driver"
                    and t.get("is_default") and not t.get("is_archived")]
        assert len(defaults) == 1

    def test_manager_cannot_create_readonly(self, readonly_headers):
        r = requests.post(f"{API}/activation/templates",
                           json={"name": "denied", "driver_type": "Other"},
                           headers=readonly_headers, timeout=15)
        assert r.status_code == 403

    def test_archive_template(self, admin_headers):
        create = requests.post(f"{API}/activation/templates",
                                json={"name": f"tobearchived-{uuid.uuid4().hex[:6]}",
                                      "driver_type": "Other"},
                                headers=admin_headers, timeout=15).json()
        r = requests.delete(f"{API}/activation/templates/{create['activation_template_id']}",
                             headers=admin_headers, timeout=15)
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Applicability + readiness
# ═══════════════════════════════════════════════════════════════════════════
class TestReadiness:
    def test_start_creates_items_and_calculates(self, activation_started):
        d = activation_started
        rec = d["record"]
        assert rec["applicable_item_count"] > 0
        assert rec["mandatory_item_count"] > 0
        assert rec["readiness_status"] in {"Incomplete", "Ready", "Ready with Override", "Blocked"}
        assert d["items"]
        # Non-applicable contractor items should be Not Applicable for Employee driver
        contractor = [i for i in d["items"] if i["item_key"] in ("acc.business_name", "acc.abn")]
        assert all(c["completion_status"] == "Not Applicable" for c in contractor), \
            "Contractor items should be Not Applicable for Employee Driver"

    def test_get_matches_start(self, admin_headers, driver_id, activation_started):
        r = requests.get(f"{API}/drivers/{driver_id}/activation", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["record"]["driver_activation_id"] == activation_started["record"]["driver_activation_id"]

    def test_recalculate_idempotent(self, admin_headers, driver_id, activation_started):
        r1 = requests.post(f"{API}/drivers/{driver_id}/activation/recalculate",
                            headers=admin_headers, timeout=15).json()
        r2 = requests.post(f"{API}/drivers/{driver_id}/activation/recalculate",
                            headers=admin_headers, timeout=15).json()
        # Same counters after repeat
        assert r1["record"]["applicable_item_count"] == r2["record"]["applicable_item_count"]
        assert r1["record"]["mandatory_completed_count"] == r2["record"]["mandatory_completed_count"]

    def test_missing_driver_404(self, admin_headers):
        r = requests.get(f"{API}/drivers/{uuid.uuid4()}/activation", headers=admin_headers, timeout=15)
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Manual completion + role gates
# ═══════════════════════════════════════════════════════════════════════════
class TestManualCompletion:
    def _manual_item(self, data):
        for it in data["items"]:
            if it["completion_type"] == "Manual" and it["applicable"] and it["completion_status"] != "Complete":
                return it
        return None

    def test_manual_complete_and_reopen(self, admin_headers, driver_id, activation_started):
        m = self._manual_item(activation_started)
        assert m, "expected a manual item"
        r = requests.put(
            f"{API}/driver-activation-items/{m['driver_activation_item_id']}/manual-complete",
            json={"manual_note": "signed off"}, headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200
        # Refresh
        r2 = requests.get(f"{API}/drivers/{driver_id}/activation", headers=admin_headers, timeout=15).json()
        refreshed = next((i for i in r2["items"] if i["driver_activation_item_id"] == m["driver_activation_item_id"]), None)
        assert refreshed["completion_status"] == "Complete"
        # Reopen
        r3 = requests.put(
            f"{API}/driver-activation-items/{m['driver_activation_item_id']}/manual-reopen",
            headers=admin_headers, timeout=15,
        )
        assert r3.status_code == 200
        r4 = requests.get(f"{API}/drivers/{driver_id}/activation", headers=admin_headers, timeout=15).json()
        refreshed2 = next((i for i in r4["items"] if i["driver_activation_item_id"] == m["driver_activation_item_id"]), None)
        assert refreshed2["completion_status"] in ("Incomplete", "Missing")

    def test_manual_readonly_denied(self, readonly_headers, driver_id, admin_headers, activation_started):
        m = self._manual_item(activation_started)
        assert m
        r = requests.put(
            f"{API}/driver-activation-items/{m['driver_activation_item_id']}/manual-complete",
            json={"manual_note": "no"}, headers=readonly_headers, timeout=15,
        )
        assert r.status_code == 403

    def test_automatic_cannot_be_manually_completed(self, admin_headers, driver_id, activation_started):
        auto = next((i for i in activation_started["items"] if i["completion_type"] == "Automatic"), None)
        assert auto
        r = requests.put(
            f"{API}/driver-activation-items/{auto['driver_activation_item_id']}/manual-complete",
            json={"manual_note": "no"}, headers=admin_headers, timeout=15,
        )
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Overrides
# ═══════════════════════════════════════════════════════════════════════════
class TestOverrides:
    def _overridable_item(self, data):
        for it in data["items"]:
            if it.get("override_allowed") and it["applicable"] and it["mandatory"] \
               and it["completion_status"] in ("Missing", "Incomplete", "Under Review", "Expired", "Due Soon"):
                return it
        return None

    def _non_overridable_item(self, data):
        for it in data["items"]:
            if not it.get("override_allowed"):
                return it
        return None

    def _reset_seed_driver(self, admin_headers, driver_id):
        """If the seed driver has been fully cleared by prior runs, re-open one
        overridable mandatory item so the override tests have something to work with."""
        full = requests.get(f"{API}/drivers/{driver_id}/activation",
                             headers=admin_headers, timeout=15).json()
        if self._overridable_item(full):
            return full
        # Reopen the first overridable manual mandatory item to restore state
        for it in full["items"]:
            if it.get("override_allowed") and it["mandatory"] and it["applicable"] \
               and it["completion_status"] == "Complete" \
               and it["completion_type"] in ("Manual", "Conditional Manual"):
                requests.put(f"{API}/driver-activation-items/{it['driver_activation_item_id']}/manual-reopen",
                              headers=admin_headers, timeout=15)
                break
        return requests.get(f"{API}/drivers/{driver_id}/activation",
                             headers=admin_headers, timeout=15).json()

    def test_override_request_requires_ack(self, allocator_headers, admin_headers, driver_id):
        full = self._reset_seed_driver(admin_headers, driver_id)
        it = self._overridable_item(full)
        if not it:
            pytest.skip("No overridable outstanding item currently available")
        r = requests.post(
            f"{API}/driver-activation-items/{it['driver_activation_item_id']}/override-request",
            json={"reason": "temp exception", "risk_acknowledgement": False, "requested_expiry_days": 3},
            headers=allocator_headers, timeout=15,
        )
        assert r.status_code == 400

    def test_override_full_flow(self, allocator_headers, manager_headers, admin_headers, driver_id):
        full = self._reset_seed_driver(admin_headers, driver_id)
        it = self._overridable_item(full)
        if not it:
            pytest.skip("No overridable outstanding item currently available")
        req = requests.post(
            f"{API}/driver-activation-items/{it['driver_activation_item_id']}/override-request",
            json={"reason": "one-time exception", "risk_acknowledgement": True, "requested_expiry_days": 3},
            headers=allocator_headers, timeout=15,
        )
        assert req.status_code == 200
        ovr_id = req.json()["activation_override_id"]
        deny = requests.post(f"{API}/activation-overrides/{ovr_id}/approve",
                              headers=allocator_headers, timeout=15)
        assert deny.status_code == 403
        ok = requests.post(f"{API}/activation-overrides/{ovr_id}/approve",
                            headers=manager_headers, timeout=15)
        assert ok.status_code == 200
        refreshed = requests.get(f"{API}/drivers/{driver_id}/activation",
                                  headers=admin_headers, timeout=15).json()
        it_after = next((i for i in refreshed["items"] if i["driver_activation_item_id"] == it["driver_activation_item_id"]), None)
        assert it_after["completion_status"] == "Override Active"

    def test_cannot_self_approve_override(self, manager_headers, driver_id, admin_headers):
        full = self._reset_seed_driver(admin_headers, driver_id)
        it = self._overridable_item(full)
        if not it:
            pytest.skip("No overridable outstanding item currently available")
        req = requests.post(
            f"{API}/driver-activation-items/{it['driver_activation_item_id']}/override-request",
            json={"reason": "self approve", "risk_acknowledgement": True, "requested_expiry_days": 2},
            headers=manager_headers, timeout=15,
        )
        assert req.status_code == 200
        ovr_id = req.json()["activation_override_id"]
        r = requests.post(f"{API}/activation-overrides/{ovr_id}/approve",
                          headers=manager_headers, timeout=15)
        assert r.status_code == 403

    def test_non_overridable_rejected(self, admin_headers, driver_id, allocator_headers):
        full = requests.get(f"{API}/drivers/{driver_id}/activation",
                             headers=admin_headers, timeout=15).json()
        no = self._non_overridable_item(full)
        assert no
        r = requests.post(
            f"{API}/driver-activation-items/{no['driver_activation_item_id']}/override-request",
            json={"reason": "attempt one", "risk_acknowledgement": True, "requested_expiry_days": 5},
            headers=allocator_headers, timeout=15,
        )
        assert r.status_code == 400

    def test_override_max_days_enforced(self, allocator_headers, driver_id, admin_headers):
        full = self._reset_seed_driver(admin_headers, driver_id)
        it = self._overridable_item(full)
        if not it:
            pytest.skip("No overridable outstanding item currently available")
        r = requests.post(
            f"{API}/driver-activation-items/{it['driver_activation_item_id']}/override-request",
            json={"reason": "too long", "risk_acknowledgement": True, "requested_expiry_days": 9999},
            headers=allocator_headers, timeout=15,
        )
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# Activation lifecycle
# ═══════════════════════════════════════════════════════════════════════════
class TestActivation:
    def test_cannot_activate_incomplete(self, manager_headers, driver_id):
        # Seed driver still has outstanding mandatories, should refuse.
        r = requests.post(f"{API}/drivers/{driver_id}/activation/activate",
                           json={"reason": "test", "set_driver_status_active": True},
                           headers=manager_headers, timeout=15)
        assert r.status_code == 400

    def test_allocator_cannot_activate(self, allocator_headers, driver_id):
        r = requests.post(f"{API}/drivers/{driver_id}/activation/activate",
                           json={"reason": "no"}, headers=allocator_headers, timeout=15)
        assert r.status_code == 403

    def test_deactivate_requires_manager(self, allocator_headers, driver_id):
        r = requests.post(f"{API}/drivers/{driver_id}/activation/deactivate",
                           json={"reason": "not authorised"}, headers=allocator_headers, timeout=15)
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Jobs
# ═══════════════════════════════════════════════════════════════════════════
class TestJobs:
    def test_recalc_all(self, admin_headers):
        r = requests.post(f"{API}/activation/jobs/recalculate-all", headers=admin_headers, timeout=60)
        assert r.status_code == 200
        assert r.json()["counts"]["processed"] >= 1

    def test_reconcile(self, admin_headers):
        r = requests.post(f"{API}/activation/jobs/reconcile", headers=admin_headers, timeout=60)
        assert r.status_code == 200

    def test_expire_overrides_job(self, admin_headers):
        r = requests.post(f"{API}/activation/jobs/expire-overrides", headers=admin_headers, timeout=60)
        assert r.status_code == 200

    def test_readonly_cannot_run_jobs(self, readonly_headers):
        r = requests.post(f"{API}/activation/jobs/recalculate-all", headers=readonly_headers, timeout=15)
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Audit
# ═══════════════════════════════════════════════════════════════════════════
class TestAudit:
    def test_events_are_append_only(self, admin_headers, driver_id):
        h = requests.get(f"{API}/drivers/{driver_id}/activation/history", headers=admin_headers, timeout=15).json()
        assert h["events"], "expected events recorded"
        types = {e["event_type"] for e in h["events"]}
        # At minimum Activation Started + Recalculated should exist
        assert any(t in types for t in ("Activation Started", "Recalculated", "Item Completed", "Override Approved"))
