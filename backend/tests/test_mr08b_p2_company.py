"""MR-08B-P2 · Canonical Company Manager + Default Company tests.

Backend-only assertions. Frontend visibility is not a security control
and is not covered here.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}


def _tag(): return uuid.uuid4().hex[:8]


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    r.raise_for_status()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _register(admin, role):
    email = f"mr08bp2-{role.lower()}-{_tag()}@acedriverhub.com"
    admin.post(f"{BASE_URL}/api/auth/register",
                json={"email": email, "password": "P@ssword1",
                      "full_name": f"MR08BP2 {role}", "role": role},
                timeout=15).raise_for_status()
    return _login(email, "P@ssword1")


@pytest.fixture(scope="module")
def admin():        return _login(ADMIN["email"], ADMIN["password"])

@pytest.fixture(scope="module")
def manager(admin): return _register(admin, "Manager")

@pytest.fixture(scope="module")
def compliance(admin): return _register(admin, "Compliance")

@pytest.fixture(scope="module")
def allocator(admin):  return _register(admin, "Allocator")

@pytest.fixture(scope="module")
def readonly(admin):   return _register(admin, "ReadOnly")


# ── Helpers ───────────────────────────────────────────────────────────
def _create_company(session, name):
    return session.post(f"{BASE_URL}/api/companies", json={"name": name}, timeout=15)


def _get_default(session):
    r = session.get(f"{BASE_URL}/api/settings/default-company", timeout=15)
    r.raise_for_status()
    return r.json()


def _set_default(session, cid):
    return session.put(f"{BASE_URL}/api/settings/default-company",
                       json={"company_id": cid}, timeout=15)


# ── (23) Idempotent ACE seed always present at start ────────────────────
class TestSeed:
    def test_ace_company_exists_and_is_default(self, admin):
        r = admin.get(f"{BASE_URL}/api/companies", timeout=15)
        r.raise_for_status()
        ace = [c for c in r.json() if c["name"] == "ACE Car Freighters" and not c["is_archived"]]
        assert len(ace) == 1, f"seed produced {len(ace)} ACE companies"
        # And default is set
        default = _get_default(admin)
        assert default["company_id"] == ace[0]["id"]


# ── (1) Create Company · role gates ─────────────────────────────────────
class TestCreateCompany:
    def test_admin_allow(self, admin):
        r = _create_company(admin, f"MR08BP2 Admin Co {_tag()}")
        assert r.status_code == 200, r.text

    def test_manager_allow(self, manager):
        r = _create_company(manager, f"MR08BP2 Mgr Co {_tag()}")
        assert r.status_code == 200, r.text

    def test_compliance_deny(self, compliance):
        assert _create_company(compliance, f"C {_tag()}").status_code == 403

    def test_allocator_deny(self, allocator):
        assert _create_company(allocator, f"A {_tag()}").status_code == 403

    def test_readonly_deny(self, readonly):
        assert _create_company(readonly, f"R {_tag()}").status_code == 403

    def test_name_required(self, admin):
        assert admin.post(f"{BASE_URL}/api/companies", json={"name": "   "}, timeout=15).status_code == 422

    def test_active_duplicate_rejected(self, admin):
        name = f"MR08BP2 Dup {_tag()}"
        assert _create_company(admin, name).status_code == 200
        assert _create_company(admin, name).status_code == 409  # case-insensitive too
        assert _create_company(admin, name.upper()).status_code == 409


# ── (2) Edit Company ────────────────────────────────────────────────────
class TestEditCompany:
    @pytest.fixture(scope="class")
    def target(self, admin):
        r = _create_company(admin, f"MR08BP2 Edit {_tag()}")
        r.raise_for_status()
        return r.json()["id"]

    def test_admin_can_rename(self, admin, target):
        new_name = f"Renamed {_tag()}"
        r = admin.put(f"{BASE_URL}/api/companies/{target}", json={"name": new_name}, timeout=15)
        assert r.status_code == 200
        assert r.json()["name"] == new_name

    def test_compliance_cannot_edit(self, compliance, target):
        assert compliance.put(f"{BASE_URL}/api/companies/{target}",
                              json={"name": "nope"}, timeout=15).status_code == 403


# ── (3, 4) Archive Company · Default Company blocker ────────────────────
class TestArchiveCompany:
    def test_admin_can_archive_non_default(self, admin):
        r = _create_company(admin, f"MR08BP2 Arch {_tag()}")
        cid = r.json()["id"]
        assert admin.delete(f"{BASE_URL}/api/companies/{cid}", timeout=15).status_code == 200

    def test_default_company_cannot_be_archived(self, admin):
        default = _get_default(admin)["company_id"]
        r = admin.delete(f"{BASE_URL}/api/companies/{default}", timeout=15)
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert isinstance(detail, dict) and detail.get("code") == "COMPANY_IS_DEFAULT"

    def test_allocator_cannot_archive(self, admin, allocator):
        r = _create_company(admin, f"MR08BP2 ArchAlloc {_tag()}")
        cid = r.json()["id"]
        assert allocator.delete(f"{BASE_URL}/api/companies/{cid}", timeout=15).status_code == 403


# ── (5, 6, 7) Set Default ───────────────────────────────────────────────
class TestSetDefault:
    def test_admin_can_set_default(self, admin):
        r = _create_company(admin, f"MR08BP2 Def {_tag()}")
        cid = r.json()["id"]
        assert _set_default(admin, cid).status_code == 200
        assert _get_default(admin)["company_id"] == cid
        # Restore ACE as default so remaining tests see the seed default
        ace = [c for c in admin.get(f"{BASE_URL}/api/companies", timeout=15).json()
               if c["name"] == "ACE Car Freighters"][0]
        _set_default(admin, ace["id"]).raise_for_status()

    def test_compliance_cannot_set_default(self, admin, compliance):
        cid = _create_company(admin, f"MR08BP2 DefC {_tag()}").json()["id"]
        assert _set_default(compliance, cid).status_code == 403

    def test_invalid_company_id_rejected(self, admin):
        assert _set_default(admin, "does-not-exist").status_code == 404

    def test_archived_company_cannot_be_default(self, admin):
        cid = _create_company(admin, f"MR08BP2 DefArch {_tag()}").json()["id"]
        admin.delete(f"{BASE_URL}/api/companies/{cid}", timeout=15).raise_for_status()
        assert _set_default(admin, cid).status_code == 409


# ── (8-11) Changing Default does not modify existing records ────────────
class TestExistingRecordsNotMutated:
    @pytest.fixture(scope="class")
    def seed_default(self, admin):
        # Ensure ACE is the default
        ace = [c for c in admin.get(f"{BASE_URL}/api/companies", timeout=15).json()
               if c["name"] == "ACE Car Freighters" and not c["is_archived"]][0]
        _set_default(admin, ace["id"]).raise_for_status()
        return ace["id"]

    def test_change_default_does_not_rewrite_existing_records(self, admin, seed_default):
        # Create one of each entity with the current default
        drv_id = admin.post(f"{BASE_URL}/api/drivers",
                            json={"full_name": f"MR08BP2 Existing {_tag()}",
                                  "driver_status": "Training"}, timeout=15).json()["id"]
        own_id = admin.post(f"{BASE_URL}/api/owners",
                            json={"name": f"MR08BP2 Owner {_tag()}",
                                  "primary_email": f"o{_tag()}@acedriverhub.com"},
                            timeout=15).json()["id"]
        veh_id = admin.post(f"{BASE_URL}/api/vehicles",
                            json={"registration_number": f"MR-{_tag().upper()}",
                                  "make": "T", "model": "MR08BP2",
                                  "owner_id": own_id, "vehicle_status": "Active"},
                            timeout=15).json()["id"]
        eq_id = admin.post(f"{BASE_URL}/api/equipment",
                            json={"equipment_number": f"EQ-{_tag().upper()}",
                                  "equipment_type": "Tray", "owner_id": own_id,
                                  "status": "Active"}, timeout=15).json()["id"]
        for cid_before, url in [(seed_default, f"/api/drivers/{drv_id}"),
                                  (seed_default, f"/api/owners/{own_id}"),
                                  (seed_default, f"/api/vehicles/{veh_id}"),
                                  (seed_default, f"/api/equipment/{eq_id}")]:
            row = admin.get(f"{BASE_URL}{url}", timeout=15).json()
            assert row["company_id"] == cid_before, url

        # Create + set a new Default. Existing records must NOT be rewritten.
        new_default_id = _create_company(admin, f"MR08BP2 NewDef {_tag()}").json()["id"]
        _set_default(admin, new_default_id).raise_for_status()
        for url in (f"/api/drivers/{drv_id}", f"/api/owners/{own_id}",
                     f"/api/vehicles/{veh_id}", f"/api/equipment/{eq_id}"):
            row = admin.get(f"{BASE_URL}{url}", timeout=15).json()
            assert row["company_id"] == seed_default, \
                f"{url} was mutated to {row['company_id']} after default change"
        # Restore ACE as default
        _set_default(admin, seed_default).raise_for_status()


# ── (12-16) New records inherit Default; explicit choice honoured ──────
class TestNewRecordsInheritDefault:
    def test_new_driver_gets_default(self, admin):
        default = _get_default(admin)["company_id"]
        drv = admin.post(f"{BASE_URL}/api/drivers",
                         json={"full_name": f"MR08BP2 NewDrv {_tag()}",
                               "driver_status": "Training"}, timeout=15).json()
        assert drv["company_id"] == default
        assert drv.get("company_ref") == "ACE Car Freighters"

    def test_new_owner_gets_default(self, admin):
        default = _get_default(admin)["company_id"]
        r = admin.post(f"{BASE_URL}/api/owners",
                       json={"name": f"MR08BP2 O {_tag()}",
                             "primary_email": f"o{_tag()}@acedriverhub.com"},
                       timeout=15).json()
        assert r["company_id"] == default

    def test_new_vehicle_gets_default(self, admin):
        own = admin.post(f"{BASE_URL}/api/owners",
                         json={"name": f"MR08BP2 OV {_tag()}",
                               "primary_email": f"ov{_tag()}@acedriverhub.com"},
                         timeout=15).json()["id"]
        default = _get_default(admin)["company_id"]
        v = admin.post(f"{BASE_URL}/api/vehicles",
                       json={"registration_number": f"V-{_tag().upper()}",
                             "make": "T", "model": "M", "owner_id": own,
                             "vehicle_status": "Active"}, timeout=15).json()
        assert v["company_id"] == default

    def test_new_equipment_gets_default(self, admin):
        own = admin.post(f"{BASE_URL}/api/owners",
                         json={"name": f"MR08BP2 OE {_tag()}",
                               "primary_email": f"oe{_tag()}@acedriverhub.com"},
                         timeout=15).json()["id"]
        default = _get_default(admin)["company_id"]
        e = admin.post(f"{BASE_URL}/api/equipment",
                       json={"equipment_number": f"E-{_tag().upper()}",
                             "equipment_type": "Tray", "owner_id": own,
                             "status": "Active"}, timeout=15).json()
        assert e["company_id"] == default

    def test_explicit_company_wins_over_default(self, admin):
        other = _create_company(admin, f"MR08BP2 Explicit {_tag()}").json()["id"]
        drv = admin.post(f"{BASE_URL}/api/drivers",
                         json={"full_name": f"MR08BP2 Ex {_tag()}",
                               "driver_status": "Training",
                               "company_id": other},
                         timeout=15).json()
        assert drv["company_id"] == other


# ── (17, 18) Invalid + archived company_id rejected ─────────────────────
class TestCompanyValidation:
    def test_invalid_company_id_rejected(self, admin):
        r = admin.post(f"{BASE_URL}/api/drivers",
                        json={"full_name": f"MR08BP2 Bad {_tag()}",
                              "driver_status": "Training",
                              "company_id": "not-a-real-id"}, timeout=15)
        assert r.status_code == 400, r.text

    def test_archived_company_id_rejected_on_new(self, admin):
        cid = _create_company(admin, f"MR08BP2 Doomed {_tag()}").json()["id"]
        admin.delete(f"{BASE_URL}/api/companies/{cid}", timeout=15).raise_for_status()
        r = admin.post(f"{BASE_URL}/api/drivers",
                        json={"full_name": f"MR08BP2 Doom {_tag()}",
                              "driver_status": "Training",
                              "company_id": cid}, timeout=15)
        assert r.status_code == 409, r.text


# ── (19, 20) Legacy records + non-mutation on unrelated edit ────────────
class TestLegacyCompatibility:
    def test_legacy_record_readable_without_mutation(self, admin, db=None):
        # Insert directly via the API using company_id=None; DB-level legacy
        # rows can also be verified through GET (they never get default at
        # UPDATE time). Here we simulate legacy by supplying an explicit
        # None override after creation via a direct DB write.
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        import asyncio
        async def _seed_legacy():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            drv_id = f"legacy-{_tag()}"
            await db["drivers"].insert_one({
                "id": drv_id, "full_name": "Legacy Driver",
                "driver_status": "Active", "is_archived": False,
                "company_ref": "ACE Car Freighters",  # legacy
                # company_id intentionally missing
                "created_at": "2020-01-01T00:00:00Z",
            })
            return drv_id
        drv_id = asyncio.run(_seed_legacy())
        r = admin.get(f"{BASE_URL}/api/drivers/{drv_id}", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("company_ref") == "ACE Car Freighters"
        assert body.get("company_id") is None
        # Edit an unrelated field — company_id must NOT get default injected
        admin.put(f"{BASE_URL}/api/drivers/{drv_id}",
                  json={"mobile_number": "0400 000 000"}, timeout=15).raise_for_status()
        after = admin.get(f"{BASE_URL}/api/drivers/{drv_id}", timeout=15).json()
        assert after.get("company_id") is None, \
            "unrelated edit spuriously assigned Default Company"


# ── (24) DCC Company shortcut is exposed in the AdminUtilitiesCard util
#        list. Frontend integration is not exercised here; we only verify
#        the backend route responds.
class TestBackendRouteReady:
    def test_company_manager_route_ready(self, admin):
        assert admin.get(f"{BASE_URL}/api/companies", timeout=15).status_code == 200
        assert admin.get(f"{BASE_URL}/api/settings/default-company", timeout=15).status_code == 200
