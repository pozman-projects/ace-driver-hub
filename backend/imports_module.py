"""
EB-06 Guided Spreadsheet Import & Migration Framework.

Provides:
    - safe workbook inspection (openpyxl `data_only=True`, macros never executed)
    - reusable domain configs (Drivers, Owners, Vehicles, Equipment, Driver Licences,
      Vehicle Registrations, Vehicle Insurance, Relationships) with target field
      configs, normalisers and matching rules
    - dry-run validation with row-level errors, warnings, conflicts and duplicate
      detection across the spreadsheet AND canonical collections
    - explicit commit with per-batch idempotency, high-risk update flagging,
      and reversible-where-safe rollback

Collections created:
    - import_jobs
    - import_files
    - import_mappings
    - import_rows
    - import_conflicts
    - import_commits
    - import_rollback_events
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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
    _classify_expiry,
)

logger = logging.getLogger("dcc.imports")

IMPORT_JOBS = "import_jobs"
IMPORT_FILES = "import_files"
IMPORT_MAPPINGS = "import_mappings"
IMPORT_ROWS = "import_rows"
IMPORT_CONFLICTS = "import_conflicts"
IMPORT_COMMITS = "import_commits"
IMPORT_ROLLBACKS = "import_rollback_events"

MAX_ROWS = 50_000
MAX_COLS = 250
MAX_FILE_BYTES = 20 * 1024 * 1024


# ---------------------------------------------------------------- enums
class JobStatus(str, Enum):
    Uploaded = "Uploaded"
    Inspecting = "Inspecting"
    MappingRequired = "Mapping Required"
    ReadyForValidation = "Ready for Validation"
    Validating = "Validating"
    ValidationFailed = "Validation Failed"
    ReadyToCommit = "Ready to Commit"
    Committing = "Committing"
    Committed = "Committed"
    PartiallyCommitted = "Partially Committed"
    CommitFailed = "Commit Failed"
    RolledBack = "Rolled Back"
    Cancelled = "Cancelled"
    Archived = "Archived"


class Mode(str, Enum):
    CreateOnly = "Create Only"
    UpdateExisting = "Update Existing"
    CreateAndUpdate = "Create and Update"
    ReconcileOnly = "Reconcile Only"


class ValidationStatus(str, Enum):
    Valid = "Valid"
    Warning = "Warning"
    Error = "Error"
    Skipped = "Skipped"


class MatchStatus(str, Enum):
    New = "New"
    ExactMatch = "Exact Match"
    ProbableMatch = "Probable Match"
    MultipleMatches = "Multiple Matches"
    NoMatch = "No Match"
    Conflict = "Conflict"


class RowAction(str, Enum):
    Create = "Create"
    Update = "Update"
    Skip = "Skip"
    Review = "Review"
    NoChange = "No Change"


class CommitStatus(str, Enum):
    NotCommitted = "Not Committed"
    Created = "Created"
    Updated = "Updated"
    Skipped = "Skipped"
    Failed = "Failed"
    RolledBack = "Rolled Back"


class ConflictSeverity(str, Enum):
    Information = "Information"
    Warning = "Warning"
    Blocking = "Blocking"


class ConflictResolution(str, Enum):
    Unresolved = "Unresolved"
    UseSource = "Use Source Value"
    KeepExisting = "Keep Existing Value"
    MapExisting = "Map to Existing Record"
    CreateNew = "Create New Record"
    SkipRow = "Skip Row"
    CorrectSource = "Correct Source Value"
    Other = "Other"


class RollbackStatus(str, Enum):
    Requested = "Requested"
    InProgress = "In Progress"
    Completed = "Completed"
    PartiallyCompleted = "Partially Completed"
    Failed = "Failed"
    NotSupported = "Not Supported"


# ---------------------------------------------------------------- helpers
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    s = re.sub(r"\s+", " ", s)
    return s or None


def _norm_email(v: Any) -> Optional[str]:
    s = _norm_str(v)
    return s.lower() if s else None


def _norm_upper(v: Any) -> Optional[str]:
    s = _norm_str(v)
    return s.upper() if s else None


def _norm_title(v: Any) -> Optional[str]:
    s = _norm_str(v)
    if not s:
        return None
    return " ".join(w[:1].upper() + w[1:] for w in s.split(" "))


def _norm_mobile(v: Any) -> Optional[str]:
    s = _norm_str(v)
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    # Australian mobile: leading zero preserved for local format
    if digits.startswith("61") and len(digits) == 11:
        digits = "0" + digits[2:]
    if len(digits) == 9 and digits.startswith("4"):
        digits = "0" + digits
    return digits


def _norm_abn(v: Any) -> Optional[str]:
    s = _norm_str(v)
    if not s:
        return None
    return re.sub(r"\D", "", s) or None


def _norm_date(v: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return (iso_date_str, error_or_None)."""
    if v is None or v == "":
        return None, None
    if isinstance(v, datetime):
        return v.date().isoformat(), None
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()[:10], None
        except Exception:  # noqa: BLE001
            pass
    if isinstance(v, (int, float)):
        # Excel serial date
        try:
            base = datetime(1899, 12, 30, tzinfo=timezone.utc)
            d = base.fromordinal(base.toordinal() + int(v))
            return d.date().isoformat(), None
        except Exception:  # noqa: BLE001
            return None, "Invalid Excel serial date"
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%-d/%-m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat(), None
        except ValueError:
            continue
    return None, f"Unrecognised date '{s}'"


def _norm_bool(v: Any) -> Optional[bool]:
    if v is None or v == "":
        return None
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1"): return True
    if s in ("false", "no", "n", "0"): return False
    return None


def _norm_pct(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    s = str(v).strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


NORMALISERS: Dict[str, Callable[[Any], Any]] = {
    "str": _norm_str,
    "title": _norm_title,
    "email": _norm_email,
    "upper": _norm_upper,
    "mobile": _norm_mobile,
    "abn": _norm_abn,
    "date": _norm_date,
    "bool": _norm_bool,
    "percentage": _norm_pct,
}


# ---------------------------------------------------------------- domain configs
class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str
    label: str
    normaliser: str = "str"
    required: bool = False
    unique: bool = False  # cross-record uniqueness (business identifier)
    controlled_values: Optional[List[str]] = None
    is_high_risk_on_update: bool = False


class DomainConfig(BaseModel):
    slug: str
    label: str
    collection: str
    business_id_field: str  # canonical business identifier used for match
    match_priority: List[str]  # ordered list of field keys for matching
    fields: List[FieldSpec]

    def field_map(self) -> Dict[str, FieldSpec]:
        return {f.key: f for f in self.fields}


DOMAIN_CONFIGS: Dict[str, DomainConfig] = {
    "drivers": DomainConfig(
        slug="drivers", label="Drivers", collection=DRIVERS_COLL,
        business_id_field="driver_code",
        match_priority=["driver_code", "dispatch_number", "email", "full_name"],
        fields=[
            FieldSpec(key="driver_code", label="Driver Code", unique=True, is_high_risk_on_update=True),
            FieldSpec(key="full_name", label="Full Name", normaliser="title", required=True),
            FieldSpec(key="dispatch_number", label="Dispatch Number", unique=True, is_high_risk_on_update=True),
            FieldSpec(key="email", label="Email", normaliser="email"),
            FieldSpec(key="mobile_number", label="Mobile", normaliser="mobile"),
            FieldSpec(key="business_name", label="Business Name"),
            FieldSpec(key="company_ref", label="Company"),
            FieldSpec(key="driver_status", label="Status",
                       controlled_values=["Active", "On Leave", "Training", "Probation", "Inactive", "Archived"]),
        ],
    ),
    "owners": DomainConfig(
        slug="owners", label="Owners", collection=OWNERS_COLL,
        business_id_field="abn",
        match_priority=["abn", "name", "email"],
        fields=[
            FieldSpec(key="name", label="Owner Name", normaliser="title", required=True),
            FieldSpec(key="abn", label="ABN", normaliser="abn", unique=True),
            FieldSpec(key="owner_type", label="Owner Type",
                       controlled_values=["Individual", "Business", "Trust", "Other"]),
            FieldSpec(key="email", label="Email", normaliser="email"),
            FieldSpec(key="mobile_number", label="Mobile", normaliser="mobile"),
            FieldSpec(key="primary_contact_name", label="Primary Contact", normaliser="title"),
            FieldSpec(key="owner_status", label="Status",
                       controlled_values=["Active", "Inactive", "Archived"]),
        ],
    ),
    "vehicles": DomainConfig(
        slug="vehicles", label="Vehicles", collection=VEHICLES_COLL,
        business_id_field="registration_number",
        match_priority=["vin", "registration_number"],
        fields=[
            FieldSpec(key="registration_number", label="Registration", normaliser="upper", required=True, unique=True, is_high_risk_on_update=True),
            FieldSpec(key="vin", label="VIN", normaliser="upper", unique=True, is_high_risk_on_update=True),
            FieldSpec(key="make", label="Make"),
            FieldSpec(key="model", label="Model"),
            FieldSpec(key="year", label="Year"),
            FieldSpec(key="vehicle_type", label="Vehicle Type"),
            FieldSpec(key="vehicle_status", label="Status",
                       controlled_values=["Active", "Inactive", "Maintenance", "Archived"]),
        ],
    ),
    "equipment": DomainConfig(
        slug="equipment", label="Equipment", collection=EQUIPMENT_COLL,
        business_id_field="equipment_number",
        match_priority=["equipment_number"],
        fields=[
            FieldSpec(key="equipment_number", label="Equipment #", normaliser="upper", required=True, unique=True),
            FieldSpec(key="equipment_type", label="Type",
                       controlled_values=["Trailer", "Tilt Tray", "Truck Body", "Other"]),
            FieldSpec(key="equipment_status", label="Status",
                       controlled_values=["Available", "Assigned", "Maintenance", "Inactive", "Archived"]),
        ],
    ),
    "driver-licences": DomainConfig(
        slug="driver-licences", label="Driver Licences", collection=LICENCES_COLL,
        business_id_field="licence_number",
        match_priority=["licence_number", "driver_id"],
        fields=[
            FieldSpec(key="driver_id", label="Driver ID", required=True),
            FieldSpec(key="licence_number", label="Licence Number", required=True),
            FieldSpec(key="state", label="State"),
            FieldSpec(key="licence_class", label="Class"),
            FieldSpec(key="issue_date", label="Issue Date", normaliser="date"),
            FieldSpec(key="expiry_date", label="Expiry Date", normaliser="date"),
            FieldSpec(key="is_primary", label="Primary", normaliser="bool"),
        ],
    ),
    "vehicle-registrations": DomainConfig(
        slug="vehicle-registrations", label="Vehicle Registrations", collection=REGISTRATIONS_COLL,
        business_id_field="registration_number_snapshot",
        match_priority=["registration_number_snapshot", "vehicle_id"],
        fields=[
            FieldSpec(key="vehicle_id", label="Vehicle ID", required=True),
            FieldSpec(key="registration_number_snapshot", label="Registration #", normaliser="upper"),
            FieldSpec(key="state", label="State"),
            FieldSpec(key="issue_date", label="Issue Date", normaliser="date"),
            FieldSpec(key="expiry_date", label="Expiry Date", normaliser="date"),
            FieldSpec(key="is_current", label="Current", normaliser="bool"),
        ],
    ),
    "vehicle-insurance": DomainConfig(
        slug="vehicle-insurance", label="Vehicle Insurance", collection=INSURANCE_COLL,
        business_id_field="policy_number",
        match_priority=["policy_number", "vehicle_id"],
        fields=[
            FieldSpec(key="vehicle_id", label="Vehicle ID", required=True),
            FieldSpec(key="policy_number", label="Policy Number", required=True),
            FieldSpec(key="provider", label="Provider"),
            FieldSpec(key="cover_type", label="Cover Type"),
            FieldSpec(key="effective_date", label="Effective Date", normaliser="date"),
            FieldSpec(key="expiry_date", label="Expiry Date", normaliser="date"),
            FieldSpec(key="is_current", label="Current", normaliser="bool"),
        ],
    ),
}


# ---------------------------------------------------------------- role helpers
def _require_role(user, allowed: Tuple[str, ...]):
    if user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=f"Role {user.get('role')} not permitted")


# ---------------------------------------------------------------- workbook safe inspection
def _inspect_workbook(binary: bytes, filename: str) -> Dict[str, Any]:
    """Inspect a workbook/CSV safely. openpyxl `data_only=True` never executes formulas."""
    if len(binary) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail=f"File exceeds {MAX_FILE_BYTES // (1024 * 1024)}MB limit")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        text = binary.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise HTTPException(status_code=400, detail="CSV appears empty")
        headers = [str(h).strip() for h in rows[0]]
        return {
            "sheets": [{
                "name": "csv",
                "hidden": False,
                "row_count": len(rows) - 1,
                "column_count": len(headers),
                "headers": headers,
                "sample_rows": rows[1:6],
                "has_formulas": False,
            }],
            "file_type": "csv",
        }
    if ext not in ("xlsx", "xlsm"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type .{ext}")
    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(binary),
            data_only=True,   # <-- never evaluate formulas; only cached values
            read_only=True,   # <-- streaming
            keep_links=False, # <-- never follow external links
            keep_vba=False,   # <-- ignore macros
        )
    except InvalidFileException as e:
        raise HTTPException(status_code=400, detail=f"Unreadable workbook: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Failed to inspect workbook: {e}")

    sheets = []
    for name in wb.sheetnames:
        ws = wb[name]
        # Row/col limits
        max_row = min(ws.max_row or 0, MAX_ROWS + 5)
        max_col = min(ws.max_column or 0, MAX_COLS + 5)
        rows_iter = ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            header_row = tuple()
        headers = [str(h).strip() if h is not None else "" for h in header_row]
        sample_rows = []
        for i, r in enumerate(rows_iter):
            if i >= 5:
                break
            sample_rows.append([("" if c is None else c) for c in r])
        # Count remaining rows
        count = len(sample_rows)
        for _ in rows_iter:
            count += 1
            if count > MAX_ROWS:
                break
        sheets.append({
            "name": name,
            "hidden": ws.sheet_state != "visible",
            "row_count": count,
            "column_count": len(headers),
            "headers": headers,
            "sample_rows": sample_rows,
            "has_formulas": False,  # data_only=True already resolved formulas
        })
    wb.close()
    return {"sheets": sheets, "file_type": ext}


def _load_sheet_rows(binary: bytes, filename: str, sheet_name: str) -> Tuple[List[str], List[List[Any]]]:
    """Return (headers, rows) fully materialised for a chosen sheet."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        text = binary.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        return ([str(h).strip() for h in rows[0]] if rows else []), [list(r) for r in rows[1:]]
    wb = openpyxl.load_workbook(io.BytesIO(binary), data_only=True, read_only=True, keep_links=False, keep_vba=False)
    if sheet_name not in wb.sheetnames:
        raise HTTPException(status_code=400, detail=f"Sheet {sheet_name} not found")
    ws = wb[sheet_name]
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        wb.close()
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in header_row]
    data = []
    for i, r in enumerate(rows_iter):
        if i >= MAX_ROWS:
            break
        # Skip fully-blank rows
        if all(c is None or (isinstance(c, str) and not c.strip()) for c in r):
            continue
        data.append(list(r))
    wb.close()
    return headers, data


# ---------------------------------------------------------------- indexes
async def ensure_indexes(db):
    for c in (IMPORT_JOBS, IMPORT_FILES, IMPORT_MAPPINGS, IMPORT_ROWS,
              IMPORT_CONFLICTS, IMPORT_COMMITS, IMPORT_ROLLBACKS):
        await db[c].create_index("id", unique=True)
    await db[IMPORT_ROWS].create_index("import_job_id")
    await db[IMPORT_CONFLICTS].create_index("import_job_id")
    await db[IMPORT_COMMITS].create_index("import_job_id")


# ---------------------------------------------------------------- router
def build_imports_router(db, get_current_user):
    router = APIRouter(prefix="/api")

    # -------- helpers requiring db --------
    async def _get_job(job_id: str) -> Dict[str, Any]:
        j = await db[IMPORT_JOBS].find_one({"id": job_id}, {"_id": 0})
        if not j:
            raise HTTPException(status_code=404, detail="Import job not found")
        return j

    async def _get_file_bytes(file_id: str) -> Tuple[bytes, str]:
        f = await db[IMPORT_FILES].find_one({"id": file_id}, {"_id": 0})
        if not f:
            raise HTTPException(status_code=404, detail="File record missing")
        # We attach binary directly to the import_files record for simplicity
        return f["binary"], f["original_filename"]

    async def _write_row(job_id: str, row_number: int, raw: List[Any], normalised: Dict[str, Any],
                        target: Dict[str, Any], validation: str, match: str, action: str,
                        errors: List[str], warnings: List[str], matched_record_id: Optional[str]):
        doc = {
            "id": str(uuid.uuid4()),
            "import_job_id": job_id,
            "row_number": row_number,
            "raw_values": [("" if v is None else v) for v in raw],
            "normalised_values": normalised,
            "target_values": target,
            "validation_status": validation,
            "match_status": match,
            "matched_record_id": matched_record_id,
            "action": action,
            "errors": errors,
            "warnings": warnings,
            "conflict_ids": [],
            "commit_status": CommitStatus.NotCommitted.value,
            "created_record_id": None,
            "updated_record_id": None,
            "is_archived": False,
            "created_at": _iso(),
        }
        await db[IMPORT_ROWS].insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def _record_conflict(job_id: str, row_id: str, ctype: str, field: str,
                                severity: str, source_value: Any, existing_value: Any,
                                existing_record_id: Optional[str], notes: str = "") -> str:
        cid = str(uuid.uuid4())
        await db[IMPORT_CONFLICTS].insert_one({
            "id": cid,
            "import_job_id": job_id,
            "import_row_id": row_id,
            "conflict_type": ctype,
            "field_name": field,
            "source_value": source_value,
            "existing_value": existing_value,
            "existing_record_id": existing_record_id,
            "severity": severity,
            "resolution": ConflictResolution.Unresolved.value,
            "resolved_value": None,
            "resolved_by": None,
            "resolved_at": None,
            "notes": notes,
            "is_archived": False,
            "created_at": _iso(),
        })
        return cid

    async def _find_existing(domain: DomainConfig, normalised: Dict[str, Any]) -> Tuple[MatchStatus, Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return (match status, best match, all candidate matches)."""
        candidates: List[Dict[str, Any]] = []
        for field in domain.match_priority:
            val = normalised.get(field)
            if not val:
                continue
            q: Dict[str, Any] = {field: val, "is_archived": {"$ne": True}}
            docs = await db[domain.collection].find(q, {"_id": 0}).to_list(10)
            if docs:
                candidates = docs
                if len(docs) == 1:
                    return MatchStatus.ExactMatch, docs[0], docs
                return MatchStatus.MultipleMatches, None, docs
        return MatchStatus.NoMatch, None, []

    async def _validate_domain_row(domain: DomainConfig, headers_map: Dict[str, str],
                                    row: List[Any], job_id: str, row_number: int,
                                    within_file_business_ids: Dict[str, int], mode: str) -> Dict[str, Any]:
        """Normalise + validate one row against the domain config."""
        raw = row
        normalised: Dict[str, Any] = {}
        errors: List[str] = []
        warnings: List[str] = []

        header_to_index = {h: i for i, h in enumerate(headers_map.keys())}
        # headers_map: source_header -> target field key
        for src_header, target_key in headers_map.items():
            if not target_key:
                continue
            spec = domain.field_map().get(target_key)
            if not spec:
                continue
            idx = list(headers_map.keys()).index(src_header)
            v = raw[idx] if idx < len(raw) else None
            fn = NORMALISERS.get(spec.normaliser, _norm_str)
            out = fn(v)
            if spec.normaliser == "date":
                iso, err = out if isinstance(out, tuple) else (out, None)
                normalised[target_key] = iso
                if err and v not in (None, ""):
                    errors.append(f"{spec.label}: {err}")
            else:
                normalised[target_key] = out

        # Required + controlled + duplicate-in-file
        for spec in domain.fields:
            v = normalised.get(spec.key)
            if spec.required and (v is None or v == ""):
                errors.append(f"{spec.label} required")
            if spec.controlled_values and v not in (None, "") and v not in spec.controlled_values:
                errors.append(f"{spec.label} '{v}' not in {spec.controlled_values}")

        # Within-file duplicate by business id
        biz = normalised.get(domain.business_id_field)
        if biz:
            if biz in within_file_business_ids:
                warnings.append(f"Duplicate {domain.business_id_field} '{biz}' also in row {within_file_business_ids[biz]}")
            else:
                within_file_business_ids[biz] = row_number

        # Match against canonical
        match_status, best, all_candidates = await _find_existing(domain, normalised)
        matched_record_id = best.get("id") if best else None
        conflicts_to_record: List[Tuple[str, str, str, Any, Any, Optional[str], str]] = []

        # Unique-field conflict detection: search each unique field on other candidates
        for spec in domain.fields:
            if not spec.unique:
                continue
            v = normalised.get(spec.key)
            if not v:
                continue
            hit = await db[domain.collection].find_one(
                {spec.key: v, "is_archived": {"$ne": True}}, {"_id": 0}
            )
            if hit and hit["id"] != matched_record_id:
                conflicts_to_record.append((
                    f"Duplicate {spec.label}", spec.key, ConflictSeverity.Blocking.value,
                    v, hit.get(spec.key), hit.get("id"),
                    f"Existing record {hit.get('id')} already has {spec.label} '{v}'"
                ))

        # Determine action based on mode + match
        action = RowAction.Skip
        if errors:
            validation = ValidationStatus.Error.value
        elif conflicts_to_record:
            validation = ValidationStatus.Error.value
        elif warnings:
            validation = ValidationStatus.Warning.value
        else:
            validation = ValidationStatus.Valid.value

        if mode == Mode.CreateOnly.value:
            action = RowAction.Create if match_status == MatchStatus.NoMatch else RowAction.Skip
        elif mode == Mode.UpdateExisting.value:
            action = RowAction.Update if match_status == MatchStatus.ExactMatch else RowAction.Skip
        elif mode == Mode.CreateAndUpdate.value:
            if match_status == MatchStatus.ExactMatch:
                action = RowAction.Update
            elif match_status == MatchStatus.NoMatch:
                action = RowAction.Create
            elif match_status == MatchStatus.MultipleMatches:
                action = RowAction.Review
                conflicts_to_record.append((
                    "Multiple Candidate Matches", domain.business_id_field, ConflictSeverity.Blocking.value,
                    biz, [c["id"] for c in all_candidates], None,
                    "Cannot resolve automatically"
                ))
                validation = ValidationStatus.Error.value
            else:
                action = RowAction.Review
        else:  # ReconcileOnly
            action = RowAction.NoChange

        # For Update: compute field-level diff
        if action == RowAction.Update and best:
            diffs = {}
            high_risk = []
            for spec in domain.fields:
                new_v = normalised.get(spec.key)
                existing_v = best.get(spec.key)
                if new_v is None:
                    continue  # do not overwrite non-empty existing with blank
                if new_v != existing_v:
                    diffs[spec.key] = {"from": existing_v, "to": new_v, "high_risk": spec.is_high_risk_on_update}
                    if spec.is_high_risk_on_update:
                        high_risk.append(spec.key)
                        warnings.append(f"HIGH-RISK change to {spec.label}: '{existing_v}' → '{new_v}'")
            if not diffs:
                action = RowAction.NoChange
                validation = ValidationStatus.Skipped.value

        row_doc = await _write_row(job_id, row_number, raw, normalised, normalised,
                                    validation, match_status.value, action.value if not isinstance(action, str) else action,
                                    errors, warnings, matched_record_id)
        # Attach any conflicts
        for ctype, field, severity, sval, eval_, erecord, notes in conflicts_to_record:
            cid = await _record_conflict(job_id, row_doc["id"], ctype, field, severity, sval, eval_, erecord, notes)
            await db[IMPORT_ROWS].update_one({"id": row_doc["id"]}, {"$push": {"conflict_ids": cid}})
        return row_doc

    # ============================================================
    # ROUTES
    # ============================================================

    @router.post("/imports")
    async def create_job(payload: dict, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance", "Allocator"))
        target = payload.get("target_domain")
        mode = payload.get("mode") or Mode.CreateAndUpdate.value
        if target not in DOMAIN_CONFIGS:
            raise HTTPException(status_code=400, detail=f"Unknown target_domain {target}")
        if mode not in [m.value for m in Mode]:
            raise HTTPException(status_code=400, detail=f"Unknown mode {mode}")
        raw_description = payload.get("description")
        description = raw_description.strip() if isinstance(raw_description, str) else None
        if description == "":
            description = None
        job = {
            "id": str(uuid.uuid4()),
            "target_domain": target,
            "status": JobStatus.Uploaded.value,
            "source_file_id": None,
            "sheet_name": None,
            "mapping_id": None,
            "mode": mode,
            "description": description,
            "total_rows": 0, "valid_rows": 0, "warning_rows": 0, "error_rows": 0,
            "conflict_rows": 0, "skipped_rows": 0,
            "created_rows": 0, "updated_rows": 0, "unchanged_rows": 0,
            "started_at": _iso(), "completed_at": None,
            "created_by": current.get("email"),
            "committed_by": None, "committed_at": None,
            "rolled_back_by": None, "rolled_back_at": None,
            "is_archived": False,
        }
        await db[IMPORT_JOBS].insert_one(job)
        job.pop("_id", None)
        return job

    @router.get("/imports")
    async def list_jobs(include_archived: bool = False, status: Optional[str] = None,
                        target_domain: Optional[str] = None, current=Depends(get_current_user)):
        q: Dict[str, Any] = {}
        if not include_archived: q["is_archived"] = {"$ne": True}
        if status: q["status"] = status
        if target_domain: q["target_domain"] = target_domain
        return await db[IMPORT_JOBS].find(q, {"_id": 0}).sort("started_at", -1).to_list(500)

    @router.get("/imports/{job_id}")
    async def get_job(job_id: str, current=Depends(get_current_user)):
        return await _get_job(job_id)

    @router.delete("/imports/{job_id}")
    async def archive_job(job_id: str, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        await _get_job(job_id)
        await db[IMPORT_JOBS].update_one({"id": job_id}, {"$set": {"is_archived": True, "status": JobStatus.Archived.value}})
        return {"status": "archived", "id": job_id}

    @router.post("/imports/{job_id}/file")
    async def upload_source_file(job_id: str, file: UploadFile = File(...), current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance", "Allocator"))
        job = await _get_job(job_id)
        if job.get("source_file_id"):
            raise HTTPException(status_code=400, detail="Job already has a source file")
        binary = await file.read()
        if not binary:
            raise HTTPException(status_code=400, detail="Empty file")
        if len(binary) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="File too large")
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in ("xlsx", "xlsm", "csv"):
            raise HTTPException(status_code=400, detail="Unsupported spreadsheet type")
        import hashlib
        sha = hashlib.sha256(binary).hexdigest()
        file_doc = {
            "id": str(uuid.uuid4()),
            "document_id": None,  # EB-05 linkage placeholder (not persisted here to keep import file bytes local)
            "original_filename": file.filename,
            "file_type": ext,
            "file_size_bytes": len(binary),
            "checksum_sha256": sha,
            "available_sheets": [],
            "selected_sheet": None,
            "uploaded_at": _iso(),
            "uploaded_by": current.get("email"),
            "is_archived": False,
            "binary": binary,  # inline storage — private, never exposed by any route
        }
        await db[IMPORT_FILES].insert_one(file_doc)
        await db[IMPORT_JOBS].update_one(
            {"id": job_id},
            {"$set": {"source_file_id": file_doc["id"], "status": JobStatus.Inspecting.value}},
        )
        return {"file_id": file_doc["id"], "filename": file.filename, "size": len(binary)}

    @router.get("/imports/{job_id}/sheets")
    async def get_sheets(job_id: str, current=Depends(get_current_user)):
        job = await _get_job(job_id)
        if not job.get("source_file_id"):
            raise HTTPException(status_code=400, detail="No source file uploaded")
        binary, name = await _get_file_bytes(job["source_file_id"])
        info = _inspect_workbook(binary, name)
        await db[IMPORT_FILES].update_one(
            {"id": job["source_file_id"]},
            {"$set": {"available_sheets": [s["name"] for s in info["sheets"]]}},
        )
        return info

    @router.post("/imports/{job_id}/inspect")
    async def choose_sheet(job_id: str, payload: dict, current=Depends(get_current_user)):
        job = await _get_job(job_id)
        sheet = payload.get("sheet_name")
        if not sheet:
            raise HTTPException(status_code=400, detail="sheet_name required")
        binary, name = await _get_file_bytes(job["source_file_id"])
        info = _inspect_workbook(binary, name)
        if sheet not in [s["name"] for s in info["sheets"]]:
            raise HTTPException(status_code=400, detail=f"Sheet {sheet} not in workbook")
        await db[IMPORT_FILES].update_one({"id": job["source_file_id"]}, {"$set": {"selected_sheet": sheet}})
        await db[IMPORT_JOBS].update_one({"id": job_id}, {"$set": {"sheet_name": sheet, "status": JobStatus.MappingRequired.value}})
        found = next(s for s in info["sheets"] if s["name"] == sheet)
        return {"headers": found["headers"], "sample_rows": found["sample_rows"], "row_count": found["row_count"]}

    @router.post("/imports/{job_id}/mapping")
    async def set_mapping(job_id: str, payload: dict, current=Depends(get_current_user)):
        """Payload: {"field_mappings": {source_header: target_field_key}, "name"?: str}. Creates or updates a mapping and attaches it to the job."""
        job = await _get_job(job_id)
        headers_map = payload.get("field_mappings") or {}
        if not headers_map:
            raise HTTPException(status_code=400, detail="field_mappings required")
        domain = DOMAIN_CONFIGS[job["target_domain"]]
        # Validate target field keys
        valid = set(domain.field_map().keys())
        for src, tgt in headers_map.items():
            if tgt and tgt not in valid:
                raise HTTPException(status_code=400, detail=f"Unknown target field '{tgt}'")
        # Required fields must all be mapped
        required = {f.key for f in domain.fields if f.required}
        mapped_targets = {v for v in headers_map.values() if v}
        missing = required - mapped_targets
        if missing:
            raise HTTPException(status_code=400, detail=f"Required target fields not mapped: {sorted(missing)}")
        mapping = {
            "id": str(uuid.uuid4()),
            "name": payload.get("name") or f"{domain.slug} mapping",
            "target_domain": domain.slug,
            "source_headers": list(headers_map.keys()),
            "field_mappings": headers_map,
            "normalisation_rules": {},
            "required_fields": sorted(list(required)),
            "matching_rules": domain.match_priority,
            "default_values": payload.get("default_values") or {},
            "version": 1,
            "is_template": False,
            "is_active": True,
            "created_at": _iso(), "updated_at": _iso(),
            "created_by": current.get("email"), "updated_by": current.get("email"),
            "is_archived": False,
        }
        await db[IMPORT_MAPPINGS].insert_one(mapping)
        await db[IMPORT_JOBS].update_one(
            {"id": job_id}, {"$set": {"mapping_id": mapping["id"], "status": JobStatus.ReadyForValidation.value}}
        )
        mapping.pop("_id", None)
        return mapping

    @router.post("/imports/{job_id}/validate")
    async def validate(job_id: str, current=Depends(get_current_user)):
        job = await _get_job(job_id)
        if not job.get("mapping_id") or not job.get("sheet_name"):
            raise HTTPException(status_code=400, detail="Mapping and sheet required before validation")
        # Clear previous rows/conflicts
        await db[IMPORT_ROWS].delete_many({"import_job_id": job_id})
        await db[IMPORT_CONFLICTS].delete_many({"import_job_id": job_id})

        binary, name = await _get_file_bytes(job["source_file_id"])
        headers, rows = _load_sheet_rows(binary, name, job["sheet_name"])
        mapping = await db[IMPORT_MAPPINGS].find_one({"id": job["mapping_id"]}, {"_id": 0})
        headers_map = mapping["field_mappings"]
        domain = DOMAIN_CONFIGS[job["target_domain"]]

        # Filter headers_map to those actually in the sheet
        headers_map = {h: t for h, t in headers_map.items() if h in headers}

        within_file: Dict[str, int] = {}
        totals = {"valid": 0, "warning": 0, "error": 0, "skipped": 0,
                   "create": 0, "update": 0, "no_change": 0, "review": 0}
        for i, r in enumerate(rows, start=2):
            # Build per-row header-value tuple aligned to headers_map keys order
            row_by_header = {h: (r[headers.index(h)] if headers.index(h) < len(r) else None) for h in headers if h in headers_map}
            aligned = [row_by_header[h] for h in headers_map.keys()]
            row_doc = await _validate_domain_row(domain, headers_map, aligned, job_id, i, within_file, job["mode"])
            totals[row_doc["validation_status"].lower()] = totals.get(row_doc["validation_status"].lower(), 0) + 1
            totals[row_doc["action"].lower().replace(" ", "_")] = totals.get(row_doc["action"].lower().replace(" ", "_"), 0) + 1

        error_rows = totals["error"]
        conflict_rows = await db[IMPORT_CONFLICTS].count_documents({"import_job_id": job_id, "severity": ConflictSeverity.Blocking.value})
        job_status = JobStatus.ValidationFailed.value if (error_rows or conflict_rows) else JobStatus.ReadyToCommit.value
        await db[IMPORT_JOBS].update_one({"id": job_id}, {"$set": {
            "total_rows": len(rows),
            "valid_rows": totals["valid"],
            "warning_rows": totals["warning"],
            "error_rows": totals["error"],
            "skipped_rows": totals["skipped"],
            "conflict_rows": conflict_rows,
            "created_rows": 0, "updated_rows": 0, "unchanged_rows": totals.get("no_change", 0),
            "status": job_status,
        }})
        return await _get_job(job_id)

    @router.get("/imports/{job_id}/validation-summary")
    async def validation_summary(job_id: str, current=Depends(get_current_user)):
        job = await _get_job(job_id)
        rows = await db[IMPORT_ROWS].count_documents({"import_job_id": job_id})
        by_action = {}
        for a in [x.value for x in RowAction]:
            by_action[a] = await db[IMPORT_ROWS].count_documents({"import_job_id": job_id, "action": a})
        conflicts = await db[IMPORT_CONFLICTS].count_documents({"import_job_id": job_id})
        blocking = await db[IMPORT_CONFLICTS].count_documents({"import_job_id": job_id, "severity": ConflictSeverity.Blocking.value,
                                                                "resolution": ConflictResolution.Unresolved.value})
        return {"job": job, "rows": rows, "by_action": by_action, "conflicts": conflicts, "blocking_unresolved": blocking}

    @router.get("/imports/{job_id}/rows")
    async def list_rows(job_id: str, validation_status: Optional[str] = None, action: Optional[str] = None,
                        limit: int = 200, offset: int = 0, current=Depends(get_current_user)):
        q: Dict[str, Any] = {"import_job_id": job_id}
        if validation_status: q["validation_status"] = validation_status
        if action: q["action"] = action
        rows = await db[IMPORT_ROWS].find(q, {"_id": 0}).sort("row_number", 1).skip(offset).limit(limit).to_list(limit)
        total = await db[IMPORT_ROWS].count_documents(q)
        return {"rows": rows, "total": total, "offset": offset, "limit": limit}

    @router.get("/imports/{job_id}/conflicts")
    async def list_conflicts(job_id: str, severity: Optional[str] = None,
                             include_resolved: bool = True, current=Depends(get_current_user)):
        q: Dict[str, Any] = {"import_job_id": job_id}
        if severity: q["severity"] = severity
        if not include_resolved: q["resolution"] = ConflictResolution.Unresolved.value
        return await db[IMPORT_CONFLICTS].find(q, {"_id": 0}).sort("created_at", 1).to_list(2000)

    @router.put("/import-conflicts/{conflict_id}")
    async def resolve_conflict(conflict_id: str, payload: dict, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        resolution = payload.get("resolution")
        if resolution not in [r.value for r in ConflictResolution]:
            raise HTTPException(status_code=400, detail="Unknown resolution")
        existing = await db[IMPORT_CONFLICTS].find_one({"id": conflict_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Conflict not found")
        await db[IMPORT_CONFLICTS].update_one({"id": conflict_id}, {"$set": {
            "resolution": resolution,
            "resolved_value": payload.get("resolved_value"),
            "resolved_by": current.get("email"),
            "resolved_at": _iso(),
        }})
        # Update associated row action if applicable
        row = await db[IMPORT_ROWS].find_one({"id": existing["import_row_id"]}, {"_id": 0})
        if row and resolution == ConflictResolution.SkipRow.value:
            await db[IMPORT_ROWS].update_one({"id": row["id"]}, {"$set": {"action": RowAction.Skip.value}})
        return await db[IMPORT_CONFLICTS].find_one({"id": conflict_id}, {"_id": 0})

    @router.post("/imports/{job_id}/commit")
    async def commit_job(job_id: str, payload: Optional[dict] = None, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        job = await _get_job(job_id)
        blocking = await db[IMPORT_CONFLICTS].count_documents({
            "import_job_id": job_id,
            "severity": ConflictSeverity.Blocking.value,
            "resolution": ConflictResolution.Unresolved.value,
        })
        if blocking > 0:
            raise HTTPException(status_code=409, detail=f"{blocking} blocking conflicts still unresolved")
        # Only run rows with action Create or Update
        rows = await db[IMPORT_ROWS].find(
            {"import_job_id": job_id, "action": {"$in": [RowAction.Create.value, RowAction.Update.value]},
             "commit_status": CommitStatus.NotCommitted.value},
            {"_id": 0},
        ).sort("row_number", 1).to_list(MAX_ROWS)

        domain = DOMAIN_CONFIGS[job["target_domain"]]
        record_actions = []
        created = updated = skipped = failed = 0
        for r in rows:
            try:
                now = _iso()
                if r["action"] == RowAction.Create.value:
                    new_id = str(uuid.uuid4())
                    doc = {"id": new_id, **{k: v for k, v in (r.get("normalised_values") or {}).items() if v is not None},
                            "is_archived": False, "created_at": now, "updated_at": now,
                            "created_by": current.get("email"), "updated_by": current.get("email"),
                            "_source": "import-eb06", "_import_job_id": job_id}
                    # Compute status for compliance rows
                    if job["target_domain"] in ("driver-licences", "vehicle-registrations", "vehicle-insurance"):
                        doc["status"] = _classify_expiry(doc.get("expiry_date"))
                    await db[domain.collection].insert_one(doc)
                    await db[IMPORT_ROWS].update_one({"id": r["id"]}, {"$set": {
                        "commit_status": CommitStatus.Created.value, "created_record_id": new_id,
                    }})
                    created += 1
                    record_actions.append({"row_id": r["id"], "action": "create", "record_id": new_id})
                else:  # Update
                    existing_id = r["matched_record_id"]
                    if not existing_id:
                        skipped += 1
                        await db[IMPORT_ROWS].update_one({"id": r["id"]}, {"$set": {"commit_status": CommitStatus.Skipped.value}})
                        continue
                    updates = {k: v for k, v in (r.get("normalised_values") or {}).items() if v is not None}
                    updates["updated_at"] = now
                    updates["updated_by"] = current.get("email")
                    updates["_import_job_id"] = job_id
                    # Recompute compliance status if expiry updated
                    if job["target_domain"] in ("driver-licences", "vehicle-registrations", "vehicle-insurance") and "expiry_date" in updates:
                        updates["status"] = _classify_expiry(updates["expiry_date"])
                    # Capture before-state for rollback
                    before = await db[domain.collection].find_one({"id": existing_id}, {"_id": 0})
                    await db[domain.collection].update_one({"id": existing_id}, {"$set": updates})
                    await db[IMPORT_ROWS].update_one({"id": r["id"]}, {"$set": {
                        "commit_status": CommitStatus.Updated.value, "updated_record_id": existing_id,
                    }})
                    updated += 1
                    record_actions.append({"row_id": r["id"], "action": "update", "record_id": existing_id,
                                             "before": {k: before.get(k) for k in updates.keys() if k in before}})
            except Exception as e:  # noqa: BLE001
                await db[IMPORT_ROWS].update_one({"id": r["id"]}, {"$set": {
                    "commit_status": CommitStatus.Failed.value,
                    "errors": (r.get("errors") or []) + [f"Commit failed: {e}"],
                }})
                failed += 1

        commit = {
            "id": str(uuid.uuid4()),
            "import_job_id": job_id,
            "commit_sequence": await db[IMPORT_COMMITS].count_documents({"import_job_id": job_id}) + 1,
            "record_actions": record_actions,
            "created_count": created, "updated_count": updated,
            "skipped_count": skipped, "failed_count": failed,
            "committed_at": _iso(), "committed_by": current.get("email"),
            "transaction_status": "committed" if failed == 0 else "partial",
            "rollback_supported": True,
            "notes": (payload or {}).get("notes"),
        }
        await db[IMPORT_COMMITS].insert_one(commit)
        commit.pop("_id", None)
        final_status = (JobStatus.Committed.value if failed == 0 and (created + updated) > 0
                        else JobStatus.PartiallyCommitted.value if (created + updated) > 0
                        else JobStatus.CommitFailed.value)
        await db[IMPORT_JOBS].update_one({"id": job_id}, {"$set": {
            "status": final_status,
            "created_rows": (job.get("created_rows") or 0) + created,
            "updated_rows": (job.get("updated_rows") or 0) + updated,
            "committed_by": current.get("email"),
            "committed_at": _iso(),
            "completed_at": _iso(),
        }})
        return commit

    @router.get("/imports/{job_id}/commit-history")
    async def commit_history(job_id: str, current=Depends(get_current_user)):
        return await db[IMPORT_COMMITS].find({"import_job_id": job_id}, {"_id": 0}).sort("committed_at", 1).to_list(200)

    @router.post("/imports/{job_id}/retry-failed")
    async def retry_failed(job_id: str, current=Depends(get_current_user)):
        # Simply flip failed rows back to NotCommitted so commit can be retried
        _require_role(current, ("Admin", "Manager", "Compliance"))
        r = await db[IMPORT_ROWS].update_many(
            {"import_job_id": job_id, "commit_status": CommitStatus.Failed.value},
            {"$set": {"commit_status": CommitStatus.NotCommitted.value}},
        )
        return {"reset_rows": r.modified_count}

    @router.post("/imports/{job_id}/rollback")
    async def rollback(job_id: str, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        job = await _get_job(job_id)
        commits = await db[IMPORT_COMMITS].find({"import_job_id": job_id}, {"_id": 0}).sort("committed_at", -1).to_list(50)
        if not commits:
            return {"status": "not-supported", "detail": "No commits found"}

        domain = DOMAIN_CONFIGS[job["target_domain"]]
        restored = archived_created = failed = 0
        errors: List[str] = []
        rb_id = str(uuid.uuid4())
        await db[IMPORT_ROLLBACKS].insert_one({
            "id": rb_id, "import_job_id": job_id, "import_commit_id": commits[0]["id"],
            "requested_at": _iso(), "requested_by": current.get("email"),
            "completed_at": None, "status": RollbackStatus.InProgress.value,
            "restored_count": 0, "archived_created_count": 0, "failed_count": 0, "errors": [], "notes": None,
        })
        for commit in commits:
            for action in commit.get("record_actions", []):
                try:
                    if action["action"] == "create":
                        # Soft-archive the created record if still present + still bearing our import id
                        await db[domain.collection].update_one(
                            {"id": action["record_id"], "_import_job_id": job_id},
                            {"$set": {"is_archived": True, "status": "Archived", "updated_at": _iso(), "updated_by": current.get("email")}},
                        )
                        archived_created += 1
                    elif action["action"] == "update":
                        before = action.get("before") or {}
                        if before:
                            await db[domain.collection].update_one(
                                {"id": action["record_id"]},
                                {"$set": {**before, "updated_at": _iso(), "updated_by": current.get("email")}},
                            )
                            restored += 1
                        else:
                            failed += 1
                            errors.append(f"No before-state for row {action.get('row_id')}")
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    errors.append(f"{action.get('record_id')}: {e}")
        final = (RollbackStatus.Completed.value if failed == 0
                 else RollbackStatus.PartiallyCompleted.value if (restored + archived_created) > 0
                 else RollbackStatus.Failed.value)
        await db[IMPORT_ROLLBACKS].update_one({"id": rb_id}, {"$set": {
            "completed_at": _iso(), "status": final, "restored_count": restored,
            "archived_created_count": archived_created, "failed_count": failed, "errors": errors,
        }})
        await db[IMPORT_JOBS].update_one({"id": job_id}, {"$set": {
            "status": JobStatus.RolledBack.value, "rolled_back_by": current.get("email"),
            "rolled_back_at": _iso(),
        }})
        return {"rollback_event_id": rb_id, "status": final, "restored": restored,
                 "archived_created": archived_created, "failed": failed, "errors": errors}

    # ---------------- templates ----------------
    @router.get("/import-templates/{target_domain}")
    async def get_template(target_domain: str, current=Depends(get_current_user)):
        if target_domain not in DOMAIN_CONFIGS:
            raise HTTPException(status_code=404, detail="Unknown domain")
        d = DOMAIN_CONFIGS[target_domain]
        return {"target_domain": d.slug, "label": d.label,
                "fields": [f.model_dump() for f in d.fields],
                "match_priority": d.match_priority,
                "supported_file_types": ["xlsx", "xlsm", "csv"],
                "required_fields": [f.key for f in d.fields if f.required],
                "unique_fields": [f.key for f in d.fields if f.unique],
                "high_risk_update_fields": [f.key for f in d.fields if f.is_high_risk_on_update]}

    @router.get("/import-templates")
    async def list_templates(current=Depends(get_current_user)):
        return [{"slug": d.slug, "label": d.label, "collection": d.collection,
                 "required_fields": [f.key for f in d.fields if f.required]} for d in DOMAIN_CONFIGS.values()]

    return router
