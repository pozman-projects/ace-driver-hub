"""EB-R03B-II · Driver DCC Inline Evidence Upload / Replace — acceptance tests.

Every mutation prescribed by the Blueprint is exercised end-to-end against
the live backend using ONLY canonical endpoints:

    POST /api/documents/upload                (Upload)
    POST /api/documents/{id}/versions         (Replace / new version)
    GET  /api/documents/{id}/preview          (Open)
    GET  /api/drivers/{id}/command-centre-profile  (DCC data source)

Proves:
  A. Profile Photo   — upload creates canonical evidence; replace preserves
                       history; DCC aggregator shows the current photo; no
                       photo bytes stored on the Driver record.
  B. Licence         — upload sets evidence_document_id; replace = new version.
  C. Registration    — same, primary vehicle scoped.
  D. Insurance       — same, primary vehicle scoped.
  E. Storage         — canonical adapter (EB-R03A) still owns the bytes.
  F. EB-R03B-I regression — 10 featured buckets still present.
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
TINY_PDF = b"%PDF-1.4\n%DCC-EB-R03B-II\n%%EOF\n"
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _iso_days(delta: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def api(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def db():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def driver_id(api):
    r = api.post(
        f"{BASE_URL}/api/drivers",
        json={"full_name": f"TEST_R03B2 {uuid.uuid4().hex[:6]}", "driver_status": "Active"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def licence_id(api, driver_id):
    r = api.post(
        f"{BASE_URL}/api/driver-licences",
        json={
            "driver_id": driver_id,
            "licence_number": f"LC{uuid.uuid4().hex[:6].upper()}",
            "state": "NSW",
            "licence_class": "MC",
            "expiry_date": _iso_days(180),
            "is_primary": True,
            "status": "Compliant",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def vehicle_id(api, driver_id):
    r = api.post(
        f"{BASE_URL}/api/vehicles",
        json={"registration_number": f"TR{uuid.uuid4().hex[:6].upper()}", "vehicle_type": "Prime Mover", "vehicle_status": "Active"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    vid = r.json()["id"]
    # Assign to driver as primary
    ra = api.post(
        f"{BASE_URL}/api/driver-vehicle-assignments",
        json={"driver_id": driver_id, "vehicle_id": vid, "is_primary": True, "is_active": True},
        timeout=15,
    )
    assert ra.status_code in (200, 201), ra.text
    return vid


@pytest.fixture(scope="module")
def registration_id(api, vehicle_id):
    r = api.post(
        f"{BASE_URL}/api/vehicle-registrations",
        json={
            "vehicle_id": vehicle_id,
            "state": "NSW",
            "expiry_date": _iso_days(120),
            "is_primary": True,
            "status": "Compliant",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def insurance_id(api, vehicle_id):
    r = api.post(
        f"{BASE_URL}/api/vehicle-insurance",
        json={
            "vehicle_id": vehicle_id,
            "insurer": "TestInsCo",
            "policy_number": f"POL{uuid.uuid4().hex[:6].upper()}",
            "cover_type": "Comprehensive",
            "expiry_date": _iso_days(120),
            "is_primary": True,
            "status": "Compliant",
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _upload_evidence(api, *, entity_type, entity_id, document_type, file, sensitivity="Standard"):
    files = {"file": file}
    data = {
        "title": f"{document_type} R03B-II",
        "document_type": document_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "relationship_type": "Evidence",
        "is_primary": "true",
        "sensitivity": sensitivity,
    }
    r = api.post(f"{BASE_URL}/api/documents/upload", files=files, data=data, timeout=30)
    return r


def _replace_version(api, document_id, file):
    files = {"file": file}
    r = api.post(
        f"{BASE_URL}/api/documents/{document_id}/versions",
        files=files, data={"change_note": "R03B-II replace"}, timeout=30,
    )
    return r


def _dcc(api, driver_id):
    r = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- A. PROFILE PHOTO
class TestProfilePhoto:
    def test_missing_then_upload_then_replace(self, api, driver_id, db):
        # Missing
        dcc = _dcc(api, driver_id)
        assert dcc["documents"]["profile_photo"] is None

        # Upload
        r = _upload_evidence(
            api,
            entity_type="Driver",
            entity_id=driver_id,
            document_type="Profile Photo",
            file=(f"pp_{uuid.uuid4().hex[:6]}.png", TINY_PNG, "image/png"),
        )
        assert r.status_code in (200, 201), r.text
        doc_id = r.json()["document"]["id"]

        # Aggregator now shows current photo
        dcc = _dcc(api, driver_id)
        photo = dcc["documents"]["profile_photo"]
        assert photo and photo["id"] == doc_id

        # Driver record MUST NOT carry photo bytes / blob
        drv = db["drivers"].find_one({"id": driver_id}, {"_id": 0})
        assert "photo" not in drv
        assert "profile_photo_blob" not in drv
        for k, v in drv.items():
            if isinstance(v, (bytes, bytearray)):
                pytest.fail(f"binary photo bytes on Driver record ({k})")

        # Replace = new canonical version, same document_id
        r2 = _replace_version(api, doc_id, (f"pp_{uuid.uuid4().hex[:6]}.png", TINY_PNG + b"\n", "image/png"))
        assert r2.status_code in (200, 201), r2.text
        # Verify version count == 2, and current version is the new one
        versions = list(db["document_versions"].find(
            {"document_id": doc_id}, {"_id": 0, "version_number": 1, "is_current": 1}))
        assert len(versions) == 2, versions
        current = [v for v in versions if v.get("is_current")]
        assert len(current) == 1
        # Aggregator still points to same document (not a duplicate)
        dcc = _dcc(api, driver_id)
        assert dcc["documents"]["profile_photo"]["id"] == doc_id


# ---------------------------------------------------------------- B. LICENCE
class TestLicenceEvidence:
    def test_upload_sets_evidence_document_id_and_replace_versions(self, api, driver_id, licence_id, db):
        # Missing
        assert db["driver_licences"].find_one({"id": licence_id})["evidence_document_id"] is None

        # Upload
        r = _upload_evidence(
            api,
            entity_type="DriverLicence",
            entity_id=licence_id,
            document_type="Driver Licence",
            file=(f"lc_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf"),
            sensitivity="Confidential",
        )
        assert r.status_code in (200, 201), r.text
        doc_id = r.json()["document"]["id"]
        # evidence_document_id wired
        rec = db["driver_licences"].find_one({"id": licence_id})
        assert rec["evidence_document_id"] == doc_id

        # Aggregator shows Present via documents.driver_licence_evidence
        dcc = _dcc(api, driver_id)
        assert (dcc["documents"].get("driver_licence_evidence") or {}).get("id") == doc_id

        # Replace = new version, still same doc, evidence_document_id unchanged
        r2 = _replace_version(api, doc_id, (f"lc2_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF + b"v2", "application/pdf"))
        assert r2.status_code in (200, 201), r2.text
        rec2 = db["driver_licences"].find_one({"id": licence_id})
        assert rec2["evidence_document_id"] == doc_id
        assert db["document_versions"].count_documents({"document_id": doc_id}) == 2

        # Open (preview) authorised for admin
        rp = api.get(f"{BASE_URL}/api/documents/{doc_id}/preview", timeout=15)
        assert rp.status_code == 200


# ---------------------------------------------------------------- C. REGISTRATION
class TestRegistrationEvidence:
    def test_upload_and_replace_registration(self, api, driver_id, registration_id, db):
        assert db["vehicle_registrations"].find_one({"id": registration_id})["evidence_document_id"] is None
        r = _upload_evidence(
            api,
            entity_type="VehicleRegistration",
            entity_id=registration_id,
            document_type="Vehicle Registration",
            file=(f"rg_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf"),
        )
        assert r.status_code in (200, 201), r.text
        doc_id = r.json()["document"]["id"]
        rec = db["vehicle_registrations"].find_one({"id": registration_id})
        assert rec["evidence_document_id"] == doc_id
        # Aggregator shows Present via documents.registration_evidence
        dcc = _dcc(api, driver_id)
        assert (dcc["documents"].get("registration_evidence") or {}).get("id") == doc_id
        # Replace preserves history
        r2 = _replace_version(api, doc_id, (f"rg2_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF + b"v2", "application/pdf"))
        assert r2.status_code in (200, 201), r2.text
        assert db["document_versions"].count_documents({"document_id": doc_id}) == 2
        assert db["vehicle_registrations"].find_one({"id": registration_id})["evidence_document_id"] == doc_id


# ---------------------------------------------------------------- D. INSURANCE
class TestInsuranceEvidence:
    def test_upload_and_replace_insurance(self, api, driver_id, insurance_id, db):
        assert db["vehicle_insurance_policies"].find_one({"id": insurance_id})["evidence_document_id"] is None
        r = _upload_evidence(
            api,
            entity_type="VehicleInsurancePolicy",
            entity_id=insurance_id,
            document_type="Vehicle Insurance",
            file=(f"in_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf"),
        )
        assert r.status_code in (200, 201), r.text
        doc_id = r.json()["document"]["id"]
        rec = db["vehicle_insurance_policies"].find_one({"id": insurance_id})
        assert rec["evidence_document_id"] == doc_id
        dcc = _dcc(api, driver_id)
        assert (dcc["documents"].get("insurance_evidence") or {}).get("id") == doc_id
        r2 = _replace_version(api, doc_id, (f"in2_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF + b"v2", "application/pdf"))
        assert r2.status_code in (200, 201), r2.text
        assert db["document_versions"].count_documents({"document_id": doc_id}) == 2


# ---------------------------------------------------------------- E. STORAGE
class TestStorageAdapterStillOwns:
    def test_uploaded_evidence_uses_canonical_adapter_provider(self, api, driver_id, db):
        # Upload a profile photo and inspect the current version metadata
        r = _upload_evidence(
            api,
            entity_type="Driver",
            entity_id=driver_id,
            document_type="Profile Photo",
            file=(f"pp2_{uuid.uuid4().hex[:6]}.png", TINY_PNG, "image/png"),
        )
        assert r.status_code in (200, 201)
        doc_id = r.json()["document"]["id"]
        version = db["document_versions"].find_one({"document_id": doc_id, "is_current": True}, {"_id": 0})
        # EB-R03A rule: provider must be the actual adapter, never "local-dev"
        assert version["storage_provider"] != "local-dev"
        # The value comes from the actual adapter
        import sys
        sys.path.insert(0, "/app/backend")
        from storage_module import _build_adapter_from_env
        adapter, _ = _build_adapter_from_env()
        assert version["storage_provider"] == adapter.provider


# ---------------------------------------------------------------- F. R03B-I REGRESSION
class TestR03BIFeaturedBucketsPreserved:
    def test_ten_featured_buckets_still_present(self, api, driver_id):
        dcc = _dcc(api, driver_id)
        featured = dcc["documents"]["stats"]["featured"]
        for k in [
            "profile_photo", "driver_licence", "starting_documents", "other_documents",
            "truck_photos", "vehicle_registration", "vehicle_insurance",
            "rapid", "prixcar", "additional_passes",
        ]:
            assert k in featured, k
