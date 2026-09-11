"""EB-R02 API acceptance tests over live backend.

Exercises the public endpoints via REACT_APP_BACKEND_URL to verify:
  A. Expiry boundaries (calculated_status + days_remaining) for licence /
     registration / insurance GETs.
  B. /api/compliance/overview exposes warning_window_days & urgent_window_days.
  C. Manual status writes are ignored (system-owned).
  D. Missing/invalid expiry -> Incomplete + days_remaining None.
  E. Vehicle compliance worst-status-wins arithmetic.
  F. prime_mover_status / tray_status / trailer_status contract.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fall back to local supervisor-managed backend if env not injected in test shell
    BASE_URL = "http://localhost:8001"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


def _iso_days(delta: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def api(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def driver_id(api) -> str:
    r = api.post(
        f"{BASE_URL}/api/drivers",
        json={"full_name": "TEST_EBR02 Driver", "driver_status": "Active"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="session")
def prime_mover_id(api) -> str:
    r = api.post(
        f"{BASE_URL}/api/vehicles",
        json={
            "registration_number": f"TEST-PM-{datetime.now().timestamp():.0f}",
            "vehicle_type": "Prime Mover",
            "vehicle_status": "Active",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="session")
def rigid_vehicle_id(api) -> str:
    r = api.post(
        f"{BASE_URL}/api/vehicles",
        json={
            "registration_number": f"TEST-RG-{datetime.now().timestamp():.0f}",
            "vehicle_type": "Rigid",
            "vehicle_status": "Active",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ---------------------------------------------------------------- helpers
def _create_licence(api, driver_id, expiry, licence_number, status_override=None):
    payload = {
        "driver_id": driver_id,
        "licence_number": licence_number,
        "expiry_date": expiry,
        "is_primary": False,
    }
    if status_override is not None:
        payload["status"] = status_override
    r = api.post(f"{BASE_URL}/api/driver-licences", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_registration(api, vehicle_id, expiry, status_override=None, current=False):
    payload = {
        "vehicle_id": vehicle_id,
        "registration_number_snapshot": f"REG-{datetime.now().timestamp():.6f}",
        "expiry_date": expiry,
        "is_current": current,
    }
    if status_override is not None:
        payload["status"] = status_override
    r = api.post(f"{BASE_URL}/api/vehicle-registrations", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_inspection(api, vehicle_id, next_due):
    r = api.post(
        f"{BASE_URL}/api/vehicle-inspections",
        json={
            "vehicle_id": vehicle_id,
            "inspection_type": "Scheduled Inspection",
            "inspection_date": _iso_days(-1),
            "next_inspection_due": next_due,
            "result": "Pass",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_insurance(api, vehicle_id, expiry, status_override=None, current=False, cover="Comprehensive"):
    payload = {
        "vehicle_id": vehicle_id,
        "policy_number": f"POL-{datetime.now().timestamp():.6f}",
        "cover_type": cover,
        "expiry_date": expiry,
        "is_current": current,
    }
    if status_override is not None:
        payload["status"] = status_override
    r = api.post(f"{BASE_URL}/api/vehicle-insurance", json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---------------------------------------------------------------- A. Expiry boundaries
BOUNDARY_CASES = [
    (31, "Compliant"),
    (30, "Due Soon"),
    (8, "Due Soon"),
    (7, "Urgent"),
    (1, "Urgent"),
    (0, "Urgent"),
    (-1, "Expired"),
]


class TestExpiryBoundariesAPI:
    @pytest.mark.parametrize("delta,expected", BOUNDARY_CASES)
    def test_licence_boundary(self, api, driver_id, delta, expected):
        expiry = _iso_days(delta)
        rec = _create_licence(api, driver_id, expiry, f"TEST_L_{delta}")
        r = api.get(f"{BASE_URL}/api/driver-licences/{rec['id']}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["calculated_status"] == expected, data
        assert data["days_remaining"] == delta
        assert isinstance(data["days_remaining"], int)

    @pytest.mark.parametrize("delta,expected", BOUNDARY_CASES)
    def test_registration_boundary(self, api, prime_mover_id, delta, expected):
        expiry = _iso_days(delta)
        rec = _create_registration(api, prime_mover_id, expiry)
        r = api.get(f"{BASE_URL}/api/vehicle-registrations/{rec['id']}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["calculated_status"] == expected, data
        assert data["days_remaining"] == delta

    @pytest.mark.parametrize("delta,expected", BOUNDARY_CASES)
    def test_insurance_boundary(self, api, prime_mover_id, delta, expected):
        expiry = _iso_days(delta)
        rec = _create_insurance(api, prime_mover_id, expiry)
        r = api.get(f"{BASE_URL}/api/vehicle-insurance/{rec['id']}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["calculated_status"] == expected, data
        assert data["days_remaining"] == delta


# ---------------------------------------------------------------- B. Overview thresholds
class TestOverviewThresholds:
    def test_overview_exposes_windows(self, api):
        r = api.get(f"{BASE_URL}/api/compliance/overview", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("warning_window_days") == 30, data
        assert data.get("urgent_window_days") == 7, data


# ---------------------------------------------------------------- C. Manual status protection
class TestManualStatusProtection:
    def test_licence_manual_status_ignored_on_create(self, api, driver_id):
        rec = _create_licence(api, driver_id, _iso_days(45), "TEST_MSP_L", status_override="Expired")
        r = api.get(f"{BASE_URL}/api/driver-licences/{rec['id']}", timeout=15)
        assert r.status_code == 200
        assert r.json()["calculated_status"] == "Compliant"

    def test_licence_manual_status_ignored_on_update(self, api, driver_id):
        rec = _create_licence(api, driver_id, _iso_days(-3), "TEST_MSP_L2")
        # try to force compliant on expired record
        upd = api.put(
            f"{BASE_URL}/api/driver-licences/{rec['id']}",
            json={"status": "Compliant"},
            timeout=15,
        )
        assert upd.status_code == 200, upd.text
        r = api.get(f"{BASE_URL}/api/driver-licences/{rec['id']}", timeout=15)
        assert r.json()["calculated_status"] == "Expired"

    def test_registration_manual_status_ignored(self, api, prime_mover_id):
        rec = _create_registration(api, prime_mover_id, _iso_days(45), status_override="Expired")
        r = api.get(f"{BASE_URL}/api/vehicle-registrations/{rec['id']}", timeout=15)
        assert r.json()["calculated_status"] == "Compliant"
        upd_rec = _create_registration(api, prime_mover_id, _iso_days(-3))
        api.put(
            f"{BASE_URL}/api/vehicle-registrations/{upd_rec['id']}",
            json={"status": "Compliant"},
            timeout=15,
        )
        r = api.get(f"{BASE_URL}/api/vehicle-registrations/{upd_rec['id']}", timeout=15)
        assert r.json()["calculated_status"] == "Expired"

    def test_insurance_manual_status_ignored(self, api, prime_mover_id):
        rec = _create_insurance(api, prime_mover_id, _iso_days(45), status_override="Expired")
        r = api.get(f"{BASE_URL}/api/vehicle-insurance/{rec['id']}", timeout=15)
        assert r.json()["calculated_status"] == "Compliant"
        upd_rec = _create_insurance(api, prime_mover_id, _iso_days(-3))
        api.put(
            f"{BASE_URL}/api/vehicle-insurance/{upd_rec['id']}",
            json={"status": "Compliant"},
            timeout=15,
        )
        r = api.get(f"{BASE_URL}/api/vehicle-insurance/{upd_rec['id']}", timeout=15)
        assert r.json()["calculated_status"] == "Expired"


# ---------------------------------------------------------------- D. Missing / invalid expiry
class TestMissingInvalidExpiry:
    def test_missing_expiry_incomplete(self, api, driver_id):
        rec = _create_licence(api, driver_id, None, "TEST_MISSING_EXP")
        r = api.get(f"{BASE_URL}/api/driver-licences/{rec['id']}", timeout=15)
        data = r.json()
        assert data["calculated_status"] == "Incomplete", data
        assert data["calculated_status"] != "Compliant"
        assert data["days_remaining"] is None

    def test_invalid_expiry_incomplete(self, api, driver_id):
        # Some Pydantic configs reject bogus strings; try both.
        r = api.post(
            f"{BASE_URL}/api/driver-licences",
            json={
                "driver_id": driver_id,
                "licence_number": "TEST_BAD_EXP",
                "expiry_date": "not-a-date",
                "is_primary": False,
            },
            timeout=15,
        )
        if r.status_code in (200, 201):
            rid = r.json()["id"]
            g = api.get(f"{BASE_URL}/api/driver-licences/{rid}", timeout=15)
            data = g.json()
            assert data["calculated_status"] == "Incomplete"
            assert data["days_remaining"] is None
        else:
            # Validation rejection is also acceptable but must not silently coerce to Compliant.
            assert r.status_code in (400, 422), r.text


# ---------------------------------------------------------------- E & F. Vehicle compliance
class TestVehicleCompliance:
    def test_all_compliant_prime_mover(self, api):
        # New PM with only far-future components
        r = api.post(
            f"{BASE_URL}/api/vehicles",
            json={
                "registration_number": f"TEST-PMOK-{datetime.now().timestamp():.0f}",
                "vehicle_type": "Prime Mover",
                "vehicle_status": "Active",
            },
            timeout=15,
        )
        vid = r.json()["id"]
        _create_registration(api, vid, _iso_days(120), current=True)
        _create_insurance(api, vid, _iso_days(120), current=True)
        _create_inspection(api, vid, _iso_days(120))
        s = api.get(f"{BASE_URL}/api/compliance/vehicles/{vid}", timeout=15).json()
        assert s.get("overall_vehicle_compliance_status") == "Compliant", s
        assert s.get("prime_mover_status") == "Compliant"
        assert s.get("tray_status") == "Not yet available"
        assert s.get("trailer_status") == "Not yet available"

    def test_due_soon_yields_conditions(self, api):
        r = api.post(
            f"{BASE_URL}/api/vehicles",
            json={
                "registration_number": f"TEST-PMDS-{datetime.now().timestamp():.0f}",
                "vehicle_type": "Prime Mover",
                "vehicle_status": "Active",
            },
            timeout=15,
        )
        vid = r.json()["id"]
        _create_registration(api, vid, _iso_days(120), current=True)
        _create_insurance(api, vid, _iso_days(10), current=True)  # Due Soon
        _create_inspection(api, vid, _iso_days(120))
        s = api.get(f"{BASE_URL}/api/compliance/vehicles/{vid}", timeout=15).json()
        assert s.get("overall_vehicle_compliance_status") == "Conditions", s
        assert s.get("prime_mover_status") == "Conditions"

    def test_urgent_yields_conditions(self, api):
        r = api.post(
            f"{BASE_URL}/api/vehicles",
            json={
                "registration_number": f"TEST-PMUR-{datetime.now().timestamp():.0f}",
                "vehicle_type": "Prime Mover",
                "vehicle_status": "Active",
            },
            timeout=15,
        )
        vid = r.json()["id"]
        _create_registration(api, vid, _iso_days(120), current=True)
        _create_insurance(api, vid, _iso_days(3), current=True)  # Urgent
        _create_inspection(api, vid, _iso_days(120))
        s = api.get(f"{BASE_URL}/api/compliance/vehicles/{vid}", timeout=15).json()
        assert s.get("overall_vehicle_compliance_status") == "Conditions", s

    def test_expired_yields_non_compliant(self, api):
        r = api.post(
            f"{BASE_URL}/api/vehicles",
            json={
                "registration_number": f"TEST-PMEX-{datetime.now().timestamp():.0f}",
                "vehicle_type": "Prime Mover",
                "vehicle_status": "Active",
            },
            timeout=15,
        )
        vid = r.json()["id"]
        _create_registration(api, vid, _iso_days(-5), current=True)
        _create_insurance(api, vid, _iso_days(120), current=True)
        s = api.get(f"{BASE_URL}/api/compliance/vehicles/{vid}", timeout=15).json()
        assert s.get("overall_vehicle_compliance_status") == "Non-Compliant", s

    def test_rigid_prime_mover_status_not_applicable(self, api, rigid_vehicle_id):
        _create_registration(api, rigid_vehicle_id, _iso_days(120), current=True)
        _create_insurance(api, rigid_vehicle_id, _iso_days(120), current=True)
        _create_inspection(api, rigid_vehicle_id, _iso_days(120))
        s = api.get(f"{BASE_URL}/api/compliance/vehicles/{rigid_vehicle_id}", timeout=15).json()
        assert s.get("prime_mover_status") == "Not Applicable", s
        assert s.get("tray_status") == "Not yet available"
        assert s.get("trailer_status") == "Not yet available"


# ---------------------------------------------------------------- I. List rows enriched
class TestListEnrichment:
    def test_licence_list_has_calculated_status(self, api, driver_id):
        # ensure at least one record exists
        _create_licence(api, driver_id, _iso_days(20), "TEST_LIST_L")
        r = api.get(f"{BASE_URL}/api/driver-licences?driver_id={driver_id}", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        for row in rows:
            assert "calculated_status" in row
            assert "days_remaining" in row

    def test_registration_list_has_calculated_status(self, api, prime_mover_id):
        _create_registration(api, prime_mover_id, _iso_days(20))
        r = api.get(f"{BASE_URL}/api/vehicle-registrations?vehicle_id={prime_mover_id}", timeout=15)
        assert r.status_code == 200
        for row in r.json():
            assert "calculated_status" in row
            assert "days_remaining" in row

    def test_insurance_list_has_calculated_status(self, api, prime_mover_id):
        _create_insurance(api, prime_mover_id, _iso_days(20))
        r = api.get(f"{BASE_URL}/api/vehicle-insurance?vehicle_id={prime_mover_id}", timeout=15)
        assert r.status_code == 200
        for row in r.json():
            assert "calculated_status" in row
            assert "days_remaining" in row
