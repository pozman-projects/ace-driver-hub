"""MR-07B · Canonical role matrix for the ACE Driver Command Centre.

Single source of truth for role-based authorisation. Every backend router
imports the canonical predicate for the specific action it guards. There
is exactly one place per action that defines who is permitted.

Roles (locked, ACE V1):
    Admin, Manager, Compliance, Allocator, ReadOnly

DO NOT add or remove roles here. DO NOT weaken MR-07A protected helpers
in `permissions.py`. Sensitive-field enforcement stays in `permissions.py`
and is composed with these predicates at each call site.
"""
from __future__ import annotations

from typing import FrozenSet, Iterable, Optional

from fastapi import HTTPException


ROLES: FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance",
                                    "Allocator", "ReadOnly"})


# ----------------------------------------------------------------------
# Canonical action → allowed roles table (locked by owner MR-07B).
# ----------------------------------------------------------------------
# Driver master
CAN_EDIT_DRIVER_CORE:        FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_ARCHIVE_DRIVER:          FrozenSet[str] = frozenset({"Admin", "Manager"})
# Driver setup (Training / Probation / On Leave / Inactive; NOT Active)
CAN_EDIT_DRIVER_SETUP:       FrozenSet[str] = frozenset({"Admin", "Manager", "Allocator"})
# Driver comms preferences (MR-05/EB-09)
CAN_EDIT_DRIVER_COMMS:       FrozenSet[str] = frozenset({"Admin", "Manager", "Allocator"})

# Owner master + Driver-Owner relationship
CAN_EDIT_OWNER_MASTER:       FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_ARCHIVE_OWNER:           FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_MANAGE_DRIVER_OWNER:     FrozenSet[str] = frozenset({"Admin", "Manager"})

# Vehicle master
CAN_EDIT_VEHICLE_MASTER:     FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_ARCHIVE_VEHICLE:         FrozenSet[str] = frozenset({"Admin", "Manager"})
# Driver ↔ Vehicle is operational allocation
CAN_ASSIGN_DRIVER_VEHICLE:   FrozenSet[str] = frozenset({"Admin", "Manager", "Allocator"})

# Equipment master
CAN_EDIT_EQUIPMENT_MASTER:   FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_ARCHIVE_EQUIPMENT:       FrozenSet[str] = frozenset({"Admin", "Manager"})
# Driver ↔ Equipment is operational allocation
CAN_ASSIGN_DRIVER_EQUIPMENT: FrozenSet[str] = frozenset({"Admin", "Manager", "Allocator"})
# Vehicle ↔ Equipment is treated as master physical configuration
# (Prime Mover ↔ Tray/Trailer coupling represents current physical setup).
CAN_COUPLE_VEHICLE_EQUIPMENT: FrozenSet[str] = frozenset({"Admin", "Manager"})

# Compliance evidence (Licence / Registration / Insurance / Inspection /
# Defect / Maintenance / Equipment Compliance).
CAN_EDIT_COMPLIANCE:         FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_ARCHIVE_COMPLIANCE:      FrozenSet[str] = frozenset({"Admin", "Manager"})

# Documents
CAN_UPLOAD_DOCUMENT:         FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance", "Allocator"})
CAN_EDIT_DOCUMENT_METADATA_STANDARD:     FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_EDIT_DOCUMENT_METADATA_CONFIDENTIAL: FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_EDIT_DOCUMENT_METADATA_RESTRICTED:   FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_DELETE_DOCUMENT:         FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_REVIEW_DOCUMENT_STANDARD:     FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_REVIEW_DOCUMENT_CONFIDENTIAL: FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_REVIEW_DOCUMENT_RESTRICTED:   FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_SIGN_DOCUMENT:           FrozenSet[str] = frozenset({"Admin", "Manager"})

# Notifications
CAN_MARK_NOTIFICATION_READ:  FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance", "Allocator"})
CAN_ACK_NOTIFICATION:        FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance", "Allocator"})
CAN_SNOOZE_NOTIFICATION:     FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance", "Allocator"})
CAN_RESOLVE_NOTIFICATION:    FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_REOPEN_NOTIFICATION:     FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_DELETE_NOTIFICATION:     FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_MANAGE_NOTIFICATION_RULES: FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_RUN_COMPLIANCE_SCAN:     FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance"})
CAN_ADMIN_NOTIFICATION_OUTBOX: FrozenSet[str] = frozenset({"Admin", "Manager"})

# Activation
CAN_ACTIVATE_DRIVER:         FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_APPROVE_ACTIVATION_OVERRIDE: FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_REQUEST_ACTIVATION_OVERRIDE: FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance", "Allocator"})
CAN_MANAGE_ACTIVATION_TEMPLATES: FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_RUN_ACTIVATION_JOBS:     FrozenSet[str] = frozenset({"Admin", "Manager"})

# Numbering
CAN_WRITE_NUMBERING:         FrozenSet[str] = frozenset({"Admin", "Manager", "Allocator"})
CAN_READ_NUMBERING_OPERATIONAL: FrozenSet[str] = frozenset({"Admin", "Manager", "Allocator"})
CAN_AUDIT_NUMBERING:         FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_EDIT_NUMBER_SEQUENCE:    FrozenSet[str] = frozenset({"Admin"})

# Admin / Settings
CAN_MANAGE_USERS:            FrozenSet[str] = frozenset({"Admin"})
CAN_ADMIN_STORAGE:           FrozenSet[str] = frozenset({"Admin"})
CAN_ADMIN_AUTOMATION:        FrozenSet[str] = frozenset({"Admin"})
CAN_USE_RECOVERY:            FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_COMMIT_MIGRATION:        FrozenSet[str] = frozenset({"Admin", "Manager"})
CAN_VALIDATE_MIGRATION:      FrozenSet[str] = frozenset({"Admin", "Manager", "Compliance", "Allocator"})


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _role(user_or_role) -> str:
    if isinstance(user_or_role, str):
        return user_or_role
    if user_or_role is None:
        return ""
    return (user_or_role.get("role") or "") if isinstance(user_or_role, dict) else str(user_or_role)


def has(role_or_user, allowed: Iterable[str]) -> bool:
    """Return True if the given role/user is in ``allowed``."""
    return _role(role_or_user) in set(allowed)


def require(role_or_user, allowed: Iterable[str],
            detail: Optional[str] = None) -> None:
    """Raise ``HTTPException(403)`` unless the caller is in ``allowed``.

    Callers should pass a canonical CAN_* frozenset from this module.
    """
    if not has(role_or_user, allowed):
        raise HTTPException(
            status_code=403,
            detail=detail or "Insufficient permissions for this action",
        )


def deny_readonly(user_or_role, detail: str = "ReadOnly role cannot mutate") -> None:
    """Preserve MR-07A/EB-13 minimum guarantee. ReadOnly may never mutate."""
    if _role(user_or_role) == "ReadOnly":
        raise HTTPException(status_code=403, detail=detail)


# ----------------------------------------------------------------------
# document sensitivity → capability sets (composed helper)
# ----------------------------------------------------------------------
_DOC_METADATA_BY_SENSITIVITY = {
    "Standard":     CAN_EDIT_DOCUMENT_METADATA_STANDARD,
    "Internal":     CAN_EDIT_DOCUMENT_METADATA_STANDARD,
    "Confidential": CAN_EDIT_DOCUMENT_METADATA_CONFIDENTIAL,
    "Restricted":   CAN_EDIT_DOCUMENT_METADATA_RESTRICTED,
}
_DOC_REVIEW_BY_SENSITIVITY = {
    "Standard":     CAN_REVIEW_DOCUMENT_STANDARD,
    "Internal":     CAN_REVIEW_DOCUMENT_STANDARD,
    "Confidential": CAN_REVIEW_DOCUMENT_CONFIDENTIAL,
    "Restricted":   CAN_REVIEW_DOCUMENT_RESTRICTED,
}


def can_edit_document_metadata(user_or_role, sensitivity: str) -> bool:
    allowed = _DOC_METADATA_BY_SENSITIVITY.get(sensitivity,
                                                 CAN_EDIT_DOCUMENT_METADATA_RESTRICTED)
    return has(user_or_role, allowed)


def can_review_document(user_or_role, sensitivity: str) -> bool:
    allowed = _DOC_REVIEW_BY_SENSITIVITY.get(sensitivity,
                                              CAN_REVIEW_DOCUMENT_RESTRICTED)
    return has(user_or_role, allowed)
