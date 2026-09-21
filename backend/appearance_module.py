"""MR-08B-P4 · Appearance (Theme scaffold + Global Skin).

Two orthogonal concerns co-located because they share the ``Appearance``
surface:

* THEME — per-user light/dark preference, persisted in
  ``user_preferences``. Default = light. Dark preference persists but is
  NOT visually applied in V1 (MR-08B-P4-DARK will own that work).
* SKIN  — one GLOBAL branding record stored in ``app_settings`` under
  ``key="skin"``. Contains ``logo_storage_object_id`` and ``accent_colour``.
  Logo bytes live in the canonical StorageAdapter (never in settings).

No parallel security constants — role gating uses ``role_matrix``.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, field_validator

USER_PREF_COLL = "user_preferences"
APP_SETTINGS_COLL = "app_settings"
SKIN_KEY = "skin"

VALID_THEMES = {"light", "dark"}
DEFAULT_THEME = "light"

# Accent must be a six-digit hex. No CSS, no gradients, no rgba.
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Logo file constraints.
LOGO_MAX_BYTES = 512 * 1024  # 512 KB is plenty for a brand mark.
LOGO_ALLOWED_MIME = {"image/png", "image/jpeg"}
LOGO_PNG_SIG = b"\x89PNG\r\n\x1a\n"
LOGO_JPEG_SIG = b"\xff\xd8\xff"

# Roles that may mutate Skin (READ is available to all authenticated roles).
SKIN_WRITE_ROLES = {"Admin", "Manager"}


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_hex(v: str) -> str:
    v = (v or "").strip()
    if not _HEX_RE.match(v):
        raise HTTPException(status_code=400,
                             detail="accent_colour must be a #RRGGBB hex value")
    return "#" + v[1:].upper()


# ─────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────
class ThemePayload(BaseModel):
    theme: str

    @field_validator("theme")
    @classmethod
    def _validate(cls, v):
        v = (v or "").strip().lower()
        if v not in VALID_THEMES:
            raise ValueError("theme must be 'light' or 'dark'")
        return v


class SkinPayload(BaseModel):
    accent_colour: Optional[str] = None

    @field_validator("accent_colour")
    @classmethod
    def _validate(cls, v):
        if v is None:
            return None
        return _normalise_hex(v)


# ─────────────────────────────────────────────────────────────────────────
# Skin persistence helpers (used by PDF renderer / driver_export_module)
# ─────────────────────────────────────────────────────────────────────────
async def load_skin(db) -> dict:
    """Return the current Skin document as a plain dict. Never raises;
    callers are expected to fall back on missing/invalid fields."""
    doc = await db[APP_SETTINGS_COLL].find_one({"key": SKIN_KEY}, {"_id": 0}) or {}
    return {
        "accent_colour": doc.get("accent_colour"),
        "logo_storage_object_id": doc.get("logo_storage_object_id"),
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }


async def load_skin_logo_bytes(db, actor_email: str = "system") -> Optional[bytes]:
    """Return raw logo bytes if a Skin logo is configured and readable.
    Any failure yields ``None`` so PDF generation may fall back safely."""
    try:
        skin = await load_skin(db)
        obj_id = skin.get("logo_storage_object_id")
        if not obj_id:
            return None
        from storage_module import get_storage_service
        svc = get_storage_service(db)
        return await svc.get_bytes(obj_id, actor_email, mode="internal")
    except Exception:  # noqa: BLE001 — Skin fetch never blocks PDFs
        return None


# ─────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────
def build_router(db, get_current_user):
    router = APIRouter(prefix="/api")

    # ---- Theme (per-user) ------------------------------------------------
    @router.get("/user-preferences/theme")
    async def get_theme(current=Depends(get_current_user)):
        uid = current.get("id")
        pref = await db[USER_PREF_COLL].find_one({"user_id": uid}, {"_id": 0}) or {}
        theme = pref.get("theme") if pref.get("theme") in VALID_THEMES else DEFAULT_THEME
        return {"theme": theme}

    @router.put("/user-preferences/theme")
    async def set_theme(payload: ThemePayload, current=Depends(get_current_user)):
        uid = current.get("id")
        now = _iso()
        await db[USER_PREF_COLL].update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "theme": payload.theme,
                       "updated_at": now, "updated_by": current.get("email")}},
            upsert=True,
        )
        return {"theme": payload.theme}

    # ---- Skin (global) ---------------------------------------------------
    def _require_skin_write(current):
        role = current.get("role") or ""
        if role not in SKIN_WRITE_ROLES:
            raise HTTPException(status_code=403,
                                 detail="Skin mutation requires Admin or Manager")

    def _sanitise_skin(doc: dict) -> dict:
        """Never expose raw storage keys."""
        return {
            "accent_colour": doc.get("accent_colour"),
            "logo_storage_object_id": doc.get("logo_storage_object_id"),
            "has_logo": bool(doc.get("logo_storage_object_id")),
            "updated_at": doc.get("updated_at"),
            "updated_by": doc.get("updated_by"),
        }

    @router.get("/settings/skin")
    async def get_skin(current=Depends(get_current_user)):
        return _sanitise_skin(await load_skin(db))

    @router.put("/settings/skin")
    async def put_skin(payload: SkinPayload, current=Depends(get_current_user)):
        _require_skin_write(current)
        now = _iso()
        set_fields = {"updated_at": now, "updated_by": current.get("email")}
        if payload.accent_colour is not None:
            set_fields["accent_colour"] = payload.accent_colour
        await db[APP_SETTINGS_COLL].update_one(
            {"key": SKIN_KEY},
            {"$set": {"key": SKIN_KEY, **set_fields}},
            upsert=True,
        )
        return _sanitise_skin(await load_skin(db))

    @router.post("/settings/skin/logo")
    async def upload_logo(file: UploadFile = File(...),
                           current=Depends(get_current_user)):
        _require_skin_write(current)
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty upload")
        if len(raw) > LOGO_MAX_BYTES:
            raise HTTPException(status_code=400,
                                 detail=f"Logo exceeds max size {LOGO_MAX_BYTES} bytes")
        mime = (file.content_type or "").lower()
        if mime not in LOGO_ALLOWED_MIME:
            raise HTTPException(status_code=400,
                                 detail="Logo must be image/png or image/jpeg")
        # Signature check — reject spoofed content types.
        if mime == "image/png" and not raw.startswith(LOGO_PNG_SIG):
            raise HTTPException(status_code=400, detail="PNG signature mismatch")
        if mime == "image/jpeg" and not raw.startswith(LOGO_JPEG_SIG):
            raise HTTPException(status_code=400, detail="JPEG signature mismatch")

        from storage_module import get_storage_service
        svc = get_storage_service(db)
        put_res = await svc.put(
            entity_type="AppearanceSkin", entity_id="global",
            filename=file.filename or f"logo-{uuid.uuid4().hex[:8]}",
            content=raw, content_type=mime,
            actor_email=current.get("email") or "system",
            retention_class="Operational Document",
            validate=False,  # module enforces its own image validation
        )
        now = _iso()
        await db[APP_SETTINGS_COLL].update_one(
            {"key": SKIN_KEY},
            {"$set": {
                "key": SKIN_KEY,
                "logo_storage_object_id": put_res["storage_object_id"],
                "updated_at": now,
                "updated_by": current.get("email"),
            }},
            upsert=True,
        )
        return _sanitise_skin(await load_skin(db))

    @router.delete("/settings/skin/logo")
    async def delete_logo(current=Depends(get_current_user)):
        _require_skin_write(current)
        now = _iso()
        await db[APP_SETTINGS_COLL].update_one(
            {"key": SKIN_KEY},
            {"$set": {"key": SKIN_KEY,
                        "logo_storage_object_id": None,
                        "updated_at": now,
                        "updated_by": current.get("email")}},
            upsert=True,
        )
        return _sanitise_skin(await load_skin(db))

    @router.get("/settings/skin/logo")
    async def get_logo(current=Depends(get_current_user)):
        raw = await load_skin_logo_bytes(db, current.get("email") or "system")
        if raw is None:
            raise HTTPException(status_code=404, detail="No Skin logo configured")
        media = "image/png" if raw.startswith(LOGO_PNG_SIG) else \
                 "image/jpeg" if raw.startswith(LOGO_JPEG_SIG) else "application/octet-stream"
        return Response(content=raw, media_type=media)

    return router
