"""
EB-05 Document Storage & Evidence Architecture.

Canonical document layer that separates metadata (Mongo) from binary content
(filesystem-backed storage adapter). Every document is versioned; each version
is written once and never overwritten. Access flows through authorised
FastAPI endpoints — the storage_key is a server-only value and is not
returned to the browser.

Collections:
    - documents
    - document_versions
    - document_links
    - document_access_events

Storage adapter (dev mode) writes into a private directory outside the web
root, configurable via env `DOCUMENT_STORAGE_PATH` (default
`/app/backend/document_storage`). No public URL is ever generated. Downloads
and previews are streamed through authenticated endpoints only.

Malware scanning is not connected in this build: files pass a strict content
sniff, size, and extension/MIME cross-check. Once those pass, the document
version is marked Active. A `_malware_scan_status` field is prepared so a
future scanning service can flip status to Quarantined without schema
changes. This limitation is disclosed in the README technical note.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status as http_status,
)
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict

from registers import (
    DRIVERS_COLL,
    OWNERS_COLL,
    VEHICLES_COLL,
    EQUIPMENT_COLL,
)
from compliance_records import (
    LICENCES_COLL,
    REGISTRATIONS_COLL,
    INSURANCE_COLL,
    INSPECTIONS_COLL,
    DEFECTS_COLL,
    MAINTENANCE_COLL,
    EQUIPMENT_COMPLIANCE_COLL,
)

logger = logging.getLogger("dcc.documents")

DOCUMENTS_COLL = "documents"
DOCUMENT_VERSIONS_COLL = "document_versions"
DOCUMENT_LINKS_COLL = "document_links"
DOCUMENT_ACCESS_EVENTS_COLL = "document_access_events"

SEED_TAG = "seed-eb05"

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
STORAGE_ROOT = Path(os.environ.get("DOCUMENT_STORAGE_PATH", "/app/backend/document_storage"))
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


# EB-R03A · Canonical storage adapter accessor.
# Routes ALL byte-writes and byte-reads through the authoritative
# StorageAdapter (LocalStorageAdapter in dev, S3CompatibleStorageAdapter
# in production) so preview/download never resolves an S3 key as a
# pod-local filesystem path.
_STORAGE_ADAPTER = None


def _get_storage_adapter():
    global _STORAGE_ADAPTER
    if _STORAGE_ADAPTER is None:
        from storage_module import _build_adapter_from_env
        _STORAGE_ADAPTER, _ = _build_adapter_from_env()
    return _STORAGE_ADAPTER


def _storage_provider_name() -> str:
    return _get_storage_adapter().provider


# ---------------------------------------------------------------- enums
class DocumentStatus(str, Enum):
    Active = "Active"
    Superseded = "Superseded"
    UnderReview = "Under Review"
    Rejected = "Rejected"
    Archived = "Archived"
    Quarantined = "Quarantined"


class Sensitivity(str, Enum):
    Standard = "Standard"
    Internal = "Internal"
    Confidential = "Confidential"
    Restricted = "Restricted"


class DocumentType(str, Enum):
    DriverLicence = "Driver Licence"
    VehicleRegistration = "Vehicle Registration"
    VehicleInsurance = "Vehicle Insurance"
    VehicleInspection = "Vehicle Inspection"
    VehicleDefect = "Vehicle Defect"
    VehicleMaintenance = "Vehicle Maintenance"
    EquipmentCompliance = "Equipment Compliance"
    DriverContract = "Driver Contract"
    DriverPass = "Driver Pass"
    ProfilePhoto = "Profile Photo"
    SupportingDocument = "Supporting Document"
    Other = "Other"


class EntityType(str, Enum):
    Driver = "Driver"
    Owner = "Owner"
    Vehicle = "Vehicle"
    Equipment = "Equipment"
    DriverLicence = "DriverLicence"
    VehicleRegistration = "VehicleRegistration"
    VehicleInsurancePolicy = "VehicleInsurancePolicy"
    VehicleInspection = "VehicleInspection"
    VehicleDefect = "VehicleDefect"
    VehicleMaintenanceTask = "VehicleMaintenanceTask"
    EquipmentCompliance = "EquipmentCompliance"
    DriverOwnerRelationship = "DriverOwnerRelationship"
    DriverVehicleAssignment = "DriverVehicleAssignment"
    DriverEquipmentAssignment = "DriverEquipmentAssignment"
    General = "General"


class LinkRelationship(str, Enum):
    Evidence = "Evidence"
    Contract = "Contract"
    Identification = "Identification"
    Photo = "Photo"
    Supporting = "Supporting"
    GeneratedExport = "Generated Export"
    Other = "Other"


class AccessAction(str, Enum):
    Upload = "Upload"
    ViewMetadata = "View Metadata"
    Preview = "Preview"
    Download = "Download"
    CreateVersion = "Create Version"
    Archive = "Archive"
    Restore = "Restore"
    Link = "Link"
    Unlink = "Unlink"
    Reject = "Reject"
    Approve = "Approve"


class AccessResult(str, Enum):
    Success = "Success"
    Denied = "Denied"
    Failed = "Failed"


# ---------------------------------------------------------------- allow lists / defaults
ALLOWED_EXTENSIONS: Dict[str, List[str]] = {
    "pdf": ["application/pdf"],
    "jpg": ["image/jpeg"],
    "jpeg": ["image/jpeg"],
    "png": ["image/png"],
    "webp": ["image/webp"],
    "doc": ["application/msword"],
    "docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    "xls": ["application/vnd.ms-excel"],
    "xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    "csv": ["text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"],
}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PREVIEWABLE_MIME_PREFIXES = ("application/pdf", "image/")

# File signature sniff — first N bytes
SIGNATURES = {
    "pdf": [b"%PDF-"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "webp": [b"RIFF"],  # + "WEBP" at offset 8
}

SENSITIVITY_DEFAULTS: Dict[str, str] = {
    DocumentType.ProfilePhoto.value: Sensitivity.Internal.value,
    DocumentType.DriverLicence.value: Sensitivity.Confidential.value,
    DocumentType.VehicleRegistration.value: Sensitivity.Internal.value,
    DocumentType.VehicleInsurance.value: Sensitivity.Confidential.value,
    DocumentType.DriverContract.value: Sensitivity.Restricted.value,
    DocumentType.DriverPass.value: Sensitivity.Confidential.value,
    DocumentType.VehicleDefect.value: Sensitivity.Internal.value,
    DocumentType.SupportingDocument.value: Sensitivity.Internal.value,
}

ENTITY_TO_COLLECTION: Dict[str, str] = {
    EntityType.Driver.value: DRIVERS_COLL,
    EntityType.Owner.value: OWNERS_COLL,
    EntityType.Vehicle.value: VEHICLES_COLL,
    EntityType.Equipment.value: EQUIPMENT_COLL,
    EntityType.DriverLicence.value: LICENCES_COLL,
    EntityType.VehicleRegistration.value: REGISTRATIONS_COLL,
    EntityType.VehicleInsurancePolicy.value: INSURANCE_COLL,
    EntityType.VehicleInspection.value: INSPECTIONS_COLL,
    EntityType.VehicleDefect.value: DEFECTS_COLL,
    EntityType.VehicleMaintenanceTask.value: MAINTENANCE_COLL,
    EntityType.EquipmentCompliance.value: EQUIPMENT_COMPLIANCE_COLL,
    EntityType.DriverOwnerRelationship.value: "driver_owner_relationships",
    EntityType.DriverVehicleAssignment.value: "driver_vehicle_assignments",
    EntityType.DriverEquipmentAssignment.value: "driver_equipment_assignments",
}

# Which compliance records carry an `evidence_document_id` primary reference
EVIDENCE_HOLDERS = {
    EntityType.DriverLicence.value: LICENCES_COLL,
    EntityType.VehicleRegistration.value: REGISTRATIONS_COLL,
    EntityType.VehicleInsurancePolicy.value: INSURANCE_COLL,
    EntityType.VehicleInspection.value: INSPECTIONS_COLL,
    EntityType.VehicleDefect.value: DEFECTS_COLL,
    EntityType.VehicleMaintenanceTask.value: MAINTENANCE_COLL,
    EntityType.EquipmentCompliance.value: EQUIPMENT_COMPLIANCE_COLL,
}


# ---------------------------------------------------------------- helpers
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitise_filename(name: str) -> str:
    name = name.strip().replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\-() ]", "_", name)
    return name[:180] or "file"


def _sniff_content(data: bytes, ext: str) -> bool:
    """Return True if the first bytes look like the claimed extension."""
    sigs = SIGNATURES.get(ext)
    if not sigs:
        # Office documents / CSV — trust extension + declared MIME only
        return True
    for sig in sigs:
        if data.startswith(sig):
            if ext == "webp":
                return len(data) >= 12 and data[8:12] == b"WEBP"
            return True
    return False


def _storage_key(document_id: str, version_number: int, ext: str) -> str:
    # Sharded path avoids gigantic directories.
    return f"{document_id[:2]}/{document_id}/v{version_number}.{ext}"


def _storage_path(key: str) -> Path:
    p = STORAGE_ROOT / key
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


async def _write_access_event(db, doc_id: str, version_id: Optional[str], user: Dict[str, Any],
                              action: AccessAction, result: AccessResult, reason: Optional[str] = None,
                              ip: Optional[str] = None, ua: Optional[str] = None):
    await db[DOCUMENT_ACCESS_EVENTS_COLL].insert_one({
        "id": str(uuid.uuid4()),
        "document_id": doc_id,
        "document_version_id": version_id,
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "user_role": user.get("role"),
        "action": action.value,
        "result": result.value,
        "reason": reason,
        "ip_address": ip,
        "user_agent": (ua or "")[:400],
        "timestamp": _iso(),
    })


def _require_write(user):
    if user.get("role") == "ReadOnly":
        raise HTTPException(status_code=403, detail="ReadOnly cannot upload or modify documents")


def _require_admin_manager(user):
    if user.get("role") not in ("Admin", "Manager"):
        raise HTTPException(status_code=403, detail="Admin or Manager only")


def _visible_by_sensitivity(user_role: str, sensitivity: str) -> bool:
    """Returns True if role is allowed to see (download/preview) this sensitivity."""
    if user_role == "Admin":
        return True
    if sensitivity == Sensitivity.Standard.value:
        return True
    if sensitivity == Sensitivity.Internal.value:
        return True
    if sensitivity == Sensitivity.Confidential.value:
        return user_role in ("Admin", "Manager", "Compliance")
    if sensitivity == Sensitivity.Restricted.value:
        return user_role in ("Admin", "Manager")
    return False


def _can_upload(user_role: str) -> bool:
    return user_role in ("Admin", "Manager", "Allocator", "Compliance")


async def _must_entity_exist(db, entity_type: str, entity_id: str):
    coll = ENTITY_TO_COLLECTION.get(entity_type)
    if not coll:
        raise HTTPException(status_code=400, detail=f"Unknown entity_type {entity_type}")
    exists = await db[coll].find_one({"id": entity_id}, {"_id": 0, "id": 1})
    if not exists:
        raise HTTPException(status_code=400, detail=f"{entity_type} {entity_id} not found")


# ---------------------------------------------------------------- upload models
class UploadValidationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)


async def _validate_and_persist(upload: UploadFile, actor_email: str, document_id: str, version_number: int) -> Dict[str, Any]:
    """Stream + validate + persist a single upload. Returns metadata."""
    if not upload.filename:
        raise UploadValidationError("Filename missing")
    original = upload.filename
    safe = _sanitise_filename(original)
    ext = safe.rsplit(".", 1)[-1].lower() if "." in safe else ""
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(f"Extension .{ext} not allowed")
    declared_mime = (upload.content_type or "").lower()
    if declared_mime and declared_mime not in ALLOWED_EXTENSIONS[ext]:
        # csv is often served as text/plain — allowed
        if not (ext == "csv" and declared_mime in ("text/plain", "text/csv", "application/csv")):
            raise UploadValidationError(f"Declared MIME '{declared_mime}' does not match extension .{ext}")

    key = _storage_key(document_id, version_number, ext)
    sha = hashlib.sha256()
    size = 0
    head = b""
    first_chunk = True
    buf = bytearray()
    try:
        while True:
            chunk = await upload.read(1024 * 64)
            if not chunk:
                break
            if first_chunk:
                head = chunk[:16]
                first_chunk = False
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise UploadValidationError(f"File exceeds max size {MAX_UPLOAD_BYTES // (1024 * 1024)}MB")
            sha.update(chunk)
            buf.extend(chunk)
        if size == 0:
            raise UploadValidationError("Zero-byte file rejected")
        if not _sniff_content(head, ext):
            raise UploadValidationError(f"File content does not match extension .{ext}")
        # EB-R03A · Persist bytes through the canonical storage adapter.
        # LocalStorageAdapter in dev, S3CompatibleStorageAdapter in
        # production. documents_module never writes to pod-local disk.
        _get_storage_adapter().put(
            key, bytes(buf),
            content_type=declared_mime or ALLOWED_EXTENSIONS[ext][0],
        )
    except UploadValidationError:
        raise
    except Exception as e:  # noqa: BLE001
        # EB-R03A · Do not persist metadata claiming success on failure.
        raise HTTPException(status_code=500, detail=f"Upload failed: {type(e).__name__}")

    return {
        "original_filename": original,
        "display_filename": safe,
        "mime_type": declared_mime or ALLOWED_EXTENSIONS[ext][0],
        "file_extension": ext,
        "file_size_bytes": size,
        "checksum_sha256": sha.hexdigest(),
        "storage_provider": _storage_provider_name(),
        "storage_key": key,
        "uploaded_at": _iso(),
        "uploaded_by": actor_email,
    }


# ---------------------------------------------------------------- indexes
async def ensure_indexes(db):
    for c in (DOCUMENTS_COLL, DOCUMENT_VERSIONS_COLL, DOCUMENT_LINKS_COLL, DOCUMENT_ACCESS_EVENTS_COLL):
        await db[c].create_index("id", unique=True)
    await db[DOCUMENT_VERSIONS_COLL].create_index("document_id")
    await db[DOCUMENT_LINKS_COLL].create_index("document_id")
    await db[DOCUMENT_LINKS_COLL].create_index([("entity_type", 1), ("entity_id", 1)])
    await db[DOCUMENT_ACCESS_EVENTS_COLL].create_index("document_id")
    await db[DOCUMENT_ACCESS_EVENTS_COLL].create_index("timestamp")


# ---------------------------------------------------------------- seed
async def seed_documents(db):
    """Idempotent EB-05 seed. Creates a handful of tiny placeholder files."""
    if await db[DOCUMENTS_COLL].count_documents({"_source": SEED_TAG}) > 0:
        return

    drivers = await db[DRIVERS_COLL].find({}, {"_id": 0, "id": 1, "full_name": 1}).to_list(50)
    vehicles = await db[VEHICLES_COLL].find({"_source": "seed-eb02"}, {"_id": 0, "id": 1}).to_list(50)
    equipment = await db[EQUIPMENT_COLL].find({"_source": "seed-eb02"}, {"_id": 0, "id": 1}).to_list(50)
    licences = await db[LICENCES_COLL].find({"_source": "seed-eb04"}, {"_id": 0, "id": 1, "driver_id": 1}).to_list(50)
    registrations = await db[REGISTRATIONS_COLL].find({"_source": "seed-eb04"}, {"_id": 0, "id": 1, "vehicle_id": 1}).to_list(50)
    insurance = await db[INSURANCE_COLL].find({"_source": "seed-eb04"}, {"_id": 0, "id": 1, "vehicle_id": 1}).to_list(50)
    inspections = await db[INSPECTIONS_COLL].find({"_source": "seed-eb04"}, {"_id": 0, "id": 1, "vehicle_id": 1}).to_list(50)
    defects = await db[DEFECTS_COLL].find({"_source": "seed-eb04"}, {"_id": 0, "id": 1, "vehicle_id": 1}).to_list(50)
    eq_comp = await db[EQUIPMENT_COMPLIANCE_COLL].find({"_source": "seed-eb04"}, {"_id": 0, "id": 1, "equipment_id": 1}).to_list(50)

    if len(drivers) < 3 or len(vehicles) < 3 or len(equipment) < 3:
        return

    tiny_pdf = b"%PDF-1.4\n%DCC-EB05 seed test PDF\n%%EOF\n"
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x8bF\x1e\xea\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    async def _make_seed_doc(title, doctype, ext, content, linked_entities):
        doc_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        key = _storage_key(doc_id, 1, ext)
        # EB-R03A · Seed writes go through the canonical adapter too, so
        # dev seed and production seed resolve identically at read time.
        _get_storage_adapter().put(key, content, ALLOWED_EXTENSIONS[ext][0])
        sha = hashlib.sha256(content).hexdigest()
        now = _iso()
        version = {
            "id": version_id,
            "document_id": doc_id,
            "version_number": 1,
            "original_filename": f"TEST-{title}.{ext}",
            "mime_type": ALLOWED_EXTENSIONS[ext][0],
            "file_extension": ext,
            "file_size_bytes": len(content),
            "checksum_sha256": sha,
            "storage_provider": _storage_provider_name(),
            "storage_key": key,
            "uploaded_at": now,
            "uploaded_by": "system-seed",
            "change_note": "seed initial version",
            "status": DocumentStatus.Active.value,
            "is_current": True,
            "is_archived": False,
            "created_at": now,
            "created_by": "system-seed",
            "_source": SEED_TAG,
        }
        await db[DOCUMENT_VERSIONS_COLL].insert_one(version)
        doc = {
            "id": doc_id,
            "title": title,
            "document_type": doctype,
            "category": "Compliance Evidence",
            "description": f"Seed EB-05 sample for {title}",
            "sensitivity": SENSITIVITY_DEFAULTS.get(doctype, Sensitivity.Internal.value),
            "status": DocumentStatus.Active.value,
            "current_version_id": version_id,
            "original_filename": version["original_filename"],
            "display_filename": _sanitise_filename(version["original_filename"]),
            "mime_type": version["mime_type"],
            "file_extension": ext,
            "file_size_bytes": len(content),
            "checksum_sha256": sha,
            "storage_provider": _storage_provider_name(),
            "storage_key": key,
            "uploaded_at": now,
            "uploaded_by": "system-seed",
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "is_archived": False,
            "_malware_scan_status": "not_scanned",
            "_source": SEED_TAG,
        }
        await db[DOCUMENTS_COLL].insert_one(doc)
        for i, (etype, eid, rel, primary) in enumerate(linked_entities):
            await db[DOCUMENT_LINKS_COLL].insert_one({
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "entity_type": etype,
                "entity_id": eid,
                "relationship_type": rel,
                "is_primary": primary,
                "is_archived": False,
                "created_at": now,
                "created_by": "system-seed",
                "_source": SEED_TAG,
            })
        # Wire evidence_document_id into the appropriate holder for the FIRST primary link on a compliance record
        for etype, eid, rel, primary in linked_entities:
            if primary and etype in EVIDENCE_HOLDERS:
                await db[EVIDENCE_HOLDERS[etype]].update_one(
                    {"id": eid}, {"$set": {"evidence_document_id": doc_id, "updated_at": now, "updated_by": "system-seed"}}
                )
                break

    # 1. Driver Licence evidence PDF
    if licences:
        lic = licences[0]
        await _make_seed_doc("Driver Licence Evidence", DocumentType.DriverLicence.value, "pdf", tiny_pdf,
                             [(EntityType.DriverLicence.value, lic["id"], LinkRelationship.Evidence.value, True),
                              (EntityType.Driver.value, lic["driver_id"], LinkRelationship.Supporting.value, False)])
    # 2. Vehicle Registration evidence PDF
    if registrations:
        reg = registrations[0]
        await _make_seed_doc("Vehicle Registration Evidence", DocumentType.VehicleRegistration.value, "pdf", tiny_pdf,
                             [(EntityType.VehicleRegistration.value, reg["id"], LinkRelationship.Evidence.value, True),
                              (EntityType.Vehicle.value, reg["vehicle_id"], LinkRelationship.Supporting.value, False)])
    # 3. Vehicle Insurance evidence PDF
    if insurance:
        ins = insurance[0]
        await _make_seed_doc("Vehicle Insurance Evidence", DocumentType.VehicleInsurance.value, "pdf", tiny_pdf,
                             [(EntityType.VehicleInsurancePolicy.value, ins["id"], LinkRelationship.Evidence.value, True),
                              (EntityType.Vehicle.value, ins["vehicle_id"], LinkRelationship.Supporting.value, False)])
    # 4. Inspection image
    if inspections:
        insp = inspections[0]
        await _make_seed_doc("Vehicle Inspection Photo", DocumentType.VehicleInspection.value, "png", tiny_png,
                             [(EntityType.VehicleInspection.value, insp["id"], LinkRelationship.Evidence.value, True),
                              (EntityType.Vehicle.value, insp["vehicle_id"], LinkRelationship.Photo.value, False)])
    # 5. Defect image
    if defects:
        d = defects[0]
        await _make_seed_doc("Vehicle Defect Photo", DocumentType.VehicleDefect.value, "png", tiny_png,
                             [(EntityType.VehicleDefect.value, d["id"], LinkRelationship.Evidence.value, True),
                              (EntityType.Vehicle.value, d["vehicle_id"], LinkRelationship.Photo.value, False)])
    # 6. Equipment compliance PDF
    if eq_comp:
        e = eq_comp[0]
        await _make_seed_doc("Equipment Compliance Cert", DocumentType.EquipmentCompliance.value, "pdf", tiny_pdf,
                             [(EntityType.EquipmentCompliance.value, e["id"], LinkRelationship.Evidence.value, True),
                              (EntityType.Equipment.value, e["equipment_id"], LinkRelationship.Supporting.value, False)])
    # 7. Driver contract PDF (Restricted)
    if drivers:
        drv = drivers[0]
        await _make_seed_doc("Driver Contract", DocumentType.DriverContract.value, "pdf", tiny_pdf,
                             [(EntityType.Driver.value, drv["id"], LinkRelationship.Contract.value, True)])
    # 8. Profile photo
    if drivers:
        drv = drivers[1] if len(drivers) > 1 else drivers[0]
        await _make_seed_doc("Driver Profile Photo", DocumentType.ProfilePhoto.value, "png", tiny_png,
                             [(EntityType.Driver.value, drv["id"], LinkRelationship.Photo.value, True)])


# ---------------------------------------------------------------- router
def build_documents_router(db, get_current_user):
    router = APIRouter(prefix="/api")

    async def _projected_doc(doc_id: str) -> Dict[str, Any]:
        d = await db[DOCUMENTS_COLL].find_one({"id": doc_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Document not found")
        return d

    async def _load_current_version(doc: Dict[str, Any]) -> Dict[str, Any]:
        v = await db[DOCUMENT_VERSIONS_COLL].find_one(
            {"id": doc.get("current_version_id")}, {"_id": 0}
        )
        if not v:
            raise HTTPException(status_code=404, detail="Current version not found")
        return v

    def _strip_storage(doc: Dict[str, Any]) -> Dict[str, Any]:
        d = {**doc}
        d.pop("storage_key", None)
        d.pop("storage_provider", None)
        return d

    def _strip_storage_v(v: Dict[str, Any]) -> Dict[str, Any]:
        d = {**v}
        d.pop("storage_key", None)
        d.pop("storage_provider", None)
        return d

    # ---------------- LIST ----------------
    @router.get("/documents")
    async def list_documents(
        document_type: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        sensitivity: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        include_archived: bool = False,
        current=Depends(get_current_user),
    ):
        q: Dict[str, Any] = {}
        if document_type: q["document_type"] = document_type
        if category: q["category"] = category
        if status: q["status"] = status
        if sensitivity: q["sensitivity"] = sensitivity
        if uploaded_by: q["uploaded_by"] = uploaded_by
        if not include_archived: q["is_archived"] = {"$ne": True}
        if entity_type and entity_id:
            links = await db[DOCUMENT_LINKS_COLL].find(
                {"entity_type": entity_type, "entity_id": entity_id, "is_archived": {"$ne": True}},
                {"_id": 0, "document_id": 1},
            ).to_list(2000)
            ids = [x["document_id"] for x in links]
            q["id"] = {"$in": ids} if ids else {"$in": ["__none__"]}
        docs = await db[DOCUMENTS_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
        # Filter by sensitivity visibility (list is always allowed metadata-wise)
        return [_strip_storage(d) for d in docs]

    @router.get("/documents/{document_id}")
    async def get_document(document_id: str, current=Depends(get_current_user)):
        d = await _projected_doc(document_id)
        await _write_access_event(db, document_id, d.get("current_version_id"), current,
                                   AccessAction.ViewMetadata, AccessResult.Success)
        return _strip_storage(d)

    # ---------------- UPLOAD ----------------
    @router.post("/documents/upload")
    async def upload_document(
        request: Request,
        file: UploadFile = File(...),
        title: str = Form(...),
        document_type: str = Form(...),
        category: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        sensitivity: Optional[str] = Form(None),
        entity_type: Optional[str] = Form(None),
        entity_id: Optional[str] = Form(None),
        relationship_type: Optional[str] = Form(None),
        is_primary: bool = Form(False),
        current=Depends(get_current_user),
    ):
        if not _can_upload(current.get("role", "")):
            raise HTTPException(status_code=403, detail="Role cannot upload documents")
        if document_type not in [t.value for t in DocumentType]:
            raise HTTPException(status_code=400, detail=f"Unknown document_type {document_type}")
        if entity_type and entity_id:
            await _must_entity_exist(db, entity_type, entity_id)

        doc_id = str(uuid.uuid4())
        try:
            meta = await _validate_and_persist(file, current.get("email") or "unknown", doc_id, 1)
        except HTTPException as e:
            # audit failure
            await _write_access_event(db, doc_id, None, current, AccessAction.Upload,
                                       AccessResult.Failed, reason=str(e.detail),
                                       ip=(request.client.host if request.client else None),
                                       ua=request.headers.get("user-agent"))
            raise
        # Optional duplicate warning
        dup = await db[DOCUMENTS_COLL].find_one(
            {"checksum_sha256": meta["checksum_sha256"], "is_archived": {"$ne": True}},
            {"_id": 0, "id": 1, "title": 1},
        )
        version_id = str(uuid.uuid4())
        now = _iso()
        sensitivity_val = sensitivity or SENSITIVITY_DEFAULTS.get(document_type, Sensitivity.Internal.value)
        version = {
            "id": version_id,
            "document_id": doc_id,
            "version_number": 1,
            **{k: meta[k] for k in ("original_filename", "mime_type", "file_extension", "file_size_bytes",
                                      "checksum_sha256", "storage_provider", "storage_key", "uploaded_at", "uploaded_by")},
            "change_note": "initial upload",
            "status": DocumentStatus.Active.value,
            "is_current": True,
            "is_archived": False,
            "created_at": now,
            "created_by": current.get("email"),
        }
        await db[DOCUMENT_VERSIONS_COLL].insert_one(version)
        version.pop("_id", None)
        doc = {
            "id": doc_id,
            "title": title,
            "document_type": document_type,
            "category": category,
            "description": description,
            "sensitivity": sensitivity_val,
            "status": DocumentStatus.Active.value,
            "current_version_id": version_id,
            **{k: meta[k] for k in ("original_filename", "mime_type", "file_extension", "file_size_bytes",
                                      "checksum_sha256", "storage_provider", "storage_key", "uploaded_at", "uploaded_by")},
            "display_filename": meta["display_filename"],
            "created_at": now,
            "updated_at": now,
            "created_by": current.get("email"),
            "updated_by": current.get("email"),
            "is_archived": False,
            "_malware_scan_status": "not_scanned",
        }
        await db[DOCUMENTS_COLL].insert_one(doc)
        doc.pop("_id", None)
        # EB-13 · Register the newly-persisted document in the private storage
        # service so it appears in the storage administration surface.
        try:
            from storage_module import get_storage_service
            svc = get_storage_service(db)
            _obj = await svc.register_existing(
                object_key=meta["storage_key"], sha256=meta["checksum_sha256"],
                file_size=meta["file_size_bytes"], content_type=meta["mime_type"],
                filename=meta["original_filename"], entity_type=entity_type,
                entity_id=entity_id, actor_email=current.get("email") or "system",
                document_id=doc_id, retention_class="Operational Document")
            await db[DOCUMENT_VERSIONS_COLL].update_one(
                {"id": version_id},
                {"$set": {"storage_object_id": _obj["storage_object_id"]}})
            await db[DOCUMENTS_COLL].update_one(
                {"id": doc_id},
                {"$set": {"storage_object_id": _obj["storage_object_id"]}})
        except Exception:  # noqa: BLE001
            # Registration is additive - never fail the upload if tracking fails.
            pass
        # Optional link
        if entity_type and entity_id:
            rel = relationship_type or LinkRelationship.Evidence.value
            # primary uniqueness by (entity_type, entity_id, relationship_type)
            if is_primary:
                await db[DOCUMENT_LINKS_COLL].update_many(
                    {"entity_type": entity_type, "entity_id": entity_id, "relationship_type": rel,
                     "is_primary": True, "is_archived": {"$ne": True}},
                    {"$set": {"is_primary": False}},
                )
            await db[DOCUMENT_LINKS_COLL].insert_one({
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "relationship_type": rel,
                "is_primary": bool(is_primary),
                "is_archived": False,
                "created_at": now,
                "created_by": current.get("email"),
            })
            # wire evidence placeholder if applicable
            if is_primary and entity_type in EVIDENCE_HOLDERS:
                await db[EVIDENCE_HOLDERS[entity_type]].update_one(
                    {"id": entity_id},
                    {"$set": {"evidence_document_id": doc_id, "updated_at": now, "updated_by": current.get("email")}},
                )
        await _write_access_event(db, doc_id, version_id, current, AccessAction.Upload, AccessResult.Success,
                                   ip=(request.client.host if request.client else None),
                                   ua=request.headers.get("user-agent"))
        return {
            "document": _strip_storage(doc),
            "duplicate_of": dup["id"] if dup else None,
            "duplicate_of_title": dup["title"] if dup else None,
        }

    # ---------------- UPDATE metadata ----------------
    @router.put("/documents/{document_id}")
    async def update_document(document_id: str, payload: dict, current=Depends(get_current_user)):
        _require_write(current)
        existing = await _projected_doc(document_id)
        allowed = {"title", "description", "category", "sensitivity", "status", "document_type"}
        updates = {k: v for k, v in (payload or {}).items() if k in allowed}
        if not updates:
            raise HTTPException(status_code=400, detail="No allowed updates provided")
        # Prevent lowering sensitivity if user cannot see it
        if "sensitivity" in updates:
            if not _visible_by_sensitivity(current.get("role", ""), existing.get("sensitivity", Sensitivity.Standard.value)):
                raise HTTPException(status_code=403, detail="Cannot alter sensitivity without permission")
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[DOCUMENTS_COLL].update_one({"id": document_id}, {"$set": updates})
        return _strip_storage(await _projected_doc(document_id))

    # ---------------- ARCHIVE / RESTORE ----------------
    @router.delete("/documents/{document_id}")
    async def archive_document(document_id: str, current=Depends(get_current_user)):
        _require_admin_manager(current)
        existing = await _projected_doc(document_id)
        await db[DOCUMENTS_COLL].update_one(
            {"id": document_id},
            {"$set": {"is_archived": True, "status": DocumentStatus.Archived.value,
                       "updated_at": _iso(), "updated_by": current.get("email")}},
        )
        await _write_access_event(db, document_id, existing.get("current_version_id"),
                                   current, AccessAction.Archive, AccessResult.Success)
        return {"status": "archived", "id": document_id}

    @router.post("/documents/{document_id}/restore")
    async def restore_document(document_id: str, current=Depends(get_current_user)):
        _require_admin_manager(current)
        existing = await _projected_doc(document_id)
        await db[DOCUMENTS_COLL].update_one(
            {"id": document_id},
            {"$set": {"is_archived": False, "status": DocumentStatus.Active.value,
                       "updated_at": _iso(), "updated_by": current.get("email")}},
        )
        await _write_access_event(db, document_id, existing.get("current_version_id"),
                                   current, AccessAction.Restore, AccessResult.Success)
        return {"status": "restored", "id": document_id}

    # ---------------- VERSIONS ----------------
    @router.get("/documents/{document_id}/versions")
    async def list_versions(document_id: str, current=Depends(get_current_user)):
        await _projected_doc(document_id)  # 404 guard
        vs = await db[DOCUMENT_VERSIONS_COLL].find({"document_id": document_id}, {"_id": 0}).sort("version_number", -1).to_list(500)
        return [_strip_storage_v(v) for v in vs]

    @router.post("/documents/{document_id}/versions")
    async def upload_new_version(
        document_id: str,
        request: Request,
        file: UploadFile = File(...),
        change_note: Optional[str] = Form(None),
        current=Depends(get_current_user),
    ):
        if not _can_upload(current.get("role", "")):
            raise HTTPException(status_code=403, detail="Role cannot upload document versions")
        doc = await _projected_doc(document_id)
        current_v = await db[DOCUMENT_VERSIONS_COLL].find_one(
            {"document_id": document_id, "is_current": True}, {"_id": 0, "version_number": 1}
        )
        new_num = (current_v.get("version_number") if current_v else 0) + 1
        meta = await _validate_and_persist(file, current.get("email") or "unknown", document_id, new_num)
        version_id = str(uuid.uuid4())
        now = _iso()
        # Close previous current
        await db[DOCUMENT_VERSIONS_COLL].update_many(
            {"document_id": document_id, "is_current": True},
            {"$set": {"is_current": False, "status": DocumentStatus.Superseded.value}},
        )
        version = {
            "id": version_id,
            "document_id": document_id,
            "version_number": new_num,
            **{k: meta[k] for k in ("original_filename", "mime_type", "file_extension", "file_size_bytes",
                                      "checksum_sha256", "storage_provider", "storage_key", "uploaded_at", "uploaded_by")},
            "change_note": change_note or f"version {new_num}",
            "status": DocumentStatus.Active.value,
            "is_current": True,
            "is_archived": False,
            "created_at": now,
            "created_by": current.get("email"),
        }
        await db[DOCUMENT_VERSIONS_COLL].insert_one(version)
        version.pop("_id", None)
        # Update doc pointer + metadata
        await db[DOCUMENTS_COLL].update_one(
            {"id": document_id},
            {"$set": {
                "current_version_id": version_id,
                **{k: meta[k] for k in ("original_filename", "mime_type", "file_extension", "file_size_bytes",
                                          "checksum_sha256", "storage_provider", "storage_key", "uploaded_at", "uploaded_by")},
                "display_filename": meta["display_filename"],
                "status": DocumentStatus.Active.value,
                "updated_at": now,
                "updated_by": current.get("email"),
            }},
        )
        await _write_access_event(db, document_id, version_id, current, AccessAction.CreateVersion, AccessResult.Success,
                                   ip=(request.client.host if request.client else None),
                                   ua=request.headers.get("user-agent"))
        return _strip_storage_v(version)

    @router.get("/documents/{document_id}/versions/{version_id}")
    async def get_version(document_id: str, version_id: str, current=Depends(get_current_user)):
        v = await db[DOCUMENT_VERSIONS_COLL].find_one({"id": version_id, "document_id": document_id}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        return _strip_storage_v(v)

    # ---------------- DOWNLOAD / PREVIEW ----------------
    def _stream_from_adapter(key: str, mime: str, filename: str, inline: bool):
        # EB-R03A · Bytes are always retrieved through the canonical
        # storage adapter. Never resolves an S3 key against the local
        # filesystem. Preserves streaming for large objects.
        adapter = _get_storage_adapter()
        try:
            gen = adapter.stream(key)
        except FileNotFoundError:
            raise HTTPException(status_code=410, detail="File missing from storage")
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — controlled error; no path/secret leakage
            raise HTTPException(status_code=502, detail="Storage read failed")
        disp = f'{"inline" if inline else "attachment"}; filename="{filename}"'
        return StreamingResponse(gen, media_type=mime, headers={"Content-Disposition": disp, "Cache-Control": "private, no-store"})

    async def _serve(doc: Dict[str, Any], version: Dict[str, Any], user, action: AccessAction, inline: bool, request: Request):
        if not _visible_by_sensitivity(user.get("role", ""), doc.get("sensitivity", Sensitivity.Standard.value)):
            await _write_access_event(db, doc["id"], version["id"], user, action, AccessResult.Denied,
                                       reason=f"Sensitivity {doc.get('sensitivity')} above role")
            raise HTTPException(status_code=403, detail="Sensitivity restricts this document for your role")
        if doc.get("is_archived") or version.get("is_archived"):
            raise HTTPException(status_code=410, detail="Document archived")
        await _write_access_event(db, doc["id"], version["id"], user, action, AccessResult.Success,
                                   ip=(request.client.host if request.client else None),
                                   ua=request.headers.get("user-agent"))
        return _stream_from_adapter(
            version["storage_key"],
            version.get("mime_type", "application/octet-stream"),
            version.get("original_filename", "file"),
            inline,
        )

    @router.get("/documents/{document_id}/download")
    async def download_current(document_id: str, request: Request, current=Depends(get_current_user)):
        doc = await _projected_doc(document_id)
        v = await _load_current_version(doc)
        return await _serve(doc, v, current, AccessAction.Download, inline=False, request=request)

    @router.get("/documents/{document_id}/preview")
    async def preview_current(document_id: str, request: Request, current=Depends(get_current_user)):
        doc = await _projected_doc(document_id)
        v = await _load_current_version(doc)
        if not (v.get("mime_type", "").startswith(PREVIEWABLE_MIME_PREFIXES)):
            raise HTTPException(status_code=415, detail="Preview not supported for this file type")
        return await _serve(doc, v, current, AccessAction.Preview, inline=True, request=request)

    @router.get("/documents/{document_id}/versions/{version_id}/download")
    async def download_version(document_id: str, version_id: str, request: Request, current=Depends(get_current_user)):
        doc = await _projected_doc(document_id)
        v = await db[DOCUMENT_VERSIONS_COLL].find_one({"id": version_id, "document_id": document_id}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        return await _serve(doc, v, current, AccessAction.Download, inline=False, request=request)

    @router.get("/documents/{document_id}/versions/{version_id}/preview")
    async def preview_version(document_id: str, version_id: str, request: Request, current=Depends(get_current_user)):
        doc = await _projected_doc(document_id)
        v = await db[DOCUMENT_VERSIONS_COLL].find_one({"id": version_id, "document_id": document_id}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        if not (v.get("mime_type", "").startswith(PREVIEWABLE_MIME_PREFIXES)):
            raise HTTPException(status_code=415, detail="Preview not supported for this file type")
        return await _serve(doc, v, current, AccessAction.Preview, inline=True, request=request)

    # ---------------- LINKS ----------------
    @router.get("/document-links")
    async def list_links(
        document_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        include_archived: bool = False,
        current=Depends(get_current_user),
    ):
        q: Dict[str, Any] = {}
        if document_id: q["document_id"] = document_id
        if entity_type: q["entity_type"] = entity_type
        if entity_id: q["entity_id"] = entity_id
        if relationship_type: q["relationship_type"] = relationship_type
        if not include_archived: q["is_archived"] = {"$ne": True}
        return await db[DOCUMENT_LINKS_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)

    @router.post("/document-links")
    async def create_link(payload: dict, current=Depends(get_current_user)):
        _require_write(current)
        needed = ("document_id", "entity_type", "entity_id")
        for k in needed:
            if not payload.get(k):
                raise HTTPException(status_code=400, detail=f"{k} required")
        # Validate document exists
        doc = await db[DOCUMENTS_COLL].find_one({"id": payload["document_id"], "is_archived": {"$ne": True}}, {"_id": 0, "id": 1})
        if not doc:
            raise HTTPException(status_code=400, detail="Document not found or archived")
        if payload["entity_type"] not in [e.value for e in EntityType]:
            raise HTTPException(status_code=400, detail=f"Unknown entity_type {payload['entity_type']}")
        if payload["entity_type"] != EntityType.General.value:
            await _must_entity_exist(db, payload["entity_type"], payload["entity_id"])
        rel = payload.get("relationship_type") or LinkRelationship.Evidence.value
        if rel not in [r.value for r in LinkRelationship]:
            raise HTTPException(status_code=400, detail=f"Unknown relationship_type {rel}")
        is_primary = bool(payload.get("is_primary"))
        if is_primary:
            await db[DOCUMENT_LINKS_COLL].update_many(
                {"entity_type": payload["entity_type"], "entity_id": payload["entity_id"],
                 "relationship_type": rel, "is_primary": True, "is_archived": {"$ne": True}},
                {"$set": {"is_primary": False}},
            )
        now = _iso()
        link = {
            "id": str(uuid.uuid4()),
            "document_id": payload["document_id"],
            "entity_type": payload["entity_type"],
            "entity_id": payload["entity_id"],
            "relationship_type": rel,
            "is_primary": is_primary,
            "is_archived": False,
            "created_at": now,
            "created_by": current.get("email"),
        }
        await db[DOCUMENT_LINKS_COLL].insert_one(link)
        link.pop("_id", None)
        # If linking primary evidence to a compliance record, wire evidence_document_id
        if is_primary and payload["entity_type"] in EVIDENCE_HOLDERS:
            await db[EVIDENCE_HOLDERS[payload["entity_type"]]].update_one(
                {"id": payload["entity_id"]},
                {"$set": {"evidence_document_id": payload["document_id"], "updated_at": now, "updated_by": current.get("email")}},
            )
        await _write_access_event(db, payload["document_id"], None, current, AccessAction.Link, AccessResult.Success,
                                   reason=f"{payload['entity_type']}:{payload['entity_id']}")
        return link

    @router.delete("/document-links/{link_id}")
    async def delete_link(link_id: str, current=Depends(get_current_user)):
        _require_write(current)
        link = await db[DOCUMENT_LINKS_COLL].find_one({"id": link_id}, {"_id": 0})
        if not link:
            raise HTTPException(status_code=404, detail="Link not found")
        await db[DOCUMENT_LINKS_COLL].update_one({"id": link_id}, {"$set": {"is_archived": True}})
        # If removing primary evidence, clear evidence_document_id on the compliance record
        if link.get("is_primary") and link["entity_type"] in EVIDENCE_HOLDERS:
            await db[EVIDENCE_HOLDERS[link["entity_type"]]].update_one(
                {"id": link["entity_id"], "evidence_document_id": link["document_id"]},
                {"$set": {"evidence_document_id": None, "updated_at": _iso(), "updated_by": current.get("email")}},
            )
        await _write_access_event(db, link["document_id"], None, current, AccessAction.Unlink, AccessResult.Success,
                                   reason=f"{link['entity_type']}:{link['entity_id']}")
        return {"status": "unlinked", "id": link_id}

    # ---------------- ACCESS HISTORY ----------------
    @router.get("/documents/{document_id}/access-history")
    async def access_history(document_id: str, current=Depends(get_current_user)):
        if current.get("role") not in ("Admin", "Manager", "Compliance"):
            raise HTTPException(status_code=403, detail="Access history restricted")
        return await db[DOCUMENT_ACCESS_EVENTS_COLL].find(
            {"document_id": document_id}, {"_id": 0}
        ).sort("timestamp", -1).to_list(1000)

    return router
