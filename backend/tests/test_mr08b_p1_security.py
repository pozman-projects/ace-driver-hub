"""MR-08B-P1 · Reporting Foundation Security + Import Role Alignment.

Part A — Import Commit role drift: verify Admin/Manager only.
Part B — Driver Profile PDF must never leak MR-07A sensitive account
        fields to Compliance / Allocator / ReadOnly callers.
"""
from __future__ import annotations

import io
import os
import re
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@acedriverhub.com", "password": "Admin@123"}


# ── fixtures ────────────────────────────────────────────────────────────
def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _register(admin, role):
    tag = _tag()
    email = f"mr08b-{role.lower()}-{tag}@acedriverhub.com"
    admin.post(f"{BASE_URL}/api/auth/register",
                json={"email": email, "password": "P@ssword1",
                      "full_name": f"MR08B {role} {tag}", "role": role},
                timeout=15).raise_for_status()
    return _login(email, "P@ssword1")


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN["email"], ADMIN["password"])


@pytest.fixture(scope="module")
def manager(admin):    return _register(admin, "Manager")

@pytest.fixture(scope="module")
def compliance(admin): return _register(admin, "Compliance")

@pytest.fixture(scope="module")
def allocator(admin):  return _register(admin, "Allocator")

@pytest.fixture(scope="module")
def readonly(admin):   return _register(admin, "ReadOnly")


# ────────────────────────────────────────────────────────────────────────
# PART A · Import Commit role drift
# ────────────────────────────────────────────────────────────────────────
class TestImportCommitAuthority:
    """MR-07B locked Import Commit to Admin/Manager. Validation stays wider."""

    def _bogus_commit(self, session):
        # We only assert the role gate. Any downstream 404/400 is fine —
        # only 403 signals the role-gate rejected the caller.
        return session.post(f"{BASE_URL}/api/imports/does-not-exist/commit",
                             json={}, timeout=15)

    def test_admin_passes_commit_role_gate(self, admin):
        r = self._bogus_commit(admin)
        assert r.status_code != 403, r.text

    def test_manager_passes_commit_role_gate(self, manager):
        r = self._bogus_commit(manager)
        assert r.status_code != 403, r.text

    def test_compliance_denied_commit(self, compliance):
        r = self._bogus_commit(compliance)
        assert r.status_code == 403, \
            f"MR-07B: Compliance must not commit imports (got {r.status_code}): {r.text[:200]}"

    def test_allocator_denied_commit(self, allocator):
        assert self._bogus_commit(allocator).status_code == 403

    def test_readonly_denied_commit(self, readonly):
        assert self._bogus_commit(readonly).status_code == 403

    # Validation / prep must remain wide for Admin/Manager/Compliance/Allocator.
    def test_compliance_can_still_validate(self, compliance):
        r = compliance.post(f"{BASE_URL}/api/imports/does-not-exist/validate",
                            json={}, timeout=15)
        assert r.status_code != 403, r.text

    def test_allocator_can_still_validate(self, allocator):
        r = allocator.post(f"{BASE_URL}/api/imports/does-not-exist/validate",
                            json={}, timeout=15)
        assert r.status_code != 403, r.text


# ────────────────────────────────────────────────────────────────────────
# PART B · Driver Profile PDF · MR-07A sensitive-field protection
# ────────────────────────────────────────────────────────────────────────
SECRETS = {
    "business_name":       "MR07A_SECRET_BUSINESS",
    "abn":                 "99 999 999 999",
    "payroll_number":      "SECRET-PAYROLL-987",
    "payment_percentage":  88.88,
}


@pytest.fixture(scope="module")
def secret_driver(admin):
    """Create a driver stamped with MR-07A sensitive markers."""
    r = admin.post(f"{BASE_URL}/api/drivers",
                   json={"full_name": f"MR08B Secrets {_tag()}",
                         "driver_status": "Training",
                         **SECRETS},
                   timeout=15)
    r.raise_for_status()
    did = r.json()["id"]
    # Confirm the sensitive fields were actually stored (Admin can see them).
    d = admin.get(f"{BASE_URL}/api/drivers/{did}", timeout=15).json()
    assert d.get("business_name") == SECRETS["business_name"]
    return did


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract rendered text from a PDF via pypdf so both FlateDecode and
    LZWDecode streams (ReportLab uses LZW for larger content streams) are
    decompressed correctly."""
    import io as _io
    import pypdf
    reader = pypdf.PdfReader(_io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _generate_profile_pdf(session, driver_id):
    r = session.post(f"{BASE_URL}/api/drivers/{driver_id}/exports/profile-pdf",
                     json={"confirm": True}, timeout=45)
    return r


def _download_pdf(session, version_id):
    r = session.get(f"{BASE_URL}/api/driver-export-versions/{version_id}/download",
                    timeout=45)
    r.raise_for_status()
    return r.content


class TestProfilePdfLeakGuard:
    """Sensitive marker values must not appear in a Profile PDF generated by
    Compliance. Allocator + ReadOnly cannot even generate a Profile PDF
    (MR-07B), so the closest permissible callable layer is the snapshot
    itself — exercised via the download route as the Compliance caller and
    by directly asserting the snapshot payload permissions block."""

    def _assert_pdf_hides_secrets(self, pdf_bytes: bytes, role: str):
        text = _extract_pdf_text(pdf_bytes)
        leaks = [k for k, v in SECRETS.items() if str(v) in text]
        assert not leaks, \
            f"MR-07A LEAK in {role} Profile PDF: fields {leaks} appeared in PDF text"

    def test_compliance_profile_pdf_hides_secrets(self, compliance, secret_driver):
        r = _generate_profile_pdf(compliance, secret_driver)
        assert r.status_code == 200, r.text
        version_id = r.json()["version"]["driver_export_version_id"]
        pdf = _download_pdf(compliance, version_id)
        self._assert_pdf_hides_secrets(pdf, "Compliance")

    def test_admin_profile_pdf_shows_secrets(self, admin, secret_driver):
        # Sanity — Admin/Manager Profile PDF may include the fields. This
        # asserts the fields are actually rendered when authorised, so the
        # Compliance-hidden assertion above proves gating rather than
        # simply proving the fields were never rendered anywhere.
        r = _generate_profile_pdf(admin, secret_driver)
        assert r.status_code == 200, r.text
        version_id = r.json()["version"]["driver_export_version_id"]
        pdf = _download_pdf(admin, version_id)
        text = _extract_pdf_text(pdf)
        assert SECRETS["business_name"] in text, \
            "Admin Profile PDF should contain business_name marker for control"

    def test_manager_profile_pdf_shows_secrets(self, manager, secret_driver):
        r = _generate_profile_pdf(manager, secret_driver)
        assert r.status_code == 200, r.text
        version_id = r.json()["version"]["driver_export_version_id"]
        pdf = _download_pdf(manager, version_id)
        text = _extract_pdf_text(pdf)
        assert SECRETS["business_name"] in text

    def test_allocator_cannot_generate_profile_pdf(self, allocator, secret_driver):
        # MR-07B locked Profile PDF to Admin/Manager/Compliance.
        r = _generate_profile_pdf(allocator, secret_driver)
        assert r.status_code == 403

    def test_readonly_cannot_generate_profile_pdf(self, readonly, secret_driver):
        r = _generate_profile_pdf(readonly, secret_driver)
        assert r.status_code == 403


class TestSnapshotHelperLeakGuard:
    """The closest callable layer for Allocator/ReadOnly is the snapshot
    resolution itself. If we import the resolver and drive it with an
    Allocator role directly, the returned payload's `business` dict must
    be empty and `permissions.account_visible` must be False."""

    def test_snapshot_hides_secrets_for_non_privileged_roles(self, secret_driver):
        import asyncio
        import sys
        sys.path.insert(0, "/app/backend")
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from driver_export_module import ExportService, EXPORT_TYPE_PROFILE_PDF

        async def _probe():
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"]]
            svc = ExportService(db)
            for role in ("Compliance", "Allocator", "ReadOnly"):
                snap = await svc._resolve_snapshot(
                    secret_driver, role, f"probe-{role}@dcc.test",
                    EXPORT_TYPE_PROFILE_PDF,
                )
                assert snap["permissions"]["account_visible"] is False, \
                    f"{role} snapshot leaked account_visible=True"
                business = snap.get("business", {})
                assert not business or all(v in (None, "") for v in business.values()), \
                    f"{role} snapshot leaked business fields: {business}"
            client.close()

        asyncio.run(_probe())
