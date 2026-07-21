"""
EB-03 Assignment & Relationship Layer.

Canonical relationship collections (all UUID-id, audit-fielded, soft-delete):
    - driver_owner_relationships
    - driver_vehicle_assignments
    - driver_equipment_assignments

Consistency service (below `_service` fns) is called by both the HTTP routes
and the startup reconciliation so business rules live in one place.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from registers import (  # noqa: F401 — reuse canonical constants
    DRIVERS_COLL,
    OWNERS_COLL,
    VEHICLES_COLL,
    EQUIPMENT_COLL,
    EquipmentStatus,
    VehicleStatus,
)

logger = logging.getLogger("dcc.relationships")

DOR_COLL = "driver_owner_relationships"
DVA_COLL = "driver_vehicle_assignments"
DEA_COLL = "driver_equipment_assignments"

BLOCKED_EQUIPMENT_STATUSES = {
    EquipmentStatus.Maintenance.value,
    EquipmentStatus.Inactive.value,
    EquipmentStatus.Archived.value,
}

SEED_TAG = "seed-eb03"


# ---------------------------------------------------------------- enums / models
class RelationshipType(str, Enum):
    SelfOwned = "Self Owned"
    CompanyDriver = "Company Driver"
    ContractorDriver = "Contractor Driver"
    ReliefDriver = "Relief Driver"
    Other = "Other"


class _Audit(BaseModel):
    id: str
    is_archived: bool = False
    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class DriverOwnerBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    driver_id: str
    owner_id: str
    relationship_type: RelationshipType = RelationshipType.CompanyDriver
    is_current: bool = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class DriverOwnerCreate(DriverOwnerBase):
    pass


class DriverOwnerUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    relationship_type: Optional[RelationshipType] = None
    is_current: Optional[bool] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class DriverOwnerRead(DriverOwnerBase, _Audit):
    pass


class DriverVehicleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    driver_id: str
    vehicle_id: str
    is_active: bool = True
    is_primary: bool = True
    display_on_dispatch: bool = True
    dispatch_number_snapshot: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class DriverVehicleCreate(DriverVehicleBase):
    pass


class DriverVehicleUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    is_active: Optional[bool] = None
    is_primary: Optional[bool] = None
    display_on_dispatch: Optional[bool] = None
    dispatch_number_snapshot: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class DriverVehicleRead(DriverVehicleBase, _Audit):
    pass


class DriverEquipmentBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    driver_id: str
    equipment_id: str
    is_active: bool = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class DriverEquipmentCreate(DriverEquipmentBase):
    pass


class DriverEquipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    is_active: Optional[bool] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class DriverEquipmentRead(DriverEquipmentBase, _Audit):
    pass


class VehicleReassignBody(BaseModel):
    driver_id: str
    vehicle_id: str
    is_primary: bool = True
    display_on_dispatch: bool = True
    dispatch_number_snapshot: Optional[str] = None
    start_date: Optional[str] = None
    notes: Optional[str] = None


class EquipmentReassignBody(BaseModel):
    driver_id: str
    equipment_id: str
    start_date: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------- helpers
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _require_write(user):
    if user.get("role") == "ReadOnly":
        raise HTTPException(status_code=403, detail="ReadOnly role cannot create or update")


def _require_archive(user):
    if user.get("role") not in ("Admin", "Manager"):
        raise HTTPException(status_code=403, detail="Only Admin or Manager may archive")


async def _must_exist(db, coll: str, id_val: str, label: str):
    if not id_val:
        raise HTTPException(status_code=400, detail=f"{label} id required")
    if not await db[coll].find_one({"id": id_val}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"{label} {id_val} not found")


# ---------------------------------------------------------------- consistency service
class _Service:
    """Enforces business rules for the three relationship collections.

    Called by HTTP routes AND startup reconciliation so rules live in one place.
    """

    def __init__(self, db):
        self.db = db

    # ----- Driver-Owner
    async def close_current_owner_for_driver(self, driver_id: str, when: str, actor: Optional[str]):
        """Close any is_current=true DOR for driver, setting end_date."""
        return await self.db[DOR_COLL].update_many(
            {"driver_id": driver_id, "is_current": True, "is_archived": {"$ne": True}},
            {
                "$set": {
                    "is_current": False,
                    "end_date": when,
                    "updated_at": _iso(),
                    "updated_by": actor,
                }
            },
        )

    async def create_driver_owner(self, payload: DriverOwnerCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, DRIVERS_COLL, payload.driver_id, "Driver")
        await _must_exist(self.db, OWNERS_COLL, payload.owner_id, "Owner")
        now = _iso()
        doc = payload.model_dump(mode="json")
        # If new record marked current, auto-close previous current relationship for that driver
        if doc.get("is_current"):
            await self.close_current_owner_for_driver(
                payload.driver_id, doc.get("start_date") or _today(), actor
            )
        doc.update(
            {
                "id": str(uuid.uuid4()),
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": actor,
                "updated_by": actor,
            }
        )
        await self.db[DOR_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # ----- Driver-Vehicle
    async def close_active_primary_for_vehicle(self, vehicle_id: str, when: str, actor: Optional[str]):
        return await self.db[DVA_COLL].update_many(
            {
                "vehicle_id": vehicle_id,
                "is_active": True,
                "is_primary": True,
                "is_archived": {"$ne": True},
            },
            {
                "$set": {
                    "is_active": False,
                    "end_date": when,
                    "updated_at": _iso(),
                    "updated_by": actor,
                }
            },
        )

    async def close_active_primary_for_driver(self, driver_id: str, when: str, actor: Optional[str]):
        return await self.db[DVA_COLL].update_many(
            {
                "driver_id": driver_id,
                "is_active": True,
                "is_primary": True,
                "is_archived": {"$ne": True},
            },
            {
                "$set": {
                    "is_active": False,
                    "end_date": when,
                    "updated_at": _iso(),
                    "updated_by": actor,
                }
            },
        )

    async def create_driver_vehicle(self, payload: DriverVehicleCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, DRIVERS_COLL, payload.driver_id, "Driver")
        await _must_exist(self.db, VEHICLES_COLL, payload.vehicle_id, "Vehicle")
        # display_on_dispatch validation
        if payload.display_on_dispatch:
            drv = await self.db[DRIVERS_COLL].find_one({"id": payload.driver_id}, {"_id": 0})
            veh = await self.db[VEHICLES_COLL].find_one({"id": payload.vehicle_id}, {"_id": 0})
            if drv.get("is_archived"):
                raise HTTPException(status_code=400, detail="display_on_dispatch requires the driver to not be archived")
            if veh.get("vehicle_status") != VehicleStatus.Active.value:
                raise HTTPException(
                    status_code=400,
                    detail="display_on_dispatch requires the vehicle to have status=Active",
                )
            if not payload.is_active:
                raise HTTPException(status_code=400, detail="display_on_dispatch requires the assignment to be active")
        # Uniqueness enforcement — if new record is active+primary, auto-close conflicts
        now = _iso()
        when = payload.start_date or _today()
        if payload.is_active and payload.is_primary:
            await self.close_active_primary_for_vehicle(payload.vehicle_id, when, actor)
            await self.close_active_primary_for_driver(payload.driver_id, when, actor)
        doc = payload.model_dump(mode="json")
        doc.update(
            {
                "id": str(uuid.uuid4()),
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": actor,
                "updated_by": actor,
            }
        )
        await self.db[DVA_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def reassign_vehicle(self, body: VehicleReassignBody, actor: Optional[str]) -> Dict[str, Any]:
        """Atomic-ish reassignment: close prior active-primary on the vehicle+driver, create new."""
        await _must_exist(self.db, DRIVERS_COLL, body.driver_id, "Driver")
        await _must_exist(self.db, VEHICLES_COLL, body.vehicle_id, "Vehicle")
        payload = DriverVehicleCreate(
            driver_id=body.driver_id,
            vehicle_id=body.vehicle_id,
            is_active=True,
            is_primary=body.is_primary,
            display_on_dispatch=body.display_on_dispatch,
            dispatch_number_snapshot=body.dispatch_number_snapshot,
            start_date=body.start_date,
            notes=body.notes,
        )
        return await self.create_driver_vehicle(payload, actor)

    # ----- Driver-Equipment (with equipment status sync)
    async def _set_equipment_status(self, equipment_id: str, status: str, actor: Optional[str]):
        await self.db[EQUIPMENT_COLL].update_one(
            {"id": equipment_id},
            {"$set": {"equipment_status": status, "updated_at": _iso(), "updated_by": actor}},
        )

    async def close_active_for_equipment(self, equipment_id: str, when: str, actor: Optional[str]) -> int:
        r = await self.db[DEA_COLL].update_many(
            {
                "equipment_id": equipment_id,
                "is_active": True,
                "is_archived": {"$ne": True},
            },
            {
                "$set": {
                    "is_active": False,
                    "end_date": when,
                    "updated_at": _iso(),
                    "updated_by": actor,
                }
            },
        )
        return r.modified_count

    async def sync_equipment_status_after_change(self, equipment_id: str, actor: Optional[str]):
        """After any assignment mutation, resync equipment_status if applicable.

        - If there is an active assignment and status is Available → set Assigned
        - If there is no active assignment and status is Assigned → set Available
        Statuses Maintenance / Inactive / Archived are left untouched.
        """
        eq = await self.db[EQUIPMENT_COLL].find_one({"id": equipment_id}, {"_id": 0})
        if not eq:
            return
        current = eq.get("equipment_status")
        if current in BLOCKED_EQUIPMENT_STATUSES:
            return
        has_active = await self.db[DEA_COLL].find_one(
            {"equipment_id": equipment_id, "is_active": True, "is_archived": {"$ne": True}},
            {"_id": 0, "id": 1},
        )
        target = EquipmentStatus.Assigned.value if has_active else EquipmentStatus.Available.value
        if current != target:
            await self._set_equipment_status(equipment_id, target, actor)

    async def create_driver_equipment(
        self, payload: DriverEquipmentCreate, actor: Optional[str], allow_conflict_close: bool = False
    ) -> Dict[str, Any]:
        await _must_exist(self.db, DRIVERS_COLL, payload.driver_id, "Driver")
        await _must_exist(self.db, EQUIPMENT_COLL, payload.equipment_id, "Equipment")
        eq = await self.db[EQUIPMENT_COLL].find_one({"id": payload.equipment_id}, {"_id": 0})
        if eq.get("equipment_status") in BLOCKED_EQUIPMENT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Equipment status {eq.get('equipment_status')} cannot be newly assigned",
            )
        if payload.is_active:
            existing = await self.db[DEA_COLL].find_one(
                {
                    "equipment_id": payload.equipment_id,
                    "is_active": True,
                    "is_archived": {"$ne": True},
                },
                {"_id": 0, "id": 1, "driver_id": 1},
            )
            if existing and not allow_conflict_close:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Equipment already actively assigned (assignment {existing['id']}). "
                        "Use POST /api/driver-equipment-assignments/reassign to close and reassign."
                    ),
                )
            if existing and allow_conflict_close:
                await self.close_active_for_equipment(payload.equipment_id, payload.start_date or _today(), actor)
        now = _iso()
        doc = payload.model_dump(mode="json")
        doc.update(
            {
                "id": str(uuid.uuid4()),
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": actor,
                "updated_by": actor,
            }
        )
        await self.db[DEA_COLL].insert_one(doc)
        doc.pop("_id", None)
        await self.sync_equipment_status_after_change(payload.equipment_id, actor)
        return doc

    async def reassign_equipment(self, body: EquipmentReassignBody, actor: Optional[str]) -> Dict[str, Any]:
        payload = DriverEquipmentCreate(
            driver_id=body.driver_id,
            equipment_id=body.equipment_id,
            is_active=True,
            start_date=body.start_date,
            notes=body.notes,
        )
        return await self.create_driver_equipment(payload, actor, allow_conflict_close=True)

    # ----- Archival cascades
    async def archive_equipment_cascade(self, equipment_id: str, actor: Optional[str]):
        """When equipment is archived, close all active assignments on it."""
        await self.db[DEA_COLL].update_many(
            {"equipment_id": equipment_id, "is_active": True, "is_archived": {"$ne": True}},
            {
                "$set": {
                    "is_active": False,
                    "end_date": _today(),
                    "updated_at": _iso(),
                    "updated_by": actor,
                }
            },
        )


# ---------------------------------------------------------------- indexes
async def ensure_indexes(db):
    for c in (DOR_COLL, DVA_COLL, DEA_COLL):
        await db[c].create_index("id", unique=True)
    await db[DOR_COLL].create_index("driver_id")
    await db[DOR_COLL].create_index("owner_id")
    await db[DVA_COLL].create_index("driver_id")
    await db[DVA_COLL].create_index("vehicle_id")
    await db[DEA_COLL].create_index("driver_id")
    await db[DEA_COLL].create_index("equipment_id")


# ---------------------------------------------------------------- reconciliation
async def startup_reconciliation(db):
    """Idempotent audit + auto-correct for seed inconsistencies only.

    Logs warnings for production-shape conflicts, never destroys history.
    """
    svc = _Service(db)
    report = {"warnings": [], "corrections": []}

    # 1. Duplicate active-primary DVA per driver
    pipeline = [
        {"$match": {"is_active": True, "is_primary": True, "is_archived": {"$ne": True}}},
        {"$group": {"_id": "$driver_id", "n": {"$sum": 1}, "ids": {"$push": "$id"}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    async for row in db[DVA_COLL].aggregate(pipeline):
        report["warnings"].append({"issue": "multiple_active_primary_per_driver", **row})

    # 2. Duplicate active-primary DVA per vehicle
    pipeline_v = [
        {"$match": {"is_active": True, "is_primary": True, "is_archived": {"$ne": True}}},
        {"$group": {"_id": "$vehicle_id", "n": {"$sum": 1}, "ids": {"$push": "$id"}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    async for row in db[DVA_COLL].aggregate(pipeline_v):
        report["warnings"].append({"issue": "multiple_active_primary_per_vehicle", **row})

    # 3. Duplicate active DEA per equipment
    pipeline_e = [
        {"$match": {"is_active": True, "is_archived": {"$ne": True}}},
        {"$group": {"_id": "$equipment_id", "n": {"$sum": 1}, "ids": {"$push": "$id"}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    async for row in db[DEA_COLL].aggregate(pipeline_e):
        report["warnings"].append({"issue": "multiple_active_per_equipment", **row})

    # 4. Equipment status mismatch — sync every equipment. Do not touch blocked statuses.
    async for eq in db[EQUIPMENT_COLL].find({}, {"_id": 0, "id": 1, "equipment_status": 1}):
        if eq.get("equipment_status") in BLOCKED_EQUIPMENT_STATUSES:
            continue
        await svc.sync_equipment_status_after_change(eq["id"], "system-reconciliation")

    if report["warnings"]:
        logger.warning("EB-03 reconciliation warnings: %s", report["warnings"])
    return report


# ---------------------------------------------------------------- seed
async def seed_relationships(db):
    """Development-only idempotent seed (dedup by driver_id + owner/vehicle/equipment_id)."""
    svc = _Service(db)
    now = _iso()

    drivers = await db[DRIVERS_COLL].find({}, {"_id": 0, "id": 1, "name": 1, "full_name": 1}).to_list(50)
    owners = await db[OWNERS_COLL].find({"_source": "seed-eb02"}, {"_id": 0, "id": 1, "name": 1}).to_list(50)
    vehicles = await db[VEHICLES_COLL].find({"_source": "seed-eb02"}, {"_id": 0, "id": 1, "registration_number": 1}).to_list(50)
    equipment = await db[EQUIPMENT_COLL].find({"_source": "seed-eb02"}, {"_id": 0, "id": 1, "equipment_number": 1}).to_list(50)

    if len(drivers) < 3 or len(owners) < 2 or len(vehicles) < 3 or len(equipment) < 3:
        logger.info("EB-03 seed skipped: not enough EB-02 master records available.")
        return

    d = drivers[:3]
    o = owners

    # --- Driver → Owner (3 current relationships)
    dor_specs = [
        (d[0]["id"], o[0]["id"], RelationshipType.CompanyDriver.value),
        (d[1]["id"], o[1]["id"], RelationshipType.ContractorDriver.value),
        (d[2]["id"], o[0]["id"], RelationshipType.CompanyDriver.value),
    ]
    for driver_id, owner_id, rtype in dor_specs:
        existing = await db[DOR_COLL].find_one(
            {"driver_id": driver_id, "owner_id": owner_id, "_source": SEED_TAG}
        )
        if existing:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "owner_id": owner_id,
            "relationship_type": rtype,
            "is_current": True,
            "start_date": "2026-01-01",
            "end_date": None,
            "notes": "seed relationship",
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "_source": SEED_TAG,
        }
        await db[DOR_COLL].insert_one(doc)

    # --- Driver → Vehicle (3 active primary + 1 closed history)
    dva_specs = [
        (d[0]["id"], vehicles[0]["id"], True, True),
        (d[1]["id"], vehicles[1]["id"], True, True),
        (d[2]["id"], vehicles[2]["id"], True, True),
    ]
    for driver_id, vehicle_id, active, primary in dva_specs:
        existing = await db[DVA_COLL].find_one(
            {"driver_id": driver_id, "vehicle_id": vehicle_id, "_source": SEED_TAG}
        )
        if existing:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "is_active": active,
            "is_primary": primary,
            "display_on_dispatch": True,
            "dispatch_number_snapshot": None,
            "start_date": "2026-01-05",
            "end_date": None,
            "notes": "seed assignment",
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "_source": SEED_TAG,
        }
        await db[DVA_COLL].insert_one(doc)
    # closed historical vehicle assignment (driver 0 was on vehicle 1 previously)
    hist_v = await db[DVA_COLL].find_one(
        {"driver_id": d[0]["id"], "vehicle_id": vehicles[1]["id"], "_source": SEED_TAG, "is_active": False}
    )
    if not hist_v:
        await db[DVA_COLL].insert_one(
            {
                "id": str(uuid.uuid4()),
                "driver_id": d[0]["id"],
                "vehicle_id": vehicles[1]["id"],
                "is_active": False,
                "is_primary": True,
                "display_on_dispatch": False,
                "dispatch_number_snapshot": None,
                "start_date": "2025-11-01",
                "end_date": "2026-01-04",
                "notes": "seed historical assignment",
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": "system-seed",
                "updated_by": "system-seed",
                "_source": SEED_TAG,
            }
        )

    # --- Driver → Equipment (3 active + 1 closed history)
    dea_specs = [
        (d[0]["id"], equipment[0]["id"], True),
        (d[1]["id"], equipment[1]["id"], True),
        (d[2]["id"], equipment[2]["id"], True),
    ]
    for driver_id, equipment_id, active in dea_specs:
        existing = await db[DEA_COLL].find_one(
            {"driver_id": driver_id, "equipment_id": equipment_id, "_source": SEED_TAG}
        )
        if existing:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "driver_id": driver_id,
            "equipment_id": equipment_id,
            "is_active": active,
            "start_date": "2026-01-05",
            "end_date": None,
            "notes": "seed equipment assignment",
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "_source": SEED_TAG,
        }
        await db[DEA_COLL].insert_one(doc)
    hist_e = await db[DEA_COLL].find_one(
        {"driver_id": d[0]["id"], "equipment_id": equipment[1]["id"], "_source": SEED_TAG, "is_active": False}
    )
    if not hist_e:
        await db[DEA_COLL].insert_one(
            {
                "id": str(uuid.uuid4()),
                "driver_id": d[0]["id"],
                "equipment_id": equipment[1]["id"],
                "is_active": False,
                "start_date": "2025-11-01",
                "end_date": "2026-01-04",
                "notes": "seed historical equipment assignment",
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
                "created_by": "system-seed",
                "updated_by": "system-seed",
                "_source": SEED_TAG,
            }
        )

    # Sync equipment statuses to reflect seeded active assignments
    for eq in equipment:
        await svc.sync_equipment_status_after_change(eq["id"], "system-seed")


# ---------------------------------------------------------------- router factory
def build_relationships_router(db, get_current_user):
    router = APIRouter(prefix="/api")
    svc = _Service(db)

    # ----------------- DRIVER-OWNER -----------------
    @router.get("/driver-owner-relationships")
    async def list_dor(
        driver_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        is_current: Optional[bool] = None,
        include_archived: bool = False,
        current=Depends(get_current_user),
    ):
        q: Dict[str, Any] = {}
        if driver_id:
            q["driver_id"] = driver_id
        if owner_id:
            q["owner_id"] = owner_id
        if is_current is not None:
            q["is_current"] = is_current
        if not include_archived:
            q["is_archived"] = {"$ne": True}
        return await db[DOR_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)

    @router.get("/driver-owner-relationships/{rid}", response_model=DriverOwnerRead)
    async def get_dor(rid: str, current=Depends(get_current_user)):
        doc = await db[DOR_COLL].find_one({"id": rid}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return doc

    @router.post("/driver-owner-relationships", response_model=DriverOwnerRead)
    async def create_dor(payload: DriverOwnerCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_driver_owner(payload, current.get("email"))

    @router.put("/driver-owner-relationships/{rid}", response_model=DriverOwnerRead)
    async def update_dor(rid: str, payload: DriverOwnerUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[DOR_COLL].find_one({"id": rid}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # If flipping to is_current=True, close any other current for the same driver
        if updates.get("is_current") is True:
            await svc.close_current_owner_for_driver(
                existing["driver_id"], updates.get("start_date") or _today(), current.get("email")
            )
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[DOR_COLL].update_one({"id": rid}, {"$set": updates})
        return await db[DOR_COLL].find_one({"id": rid}, {"_id": 0})

    @router.delete("/driver-owner-relationships/{rid}")
    async def archive_dor(rid: str, current=Depends(get_current_user)):
        _require_archive(current)
        res = await db[DOR_COLL].update_one(
            {"id": rid},
            {
                "$set": {
                    "is_archived": True,
                    "is_current": False,
                    "end_date": _today(),
                    "updated_at": _iso(),
                    "updated_by": current.get("email"),
                }
            },
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"status": "archived", "id": rid}

    # ----------------- DRIVER-VEHICLE -----------------
    @router.get("/driver-vehicle-assignments")
    async def list_dva(
        driver_id: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_primary: Optional[bool] = None,
        display_on_dispatch: Optional[bool] = None,
        include_archived: bool = False,
        current=Depends(get_current_user),
    ):
        q: Dict[str, Any] = {}
        if driver_id:
            q["driver_id"] = driver_id
        if vehicle_id:
            q["vehicle_id"] = vehicle_id
        if is_active is not None:
            q["is_active"] = is_active
        if is_primary is not None:
            q["is_primary"] = is_primary
        if display_on_dispatch is not None:
            q["display_on_dispatch"] = display_on_dispatch
        if not include_archived:
            q["is_archived"] = {"$ne": True}
        return await db[DVA_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)

    @router.get("/driver-vehicle-assignments/{aid}", response_model=DriverVehicleRead)
    async def get_dva(aid: str, current=Depends(get_current_user)):
        doc = await db[DVA_COLL].find_one({"id": aid}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return doc

    @router.post("/driver-vehicle-assignments", response_model=DriverVehicleRead)
    async def create_dva(payload: DriverVehicleCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_driver_vehicle(payload, current.get("email"))

    @router.post("/driver-vehicle-assignments/reassign", response_model=DriverVehicleRead)
    async def reassign_dva(body: VehicleReassignBody, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.reassign_vehicle(body, current.get("email"))

    @router.put("/driver-vehicle-assignments/{aid}", response_model=DriverVehicleRead)
    async def update_dva(aid: str, payload: DriverVehicleUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[DVA_COLL].find_one({"id": aid}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # If flipping to active+primary, close conflicts on driver/vehicle
        if updates.get("is_active") is True and (updates.get("is_primary", existing.get("is_primary"))):
            when = updates.get("start_date") or existing.get("start_date") or _today()
            actor = current.get("email")
            # exclude self from closure
            await db[DVA_COLL].update_many(
                {"vehicle_id": existing["vehicle_id"], "id": {"$ne": aid}, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}},
                {"$set": {"is_active": False, "end_date": when, "updated_at": _iso(), "updated_by": actor}},
            )
            await db[DVA_COLL].update_many(
                {"driver_id": existing["driver_id"], "id": {"$ne": aid}, "is_active": True, "is_primary": True, "is_archived": {"$ne": True}},
                {"$set": {"is_active": False, "end_date": when, "updated_at": _iso(), "updated_by": actor}},
            )
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[DVA_COLL].update_one({"id": aid}, {"$set": updates})
        return await db[DVA_COLL].find_one({"id": aid}, {"_id": 0})

    @router.delete("/driver-vehicle-assignments/{aid}")
    async def archive_dva(aid: str, current=Depends(get_current_user)):
        _require_archive(current)
        res = await db[DVA_COLL].update_one(
            {"id": aid},
            {
                "$set": {
                    "is_archived": True,
                    "is_active": False,
                    "end_date": _today(),
                    "updated_at": _iso(),
                    "updated_by": current.get("email"),
                }
            },
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Not found")
        return {"status": "archived", "id": aid}

    # ----------------- DRIVER-EQUIPMENT -----------------
    @router.get("/driver-equipment-assignments")
    async def list_dea(
        driver_id: Optional[str] = None,
        equipment_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        include_archived: bool = False,
        current=Depends(get_current_user),
    ):
        q: Dict[str, Any] = {}
        if driver_id:
            q["driver_id"] = driver_id
        if equipment_id:
            q["equipment_id"] = equipment_id
        if is_active is not None:
            q["is_active"] = is_active
        if not include_archived:
            q["is_archived"] = {"$ne": True}
        return await db[DEA_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)

    @router.get("/driver-equipment-assignments/{aid}", response_model=DriverEquipmentRead)
    async def get_dea(aid: str, current=Depends(get_current_user)):
        doc = await db[DEA_COLL].find_one({"id": aid}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
        return doc

    @router.post("/driver-equipment-assignments", response_model=DriverEquipmentRead)
    async def create_dea(payload: DriverEquipmentCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_driver_equipment(payload, current.get("email"), allow_conflict_close=False)

    @router.post("/driver-equipment-assignments/reassign", response_model=DriverEquipmentRead)
    async def reassign_dea(body: EquipmentReassignBody, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.reassign_equipment(body, current.get("email"))

    @router.put("/driver-equipment-assignments/{aid}", response_model=DriverEquipmentRead)
    async def update_dea(aid: str, payload: DriverEquipmentUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[DEA_COLL].find_one({"id": aid}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # If flipping to active=True, must not conflict
        if updates.get("is_active") is True:
            other = await db[DEA_COLL].find_one(
                {
                    "equipment_id": existing["equipment_id"],
                    "id": {"$ne": aid},
                    "is_active": True,
                    "is_archived": {"$ne": True},
                },
                {"_id": 0, "id": 1},
            )
            if other:
                raise HTTPException(status_code=409, detail="Equipment already actively assigned elsewhere")
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[DEA_COLL].update_one({"id": aid}, {"$set": updates})
        # Sync status
        await svc.sync_equipment_status_after_change(existing["equipment_id"], current.get("email"))
        return await db[DEA_COLL].find_one({"id": aid}, {"_id": 0})

    @router.delete("/driver-equipment-assignments/{aid}")
    async def archive_dea(aid: str, current=Depends(get_current_user)):
        _require_archive(current)
        existing = await db[DEA_COLL].find_one({"id": aid}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        await db[DEA_COLL].update_one(
            {"id": aid},
            {
                "$set": {
                    "is_archived": True,
                    "is_active": False,
                    "end_date": _today(),
                    "updated_at": _iso(),
                    "updated_by": current.get("email"),
                }
            },
        )
        await svc.sync_equipment_status_after_change(existing["equipment_id"], current.get("email"))
        return {"status": "archived", "id": aid}

    return router
