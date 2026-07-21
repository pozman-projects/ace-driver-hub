"""EB-02 Foundation Registers — backend tests.

Covers all four canonical registers (drivers, owners, vehicles, equipment):
- CRUD via /api/{register}/*
- UUID-style internal IDs
- Uniqueness (driver_code, dispatch_number, registration_number, vin, equipment_number)
- Reserved dispatch numbers (0 and 13)
- Invalid owner references
- Role restrictions (ReadOnly cannot mutate; only Admin/Manager may archive)
- Archive behaviour (soft delete)
- Idempotent seed behaviour
"""
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


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


def _make_user(admin_headers, role):
    email = f"TEST_{role.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Test@1234", "full_name": f"TEST {role}", "role": role},
        headers=admin_headers,
        timeout=20,
    )
    assert r.status_code == 200, f"register {role} failed: {r.text}"
    r2 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Test@1234"}, timeout=20)
    return {"Authorization": f"Bearer {r2.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    return _make_user(admin_headers, "ReadOnly")


@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    return _make_user(admin_headers, "Allocator")


# ---------- Helpers ----------
def _delete(headers, path):
    return requests.delete(f"{API}{path}", headers=headers, timeout=20)


def _post(headers, path, body):
    return requests.post(f"{API}{path}", headers=headers, json=body, timeout=20)


def _put(headers, path, body):
    return requests.put(f"{API}{path}", headers=headers, json=body, timeout=20)


def _get(headers, path):
    return requests.get(f"{API}{path}", headers=headers, timeout=20)


# ============================================================================
# SEED & LIST
# ============================================================================
class TestSeed:
    def test_drivers_seed(self, admin_headers):
        r = _get(admin_headers, "/drivers")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 3, "expected at least the 3 seeded drivers"
        for d in data:
            assert UUID_RE.match(d["id"]), f"driver id not UUID: {d['id']}"

    def test_owners_seed(self, admin_headers):
        r = _get(admin_headers, "/owners")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 2
        for o in data:
            assert UUID_RE.match(o["id"])
            assert o["owner_status"] in {"Active", "Inactive", "Archived"}

    def test_vehicles_seed(self, admin_headers):
        r = _get(admin_headers, "/vehicles")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 3
        for v in data:
            assert UUID_RE.match(v["id"])
            assert v["vehicle_status"] in {"Active", "Inactive", "Maintenance", "Archived"}

    def test_equipment_seed(self, admin_headers):
        r = _get(admin_headers, "/equipment")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 4
        for e in data:
            assert UUID_RE.match(e["id"])
            assert e["equipment_type"] in {"Tray", "Trailer", "Other"}
            assert e["equipment_status"] in {
                "Available", "Assigned", "Maintenance", "Inactive", "Archived",
            }

    def test_seed_idempotent_after_second_request(self, admin_headers):
        """Two consecutive list reads should return identical id set (seed does not duplicate)."""
        a = {v["id"] for v in _get(admin_headers, "/owners").json()}
        b = {v["id"] for v in _get(admin_headers, "/owners").json()}
        assert a == b


# ============================================================================
# DRIVERS — validation and uniqueness
# ============================================================================
class TestDriversValidation:
    def test_create_and_get(self, admin_headers):
        code = f"TESTDC-{uuid.uuid4().hex[:6]}"
        r = _post(admin_headers, "/drivers", {
            "full_name": "TEST Driver Alpha",
            "driver_code": code,
            "mobile_number": "+61 400 111 111",
            "driver_status": "Active",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert UUID_RE.match(d["id"])
        assert d["full_name"] == "TEST Driver Alpha"
        assert d["driver_code"] == code
        assert d["is_archived"] is False
        # cleanup
        _delete(admin_headers, f"/drivers/{d['id']}")

    def test_duplicate_driver_code_rejected(self, admin_headers):
        code = f"DUP-{uuid.uuid4().hex[:6]}"
        r1 = _post(admin_headers, "/drivers", {"full_name": "TEST X", "driver_code": code})
        assert r1.status_code == 200
        r2 = _post(admin_headers, "/drivers", {"full_name": "TEST Y", "driver_code": code})
        assert r2.status_code == 400
        assert "already exists" in r2.text.lower()
        _delete(admin_headers, f"/drivers/{r1.json()['id']}")

    def test_dispatch_number_reserved_zero(self, admin_headers):
        r = _post(admin_headers, "/drivers", {"full_name": "TEST Z", "dispatch_number": "0"})
        assert r.status_code == 400
        assert "reserved" in r.text.lower()

    def test_dispatch_number_reserved_thirteen(self, admin_headers):
        r = _post(admin_headers, "/drivers", {"full_name": "TEST Z", "dispatch_number": "13"})
        assert r.status_code == 400
        assert "reserved" in r.text.lower()

    def test_dispatch_number_unique_when_active(self, admin_headers):
        dn = "77"
        r1 = _post(admin_headers, "/drivers", {"full_name": "TEST DN1", "dispatch_number": dn})
        assert r1.status_code == 200, r1.text
        r2 = _post(admin_headers, "/drivers", {"full_name": "TEST DN2", "dispatch_number": dn})
        assert r2.status_code == 400
        assert "already active" in r2.text.lower()
        _delete(admin_headers, f"/drivers/{r1.json()['id']}")

    def test_payment_percentage_range(self, admin_headers):
        r = _post(admin_headers, "/drivers", {"full_name": "TEST PCT", "payment_percentage": 150})
        assert r.status_code == 422 or r.status_code == 400

    def test_driver_status_controlled(self, admin_headers):
        r = _post(admin_headers, "/drivers", {"full_name": "TEST S", "driver_status": "Bogus"})
        assert r.status_code == 422 or r.status_code == 400

    def test_email_format_validated(self, admin_headers):
        r = _post(admin_headers, "/drivers", {"full_name": "TEST E", "email": "not-an-email"})
        assert r.status_code == 422

    def test_update_driver(self, admin_headers):
        r = _post(admin_headers, "/drivers", {"full_name": "TEST U", "driver_status": "Active"})
        assert r.status_code == 200
        did = r.json()["id"]
        r2 = _put(admin_headers, f"/drivers/{did}", {"full_name": "TEST Updated", "driver_status": "On Leave"})
        assert r2.status_code == 200
        d = r2.json()
        assert d["full_name"] == "TEST Updated"
        assert d["driver_status"] == "On Leave"
        _delete(admin_headers, f"/drivers/{did}")

    def test_archive_driver(self, admin_headers):
        r = _post(admin_headers, "/drivers", {"full_name": "TEST Archive"})
        did = r.json()["id"]
        r2 = _delete(admin_headers, f"/drivers/{did}")
        assert r2.status_code == 200 and r2.json()["status"] == "archived"
        # Default list excludes archived
        lst = _get(admin_headers, "/drivers").json()
        assert did not in {x["id"] for x in lst}
        # But include_archived=true returns it
        lst2 = _get(admin_headers, "/drivers?include_archived=true").json()
        found = [x for x in lst2 if x["id"] == did]
        assert len(found) == 1 and found[0]["is_archived"] is True and found[0]["driver_status"] == "Archived"


# ============================================================================
# OWNERS — validation
# ============================================================================
class TestOwners:
    def test_crud(self, admin_headers):
        r = _post(admin_headers, "/owners", {"name": "TEST Owner Co", "owner_type": "Business", "abn": "00 111 222 333"})
        assert r.status_code == 200, r.text
        oid = r.json()["id"]
        assert UUID_RE.match(oid)
        # abn preserved as text with spaces
        assert r.json()["abn"] == "00 111 222 333"
        r2 = _put(admin_headers, f"/owners/{oid}", {"owner_status": "Inactive"})
        assert r2.status_code == 200
        assert r2.json()["owner_status"] == "Inactive"
        r3 = _delete(admin_headers, f"/owners/{oid}")
        assert r3.status_code == 200
        # Confirm archived
        got = _get(admin_headers, f"/owners/{oid}").json()
        assert got["is_archived"] is True

    def test_owner_status_controlled(self, admin_headers):
        r = _post(admin_headers, "/owners", {"name": "TEST Bogus", "owner_status": "Weird"})
        assert r.status_code == 422 or r.status_code == 400


# ============================================================================
# VEHICLES — validation and owner ref
# ============================================================================
class TestVehicles:
    def test_duplicate_registration_rejected(self, admin_headers):
        reg = f"UNIQ-{uuid.uuid4().hex[:6].upper()}"
        r1 = _post(admin_headers, "/vehicles", {"registration_number": reg})
        assert r1.status_code == 200, r1.text
        r2 = _post(admin_headers, "/vehicles", {"registration_number": reg})
        assert r2.status_code == 400 and "already exists" in r2.text.lower()
        _delete(admin_headers, f"/vehicles/{r1.json()['id']}")

    def test_duplicate_vin_rejected(self, admin_headers):
        vin = f"VIN-{uuid.uuid4().hex[:10].upper()}"
        r1 = _post(admin_headers, "/vehicles", {"registration_number": f"R-{uuid.uuid4().hex[:6]}", "vin": vin})
        assert r1.status_code == 200
        r2 = _post(admin_headers, "/vehicles", {"registration_number": f"R-{uuid.uuid4().hex[:6]}", "vin": vin})
        assert r2.status_code == 400
        _delete(admin_headers, f"/vehicles/{r1.json()['id']}")

    def test_invalid_owner_ref_rejected(self, admin_headers):
        r = _post(admin_headers, "/vehicles", {"registration_number": f"BADO-{uuid.uuid4().hex[:6]}", "owner_id": "nonexistent-owner-id"})
        assert r.status_code == 400 and "owner" in r.text.lower()

    def test_valid_owner_ref_ok(self, admin_headers):
        owners = _get(admin_headers, "/owners").json()
        assert owners, "seed owners missing"
        oid = owners[0]["id"]
        r = _post(admin_headers, "/vehicles", {"registration_number": f"GOOD-{uuid.uuid4().hex[:6]}", "owner_id": oid})
        assert r.status_code == 200
        assert r.json()["owner_id"] == oid
        _delete(admin_headers, f"/vehicles/{r.json()['id']}")

    def test_vehicle_status_controlled(self, admin_headers):
        r = _post(admin_headers, "/vehicles", {"registration_number": f"S-{uuid.uuid4().hex[:6]}", "vehicle_status": "Broken"})
        assert r.status_code == 422 or r.status_code == 400


# ============================================================================
# EQUIPMENT — validation, types, owner ref
# ============================================================================
class TestEquipment:
    def test_duplicate_equipment_number_rejected(self, admin_headers):
        num = f"E-{uuid.uuid4().hex[:6].upper()}"
        r1 = _post(admin_headers, "/equipment", {"equipment_number": num, "equipment_type": "Tray"})
        assert r1.status_code == 200
        r2 = _post(admin_headers, "/equipment", {"equipment_number": num, "equipment_type": "Trailer"})
        assert r2.status_code == 400
        _delete(admin_headers, f"/equipment/{r1.json()['id']}")

    def test_equipment_type_controlled(self, admin_headers):
        r = _post(admin_headers, "/equipment", {"equipment_number": f"T-{uuid.uuid4().hex[:6]}", "equipment_type": "Rocket"})
        assert r.status_code == 422

    def test_equipment_types_supported(self, admin_headers):
        for t in ["Tray", "Trailer", "Other"]:
            r = _post(admin_headers, "/equipment", {"equipment_number": f"T{t}-{uuid.uuid4().hex[:6]}", "equipment_type": t})
            assert r.status_code == 200
            _delete(admin_headers, f"/equipment/{r.json()['id']}")

    def test_invalid_owner_ref_rejected(self, admin_headers):
        r = _post(admin_headers, "/equipment", {"equipment_number": f"BADO-{uuid.uuid4().hex[:6]}", "owner_id": "nope"})
        assert r.status_code == 400


# ============================================================================
# ROLE RESTRICTIONS
# ============================================================================
class TestRoles:
    def test_readonly_cannot_create_driver(self, readonly_headers):
        r = _post(readonly_headers, "/drivers", {"full_name": "TEST RO"})
        assert r.status_code == 403

    def test_readonly_cannot_create_owner(self, readonly_headers):
        r = _post(readonly_headers, "/owners", {"name": "TEST RO Owner"})
        assert r.status_code == 403

    def test_readonly_cannot_create_vehicle(self, readonly_headers):
        r = _post(readonly_headers, "/vehicles", {"registration_number": "RO-VEH"})
        assert r.status_code == 403

    def test_readonly_cannot_create_equipment(self, readonly_headers):
        r = _post(readonly_headers, "/equipment", {"equipment_number": "RO-EQ"})
        assert r.status_code == 403

    def test_allocator_can_create_but_not_archive(self, allocator_headers, admin_headers):
        r = _post(allocator_headers, "/owners", {"name": f"TEST Alloc Owner {uuid.uuid4().hex[:4]}"})
        assert r.status_code == 200
        oid = r.json()["id"]
        # Allocator archive should be forbidden
        r2 = _delete(allocator_headers, f"/owners/{oid}")
        assert r2.status_code == 403
        # Admin can archive
        r3 = _delete(admin_headers, f"/owners/{oid}")
        assert r3.status_code == 200


# ============================================================================
# LEGACY compatibility (no regression on prototype APIs)
# ============================================================================
class TestLegacyPreserved:
    def test_modules_drivers_still_works(self, admin_headers):
        r = _get(admin_headers, "/modules/drivers")
        assert r.status_code == 200 and isinstance(r.json(), list)

    def test_driver_profile_still_works(self, admin_headers):
        drivers = _get(admin_headers, "/drivers").json()
        assert drivers
        r = _get(admin_headers, f"/drivers/{drivers[0]['id']}/profile")
        assert r.status_code == 200
        body = r.json()
        assert "driver" in body and "linked" in body
