"""MR-05 · Owner / Carrier / Relationship Editing — acceptance tests.

Covers the acceptance items A–P (backend-verifiable) plus regression checks
V (MR-04 activation preservation) and W (MR-07A privacy preservation).
UI-only items (U — DCC 3x3 layout, N — DCC visual) are covered by frontend
smoke render tests in a separate file.
"""
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
    email = f"mr05-{role.lower()}-{_tag()}@ace.example.com"
    admin_session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "Test@123!", "full_name": f"MR05 {role}", "role": role},
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
def readonly(admin):
    return _register_and_login(admin, "ReadOnly")


@pytest.fixture(scope="session")
def allocator(admin):
    return _register_and_login(admin, "Allocator")


@pytest.fixture(scope="session")
def db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _mk_driver(admin, **kw):
    r = admin.post(f"{BASE_URL}/api/drivers",
                    json={"full_name": f"MR05 Driver {_tag()}", "driver_status": "Training", **kw},
                    timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _mk_owner(admin, **kw):
    r = admin.post(f"{BASE_URL}/api/owners",
                    json={"name": f"MR05 Owner {_tag()}", "owner_type": "Business",
                          "mobile_number": "0400 000 111", "email": f"o{_tag()}@ex.com", **kw},
                    timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _mk_vehicle(admin, **kw):
    r = admin.post(f"{BASE_URL}/api/vehicles",
                    json={"registration_number": f"V{_tag().upper()}",
                          "vehicle_type": "Prime Mover",
                          "ownership_model": "Owned",
                          "carrier_configuration": "Two Deck",
                          "vehicle_status": "Active", **kw}, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _mk_equipment(admin, equipment_type, **kw):
    r = admin.post(f"{BASE_URL}/api/equipment",
                    json={"equipment_number": f"E{_tag().upper()}",
                          "equipment_type": equipment_type,
                          "ownership_model": "Owned",
                          "equipment_status": "Available", **kw}, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _link_owner(admin, driver_id, owner_id):
    r = admin.post(f"{BASE_URL}/api/driver-owner-relationships",
                    json={"driver_id": driver_id, "owner_id": owner_id, "is_current": True,
                          "start_date": datetime.now(timezone.utc).date().isoformat()}, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _assign_vehicle(admin, driver_id, vehicle_id):
    r = admin.post(f"{BASE_URL}/api/driver-vehicle-assignments",
                    json={"driver_id": driver_id, "vehicle_id": vehicle_id,
                          "is_primary": True, "is_active": True}, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


# ─── Aggregator exposes canonical current relationship data (Part 18) ───────
class TestAggregatorRelationshipPayload:
    def test_owner_and_vehicle_visible(self, admin):
        d = _mk_driver(admin); o = _mk_owner(admin); v = _mk_vehicle(admin)
        _link_owner(admin, d, o["id"]); _assign_vehicle(admin, d, v["id"])
        p = admin.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert p["owner"]["id"] == o["id"]
        assert p["owner_relationship"]["is_current"] is True
        assert p["vehicle"]["id"] == v["id"]

    def test_current_tray_and_trailer_couplings_exposed(self, admin):
        d = _mk_driver(admin); v = _mk_vehicle(admin)
        _assign_vehicle(admin, d, v["id"])
        tray = _mk_equipment(admin, "Tray")
        trailer = _mk_equipment(admin, "Trailer")
        admin.post(f"{BASE_URL}/api/vehicle-equipment-couplings",
                   json={"vehicle_id": v["id"], "equipment_id": tray["id"], "role": "Tray", "is_active": True},
                   timeout=15).raise_for_status()
        admin.post(f"{BASE_URL}/api/vehicle-equipment-couplings",
                   json={"vehicle_id": v["id"], "equipment_id": trailer["id"], "role": "Trailer", "is_active": True},
                   timeout=15).raise_for_status()
        p = admin.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert p["tray_equipment"]["id"] == tray["id"]
        assert p["trailer_equipment"]["id"] == trailer["id"]
        # Ownership canonical values only
        assert p["tray_equipment"]["ownership_model"] in ("Owned", "Leased", "Sub-Contracted", "Other")

    def test_historical_owner_not_current(self, admin):
        d = _mk_driver(admin); o1 = _mk_owner(admin); o2 = _mk_owner(admin)
        _link_owner(admin, d, o1["id"])
        _link_owner(admin, d, o2["id"])  # new becomes current, o1 auto-closed
        p = admin.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert p["owner"]["id"] == o2["id"], p["owner"]


# ─── Owner mutation via canonical endpoint ──────────────────────────────────
class TestOwnerContactCanonical:
    def test_owner_edit_reflects_in_aggregator(self, admin):
        d = _mk_driver(admin); o = _mk_owner(admin)
        _link_owner(admin, d, o["id"])
        admin.put(f"{BASE_URL}/api/owners/{o['id']}",
                  json={"mobile_number": "0499 111 222", "email": "shared-test@ex.com"}, timeout=15)
        p = admin.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert p["owner"]["mobile_number"] == "0499 111 222"
        assert p["owner"]["email"] == "shared-test@ex.com"
        # No leakage of duplicate owner_* fields onto Driver record
        assert "owner_mobile" not in p["driver"]
        assert "owner_email" not in p["driver"]

    def test_shared_owner_reflects_on_multiple_drivers(self, admin):
        o = _mk_owner(admin)
        d1 = _mk_driver(admin); d2 = _mk_driver(admin)
        _link_owner(admin, d1, o["id"]); _link_owner(admin, d2, o["id"])
        admin.put(f"{BASE_URL}/api/owners/{o['id']}", json={"mobile_number": "0400 333 444"}, timeout=15)
        p1 = admin.get(f"{BASE_URL}/api/drivers/{d1}/command-centre-profile", timeout=15).json()
        p2 = admin.get(f"{BASE_URL}/api/drivers/{d2}/command-centre-profile", timeout=15).json()
        assert p1["owner"]["mobile_number"] == "0400 333 444"
        assert p2["owner"]["mobile_number"] == "0400 333 444"


# ─── ReadOnly cannot mutate ─────────────────────────────────────────────────
class TestReadOnlyBlocked:
    def test_readonly_cannot_create_owner(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/owners",
                          json={"name": "RO created", "owner_type": "Business"}, timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_readonly_cannot_update_owner(self, admin, readonly):
        o = _mk_owner(admin)
        r = readonly.put(f"{BASE_URL}/api/owners/{o['id']}", json={"mobile_number": "0"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_readonly_cannot_reassign_vehicle(self, admin, readonly):
        d = _mk_driver(admin); v = _mk_vehicle(admin)
        r = readonly.post(f"{BASE_URL}/api/driver-vehicle-assignments/reassign",
                           json={"driver_id": d, "vehicle_id": v["id"], "is_primary": True}, timeout=15)
        assert r.status_code in (401, 403)

    def test_readonly_cannot_couple_equipment(self, admin, readonly):
        v = _mk_vehicle(admin); eq = _mk_equipment(admin, "Tray")
        r = readonly.post(f"{BASE_URL}/api/vehicle-equipment-couplings",
                           json={"vehicle_id": v["id"], "equipment_id": eq["id"], "role": "Tray", "is_active": True},
                           timeout=15)
        assert r.status_code in (401, 403)


# ─── Vehicle reassignment history ────────────────────────────────────────────
class TestVehicleReassignHistory:
    def test_reassign_preserves_history_and_switches_current(self, admin, db):
        d = _mk_driver(admin); v1 = _mk_vehicle(admin); v2 = _mk_vehicle(admin)
        _assign_vehicle(admin, d, v1["id"])
        admin.post(f"{BASE_URL}/api/driver-vehicle-assignments/reassign",
                   json={"driver_id": d, "vehicle_id": v2["id"], "is_primary": True,
                         "start_date": datetime.now(timezone.utc).date().isoformat()},
                   timeout=15).raise_for_status()
        rows = list(db["driver_vehicle_assignments"].find({"driver_id": d}))
        assert len(rows) == 2, rows
        current = [r for r in rows if r.get("is_active") and r.get("is_primary")]
        assert len(current) == 1
        assert current[0]["vehicle_id"] == v2["id"]
        # Old assignment retained but inactive
        historical = [r for r in rows if r["vehicle_id"] == v1["id"]]
        assert historical and not historical[0].get("is_active")


# ─── Tray/Trailer type validation & one-current rule ────────────────────────
class TestCouplingRules:
    def test_wrong_equipment_type_blocked(self, admin):
        v = _mk_vehicle(admin); trailer_eq = _mk_equipment(admin, "Trailer")
        r = admin.post(f"{BASE_URL}/api/vehicle-equipment-couplings",
                       json={"vehicle_id": v["id"], "equipment_id": trailer_eq["id"], "role": "Tray", "is_active": True},
                       timeout=15)
        assert r.status_code == 400
        assert "Tray" in r.text

    def test_two_current_trays_blocked_without_reassign(self, admin):
        v = _mk_vehicle(admin); t1 = _mk_equipment(admin, "Tray"); t2 = _mk_equipment(admin, "Tray")
        admin.post(f"{BASE_URL}/api/vehicle-equipment-couplings",
                   json={"vehicle_id": v["id"], "equipment_id": t1["id"], "role": "Tray", "is_active": True},
                   timeout=15).raise_for_status()
        r2 = admin.post(f"{BASE_URL}/api/vehicle-equipment-couplings",
                        json={"vehicle_id": v["id"], "equipment_id": t2["id"], "role": "Tray", "is_active": True},
                        timeout=15)
        assert r2.status_code == 409

    def test_coupling_reassign_preserves_history(self, admin, db):
        v = _mk_vehicle(admin); t1 = _mk_equipment(admin, "Tray"); t2 = _mk_equipment(admin, "Tray")
        c1 = admin.post(f"{BASE_URL}/api/vehicle-equipment-couplings",
                        json={"vehicle_id": v["id"], "equipment_id": t1["id"], "role": "Tray", "is_active": True},
                        timeout=15).json()
        admin.post(f"{BASE_URL}/api/vehicle-equipment-couplings/reassign",
                   json={"vehicle_id": v["id"], "equipment_id": t2["id"], "role": "Tray"},
                   timeout=15).raise_for_status()
        rows = list(db["vehicle_equipment_couplings"].find({"vehicle_id": v["id"], "role": "Tray"}))
        assert len(rows) == 2
        active = [r for r in rows if r.get("is_active")]
        assert len(active) == 1 and active[0]["equipment_id"] == t2["id"]
        # Old coupling retained (not deleted)
        old = next(r for r in rows if r["id"] == c1["id"])
        assert old.get("is_active") is False


# ─── Vehicle canonical lifecycle values only (Part 10) ──────────────────────
class TestCanonicalLifecycle:
    def test_vehicle_update_rejects_deprecated(self, admin):
        v = _mk_vehicle(admin)
        for bad in ("Inactive", "Maintenance"):
            r = admin.put(f"{BASE_URL}/api/vehicles/{v['id']}", json={"vehicle_status": bad}, timeout=15)
            assert r.status_code >= 400, f"Deprecated status '{bad}' was accepted"


# ─── MR-04 activation regression ────────────────────────────────────────────
class TestMR04Regression:
    def test_relationship_change_does_not_add_activation_blockers(self, admin):
        d = _mk_driver(admin)
        rd = admin.get(f"{BASE_URL}/api/drivers/{d}/blueprint-readiness", timeout=15).json()
        keys_before = {i["key"] for i in rd["items"]}
        o = _mk_owner(admin); _link_owner(admin, d, o["id"])
        rd2 = admin.get(f"{BASE_URL}/api/drivers/{d}/blueprint-readiness", timeout=15).json()
        keys_after = {i["key"] for i in rd2["items"]}
        assert keys_before == keys_after
        assert len(keys_after) == 7


# ─── MR-07A privacy regression on aggregator ────────────────────────────────
class TestMR07ARegression:
    def test_aggregator_hides_sensitive_for_allocator(self, admin, allocator):
        d = _mk_driver(admin, business_name="SECRET BIZ", abn="99 000 111 222", payroll_number="P-X")
        p = allocator.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).json()
        assert p["driver"].get("business_name") in (None, "")
        assert p["driver"].get("abn") in (None, "")
        # Body must not include the actual sensitive strings anywhere
        body = allocator.get(f"{BASE_URL}/api/drivers/{d}/command-centre-profile", timeout=15).text
        assert "SECRET BIZ" not in body
        assert "99 000 111 222" not in body
