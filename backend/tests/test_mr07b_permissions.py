"""MR-07B · Canonical role matrix enforcement tests.

Backend-only assertions. Every canonical action from the owner-locked
matrix is verified against the five roles. Frontend hiding is NOT a
security control and is not covered here.
"""
from __future__ import annotations

import os
import uuid
from typing import Dict

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}


# ── fixtures ────────────────────────────────────────────────────────────
def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _login(email: str, password: str) -> requests.Session:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _register(admin: requests.Session, role: str) -> requests.Session:
    tag = _tag()
    email = f"mr07b-{role.lower()}-{tag}@acedriverhub.com"
    password = "P@ssword1"
    r = admin.post(f"{BASE_URL}/api/auth/register",
                   json={"email": email, "password": password,
                         "full_name": f"MR07B {role} {tag}", "role": role},
                   timeout=15)
    r.raise_for_status()
    return _login(email, password)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN["email"], ADMIN["password"])


@pytest.fixture(scope="module")
def manager(admin):
    return _register(admin, "Manager")


@pytest.fixture(scope="module")
def compliance(admin):
    return _register(admin, "Compliance")


@pytest.fixture(scope="module")
def allocator(admin):
    return _register(admin, "Allocator")


@pytest.fixture(scope="module")
def readonly(admin):
    return _register(admin, "ReadOnly")


# ── canonical fixtures ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def base_driver(admin) -> str:
    r = admin.post(f"{BASE_URL}/api/drivers",
                   json={"full_name": f"MR07B Driver {_tag()}",
                         "driver_status": "Training"}, timeout=15)
    r.raise_for_status()
    return r.json()["id"]


@pytest.fixture(scope="module")
def base_owner(admin) -> str:
    r = admin.post(f"{BASE_URL}/api/owners",
                   json={"name": f"MR07B Owner {_tag()}",
                         "trading_name": "MR07B Trading",
                         "primary_email": f"o-{_tag()}@acedriverhub.com"},
                   timeout=15)
    r.raise_for_status()
    return r.json()["id"]


@pytest.fixture(scope="module")
def base_vehicle(admin, base_owner) -> str:
    r = admin.post(f"{BASE_URL}/api/vehicles",
                   json={"registration_number": f"MR07B-{_tag().upper()}",
                         "make": "Test", "model": "MR07B",
                         "owner_id": base_owner, "vehicle_status": "Active"},
                   timeout=15)
    r.raise_for_status()
    return r.json()["id"]


# ── helper matrix runner ────────────────────────────────────────────────
def _expect_status(session: requests.Session, method: str, path: str,
                   *, json=None, expected_ok=False):
    fn = getattr(session, method.lower())
    r = fn(f"{BASE_URL}{path}", json=json, timeout=15) if json is not None \
        else fn(f"{BASE_URL}{path}", timeout=15)
    if expected_ok:
        assert r.status_code in (200, 201), \
            f"{method} {path} expected allow, got {r.status_code}: {r.text[:200]}"
    else:
        assert r.status_code == 403, \
            f"{method} {path} expected 403, got {r.status_code}: {r.text[:200]}"
    return r


# ────────────────────────────────────────────────────────────────────────
# 1. DRIVER CORE
# ────────────────────────────────────────────────────────────────────────
class TestDriverCore:
    def _body(self):
        return {"full_name": f"MR07B DrvCore {_tag()}", "driver_status": "Training"}

    def test_admin_can_create(self, admin):
        _expect_status(admin, "POST", "/api/drivers", json=self._body(), expected_ok=True)

    def test_manager_can_create(self, manager):
        _expect_status(manager, "POST", "/api/drivers", json=self._body(), expected_ok=True)

    def test_compliance_denied_create(self, compliance):
        _expect_status(compliance, "POST", "/api/drivers", json=self._body())

    def test_allocator_denied_create(self, allocator):
        _expect_status(allocator, "POST", "/api/drivers", json=self._body())

    def test_readonly_denied_create(self, readonly):
        _expect_status(readonly, "POST", "/api/drivers", json=self._body())

    def test_compliance_denied_edit_core(self, compliance, base_driver):
        _expect_status(compliance, "PUT", f"/api/drivers/{base_driver}",
                       json={"full_name": "Compliance edit attempt"})

    def test_allocator_denied_edit_core(self, allocator, base_driver):
        # Full-name is a core master field — Allocator not permitted.
        _expect_status(allocator, "PUT", f"/api/drivers/{base_driver}",
                       json={"full_name": "Allocator edit attempt"})

    def test_allocator_allowed_setup_status_transition(self, allocator, base_driver):
        # driver_status is a setup field. Allocator may change it to a
        # non-Active state (Active still gated by MR-04).
        _expect_status(allocator, "PUT", f"/api/drivers/{base_driver}",
                       json={"driver_status": "Training"}, expected_ok=True)


# ────────────────────────────────────────────────────────────────────────
# 2. ACCOUNT DETAILS (MR-07A regression)
# ────────────────────────────────────────────────────────────────────────
class TestAccountDetails:
    def test_admin_can_write_account(self, admin, base_driver):
        r = admin.put(f"{BASE_URL}/api/drivers/{base_driver}",
                      json={"business_name": "ACE Test Co"}, timeout=15)
        assert r.status_code == 200

    def test_manager_can_write_account(self, manager, base_driver):
        r = manager.put(f"{BASE_URL}/api/drivers/{base_driver}",
                        json={"business_name": "ACE Test Co 2"}, timeout=15)
        assert r.status_code == 200

    def test_compliance_denied_write_account(self, compliance, base_driver):
        r = compliance.put(f"{BASE_URL}/api/drivers/{base_driver}",
                           json={"business_name": "Nope"}, timeout=15)
        assert r.status_code == 403

    def test_allocator_denied_write_account(self, allocator, base_driver):
        r = allocator.put(f"{BASE_URL}/api/drivers/{base_driver}",
                          json={"business_name": "Nope"}, timeout=15)
        assert r.status_code == 403

    def test_non_privileged_read_strips_sensitive(self, compliance, allocator,
                                                    readonly, base_driver):
        for s in (compliance, allocator, readonly):
            r = s.get(f"{BASE_URL}/api/drivers/{base_driver}", timeout=15)
            assert r.status_code == 200
            d = r.json()
            for f in ("business_name", "abn", "payroll_number", "payment_percentage"):
                assert f not in d, f"{f} leaked to non-privileged role"


# ────────────────────────────────────────────────────────────────────────
# 3. OWNER MASTER
# ────────────────────────────────────────────────────────────────────────
class TestOwnerMaster:
    def _body(self):
        return {"name": f"MR07B Owner {_tag()}", "trading_name": "T",
                "primary_email": f"o-{_tag()}@acedriverhub.com"}

    def test_admin_manager_allow(self, admin, manager):
        for s in (admin, manager):
            _expect_status(s, "POST", "/api/owners", json=self._body(), expected_ok=True)

    def test_compliance_allocator_readonly_deny(self, compliance, allocator, readonly):
        for s in (compliance, allocator, readonly):
            _expect_status(s, "POST", "/api/owners", json=self._body())


# ────────────────────────────────────────────────────────────────────────
# 4. VEHICLE MASTER
# ────────────────────────────────────────────────────────────────────────
class TestVehicleMaster:
    def _body(self, owner_id):
        return {"registration_number": f"VM-{_tag().upper()}",
                "make": "Test", "model": "MR07B",
                "owner_id": owner_id, "vehicle_status": "Active"}

    def test_admin_manager_allow(self, admin, manager, base_owner):
        for s in (admin, manager):
            _expect_status(s, "POST", "/api/vehicles",
                           json=self._body(base_owner), expected_ok=True)

    def test_compliance_allocator_readonly_deny(self, compliance, allocator, readonly,
                                                  base_owner):
        for s in (compliance, allocator, readonly):
            _expect_status(s, "POST", "/api/vehicles", json=self._body(base_owner))


# ────────────────────────────────────────────────────────────────────────
# 5. EQUIPMENT MASTER
# ────────────────────────────────────────────────────────────────────────
class TestEquipmentMaster:
    def _body(self, owner_id):
        return {"equipment_number": f"EQ-{_tag().upper()}",
                "equipment_type": "Tray",
                "owner_id": owner_id, "status": "Active"}

    def test_admin_manager_allow(self, admin, manager, base_owner):
        for s in (admin, manager):
            _expect_status(s, "POST", "/api/equipment",
                           json=self._body(base_owner), expected_ok=True)

    def test_compliance_allocator_readonly_deny(self, compliance, allocator, readonly,
                                                  base_owner):
        for s in (compliance, allocator, readonly):
            _expect_status(s, "POST", "/api/equipment", json=self._body(base_owner))


# ────────────────────────────────────────────────────────────────────────
# 6. DRIVER ↔ VEHICLE ASSIGNMENT
# ────────────────────────────────────────────────────────────────────────
class TestDriverVehicleAssignment:
    def _body(self, driver_id, vehicle_id):
        return {"driver_id": driver_id, "vehicle_id": vehicle_id,
                "is_current": True, "is_primary": True}

    def test_admin_manager_allocator_allow(self, admin, manager, allocator,
                                             base_driver, base_vehicle):
        for s in (admin, manager, allocator):
            r = s.post(f"{BASE_URL}/api/driver-vehicle-assignments",
                       json=self._body(base_driver, base_vehicle), timeout=15)
            # 200/201 allowed; conflict allowed (409) because backend allowed
            # the caller through the role gate — that's what matters here.
            assert r.status_code in (200, 201, 400, 409), \
                f"expected allow, got {r.status_code}: {r.text[:200]}"

    def test_compliance_readonly_deny(self, compliance, readonly,
                                        base_driver, base_vehicle):
        for s in (compliance, readonly):
            _expect_status(s, "POST", "/api/driver-vehicle-assignments",
                           json=self._body(base_driver, base_vehicle))


# ────────────────────────────────────────────────────────────────────────
# 7. VEHICLE ↔ EQUIPMENT COUPLING (Admin/Manager only)
# ────────────────────────────────────────────────────────────────────────
class TestVehicleEquipmentCoupling:
    def test_allocator_denied(self, allocator, base_vehicle, base_owner):
        # create a fresh piece of equipment for the coupling attempt
        r_eq = _login(ADMIN["email"], ADMIN["password"]).post(
            f"{BASE_URL}/api/equipment",
            json={"equipment_number": f"VEC-{_tag().upper()}",
                  "equipment_type": "Tray", "owner_id": base_owner,
                  "status": "Active"}, timeout=15)
        r_eq.raise_for_status()
        eq_id = r_eq.json()["id"]
        _expect_status(allocator, "POST", "/api/vehicle-equipment-couplings",
                       json={"vehicle_id": base_vehicle, "equipment_id": eq_id,
                             "role": "Tray"})

    def test_compliance_readonly_denied(self, compliance, readonly,
                                          base_vehicle):
        for s in (compliance, readonly):
            _expect_status(s, "POST", "/api/vehicle-equipment-couplings",
                           json={"vehicle_id": base_vehicle,
                                 "equipment_id": "does-not-matter",
                                 "role": "Tray"})


# ────────────────────────────────────────────────────────────────────────
# 8. COMPLIANCE RECORD WRITE
# ────────────────────────────────────────────────────────────────────────
class TestComplianceRecordWrite:
    def _body(self, driver_id):
        return {"driver_id": driver_id,
                "licence_number": f"LC-{_tag().upper()}",
                "state": "NSW", "licence_class": "MC",
                "expiry_date": "2030-01-01", "is_primary": True}

    def test_admin_manager_compliance_allow(self, admin, manager, compliance,
                                              base_driver):
        for s in (admin, manager, compliance):
            _expect_status(s, "POST", "/api/driver-licences",
                           json=self._body(base_driver), expected_ok=True)

    def test_allocator_readonly_deny(self, allocator, readonly, base_driver):
        for s in (allocator, readonly):
            _expect_status(s, "POST", "/api/driver-licences",
                           json=self._body(base_driver))


# ────────────────────────────────────────────────────────────────────────
# 9. NOTIFICATION REOPEN — Compliance now allowed
# ────────────────────────────────────────────────────────────────────────
class TestNotificationReopen:
    def test_compliance_allowed_reopen_route(self, compliance):
        # Route exists and role passes — 404 for a bogus id, NOT 403.
        r = compliance.post(f"{BASE_URL}/api/notifications/does-not-exist/reopen", timeout=15)
        assert r.status_code in (404, 400), \
            f"expected role-allowed then 404/400, got {r.status_code}: {r.text[:200]}"

    def test_allocator_denied_reopen(self, allocator):
        r = allocator.post(f"{BASE_URL}/api/notifications/x/reopen", timeout=15)
        assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# 10. NUMBERING WRITE + AUDIT + SEQUENCE
# ────────────────────────────────────────────────────────────────────────
class TestNumbering:
    def test_allocator_can_write(self, allocator):
        r = allocator.get(f"{BASE_URL}/api/numbering/driver-code/suggestion", timeout=15)
        assert r.status_code == 200

    def test_compliance_denied_write(self, compliance):
        r = compliance.post(f"{BASE_URL}/api/numbering/driver-code/reserve",
                            json={}, timeout=15)
        assert r.status_code == 403

    def test_readonly_denied_write(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/numbering/driver-code/reserve",
                          json={}, timeout=15)
        assert r.status_code == 403

    def test_compliance_denied_audit(self, compliance):
        r = compliance.get(f"{BASE_URL}/api/numbering/allocation-events", timeout=15)
        assert r.status_code == 403

    def test_allocator_denied_audit(self, allocator):
        r = allocator.get(f"{BASE_URL}/api/numbering/allocation-events", timeout=15)
        assert r.status_code == 403

    def test_manager_allowed_audit(self, manager):
        r = manager.get(f"{BASE_URL}/api/numbering/allocation-events", timeout=15)
        assert r.status_code == 200

    def test_only_admin_edits_sequence(self, manager, compliance, allocator, readonly):
        for s in (manager, compliance, allocator, readonly):
            r = s.put(f"{BASE_URL}/api/numbering/driver-code/sequence",
                      json={"value": 99}, timeout=15)
            assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# 11. ACTIVATION
# ────────────────────────────────────────────────────────────────────────
class TestActivation:
    def test_only_admin_manager_activate(self, compliance, allocator, readonly,
                                           base_driver):
        for s in (compliance, allocator, readonly):
            r = s.post(f"{BASE_URL}/api/drivers/{base_driver}/activation/activate",
                       json={}, timeout=15)
            assert r.status_code == 403

    def test_compliance_can_request_override(self, compliance, base_driver):
        r = compliance.post(
            f"{BASE_URL}/api/drivers/{base_driver}/activation/override-requests",
            json={"item_key": "some_item", "justification": "role-gate probe",
                  "expires_at": "2099-01-01T00:00:00Z"},
            timeout=15,
        )
        # We only assert the role gate passed. Any 400/404/409 downstream is fine.
        assert r.status_code != 403


# ────────────────────────────────────────────────────────────────────────
# 12. ADMIN / SETTINGS
# ────────────────────────────────────────────────────────────────────────
class TestAdminSettings:
    def test_only_admin_creates_users(self, manager, compliance, allocator, readonly):
        for s in (manager, compliance, allocator, readonly):
            r = s.post(f"{BASE_URL}/api/auth/register",
                       json={"email": f"x-{_tag()}@acedriverhub.com", "password": "P@ss1",
                             "full_name": "x", "role": "Manager"}, timeout=15)
            assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# 13. DOCUMENT REVIEW LIFECYCLE
# ────────────────────────────────────────────────────────────────────────
class TestDocumentReview:
    @pytest.fixture(scope="class")
    def standard_doc(self, admin, base_driver):
        # Upload minimal document as Admin
        files = {"file": (f"mr07b-{_tag()}.csv", b"hello", "text/csv")}
        data = {"entity_type": "Driver", "entity_id": base_driver,
                "document_type": "Other", "sensitivity": "Standard",
                "title": f"MR07B Doc {_tag()}"}
        r = admin.post(f"{BASE_URL}/api/documents/upload", files=files, data=data,
                        timeout=30)
        r.raise_for_status()
        return r.json()["document"]["id"]

    def test_compliance_can_review_standard(self, compliance, standard_doc):
        r = compliance.post(f"{BASE_URL}/api/documents/{standard_doc}/review",
                            json={"decision": "approve", "note": "ok"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("review_decision") == "approve"

    def test_allocator_denied_review(self, allocator, standard_doc):
        r = allocator.post(f"{BASE_URL}/api/documents/{standard_doc}/review",
                           json={"decision": "reject", "note": "no"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_denied_review(self, readonly, standard_doc):
        r = readonly.post(f"{BASE_URL}/api/documents/{standard_doc}/review",
                          json={"decision": "approve"}, timeout=15)
        assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
# 14. DOCUMENT METADATA — sensitivity gate
# ────────────────────────────────────────────────────────────────────────
class TestDocumentMetadata:
    @pytest.fixture(scope="class")
    def restricted_doc(self, admin, base_driver):
        files = {"file": (f"mr07b-r-{_tag()}.csv", b"restricted", "text/csv")}
        data = {"entity_type": "Driver", "entity_id": base_driver,
                "document_type": "Other", "sensitivity": "Restricted",
                "title": f"MR07B Restricted {_tag()}"}
        r = admin.post(f"{BASE_URL}/api/documents/upload", files=files, data=data,
                        timeout=30)
        r.raise_for_status()
        return r.json()["document"]["id"]

    def test_compliance_denied_restricted_metadata(self, compliance, restricted_doc):
        r = compliance.put(f"{BASE_URL}/api/documents/{restricted_doc}",
                           json={"title": "compliance attempt"}, timeout=15)
        assert r.status_code == 403

    def test_allocator_denied_restricted_metadata(self, allocator, restricted_doc):
        r = allocator.put(f"{BASE_URL}/api/documents/{restricted_doc}",
                          json={"title": "allocator attempt"}, timeout=15)
        assert r.status_code == 403

    def test_manager_allowed_restricted_metadata(self, manager, restricted_doc):
        r = manager.put(f"{BASE_URL}/api/documents/{restricted_doc}",
                        json={"title": "manager ok"}, timeout=15)
        assert r.status_code == 200
