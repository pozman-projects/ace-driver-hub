// Module configuration shared across landing hub + module pages.
// `driver_select` is a special field type rendered as a searchable driver dropdown.
// The virtual column "driver" is resolved at render-time using the canonical driver
// record looked up via driver_id (with text-field fallback for legacy data).

export const MODULES = [
  {
    slug: "drivers",
    title: "Driver Hub",
    icon: "Users",
    description: "Driver profiles, contacts, status and master records.",
    fields: [
      { key: "name", label: "Full Name", required: true },
      { key: "driver_number", label: "Driver Number" },
      { key: "company", label: "Company" },
      { key: "phone", label: "Phone" },
      { key: "email", label: "Email" },
      { key: "licence_number", label: "Licence Number" },
      { key: "base", label: "Base Depot" },
      { key: "status", label: "Status", placeholder: "Active / On Leave / Inactive" },
    ],
    columns: ["name", "driver_number", "company", "phone", "base", "status"],
    rowLinkTo: (row) => `/drivers/${row.id}`,
  },
  {
    slug: "licences",
    title: "Driver Licences",
    icon: "IdentificationCard",
    description: "Licence expiry tracking, alerts and uploaded licence documents.",
    fields: [
      { key: "driver_id", label: "Driver", type: "driver_select", required: true },
      { key: "licence_number", label: "Licence Number", required: true },
      { key: "licence_class", label: "Class", placeholder: "HR / HC / MC" },
      { key: "issue_date", label: "Issue Date", type: "date" },
      { key: "expiry_date", label: "Expiry Date", type: "date" },
      { key: "status", label: "Status", placeholder: "Valid / Expiring Soon / Expired" },
    ],
    columns: ["driver", "licence_number", "licence_class", "issue_date", "expiry_date", "status"],
    fallbackNameField: "driver_name",
  },
  {
    slug: "truck-rego",
    title: "Driver Truck Rego",
    icon: "Truck",
    description: "Truck registration tracking and due dates.",
    fields: [
      { key: "rego_number", label: "Rego Number", required: true },
      { key: "driver_id", label: "Assigned Driver", type: "driver_select" },
      { key: "make", label: "Make" },
      { key: "model", label: "Model" },
      { key: "year", label: "Year" },
      { key: "expiry_date", label: "Rego Expiry", type: "date" },
    ],
    columns: ["rego_number", "driver", "make", "model", "year", "expiry_date"],
    fallbackNameField: "driver_name",
  },
  {
    slug: "insurance",
    title: "Driver Insurance",
    icon: "ShieldCheck",
    description: "Insurance tracking, expiry dates and compliance alerts.",
    fields: [
      { key: "policy_number", label: "Policy Number", required: true },
      { key: "driver_id", label: "Driver", type: "driver_select", required: true },
      { key: "provider", label: "Provider" },
      { key: "type", label: "Cover Type" },
      { key: "expiry_date", label: "Expiry Date", type: "date" },
      { key: "premium", label: "Premium" },
    ],
    columns: ["policy_number", "driver", "provider", "type", "expiry_date", "premium"],
    fallbackNameField: "driver_name",
  },
  {
    slug: "equipment",
    title: "ACE Equipment",
    icon: "Wrench",
    description: "Equipment assigned to drivers and vehicles.",
    fields: [
      { key: "equipment_id", label: "Equipment ID", required: true },
      { key: "name", label: "Item Name" },
      { key: "type", label: "Type" },
      { key: "driver_id", label: "Assigned Driver", type: "driver_select" },
      { key: "condition", label: "Condition" },
      { key: "location", label: "Location" },
    ],
    columns: ["equipment_id", "name", "type", "driver", "condition", "location"],
    fallbackNameField: "assigned_to",
  },
  {
    slug: "maintenance",
    title: "ACE Maintenance",
    icon: "Toolbox",
    description: "Maintenance records, inspections, defects and service history.",
    fields: [
      { key: "vehicle_rego", label: "Vehicle Rego", required: true },
      { key: "driver_id", label: "Driver", type: "driver_select" },
      { key: "service_type", label: "Service Type" },
      { key: "service_date", label: "Service Date", type: "date" },
      { key: "next_service", label: "Next Service", type: "date" },
      { key: "mechanic", label: "Mechanic / Workshop" },
      { key: "notes", label: "Notes" },
    ],
    columns: ["vehicle_rego", "driver", "service_type", "service_date", "next_service", "mechanic"],
    fallbackNameField: null,
  },
  {
    slug: "tilt-trays",
    title: "ACE Tilt Trays",
    icon: "Trailer",
    description: "Tilt tray register and tray-specific compliance tracking.",
    fields: [
      { key: "tray_id", label: "Tray ID", required: true },
      { key: "rego", label: "Rego" },
      { key: "capacity", label: "Capacity" },
      { key: "driver_id", label: "Driver Assigned", type: "driver_select" },
      { key: "last_inspection", label: "Last Inspection", type: "date" },
      { key: "status", label: "Compliance Status" },
    ],
    columns: ["tray_id", "rego", "capacity", "driver", "last_inspection", "status"],
    fallbackNameField: "driver_assigned",
  },
  {
    slug: "onboarding",
    title: "Driver Start Profile",
    icon: "UserPlus",
    description: "New driver onboarding workflow and setup process.",
    fields: [
      { key: "full_name", label: "Driver Full Name", required: true },
      { key: "driver_id", label: "Link to Existing Driver", type: "driver_select" },
      { key: "start_date", label: "Start Date", type: "date" },
      { key: "stage", label: "Onboarding Stage" },
      { key: "contact", label: "Contact" },
      { key: "documents_status", label: "Documents Status" },
    ],
    columns: ["full_name", "driver", "start_date", "stage", "contact", "documents_status"],
    fallbackNameField: "full_name",
  },
];

export function findModule(slug) {
  return MODULES.find((m) => m.slug === slug);
}

export function humanLabel(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Resolve the canonical driver name for a row in a relationship module.
 *  - Prefer drivers[row.driver_id].name
 *  - Fall back to row[module.fallbackNameField] for legacy/unlinked records.
 */
export function resolveDriverName(row, mod, driversById) {
  const id = row?.driver_id;
  if (id && driversById && driversById[id]) {
    return driversById[id].name;
  }
  if (mod?.fallbackNameField) {
    return row?.[mod.fallbackNameField] || "";
  }
  return "";
}

export function hasDriverRelationship(mod) {
  return mod?.fields?.some((f) => f.type === "driver_select");
}
