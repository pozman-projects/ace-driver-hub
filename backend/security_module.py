"""EB-17a · Security Foundation.

Parts 1-9:
  1. Security Control Centre backing collections + control catalogue
  2. Security assessment engine (posture, findings, runs, snapshots)
  3. Authentication + session hardening checks
  4. RBAC audit + complete permission matrix generator
  5. API security validation (auth/role coverage, unsafe verbs)
  6. Secrets / environment validation (leak scan, config snapshot)
  7. Privacy + sensitive-data audit (PII/restricted-field inventory)
  8. Audit-log integrity (append-only assertions)
  9. Security exception workflow (request -> approve/reject -> expire/revoke)

Rules honoured:
  - Fictional/sanitized data only. No live providers, no real ACE data.
  - No cron loops. Assessments are manual + idempotent per correlation id.
  - No test uses external preview URLs.
"""
from __future__ import annotations

import inspect
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
# Collections
# ═══════════════════════════════════════════════════════════════════════
CTRL_COLL = "security_control_definitions"
RUN_COLL = "security_assessment_runs"
FIND_COLL = "security_assessment_findings"
EVENT_COLL = "security_assessment_events"
SNAP_COLL = "security_configuration_snapshots"
EXC_REQ_COLL = "security_exception_requests"
EXC_APR_COLL = "security_exception_approvals"


ROLE_READONLY = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}
ROLE_ALLOCATOR = {"Allocator", "Compliance", "Manager", "Admin"}
ROLE_COMPLIANCE = {"Compliance", "Manager", "Admin"}
ROLE_MANAGER = {"Manager", "Admin"}
ROLE_ADMIN = {"Admin"}

SEVERITY_ORDER = {"Info": 0, "Warning": 1, "Error": 2, "Critical": 3}
RESULT_FROM_SEVERITY = {
    "Info": "PASS",
    "Warning": "PASS_WITH_WARNINGS",
    "Error": "FAIL",
    "Critical": "FAIL",
}


def _uuid() -> str: return str(uuid.uuid4())
def _iso() -> str: return datetime.now(timezone.utc).isoformat()
def _strip(d): return {k: v for k, v in d.items() if k != "_id"} if d else d


def _require(user, allowed: set, err: str = "Forbidden"):
    if not user or user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=err)


def _worst(sevs: List[str]) -> str:
    if not sevs:
        return "Info"
    return max(sevs, key=lambda s: SEVERITY_ORDER.get(s, 0))


def _overall_result(findings: List[Dict[str, Any]]) -> str:
    if not findings:
        return "PASS"
    worst = _worst([f["severity"] for f in findings])
    return RESULT_FROM_SEVERITY.get(worst, "PASS")


# ═══════════════════════════════════════════════════════════════════════
# Control Catalogue (deterministic, code-defined; seeded idempotently)
# ═══════════════════════════════════════════════════════════════════════
class ControlDef(BaseModel):
    control_key: str
    domain: str  # AuthSession | RBAC | API | Secrets | Privacy | AuditLog
    part: int
    title: str
    severity: str  # baseline severity when the control fails
    description: str


CONTROLS: List[ControlDef] = [
    # ── Part 3 · Auth & Session Hardening ────────────────────────────
    ControlDef(control_key="auth.bcrypt_cost_min", domain="AuthSession", part=3,
               title="Bcrypt cost factor >= 10", severity="Error",
               description="Password hashes must use bcrypt with cost >= 10."),
    ControlDef(control_key="auth.jwt_expiry_bounded", domain="AuthSession", part=3,
               title="JWT access token TTL <= 30 days", severity="Warning",
               description="Access tokens must expire within a defined ceiling."),
    ControlDef(control_key="auth.jwt_secret_strength", domain="AuthSession", part=3,
               title="JWT secret entropy", severity="Critical",
               description="JWT_SECRET must be >= 32 characters."),
    ControlDef(control_key="auth.jwt_type_check", domain="AuthSession", part=3,
               title="JWT type claim enforced", severity="Error",
               description="Token payload must be verified for type='access'."),
    ControlDef(control_key="auth.admin_password_not_default", domain="AuthSession", part=3,
               title="Admin password not the seeded default", severity="Warning",
               description="Seeded admin password should be rotated for prod."),
    ControlDef(control_key="auth.password_hash_present", domain="AuthSession", part=3,
               title="All user rows have a password hash", severity="Critical",
               description="A user without a password hash cannot be safely authenticated."),
    # ── Part 4 · RBAC audit ──────────────────────────────────────────
    ControlDef(control_key="rbac.role_gate_present", domain="RBAC", part=4,
               title="Sensitive routes are role-gated", severity="Error",
               description="Every mutation route must enforce a role check."),
    ControlDef(control_key="rbac.readonly_not_writable", domain="RBAC", part=4,
               title="ReadOnly role never granted write", severity="Critical",
               description="No mutation route permits ReadOnly role."),
    ControlDef(control_key="rbac.permission_matrix_complete", domain="RBAC", part=4,
               title="Permission matrix generated for every route", severity="Info",
               description="RBAC matrix covers every registered API route."),
    # ── Part 5 · API security ────────────────────────────────────────
    ControlDef(control_key="api.auth_required_coverage", domain="API", part=5,
               title="Auth required on all /api routes (except allow-list)", severity="Error",
               description="Non-public /api routes must require authentication."),
    ControlDef(control_key="api.cors_not_wildcard_in_prod", domain="API", part=5,
               title="CORS not wildcard when APP_ENV=production", severity="Error",
               description="CORS_ORIGINS must be explicit in production."),
    ControlDef(control_key="api.unsafe_verb_role_gated", domain="API", part=5,
               title="POST/PUT/DELETE routes are role-gated", severity="Error",
               description="Every write route must enforce a role gate."),
    # ── Part 6 · Secrets / env ───────────────────────────────────────
    ControlDef(control_key="env.required_keys_present", domain="Secrets", part=6,
               title="All required environment variables are set", severity="Critical",
               description="MONGO_URL, DB_NAME, JWT_SECRET must be configured."),
    ControlDef(control_key="env.secret_leak_in_config_endpoint", domain="Secrets", part=6,
               title="No secret-shaped keys returned by public config endpoints", severity="Critical",
               description="/configuration-status style endpoints must not leak credentials."),
    ControlDef(control_key="env.storage_backend_declared", domain="Secrets", part=6,
               title="Object storage backend explicitly configured", severity="Info",
               description="Storage adapter selection must be declared."),
    # ── Part 7 · Privacy / sensitive data ────────────────────────────
    ControlDef(control_key="data.pii_inventory_present", domain="Privacy", part=7,
               title="PII field inventory documented", severity="Info",
               description="Every PII field lives in the classification inventory."),
    ControlDef(control_key="data.restricted_field_gated", domain="Privacy", part=7,
               title="Restricted fields are role-gated in aggregators", severity="Error",
               description="Sensitive Account Details must be stripped for lower roles."),
    # ── Part 8 · Audit-log integrity ─────────────────────────────────
    ControlDef(control_key="audit.append_only_collections_declared", domain="AuditLog", part=8,
               title="Append-only audit collections declared", severity="Info",
               description="Critical event streams are declared append-only."),
    ControlDef(control_key="audit.security_events_immutable", domain="AuditLog", part=8,
               title="Security assessment events are immutable", severity="Critical",
               description="security_assessment_events entries must never be mutated."),
]


# ═══════════════════════════════════════════════════════════════════════
# Static PII / restricted-data inventory (Part 7)
# ═══════════════════════════════════════════════════════════════════════
PII_INVENTORY: List[Dict[str, Any]] = [
    {"collection": "drivers", "field": "email", "classification": "PII",
     "sensitivity": "Internal", "notes": "Driver contact email."},
    {"collection": "drivers", "field": "phone", "classification": "PII",
     "sensitivity": "Internal", "notes": "Driver contact phone."},
    {"collection": "drivers", "field": "licence_number", "classification": "PII",
     "sensitivity": "Internal", "notes": "Driver licence identifier."},
    {"collection": "drivers", "field": "abn", "classification": "SensitiveAccount",
     "sensitivity": "Restricted", "notes": "Restricted account detail."},
    {"collection": "drivers", "field": "business_name", "classification": "SensitiveAccount",
     "sensitivity": "Restricted", "notes": "Restricted account detail."},
    {"collection": "drivers", "field": "payroll_number", "classification": "SensitiveAccount",
     "sensitivity": "Restricted", "notes": "Restricted account detail."},
    {"collection": "drivers", "field": "payment_percentage", "classification": "SensitiveAccount",
     "sensitivity": "Restricted", "notes": "Restricted account detail."},
    {"collection": "owners", "field": "abn", "classification": "SensitiveAccount",
     "sensitivity": "Restricted", "notes": "Owner ABN."},
    {"collection": "users", "field": "email", "classification": "PII",
     "sensitivity": "Internal", "notes": "Login identifier."},
    {"collection": "users", "field": "password_hash", "classification": "Credential",
     "sensitivity": "Confidential", "notes": "Bcrypt password hash — never returned by API."},
    {"collection": "documents", "field": "storage_key", "classification": "Internal",
     "sensitivity": "Confidential", "notes": "Storage key never leaked to browser."},
    {"collection": "notification_recipients", "field": "email_address",
     "classification": "PII", "sensitivity": "Internal",
     "notes": "Snapshot for delivery history; canonical email lives in users/drivers."},
    {"collection": "notification_recipients", "field": "mobile_number",
     "classification": "PII", "sensitivity": "Internal",
     "notes": "Snapshot for delivery history."},
]


# Append-only / immutable audit collection declaration (Part 8)
APPEND_ONLY_COLLECTIONS = [
    "security_assessment_events",
    "security_exception_approvals",
    "notification_provider_events",
    "notification_escalations",
    "driver_activation_events",
    "document_access_events",
    "storage_events",
    "migration_commit_actions",
    "import_rollback_events",
    "driver_export_events",
    "number_allocation_events",
    "driver_note_versions",
    "integrity_check_events",
]


# Routes that are intentionally public (no auth required) — allow-list
PUBLIC_ROUTES_ALLOWLIST = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/"),
    ("HEAD", "/api/"),
    # Provider webhooks — signature-verified, not user-authenticated.
    ("POST", "/api/webhooks/sendgrid"),
    ("POST", "/api/webhooks/twilio"),
}

# Verbs that MUST be role-gated
UNSAFE_VERBS = {"POST", "PUT", "PATCH", "DELETE"}


# ═══════════════════════════════════════════════════════════════════════
# Route Inventory (introspected at run-time from the FastAPI app)
# ═══════════════════════════════════════════════════════════════════════
_ROLE_CHECK_TOKEN_RE = re.compile(
    r"("
    r"_require\s*\(|"                              # explicit require*
    r"_require_[a-z_]+\s*\(|"
    r"current\s*\[\s*[\"']role[\"']\s*\]|"          # current["role"]
    r"user\s*\[\s*[\"']role[\"']\s*\]|"
    r"current\.get\s*\(\s*[\"']role[\"']|"          # current.get("role")
    r"user\.get\s*\(\s*[\"']role[\"']|"
    r"actor\.get\s*\(\s*[\"']role[\"']|"
    r"actor\s*\[\s*[\"']role[\"']\s*\]"
    r")"
)


def _resolve_object_from_source(src_context: str, obj_name: str, closure_map: Dict[str, Any]) -> Any:
    """Look up an object referenced from a source snippet (best-effort)."""
    obj = closure_map.get(obj_name)
    if obj is not None:
        return obj
    # self.<attr> — dereference to the attribute on the class
    return None


def _delegated_source(endpoint, max_depth: int = 3) -> str:
    """Return concatenated source of the endpoint AND any service methods it
    delegates to, walking up to ``max_depth`` levels.

    Handles common patterns:
      - endpoint → svc.method → self.other_method → self.approval_svc.method
    """
    try:
        base_src = inspect.getsource(endpoint)
    except (OSError, TypeError):
        return ""
    # Closure/globals for the top-level endpoint
    try:
        closure = inspect.getclosurevars(endpoint)
        closure_map = dict(getattr(closure, "nonlocals", {}) or {})
        closure_map.update(getattr(closure, "globals", {}) or {})
    except Exception:
        closure_map = {}

    SKIP_NAMES = {"self", "logging", "logger", "os", "re", "json", "datetime",
                  "asyncio", "db", "current", "user", "payload", "body",
                  "request", "req", "app", "router", "response"}

    combined_src = base_src
    # We progressively add methods called into a queue and walk them.
    # Each queue entry: (source, closure_map, self_class)
    queue: List[Tuple[str, Dict[str, Any], Any]] = [(base_src, closure_map, None)]
    seen: set = set()
    for _ in range(max_depth):
        next_queue: List[Tuple[str, Dict[str, Any], Any]] = []
        for src, cmap, self_cls in queue:
            calls = re.findall(r"([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?)\.([A-Za-z_][A-Za-z_0-9]*)\s*\(", src)
            # Also match self.<attr>.<method>
            calls_self = re.findall(r"self\.([A-Za-z_][A-Za-z_0-9]*)\.([A-Za-z_][A-Za-z_0-9]*)\s*\(", src)
            # Simple self.<method>() calls
            calls_direct_self = re.findall(r"self\.([A-Za-z_][A-Za-z_0-9]*)\s*\(", src)

            for obj_name, method_name in calls:
                if "." in obj_name:  # already handled below
                    continue
                if obj_name in SKIP_NAMES:
                    continue
                key = ("obj", obj_name, method_name)
                if key in seen:
                    continue
                seen.add(key)
                obj = cmap.get(obj_name)
                if obj is None:
                    continue
                method = getattr(obj, method_name, None)
                if method is None:
                    continue
                try:
                    inner = inspect.getsource(method)
                except (OSError, TypeError):
                    continue
                combined_src += "\n" + inner
                # capture the class of `obj` for `self.` chain resolution
                next_queue.append((inner, cmap, type(obj)))

            for attr_name, method_name in calls_self:
                if self_cls is None:
                    continue
                key = ("self_attr", id(self_cls), attr_name, method_name)
                if key in seen:
                    continue
                seen.add(key)
                # We can't easily resolve self.<attr> without an instance
                # (since self.approval_svc = ApprovalService(...)). Instead
                # we scan the class __init__ to see what type attr_name is
                # bound to.
                try:
                    init_src = inspect.getsource(self_cls.__init__)
                except (OSError, TypeError):
                    continue
                m = re.search(
                    r"self\." + re.escape(attr_name) + r"\s*=\s*([A-Za-z_][A-Za-z_0-9]*)",
                    init_src)
                if not m:
                    continue
                inner_cls_name = m.group(1)
                inner_cls = cmap.get(inner_cls_name)
                # Also look at the module of self_cls
                if inner_cls is None:
                    inner_cls = getattr(inspect.getmodule(self_cls), inner_cls_name, None)
                if inner_cls is None:
                    continue
                inner_method = getattr(inner_cls, method_name, None)
                if inner_method is None:
                    continue
                try:
                    inner_src = inspect.getsource(inner_method)
                except (OSError, TypeError):
                    continue
                combined_src += "\n" + inner_src
                next_queue.append((inner_src, cmap, inner_cls))

            for method_name in calls_direct_self:
                if self_cls is None:
                    continue
                key = ("direct_self", id(self_cls), method_name)
                if key in seen:
                    continue
                seen.add(key)
                inner_method = getattr(self_cls, method_name, None)
                if inner_method is None:
                    continue
                try:
                    inner_src = inspect.getsource(inner_method)
                except (OSError, TypeError):
                    continue
                combined_src += "\n" + inner_src
                next_queue.append((inner_src, cmap, self_cls))
        queue = next_queue
        if not queue:
            break
    return combined_src


def _extract_role_gate_from_endpoint(endpoint) -> Optional[str]:
    """Return a role-check hint discovered inside a route's endpoint source
    (and — one level down — any service method the endpoint delegates to).
    """
    if endpoint is None:
        return None
    src = _delegated_source(endpoint)
    if not src:
        return None

    # Pattern 1: _require(current[...], ROLE_SYMBOL)
    m = re.search(r"_require\s*\([^)]*?(ROLE_[A-Z_]+)", src)
    if m:
        return m.group(1)

    # Pattern 2: _require(..., {"Admin", "Manager", ...})
    m = re.search(r"_require\s*\([^)]*?\{([^}]*)\}", src)
    if m:
        return f"INLINE_SET:{m.group(1).strip()}"

    # Pattern 3: custom helpers like _require_admin_manager, _require_write, etc.
    m = re.search(r"_require_([a-z_]+)\s*\(", src)
    if m:
        return f"HELPER:_require_{m.group(1)}"

    # Pattern 4: current["role"] not in (...)
    m = re.search(r"current\[[\"']role[\"']\]\s+not\s+in\s+[\(\[\{]([^\)\]\}]+)[\)\]\}]", src)
    if m:
        return f"INLINE_NOT_IN:{m.group(1).strip()}"

    # Pattern 5: current["role"] == "Admin"
    m = re.search(r"current\[[\"']role[\"']\]\s*==\s*[\"']([A-Za-z]+)[\"']", src)
    if m:
        return f"EQ:{m.group(1)}"

    # Pattern 6: current["role"] != "Admin"
    m = re.search(r"current\[[\"']role[\"']\]\s*!=\s*[\"']([A-Za-z]+)[\"']", src)
    if m:
        return f"NEQ:{m.group(1)}"

    # Pattern 7: <any>.get("role") not in (...)
    m = re.search(r"[A-Za-z_][A-Za-z_0-9]*\.get\(\s*[\"']role[\"']\s*\)\s+not\s+in\s+([A-Z_]+)", src)
    if m:
        return m.group(1)  # ROLE_* symbol
    m = re.search(r"[A-Za-z_][A-Za-z_0-9]*\.get\(\s*[\"']role[\"']\s*\)\s+not\s+in\s+[\(\[\{]([^\)\]\}]+)[\)\]\}]", src)
    if m:
        return f"INLINE_NOT_IN:{m.group(1).strip()}"

    # Pattern 8: <any>.get("role") == "..."
    m = re.search(r"[A-Za-z_][A-Za-z_0-9]*\.get\(\s*[\"']role[\"']\s*\)\s*==\s*[\"']([A-Za-z]+)[\"']", src)
    if m:
        return f"EQ:{m.group(1)}"
    m = re.search(r"[A-Za-z_][A-Za-z_0-9]*\.get\(\s*[\"']role[\"']\s*\)\s*!=\s*[\"']([A-Za-z]+)[\"']", src)
    if m:
        return f"NEQ:{m.group(1)}"

    # Pattern 9: any bare role reference (last-resort inline check).
    if _ROLE_CHECK_TOKEN_RE.search(src):
        return "INLINE_ROLE_CHECK"

    return None


_ROLE_LEVEL_ORDER = ["ReadOnly", "Allocator", "Compliance", "Manager", "Admin"]


_HELPER_ROLE_SETS: Dict[str, List[str]] = {
    # documents_module
    "_require_write": ["Admin", "Allocator", "Compliance", "Manager"],
    "_require_admin_manager": ["Admin", "Manager"],
    # registers / compliance / relationships
    "_require_write_role": ["Admin", "Allocator", "Compliance", "Manager"],
    "_require_delete_role": ["Admin", "Manager"],
    "_require_archive": ["Admin", "Manager"],
    # imports / notifications / numbering / driver_export / driver_profile
    "_require_role": ["Admin", "Manager"],  # coarse default; refined per call site if we can
}


def _role_set_for_gate(gate: Optional[str]) -> List[str]:
    mapping = {
        "ROLE_READONLY": sorted(list(ROLE_READONLY)),
        "ROLE_ALLOCATOR": sorted(list(ROLE_ALLOCATOR)),
        "ROLE_COMPLIANCE": sorted(list(ROLE_COMPLIANCE)),
        "ROLE_MANAGER": sorted(list(ROLE_MANAGER)),
        "ROLE_ADMIN": sorted(list(ROLE_ADMIN)),
        # Common project-specific aliases spotted in the codebase
        "ROLE_MANAGE_TEMPLATES": sorted(list(ROLE_MANAGER)),
        "ROLE_ACTIVATE": sorted(list(ROLE_MANAGER)),
        "ROLE_MANUAL_COMPLETE": sorted(list(ROLE_ALLOCATOR)),
        "ROLE_REQUEST_OVERRIDE": sorted(list(ROLE_ALLOCATOR)),
        "ROLE_APPROVE_OVERRIDE": sorted(list(ROLE_MANAGER)),
        "ROLE_MANAGE_JOBS": sorted(list(ROLE_MANAGER)),
    }
    if gate in mapping:
        return mapping[gate]
    if not gate:
        return []
    if gate.startswith("HELPER:"):
        helper = gate[len("HELPER:"):]
        return sorted(_HELPER_ROLE_SETS.get(helper, ["<inline>"]))
    if gate.startswith("INLINE_SET:"):
        raw = gate[len("INLINE_SET:"):]
        roles = [t.strip().strip("\"'") for t in raw.split(",")]
        roles = [r for r in roles if r in _ROLE_LEVEL_ORDER]
        return sorted(roles)
    if gate.startswith("INLINE_NOT_IN:"):
        # Pattern: `if role not in (A, B): raise` → allowed = {A, B}
        raw = gate[len("INLINE_NOT_IN:"):]
        allowed = [t.strip().strip("\"'") for t in raw.split(",")]
        allowed = [r for r in allowed if r in _ROLE_LEVEL_ORDER]
        return sorted(allowed)
    if gate.startswith("EQ:"):
        # Pattern: `if role == "X": raise` → denied = {X} → allowed = everyone else
        role = gate[len("EQ:"):]
        if role not in _ROLE_LEVEL_ORDER:
            return []
        return sorted([r for r in _ROLE_LEVEL_ORDER if r != role])
    if gate.startswith("NEQ:"):
        # Pattern: `if role != "X": raise` → allowed = {X}
        role = gate[len("NEQ:"):]
        return [role] if role in _ROLE_LEVEL_ORDER else []
    if gate == "INLINE_ROLE_CHECK":
        return ["<inline>"]
    return []


def _endpoint_auth_type(endpoint) -> str:
    """Return one of: 'user' | 'service_token' | 'signature' | 'none'."""
    if endpoint is None:
        return "none"
    try:
        sig = inspect.signature(endpoint)
    except (ValueError, TypeError):
        return "none"
    for p in sig.parameters.values():
        default = p.default
        dep = getattr(default, "dependency", None)
        if dep is not None:
            name = getattr(dep, "__name__", "") or ""
            if name == "get_current_user":
                return "user"
            if name == "scheduler_auth":
                return "service_token"
    try:
        src = inspect.getsource(endpoint)
    except (OSError, TypeError):
        return "none"
    if re.search(r"hmac\.compare_digest|hmac\.new|_verify_signature", src):
        return "signature"
    return "none"


def _endpoint_requires_auth(endpoint) -> bool:
    return _endpoint_auth_type(endpoint) != "none"


def build_route_inventory(app) -> List[Dict[str, Any]]:
    """Enumerate every /api route registered on the FastAPI app."""
    inv: List[Dict[str, Any]] = []
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        endpoint = getattr(route, "endpoint", None)
        if not path or not methods:
            continue
        if not path.startswith("/api"):
            continue
        methods = {m for m in methods if m != "HEAD"}
        if not methods:
            continue
        gate = _extract_role_gate_from_endpoint(endpoint)
        allowed_roles = _role_set_for_gate(gate)
        auth_type = _endpoint_auth_type(endpoint)
        requires_auth = auth_type != "none"
        for m in sorted(methods):
            inv.append({
                "method": m,
                "path": path,
                "requires_auth": requires_auth,
                "auth_type": auth_type,
                "role_gate": gate,
                "allowed_roles": allowed_roles,
                "public_allowlisted": (m, path) in PUBLIC_ROUTES_ALLOWLIST,
                "is_write": m in UNSAFE_VERBS,
            })
    inv.sort(key=lambda x: (x["path"], x["method"]))
    return inv


# ═══════════════════════════════════════════════════════════════════════
# Configuration Status (Part 6) — never leaks secrets
# ═══════════════════════════════════════════════════════════════════════
SECRET_KEY_RE = re.compile(
    r"(secret|password|passwd|api[_-]?key|token|credential|private[_-]?key|"
    r"access[_-]?key|session|bearer)",
    re.IGNORECASE,
)


def _scrub_config_status(cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Return (safe_view, leaked_keys).

    A key is only considered *leaked* when its NAME matches the secret regex
    AND its VALUE is a plausibly-secret string (non-empty, longer than 8 chars,
    not a boolean/int). Booleans and lengths named e.g. ``jwt_secret_configured``
    or ``jwt_secret_length`` do NOT trigger a finding — but the raw
    ``JWT_SECRET`` string absolutely would.
    """
    leaked = []
    safe: Dict[str, Any] = {}
    for k, v in cfg.items():
        if SECRET_KEY_RE.search(k) and isinstance(v, str) and len(v) > 8:
            leaked.append(k)
            safe[k] = "[REDACTED]"
        else:
            safe[k] = v
    return safe, leaked


def _current_configuration_snapshot() -> Dict[str, Any]:
    """Snapshot only environment-driven booleans and lengths/backend selectors
    — NEVER the raw values themselves.
    """
    def _has(k: str) -> bool:
        return bool(os.environ.get(k))

    def _len(k: str) -> int:
        return len(os.environ.get(k) or "")

    return {
        "app_env": os.environ.get("APP_ENV", "development"),
        "mongo_url_configured": _has("MONGO_URL"),
        "db_name_configured": _has("DB_NAME"),
        "jwt_secret_configured": _has("JWT_SECRET"),
        "jwt_secret_length": _len("JWT_SECRET"),
        "cors_origins_wildcard": (os.environ.get("CORS_ORIGINS", "*").strip() == "*"),
        "storage_backend": os.environ.get("OBJECT_STORAGE_BACKEND", "local"),
        "storage_root_configured": _has("DOCUMENT_STORAGE_PATH"),
        "webhooks_enabled": os.environ.get("WEBHOOKS_ENABLED", "false").lower() == "true",
        "admin_email_configured": _has("ADMIN_EMAIL"),
    }


# ═══════════════════════════════════════════════════════════════════════
# Assessment Engine
# ═══════════════════════════════════════════════════════════════════════
class SecurityService:
    def __init__(self, db, app=None):
        self.db = db
        self.app = app

    # ── Persistence helpers ────────────────────────────────────────
    async def seed_controls(self) -> int:
        """Idempotent seed of the deterministic control catalogue."""
        inserted = 0
        for c in CONTROLS:
            insert_doc = {
                "security_control_definition_id": _uuid(),
                "control_key": c.control_key,
                "created_at": _iso(),
                "_source": "seed-eb17a",
            }
            set_doc = {
                "domain": c.domain,
                "part": c.part,
                "title": c.title,
                "severity": c.severity,
                "description": c.description,
                "active": True,
                "updated_at": _iso(),
            }
            r = await self.db[CTRL_COLL].update_one(
                {"control_key": c.control_key},
                {"$setOnInsert": insert_doc, "$set": set_doc},
                upsert=True,
            )
            if r.upserted_id is not None:
                inserted += 1
        return inserted

    async def _log_event(self, event_type: str, ref: Dict[str, Any],
                         actor: Optional[str], payload: Dict[str, Any]) -> None:
        doc = {
            "security_assessment_event_id": _uuid(),
            "event_type": event_type,
            "at": _iso(),
            "actor": actor,
            **ref,
            "payload": payload,
        }
        await self.db[EVENT_COLL].insert_one(doc)

    # ── Individual checks ──────────────────────────────────────────
    async def _check_auth_session(self) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        # JWT secret strength
        secret = os.environ.get("JWT_SECRET", "")
        if len(secret) < 32:
            findings.append({
                "control_key": "auth.jwt_secret_strength",
                "severity": "Critical",
                "message": f"JWT_SECRET length {len(secret)} < 32.",
                "context": {"length": len(secret)},
            })
        # JWT expiry bounded
        from server import ACCESS_TOKEN_EXPIRE_MINUTES
        max_minutes = 60 * 24 * 30  # 30 days
        if ACCESS_TOKEN_EXPIRE_MINUTES > max_minutes:
            findings.append({
                "control_key": "auth.jwt_expiry_bounded",
                "severity": "Warning",
                "message": f"Access token TTL {ACCESS_TOKEN_EXPIRE_MINUTES} min exceeds ceiling {max_minutes}.",
                "context": {"minutes": ACCESS_TOKEN_EXPIRE_MINUTES},
            })
        # bcrypt cost — read from a sample hash on the seeded admin
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@acedriverhub.com").lower().strip()
        admin = await self.db.users.find_one({"email": admin_email})
        if admin and admin.get("password_hash"):
            m = re.match(r"^\$2[aby]\$(\d{2})\$", admin["password_hash"])
            if m:
                cost = int(m.group(1))
                if cost < 10:
                    findings.append({
                        "control_key": "auth.bcrypt_cost_min",
                        "severity": "Error",
                        "message": f"Bcrypt cost {cost} < 10.",
                        "context": {"cost": cost},
                    })
        # Admin default password (Warning only for dev)
        if os.environ.get("ADMIN_PASSWORD", "Admin@123") == "Admin@123":
            findings.append({
                "control_key": "auth.admin_password_not_default",
                "severity": "Warning",
                "message": "Seeded admin password is the shipped default.",
                "context": {},
            })
        # Users without password hash
        missing_pw = await self.db.users.count_documents({"password_hash": {"$exists": False}})
        if missing_pw:
            findings.append({
                "control_key": "auth.password_hash_present",
                "severity": "Critical",
                "message": f"{missing_pw} user rows missing password_hash.",
                "context": {"count": missing_pw},
            })
        # JWT type-check — verify server enforces payload['type'] == 'access'
        try:
            src = inspect.getsource(__import__("server").get_current_user)
            if 'payload.get("type")' not in src and "payload['type']" not in src:
                findings.append({
                    "control_key": "auth.jwt_type_check",
                    "severity": "Error",
                    "message": "JWT type claim is not verified in get_current_user.",
                    "context": {},
                })
        except Exception:
            pass
        return findings

    def _check_rbac(self, inv: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        for r in inv:
            if r["public_allowlisted"]:
                continue
            # Service-token / signature auth: role gate not applicable
            if r.get("auth_type") in ("service_token", "signature"):
                continue
            if r["is_write"] and not r["role_gate"]:
                findings.append({
                    "control_key": "rbac.role_gate_present",
                    "severity": "Error",
                    "message": f"Write route without role gate: {r['method']} {r['path']}.",
                    "context": {"method": r["method"], "path": r["path"]},
                })
            if r["is_write"] and "ReadOnly" in r["allowed_roles"]:
                findings.append({
                    "control_key": "rbac.readonly_not_writable",
                    "severity": "Critical",
                    "message": f"Write route accepts ReadOnly: {r['method']} {r['path']}.",
                    "context": {"method": r["method"], "path": r["path"]},
                })
        return findings

    def _check_api(self, inv: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        for r in inv:
            if r["public_allowlisted"]:
                continue
            if not r["requires_auth"]:
                findings.append({
                    "control_key": "api.auth_required_coverage",
                    "severity": "Error",
                    "message": f"Route lacks authentication: {r['method']} {r['path']}.",
                    "context": {"method": r["method"], "path": r["path"]},
                })
            # Service-token / signature auth: role gate not applicable
            if r.get("auth_type") in ("service_token", "signature"):
                continue
            if r["is_write"] and not r["role_gate"]:
                findings.append({
                    "control_key": "api.unsafe_verb_role_gated",
                    "severity": "Error",
                    "message": f"Unsafe verb without role gate: {r['method']} {r['path']}.",
                    "context": {"method": r["method"], "path": r["path"]},
                })
        # CORS wildcard in production
        app_env = os.environ.get("APP_ENV", "development")
        cors = os.environ.get("CORS_ORIGINS", "*").strip()
        if app_env == "production" and cors == "*":
            findings.append({
                "control_key": "api.cors_not_wildcard_in_prod",
                "severity": "Error",
                "message": "CORS_ORIGINS='*' while APP_ENV=production.",
                "context": {"cors": cors},
            })
        return findings

    def _check_secrets(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        for key in ("MONGO_URL", "DB_NAME", "JWT_SECRET"):
            if not os.environ.get(key):
                findings.append({
                    "control_key": "env.required_keys_present",
                    "severity": "Critical",
                    "message": f"Required env var missing: {key}.",
                    "context": {"key": key},
                })
        snap = _current_configuration_snapshot()
        safe, leaked = _scrub_config_status(snap)
        for k in leaked:
            findings.append({
                "control_key": "env.secret_leak_in_config_endpoint",
                "severity": "Critical",
                "message": f"Configuration snapshot contained secret-shaped key: {k}.",
                "context": {"key": k},
            })
        return findings, safe

    async def _check_privacy(self) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        # Restricted-field gating — verify driver_profile_module strips
        # them for non-Manager roles.
        try:
            src = inspect.getsource(__import__("driver_profile_module"))
        except Exception:
            src = ""
        expected_restricted = {"business_name", "abn", "payroll_number", "payment_percentage"}
        for field in expected_restricted:
            if field not in src:
                findings.append({
                    "control_key": "data.restricted_field_gated",
                    "severity": "Error",
                    "message": f"Restricted field '{field}' not referenced in driver_profile_module gating.",
                    "context": {"field": field},
                })
        return findings

    async def _check_audit(self) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        # Tamper-detection: for security_assessment_events, verify no
        # doc has updated_at > created at (they should be write-once).
        try:
            bad = await self.db[EVENT_COLL].count_documents({"updated_at": {"$exists": True}})
            if bad:
                findings.append({
                    "control_key": "audit.security_events_immutable",
                    "severity": "Critical",
                    "message": f"{bad} security assessment events show mutation markers.",
                    "context": {"count": bad},
                })
        except Exception:
            pass
        return findings

    # ── Assessment run ────────────────────────────────────────────
    async def run_assessment(
        self,
        actor: Optional[str],
        run_type: str = "FullSystem",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Idempotent per correlation_id. When a correlation_id is provided
        and an existing run with that id already exists, that run is
        returned unchanged.
        """
        if correlation_id:
            existing = await self.db[RUN_COLL].find_one(
                {"correlation_id": correlation_id}, {"_id": 0})
            if existing:
                return existing

        run_id = _uuid()
        started_at = _iso()
        # Snapshot config
        snap = _current_configuration_snapshot()
        safe_snap, _ = _scrub_config_status(snap)

        # Aggregate findings
        findings: List[Dict[str, Any]] = []
        findings += await self._check_auth_session()
        inv = build_route_inventory(self.app) if self.app else []
        findings += self._check_rbac(inv)
        findings += self._check_api(inv)
        sec_findings, safe_view = self._check_secrets()
        findings += sec_findings
        findings += await self._check_privacy()
        findings += await self._check_audit()

        # Persist configuration snapshot
        snap_doc = {
            "security_configuration_snapshot_id": _uuid(),
            "security_assessment_run_id": run_id,
            "captured_at": started_at,
            "configuration": safe_view,
            "_source": "seed-eb17a",
        }
        await self.db[SNAP_COLL].insert_one(dict(snap_doc))

        # Persist findings
        finding_docs = []
        for f in findings:
            doc = {
                "security_assessment_finding_id": _uuid(),
                "security_assessment_run_id": run_id,
                "control_key": f["control_key"],
                "severity": f["severity"],
                "status": "Open",
                "message": f["message"],
                "context": f.get("context", {}),
                "created_at": _iso(),
                "_source": "seed-eb17a",
            }
            finding_docs.append(doc)
        if finding_docs:
            await self.db[FIND_COLL].insert_many([dict(d) for d in finding_docs])

        overall = _overall_result(findings)
        counts = {"Info": 0, "Warning": 0, "Error": 0, "Critical": 0}
        for f in findings:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1

        run_doc = {
            "security_assessment_run_id": run_id,
            "run_type": run_type,
            "correlation_id": correlation_id,
            "started_at": started_at,
            "finished_at": _iso(),
            "actor": actor,
            "overall_result": overall,
            "findings_by_severity": counts,
            "findings_count": len(findings),
            "route_count": len(inv),
            "security_configuration_snapshot_id": snap_doc["security_configuration_snapshot_id"],
            "_source": "seed-eb17a",
        }
        await self.db[RUN_COLL].insert_one(dict(run_doc))
        await self._log_event("assessment.run", {"security_assessment_run_id": run_id},
                              actor, {"overall": overall, "counts": counts})
        return _strip(run_doc)

    async def status_summary(self) -> Dict[str, Any]:
        last = await self.db[RUN_COLL].find({}, {"_id": 0}).sort("started_at", -1).limit(1).to_list(1)
        last_run = last[0] if last else None
        # Open exceptions count
        open_exc = await self.db[EXC_REQ_COLL].count_documents({"status": "Pending"})
        approved_exc = await self.db[EXC_REQ_COLL].count_documents({"status": "Approved"})
        return {
            "last_assessment": last_run,
            "controls_count": await self.db[CTRL_COLL].count_documents({"active": True}),
            "exceptions": {"pending": open_exc, "approved": approved_exc},
            "generated_at": _iso(),
        }


# ═══════════════════════════════════════════════════════════════════════
# Exception Workflow (Part 9)
# ═══════════════════════════════════════════════════════════════════════
class ExceptionRequestBody(BaseModel):
    control_key: str
    security_assessment_finding_id: Optional[str] = None
    reason: str = Field(..., min_length=10)
    risk_acknowledgement: str = Field(..., min_length=10)
    requested_days: int = Field(30, ge=1, le=365)


class ExceptionActionBody(BaseModel):
    note: Optional[str] = None


class ExceptionService:
    def __init__(self, db):
        self.db = db

    async def create(self, actor_email: str, body: ExceptionRequestBody) -> Dict[str, Any]:
        ctrl = await self.db[CTRL_COLL].find_one({"control_key": body.control_key})
        if not ctrl:
            raise HTTPException(status_code=400, detail=f"Unknown control: {body.control_key}")
        # Critical controls cannot be excepted below Admin later; that is
        # enforced at approve-time.
        req = {
            "security_exception_request_id": _uuid(),
            "control_key": body.control_key,
            "security_assessment_finding_id": body.security_assessment_finding_id,
            "reason": body.reason.strip(),
            "risk_acknowledgement": body.risk_acknowledgement.strip(),
            "requested_days": body.requested_days,
            "status": "Pending",
            "requested_by": actor_email,
            "requested_at": _iso(),
            "expires_at": None,  # set on approval
            "_source": "seed-eb17a",
        }
        await self.db[EXC_REQ_COLL].insert_one(dict(req))
        # Append-only event
        await self.db[EXC_APR_COLL].insert_one({
            "security_exception_approval_id": _uuid(),
            "security_exception_request_id": req["security_exception_request_id"],
            "action": "Requested",
            "actor": actor_email,
            "at": _iso(),
            "note": None,
            "_source": "seed-eb17a",
        })
        return _strip(req)

    async def approve(self, exc_id: str, actor_email: str,
                      actor_role: str, note: Optional[str]) -> Dict[str, Any]:
        req = await self.db[EXC_REQ_COLL].find_one({"security_exception_request_id": exc_id})
        if not req:
            raise HTTPException(status_code=404, detail="Exception request not found")
        if req["status"] != "Pending":
            raise HTTPException(status_code=400, detail=f"Cannot approve from status {req['status']}.")
        if req.get("requested_by") == actor_email:
            raise HTTPException(status_code=403, detail="Requester cannot approve their own exception.")
        ctrl = await self.db[CTRL_COLL].find_one({"control_key": req["control_key"]})
        if ctrl and ctrl.get("severity") == "Critical" and actor_role != "Admin":
            raise HTTPException(status_code=403, detail="Critical controls require Admin approval.")
        expires_at = (datetime.now(timezone.utc)
                      + timedelta(days=req["requested_days"])).isoformat()
        await self.db[EXC_REQ_COLL].update_one(
            {"security_exception_request_id": exc_id},
            {"$set": {"status": "Approved", "approved_by": actor_email,
                      "approved_at": _iso(), "expires_at": expires_at}},
        )
        await self.db[EXC_APR_COLL].insert_one({
            "security_exception_approval_id": _uuid(),
            "security_exception_request_id": exc_id,
            "action": "Approved",
            "actor": actor_email,
            "at": _iso(),
            "note": note,
            "_source": "seed-eb17a",
        })
        return await self.db[EXC_REQ_COLL].find_one(
            {"security_exception_request_id": exc_id}, {"_id": 0})

    async def reject(self, exc_id: str, actor_email: str, note: Optional[str]) -> Dict[str, Any]:
        req = await self.db[EXC_REQ_COLL].find_one({"security_exception_request_id": exc_id})
        if not req:
            raise HTTPException(status_code=404, detail="Exception request not found")
        if req["status"] != "Pending":
            raise HTTPException(status_code=400, detail=f"Cannot reject from status {req['status']}.")
        if req.get("requested_by") == actor_email:
            raise HTTPException(status_code=403, detail="Requester cannot reject their own exception.")
        await self.db[EXC_REQ_COLL].update_one(
            {"security_exception_request_id": exc_id},
            {"$set": {"status": "Rejected", "rejected_by": actor_email,
                      "rejected_at": _iso()}},
        )
        await self.db[EXC_APR_COLL].insert_one({
            "security_exception_approval_id": _uuid(),
            "security_exception_request_id": exc_id,
            "action": "Rejected",
            "actor": actor_email,
            "at": _iso(),
            "note": note,
            "_source": "seed-eb17a",
        })
        return await self.db[EXC_REQ_COLL].find_one(
            {"security_exception_request_id": exc_id}, {"_id": 0})

    async def revoke(self, exc_id: str, actor_email: str, note: Optional[str]) -> Dict[str, Any]:
        req = await self.db[EXC_REQ_COLL].find_one({"security_exception_request_id": exc_id})
        if not req:
            raise HTTPException(status_code=404, detail="Exception request not found")
        if req["status"] != "Approved":
            raise HTTPException(status_code=400, detail=f"Cannot revoke from status {req['status']}.")
        await self.db[EXC_REQ_COLL].update_one(
            {"security_exception_request_id": exc_id},
            {"$set": {"status": "Revoked", "revoked_by": actor_email,
                      "revoked_at": _iso()}},
        )
        await self.db[EXC_APR_COLL].insert_one({
            "security_exception_approval_id": _uuid(),
            "security_exception_request_id": exc_id,
            "action": "Revoked",
            "actor": actor_email,
            "at": _iso(),
            "note": note,
            "_source": "seed-eb17a",
        })
        return await self.db[EXC_REQ_COLL].find_one(
            {"security_exception_request_id": exc_id}, {"_id": 0})

    async def expire_due(self) -> Dict[str, Any]:
        """Idempotent expiry sweep — flips Approved -> Expired when past TTL."""
        now = _iso()
        cursor = self.db[EXC_REQ_COLL].find(
            {"status": "Approved", "expires_at": {"$lt": now}}, {"_id": 0})
        expired = []
        async for d in cursor:
            expired.append(d["security_exception_request_id"])
            await self.db[EXC_REQ_COLL].update_one(
                {"security_exception_request_id": d["security_exception_request_id"]},
                {"$set": {"status": "Expired", "expired_at": now}},
            )
            await self.db[EXC_APR_COLL].insert_one({
                "security_exception_approval_id": _uuid(),
                "security_exception_request_id": d["security_exception_request_id"],
                "action": "Expired",
                "actor": "system",
                "at": now,
                "note": "TTL elapsed",
                "_source": "seed-eb17a",
            })
        return {"expired": expired, "count": len(expired)}


# ═══════════════════════════════════════════════════════════════════════
# Indexes
# ═══════════════════════════════════════════════════════════════════════
async def ensure_indexes(db):
    await db[CTRL_COLL].create_index("control_key", unique=True)
    await db[CTRL_COLL].create_index("security_control_definition_id", unique=True, sparse=True)
    await db[RUN_COLL].create_index("security_assessment_run_id", unique=True)
    await db[RUN_COLL].create_index([("started_at", -1)])
    await db[RUN_COLL].create_index("correlation_id", sparse=True)
    await db[FIND_COLL].create_index("security_assessment_finding_id", unique=True)
    await db[FIND_COLL].create_index([("security_assessment_run_id", 1), ("severity", -1)])
    await db[FIND_COLL].create_index("control_key")
    await db[EVENT_COLL].create_index("security_assessment_event_id", unique=True)
    await db[EVENT_COLL].create_index([("at", -1)])
    await db[SNAP_COLL].create_index("security_configuration_snapshot_id", unique=True)
    await db[SNAP_COLL].create_index([("captured_at", -1)])
    await db[EXC_REQ_COLL].create_index("security_exception_request_id", unique=True)
    await db[EXC_REQ_COLL].create_index("status")
    await db[EXC_APR_COLL].create_index("security_exception_approval_id", unique=True)
    await db[EXC_APR_COLL].create_index("security_exception_request_id")


# ═══════════════════════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════════════════════
class AssessmentRunBody(BaseModel):
    run_type: str = "FullSystem"
    correlation_id: Optional[str] = None


def build_security_router(db, app, get_current_user):
    router = APIRouter(tags=["security"])
    svc = SecurityService(db, app=app)
    exc = ExceptionService(db)

    # ── Status + catalogue ─────────────────────────────────────────
    @router.get("/api/security/status")
    async def status(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await svc.status_summary()

    @router.get("/api/security/controls")
    async def controls(current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await db[CTRL_COLL].find(
            {"active": True}, {"_id": 0}).sort("part", 1).to_list(500)

    # ── Assessments ────────────────────────────────────────────────
    @router.post("/api/security/assessments")
    async def new_assessment(body: AssessmentRunBody = Body(default_factory=AssessmentRunBody),
                             current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await svc.run_assessment(
            current.get("email"), run_type=body.run_type,
            correlation_id=body.correlation_id,
        )

    @router.get("/api/security/assessments")
    async def list_assessments(limit: int = 50, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        return await db[RUN_COLL].find(
            {}, {"_id": 0}).sort("started_at", -1).limit(limit).to_list(limit)

    @router.get("/api/security/assessments/{run_id}")
    async def get_assessment(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        r = await db[RUN_COLL].find_one(
            {"security_assessment_run_id": run_id}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Not found")
        return r

    @router.get("/api/security/assessments/{run_id}/findings")
    async def assessment_findings(run_id: str,
                                  severity: Optional[str] = None,
                                  control_key: Optional[str] = None,
                                  current=Depends(get_current_user)):
        _require(current, ROLE_READONLY)
        q: Dict[str, Any] = {"security_assessment_run_id": run_id}
        if severity: q["severity"] = severity
        if control_key: q["control_key"] = control_key
        return await db[FIND_COLL].find(q, {"_id": 0}).to_list(2000)

    # ── Configuration status (never leaks secrets) ─────────────────
    @router.get("/api/security/configuration-status")
    async def configuration_status(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        raw = _current_configuration_snapshot()
        safe, leaked = _scrub_config_status(raw)
        return {
            "configuration": safe,
            "leaked_keys": leaked,
            "generated_at": _iso(),
        }

    # ── Permission matrix ──────────────────────────────────────────
    @router.get("/api/security/permission-matrix")
    async def permission_matrix(current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE)
        inv = build_route_inventory(app)
        return {
            "roles": ["ReadOnly", "Allocator", "Compliance", "Manager", "Admin"],
            "routes": inv,
            "generated_at": _iso(),
        }

    # ── Data classification / PII inventory ────────────────────────
    @router.get("/api/security/data-classification")
    async def data_classification(current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE)
        return {
            "fields": PII_INVENTORY,
            "restricted_field_owners": [
                "driver_profile_module (Sensitive Account Details)"
            ],
            "generated_at": _iso(),
        }

    # ── Audit-log integrity surface ────────────────────────────────
    @router.get("/api/security/audit-integrity")
    async def audit_integrity(current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE)
        rows = []
        for coll in APPEND_ONLY_COLLECTIONS:
            try:
                total = await db[coll].count_documents({})
                mutated = await db[coll].count_documents({"updated_at": {"$exists": True}})
            except Exception:
                total, mutated = 0, 0
            rows.append({
                "collection": coll,
                "total": total,
                "mutated": mutated,
                "immutable": (mutated == 0),
            })
        return {
            "collections": rows,
            "worst_status": "OK" if all(r["immutable"] for r in rows) else "TAMPERED",
            "generated_at": _iso(),
        }

    # ── Exception workflow ─────────────────────────────────────────
    @router.post("/api/security/exceptions")
    async def create_exception(body: ExceptionRequestBody,
                               current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await exc.create(current.get("email"), body)

    @router.get("/api/security/exceptions")
    async def list_exceptions(status_: Optional[str] = None,
                              current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE)
        q: Dict[str, Any] = {}
        if status_:
            q["status"] = status_
        return await db[EXC_REQ_COLL].find(
            q, {"_id": 0}).sort("requested_at", -1).to_list(500)

    @router.get("/api/security/exceptions/{exc_id}")
    async def get_exception(exc_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_COMPLIANCE)
        r = await db[EXC_REQ_COLL].find_one(
            {"security_exception_request_id": exc_id}, {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Not found")
        approvals = await db[EXC_APR_COLL].find(
            {"security_exception_request_id": exc_id}, {"_id": 0}
        ).sort("at", 1).to_list(500)
        r["approvals"] = approvals
        return r

    @router.post("/api/security/exceptions/{exc_id}/approve")
    async def approve_exception(exc_id: str,
                                body: ExceptionActionBody = Body(default_factory=ExceptionActionBody),
                                current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await exc.approve(exc_id, current.get("email"),
                                 current.get("role"), body.note)

    @router.post("/api/security/exceptions/{exc_id}/reject")
    async def reject_exception(exc_id: str,
                               body: ExceptionActionBody = Body(default_factory=ExceptionActionBody),
                               current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await exc.reject(exc_id, current.get("email"), body.note)

    @router.post("/api/security/exceptions/{exc_id}/revoke")
    async def revoke_exception(exc_id: str,
                               body: ExceptionActionBody = Body(default_factory=ExceptionActionBody),
                               current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await exc.revoke(exc_id, current.get("email"), body.note)

    @router.post("/api/security/exceptions/expire-due")
    async def expire_due(current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        return await exc.expire_due()

    return router
