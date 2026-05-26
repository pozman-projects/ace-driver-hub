// Module configuration shared across landing hub + module pages.
// Each entry: route slug, label, icon name (Phosphor), short description,
// list of fields (used by the generic ModulePage for table + create dialog).

export const MODULES = [
  {
    slug: "drivers",
    title: "Driver Hub",
    icon: "Users",
    description: "Driver profiles, contacts, status and master records.",
    fields: [
      { key: "name", label: "Full Name", required: true },
      { key: "phone", label: "Phone" },
      { key: "email", label: "Email" },
      { key: "licence_number", label: "Licence Number" },
      { key: "base", label: "Base Depot" },
      { key: "status", label: "Status", placeholder: "Active / On Leave / Inactive" },
    ],
    columns: ["name", "phone", "email", "licence_number", "base", "status"],
  },
  {
    slug: "licences",
    title: "Driver Licences",
    icon: "IdentificationCard",
    description: "Licence expiry tracking, alerts and uploaded licence documents.",
    fields: [
      { key: "driver_name", label: "Driver Name", required: true },
      { key: "licence_number", label: "Licence Number", required: true },
      { key: "licence_class", label: "Class", placeholder: "HR / HC / MC" },
      { key: "issue_date", label: "Issue Date", type: "date" },
      { key: "expiry_date", label: "Expiry Date", type: "date" },
      { key: "status", label: "Status", placeholder: "Valid / Expiring Soon / Expired" },
    ],
    columns: ["driver_name", "licence_number", "licence_class", "issue_date", "expiry_date", "status"],
  },
  {
    slug: "truck-rego",
    title: "Driver Truck Rego",
    icon: "Truck",
    description: "Truck registration tracking and due dates.",
    fields: [
      { key: "rego_number", label: "Rego Number", required: true },
      { key: "driver_name", label: "Assigned Driver" },
      { key: "make", label: "Make" },
      { key: "model", label: "Model" },
      { key: "year", label: "Year" },
      { key: "expiry_date", label: "Rego Expiry", type: "date" },
    ],
    columns: ["rego_number", "driver_name", "make", "model", "year", "expiry_date"],
  },
  {
    slug: "insurance",
    title: "Driver Insurance",
    icon: "ShieldCheck",
    description: "Insurance tracking, expiry dates and compliance alerts.",
    fields: [
      { key: "policy_number", label: "Policy Number", required: true },
      { key: "driver_name", label: "Driver Name" },
      { key: "provider", label: "Provider" },
      { key: "type", label: "Cover Type" },
      { key: "expiry_date", label: "Expiry Date", type: "date" },
      { key: "premium", label: "Premium" },
    ],
    columns: ["policy_number", "driver_name", "provider", "type", "expiry_date", "premium"],
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
      { key: "assigned_to", label: "Assigned To" },
      { key: "condition", label: "Condition" },
      { key: "location", label: "Location" },
    ],
    columns: ["equipment_id", "name", "type", "assigned_to", "condition", "location"],
  },
  {
    slug: "maintenance",
    title: "ACE Maintenance",
    icon: "Toolbox",
    description: "Maintenance records, inspections, defects and service history.",
    fields: [
      { key: "vehicle_rego", label: "Vehicle Rego", required: true },
      { key: "service_type", label: "Service Type" },
      { key: "service_date", label: "Service Date", type: "date" },
      { key: "next_service", label: "Next Service", type: "date" },
      { key: "mechanic", label: "Mechanic / Workshop" },
      { key: "notes", label: "Notes" },
    ],
    columns: ["vehicle_rego", "service_type", "service_date", "next_service", "mechanic", "notes"],
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
      { key: "driver_assigned", label: "Driver Assigned" },
      { key: "last_inspection", label: "Last Inspection", type: "date" },
      { key: "status", label: "Compliance Status" },
    ],
    columns: ["tray_id", "rego", "capacity", "driver_assigned", "last_inspection", "status"],
  },
  {
    slug: "onboarding",
    title: "Driver Start Profile",
    icon: "UserPlus",
    description: "New driver onboarding workflow and setup process.",
    fields: [
      { key: "full_name", label: "Driver Full Name", required: true },
      { key: "start_date", label: "Start Date", type: "date" },
      { key: "stage", label: "Onboarding Stage" },
      { key: "contact", label: "Contact" },
      { key: "documents_status", label: "Documents Status" },
    ],
    columns: ["full_name", "start_date", "stage", "contact", "documents_status"],
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
