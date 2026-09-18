"""MR-04B · Blueprint V1 Activation Readiness Gate — acceptance tests.

Every mutation goes through canonical endpoints. No test writes anything
directly to the driver_status field via the DB.
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}
TINY_PDF = b"%PDF-1.4\n%MR04B\n%%EOF\n"

BLUEPRINT_KEYS = {
    "driver_licence", "company_details", "abn",
    "business_registration_certificate", "truck_insurance",
    "blink_driver_app", "driver_contract_signed",
}


def _iso_days(delta):
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200:
        pytest.skip("login failed")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin(admin_token):
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {admin_token}"})
    return s


@pytest.fixture(scope="session")
def db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _register_and_login(admin, role, tag):
    email = f"mr04b-{role.lower()}-{tag}@ace.example.com"
    admin.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "Test@123!", "full_name": f"MR04B {role}", "role": role},
        timeout=15,
    )
    lr = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "Test@123!"}, timeout=15)
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {lr.json()['access_token']}"})
    return s


@pytest.fixture(scope="session")
def allocator(admin):
    return _register_and_login(admin, "Allocator", uuid.uuid4().hex[:6])


def _mk_ready_driver(admin, db, tag):
    """Build a fully ready driver with all seven blueprint items satisfied.
    Driver is created in Training so the transition to Active is meaningful."""
    d = admin.post(
        f"{BASE_URL}/api/drivers",
        json={
            "full_name": f"MR04B Ready {tag}",
            "driver_status": "Training",
            "business_name": "ACE Test Pty Ltd",
            "abn": "12 345 678 901",
            "blink_driver_app_complete": True,
        },
        timeout=15,
    )
    assert d.status_code in (200, 201), d.text
    driver = d.json()
    driver_id = driver["id"]

    # 1. Licence + evidence
    lic = admin.post(
        f"{BASE_URL}/api/driver-licences",
        json={
            "driver_id": driver_id,
            "licence_number": f"LC{uuid.uuid4().hex[:6].upper()}",
            "state": "NSW",
            "licence_class": "MC",
            "expiry_date": _iso_days(365),
            "is_primary": True,
            "status": "Compliant",
        },
        timeout=15,
    ).json()
    admin.post(
        f"{BASE_URL}/api/documents/upload",
        files={"file": (f"lic_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
        data={
            "title": "Licence", "document_type": "Driver Licence",
            "entity_type": "DriverLicence", "entity_id": lic["id"],
            "relationship_type": "Evidence", "is_primary": "true",
            "sensitivity": "Confidential",
        }, timeout=30,
    )

    # 4. Certificate of Business Registration linked to Driver
    admin.post(
        f"{BASE_URL}/api/documents/upload",
        files={"file": (f"cbr_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
        data={
            "title": "Cert Business Reg",
            "document_type": "Certificate of Business Registration",
            "entity_type": "Driver", "entity_id": driver_id,
            "relationship_type": "Evidence", "is_primary": "true",
            "sensitivity": "Standard",
        }, timeout=30,
    )

    # 5. Vehicle + primary assignment + insurance
    v = admin.post(
        f"{BASE_URL}/api/vehicles",
        json={"registration_number": f"VR{uuid.uuid4().hex[:6].upper()}", "vehicle_type": "Prime Mover", "vehicle_status": "Active"},
        timeout=15,
    ).json()
    admin.post(
        f"{BASE_URL}/api/driver-vehicle-assignments",
        json={"driver_id": driver_id, "vehicle_id": v["id"], "is_primary": True, "is_active": True},
        timeout=15,
    )
    ins = admin.post(
        f"{BASE_URL}/api/vehicle-insurance",
        json={"vehicle_id": v["id"], "insurer": "X", "policy_number": f"P{uuid.uuid4().hex[:6]}",
              "cover_type": "Comprehensive", "expiry_date": _iso_days(365),
              "is_primary": True, "status": "Compliant"},
        timeout=15,
    ).json()
    admin.post(
        f"{BASE_URL}/api/documents/upload",
        files={"file": (f"ins_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
        data={
            "title": "Insurance", "document_type": "Vehicle Insurance",
            "entity_type": "VehicleInsurancePolicy", "entity_id": ins["id"],
            "relationship_type": "Evidence", "is_primary": "true",
            "sensitivity": "Standard",
        }, timeout=30,
    )

    # 7. Driver Contract document + Signed
    contract = admin.post(
        f"{BASE_URL}/api/documents/upload",
        files={"file": (f"ct_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
        data={
            "title": "Driver Contract", "document_type": "Driver Contract",
            "entity_type": "Driver", "entity_id": driver_id,
            "relationship_type": "Evidence", "is_primary": "true",
            "sensitivity": "Confidential",
        }, timeout=30,
    ).json()["document"]
    admin.patch(
        f"{BASE_URL}/api/documents/{contract['id']}/signature",
        json={"signature_status": "Signed"}, timeout=15,
    )

    return driver_id


def _readiness(admin, driver_id):
    r = admin.get(f"{BASE_URL}/api/drivers/{driver_id}/blueprint-readiness", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- A. Exact seven
class TestExactSeven:
    def test_readiness_returns_exactly_seven_items(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        rd = _readiness(admin, did)
        keys = {i["key"] for i in rd["items"]}
        assert keys == BLUEPRINT_KEYS, keys
        assert all(i["mandatory"] for i in rd["items"])


# ---------------------------------------------------------------- B. Ready
class TestReadyDriverActivates:
    def test_ready_driver_activates(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        rd = _readiness(admin, did)
        assert rd["readiness"] == "Ready", rd
        r = admin.put(f"{BASE_URL}/api/drivers/{did}", json={"driver_status": "Active"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["driver_status"] == "Active"


# ---------------------------------------------------------------- C/D. Each item missing blocks
def _make_missing(admin, db, key, tag):
    did = _mk_ready_driver(admin, db, tag)
    if key == "company_details":
        db["drivers"].update_one({"id": did}, {"$set": {"business_name": ""}})
    elif key == "abn":
        db["drivers"].update_one({"id": did}, {"$set": {"abn": ""}})
    elif key == "blink_driver_app":
        db["drivers"].update_one({"id": did}, {"$set": {"blink_driver_app_complete": False}})
    elif key == "business_registration_certificate":
        db["documents"].update_many(
            {"document_type": "Certificate of Business Registration"},
            {"$set": {"is_archived": True}},
        )
    elif key == "driver_contract_signed":
        db["documents"].update_many(
            {"document_type": "Driver Contract"},
            {"$set": {"signature_status": "Not Signed"}},
        )
    elif key == "truck_insurance":
        db["vehicle_insurance_policies"].update_many(
            {"driver_id": {"$exists": False}},
            {"$set": {"expiry_date": _iso_days(-30)}},
        )
        # Simpler: force insurance policies to expired for this driver's vehicle
        dva = db["driver_vehicle_assignments"].find_one({"driver_id": did, "is_active": True})
        if dva:
            db["vehicle_insurance_policies"].update_many(
                {"vehicle_id": dva["vehicle_id"]},
                {"$set": {"expiry_date": _iso_days(-30)}},
            )
    elif key == "driver_licence":
        db["driver_licences"].update_many(
            {"driver_id": did}, {"$set": {"expiry_date": _iso_days(-30)}}
        )
    return did


@pytest.mark.parametrize("key", sorted(BLUEPRINT_KEYS))
class TestEachItemMissingBlocks:
    def test_missing_item_marks_not_ready_and_blocks_activation(self, admin, db, key):
        did = _make_missing(admin, db, key, uuid.uuid4().hex[:4])
        rd = _readiness(admin, did)
        assert rd["readiness"] == "Not Ready"
        assert key in rd["missing"], (key, rd["missing"])
        r = admin.put(f"{BASE_URL}/api/drivers/{did}", json={"driver_status": "Active"}, timeout=15)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "DRIVER_NOT_READY"
        # Stored status unchanged
        drv = db["drivers"].find_one({"id": did})
        assert drv["driver_status"] != "Active"


# ---------------------------------------------------------------- K. Ordinary edit on Active
class TestActiveDriverOrdinaryEdit:
    def test_active_driver_can_update_unrelated_field(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        admin.put(f"{BASE_URL}/api/drivers/{did}", json={"driver_status": "Active"}, timeout=15)
        r = admin.put(f"{BASE_URL}/api/drivers/{did}", json={"mobile_number": "0400 111 222"}, timeout=15)
        assert r.status_code == 200


# ---------------------------------------------------------------- L. Non-Active transition
class TestNonActiveTransitionsFree:
    def test_training_to_probation_allowed_regardless(self, admin, db):
        d = admin.post(
            f"{BASE_URL}/api/drivers",
            json={"full_name": f"MR04B NonAct {uuid.uuid4().hex[:4]}", "driver_status": "Training"},
            timeout=15,
        ).json()
        r = admin.put(f"{BASE_URL}/api/drivers/{d['id']}", json={"driver_status": "Probation"}, timeout=15)
        assert r.status_code == 200


# ---------------------------------------------------------------- G. Contract Signed strict
class TestContractSignedStrict:
    def test_contract_on_file_without_signature_fails(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["documents"].update_many({"document_type": "Driver Contract"},
                                    {"$set": {"signature_status": "Not Signed", "signed_at": None}})
        rd = _readiness(admin, did)
        assert "driver_contract_signed" in rd["missing"]


# ---------------------------------------------------------------- E. Business Registration strictness
class TestBusinessRegistrationStrict:
    def test_generic_starting_document_does_not_satisfy_cbr(self, admin, db):
        # Fresh driver, no CBR uploaded yet — only Starting Document.
        d = admin.post(
            f"{BASE_URL}/api/drivers",
            json={"full_name": f"MR04B CBR {uuid.uuid4().hex[:4]}", "driver_status": "Training",
                  "business_name": "X", "abn": "1", "blink_driver_app_complete": True},
            timeout=15,
        ).json()
        # Upload a random StartingDocument
        admin.post(
            f"{BASE_URL}/api/documents/upload",
            files={"file": ("s.pdf", TINY_PDF, "application/pdf")},
            data={"title": "Random", "document_type": "Starting Document",
                  "entity_type": "Driver", "entity_id": d["id"]}, timeout=30,
        )
        rd = _readiness(admin, d["id"])
        assert "business_registration_certificate" in rd["missing"]


# ---------------------------------------------------------------- O. Permission leak
class TestPermissionLeak:
    def test_readiness_response_never_leaks_protected_values(self, admin, allocator, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["drivers"].update_one({"id": did}, {"$set": {"business_name": "SECRET_CORP_XYZ", "abn": "99 999 999 999"}})
        r = allocator.get(f"{BASE_URL}/api/drivers/{did}/blueprint-readiness", timeout=15)
        assert r.status_code == 200
        body = r.text
        assert "SECRET_CORP_XYZ" not in body
        assert "99 999 999 999" not in body
        # Item still present with status
        keys = {i["key"] for i in r.json()["items"]}
        assert "company_details" in keys and "abn" in keys


# ---------------------------------------------------------------- J. Direct bypass (already asserted)
# See TestEachItemMissingBlocks — PUT /api/drivers/{id} with driver_status=Active is rejected 409.
