// EB-07b — shared frontend helpers for the notification experience.

export const SEVERITY_STYLES = {
  Critical: "bg-red-100 text-red-800 border-red-300",
  High: "bg-orange-100 text-orange-800 border-orange-300",
  Medium: "bg-amber-100 text-amber-800 border-amber-300",
  Low: "bg-slate-100 text-slate-700 border-slate-300",
  Information: "bg-blue-50 text-blue-700 border-blue-200",
};

export const SEVERITY_DOT = {
  Critical: "bg-red-500",
  High: "bg-orange-500",
  Medium: "bg-amber-500",
  Low: "bg-slate-400",
  Information: "bg-blue-400",
};

export const SEVERITY_ORDER = {
  Information: 10,
  Low: 20,
  Medium: 30,
  High: 40,
  Critical: 50,
};

export const STATUS_STYLES = {
  New: "bg-slate-100 text-slate-700 border-slate-300",
  Active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Acknowledged: "bg-blue-50 text-blue-700 border-blue-200",
  Snoozed: "bg-slate-100 text-slate-500 border-slate-200",
  Escalated: "bg-red-50 text-red-700 border-red-200",
  Resolved: "bg-slate-100 text-slate-500 border-slate-200",
  "Delivery Failed": "bg-red-50 text-red-700 border-red-200",
  Archived: "bg-slate-100 text-slate-400 border-slate-200",
};

export const EVENT_TYPES = [
  "Compliance Due Soon",
  "Compliance Expired",
  "Compliance Missing",
  "Compliance Under Review",
  "Critical Vehicle Defect",
  "High Vehicle Defect",
  "Maintenance Due Soon",
  "Maintenance Overdue",
  "Driver Activation Incomplete",
  "Driver Activation Override Expiring",
  "Document Under Review",
  "Document Rejected",
  "Import Validation Failed",
  "Import Ready to Commit",
  "Import Partially Committed",
  "Import Commit Failed",
  "Import Rollback Failed",
  "Manual Notification",
  "Other",
];

export const ENTITY_TYPES = [
  "Driver", "Owner", "Vehicle", "Equipment", "DriverLicence",
  "VehicleRegistration", "VehicleInsurancePolicy", "VehicleInspection",
  "VehicleDefect", "VehicleMaintenanceTask", "EquipmentCompliance",
  "Document", "ImportJob", "DriverActivation", "General",
];

export const CHANNELS = ["In App", "Email", "SMS"];
export const SEVERITIES = ["Information", "Low", "Medium", "High", "Critical"];
export const STATUSES = ["New", "Active", "Acknowledged", "Snoozed", "Escalated", "Resolved", "Delivery Failed", "Archived"];
export const DIGEST_MODES = ["Immediate", "Hourly Digest", "Daily Digest", "Weekly Digest", "None"];
export const RECIPIENT_STRATEGIES = [
  "Assigned Compliance Team", "All Compliance users", "All Managers",
  "All Administrators", "Assigned Allocator", "Driver", "Owner",
  "Driver and Owner", "Driver, Owner and Compliance", "Record Creator",
  "Custom Recipients", "No External Recipient",
];

// Max snooze hours per severity — mirrors backend engine ceiling
export const MAX_SNOOZE_HOURS = {
  Information: 30 * 24,
  Low: 30 * 24,
  Medium: 14 * 24,
  High: 7 * 24,
  Critical: 24,
};

export const SNOOZE_PRESETS = [
  { label: "1 hour", hours: 1 },
  { label: "4 hours", hours: 4 },
  { label: "24 hours", hours: 24 },
  { label: "3 days", hours: 72 },
  { label: "7 days", hours: 168 },
];

// Map a notification entity_type → source-record deep-link URL.
// Notifications carry entity_id and source_record_id from the canonical
// modules — the mapping below relies on those references only.
export function sourceLink(notification) {
  if (!notification) return null;
  const { entity_type, entity_id, source_record_id } = notification;
  const src = source_record_id;
  switch (entity_type) {
    case "Driver":
      return `/drivers/${entity_id}`;
    case "DriverLicence":
      return `/compliance/records/driver-licences?record=${src}`;
    case "Vehicle":
      return `/registers/vehicles?record=${entity_id}`;
    case "VehicleRegistration":
      return `/compliance/records/vehicle-registrations?record=${src}`;
    case "VehicleInsurancePolicy":
      return `/compliance/records/vehicle-insurance?record=${src}`;
    case "VehicleInspection":
      return `/compliance/records/vehicle-inspections?record=${src}`;
    case "VehicleDefect":
      return `/compliance/records/vehicle-defects?record=${src}`;
    case "VehicleMaintenanceTask":
      return `/compliance/records/vehicle-maintenance-tasks?record=${src}`;
    case "EquipmentCompliance":
      return `/compliance/records/equipment-compliance?record=${src}`;
    case "Document":
      return `/documents?doc=${src}`;
    case "ImportJob":
      return `/imports/${src || entity_id}`;
    case "Equipment":
      return `/registers/equipment?record=${entity_id}`;
    case "Owner":
      return `/registers/owners?record=${entity_id}`;
    default:
      return null;
  }
}

export function humanTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString("en-AU", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("en-AU", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
    timeZone: "Australia/Melbourne",
  });
}

export function highestSeverity(list) {
  let best = null;
  for (const n of list || []) {
    if (!best || (SEVERITY_ORDER[n.severity] || 0) > (SEVERITY_ORDER[best] || 0)) {
      best = n.severity;
    }
  }
  return best;
}
