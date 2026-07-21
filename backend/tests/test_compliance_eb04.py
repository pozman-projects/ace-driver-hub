"""EB-04 Canonical Compliance Foundation — backend tests."""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://fleet-ops-center-1.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    email = f"eb04ro_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register", json={"email": email, "password": "T@1234", "full_name": "RO", "role": "ReadOnly"}, headers=admin_headers, timeout=15)
    tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "T@1234"}, timeout=15).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _g(h, p, **params):
    return requests.get(f"{API}{p}", headers=h, params=params, timeout=20)


def _p(h, p, body):
    return requests.post(f"{API}{p}", headers=h, json=body, timeout=20)


def _u(h, p, body):
    return requests.put(f"{API}{p}", headers=h, json=body, timeout=20)


def _d(h, p):
    return requests.delete(f"{API}{p}", headers=h, timeout=20)


def _future(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _past(days: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


@pytest.fixture(scope="session")
def master(admin_headers):
    drivers = _g(admin_headers, "/drivers").json()
    vehicles = _g(admin_headers, "/vehicles").json()
    equipment = _g(admin_headers, "/equipment").json()
    assert len(drivers) >= 3 and len(vehicles) >= 3 and len(equipment) >= 3
    return {"drivers": drivers, "vehicles": vehicles, "equipment": equipment}


# ============================================================================
# DRIVER LICENCES
# ============================================================================
class TestDriverLicences:
    def test_list_returns_seed(self, admin_headers):
        r = _g(admin_headers, "/driver-licences")
        assert r.status_code == 200
        assert len(r.json()) >= 3

    def test_create_valid_licence(self, admin_headers, master):
        drv = master["drivers"][0]
        body = {"driver_id": drv["id"], "licence_number": f"TEST-{uuid.uuid4().hex[:6]}",
                "expiry_date": _future(200), "is_primary": False}
        r = _p(admin_headers, "/driver-licences", body)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Compliant"

    def test_invalid_driver_reference(self, admin_headers):
        r = _p(admin_headers, "/driver-licences", {"driver_id": "nope", "licence_number": "X"})
        assert r.status_code == 400

    def test_one_primary_licence_only(self, admin_headers, master):
        drv = master["drivers"][1]
        # existing seed primary already exists — create a new primary
        body = {"driver_id": drv["id"], "licence_number": f"NEW-{uuid.uuid4().hex[:6]}",
                "expiry_date": _future(300), "is_primary": True}
        r = _p(admin_headers, "/driver-licences", body)
        assert r.status_code == 200
        # Now count active primaries
        rows = _g(admin_headers, "/driver-licences", driver_id=drv["id"]).json()
        primary_active = [x for x in rows if x.get("is_primary") and not x.get("is_archived")]
        assert len(primary_active) == 1

    def test_expiry_classification(self, admin_headers, master):
        drv = master["drivers"][0]
        r = _p(admin_headers, "/driver-licences", {"driver_id": drv["id"], "licence_number": f"SOON-{uuid.uuid4().hex[:6]}",
                                                    "expiry_date": _future(10), "is_primary": False})
        assert r.json()["status"] == "Due Soon"
        r2 = _p(admin_headers, "/driver-licences", {"driver_id": drv["id"], "licence_number": f"OLD-{uuid.uuid4().hex[:6]}",
                                                     "expiry_date": _past(5), "is_primary": False})
        assert r2.json()["status"] == "Expired"

    def test_readonly_cannot_create(self, readonly_headers, master):
        drv = master["drivers"][0]
        r = _p(readonly_headers, "/driver-licences", {"driver_id": drv["id"], "licence_number": "RO-XX"})
        assert r.status_code == 403

    def test_archived_primary_causes_missing_summary(self, admin_headers, master):
        # Create a fresh driver so we can test in isolation
        drv = _p(admin_headers, "/drivers", {"full_name": f"TestDrv{uuid.uuid4().hex[:6]}"}).json()
        # Summary should be Missing (no licence)
        s = _g(admin_headers, f"/compliance/drivers/{drv['id']}").json()
        assert s["overall_status"] == "Missing"
        # Add a primary licence
        lic = _p(admin_headers, "/driver-licences", {"driver_id": drv["id"], "licence_number": f"LX-{uuid.uuid4().hex[:6]}",
                                                     "expiry_date": _future(200), "is_primary": True}).json()
        s = _g(admin_headers, f"/compliance/drivers/{drv['id']}").json()
        assert s["overall_status"] == "Compliant"
        # Archive the primary
        _d(admin_headers, f"/driver-licences/{lic['id']}")
        s = _g(admin_headers, f"/compliance/drivers/{drv['id']}").json()
        assert s["overall_status"] == "Missing"


# ============================================================================
# VEHICLE REGISTRATION
# ============================================================================
class TestVehicleRegistrations:
    def test_create_current_registration(self, admin_headers, master):
        veh = master["vehicles"][0]
        body = {"vehicle_id": veh["id"], "registration_number_snapshot": veh.get("registration_number"),
                "expiry_date": _future(120), "is_current": True}
        r = _p(admin_headers, "/vehicle-registrations", body)
        assert r.status_code == 200
        assert r.json()["status"] == "Compliant"
        # Only one current
        rows = _g(admin_headers, "/vehicle-registrations", vehicle_id=veh["id"]).json()
        current_active = [x for x in rows if x.get("is_current") and not x.get("is_archived")]
        assert len(current_active) == 1

    def test_invalid_vehicle_reference(self, admin_headers):
        r = _p(admin_headers, "/vehicle-registrations", {"vehicle_id": "nope"})
        assert r.status_code == 400

    def test_previous_registration_closes(self, admin_headers, master):
        veh = master["vehicles"][1]
        r1 = _p(admin_headers, "/vehicle-registrations", {"vehicle_id": veh["id"],
                                                          "expiry_date": _future(50), "is_current": True})
        first_id = r1.json()["id"]
        r2 = _p(admin_headers, "/vehicle-registrations", {"vehicle_id": veh["id"],
                                                          "expiry_date": _future(365), "is_current": True})
        assert r2.status_code == 200
        first = _g(admin_headers, f"/vehicle-registrations/{first_id}").json()
        assert first["is_current"] is False

    def test_history_retained(self, admin_headers, master):
        veh = master["vehicles"][2]
        rows = _g(admin_headers, "/vehicle-registrations", vehicle_id=veh["id"]).json()
        # After previous tests, we should have multiple rows
        assert len(rows) >= 1


# ============================================================================
# VEHICLE INSURANCE
# ============================================================================
class TestVehicleInsurance:
    def test_create_current_policy(self, admin_headers, master):
        veh = master["vehicles"][0]
        r = _p(admin_headers, "/vehicle-insurance", {"vehicle_id": veh["id"], "policy_number": f"POL-{uuid.uuid4().hex[:6]}",
                                                    "cover_type": "Comprehensive", "expiry_date": _future(180), "is_current": True})
        assert r.status_code == 200
        assert r.json()["status"] == "Compliant"

    def test_one_current_per_cover_type(self, admin_headers, master):
        veh = master["vehicles"][1]
        r1 = _p(admin_headers, "/vehicle-insurance", {"vehicle_id": veh["id"], "policy_number": f"CT1-{uuid.uuid4().hex[:6]}",
                                                     "cover_type": "Comprehensive", "expiry_date": _future(90), "is_current": True})
        id1 = r1.json()["id"]
        # Different cover type — both should stay current
        r2 = _p(admin_headers, "/vehicle-insurance", {"vehicle_id": veh["id"], "policy_number": f"CT2-{uuid.uuid4().hex[:6]}",
                                                     "cover_type": "Third Party", "expiry_date": _future(90), "is_current": True})
        assert _g(admin_headers, f"/vehicle-insurance/{id1}").json()["is_current"] is True
        # New Comprehensive — closes the first
        r3 = _p(admin_headers, "/vehicle-insurance", {"vehicle_id": veh["id"], "policy_number": f"CT3-{uuid.uuid4().hex[:6]}",
                                                     "cover_type": "Comprehensive", "expiry_date": _future(365), "is_current": True})
        assert _g(admin_headers, f"/vehicle-insurance/{id1}").json()["is_current"] is False


# ============================================================================
# VEHICLE INSPECTIONS
# ============================================================================
class TestVehicleInspections:
    def test_pass_inspection(self, admin_headers, master):
        veh = master["vehicles"][0]
        r = _p(admin_headers, "/vehicle-inspections", {"vehicle_id": veh["id"], "inspection_date": _past(2),
                                                       "next_inspection_due": _future(180), "result": "Pass"})
        assert r.status_code == 200
        assert r.json()["status"] == "Compliant"

    def test_fail_inspection(self, admin_headers, master):
        veh = master["vehicles"][0]
        r = _p(admin_headers, "/vehicle-inspections", {"vehicle_id": veh["id"], "inspection_date": _past(1),
                                                       "result": "Fail"})
        assert r.json()["status"] == "Expired"

    def test_failed_inspection_affects_vehicle_summary(self, admin_headers, master):
        # Create a fresh vehicle and log a failed inspection
        veh = _p(admin_headers, "/vehicles", {"registration_number": f"TEST-{uuid.uuid4().hex[:6]}"}).json()
        _p(admin_headers, "/vehicle-registrations", {"vehicle_id": veh["id"], "expiry_date": _future(400), "is_current": True})
        _p(admin_headers, "/vehicle-insurance", {"vehicle_id": veh["id"], "policy_number": "PX", "expiry_date": _future(400), "is_current": True})
        _p(admin_headers, "/vehicle-inspections", {"vehicle_id": veh["id"], "inspection_date": _past(1), "result": "Fail"})
        s = _g(admin_headers, f"/compliance/vehicles/{veh['id']}").json()
        assert s["overall_status"] == "Expired"
        # worst_component must identify inspection
        assert s["worst_component"] == "inspection"


# ============================================================================
# DEFECTS
# ============================================================================
class TestDefects:
    def test_open_defect(self, admin_headers, master):
        veh = master["vehicles"][0]
        r = _p(admin_headers, "/vehicle-defects", {"vehicle_id": veh["id"], "description": "Test defect",
                                                   "severity": "Low", "status": "Open"})
        assert r.status_code == 200

    def test_critical_defect_prevents_compliant(self, admin_headers, master):
        veh = _p(admin_headers, "/vehicles", {"registration_number": f"CRT-{uuid.uuid4().hex[:6]}"}).json()
        _p(admin_headers, "/vehicle-registrations", {"vehicle_id": veh["id"], "expiry_date": _future(400), "is_current": True})
        _p(admin_headers, "/vehicle-insurance", {"vehicle_id": veh["id"], "policy_number": "PX", "expiry_date": _future(400), "is_current": True})
        _p(admin_headers, "/vehicle-inspections", {"vehicle_id": veh["id"], "inspection_date": _past(1),
                                                    "next_inspection_due": _future(400), "result": "Pass"})
        _p(admin_headers, "/vehicle-defects", {"vehicle_id": veh["id"], "description": "Brake fault",
                                               "severity": "Critical", "status": "Open"})
        s = _g(admin_headers, f"/compliance/vehicles/{veh['id']}").json()
        assert s["overall_status"] == "Expired"
        assert s["worst_component"] == "defects"

    def test_rectification_records_actor(self, admin_headers, master):
        veh = master["vehicles"][0]
        d = _p(admin_headers, "/vehicle-defects", {"vehicle_id": veh["id"], "description": "Small chip", "severity": "Low"}).json()
        r = _u(admin_headers, f"/vehicle-defects/{d['id']}", {"status": "Rectified", "rectified_date": _past(0)})
        assert r.status_code == 200
        assert r.json()["rectified_by"] == ADMIN_EMAIL

    def test_archive_preserves_history(self, admin_headers, master):
        veh = master["vehicles"][0]
        d = _p(admin_headers, "/vehicle-defects", {"vehicle_id": veh["id"], "description": "Historical", "severity": "Low"}).json()
        _d(admin_headers, f"/vehicle-defects/{d['id']}")
        row = _g(admin_headers, f"/vehicle-defects/{d['id']}").json()
        assert row["is_archived"] is True
        assert row["status"] == "Archived"


# ============================================================================
# MAINTENANCE
# ============================================================================
class TestMaintenance:
    def test_overdue_task_affects_vehicle_summary(self, admin_headers, master):
        veh = _p(admin_headers, "/vehicles", {"registration_number": f"MNT-{uuid.uuid4().hex[:6]}"}).json()
        _p(admin_headers, "/vehicle-registrations", {"vehicle_id": veh["id"], "expiry_date": _future(400), "is_current": True})
        _p(admin_headers, "/vehicle-insurance", {"vehicle_id": veh["id"], "policy_number": "PX", "expiry_date": _future(400), "is_current": True})
        _p(admin_headers, "/vehicle-inspections", {"vehicle_id": veh["id"], "inspection_date": _past(1),
                                                    "next_inspection_due": _future(400), "result": "Pass"})
        r = _p(admin_headers, "/vehicle-maintenance-tasks", {"vehicle_id": veh["id"], "task_type": "Service",
                                                             "scheduled_date": _past(10)})
        assert r.json()["status"] == "Overdue"
        s = _g(admin_headers, f"/compliance/vehicles/{veh['id']}").json()
        assert s["overall_status"] == "Expired"
        assert s["worst_component"] == "maintenance"

    def test_scheduled_due_soon(self, admin_headers, master):
        veh = master["vehicles"][0]
        r = _p(admin_headers, "/vehicle-maintenance-tasks", {"vehicle_id": veh["id"], "task_type": "Check",
                                                             "scheduled_date": _future(15)})
        assert r.json()["status"] == "Due Soon"

    def test_completed_status(self, admin_headers, master):
        veh = master["vehicles"][0]
        r = _p(admin_headers, "/vehicle-maintenance-tasks", {"vehicle_id": veh["id"], "task_type": "Oil",
                                                             "status": "Completed", "completed_date": _past(2)})
        assert r.json()["status"] == "Completed"


# ============================================================================
# EQUIPMENT COMPLIANCE
# ============================================================================
class TestEquipmentCompliance:
    def test_create_record(self, admin_headers, master):
        eq = master["equipment"][0]
        r = _p(admin_headers, "/equipment-compliance", {"equipment_id": eq["id"], "compliance_type": "Certification",
                                                        "reference_number": f"REF-{uuid.uuid4().hex[:6]}", "expiry_date": _future(200), "is_current": True})
        assert r.status_code == 200
        assert r.json()["status"] == "Compliant"

    def test_invalid_equipment_reference(self, admin_headers):
        r = _p(admin_headers, "/equipment-compliance", {"equipment_id": "nope", "compliance_type": "Registration"})
        assert r.status_code == 400

    def test_current_record_per_type(self, admin_headers, master):
        eq = master["equipment"][1]
        r1 = _p(admin_headers, "/equipment-compliance", {"equipment_id": eq["id"], "compliance_type": "Maintenance",
                                                         "expiry_date": _future(30), "is_current": True})
        id1 = r1.json()["id"]
        _p(admin_headers, "/equipment-compliance", {"equipment_id": eq["id"], "compliance_type": "Maintenance",
                                                    "expiry_date": _future(200), "is_current": True})
        assert _g(admin_headers, f"/equipment-compliance/{id1}").json()["is_current"] is False


# ============================================================================
# SUMMARY / OVERVIEW
# ============================================================================
class TestSummaryEngine:
    def test_worst_status_wins(self, admin_headers, master):
        # Vehicle 2 has an expired registration from seed
        veh = master["vehicles"][2]
        s = _g(admin_headers, f"/compliance/vehicles/{veh['id']}").json()
        assert s["overall_status"] in ("Expired", "Missing")
        # Severity numeric non-zero
        assert s["severity"] >= 20

    def test_summary_contains_components(self, admin_headers, master):
        veh = master["vehicles"][0]
        s = _g(admin_headers, f"/compliance/vehicles/{veh['id']}").json()
        keys = {c["component"] for c in s["components"]}
        assert {"registration", "insurance", "inspection", "defects", "maintenance"}.issubset(keys)

    def test_overview_returns_totals(self, admin_headers):
        r = _g(admin_headers, "/compliance/overview")
        assert r.status_code == 200
        j = r.json()
        assert "totals" in j
        assert "drivers" in j["totals"]

    def test_overview_filters_by_status(self, admin_headers):
        r = _g(admin_headers, "/compliance/overview", status="Expired")
        assert r.status_code == 200
        for row in r.json()["drivers"] + r.json()["vehicles"] + r.json()["equipment"]:
            assert row["overall_status"] == "Expired"

    def test_overview_entity_filter(self, admin_headers):
        r = _g(admin_headers, "/compliance/overview", entity_type="driver")
        assert r.status_code == 200
        assert r.json()["vehicles"] == []
        assert r.json()["equipment"] == []


# ============================================================================
# ROLE ENFORCEMENT & LEGACY COMPAT
# ============================================================================
class TestRoleAndLegacy:
    def test_readonly_blocked_across_types(self, readonly_headers, master):
        drv = master["drivers"][0]
        for path, body in [
            ("/driver-licences", {"driver_id": drv["id"], "licence_number": "X"}),
            ("/vehicle-registrations", {"vehicle_id": master["vehicles"][0]["id"]}),
            ("/vehicle-insurance", {"vehicle_id": master["vehicles"][0]["id"], "policy_number": "X"}),
            ("/vehicle-inspections", {"vehicle_id": master["vehicles"][0]["id"]}),
            ("/vehicle-defects", {"vehicle_id": master["vehicles"][0]["id"], "description": "x"}),
            ("/vehicle-maintenance-tasks", {"vehicle_id": master["vehicles"][0]["id"], "task_type": "t"}),
            ("/equipment-compliance", {"equipment_id": master["equipment"][0]["id"]}),
        ]:
            r = _p(readonly_headers, path, body)
            assert r.status_code == 403

    def test_legacy_compliance_endpoint_unchanged(self, admin_headers):
        r = _g(admin_headers, "/compliance/expiring")
        assert r.status_code == 200
        j = r.json()
        assert "totals" in j and "modules" in j and "records" in j
        # Still returns the legacy shape
        assert set(j["totals"].keys()) >= {"expired", "expiring"}

    def test_legacy_module_routes_unchanged(self, admin_headers):
        for slug in ("licences", "truck-rego", "insurance"):
            r = _g(admin_headers, f"/modules/{slug}")
            assert r.status_code == 200
