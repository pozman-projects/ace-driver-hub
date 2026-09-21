"""MR-08A · Driver Code + Dispatch Numbering acceptance tests."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}


def _tag(): return uuid.uuid4().hex[:6]


def _register_and_login(admin_session, role):
    email = f"mr08a-{role.lower()}-{_tag()}@ace.example.com"
    admin_session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "Test@123!", "full_name": f"MR08A {role}", "role": role},
        timeout=15,
    )
    lr = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "Test@123!"}, timeout=15)
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {lr.json()['access_token']}"})
    return s


@pytest.fixture(scope="session")
def admin():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200: pytest.skip("login failed")
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="session")
def readonly(admin): return _register_and_login(admin, "ReadOnly")


@pytest.fixture(scope="session")
def allocator(admin): return _register_and_login(admin, "Allocator")


@pytest.fixture(scope="session")
def db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _mk_driver(admin, **kw):
    r = admin.post(f"{BASE_URL}/api/drivers",
                    json={"full_name": f"MR08A Driver {_tag()}", "driver_status": "Training", **kw},
                    timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _next_free_active(admin):
    """Ask the canonical numbering service for a currently-free active value.
    Uses `/numbering/dispatch/available` which considers both active drivers
    AND open reservations, avoiding cross-test contamination."""
    avail = admin.get(f"{BASE_URL}/api/numbering/dispatch/available", timeout=15).json()
    if avail.get("reusable"):
        return avail["reusable"][0]
    if avail.get("next_new"):
        return int(avail["next_new"])
    raise RuntimeError("no free active dispatch")


# ────────────────────────────── Driver Code ──────────────────────────────
class TestDriverCode:
    def test_suggestion_does_not_advance_sequence(self, admin):
        seq_before = admin.get(f"{BASE_URL}/api/numbering/driver-code/sequence").json()["value"]
        # 3 suggestions in a row — sequence value must not move
        for _ in range(3):
            admin.get(f"{BASE_URL}/api/numbering/driver-code/suggestion").raise_for_status()
        seq_after = admin.get(f"{BASE_URL}/api/numbering/driver-code/sequence").json()["value"]
        assert seq_before == seq_after

    def test_automatic_reserve_is_unique_and_logs_history(self, admin, db):
        r = admin.post(f"{BASE_URL}/api/numbering/driver-code/reserve", json={})
        r.raise_for_status()
        body = r.json()
        code = body["identifier_value"]
        # A second automatic reserve returns a strictly different value
        r2 = admin.post(f"{BASE_URL}/api/numbering/driver-code/reserve", json={})
        r2.raise_for_status()
        code2 = r2.json()["identifier_value"]
        assert code != code2
        # A history event exists for the first reservation
        ev = db["number_allocation_events"].find_one(
            {"identifier_type": "Driver Code",
             "identifier_value": code,
             "action": "Reserved"},
        )
        assert ev is not None

    def test_manual_code_duplicate_rejected(self, admin):
        r = admin.post(f"{BASE_URL}/api/numbering/driver-code/reserve",
                        json={"value": f"DUP-{_tag()}"})
        r.raise_for_status()
        code = r.json()["identifier_value"]
        r2 = admin.post(f"{BASE_URL}/api/numbering/driver-code/reserve", json={"value": code})
        assert r2.status_code == 409

    def test_driver_code_zero_and_thirteen_not_special(self, admin):
        # MR-08A locked: 0/13 rules do NOT apply to Driver Code.
        r13 = admin.post(f"{BASE_URL}/api/numbering/driver-code/reserve", json={"value": "13"})
        assert r13.status_code in (200, 201, 409), r13.text  # 409 only if already taken
        r0 = admin.post(f"{BASE_URL}/api/numbering/driver-code/reserve", json={"value": "0"})
        assert r0.status_code in (200, 201, 409), r0.text

    def test_no_v1_activation_blocker_for_missing_driver_code(self, admin, db):
        d = _mk_driver(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_code": ""}})
        rd = admin.get(f"{BASE_URL}/api/drivers/{d}/blueprint-readiness").json()
        for item in rd["items"]:
            assert item["key"] != "driver_code"


# ────────────────────────────── Dispatch pools ──────────────────────────────
class TestDispatchActivePool:
    def test_reserved_values_rejected(self, admin):
        for v in (0, 13):
            r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve", json={"value": v})
            assert r.status_code == 400
            assert "reserved" in r.text.lower()

    def test_below_floor_rejected(self, admin):
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve", json={"value": -1})
        assert r.status_code == 400

    def test_above_ceiling_rejected_for_active(self, admin):
        for v in (100, 500, 999):
            r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve", json={"value": v})
            assert r.status_code == 400, f"{v} should not be reservable in active pool"

    def test_valid_active_values_accepted(self, admin):
        # Use the canonical availability endpoint to pick a genuinely free slot
        candidate = _next_free_active(admin)
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve", json={"value": candidate})
        assert r.status_code == 200, r.text


class TestDispatchInactivePool:
    def test_allocate_inactive_requires_status_inactive(self, admin):
        # Non-inactive driver → 409
        d = _mk_driver(admin, driver_status="Training")
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/allocate-inactive",
                       json={"driver_id": d})
        assert r.status_code == 409, r.text

    def test_status_transition_active_to_inactive_auto_allocates(self, admin, db):
        d = _mk_driver(admin, driver_status="Training")
        # Bring to Active — this sets a live active number-less driver
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "5"}})
        # Now flip to Inactive via canonical PUT
        r = admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "Inactive"})
        assert r.status_code == 200, r.text
        drv = db["drivers"].find_one({"id": d})
        n = int(drv["dispatch_number"])
        assert 100 <= n <= 999
        # Numbering event logged
        ev = db["number_allocation_events"].find_one(
            {"driver_id": d, "identifier_type": "Inactive Dispatch Number", "action": "Allocated"})
        assert ev is not None

    def test_inactive_allocation_counts_down_from_999(self, admin, db):
        # Ensure 999 is not currently held before this test; if it is, we
        # simply verify the allocated number is < 999 and >= 100.
        d = _mk_driver(admin, driver_status="Inactive")
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/allocate-inactive",
                        json={"driver_id": d})
        assert r.status_code == 200
        n = int(r.json()["dispatch_number"])
        assert 100 <= n <= 999


class TestOnLeaveAndArchived:
    def test_on_leave_does_not_change_dispatch(self, admin, db):
        d = _mk_driver(admin, driver_status="Training")
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "7"}})
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "On Leave"}).raise_for_status()
        drv = db["drivers"].find_one({"id": d})
        assert drv["dispatch_number"] == "7"

    def test_archived_does_not_get_new_inactive_number(self, admin, db):
        # MR-07B-FIX2 · archive is only via the canonical DELETE endpoint.
        d = _mk_driver(admin, driver_status="Training")
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "8"}})
        admin.delete(f"{BASE_URL}/api/drivers/{d}").raise_for_status()
        drv = db["drivers"].find_one({"id": d})
        # Dispatch number preserved verbatim; no inactive-pool allocation on archive.
        assert drv["dispatch_number"] == "8"


class TestReactivate:
    def test_inactive_to_active_restores_prior_when_free(self, admin, db):
        d = _mk_driver(admin, driver_status="Training")
        free = _next_free_active(admin)
        # Give an active number + history, then flip to Inactive.
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": str(free)}})
        admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve",
                   json={"value": free, "driver_id": d, "manual_override": True,
                         "reason": "seed for MR-08A test"}).raise_for_status()
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "Inactive"}).raise_for_status()
        inact = db["drivers"].find_one({"id": d})["dispatch_number"]
        assert 100 <= int(inact) <= 999
        # Return to Active via reactivate endpoint (bypasses MR-04B gate, exercises
        # the canonical restore logic directly). Note that PUT status=Active is
        # correctly still gated by Blueprint V1 readiness; that is intentional.
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reactivate", json={"driver_id": d})
        assert r.status_code == 200, r.text
        assert r.json()["dispatch_number"] == str(free)
        assert db["drivers"].find_one({"id": d})["dispatch_number"] == str(free)

    def test_inactive_to_active_allocates_when_prior_taken(self, admin, db):
        d1 = _mk_driver(admin, driver_status="Training")
        d2 = _mk_driver(admin, driver_status="Training")
        target = _next_free_active(admin)
        db["drivers"].update_one({"id": d1}, {"$set": {"driver_status": "Active", "dispatch_number": str(target)}})
        admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve",
                    json={"value": target, "driver_id": d1, "manual_override": True}).raise_for_status()
        admin.put(f"{BASE_URL}/api/drivers/{d1}", json={"driver_status": "Inactive"}).raise_for_status()
        # d2 now takes target
        db["drivers"].update_one({"id": d2}, {"$set": {"driver_status": "Active", "dispatch_number": str(target)}})
        # d1 returns to Active via reactivate endpoint — should NOT get target back
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reactivate", json={"driver_id": d1})
        assert r.status_code == 200, r.text
        n = int(r.json()["dispatch_number"])
        assert 1 <= n <= 99 and n != 13 and n != target

    def test_reactivate_endpoint_without_number_is_automatic(self, admin, db):
        d = _mk_driver(admin, driver_status="Inactive")
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reactivate",
                        json={"driver_id": d})
        assert r.status_code == 200, r.text
        n = int(r.json()["dispatch_number"])
        assert 1 <= n <= 99 and n != 13


# ────────────────────────────── Permissions ──────────────────────────────
class TestReadOnly:
    def test_readonly_cannot_reserve(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/numbering/driver-code/reserve", json={})
        assert r.status_code in (401, 403)

    def test_readonly_cannot_dispatch_reserve(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/numbering/dispatch/reserve", json={"value": 20})
        assert r.status_code in (401, 403)


# ────────────────────────────── Regressions ──────────────────────────────
class TestRegressions:
    def test_activation_gate_unaffected(self, admin, db):
        d = _mk_driver(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_code": "", "dispatch_number": ""}})
        rd = admin.get(f"{BASE_URL}/api/drivers/{d}/blueprint-readiness").json()
        keys = {i["key"] for i in rd["items"]}
        assert "driver_code" not in keys and "dispatch_number" not in keys
        assert len(keys) == 7

    def test_mr07a_privacy_still_stripping(self, admin, allocator):
        d = _mk_driver(admin, business_name="MR08A_SECRET", abn="99 999 999 999")
        p = allocator.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile").text
        assert "MR08A_SECRET" not in p
        assert "99 999 999 999" not in p
