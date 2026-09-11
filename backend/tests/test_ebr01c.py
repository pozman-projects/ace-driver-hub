"""EB-R01C · Legacy write isolation + canonical service regression."""
import os
import pytest
import requests

BASE_URL = "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}

LEGACY_RESOURCES = [
    "drivers", "licences", "truck-rego", "insurance",
    "equipment", "maintenance", "tilt-trays", "onboarding",
]

LEGACY_COLLECTIONS = {
    "drivers": "drivers",
    "licences": "licences",
    "truck-rego": "truck_regos",
    "insurance": "insurances",
    "equipment": "equipment",
    "maintenance": "maintenance",
    "tilt-trays": "tilt_trays",
    "onboarding": "onboarding",
}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# Legacy write isolation
@pytest.mark.parametrize("resource", LEGACY_RESOURCES)
def test_legacy_post_returns_410(headers, resource):
    r = requests.post(f"{BASE_URL}/api/modules/{resource}", json={"name": "x"}, headers=headers, timeout=15)
    assert r.status_code == 410, f"{resource} POST => {r.status_code}: {r.text}"
    body = r.json()
    detail = body.get("detail", {})
    assert isinstance(detail, dict), f"detail not dict: {detail}"
    assert detail.get("code") == "legacy_module_retired"


@pytest.mark.parametrize("resource", LEGACY_RESOURCES)
def test_legacy_put_returns_410(headers, resource):
    r = requests.put(f"{BASE_URL}/api/modules/{resource}/xyz", json={"name": "x"}, headers=headers, timeout=15)
    assert r.status_code == 410
    assert r.json().get("detail", {}).get("code") == "legacy_module_retired"


@pytest.mark.parametrize("resource", LEGACY_RESOURCES)
def test_legacy_delete_returns_410(headers, resource):
    r = requests.delete(f"{BASE_URL}/api/modules/{resource}/xyz", headers=headers, timeout=15)
    assert r.status_code == 410
    assert r.json().get("detail", {}).get("code") == "legacy_module_retired"


# Legacy read remains
@pytest.mark.parametrize("resource", LEGACY_RESOURCES)
def test_legacy_get_list_still_works(headers, resource):
    r = requests.get(f"{BASE_URL}/api/modules/{resource}", headers=headers, timeout=15)
    assert r.status_code == 200, f"{resource} GET => {r.status_code}"
    assert isinstance(r.json(), list)


@pytest.mark.parametrize("resource", LEGACY_RESOURCES)
def test_legacy_get_nonexistent_returns_404(headers, resource):
    r = requests.get(f"{BASE_URL}/api/modules/{resource}/nonexistent-id-xyz-123", headers=headers, timeout=15)
    assert r.status_code == 404


# Canonical service regression
def test_canonical_drivers_post_not_410(headers):
    payload = {"full_name": "TEST_EBR01C Driver", "email": "TEST_ebr01c@example.com"}
    r = requests.post(f"{BASE_URL}/api/drivers", json=payload, headers=headers, timeout=15)
    assert r.status_code != 410, f"canonical drivers POST unexpectedly returned 410: {r.text}"
    assert r.status_code in (200, 201, 400, 409, 422), f"unexpected status {r.status_code}: {r.text}"
    # cleanup if created
    if r.status_code in (200, 201):
        did = r.json().get("id")
        if did:
            requests.delete(f"{BASE_URL}/api/drivers/{did}", headers=headers, timeout=15)


def test_canonical_vehicles_list(headers):
    r = requests.get(f"{BASE_URL}/api/vehicles", headers=headers, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_canonical_equipment_list(headers):
    r = requests.get(f"{BASE_URL}/api/equipment", headers=headers, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# Vehicle compliance overview canonical endpoint
def test_vehicle_compliance_overview(headers):
    r = requests.get(f"{BASE_URL}/api/compliance/overview", params={"entity_type": "vehicle"}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "vehicles" in data


# Data-preservation: assert legacy collection counts didn't drop
def test_legacy_collection_counts_unchanged(headers):
    """Baseline counts before/after this test module -- since we didn't write, they must be identical."""
    counts_before = {}
    for r in LEGACY_RESOURCES:
        resp = requests.get(f"{BASE_URL}/api/modules/{r}", headers=headers, timeout=15)
        counts_before[r] = len(resp.json()) if resp.status_code == 200 else -1
    # attempt writes (should all fail 410)
    for r in LEGACY_RESOURCES:
        requests.post(f"{BASE_URL}/api/modules/{r}", json={"name": "TEST_should_not_persist"}, headers=headers, timeout=15)
    counts_after = {}
    for r in LEGACY_RESOURCES:
        resp = requests.get(f"{BASE_URL}/api/modules/{r}", headers=headers, timeout=15)
        counts_after[r] = len(resp.json()) if resp.status_code == 200 else -1
    assert counts_before == counts_after, f"legacy counts changed: {counts_before} => {counts_after}"
