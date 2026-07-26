"""EB-05 Documents & Evidence — backend tests."""
import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://fleet-ops-center-1.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@acedriverhub.com"
ADMIN_PASSWORD = "Admin@123"

TINY_PDF = b"%PDF-1.4\n%test\n%%EOF\n"
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x8bF\x1e\xea\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def readonly_headers(admin_headers):
    email = f"eb05ro_{uuid.uuid4().hex[:6]}@example.com"
    requests.post(f"{API}/auth/register", json={"email": email, "password": "T@1234", "full_name": "RO", "role": "ReadOnly"},
                  headers={**admin_headers, "Content-Type": "application/json"}, timeout=15)
    tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "T@1234"}, timeout=15).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def masters(admin_headers):
    drv = requests.get(f"{API}/drivers", headers=admin_headers, timeout=15).json()
    veh = requests.get(f"{API}/vehicles", headers=admin_headers, timeout=15).json()
    eq = requests.get(f"{API}/equipment", headers=admin_headers, timeout=15).json()
    return {"drivers": drv, "vehicles": veh, "equipment": eq}


def _upload(headers, file_bytes, filename, mime, title, doctype, entity_type=None, entity_id=None,
            relationship_type=None, is_primary=False, sensitivity=None):
    files = {"file": (filename, io.BytesIO(file_bytes), mime)}
    data = {"title": title, "document_type": doctype}
    if sensitivity: data["sensitivity"] = sensitivity
    if entity_type: data["entity_type"] = entity_type
    if entity_id: data["entity_id"] = entity_id
    if relationship_type: data["relationship_type"] = relationship_type
    if is_primary: data["is_primary"] = "true"
    return requests.post(f"{API}/documents/upload", headers=headers, files=files, data=data, timeout=30)


# ============================================================================
class TestUpload:
    def test_upload_valid_pdf(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "test.pdf", "application/pdf",
                    "T PDF", "Supporting Document", "Driver", drv["id"])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["document"]["file_size_bytes"] == len(TINY_PDF)
        assert j["document"]["checksum_sha256"]
        assert "storage_key" not in j["document"]  # never exposed

    def test_upload_valid_image(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PNG, "photo.png", "image/png",
                    "T Photo", "Profile Photo", "Driver", drv["id"])
        assert r.status_code == 200

    def test_reject_unsupported_extension(self, admin_headers):
        r = _upload(admin_headers, b"MZfoo", "malware.exe", "application/octet-stream", "bad", "Other")
        assert r.status_code == 400

    def test_reject_oversized(self, admin_headers):
        big = b"%PDF-1.4\n" + b"A" * (16 * 1024 * 1024)
        r = _upload(admin_headers, big, "big.pdf", "application/pdf", "big", "Supporting Document")
        assert r.status_code == 400

    def test_reject_zero_byte(self, admin_headers):
        r = _upload(admin_headers, b"", "empty.pdf", "application/pdf", "Empty", "Supporting Document")
        assert r.status_code == 400

    def test_reject_mismatched_mime(self, admin_headers):
        r = _upload(admin_headers, TINY_PDF, "trick.pdf", "image/jpeg", "trick", "Supporting Document")
        assert r.status_code == 400

    def test_reject_content_mismatch(self, admin_headers):
        # PNG bytes with .pdf extension — should fail signature sniff
        r = _upload(admin_headers, TINY_PNG, "fake.pdf", "application/pdf", "fake", "Supporting Document")
        assert r.status_code == 400

    def test_filename_sanitised(self, admin_headers):
        r = _upload(admin_headers, TINY_PDF, "../../etc/passwd.pdf", "application/pdf", "Path", "Supporting Document")
        assert r.status_code == 200
        assert "/" not in r.json()["document"]["display_filename"]
        assert ".." not in r.json()["document"]["display_filename"]

    def test_readonly_cannot_upload(self, readonly_headers):
        r = _upload(readonly_headers, TINY_PDF, "ro.pdf", "application/pdf", "ro", "Supporting Document")
        assert r.status_code == 403

    def test_no_orphan_on_failure(self, admin_headers):
        before = requests.get(f"{API}/documents", headers=admin_headers, timeout=15).json()
        _upload(admin_headers, b"", "empty.pdf", "application/pdf", "Zero", "Supporting Document")
        after = requests.get(f"{API}/documents", headers=admin_headers, timeout=15).json()
        assert len(after) == len(before)


# ============================================================================
class TestVersions:
    def test_new_version_supersedes(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "v1.pdf", "application/pdf", "VerTest", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        v1_id = r.json()["document"]["current_version_id"]
        # Upload new version — must use bytes that differ so checksum warning does not care
        new_bytes = TINY_PDF + b"v2"
        files = {"file": ("v2.pdf", io.BytesIO(new_bytes), "application/pdf")}
        r2 = requests.post(f"{API}/documents/{doc_id}/versions", headers=admin_headers, files=files,
                          data={"change_note": "v2"}, timeout=20)
        assert r2.status_code == 200
        v2 = r2.json()
        assert v2["version_number"] == 2
        assert v2["is_current"] is True
        # v1 must no longer be current
        vs = requests.get(f"{API}/documents/{doc_id}/versions", headers=admin_headers, timeout=15).json()
        v1_after = next(x for x in vs if x["id"] == v1_id)
        assert v1_after["is_current"] is False
        assert v1_after["status"] == "Superseded"

    def test_history_retained(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "h1.pdf", "application/pdf", "HistTest", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        for i in range(2, 4):
            files = {"file": (f"h{i}.pdf", io.BytesIO(TINY_PDF + str(i).encode()), "application/pdf")}
            requests.post(f"{API}/documents/{doc_id}/versions", headers=admin_headers, files=files, data={"change_note": f"v{i}"}, timeout=20)
        vs = requests.get(f"{API}/documents/{doc_id}/versions", headers=admin_headers, timeout=15).json()
        assert len(vs) >= 3

    def test_archive_and_restore(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "arch.pdf", "application/pdf", "ArchTest", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        assert requests.delete(f"{API}/documents/{doc_id}", headers=admin_headers, timeout=15).status_code == 200
        d = requests.get(f"{API}/documents/{doc_id}", headers=admin_headers, timeout=15).json()
        assert d["is_archived"] is True and d["status"] == "Archived"
        assert requests.post(f"{API}/documents/{doc_id}/restore", headers=admin_headers, timeout=15).status_code == 200
        d = requests.get(f"{API}/documents/{doc_id}", headers=admin_headers, timeout=15).json()
        assert d["is_archived"] is False


# ============================================================================
class TestLinks:
    def test_create_link_valid(self, admin_headers, masters):
        drv = masters["drivers"][1]
        r = _upload(admin_headers, TINY_PDF, "l.pdf", "application/pdf", "L", "Supporting Document")
        doc_id = r.json()["document"]["id"]
        lr = requests.post(f"{API}/document-links", headers={**admin_headers, "Content-Type": "application/json"},
                           json={"document_id": doc_id, "entity_type": "Driver", "entity_id": drv["id"],
                                 "relationship_type": "Supporting"}, timeout=15)
        assert lr.status_code == 200

    def test_invalid_entity_rejected(self, admin_headers):
        r = _upload(admin_headers, TINY_PDF, "l2.pdf", "application/pdf", "L2", "Supporting Document")
        doc_id = r.json()["document"]["id"]
        lr = requests.post(f"{API}/document-links", headers={**admin_headers, "Content-Type": "application/json"},
                           json={"document_id": doc_id, "entity_type": "Driver", "entity_id": "nope"}, timeout=15)
        assert lr.status_code == 400

    def test_primary_uniqueness(self, admin_headers, masters):
        veh = masters["vehicles"][0]
        r1 = _upload(admin_headers, TINY_PDF, "p1.pdf", "application/pdf", "P1", "Vehicle Registration",
                     "Vehicle", veh["id"], "Evidence", True)
        r2 = _upload(admin_headers, TINY_PDF, "p2.pdf", "application/pdf", "P2", "Vehicle Registration",
                     "Vehicle", veh["id"], "Evidence", True)
        assert r1.status_code == 200 and r2.status_code == 200
        links = requests.get(f"{API}/document-links",
                             params={"entity_type": "Vehicle", "entity_id": veh["id"], "relationship_type": "Evidence"},
                             headers=admin_headers, timeout=15).json()
        primaries = [x for x in links if x.get("is_primary") and not x.get("is_archived")]
        assert len(primaries) == 1

    def test_unlink_preserves_document(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "u.pdf", "application/pdf", "U", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        links = requests.get(f"{API}/document-links", params={"document_id": doc_id}, headers=admin_headers, timeout=15).json()
        lid = links[0]["id"]
        requests.delete(f"{API}/document-links/{lid}", headers=admin_headers, timeout=15)
        # Doc still exists
        d = requests.get(f"{API}/documents/{doc_id}", headers=admin_headers, timeout=15)
        assert d.status_code == 200


# ============================================================================
class TestEvidenceIntegration:
    def test_primary_evidence_wires_placeholder(self, admin_headers):
        licences = requests.get(f"{API}/driver-licences", headers=admin_headers, timeout=15).json()
        lic = licences[0]
        r = _upload(admin_headers, TINY_PDF, "lic.pdf", "application/pdf", "Lic Evidence",
                    "Driver Licence", "DriverLicence", lic["id"], "Evidence", True)
        assert r.status_code == 200
        doc_id = r.json()["document"]["id"]
        lic_after = requests.get(f"{API}/driver-licences/{lic['id']}", headers=admin_headers, timeout=15).json()
        assert lic_after.get("evidence_document_id") == doc_id


# ============================================================================
class TestDownloadPreview:
    def test_download_permitted(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "dl.pdf", "application/pdf", "DL", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        dl = requests.get(f"{API}/documents/{doc_id}/download", headers=admin_headers, timeout=15)
        assert dl.status_code == 200
        assert dl.content == TINY_PDF
        # Content-Disposition attachment
        assert "attachment" in dl.headers.get("content-disposition", "").lower()

    def test_readonly_cannot_download_restricted(self, admin_headers, readonly_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "rst.pdf", "application/pdf", "Rst", "Driver Contract",
                    "Driver", drv["id"], sensitivity="Restricted")
        doc_id = r.json()["document"]["id"]
        dl = requests.get(f"{API}/documents/{doc_id}/download", headers=readonly_headers, timeout=15)
        assert dl.status_code == 403

    def test_preview_pdf(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "pv.pdf", "application/pdf", "Pv", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        pv = requests.get(f"{API}/documents/{doc_id}/preview", headers=admin_headers, timeout=15)
        assert pv.status_code == 200
        assert "inline" in pv.headers.get("content-disposition", "").lower()

    def test_access_events_recorded(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "ae.pdf", "application/pdf", "AE", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        requests.get(f"{API}/documents/{doc_id}/download", headers=admin_headers, timeout=15)
        history = requests.get(f"{API}/documents/{doc_id}/access-history", headers=admin_headers, timeout=15).json()
        actions = {h["action"] for h in history}
        assert "Upload" in actions
        assert "Download" in actions


# ============================================================================
class TestSecurity:
    def test_unauthenticated_rejected(self):
        r = requests.get(f"{API}/documents", timeout=10)
        assert r.status_code in (401, 403)

    def test_storage_key_not_exposed_in_list(self, admin_headers):
        docs = requests.get(f"{API}/documents", headers=admin_headers, timeout=15).json()
        for d in docs:
            assert "storage_key" not in d

    def test_access_history_role_restricted(self, admin_headers, readonly_headers):
        docs = requests.get(f"{API}/documents", headers=admin_headers, timeout=15).json()
        did = docs[0]["id"]
        r = requests.get(f"{API}/documents/{did}/access-history", headers=readonly_headers, timeout=15)
        assert r.status_code == 403

    def test_archived_excluded_from_default_list(self, admin_headers, masters):
        drv = masters["drivers"][0]
        r = _upload(admin_headers, TINY_PDF, "excl.pdf", "application/pdf", "Excl", "Supporting Document", "Driver", drv["id"])
        doc_id = r.json()["document"]["id"]
        requests.delete(f"{API}/documents/{doc_id}", headers=admin_headers, timeout=15)
        listing = requests.get(f"{API}/documents", headers=admin_headers, timeout=15).json()
        assert doc_id not in [d["id"] for d in listing]
        listing2 = requests.get(f"{API}/documents", headers=admin_headers, params={"include_archived": "true"}, timeout=15).json()
        assert doc_id in [d["id"] for d in listing2]


# ============================================================================
class TestSeed:
    def test_seed_present(self, admin_headers):
        docs = requests.get(f"{API}/documents", headers=admin_headers, timeout=15).json()
        # 8 seed docs expected
        titles = {d["title"] for d in docs}
        assert "Driver Licence Evidence" in titles
        assert "Driver Contract" in titles
        assert "Driver Profile Photo" in titles

    def test_seed_idempotent_count(self, admin_headers):
        """Seed inserts should not duplicate on repeated startup calls."""
        docs = requests.get(f"{API}/documents", headers=admin_headers, params={"include_archived": "true"}, timeout=15).json()
        seeded = [d for d in docs if d.get("_source") == "seed-eb05"]
        assert 6 <= len(seeded) <= 8
