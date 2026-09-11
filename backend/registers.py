"""
EB-02 Foundation Registers: Drivers, Owners, Vehicles, Equipment.

Canonical master registers with UUID string IDs and audit fields.
Runs alongside the legacy /api/modules/{slug} generic API — see README.
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

logger = logging.getLogger("dcc.registers")

# ---------- Collection names ---------------------------------------------------
# `drivers` is shared with the legacy prototype (idempotent field migration).
# Vehicles and Equipment are stored in dedicated canonical collections
# separate from the legacy `truck_regos` / `equipment` prototype collections,
# to avoid shape collisions.
DRIVERS_COLL = "drivers"
OWNERS_COLL = "owners"
VEHICLES_COLL = "vehicles_register"
EQUIPMENT_COLL = "equipment_register"


# ---------- Controlled value enums --------------------------------------------
class DriverStatus(str, Enum):
    Active = "Active"
    OnLeave = "On Leave"
    Training = "Training"
    Probation = "Probation"
    Inactive = "Inactive"
    Archived = "Archived"


class OwnerType(str, Enum):
    Individual = "Individual"
    Business = "Business"
    Trust = "Trust"
    Other = "Other"


class OwnerStatus(str, Enum):
    Active = "Active"
    Inactive = "Inactive"
    Archived = "Archived"


class OwnershipModel(str, Enum):
    Owned = "Owned"
    Leased = "Leased"
    SubContracted = "Sub-Contracted"
    Other = "Other"


class VehicleStatus(str, Enum):
    """EB-R02C · Canonical Vehicle Lifecycle values.

    Locked owner decisions:
      - "Inactive" is DEPRECATED and MUST NOT be a selectable/accepted value.
      - "Maintenance" is superseded by "In Workshop".
      - "Archived" is NOT a lifecycle state. Archival is controlled by is_archived.
    Legacy stored values are tolerated on READ only (see VehicleRead uses `str`).
    """

    Active = "Active"
    InWorkshop = "In Workshop"
    Retired = "Retired"
    Sold = "Sold"
    WrittenOff = "Written Off"
    PendingDisposal = "Pending Disposal"


# EB-R02C · Values allowed for READ tolerance only. Blocked on WRITE.
DEPRECATED_VEHICLE_STATUSES = {"Inactive", "Maintenance", "Archived"}
ALLOWED_VEHICLE_STATUSES = {s.value for s in VehicleStatus}


def _validate_vehicle_status_on_write(v):
    """Accepts only the six approved lifecycle values. Rejects deprecated ones.
    Called from write payloads (VehicleCreate / VehicleUpdate) only."""
    if v is None or v == "":
        return None
    if v in DEPRECATED_VEHICLE_STATUSES:
        raise ValueError(
            f"vehicle_status '{v}' is deprecated. Use one of {sorted(ALLOWED_VEHICLE_STATUSES)}."
        )
    if v not in ALLOWED_VEHICLE_STATUSES:
        raise ValueError(
            f"vehicle_status must be one of {sorted(ALLOWED_VEHICLE_STATUSES)}"
        )
    return v


class EquipmentType(str, Enum):
    Tray = "Tray"
    Trailer = "Trailer"
    Other = "Other"


class EquipmentStatus(str, Enum):
    Available = "Available"
    Assigned = "Assigned"
    Maintenance = "Maintenance"
    Inactive = "Inactive"
    Archived = "Archived"


# ---------- Base audit mixin (fields on every canonical record) ---------------
class AuditFields(BaseModel):
    id: str
    is_archived: bool = False
    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


# ---------- Drivers -----------------------------------------------------------
RESERVED_DISPATCH_NUMBERS = {"0", "13"}


def _normalise_dispatch(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    # If numeric, normalise leading zeros to canonical int-string for uniqueness
    try:
        n = int(s)
        canonical = str(n)
        if canonical in RESERVED_DISPATCH_NUMBERS:
            raise HTTPException(
                status_code=400,
                detail=f"Dispatch Number {canonical} is reserved and cannot be allocated",
            )
        return canonical
    except ValueError:
        # non-numeric dispatch tokens are allowed but must not be reserved names
        return s


class DriverBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str = Field(min_length=1)
    residential_address: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[EmailStr] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    profile_image_ref: Optional[str] = None
    driver_code: Optional[str] = None
    dispatch_number: Optional[str] = None
    start_date: Optional[str] = None
    driver_status: DriverStatus = DriverStatus.Active
    company_ref: Optional[str] = None
    business_name: Optional[str] = None
    abn: Optional[str] = None
    payroll_number: Optional[str] = None
    payment_percentage: Optional[float] = None

    @field_validator("payment_percentage")
    @classmethod
    def _valid_pct(cls, v):
        if v is None:
            return v
        if v < 0 or v > 100:
            raise ValueError("payment_percentage must be between 0 and 100")
        return v

    @field_validator("dispatch_number")
    @classmethod
    def _valid_dispatch(cls, v):
        return _normalise_dispatch(v)


class DriverCreate(DriverBase):
    pass


class DriverUpdate(BaseModel):
    """All fields optional for PATCH-style update."""

    model_config = ConfigDict(extra="ignore")

    full_name: Optional[str] = None
    residential_address: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[EmailStr] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    profile_image_ref: Optional[str] = None
    driver_code: Optional[str] = None
    dispatch_number: Optional[str] = None
    start_date: Optional[str] = None
    driver_status: Optional[DriverStatus] = None
    company_ref: Optional[str] = None
    business_name: Optional[str] = None
    abn: Optional[str] = None
    payroll_number: Optional[str] = None
    payment_percentage: Optional[float] = None
    is_archived: Optional[bool] = None

    @field_validator("payment_percentage")
    @classmethod
    def _valid_pct(cls, v):
        if v is None:
            return v
        if v < 0 or v > 100:
            raise ValueError("payment_percentage must be between 0 and 100")
        return v

    @field_validator("dispatch_number")
    @classmethod
    def _valid_dispatch(cls, v):
        return _normalise_dispatch(v)


class DriverRead(DriverBase, AuditFields):
    pass


# ---------- Owners ------------------------------------------------------------
class OwnerBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    owner_type: OwnerType = OwnerType.Business
    abn: Optional[str] = None  # stored as text to preserve formatting
    primary_contact_name: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[EmailStr] = None
    business_address: Optional[str] = None
    owner_status: OwnerStatus = OwnerStatus.Active
    company_ref: Optional[str] = None


class OwnerCreate(OwnerBase):
    pass


class OwnerUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    owner_type: Optional[OwnerType] = None
    abn: Optional[str] = None
    primary_contact_name: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[EmailStr] = None
    business_address: Optional[str] = None
    owner_status: Optional[OwnerStatus] = None
    company_ref: Optional[str] = None
    is_archived: Optional[bool] = None


class OwnerRead(OwnerBase, AuditFields):
    pass


# ---------- Vehicles ----------------------------------------------------------
class VehicleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    registration_number: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = None
    vehicle_type: Optional[str] = None
    carrier_configuration: Optional[str] = None
    ownership_model: Optional[OwnershipModel] = None
    owner_id: Optional[str] = None
    # EB-R02C · stored as plain str for legacy tolerance on READ. Writes go
    # through VehicleCreate / VehicleUpdate which enforce the canonical enum.
    vehicle_status: Optional[str] = VehicleStatus.Active.value
    company_ref: Optional[str] = None


class VehicleCreate(VehicleBase):
    @field_validator("vehicle_status")
    @classmethod
    def _valid_vehicle_status(cls, v):
        return _validate_vehicle_status_on_write(v)


class VehicleUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    registration_number: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = None
    vehicle_type: Optional[str] = None
    carrier_configuration: Optional[str] = None
    ownership_model: Optional[OwnershipModel] = None
    owner_id: Optional[str] = None
    vehicle_status: Optional[str] = None
    company_ref: Optional[str] = None
    is_archived: Optional[bool] = None

    @field_validator("vehicle_status")
    @classmethod
    def _valid_vehicle_status(cls, v):
        return _validate_vehicle_status_on_write(v)


class VehicleRead(VehicleBase, AuditFields):
    pass


# ---------- Equipment ---------------------------------------------------------
class EquipmentBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equipment_number: Optional[str] = None
    equipment_type: EquipmentType = EquipmentType.Other
    ownership_model: Optional[OwnershipModel] = None
    owner_id: Optional[str] = None
    equipment_status: EquipmentStatus = EquipmentStatus.Available
    company_ref: Optional[str] = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equipment_number: Optional[str] = None
    equipment_type: Optional[EquipmentType] = None
    ownership_model: Optional[OwnershipModel] = None
    owner_id: Optional[str] = None
    equipment_status: Optional[EquipmentStatus] = None
    company_ref: Optional[str] = None
    is_archived: Optional[bool] = None


class EquipmentRead(EquipmentBase, AuditFields):
    pass


# ---------- Helpers -----------------------------------------------------------
def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_unique(db, coll: str, field: str, value: Optional[str], exclude_id: Optional[str] = None):
    if value is None or value == "":
        return
    q = {field: value}
    if exclude_id is not None:
        q["id"] = {"$ne": exclude_id}
    existing = await db[coll].find_one(q, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"{field}='{value}' already exists on record {existing.get('id')}",
        )


async def _ensure_unique_dispatch(db, value: Optional[str], exclude_id: Optional[str] = None):
    """Dispatch Number must be unique among non-archived drivers when set."""
    if value is None or value == "":
        return
    q = {"dispatch_number": value, "is_archived": {"$ne": True}}
    if exclude_id is not None:
        q["id"] = {"$ne": exclude_id}
    existing = await db[DRIVERS_COLL].find_one(q, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Dispatch Number '{value}' is already active on driver {existing.get('id')}",
        )


async def _ensure_owner_exists(db, owner_id: Optional[str]):
    if owner_id is None or owner_id == "":
        return
    doc = await db[OWNERS_COLL].find_one({"id": owner_id}, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(status_code=400, detail=f"Owner {owner_id} not found")


def _require_write_role(user):
    if user.get("role") == "ReadOnly":
        raise HTTPException(status_code=403, detail="ReadOnly role cannot create or update")


def _require_delete_role(user):
    if user.get("role") not in ("Admin", "Manager"):
        raise HTTPException(status_code=403, detail="Only Admin or Manager may archive/delete")


# ---------- Migration + seeding (idempotent) ----------------------------------
async def migrate_existing_drivers(db):
    """Copy legacy driver fields into canonical fields where missing.

    Legacy → Canonical mapping:
        name           -> full_name
        driver_number  -> driver_code
        phone          -> mobile_number
        status         -> driver_status (mapped to controlled values)
        company        -> company_ref
    """
    status_map = {
        "Active": DriverStatus.Active.value,
        "On Leave": DriverStatus.OnLeave.value,
        "Inactive": DriverStatus.Inactive.value,
        "Training": DriverStatus.Training.value,
        "Probation": DriverStatus.Probation.value,
        "Archived": DriverStatus.Archived.value,
    }
    now = _iso_now()
    cursor = db[DRIVERS_COLL].find({}, {"_id": 0})
    async for d in cursor:
        updates = {}
        if not d.get("full_name") and d.get("name"):
            updates["full_name"] = d["name"]
        if not d.get("driver_code") and d.get("driver_number"):
            updates["driver_code"] = d["driver_number"]
        if not d.get("mobile_number") and d.get("phone"):
            updates["mobile_number"] = d["phone"]
        if not d.get("driver_status"):
            legacy_status = d.get("status") or "Active"
            updates["driver_status"] = status_map.get(legacy_status, DriverStatus.Active.value)
        if not d.get("company_ref") and d.get("company"):
            updates["company_ref"] = d["company"]
        if "is_archived" not in d:
            updates["is_archived"] = False
        if "updated_at" not in d:
            updates["updated_at"] = d.get("created_at") or now
        if updates:
            updates["_migrated_at"] = now
            await db[DRIVERS_COLL].update_one({"id": d["id"]}, {"$set": updates})


SEED_TAG = "seed-eb02"

SEED_OWNERS = [
    {
        "name": "TEST · River Freight Holdings Pty Ltd",
        "owner_type": OwnerType.Business.value,
        "abn": "12 345 678 901",
        "primary_contact_name": "Karen Iyer",
        "mobile_number": "+61 411 000 001",
        "business_address": "12 Freight Ln, Alexandria NSW",
        "owner_status": OwnerStatus.Active.value,
        "company_ref": "ACE Car Freighters",
    },
    {
        "name": "TEST · Blackwood Transport Trust",
        "owner_type": OwnerType.Trust.value,
        "abn": "98 765 432 109",
        "primary_contact_name": "Marcus Blackwood",
        "mobile_number": "+61 411 000 002",
        "business_address": "7 Wharf Rd, Port Melbourne VIC",
        "owner_status": OwnerStatus.Active.value,
        "company_ref": "ACE Car Freighters",
    },
]

SEED_VEHICLES = [
    {
        "registration_number": "TEST-V01",
        "vin": "TESTVIN0000000001",
        "make": "Kenworth",
        "model": "T610",
        "year": "2021",
        "vehicle_type": "Prime Mover",
        "carrier_configuration": "Semi-trailer",
        "ownership_model": OwnershipModel.Owned.value,
        "vehicle_status": VehicleStatus.Active.value,
        "company_ref": "ACE Car Freighters",
        "_seed_owner_key": "TEST · River Freight Holdings Pty Ltd",
    },
    {
        "registration_number": "TEST-V02",
        "vin": "TESTVIN0000000002",
        "make": "Volvo",
        "model": "FH16",
        "year": "2022",
        "vehicle_type": "Prime Mover",
        "carrier_configuration": "B-Double",
        "ownership_model": OwnershipModel.Leased.value,
        "vehicle_status": VehicleStatus.Active.value,
        "company_ref": "ACE Car Freighters",
        "_seed_owner_key": "TEST · Blackwood Transport Trust",
    },
    {
        "registration_number": "TEST-V03",
        "vin": "TESTVIN0000000003",
        "make": "Hino",
        "model": "700",
        "year": "2020",
        "vehicle_type": "Rigid",
        "carrier_configuration": "Single-carrier",
        "ownership_model": OwnershipModel.SubContracted.value,
        "vehicle_status": VehicleStatus.InWorkshop.value,
        "company_ref": "ACE Car Freighters",
        "_seed_owner_key": None,
    },
]

SEED_EQUIPMENT = [
    {
        "equipment_number": "TEST-E01",
        "equipment_type": EquipmentType.Tray.value,
        "ownership_model": OwnershipModel.Owned.value,
        "equipment_status": EquipmentStatus.Available.value,
        "company_ref": "ACE Car Freighters",
        "_seed_owner_key": "TEST · River Freight Holdings Pty Ltd",
    },
    {
        "equipment_number": "TEST-E02",
        "equipment_type": EquipmentType.Trailer.value,
        "ownership_model": OwnershipModel.Leased.value,
        "equipment_status": EquipmentStatus.Assigned.value,
        "company_ref": "ACE Car Freighters",
        "_seed_owner_key": "TEST · Blackwood Transport Trust",
    },
    {
        "equipment_number": "TEST-E03",
        "equipment_type": EquipmentType.Trailer.value,
        "ownership_model": OwnershipModel.SubContracted.value,
        "equipment_status": EquipmentStatus.Maintenance.value,
        "company_ref": "ACE Car Freighters",
        "_seed_owner_key": None,
    },
    {
        "equipment_number": "TEST-E04",
        "equipment_type": EquipmentType.Other.value,
        "ownership_model": OwnershipModel.Owned.value,
        "equipment_status": EquipmentStatus.Available.value,
        "company_ref": "ACE Car Freighters",
        "_seed_owner_key": None,
    },
]


async def seed_registers(db):
    """Idempotent development-only seed. All rows tagged `_source=seed-eb02`.

    Never duplicates on restart. Never inserts real ACE production data.
    """
    now = _iso_now()

    # Owners — dedup by name
    owner_key_to_id = {}
    for spec in SEED_OWNERS:
        existing = await db[OWNERS_COLL].find_one({"name": spec["name"]}, {"_id": 0, "id": 1})
        if existing:
            owner_key_to_id[spec["name"]] = existing["id"]
            continue
        doc = {
            **spec,
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "_source": SEED_TAG,
        }
        await db[OWNERS_COLL].insert_one(doc)
        owner_key_to_id[spec["name"]] = doc["id"]

    # Vehicles — dedup by registration_number
    for spec in SEED_VEHICLES:
        if await db[VEHICLES_COLL].find_one({"registration_number": spec["registration_number"]}):
            continue
        owner_key = spec.pop("_seed_owner_key", None)
        doc = {
            **spec,
            "id": str(uuid.uuid4()),
            "owner_id": owner_key_to_id.get(owner_key) if owner_key else None,
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "_source": SEED_TAG,
        }
        await db[VEHICLES_COLL].insert_one(doc)

    # Equipment — dedup by equipment_number
    for spec in SEED_EQUIPMENT:
        if await db[EQUIPMENT_COLL].find_one({"equipment_number": spec["equipment_number"]}):
            continue
        owner_key = spec.pop("_seed_owner_key", None)
        doc = {
            **spec,
            "id": str(uuid.uuid4()),
            "owner_id": owner_key_to_id.get(owner_key) if owner_key else None,
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "_source": SEED_TAG,
        }
        await db[EQUIPMENT_COLL].insert_one(doc)


async def ensure_indexes(db):
    await db[DRIVERS_COLL].create_index("id", unique=True)
    await db[OWNERS_COLL].create_index("id", unique=True)
    await db[VEHICLES_COLL].create_index("id", unique=True)
    await db[EQUIPMENT_COLL].create_index("id", unique=True)


async def reconcile_vehicle_lifecycle(db):
    """EB-R02C · Idempotent one-time lifecycle reconciliation.

    Rules (from locked owner decisions):
      * Existing "Active" rows: unchanged.
      * Existing "Maintenance" rows on NON-archived vehicles: safely remap to
        "In Workshop" (1:1 semantic — locked decision).
      * Existing "Inactive" rows: NEVER auto-map. Log a critical warning and
        return without mutation so the owner can triage.
      * Existing "Archived" rows: NEVER auto-map. Archived is not a lifecycle
        state. Left in place; is_archived remains the record-management flag.

    Returns a dict with counts for observability.
    """
    report = {"remapped_maintenance": 0, "encountered_inactive": 0, "left_archived": 0}

    # 1. Maintenance -> In Workshop (only non-archived rows)
    r = await db[VEHICLES_COLL].update_many(
        {"vehicle_status": "Maintenance", "is_archived": {"$ne": True}},
        {"$set": {"vehicle_status": VehicleStatus.InWorkshop.value, "updated_at": _iso_now(), "updated_by": "system-ebr02c"}},
    )
    report["remapped_maintenance"] = r.modified_count

    # 2. Inactive rows: DO NOT auto-map. Log for owner triage.
    report["encountered_inactive"] = await db[VEHICLES_COLL].count_documents(
        {"vehicle_status": "Inactive", "is_archived": {"$ne": True}}
    )
    if report["encountered_inactive"] > 0:
        logger.critical(
            "EB-R02C · %d vehicle(s) still have deprecated vehicle_status='Inactive'. "
            "No auto-mapping performed. Owner triage required.",
            report["encountered_inactive"],
        )

    # 3. Archived legacy lifecycle rows: left in place (audit-only count).
    report["left_archived"] = await db[VEHICLES_COLL].count_documents(
        {"vehicle_status": "Archived"}
    )

    if report["remapped_maintenance"]:
        logger.info("EB-R02C reconciliation: %s", report)
    return report


# ---------- Router factory ----------------------------------------------------
def build_registers_router(db, get_current_user):
    """Return the /api registers router. `db` is a Motor DB, `get_current_user` a FastAPI dep."""
    router = APIRouter(prefix="/api")

    # ------------------ DRIVERS ------------------
    @router.get("/drivers")
    async def list_drivers(include_archived: bool = False, current=Depends(get_current_user)):
        q = {} if include_archived else {"is_archived": {"$ne": True}}
        docs = await db[DRIVERS_COLL].find(q, {"_id": 0}).to_list(2000)
        # Ensure canonical fields exist on legacy docs (defensive)
        for d in docs:
            d.setdefault("full_name", d.get("name") or "")
            d.setdefault("driver_status", d.get("status") or DriverStatus.Active.value)
            d.setdefault("is_archived", False)
            d.setdefault("updated_at", d.get("created_at") or _iso_now())
        return docs

    @router.get("/drivers/{driver_id}")
    async def get_driver(driver_id: str, current=Depends(get_current_user)):
        doc = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Driver not found")
        doc.setdefault("full_name", doc.get("name") or "")
        doc.setdefault("driver_status", doc.get("status") or DriverStatus.Active.value)
        doc.setdefault("is_archived", False)
        return doc

    @router.post("/drivers", response_model=DriverRead)
    async def create_driver(payload: DriverCreate, current=Depends(get_current_user)):
        _require_write_role(current)
        await _ensure_unique(db, DRIVERS_COLL, "driver_code", payload.driver_code)
        await _ensure_unique_dispatch(db, payload.dispatch_number)
        now = _iso_now()
        doc = payload.model_dump()
        # legacy mirror for compat with existing readers (Driver Profile page etc)
        doc.setdefault("name", payload.full_name)
        doc.setdefault("driver_number", payload.driver_code or "")
        doc.setdefault("phone", payload.mobile_number or "")
        doc.setdefault("status", payload.driver_status.value if hasattr(payload.driver_status, 'value') else payload.driver_status)
        doc.setdefault("company", payload.company_ref or "")
        doc.update(
            {
                "id": str(uuid.uuid4()),
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": current.get("email"),
                "updated_by": current.get("email"),
            }
        )
        await db[DRIVERS_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.put("/drivers/{driver_id}", response_model=DriverRead)
    async def update_driver(driver_id: str, payload: DriverUpdate, current=Depends(get_current_user)):
        _require_write_role(current)
        existing = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Driver not found")
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        if "driver_code" in updates:
            await _ensure_unique(db, DRIVERS_COLL, "driver_code", updates["driver_code"], exclude_id=driver_id)
        if "dispatch_number" in updates:
            await _ensure_unique_dispatch(db, updates["dispatch_number"], exclude_id=driver_id)
        # Mirror canonical → legacy on update where relevant
        if "full_name" in updates:
            updates["name"] = updates["full_name"]
        if "driver_code" in updates:
            updates["driver_number"] = updates["driver_code"] or ""
        if "mobile_number" in updates:
            updates["phone"] = updates["mobile_number"] or ""
        if "driver_status" in updates:
            updates["status"] = updates["driver_status"]
        updates["updated_at"] = _iso_now()
        updates["updated_by"] = current.get("email")
        await db[DRIVERS_COLL].update_one({"id": driver_id}, {"$set": updates})
        doc = await db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        return doc

    @router.delete("/drivers/{driver_id}")
    async def archive_driver(driver_id: str, current=Depends(get_current_user)):
        """Soft-delete: mark is_archived=True, status=Archived. Preserves history."""
        _require_delete_role(current)
        result = await db[DRIVERS_COLL].update_one(
            {"id": driver_id},
            {
                "$set": {
                    "is_archived": True,
                    "driver_status": DriverStatus.Archived.value,
                    "status": DriverStatus.Archived.value,
                    "updated_at": _iso_now(),
                    "updated_by": current.get("email"),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Driver not found")
        return {"status": "archived", "id": driver_id}

    # ------------------ OWNERS ------------------
    @router.get("/owners", response_model=List[OwnerRead])
    async def list_owners(include_archived: bool = False, current=Depends(get_current_user)):
        q = {} if include_archived else {"is_archived": {"$ne": True}}
        return await db[OWNERS_COLL].find(q, {"_id": 0}).to_list(2000)

    @router.get("/owners/{owner_id}", response_model=OwnerRead)
    async def get_owner(owner_id: str, current=Depends(get_current_user)):
        doc = await db[OWNERS_COLL].find_one({"id": owner_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Owner not found")
        return doc

    @router.post("/owners", response_model=OwnerRead)
    async def create_owner(payload: OwnerCreate, current=Depends(get_current_user)):
        _require_write_role(current)
        now = _iso_now()
        doc = payload.model_dump()
        doc.update(
            {
                "id": str(uuid.uuid4()),
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": current.get("email"),
                "updated_by": current.get("email"),
            }
        )
        await db[OWNERS_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.put("/owners/{owner_id}", response_model=OwnerRead)
    async def update_owner(owner_id: str, payload: OwnerUpdate, current=Depends(get_current_user)):
        _require_write_role(current)
        existing = await db[OWNERS_COLL].find_one({"id": owner_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Owner not found")
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        updates["updated_at"] = _iso_now()
        updates["updated_by"] = current.get("email")
        await db[OWNERS_COLL].update_one({"id": owner_id}, {"$set": updates})
        return await db[OWNERS_COLL].find_one({"id": owner_id}, {"_id": 0})

    @router.delete("/owners/{owner_id}")
    async def archive_owner(owner_id: str, current=Depends(get_current_user)):
        _require_delete_role(current)
        result = await db[OWNERS_COLL].update_one(
            {"id": owner_id},
            {
                "$set": {
                    "is_archived": True,
                    "owner_status": OwnerStatus.Archived.value,
                    "updated_at": _iso_now(),
                    "updated_by": current.get("email"),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Owner not found")
        return {"status": "archived", "id": owner_id}

    # ------------------ VEHICLES ------------------
    @router.get("/vehicles", response_model=List[VehicleRead])
    async def list_vehicles(include_archived: bool = False, current=Depends(get_current_user)):
        q = {} if include_archived else {"is_archived": {"$ne": True}}
        return await db[VEHICLES_COLL].find(q, {"_id": 0}).to_list(2000)

    @router.get("/vehicles/{vehicle_id}", response_model=VehicleRead)
    async def get_vehicle(vehicle_id: str, current=Depends(get_current_user)):
        doc = await db[VEHICLES_COLL].find_one({"id": vehicle_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        return doc

    @router.post("/vehicles", response_model=VehicleRead)
    async def create_vehicle(payload: VehicleCreate, current=Depends(get_current_user)):
        _require_write_role(current)
        await _ensure_unique(db, VEHICLES_COLL, "registration_number", payload.registration_number)
        await _ensure_unique(db, VEHICLES_COLL, "vin", payload.vin)
        await _ensure_owner_exists(db, payload.owner_id)
        now = _iso_now()
        doc = payload.model_dump()
        doc.update(
            {
                "id": str(uuid.uuid4()),
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": current.get("email"),
                "updated_by": current.get("email"),
            }
        )
        await db[VEHICLES_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.put("/vehicles/{vehicle_id}", response_model=VehicleRead)
    async def update_vehicle(vehicle_id: str, payload: VehicleUpdate, current=Depends(get_current_user)):
        _require_write_role(current)
        existing = await db[VEHICLES_COLL].find_one({"id": vehicle_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        if "registration_number" in updates:
            await _ensure_unique(db, VEHICLES_COLL, "registration_number", updates["registration_number"], exclude_id=vehicle_id)
        if "vin" in updates:
            await _ensure_unique(db, VEHICLES_COLL, "vin", updates["vin"], exclude_id=vehicle_id)
        if "owner_id" in updates:
            await _ensure_owner_exists(db, updates["owner_id"])
        updates["updated_at"] = _iso_now()
        updates["updated_by"] = current.get("email")
        await db[VEHICLES_COLL].update_one({"id": vehicle_id}, {"$set": updates})
        return await db[VEHICLES_COLL].find_one({"id": vehicle_id}, {"_id": 0})

    @router.delete("/vehicles/{vehicle_id}")
    async def archive_vehicle(vehicle_id: str, current=Depends(get_current_user)):
        _require_delete_role(current)
        # EB-R02C · Archival is controlled by is_archived. vehicle_status
        # (lifecycle) is NOT touched — Archived is not a lifecycle state.
        result = await db[VEHICLES_COLL].update_one(
            {"id": vehicle_id},
            {
                "$set": {
                    "is_archived": True,
                    "updated_at": _iso_now(),
                    "updated_by": current.get("email"),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        return {"status": "archived", "id": vehicle_id}

    # ------------------ EQUIPMENT ------------------
    @router.get("/equipment", response_model=List[EquipmentRead])
    async def list_equipment(include_archived: bool = False, current=Depends(get_current_user)):
        q = {} if include_archived else {"is_archived": {"$ne": True}}
        return await db[EQUIPMENT_COLL].find(q, {"_id": 0}).to_list(2000)

    @router.get("/equipment/{equipment_id}", response_model=EquipmentRead)
    async def get_equipment(equipment_id: str, current=Depends(get_current_user)):
        doc = await db[EQUIPMENT_COLL].find_one({"id": equipment_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Equipment not found")
        return doc

    @router.post("/equipment", response_model=EquipmentRead)
    async def create_equipment(payload: EquipmentCreate, current=Depends(get_current_user)):
        _require_write_role(current)
        await _ensure_unique(db, EQUIPMENT_COLL, "equipment_number", payload.equipment_number)
        await _ensure_owner_exists(db, payload.owner_id)
        now = _iso_now()
        doc = payload.model_dump()
        doc.update(
            {
                "id": str(uuid.uuid4()),
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": current.get("email"),
                "updated_by": current.get("email"),
            }
        )
        await db[EQUIPMENT_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.put("/equipment/{equipment_id}", response_model=EquipmentRead)
    async def update_equipment(equipment_id: str, payload: EquipmentUpdate, current=Depends(get_current_user)):
        _require_write_role(current)
        existing = await db[EQUIPMENT_COLL].find_one({"id": equipment_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Equipment not found")
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        if "equipment_number" in updates:
            await _ensure_unique(db, EQUIPMENT_COLL, "equipment_number", updates["equipment_number"], exclude_id=equipment_id)
        if "owner_id" in updates:
            await _ensure_owner_exists(db, updates["owner_id"])
        updates["updated_at"] = _iso_now()
        updates["updated_by"] = current.get("email")
        await db[EQUIPMENT_COLL].update_one({"id": equipment_id}, {"$set": updates})
        return await db[EQUIPMENT_COLL].find_one({"id": equipment_id}, {"_id": 0})

    @router.delete("/equipment/{equipment_id}")
    async def archive_equipment(equipment_id: str, current=Depends(get_current_user)):
        _require_delete_role(current)
        result = await db[EQUIPMENT_COLL].update_one(
            {"id": equipment_id},
            {
                "$set": {
                    "is_archived": True,
                    "equipment_status": EquipmentStatus.Archived.value,
                    "updated_at": _iso_now(),
                    "updated_by": current.get("email"),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Equipment not found")
        return {"status": "archived", "id": equipment_id}

    return router
