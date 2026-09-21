"""MR-07A · Backend Permissions & Data Protection — acceptance tests.

Proves canonical Driver endpoints AND the DCC aggregator enforce the LOCKED V1
Driver-account rules consistently. Also confirms ReadOnly cannot mutate
canonical operational records, and that the legacy write wall + document
sensitivity gates remain in place.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}

RESTRICTED_FIELDS = {"business_name", "abn", "payroll_number", "payment_percentage"}


def _iso_days(delta: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


# ---------------------------------------------------------------- Fixtures
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code}")
    return r.json()["access_token"]


def _mk_session(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def admin(admin_token):
    return _mk_session(admin_token)


def _register_and_login(admin, role, tag):
    email = f"mr07a-{role.lower()}-{tag}@ace.example.com"
    password = "Test@123!"
    r = admin.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password, "full_name": f"MR07A {role}", "role": role},
        timeout=15,
    )
    # 409/400 = already registered; that is OK when tests re-run
    assert r.status_code in (200, 201, 400, 409), r.text
    lr = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert lr.status_code == 200, lr.text
    return _mk_session(lr.json()["access_token"])


@pytest.fixture(scope="session")
def role_tag():
    return uuid.uuid4().hex[:6]


@pytest.fixture(scope="session")
def manager(admin, role_tag):
    return _register_and_login(admin, "Manager", role_tag)


@pytest.fixture(scope="session")
def compliance(admin, role_tag):
    return _register_and_login(admin, "Compliance", role_tag)


@pytest.fixture(scope="session")
def allocator(admin, role_tag):
    return _register_and_login(admin, "Allocator", role_tag)


@pytest.fixture(scope="session")
def readonly(admin, role_tag):
    return _register_and_login(admin, "ReadOnly", role_tag)


@pytest.fixture(scope="module")
def driver(admin):
    r = admin.post(
        f"{BASE_URL}/api/drivers",
        json={
            "full_name": f"MR07A driver {uuid.uuid4().hex[:6]}",
            "driver_status": "Active",
            "business_name": "ACME Pty Ltd",
            "abn": "12 345 678 901",
            "payroll_number": "P-777",
            "payment_percentage": 42.5,
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---------------------------------------------------------------- A/B. Canonical Driver READ
class TestCanonicalDriverRead:
    def _assert_present(self, doc):
        for f in RESTRICTED_FIELDS:
            assert f in doc, f"expected {f} present, got: {list(doc.keys())}"

    def _assert_absent(self, doc):
        for f in RESTRICTED_FIELDS:
            assert f not in doc, f"expected {f} STRIPPED, got: {list(doc.keys())}"

    @pytest.mark.parametrize("session_name", ["admin", "manager"])
    def test_privileged_roles_see_account_fields(self, request, driver, session_name):
        sess = request.getfixturevalue(session_name)
        r = sess.get(f"{BASE_URL}/api/drivers/{driver['id']}", timeout=15)
        assert r.status_code == 200
        self._assert_present(r.json())
        # List endpoint
        rl = sess.get(f"{BASE_URL}/api/drivers", timeout=15)
        assert rl.status_code == 200
        row = next(d for d in rl.json() if d["id"] == driver["id"])
        self._assert_present(row)

    @pytest.mark.parametrize("session_name", ["compliance", "allocator", "readonly"])
    def test_non_privileged_roles_have_fields_stripped(self, request, driver, session_name):
        sess = request.getfixturevalue(session_name)
        r = sess.get(f"{BASE_URL}/api/drivers/{driver['id']}", timeout=15)
        assert r.status_code == 200
        self._assert_absent(r.json())
        # List endpoint
        rl = sess.get(f"{BASE_URL}/api/drivers", timeout=15)
        assert rl.status_code == 200
        row = next(d for d in rl.json() if d["id"] == driver["id"])
        self._assert_absent(row)


# ---------------------------------------------------------------- C/D/E. WRITE rules
class TestCanonicalDriverWrite:
    @pytest.mark.parametrize("session_name", ["admin", "manager"])
    def test_privileged_can_update_restricted_fields(self, request, admin, session_name):
        # Fresh driver per test to keep them independent
        d = admin.post(
            f"{BASE_URL}/api/drivers",
            json={"full_name": f"Wperm {session_name} {uuid.uuid4().hex[:4]}", "driver_status": "Active"},
            timeout=15,
        ).json()
        sess = request.getfixturevalue(session_name)
        r = sess.put(
            f"{BASE_URL}/api/drivers/{d['id']}",
            json={"payroll_number": "P-999"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Admin verifies stored value
        v = admin.get(f"{BASE_URL}/api/drivers/{d['id']}", timeout=15).json()
        assert v["payroll_number"] == "P-999"

    @pytest.mark.parametrize("session_name", ["compliance", "allocator", "readonly"])
    def test_non_privileged_403_when_restricted_fields_supplied(self, request, admin, session_name):
        d = admin.post(
            f"{BASE_URL}/api/drivers",
            json={
                "full_name": f"Wperm2 {session_name} {uuid.uuid4().hex[:4]}",
                "driver_status": "Active",
                "payroll_number": "ORIGINAL",
            },
            timeout=15,
        ).json()
        sess = request.getfixturevalue(session_name)
        r = sess.put(
            f"{BASE_URL}/api/drivers/{d['id']}",
            json={"payroll_number": "SNEAKY"},
            timeout=15,
        )
        # ReadOnly is blocked earlier by _require_write_role (403).
        # Compliance/Allocator have write role but lack account-write.
        assert r.status_code == 403, r.text
        # Value must not have changed
        v = admin.get(f"{BASE_URL}/api/drivers/{d['id']}", timeout=15).json()
        assert v["payroll_number"] == "ORIGINAL"

    @pytest.mark.parametrize("session_name", ["compliance", "allocator"])
    def test_non_privileged_can_still_update_non_restricted_fields(
        self, request, admin, session_name
    ):
        # MR-07B · Compliance and Allocator are now denied Driver core writes
        # (mobile_number is a core master field). This test used to pass under
        # the pre-MR-07B "everyone-but-ReadOnly" write policy. The canonical
        # matrix now blocks both roles from Driver core edits — the resulting
        # 403 is the intended behaviour.
        d = admin.post(
            f"{BASE_URL}/api/drivers",
            json={"full_name": f"Wperm3 {session_name} {uuid.uuid4().hex[:4]}", "driver_status": "Active"},
            timeout=15,
        ).json()
        sess = request.getfixturevalue(session_name)
        r = sess.put(
            f"{BASE_URL}/api/drivers/{d['id']}",
            json={"mobile_number": "0400 000 111"},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    @pytest.mark.parametrize("session_name", ["compliance", "allocator"])
    def test_non_privileged_create_with_restricted_fields_blocked(
        self, request, session_name
    ):
        sess = request.getfixturevalue(session_name)
        r = sess.post(
            f"{BASE_URL}/api/drivers",
            json={
                "full_name": f"Create block {session_name}",
                "driver_status": "Active",
                "abn": "12 345 678 901",
            },
            timeout=15,
        )
        assert r.status_code == 403, r.text


# ---------------------------------------------------------------- F. DCC aggregator
class TestDCCAggregator:
    def test_admin_sees_account_fields(self, admin, driver):
        r = admin.get(f"{BASE_URL}/api/drivers/{driver['id']}/command-centre-profile", timeout=30)
        assert r.status_code == 200
        drv = r.json()["driver"]
        for f in RESTRICTED_FIELDS:
            assert f in drv, f

    def test_allocator_has_fields_stripped(self, allocator, driver):
        r = allocator.get(f"{BASE_URL}/api/drivers/{driver['id']}/command-centre-profile", timeout=30)
        assert r.status_code == 200
        drv = r.json()["driver"]
        for f in RESTRICTED_FIELDS:
            assert f not in drv, f


# ---------------------------------------------------------------- G. ReadOnly write block
class TestReadOnlyWriteBlock:
    def test_readonly_cannot_create_driver(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/drivers", json={"full_name": "RO", "driver_status": "Active"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_cannot_create_vehicle(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/vehicles", json={"registration_number": "RO1", "vehicle_status": "Active"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_cannot_create_equipment(self, readonly):
        r = readonly.post(f"{BASE_URL}/api/equipment", json={"equipment_number": f"RO{uuid.uuid4().hex[:4]}", "equipment_type": "Tray"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_cannot_create_driver_licence(self, admin, readonly):
        d = admin.post(f"{BASE_URL}/api/drivers", json={"full_name": "LcOwner", "driver_status": "Active"}, timeout=15).json()
        r = readonly.post(
            f"{BASE_URL}/api/driver-licences",
            json={
                "driver_id": d["id"],
                "licence_number": f"RO{uuid.uuid4().hex[:6].upper()}",
                "state": "NSW",
                "licence_class": "MC",
                "expiry_date": _iso_days(180),
                "status": "Compliant",
            },
            timeout=15,
        )
        assert r.status_code == 403

    def test_readonly_cannot_create_vehicle_registration(self, admin, readonly):
        v = admin.post(f"{BASE_URL}/api/vehicles", json={"registration_number": f"ROV{uuid.uuid4().hex[:4]}", "vehicle_status": "Active"}, timeout=15).json()
        r = readonly.post(
            f"{BASE_URL}/api/vehicle-registrations",
            json={"vehicle_id": v["id"], "state": "NSW", "expiry_date": _iso_days(90), "status": "Compliant"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_readonly_cannot_create_vehicle_insurance(self, admin, readonly):
        v = admin.post(f"{BASE_URL}/api/vehicles", json={"registration_number": f"ROI{uuid.uuid4().hex[:4]}", "vehicle_status": "Active"}, timeout=15).json()
        r = readonly.post(
            f"{BASE_URL}/api/vehicle-insurance",
            json={
                "vehicle_id": v["id"],
                "insurer": "TestCo",
                "policy_number": f"RO{uuid.uuid4().hex[:4]}",
                "cover_type": "Comprehensive",
                "expiry_date": _iso_days(90),
                "status": "Compliant",
            },
            timeout=15,
        )
        assert r.status_code == 403


# ---------------------------------------------------------------- H. Legacy wall
class TestLegacyWriteWallStillHolds:
    @pytest.mark.parametrize("resource", ["licences", "insurance", "tilt-trays"])
    def test_legacy_module_write_returns_410(self, admin, resource):
        r = admin.post(f"{BASE_URL}/api/modules/{resource}", json={"any": "thing"}, timeout=15)
        assert r.status_code == 410


# ---------------------------------------------------------------- I. Document security
class TestDocumentSecurity:
    def test_document_response_never_contains_storage_key(self, admin, driver):
        TINY = b"%PDF-1.4\n%MR07A\n%%EOF\n"
        r = admin.post(
            f"{BASE_URL}/api/documents/upload",
            files={"file": (f"m07a_{uuid.uuid4().hex[:6]}.pdf", TINY, "application/pdf")},
            data={
                "title": "MR07A doc",
                "document_type": "Driver Licence",
                "entity_type": "Driver",
                "entity_id": driver["id"],
                "sensitivity": "Confidential",
            },
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        # Storage key must never leak on any response variant
        assert "storage_key" not in r.text
        # Detail endpoint
        doc_id = r.json()["document"]["id"]
        rd = admin.get(f"{BASE_URL}/api/documents/{doc_id}", timeout=15)
        assert rd.status_code == 200
        assert "storage_key" not in rd.text
        # Listing
        rl = admin.get(f"{BASE_URL}/api/documents", timeout=15)
        assert rl.status_code == 200
        assert "storage_key" not in rl.text

    def test_confidential_document_binary_gate_still_applies(self, admin, allocator, driver):
        TINY = b"%PDF-1.4\n%MR07A\n%%EOF\n"
        r = admin.post(
            f"{BASE_URL}/api/documents/upload",
            files={"file": (f"m07a2_{uuid.uuid4().hex[:6]}.pdf", TINY, "application/pdf")},
            data={
                "title": "Restricted",
                "document_type": "Driver Licence",
                "entity_type": "Driver",
                "entity_id": driver["id"],
                "sensitivity": "Restricted",
            },
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        doc_id = r.json()["document"]["id"]
        # Allocator may not preview a Restricted doc
        rp = allocator.get(f"{BASE_URL}/api/documents/{doc_id}/preview", timeout=15)
        assert rp.status_code == 403, rp.text
