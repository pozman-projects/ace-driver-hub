"""EB-R03B-II-FIX · Targeted regression.

Fix 1 (Profile Photo thumbnail) is a pure frontend concern — the canonical
`/api/documents/{id}/preview` endpoint it depends on is already covered by
the EB-R03A test suite. No new backend endpoint is required.

Fix 2 must be verified on the backend: driver_licence_evidence MUST resolve
via `driver_licences.evidence_document_id` and never via an arbitrary
DriverLicence document_links row.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}
TINY_PDF = b"%PDF-1.4\n%R03B-II-FIX\n%%EOF\n"


def _iso_days(delta):
    return (datetime.now(timezone.utc).date() + timedelta(days=delta)).isoformat()


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200:
        pytest.skip("login failed")
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


class TestLicenceEvidenceCanonicalPointer:
    """
    Guarantees driver_licence_evidence follows evidence_document_id, not an
    arbitrary link. Also verifies the primary-link fallback still works when
    the pointer is absent.
    """

    def _make_driver_licence(self, api):
        drv = api.post(
            f"{BASE_URL}/api/drivers",
            json={"full_name": f"TEST_FIX {uuid.uuid4().hex[:6]}", "driver_status": "Active"},
            timeout=15,
        ).json()
        lic = api.post(
            f"{BASE_URL}/api/driver-licences",
            json={
                "driver_id": drv["id"],
                "licence_number": f"LC{uuid.uuid4().hex[:6].upper()}",
                "state": "NSW",
                "licence_class": "MC",
                "expiry_date": _iso_days(180),
                "is_primary": True,
                "status": "Compliant",
            },
            timeout=15,
        ).json()
        return drv["id"], lic["id"]

    def _upload_doc(self, api, entity_type, entity_id, is_primary):
        files = {"file": (f"lc_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")}
        data = {
            "title": "Licence Doc R03B-II-FIX",
            "document_type": "Driver Licence",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "relationship_type": "Evidence",
            "is_primary": "true" if is_primary else "false",
            "sensitivity": "Confidential",
        }
        r = api.post(f"{BASE_URL}/api/documents/upload", files=files, data=data, timeout=30)
        assert r.status_code in (200, 201), r.text
        return r.json()["document"]["id"]

    def test_evidence_document_id_wins_over_arbitrary_link(self, api, db):
        driver_id, licence_id = self._make_driver_licence(api)
        # 1) Create a non-primary secondary link with a different Document
        secondary_doc_id = self._upload_doc(api, "DriverLicence", licence_id, is_primary=False)
        # 2) Upload the authoritative evidence (is_primary=true → sets evidence_document_id)
        primary_doc_id = self._upload_doc(api, "DriverLicence", licence_id, is_primary=True)
        # Sanity: authoritative pointer is set
        rec = db["driver_licences"].find_one({"id": licence_id})
        assert rec["evidence_document_id"] == primary_doc_id
        # Aggregator must return the pointer's doc, not the secondary
        r = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
        assert r.status_code == 200
        ev = r.json()["documents"].get("driver_licence_evidence")
        assert ev is not None
        assert ev["id"] == primary_doc_id, f"expected primary {primary_doc_id}, got {ev['id']}"
        assert ev["id"] != secondary_doc_id

    def test_primary_link_fallback_when_pointer_absent(self, api, db):
        driver_id, licence_id = self._make_driver_licence(api)
        # Upload only a NON-primary linked doc (no is_primary → no
        # evidence_document_id pointer).
        secondary_doc_id = self._upload_doc(api, "DriverLicence", licence_id, is_primary=False)
        # Clear evidence_document_id explicitly (defensive)
        db["driver_licences"].update_one({"id": licence_id}, {"$set": {"evidence_document_id": None}})
        # Fallback should NOT pick the arbitrary link (non-primary).
        r = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
        ev = r.json()["documents"].get("driver_licence_evidence")
        assert ev is None
        # Now flip that link to is_primary=true and confirm fallback matches.
        db["document_links"].update_one(
            {"entity_type": "DriverLicence", "entity_id": licence_id, "document_id": secondary_doc_id},
            {"$set": {"is_primary": True}},
        )
        r2 = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
        ev2 = r2.json()["documents"].get("driver_licence_evidence")
        assert ev2 is not None
        assert ev2["id"] == secondary_doc_id

    def test_none_when_neither_pointer_nor_primary_link(self, api, db):
        driver_id, licence_id = self._make_driver_licence(api)
        # No documents at all
        r = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
        assert r.json()["documents"].get("driver_licence_evidence") is None
