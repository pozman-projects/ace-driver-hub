"""MR-08B-P2 · Canonical Company Manager + Default Company.

Single source of truth for the Company entity across the ACE Driver
Command Centre. Registers (Driver/Owner/Vehicle/Equipment) reference
Company through an immutable ``company_id``. The pre-existing free-text
``company_ref`` field is preserved as a compatibility mirror for legacy
records only — new writes always resolve through this module.

Locked owner decisions in MR-08B-P2:
    * ONE global persisted Default Company (not per-user).
    * Changing Default affects NEW records only. Existing records
      are NEVER rewritten.
    * Admin / Manager may mutate; other roles read only.
    * Default Company cannot be archived; another active Company must
      be selected as default first.
    * No retroactive migration of existing ``company_ref`` values.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator


COMPANIES_COLL = "companies"
APP_SETTINGS_COLL = "app_settings"
DEFAULT_COMPANY_KEY = "default_company"
ACE_COMPANY_NAME = "ACE Car Freighters"


# ────────────────────────────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────────────────────────────
class CompanyBase(BaseModel):
    name: str
    is_active: bool = True
    is_archived: bool = False


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name is required")
        return v


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _clean(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v


class CompanyRead(BaseModel):
    id: str
    name: str
    is_active: bool
    is_archived: bool
    created_at: str
    created_by: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class SetDefaultBody(BaseModel):
    company_id: str


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────
def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _norm_name(name: str) -> str:
    return " ".join((name or "").strip().split()).casefold()


async def _get_company(db, company_id: str) -> Dict[str, Any]:
    doc = await db[COMPANIES_COLL].find_one({"id": company_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    return doc


async def _find_active_by_name(db, name: str, exclude_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    q: Dict[str, Any] = {"is_active": True, "is_archived": False}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    rows = await db[COMPANIES_COLL].find(q, {"_id": 0}).to_list(1000)
    n = _norm_name(name)
    for r in rows:
        if _norm_name(r.get("name", "")) == n:
            return r
    return None


async def resolve_default_company(db) -> Optional[Dict[str, Any]]:
    """Return the current Default Company doc (or None). Public helper
    for other modules that need to apply the default at record-creation
    time."""
    setting = await db[APP_SETTINGS_COLL].find_one(
        {"key": DEFAULT_COMPANY_KEY}, {"_id": 0}
    )
    if not setting or not setting.get("company_id"):
        return None
    doc = await db[COMPANIES_COLL].find_one(
        {"id": setting["company_id"]}, {"_id": 0}
    )
    if not doc or doc.get("is_archived") or not doc.get("is_active", True):
        return None
    return doc


async def resolve_company(db, company_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return an active, non-archived Company or None. Used when
    validating supplied company_id on register writes."""
    if not company_id:
        return None
    doc = await db[COMPANIES_COLL].find_one({"id": company_id}, {"_id": 0})
    return doc


async def validate_supplied_company(db, payload: Dict[str, Any]) -> None:
    """MR-08B-P2 helper for UPDATE paths. If ``payload`` contains
    ``company_id``, verify the target Company exists, is active, and is
    not archived. Never injects a default. If ``company_id`` is not in
    the payload this is a no-op — legacy records without a canonical
    Company ID are left untouched by unrelated field edits."""
    if "company_id" not in payload:
        return
    supplied = payload.get("company_id")
    if not supplied:
        return
    c = await resolve_company(db, supplied)
    if not c:
        raise HTTPException(status_code=400,
                            detail=f"Company {supplied} not found")
    if c.get("is_archived") or not c.get("is_active", True):
        raise HTTPException(status_code=409,
                            detail=f"Company {supplied} is archived or inactive")


async def apply_default_company_if_missing(db, payload: Dict[str, Any]) -> Dict[str, Any]:
    """MR-08B-P2 helper for CREATE paths only.

    Given a mutable ``payload`` dict about to be inserted as a canonical
    register row, resolve/inject Company data:

    * If caller supplied ``company_id``: validate it. Reject if unknown /
      archived / inactive. Mirror the canonical name into ``company_ref``.
    * If caller omitted ``company_id``: read the Default Company and
      inject its id + name mirror. If there is no default, leave the
      field unset (do not use a hardcoded string).
    """
    supplied = payload.get("company_id")
    if supplied:
        c = await resolve_company(db, supplied)
        if not c:
            raise HTTPException(status_code=400,
                                detail=f"Company {supplied} not found")
        if c.get("is_archived") or not c.get("is_active", True):
            raise HTTPException(status_code=409,
                                detail=f"Company {supplied} is archived or inactive")
        payload["company_id"] = c["id"]
        # legacy display mirror — never authoritative
        if not payload.get("company_ref"):
            payload["company_ref"] = c["name"]
        return payload
    default = await resolve_default_company(db)
    if default:
        payload["company_id"] = default["id"]
        if not payload.get("company_ref"):
            payload["company_ref"] = default["name"]
    return payload


# ────────────────────────────────────────────────────────────────────────
# Seed
# ────────────────────────────────────────────────────────────────────────
async def seed_company_registry(db, actor: str = "system") -> None:
    """Idempotent bootstrap. Ensures at least one canonical Company exists
    (ACE Car Freighters) and that the Default Company setting points at
    it if no default is already configured.

    Runs on backend startup. Never overwrites an existing configured
    default. Never creates duplicates."""
    existing = await _find_active_by_name(db, ACE_COMPANY_NAME)
    if not existing:
        now = _iso()
        doc = {
            "id": _uuid(),
            "name": ACE_COMPANY_NAME,
            "is_active": True,
            "is_archived": False,
            "created_at": now,
            "created_by": actor,
            "updated_at": now,
            "updated_by": actor,
        }
        await db[COMPANIES_COLL].insert_one(doc)
        existing = doc

    setting = await db[APP_SETTINGS_COLL].find_one(
        {"key": DEFAULT_COMPANY_KEY}, {"_id": 0}
    )
    if setting and setting.get("company_id"):
        current = await db[COMPANIES_COLL].find_one(
            {"id": setting["company_id"], "is_archived": {"$ne": True}},
            {"_id": 0},
        )
        if current:
            return  # existing default is still valid — do not touch
    # No default configured (or the configured default is missing/archived)
    # → point at the ACE seed record.
    await db[APP_SETTINGS_COLL].update_one(
        {"key": DEFAULT_COMPANY_KEY},
        {"$set": {
            "key": DEFAULT_COMPANY_KEY,
            "company_id": existing["id"],
            "updated_at": _iso(),
            "updated_by": actor,
        }},
        upsert=True,
    )


# ────────────────────────────────────────────────────────────────────────
# Router
# ────────────────────────────────────────────────────────────────────────
def build_router(db, get_current_user):
    router = APIRouter(prefix="/api")

    def _require_manage(user):
        # MR-07B canonical set for Company administration.
        if user.get("role") not in {"Admin", "Manager"}:
            raise HTTPException(
                status_code=403,
                detail="Only Admin or Manager may administer Companies",
            )

    # ------------- Company CRUD -----------------------------------------
    @router.get("/companies")
    async def list_companies(include_archived: bool = False,
                             current=Depends(get_current_user)):
        q: Dict[str, Any] = {} if include_archived else {"is_archived": {"$ne": True}}
        docs = await db[COMPANIES_COLL].find(q, {"_id": 0}).sort("name", 1).to_list(1000)
        default = await resolve_default_company(db)
        default_id = default["id"] if default else None
        return [{**d, "is_default": d["id"] == default_id} for d in docs]

    @router.get("/companies/{company_id}", response_model=CompanyRead)
    async def get_company(company_id: str, current=Depends(get_current_user)):
        return await _get_company(db, company_id)

    @router.post("/companies", response_model=CompanyRead)
    async def create_company(payload: CompanyCreate, current=Depends(get_current_user)):
        _require_manage(current)
        dup = await _find_active_by_name(db, payload.name)
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"An active Company named '{dup['name']}' already exists",
            )
        now = _iso()
        doc = {
            "id": _uuid(),
            "name": payload.name.strip(),
            "is_active": True,
            "is_archived": False,
            "created_at": now,
            "created_by": current.get("email"),
            "updated_at": now,
            "updated_by": current.get("email"),
        }
        await db[COMPANIES_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.put("/companies/{company_id}", response_model=CompanyRead)
    async def update_company(company_id: str, payload: CompanyUpdate,
                              current=Depends(get_current_user)):
        _require_manage(current)
        existing = await _get_company(db, company_id)
        if existing.get("is_archived"):
            raise HTTPException(status_code=409, detail="Company is archived")
        updates = payload.model_dump(exclude_unset=True)
        if "name" in updates and updates["name"]:
            dup = await _find_active_by_name(db, updates["name"], exclude_id=company_id)
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail=f"An active Company named '{dup['name']}' already exists",
                )
        updates["updated_at"] = _iso()
        updates["updated_by"] = current.get("email")
        await db[COMPANIES_COLL].update_one({"id": company_id}, {"$set": updates})
        return await _get_company(db, company_id)

    @router.delete("/companies/{company_id}")
    async def archive_company(company_id: str, current=Depends(get_current_user)):
        _require_manage(current)
        existing = await _get_company(db, company_id)
        default = await resolve_default_company(db)
        if default and default["id"] == company_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "COMPANY_IS_DEFAULT",
                    "message": ("This Company is the current Default Company. "
                                 "Set another active Company as the Default before archiving."),
                },
            )
        await db[COMPANIES_COLL].update_one(
            {"id": company_id},
            {"$set": {
                "is_active": False,
                "is_archived": True,
                "updated_at": _iso(),
                "updated_by": current.get("email"),
            }},
        )
        return {"id": company_id, "is_archived": True}

    # ------------- Default Company --------------------------------------
    @router.get("/settings/default-company")
    async def get_default(current=Depends(get_current_user)):
        default = await resolve_default_company(db)
        if not default:
            return {"company_id": None, "company": None}
        return {"company_id": default["id"], "company": default}

    @router.put("/settings/default-company")
    async def set_default(body: SetDefaultBody, current=Depends(get_current_user)):
        _require_manage(current)
        c = await db[COMPANIES_COLL].find_one({"id": body.company_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail=f"Company {body.company_id} not found")
        if c.get("is_archived") or not c.get("is_active", True):
            raise HTTPException(
                status_code=409,
                detail="Default Company must be active and not archived",
            )
        await db[APP_SETTINGS_COLL].update_one(
            {"key": DEFAULT_COMPANY_KEY},
            {"$set": {
                "key": DEFAULT_COMPANY_KEY,
                "company_id": body.company_id,
                "updated_at": _iso(),
                "updated_by": current.get("email"),
            }},
            upsert=True,
        )
        return {"company_id": body.company_id, "company": c}

    return router
