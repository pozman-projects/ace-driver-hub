"""EB-03 Assignment & Relationship Layer — backend tests."""
import os
import re
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://fleet-ops-center-1.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    email = f"ro_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register", json={"email": email, "password": "T@1234", "full_name": "RO", "role": "ReadOnly"}, headers=admin_headers, timeout=15)
    tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "T@1234"}, timeout=15).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _get(h, p, **params):
    return requests.get(f"{API}{p}", headers=h, params=params, timeout=20)


def _post(h, p, body):
    return requests.post(f"{API}{p}", headers=h, json=body, timeout=20)


def _put(h, p, body):
    return requests.put(f"{API}{p}", headers=h, json=body, timeout=20)


def _del(h, p):
    return requests.delete(f"{API}{p}", headers=h, timeout=20)


@pytest.fixture(scope="session")
def master(admin_headers):
    """Fetch existing master ids: 3 drivers, 2 owners, 3 vehicles, 4 equipment."""
    drivers = _get(admin_headers, "/drivers").json()
    owners = _get(admin_headers, "/owners").json()
    vehicles = _get(admin_headers, "/vehicles").json()
    equipment = _get(admin_headers, "/equipment").json()
    assert len(drivers) >= 3 and len(owners) >= 2 and len(vehicles) >= 3 and len(equipment) >= 3
    return {"drivers": drivers, "owners": owners, "vehicles": vehicles, "equipment": equipment}


# ============================================================================
# DRIVER-OWNER
# ============================================================================
class TestDriverOwner:
    def test_seed_current_relationships(self, admin_headers):
        r = _get(admin_headers, "/driver-owner-relationships", is_current="true")
        assert r.status_code == 200
        assert len(r.json()) >= 3

    def test_invalid_driver_rejected(self, admin_headers, master):
        r = _post(admin_headers, "/driver-owner-relationships", {"driver_id": "bad", "owner_id": master["owners"][0]["id"]})
        assert r.status_code == 400

    def test_invalid_owner_rejected(self, admin_headers, master):
        r = _post(admin_headers, "/driver-owner-relationships", {"driver_id": master["drivers"][0]["id"], "owner_id": "bad"})
        assert r.status_code == 400

    def test_new_current_closes_previous(self, admin_headers, master):
        driver = master["drivers"][0]
        # Ensure at least one current exists first
        _post(admin_headers, "/driver-owner-relationships", {
            "driver_id": driver["id"], "owner_id": master["owners"][0]["id"],
            "is_current": True, "start_date": "2026-01-01"
        })
        before = _get(admin_headers, "/driver-owner-relationships", driver_id=driver["id"], is_current="true").json()
        # Create a NEW current with a different owner
        r = _post(admin_headers, "/driver-owner-relationships", {
            "driver_id": driver["id"], "owner_id": master["owners"][1]["id"],
            "is_current": True, "start_date": "2026-06-01"
        })
        assert r.status_code == 200
        after = _get(admin_headers, "/driver-owner-relationships", driver_id=driver["id"], is_current="true").json()
        # Only exactly one current should remain
        assert len(after) == 1
        assert after[0]["owner_id"] == master["owners"][1]["id"]
        # Historical rows are still readable (not deleted)
        allrows = _get(admin_headers, "/driver-owner-relationships", driver_id=driver["id"]).json()
        assert len(allrows) >= len(before)
        # Previous currents now closed with end_date
        closed = [x for x in allrows if not x["is_current"] and not x["is_archived"]]
        assert any(x.get("end_date") == "2026-06-01" for x in closed)

    def test_archive(self, admin_headers, master):
        r = _post(admin_headers, "/driver-owner-relationships", {
            "driver_id": master["drivers"][2]["id"], "owner_id": master["owners"][0]["id"], "is_current": False
        })
        assert r.status_code == 200
        rid = r.json()["id"]
        a = _del(admin_headers, f"/driver-owner-relationships/{rid}")
        assert a.status_code == 200 and a.json()["status"] == "archived"

    def test_readonly_forbidden(self, readonly_headers, master):
        r = _post(readonly_headers, "/driver-owner-relationships", {"driver_id": master["drivers"][0]["id"], "owner_id": master["owners"][0]["id"]})
        assert r.status_code == 403


# ============================================================================
# DRIVER-VEHICLE
# ============================================================================
class TestDriverVehicle:
    def test_seed_active_primary(self, admin_headers):
        r = _get(admin_headers, "/driver-vehicle-assignments", is_active="true", is_primary="true")
        assert r.status_code == 200 and len(r.json()) >= 1

    def test_invalid_refs(self, admin_headers, master):
        r1 = _post(admin_headers, "/driver-vehicle-assignments", {"driver_id": "bad", "vehicle_id": master["vehicles"][0]["id"]})
        r2 = _post(admin_headers, "/driver-vehicle-assignments", {"driver_id": master["drivers"][0]["id"], "vehicle_id": "bad"})
        assert r1.status_code == 400 and r2.status_code == 400

    def test_only_one_active_primary_per_vehicle(self, admin_headers, master):
        # Reassign driver 0 to vehicle 0 (already active-primary from seed) via reassign endpoint
        d0, v0 = master["drivers"][0]["id"], master["vehicles"][0]["id"]
        r = _post(admin_headers, "/driver-vehicle-assignments/reassign", {"driver_id": d0, "vehicle_id": v0, "start_date": "2026-06-15"})
        assert r.status_code == 200
        # Now count active primary for that vehicle
        active = _get(admin_headers, "/driver-vehicle-assignments", vehicle_id=v0, is_active="true", is_primary="true").json()
        assert len(active) == 1

    def test_reassign_closes_prior_and_preserves_history(self, admin_headers, master):
        d1, v1 = master["drivers"][1]["id"], master["vehicles"][1]["id"]
        # Reassign d1 to v1 via controlled endpoint
        r = _post(admin_headers, "/driver-vehicle-assignments/reassign", {"driver_id": d1, "vehicle_id": v1, "start_date": "2026-06-20"})
        assert r.status_code == 200
        # New assignment is active-primary
        newid = r.json()["id"]
        # Prior actives on that driver or vehicle should be closed (is_active=false)
        actives_v = _get(admin_headers, "/driver-vehicle-assignments", vehicle_id=v1, is_active="true", is_primary="true").json()
        assert len(actives_v) == 1 and actives_v[0]["id"] == newid
        # History still exists
        allv = _get(admin_headers, "/driver-vehicle-assignments", vehicle_id=v1).json()
        assert len(allv) >= 2

    def test_display_on_dispatch_requires_active_vehicle(self, admin_headers, master):
        # Set a vehicle to Maintenance, then try to assign with display_on_dispatch=true
        vid = master["vehicles"][2]["id"]
        _put(admin_headers, f"/vehicles/{vid}", {"vehicle_status": "Maintenance"})
        r = _post(admin_headers, "/driver-vehicle-assignments", {
            "driver_id": master["drivers"][2]["id"], "vehicle_id": vid, "display_on_dispatch": True
        })
        assert r.status_code == 400
        _put(admin_headers, f"/vehicles/{vid}", {"vehicle_status": "Active"})

    def test_archive_dva(self, admin_headers, master):
        r = _post(admin_headers, "/driver-vehicle-assignments/reassign", {
            "driver_id": master["drivers"][2]["id"], "vehicle_id": master["vehicles"][2]["id"], "start_date": "2026-07-01"
        })
        assert r.status_code == 200
        aid = r.json()["id"]
        a = _del(admin_headers, f"/driver-vehicle-assignments/{aid}")
        assert a.status_code == 200

    def test_readonly_forbidden(self, readonly_headers, master):
        r = _post(readonly_headers, "/driver-vehicle-assignments", {"driver_id": master["drivers"][0]["id"], "vehicle_id": master["vehicles"][0]["id"]})
        assert r.status_code == 403


# ============================================================================
# DRIVER-EQUIPMENT (with equipment status sync)
# ============================================================================
class TestDriverEquipment:
    def test_seed(self, admin_headers):
        r = _get(admin_headers, "/driver-equipment-assignments", is_active="true")
        assert r.status_code == 200 and len(r.json()) >= 3

    def test_invalid_refs(self, admin_headers, master):
        r1 = _post(admin_headers, "/driver-equipment-assignments", {"driver_id": "bad", "equipment_id": master["equipment"][0]["id"]})
        r2 = _post(admin_headers, "/driver-equipment-assignments", {"driver_id": master["drivers"][0]["id"], "equipment_id": "bad"})
        assert r1.status_code == 400 and r2.status_code == 400

    def test_block_duplicate_active_allocation(self, admin_headers, master):
        # equipment[0] already actively assigned to drivers[0] from seed
        e = master["equipment"][0]["id"]
        r = _post(admin_headers, "/driver-equipment-assignments", {"driver_id": master["drivers"][1]["id"], "equipment_id": e})
        assert r.status_code == 409

    def test_reassign_closes_prior_and_updates_status(self, admin_headers, master):
        # Fetch a Trailer-type equipment (E02 currently Assigned to driver 1)
        e = master["equipment"][1]["id"]
        new_driver = master["drivers"][2]["id"]
        r = _post(admin_headers, "/driver-equipment-assignments/reassign", {"driver_id": new_driver, "equipment_id": e})
        assert r.status_code == 200
        # Old assignment closed
        actives = _get(admin_headers, "/driver-equipment-assignments", equipment_id=e, is_active="true").json()
        assert len(actives) == 1 and actives[0]["driver_id"] == new_driver
        # Equipment status still Assigned
        eq = requests.get(f"{API}/equipment/{e}", headers=admin_headers, timeout=20).json()
        assert eq["equipment_status"] == "Assigned"

    def test_status_returns_available_when_all_closed(self, admin_headers, master):
        # Pick equipment[3] (E04, Available, no active). Create assignment, then archive.
        e = master["equipment"][3]["id"]
        r = _post(admin_headers, "/driver-equipment-assignments", {"driver_id": master["drivers"][0]["id"], "equipment_id": e})
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        eq_after_create = requests.get(f"{API}/equipment/{e}", headers=admin_headers, timeout=20).json()
        assert eq_after_create["equipment_status"] == "Assigned"
        # Archive assignment → equipment should return to Available
        a = _del(admin_headers, f"/driver-equipment-assignments/{aid}")
        assert a.status_code == 200
        eq_after_archive = requests.get(f"{API}/equipment/{e}", headers=admin_headers, timeout=20).json()
        assert eq_after_archive["equipment_status"] == "Available"

    def test_cannot_assign_maintenance_equipment(self, admin_headers, master):
        # Find seeded equipment with status Maintenance (E03)
        eqs = _get(admin_headers, "/equipment").json()
        maint = [e for e in eqs if e["equipment_status"] == "Maintenance"]
        assert maint, "expected at least one maintenance equipment from seed"
        r = _post(admin_headers, "/driver-equipment-assignments", {"driver_id": master["drivers"][0]["id"], "equipment_id": maint[0]["id"]})
        assert r.status_code == 400

    def test_readonly_forbidden(self, readonly_headers, master):
        r = _post(readonly_headers, "/driver-equipment-assignments", {"driver_id": master["drivers"][0]["id"], "equipment_id": master["equipment"][0]["id"]})
        assert r.status_code == 403


# ============================================================================
# RECONCILIATION / IDEMPOTENCY
# ============================================================================
class TestReconciliation:
    def test_seed_idempotent_counts(self, admin_headers):
        # Two consecutive lists should yield same id set (seed does not duplicate)
        a = {x["id"] for x in _get(admin_headers, "/driver-owner-relationships").json()}
        b = {x["id"] for x in _get(admin_headers, "/driver-owner-relationships").json()}
        assert a == b

    def test_no_multiple_active_primary_per_driver(self, admin_headers, master):
        rows = _get(admin_headers, "/driver-vehicle-assignments", is_active="true", is_primary="true").json()
        by_driver = {}
        for r in rows:
            by_driver.setdefault(r["driver_id"], []).append(r)
        for d, lst in by_driver.items():
            assert len(lst) == 1, f"driver {d} has {len(lst)} active primary vehicles"

    def test_no_multiple_active_per_equipment(self, admin_headers):
        rows = _get(admin_headers, "/driver-equipment-assignments", is_active="true").json()
        by_eq = {}
        for r in rows:
            by_eq.setdefault(r["equipment_id"], []).append(r)
        for eid, lst in by_eq.items():
            assert len(lst) == 1


# ============================================================================
# REGRESSION — legacy endpoints still work
# ============================================================================
class TestNoRegression:
    def test_legacy_module_and_profile(self, admin_headers):
        assert _get(admin_headers, "/modules/drivers").status_code == 200
        drivers = _get(admin_headers, "/drivers").json()
        r = requests.get(f"{API}/drivers/{drivers[0]['id']}/profile", headers=admin_headers, timeout=20)
        assert r.status_code == 200
