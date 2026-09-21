"""MR-08A-FIX · Numbering reservation lifecycle + status transition integrity + performed_at ordering."""
from __future__ import annotations

import os
import uuid
import time
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}


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
                   json={"full_name": f"MR08A-FIX {_tag()}", "driver_status": "Training", **kw},
                   timeout=15)
    r.raise_for_status()
    return r.json()["id"]


def _next_free_active(admin):
    avail = admin.get(f"{BASE_URL}/api/numbering/dispatch/available", timeout=15).json()
    if avail.get("reusable"): return avail["reusable"][0]
    return int(avail["next_new"])


# ── Defect 1 · Reservation lifecycle ─────────────────────────────────────
class TestReservationConsume:
    def test_driver_code_reserve_consume_marks_consumed(self, admin, db):
        d = _mk_driver(admin)
        r = admin.post(f"{BASE_URL}/api/numbering/driver-code/reserve", json={})
        r.raise_for_status()
        res = r.json()
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_code": res["identifier_value"]}).raise_for_status()
        admin.post(f"{BASE_URL}/api/numbering/driver-code/consume",
                   json={"reservation_id": res["reservation_id"], "driver_id": d}).raise_for_status()
        row = db["dispatch_number_reservations"].find_one({"reservation_id": res["reservation_id"]})
        assert row["status"] == "Consumed", row
        ev = db["number_allocation_events"].find_one(
            {"identifier_value": res["identifier_value"], "action": "Allocated"})
        assert ev is not None

    def test_dispatch_reserve_consume_marks_consumed(self, admin, db):
        d = _mk_driver(admin)
        n = _next_free_active(admin)
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve", json={"value": n, "driver_id": d})
        r.raise_for_status()
        res = r.json()
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"dispatch_number": res["dispatch_number"]}).raise_for_status()
        admin.post(f"{BASE_URL}/api/numbering/dispatch/consume",
                   json={"reservation_id": res["reservation_id"], "driver_id": d}).raise_for_status()
        row = db["dispatch_number_reservations"].find_one({"reservation_id": res["reservation_id"]})
        assert row["status"] == "Consumed"
        # Canonical Allocated event exists
        ev = db["number_allocation_events"].find_one(
            {"driver_id": d, "identifier_type": "Active Dispatch Number",
             "identifier_value": str(n), "action": "Allocated"})
        assert ev is not None

    def test_release_restores_open_state(self, admin, db):
        d = _mk_driver(admin)
        n = _next_free_active(admin)
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve", json={"value": n, "driver_id": d})
        rid = r.json()["reservation_id"]
        admin.post(f"{BASE_URL}/api/numbering/dispatch/release",
                   json={"reservation_id": rid}).raise_for_status()
        row = db["dispatch_number_reservations"].find_one({"reservation_id": rid})
        assert row["status"] == "Released"


# ── Defect 2 · Status transition integrity ────────────────────────────────
class TestStatusTransitionIntegrity:
    def test_active_to_inactive_atomic_both_change(self, admin, db):
        d = _mk_driver(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "5"}})
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "Inactive"}).raise_for_status()
        drv = db["drivers"].find_one({"id": d})
        assert drv["driver_status"] == "Inactive"
        assert 100 <= int(drv["dispatch_number"]) <= 999

    def test_inactive_allocation_failure_rolls_back_status(self, admin, db):
        """When no inactive slot is available, transition to Inactive must
        return 409 and the driver must remain in its prior status/dispatch."""
        d = _mk_driver(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "6"}})
        # Fill entire inactive pool by inserting synthetic driver rows
        pool_ids = []
        for n in range(100, 1000):
            pid = f"pool-{_tag()}-{n}"
            db["drivers"].insert_one({
                "id": pid, "full_name": f"pool-{n}",
                "driver_status": "Inactive", "dispatch_number": str(n),
                "is_archived": False, "created_at": datetime.now(timezone.utc).isoformat(),
            })
            pool_ids.append(pid)
        try:
            r = admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "Inactive"})
            assert r.status_code == 409, r.text
            drv = db["drivers"].find_one({"id": d})
            assert drv["driver_status"] == "Active"
            assert drv["dispatch_number"] == "6"
        finally:
            db["drivers"].delete_many({"id": {"$in": pool_ids}})

    def test_active_restore_failure_rolls_back_status(self, admin, db):
        """When Inactive→Active but no active slot is free, must return 409
        and leave the driver Inactive with its 999-down number."""
        d = _mk_driver(admin)
        # Prepare an inactive driver with an inactive number
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "9"}})
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "Inactive"}).raise_for_status()
        inactive_num = db["drivers"].find_one({"id": d})["dispatch_number"]
        # Fill entire active pool (1..99 excluding 13)
        pool_ids = []
        for n in list(range(1, 100)):
            if n == 13: continue
            pid = f"pool-a-{_tag()}-{n}"
            db["drivers"].insert_one({
                "id": pid, "full_name": f"pool-a-{n}",
                "driver_status": "Active", "dispatch_number": str(n),
                "is_archived": False, "created_at": datetime.now(timezone.utc).isoformat(),
            })
            pool_ids.append(pid)
        try:
            r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reactivate",
                           json={"driver_id": d})
            assert r.status_code == 409, r.text
            drv = db["drivers"].find_one({"id": d})
            assert drv["driver_status"] == "Inactive"
            assert drv["dispatch_number"] == inactive_num
        finally:
            db["drivers"].delete_many({"id": {"$in": pool_ids}})

    def test_normal_inactive_to_active_via_reactivate(self, admin, db):
        d = _mk_driver(admin)
        # Ready driver? we bypass to Active via db then flip to Inactive via canonical
        target = _next_free_active(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active",
                                                       "dispatch_number": str(target)}})
        admin.post(f"{BASE_URL}/api/numbering/dispatch/reserve",
                   json={"value": target, "driver_id": d, "manual_override": True}).raise_for_status()
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "Inactive"}).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reactivate", json={"driver_id": d})
        assert r.status_code == 200
        assert r.json()["dispatch_number"] == str(target)


# ── Defect 3 · performed_at ordering ─────────────────────────────────────
class TestPerformedAtOrdering:
    def test_find_last_active_uses_performed_at(self, admin, db):
        d = _mk_driver(admin)
        # Pick TWO currently-free active values so restore can pick one
        # deterministically. The higher-performed_at event wins.
        used = {int(x.get("dispatch_number") or 0)
                for x in db["drivers"].find({"is_archived": {"$ne": True}},
                                              {"dispatch_number": 1})}
        free = [n for n in range(1, 100) if n != 13 and n not in used]
        older_n, newer_n = str(free[0]), str(free[1])
        db["number_allocation_events"].insert_many([
            {
                "allocation_event_id": f"ev-old-{_tag()}",
                "identifier_type": "Active Dispatch Number",
                "identifier_value": older_n,
                "action": "Allocated",
                "performed_at": "2020-01-01T00:00:00+00:00",
                "created_at": "2099-01-01T00:00:00+00:00",  # opposite order
                "driver_id": d,
                "actor_email": "seed",
            },
            {
                "allocation_event_id": f"ev-new-{_tag()}",
                "identifier_type": "Active Dispatch Number",
                "identifier_value": newer_n,
                "action": "Allocated",
                "performed_at": "2024-06-01T00:00:00+00:00",
                "created_at": "2000-01-01T00:00:00+00:00",
                "driver_id": d,
                "actor_email": "seed",
            },
        ])
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Inactive",
                                                       "dispatch_number": "555"}})
        r = admin.post(f"{BASE_URL}/api/numbering/dispatch/reactivate", json={"driver_id": d})
        assert r.status_code == 200, r.text
        # Restored value must be the newer-by-performed_at, not the older or auto-allocated
        assert r.json()["dispatch_number"] == newer_n


# ── Regressions ──────────────────────────────────────────────────────────
class TestRegressions:
    def test_on_leave_no_numbering(self, admin, db):
        d = _mk_driver(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "11"}})
        admin.put(f"{BASE_URL}/api/drivers/{d}", json={"driver_status": "On Leave"}).raise_for_status()
        drv = db["drivers"].find_one({"id": d})
        assert drv["dispatch_number"] == "11"

    def test_archived_no_inactive(self, admin, db):
        # MR-07B-FIX2 · archive is only via the canonical DELETE endpoint.
        d = _mk_driver(admin)
        db["drivers"].update_one({"id": d}, {"$set": {"driver_status": "Active", "dispatch_number": "12"}})
        admin.delete(f"{BASE_URL}/api/drivers/{d}").raise_for_status()
        drv = db["drivers"].find_one({"id": d})
        assert drv["dispatch_number"] == "12"

    def test_activation_gate_unaffected(self, admin, db):
        d = _mk_driver(admin)
        rd = admin.get(f"{BASE_URL}/api/drivers/{d}/blueprint-readiness").json()
        keys = {i["key"] for i in rd["items"]}
        assert "driver_code" not in keys and "dispatch_number" not in keys


# ── Frontend UX guards ────────────────────────────────────────────────────
class TestFrontendUX:
    def _read(self):
        from pathlib import Path
        return Path("/app/frontend/src/components/driver-cc/DriverSetupCard.jsx").read_text()

    def test_dispatch_input_disabled_when_target_inactive(self):
        src = self._read()
        assert 'disabled={form.driver_status === "Inactive"}' in src
        assert "dispatch-inactive-hint" in src

    def test_reactivate_does_not_reserve_inactive_number(self):
        src = self._read()
        # The guard variable that avoids reserving during status auto-flows
        assert "statusTransitionAutoDispatch" in src
        # And the reactivate hint UI
        assert "dispatch-reactivate-hint" in src

    def test_consume_calls_are_present_after_put(self):
        src = self._read()
        assert "/numbering/driver-code/consume" in src
        assert "/numbering/dispatch/consume" in src

    def test_release_calls_are_present_for_failure(self):
        src = self._read()
        assert "/numbering/driver-code/release" in src
        assert "/numbering/dispatch/release" in src
