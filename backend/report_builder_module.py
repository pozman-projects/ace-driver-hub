"""MR-08B-P3 · Canonical Report Builder.

One-source, no-join Report Builder over the 13 owner-approved canonical
domains. Reads canonical collections and MR-04 readiness only. All
sensitive-field and document-sensitivity enforcement is server-side and
reuses MR-07A/MR-07B/documents_module policy — no parallel security
constants.

V1 excludes: PDF, saved report definitions, grouping, charts, scheduling,
emailed reports, cross-source joins, calculated fields, custom SQL.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

REPORTS_EXPORT_COLL = "report_exports"
DEFAULT_PREVIEW_LIMIT = 200
MAX_PREVIEW_LIMIT = 1000
MAX_EXPORT_ROWS = 10000
SENSITIVE_DRIVER_FIELDS = frozenset({
    "business_name", "abn", "payroll_number", "payment_percentage",
})


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────
# Field types + operator matrix
# ─────────────────────────────────────────────────────────────────────────
STRING_OPS   = {"equals", "not_equals", "contains", "starts_with", "is_empty", "is_not_empty"}
NUMBER_OPS   = {"equals", "not_equals", "greater_than", "less_than", "greater_or_equal", "less_or_equal", "is_empty", "is_not_empty"}
DATE_OPS     = {"equals", "not_equals", "before", "after", "greater_or_equal", "less_or_equal", "is_empty", "is_not_empty"}
BOOL_OPS     = {"equals", "not_equals"}
OPS_BY_TYPE  = {"string": STRING_OPS, "number": NUMBER_OPS, "date": DATE_OPS, "boolean": BOOL_OPS}


class Field_(BaseModel):
    key: str
    label: str
    type: str  # string | number | date | boolean
    sortable: bool = True
    sensitive: bool = False  # MR-07A driver account fields


class Source(BaseModel):
    key: str
    label: str
    collection: str
    fields: List[Field_]
    archive_field: Optional[str] = "is_archived"

    def field_map(self) -> Dict[str, Field_]:
        return {f.key: f for f in self.fields}


# ─────────────────────────────────────────────────────────────────────────
# SOURCE REGISTRY
# ─────────────────────────────────────────────────────────────────────────
def _field(key, label, ftype, sortable=True, sensitive=False):
    return Field_(key=key, label=label, type=ftype, sortable=sortable, sensitive=sensitive)


REPORT_SOURCES: Dict[str, Source] = {
    "drivers": Source(
        key="drivers", label="Drivers", collection="drivers",
        fields=[
            _field("full_name", "Full Name", "string"),
            _field("mobile_number", "Mobile", "string"),
            _field("email", "Email", "string"),
            _field("residential_address", "Address", "string", sortable=False),
            _field("emergency_contact_name", "Emergency Contact", "string"),
            _field("emergency_contact_phone", "Emergency Phone", "string"),
            _field("driver_code", "Driver Code", "string"),
            _field("dispatch_number", "Dispatch", "string"),
            _field("start_date", "Start Date", "date"),
            _field("driver_status", "Status", "string"),
            _field("company_id", "Company ID", "string"),
            _field("business_name", "Business Name", "string", sensitive=True),
            _field("abn", "ABN", "string", sensitive=True),
            _field("payroll_number", "Payroll Number", "string", sensitive=True),
            _field("payment_percentage", "Payment %", "number", sensitive=True),
        ],
    ),
    "owners": Source(
        key="owners", label="Owners", collection="owners",
        fields=[
            _field("name", "Owner Name", "string"),
            _field("trading_name", "Trading Name", "string"),
            _field("primary_email", "Primary Email", "string"),
            _field("primary_phone", "Primary Phone", "string"),
            _field("company_id", "Company ID", "string"),
        ],
    ),
    "vehicles": Source(
        key="vehicles", label="Vehicles", collection="vehicles_register",
        fields=[
            _field("registration_number", "Registration #", "string"),
            _field("make", "Make", "string"),
            _field("model", "Model", "string"),
            _field("vin", "VIN", "string"),
            _field("vehicle_status", "Status", "string"),
            _field("owner_id", "Owner ID", "string"),
            _field("company_id", "Company ID", "string"),
        ],
    ),
    "equipment": Source(
        key="equipment", label="Equipment", collection="equipment_register",
        fields=[
            _field("equipment_number", "Equipment #", "string"),
            _field("equipment_type", "Type", "string"),
            _field("status", "Status", "string"),
            _field("owner_id", "Owner ID", "string"),
            _field("company_id", "Company ID", "string"),
        ],
    ),
    "driver-licences": Source(
        key="driver-licences", label="Driver Licences", collection="driver_licences",
        fields=[
            _field("driver_id", "Driver ID", "string"),
            _field("licence_number", "Licence #", "string"),
            _field("state", "State", "string"),
            _field("licence_class", "Class", "string"),
            _field("expiry_date", "Expiry", "date"),
            _field("status", "Status", "string"),
            _field("is_primary", "Primary", "boolean"),
        ],
    ),
    "vehicle-registrations": Source(
        key="vehicle-registrations", label="Vehicle Registrations", collection="vehicle_registrations",
        fields=[
            _field("vehicle_id", "Vehicle ID", "string"),
            _field("state", "State", "string"),
            _field("expiry_date", "Expiry", "date"),
            _field("status", "Status", "string"),
            _field("is_current", "Current", "boolean"),
        ],
    ),
    "vehicle-insurance": Source(
        key="vehicle-insurance", label="Vehicle Insurance", collection="vehicle_insurance_policies",
        fields=[
            _field("vehicle_id", "Vehicle ID", "string"),
            _field("insurer", "Insurer", "string"),
            _field("policy_number", "Policy #", "string"),
            _field("policy_type", "Policy Type", "string"),
            _field("expiry_date", "Expiry", "date"),
            _field("status", "Status", "string"),
            _field("is_current", "Current", "boolean"),
        ],
    ),
    "vehicle-inspections": Source(
        key="vehicle-inspections", label="Vehicle Inspections", collection="vehicle_inspections",
        fields=[
            _field("vehicle_id", "Vehicle ID", "string"),
            _field("inspection_type", "Type", "string"),
            _field("inspection_date", "Date", "date"),
            _field("outcome", "Outcome", "string"),
            _field("inspector", "Inspector", "string"),
        ],
    ),
    "vehicle-defects": Source(
        key="vehicle-defects", label="Vehicle Defects", collection="vehicle_defects",
        fields=[
            _field("vehicle_id", "Vehicle ID", "string"),
            _field("severity", "Severity", "string"),
            _field("status", "Status", "string"),
            _field("reported_at", "Reported", "date"),
            _field("resolved_at", "Resolved", "date"),
            _field("description", "Description", "string", sortable=False),
        ],
    ),
    "vehicle-maintenance": Source(
        key="vehicle-maintenance", label="Vehicle Maintenance", collection="vehicle_maintenance_tasks",
        fields=[
            _field("vehicle_id", "Vehicle ID", "string"),
            _field("task_type", "Task Type", "string"),
            _field("scheduled_date", "Scheduled", "date"),
            _field("completed_date", "Completed", "date"),
            _field("status", "Status", "string"),
        ],
    ),
    "equipment-compliance": Source(
        key="equipment-compliance", label="Equipment Compliance", collection="equipment_compliance_records",
        fields=[
            _field("equipment_id", "Equipment ID", "string"),
            _field("check_type", "Check Type", "string"),
            _field("check_date", "Date", "date"),
            _field("outcome", "Outcome", "string"),
        ],
    ),
    "activation-readiness": Source(
        key="activation-readiness", label="Activation Readiness", collection="__virtual_activation__",
        fields=[
            _field("driver_id", "Driver ID", "string"),
            _field("driver_full_name", "Driver", "string"),
            _field("readiness", "Readiness", "string"),
            _field("complete_count", "Complete", "number"),
            _field("missing_count", "Missing", "number"),
        ],
        archive_field=None,
    ),
    "documents": Source(
        key="documents", label="Documents", collection="documents",
        fields=[
            _field("title", "Title", "string"),
            _field("document_type", "Type", "string"),
            _field("sensitivity", "Sensitivity", "string"),
            _field("status", "Status", "string"),
            _field("entity_type", "Entity Type", "string"),
            _field("entity_id", "Entity ID", "string"),
            _field("created_at", "Created", "date"),
        ],
    ),
}


# ─────────────────────────────────────────────────────────────────────────
# Role-filtered field access
# ─────────────────────────────────────────────────────────────────────────
def _role_visible_fields(source: Source, role: str) -> List[Field_]:
    """Filter fields caller may see for this source + role."""
    out = []
    for f in source.fields:
        if f.sensitive and role not in {"Admin", "Manager"}:
            continue  # MR-07A · financial fields hidden
        out.append(f)
    return out


def _sensitivity_visibility(role: str, sensitivity: str) -> bool:
    """Mirror documents_module._visible_by_sensitivity so Report Builder
    never grants a role wider metadata visibility than the canonical
    document policy."""
    if sensitivity in ("Standard", "Internal"):
        return True
    if sensitivity == "Confidential":
        return role in {"Admin", "Manager", "Compliance"}
    if sensitivity == "Restricted":
        return role in {"Admin", "Manager"}
    return False


# ─────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────
class Filter(BaseModel):
    field: str
    operator: str
    value: Optional[Any] = None


class Sort(BaseModel):
    field: str
    direction: str = "asc"

    @field_validator("direction")
    @classmethod
    def _dir(cls, v):
        if v not in ("asc", "desc"):
            raise ValueError("direction must be asc or desc")
        return v


class RunRequest(BaseModel):
    source: str
    fields: List[str] = Field(default_factory=list)
    filters: List[Filter] = Field(default_factory=list)
    sort: List[Sort] = Field(default_factory=list)
    include_archived: bool = False
    limit: int = Field(default=DEFAULT_PREVIEW_LIMIT, ge=1, le=MAX_PREVIEW_LIMIT)


# ─────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────
def _validate_request(req: RunRequest, role: str) -> Tuple[Source, List[Field_]]:
    src = REPORT_SOURCES.get(req.source)
    if not src:
        raise HTTPException(status_code=400, detail=f"Unknown source '{req.source}'")
    visible = {f.key: f for f in _role_visible_fields(src, role)}
    fmap = src.field_map()
    if not req.fields:
        raise HTTPException(status_code=400, detail="At least one field is required")
    selected: List[Field_] = []
    for k in req.fields:
        if k not in fmap:
            raise HTTPException(status_code=400, detail=f"Unknown field '{k}'")
        if k not in visible:
            # MR-07A / sensitive
            raise HTTPException(status_code=403, detail=f"Role not permitted to select field '{k}'")
        selected.append(fmap[k])
    # Filters
    for flt in req.filters:
        f = fmap.get(flt.field)
        if not f:
            raise HTTPException(status_code=400, detail=f"Unknown filter field '{flt.field}'")
        if f.key not in visible:
            raise HTTPException(status_code=403, detail=f"Role not permitted to filter on '{f.key}'")
        allowed_ops = OPS_BY_TYPE.get(f.type, set())
        if flt.operator not in allowed_ops:
            raise HTTPException(status_code=400,
                                 detail=f"Operator '{flt.operator}' not valid for {f.type} field '{f.key}'")
    # Sort
    if len(req.sort) > 2:
        raise HTTPException(status_code=400, detail="At most 2 sort fields allowed")
    for s in req.sort:
        f = fmap.get(s.field)
        if not f:
            raise HTTPException(status_code=400, detail=f"Unknown sort field '{s.field}'")
        if not f.sortable:
            raise HTTPException(status_code=400, detail=f"Field '{s.field}' is not sortable")
        if f.key not in visible:
            raise HTTPException(status_code=403, detail=f"Role not permitted to sort on '{f.key}'")
    return src, selected


# ─────────────────────────────────────────────────────────────────────────
# Mongo query construction
# ─────────────────────────────────────────────────────────────────────────
def _op_to_mongo(f: Field_, flt: Filter) -> Optional[Dict[str, Any]]:
    op, v = flt.operator, flt.value
    if op == "equals":            return {f.key: v}
    if op == "not_equals":        return {f.key: {"$ne": v}}
    if op == "contains":          return {f.key: {"$regex": re.escape(str(v or "")), "$options": "i"}}
    if op == "starts_with":       return {f.key: {"$regex": f"^{re.escape(str(v or ''))}", "$options": "i"}}
    if op == "is_empty":          return {"$or": [{f.key: {"$exists": False}}, {f.key: None}, {f.key: ""}]}
    if op == "is_not_empty":      return {f.key: {"$exists": True, "$nin": [None, ""]}}
    if op == "greater_than":      return {f.key: {"$gt": v}}
    if op == "less_than":         return {f.key: {"$lt": v}}
    if op == "greater_or_equal":  return {f.key: {"$gte": v}}
    if op == "less_or_equal":     return {f.key: {"$lte": v}}
    if op == "before":            return {f.key: {"$lt": v}}
    if op == "after":             return {f.key: {"$gt": v}}
    return None


async def _fetch_rows(db, src: Source, selected: List[Field_], req: RunRequest,
                       role: str, limit: int) -> List[Dict[str, Any]]:
    # ── Virtual sources ───────────────────────────────────────────────
    if src.key == "activation-readiness":
        return await _fetch_activation_readiness(db, selected, req, role, limit)

    q: Dict[str, Any] = {}
    if src.archive_field and not req.include_archived:
        q[src.archive_field] = {"$ne": True}
    for flt in req.filters:
        f = src.field_map()[flt.field]
        cond = _op_to_mongo(f, flt)
        if cond:
            if "$and" in q:
                q["$and"].append(cond)
            else:
                q = {"$and": [q, cond]} if q else cond
    projection = {"_id": 0}
    # Documents source · additional sensitivity filter server-side
    coll = db[src.collection]
    cur = coll.find(q if q else {}, projection)
    if req.sort:
        cur = cur.sort([(s.field, 1 if s.direction == "asc" else -1) for s in req.sort])
    rows = await cur.to_list(limit)
    if src.key == "documents":
        rows = [r for r in rows if _sensitivity_visibility(role, r.get("sensitivity", "Standard"))]
    return rows


async def _fetch_activation_readiness(db, selected, req, role, limit) -> List[Dict[str, Any]]:
    """Read canonical MR-04 blueprint_v1_readiness for each Driver."""
    from activation_module import blueprint_v1_readiness
    drivers = await db["drivers"].find({"is_archived": {"$ne": True}}, {"_id": 0}).to_list(limit)
    rows = []
    for d in drivers:
        try:
            r = await blueprint_v1_readiness(db, d["id"])
        except Exception:
            continue
        items = r.get("items", [])
        rows.append({
            "driver_id": d["id"],
            "driver_full_name": d.get("full_name") or d.get("name"),
            "readiness": r.get("readiness"),
            "complete_count": sum(1 for i in items if i.get("complete")),
            "missing_count": sum(1 for i in items if not i.get("complete")),
        })
    # apply filters manually
    fmap = REPORT_SOURCES["activation-readiness"].field_map()
    for flt in req.filters:
        f = fmap[flt.field]
        rows = [r for r in rows if _match(r.get(flt.field), flt.operator, flt.value, f.type)]
    for s in reversed(req.sort):
        rows.sort(key=lambda x: (x.get(s.field) is None, x.get(s.field)),
                    reverse=(s.direction == "desc"))
    return rows[:limit]


def _match(cell, op, v, ftype) -> bool:
    if op == "is_empty":     return cell in (None, "", [])
    if op == "is_not_empty": return cell not in (None, "", [])
    if cell is None:
        return False
    if op == "equals":       return cell == v
    if op == "not_equals":   return cell != v
    if op == "contains":     return str(v or "").lower() in str(cell).lower()
    if op == "starts_with":  return str(cell).lower().startswith(str(v or "").lower())
    try:
        if op in ("greater_than", "after"):     return cell > v
        if op in ("less_than", "before"):       return cell < v
        if op == "greater_or_equal":            return cell >= v
        if op == "less_or_equal":               return cell <= v
    except TypeError:
        return False
    return False


# ─────────────────────────────────────────────────────────────────────────
# Company display resolution
# ─────────────────────────────────────────────────────────────────────────
async def _company_name_cache(db) -> Dict[str, str]:
    docs = await db["companies"].find({}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    return {d["id"]: d["name"] for d in docs if d.get("id")}


def _resolve_display(row: Dict[str, Any], selected_keys: List[str], companies: Dict[str, str]) -> Dict[str, Any]:
    """When company_id is selected, replace the value with the resolved
    Company name (fallback company_ref then blank). Original id is not
    returned unless explicitly requested elsewhere."""
    out = {k: row.get(k) for k in selected_keys}
    if "company_id" in out:
        cid = out.get("company_id")
        if cid and cid in companies:
            out["company_id"] = companies[cid]
        elif not cid and row.get("company_ref"):
            out["company_id"] = row["company_ref"]
    return out


# ─────────────────────────────────────────────────────────────────────────
# CSV / XLSX
# ─────────────────────────────────────────────────────────────────────────
def _neutralise_formula(v: Any) -> Any:
    """Neutralise leading =, +, -, @ to prevent spreadsheet formula injection."""
    if not isinstance(v, str):
        return v
    if v and v[0] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _row_to_display(row: Dict[str, Any], selected: List[Field_]) -> List[Any]:
    out = []
    for f in selected:
        v = row.get(f.key)
        if v is None:
            out.append("")
        else:
            out.append(_neutralise_formula(v))
    return out


def _build_csv(rows: List[Dict[str, Any]], selected: List[Field_]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([f.label for f in selected])
    for r in rows:
        w.writerow(_row_to_display(r, selected))
    return buf.getvalue().encode("utf-8")


def _build_xlsx(rows: List[Dict[str, Any]], selected: List[Field_], sheet_title: str) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    # sanitise sheet title (max 31 chars, no special chars)
    ws.title = re.sub(r"[\\\/\?\*\[\]:]", "_", (sheet_title or "Report"))[:31] or "Report"
    ws.append([f.label for f in selected])
    for r in rows:
        ws.append(_row_to_display(r, selected))
    # freeze header + autofilter + reasonable column widths
    ws.freeze_panes = "A2"
    if rows:
        end_col_letter = ws.cell(row=1, column=len(selected)).column_letter
        ws.auto_filter.ref = f"A1:{end_col_letter}{len(rows) + 1}"
    for idx, f in enumerate(selected, start=1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = max(12, min(40, len(f.label) + 4))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────
def build_router(db, get_current_user):
    router = APIRouter(prefix="/api")
    from storage_module import get_storage_service

    @router.get("/reports/sources")
    async def list_sources(current=Depends(get_current_user)):
        # every authenticated user sees the list; per-source field filtering
        # happens in /fields.
        return [{"key": s.key, "label": s.label} for s in REPORT_SOURCES.values()]

    @router.get("/reports/sources/{source}/fields")
    async def get_fields(source: str, current=Depends(get_current_user)):
        src = REPORT_SOURCES.get(source)
        if not src:
            raise HTTPException(status_code=400, detail=f"Unknown source '{source}'")
        role = current.get("role") or ""
        visible = _role_visible_fields(src, role)
        return {
            "source": src.key,
            "label": src.label,
            "fields": [f.model_dump() for f in visible],
            "operators": {k: sorted(list(v)) for k, v in OPS_BY_TYPE.items()},
        }

    async def _run(req: RunRequest, current: dict, limit: int) -> Dict[str, Any]:
        role = current.get("role") or ""
        src, selected = _validate_request(req, role)
        rows = await _fetch_rows(db, src, selected, req, role, limit + 1)
        truncated = len(rows) > limit
        rows = rows[:limit]
        companies = await _company_name_cache(db) if any(f.key == "company_id" for f in selected) else {}
        display_rows = [_resolve_display(r, [f.key for f in selected], companies) for r in rows]
        return {
            "source": src.key,
            "fields": [f.model_dump() for f in selected],
            "rows": display_rows,
            "row_count": len(display_rows),
            "truncated": truncated,
            "generated_at": _iso(),
        }

    @router.post("/reports/run")
    async def run_report(payload: RunRequest, current=Depends(get_current_user)):
        return await _run(payload, current, payload.limit)

    async def _record_export(current, payload, fmt, storage_object_id, checksum, row_count):
        role = current.get("role") or ""
        # Never store sensitive field VALUES. We store field keys only.
        rec = {
            "id": _uuid(),
            "source": payload.source,
            "format": fmt,
            "selected_fields": list(payload.fields),
            "filters": [f.model_dump() for f in payload.filters],
            "sort": [s.model_dump() for s in payload.sort],
            "generated_by": current.get("email"),
            "generated_role": role,
            "generated_at": _iso(),
            "storage_object_id": storage_object_id,
            "checksum": checksum,
            "row_count": row_count,
        }
        await db[REPORTS_EXPORT_COLL].insert_one(rec)
        rec.pop("_id", None)
        return rec

    async def _export(payload: RunRequest, current, fmt: str):
        role = current.get("role") or ""
        src, selected = _validate_request(payload, role)
        # bounded export scan
        limit = min(MAX_EXPORT_ROWS, MAX_EXPORT_ROWS)
        rows = await _fetch_rows(db, src, selected, payload, role, limit)
        companies = await _company_name_cache(db) if any(f.key == "company_id" for f in selected) else {}
        display_rows = [_resolve_display(r, [f.key for f in selected], companies) for r in rows]
        if fmt == "csv":
            data = _build_csv(display_rows, selected)
            content_type = "text/csv"
            ext = "csv"
        else:
            data = _build_xlsx(display_rows, selected, sheet_title=src.label)
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = "xlsx"
        filename = f"report-{src.key}-{_iso().replace(':', '').replace('-', '')[:15]}.{ext}"
        # Store via canonical StorageAdapter
        svc = get_storage_service(db)
        put_result = await svc.put(
            entity_type="Report", entity_id=None,
            filename=filename, content=data, content_type=content_type,
            actor_email=current.get("email") or "system",
            retention_class="Operational Document",
            validate=False,  # Report Builder does its own content validation.
        )
        import hashlib
        checksum = hashlib.sha256(data).hexdigest()
        rec = await _record_export(current, payload, fmt,
                                     put_result["storage_object_id"], checksum,
                                     len(display_rows))
        return {
            "export": rec,
            "filename": filename,
            "content_type": content_type,
            "row_count": len(display_rows),
            # inline the bytes so the caller can download without a second round-trip.
            # Downloading via /reports/exports/{id}/download is also available.
        }

    @router.post("/reports/export/csv")
    async def export_csv(payload: RunRequest, current=Depends(get_current_user)):
        return await _export(payload, current, "csv")

    @router.post("/reports/export/xlsx")
    async def export_xlsx(payload: RunRequest, current=Depends(get_current_user)):
        return await _export(payload, current, "xlsx")

    @router.get("/reports/exports")
    async def list_exports(current=Depends(get_current_user)):
        role = current.get("role") or ""
        q: Dict[str, Any] = {}
        if role not in {"Admin", "Manager"}:
            q["generated_by"] = current.get("email")
        rows = await db[REPORTS_EXPORT_COLL].find(q, {"_id": 0}).sort("generated_at", -1).to_list(500)
        return rows

    @router.get("/reports/exports/{export_id}/download")
    async def download_export(export_id: str, current=Depends(get_current_user)):
        rec = await db[REPORTS_EXPORT_COLL].find_one({"id": export_id}, {"_id": 0})
        if not rec:
            raise HTTPException(status_code=404, detail="Export not found")
        role = current.get("role") or ""
        # Authorisation: creator or Admin/Manager.
        if role not in {"Admin", "Manager"} and rec.get("generated_by") != current.get("email"):
            raise HTTPException(status_code=403, detail="Not authorised to download this export")
        svc = get_storage_service(db)
        data = await svc.get_bytes(rec["storage_object_id"], current.get("email") or "system")
        content_type = "text/csv" if rec.get("format") == "csv" else \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return Response(content=data, media_type=content_type)

    return router
