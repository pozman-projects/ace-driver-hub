"""EB-R02C · Targeted acceptance tests over live backend.

Covers:
  A. Vehicle lifecycle enum — 6 canonical values accepted, 3 deprecated rejected.
  B. Coupling creation — happy paths, role/type mismatches, archived guards.
  C. Uniqueness — one active Tray / Trailer per vehicle; equipment cannot be
     active on two vehicles; reassign closes previous.
  D. Compliance integration — Prime Mover + Tray + Trailer WSW roll-up on
     the per-vehicle summary and on the fleet aggregate.
  E. Display — /compliance/overview exposes canonical fleet_vehicle_compliance.
  F. Data safety — DELETE is soft-close (history preserved), no physical erasure.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


def _iso_days(delta: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


def _tag() -> str:
    return uuid.uuid4().hex[:8]


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


def _post_vehicle(api, reg, vtype="Prime Mover", status="Active"):
    r = api.post(
        f"{BASE_URL}/api/vehicles",
        json={"registration_number": reg, "vehicle_type": vtype, "vehicle_status": status},
        timeout=15,
    )
    return r


def _post_equipment(api, num, eq_type):
    r = api.post(
        f"{BASE_URL}/api/equipment",
        json={"equipment_number": num, "equipment_type": eq_type, "equipment_status": "Available"},
        timeout=15,
    )
    return r


# ---------------------------------------------------------------- A. Lifecycle
CANONICAL_STATUSES = [
    "Active", "In Workshop", "Retired", "Sold", "Written Off", "Pending Disposal",
]
DEPRECATED_STATUSES = ["Inactive", "Maintenance", "Archived"]


class TestVehicleLifecycle:
    @pytest.mark.parametrize("status", CANONICAL_STATUSES)
    def test_accepts_canonical_status(self, api, status):
        r = _post_vehicle(api, f"TEST-LC-{_tag()}", status=status)
        assert r.status_code in (200, 201), r.text
        assert r.json()["vehicle_status"] == status

    @pytest.mark.parametrize("status", DEPRECATED_STATUSES)
    def test_rejects_deprecated_status_on_create(self, api, status):
        r = _post_vehicle(api, f"TEST-LC-{_tag()}", status=status)
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("status", DEPRECATED_STATUSES)
    def test_rejects_deprecated_status_on_update(self, api, status):
        r = _post_vehicle(api, f"TEST-LC-{_tag()}", status="Active")
        assert r.status_code in (200, 201)
        vid = r.json()["id"]
        r2 = api.put(
            f"{BASE_URL}/api/vehicles/{vid}",
            json={"vehicle_status": status},
            timeout=15,
        )
        assert r2.status_code == 422, r2.text

    def test_archive_preserves_lifecycle_and_sets_is_archived(self, api):
        r = _post_vehicle(api, f"TEST-ARCH-{_tag()}", status="Retired")
        assert r.status_code in (200, 201)
        vid = r.json()["id"]
        rd = api.delete(f"{BASE_URL}/api/vehicles/{vid}", timeout=15)
        assert rd.status_code == 200
        # include archived to fetch the archived doc
        rl = api.get(f"{BASE_URL}/api/vehicles?include_archived=true", timeout=15)
        assert rl.status_code == 200
        row = next(v for v in rl.json() if v["id"] == vid)
        assert row["is_archived"] is True
        # Lifecycle value must be preserved (Archived is NOT a lifecycle state)
        assert row["vehicle_status"] == "Retired"


# ---------------------------------------------------------------- B. Coupling creation
@pytest.fixture(scope="module")
def pm_id(api):
    r = _post_vehicle(api, f"TEST-PM-{_tag()}", status="Active")
    assert r.status_code in (200, 201)
    return r.json()["id"]


@pytest.fixture(scope="module")
def tray_id(api):
    r = _post_equipment(api, f"TEST-TR-{_tag()}", "Tray")
    assert r.status_code in (200, 201)
    return r.json()["id"]


@pytest.fixture(scope="module")
def trailer_id(api):
    r = _post_equipment(api, f"TEST-TL-{_tag()}", "Trailer")
    assert r.status_code in (200, 201)
    return r.json()["id"]


@pytest.fixture(scope="module")
def other_equipment_id(api):
    r = _post_equipment(api, f"TEST-OT-{_tag()}", "Other")
    assert r.status_code in (200, 201)
    return r.json()["id"]


class TestCouplingCreation:
    def test_valid_tray_coupling_succeeds(self, api, pm_id, tray_id):
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm_id, "equipment_id": tray_id, "role": "Tray"},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        assert r.json()["role"] == "Tray"
        assert r.json()["is_active"] is True

    def test_valid_trailer_coupling_succeeds(self, api, pm_id, trailer_id):
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm_id, "equipment_id": trailer_id, "role": "Trailer"},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        assert r.json()["role"] == "Trailer"

    def test_tray_role_on_trailer_equipment_rejected(self, api, pm_id, trailer_id):
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm_id, "equipment_id": trailer_id, "role": "Tray"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "Tray" in r.text

    def test_trailer_role_on_tray_equipment_rejected(self, api, pm_id, tray_id):
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm_id, "equipment_id": tray_id, "role": "Trailer"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "Trailer" in r.text

    def test_unknown_vehicle_rejected(self, api, tray_id):
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": "does-not-exist", "equipment_id": tray_id, "role": "Tray"},
            timeout=15,
        )
        assert r.status_code == 400

    def test_unknown_equipment_rejected(self, api, pm_id):
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm_id, "equipment_id": "does-not-exist", "role": "Tray"},
            timeout=15,
        )
        assert r.status_code == 400


# ---------------------------------------------------------------- C. Uniqueness
class TestCouplingUniqueness:
    def test_second_active_tray_on_same_vehicle_blocked(self, api):
        pm = _post_vehicle(api, f"TEST-U-PM-{_tag()}").json()
        t1 = _post_equipment(api, f"TEST-U-T1-{_tag()}", "Tray").json()
        t2 = _post_equipment(api, f"TEST-U-T2-{_tag()}", "Tray").json()
        r1 = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": t1["id"], "role": "Tray"},
            timeout=15,
        )
        assert r1.status_code in (200, 201)
        r2 = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": t2["id"], "role": "Tray"},
            timeout=15,
        )
        assert r2.status_code == 409, r2.text

    def test_second_active_trailer_on_same_vehicle_blocked(self, api):
        pm = _post_vehicle(api, f"TEST-U-PM-{_tag()}").json()
        t1 = _post_equipment(api, f"TEST-U-TR1-{_tag()}", "Trailer").json()
        t2 = _post_equipment(api, f"TEST-U-TR2-{_tag()}", "Trailer").json()
        api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": t1["id"], "role": "Trailer"},
            timeout=15,
        )
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": t2["id"], "role": "Trailer"},
            timeout=15,
        )
        assert r.status_code == 409

    def test_equipment_cannot_be_active_on_two_vehicles(self, api):
        pm1 = _post_vehicle(api, f"TEST-M-PM1-{_tag()}").json()
        pm2 = _post_vehicle(api, f"TEST-M-PM2-{_tag()}").json()
        tr = _post_equipment(api, f"TEST-M-T-{_tag()}", "Tray").json()
        r1 = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm1["id"], "equipment_id": tr["id"], "role": "Tray"},
            timeout=15,
        )
        assert r1.status_code in (200, 201)
        r2 = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm2["id"], "equipment_id": tr["id"], "role": "Tray"},
            timeout=15,
        )
        assert r2.status_code == 409

    def test_reassign_closes_previous_and_preserves_history(self, api):
        pm = _post_vehicle(api, f"TEST-R-PM-{_tag()}").json()
        t1 = _post_equipment(api, f"TEST-R-T1-{_tag()}", "Tray").json()
        t2 = _post_equipment(api, f"TEST-R-T2-{_tag()}", "Tray").json()
        r1 = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": t1["id"], "role": "Tray"},
            timeout=15,
        )
        c1_id = r1.json()["id"]
        r2 = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings/reassign",
            json={"vehicle_id": pm["id"], "equipment_id": t2["id"], "role": "Tray"},
            timeout=15,
        )
        assert r2.status_code in (200, 201), r2.text
        assert r2.json()["id"] != c1_id
        # Previous coupling still present but closed
        lr = api.get(
            f"{BASE_URL}/api/vehicle-equipment-couplings?vehicle_id={pm['id']}&role=Tray&include_archived=true",
            timeout=15,
        )
        rows = lr.json()
        old = next(c for c in rows if c["id"] == c1_id)
        assert old["is_active"] is False
        assert old.get("end_date")
        # Exactly one active Tray for this vehicle
        actives = [c for c in rows if c["is_active"]]
        assert len(actives) == 1
        assert actives[0]["equipment_id"] == t2["id"]


# ---------------------------------------------------------------- D. Compliance integration
class TestVehicleComplianceIntegration:
    def test_prime_mover_summary_returns_new_fields(self, api, pm_id):
        r = api.get(f"{BASE_URL}/api/compliance/vehicles/{pm_id}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "prime_mover_status" in data
        assert "tray_status" in data
        assert "trailer_status" in data
        assert "overall_vehicle_compliance_status" in data
        assert "tray_coupled" in data
        assert "trailer_coupled" in data

    def test_uncoupled_vehicle_tray_and_trailer_are_not_applicable(self, api):
        pm = _post_vehicle(api, f"TEST-NA-PM-{_tag()}").json()
        r = api.get(f"{BASE_URL}/api/compliance/vehicles/{pm['id']}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["tray_coupled"] is False
        assert data["trailer_coupled"] is False
        assert data["tray_status"] == "Not Applicable"
        assert data["trailer_status"] == "Not Applicable"

    def test_coupled_tray_status_flows_through(self, api):
        pm = _post_vehicle(api, f"TEST-CS-PM-{_tag()}").json()
        tr = _post_equipment(api, f"TEST-CS-T-{_tag()}", "Tray").json()
        # Couple the tray
        c = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": tr["id"], "role": "Tray"},
            timeout=15,
        )
        assert c.status_code in (200, 201)
        # No compliance records on tray → equipment_summary returns Missing → VC = Non-Compliant
        r = api.get(f"{BASE_URL}/api/compliance/vehicles/{pm['id']}", timeout=15)
        data = r.json()
        assert data["tray_coupled"] is True
        assert data["tray_status"] == "Non-Compliant"
        # Overall is worst of PM + Tray + Trailer. Trailer=NA, PM depends on its own
        # records. So overall must be at least Non-Compliant.
        assert data["overall_vehicle_compliance_status"] == "Non-Compliant"

    def test_fleet_aggregate_returns_canonical_wsw(self, api):
        r = api.get(
            f"{BASE_URL}/api/compliance/overview?entity_type=vehicle",
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        fleet = data.get("fleet_vehicle_compliance")
        assert isinstance(fleet, dict)
        for k in ("prime_mover_status", "tray_status", "trailer_status", "overall_vehicle_compliance_status"):
            assert k in fleet
            assert fleet[k] in ("Compliant", "Conditions", "Non-Compliant", "Not Applicable")


# ---------------------------------------------------------------- E. Data safety
class TestCouplingDataSafety:
    def test_delete_soft_closes_and_preserves_history(self, api):
        pm = _post_vehicle(api, f"TEST-DS-PM-{_tag()}").json()
        tr = _post_equipment(api, f"TEST-DS-T-{_tag()}", "Tray").json()
        c = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": tr["id"], "role": "Tray"},
            timeout=15,
        )
        cid = c.json()["id"]
        d = api.delete(f"{BASE_URL}/api/vehicle-equipment-couplings/{cid}", timeout=15)
        assert d.status_code == 200
        # Row must still exist
        g = api.get(f"{BASE_URL}/api/vehicle-equipment-couplings/{cid}", timeout=15)
        assert g.status_code == 200
        row = g.json()
        assert row["is_active"] is False
        assert row["is_archived"] is True
        assert row.get("end_date")

    def test_archived_vehicle_cannot_be_coupled(self, api):
        pm = _post_vehicle(api, f"TEST-AV-PM-{_tag()}").json()
        api.delete(f"{BASE_URL}/api/vehicles/{pm['id']}", timeout=15)
        tr = _post_equipment(api, f"TEST-AV-T-{_tag()}", "Tray").json()
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": tr["id"], "role": "Tray"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "archived" in r.text.lower()

    def test_archived_equipment_cannot_be_coupled(self, api):
        pm = _post_vehicle(api, f"TEST-AE-PM-{_tag()}").json()
        tr = _post_equipment(api, f"TEST-AE-T-{_tag()}", "Tray").json()
        api.delete(f"{BASE_URL}/api/equipment/{tr['id']}", timeout=15)
        r = api.post(
            f"{BASE_URL}/api/vehicle-equipment-couplings",
            json={"vehicle_id": pm["id"], "equipment_id": tr["id"], "role": "Tray"},
            timeout=15,
        )
        # Either 400 (archived guard) or blocked-status guard.
        assert r.status_code == 400
