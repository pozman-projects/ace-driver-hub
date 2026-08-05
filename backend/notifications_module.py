"""
EB-07a — Notifications, Alerts & Escalation Engine (backend).

Canonical DCC notification engine. Consumes canonical events from EB-04
compliance, EB-05 documents and EB-06 imports; produces deduplicated,
auditable, in-app notifications with simulated email and SMS deliveries.

No external provider is contacted in development. Email and SMS deliveries
are recorded with status `Simulated`; the rendered content is inspectable
via the development outbox.

This file is deliberately self-contained: constants, models, engine,
router, seed and helpers are all here so the module can be reasoned about
as a unit and unit-tested end-to-end without touching legacy code.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from compliance_records import (
    DEFECTS_COLL,
    INSPECTIONS_COLL,
    INSURANCE_COLL,
    LICENCES_COLL,
    MAINTENANCE_COLL,
    REGISTRATIONS_COLL,
    EQUIPMENT_COMPLIANCE_COLL,
    ComplianceStatus,
    _classify_expiry,
    _parse_date,
)
from registers import DRIVERS_COLL, EQUIPMENT_COLL, OWNERS_COLL, VEHICLES_COLL

logger = logging.getLogger("dcc.notifications")

# ---------------------------------------------------------------- collections
RULES_COLL = "notification_rules"
EVENTS_COLL = "notification_events"
NOTIFS_COLL = "notifications"
RECIPIENTS_COLL = "notification_recipients"
DELIVERIES_COLL = "notification_deliveries"
ACKS_COLL = "notification_acknowledgements"
SNOOZES_COLL = "notification_snoozes"
ESCALATIONS_COLL = "notification_escalations"
JOB_RUNS_COLL = "notification_job_runs"
DEAD_LETTERS_COLL = "notification_dead_letters"
PREFS_COLL = "notification_preferences"

SEED_TAG = "seed-eb07"

# ---------------------------------------------------------------- controlled vocabularies
class EventType(str, Enum):
    ComplianceDueSoon = "Compliance Due Soon"
    ComplianceExpired = "Compliance Expired"
    ComplianceMissing = "Compliance Missing"
    ComplianceUnderReview = "Compliance Under Review"
    CriticalDefect = "Critical Vehicle Defect"
    HighDefect = "High Vehicle Defect"
    MaintenanceDueSoon = "Maintenance Due Soon"
    MaintenanceOverdue = "Maintenance Overdue"
    DriverActivationIncomplete = "Driver Activation Incomplete"
    DriverActivationOverrideExpiring = "Driver Activation Override Expiring"
    DocumentUnderReview = "Document Under Review"
    DocumentRejected = "Document Rejected"
    ImportValidationFailed = "Import Validation Failed"
    ImportReadyToCommit = "Import Ready to Commit"
    ImportPartiallyCommitted = "Import Partially Committed"
    ImportCommitFailed = "Import Commit Failed"
    ImportRollbackFailed = "Import Rollback Failed"
    ManualNotification = "Manual Notification"
    Other = "Other"


class EntityType(str, Enum):
    Driver = "Driver"
    Owner = "Owner"
    Vehicle = "Vehicle"
    Equipment = "Equipment"
    DriverLicence = "DriverLicence"
    VehicleRegistration = "VehicleRegistration"
    VehicleInsurancePolicy = "VehicleInsurancePolicy"
    VehicleInspection = "VehicleInspection"
    VehicleDefect = "VehicleDefect"
    VehicleMaintenanceTask = "VehicleMaintenanceTask"
    EquipmentCompliance = "EquipmentCompliance"
    Document = "Document"
    ImportJob = "ImportJob"
    DriverActivation = "DriverActivation"
    General = "General"


class Severity(str, Enum):
    Information = "Information"
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Critical = "Critical"


SEVERITY_ORDER = {
    Severity.Information.value: 10,
    Severity.Low.value: 20,
    Severity.Medium.value: 30,
    Severity.High.value: 40,
    Severity.Critical.value: 50,
}


class Channel(str, Enum):
    InApp = "In App"
    Email = "Email"
    SMS = "SMS"


class NotificationStatus(str, Enum):
    New = "New"
    Active = "Active"
    Acknowledged = "Acknowledged"
    Snoozed = "Snoozed"
    Escalated = "Escalated"
    Resolved = "Resolved"
    DeliveryFailed = "Delivery Failed"
    Archived = "Archived"


class DeliveryStatus(str, Enum):
    Pending = "Pending"
    Queued = "Queued"
    Simulated = "Simulated"
    Sent = "Sent"
    Delivered = "Delivered"
    Failed = "Failed"
    RetryScheduled = "Retry Scheduled"
    Cancelled = "Cancelled"
    Suppressed = "Suppressed"


class DigestMode(str, Enum):
    Immediate = "Immediate"
    HourlyDigest = "Hourly Digest"
    DailyDigest = "Daily Digest"
    WeeklyDigest = "Weekly Digest"
    NoneMode = "None"


class RecipientType(str, Enum):
    DCCUser = "DCC User"
    Driver = "Driver"
    Owner = "Owner"
    Manager = "Manager"
    ComplianceTeam = "Compliance Team"
    Allocator = "Allocator"
    Administrator = "Administrator"
    Custom = "Custom"
    System = "System"


class RecipientStrategy(str, Enum):
    AssignedCompliance = "Assigned Compliance Team"
    AllCompliance = "All Compliance users"
    AllManagers = "All Managers"
    AllAdmins = "All Administrators"
    AssignedAllocator = "Assigned Allocator"
    DriverOnly = "Driver"
    OwnerOnly = "Owner"
    DriverAndOwner = "Driver and Owner"
    DriverOwnerCompliance = "Driver, Owner and Compliance"
    RecordCreator = "Record Creator"
    Custom = "Custom Recipients"
    NoExternal = "No External Recipient"


class JobStatus(str, Enum):
    Running = "Running"
    Completed = "Completed"
    CompletedWithWarnings = "Completed with Warnings"
    Failed = "Failed"
    Cancelled = "Cancelled"


class DeadLetterStatus(str, Enum):
    Open = "Open"
    Retrying = "Retrying"
    Resolved = "Resolved"
    Abandoned = "Abandoned"


# ---------------------------------------------------------------- helpers
def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _hash_key(*parts: str) -> str:
    h = hashlib.sha256("::".join(str(p or "") for p in parts).encode("utf-8")).hexdigest()
    return h[:32]


def _event_key(event_type: str, entity_type: str, entity_id: str, source_record_id: str,
               scope: str = "") -> str:
    """Deterministic event key.

    Repeated processing of the same logical event must NOT create duplicate
    notifications. Two events with the same key are the same event.
    """
    return _hash_key(event_type, entity_type, entity_id, source_record_id, scope)


def _dedup_key(event_type: str, entity_type: str, entity_id: str,
               source_record_id: str) -> str:
    """Deduplication key for the notification itself (independent of scope)."""
    return _hash_key("dedup", event_type, entity_type, entity_id, source_record_id)


def _severity_gte(a: str, b: str) -> bool:
    return SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0)


# ---------------------------------------------------------------- default snooze ceilings
DEFAULT_SNOOZE_HOURS = {
    Severity.Information.value: 30 * 24,
    Severity.Low.value: 30 * 24,
    Severity.Medium.value: 14 * 24,
    Severity.High.value: 7 * 24,
    Severity.Critical.value: 24,
}


# ---------------------------------------------------------------- retry schedule (in minutes from previous attempt)
DEFAULT_RETRY_SCHEDULE_MINUTES = [0, 5, 30, 120, 720]
MAX_DELIVERY_ATTEMPTS = len(DEFAULT_RETRY_SCHEDULE_MINUTES)


# ---------------------------------------------------------------- templates
TEMPLATES: Dict[str, Dict[str, str]] = {
    "compliance_due_soon": {
        "title": "{entity_label} · {component} due soon",
        "message": "{component} for {entity_label} expires on {expiry_date} ({days_until} days).",
        "email_subject": "[DCC] {component} due soon — {entity_label}",
        "email_body": "The {component} for {entity_label} expires on {expiry_date} ({days_until} days remaining). Please action or renew.",
        "sms_body": "DCC: {component} for {entity_label} due {expiry_date}.",
    },
    "compliance_expired": {
        "title": "{entity_label} · {component} EXPIRED",
        "message": "{component} for {entity_label} expired on {expiry_date} ({days_expired} days ago).",
        "email_subject": "[DCC] {component} EXPIRED — {entity_label}",
        "email_body": "The {component} for {entity_label} expired on {expiry_date} ({days_expired} days ago). Immediate action required.",
        "sms_body": "DCC: {component} for {entity_label} EXPIRED {expiry_date}.",
    },
    "compliance_missing": {
        "title": "{entity_label} · {component} missing",
        "message": "No active {component} on record for {entity_label}.",
        "email_subject": "[DCC] {component} missing — {entity_label}",
        "email_body": "No active {component} is on record for {entity_label}. Please attach or create the record.",
        "sms_body": "DCC: {component} missing for {entity_label}.",
    },
    "critical_defect": {
        "title": "{entity_label} · Critical defect",
        "message": "Critical defect open on {entity_label}: {description}.",
        "email_subject": "[DCC] Critical defect — {entity_label}",
        "email_body": "A CRITICAL defect is open on {entity_label}: {description}. Immediate attention required.",
        "sms_body": "DCC: CRITICAL defect on {entity_label}.",
    },
    "high_defect": {
        "title": "{entity_label} · High defect",
        "message": "High-severity defect open on {entity_label}: {description}.",
        "email_subject": "[DCC] High defect — {entity_label}",
        "email_body": "A HIGH-severity defect is open on {entity_label}: {description}.",
        "sms_body": "DCC: HIGH defect on {entity_label}.",
    },
    "maintenance_due_soon": {
        "title": "{entity_label} · Maintenance due soon",
        "message": "{task_type} due on {due_date} for {entity_label}.",
        "email_subject": "[DCC] Maintenance due soon — {entity_label}",
        "email_body": "The scheduled {task_type} is due on {due_date} for {entity_label}.",
        "sms_body": "DCC: {task_type} due {due_date} — {entity_label}.",
    },
    "maintenance_overdue": {
        "title": "{entity_label} · Maintenance OVERDUE",
        "message": "{task_type} was due on {due_date} for {entity_label} and remains open.",
        "email_subject": "[DCC] Maintenance OVERDUE — {entity_label}",
        "email_body": "The scheduled {task_type} for {entity_label} was due on {due_date} and is now overdue.",
        "sms_body": "DCC: {task_type} OVERDUE — {entity_label}.",
    },
    "driver_activation_incomplete": {
        "title": "{entity_label} · Activation incomplete",
        "message": "Driver activation checklist for {entity_label} has outstanding mandatory items.",
        "email_subject": "[DCC] Activation incomplete — {entity_label}",
        "email_body": "The activation checklist for {entity_label} still has outstanding mandatory items.",
        "sms_body": "DCC: Activation incomplete — {entity_label}.",
    },
    "document_under_review": {
        "title": "{entity_label} · Document under review",
        "message": "Document '{document_title}' is Under Review.",
        "email_subject": "[DCC] Document under review — {document_title}",
        "email_body": "The document '{document_title}' (linked to {entity_label}) is Under Review.",
        "sms_body": "DCC: '{document_title}' under review.",
    },
    "document_rejected": {
        "title": "{entity_label} · Document rejected",
        "message": "Document '{document_title}' was Rejected.",
        "email_subject": "[DCC] Document rejected — {document_title}",
        "email_body": "The document '{document_title}' (linked to {entity_label}) was Rejected.",
        "sms_body": "DCC: '{document_title}' rejected.",
    },
    "import_validation_failed": {
        "title": "Import job {job_ref} · validation failed",
        "message": "Import into {target_domain} has {error_rows} rows with errors.",
        "email_subject": "[DCC] Import validation failed — {target_domain}",
        "email_body": "Import job {job_ref} into {target_domain} has {error_rows} rows with errors and cannot be committed.",
        "sms_body": "DCC: Import {job_ref} failed validation.",
    },
    "import_ready_to_commit": {
        "title": "Import job {job_ref} · ready to commit",
        "message": "Import into {target_domain} is validated and ready to commit ({valid_rows} rows).",
        "email_subject": "[DCC] Import ready to commit — {target_domain}",
        "email_body": "Import job {job_ref} into {target_domain} passed validation and is ready to commit ({valid_rows} valid rows).",
        "sms_body": "DCC: Import {job_ref} ready to commit.",
    },
    "import_partial_commit": {
        "title": "Import job {job_ref} · partially committed",
        "message": "Import into {target_domain} committed with warnings.",
        "email_subject": "[DCC] Import partially committed — {target_domain}",
        "email_body": "Import job {job_ref} into {target_domain} completed with warnings. Review the audit log.",
        "sms_body": "DCC: Import {job_ref} partial commit.",
    },
    "import_commit_failed": {
        "title": "Import job {job_ref} · commit failed",
        "message": "Import into {target_domain} FAILED at commit.",
        "email_subject": "[DCC] Import commit failed — {target_domain}",
        "email_body": "Import job {job_ref} into {target_domain} failed during commit.",
        "sms_body": "DCC: Import {job_ref} commit FAILED.",
    },
    "manual_notification": {
        "title": "{title}",
        "message": "{message}",
        "email_subject": "[DCC] {title}",
        "email_body": "{message}",
        "sms_body": "DCC: {title}",
    },
}


def render_template(key: str, payload: Dict[str, Any]) -> Dict[str, str]:
    tpl = TEMPLATES.get(key) or TEMPLATES["manual_notification"]
    safe = {k: ("" if v is None else str(v)) for k, v in (payload or {}).items()}
    out: Dict[str, str] = {}
    for tk, tv in tpl.items():
        try:
            out[tk] = tv.format_map(_SafeMap(safe))
        except Exception:
            out[tk] = tv
    return out


class _SafeMap(dict):
    def __missing__(self, key):
        return "{" + key + "}"


# ---------------------------------------------------------------- default rules
DEFAULT_RULES: List[Dict[str, Any]] = [
    {
        "name": "Compliance · Due Soon (30d)",
        "description": "Warn when a compliance record is within the warning window.",
        "event_type": EventType.ComplianceDueSoon.value,
        "entity_type": None,
        "conditions": {},
        "severity": Severity.Medium.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.AllCompliance.value,
        "warning_days": 30,
        "repeat_interval_hours": 14 * 24,
        "escalation_policy": {"levels": [{"after_hours": 23 * 24, "to_severity": Severity.High.value}]},
        "template_key": "compliance_due_soon",
        "is_active": True,
        "priority": 100,
    },
    {
        "name": "Compliance · Expired",
        "description": "Immediate high alert when a compliance record has expired.",
        "event_type": EventType.ComplianceExpired.value,
        "entity_type": None,
        "conditions": {},
        "severity": Severity.High.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.AllCompliance.value,
        "warning_days": 0,
        "repeat_interval_hours": 24,
        "escalation_policy": {"levels": [{"after_hours": 3 * 24, "to_severity": Severity.Critical.value}]},
        "template_key": "compliance_expired",
        "is_active": True,
        "priority": 90,
    },
    {
        "name": "Compliance · Missing",
        "description": "Alert when no active primary compliance record exists.",
        "event_type": EventType.ComplianceMissing.value,
        "entity_type": None,
        "conditions": {},
        "severity": Severity.High.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.AllCompliance.value,
        "warning_days": 0,
        "repeat_interval_hours": 3 * 24,
        "escalation_policy": {"levels": []},
        "template_key": "compliance_missing",
        "is_active": True,
        "priority": 95,
    },
    {
        "name": "Critical Vehicle Defect",
        "description": "Immediate critical alert on any open critical defect.",
        "event_type": EventType.CriticalDefect.value,
        "entity_type": EntityType.Vehicle.value,
        "conditions": {},
        "severity": Severity.Critical.value,
        "channels": [Channel.InApp.value, Channel.Email.value, Channel.SMS.value],
        "recipient_strategy": RecipientStrategy.AllManagers.value,
        "warning_days": 0,
        "repeat_interval_hours": 4,
        "escalation_policy": {"levels": [{"after_hours": 24, "to_severity": Severity.Critical.value,
                                          "expand_to": RecipientStrategy.AllAdmins.value}]},
        "template_key": "critical_defect",
        "is_active": True,
        "priority": 10,
    },
    {
        "name": "High Vehicle Defect",
        "description": "High-severity alert on open high defects.",
        "event_type": EventType.HighDefect.value,
        "entity_type": EntityType.Vehicle.value,
        "conditions": {},
        "severity": Severity.High.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.AllManagers.value,
        "warning_days": 0,
        "repeat_interval_hours": 24,
        "escalation_policy": {"levels": []},
        "template_key": "high_defect",
        "is_active": True,
        "priority": 20,
    },
    {
        "name": "Maintenance Due Soon",
        "description": "Warn when a scheduled maintenance task is due within the window.",
        "event_type": EventType.MaintenanceDueSoon.value,
        "entity_type": EntityType.Vehicle.value,
        "conditions": {},
        "severity": Severity.Medium.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.AllManagers.value,
        "warning_days": 14,
        "repeat_interval_hours": 7 * 24,
        "escalation_policy": {"levels": []},
        "template_key": "maintenance_due_soon",
        "is_active": True,
        "priority": 60,
    },
    {
        "name": "Maintenance Overdue",
        "description": "Alert when scheduled maintenance is past the due date.",
        "event_type": EventType.MaintenanceOverdue.value,
        "entity_type": EntityType.Vehicle.value,
        "conditions": {},
        "severity": Severity.High.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.AllManagers.value,
        "warning_days": 0,
        "repeat_interval_hours": 24,
        "escalation_policy": {"levels": [{"after_hours": 3 * 24, "to_severity": Severity.Critical.value}]},
        "template_key": "maintenance_overdue",
        "is_active": True,
        "priority": 30,
    },
    {
        "name": "Document Under Review",
        "description": "Track documents parked in Under Review.",
        "event_type": EventType.DocumentUnderReview.value,
        "entity_type": EntityType.Document.value,
        "conditions": {},
        "severity": Severity.Low.value,
        "channels": [Channel.InApp.value],
        "recipient_strategy": RecipientStrategy.AllCompliance.value,
        "warning_days": 0,
        "repeat_interval_hours": 3 * 24,
        "escalation_policy": {"levels": []},
        "template_key": "document_under_review",
        "is_active": True,
        "priority": 200,
    },
    {
        "name": "Document Rejected",
        "description": "Track documents rejected during review.",
        "event_type": EventType.DocumentRejected.value,
        "entity_type": EntityType.Document.value,
        "conditions": {},
        "severity": Severity.Medium.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.AllCompliance.value,
        "warning_days": 0,
        "repeat_interval_hours": 24,
        "escalation_policy": {"levels": []},
        "template_key": "document_rejected",
        "is_active": True,
        "priority": 150,
    },
    {
        "name": "Import Validation Failed",
        "description": "Alert when a spreadsheet import fails validation.",
        "event_type": EventType.ImportValidationFailed.value,
        "entity_type": EntityType.ImportJob.value,
        "conditions": {},
        "severity": Severity.Medium.value,
        "channels": [Channel.InApp.value],
        "recipient_strategy": RecipientStrategy.RecordCreator.value,
        "warning_days": 0,
        "repeat_interval_hours": 0,
        "escalation_policy": {"levels": []},
        "template_key": "import_validation_failed",
        "is_active": True,
        "priority": 180,
    },
    {
        "name": "Import Ready to Commit",
        "description": "Notify creator when the dry-run is clean.",
        "event_type": EventType.ImportReadyToCommit.value,
        "entity_type": EntityType.ImportJob.value,
        "conditions": {},
        "severity": Severity.Information.value,
        "channels": [Channel.InApp.value],
        "recipient_strategy": RecipientStrategy.RecordCreator.value,
        "warning_days": 0,
        "repeat_interval_hours": 0,
        "escalation_policy": {"levels": []},
        "template_key": "import_ready_to_commit",
        "is_active": True,
        "priority": 210,
    },
    {
        "name": "Import Partially Committed",
        "description": "Notify creator when a commit only partially succeeded.",
        "event_type": EventType.ImportPartiallyCommitted.value,
        "entity_type": EntityType.ImportJob.value,
        "conditions": {},
        "severity": Severity.Medium.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.RecordCreator.value,
        "warning_days": 0,
        "repeat_interval_hours": 0,
        "escalation_policy": {"levels": []},
        "template_key": "import_partial_commit",
        "is_active": True,
        "priority": 170,
    },
    {
        "name": "Import Commit Failed",
        "description": "Escalate an import that failed at commit.",
        "event_type": EventType.ImportCommitFailed.value,
        "entity_type": EntityType.ImportJob.value,
        "conditions": {},
        "severity": Severity.High.value,
        "channels": [Channel.InApp.value, Channel.Email.value],
        "recipient_strategy": RecipientStrategy.RecordCreator.value,
        "warning_days": 0,
        "repeat_interval_hours": 0,
        "escalation_policy": {"levels": []},
        "template_key": "import_commit_failed",
        "is_active": True,
        "priority": 40,
    },
]


# =============================================================================
#  Engine
# =============================================================================
class NotificationsEngine:
    def __init__(self, db):
        self.db = db

    # -------------------------------------------------- rule ops
    async def _active_rules_for(self, event_type: str, entity_type: Optional[str]) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"event_type": event_type, "is_active": True, "is_archived": {"$ne": True}}
        rules = await self.db[RULES_COLL].find(q, {"_id": 0}).sort("priority", 1).to_list(200)
        # Filter by entity_type (None on rule means "any entity type")
        return [r for r in rules if not r.get("entity_type") or r.get("entity_type") == entity_type]

    # -------------------------------------------------- recipient resolution
    async def _resolve_recipients(self, strategy: str, event: Dict[str, Any],
                                  channels: List[str], custom: Optional[List[Dict[str, Any]]] = None
                                  ) -> List[Dict[str, Any]]:
        """Return a list of recipient dicts (not yet persisted)."""
        out: List[Dict[str, Any]] = []
        role_map = {
            RecipientStrategy.AllCompliance.value: ["Compliance"],
            RecipientStrategy.AllManagers.value: ["Manager"],
            RecipientStrategy.AllAdmins.value: ["Admin"],
            RecipientStrategy.AssignedCompliance.value: ["Compliance"],
            RecipientStrategy.AssignedAllocator.value: ["Allocator"],
        }
        if strategy == RecipientStrategy.NoExternal.value:
            return out
        if strategy in role_map:
            users = await self.db.users.find({"role": {"$in": role_map[strategy]}},
                                             {"_id": 0}).to_list(500)
            for u in users:
                for ch in channels:
                    out.append({
                        "recipient_type": self._recipient_type_for_role(u.get("role")),
                        "user_id": u["id"],
                        "email_address": u.get("email") if ch == Channel.Email.value else None,
                        "mobile_number": None,  # DCC users have no mobile on record — SMS is suppressed
                        "display_name": u.get("full_name") or u.get("email"),
                        "channel": ch,
                        "is_primary": ch == Channel.InApp.value,
                        "recipient_reason": f"Role {u.get('role')} matched strategy {strategy}",
                    })
        elif strategy in (RecipientStrategy.DriverOnly.value,
                          RecipientStrategy.DriverAndOwner.value,
                          RecipientStrategy.DriverOwnerCompliance.value):
            drv_id = (event.get("payload") or {}).get("driver_id")
            if drv_id:
                drv = await self.db[DRIVERS_COLL].find_one({"id": drv_id}, {"_id": 0})
                if drv:
                    for ch in channels:
                        # Snapshot email/mobile from canonical driver for delivery history only
                        out.append({
                            "recipient_type": RecipientType.Driver.value,
                            "driver_id": drv_id,
                            "email_address": drv.get("email") if ch == Channel.Email.value else None,
                            "mobile_number": drv.get("mobile_number") if ch == Channel.SMS.value else None,
                            "display_name": drv.get("full_name") or drv.get("name") or drv_id,
                            "channel": ch,
                            "is_primary": ch == Channel.InApp.value,
                            "recipient_reason": f"Driver strategy {strategy}",
                        })
        elif strategy in (RecipientStrategy.OwnerOnly.value,
                          RecipientStrategy.DriverAndOwner.value):
            own_id = (event.get("payload") or {}).get("owner_id")
            if own_id:
                own = await self.db[OWNERS_COLL].find_one({"id": own_id}, {"_id": 0})
                if own:
                    for ch in channels:
                        out.append({
                            "recipient_type": RecipientType.Owner.value,
                            "owner_id": own_id,
                            "email_address": own.get("primary_email") if ch == Channel.Email.value else None,
                            "mobile_number": None,
                            "display_name": own.get("name") or own.get("trading_name") or own_id,
                            "channel": ch,
                            "is_primary": ch == Channel.InApp.value,
                            "recipient_reason": f"Owner strategy {strategy}",
                        })
        elif strategy == RecipientStrategy.RecordCreator.value:
            creator_email = (event.get("payload") or {}).get("created_by")
            if creator_email:
                user = await self.db.users.find_one({"email": creator_email}, {"_id": 0})
                if user:
                    for ch in channels:
                        out.append({
                            "recipient_type": RecipientType.DCCUser.value,
                            "user_id": user["id"],
                            "email_address": user.get("email") if ch == Channel.Email.value else None,
                            "mobile_number": None,
                            "display_name": user.get("full_name") or user.get("email"),
                            "channel": ch,
                            "is_primary": ch == Channel.InApp.value,
                            "recipient_reason": "Record creator",
                        })
        elif strategy == RecipientStrategy.Custom.value and custom:
            for c in custom:
                out.append({**c, "recipient_reason": c.get("recipient_reason", "Custom recipient")})

        # Include compliance role also for DriverOwnerCompliance
        if strategy == RecipientStrategy.DriverOwnerCompliance.value:
            more = await self._resolve_recipients(
                RecipientStrategy.AllCompliance.value, event, channels
            )
            out.extend(more)

        # Suppress recipients missing the required contact for their channel
        cleaned: List[Dict[str, Any]] = []
        for r in out:
            if r["channel"] == Channel.Email.value and not r.get("email_address"):
                r["channel"] = Channel.InApp.value
                r["is_primary"] = True
                r["recipient_reason"] += " (email missing → in-app only)"
            if r["channel"] == Channel.SMS.value and not r.get("mobile_number"):
                # Suppress SMS entirely when there's no mobile
                continue
            cleaned.append(r)
        return cleaned

    @staticmethod
    def _recipient_type_for_role(role: str) -> str:
        mapping = {
            "Admin": RecipientType.Administrator.value,
            "Manager": RecipientType.Manager.value,
            "Compliance": RecipientType.ComplianceTeam.value,
            "Allocator": RecipientType.Allocator.value,
        }
        return mapping.get(role, RecipientType.DCCUser.value)

    # -------------------------------------------------- event ingestion
    async def emit_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        source_record_id: str,
        payload: Dict[str, Any],
        severity: Optional[str] = None,
        source_status: Optional[str] = None,
        scope: str = "",
        correlation_id: Optional[str] = None,
        source: str = "engine",
    ) -> Dict[str, Any]:
        """Append or update the canonical event, then process it idempotently."""
        key = _event_key(event_type, entity_type, entity_id, source_record_id, scope)
        existing = await self.db[EVENTS_COLL].find_one({"event_key": key}, {"_id": 0})
        now = _iso()
        if existing:
            # Idempotent: refresh last-seen data but don't create a duplicate
            await self.db[EVENTS_COLL].update_one(
                {"event_key": key},
                {"$set": {"payload": payload, "severity": severity or existing.get("severity"),
                          "source_status": source_status or existing.get("source_status"),
                          "occurred_at": now, "is_processed": False}},
            )
            event = await self.db[EVENTS_COLL].find_one({"event_key": key}, {"_id": 0})
        else:
            event = {
                "notification_event_id": _uuid(),
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "source_record_id": source_record_id,
                "source_status": source_status,
                "severity": severity,
                "event_key": key,
                "occurred_at": now,
                "detected_at": now,
                "payload": payload or {},
                "correlation_id": correlation_id or _uuid(),
                "is_processed": False,
                "processed_at": None,
                "processing_result": None,
                "created_at": now,
                "_source": source,
            }
            await self.db[EVENTS_COLL].insert_one(event)
            event.pop("_id", None)
        # Process synchronously (small volume; predictable for tests)
        result = await self._process_event(event)
        return {"event": event, "result": result}

    async def _process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        rules = await self._active_rules_for(event["event_type"], event.get("entity_type"))
        created: List[str] = []
        updated: List[str] = []
        deliveries_created = 0
        for rule in rules:
            notif, is_new = await self._create_or_update_notification(rule, event)
            if is_new:
                created.append(notif["notification_id"])
            else:
                updated.append(notif["notification_id"])
            deliveries_created += await self._materialise_deliveries(rule, notif, event)
        await self.db[EVENTS_COLL].update_one(
            {"event_key": event["event_key"]},
            {"$set": {"is_processed": True, "processed_at": _iso(),
                      "processing_result": {"created": created, "updated": updated,
                                            "deliveries_created": deliveries_created}}},
        )
        return {"created": created, "updated": updated, "deliveries_created": deliveries_created}

    # -------------------------------------------------- notification lifecycle
    async def _create_or_update_notification(self, rule: Dict[str, Any],
                                             event: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        dedup = _dedup_key(event["event_type"], event["entity_type"], event["entity_id"],
                           event["source_record_id"])
        rendered = render_template(rule.get("template_key") or "manual_notification",
                                   {**(event.get("payload") or {}),
                                    "entity_label": (event.get("payload") or {}).get("entity_label")
                                    or event["entity_id"]})
        now = _iso()
        # Find existing active notification for this dedup key
        existing = await self.db[NOTIFS_COLL].find_one(
            {"deduplication_key": dedup, "status": {"$nin": [NotificationStatus.Resolved.value,
                                                              NotificationStatus.Archived.value]}},
            {"_id": 0},
        )
        if existing:
            update = {
                "last_triggered_at": now,
                "title": rendered.get("title") or existing["title"],
                "message": rendered.get("message") or existing["message"],
                "severity": self._max_severity(existing.get("severity"), rule.get("severity")),
                "updated_at": now,
                "notification_event_id": event["notification_event_id"],
                "notification_rule_id": rule["notification_rule_id"],
            }
            # Advance status from New → Active if untouched
            if existing.get("status") == NotificationStatus.New.value:
                update["status"] = NotificationStatus.Active.value
            await self.db[NOTIFS_COLL].update_one({"notification_id": existing["notification_id"]},
                                                  {"$set": update})
            merged = {**existing, **update}
            return merged, False
        notif = {
            "notification_id": _uuid(),
            "notification_rule_id": rule["notification_rule_id"],
            "notification_event_id": event["notification_event_id"],
            "entity_type": event["entity_type"],
            "entity_id": event["entity_id"],
            "source_record_id": event["source_record_id"],
            "title": rendered.get("title") or "Notification",
            "message": rendered.get("message") or "",
            "severity": rule.get("severity") or Severity.Medium.value,
            "status": NotificationStatus.Active.value,
            "priority": rule.get("priority", 100),
            "first_triggered_at": now,
            "last_triggered_at": now,
            "next_repeat_at": self._next_repeat_at(rule, now),
            "resolved_at": None,
            "resolved_by": None,
            "resolution_reason": None,
            "deduplication_key": dedup,
            "is_read": False,
            "read_at": None,
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "_source": event.get("_source") or "engine",
        }
        await self.db[NOTIFS_COLL].insert_one(notif)
        notif.pop("_id", None)
        return notif, True

    @staticmethod
    def _max_severity(a: Optional[str], b: Optional[str]) -> str:
        if not a:
            return b or Severity.Medium.value
        if not b:
            return a
        return a if SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0) else b

    @staticmethod
    def _next_repeat_at(rule: Dict[str, Any], now_iso: str) -> Optional[str]:
        hours = rule.get("repeat_interval_hours") or 0
        if not hours:
            return None
        return _iso(datetime.fromisoformat(now_iso) + timedelta(hours=hours))

    # -------------------------------------------------- deliveries
    async def _materialise_deliveries(self, rule: Dict[str, Any], notification: Dict[str, Any],
                                      event: Dict[str, Any]) -> int:
        channels: List[str] = rule.get("channels") or [Channel.InApp.value]
        strategy = rule.get("recipient_strategy") or RecipientStrategy.AllCompliance.value
        resolved = await self._resolve_recipients(strategy, event, channels)
        deliveries_created = 0
        rendered = render_template(rule.get("template_key") or "manual_notification",
                                   {**(event.get("payload") or {}),
                                    "entity_label": (event.get("payload") or {}).get("entity_label")
                                    or event["entity_id"]})
        now = _iso()
        for r in resolved:
            # EB-13 hardening · Dedup by stable recipient identity, NOT the
            # freshly generated recipient_id. Previously the dedup check
            # matched on a brand-new UUID and never hit, so every scan
            # re-created recipient + delivery rows and the collection grew
            # without bound - triggering timeouts on subsequent scans.
            identity: Dict[str, Any] = {
                "notification_id": notification["notification_id"],
                "channel": r["channel"],
            }
            for stable_key in ("user_id", "driver_id", "owner_id",
                                "email_address", "mobile_number"):
                if r.get(stable_key):
                    identity[stable_key] = r[stable_key]
                    break
            existing = await self.db[DELIVERIES_COLL].find_one(identity, {"_id": 0})
            if existing:
                continue
            rec_id = _uuid()
            rec_doc = {
                "notification_recipient_id": rec_id,
                "notification_id": notification["notification_id"],
                **{k: r.get(k) for k in ("recipient_type", "user_id", "driver_id", "owner_id",
                                          "email_address", "mobile_number", "display_name",
                                          "channel", "is_primary", "recipient_reason")},
                "created_at": now,
                "is_archived": False,
            }
            await self.db[RECIPIENTS_COLL].insert_one(rec_doc)
            provider = "in-app" if r["channel"] == Channel.InApp.value else "simulated"
            if r["channel"] == Channel.InApp.value:
                status_ = DeliveryStatus.Sent.value
                delivered_at = now
                subject = None
                body = rendered.get("message") or notification["message"]
            elif r["channel"] == Channel.Email.value:
                status_ = DeliveryStatus.Simulated.value
                delivered_at = now
                subject = rendered.get("email_subject") or notification["title"]
                body = rendered.get("email_body") or notification["message"]
            else:  # SMS
                status_ = DeliveryStatus.Simulated.value
                delivered_at = now
                subject = None
                body = rendered.get("sms_body") or notification["message"]
            delivery = {
                "notification_delivery_id": _uuid(),
                "notification_id": notification["notification_id"],
                "notification_recipient_id": rec_id,
                # EB-13 hardening · duplicate stable identity keys on the
                # delivery row itself so dedup lookups are index-friendly
                # and never depend on a recipient_id join.
                **{k: r.get(k) for k in ("user_id", "driver_id", "owner_id",
                                          "email_address", "mobile_number")},
                "channel": r["channel"],
                "provider": provider,
                "provider_message_id": None,
                "delivery_status": status_,
                "attempt_number": 1,
                "scheduled_at": now,
                "attempted_at": now,
                "delivered_at": delivered_at,
                "failed_at": None,
                "failure_code": None,
                "failure_reason": None,
                "next_retry_at": None,
                "rendered_subject": subject,
                "rendered_body": body,
                "created_at": now,
                "updated_at": now,
                "_source": event.get("_source") or "engine",
            }
            await self.db[DELIVERIES_COLL].insert_one(delivery)
            deliveries_created += 1
        return deliveries_created

    # -------------------------------------------------- scans
    async def compliance_scan(self, triggered_by: str = "system") -> Dict[str, Any]:
        return await self._run_job("compliance-scan", triggered_by, self._compliance_scan_impl)

    async def critical_scan(self, triggered_by: str = "system") -> Dict[str, Any]:
        return await self._run_job("critical-scan", triggered_by, self._critical_scan_impl)

    async def process_snoozes(self, triggered_by: str = "system") -> Dict[str, Any]:
        return await self._run_job("process-snoozes", triggered_by, self._process_snoozes_impl)

    async def process_escalations(self, triggered_by: str = "system") -> Dict[str, Any]:
        return await self._run_job("process-escalations", triggered_by,
                                   self._process_escalations_impl)

    async def retry_deliveries(self, triggered_by: str = "system") -> Dict[str, Any]:
        return await self._run_job("retry-deliveries", triggered_by,
                                   self._retry_deliveries_impl)

    async def reconcile(self, triggered_by: str = "system") -> Dict[str, Any]:
        return await self._run_job("reconcile", triggered_by, self._reconcile_impl)

    async def _run_job(self, job_type: str, triggered_by: str, impl) -> Dict[str, Any]:
        run = {
            "notification_job_run_id": _uuid(),
            "job_type": job_type,
            "started_at": _iso(),
            "completed_at": None,
            "status": JobStatus.Running.value,
            "records_scanned": 0,
            "events_created": 0,
            "notifications_created": 0,
            "notifications_updated": 0,
            "deliveries_created": 0,
            "failures": [],
            "correlation_id": _uuid(),
            "triggered_by": triggered_by,
            "created_at": _iso(),
        }
        await self.db[JOB_RUNS_COLL].insert_one(run)
        run.pop("_id", None)
        try:
            stats = await impl(run)
        except Exception as e:  # pragma: no cover - safety net
            logger.exception("Job %s failed", job_type)
            await self.db[JOB_RUNS_COLL].update_one(
                {"notification_job_run_id": run["notification_job_run_id"]},
                {"$set": {"status": JobStatus.Failed.value, "completed_at": _iso(),
                          "failures": [str(e)]}},
            )
            return {**run, "status": JobStatus.Failed.value, "failures": [str(e)]}
        status_ = JobStatus.CompletedWithWarnings.value if stats.get("failures") else \
            JobStatus.Completed.value
        await self.db[JOB_RUNS_COLL].update_one(
            {"notification_job_run_id": run["notification_job_run_id"]},
            {"$set": {"status": status_, "completed_at": _iso(), **stats}},
        )
        return {**run, "status": status_, **stats}

    async def _compliance_scan_impl(self, run: Dict[str, Any]) -> Dict[str, Any]:
        stats = {"records_scanned": 0, "events_created": 0, "notifications_created": 0,
                 "notifications_updated": 0, "deliveries_created": 0, "failures": []}
        drivers = {d["id"]: d for d in await self.db[DRIVERS_COLL].find({}, {"_id": 0}).to_list(5000)}
        vehicles = {v["id"]: v for v in await self.db[VEHICLES_COLL].find({}, {"_id": 0}).to_list(5000)}
        equipment = {e["id"]: e for e in await self.db[EQUIPMENT_COLL].find({}, {"_id": 0}).to_list(5000)}

        async def emit(evt_type, entity_type, entity_id, source_id, payload,
                       severity=None, source_status=None):
            r = await self.emit_event(evt_type, entity_type, entity_id, source_id, payload,
                                      severity=severity, source_status=source_status,
                                      correlation_id=run["correlation_id"], source="engine")
            stats["events_created"] += 1
            res = r.get("result") or {}
            stats["notifications_created"] += len(res.get("created") or [])
            stats["notifications_updated"] += len(res.get("updated") or [])
            stats["deliveries_created"] += res.get("deliveries_created") or 0

        # Licences (primary + active per driver)
        licences = await self.db[LICENCES_COLL].find(
            {"is_archived": {"$ne": True}, "is_primary": True}, {"_id": 0}
        ).to_list(10000)
        stats["records_scanned"] += len(licences)
        seen_driver_licence = set()
        for lic in licences:
            drv = drivers.get(lic.get("driver_id")) or {}
            label = drv.get("full_name") or drv.get("name") or lic.get("driver_id")
            seen_driver_licence.add(lic.get("driver_id"))
            status = _classify_expiry(lic.get("expiry_date"))
            payload = {"entity_label": label, "component": "Driver Licence",
                       "expiry_date": lic.get("expiry_date"), "driver_id": lic.get("driver_id")}
            if status == ComplianceStatus.DueSoon.value:
                d = _parse_date(lic.get("expiry_date"))
                if d:
                    payload["days_until"] = max(0, (d.date() - datetime.now(timezone.utc).date()).days)
                await emit(EventType.ComplianceDueSoon.value, EntityType.Driver.value,
                           lic.get("driver_id"), lic["id"], payload, source_status=status)
            elif status == ComplianceStatus.Expired.value:
                d = _parse_date(lic.get("expiry_date"))
                if d:
                    payload["days_expired"] = max(0, (datetime.now(timezone.utc).date() - d.date()).days)
                await emit(EventType.ComplianceExpired.value, EntityType.Driver.value,
                           lic.get("driver_id"), lic["id"], payload, source_status=status)

        # Missing licences
        for drv_id, drv in drivers.items():
            if drv.get("is_archived"):
                continue
            if drv_id not in seen_driver_licence:
                label = drv.get("full_name") or drv.get("name") or drv_id
                await emit(EventType.ComplianceMissing.value, EntityType.Driver.value,
                           drv_id, drv_id,
                           {"entity_label": label, "component": "Driver Licence",
                            "driver_id": drv_id},
                           source_status=ComplianceStatus.Missing.value)

        # Vehicle registrations (current)
        regs = await self.db[REGISTRATIONS_COLL].find(
            {"is_archived": {"$ne": True}, "is_current": True}, {"_id": 0}
        ).to_list(10000)
        stats["records_scanned"] += len(regs)
        seen_veh_reg = set()
        for r in regs:
            veh = vehicles.get(r.get("vehicle_id")) or {}
            label = veh.get("registration_number") or r.get("vehicle_id")
            seen_veh_reg.add(r.get("vehicle_id"))
            status = _classify_expiry(r.get("expiry_date"))
            payload = {"entity_label": label, "component": "Vehicle Registration",
                       "expiry_date": r.get("expiry_date")}
            if status == ComplianceStatus.DueSoon.value:
                d = _parse_date(r.get("expiry_date"))
                if d:
                    payload["days_until"] = max(0, (d.date() - datetime.now(timezone.utc).date()).days)
                await emit(EventType.ComplianceDueSoon.value, EntityType.Vehicle.value,
                           r.get("vehicle_id"), r["id"], payload, source_status=status)
            elif status == ComplianceStatus.Expired.value:
                d = _parse_date(r.get("expiry_date"))
                if d:
                    payload["days_expired"] = max(0, (datetime.now(timezone.utc).date() - d.date()).days)
                await emit(EventType.ComplianceExpired.value, EntityType.Vehicle.value,
                           r.get("vehicle_id"), r["id"], payload, source_status=status)

        # Insurance policies (current)
        pols = await self.db[INSURANCE_COLL].find(
            {"is_archived": {"$ne": True}, "is_current": True}, {"_id": 0}
        ).to_list(10000)
        stats["records_scanned"] += len(pols)
        seen_veh_ins = set()
        for p in pols:
            veh = vehicles.get(p.get("vehicle_id")) or {}
            label = veh.get("registration_number") or p.get("vehicle_id")
            seen_veh_ins.add(p.get("vehicle_id"))
            status = _classify_expiry(p.get("expiry_date"))
            payload = {"entity_label": label, "component": "Vehicle Insurance",
                       "expiry_date": p.get("expiry_date")}
            if status == ComplianceStatus.DueSoon.value:
                await emit(EventType.ComplianceDueSoon.value, EntityType.Vehicle.value,
                           p.get("vehicle_id"), p["id"], payload, source_status=status)
            elif status == ComplianceStatus.Expired.value:
                await emit(EventType.ComplianceExpired.value, EntityType.Vehicle.value,
                           p.get("vehicle_id"), p["id"], payload, source_status=status)

        # Missing insurance
        for veh_id, veh in vehicles.items():
            if veh.get("is_archived"):
                continue
            if veh_id not in seen_veh_ins:
                label = veh.get("registration_number") or veh_id
                await emit(EventType.ComplianceMissing.value, EntityType.Vehicle.value,
                           veh_id, veh_id,
                           {"entity_label": label, "component": "Vehicle Insurance"},
                           source_status=ComplianceStatus.Missing.value)

        return stats

    async def _critical_scan_impl(self, run: Dict[str, Any]) -> Dict[str, Any]:
        stats = {"records_scanned": 0, "events_created": 0, "notifications_created": 0,
                 "notifications_updated": 0, "deliveries_created": 0, "failures": []}
        vehicles = {v["id"]: v for v in await self.db[VEHICLES_COLL].find({}, {"_id": 0}).to_list(5000)}

        async def emit(evt_type, entity_type, entity_id, source_id, payload,
                       severity=None, source_status=None):
            r = await self.emit_event(evt_type, entity_type, entity_id, source_id, payload,
                                      severity=severity, source_status=source_status,
                                      correlation_id=run["correlation_id"], source="engine")
            stats["events_created"] += 1
            res = r.get("result") or {}
            stats["notifications_created"] += len(res.get("created") or [])
            stats["notifications_updated"] += len(res.get("updated") or [])
            stats["deliveries_created"] += res.get("deliveries_created") or 0

        # Critical defects
        crits = await self.db[DEFECTS_COLL].find(
            {"is_archived": {"$ne": True}, "severity": "Critical",
             "status": {"$nin": ["Rectified", "Closed"]}},
            {"_id": 0},
        ).to_list(5000)
        stats["records_scanned"] += len(crits)
        for d in crits:
            veh = vehicles.get(d.get("vehicle_id")) or {}
            payload = {"entity_label": veh.get("registration_number") or d.get("vehicle_id"),
                       "description": d.get("description") or d.get("defect_number") or "critical defect"}
            await emit(EventType.CriticalDefect.value, EntityType.Vehicle.value,
                       d.get("vehicle_id"), d["id"], payload,
                       source_status="Open")

        # High defects
        highs = await self.db[DEFECTS_COLL].find(
            {"is_archived": {"$ne": True}, "severity": "High",
             "status": {"$nin": ["Rectified", "Closed"]}},
            {"_id": 0},
        ).to_list(5000)
        stats["records_scanned"] += len(highs)
        for d in highs:
            veh = vehicles.get(d.get("vehicle_id")) or {}
            payload = {"entity_label": veh.get("registration_number") or d.get("vehicle_id"),
                       "description": d.get("description") or d.get("defect_number") or "high defect"}
            await emit(EventType.HighDefect.value, EntityType.Vehicle.value,
                       d.get("vehicle_id"), d["id"], payload,
                       source_status="Open")

        # Maintenance
        today_iso = datetime.now(timezone.utc).date().isoformat()
        maints = await self.db[MAINTENANCE_COLL].find(
            {"is_archived": {"$ne": True},
             "status": {"$nin": ["Completed", "Cancelled", "Archived"]}},
            {"_id": 0},
        ).to_list(5000)
        stats["records_scanned"] += len(maints)
        for m in maints:
            veh = vehicles.get(m.get("vehicle_id")) or {}
            due = m.get("due_date") or m.get("scheduled_date")
            dt = _parse_date(due)
            if not dt:
                continue
            days = (dt.date() - datetime.now(timezone.utc).date()).days
            payload = {"entity_label": veh.get("registration_number") or m.get("vehicle_id"),
                       "task_type": m.get("task_type") or "Maintenance", "due_date": due}
            if days < 0:
                payload["days_overdue"] = -days
                await emit(EventType.MaintenanceOverdue.value, EntityType.Vehicle.value,
                           m.get("vehicle_id"), m["id"], payload, source_status="Overdue")
            elif days <= 14:
                payload["days_until"] = days
                await emit(EventType.MaintenanceDueSoon.value, EntityType.Vehicle.value,
                           m.get("vehicle_id"), m["id"], payload, source_status="Due Soon")

        return stats

    async def _process_snoozes_impl(self, run: Dict[str, Any]) -> Dict[str, Any]:
        now = _iso()
        # Find snoozed notifications whose snooze has expired
        expired = await self.db[NOTIFS_COLL].find(
            {"status": NotificationStatus.Snoozed.value, "snoozed_until": {"$lte": now}},
            {"_id": 0},
        ).to_list(5000)
        for n in expired:
            await self.db[NOTIFS_COLL].update_one(
                {"notification_id": n["notification_id"]},
                {"$set": {"status": NotificationStatus.Active.value, "snoozed_until": None,
                          "updated_at": now}},
            )
            await self.db[SNOOZES_COLL].update_many(
                {"notification_id": n["notification_id"], "ended_at": None},
                {"$set": {"ended_at": now}},
            )
        return {"records_scanned": len(expired), "events_created": 0,
                "notifications_created": 0, "notifications_updated": len(expired),
                "deliveries_created": 0, "failures": []}

    async def _process_escalations_impl(self, run: Dict[str, Any]) -> Dict[str, Any]:
        now_dt = datetime.now(timezone.utc)
        stats = {"records_scanned": 0, "events_created": 0, "notifications_created": 0,
                 "notifications_updated": 0, "deliveries_created": 0, "failures": []}
        actives = await self.db[NOTIFS_COLL].find(
            {"status": {"$in": [NotificationStatus.Active.value, NotificationStatus.Escalated.value]},
             "is_archived": {"$ne": True}},
            {"_id": 0},
        ).to_list(5000)
        stats["records_scanned"] = len(actives)
        for n in actives:
            rule = await self.db[RULES_COLL].find_one({"notification_rule_id": n["notification_rule_id"]},
                                                       {"_id": 0})
            if not rule:
                continue
            policy = (rule.get("escalation_policy") or {}).get("levels") or []
            already = await self.db[ESCALATIONS_COLL].count_documents(
                {"notification_id": n["notification_id"]}
            )
            if already >= len(policy):
                continue
            level = policy[already]
            triggered_at = _parse_date(n["first_triggered_at"]) or now_dt
            if (now_dt - triggered_at).total_seconds() < (level.get("after_hours") or 0) * 3600:
                continue
            new_sev = level.get("to_severity") or n["severity"]
            await self.db[NOTIFS_COLL].update_one(
                {"notification_id": n["notification_id"]},
                {"$set": {"severity": new_sev, "status": NotificationStatus.Escalated.value,
                          "updated_at": _iso()}},
            )
            expand = level.get("expand_to")
            escalation = {
                "escalation_id": _uuid(),
                "notification_id": n["notification_id"],
                "escalation_level": f"Level {already + 1}",
                "triggered_at": _iso(),
                "trigger_reason": f"Auto-escalation after {level.get('after_hours')}h",
                "from_severity": n["severity"],
                "to_severity": new_sev,
                "added_recipient_strategy": expand,
                "created_deliveries": 0,
                "created_at": _iso(),
            }
            await self.db[ESCALATIONS_COLL].insert_one(escalation)
            stats["notifications_updated"] += 1
        return stats

    async def _retry_deliveries_impl(self, run: Dict[str, Any]) -> Dict[str, Any]:
        stats = {"records_scanned": 0, "events_created": 0, "notifications_created": 0,
                 "notifications_updated": 0, "deliveries_created": 0, "failures": []}
        now = _iso()
        pending = await self.db[DELIVERIES_COLL].find(
            {"delivery_status": DeliveryStatus.RetryScheduled.value,
             "next_retry_at": {"$lte": now}},
            {"_id": 0},
        ).to_list(5000)
        stats["records_scanned"] = len(pending)
        for d in pending:
            attempt = int(d.get("attempt_number") or 1) + 1
            if attempt > MAX_DELIVERY_ATTEMPTS:
                await self._dead_letter(d, "Max attempts exceeded")
                continue
            # Simulated: assume retry succeeds unless the delivery has a "force_fail" flag
            if d.get("_force_fail_next"):
                offset = DEFAULT_RETRY_SCHEDULE_MINUTES[min(attempt - 1, MAX_DELIVERY_ATTEMPTS - 1)]
                next_retry = _iso(datetime.now(timezone.utc) + timedelta(minutes=offset))
                await self.db[DELIVERIES_COLL].update_one(
                    {"notification_delivery_id": d["notification_delivery_id"]},
                    {"$set": {"attempt_number": attempt, "attempted_at": now,
                              "delivery_status": DeliveryStatus.RetryScheduled.value,
                              "next_retry_at": next_retry}},
                )
            else:
                await self.db[DELIVERIES_COLL].update_one(
                    {"notification_delivery_id": d["notification_delivery_id"]},
                    {"$set": {"attempt_number": attempt, "attempted_at": now,
                              "delivered_at": now,
                              "delivery_status": DeliveryStatus.Simulated.value
                              if d["channel"] != Channel.InApp.value
                              else DeliveryStatus.Sent.value,
                              "next_retry_at": None}},
                )
        return stats

    async def _dead_letter(self, delivery: Dict[str, Any], reason: str) -> None:
        now = _iso()
        await self.db[DELIVERIES_COLL].update_one(
            {"notification_delivery_id": delivery["notification_delivery_id"]},
            {"$set": {"delivery_status": DeliveryStatus.Failed.value, "failed_at": now,
                      "failure_reason": reason, "next_retry_at": None}},
        )
        await self.db[DEAD_LETTERS_COLL].insert_one({
            "dead_letter_id": _uuid(),
            "notification_delivery_id": delivery["notification_delivery_id"],
            "notification_id": delivery["notification_id"],
            "channel": delivery["channel"],
            "failure_reason": reason,
            "attempt_count": int(delivery.get("attempt_number") or 1),
            "last_attempt_at": now,
            "created_at": now,
            "resolved_at": None,
            "resolved_by": None,
            "resolution_note": None,
            "status": DeadLetterStatus.Open.value,
        })
        # If all deliveries for this notification failed, set the notification to Delivery Failed
        remaining = await self.db[DELIVERIES_COLL].count_documents(
            {"notification_id": delivery["notification_id"],
             "delivery_status": {"$in": [DeliveryStatus.Sent.value, DeliveryStatus.Simulated.value,
                                          DeliveryStatus.Delivered.value]}},
        )
        if remaining == 0:
            await self.db[NOTIFS_COLL].update_one(
                {"notification_id": delivery["notification_id"]},
                {"$set": {"status": NotificationStatus.DeliveryFailed.value, "updated_at": now}},
            )

    async def _reconcile_impl(self, run: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-resolve notifications whose source condition is no longer true."""
        stats = {"records_scanned": 0, "events_created": 0, "notifications_created": 0,
                 "notifications_updated": 0, "deliveries_created": 0, "failures": []}
        opens = await self.db[NOTIFS_COLL].find(
            {"status": {"$in": [NotificationStatus.Active.value,
                                 NotificationStatus.Acknowledged.value,
                                 NotificationStatus.Escalated.value,
                                 NotificationStatus.Snoozed.value]},
             "entity_type": {"$in": [EntityType.Driver.value, EntityType.Vehicle.value]}},
            {"_id": 0},
        ).to_list(5000)
        stats["records_scanned"] = len(opens)
        for n in opens:
            src = await self._lookup_source_record(n)
            if not src:
                continue
            evt_type = None
            evt = await self.db[EVENTS_COLL].find_one(
                {"notification_event_id": n["notification_event_id"]}, {"_id": 0}
            )
            if evt:
                evt_type = evt["event_type"]
            resolved = False
            if evt_type == EventType.ComplianceExpired.value:
                if _classify_expiry(src.get("expiry_date")) not in (
                    ComplianceStatus.Expired.value,
                ):
                    resolved = True
            elif evt_type == EventType.ComplianceDueSoon.value:
                if _classify_expiry(src.get("expiry_date")) == ComplianceStatus.Compliant.value:
                    resolved = True
            if resolved:
                await self._resolve(n["notification_id"], "system", "Reconciled: source resolved")
                stats["notifications_updated"] += 1
        return stats

    async def _lookup_source_record(self, notification: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Best-effort lookup by source_record_id across likely collections
        for coll in (LICENCES_COLL, REGISTRATIONS_COLL, INSURANCE_COLL, INSPECTIONS_COLL,
                      DEFECTS_COLL, MAINTENANCE_COLL, EQUIPMENT_COMPLIANCE_COLL):
            doc = await self.db[coll].find_one(
                {"id": notification.get("source_record_id")}, {"_id": 0}
            )
            if doc:
                return doc
        return None

    # -------------------------------------------------- state transitions
    async def acknowledge(self, notification_id: str, user: Dict[str, Any],
                          note: Optional[str] = None) -> Dict[str, Any]:
        n = await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                 {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        if n["status"] == NotificationStatus.Resolved.value:
            raise HTTPException(status_code=409, detail="Cannot acknowledge a resolved notification")
        # Duplicate ack for the same user is a no-op
        existing = await self.db[ACKS_COLL].find_one(
            {"notification_id": notification_id, "acknowledged_by": user.get("email")},
            {"_id": 0},
        )
        if existing:
            return n
        now = _iso()
        await self.db[ACKS_COLL].insert_one({
            "acknowledgement_id": _uuid(),
            "notification_id": notification_id,
            "acknowledged_by": user.get("email"),
            "acknowledged_at": now,
            "note": note,
            "created_at": now,
        })
        # Do not downgrade Escalated
        set_ = {"updated_at": now}
        if n["status"] not in (NotificationStatus.Escalated.value,
                                NotificationStatus.DeliveryFailed.value):
            set_["status"] = NotificationStatus.Acknowledged.value
        await self.db[NOTIFS_COLL].update_one({"notification_id": notification_id}, {"$set": set_})
        return await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                    {"_id": 0})

    async def snooze(self, notification_id: str, user: Dict[str, Any],
                     hours: int, reason: Optional[str] = None) -> Dict[str, Any]:
        n = await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                 {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        if n["status"] == NotificationStatus.Resolved.value:
            raise HTTPException(status_code=409, detail="Cannot snooze a resolved notification")
        max_hours = DEFAULT_SNOOZE_HOURS.get(n["severity"], 7 * 24)
        if hours <= 0:
            raise HTTPException(status_code=400, detail="Snooze hours must be positive")
        if hours > max_hours:
            raise HTTPException(status_code=400,
                                 detail=f"Max snooze for {n['severity']} is {max_hours}h")
        now = _iso()
        until = _iso(datetime.now(timezone.utc) + timedelta(hours=hours))
        await self.db[SNOOZES_COLL].insert_one({
            "snooze_id": _uuid(),
            "notification_id": notification_id,
            "snoozed_by": user.get("email"),
            "snoozed_at": now,
            "snooze_until": until,
            "reason": reason,
            "ended_at": None,
            "created_at": now,
        })
        await self.db[NOTIFS_COLL].update_one(
            {"notification_id": notification_id},
            {"$set": {"status": NotificationStatus.Snoozed.value, "snoozed_until": until,
                      "updated_at": now}},
        )
        return await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                    {"_id": 0})

    async def _resolve(self, notification_id: str, actor_email: str,
                       reason: Optional[str] = None) -> Dict[str, Any]:
        now = _iso()
        await self.db[NOTIFS_COLL].update_one(
            {"notification_id": notification_id},
            {"$set": {"status": NotificationStatus.Resolved.value, "resolved_at": now,
                      "resolved_by": actor_email, "resolution_reason": reason,
                      "updated_at": now}},
        )
        return await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                    {"_id": 0})

    async def resolve(self, notification_id: str, user: Dict[str, Any],
                      reason: Optional[str] = None) -> Dict[str, Any]:
        n = await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                 {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        return await self._resolve(notification_id, user.get("email"), reason)

    async def reopen(self, notification_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        n = await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                 {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        if n["status"] != NotificationStatus.Resolved.value:
            raise HTTPException(status_code=409, detail="Only resolved notifications may be reopened")
        now = _iso()
        await self.db[NOTIFS_COLL].update_one(
            {"notification_id": notification_id},
            {"$set": {"status": NotificationStatus.Active.value, "resolved_at": None,
                      "resolved_by": None, "resolution_reason": None, "updated_at": now,
                      "last_triggered_at": now}},
        )
        return await self.db[NOTIFS_COLL].find_one({"notification_id": notification_id},
                                                    {"_id": 0})


# =============================================================================
#  Indexes and seeding
# =============================================================================
async def ensure_indexes(db) -> None:
    for c in (RULES_COLL, EVENTS_COLL, NOTIFS_COLL, RECIPIENTS_COLL, DELIVERIES_COLL,
              ACKS_COLL, SNOOZES_COLL, ESCALATIONS_COLL, JOB_RUNS_COLL, DEAD_LETTERS_COLL,
              PREFS_COLL):
        # Best-effort index creation; ignore if not supported by DB backend
        try:
            await db[c].create_index("id")
        except Exception:
            pass
    await db[RULES_COLL].create_index("notification_rule_id", unique=True, sparse=True)
    await db[EVENTS_COLL].create_index("event_key", unique=True, sparse=True)
    await db[EVENTS_COLL].create_index("notification_event_id", unique=True, sparse=True)
    await db[NOTIFS_COLL].create_index("notification_id", unique=True, sparse=True)
    await db[NOTIFS_COLL].create_index("deduplication_key")
    await db[NOTIFS_COLL].create_index("status")
    await db[NOTIFS_COLL].create_index("entity_type")
    await db[DELIVERIES_COLL].create_index("notification_delivery_id", unique=True, sparse=True)
    await db[DELIVERIES_COLL].create_index("notification_id")
    await db[DELIVERIES_COLL].create_index("delivery_status")
    # EB-13 hardening · dedup lookup keys used by _materialise_deliveries.
    await db[DELIVERIES_COLL].create_index([("notification_id", 1), ("channel", 1), ("user_id", 1)])
    await db[DELIVERIES_COLL].create_index([("notification_id", 1), ("channel", 1), ("driver_id", 1)])
    await db[DELIVERIES_COLL].create_index([("notification_id", 1), ("channel", 1), ("owner_id", 1)])
    await db[DELIVERIES_COLL].create_index([("notification_id", 1), ("channel", 1), ("email_address", 1)])
    await db[DELIVERIES_COLL].create_index([("notification_id", 1), ("channel", 1), ("mobile_number", 1)])
    await db[RECIPIENTS_COLL].create_index("notification_recipient_id", unique=True, sparse=True)
    await db[RECIPIENTS_COLL].create_index("notification_id")
    await db[ACKS_COLL].create_index("acknowledgement_id", unique=True, sparse=True)
    await db[SNOOZES_COLL].create_index("snooze_id", unique=True, sparse=True)
    await db[ESCALATIONS_COLL].create_index("escalation_id", unique=True, sparse=True)
    await db[JOB_RUNS_COLL].create_index("notification_job_run_id", unique=True, sparse=True)
    await db[DEAD_LETTERS_COLL].create_index("dead_letter_id", unique=True, sparse=True)
    await db[PREFS_COLL].create_index("notification_preference_id", unique=True, sparse=True)
    await db[PREFS_COLL].create_index([("user_id", 1), ("event_type", 1)])


async def seed_rules(db) -> None:
    now = _iso()
    for spec in DEFAULT_RULES:
        existing = await db[RULES_COLL].find_one({"name": spec["name"]}, {"_id": 0})
        if existing:
            # Idempotent: keep existing rule id, refresh any newer defaults
            continue
        doc = {
            **spec,
            "notification_rule_id": _uuid(),
            "created_at": now,
            "updated_at": now,
            "created_by": "system-seed",
            "updated_by": "system-seed",
            "is_archived": False,
            "_source": SEED_TAG,
        }
        await db[RULES_COLL].insert_one(doc)


async def seed_examples(db) -> None:
    """Idempotent example notifications spanning every lifecycle state.

    All examples use `_source: "seed-eb07"` and are keyed on synthetic
    source_record_ids so real canonical scans never collide with them.
    """
    engine = NotificationsEngine(db)
    now = _iso()

    async def _emit(evt_type, entity_type, entity_id, source_record_id, payload, severity=None):
        # Use engine.emit_event so rules fire and deliveries materialise
        return await engine.emit_event(evt_type, entity_type, entity_id, source_record_id,
                                        payload, severity=severity, source="seed-eb07")

    admin = await db.users.find_one({"role": "Admin"}, {"_id": 0})
    admin_email = (admin or {}).get("email") or "system"

    # Always link the ImportJob seed to a real job if one exists — this is
    # dedup-safe via event_key and gives the /imports badge something to
    # render on every restart.
    try:
        existing_job = await db["import_jobs"].find_one({}, {"_id": 0, "id": 1})
        if existing_job and existing_job.get("id"):
            rid = existing_job["id"]
            await _emit(EventType.ImportValidationFailed.value, EntityType.ImportJob.value,
                        rid, rid,
                        {"job_ref": rid, "target_domain": "drivers", "error_rows": 3,
                         "created_by": admin_email})
    except Exception:
        pass

    # Skip the rest if any seed-eb07 example already exists — idempotent
    if await db[NOTIFS_COLL].count_documents({"_source": SEED_TAG, "entity_type": {"$ne": "ImportJob"}}) > 0:
        return

    await _emit(EventType.ComplianceDueSoon.value, EntityType.Driver.value,
                "seed-drv-01", "seed-lic-01",
                {"entity_label": "Seed Driver A", "component": "Driver Licence",
                 "expiry_date": "2027-01-31", "days_until": 15})

    await _emit(EventType.ComplianceExpired.value, EntityType.Vehicle.value,
                "seed-veh-01", "seed-reg-01",
                {"entity_label": "SEED-V01", "component": "Vehicle Registration",
                 "expiry_date": "2025-12-31", "days_expired": 30})

    await _emit(EventType.ComplianceMissing.value, EntityType.Vehicle.value,
                "seed-veh-02", "seed-veh-02",
                {"entity_label": "SEED-V02", "component": "Vehicle Insurance"})

    await _emit(EventType.CriticalDefect.value, EntityType.Vehicle.value,
                "seed-veh-03", "seed-def-01",
                {"entity_label": "SEED-V03", "description": "Brake fluid leak — CRITICAL"})

    await _emit(EventType.MaintenanceOverdue.value, EntityType.Vehicle.value,
                "seed-veh-04", "seed-mnt-01",
                {"entity_label": "SEED-V04", "task_type": "Scheduled Service",
                 "due_date": "2025-11-01", "days_overdue": 90})

    await _emit(EventType.DocumentUnderReview.value, EntityType.Document.value,
                "seed-doc-01", "seed-doc-01",
                {"entity_label": "SEED-V05", "document_title": "Insurance Cert 2027"})

    # (ImportJob validation-failed emission moved above — runs on every startup
    #  and safely dedups via event_key.)

    # Acknowledged example
    ack_res = await _emit(EventType.ComplianceDueSoon.value, EntityType.Driver.value,
                          "seed-drv-02", "seed-lic-02",
                          {"entity_label": "Seed Driver B", "component": "Driver Licence",
                           "expiry_date": "2027-02-28", "days_until": 20})
    ack_notif_ids = (ack_res.get("result") or {}).get("created") or []
    if ack_notif_ids:
        await engine.acknowledge(ack_notif_ids[0], admin or {"email": admin_email},
                                 note="Seed acknowledged example")

    # Snoozed example
    sn_res = await _emit(EventType.ComplianceDueSoon.value, EntityType.Driver.value,
                         "seed-drv-03", "seed-lic-03",
                         {"entity_label": "Seed Driver C", "component": "Driver Licence",
                          "expiry_date": "2027-03-31", "days_until": 25})
    sn_ids = (sn_res.get("result") or {}).get("created") or []
    if sn_ids:
        try:
            await engine.snooze(sn_ids[0], admin or {"email": admin_email}, hours=48,
                                reason="Seed snoozed example")
        except HTTPException:
            pass

    # Escalated example
    esc_res = await _emit(EventType.ComplianceExpired.value, EntityType.Vehicle.value,
                          "seed-veh-05", "seed-reg-02",
                          {"entity_label": "SEED-V05", "component": "Vehicle Registration",
                           "expiry_date": "2025-10-01", "days_expired": 90})
    esc_ids = (esc_res.get("result") or {}).get("created") or []
    for nid in esc_ids:
        # Backdate first_triggered_at so process_escalations picks it up
        await db[NOTIFS_COLL].update_one(
            {"notification_id": nid},
            {"$set": {"first_triggered_at": _iso(datetime.now(timezone.utc) - timedelta(days=10))}},
        )
    await engine.process_escalations("seed-eb07")

    # Failed simulated delivery example
    fd_res = await _emit(EventType.HighDefect.value, EntityType.Vehicle.value,
                         "seed-veh-06", "seed-def-02",
                         {"entity_label": "SEED-V06", "description": "Warning light — HIGH"})
    fd_ids = (fd_res.get("result") or {}).get("created") or []
    if fd_ids:
        # Find one of its deliveries and drive it to dead-letter
        d = await db[DELIVERIES_COLL].find_one({"notification_id": fd_ids[0]}, {"_id": 0})
        if d:
            await engine._dead_letter(d, "Seed simulated delivery failure")

    # Resolved example
    rv_res = await _emit(EventType.ComplianceDueSoon.value, EntityType.Driver.value,
                         "seed-drv-04", "seed-lic-04",
                         {"entity_label": "Seed Driver D", "component": "Driver Licence",
                          "expiry_date": "2027-04-30", "days_until": 50})
    rv_ids = (rv_res.get("result") or {}).get("created") or []
    if rv_ids:
        await engine.resolve(rv_ids[0], admin or {"email": admin_email},
                             reason="Seed resolved example")


# =============================================================================
#  Router
# =============================================================================
def _require_role(user: Dict[str, Any], allowed: Tuple[str, ...]) -> None:
    if user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=f"Requires one of {allowed}")


def build_notifications_router(db, get_current_user):
    router = APIRouter(prefix="/api")
    engine = NotificationsEngine(db)

    # ----------------- notifications
    @router.get("/notifications/overview")
    async def overview(current=Depends(get_current_user)):
        pipe_by_status = await db[NOTIFS_COLL].aggregate([
            {"$match": {"is_archived": {"$ne": True}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]).to_list(50)
        pipe_by_sev = await db[NOTIFS_COLL].aggregate([
            {"$match": {"is_archived": {"$ne": True},
                        "status": {"$nin": [NotificationStatus.Resolved.value,
                                             NotificationStatus.Archived.value]}}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ]).to_list(50)
        failures = await db[DELIVERIES_COLL].count_documents(
            {"delivery_status": DeliveryStatus.Failed.value}
        )
        dl_open = await db[DEAD_LETTERS_COLL].count_documents({"status": DeadLetterStatus.Open.value})
        return {
            "by_status": {r["_id"]: r["count"] for r in pipe_by_status},
            "by_severity": {r["_id"]: r["count"] for r in pipe_by_sev},
            "delivery_failures": failures,
            "dead_letters_open": dl_open,
        }

    @router.get("/notifications/counts")
    async def counts(current=Depends(get_current_user)):
        active = await db[NOTIFS_COLL].count_documents(
            {"is_archived": {"$ne": True},
             "status": {"$nin": [NotificationStatus.Resolved.value,
                                  NotificationStatus.Archived.value]}}
        )
        unread = await db[NOTIFS_COLL].count_documents(
            {"is_archived": {"$ne": True}, "is_read": False,
             "status": {"$nin": [NotificationStatus.Resolved.value,
                                  NotificationStatus.Archived.value]}}
        )
        critical = await db[NOTIFS_COLL].count_documents(
            {"is_archived": {"$ne": True}, "severity": Severity.Critical.value,
             "status": {"$nin": [NotificationStatus.Resolved.value,
                                  NotificationStatus.Archived.value]}}
        )
        high = await db[NOTIFS_COLL].count_documents(
            {"is_archived": {"$ne": True}, "severity": Severity.High.value,
             "status": {"$nin": [NotificationStatus.Resolved.value,
                                  NotificationStatus.Archived.value]}}
        )
        return {"active": active, "unread": unread, "critical": critical, "high": high}

    @router.get("/notifications/my-notifications")
    async def my_notifications(current=Depends(get_current_user)):
        # Notifications for which this user is a recipient
        recips = await db[RECIPIENTS_COLL].find(
            {"user_id": current["id"]}, {"_id": 0, "notification_id": 1}
        ).to_list(2000)
        nids = list({r["notification_id"] for r in recips})
        if not nids:
            return []
        return await db[NOTIFS_COLL].find(
            {"notification_id": {"$in": nids}, "is_archived": {"$ne": True}}, {"_id": 0}
        ).sort("last_triggered_at", -1).to_list(500)

    @router.get("/notifications")
    async def list_notifications(
        status: Optional[str] = None,
        severity: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        event_type: Optional[str] = None,
        unread_only: bool = False,
        include_archived: bool = False,
        current=Depends(get_current_user),
    ):
        q: Dict[str, Any] = {}
        if not include_archived:
            q["is_archived"] = {"$ne": True}
        if status:
            q["status"] = status
        if severity:
            q["severity"] = severity
        if entity_type:
            q["entity_type"] = entity_type
        if entity_id:
            q["entity_id"] = entity_id
        if unread_only:
            q["is_read"] = False
        if event_type:
            # event_type lives on the notification_events; join via notification_event_id
            evts = await db[EVENTS_COLL].find({"event_type": event_type},
                                               {"_id": 0, "notification_event_id": 1}).to_list(5000)
            q["notification_event_id"] = {"$in": [e["notification_event_id"] for e in evts]}
        return await db[NOTIFS_COLL].find(q, {"_id": 0}).sort("last_triggered_at", -1).to_list(500)

    @router.get("/notifications/{notification_id}")
    async def get_notification(notification_id: str, current=Depends(get_current_user)):
        n = await db[NOTIFS_COLL].find_one({"notification_id": notification_id}, {"_id": 0})
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        recips = await db[RECIPIENTS_COLL].find({"notification_id": notification_id},
                                                 {"_id": 0}).to_list(500)
        deliveries = await db[DELIVERIES_COLL].find({"notification_id": notification_id},
                                                     {"_id": 0}).to_list(500)
        acks = await db[ACKS_COLL].find({"notification_id": notification_id},
                                          {"_id": 0}).to_list(500)
        snoozes = await db[SNOOZES_COLL].find({"notification_id": notification_id},
                                                {"_id": 0}).to_list(500)
        escs = await db[ESCALATIONS_COLL].find({"notification_id": notification_id},
                                                 {"_id": 0}).to_list(500)
        return {**n, "recipients": recips, "deliveries": deliveries,
                "acknowledgements": acks, "snoozes": snoozes, "escalations": escs}

    @router.put("/notifications/{notification_id}/read")
    async def mark_read(notification_id: str, current=Depends(get_current_user)):
        # Any authenticated non-ReadOnly user may mark a notification read.
        if current.get("role") == "ReadOnly":
            raise HTTPException(status_code=403, detail="ReadOnly cannot mark notifications read")
        r = await db[NOTIFS_COLL].update_one(
            {"notification_id": notification_id},
            {"$set": {"is_read": True, "read_at": _iso(), "updated_at": _iso()}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"status": "read"}

    @router.post("/notifications/{notification_id}/acknowledge")
    async def ack_route(notification_id: str, payload: Optional[Dict[str, Any]] = None,
                        current=Depends(get_current_user)):
        if current.get("role") == "ReadOnly":
            raise HTTPException(status_code=403, detail="ReadOnly cannot acknowledge")
        return await engine.acknowledge(notification_id, current, (payload or {}).get("note"))

    @router.post("/notifications/{notification_id}/snooze")
    async def snooze_route(notification_id: str, payload: Dict[str, Any],
                           current=Depends(get_current_user)):
        if current.get("role") == "ReadOnly":
            raise HTTPException(status_code=403, detail="ReadOnly cannot snooze")
        try:
            hours = int(payload.get("hours") or 0)
        except Exception:
            raise HTTPException(status_code=400, detail="hours must be an integer")
        return await engine.snooze(notification_id, current, hours, payload.get("reason"))

    @router.post("/notifications/{notification_id}/resolve")
    async def resolve_route(notification_id: str, payload: Optional[Dict[str, Any]] = None,
                            current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        return await engine.resolve(notification_id, current, (payload or {}).get("reason"))

    @router.post("/notifications/{notification_id}/reopen")
    async def reopen_route(notification_id: str, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await engine.reopen(notification_id, current)

    @router.delete("/notifications/{notification_id}")
    async def archive_notification(notification_id: str, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        r = await db[NOTIFS_COLL].update_one(
            {"notification_id": notification_id},
            {"$set": {"is_archived": True, "status": NotificationStatus.Archived.value,
                      "updated_at": _iso()}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"status": "archived"}

    # ----------------- rules
    @router.get("/notification-rules")
    async def list_rules(include_archived: bool = False, current=Depends(get_current_user)):
        q: Dict[str, Any] = {}
        if not include_archived:
            q["is_archived"] = {"$ne": True}
        return await db[RULES_COLL].find(q, {"_id": 0}).sort("priority", 1).to_list(500)

    @router.post("/notification-rules")
    async def create_rule(payload: Dict[str, Any], current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        if payload.get("event_type") not in {e.value for e in EventType}:
            raise HTTPException(status_code=400, detail="Unknown event_type")
        now = _iso()
        doc = {
            **payload,
            "notification_rule_id": _uuid(),
            "is_active": bool(payload.get("is_active", True)),
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
            "created_by": current.get("email"),
            "updated_by": current.get("email"),
        }
        await db[RULES_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.get("/notification-rules/{notification_rule_id}")
    async def get_rule(notification_rule_id: str, current=Depends(get_current_user)):
        r = await db[RULES_COLL].find_one({"notification_rule_id": notification_rule_id},
                                           {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Rule not found")
        return r

    @router.put("/notification-rules/{notification_rule_id}")
    async def update_rule(notification_rule_id: str, payload: Dict[str, Any],
                          current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        update = {k: v for k, v in (payload or {}).items()
                  if k not in ("notification_rule_id", "_id", "created_at", "created_by")}
        update["updated_at"] = _iso()
        update["updated_by"] = current.get("email")
        r = await db[RULES_COLL].update_one({"notification_rule_id": notification_rule_id},
                                             {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        return await db[RULES_COLL].find_one({"notification_rule_id": notification_rule_id},
                                              {"_id": 0})

    @router.delete("/notification-rules/{notification_rule_id}")
    async def archive_rule(notification_rule_id: str, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        r = await db[RULES_COLL].update_one(
            {"notification_rule_id": notification_rule_id},
            {"$set": {"is_archived": True, "is_active": False, "updated_at": _iso(),
                      "updated_by": current.get("email")}},
        )
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        return {"status": "archived"}

    # ----------------- preferences
    @router.get("/notification-preferences/me")
    async def get_my_prefs(current=Depends(get_current_user)):
        return await db[PREFS_COLL].find({"user_id": current["id"]}, {"_id": 0}).to_list(200)

    @router.put("/notification-preferences/me")
    async def upsert_my_pref(payload: Dict[str, Any], current=Depends(get_current_user)):
        event_type = payload.get("event_type")
        channel = payload.get("channel")
        if event_type not in {e.value for e in EventType}:
            raise HTTPException(status_code=400, detail="Unknown event_type")
        if channel not in {c.value for c in Channel}:
            raise HTTPException(status_code=400, detail="Unknown channel")
        # Critical alerts cannot be fully disabled by ordinary users
        min_sev = payload.get("minimum_severity") or Severity.Information.value
        if current.get("role") not in ("Admin", "Manager") and \
                (payload.get("is_enabled") is False) and min_sev == Severity.Critical.value:
            raise HTTPException(status_code=400,
                                 detail="Critical alerts cannot be fully disabled")
        now = _iso()
        q = {"user_id": current["id"], "event_type": event_type, "channel": channel}
        existing = await db[PREFS_COLL].find_one(q, {"_id": 0})
        if existing:
            await db[PREFS_COLL].update_one(q, {"$set": {**payload, "updated_at": now}})
            return await db[PREFS_COLL].find_one(q, {"_id": 0})
        doc = {
            "notification_preference_id": _uuid(),
            "user_id": current["id"],
            "event_type": event_type,
            "channel": channel,
            "is_enabled": bool(payload.get("is_enabled", True)),
            "minimum_severity": min_sev,
            "digest_mode": payload.get("digest_mode") or DigestMode.Immediate.value,
            "quiet_hours_start": payload.get("quiet_hours_start"),
            "quiet_hours_end": payload.get("quiet_hours_end"),
            "timezone": payload.get("timezone"),
            "created_at": now,
            "updated_at": now,
        }
        await db[PREFS_COLL].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.get("/notification-preferences")
    async def list_prefs(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await db[PREFS_COLL].find({}, {"_id": 0}).to_list(2000)

    @router.put("/notification-preferences/{notification_preference_id}")
    async def update_pref(notification_preference_id: str, payload: Dict[str, Any],
                           current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        update = {**payload, "updated_at": _iso()}
        r = await db[PREFS_COLL].update_one({"notification_preference_id": notification_preference_id},
                                             {"$set": update})
        if r.matched_count == 0:
            raise HTTPException(status_code=404, detail="Preference not found")
        return await db[PREFS_COLL].find_one({"notification_preference_id": notification_preference_id},
                                              {"_id": 0})

    # ----------------- jobs
    @router.post("/notification-jobs/compliance-scan")
    async def route_compliance_scan(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        return await engine.compliance_scan(triggered_by=current.get("email") or "system")

    @router.post("/notification-jobs/critical-scan")
    async def route_critical_scan(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        return await engine.critical_scan(triggered_by=current.get("email") or "system")

    @router.post("/notification-jobs/process-snoozes")
    async def route_process_snoozes(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await engine.process_snoozes(triggered_by=current.get("email") or "system")

    @router.post("/notification-jobs/process-escalations")
    async def route_process_escalations(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await engine.process_escalations(triggered_by=current.get("email") or "system")

    @router.post("/notification-jobs/retry-deliveries")
    async def route_retry(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await engine.retry_deliveries(triggered_by=current.get("email") or "system")

    @router.post("/notification-jobs/reconcile")
    async def route_reconcile(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await engine.reconcile(triggered_by=current.get("email") or "system")

    @router.get("/notification-jobs")
    async def list_jobs(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        return await db[JOB_RUNS_COLL].find({}, {"_id": 0}).sort("started_at", -1).to_list(200)

    @router.get("/notification-jobs/{notification_job_run_id}")
    async def get_job(notification_job_run_id: str, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        r = await db[JOB_RUNS_COLL].find_one({"notification_job_run_id": notification_job_run_id},
                                              {"_id": 0})
        if not r:
            raise HTTPException(status_code=404, detail="Job run not found")
        return r

    # ----------------- outbox
    @router.get("/notification-outbox")
    async def outbox(status: Optional[str] = None, channel: Optional[str] = None,
                     current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        q: Dict[str, Any] = {}
        if status:
            q["delivery_status"] = status
        if channel:
            q["channel"] = channel
        return await db[DELIVERIES_COLL].find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

    @router.get("/notification-outbox/{notification_delivery_id}")
    async def outbox_detail(notification_delivery_id: str, current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager", "Compliance"))
        d = await db[DELIVERIES_COLL].find_one({"notification_delivery_id": notification_delivery_id},
                                                {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Delivery not found")
        return d

    @router.post("/notification-outbox/{notification_delivery_id}/simulate-failure")
    async def simulate_failure(notification_delivery_id: str, payload: Optional[Dict[str, Any]] = None,
                                current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        d = await db[DELIVERIES_COLL].find_one({"notification_delivery_id": notification_delivery_id},
                                                 {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Delivery not found")
        attempt = int(d.get("attempt_number") or 1)
        reason = ((payload or {}).get("reason")) or "Simulated failure"
        if attempt >= MAX_DELIVERY_ATTEMPTS:
            await engine._dead_letter(d, reason)
            return await db[DELIVERIES_COLL].find_one(
                {"notification_delivery_id": notification_delivery_id}, {"_id": 0}
            )
        offset = DEFAULT_RETRY_SCHEDULE_MINUTES[min(attempt, MAX_DELIVERY_ATTEMPTS - 1)]
        next_retry = _iso(datetime.now(timezone.utc) + timedelta(minutes=offset))
        await db[DELIVERIES_COLL].update_one(
            {"notification_delivery_id": notification_delivery_id},
            {"$set": {"delivery_status": DeliveryStatus.RetryScheduled.value,
                      "failure_reason": reason, "failed_at": _iso(),
                      "next_retry_at": next_retry, "updated_at": _iso()}},
        )
        return await db[DELIVERIES_COLL].find_one(
            {"notification_delivery_id": notification_delivery_id}, {"_id": 0}
        )

    @router.post("/notification-outbox/{notification_delivery_id}/simulate-success")
    async def simulate_success(notification_delivery_id: str,
                                current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        d = await db[DELIVERIES_COLL].find_one({"notification_delivery_id": notification_delivery_id},
                                                 {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Delivery not found")
        now = _iso()
        target = DeliveryStatus.Simulated.value if d["channel"] != Channel.InApp.value \
            else DeliveryStatus.Sent.value
        await db[DELIVERIES_COLL].update_one(
            {"notification_delivery_id": notification_delivery_id},
            {"$set": {"delivery_status": target, "delivered_at": now,
                      "failure_reason": None, "failed_at": None, "next_retry_at": None,
                      "updated_at": now}},
        )
        return await db[DELIVERIES_COLL].find_one(
            {"notification_delivery_id": notification_delivery_id}, {"_id": 0}
        )

    return router


# =============================================================================
#  Event-driven hooks (called from other modules)
# =============================================================================
async def emit_document_status_event(db, document: Dict[str, Any]) -> None:
    """Called after a document status changes to Under Review or Rejected."""
    engine = NotificationsEngine(db)
    if document.get("status") == "Under Review":
        await engine.emit_event(
            EventType.DocumentUnderReview.value, EntityType.Document.value,
            document["id"], document["id"],
            {"entity_label": document.get("title") or document["id"],
             "document_title": document.get("title") or document["id"]},
            source="doc-event",
        )
    elif document.get("status") == "Rejected":
        await engine.emit_event(
            EventType.DocumentRejected.value, EntityType.Document.value,
            document["id"], document["id"],
            {"entity_label": document.get("title") or document["id"],
             "document_title": document.get("title") or document["id"]},
            source="doc-event",
        )


async def emit_import_job_event(db, job: Dict[str, Any]) -> None:
    """Called after an import job status changes."""
    status = job.get("status")
    map_ = {
        "Validation Failed": EventType.ImportValidationFailed.value,
        "Ready to Commit": EventType.ImportReadyToCommit.value,
        "Committed": None,  # success — no notification
        "Partially Committed": EventType.ImportPartiallyCommitted.value,
        "Commit Failed": EventType.ImportCommitFailed.value,
        "Rolled Back": None,
    }
    evt = map_.get(status)
    if not evt:
        return
    engine = NotificationsEngine(db)
    await engine.emit_event(
        evt, EntityType.ImportJob.value, job["id"], job["id"],
        {"job_ref": job.get("id"), "target_domain": job.get("target_domain"),
         "error_rows": job.get("error_rows"), "valid_rows": job.get("valid_rows"),
         "created_by": job.get("created_by")},
        source="import-event",
    )
