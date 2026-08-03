from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict


# ----------- MongoDB connection -----------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ----------- Config -----------
JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24h for ops prototype

ROLES = ["Admin", "Allocator", "Compliance", "Manager", "ReadOnly"]

# Module -> Mongo collection mapping
MODULE_COLLECTIONS = {
    "drivers": "drivers",
    "licences": "licences",
    "truck-rego": "truck_regos",
    "insurance": "insurances",
    "equipment": "equipment",
    "maintenance": "maintenance",
    "tilt-trays": "tilt_trays",
    "onboarding": "onboarding",
}

# ----------- FastAPI app -----------
app = FastAPI(title="ACE Driver Hub API")
api_router = APIRouter(prefix="/api")
bearer_scheme = HTTPBearer(auto_error=False)


# ----------- Models -----------
class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: EmailStr
    full_name: str
    role: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "ReadOnly"


# ----------- Password helpers -----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ----------- JWT helpers -----------
def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    token = None
    if creds and creds.scheme.lower() == "bearer":
        token = creds.credentials
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ----------- Auth endpoints -----------
@api_router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    user_public = {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "created_at": user["created_at"],
    }
    return {"access_token": token, "token_type": "bearer", "user": user_public}


@api_router.post("/auth/register", response_model=UserPublic)
async def register(payload: RegisterRequest, current=Depends(get_current_user)):
    if current["role"] != "Admin":
        raise HTTPException(status_code=403, detail="Only admins can create users")
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {ROLES}")
    email = payload.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(payload.password),
        "full_name": payload.full_name,
        "role": payload.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    return {
        "id": user_doc["id"],
        "email": user_doc["email"],
        "full_name": user_doc["full_name"],
        "role": user_doc["role"],
        "created_at": user_doc["created_at"],
    }


@api_router.get("/auth/me", response_model=UserPublic)
async def me(current=Depends(get_current_user)):
    return current


# ----------- Generic Module CRUD -----------
def _validate_resource(resource: str):
    if resource not in MODULE_COLLECTIONS:
        raise HTTPException(status_code=404, detail=f"Unknown module: {resource}")
    return MODULE_COLLECTIONS[resource]


@api_router.get("/modules/{resource}")
async def list_module_items(resource: str, current=Depends(get_current_user)):
    coll_name = _validate_resource(resource)
    items = await db[coll_name].find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@api_router.post("/modules/{resource}")
async def create_module_item(resource: str, payload: dict, current=Depends(get_current_user)):
    coll_name = _validate_resource(resource)
    if current["role"] == "ReadOnly":
        raise HTTPException(status_code=403, detail="ReadOnly role cannot create")
    doc = dict(payload or {})
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = doc["created_at"]
    doc["created_by"] = current["email"]
    await db[coll_name].insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/modules/{resource}/{item_id}")
async def update_module_item(resource: str, item_id: str, payload: dict, current=Depends(get_current_user)):
    coll_name = _validate_resource(resource)
    if current["role"] == "ReadOnly":
        raise HTTPException(status_code=403, detail="ReadOnly role cannot update")
    update = {k: v for k, v in (payload or {}).items() if k not in ("id", "_id", "created_at", "created_by")}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current["email"]
    result = await db[coll_name].update_one({"id": item_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    doc = await db[coll_name].find_one({"id": item_id}, {"_id": 0})
    return doc


@api_router.delete("/modules/{resource}/{item_id}")
async def delete_module_item(resource: str, item_id: str, current=Depends(get_current_user)):
    coll_name = _validate_resource(resource)
    if current["role"] not in ("Admin", "Manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions to delete")
    result = await db[coll_name].delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "deleted", "id": item_id}


@api_router.get("/modules/{resource}/{item_id}")
async def get_module_item(resource: str, item_id: str, current=Depends(get_current_user)):
    coll_name = _validate_resource(resource)
    doc = await db[coll_name].find_one({"id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found")
    return doc


# ----------- Stats endpoint for hub overview -----------
@api_router.get("/stats/overview")
async def stats_overview(current=Depends(get_current_user)):
    out = {}
    for slug, coll in MODULE_COLLECTIONS.items():
        out[slug] = await db[coll].count_documents({})
    return out


# ----------- Compliance: Expiring Soon -----------
COMPLIANCE_MODULES = ["licences", "truck-rego", "insurance"]


def _classify_expiry(expiry_str: Optional[str], today: datetime, horizon_days: int = 30):
    """Return ('expired'|'expiring'|'ok'|'unknown', days_until). Negative days => expired."""
    if not expiry_str:
        return ("unknown", None)
    try:
        # Accept ISO date or datetime
        d = datetime.fromisoformat(str(expiry_str).replace("Z", "+00:00"))
    except ValueError:
        return ("unknown", None)
    # Normalize to date-only comparison
    exp_date = d.date() if hasattr(d, "date") else d
    today_date = today.date()
    delta = (exp_date - today_date).days
    if delta < 0:
        return ("expired", delta)
    if delta <= horizon_days:
        return ("expiring", delta)
    return ("ok", delta)


@api_router.get("/compliance/expiring")
async def compliance_expiring(current=Depends(get_current_user), horizon: int = 30):
    """Return rollup counts + per-record details for licences / truck-rego / insurance."""
    today = datetime.now(timezone.utc)
    # Build a driver_id -> name lookup so records can show the canonical driver name
    drivers = await db.drivers.find({}, {"_id": 0, "id": 1, "name": 1, "full_name": 1}).to_list(2000)
    driver_name_by_id = {d["id"]: (d.get("name") or d.get("full_name") or "") for d in drivers}

    result = {
        "horizon_days": horizon,
        "totals": {"expired": 0, "expiring": 0, "ok": 0, "unknown": 0},
        "modules": {},
        "records": [],  # flat list of expired + expiring across modules
    }
    for slug in COMPLIANCE_MODULES:
        coll = db[MODULE_COLLECTIONS[slug]]
        docs = await coll.find({}, {"_id": 0}).to_list(2000)
        per_mod = {"expired": 0, "expiring": 0, "ok": 0, "unknown": 0, "total": len(docs)}
        for d in docs:
            status, days = _classify_expiry(d.get("expiry_date"), today, horizon)
            per_mod[status] += 1
            result["totals"][status] += 1
            if status in ("expired", "expiring"):
                # Canonical driver name from driver_id, fallback to legacy text field
                driver_id = d.get("driver_id")
                driver_name = driver_name_by_id.get(driver_id) if driver_id else None
                if not driver_name:
                    driver_name = d.get("driver_name") or ""
                result["records"].append({
                    "module": slug,
                    "id": d.get("id"),
                    "status": status,
                    "days_until": days,
                    "expiry_date": d.get("expiry_date"),
                    "driver_id": driver_id,
                    "driver_name": driver_name,
                    "title": driver_name or d.get("rego_number") or d.get("policy_number") or "Record",
                    "subtitle": d.get("licence_number") or d.get("rego_number") or d.get("policy_number") or "",
                    "extra": d.get("provider") or d.get("make") or d.get("licence_class") or "",
                })
        result["modules"][slug] = per_mod

    # Sort records: expired first (most overdue), then expiring soonest
    result["records"].sort(key=lambda r: (0 if r["status"] == "expired" else 1, r["days_until"] if r["days_until"] is not None else 9999))
    return result


# ----------- Driver Profile (driver + linked records) -----------
# Maps each module slug -> field on the record that points back to a driver
DRIVER_LINK_FIELD = "driver_id"
DRIVER_LINKED_MODULES = [
    "licences",
    "truck-rego",
    "insurance",
    "equipment",
    "maintenance",
    "tilt-trays",
    "onboarding",
]


@api_router.get("/drivers/{driver_id}/profile")
async def driver_profile(driver_id: str, current=Depends(get_current_user)):
    driver = await db.drivers.find_one({"id": driver_id}, {"_id": 0})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    linked = {}
    for slug in DRIVER_LINKED_MODULES:
        coll = db[MODULE_COLLECTIONS[slug]]
        docs = await coll.find(
            {DRIVER_LINK_FIELD: driver_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(500)
        linked[slug] = docs

    return {"driver": driver, "linked": linked}



# ----------- Health -----------
@api_router.get("/")
async def root():
    return {"service": "ACE Driver Hub API", "status": "ok"}


# ----------- Startup: indexes, admin seed, sample data -----------
async def seed_sample_data():
    """Seed sample data only when collections are empty."""
    samples = {
        "drivers": [
            {"name": "James Carter", "driver_number": "DRV-001", "company": "ACE Car Freighters", "phone": "+61 412 555 101", "email": "james.c@ace.com", "licence_number": "NSW-1234567", "status": "Active", "base": "Sydney"},
            {"name": "Liam O'Brien", "driver_number": "DRV-002", "company": "ACE Car Freighters", "phone": "+61 412 555 102", "email": "liam.o@ace.com", "licence_number": "VIC-2345678", "status": "Active", "base": "Melbourne"},
            {"name": "Noah Williams", "driver_number": "DRV-003", "company": "ACE Car Freighters", "phone": "+61 412 555 103", "email": "noah.w@ace.com", "licence_number": "QLD-3456789", "status": "On Leave", "base": "Brisbane"},
        ],
        "licences": [
            {"driver_name": "James Carter", "licence_number": "NSW-1234567", "licence_class": "HR", "issue_date": "2022-03-15", "expiry_date": "2027-03-15", "status": "Valid"},
            {"driver_name": "Liam O'Brien", "licence_number": "VIC-2345678", "licence_class": "MC", "issue_date": "2021-06-01", "expiry_date": "2026-06-01", "status": "Valid"},
            {"driver_name": "Noah Williams", "licence_number": "QLD-3456789", "licence_class": "HC", "issue_date": "2020-09-20", "expiry_date": "2025-09-20", "status": "Expiring Soon"},
        ],
        "truck-rego": [
            {"rego_number": "ACE-001", "driver_name": "James Carter", "make": "Kenworth", "model": "T610", "year": "2021", "expiry_date": "2026-08-12"},
            {"rego_number": "ACE-002", "driver_name": "Liam O'Brien", "make": "Volvo", "model": "FH16", "year": "2022", "expiry_date": "2026-11-30"},
        ],
        "insurance": [
            {"policy_number": "POL-887766", "driver_name": "James Carter", "provider": "NTI", "type": "Comprehensive", "expiry_date": "2026-04-30", "premium": "$4,200"},
            {"policy_number": "POL-998877", "driver_name": "Liam O'Brien", "provider": "Allianz", "type": "Heavy Vehicle", "expiry_date": "2026-09-15", "premium": "$5,100"},
        ],
        "equipment": [
            {"equipment_id": "EQ-101", "name": "Load Restraint Kit", "type": "Strapping", "assigned_to": "James Carter", "condition": "Good", "location": "Sydney Yard"},
            {"equipment_id": "EQ-102", "name": "GPS Tracker Unit", "type": "Electronics", "assigned_to": "Liam O'Brien", "condition": "Excellent", "location": "Melbourne Yard"},
        ],
        "maintenance": [
            {"vehicle_rego": "ACE-001", "service_type": "Scheduled Service", "service_date": "2026-01-15", "next_service": "2026-07-15", "mechanic": "Sydney Diesel Co", "notes": "Oil + filter, brake check"},
            {"vehicle_rego": "ACE-002", "service_type": "Defect Repair", "service_date": "2026-01-22", "next_service": "2026-04-22", "mechanic": "Vic Heavy Trucks", "notes": "Air leak in rear brake line"},
        ],
        "tilt-trays": [
            {"tray_id": "TT-A1", "rego": "TLT-555", "capacity": "8.0 tonne", "driver_assigned": "James Carter", "last_inspection": "2025-12-01", "status": "Compliant"},
            {"tray_id": "TT-A2", "rego": "TLT-556", "capacity": "10.0 tonne", "driver_assigned": "Noah Williams", "last_inspection": "2025-11-12", "status": "Compliant"},
        ],
        "onboarding": [
            {"full_name": "Ethan Brooks", "start_date": "2026-02-10", "stage": "Documents Pending", "contact": "+61 412 555 200", "documents_status": "2 of 5 received"},
            {"full_name": "Marcus Hill", "start_date": "2026-02-17", "stage": "Induction Scheduled", "contact": "+61 412 555 201", "documents_status": "5 of 5 received"},
        ],
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    for slug, rows in samples.items():
        coll = db[MODULE_COLLECTIONS[slug]]
        if await coll.count_documents({}) == 0:
            for r in rows:
                r["id"] = str(uuid.uuid4())
                r["created_at"] = now_iso
                r["updated_at"] = now_iso
                r["created_by"] = "system-seed"
            await coll.insert_many(rows)


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@acedriverhub.com").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "full_name": "ACE Administrator",
            "role": "Admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )


async def backfill_driver_ids():
    """One-time idempotent backfill: link existing records to a driver by name.

    Only updates records that don't already have a driver_id.
    """
    # Enrich seeded drivers with driver_number/company if missing
    enrichments = {
        "James Carter": {"driver_number": "DRV-001", "company": "ACE Car Freighters"},
        "Liam O'Brien": {"driver_number": "DRV-002", "company": "ACE Car Freighters"},
        "Noah Williams": {"driver_number": "DRV-003", "company": "ACE Car Freighters"},
    }
    for name, extra in enrichments.items():
        for k, v in extra.items():
            await db.drivers.update_one(
                {"name": name, k: {"$exists": False}}, {"$set": {k: v}}
            )

    drivers = await db.drivers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)
    name_to_id = {d["name"]: d["id"] for d in drivers if d.get("name")}
    if not name_to_id:
        return
    mappings = [
        ("licences", "driver_name"),
        ("truck_regos", "driver_name"),
        ("insurances", "driver_name"),
        ("equipment", "assigned_to"),
        ("tilt_trays", "driver_assigned"),
        ("onboarding", "full_name"),
    ]
    for coll_name, source_field in mappings:
        cursor = db[coll_name].find(
            {"driver_id": {"$exists": False}}, {"_id": 0, "id": 1, source_field: 1}
        )
        async for doc in cursor:
            name = doc.get(source_field)
            if name and name in name_to_id:
                await db[coll_name].update_one(
                    {"id": doc["id"]},
                    {"$set": {"driver_id": name_to_id[name]}},
                )


@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    for coll in MODULE_COLLECTIONS.values():
        await db[coll].create_index("id", unique=True)
    await seed_admin()
    await seed_sample_data()
    await backfill_driver_ids()
    # --- EB-02 Foundation Registers ---
    from registers import ensure_indexes, migrate_existing_drivers, seed_registers
    await ensure_indexes(db)
    await migrate_existing_drivers(db)
    await seed_registers(db)
    # --- EB-03 Relationships & Assignments ---
    from relationships import (
        ensure_indexes as rel_ensure_indexes,
        seed_relationships,
        startup_reconciliation,
    )
    await rel_ensure_indexes(db)
    await seed_relationships(db)
    await startup_reconciliation(db)
    # --- EB-04 Canonical Compliance Foundation ---
    from compliance_records import (
        ensure_indexes as comp_ensure_indexes,
        seed_compliance,
        startup_reconciliation as comp_reconciliation,
    )
    await comp_ensure_indexes(db)
    await seed_compliance(db)
    await comp_reconciliation(db)
    # --- EB-05 Documents & Evidence ---
    from documents_module import (
        ensure_indexes as doc_ensure_indexes,
        seed_documents,
    )
    await doc_ensure_indexes(db)
    await seed_documents(db)
    # --- EB-06 Guided Spreadsheet Import ---
    from imports_module import ensure_indexes as imp_ensure_indexes
    await imp_ensure_indexes(db)
    # --- EB-07a Notifications, Alerts & Escalation Engine ---
    from notifications_module import (
        ensure_indexes as notif_ensure_indexes,
        seed_rules as notif_seed_rules,
        seed_examples as notif_seed_examples,
    )
    await notif_ensure_indexes(db)
    await notif_seed_rules(db)
    await notif_seed_examples(db)
    # --- EB-08 Automated Numbering ---
    from numbering_module import ensure_indexes as num_ensure_indexes, seed_examples as num_seed
    await num_ensure_indexes(db)
    await num_seed(db)
    # --- EB-09 Driver Profile aggregator + notes/comms ---
    from driver_profile_module import ensure_indexes as prof_ensure_indexes, seed_eb09
    await prof_ensure_indexes(db)
    await seed_eb09(db)
    # --- EB-10 Activation & Onboarding Gate ---
    from activation_module import ensure_indexes as act_ensure_indexes, seed_default_template
    await act_ensure_indexes(db)
    await seed_default_template(db)
    # --- EB-11 Driver Exports (Start Sheet + Profile PDF) ---
    from driver_export_module import ensure_indexes as exp_ensure_indexes, seed_dev_examples as exp_seed
    await exp_ensure_indexes(db)
    await exp_seed(db)
    # --- EB-12 Migration Preparation ---
    from migration_prep_module import ensure_indexes as mp_ensure_indexes, seed_transform_rules as mp_seed_rules
    await mp_ensure_indexes(db)
    await mp_seed_rules(db)


# Include router and CORS
app.include_router(api_router)

# --- EB-02 Foundation Registers router ---
from registers import build_registers_router  # noqa: E402
app.include_router(build_registers_router(db, get_current_user))

# --- EB-03 Relationships router ---
from relationships import build_relationships_router  # noqa: E402
app.include_router(build_relationships_router(db, get_current_user))

# --- EB-04 Compliance router ---
from compliance_records import build_compliance_router  # noqa: E402
app.include_router(build_compliance_router(db, get_current_user))

# --- EB-05 Documents router ---
from documents_module import build_documents_router  # noqa: E402
app.include_router(build_documents_router(db, get_current_user))

# --- EB-06 Imports router ---
from imports_module import build_imports_router  # noqa: E402
app.include_router(build_imports_router(db, get_current_user))

# --- EB-07a Notifications router ---
from notifications_module import build_notifications_router  # noqa: E402
app.include_router(build_notifications_router(db, get_current_user))

# --- EB-08 Numbering router ---
from numbering_module import build_numbering_router  # noqa: E402
app.include_router(build_numbering_router(db, get_current_user))

# --- EB-09 Driver Profile aggregator router ---
from driver_profile_module import build_driver_profile_router  # noqa: E402
app.include_router(build_driver_profile_router(db, get_current_user))

# --- EB-10 Activation & Onboarding Gate ---
from activation_module import build_activation_router  # noqa: E402
app.include_router(build_activation_router(db, get_current_user))

# --- EB-11 Driver Exports ---
from driver_export_module import build_driver_export_router  # noqa: E402
app.include_router(build_driver_export_router(db, get_current_user))

# --- EB-12 Migration Preparation ---
from migration_prep_module import build_migration_prep_router  # noqa: E402
app.include_router(build_migration_prep_router(db, get_current_user))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
