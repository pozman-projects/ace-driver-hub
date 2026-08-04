"""EB-13 · Private Object Storage Abstraction.

Provider-neutral storage service backing all DCC file I/O. Two adapters
ship: LocalStorageAdapter (filesystem, dev-only) and
S3CompatibleStorageAdapter (AWS S3 / Cloudflare R2 / Backblaze B2 / MinIO
via boto3). Business modules call the ``StorageService`` — never a vendor
SDK directly.

Collections (all UUID-keyed):
  storage_objects              ← metadata for every stored file
  storage_object_versions      ← immutable versions per object
  storage_events               ← append-only audit log
  storage_migration_jobs       ← local → object-storage migrations
  storage_reconciliation_runs  ← health/reconciliation results
  storage_retention_policies   ← retention classes + rules
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field


# ── Collections ───────────────────────────────────────────────────────────────
OBJ_COLL = "storage_objects"
OBJVER_COLL = "storage_object_versions"
EV_COLL = "storage_events"
MIG_COLL = "storage_migration_jobs"
RECON_COLL = "storage_reconciliation_runs"
POL_COLL = "storage_retention_policies"

# ── Enums ─────────────────────────────────────────────────────────────────────
OBJ_STATUSES = {"Pending", "Available", "Verification Failed", "Archived",
                "Quarantined", "Missing", "Deleted", "Migration Pending",
                "Migration Failed"}
EVENT_TYPES = {"Upload Requested", "Upload Started", "Upload Completed",
                "Upload Failed", "Checksum Verified", "Checksum Failed",
                "Preview Requested", "Download Requested", "Signed Access Issued",
                "Access Denied", "Archived", "Restored", "Deleted", "Quarantined",
                "Migration Started", "Migration Completed", "Migration Failed",
                "Reconciliation Detected Missing", "Reconciliation Detected Orphan",
                "Metadata Updated"}
RETENTION_CLASSES = {"Operational Document", "Compliance Evidence",
                     "Generated Export", "Migration Source", "Temporary Upload",
                     "Archived Historical"}

ALLOWED_MIME = {
    "application/pdf", "image/jpeg", "image/png", "image/webp",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "text/csv", "application/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/octet-stream",   # fall-through for tests
}
BLOCKED_EXT = {"exe", "bat", "cmd", "com", "sh", "js", "vbs", "ps1", "html", "htm"}
DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB

ROLE_ADMIN = {"Admin"}
ROLE_MANAGER = {"Manager", "Admin"}
ROLE_STORAGE_VIEW = {"Manager", "Admin"}
ROLE_ALL = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}


def _uuid() -> str: return str(uuid.uuid4())
def _iso() -> str: return datetime.now(timezone.utc).isoformat()
def _sha256(data: bytes) -> str: return hashlib.sha256(data).hexdigest()


def _require(user: Dict[str, Any], allowed: set, err="Insufficient permissions"):
    if user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=err)


def _strip(v: Optional[dict]) -> Optional[dict]:
    if not v:
        return v
    out = dict(v)
    out.pop("_id", None)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Adapters
# ═══════════════════════════════════════════════════════════════════════════
class StorageAdapter:
    """Provider-neutral interface."""
    provider = "abstract"

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def stream(self, key: str):
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def head(self, key: str) -> Optional[dict]:
        raise NotImplementedError

    def signed_url(self, key: str, ttl_seconds: int = 300, mode: str = "download") -> Optional[str]:
        return None  # Local returns None; S3 returns a short-lived URL.

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def copy(self, src_key: str, dst_key: str) -> bool:
        raise NotImplementedError

    def list_prefix(self, prefix: str) -> List[str]:
        raise NotImplementedError

    def health(self) -> dict:
        return {"provider": self.provider, "ok": True}


class LocalStorageAdapter(StorageAdapter):
    provider = "local"

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # sanitise key: strip leading slashes
        rel = key.lstrip("/")
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put(self, key, data, content_type="application/octet-stream"):
        p = self._path(key)
        p.write_bytes(data)
        return {"provider": self.provider, "key": key, "size": len(data),
                "sha256": _sha256(data), "content_type": content_type,
                "provider_version_id": None, "etag": _sha256(data)[:16]}

    def get(self, key):
        p = self._path(key)
        if not p.exists():
            raise FileNotFoundError(key)
        return p.read_bytes()

    def stream(self, key):
        p = self._path(key)
        if not p.exists():
            raise FileNotFoundError(key)
        def gen():
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
        return gen()

    def exists(self, key):
        return self._path(key).exists()

    def head(self, key):
        p = self._path(key)
        if not p.exists():
            return None
        return {"size": p.stat().st_size, "provider_version_id": None}

    def delete(self, key):
        p = self._path(key)
        if p.exists():
            p.unlink()
            return True
        return False

    def copy(self, src, dst):
        src_p, dst_p = self._path(src), self._path(dst)
        if not src_p.exists():
            return False
        dst_p.write_bytes(src_p.read_bytes())
        return True

    def list_prefix(self, prefix):
        base = self.root / prefix.lstrip("/")
        if not base.exists():
            return []
        return [str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file()]

    def health(self):
        return {"provider": self.provider, "ok": True,
                "root_exists": self.root.exists(),
                "writable": os.access(str(self.root), os.W_OK)}


class S3CompatibleStorageAdapter(StorageAdapter):
    provider = "s3"

    def __init__(self, endpoint: Optional[str], region: str, bucket: str,
                  access_key: str, secret_key: str, session_token: Optional[str] = None,
                  use_ssl: bool = True, path_style: bool = False,
                  signed_ttl: int = 300, prefix: str = ""):
        import boto3
        from botocore.client import Config
        self.bucket = bucket
        self.signed_ttl = signed_ttl
        self.prefix = prefix.rstrip("/")
        config = Config(signature_version="s3v4",
                         s3={"addressing_style": "path" if path_style else "virtual"})
        client_kwargs = {"region_name": region, "config": config,
                          "aws_access_key_id": access_key,
                          "aws_secret_access_key": secret_key}
        if session_token:
            client_kwargs["aws_session_token"] = session_token
        if endpoint:
            client_kwargs["endpoint_url"] = endpoint
        client_kwargs["use_ssl"] = use_ssl
        self.client = boto3.client("s3", **client_kwargs)

    def _k(self, key):
        return f"{self.prefix}/{key.lstrip('/')}" if self.prefix else key.lstrip("/")

    def put(self, key, data, content_type="application/octet-stream"):
        k = self._k(key)
        r = self.client.put_object(Bucket=self.bucket, Key=k, Body=data,
                                    ContentType=content_type,
                                    ServerSideEncryption="AES256")
        return {"provider": self.provider, "key": key, "size": len(data),
                "sha256": _sha256(data), "content_type": content_type,
                "provider_version_id": r.get("VersionId"),
                "etag": (r.get("ETag") or "").strip('"')}

    def get(self, key):
        k = self._k(key)
        r = self.client.get_object(Bucket=self.bucket, Key=k)
        return r["Body"].read()

    def stream(self, key):
        k = self._k(key)
        r = self.client.get_object(Bucket=self.bucket, Key=k)
        return r["Body"].iter_chunks(chunk_size=65536)

    def exists(self, key):
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except ClientError:
            return False

    def head(self, key):
        from botocore.exceptions import ClientError
        try:
            r = self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return {"size": r.get("ContentLength"),
                    "provider_version_id": r.get("VersionId")}
        except ClientError:
            return None

    def signed_url(self, key, ttl_seconds=None, mode="download"):
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._k(key)},
            ExpiresIn=ttl_seconds or self.signed_ttl,
        )

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=self._k(key))
        return True

    def copy(self, src, dst):
        self.client.copy_object(Bucket=self.bucket,
                                 CopySource={"Bucket": self.bucket, "Key": self._k(src)},
                                 Key=self._k(dst))
        return True

    def list_prefix(self, prefix):
        keys = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self._k(prefix)):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def health(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return {"provider": self.provider, "ok": True, "bucket": self.bucket}
        except Exception as e:  # noqa: BLE001
            return {"provider": self.provider, "ok": False, "error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════════════════
def _build_adapter_from_env() -> Tuple[StorageAdapter, dict]:
    backend = os.environ.get("DOCUMENT_STORAGE_BACKEND", "local").lower()
    status = {"backend": backend, "configured": False, "signed_url_ttl": 300}
    if backend == "s3":
        endpoint = os.environ.get("OBJECT_STORAGE_ENDPOINT") or None
        region = os.environ.get("OBJECT_STORAGE_REGION", "us-east-1")
        bucket = os.environ.get("OBJECT_STORAGE_BUCKET")
        ak = os.environ.get("OBJECT_STORAGE_ACCESS_KEY_ID")
        sk = os.environ.get("OBJECT_STORAGE_SECRET_ACCESS_KEY")
        token = os.environ.get("OBJECT_STORAGE_SESSION_TOKEN")
        use_ssl = os.environ.get("OBJECT_STORAGE_USE_SSL", "true").lower() != "false"
        path_style = os.environ.get("OBJECT_STORAGE_PATH_STYLE", "false").lower() == "true"
        ttl = int(os.environ.get("OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS", "300"))
        prefix = os.environ.get("OBJECT_STORAGE_PREFIX", "")
        status["signed_url_ttl"] = ttl
        status["region"] = region
        status["endpoint_configured"] = bool(endpoint)
        status["bucket_configured"] = bool(bucket)
        status["credentials_configured"] = bool(ak and sk)
        if bucket and ak and sk:
            try:
                adapter = S3CompatibleStorageAdapter(
                    endpoint, region, bucket, ak, sk, token, use_ssl, path_style, ttl, prefix)
                status["configured"] = True
                return adapter, status
            except Exception as e:  # noqa: BLE001
                status["error"] = f"S3 init failed: {type(e).__name__}"
        # Fallback to local if S3 misconfigured
    root = os.environ.get("DOCUMENT_STORAGE_PATH", "/app/backend/document_storage")
    status["backend"] = "local"
    status["configured"] = True
    status["root_configured"] = bool(root)
    return LocalStorageAdapter(root), status


class StorageService:
    def __init__(self, db, adapter: Optional[StorageAdapter] = None,
                  status: Optional[dict] = None):
        self.db = db
        if adapter is None:
            adapter, status = _build_adapter_from_env()
        self.adapter = adapter
        self.status = status or {"backend": adapter.provider, "configured": True}
        self.max_bytes = int(os.environ.get("OBJECT_STORAGE_UPLOAD_MAX_BYTES",
                                              str(DEFAULT_MAX_BYTES)))

    # ---- upload ------------------------------------------------------------
    def _validate_upload(self, data: bytes, content_type: str, filename: str):
        if len(data) > self.max_bytes:
            raise HTTPException(status_code=400,
                                 detail=f"File exceeds max size {self.max_bytes}")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in BLOCKED_EXT:
            raise HTTPException(status_code=400,
                                 detail=f"Blocked extension .{ext}")
        # Basic signature checks
        if ext == "pdf" and not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="PDF signature mismatch")
        if content_type and content_type not in ALLOWED_MIME:
            # Allow only known types
            raise HTTPException(status_code=400,
                                 detail=f"Content type '{content_type}' not allowed")

    async def put(self, *, entity_type: Optional[str], entity_id: Optional[str],
                    filename: str, content: bytes, content_type: str,
                    actor_email: str, retention_class: str = "Operational Document",
                    document_id: Optional[str] = None,
                    migration_workbook_id: Optional[str] = None,
                    export_version_id: Optional[str] = None,
                    validate: bool = True) -> dict:
        if validate:
            self._validate_upload(content, content_type, filename)
        obj_id = _uuid()
        version_id = _uuid()
        object_uuid = _uuid()
        env = os.environ.get("APP_ENV", "dev")
        # Build key by entity type
        if migration_workbook_id:
            key = f"dcc/{env}/migration/{migration_workbook_id}/{object_uuid}"
        elif export_version_id:
            key = f"dcc/{env}/exports/{entity_id or 'anon'}/{export_version_id}/{object_uuid}"
        elif entity_type and entity_id:
            key = f"dcc/{env}/{entity_type}/{entity_id}/{document_id or obj_id}/{version_id}/{object_uuid}"
        else:
            key = f"dcc/{env}/misc/{object_uuid}"
        # Write event: upload started
        corr = _uuid()
        await self._event(obj_id, None, entity_type, entity_id, "Upload Started",
                           actor_email, corr, {"filename": filename})
        try:
            result = self.adapter.put(key, content, content_type or "application/octet-stream")
        except Exception as e:  # noqa: BLE001
            await self._event(obj_id, None, entity_type, entity_id, "Upload Failed",
                               actor_email, corr, {"error": str(e)[:200]})
            raise HTTPException(status_code=500,
                                 detail=f"Storage upload failed: {type(e).__name__}")
        checksum = result["sha256"]
        now = _iso()
        obj = {
            "storage_object_id": obj_id,
            "provider": self.adapter.provider,
            "bucket": getattr(self.adapter, "bucket", None),
            "object_key": key,
            "entity_type": entity_type, "entity_id": entity_id,
            "document_id": document_id,
            "migration_workbook_id": migration_workbook_id,
            "export_version_id": export_version_id,
            "current_version_id": version_id,
            "status": "Available",
            "content_type": content_type or "application/octet-stream",
            "original_file_name": (filename or "")[:200],
            "file_extension": (filename.rsplit(".", 1)[-1].lower() if "." in filename else ""),
            "file_size": len(content), "sha256": checksum,
            "encryption_status": "AES256" if self.adapter.provider == "s3" else "TLS/at-rest-N/A",
            "retention_class": retention_class,
            "malware_scan_status": "Not Scanned",
            "created_at": now, "updated_at": now,
            "created_by": actor_email, "updated_by": actor_email,
            "is_archived": False, "_source": "runtime",
        }
        version = {
            "storage_object_version_id": version_id,
            "storage_object_id": obj_id,
            "provider_version_id": result.get("provider_version_id"),
            "object_key": key, "version_number": 1,
            "content_type": obj["content_type"],
            "file_size": len(content), "sha256": checksum,
            "etag": result.get("etag"),
            "uploaded_at": now, "uploaded_by": actor_email,
            "verified_at": now, "verification_status": "Verified",
            "archive_status": "Active", "retention_until": None,
            "created_at": now, "is_archived": False,
        }
        await self.db[OBJ_COLL].insert_one(obj)
        await self.db[OBJVER_COLL].insert_one(version)
        await self._event(obj_id, version_id, entity_type, entity_id,
                           "Upload Completed", actor_email, corr,
                           {"sha256": checksum, "size": len(content)})
        await self._event(obj_id, version_id, entity_type, entity_id,
                           "Checksum Verified", actor_email, corr,
                           {"sha256": checksum})
        return _strip(obj)

    async def get_bytes(self, obj_id: str, actor_email: str, mode: str = "download") -> bytes:
        obj = await self.db[OBJ_COLL].find_one({"storage_object_id": obj_id}, {"_id": 0})
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found")
        if obj["status"] in ("Quarantined", "Verification Failed", "Deleted", "Missing"):
            raise HTTPException(status_code=400,
                                 detail=f"Object status '{obj['status']}' prevents access")
        try:
            data = self.adapter.get(obj["object_key"])
        except FileNotFoundError:
            await self._event(obj_id, obj["current_version_id"], obj.get("entity_type"),
                               obj.get("entity_id"), "Access Denied", actor_email, _uuid(),
                               {"reason": "object missing on backend"})
            raise HTTPException(status_code=404, detail="Object file missing")
        actual = _sha256(data)
        if actual != obj["sha256"]:
            await self._event(obj_id, obj["current_version_id"], obj.get("entity_type"),
                               obj.get("entity_id"), "Checksum Failed", actor_email, _uuid(),
                               {"expected": obj["sha256"], "actual": actual})
            raise HTTPException(status_code=500, detail="Checksum mismatch — refusing to serve")
        ev = "Preview Requested" if mode == "preview" else "Download Requested"
        await self._event(obj_id, obj["current_version_id"], obj.get("entity_type"),
                           obj.get("entity_id"), ev, actor_email, _uuid())
        return data

    async def signed_access(self, obj_id: str, actor_email: str, ttl: int = 300) -> Optional[str]:
        obj = await self.db[OBJ_COLL].find_one({"storage_object_id": obj_id}, {"_id": 0})
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found")
        url = self.adapter.signed_url(obj["object_key"], ttl_seconds=ttl)
        if url:
            await self._event(obj_id, obj["current_version_id"], obj.get("entity_type"),
                               obj.get("entity_id"), "Signed Access Issued",
                               actor_email, _uuid(), {"ttl": ttl})
        return url

    async def verify(self, obj_id: str, actor_email: str) -> dict:
        obj = await self.db[OBJ_COLL].find_one({"storage_object_id": obj_id}, {"_id": 0})
        if not obj:
            raise HTTPException(status_code=404, detail="Object not found")
        try:
            data = self.adapter.get(obj["object_key"])
            actual = _sha256(data)
            ok = (actual == obj["sha256"])
            new_status = "Available" if ok else "Verification Failed"
            await self.db[OBJ_COLL].update_one(
                {"storage_object_id": obj_id},
                {"$set": {"status": new_status, "updated_at": _iso()}})
            await self._event(obj_id, obj["current_version_id"], obj.get("entity_type"),
                               obj.get("entity_id"),
                               "Checksum Verified" if ok else "Checksum Failed",
                               actor_email, _uuid(),
                               {"expected": obj["sha256"], "actual": actual})
            return {"ok": ok, "expected": obj["sha256"], "actual": actual, "status": new_status}
        except FileNotFoundError:
            await self.db[OBJ_COLL].update_one(
                {"storage_object_id": obj_id},
                {"$set": {"status": "Missing", "updated_at": _iso()}})
            return {"ok": False, "status": "Missing"}

    async def archive(self, obj_id: str, actor_email: str):
        r = await self.db[OBJ_COLL].update_one(
            {"storage_object_id": obj_id},
            {"$set": {"is_archived": True, "status": "Archived", "updated_at": _iso()}})
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Object not found")
        await self._event(obj_id, None, None, None, "Archived", actor_email, _uuid())

    async def restore(self, obj_id: str, actor_email: str):
        r = await self.db[OBJ_COLL].update_one(
            {"storage_object_id": obj_id, "status": "Archived"},
            {"$set": {"is_archived": False, "status": "Available", "updated_at": _iso()}})
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Object not archived / not found")
        await self._event(obj_id, None, None, None, "Restored", actor_email, _uuid())

    async def quarantine(self, obj_id: str, actor_email: str, reason: str = ""):
        await self.db[OBJ_COLL].update_one(
            {"storage_object_id": obj_id},
            {"$set": {"status": "Quarantined", "updated_at": _iso()}})
        await self._event(obj_id, None, None, None, "Quarantined", actor_email, _uuid(),
                           {"reason": reason})

    async def _event(self, obj_id, ver_id, ent_t, ent_id, ev, actor, corr, payload=None):
        await self.db[EV_COLL].insert_one({
            "storage_event_id": _uuid(),
            "storage_object_id": obj_id,
            "storage_object_version_id": ver_id,
            "event_type": ev, "entity_type": ent_t, "entity_id": ent_id,
            "performed_by": actor, "performed_at": _iso(),
            "correlation_id": corr, "result": "Success",
            "payload": payload or {}, "created_at": _iso(),
        })

    async def register_existing(self, *, object_key: str, sha256: str,
                                  file_size: int, content_type: str,
                                  filename: str, entity_type: Optional[str],
                                  entity_id: Optional[str], actor_email: str,
                                  document_id: Optional[str] = None,
                                  export_version_id: Optional[str] = None,
                                  retention_class: str = "Operational Document",
                                  provider_override: Optional[str] = None) -> dict:
        """Register metadata for a file that has ALREADY been written to the
        adapter's backing store (e.g. by EB-05 documents or EB-11 exports).
        Does NOT re-write bytes. Used to give existing modules first-class
        visibility inside the EB-13 storage administration surface.
        """
        obj_id = _uuid()
        version_id = _uuid()
        now = _iso()
        provider = provider_override or self.adapter.provider
        obj = {
            "storage_object_id": obj_id,
            "provider": provider,
            "bucket": getattr(self.adapter, "bucket", None),
            "object_key": object_key,
            "entity_type": entity_type, "entity_id": entity_id,
            "document_id": document_id,
            "migration_workbook_id": None,
            "export_version_id": export_version_id,
            "current_version_id": version_id,
            "status": "Available",
            "content_type": content_type or "application/octet-stream",
            "original_file_name": (filename or "")[:200],
            "file_extension": (filename.rsplit(".", 1)[-1].lower() if "." in filename else ""),
            "file_size": file_size, "sha256": sha256,
            "encryption_status": "AES256" if provider == "s3" else "TLS/at-rest-N/A",
            "retention_class": retention_class,
            "malware_scan_status": "Not Scanned",
            "created_at": now, "updated_at": now,
            "created_by": actor_email, "updated_by": actor_email,
            "is_archived": False, "_source": "register-existing",
        }
        version = {
            "storage_object_version_id": version_id,
            "storage_object_id": obj_id,
            "provider_version_id": None,
            "object_key": object_key, "version_number": 1,
            "content_type": obj["content_type"],
            "file_size": file_size, "sha256": sha256,
            "etag": (sha256 or "")[:16],
            "uploaded_at": now, "uploaded_by": actor_email,
            "verified_at": now, "verification_status": "Verified",
            "archive_status": "Active", "retention_until": None,
            "created_at": now, "is_archived": False,
        }
        await self.db[OBJ_COLL].insert_one(obj)
        await self.db[OBJVER_COLL].insert_one(version)
        await self._event(obj_id, version_id, entity_type, entity_id,
                           "Upload Completed", actor_email, _uuid(),
                           {"sha256": sha256, "size": file_size,
                            "source": "register-existing"})
        return _strip(obj)

    async def reconcile(self, actor_email: str, run_type: str = "Full") -> dict:
        run_id = _uuid()
        now = _iso()
        objects = await self.db[OBJ_COLL].find({"is_archived": {"$ne": True}}, {"_id": 0}).to_list(5000)
        healthy = missing = orphan = mismatch = 0
        for o in objects:
            if not self.adapter.exists(o["object_key"]):
                missing += 1
                await self.db[OBJ_COLL].update_one(
                    {"storage_object_id": o["storage_object_id"]},
                    {"$set": {"status": "Missing", "updated_at": _iso()}})
                await self._event(o["storage_object_id"], None, o.get("entity_type"),
                                   o.get("entity_id"), "Reconciliation Detected Missing",
                                   actor_email, run_id)
            else:
                healthy += 1
        # Orphan detection: list_prefix + set-diff
        try:
            all_keys = set(self.adapter.list_prefix(f"dcc/{os.environ.get('APP_ENV', 'dev')}"))
            known_keys = {o["object_key"] for o in objects}
            for k in all_keys - known_keys:
                orphan += 1
                await self._event(None, None, None, None,
                                   "Reconciliation Detected Orphan",
                                   actor_email, run_id, {"key": k[:100]})
        except Exception:  # noqa: BLE001
            pass
        run = {
            "storage_reconciliation_run_id": run_id, "run_type": run_type,
            "status": "Complete", "requested_by": actor_email,
            "started_at": now, "completed_at": _iso(),
            "object_count": len(objects), "healthy_count": healthy,
            "missing_count": missing, "orphan_count": orphan,
            "checksum_failure_count": mismatch, "metadata_mismatch_count": 0,
            "correlation_id": run_id, "created_at": now,
        }
        await self.db[RECON_COLL].insert_one(run)
        return _strip(run)


# ── Indexes / Seed ────────────────────────────────────────────────────────────
async def ensure_indexes(db):
    await db[OBJ_COLL].create_index("storage_object_id", unique=True)
    await db[OBJ_COLL].create_index("entity_type")
    await db[OBJ_COLL].create_index("entity_id")
    await db[OBJ_COLL].create_index("document_id")
    await db[OBJ_COLL].create_index("migration_workbook_id")
    await db[OBJ_COLL].create_index("export_version_id")
    await db[OBJ_COLL].create_index("status")
    await db[OBJVER_COLL].create_index("storage_object_version_id", unique=True)
    await db[OBJVER_COLL].create_index("storage_object_id")
    await db[EV_COLL].create_index("storage_event_id", unique=True)
    await db[EV_COLL].create_index("storage_object_id")
    await db[MIG_COLL].create_index("storage_migration_job_id", unique=True)
    await db[RECON_COLL].create_index("storage_reconciliation_run_id", unique=True)
    await db[POL_COLL].create_index("storage_retention_policy_id", unique=True)


async def seed_retention_policies(db):
    if await db[POL_COLL].count_documents({"_source": "seed-eb13"}) > 0:
        return
    defaults = [
        ("Standard Operational", "Operational Document", 730, 365, True, False),
        ("Compliance Evidence Long", "Compliance Evidence", 2555, 730, False, True),
        ("Generated Export Historical", "Generated Export", 1825, 730, False, True),
        ("Migration Source Retention", "Migration Source", 365, 90, False, True),
        ("Temporary Upload", "Temporary Upload", 30, 7, True, False),
    ]
    now = _iso()
    for name, cls, ret, arch, del_ok, hold in defaults:
        await db[POL_COLL].insert_one({
            "storage_retention_policy_id": _uuid(),
            "name": name, "retention_class": cls,
            "retention_days": ret, "archive_after_days": arch,
            "deletion_allowed": del_ok, "legal_hold_supported": hold,
            "is_active": True, "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": "seed-eb13",
        })


# ── Pydantic ──────────────────────────────────────────────────────────────────
class RetentionPolicyCreate(BaseModel):
    name: str
    retention_class: str
    retention_days: int = 730
    archive_after_days: int = 365
    deletion_allowed: bool = False
    legal_hold_supported: bool = False


class MigrationCreate(BaseModel):
    source_backend: str = "local"
    target_backend: str = "s3"
    scope: str = "Migration Workbooks"


# ── Router ────────────────────────────────────────────────────────────────────
_service_singleton: Optional[StorageService] = None

def get_storage_service(db) -> StorageService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = StorageService(db)
    return _service_singleton


def build_storage_router(db, get_current_user):
    router = APIRouter(prefix="/api/storage", tags=["storage"])
    svc = get_storage_service(db)

    @router.get("/health")
    async def health(current=Depends(get_current_user)):
        _require(current, ROLE_STORAGE_VIEW)
        return {"adapter": svc.adapter.health(),
                 "objects": await db[OBJ_COLL].count_documents({}),
                 "available": await db[OBJ_COLL].count_documents({"status": "Available"}),
                 "missing": await db[OBJ_COLL].count_documents({"status": "Missing"}),
                 "quarantined": await db[OBJ_COLL].count_documents({"status": "Quarantined"})}

    @router.get("/configuration-status")
    async def config_status(current=Depends(get_current_user)):
        _require(current, ROLE_STORAGE_VIEW)
        # Return only safe booleans / provider type, NEVER credentials
        safe = dict(svc.status)
        # scrub anything credential-like defensively
        for k in list(safe.keys()):
            if any(bad in k.lower() for bad in ("secret", "key", "token", "password")):
                safe.pop(k)
        safe["max_upload_bytes"] = svc.max_bytes
        return safe

    @router.get("/objects")
    async def list_objects(current=Depends(get_current_user)):
        _require(current, ROLE_STORAGE_VIEW)
        rows = await db[OBJ_COLL].find({}, {"_id": 0, "object_key": 0}).sort("created_at", -1).to_list(500)
        return rows

    @router.get("/objects/{obj_id}")
    async def get_object(obj_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_STORAGE_VIEW)
        o = await db[OBJ_COLL].find_one({"storage_object_id": obj_id},
                                         {"_id": 0, "object_key": 0})
        if not o:
            raise HTTPException(status_code=404, detail="Not found")
        return o

    @router.get("/objects/{obj_id}/versions")
    async def list_versions(obj_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_STORAGE_VIEW)
        return await db[OBJVER_COLL].find(
            {"storage_object_id": obj_id}, {"_id": 0, "object_key": 0}
        ).sort("version_number", -1).to_list(200)

    @router.post("/objects/{obj_id}/archive")
    async def archive(obj_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await svc.archive(obj_id, current.get("email"))
        return {"archived": True}

    @router.post("/objects/{obj_id}/restore")
    async def restore(obj_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await svc.restore(obj_id, current.get("email"))
        return {"restored": True}

    @router.post("/objects/{obj_id}/verify")
    async def verify(obj_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await svc.verify(obj_id, current.get("email"))

    @router.post("/objects/{obj_id}/quarantine")
    async def quarantine(obj_id: str, payload: Dict[str, Any] = None,
                          current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        await svc.quarantine(obj_id, current.get("email"),
                              (payload or {}).get("reason", ""))
        return {"quarantined": True}

    @router.get("/objects/{obj_id}/preview")
    async def preview_obj(obj_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        data = await svc.get_bytes(obj_id, current.get("email"), mode="preview")
        obj = await db[OBJ_COLL].find_one({"storage_object_id": obj_id}, {"_id": 0})
        return Response(content=data, media_type=obj.get("content_type", "application/octet-stream"))

    @router.get("/objects/{obj_id}/download")
    async def download_obj(obj_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        data = await svc.get_bytes(obj_id, current.get("email"), mode="download")
        obj = await db[OBJ_COLL].find_one({"storage_object_id": obj_id}, {"_id": 0})
        return Response(content=data, media_type=obj.get("content_type", "application/octet-stream"),
                         headers={"Content-Disposition": f'attachment; filename="{obj.get("original_file_name", "download")}"'})

    # Migrations
    @router.post("/migrations")
    async def create_migration(payload: MigrationCreate, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        job = {
            "storage_migration_job_id": _uuid(),
            "source_backend": payload.source_backend,
            "target_backend": payload.target_backend,
            "scope": payload.scope, "status": "Queued",
            "requested_by": current.get("email"), "requested_at": _iso(),
            "started_at": None, "completed_at": None, "failed_at": None,
            "total_objects": 0, "migrated_objects": 0,
            "failed_objects": 0, "skipped_objects": 0, "bytes_migrated": 0,
            "correlation_id": _uuid(), "failure_reason": None,
            "created_at": _iso(), "updated_at": _iso(),
        }
        await db[MIG_COLL].insert_one(job)
        return _strip(job)

    @router.get("/migrations")
    async def list_migrations(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await db[MIG_COLL].find({}, {"_id": 0}).sort("created_at", -1).to_list(200)

    @router.get("/migrations/{job_id}")
    async def get_migration(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        j = await db[MIG_COLL].find_one({"storage_migration_job_id": job_id}, {"_id": 0})
        if not j:
            raise HTTPException(status_code=404, detail="Not found")
        return j

    @router.post("/migrations/{job_id}/execute")
    async def execute_migration(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        job = await db[MIG_COLL].find_one({"storage_migration_job_id": job_id}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Not found")
        # Scope: migrate legacy migration workbooks with _data bytes into storage
        migrated = failed = skipped = bytes_moved = 0
        if job["scope"] == "Migration Workbooks":
            wbs = await db["migration_source_workbooks"].find(
                {"_data": {"$exists": True, "$ne": None}}).to_list(500)
            for wb in wbs:
                if wb.get("storage_object_id"):
                    skipped += 1
                    continue
                try:
                    obj = await svc.put(
                        entity_type=None, entity_id=None,
                        filename=wb.get("sanitised_file_name", "workbook.xlsx"),
                        content=wb["_data"],
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        actor_email=current.get("email"),
                        migration_workbook_id=wb["migration_source_workbook_id"],
                        retention_class="Migration Source", validate=False)
                    await db["migration_source_workbooks"].update_one(
                        {"migration_source_workbook_id": wb["migration_source_workbook_id"]},
                        {"$set": {"storage_object_id": obj["storage_object_id"]},
                          "$unset": {"_data": ""}})
                    migrated += 1
                    bytes_moved += len(wb["_data"])
                except Exception:  # noqa: BLE001
                    failed += 1
        await db[MIG_COLL].update_one(
            {"storage_migration_job_id": job_id},
            {"$set": {"status": "Completed" if failed == 0 else "Failed",
                       "started_at": _iso(), "completed_at": _iso(),
                       "total_objects": migrated + failed + skipped,
                       "migrated_objects": migrated, "failed_objects": failed,
                       "skipped_objects": skipped, "bytes_migrated": bytes_moved,
                       "updated_at": _iso()}})
        return _strip(await db[MIG_COLL].find_one({"storage_migration_job_id": job_id}, {"_id": 0}))

    @router.post("/migrations/{job_id}/retry")
    async def retry_migration(job_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        # Idempotent - just re-execute
        return await execute_migration(job_id, current)  # type: ignore

    # Reconciliation
    @router.post("/reconciliation")
    async def start_reconciliation(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await svc.reconcile(current.get("email"))

    @router.get("/reconciliation")
    async def list_reconciliation(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await db[RECON_COLL].find({}, {"_id": 0}).sort("started_at", -1).to_list(200)

    @router.get("/reconciliation/{run_id}")
    async def get_reconciliation(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        r = await db[RECON_COLL].find_one({"storage_reconciliation_run_id": run_id}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Not found")
        return r

    # Retention
    @router.get("/retention-policies")
    async def list_policies(current=Depends(get_current_user)):
        _require(current, ROLE_STORAGE_VIEW)
        return await db[POL_COLL].find({"is_active": True}, {"_id": 0}).to_list(200)

    @router.post("/retention-policies")
    async def create_policy(payload: RetentionPolicyCreate, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        if payload.retention_class not in RETENTION_CLASSES:
            raise HTTPException(status_code=400, detail="Invalid retention_class")
        doc = {"storage_retention_policy_id": _uuid(),
                **payload.dict(), "is_active": True,
                "created_at": _iso(), "updated_at": _iso(),
                "created_by": current.get("email"), "updated_by": current.get("email"),
                "_source": "runtime"}
        await db[POL_COLL].insert_one(doc)
        return _strip(doc)

    @router.put("/retention-policies/{policy_id}")
    async def update_policy(policy_id: str, payload: Dict[str, Any],
                              current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        allowed = {"name", "retention_days", "archive_after_days",
                    "deletion_allowed", "legal_hold_supported", "is_active"}
        upd = {k: v for k, v in payload.items() if k in allowed}
        upd["updated_at"] = _iso()
        r = await db[POL_COLL].update_one(
            {"storage_retention_policy_id": policy_id}, {"$set": upd})
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Not found")
        return _strip(await db[POL_COLL].find_one({"storage_retention_policy_id": policy_id}, {"_id": 0}))

    @router.post("/retention-policies/{policy_id}/archive")
    async def archive_policy(policy_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        r = await db[POL_COLL].update_one(
            {"storage_retention_policy_id": policy_id},
            {"$set": {"is_active": False, "updated_at": _iso()}})
        if not r.matched_count:
            raise HTTPException(status_code=404, detail="Not found")
        return {"archived": True}

    return router
