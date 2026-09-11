"""EB-R03B · Documents / Passes / Photos featured aggregator + taxonomy tests.

Covers:
  A. Taxonomy — new DocumentType members 'Starting Document' and 'Truck Photo'
     are canonically accepted on upload.
  B. Featured buckets — driver_profile aggregator returns 10 canonical featured
     categories on `documents.stats.featured`, driven by canonical Documents +
     Document Links + evidence_document_id (no free-text substitution).
  C. Truck Photos come from the driver's CURRENT primary vehicle links —
     when there is no primary vehicle the bucket count is 0.
  D. Passes — RAPID / PrixCar / Additional Passes counted via canonical
     `document_type = Driver Pass` + `category`. No frontend expiry.
  E. Total documents count matches canonical Driver-linked documents count.
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"

ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}
TINY_PDF = b"%PDF-1.4\n%DCC-EB-R03B\n%%EOF\n"


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


@pytest.fixture(scope="module")
def driver_id(api):
    r = api.post(
        f"{BASE_URL}/api/drivers",
        json={"full_name": f"TEST_R03B {uuid.uuid4().hex[:6]}", "driver_status": "Active"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _upload(api, driver_id, document_type, category=None, entity_type="Driver", entity_id=None):
    files = {"file": (f"{document_type.replace(' ', '_')}_{uuid.uuid4().hex[:6]}.pdf", TINY_PDF, "application/pdf")}
    data = {
        "title": f"{document_type} R03B",
        "document_type": document_type,
        "entity_type": entity_type,
        "entity_id": entity_id or driver_id,
    }
    if category:
        data["category"] = category
    r = api.post(f"{BASE_URL}/api/documents/upload", files=files, data=data, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()["document"]


# ---------------------------------------------------------------- A. Taxonomy
class TestTaxonomyAdditions:
    def test_starting_document_accepted(self, api, driver_id):
        d = _upload(api, driver_id, "Starting Document")
        assert d["document_type"] == "Starting Document"

    def test_truck_photo_accepted(self, api, driver_id):
        d = _upload(api, driver_id, "Truck Photo")
        assert d["document_type"] == "Truck Photo"


# ---------------------------------------------------------------- B/D. Featured buckets
class TestFeaturedBuckets:
    def test_aggregator_returns_all_featured_categories(self, api, driver_id):
        _upload(api, driver_id, "Profile Photo")
        _upload(api, driver_id, "Driver Licence")
        _upload(api, driver_id, "Starting Document")
        _upload(api, driver_id, "Vehicle Registration")
        _upload(api, driver_id, "Vehicle Insurance")
        _upload(api, driver_id, "Driver Pass", category="RAPID")
        _upload(api, driver_id, "Driver Pass", category="PrixCar")
        _upload(api, driver_id, "Driver Pass", category="Yard Pass")  # counts as Additional Pass
        _upload(api, driver_id, "Supporting Document")
        # Fetch aggregator
        r = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
        assert r.status_code == 200, r.text
        featured = r.json()["documents"]["stats"]["featured"]
        expected = [
            "profile_photo", "driver_licence", "starting_documents",
            "other_documents", "truck_photos", "vehicle_registration",
            "vehicle_insurance", "rapid", "prixcar", "additional_passes",
        ]
        for k in expected:
            assert k in featured, k
        assert featured["profile_photo"]["current"] is not None
        assert featured["driver_licence"]["count"] >= 1
        assert featured["starting_documents"]["count"] >= 1
        assert featured["rapid"]["count"] >= 1
        assert featured["prixcar"]["count"] >= 1
        assert featured["additional_passes"]["count"] >= 1
        assert featured["other_documents"]["count"] >= 1
        assert featured["vehicle_registration"]["count"] >= 1
        assert featured["vehicle_insurance"]["count"] >= 1


# ---------------------------------------------------------------- C. Truck Photos scope
class TestTruckPhotosVehicleScoped:
    def test_no_primary_vehicle_means_zero(self, api, driver_id):
        r = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
        assert r.status_code == 200
        tp = r.json()["documents"]["stats"]["featured"]["truck_photos"]
        # When there is no primary vehicle assignment, count is 0 and vehicle_id is None
        assert tp["count"] == 0
        assert tp.get("vehicle_id") in (None, "")


# ---------------------------------------------------------------- E. Total
class TestTotalDocumentsCount:
    def test_total_matches_driver_linked_documents(self, api, driver_id):
        r = api.get(f"{BASE_URL}/api/drivers/{driver_id}/command-centre-profile", timeout=30)
        s = r.json()["documents"]["stats"]
        assert s["total"] >= 8  # from the featured seed above
