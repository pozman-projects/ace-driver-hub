"""EB-10 additional integration coverage: category role gating, event history append-only,
notification dedup, reactivate flow, non-overridable guard. Complements test_activation_eb10.py."""
from __future__ import annotations
import os
import uuid
import time
import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@acedriverhub.com", "Admin@123")
SEED_DRIVER_ID = "ef239b34-6611-41e2-8d68-7258bef0b0b9"

NON_OVR_KEYS = {"cmp.licence_exists", "cmp.licence_not_expired",
                "cmp.no_critical_defect", "setup.driver_code",
                "setup.dispatch_number"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_user(admin_headers, role, tag=""):
    email = f"eb10x_{role.lower()}_{tag}{uuid.uuid4().hex[:5]}@acedriverhub.com"
    requests.post(f"{API}/auth/register",
                  json={"email": email, "password": "T@1234",
                        "full_name": f"EB10x {role}", "role": role},
                  headers={**admin_headers, "Content-Type": "application/json"},
                  timeout=20)
    return _login(email, "T@1234")


@pytest.fixture(scope="module")
def admin_headers():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def allocator_headers(admin_headers):
    return _seed_user(admin_headers, "Allocator")


@pytest.fixture(scope="module")
def driver_id(admin_headers):
    r = requests.get(f"{API}/drivers/{SEED_DRIVER_ID}", headers=admin_headers, timeout=20)
    if r.status_code == 200:
        return SEED_DRIVER_ID
    return requests.get(f"{API}/drivers", headers=admin_headers, timeout=20).json()[0]["id"]


@pytest.fixture(scope="module")
def activation(admin_headers, driver_id):
    r = requests.post(f"{API}/drivers/{driver_id}/activation/start",
                      headers=admin_headers, timeout=25)
    assert r.status_code == 200, r.text
    return r.json()


def _item_id(it):
    return it.get("driver_activation_item_id") or it.get("id")


def _item_status(it):
    return (it.get("completion_status") or it.get("status") or "").lower()


def _item_mode(it):
    return (it.get("completion_type") or it.get("resolution_mode") or "").lower()


# --- Category role gating for manual complete ---

class TestCategoryRoleGating:
    def test_allocator_denied_on_licence_and_compliance_manual(
            self, allocator_headers, activation):
        target = next(
            (it for it in activation["items"]
             if it.get("category", "").startswith("Licence")
             and "manual" in _item_mode(it)),
            None,
        )
        if not target:
            pytest.skip("No manual Licence and Compliance item in template")
        r = requests.put(
            f"{API}/driver-activation-items/{_item_id(target)}/manual-complete",
            json={"note": "trying"},
            headers={**allocator_headers, "Content-Type": "application/json"},
            timeout=20,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_allocator_allowed_on_non_compliance_manual(
            self, allocator_headers, activation):
        target = next(
            (it for it in activation["items"]
             if not it.get("category", "").startswith("Licence")
             and it.get("category") != "Account Setup"
             and "manual" in _item_mode(it)
             and _item_status(it) not in ("complete", "override active")),
            None,
        )
        if not target:
            pytest.skip("No non-Compliance manual item available")
        r = requests.put(
            f"{API}/driver-activation-items/{_item_id(target)}/manual-complete",
            json={"note": "allocator completing induction-style item"},
            headers={**allocator_headers, "Content-Type": "application/json"},
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text


# --- Event history append-only ---

class TestEventHistoryAppendOnly:
    def _fetch(self, admin_headers, driver_id):
        r = requests.get(f"{API}/drivers/{driver_id}/activation/history",
                         headers=admin_headers, timeout=25)
        assert r.status_code == 200, r.text
        d = r.json()
        if isinstance(d, dict):
            d = d.get("events") or d.get("items") or []
        return d

    def test_history_returns_events(self, admin_headers, driver_id, activation):
        events = self._fetch(admin_headers, driver_id)
        assert isinstance(events, list)
        assert len(events) > 0
        types = {e.get("event_type") or e.get("type") or "" for e in events}
        assert any("tart" in t for t in types), f"no 'Started' event: {types}"

    def test_history_append_only_after_recalculate(self, admin_headers, driver_id):
        h1 = self._fetch(admin_headers, driver_id)
        r = requests.post(f"{API}/drivers/{driver_id}/activation/recalculate",
                          headers=admin_headers, timeout=25)
        assert r.status_code == 200, r.text
        h2 = self._fetch(admin_headers, driver_id)
        assert len(h2) >= len(h1)

        def _id(e):
            return (e.get("activation_event_id") or e.get("event_id")
                    or e.get("id") or str(e.get("created_at")))

        ids1 = [_id(e) for e in h1]
        ids2 = [_id(e) for e in h2]
        # Newest events are prepended (sorted desc). Prior events should
        # remain intact - i.e., ids1 must be a subset of ids2.
        assert set(ids1).issubset(set(ids2)), "Prior events were removed"


# --- Notification dedup on recalculate ---

class TestNotificationDedup:
    def test_recalc_twice_no_dup_notifications(self, admin_headers, driver_id):
        def _count():
            r = requests.get(
                f"{API}/notifications",
                params={"entity_type": "Driver", "entity_id": driver_id},
                headers=admin_headers,
                timeout=25,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, dict):
                data = data.get("items") or data.get("results") or data.get("notifications") or []
            return len(data)

        c0 = _count()
        if c0 is None:
            pytest.skip("notifications/all endpoint not available")
        requests.post(f"{API}/drivers/{driver_id}/activation/recalculate",
                      headers=admin_headers, timeout=25)
        time.sleep(1.5)
        requests.post(f"{API}/drivers/{driver_id}/activation/recalculate",
                      headers=admin_headers, timeout=25)
        time.sleep(1.5)
        c1 = _count()
        assert c1 - c0 <= 1, f"Duplicate notifications on repeat recalc: {c0} -> {c1}"


# --- Deactivate short-reason validation (422) ---

class TestDeactivateValidation:
    def test_deactivate_short_reason_422(self, admin_headers, driver_id):
        r = requests.post(f"{API}/drivers/{driver_id}/activation/deactivate",
                          json={"reason": "no"},
                          headers={**admin_headers, "Content-Type": "application/json"},
                          timeout=20)
        assert r.status_code in (400, 422), r.status_code


# --- Non-overridable direct API guard ---

class TestNonOverridable:
    def test_non_overridable_direct_api(self, allocator_headers, activation):
        target = next(
            (it for it in activation["items"] if it.get("item_key") in NON_OVR_KEYS),
            None,
        )
        if not target:
            pytest.skip("no non-overridable item present")
        r = requests.post(
            f"{API}/driver-activation-items/{_item_id(target)}/override-request",
            json={"reason": "please override",
                  "requested_expiry_days": 3,
                  "risk_acknowledgement": True},
            headers={**allocator_headers, "Content-Type": "application/json"},
            timeout=20,
        )
        assert r.status_code == 400, r.text


# --- Activate/Deactivate Manager+Admin gate ---

class TestActivateGate:
    def test_allocator_activate_403(self, allocator_headers, driver_id):
        r = requests.post(f"{API}/drivers/{driver_id}/activation/activate",
                          json={"reason": "attempt", "set_driver_status_active": True},
                          headers={**allocator_headers, "Content-Type": "application/json"},
                          timeout=20)
        assert r.status_code == 403, r.text

    def test_allocator_deactivate_403(self, allocator_headers, driver_id):
        r = requests.post(f"{API}/drivers/{driver_id}/activation/deactivate",
                          json={"reason": "attempt deactivate"},
                          headers={**allocator_headers, "Content-Type": "application/json"},
                          timeout=20)
        assert r.status_code == 403, r.text
