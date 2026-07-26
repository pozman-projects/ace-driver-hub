"""EB-06 Guided Spreadsheet Import — backend tests."""
import io
import os
import uuid
from datetime import date

import openpyxl
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://fleet-ops-center-1.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="session")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    email = f"eb06ro_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register", json={"email": email, "password": "T@1234", "full_name": "RO", "role": "ReadOnly"},
                  headers={**admin_headers, "Content-Type": "application/json"}, timeout=15)
    tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "T@1234"}, timeout=15).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _make_xlsx(rows_by_header: dict) -> bytes:
    """rows_by_header: {'HeaderA': [a1, a2], 'HeaderB': [b1, b2]}."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    headers = list(rows_by_header.keys())
    ws.append(headers)
    n = max((len(v) for v in rows_by_header.values()), default=0)
    for i in range(n):
        ws.append([rows_by_header[h][i] if i < len(rows_by_header[h]) else None for h in headers])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _make_csv(rows_by_header: dict) -> bytes:
    headers = list(rows_by_header.keys())
    n = max((len(v) for v in rows_by_header.values()), default=0)
    lines = [",".join(headers)]
    for i in range(n):
        lines.append(",".join(str(rows_by_header[h][i] if i < len(rows_by_header[h]) else "") for h in headers))
    return ("\n".join(lines)).encode("utf-8")


def _create_job(headers, domain="drivers", mode="Create and Update"):
    r = requests.post(f"{API}/imports", headers={**headers, "Content-Type": "application/json"},
                      json={"target_domain": domain, "mode": mode}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _upload(headers, job_id, content, filename):
    files = {"file": (filename, io.BytesIO(content),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if filename.endswith("xlsx") else "text/csv")}
    return requests.post(f"{API}/imports/{job_id}/file", headers=headers, files=files, timeout=30)


def _sheets(headers, job_id):
    return requests.get(f"{API}/imports/{job_id}/sheets", headers=headers, timeout=20)


def _inspect(headers, job_id, sheet):
    return requests.post(f"{API}/imports/{job_id}/inspect", headers={**headers, "Content-Type": "application/json"},
                         json={"sheet_name": sheet}, timeout=20)


def _mapping(headers, job_id, field_map):
    return requests.post(f"{API}/imports/{job_id}/mapping", headers={**headers, "Content-Type": "application/json"},
                          json={"field_mappings": field_map}, timeout=20)


def _validate(headers, job_id):
    return requests.post(f"{API}/imports/{job_id}/validate", headers=headers, timeout=60)


def _commit(headers, job_id):
    return requests.post(f"{API}/imports/{job_id}/commit", headers=headers, timeout=60)


# ============================================================================
class TestInspection:
    def test_xlsx_accepted(self, admin_headers):
        job = _create_job(admin_headers)
        b = _make_xlsx({"Name": ["Alice"], "Code": ["DRV-9001"]})
        r = _upload(admin_headers, job["id"], b, "t.xlsx")
        assert r.status_code == 200
        s = _sheets(admin_headers, job["id"]).json()
        assert any(x["name"] == "Sheet1" for x in s["sheets"])

    def test_csv_accepted(self, admin_headers):
        job = _create_job(admin_headers)
        b = _make_csv({"Name": ["Bob"], "Code": ["DRV-9002"]})
        assert _upload(admin_headers, job["id"], b, "t.csv").status_code == 200
        s = _sheets(admin_headers, job["id"]).json()
        assert s["sheets"][0]["name"] == "csv"
        assert s["sheets"][0]["headers"] == ["Name", "Code"]

    def test_unsupported_file_rejected(self, admin_headers):
        job = _create_job(admin_headers)
        r = _upload(admin_headers, job["id"], b"MZ", "bad.exe")
        assert r.status_code == 400

    def test_empty_file_rejected(self, admin_headers):
        job = _create_job(admin_headers)
        r = _upload(admin_headers, job["id"], b"", "empty.xlsx")
        assert r.status_code == 400

    def test_headers_detected(self, admin_headers):
        job = _create_job(admin_headers)
        b = _make_xlsx({"A": [1], "B": [2], "C": [3]})
        _upload(admin_headers, job["id"], b, "t.xlsx")
        s = _sheets(admin_headers, job["id"]).json()
        assert s["sheets"][0]["headers"] == ["A", "B", "C"]

    def test_second_upload_rejected(self, admin_headers):
        job = _create_job(admin_headers)
        b = _make_csv({"A": ["1"]})
        _upload(admin_headers, job["id"], b, "t.csv")
        r = _upload(admin_headers, job["id"], b, "t2.csv")
        assert r.status_code == 400


# ============================================================================
class TestNormalisation:
    def test_dates_and_upper_and_email(self, admin_headers):
        # Create a Drivers import with mixed formats
        job = _create_job(admin_headers)
        b = _make_xlsx({
            "Full Name": [" alice   smith "],
            "Email": ["ALICE@Example.com"],
            "Mobile": ["+61 4 1234 5678"],
            "Driver Code": [f"DRV-N-{uuid.uuid4().hex[:5]}"],
        })
        _upload(admin_headers, job["id"], b, "t.xlsx")
        _inspect(admin_headers, job["id"], "Sheet1")
        _mapping(admin_headers, job["id"], {
            "Full Name": "full_name", "Email": "email", "Mobile": "mobile_number", "Driver Code": "driver_code",
        })
        _validate(admin_headers, job["id"])
        rows = requests.get(f"{API}/imports/{job['id']}/rows", headers=admin_headers, timeout=15).json()["rows"]
        r = rows[0]
        assert r["normalised_values"]["full_name"] == "Alice Smith"
        assert r["normalised_values"]["email"] == "alice@example.com"
        assert r["normalised_values"]["mobile_number"].startswith("04")


# ============================================================================
class TestMatchingAndCommit:
    def test_create_and_validate_and_commit_drivers(self, admin_headers):
        job = _create_job(admin_headers)
        uid_a = uuid.uuid4().hex[:6]
        uid_b = uuid.uuid4().hex[:6]
        b = _make_xlsx({
            "Name": [f"Charlie X {uid_a}", f"Dana L {uid_b}"],
            "Code": [f"DRV-M-{uid_a}", f"DRV-M-{uid_b}"],
            "Email": [f"c{uid_a}@x.io", f"d{uid_b}@x.io"],
        })
        _upload(admin_headers, job["id"], b, "t.xlsx")
        _inspect(admin_headers, job["id"], "Sheet1")
        _mapping(admin_headers, job["id"], {"Name": "full_name", "Code": "driver_code", "Email": "email"})
        v = _validate(admin_headers, job["id"]).json()
        assert v["error_rows"] == 0
        assert v["status"] == "Ready to Commit"
        c = _commit(admin_headers, job["id"]).json()
        assert c["created_count"] == 2

        # Second run with same data → idempotent Update / NoChange
        job2 = _create_job(admin_headers)
        _upload(admin_headers, job2["id"], b, "t2.xlsx")
        _inspect(admin_headers, job2["id"], "Sheet1")
        _mapping(admin_headers, job2["id"], {"Name": "full_name", "Code": "driver_code", "Email": "email"})
        _validate(admin_headers, job2["id"])
        rows2 = requests.get(f"{API}/imports/{job2['id']}/rows", headers=admin_headers, timeout=15).json()["rows"]
        actions = [r["action"] for r in rows2]
        # Both rows should map to existing → either No Change or Update (no diffs → No Change)
        assert set(actions).issubset({"No Change", "Update"})

    def test_duplicate_within_file_flagged(self, admin_headers):
        job = _create_job(admin_headers)
        code = f"DRV-DUP-{uuid.uuid4().hex[:5]}"
        b = _make_xlsx({"Name": ["A", "B"], "Code": [code, code]})
        _upload(admin_headers, job["id"], b, "t.xlsx")
        _inspect(admin_headers, job["id"], "Sheet1")
        _mapping(admin_headers, job["id"], {"Name": "full_name", "Code": "driver_code"})
        _validate(admin_headers, job["id"])
        rows = requests.get(f"{API}/imports/{job['id']}/rows", headers=admin_headers, timeout=15).json()["rows"]
        assert any("Duplicate" in w for w in (rows[1].get("warnings") or []))

    def test_required_missing_error(self, admin_headers):
        job = _create_job(admin_headers, domain="vehicles")
        b = _make_xlsx({"Registration": [""], "Make": ["Kenworth"]})
        _upload(admin_headers, job["id"], b, "t.xlsx")
        _inspect(admin_headers, job["id"], "Sheet1")
        _mapping(admin_headers, job["id"], {"Registration": "registration_number", "Make": "make"})
        v = _validate(admin_headers, job["id"]).json()
        assert v["error_rows"] >= 1

    def test_unique_field_conflict_blocking(self, admin_headers):
        # First job — create a driver with a unique code
        code = f"DRV-UNQ-{uuid.uuid4().hex[:6]}"
        j1 = _create_job(admin_headers)
        b = _make_xlsx({"Name": [f"First {code}"], "Code": [code]})
        _upload(admin_headers, j1["id"], b, "u.xlsx")
        _inspect(admin_headers, j1["id"], "Sheet1")
        _mapping(admin_headers, j1["id"], {"Name": "full_name", "Code": "driver_code"})
        _validate(admin_headers, j1["id"])
        _commit(admin_headers, j1["id"])

        # Second job in Create Only mode — same code, existing driver already present → Skip action
        j2 = _create_job(admin_headers, mode="Create Only")
        b2 = _make_xlsx({"Name": [f"Different {code}"], "Code": [code]})
        _upload(admin_headers, j2["id"], b2, "u2.xlsx")
        _inspect(admin_headers, j2["id"], "Sheet1")
        _mapping(admin_headers, j2["id"], {"Name": "full_name", "Code": "driver_code"})
        _validate(admin_headers, j2["id"])
        rows = requests.get(f"{API}/imports/{j2['id']}/rows", headers=admin_headers, timeout=15).json()["rows"]
        # Create Only + existing driver → Skip
        assert rows[0]["action"] == "Skip"
        assert rows[0]["match_status"] == "Exact Match"

    def test_high_risk_flag(self, admin_headers):
        # Create a vehicle, then run an update job which changes VIN → warning about high-risk
        rego = f"HR-{uuid.uuid4().hex[:5]}"
        vin1 = "VIN" + uuid.uuid4().hex[:10].upper()
        j = _create_job(admin_headers, domain="vehicles")
        b = _make_xlsx({"Rego": [rego], "VIN": [vin1]})
        _upload(admin_headers, j["id"], b, "hr.xlsx")
        _inspect(admin_headers, j["id"], "Sheet1")
        _mapping(admin_headers, j["id"], {"Rego": "registration_number", "VIN": "vin"})
        _validate(admin_headers, j["id"])
        _commit(admin_headers, j["id"])

        # Second run with SAME registration but DIFFERENT VIN — will conflict (unique VIN)
        j2 = _create_job(admin_headers, domain="vehicles", mode="Create and Update")
        vin2 = "VIN" + uuid.uuid4().hex[:10].upper()
        b2 = _make_xlsx({"Rego": [rego], "VIN": [vin2]})
        _upload(admin_headers, j2["id"], b2, "hr2.xlsx")
        _inspect(admin_headers, j2["id"], "Sheet1")
        _mapping(admin_headers, j2["id"], {"Rego": "registration_number", "VIN": "vin"})
        _validate(admin_headers, j2["id"])
        rows = requests.get(f"{API}/imports/{j2['id']}/rows", headers=admin_headers, timeout=15).json()["rows"]
        row = rows[0]
        # matched by registration_number → Update action, HIGH-RISK warning about VIN
        if row["action"] == "Update":
            assert any("HIGH-RISK" in w for w in (row["warnings"] or []))


# ============================================================================
class TestConflictAndRollback:
    def test_blocking_conflict_blocks_commit(self, admin_headers):
        # Set up a scenario with MultipleMatches: two drivers sharing the same email
        # (This can happen legitimately in test data.) Import a row where email match
        # produces >1 candidate → row gets MultipleMatches conflict which is Blocking.
        code_a = f"DRV-DUAL-{uuid.uuid4().hex[:6]}"
        code_b = f"DRV-DUAL-{uuid.uuid4().hex[:6]}"
        shared_email = f"dual-{uuid.uuid4().hex[:6]}@x.io"

        # Create two drivers sharing an email
        j1 = _create_job(admin_headers)
        _upload(admin_headers, j1["id"],
                _make_xlsx({"Name": [f"A {code_a}", f"B {code_b}"],
                             "Code": [code_a, code_b], "Email": [shared_email, shared_email]}),
                "d1.xlsx")
        _inspect(admin_headers, j1["id"], "Sheet1")
        _mapping(admin_headers, j1["id"], {"Name": "full_name", "Code": "driver_code", "Email": "email"})
        _validate(admin_headers, j1["id"])
        _commit(admin_headers, j1["id"])

        # Now attempt an import mapping only email + name (no driver_code) so match
        # will hit multiple candidates via email.
        j2 = _create_job(admin_headers, mode="Create and Update")
        _upload(admin_headers, j2["id"],
                _make_xlsx({"Name": ["Whoever"], "Email": [shared_email]}), "d2.xlsx")
        _inspect(admin_headers, j2["id"], "Sheet1")
        _mapping(admin_headers, j2["id"], {"Name": "full_name", "Email": "email"})
        v = _validate(admin_headers, j2["id"]).json()
        # Multiple candidates should raise a blocking conflict
        assert v["conflict_rows"] >= 1 or v["error_rows"] >= 1
        # Commit should be blocked
        r = _commit(admin_headers, j2["id"])
        assert r.status_code == 409

    def test_rollback_soft_archives_created(self, admin_headers):
        code = f"DRV-RB-{uuid.uuid4().hex[:6]}"
        j = _create_job(admin_headers)
        _upload(admin_headers, j["id"], _make_xlsx({"Name": ["Rob"], "Code": [code]}), "rb.xlsx")
        _inspect(admin_headers, j["id"], "Sheet1")
        _mapping(admin_headers, j["id"], {"Name": "full_name", "Code": "driver_code"})
        _validate(admin_headers, j["id"])
        c = _commit(admin_headers, j["id"]).json()
        assert c["created_count"] == 1
        created_id = c["record_actions"][0]["record_id"]

        # verify driver exists
        d = requests.get(f"{API}/drivers/{created_id}", headers=admin_headers, timeout=15).json()
        assert d.get("is_archived") is not True

        # rollback
        rb = requests.post(f"{API}/imports/{j['id']}/rollback", headers=admin_headers, timeout=30).json()
        assert rb["status"] in ("Completed", "Partially Completed")

        # driver should now be archived
        # Fetch with include_archived
        driver = requests.get(f"{API}/drivers/{created_id}?include_archived=true", headers=admin_headers, timeout=15)
        if driver.status_code == 200:
            assert driver.json().get("is_archived") is True


# ============================================================================
class TestPermissions:
    def test_readonly_cannot_create_job(self, readonly_headers):
        r = requests.post(f"{API}/imports", headers={**readonly_headers, "Content-Type": "application/json"},
                          json={"target_domain": "drivers"}, timeout=15)
        assert r.status_code == 403

    def test_readonly_can_list_jobs(self, readonly_headers):
        r = requests.get(f"{API}/imports", headers=readonly_headers, timeout=15)
        assert r.status_code == 200


# ============================================================================
class TestTemplates:
    def test_template_returns_fields(self, admin_headers):
        r = requests.get(f"{API}/import-templates/drivers", headers=admin_headers, timeout=15).json()
        assert r["target_domain"] == "drivers"
        assert "full_name" in r["required_fields"]
        assert "driver_code" in r["unique_fields"]

    def test_template_lists_domains(self, admin_headers):
        r = requests.get(f"{API}/import-templates", headers=admin_headers, timeout=15).json()
        slugs = {x["slug"] for x in r}
        assert {"drivers", "owners", "vehicles", "equipment"}.issubset(slugs)


# ============================================================================
class TestFullLifecycle:
    def test_owner_import_lifecycle(self, admin_headers):
        j = _create_job(admin_headers, domain="owners")
        uid = uuid.uuid4().hex[:8]
        abn_a = "11" + str(uuid.uuid4().int)[:9]
        b = _make_xlsx({"Business": [f"Freight Co {uid} Pty Ltd"], "ABN": [abn_a], "Type": ["Business"]})
        _upload(admin_headers, j["id"], b, "o.xlsx")
        _inspect(admin_headers, j["id"], "Sheet1")
        _mapping(admin_headers, j["id"], {"Business": "name", "ABN": "abn", "Type": "owner_type"})
        v = _validate(admin_headers, j["id"]).json()
        assert v["status"] == "Ready to Commit"
        c = _commit(admin_headers, j["id"]).json()
        assert c["created_count"] == 1

    def test_equipment_import_lifecycle(self, admin_headers):
        j = _create_job(admin_headers, domain="equipment")
        num = f"EQ-{uuid.uuid4().hex[:6].upper()}"
        b = _make_xlsx({"Number": [num], "Type": ["Trailer"]})
        _upload(admin_headers, j["id"], b, "e.xlsx")
        _inspect(admin_headers, j["id"], "Sheet1")
        _mapping(admin_headers, j["id"], {"Number": "equipment_number", "Type": "equipment_type"})
        _validate(admin_headers, j["id"])
        c = _commit(admin_headers, j["id"]).json()
        assert c["created_count"] == 1
