"""MR-04B-FIX · Surgical single-source Blueprint V1 activation cutover.

Acceptance tests covering the six defect fixes only. Uses canonical HTTP
endpoints. Reuses the ready-driver builder pattern from test_mr04b_activation_gate.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}
TINY_PDF = b"%PDF-1.4\n%MR04B-FIX\n%%EOF\n"

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
    email = f"mr04b-fix-{role.lower()}-{tag}@ace.example.com"
    admin.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "Test@123!", "full_name": f"MR04B-FIX {role}", "role": role},
        timeout=15,
    )
    lr = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "Test@123!"}, timeout=15)
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {lr.json()['access_token']}"})
    return s


@pytest.fixture(scope="session")
def allocator(admin):
    return _register_and_login(admin, "Allocator", uuid.uuid4().hex[:6])


def _mk_ready_driver(admin, db, tag, *, include_licence_evidence=True):
    d = admin.post(
        f"{BASE_URL}/api/drivers",
        json={
            "full_name": f"MR04B-FIX Ready {tag}",
            "driver_status": "Training",
            "business_name": "ACE Fix Pty Ltd",
            "abn": "22 333 444 555",
            "blink_driver_app_complete": True,
        },
        timeout=15,
    )
    assert d.status_code in (200, 201), d.text
    driver_id = d.json()["id"]

    lic = admin.post(
        f"{BASE_URL}/api/driver-licences",
        json={"driver_id": driver_id, "licence_number": f"LC{uuid.uuid4().hex[:6].upper()}",
              "state": "NSW", "licence_class": "MC", "expiry_date": _iso_days(365),
              "is_primary": True, "status": "Compliant"}, timeout=15,
    ).json()
    if include_licence_evidence:
        admin.post(
            f"{BASE_URL}/api/documents/upload",
            files={"file": (f"lic_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
            data={"title": "Licence", "document_type": "Driver Licence",
                  "entity_type": "DriverLicence", "entity_id": lic["id"],
                  "relationship_type": "Evidence", "is_primary": "true",
                  "sensitivity": "Confidential"}, timeout=30,
        )

    admin.post(
        f"{BASE_URL}/api/documents/upload",
        files={"file": (f"cbr_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
        data={"title": "Cert Business Reg",
              "document_type": "Certificate of Business Registration",
              "entity_type": "Driver", "entity_id": driver_id,
              "relationship_type": "Evidence", "is_primary": "true",
              "sensitivity": "Standard"}, timeout=30,
    )

    v = admin.post(
        f"{BASE_URL}/api/vehicles",
        json={"registration_number": f"VR{uuid.uuid4().hex[:6].upper()}",
              "vehicle_type": "Prime Mover", "vehicle_status": "Active"}, timeout=15,
    ).json()
    admin.post(
        f"{BASE_URL}/api/driver-vehicle-assignments",
        json={"driver_id": driver_id, "vehicle_id": v["id"],
              "is_primary": True, "is_active": True}, timeout=15,
    )
    ins = admin.post(
        f"{BASE_URL}/api/vehicle-insurance",
        json={"vehicle_id": v["id"], "insurer": "X", "policy_number": f"P{uuid.uuid4().hex[:6]}",
              "cover_type": "Comprehensive", "expiry_date": _iso_days(365),
              "is_primary": True, "status": "Compliant"}, timeout=15,
    ).json()
    admin.post(
        f"{BASE_URL}/api/documents/upload",
        files={"file": (f"ins_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
        data={"title": "Insurance", "document_type": "Vehicle Insurance",
              "entity_type": "VehicleInsurancePolicy", "entity_id": ins["id"],
              "relationship_type": "Evidence", "is_primary": "true",
              "sensitivity": "Standard"}, timeout=30,
    )

    contract = admin.post(
        f"{BASE_URL}/api/documents/upload",
        files={"file": (f"ct_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")},
        data={"title": "Driver Contract", "document_type": "Driver Contract",
              "entity_type": "Driver", "entity_id": driver_id,
              "relationship_type": "Evidence", "is_primary": "true",
              "sensitivity": "Confidential"}, timeout=30,
    ).json()["document"]
    admin.patch(
        f"{BASE_URL}/api/documents/{contract['id']}/signature",
        json={"signature_status": "Signed"}, timeout=15,
    )

    return driver_id


# ─── Defect 1 ────────────────────────────────────────────────────────────────
class TestDefect1DedicatedActivate:
    def test_dedicated_activate_uses_blueprint_gate(self, admin, db):
        """POST /activation/activate must return 409 DRIVER_NOT_READY when one of
        the seven items is missing — no separate 400 responses, no driver_code."""
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["drivers"].update_one({"id": did}, {"$set": {"blink_driver_app_complete": False}})
        r = admin.post(f"{BASE_URL}/api/drivers/{did}/activation/activate",
                       json={"reason": "test", "set_driver_status_active": True}, timeout=15)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "DRIVER_NOT_READY"

    def test_driver_code_missing_does_not_block_activation(self, admin, db):
        """Blueprint V1: Driver Code must not gate normal activation."""
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["drivers"].update_one({"id": did}, {"$set": {"driver_code": ""}})
        # readiness stays Ready
        rd = admin.get(f"{BASE_URL}/api/drivers/{did}/blueprint-readiness", timeout=15).json()
        assert rd["readiness"] == "Ready", rd
        r = admin.post(f"{BASE_URL}/api/drivers/{did}/activation/activate",
                       json={"reason": "no driver_code", "set_driver_status_active": True}, timeout=15)
        assert r.status_code == 200, r.text
        drv = db["drivers"].find_one({"id": did})
        assert drv["driver_status"] == "Active"

    def test_put_and_activate_gate_agree(self, admin, db):
        """Same missing item -> PUT 409 and POST activate 409 with same code."""
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["drivers"].update_one({"id": did}, {"$set": {"abn": ""}})
        r_put = admin.put(f"{BASE_URL}/api/drivers/{did}", json={"driver_status": "Active"}, timeout=15)
        r_act = admin.post(f"{BASE_URL}/api/drivers/{did}/activation/activate",
                           json={"reason": "x", "set_driver_status_active": True}, timeout=15)
        assert r_put.status_code == 409
        assert r_act.status_code == 409
        assert r_put.json()["detail"]["code"] == "DRIVER_NOT_READY"
        assert r_act.json()["detail"]["code"] == "DRIVER_NOT_READY"


# ─── Defect 3 ────────────────────────────────────────────────────────────────
class TestDefect3AggregatorSingleSource:
    def test_aggregator_returns_canonical_seven_items(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        r = admin.get(f"{BASE_URL}/api/drivers/{did}/command-centre-profile", timeout=15)
        assert r.status_code == 200
        activation = r.json().get("activation")
        assert activation is not None
        keys = {i["key"] for i in activation.get("items", [])}
        assert keys == BLUEPRINT_KEYS, keys
        assert activation["readiness"] in ("Ready", "Not Ready")
        # Legacy shape indicators must be absent
        assert "mandatory_missing_items" not in activation
        assert "mandatory_total" not in activation

    def test_activation_summary_endpoint_returns_canonical_seven(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        r = admin.get(f"{BASE_URL}/api/drivers/{did}/activation-summary", timeout=15)
        assert r.status_code == 200
        body = r.json()
        keys = {i["key"] for i in body.get("items", [])}
        assert keys == BLUEPRINT_KEYS

    def test_missing_driver_code_and_dispatch_does_not_flag_readiness(self, admin, db):
        """Legacy driver_code / dispatch_number / owner_relationship / vehicle_assignment
        must NOT appear as blockers in the canonical activation section."""
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["drivers"].update_one({"id": did}, {"$set": {"driver_code": "", "dispatch_number": ""}})
        r = admin.get(f"{BASE_URL}/api/drivers/{did}/command-centre-profile", timeout=15)
        activation = r.json()["activation"]
        assert activation["readiness"] == "Ready", activation
        assert not activation["missing"]


# ─── Defect 4 ────────────────────────────────────────────────────────────────
class TestDefect4DefaultTemplate:
    def test_default_template_module_constant_is_exact_seven(self):
        """The DEFAULT_ITEMS constant that seeds fresh V1 templates now has
        exactly the seven Blueprint mandatory items."""
        from activation_module import DEFAULT_ITEMS, BLUEPRINT_V1_ITEM_KEYS
        keys = [i["item_key"] for i in DEFAULT_ITEMS]
        assert keys == list(BLUEPRINT_V1_ITEM_KEYS)
        assert all(i["mandatory"] for i in DEFAULT_ITEMS)
        assert len(DEFAULT_ITEMS) == 7


# ─── Defect 5 ────────────────────────────────────────────────────────────────
class TestDefect5CanonicalCompliance:
    def test_licence_uses_canonical_compliance(self, admin, db):
        """Licence readiness must mirror canonical Compliance driver_summary."""
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        # Push licence to Urgent (within 7 days) — canonical treats this as
        # still 'Conditions' i.e. acceptable, so V1 stays Ready.
        db["driver_licences"].update_many(
            {"driver_id": did}, {"$set": {"expiry_date": _iso_days(5)}}
        )
        rd = admin.get(f"{BASE_URL}/api/drivers/{did}/blueprint-readiness", timeout=15).json()
        # Confirm Compliance returns Urgent for this driver
        summ = admin.get(f"{BASE_URL}/api/compliance/drivers/{did}", timeout=15).json()
        lic_comp = next(c for c in summ["components"] if c["component"] == "primary_licence")
        assert lic_comp["status"] == "Urgent"
        # Blueprint should still pass on Urgent (canonical Conditions -> pass)
        lic_item = next(i for i in rd["items"] if i["key"] == "driver_licence")
        assert lic_item["complete"], lic_item

    def test_licence_expired_fails(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["driver_licences"].update_many(
            {"driver_id": did}, {"$set": {"expiry_date": _iso_days(-5)}}
        )
        rd = admin.get(f"{BASE_URL}/api/drivers/{did}/blueprint-readiness", timeout=15).json()
        lic_item = next(i for i in rd["items"] if i["key"] == "driver_licence")
        assert not lic_item["complete"]
        # Reason must reference canonical compliance status, not raw expiry date
        assert "compliance" in lic_item["reason"].lower()

    def test_insurance_uses_canonical_compliance(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        # Set insurance to Urgent
        dva = db["driver_vehicle_assignments"].find_one({"driver_id": did, "is_active": True})
        db["vehicle_insurance_policies"].update_many(
            {"vehicle_id": dva["vehicle_id"]}, {"$set": {"expiry_date": _iso_days(3)}}
        )
        rd = admin.get(f"{BASE_URL}/api/drivers/{did}/blueprint-readiness", timeout=15).json()
        ins_item = next(i for i in rd["items"] if i["key"] == "truck_insurance")
        assert ins_item["complete"], ins_item
        assert "compliance" in ins_item["reason"].lower()


# ─── Defect 6 ────────────────────────────────────────────────────────────────
class TestDefect6LicenceEvidenceNotBlocker:
    def test_licence_ready_without_evidence_document(self, admin, db):
        """The primary licence has valid expiry but NO uploaded evidence.
        Blueprint V1 must still pass since evidence is not a V1 blocker."""
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4], include_licence_evidence=False)
        # Also clear the evidence_document_id pointer to prove it doesn't gate
        db["driver_licences"].update_many(
            {"driver_id": did}, {"$set": {"evidence_document_id": None}}
        )
        rd = admin.get(f"{BASE_URL}/api/drivers/{did}/blueprint-readiness", timeout=15).json()
        lic_item = next(i for i in rd["items"] if i["key"] == "driver_licence")
        assert lic_item["complete"], lic_item
        assert rd["readiness"] == "Ready", rd


# ─── Preservation checks ─────────────────────────────────────────────────────
class TestPreservation:
    def test_mr07a_no_leak_via_readiness(self, admin, allocator, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        db["drivers"].update_one({"id": did}, {"$set": {"business_name": "LEAKY_CORP", "abn": "88 888 888 888"}})
        r = allocator.get(f"{BASE_URL}/api/drivers/{did}/blueprint-readiness", timeout=15)
        assert r.status_code == 200
        body = r.text
        assert "LEAKY_CORP" not in body
        assert "88 888 888 888" not in body

    def test_active_driver_ordinary_edit_not_gated(self, admin, db):
        did = _mk_ready_driver(admin, db, uuid.uuid4().hex[:4])
        admin.put(f"{BASE_URL}/api/drivers/{did}", json={"driver_status": "Active"}, timeout=15)
        # Break a V1 item — ordinary edit still succeeds
        db["drivers"].update_one({"id": did}, {"$set": {"blink_driver_app_complete": False}})
        r = admin.put(f"{BASE_URL}/api/drivers/{did}", json={"mobile_number": "0400 999 888"}, timeout=15)
        assert r.status_code == 200, r.text

    def test_non_active_transition_not_gated(self, admin):
        d = admin.post(f"{BASE_URL}/api/drivers",
                       json={"full_name": f"FIX NonAct {uuid.uuid4().hex[:4]}", "driver_status": "Training"},
                       timeout=15).json()
        r = admin.put(f"{BASE_URL}/api/drivers/{d['id']}", json={"driver_status": "On Leave"}, timeout=15)
        assert r.status_code == 200
