"""ACE Driver Hub - Phase 1 iteration 3: Driver-centric relationships.

Covers:
- Seeded drivers now have driver_number + company
- Existing seeded child records backfilled with driver_id
- POST creates with driver_id persist
- GET /api/drivers/{id}/profile — shape, linked records grouping, auth, 404
- GET /api/compliance/expiring records contain driver_id + driver_name
"""
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"

DRIVER_LINKED_SLUGS = ["licences", "truck-rego", "insurance", "equipment", "maintenance", "tilt-trays", "onboarding"]


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def seeded_drivers(admin_headers):
    r = requests.get(f"{API}/modules/drivers", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    drivers = r.json()
    assert isinstance(drivers, list) and len(drivers) >= 3
    return drivers


class TestSeededDriverEnrichment:
    """Drivers must have driver_number + company after backfill."""

    def test_seeded_drivers_have_number_and_company(self, seeded_drivers):
        by_name = {d["name"]: d for d in seeded_drivers if d.get("name")}
        for n, expected_num in [("James Carter", "DRV-001"), ("Liam O'Brien", "DRV-002"), ("Noah Williams", "DRV-003")]:
            assert n in by_name, f"missing seeded driver {n}"
            d = by_name[n]
            assert d.get("driver_number") == expected_num, f"{n} driver_number={d.get('driver_number')}"
            assert d.get("company") == "ACE Car Freighters"


class TestBackfillLinks:
    """Child records seeded by name should have driver_id populated by backfill."""

    @pytest.mark.parametrize("slug,name_field", [
        ("licences", "driver_name"),
        ("truck-rego", "driver_name"),
        ("insurance", "driver_name"),
        ("equipment", "assigned_to"),
        ("tilt-trays", "driver_assigned"),
    ])
    def test_seeded_records_have_driver_id(self, admin_headers, seeded_drivers, slug, name_field):
        names = {d["name"] for d in seeded_drivers if d.get("name")}
        r = requests.get(f"{API}/modules/{slug}", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        rows = r.json()
        # find seeded rows (created_by == system-seed) whose source name matches a real driver
        for row in rows:
            if row.get("created_by") == "system-seed" and row.get(name_field) in names:
                assert row.get("driver_id"), f"{slug} row {row.get('id')} missing driver_id (name={row.get(name_field)})"


class TestCreateWithDriverId:
    """POST with driver_id should persist and be returned by GET."""

    @pytest.mark.parametrize("slug,extra", [
        ("licences", {"licence_number": "TEST-LIC", "licence_class": "HR", "issue_date": "2025-01-01", "expiry_date": "2027-01-01", "status": "Valid"}),
        ("truck-rego", {"rego_number": "TEST-TR", "make": "Test", "model": "M"}),
        ("insurance", {"policy_number": "TEST-INS", "provider": "TestCo", "expiry_date": "2027-01-01"}),
        ("equipment", {"equipment_id": "TEST-EQ", "name": "TestKit"}),
        ("maintenance", {"vehicle_rego": "TEST-MT", "service_type": "Test"}),
        ("tilt-trays", {"tray_id": "TEST-TT3", "rego": "TLT-T3"}),
        ("onboarding", {"full_name": "TEST_Onb3", "stage": "Test"}),
    ])
    def test_create_with_driver_id(self, admin_headers, seeded_drivers, slug, extra):
        driver = seeded_drivers[0]
        payload = dict(extra)
        payload["driver_id"] = driver["id"]
        r = requests.post(f"{API}/modules/{slug}", json=payload, headers=admin_headers, timeout=20)
        assert r.status_code == 200, f"create {slug}: {r.text}"
        created = r.json()
        assert created.get("driver_id") == driver["id"]
        item_id = created["id"]
        # GET back
        rg = requests.get(f"{API}/modules/{slug}/{item_id}", headers=admin_headers, timeout=20)
        assert rg.status_code == 200
        assert rg.json().get("driver_id") == driver["id"]
        # cleanup
        requests.delete(f"{API}/modules/{slug}/{item_id}", headers=admin_headers, timeout=20)


class TestDriverProfile:
    def test_profile_requires_auth(self, seeded_drivers):
        d = seeded_drivers[0]
        r = requests.get(f"{API}/drivers/{d['id']}/profile", timeout=20)
        assert r.status_code == 401

    def test_profile_404_for_unknown(self, admin_headers):
        r = requests.get(f"{API}/drivers/{uuid.uuid4()}/profile", headers=admin_headers, timeout=20)
        assert r.status_code == 404

    def test_profile_shape(self, admin_headers, seeded_drivers):
        d = next(x for x in seeded_drivers if x.get("name") == "James Carter")
        r = requests.get(f"{API}/drivers/{d['id']}/profile", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "driver" in body and "linked" in body
        assert body["driver"]["id"] == d["id"]
        assert body["driver"]["name"] == "James Carter"
        for slug in DRIVER_LINKED_SLUGS:
            assert slug in body["linked"], f"missing linked group {slug}"
            assert isinstance(body["linked"][slug], list)

    def test_profile_links_filtered_by_driver_id(self, admin_headers, seeded_drivers):
        d = next(x for x in seeded_drivers if x.get("name") == "James Carter")
        r = requests.get(f"{API}/drivers/{d['id']}/profile", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        linked = r.json()["linked"]
        # James seeded with 1 licence + 1 truck-rego + 1 insurance + 1 equipment + 1 tilt-tray
        assert len(linked["licences"]) >= 1
        assert len(linked["truck-rego"]) >= 1
        assert len(linked["insurance"]) >= 1
        assert len(linked["equipment"]) >= 1
        assert len(linked["tilt-trays"]) >= 1
        # All linked rows must carry the right driver_id
        for slug in DRIVER_LINKED_SLUGS:
            for row in linked[slug]:
                assert row.get("driver_id") == d["id"], f"{slug} row {row.get('id')} has wrong driver_id"

    def test_profile_isolation_between_drivers(self, admin_headers, seeded_drivers):
        james = next(x for x in seeded_drivers if x.get("name") == "James Carter")
        noah = next(x for x in seeded_drivers if x.get("name") == "Noah Williams")
        rj = requests.get(f"{API}/drivers/{james['id']}/profile", headers=admin_headers, timeout=20).json()
        rn = requests.get(f"{API}/drivers/{noah['id']}/profile", headers=admin_headers, timeout=20).json()
        james_lic_ids = {x["id"] for x in rj["linked"]["licences"]}
        noah_lic_ids = {x["id"] for x in rn["linked"]["licences"]}
        # No overlap
        assert james_lic_ids.isdisjoint(noah_lic_ids)


class TestComplianceDriverFields:
    def test_records_have_driver_id_and_name(self, admin_headers, seeded_drivers):
        r = requests.get(f"{API}/compliance/expiring", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        body = r.json()
        names = {d["name"] for d in seeded_drivers if d.get("name")}
        seen_driver_id = False
        for rec in body["records"]:
            assert "driver_id" in rec
            assert "driver_name" in rec
            if rec.get("driver_id"):
                seen_driver_id = True
                # driver_name should resolve to a seeded driver's name when driver_id is present
                assert rec["driver_name"] in names, f"unexpected driver_name {rec['driver_name']}"
        # Given backfill, at least some at-risk records should have driver_id (Noah licence is expired)
        if body["totals"]["expired"] + body["totals"]["expiring"] >= 1:
            assert seen_driver_id, "expected at least one at-risk record to carry driver_id post-backfill"
