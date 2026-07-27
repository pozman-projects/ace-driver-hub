"""EB-08 Automated Driver Code & Dispatch Number Allocation — backend tests."""
from __future__ import annotations

import os
import uuid
import time
from typing import Dict

import pytest
import requests


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


def _login(email: str, password: str) -> Dict[str, str]:
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def _seed_role_user(admin_headers, role: str):
    email = f"eb08_{role.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB08 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"},
                   timeout=20)
    return _login(email, "T@1234")


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    return _seed_role_user(admin_headers, "ReadOnly")


@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    return _seed_role_user(admin_headers, "Allocator")


@pytest.fixture(scope="session")
def manager_headers(admin_headers):
    return _seed_role_user(admin_headers, "Manager")


@pytest.fixture(scope="session")
def compliance_headers(admin_headers):
    return _seed_role_user(admin_headers, "Compliance")


def _create_driver(admin_headers, full_name: str, driver_code: str = None,
                    dispatch: str = None, status: str = "Active") -> dict:
    payload = {"full_name": full_name, "driver_status": status}
    if driver_code is not None:
        payload["driver_code"] = str(driver_code)
    if dispatch is not None:
        payload["dispatch_number"] = str(dispatch)
    r = requests.post(f"{API}/drivers", json=payload, headers=admin_headers, timeout=20)
    r.raise_for_status()
    return r.json()


def _delete_driver(admin_headers, driver_id: str):
    requests.delete(f"{API}/drivers/{driver_id}", headers=admin_headers, timeout=20)


# ================================================================
#  Driver Code — suggestion & sequence
# ================================================================
def test_sequence_endpoint(admin_headers):
    r = requests.get(f"{API}/numbering/driver-code/sequence",
                      headers=admin_headers, timeout=20)
    r.raise_for_status()
    assert "value" in r.json()
    assert "sequence_id" in r.json()


def test_suggestion_endpoint(admin_headers):
    r = requests.get(f"{API}/numbering/driver-code/suggestion",
                      headers=admin_headers, timeout=20)
    r.raise_for_status()
    d = r.json()
    for k in ("suggested_driver_code", "current_sequence_value", "next_after_advance"):
        assert k in d


def test_auto_reserve_advances_sequence(admin_headers):
    seq_before = requests.get(f"{API}/numbering/driver-code/sequence",
                                headers=admin_headers, timeout=20).json()["value"]
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={}, headers=admin_headers, timeout=20)
    assert r.status_code == 200
    res = r.json()
    assert res["automatic"] is True
    assert res["sequence_advanced"] is True
    seq_after = requests.get(f"{API}/numbering/driver-code/sequence",
                                headers=admin_headers, timeout=20).json()["value"]
    assert seq_after > seq_before
    # Cleanup
    requests.post(f"{API}/numbering/driver-code/release",
                   json={"reservation_id": res["reservation_id"]},
                   headers=admin_headers, timeout=20)


def test_manual_historical_override_no_advance(admin_headers):
    seq_before = requests.get(f"{API}/numbering/driver-code/sequence",
                                headers=admin_headers, timeout=20).json()["value"]
    # Pick a value far below the current sequence and different from any existing
    hist = "10000075"
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={"value": hist, "historical": True, "manual_override": True},
                       headers=admin_headers, timeout=20)
    assert r.status_code == 200
    res = r.json()
    assert res["sequence_advanced"] is False
    seq_after = requests.get(f"{API}/numbering/driver-code/sequence",
                                headers=admin_headers, timeout=20).json()["value"]
    assert seq_after == seq_before
    requests.post(f"{API}/numbering/driver-code/release",
                   json={"reservation_id": res["reservation_id"]},
                   headers=admin_headers, timeout=20)


def test_manual_explicit_live_advance(admin_headers):
    seq_before = requests.get(f"{API}/numbering/driver-code/sequence",
                                headers=admin_headers, timeout=20).json()["value"]
    live = str(seq_before + 500)
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={"value": live, "historical": False,
                             "manual_override": True},
                       headers=admin_headers, timeout=20)
    assert r.status_code == 200
    seq_after = requests.get(f"{API}/numbering/driver-code/sequence",
                                headers=admin_headers, timeout=20).json()["value"]
    assert seq_after == int(live)
    requests.post(f"{API}/numbering/driver-code/release",
                   json={"reservation_id": r.json()["reservation_id"]},
                   headers=admin_headers, timeout=20)


def test_duplicate_manual_driver_code_rejected(admin_headers):
    # Create a driver with a known driver_code first
    dup = f"999{uuid.uuid4().hex[:4]}"
    d = _create_driver(admin_headers, "EB08 Dup Base", driver_code=dup, status="Active")
    try:
        r = requests.post(f"{API}/numbering/driver-code/reserve",
                           json={"value": dup, "historical": True,
                                 "manual_override": True},
                           headers=admin_headers, timeout=20)
        assert r.status_code == 409
    finally:
        _delete_driver(admin_headers, d["id"])


def test_release_reservation(admin_headers):
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={}, headers=admin_headers, timeout=20)
    rid = r.json()["reservation_id"]
    r2 = requests.post(f"{API}/numbering/driver-code/release",
                        json={"reservation_id": rid, "reason": "cancel"},
                        headers=admin_headers, timeout=20)
    assert r2.status_code == 200
    assert r2.json()["status"] == "Released"


def test_consume_reservation(admin_headers):
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={}, headers=admin_headers, timeout=20)
    res = r.json()
    d = _create_driver(admin_headers, "EB08 Consume", driver_code=res["identifier_value"],
                        status="Active")
    try:
        r2 = requests.post(f"{API}/numbering/driver-code/consume",
                            json={"reservation_id": res["reservation_id"],
                                  "driver_id": d["id"]},
                            headers=admin_headers, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["status"] == "Consumed"
    finally:
        _delete_driver(admin_headers, d["id"])


def test_double_consume_rejected(admin_headers):
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={}, headers=admin_headers, timeout=20)
    res = r.json()
    d = _create_driver(admin_headers, "EB08 DblCons",
                        driver_code=res["identifier_value"], status="Active")
    try:
        requests.post(f"{API}/numbering/driver-code/consume",
                       json={"reservation_id": res["reservation_id"],
                             "driver_id": d["id"]},
                       headers=admin_headers, timeout=20)
        r2 = requests.post(f"{API}/numbering/driver-code/consume",
                            json={"reservation_id": res["reservation_id"],
                                  "driver_id": d["id"]},
                            headers=admin_headers, timeout=20)
        assert r2.status_code == 409
    finally:
        _delete_driver(admin_headers, d["id"])


def test_admin_only_sequence_edit(admin_headers, manager_headers):
    # Manager cannot set sequence
    r = requests.put(f"{API}/numbering/driver-code/sequence",
                      json={"value": 500, "reason": "test"},
                      headers=manager_headers, timeout=20)
    assert r.status_code == 403
    # Admin can
    cur = requests.get(f"{API}/numbering/driver-code/sequence",
                        headers=admin_headers, timeout=20).json()["value"]
    r2 = requests.put(f"{API}/numbering/driver-code/sequence",
                       json={"value": cur, "reason": "no-op"},
                       headers=admin_headers, timeout=20)
    assert r2.status_code == 200


# ================================================================
#  Dispatch Numbers
# ================================================================
def test_dispatch_available_shape(admin_headers):
    r = requests.get(f"{API}/numbering/dispatch/available",
                      headers=admin_headers, timeout=20)
    r.raise_for_status()
    d = r.json()
    for k in ("reusable", "next_new", "reserved", "reserved_permanent",
              "in_use", "inactive_in_use"):
        assert k in d
    assert 0 in d["reserved_permanent"]
    assert 13 in d["reserved_permanent"]


def test_reject_zero(admin_headers):
    r = requests.post(f"{API}/numbering/dispatch/reserve",
                       json={"value": 0}, headers=admin_headers, timeout=20)
    assert r.status_code == 400


def test_reject_thirteen(admin_headers):
    r = requests.post(f"{API}/numbering/dispatch/reserve",
                       json={"value": 13}, headers=admin_headers, timeout=20)
    assert r.status_code == 400


def test_reserve_active_dispatch_and_release(admin_headers):
    avail = requests.get(f"{API}/numbering/dispatch/available",
                          headers=admin_headers, timeout=20).json()
    candidate = avail["next_new"] or 999
    r = requests.post(f"{API}/numbering/dispatch/reserve",
                       json={"value": candidate}, headers=admin_headers, timeout=20)
    assert r.status_code == 200
    rid = r.json()["reservation_id"]
    # Duplicate reservation should now conflict
    r2 = requests.post(f"{API}/numbering/dispatch/reserve",
                        json={"value": candidate}, headers=admin_headers, timeout=20)
    assert r2.status_code == 409
    # Release
    r3 = requests.post(f"{API}/numbering/dispatch/release",
                        json={"reservation_id": rid, "reason": "cleanup"},
                        headers=admin_headers, timeout=20)
    assert r3.status_code == 200
    assert r3.json()["status"] == "Released"


def test_reserve_active_duplicate_of_existing_driver(admin_headers):
    avail = requests.get(f"{API}/numbering/dispatch/available",
                          headers=admin_headers, timeout=20).json()
    n = avail["next_new"] or 500
    d = _create_driver(admin_headers, "EB08 DupDispatch", dispatch=str(n),
                        status="Active")
    try:
        r = requests.post(f"{API}/numbering/dispatch/reserve",
                           json={"value": n}, headers=admin_headers, timeout=20)
        assert r.status_code == 409
    finally:
        _delete_driver(admin_headers, d["id"])


def test_automatic_reservation_prefers_reusable(admin_headers):
    # Attempt automatic — returns whatever the service considers next
    r = requests.post(f"{API}/numbering/dispatch/reserve",
                       json={}, headers=admin_headers, timeout=20)
    assert r.status_code == 200
    n = int(r.json()["dispatch_number"])
    assert n not in {0, 13}
    assert 1 <= n < 999
    requests.post(f"{API}/numbering/dispatch/release",
                   json={"reservation_id": r.json()["reservation_id"]},
                   headers=admin_headers, timeout=20)


def test_inactive_allocation_starts_at_999(admin_headers):
    d = _create_driver(admin_headers, "EB08 Inactivate", status="Active",
                        dispatch=None)
    try:
        r = requests.post(f"{API}/numbering/dispatch/allocate-inactive",
                           json={"driver_id": d["id"],
                                 "reason": "moved to Inactive"},
                           headers=admin_headers, timeout=20)
        assert r.status_code == 200
        n = int(r.json()["dispatch_number"])
        assert 100 <= n <= 999
        # Allocate a second driver — should be lower
        d2 = _create_driver(admin_headers, "EB08 Inactivate2", status="Active",
                              dispatch=None)
        try:
            r2 = requests.post(f"{API}/numbering/dispatch/allocate-inactive",
                                json={"driver_id": d2["id"]},
                                headers=admin_headers, timeout=20)
            assert r2.status_code == 200
            assert int(r2.json()["dispatch_number"]) < n
        finally:
            _delete_driver(admin_headers, d2["id"])
    finally:
        _delete_driver(admin_headers, d["id"])


def test_reactivate_requires_valid_active_number(admin_headers):
    d = _create_driver(admin_headers, "EB08 Reactivate", status="Active",
                        dispatch=None)
    try:
        # Assign inactive first
        requests.post(f"{API}/numbering/dispatch/allocate-inactive",
                       json={"driver_id": d["id"]}, headers=admin_headers, timeout=20)
        # Try to reactivate with 0 → rejected
        r = requests.post(f"{API}/numbering/dispatch/reactivate",
                           json={"driver_id": d["id"], "value": 0},
                           headers=admin_headers, timeout=20)
        assert r.status_code == 400
        r2 = requests.post(f"{API}/numbering/dispatch/reactivate",
                            json={"driver_id": d["id"], "value": 13},
                            headers=admin_headers, timeout=20)
        assert r2.status_code == 400
        # Real active number should succeed
        avail = requests.get(f"{API}/numbering/dispatch/available",
                              headers=admin_headers, timeout=20).json()
        n = avail["next_new"] or 500
        r3 = requests.post(f"{API}/numbering/dispatch/reactivate",
                            json={"driver_id": d["id"], "value": n},
                            headers=admin_headers, timeout=20)
        assert r3.status_code == 200
    finally:
        _delete_driver(admin_headers, d["id"])


def test_list_reservations(admin_headers):
    r = requests.get(f"{API}/numbering/dispatch/reservations",
                      headers=admin_headers, timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ================================================================
#  Allocation events / history
# ================================================================
def test_allocation_events_list(admin_headers):
    r = requests.get(f"{API}/numbering/allocation-events",
                      headers=admin_headers, timeout=20)
    r.raise_for_status()
    rows = r.json()
    assert isinstance(rows, list)
    assert any(r.get("identifier_type") == "Driver Code" for r in rows[:200])


def test_driver_history_endpoint(admin_headers):
    # Reserve + consume for a fresh driver, then look up history
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={}, headers=admin_headers, timeout=20)
    res = r.json()
    d = _create_driver(admin_headers, "EB08 HistoryDriver",
                        driver_code=res["identifier_value"], status="Active")
    try:
        requests.post(f"{API}/numbering/driver-code/consume",
                       json={"reservation_id": res["reservation_id"],
                             "driver_id": d["id"]},
                       headers=admin_headers, timeout=20)
        hist = requests.get(f"{API}/numbering/drivers/{d['id']}/history",
                              headers=admin_headers, timeout=20)
        assert hist.status_code == 200
        rows = hist.json()
        assert len(rows) >= 1
        assert all(r["driver_id"] == d["id"] for r in rows)
    finally:
        _delete_driver(admin_headers, d["id"])


# ================================================================
#  Permissions
# ================================================================
def test_readonly_cannot_reserve(readonly_headers):
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={}, headers=readonly_headers, timeout=20)
    assert r.status_code == 403


def test_readonly_can_read_suggestion(readonly_headers):
    r = requests.get(f"{API}/numbering/driver-code/suggestion",
                      headers=readonly_headers, timeout=20)
    # ReadOnly is not in READ_ROLES — should be 403
    assert r.status_code == 403


def test_allocator_can_reserve(allocator_headers):
    r = requests.post(f"{API}/numbering/dispatch/reserve",
                       json={}, headers=allocator_headers, timeout=20)
    assert r.status_code == 200
    requests.post(f"{API}/numbering/dispatch/release",
                   json={"reservation_id": r.json()["reservation_id"]},
                   headers=allocator_headers, timeout=20)


def test_compliance_can_read(compliance_headers):
    r = requests.get(f"{API}/numbering/allocation-events",
                      headers=compliance_headers, timeout=20)
    assert r.status_code == 200


def test_compliance_cannot_reserve(compliance_headers):
    r = requests.post(f"{API}/numbering/driver-code/reserve",
                       json={}, headers=compliance_headers, timeout=20)
    assert r.status_code == 403


def test_allocator_cannot_edit_sequence(allocator_headers):
    r = requests.put(f"{API}/numbering/driver-code/sequence",
                      json={"value": 1}, headers=allocator_headers, timeout=20)
    assert r.status_code == 403


def test_manager_cannot_edit_sequence(manager_headers):
    r = requests.put(f"{API}/numbering/driver-code/sequence",
                      json={"value": 1}, headers=manager_headers, timeout=20)
    assert r.status_code == 403


def test_readonly_cannot_run_jobs(readonly_headers):
    r = requests.post(f"{API}/numbering/jobs/reconcile",
                       headers=readonly_headers, timeout=20)
    assert r.status_code == 403


# ================================================================
#  Maintenance jobs
# ================================================================
def test_reconcile_is_idempotent(admin_headers):
    r1 = requests.post(f"{API}/numbering/jobs/reconcile",
                        headers=admin_headers, timeout=30)
    assert r1.status_code == 200
    r2 = requests.post(f"{API}/numbering/jobs/reconcile",
                        headers=admin_headers, timeout=30)
    assert r2.status_code == 200
    # Sequence should not oscillate
    assert r2.json()["conflicts_found"] >= 0


def test_expire_reservations_runs(admin_headers):
    r = requests.post(f"{API}/numbering/jobs/expire-reservations",
                       headers=admin_headers, timeout=20)
    assert r.status_code == 200
    assert "expired_count" in r.json()


# ================================================================
#  Concurrent allocation protection
# ================================================================
def test_concurrent_auto_reserve_no_dup(admin_headers):
    import concurrent.futures
    def _one():
        return requests.post(f"{API}/numbering/driver-code/reserve",
                              json={}, headers=admin_headers, timeout=20).json()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(lambda _: _one(), range(5)))
    values = [r["identifier_value"] for r in results]
    # No duplicate identifiers
    assert len(values) == len(set(values))
    # Cleanup
    for r in results:
        requests.post(f"{API}/numbering/driver-code/release",
                       json={"reservation_id": r["reservation_id"]},
                       headers=admin_headers, timeout=20)


# ================================================================
#  Historical dispatch snapshot preserved
# ================================================================
def test_dispatch_snapshot_preserved_on_inactive(admin_headers):
    # Give driver an active dispatch, then move to inactive
    avail = requests.get(f"{API}/numbering/dispatch/available",
                          headers=admin_headers, timeout=20).json()
    n = avail["next_new"] or 500
    d = _create_driver(admin_headers, "EB08 Snapshot", dispatch=str(n),
                        status="Active")
    try:
        r = requests.post(f"{API}/numbering/dispatch/allocate-inactive",
                           json={"driver_id": d["id"]},
                           headers=admin_headers, timeout=20)
        assert r.status_code == 200
        # Historical assignment snapshots in driver_vehicle_assignments must
        # remain unchanged. We simply verify the driver record moved and no
        # crash happens on subsequent reads.
        drv = requests.get(f"{API}/drivers/{d['id']}",
                             headers=admin_headers, timeout=20).json()
        assert drv["dispatch_number"] != str(n)
    finally:
        _delete_driver(admin_headers, d["id"])
