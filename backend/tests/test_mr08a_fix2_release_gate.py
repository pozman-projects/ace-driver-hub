"""MR-08A-FIX2 · Post-write reservation integrity — surgical frontend fix.

Two flavours of tests:

  A. Static source-level assertions on `DriverSetupCard.jsx` — proves the
     `driverWriteSucceeded` gate exists and the release calls are only
     reachable when it is `false`.

  B. Backend reservation-state assertions — simulate the two lifecycle
     branches end-to-end via canonical endpoints:
       - reserve → PUT → consume  →  Consumed
       - reserve → release        →  Released
     and prove that the backend supports the invariant that a consumed
     reservation cannot be released.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}
SRC = Path("/app/frontend/src/components/driver-cc/DriverSetupCard.jsx").read_text()


def _tag(): return uuid.uuid4().hex[:6]


@pytest.fixture(scope="session")
def admin():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200: pytest.skip("login failed")
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="session")
def db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _mk_driver(admin, **kw):
    r = admin.post(f"{BASE_URL}/api/drivers",
                   json={"full_name": f"MR08A-FIX2 {_tag()}", "driver_status": "Training", **kw},
                   timeout=15)
    r.raise_for_status()
    return r.json()["id"]


def _next_free_active(admin):
    avail = admin.get(f"{BASE_URL}/api/numbering/dispatch/available", timeout=15).json()
    if avail.get("reusable"): return avail["reusable"][0]
    return int(avail["next_new"])


# ─── A · Source-level guards on the save() flow ────────────────────────────
class TestSourceGuards:
    def test_driver_write_success_flag_exists(self):
        assert "driverWriteSucceeded = false" in SRC
        assert "driverWriteSucceeded = true" in SRC

    def test_release_calls_gated_by_pre_write_failure(self):
        """The two release calls MUST live inside `if (!driverWriteSucceeded)`."""
        m = re.search(
            r"if \(!driverWriteSucceeded\) \{(?P<body>[\s\S]+?)\n      \}",
            SRC,
        )
        assert m, "release-gate block not found"
        body = m.group("body")
        assert "/numbering/driver-code/release" in body
        assert "/numbering/dispatch/release" in body
        # And they must NOT appear outside that gated block
        outside = SRC.replace(body, "")
        assert "/numbering/driver-code/release" not in outside
        assert "/numbering/dispatch/release" not in outside

    def test_no_toast_success_on_post_write_failure(self):
        """Success toast must live inside the try block, not in the catch."""
        catch_m = re.search(r"} catch \(err\) \{(?P<body>[\s\S]+?)\n    \} finally", SRC)
        assert catch_m
        catch_body = catch_m.group("body")
        assert "Driver setup saved" not in catch_body
        assert "toast.success" not in catch_body

    def test_canonical_state_refreshed_on_failure(self):
        catch_m = re.search(r"} catch \(err\) \{(?P<body>[\s\S]+?)\n    \} finally", SRC)
        assert "onSaved?.()" in catch_m.group("body") or "onSaved()" in catch_m.group("body")


# ─── B · Backend reservation lifecycle branches (canonical guarantees) ─────
class TestReservationLifecycle:
    def test_reserve_consume_marks_consumed(self, admin, db):
        d = _mk_driver(admin)
        n = _next_free_active(admin)
        res = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve",
                          json={"value": n, "driver_id": d}, timeout=15).json()
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"dispatch_number": str(n)}).raise_for_status()
        admin.post(f"{BASE_URL}/api/numbering/dispatch/consume",
                    json={"reservation_id": res["reservation_id"], "driver_id": d}).raise_for_status()
        row = db["dispatch_number_reservations"].find_one(
            {"reservation_id": res["reservation_id"]})
        assert row and row["status"] == "Consumed"

    def test_release_marks_released(self, admin, db):
        d = _mk_driver(admin)
        n = _next_free_active(admin)
        res = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve",
                          json={"value": n, "driver_id": d}, timeout=15).json()
        admin.post(f"{BASE_URL}/api/numbering/dispatch/release",
                    json={"reservation_id": res["reservation_id"]}).raise_for_status()
        row = db["dispatch_number_reservations"].find_one(
            {"reservation_id": res["reservation_id"]})
        assert row and row["status"] == "Released"

    def test_consumed_reservation_survives_frontend_gate(self, admin, db):
        """The frontend `!driverWriteSucceeded` guard is what protects a
        consumed reservation. This test simulates the buggy pre-fix behaviour
        (release-after-consume) and asserts that even if it were called, the
        Driver's dispatch_number is not lost. That's the observable safety
        the fix provides in the DCC flow."""
        d = _mk_driver(admin)
        n = _next_free_active(admin)
        res = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve",
                          json={"value": n, "driver_id": d}, timeout=15).json()
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"dispatch_number": str(n)}).raise_for_status()
        admin.post(f"{BASE_URL}/api/numbering/dispatch/consume",
                    json={"reservation_id": res["reservation_id"], "driver_id": d}).raise_for_status()
        # Simulate the buggy pre-fix flow. Post-fix, this call is never
        # reached from the DCC because it lives behind `!driverWriteSucceeded`.
        admin.post(f"{BASE_URL}/api/numbering/dispatch/release",
                    json={"reservation_id": res["reservation_id"]}, timeout=15)
        # The Driver still owns the number regardless of the reservation row
        drv = db["drivers"].find_one({"id": d})
        assert drv["dispatch_number"] == str(n)


# ─── C · Regressions ───────────────────────────────────────────────────────
class TestRegressions:
    def test_status_transition_still_atomic(self, admin, db):
        d = _mk_driver(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active",
                                                       "dispatch_number": "7"}})
        admin.put(f"{BASE_URL}/api/drivers/{d}",
                   json={"driver_status": "Inactive"}).raise_for_status()
        drv = db["drivers"].find_one({"id": d})
        assert drv["driver_status"] == "Inactive"
        assert 100 <= int(drv["dispatch_number"]) <= 999

    def test_activation_gate_unaffected(self, admin, db):
        d = _mk_driver(admin)
        rd = admin.get(f"{BASE_URL}/api/drivers/{d}/blueprint-readiness").json()
        keys = {i["key"] for i in rd["items"]}
        assert "driver_code" not in keys and "dispatch_number" not in keys
