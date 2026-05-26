"""ACE Driver Hub - Backend API tests.

Covers:
- Service health
- Auth (login, /me, register, role enforcement)
- Stats overview (all 8 slugs)
- Generic module CRUD for all slugs + unknown slug 404
- Role-based access (ReadOnly cannot create; only Admin/Manager can delete)
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://fleet-ops-center-1.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"

SLUGS = ["drivers", "licences", "truck-rego", "insurance", "equipment", "maintenance", "tilt-trays", "onboarding"]


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data and data["user"]["role"] == "Admin"
    return data["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def _create_user(admin_headers, role):
    email = f"TEST_{role.lower()}_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "Test@1234"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": pwd, "full_name": f"TEST {role}", "role": role},
        headers=admin_headers,
        timeout=20,
    )
    assert r.status_code == 200, f"register {role} failed: {r.status_code} {r.text}"
    # login as that user
    r2 = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r2.status_code == 200, f"login {role} failed: {r2.status_code} {r2.text}"
    return {"Authorization": f"Bearer {r2.json()['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    return _create_user(admin_headers, "ReadOnly")


@pytest.fixture(scope="session")
def manager_headers(admin_headers):
    return _create_user(admin_headers, "Manager")


@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    return _create_user(admin_headers, "Allocator")


# ---------- Health ----------
class TestHealth:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "ACE" in data.get("service", "")


# ---------- Auth ----------
class TestAuth:
    def test_login_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["token_type"] == "bearer"
        assert isinstance(d["access_token"], str) and len(d["access_token"]) > 20
        assert d["user"]["email"] == ADMIN_EMAIL
        assert d["user"]["role"] == "Admin"
        assert "id" in d["user"]

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "WRONG"}, timeout=15)
        assert r.status_code == 401

    def test_login_unknown_email(self):
        r = requests.post(f"{API}/auth/login", json={"email": "nobody@nowhere.com", "password": "x"}, timeout=15)
        assert r.status_code == 401

    def test_me_with_token(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_without_token(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_invalid_token(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer notavalidjwt"}, timeout=15)
        assert r.status_code == 401

    def test_register_requires_admin(self, readonly_headers):
        r = requests.post(
            f"{API}/auth/register",
            json={"email": f"TEST_x_{uuid.uuid4().hex[:6]}@ex.com", "password": "Pw@12345", "full_name": "x", "role": "ReadOnly"},
            headers=readonly_headers,
            timeout=15,
        )
        assert r.status_code == 403

    def test_register_without_token(self):
        r = requests.post(
            f"{API}/auth/register",
            json={"email": f"TEST_x_{uuid.uuid4().hex[:6]}@ex.com", "password": "Pw@12345", "full_name": "x", "role": "ReadOnly"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_register_invalid_role(self, admin_headers):
        r = requests.post(
            f"{API}/auth/register",
            json={"email": f"TEST_x_{uuid.uuid4().hex[:6]}@ex.com", "password": "Pw@12345", "full_name": "x", "role": "SuperGod"},
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 400


# ---------- Stats ----------
class TestStats:
    def test_stats_overview(self, admin_headers):
        r = requests.get(f"{API}/stats/overview", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        for slug in SLUGS:
            assert slug in data, f"missing {slug} in stats"
            assert isinstance(data[slug], int)
            assert data[slug] >= 0

    def test_stats_overview_unauth(self):
        r = requests.get(f"{API}/stats/overview", timeout=15)
        assert r.status_code == 401


# ---------- Module CRUD ----------
SAMPLE_PAYLOADS = {
    "drivers": {"name": "TEST_Driver", "phone": "0400", "status": "Active"},
    "licences": {"driver_name": "TEST_Driver", "licence_number": "TEST-1", "licence_class": "HR"},
    "truck-rego": {"rego_number": "TEST-RGO", "make": "Test", "model": "M"},
    "insurance": {"policy_number": "TEST-POL", "provider": "TestCo"},
    "equipment": {"equipment_id": "TEST-EQ", "name": "TestKit"},
    "maintenance": {"vehicle_rego": "TEST-RGO", "service_type": "Test"},
    "tilt-trays": {"tray_id": "TEST-TT", "rego": "TLT-TEST"},
    "onboarding": {"full_name": "TEST_Onboard", "stage": "Test"},
}


class TestModuleCRUD:
    @pytest.mark.parametrize("slug", SLUGS)
    def test_list_seeded(self, admin_headers, slug):
        r = requests.get(f"{API}/modules/{slug}", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # Seed adds rows on startup; allow >=0 but warn if 0
        for it in items:
            assert "_id" not in it, "Mongo _id leaked"
            assert "id" in it

    @pytest.mark.parametrize("slug", SLUGS)
    def test_create_get_delete(self, admin_headers, slug):
        payload = dict(SAMPLE_PAYLOADS[slug])
        r = requests.post(f"{API}/modules/{slug}", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"create {slug} failed: {r.text}"
        created = r.json()
        assert "id" in created and "created_at" in created
        for k, v in payload.items():
            assert created[k] == v
        item_id = created["id"]

        # GET single
        rg = requests.get(f"{API}/modules/{slug}/{item_id}", headers=admin_headers, timeout=15)
        assert rg.status_code == 200
        assert rg.json()["id"] == item_id

        # DELETE
        rd = requests.delete(f"{API}/modules/{slug}/{item_id}", headers=admin_headers, timeout=15)
        assert rd.status_code == 200
        # Verify gone
        rg2 = requests.get(f"{API}/modules/{slug}/{item_id}", headers=admin_headers, timeout=15)
        assert rg2.status_code == 404

    def test_unknown_slug(self, admin_headers):
        r = requests.get(f"{API}/modules/not-a-real-slug", headers=admin_headers, timeout=15)
        assert r.status_code == 404
        r2 = requests.post(f"{API}/modules/not-a-real-slug", json={"x": 1}, headers=admin_headers, timeout=15)
        assert r2.status_code == 404

    def test_list_unauth(self):
        r = requests.get(f"{API}/modules/drivers", timeout=15)
        assert r.status_code == 401


# ---------- Role enforcement ----------
class TestRoles:
    def test_readonly_cannot_create(self, readonly_headers):
        r = requests.post(f"{API}/modules/drivers", json={"name": "TEST_RO_x"}, headers=readonly_headers, timeout=15)
        assert r.status_code == 403

    def test_readonly_can_list(self, readonly_headers):
        r = requests.get(f"{API}/modules/drivers", headers=readonly_headers, timeout=15)
        assert r.status_code == 200

    def test_allocator_can_create_but_not_delete(self, allocator_headers, admin_headers):
        r = requests.post(f"{API}/modules/drivers", json={"name": "TEST_Alloc"}, headers=allocator_headers, timeout=15)
        assert r.status_code == 200
        item_id = r.json()["id"]

        rd = requests.delete(f"{API}/modules/drivers/{item_id}", headers=allocator_headers, timeout=15)
        assert rd.status_code == 403
        # cleanup as admin
        requests.delete(f"{API}/modules/drivers/{item_id}", headers=admin_headers, timeout=15)

    def test_manager_can_delete(self, manager_headers, admin_headers):
        # create via admin
        r = requests.post(f"{API}/modules/drivers", json={"name": "TEST_Mgr_target"}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        item_id = r.json()["id"]
        rd = requests.delete(f"{API}/modules/drivers/{item_id}", headers=manager_headers, timeout=15)
        assert rd.status_code == 200
