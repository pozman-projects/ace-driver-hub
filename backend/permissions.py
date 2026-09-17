"""MR-07A · Shared permission helpers for canonical backend APIs.

Deliberately small. No policy engine, no DB-driven RBAC, no permission tables.
Consumers import these helpers instead of duplicating role-check literals.

Current ACE V1 roles (authoritative — sourced from `auth_module.UserRole`):
    Admin, Manager, Compliance, Allocator, ReadOnly

LOCKED V1 rules for Driver Account fields
    Sensitive fields: business_name, abn, payroll_number, payment_percentage
    Read allowed:  Admin, Manager
    Write allowed: Admin, Manager
"""
from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException


SENSITIVE_ACCOUNT_FIELDS: frozenset = frozenset(
    {"business_name", "abn", "payroll_number", "payment_percentage"}
)

ACCOUNT_READ_ROLES: frozenset = frozenset({"Admin", "Manager"})
ACCOUNT_WRITE_ROLES: frozenset = frozenset({"Admin", "Manager"})


def _role(user_or_role) -> str:
    if isinstance(user_or_role, str):
        return user_or_role
    if user_or_role is None:
        return ""
    return (user_or_role.get("role") or "") if isinstance(user_or_role, dict) else str(user_or_role)


def can_read_driver_account(user_or_role) -> bool:
    return _role(user_or_role) in ACCOUNT_READ_ROLES


def can_write_driver_account(user_or_role) -> bool:
    return _role(user_or_role) in ACCOUNT_WRITE_ROLES


def strip_driver_account_fields(driver: Optional[dict], user_or_role) -> Optional[dict]:
    """Return a NEW dict with sensitive account fields removed when the caller
    lacks account-read permission. Never mutates the input."""
    if not driver:
        return driver
    if can_read_driver_account(user_or_role):
        return driver
    out = dict(driver)
    for f in SENSITIVE_ACCOUNT_FIELDS:
        out.pop(f, None)
    return out


def strip_driver_account_fields_many(drivers: Iterable[dict], user_or_role):
    if can_read_driver_account(user_or_role):
        return list(drivers)
    out = []
    for d in drivers:
        if not d:
            out.append(d)
            continue
        clean = dict(d)
        for f in SENSITIVE_ACCOUNT_FIELDS:
            clean.pop(f, None)
        out.append(clean)
    return out


def enforce_driver_account_write(payload_fields: Iterable[str], user_or_role) -> None:
    """Raise 403 if the payload contains any sensitive account field and the
    caller cannot write account data. Message is field-name only — never
    value — so no denied value leaks."""
    if can_write_driver_account(user_or_role):
        return
    supplied = [f for f in payload_fields if f in SENSITIVE_ACCOUNT_FIELDS]
    if supplied:
        raise HTTPException(
            status_code=403,
            detail=(
                "Only Admin or Manager may set Driver account fields "
                f"({', '.join(sorted(supplied))})"
            ),
        )
