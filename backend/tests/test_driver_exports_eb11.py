"""EB-11 · Driver Start Sheet + Profile PDF export tests."""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests
from pypdf import PdfReader

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(admin_headers, role):
    email = f"eb11_{role.lower()}_{uuid.uuid4().hex[:6]}@acedriverhub.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB11 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"},
                   timeout=25)
    return _login(email, "T@1234")


@pytest.fixture(scope="session")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")

@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    return _register(admin_headers, "ReadOnly")

@pytest.fixture(scope="session")
def allocator_headers(admin_headers):
    return _register(admin_headers, "Allocator")

@pytest.fixture(scope="session")
def compliance_headers(admin_headers):
    return _register(admin_headers, "Compliance")

@pytest.fixture(scope="session")
def manager_headers(admin_headers):
    return _register(admin_headers, "Manager")


@pytest.fixture(scope="session")
def driver_id(admin_headers):
    rows = requests.get(f"{API}/drivers", headers=admin_headers, timeout=15).json()
    return rows[0]["id"]


def _gen_start_sheet(headers, driver_id):
    r = requests.post(f"{API}/drivers/{driver_id}/exports/start-sheet",
                       json={"confirm": True}, headers=headers, timeout=60)
    return r


def _gen_profile_pdf(headers, driver_id):
    r = requests.post(f"{API}/drivers/{driver_id}/exports/profile-pdf",
                       json={"confirm": True}, headers=headers, timeout=60)
    return r


def _download(version_id, headers):
    return requests.get(f"{API}/driver-export-versions/{version_id}/download",
                         headers=headers, timeout=25)


def _preview(version_id, headers):
    return requests.get(f"{API}/driver-export-versions/{version_id}/preview",
                         headers=headers, timeout=25)


def _pdf_pages(content: bytes) -> int:
    return len(PdfReader(io.BytesIO(content)).pages)


# ═══════════════════════════════════════════════════════════════════════════
# Generation - happy paths
# ═══════════════════════════════════════════════════════════════════════════
class TestStartSheetGeneration:

    def test_start_sheet_generates_valid_pdf(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id)
        assert r.status_code == 200, r.text
        data = r.json()
        v = data["version"]
        assert v["export_type"] == "Driver Start Sheet"
        assert v["page_count"] >= 1
        assert v["page_count"] <= 4
        assert v["file_size"] > 500
        assert len(v["sha256"]) == 64
        assert v["verification_reference"].startswith("ACE-")
        dl = _download(v["driver_export_version_id"], admin_headers)
        assert dl.status_code == 200
        assert dl.headers.get("content-type", "").startswith("application/pdf")
        assert dl.content[:4] == b"%PDF"
        assert _pdf_pages(dl.content) == v["page_count"]

    def test_start_sheet_title_present(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id)
        v = r.json()["version"]
        dl = _download(v["driver_export_version_id"], admin_headers)
        reader = PdfReader(io.BytesIO(dl.content))
        assert (reader.metadata.title or "").startswith("Driver Start Sheet")

    def test_readonly_cannot_generate(self, readonly_headers, driver_id):
        r = _gen_start_sheet(readonly_headers, driver_id)
        assert r.status_code == 403

    def test_allocator_can_generate_start_sheet(self, allocator_headers, driver_id):
        r = _gen_start_sheet(allocator_headers, driver_id)
        assert r.status_code == 200

    def test_missing_driver_returns_404(self, admin_headers):
        r = _gen_start_sheet(admin_headers, str(uuid.uuid4()))
        assert r.status_code == 404


class TestProfilePdfGeneration:

    def test_profile_pdf_generates_valid_pdf(self, admin_headers, driver_id):
        r = _gen_profile_pdf(admin_headers, driver_id)
        assert r.status_code == 200, r.text
        v = r.json()["version"]
        assert v["export_type"] == "Driver Profile PDF"
        assert v["page_count"] >= 4
        assert v["file_size"] > 1000
        dl = _download(v["driver_export_version_id"], admin_headers)
        assert dl.content[:4] == b"%PDF"

    def test_allocator_cannot_generate_profile(self, allocator_headers, driver_id):
        r = _gen_profile_pdf(allocator_headers, driver_id)
        assert r.status_code == 403

    def test_compliance_can_generate_profile(self, compliance_headers, driver_id):
        r = _gen_profile_pdf(compliance_headers, driver_id)
        assert r.status_code == 200

    def test_readonly_cannot_generate_profile(self, readonly_headers, driver_id):
        r = _gen_profile_pdf(readonly_headers, driver_id)
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Snapshot security & permission filtering
# ═══════════════════════════════════════════════════════════════════════════
class TestSnapshotSecurity:

    def test_admin_snapshot_contains_account_fields(self, admin_headers, driver_id):
        r = _gen_profile_pdf(admin_headers, driver_id)
        vid = r.json()["version"]["driver_export_version_id"]
        v = requests.get(f"{API}/driver-export-versions/{vid}",
                          headers=admin_headers, timeout=15).json()
        # Admin gets full snapshot
        assert "snapshot_payload" in v
        assert v["snapshot_payload"]["permissions"]["account_visible"] is True

    def test_compliance_snapshot_omits_accounts(self, compliance_headers, admin_headers,
                                                  driver_id):
        r = _gen_profile_pdf(compliance_headers, driver_id)
        vid = r.json()["version"]["driver_export_version_id"]
        v = requests.get(f"{API}/driver-export-versions/{vid}",
                          headers=admin_headers, timeout=15).json()
        payload = v["snapshot_payload"]
        assert payload["permissions"]["account_visible"] is False
        # business dict was skipped
        assert payload.get("business") in ({}, None)
        # Notes must not include Accounts category
        notes = payload.get("notes") or []
        assert all((n.get("category") or "General") != "Accounts" for n in notes)

    def test_allocator_start_sheet_omits_accounts(self, allocator_headers,
                                                    admin_headers, driver_id):
        r = _gen_start_sheet(allocator_headers, driver_id)
        vid = r.json()["version"]["driver_export_version_id"]
        v = requests.get(f"{API}/driver-export-versions/{vid}",
                          headers=admin_headers, timeout=15).json()
        assert v["snapshot_payload"]["permissions"]["account_visible"] is False
        assert v["snapshot_payload"]["business"] in ({}, None)

    def test_compliance_role_cannot_download_managers_export(
            self, admin_headers, compliance_headers, driver_id):
        """Historical exports generated with Manager/Admin role that expose
        account fields must still 403 when downloaded by Compliance."""
        r = _gen_profile_pdf(admin_headers, driver_id)
        vid = r.json()["version"]["driver_export_version_id"]
        dl = _download(vid, compliance_headers)
        assert dl.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Versioning & history
# ═══════════════════════════════════════════════════════════════════════════
class TestVersioning:

    def test_regenerate_creates_new_version(self, admin_headers, driver_id):
        r1 = _gen_start_sheet(admin_headers, driver_id).json()
        vnum1 = r1["version"]["version_number"]
        r2 = requests.post(
            f"{API}/driver-exports/{r1['job']['driver_export_job_id']}/regenerate",
            headers=admin_headers, timeout=60).json()
        assert r2["version"]["version_number"] == vnum1 + 1 or \
               r2["version"]["version_number"] > vnum1

    def test_history_lists_multiple_versions(self, admin_headers, driver_id):
        _gen_start_sheet(admin_headers, driver_id)
        _gen_start_sheet(admin_headers, driver_id)
        history = requests.get(f"{API}/drivers/{driver_id}/exports",
                                 headers=admin_headers, timeout=15).json()
        assert len(history) >= 2
        for entry in history:
            assert entry["job"]["status"] in ("Completed", "Failed", "Archived")

    def test_archive_version(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        a = requests.post(f"{API}/driver-export-versions/{vid}/archive",
                            headers=admin_headers, timeout=15)
        assert a.status_code == 200
        assert a.json()["is_archived"] is True

    def test_allocator_cannot_archive(self, allocator_headers, admin_headers,
                                        driver_id):
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        a = requests.post(f"{API}/driver-export-versions/{vid}/archive",
                            headers=allocator_headers, timeout=15)
        assert a.status_code == 403

    def test_version_immutable(self, admin_headers, driver_id):
        """Reading the same version twice returns identical checksum."""
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        v1 = requests.get(f"{API}/driver-export-versions/{vid}",
                            headers=admin_headers, timeout=15).json()
        v2 = requests.get(f"{API}/driver-export-versions/{vid}",
                            headers=admin_headers, timeout=15).json()
        assert v1["sha256"] == v2["sha256"]


# ═══════════════════════════════════════════════════════════════════════════
# File access + audit
# ═══════════════════════════════════════════════════════════════════════════
class TestAccessAudit:

    def test_no_storage_path_in_api_response(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id).json()
        text = str(r)
        assert "document_storage" not in text
        assert "storage_key" not in text
        assert "storage_provider" not in text

    def test_preview_returns_pdf(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        p = _preview(vid, admin_headers)
        assert p.status_code == 200
        assert p.content[:4] == b"%PDF"
        assert "inline" in p.headers.get("content-disposition", "")

    def test_download_returns_attachment(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        d = _download(vid, admin_headers)
        assert d.status_code == 200
        assert "attachment" in d.headers.get("content-disposition", "")


# ═══════════════════════════════════════════════════════════════════════════
# Verification reference
# ═══════════════════════════════════════════════════════════════════════════
class TestVerification:

    def test_valid_reference_returns_summary(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vref = r["verification_reference"]
        v = requests.get(f"{API}/driver-exports/verify/{vref}",
                          headers=admin_headers, timeout=15)
        assert v.status_code == 200
        data = v.json()
        assert data["verification_reference"] == vref
        assert data["checksum_ok"] is True
        assert data["can_open"] is True

    def test_invalid_reference_404(self, admin_headers):
        v = requests.get(f"{API}/driver-exports/verify/ACE-BAD1-BAD2-BAD3",
                          headers=admin_headers, timeout=15)
        assert v.status_code == 404

    def test_unauthenticated_verify_denied(self):
        v = requests.get(f"{API}/driver-exports/verify/ACE-BAD1-BAD2-BAD3", timeout=15)
        assert v.status_code == 401

    def test_verify_role_filter_hides_manager_export(self, admin_headers,
                                                      compliance_headers, driver_id):
        r = _gen_profile_pdf(admin_headers, driver_id).json()
        vref = r["verification_reference"]
        v = requests.get(f"{API}/driver-exports/verify/{vref}",
                          headers=compliance_headers, timeout=15).json()
        # can_open must be False because compliance cannot access account fields
        assert v["can_open"] is False
        assert v["driver_export_version_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# PDF validation
# ═══════════════════════════════════════════════════════════════════════════
class TestPdfValidation:

    def test_pdf_signature_and_pages(self, admin_headers, driver_id):
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        d = _download(vid, admin_headers)
        assert d.content.startswith(b"%PDF")
        reader = PdfReader(io.BytesIO(d.content))
        assert len(reader.pages) >= 1
        # Extract text from page 1 — must include "Driver Start Sheet" title
        text0 = reader.pages[0].extract_text() or ""
        assert "Driver Start Sheet" in text0

    def test_profile_pdf_pages_and_title(self, admin_headers, driver_id):
        r = _gen_profile_pdf(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        d = _download(vid, admin_headers)
        reader = PdfReader(io.BytesIO(d.content))
        assert len(reader.pages) >= 4
        # Extract text from any page — must include "Driver Command Centre Profile"
        joined = " ".join((p.extract_text() or "") for p in reader.pages)
        assert "Driver Command Centre Profile" in joined

    def test_checksum_matches_downloaded_bytes(self, admin_headers, driver_id):
        import hashlib
        r = _gen_start_sheet(admin_headers, driver_id).json()
        vid = r["version"]["driver_export_version_id"]
        d = _download(vid, admin_headers)
        expected = r["version"]["sha256"]
        assert hashlib.sha256(d.content).hexdigest() == expected
