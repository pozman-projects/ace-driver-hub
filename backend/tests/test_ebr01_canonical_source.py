"""EB-R01 · Canonical vehicles_register / equipment_register source resolution.

Verifies that Driver Profile aggregator, Driver Export snapshot and Activation
constants read from CANONICAL registers ('vehicles_register' / 'equipment_register')
and NOT from legacy 'vehicles' / 'equipment' collections.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = "http://localhost:8001"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ace_driver_hub")

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def sess(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def canonical_setup(sess, mongo):
    """Create canonical driver, vehicle, equipment, and assignments."""
    tag = uuid.uuid4().hex[:8]

    # Vehicle (canonical, via /api/vehicles → vehicles_register)
    v_payload = {
        "registration_number": f"TEST-EBR01-V-{tag}",
        "vin": f"VINEBR01{tag}",
        "make": "Kenworth",
        "model": "T909",
        "vehicle_type": "Prime Mover",
        "carrier_configuration": "B-Double",
        "vehicle_status": "Active",
    }
    r = sess.post(f"{BASE_URL}/api/vehicles", json=v_payload, timeout=30)
    assert r.status_code in (200, 201), f"vehicle create failed: {r.status_code} {r.text}"
    vehicle = r.json()

    # Equipment (canonical, via /api/equipment → equipment_register)
    e_payload = {
        "equipment_number": f"TEST-EBR01-E-{tag}",
        "equipment_type": "Tray",
        "equipment_status": "Available",
    }
    r = sess.post(f"{BASE_URL}/api/equipment", json=e_payload, timeout=30)
    assert r.status_code in (200, 201), f"equipment create failed: {r.status_code} {r.text}"
    equipment = r.json()

    # Driver
    d_payload = {
        "full_name": f"TEST EBR01 Driver {tag}",
        "mobile_number": "0400000000",
        "email": f"ebr01.{tag}@example.com",
        "driver_status": "Active",
    }
    r = sess.post(f"{BASE_URL}/api/drivers", json=d_payload, timeout=30)
    assert r.status_code in (200, 201), f"driver create failed: {r.status_code} {r.text}"
    driver = r.json()

    # Driver-Vehicle assignment (primary)
    r = sess.post(
        f"{BASE_URL}/api/driver-vehicle-assignments",
        json={"driver_id": driver["id"], "vehicle_id": vehicle["id"],
              "is_active": True, "is_primary": True},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"DVA failed: {r.status_code} {r.text}"
    dva = r.json()

    # Driver-Equipment assignment
    r = sess.post(
        f"{BASE_URL}/api/driver-equipment-assignments",
        json={"driver_id": driver["id"], "equipment_id": equipment["id"],
              "is_active": True},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"DEA failed: {r.status_code} {r.text}"
    dea = r.json()

    yield {"driver": driver, "vehicle": vehicle, "equipment": equipment,
           "dva": dva, "dea": dea, "tag": tag}

    # Teardown — remove legacy pollution & assignments
    try:
        mongo["vehicles"].delete_many({"id": vehicle["id"]})
        mongo["equipment"].delete_many({"id": equipment["id"]})
    except Exception:
        pass


# ─── Test 1: Canonical Vehicle lookup in Driver Profile ───────────────────────
def test_profile_resolves_vehicle_from_canonical_register(sess, canonical_setup):
    d = canonical_setup["driver"]
    v = canonical_setup["vehicle"]
    r = sess.get(f"{BASE_URL}/api/drivers/{d['id']}/command-centre-profile", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    veh = body.get("vehicle")
    assert veh is not None, "profile.vehicle missing"
    assert veh["id"] == v["id"]
    # Canonical vehicle_register keys must be present
    for key in ("registration_number", "vin", "make", "model", "vehicle_type",
                "carrier_configuration", "vehicle_status"):
        assert key in veh, f"Canonical vehicle key '{key}' missing in profile"
    assert veh["registration_number"] == v["registration_number"]
    assert veh["vin"] == v["vin"]


# ─── Test 2: Canonical Equipment lookup in Driver Profile ─────────────────────
def test_profile_resolves_equipment_from_canonical_register(sess, canonical_setup):
    d = canonical_setup["driver"]
    e = canonical_setup["equipment"]
    r = sess.get(f"{BASE_URL}/api/drivers/{d['id']}/command-centre-profile", timeout=30)
    assert r.status_code == 200
    body = r.json()
    eq_assignments = body.get("equipment_assignments") or []
    assert len(eq_assignments) >= 1, "no equipment assignments returned"
    match = next((row for row in eq_assignments
                  if row.get("equipment") and row["equipment"]["id"] == e["id"]), None)
    assert match, f"canonical equipment {e['id']} not embedded in profile"
    eq_doc = match["equipment"]
    for key in ("equipment_number", "equipment_type", "equipment_status"):
        assert key in eq_doc, f"canonical equipment key '{key}' missing"
    assert eq_doc["equipment_number"] == e["equipment_number"]


# ─── Test 3: Legacy-override negative test ────────────────────────────────────
def test_legacy_vehicle_shadow_does_not_override_canonical(sess, mongo, canonical_setup):
    d = canonical_setup["driver"]
    v = canonical_setup["vehicle"]

    # Insert a legacy 'vehicles' record with the SAME id but DIFFERENT payload.
    legacy_doc = {
        "id": v["id"],
        "registration_number": "LEGACY-SHOULD-NOT-APPEAR",
        "vin": "LEGACYVIN-XXX",
        "make": "LegacyBrand",
        "model": "LegacyModel",
        "vehicle_type": "LegacyType",
        "vehicle_status": "Retired",
        "_source": "legacy-shadow-ebr01",
    }
    # Also legacy 'equipment' shadow
    e = canonical_setup["equipment"]
    legacy_eq = {
        "id": e["id"],
        "equipment_number": "LEGACY-EQ-SHOULD-NOT-APPEAR",
        "equipment_type": "LegacyEquipType",
        "equipment_status": "Retired",
        "_source": "legacy-shadow-ebr01",
    }
    mongo["vehicles"].replace_one({"id": v["id"]}, legacy_doc, upsert=True)
    mongo["equipment"].replace_one({"id": e["id"]}, legacy_eq, upsert=True)

    r = sess.get(f"{BASE_URL}/api/drivers/{d['id']}/command-centre-profile", timeout=30)
    assert r.status_code == 200
    body = r.json()

    veh = body.get("vehicle")
    assert veh is not None
    assert veh["registration_number"] == v["registration_number"], (
        f"Aggregator returned legacy shadow: {veh['registration_number']}"
    )
    assert veh["vin"] == v["vin"]
    assert veh.get("make") != "LegacyBrand"

    eq_assignments = body.get("equipment_assignments") or []
    match = next((row for row in eq_assignments
                  if row.get("equipment") and row["equipment"]["id"] == e["id"]), None)
    assert match is not None
    assert match["equipment"]["equipment_number"] == e["equipment_number"], (
        "Aggregator returned legacy equipment shadow instead of canonical"
    )


# ─── Test 4 & 5: Driver Export snapshot uses canonical Vehicle + Equipment ───
def test_export_start_sheet_uses_canonical_vehicle_and_equipment(sess, mongo, canonical_setup):
    d = canonical_setup["driver"]
    v = canonical_setup["vehicle"]
    e = canonical_setup["equipment"]

    # legacy shadows still present from previous test — keep them to prove point;
    # re-insert defensively if pytest ordering differs.
    mongo["vehicles"].replace_one(
        {"id": v["id"]},
        {"id": v["id"], "registration_number": "LEGACY-SHOULD-NOT-APPEAR",
         "vehicle_status": "Retired", "_source": "legacy-shadow-ebr01"},
        upsert=True,
    )
    mongo["equipment"].replace_one(
        {"id": e["id"]},
        {"id": e["id"], "equipment_number": "LEGACY-EQ-SHOULD-NOT-APPEAR",
         "_source": "legacy-shadow-ebr01"},
        upsert=True,
    )

    r = sess.post(f"{BASE_URL}/api/drivers/{d['id']}/exports/start-sheet",
                  json={"confirm": True}, timeout=60)
    assert r.status_code == 200, f"start-sheet failed: {r.status_code} {r.text}"
    result = r.json()
    version_id = result["version"]["driver_export_version_id"]

    # Read the persisted snapshot (Admin gets full payload)
    r = sess.get(f"{BASE_URL}/api/driver-export-versions/{version_id}", timeout=30)
    assert r.status_code == 200, r.text
    ver = r.json()
    snap = ver.get("snapshot_payload") or {}
    op = snap.get("operational") or {}

    # Canonical vehicle registration_number should appear as vehicle_label
    assert op.get("vehicle_label") == v["registration_number"], (
        f"snapshot vehicle_label={op.get('vehicle_label')!r} "
        f"expected canonical={v['registration_number']!r}"
    )
    # Ensure the LEGACY value did NOT leak into the snapshot
    assert "LEGACY-SHOULD-NOT-APPEAR" not in str(op.get("vehicle_label", ""))

    # Equipment must include canonical equipment_number/equipment_type
    eq_items = op.get("equipment_items") or []
    combined_serials = " ".join(str(i.get("serial", "")) for i in eq_items)
    assert "LEGACY-EQ-SHOULD-NOT-APPEAR" not in combined_serials
    # canonical equipment_type should appear (label falls back to type when name missing);
    # legacy shadow's fields ("LegacyEquipType", "LEGACY-EQ-...") must not appear.
    combined_all = " ".join(f"{i.get('label')} {i.get('serial')}" for i in eq_items)
    assert "LegacyEquipType" not in combined_all
    assert e["equipment_type"] in combined_all, (
        f"canonical equipment_type not in snapshot equipment_items: {eq_items}"
    )


# ─── Test 6: Activation regression — flow completes without error ─────────────
def test_activation_flow_no_regression(sess, canonical_setup):
    d = canonical_setup["driver"]
    # Start activation
    r = sess.post(f"{BASE_URL}/api/drivers/{d['id']}/activation/start", timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("record") is not None
    # Recalculate
    r = sess.post(f"{BASE_URL}/api/drivers/{d['id']}/activation/recalculate", timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["record"]["readiness_status"] in (
        "Not Assessed", "Incomplete", "Ready", "Ready with Override", "Blocked", "Activated",
    )


# ─── Test 7: Canonical CRUD regression ────────────────────────────────────────
def test_canonical_vehicles_and_equipment_listing(sess, canonical_setup):
    v = canonical_setup["vehicle"]
    e = canonical_setup["equipment"]
    r = sess.get(f"{BASE_URL}/api/vehicles", timeout=30)
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert v["id"] in ids

    r = sess.get(f"{BASE_URL}/api/equipment", timeout=30)
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert e["id"] in ids


def test_canonical_dva_and_dea_listing(sess, canonical_setup):
    d = canonical_setup["driver"]
    r = sess.get(f"{BASE_URL}/api/driver-vehicle-assignments?driver_id={d['id']}", timeout=30)
    assert r.status_code == 200
    assert any(row["driver_id"] == d["id"] for row in r.json())

    r = sess.get(f"{BASE_URL}/api/driver-equipment-assignments?driver_id={d['id']}", timeout=30)
    assert r.status_code == 200
    assert any(row["driver_id"] == d["id"] for row in r.json())
