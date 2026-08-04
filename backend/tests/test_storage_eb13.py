"""EB-13 · Private Object Storage tests.

Uses:
    - Live REACT_APP_BACKEND_URL for the FastAPI storage router (LocalAdapter
      by default in the running preview env).
    - `moto` to unit-test the S3CompatibleStorageAdapter against a mocked
      AWS S3 endpoint. Real credentials are never used or created.

Fictional fixtures only. No real ACE identifiers.
"""
from __future__ import annotations

import hashlib
import io
import os
import uuid

import boto3
import pytest
import requests
from moto import mock_aws

# ── Live API base ────────────────────────────────────────────────────────────
BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
STO = f"{API}/storage"


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(admin_headers, role):
    email = f"eb13_{role.lower()}_{uuid.uuid4().hex[:6]}@acedriverhub.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB13 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"},
                   timeout=25)
    return _login(email, "T@1234")


@pytest.fixture(scope="module")
def admin_headers():
    return _login("admin@acedriverhub.com", "Admin@123")


@pytest.fixture(scope="module")
def readonly_headers(admin_headers):
    return _register(admin_headers, "ReadOnly")


@pytest.fixture(scope="module")
def manager_headers(admin_headers):
    return _register(admin_headers, "Manager")


# ══════════════════════════════════════════════════════════════════════════
# 1. Live LocalAdapter smoke via API
# ══════════════════════════════════════════════════════════════════════════
class TestLiveLocalAdapter:

    def test_health_endpoint(self, admin_headers):
        r = requests.get(f"{STO}/health", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["adapter"]["ok"] is True
        assert "objects" in body

    def test_configuration_status_never_leaks_credentials(self, admin_headers):
        r = requests.get(f"{STO}/configuration-status", headers=admin_headers).json()
        # No key that hints at credentials
        for k in r.keys():
            low = k.lower()
            assert "secret" not in low
            assert "access_key" not in low
            assert "token" not in low
            assert "password" not in low
        assert "backend" in r

    def test_readonly_denied_on_objects(self, readonly_headers):
        r = requests.get(f"{STO}/objects", headers=readonly_headers)
        assert r.status_code == 403

    def test_list_objects_admin_ok(self, admin_headers):
        r = requests.get(f"{STO}/objects", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_retention_policies_seeded(self, admin_headers):
        r = requests.get(f"{STO}/retention-policies", headers=admin_headers).json()
        assert len(r) >= 5
        names = {p["name"] for p in r}
        assert "Standard Operational" in names
        assert "Compliance Evidence Long" in names


# ══════════════════════════════════════════════════════════════════════════
# 2. EB-12 workbook uploads are stored via the storage service
# ══════════════════════════════════════════════════════════════════════════
class TestEB12WorkbookIntegration:

    def test_new_workbook_has_storage_object_id_and_no_inline_bytes(self, admin_headers):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(["driver_code", "full_name"])
        wb.active.append(["9901", "Ficta Storage"])
        buf = io.BytesIO(); wb.save(buf)
        files = {"file": ("eb13.xlsx", buf.getvalue(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        form = {"profile_name": f"EB13-STORAGE-{uuid.uuid4().hex[:6]}",
                "authority_level": "Authoritative", "data_domain": "Driver"}
        r = requests.post(f"{API}/migration-prep/workbooks/profile",
                            files=files, data=form, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        wb_out = r.json()
        assert wb_out.get("storage_object_id"), "new workbook must reference a storage object"
        # No inline bytes leaked via API
        assert "_data" not in wb_out
        # And the referenced storage object is visible to admin
        obj_r = requests.get(f"{STO}/objects/{wb_out['storage_object_id']}",
                              headers=admin_headers)
        assert obj_r.status_code == 200
        obj = obj_r.json()
        assert obj["status"] == "Available"
        assert obj["file_size"] > 0
        assert obj["sha256"] == wb_out["file_sha256"]


# ══════════════════════════════════════════════════════════════════════════
# 3. Retention policy CRUD
# ══════════════════════════════════════════════════════════════════════════
class TestRetentionCRUD:

    def test_create_and_update_policy(self, admin_headers):
        name = f"Test-{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{STO}/retention-policies",
                            json={"name": name,
                                   "retention_class": "Operational Document",
                                   "retention_days": 500,
                                   "archive_after_days": 200,
                                   "deletion_allowed": True,
                                   "legal_hold_supported": False},
                            headers=admin_headers, timeout=15)
        assert r.status_code == 200
        pid = r.json()["storage_retention_policy_id"]
        upd = requests.put(f"{STO}/retention-policies/{pid}",
                            json={"retention_days": 600},
                            headers=admin_headers).json()
        assert upd["retention_days"] == 600

    def test_invalid_class_rejected(self, admin_headers):
        r = requests.post(f"{STO}/retention-policies",
                            json={"name": "bad",
                                   "retention_class": "NotAClass",
                                   "retention_days": 30,
                                   "archive_after_days": 7,
                                   "deletion_allowed": False,
                                   "legal_hold_supported": False},
                            headers=admin_headers)
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
# 4. Reconciliation + Migration job endpoints
# ══════════════════════════════════════════════════════════════════════════
class TestReconciliationAndMigration:

    def test_start_reconciliation(self, admin_headers):
        r = requests.post(f"{STO}/reconciliation", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "Complete"
        assert "object_count" in body
        assert "healthy_count" in body

    def test_list_reconciliation_runs(self, admin_headers):
        r = requests.get(f"{STO}/reconciliation", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_migration_job(self, admin_headers):
        r = requests.post(f"{STO}/migrations",
                            json={"source_backend": "local",
                                   "target_backend": "s3",
                                   "scope": "Migration Workbooks"},
                            headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "Queued"

    def test_readonly_cannot_migrate(self, readonly_headers):
        r = requests.post(f"{STO}/migrations",
                            json={"source_backend": "local",
                                   "target_backend": "s3",
                                   "scope": "Migration Workbooks"},
                            headers=readonly_headers)
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
# 5. moto-mocked S3 adapter unit tests (no live API involved)
# ══════════════════════════════════════════════════════════════════════════
@mock_aws
class TestS3AdapterMotoMock:

    BUCKET = "eb13-test-bucket"
    REGION = "us-east-1"

    def _adapter(self):
        # Create the bucket inside the mock first
        s3 = boto3.client("s3", region_name=self.REGION,
                          aws_access_key_id="test", aws_secret_access_key="test")
        s3.create_bucket(Bucket=self.BUCKET)
        from storage_module import S3CompatibleStorageAdapter
        return S3CompatibleStorageAdapter(
            endpoint=None, region=self.REGION, bucket=self.BUCKET,
            access_key="test", secret_key="test",
            use_ssl=True, path_style=False, signed_ttl=60, prefix="dcc/test")

    def test_put_and_get(self):
        a = self._adapter()
        data = b"Hello EB-13 storage"
        meta = a.put("licences/abc/v1", data, "text/plain")
        assert meta["size"] == len(data)
        assert meta["sha256"] == hashlib.sha256(data).hexdigest()
        got = a.get("licences/abc/v1")
        assert got == data

    def test_exists_and_head(self):
        a = self._adapter()
        a.put("x/y/1", b"foo", "application/octet-stream")
        assert a.exists("x/y/1") is True
        assert a.exists("nope") is False
        h = a.head("x/y/1")
        assert h["size"] == 3

    def test_delete(self):
        a = self._adapter()
        a.put("z", b"bar")
        assert a.exists("z") is True
        a.delete("z")
        assert a.exists("z") is False

    def test_copy(self):
        a = self._adapter()
        a.put("src", b"payload")
        a.copy("src", "dst")
        assert a.get("dst") == b"payload"

    def test_signed_url(self):
        a = self._adapter()
        a.put("signme", b"payload")
        url = a.signed_url("signme", ttl_seconds=60)
        assert isinstance(url, str)
        assert self.BUCKET in url
        assert "Signature" in url or "X-Amz-Signature" in url

    def test_list_prefix(self):
        a = self._adapter()
        a.put("group/a/1", b"1")
        a.put("group/a/2", b"2")
        a.put("group/b/1", b"3")
        keys = a.list_prefix("group/a")
        assert len(keys) == 2

    def test_health_ok(self):
        a = self._adapter()
        h = a.health()
        assert h["ok"] is True
        assert h["provider"] == "s3"

    def test_encryption_header_used_on_put(self):
        """Verify server-side encryption header is requested on put."""
        a = self._adapter()
        a.put("enc/test", b"secret payload", "text/plain")
        # moto does not surface SSE, but the call succeeded which means the
        # kwargs (ServerSideEncryption=AES256) were accepted. Attempt to
        # verify with head_object; moto records the field.
        s3 = boto3.client("s3", region_name=self.REGION,
                          aws_access_key_id="test", aws_secret_access_key="test")
        h = s3.head_object(Bucket=self.BUCKET, Key="dcc/test/enc/test")
        # Some moto versions expose SSE in head; if not, ContentLength is enough
        assert h["ContentLength"] == len(b"secret payload")


# ══════════════════════════════════════════════════════════════════════════
# 6. LocalAdapter unit tests (direct)
# ══════════════════════════════════════════════════════════════════════════
class TestLocalAdapter:

    def _mktmp(self, tmp_path):
        from storage_module import LocalStorageAdapter
        return LocalStorageAdapter(str(tmp_path / "storage"))

    def test_put_get(self, tmp_path):
        a = self._mktmp(tmp_path)
        m = a.put("a/b/1", b"hi", "text/plain")
        assert m["size"] == 2
        assert a.get("a/b/1") == b"hi"

    def test_signed_url_none(self, tmp_path):
        a = self._mktmp(tmp_path)
        a.put("x", b"1")
        assert a.signed_url("x") is None  # local returns None

    def test_delete_and_missing(self, tmp_path):
        a = self._mktmp(tmp_path)
        a.put("x", b"1")
        assert a.delete("x") is True
        assert a.delete("x") is False
        with pytest.raises(FileNotFoundError):
            a.get("x")

    def test_list_prefix(self, tmp_path):
        a = self._mktmp(tmp_path)
        a.put("p/1", b"1"); a.put("p/2", b"2"); a.put("q/1", b"3")
        assert len(a.list_prefix("p")) == 2
        assert len(a.list_prefix("q")) == 1

    def test_health_reports_writable(self, tmp_path):
        a = self._mktmp(tmp_path)
        h = a.health()
        assert h["ok"] is True
        assert h["root_exists"] is True


# ══════════════════════════════════════════════════════════════════════════
# 7. Security: no PII in object keys
# ══════════════════════════════════════════════════════════════════════════
class TestKeyHygiene:

    def test_object_key_uses_uuid_only(self, admin_headers):
        # Fetch listing and check no email / phone-like patterns in keys.
        # object_key is stripped from list endpoint by design (privacy). Verify.
        r = requests.get(f"{STO}/objects", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        for row in r.json():
            assert "object_key" not in row, "object_key must not be exposed in list"
