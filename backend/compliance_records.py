"""
EB-04 Canonical Compliance Foundation.

Seven canonical compliance-record collections that monitor the master records
established by EB-02 (Drivers, Owners, Vehicles, Equipment). Compliance records
never own authoritative identity — they carry immutable UUID ids and reference
the master record ids only.

Collections created here:
    - driver_licences
    - vehicle_registrations
    - vehicle_insurance_policies
    - vehicle_inspections
    - vehicle_defects
    - vehicle_maintenance_tasks
    - equipment_compliance_records

The service layer below implements the Worst-Status-Wins summary engine and
enforces the one-active-primary / one-current business rules per master record.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from registers import (
    DRIVERS_COLL,
    EQUIPMENT_COLL,
    VEHICLES_COLL,
    EquipmentStatus,
)

logger = logging.getLogger("dcc.compliance")

# ---------------------------------------------------------------- collections
LICENCES_COLL = "driver_licences"
REGISTRATIONS_COLL = "vehicle_registrations"
INSURANCE_COLL = "vehicle_insurance_policies"
INSPECTIONS_COLL = "vehicle_inspections"
DEFECTS_COLL = "vehicle_defects"
MAINTENANCE_COLL = "vehicle_maintenance_tasks"
EQUIPMENT_COMPLIANCE_COLL = "equipment_compliance_records"

SEED_TAG = "seed-eb04"

# Warning window — configurable via env, default 30 days
WARNING_WINDOW_DAYS = int(os.environ.get("COMPLIANCE_WARNING_DAYS", "30"))
# EB-R02 · Urgent tier — configurable via env, default 7 days.
# ONE canonical source. Downstream consumers must NOT hardcode this.
URGENT_WINDOW_DAYS = int(os.environ.get("COMPLIANCE_URGENT_DAYS", "7"))


# ---------------------------------------------------------------- enums
class ComplianceStatus(str, Enum):
    Compliant = "Compliant"
    DueSoon = "Due Soon"
    Urgent = "Urgent"
    Expired = "Expired"
    Missing = "Missing"
    Incomplete = "Incomplete"
    UnderReview = "Under Review"
    NotApplicable = "Not Applicable"
    Archived = "Archived"


class VerificationStatus(str, Enum):
    Unverified = "Unverified"
    Pending = "Pending"
    Verified = "Verified"
    Rejected = "Rejected"


class InspectionType(str, Enum):
    Roadworthy = "Roadworthy"
    Scheduled = "Scheduled Inspection"
    PreStart = "Pre-Start Inspection"
    Annual = "Annual Inspection"
    Other = "Other"


class InspectionResult(str, Enum):
    Pass = "Pass"
    PassWithObservations = "Pass with Observations"
    Fail = "Fail"
    Pending = "Pending"


class DefectSeverity(str, Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Critical = "Critical"


class DefectStatus(str, Enum):
    Open = "Open"
    UnderReview = "Under Review"
    RepairScheduled = "Repair Scheduled"
    Rectified = "Rectified"
    Closed = "Closed"
    Archived = "Archived"


class MaintenanceStatus(str, Enum):
    Scheduled = "Scheduled"
    DueSoon = "Due Soon"
    Overdue = "Overdue"
    InProgress = "In Progress"
    Completed = "Completed"
    Cancelled = "Cancelled"
    Archived = "Archived"


class EquipmentComplianceType(str, Enum):
    Registration = "Registration"
    Inspection = "Inspection"
    Certification = "Certification"
    Insurance = "Insurance"
    Maintenance = "Maintenance"
    Other = "Other"


# Worst-Status-Wins severity: higher = worse.
# Archived is deliberately excluded from active severity calculations.
STATUS_SEVERITY: Dict[str, int] = {
    ComplianceStatus.NotApplicable.value: 0,
    ComplianceStatus.Compliant.value: 10,
    ComplianceStatus.DueSoon.value: 20,
    ComplianceStatus.UnderReview.value: 25,
    ComplianceStatus.Urgent.value: 28,
    ComplianceStatus.Incomplete.value: 30,
    ComplianceStatus.Missing.value: 40,
    ComplianceStatus.Expired.value: 50,
}


def _worst(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the worst (highest severity) component or a Compliant placeholder."""
    active = [c for c in components if c.get("status") != ComplianceStatus.Archived.value]
    if not active:
        return {"status": ComplianceStatus.Compliant.value, "severity": STATUS_SEVERITY[ComplianceStatus.Compliant.value]}
    return max(active, key=lambda c: STATUS_SEVERITY.get(c.get("status", ""), 0))


# ---------------------------------------------------------------- helpers
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _classify_expiry(
    expiry: Optional[str],
    warning_days: int = WARNING_WINDOW_DAYS,
    urgent_days: int = URGENT_WINDOW_DAYS,
) -> str:
    """EB-R02 canonical expiry classifier for Licence / Registration /
    Insurance. Missing or unparsable expiry ALWAYS returns Incomplete
    (never Compliant). Uses calendar-day logic.
    """
    d = _parse_date(expiry)
    if not d:
        return ComplianceStatus.Incomplete.value
    delta = (d.date() - datetime.now(timezone.utc).date()).days
    if delta < 0:
        return ComplianceStatus.Expired.value
    if delta <= urgent_days:
        return ComplianceStatus.Urgent.value
    if delta <= warning_days:
        return ComplianceStatus.DueSoon.value
    return ComplianceStatus.Compliant.value


def _days_remaining(expiry: Optional[str]) -> Optional[int]:
    """Return integer calendar days until expiry, or None if unparsable."""
    d = _parse_date(expiry)
    if not d:
        return None
    return (d.date() - datetime.now(timezone.utc).date()).days


# EB-R02 · Vehicle Compliance component translation.
# Expiry-domain labels (Current/DueSoon/Urgent/Expired) must NOT be
# used as the top-level Vehicle Compliance component outcome. Blueprint
# semantics: Compliant / Conditions / Non-Compliant / Not Applicable.
_VC_COMPONENT_MAP: Dict[str, str] = {
    ComplianceStatus.Compliant.value: "Compliant",
    ComplianceStatus.UnderReview.value: "Compliant",
    ComplianceStatus.DueSoon.value: "Conditions",
    ComplianceStatus.Urgent.value: "Conditions",
    ComplianceStatus.Expired.value: "Non-Compliant",
    ComplianceStatus.Missing.value: "Non-Compliant",
    ComplianceStatus.Incomplete.value: "Non-Compliant",
    ComplianceStatus.NotApplicable.value: "Not Applicable",
}


def _to_vc_component(status: Optional[str]) -> str:
    """Translate a canonical component compliance status into the
    Blueprint Vehicle Compliance semantics."""
    return _VC_COMPONENT_MAP.get(status or "", "Non-Compliant")


def _worst_vc(component_statuses: List[str]) -> str:
    """Vehicle Compliance Worst Status Wins.
    Order: Non-Compliant > Conditions > Compliant. Not Applicable is
    excluded from the comparison. If all are Not Applicable, returns
    Not Applicable."""
    rank = {"Compliant": 1, "Conditions": 2, "Non-Compliant": 3}
    ranked = [s for s in component_statuses if s and s != "Not Applicable"]
    if not ranked:
        return "Not Applicable" if component_statuses else "Not Applicable"
    return max(ranked, key=lambda s: rank.get(s, 0))


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


# ---------------------------------------------------------------- shared audit
class _Audit(BaseModel):
    id: str
    is_archived: bool = False
    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    _source: Optional[str] = None
    legacy_record_id: Optional[str] = None
    evidence_document_id: Optional[str] = None


# ---------------------------------------------------------------- Driver Licence
class DriverLicenceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    driver_id: str
    licence_number: str
    state: Optional[str] = None
    licence_class: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: ComplianceStatus = ComplianceStatus.Compliant
    is_primary: bool = True
    verification_status: VerificationStatus = VerificationStatus.Unverified
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    legacy_record_id: Optional[str] = None


class DriverLicenceCreate(DriverLicenceBase):
    pass


class DriverLicenceUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    licence_number: Optional[str] = None
    state: Optional[str] = None
    licence_class: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: Optional[ComplianceStatus] = None
    is_primary: Optional[bool] = None
    verification_status: Optional[VerificationStatus] = None
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class DriverLicenceRead(DriverLicenceBase, _Audit):
    pass


# ---------------------------------------------------------------- Vehicle Registration
class VehicleRegistrationBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vehicle_id: str
    registration_number_snapshot: Optional[str] = None
    state: Optional[str] = None
    registration_class: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: ComplianceStatus = ComplianceStatus.Compliant
    is_current: bool = True
    verification_status: VerificationStatus = VerificationStatus.Unverified
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    legacy_record_id: Optional[str] = None


class VehicleRegistrationCreate(VehicleRegistrationBase):
    pass


class VehicleRegistrationUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    registration_number_snapshot: Optional[str] = None
    state: Optional[str] = None
    registration_class: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: Optional[ComplianceStatus] = None
    is_current: Optional[bool] = None
    verification_status: Optional[VerificationStatus] = None
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class VehicleRegistrationRead(VehicleRegistrationBase, _Audit):
    pass


# ---------------------------------------------------------------- Vehicle Insurance
class VehicleInsuranceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vehicle_id: str
    policy_number: str
    provider: Optional[str] = None
    cover_type: str = "Comprehensive"
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: ComplianceStatus = ComplianceStatus.Compliant
    is_current: bool = True
    verification_status: VerificationStatus = VerificationStatus.Unverified
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    legacy_record_id: Optional[str] = None


class VehicleInsuranceCreate(VehicleInsuranceBase):
    pass


class VehicleInsuranceUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    policy_number: Optional[str] = None
    provider: Optional[str] = None
    cover_type: Optional[str] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: Optional[ComplianceStatus] = None
    is_current: Optional[bool] = None
    verification_status: Optional[VerificationStatus] = None
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class VehicleInsuranceRead(VehicleInsuranceBase, _Audit):
    pass


# ---------------------------------------------------------------- Vehicle Inspection
class VehicleInspectionBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vehicle_id: str
    inspection_type: InspectionType = InspectionType.Scheduled
    inspection_date: Optional[str] = None
    next_inspection_due: Optional[str] = None
    result: InspectionResult = InspectionResult.Pending
    status: ComplianceStatus = ComplianceStatus.UnderReview
    inspector_name: Optional[str] = None
    odometer: Optional[float] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    legacy_record_id: Optional[str] = None


class VehicleInspectionCreate(VehicleInspectionBase):
    pass


class VehicleInspectionUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    inspection_type: Optional[InspectionType] = None
    inspection_date: Optional[str] = None
    next_inspection_due: Optional[str] = None
    result: Optional[InspectionResult] = None
    status: Optional[ComplianceStatus] = None
    inspector_name: Optional[str] = None
    odometer: Optional[float] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class VehicleInspectionRead(VehicleInspectionBase, _Audit):
    pass


# ---------------------------------------------------------------- Vehicle Defect
class VehicleDefectBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vehicle_id: str
    inspection_id: Optional[str] = None
    defect_number: Optional[str] = None
    reported_date: Optional[str] = None
    severity: DefectSeverity = DefectSeverity.Low
    description: str
    status: DefectStatus = DefectStatus.Open
    rectification_required: bool = True
    rectified_date: Optional[str] = None
    rectified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    legacy_record_id: Optional[str] = None


class VehicleDefectCreate(VehicleDefectBase):
    pass


class VehicleDefectUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    inspection_id: Optional[str] = None
    defect_number: Optional[str] = None
    reported_date: Optional[str] = None
    severity: Optional[DefectSeverity] = None
    description: Optional[str] = None
    status: Optional[DefectStatus] = None
    rectification_required: Optional[bool] = None
    rectified_date: Optional[str] = None
    rectified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class VehicleDefectRead(VehicleDefectBase, _Audit):
    pass


# ---------------------------------------------------------------- Maintenance Task
class MaintenanceTaskBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vehicle_id: str
    defect_id: Optional[str] = None
    task_type: str
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    completed_date: Optional[str] = None
    status: MaintenanceStatus = MaintenanceStatus.Scheduled
    provider: Optional[str] = None
    odometer_due: Optional[float] = None
    odometer_completed: Optional[float] = None
    cost: Optional[float] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    legacy_record_id: Optional[str] = None


class MaintenanceTaskCreate(MaintenanceTaskBase):
    pass


class MaintenanceTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    defect_id: Optional[str] = None
    task_type: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    completed_date: Optional[str] = None
    status: Optional[MaintenanceStatus] = None
    provider: Optional[str] = None
    odometer_due: Optional[float] = None
    odometer_completed: Optional[float] = None
    cost: Optional[float] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class MaintenanceTaskRead(MaintenanceTaskBase, _Audit):
    pass


# ---------------------------------------------------------------- Equipment Compliance
class EquipmentComplianceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    equipment_id: str
    compliance_type: EquipmentComplianceType = EquipmentComplianceType.Certification
    reference_number: Optional[str] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: ComplianceStatus = ComplianceStatus.Compliant
    is_current: bool = True
    is_mandatory: bool = True
    verification_status: VerificationStatus = VerificationStatus.Unverified
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    legacy_record_id: Optional[str] = None


class EquipmentComplianceCreate(EquipmentComplianceBase):
    pass


class EquipmentComplianceUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    compliance_type: Optional[EquipmentComplianceType] = None
    reference_number: Optional[str] = None
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: Optional[ComplianceStatus] = None
    is_current: Optional[bool] = None
    is_mandatory: Optional[bool] = None
    verification_status: Optional[VerificationStatus] = None
    verified_at: Optional[str] = None
    verified_by: Optional[str] = None
    evidence_document_id: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None


class EquipmentComplianceRead(EquipmentComplianceBase, _Audit):
    pass


# ---------------------------------------------------------------- Service layer
class _ComplianceService:
    """Business logic layer. Callable from both HTTP routes and startup reconciliation."""

    def __init__(self, db):
        self.db = db

    # -------- Driver Licence --------
    async def close_current_primary_licence(self, driver_id: str, actor: Optional[str]):
        await self.db[LICENCES_COLL].update_many(
            {"driver_id": driver_id, "is_primary": True, "is_archived": {"$ne": True}},
            {"$set": {"is_primary": False, "updated_at": _iso(), "updated_by": actor}},
        )

    async def create_licence(self, payload: DriverLicenceCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, DRIVERS_COLL, payload.driver_id, "Driver")
        now = _iso()
        doc = payload.model_dump(mode="json")
        # Auto-calc status from expiry
        doc["status"] = _classify_expiry(doc.get("expiry_date"))
        if doc.get("is_primary"):
            await self.close_current_primary_licence(payload.driver_id, actor)
        doc.update({
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        })
        await self.db[LICENCES_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # -------- Vehicle Registration --------
    async def close_current_registration(self, vehicle_id: str, actor: Optional[str]):
        await self.db[REGISTRATIONS_COLL].update_many(
            {"vehicle_id": vehicle_id, "is_current": True, "is_archived": {"$ne": True}},
            {"$set": {"is_current": False, "updated_at": _iso(), "updated_by": actor}},
        )

    async def create_registration(self, payload: VehicleRegistrationCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, VEHICLES_COLL, payload.vehicle_id, "Vehicle")
        now = _iso()
        doc = payload.model_dump(mode="json")
        doc["status"] = _classify_expiry(doc.get("expiry_date"))
        if doc.get("is_current"):
            await self.close_current_registration(payload.vehicle_id, actor)
        doc.update({
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        })
        await self.db[REGISTRATIONS_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # -------- Vehicle Insurance --------
    async def close_current_insurance(self, vehicle_id: str, cover_type: str, actor: Optional[str]):
        await self.db[INSURANCE_COLL].update_many(
            {
                "vehicle_id": vehicle_id,
                "cover_type": cover_type,
                "is_current": True,
                "is_archived": {"$ne": True},
            },
            {"$set": {"is_current": False, "updated_at": _iso(), "updated_by": actor}},
        )

    async def create_insurance(self, payload: VehicleInsuranceCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, VEHICLES_COLL, payload.vehicle_id, "Vehicle")
        now = _iso()
        doc = payload.model_dump(mode="json")
        doc["status"] = _classify_expiry(doc.get("expiry_date"))
        if doc.get("is_current"):
            await self.close_current_insurance(payload.vehicle_id, doc.get("cover_type"), actor)
        doc.update({
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        })
        await self.db[INSURANCE_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # -------- Inspection --------
    async def create_inspection(self, payload: VehicleInspectionCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, VEHICLES_COLL, payload.vehicle_id, "Vehicle")
        now = _iso()
        doc = payload.model_dump(mode="json")
        result = doc.get("result")
        if result == InspectionResult.Fail.value:
            doc["status"] = ComplianceStatus.Expired.value
        elif result in (InspectionResult.Pass.value, InspectionResult.PassWithObservations.value):
            doc["status"] = _classify_expiry(doc.get("next_inspection_due"))
        else:
            doc["status"] = ComplianceStatus.UnderReview.value
        doc.update({
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        })
        await self.db[INSPECTIONS_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # -------- Defect --------
    async def create_defect(self, payload: VehicleDefectCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, VEHICLES_COLL, payload.vehicle_id, "Vehicle")
        if payload.inspection_id:
            await _must_exist(self.db, INSPECTIONS_COLL, payload.inspection_id, "Inspection")
        now = _iso()
        doc = payload.model_dump(mode="json")
        doc.update({
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        })
        await self.db[DEFECTS_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # -------- Maintenance --------
    async def create_maintenance(self, payload: MaintenanceTaskCreate, actor: Optional[str]) -> Dict[str, Any]:
        await _must_exist(self.db, VEHICLES_COLL, payload.vehicle_id, "Vehicle")
        if payload.defect_id:
            await _must_exist(self.db, DEFECTS_COLL, payload.defect_id, "Defect")
        now = _iso()
        doc = payload.model_dump(mode="json")
        # Overdue check
        if doc.get("status") == MaintenanceStatus.Scheduled.value:
            sched = _parse_date(doc.get("scheduled_date"))
            if sched:
                delta = (sched.date() - datetime.now(timezone.utc).date()).days
                if delta < 0:
                    doc["status"] = MaintenanceStatus.Overdue.value
                elif delta <= WARNING_WINDOW_DAYS:
                    doc["status"] = MaintenanceStatus.DueSoon.value
        doc.update({
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        })
        await self.db[MAINTENANCE_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # -------- Equipment Compliance --------
    async def close_current_equipment_compliance(self, equipment_id: str, compliance_type: str, actor: Optional[str]):
        await self.db[EQUIPMENT_COMPLIANCE_COLL].update_many(
            {
                "equipment_id": equipment_id,
                "compliance_type": compliance_type,
                "is_current": True,
                "is_archived": {"$ne": True},
            },
            {"$set": {"is_current": False, "updated_at": _iso(), "updated_by": actor}},
        )

    async def create_equipment_compliance(
        self, payload: EquipmentComplianceCreate, actor: Optional[str]
    ) -> Dict[str, Any]:
        await _must_exist(self.db, EQUIPMENT_COLL, payload.equipment_id, "Equipment")
        now = _iso()
        doc = payload.model_dump(mode="json")
        doc["status"] = _classify_expiry(doc.get("expiry_date"))
        if doc.get("is_current"):
            await self.close_current_equipment_compliance(
                payload.equipment_id, doc.get("compliance_type"), actor
            )
        doc.update({
            "id": str(uuid.uuid4()),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        })
        await self.db[EQUIPMENT_COMPLIANCE_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    # -------- Summary engine --------
    async def driver_summary(self, driver_id: str) -> Dict[str, Any]:
        driver = await self.db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")

        components: List[Dict[str, Any]] = []
        # Primary Licence
        primary_licence = await self.db[LICENCES_COLL].find_one(
            {"driver_id": driver_id, "is_primary": True, "is_archived": {"$ne": True}},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if not primary_licence:
            components.append({
                "component": "primary_licence",
                "label": "Primary Driver Licence",
                "status": ComplianceStatus.Missing.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Missing.value],
                "record_id": None,
                "reason": "No active primary licence on file",
            })
        else:
            status = _classify_expiry(primary_licence.get("expiry_date"))
            components.append({
                "component": "primary_licence",
                "label": "Primary Driver Licence",
                "status": status,
                "severity": STATUS_SEVERITY.get(status, 0),
                "record_id": primary_licence["id"],
                "expiry_date": primary_licence.get("expiry_date"),
                "licence_number": primary_licence.get("licence_number"),
                "reason": f"Expires {primary_licence.get('expiry_date') or 'unknown'}",
            })

        worst = _worst(components)
        return {
            "driver_id": driver_id,
            "driver_name": driver.get("full_name") or driver.get("name"),
            "overall_status": worst.get("status"),
            "severity": worst.get("severity", 0),
            "components": components,
            "worst_component": worst.get("component") if isinstance(worst, dict) and "component" in worst else None,
            "calculated_at": _iso(),
        }

    async def vehicle_summary(self, vehicle_id: str) -> Dict[str, Any]:
        vehicle = await self.db[VEHICLES_COLL].find_one({"id": vehicle_id}, {"_id": 0})
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vehicle not found")

        components: List[Dict[str, Any]] = []

        # Registration
        reg = await self.db[REGISTRATIONS_COLL].find_one(
            {"vehicle_id": vehicle_id, "is_current": True, "is_archived": {"$ne": True}},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if not reg:
            components.append({
                "component": "registration",
                "label": "Registration",
                "status": ComplianceStatus.Missing.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Missing.value],
                "record_id": None,
                "reason": "No current registration record",
            })
        else:
            s = _classify_expiry(reg.get("expiry_date"))
            components.append({
                "component": "registration",
                "label": "Registration",
                "status": s,
                "severity": STATUS_SEVERITY.get(s, 0),
                "record_id": reg["id"],
                "expiry_date": reg.get("expiry_date"),
                "reason": f"Expires {reg.get('expiry_date') or 'unknown'}",
            })

        # Insurance
        ins = await self.db[INSURANCE_COLL].find_one(
            {"vehicle_id": vehicle_id, "is_current": True, "is_archived": {"$ne": True}},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if not ins:
            components.append({
                "component": "insurance",
                "label": "Insurance",
                "status": ComplianceStatus.Missing.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Missing.value],
                "record_id": None,
                "reason": "No current insurance policy",
            })
        else:
            s = _classify_expiry(ins.get("expiry_date"))
            components.append({
                "component": "insurance",
                "label": "Insurance",
                "status": s,
                "severity": STATUS_SEVERITY.get(s, 0),
                "record_id": ins["id"],
                "expiry_date": ins.get("expiry_date"),
                "reason": f"{ins.get('provider') or 'Policy'} expires {ins.get('expiry_date') or 'unknown'}",
            })

        # Latest inspection
        insp = await self.db[INSPECTIONS_COLL].find_one(
            {"vehicle_id": vehicle_id, "is_archived": {"$ne": True}},
            {"_id": 0},
            sort=[("inspection_date", -1), ("created_at", -1)],
        )
        if not insp:
            components.append({
                "component": "inspection",
                "label": "Inspection",
                "status": ComplianceStatus.Missing.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Missing.value],
                "record_id": None,
                "reason": "No inspection on file",
            })
        else:
            if insp.get("result") == InspectionResult.Fail.value:
                s = ComplianceStatus.Expired.value
                reason = "Latest inspection failed"
            elif insp.get("result") == InspectionResult.Pending.value:
                s = ComplianceStatus.UnderReview.value
                reason = "Inspection pending"
            else:
                s = _classify_expiry(insp.get("next_inspection_due"))
                reason = f"Next due {insp.get('next_inspection_due') or 'unknown'}"
            components.append({
                "component": "inspection",
                "label": "Inspection",
                "status": s,
                "severity": STATUS_SEVERITY.get(s, 0),
                "record_id": insp["id"],
                "reason": reason,
            })

        # Open defects
        open_defects = await self.db[DEFECTS_COLL].find(
            {
                "vehicle_id": vehicle_id,
                "is_archived": {"$ne": True},
                "status": {"$in": [DefectStatus.Open.value, DefectStatus.UnderReview.value, DefectStatus.RepairScheduled.value]},
            },
            {"_id": 0, "id": 1, "severity": 1},
        ).to_list(200)
        crit = [d for d in open_defects if d.get("severity") == DefectSeverity.Critical.value]
        if crit:
            components.append({
                "component": "defects",
                "label": "Defects",
                "status": ComplianceStatus.Expired.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Expired.value],
                "record_id": crit[0]["id"],
                "reason": f"{len(crit)} critical defect(s) open",
                "count": len(open_defects),
            })
        elif open_defects:
            components.append({
                "component": "defects",
                "label": "Defects",
                "status": ComplianceStatus.DueSoon.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.DueSoon.value],
                "record_id": open_defects[0]["id"],
                "reason": f"{len(open_defects)} open defect(s)",
                "count": len(open_defects),
            })
        else:
            components.append({
                "component": "defects",
                "label": "Defects",
                "status": ComplianceStatus.Compliant.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Compliant.value],
                "record_id": None,
                "reason": "No open defects",
                "count": 0,
            })

        # Overdue maintenance
        overdue = await self.db[MAINTENANCE_COLL].count_documents(
            {
                "vehicle_id": vehicle_id,
                "is_archived": {"$ne": True},
                "status": MaintenanceStatus.Overdue.value,
            }
        )
        if overdue:
            components.append({
                "component": "maintenance",
                "label": "Maintenance",
                "status": ComplianceStatus.Expired.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Expired.value],
                "record_id": None,
                "reason": f"{overdue} overdue maintenance task(s)",
                "count": overdue,
            })
        else:
            due_soon = await self.db[MAINTENANCE_COLL].count_documents(
                {
                    "vehicle_id": vehicle_id,
                    "is_archived": {"$ne": True},
                    "status": MaintenanceStatus.DueSoon.value,
                }
            )
            if due_soon:
                components.append({
                    "component": "maintenance",
                    "label": "Maintenance",
                    "status": ComplianceStatus.DueSoon.value,
                    "severity": STATUS_SEVERITY[ComplianceStatus.DueSoon.value],
                    "record_id": None,
                    "reason": f"{due_soon} due-soon maintenance task(s)",
                    "count": due_soon,
                })
            else:
                components.append({
                    "component": "maintenance",
                    "label": "Maintenance",
                    "status": ComplianceStatus.Compliant.value,
                    "severity": STATUS_SEVERITY[ComplianceStatus.Compliant.value],
                    "record_id": None,
                    "reason": "No overdue maintenance",
                    "count": 0,
                })

        worst = _worst(components)
        worst_component = next(
            (c.get("component") for c in components if c.get("status") == worst.get("status") and c.get("severity") == worst.get("severity")),
            None,
        )
        # EB-R02 · Vehicle Compliance Blueprint semantics
        # (Compliant / Conditions / Non-Compliant / Not Applicable).
        # Component-level VC output uses _to_vc_component; overall uses
        # canonical WSW over VC-translated components.
        vc_components = [_to_vc_component(c.get("status")) for c in components]
        overall_vc_status = _worst_vc(vc_components)
        # Prime Mover: proven from canonical vehicle_type. Tray and
        # Trailer are NOT YET AVAILABLE as canonical component outputs
        # (no canonical role marker exists).
        prime_mover_status = overall_vc_status if (vehicle.get("vehicle_type") == "Prime Mover") else "Not Applicable"
        return {
            "vehicle_id": vehicle_id,
            "registration_number": vehicle.get("registration_number"),
            "vehicle_type": vehicle.get("vehicle_type"),
            "overall_status": worst.get("status"),
            "severity": worst.get("severity", 0),
            "components": components,
            "worst_component": worst_component,
            "overall_vehicle_compliance_status": overall_vc_status,
            "prime_mover_status": prime_mover_status,
            "tray_status": "Not yet available",
            "trailer_status": "Not yet available",
            "calculated_at": _iso(),
        }

    async def equipment_summary(self, equipment_id: str) -> Dict[str, Any]:
        eq = await self.db[EQUIPMENT_COLL].find_one({"id": equipment_id}, {"_id": 0})
        if not eq:
            raise HTTPException(status_code=404, detail="Equipment not found")

        records = await self.db[EQUIPMENT_COMPLIANCE_COLL].find(
            {"equipment_id": equipment_id, "is_current": True, "is_archived": {"$ne": True}},
            {"_id": 0},
        ).to_list(200)

        components: List[Dict[str, Any]] = []
        if not records:
            components.append({
                "component": "equipment_compliance",
                "label": "Equipment Compliance",
                "status": ComplianceStatus.Missing.value,
                "severity": STATUS_SEVERITY[ComplianceStatus.Missing.value],
                "record_id": None,
                "reason": "No compliance records on file",
            })
        else:
            for r in records:
                s = _classify_expiry(r.get("expiry_date"))
                if r.get("is_mandatory") is False and s in (
                    ComplianceStatus.Missing.value,
                    ComplianceStatus.Incomplete.value,
                ):
                    s = ComplianceStatus.NotApplicable.value
                components.append({
                    "component": f"eq_{r.get('compliance_type', 'other')}",
                    "label": r.get("compliance_type", "Compliance"),
                    "status": s,
                    "severity": STATUS_SEVERITY.get(s, 0),
                    "record_id": r["id"],
                    "expiry_date": r.get("expiry_date"),
                    "reason": f"{r.get('compliance_type')} expires {r.get('expiry_date') or 'unknown'}",
                })

        worst = _worst(components)
        worst_component = next(
            (c.get("component") for c in components if c.get("status") == worst.get("status") and c.get("severity") == worst.get("severity")),
            None,
        )
        return {
            "equipment_id": equipment_id,
            "equipment_number": eq.get("equipment_number"),
            "overall_status": worst.get("status"),
            "severity": worst.get("severity", 0),
            "components": components,
            "worst_component": worst_component,
            "calculated_at": _iso(),
        }


# ---------------------------------------------------------------- indexes
async def ensure_indexes(db):
    for c in (
        LICENCES_COLL,
        REGISTRATIONS_COLL,
        INSURANCE_COLL,
        INSPECTIONS_COLL,
        DEFECTS_COLL,
        MAINTENANCE_COLL,
        EQUIPMENT_COMPLIANCE_COLL,
    ):
        await db[c].create_index("id", unique=True)
    await db[LICENCES_COLL].create_index("driver_id")
    await db[REGISTRATIONS_COLL].create_index("vehicle_id")
    await db[INSURANCE_COLL].create_index("vehicle_id")
    await db[INSPECTIONS_COLL].create_index("vehicle_id")
    await db[DEFECTS_COLL].create_index("vehicle_id")
    await db[MAINTENANCE_COLL].create_index("vehicle_id")
    await db[EQUIPMENT_COMPLIANCE_COLL].create_index("equipment_id")


# ---------------------------------------------------------------- seed
async def seed_compliance(db):
    """Development-only idempotent seed tagged `_source=seed-eb04`. Uses EB-02 masters."""
    svc = _ComplianceService(db)
    now = _iso()

    drivers = await db[DRIVERS_COLL].find({}, {"_id": 0, "id": 1, "full_name": 1, "name": 1}).to_list(50)
    vehicles = await db[VEHICLES_COLL].find({"_source": "seed-eb02"}, {"_id": 0, "id": 1, "registration_number": 1}).to_list(50)
    equipment = await db[EQUIPMENT_COLL].find({"_source": "seed-eb02"}, {"_id": 0, "id": 1, "equipment_number": 1}).to_list(50)

    if len(drivers) < 3 or len(vehicles) < 3 or len(equipment) < 3:
        logger.info("EB-04 seed skipped: insufficient EB-02 masters.")
        return

    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    future = (today + timedelta(days=180)).isoformat()
    due_soon = (today + timedelta(days=15)).isoformat()
    expired = (today - timedelta(days=10)).isoformat()

    # --- Driver Licences (3 primary: 1 compliant, 1 due soon, 1 expired)
    licence_specs = [
        (drivers[0], "LIC-DRV-001", future, ComplianceStatus.Compliant.value),
        (drivers[1], "LIC-DRV-002", due_soon, ComplianceStatus.DueSoon.value),
        (drivers[2], "LIC-DRV-003", expired, ComplianceStatus.Expired.value),
    ]
    for drv, num, exp, _status in licence_specs:
        existing = await db[LICENCES_COLL].find_one({"driver_id": drv["id"], "_source": SEED_TAG})
        if existing:
            continue
        await db[LICENCES_COLL].insert_one({
            "id": str(uuid.uuid4()),
            "driver_id": drv["id"],
            "licence_number": num,
            "state": "NSW",
            "licence_class": "HR",
            "issue_date": "2022-01-01",
            "expiry_date": exp,
            "status": _classify_expiry(exp),
            "is_primary": True,
            "verification_status": VerificationStatus.Verified.value,
            "verified_at": now,
            "verified_by": "system-seed",
            "notes": "seed licence",
            "is_archived": False,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": SEED_TAG,
        })

    # --- Vehicle Registrations (3)
    reg_specs = [
        (vehicles[0], "TEST-V01", future),
        (vehicles[1], "TEST-V02", due_soon),
        (vehicles[2], "TEST-V03", expired),
    ]
    for veh, snap, exp in reg_specs:
        existing = await db[REGISTRATIONS_COLL].find_one({"vehicle_id": veh["id"], "_source": SEED_TAG})
        if existing:
            continue
        await db[REGISTRATIONS_COLL].insert_one({
            "id": str(uuid.uuid4()),
            "vehicle_id": veh["id"],
            "registration_number_snapshot": snap,
            "state": "NSW",
            "registration_class": "Heavy",
            "issue_date": "2025-01-01",
            "expiry_date": exp,
            "status": _classify_expiry(exp),
            "is_current": True,
            "verification_status": VerificationStatus.Verified.value,
            "notes": "seed registration",
            "is_archived": False,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": SEED_TAG,
        })

    # --- Vehicle Insurance (3)
    ins_specs = [
        (vehicles[0], "POL-887766", "NTI", future),
        (vehicles[1], "POL-998877", "Allianz", due_soon),
        (vehicles[2], "POL-112233", "QBE", future),
    ]
    for veh, num, prov, exp in ins_specs:
        existing = await db[INSURANCE_COLL].find_one({"vehicle_id": veh["id"], "_source": SEED_TAG})
        if existing:
            continue
        await db[INSURANCE_COLL].insert_one({
            "id": str(uuid.uuid4()),
            "vehicle_id": veh["id"],
            "policy_number": num,
            "provider": prov,
            "cover_type": "Comprehensive",
            "effective_date": "2025-01-01",
            "expiry_date": exp,
            "status": _classify_expiry(exp),
            "is_current": True,
            "verification_status": VerificationStatus.Verified.value,
            "notes": "seed insurance",
            "is_archived": False,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": SEED_TAG,
        })

    # --- Inspections (3)
    insp_specs = [
        (vehicles[0], InspectionResult.Pass.value, future),
        (vehicles[1], InspectionResult.PassWithObservations.value, due_soon),
        (vehicles[2], InspectionResult.Fail.value, None),
    ]
    for veh, result, nxt in insp_specs:
        existing = await db[INSPECTIONS_COLL].find_one({"vehicle_id": veh["id"], "_source": SEED_TAG})
        if existing:
            continue
        if result == InspectionResult.Fail.value:
            status = ComplianceStatus.Expired.value
        else:
            status = _classify_expiry(nxt)
        await db[INSPECTIONS_COLL].insert_one({
            "id": str(uuid.uuid4()),
            "vehicle_id": veh["id"],
            "inspection_type": InspectionType.Scheduled.value,
            "inspection_date": today.isoformat(),
            "next_inspection_due": nxt,
            "result": result,
            "status": status,
            "inspector_name": "Seed Inspector",
            "notes": "seed inspection",
            "is_archived": False,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": SEED_TAG,
        })

    # --- Defects (2: one critical open, one closed rectified)
    defect_specs = [
        (vehicles[2], DefectSeverity.Critical.value, DefectStatus.Open.value, "Air leak in rear brake line"),
        (vehicles[0], DefectSeverity.Low.value, DefectStatus.Rectified.value, "Cracked side mirror"),
    ]
    for i, (veh, sev, st, desc) in enumerate(defect_specs):
        existing = await db[DEFECTS_COLL].find_one({"vehicle_id": veh["id"], "description": desc, "_source": SEED_TAG})
        if existing:
            continue
        await db[DEFECTS_COLL].insert_one({
            "id": str(uuid.uuid4()),
            "vehicle_id": veh["id"],
            "defect_number": f"DEF-SEED-{i+1:03d}",
            "reported_date": today.isoformat(),
            "severity": sev,
            "description": desc,
            "status": st,
            "rectification_required": st != DefectStatus.Rectified.value,
            "rectified_date": today.isoformat() if st == DefectStatus.Rectified.value else None,
            "rectified_by": "seed-mech" if st == DefectStatus.Rectified.value else None,
            "notes": "seed defect",
            "is_archived": False,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": SEED_TAG,
        })

    # --- Maintenance (3: scheduled, overdue, completed)
    maint_specs = [
        (vehicles[0], "Scheduled Service", (today + timedelta(days=45)).isoformat(), None, MaintenanceStatus.Scheduled.value),
        (vehicles[1], "Brake Service", (today - timedelta(days=5)).isoformat(), None, MaintenanceStatus.Overdue.value),
        (vehicles[2], "Oil Change", (today - timedelta(days=30)).isoformat(), (today - timedelta(days=28)).isoformat(), MaintenanceStatus.Completed.value),
    ]
    for i, (veh, task, sched, comp, st) in enumerate(maint_specs):
        existing = await db[MAINTENANCE_COLL].find_one({"vehicle_id": veh["id"], "task_type": task, "_source": SEED_TAG})
        if existing:
            continue
        await db[MAINTENANCE_COLL].insert_one({
            "id": str(uuid.uuid4()),
            "vehicle_id": veh["id"],
            "task_type": task,
            "description": f"Seed {task}",
            "scheduled_date": sched,
            "completed_date": comp,
            "status": st,
            "provider": "ACE Workshop",
            "notes": "seed maintenance",
            "is_archived": False,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": SEED_TAG,
        })

    # --- Equipment Compliance (4)
    eq_specs = [
        (equipment[0], EquipmentComplianceType.Certification.value, "CERT-001", future),
        (equipment[1], EquipmentComplianceType.Inspection.value, "INSP-001", due_soon),
        (equipment[2], EquipmentComplianceType.Registration.value, "REG-001", expired),
        (equipment[0], EquipmentComplianceType.Insurance.value, "INS-001", future),
    ]
    for eq, ctype, ref, exp in eq_specs:
        existing = await db[EQUIPMENT_COMPLIANCE_COLL].find_one(
            {"equipment_id": eq["id"], "compliance_type": ctype, "_source": SEED_TAG}
        )
        if existing:
            continue
        await db[EQUIPMENT_COMPLIANCE_COLL].insert_one({
            "id": str(uuid.uuid4()),
            "equipment_id": eq["id"],
            "compliance_type": ctype,
            "reference_number": ref,
            "effective_date": "2025-01-01",
            "expiry_date": exp,
            "status": _classify_expiry(exp),
            "is_current": True,
            "is_mandatory": True,
            "verification_status": VerificationStatus.Verified.value,
            "notes": "seed equipment compliance",
            "is_archived": False,
            "created_at": now, "updated_at": now,
            "created_by": "system-seed", "updated_by": "system-seed",
            "_source": SEED_TAG,
        })


# ---------------------------------------------------------------- reconciliation
async def startup_reconciliation(db):
    """Idempotent: recompute status on all active records so seed edge-cases self-heal."""
    for coll, expiry_field in (
        (LICENCES_COLL, "expiry_date"),
        (REGISTRATIONS_COLL, "expiry_date"),
        (INSURANCE_COLL, "expiry_date"),
        (EQUIPMENT_COMPLIANCE_COLL, "expiry_date"),
    ):
        async for doc in db[coll].find({"is_archived": {"$ne": True}}, {"_id": 0, "id": 1, expiry_field: 1, "status": 1}):
            new_status = _classify_expiry(doc.get(expiry_field))
            if doc.get("status") != new_status:
                await db[coll].update_one(
                    {"id": doc["id"]},
                    {"$set": {"status": new_status, "updated_at": _iso(), "updated_by": "system-reconciliation"}},
                )

    # Overdue check for scheduled maintenance
    today = datetime.now(timezone.utc).date()
    async for m in db[MAINTENANCE_COLL].find(
        {"is_archived": {"$ne": True}, "status": MaintenanceStatus.Scheduled.value},
        {"_id": 0, "id": 1, "scheduled_date": 1},
    ):
        sched = _parse_date(m.get("scheduled_date"))
        if sched and sched.date() < today:
            await db[MAINTENANCE_COLL].update_one(
                {"id": m["id"]},
                {"$set": {"status": MaintenanceStatus.Overdue.value, "updated_at": _iso(), "updated_by": "system-reconciliation"}},
            )


# ---------------------------------------------------------------- router factory
def _build_generic_crud(router, coll_name: str, prefix: str, service_create, model_read):
    """Attach generic list/get/put/delete for a compliance collection."""
    from fastapi import Query  # noqa: F401

    # Skipping — routes are attached explicitly below for clarity.
    return


def build_compliance_router(db, get_current_user):
    router = APIRouter(prefix="/api")
    svc = _ComplianceService(db)

    # ---- helper for generic list/put/delete used across records
    # Collections whose records carry an expiry_date and must expose
    # EB-R02 calculated intelligence (calculated_status + days_remaining)
    # on every read, regardless of stored status value.
    _EXPIRY_ENRICH_COLLS = {LICENCES_COLL, REGISTRATIONS_COLL, INSURANCE_COLL}

    def _enrich_expiry(coll_name: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        if coll_name in _EXPIRY_ENRICH_COLLS and doc is not None:
            exp = doc.get("expiry_date")
            doc["calculated_status"] = _classify_expiry(exp)
            doc["days_remaining"] = _days_remaining(exp)
        return doc

    def _make_list(coll_name: str):
        async def handler(
            driver_id: Optional[str] = None,
            vehicle_id: Optional[str] = None,
            equipment_id: Optional[str] = None,
            status: Optional[str] = None,
            include_archived: bool = False,
            current=Depends(get_current_user),
        ):
            q: Dict[str, Any] = {}
            if driver_id:
                q["driver_id"] = driver_id
            if vehicle_id:
                q["vehicle_id"] = vehicle_id
            if equipment_id:
                q["equipment_id"] = equipment_id
            if status:
                q["status"] = status
            if not include_archived:
                q["is_archived"] = {"$ne": True}
            rows = await db[coll_name].find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
            return [_enrich_expiry(coll_name, r) for r in rows]

        return handler

    def _make_get(coll_name: str, id_label: str):
        async def handler(record_id: str, current=Depends(get_current_user)):
            doc = await db[coll_name].find_one({"id": record_id}, {"_id": 0})
            if not doc:
                raise HTTPException(status_code=404, detail=f"{id_label} not found")
            return _enrich_expiry(coll_name, doc)

        return handler

    def _make_update(coll_name: str, expiry_field: Optional[str], id_label: str):
        async def handler(record_id: str, payload: dict, current=Depends(get_current_user)):
            _require_write(current)
            existing = await db[coll_name].find_one({"id": record_id}, {"_id": 0})
            if not existing:
                raise HTTPException(status_code=404, detail=f"{id_label} not found")
            updates = {k: v for k, v in (payload or {}).items() if k not in ("id", "_id", "created_at", "created_by")}
            # Recompute status if expiry changed
            if expiry_field and expiry_field in updates:
                updates["status"] = _classify_expiry(updates[expiry_field])
            updates["updated_at"] = _iso()
            updates["updated_by"] = current.get("email")
            await db[coll_name].update_one({"id": record_id}, {"$set": updates})
            return await db[coll_name].find_one({"id": record_id}, {"_id": 0})

        return handler

    def _make_archive(coll_name: str, id_label: str):
        async def handler(record_id: str, current=Depends(get_current_user)):
            _require_archive(current)
            existing = await db[coll_name].find_one({"id": record_id}, {"_id": 0})
            if not existing:
                raise HTTPException(status_code=404, detail=f"{id_label} not found")
            updates = {
                "is_archived": True,
                "status": ComplianceStatus.Archived.value,
                "updated_at": _iso(),
                "updated_by": current.get("email"),
            }
            # Also close is_primary / is_current where applicable
            if "is_primary" in existing:
                updates["is_primary"] = False
            if "is_current" in existing:
                updates["is_current"] = False
            await db[coll_name].update_one({"id": record_id}, {"$set": updates})
            return {"status": "archived", "id": record_id}

        return handler

    # ---------------- Driver Licences ----------------
    router.get("/driver-licences")(_make_list(LICENCES_COLL))
    router.get("/driver-licences/{record_id}")(_make_get(LICENCES_COLL, "Licence"))

    @router.post("/driver-licences", response_model=DriverLicenceRead)
    async def create_licence(payload: DriverLicenceCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_licence(payload, current.get("email"))

    @router.put("/driver-licences/{record_id}")
    async def update_licence(record_id: str, payload: DriverLicenceUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[LICENCES_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Licence not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # EB-R02 · calculated status is system-owned. Ignore any
        # user-supplied status on update.
        updates.pop("status", None)
        # If flipping to primary, close previous primary
        if updates.get("is_primary") is True:
            await db[LICENCES_COLL].update_many(
                {"driver_id": existing["driver_id"], "id": {"$ne": record_id}, "is_primary": True, "is_archived": {"$ne": True}},
                {"$set": {"is_primary": False, "updated_at": _iso(), "updated_by": current.get("email")}},
            )
        if "expiry_date" in updates:
            updates["status"] = _classify_expiry(updates["expiry_date"])
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[LICENCES_COLL].update_one({"id": record_id}, {"$set": updates})
        return await db[LICENCES_COLL].find_one({"id": record_id}, {"_id": 0})

    router.delete("/driver-licences/{record_id}")(_make_archive(LICENCES_COLL, "Licence"))

    # ---------------- Vehicle Registrations ----------------
    router.get("/vehicle-registrations")(_make_list(REGISTRATIONS_COLL))
    router.get("/vehicle-registrations/{record_id}")(_make_get(REGISTRATIONS_COLL, "Registration"))

    @router.post("/vehicle-registrations", response_model=VehicleRegistrationRead)
    async def create_registration(payload: VehicleRegistrationCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_registration(payload, current.get("email"))

    @router.put("/vehicle-registrations/{record_id}")
    async def update_registration(record_id: str, payload: VehicleRegistrationUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[REGISTRATIONS_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Registration not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # EB-R02 · calculated status is system-owned.
        updates.pop("status", None)
        if updates.get("is_current") is True:
            await db[REGISTRATIONS_COLL].update_many(
                {"vehicle_id": existing["vehicle_id"], "id": {"$ne": record_id}, "is_current": True, "is_archived": {"$ne": True}},
                {"$set": {"is_current": False, "updated_at": _iso(), "updated_by": current.get("email")}},
            )
        if "expiry_date" in updates:
            updates["status"] = _classify_expiry(updates["expiry_date"])
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[REGISTRATIONS_COLL].update_one({"id": record_id}, {"$set": updates})
        return await db[REGISTRATIONS_COLL].find_one({"id": record_id}, {"_id": 0})

    router.delete("/vehicle-registrations/{record_id}")(_make_archive(REGISTRATIONS_COLL, "Registration"))

    # ---------------- Vehicle Insurance ----------------
    router.get("/vehicle-insurance")(_make_list(INSURANCE_COLL))
    router.get("/vehicle-insurance/{record_id}")(_make_get(INSURANCE_COLL, "Insurance"))

    @router.post("/vehicle-insurance", response_model=VehicleInsuranceRead)
    async def create_insurance(payload: VehicleInsuranceCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_insurance(payload, current.get("email"))

    @router.put("/vehicle-insurance/{record_id}")
    async def update_insurance(record_id: str, payload: VehicleInsuranceUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[INSURANCE_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Insurance not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # EB-R02 · calculated status is system-owned.
        updates.pop("status", None)
        if updates.get("is_current") is True:
            await db[INSURANCE_COLL].update_many(
                {
                    "vehicle_id": existing["vehicle_id"],
                    "cover_type": updates.get("cover_type") or existing.get("cover_type"),
                    "id": {"$ne": record_id},
                    "is_current": True,
                    "is_archived": {"$ne": True},
                },
                {"$set": {"is_current": False, "updated_at": _iso(), "updated_by": current.get("email")}},
            )
        if "expiry_date" in updates:
            updates["status"] = _classify_expiry(updates["expiry_date"])
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[INSURANCE_COLL].update_one({"id": record_id}, {"$set": updates})
        return await db[INSURANCE_COLL].find_one({"id": record_id}, {"_id": 0})

    router.delete("/vehicle-insurance/{record_id}")(_make_archive(INSURANCE_COLL, "Insurance"))

    # ---------------- Vehicle Inspections ----------------
    router.get("/vehicle-inspections")(_make_list(INSPECTIONS_COLL))
    router.get("/vehicle-inspections/{record_id}")(_make_get(INSPECTIONS_COLL, "Inspection"))

    @router.post("/vehicle-inspections", response_model=VehicleInspectionRead)
    async def create_inspection(payload: VehicleInspectionCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_inspection(payload, current.get("email"))

    @router.put("/vehicle-inspections/{record_id}")
    async def update_inspection(record_id: str, payload: VehicleInspectionUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[INSPECTIONS_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Inspection not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # Recompute status
        result = updates.get("result") or existing.get("result")
        nxt = updates.get("next_inspection_due") if "next_inspection_due" in updates else existing.get("next_inspection_due")
        if result == InspectionResult.Fail.value:
            updates["status"] = ComplianceStatus.Expired.value
        elif result in (InspectionResult.Pass.value, InspectionResult.PassWithObservations.value):
            updates["status"] = _classify_expiry(nxt)
        elif result == InspectionResult.Pending.value:
            updates["status"] = ComplianceStatus.UnderReview.value
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[INSPECTIONS_COLL].update_one({"id": record_id}, {"$set": updates})
        return await db[INSPECTIONS_COLL].find_one({"id": record_id}, {"_id": 0})

    router.delete("/vehicle-inspections/{record_id}")(_make_archive(INSPECTIONS_COLL, "Inspection"))

    # ---------------- Vehicle Defects ----------------
    router.get("/vehicle-defects")(_make_list(DEFECTS_COLL))
    router.get("/vehicle-defects/{record_id}")(_make_get(DEFECTS_COLL, "Defect"))

    @router.post("/vehicle-defects", response_model=VehicleDefectRead)
    async def create_defect(payload: VehicleDefectCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_defect(payload, current.get("email"))

    @router.put("/vehicle-defects/{record_id}")
    async def update_defect(record_id: str, payload: VehicleDefectUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[DEFECTS_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Defect not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        # Enforce rectification requires date+user
        if updates.get("status") == DefectStatus.Rectified.value:
            if not (updates.get("rectified_date") or existing.get("rectified_date")):
                raise HTTPException(status_code=400, detail="Rectified date required when marking Rectified")
            if not (updates.get("rectified_by") or existing.get("rectified_by")):
                updates["rectified_by"] = current.get("email")
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[DEFECTS_COLL].update_one({"id": record_id}, {"$set": updates})
        return await db[DEFECTS_COLL].find_one({"id": record_id}, {"_id": 0})

    @router.delete("/vehicle-defects/{record_id}")
    async def archive_defect(record_id: str, current=Depends(get_current_user)):
        _require_archive(current)
        existing = await db[DEFECTS_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Defect not found")
        await db[DEFECTS_COLL].update_one(
            {"id": record_id},
            {
                "$set": {
                    "is_archived": True,
                    "status": DefectStatus.Archived.value,
                    "updated_at": _iso(),
                    "updated_by": current.get("email"),
                }
            },
        )
        return {"status": "archived", "id": record_id}

    # ---------------- Maintenance ----------------
    router.get("/vehicle-maintenance-tasks")(_make_list(MAINTENANCE_COLL))
    router.get("/vehicle-maintenance-tasks/{record_id}")(_make_get(MAINTENANCE_COLL, "Maintenance task"))

    @router.post("/vehicle-maintenance-tasks", response_model=MaintenanceTaskRead)
    async def create_maintenance(payload: MaintenanceTaskCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_maintenance(payload, current.get("email"))

    @router.put("/vehicle-maintenance-tasks/{record_id}")
    async def update_maintenance(record_id: str, payload: MaintenanceTaskUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[MAINTENANCE_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Maintenance task not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[MAINTENANCE_COLL].update_one({"id": record_id}, {"$set": updates})
        return await db[MAINTENANCE_COLL].find_one({"id": record_id}, {"_id": 0})

    @router.delete("/vehicle-maintenance-tasks/{record_id}")
    async def archive_maintenance(record_id: str, current=Depends(get_current_user)):
        _require_archive(current)
        existing = await db[MAINTENANCE_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Maintenance task not found")
        await db[MAINTENANCE_COLL].update_one(
            {"id": record_id},
            {
                "$set": {
                    "is_archived": True,
                    "status": MaintenanceStatus.Archived.value,
                    "updated_at": _iso(),
                    "updated_by": current.get("email"),
                }
            },
        )
        return {"status": "archived", "id": record_id}

    # ---------------- Equipment Compliance ----------------
    router.get("/equipment-compliance")(_make_list(EQUIPMENT_COMPLIANCE_COLL))
    router.get("/equipment-compliance/{record_id}")(_make_get(EQUIPMENT_COMPLIANCE_COLL, "Equipment compliance"))

    @router.post("/equipment-compliance", response_model=EquipmentComplianceRead)
    async def create_eq_compliance(payload: EquipmentComplianceCreate, current=Depends(get_current_user)):
        _require_write(current)
        return await svc.create_equipment_compliance(payload, current.get("email"))

    @router.put("/equipment-compliance/{record_id}")
    async def update_eq_compliance(record_id: str, payload: EquipmentComplianceUpdate, current=Depends(get_current_user)):
        _require_write(current)
        existing = await db[EQUIPMENT_COMPLIANCE_COLL].find_one({"id": record_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Equipment compliance not found")
        updates = payload.model_dump(mode="json", exclude_unset=True)
        if updates.get("is_current") is True:
            await db[EQUIPMENT_COMPLIANCE_COLL].update_many(
                {
                    "equipment_id": existing["equipment_id"],
                    "compliance_type": updates.get("compliance_type") or existing.get("compliance_type"),
                    "id": {"$ne": record_id},
                    "is_current": True,
                    "is_archived": {"$ne": True},
                },
                {"$set": {"is_current": False, "updated_at": _iso(), "updated_by": current.get("email")}},
            )
        if "expiry_date" in updates:
            updates["status"] = _classify_expiry(updates["expiry_date"])
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[EQUIPMENT_COMPLIANCE_COLL].update_one({"id": record_id}, {"$set": updates})
        return await db[EQUIPMENT_COMPLIANCE_COLL].find_one({"id": record_id}, {"_id": 0})

    router.delete("/equipment-compliance/{record_id}")(_make_archive(EQUIPMENT_COMPLIANCE_COLL, "Equipment compliance"))

    # ---------------- Summary endpoints ----------------
    @router.get("/compliance/drivers/{driver_id}")
    async def driver_summary_route(driver_id: str, current=Depends(get_current_user)):
        return await svc.driver_summary(driver_id)

    @router.get("/compliance/vehicles/{vehicle_id}")
    async def vehicle_summary_route(vehicle_id: str, current=Depends(get_current_user)):
        return await svc.vehicle_summary(vehicle_id)

    @router.get("/compliance/equipment/{equipment_id}")
    async def equipment_summary_route(equipment_id: str, current=Depends(get_current_user)):
        return await svc.equipment_summary(equipment_id)

    @router.get("/compliance/overview")
    async def compliance_overview(
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        due_within_days: Optional[int] = None,
        company_ref: Optional[str] = None,
        include_archived: bool = False,
        current=Depends(get_current_user),
    ):
        """Canonical compliance overview. Aggregates per-driver/vehicle/equipment summaries."""
        results = {
            "warning_window_days": WARNING_WINDOW_DAYS,
            "urgent_window_days": URGENT_WINDOW_DAYS,
            "drivers": [],
            "vehicles": [],
            "equipment": [],
            "totals": {"drivers": {}, "vehicles": {}, "equipment": {}},
            "calculated_at": _iso(),
        }

        drv_q: Dict[str, Any] = {} if include_archived else {"is_archived": {"$ne": True}}
        if company_ref:
            drv_q["company_ref"] = company_ref
        veh_q: Dict[str, Any] = {} if include_archived else {"is_archived": {"$ne": True}}
        if company_ref:
            veh_q["company_ref"] = company_ref
        eq_q: Dict[str, Any] = {} if include_archived else {"is_archived": {"$ne": True}}
        if company_ref:
            eq_q["company_ref"] = company_ref

        include_types = None
        if entity_type:
            include_types = {t.strip() for t in entity_type.split(",")}

        def _matches(summary: Dict[str, Any]) -> bool:
            if status and summary.get("overall_status") != status:
                return False
            if due_within_days is not None:
                # Include only rows where at least one component expires within the window
                found = False
                for c in summary.get("components", []):
                    d = _parse_date(c.get("expiry_date"))
                    if d and 0 <= (d.date() - datetime.now(timezone.utc).date()).days <= due_within_days:
                        found = True
                        break
                if not found:
                    return False
            return True

        if include_types is None or "driver" in include_types:
            async for d in db[DRIVERS_COLL].find(drv_q, {"_id": 0, "id": 1}):
                s = await svc.driver_summary(d["id"])
                results["totals"]["drivers"][s["overall_status"]] = results["totals"]["drivers"].get(s["overall_status"], 0) + 1
                if _matches(s):
                    results["drivers"].append(s)

        if include_types is None or "vehicle" in include_types:
            async for v in db[VEHICLES_COLL].find(veh_q, {"_id": 0, "id": 1}):
                s = await svc.vehicle_summary(v["id"])
                results["totals"]["vehicles"][s["overall_status"]] = results["totals"]["vehicles"].get(s["overall_status"], 0) + 1
                if _matches(s):
                    results["vehicles"].append(s)

        if include_types is None or "equipment" in include_types:
            async for e in db[EQUIPMENT_COLL].find(eq_q, {"_id": 0, "id": 1}):
                s = await svc.equipment_summary(e["id"])
                results["totals"]["equipment"][s["overall_status"]] = results["totals"]["equipment"].get(s["overall_status"], 0) + 1
                if _matches(s):
                    results["equipment"].append(s)

        return results

    return router
