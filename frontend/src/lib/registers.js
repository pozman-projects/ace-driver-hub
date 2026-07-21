// EB-02 Foundation Registers config — used by RegisterPage.jsx
// Every register has: slug, title, description, icon, api base, status field,
// controlled status options, columns (for the list table), and fields
// (for the create/edit dialog).

export const REGISTERS = {
  drivers: {
    slug: "drivers",
    title: "Drivers",
    description: "Canonical driver identity register — one source of truth per person.",
    icon: "IdentificationBadge",
    api: "/drivers",
    idField: "id",
    primaryField: "full_name",
    statusField: "driver_status",
    statusOptions: ["Active", "On Leave", "Training", "Probation", "Inactive", "Archived"],
    searchFields: [
      "full_name",
      "driver_code",
      "dispatch_number",
      "email",
      "mobile_number",
      "company_ref",
      "business_name",
      "abn",
    ],
    columns: [
      { key: "full_name", label: "Full Name", weight: "primary" },
      { key: "driver_code", label: "Driver Code" },
      { key: "dispatch_number", label: "Dispatch" },
      { key: "mobile_number", label: "Mobile" },
      { key: "email", label: "Email" },
      { key: "company_ref", label: "Company" },
      { key: "driver_status", label: "Status", type: "status" },
    ],
    fields: [
      { key: "full_name", label: "Full Name", required: true },
      { key: "driver_code", label: "Driver Code" },
      { key: "dispatch_number", label: "Dispatch Number", placeholder: "0 and 13 reserved" },
      {
        key: "driver_status",
        label: "Status",
        type: "select",
        options: ["Active", "On Leave", "Training", "Probation", "Inactive", "Archived"],
      },
      { key: "mobile_number", label: "Mobile" },
      { key: "email", label: "Email", type: "email" },
      { key: "residential_address", label: "Residential Address" },
      { key: "emergency_contact_name", label: "Emergency Contact Name" },
      { key: "emergency_contact_phone", label: "Emergency Contact Phone" },
      { key: "start_date", label: "Start Date", type: "date" },
      { key: "company_ref", label: "Company" },
      { key: "business_name", label: "Business Name" },
      { key: "abn", label: "ABN" },
      { key: "payroll_number", label: "Payroll Number" },
      { key: "payment_percentage", label: "Payment %", type: "number", placeholder: "0 – 100" },
    ],
  },

  owners: {
    slug: "owners",
    title: "Owners",
    description: "Master register for individuals, businesses and trusts that own fleet assets.",
    icon: "Buildings",
    api: "/owners",
    idField: "id",
    primaryField: "name",
    statusField: "owner_status",
    statusOptions: ["Active", "Inactive", "Archived"],
    searchFields: ["name", "abn", "primary_contact_name", "email", "mobile_number", "company_ref"],
    columns: [
      { key: "name", label: "Name", weight: "primary" },
      { key: "owner_type", label: "Type" },
      { key: "abn", label: "ABN" },
      { key: "primary_contact_name", label: "Contact" },
      { key: "mobile_number", label: "Mobile" },
      { key: "owner_status", label: "Status", type: "status" },
    ],
    fields: [
      { key: "name", label: "Name / Business Name", required: true },
      {
        key: "owner_type",
        label: "Owner Type",
        type: "select",
        options: ["Individual", "Business", "Trust", "Other"],
      },
      { key: "abn", label: "ABN" },
      { key: "primary_contact_name", label: "Primary Contact" },
      { key: "mobile_number", label: "Mobile" },
      { key: "email", label: "Email", type: "email" },
      { key: "business_address", label: "Business Address" },
      {
        key: "owner_status",
        label: "Status",
        type: "select",
        options: ["Active", "Inactive", "Archived"],
      },
      { key: "company_ref", label: "Company" },
    ],
  },

  vehicles: {
    slug: "vehicles",
    title: "Vehicles",
    description: "Canonical vehicle register — rego, VIN, make/model, ownership.",
    icon: "Truck",
    api: "/vehicles",
    idField: "id",
    primaryField: "registration_number",
    statusField: "vehicle_status",
    statusOptions: ["Active", "Inactive", "Maintenance", "Archived"],
    searchFields: ["registration_number", "vin", "make", "model", "year", "vehicle_type", "carrier_configuration"],
    columns: [
      { key: "registration_number", label: "Rego", weight: "primary" },
      { key: "vin", label: "VIN" },
      { key: "make", label: "Make" },
      { key: "model", label: "Model" },
      { key: "year", label: "Year" },
      { key: "vehicle_type", label: "Type" },
      { key: "owner_id", label: "Owner", type: "owner_lookup" },
      { key: "vehicle_status", label: "Status", type: "status" },
    ],
    fields: [
      { key: "registration_number", label: "Registration Number", required: true },
      { key: "vin", label: "VIN" },
      { key: "make", label: "Make" },
      { key: "model", label: "Model" },
      { key: "year", label: "Year" },
      { key: "vehicle_type", label: "Vehicle Type", placeholder: "Prime Mover / Rigid / …" },
      { key: "carrier_configuration", label: "Carrier Configuration", placeholder: "Semi / B-Double / …" },
      {
        key: "ownership_model",
        label: "Ownership Model",
        type: "select",
        options: ["Owned", "Leased", "Sub-Contracted", "Other"],
      },
      { key: "owner_id", label: "Owner", type: "owner_select" },
      {
        key: "vehicle_status",
        label: "Status",
        type: "select",
        options: ["Active", "Inactive", "Maintenance", "Archived"],
      },
      { key: "company_ref", label: "Company" },
    ],
  },

  equipment: {
    slug: "equipment",
    title: "Equipment",
    description: "Trays, trailers and other equipment with ownership and status.",
    icon: "Cube",
    api: "/equipment",
    idField: "id",
    primaryField: "equipment_number",
    statusField: "equipment_status",
    statusOptions: ["Available", "Assigned", "Maintenance", "Inactive", "Archived"],
    searchFields: ["equipment_number", "equipment_type", "ownership_model", "company_ref"],
    columns: [
      { key: "equipment_number", label: "Equipment #", weight: "primary" },
      { key: "equipment_type", label: "Type" },
      { key: "ownership_model", label: "Ownership" },
      { key: "owner_id", label: "Owner", type: "owner_lookup" },
      { key: "equipment_status", label: "Status", type: "status" },
    ],
    fields: [
      { key: "equipment_number", label: "Equipment Number", required: true },
      {
        key: "equipment_type",
        label: "Equipment Type",
        type: "select",
        options: ["Tray", "Trailer", "Other"],
      },
      {
        key: "ownership_model",
        label: "Ownership Model",
        type: "select",
        options: ["Owned", "Leased", "Sub-Contracted", "Other"],
      },
      { key: "owner_id", label: "Owner", type: "owner_select" },
      {
        key: "equipment_status",
        label: "Status",
        type: "select",
        options: ["Available", "Assigned", "Maintenance", "Inactive", "Archived"],
      },
      { key: "company_ref", label: "Company" },
    ],
  },
};

export const REGISTER_SLUGS = ["drivers", "owners", "vehicles", "equipment"];

export function statusTone(status) {
  const s = String(status || "").toLowerCase();
  if (s === "archived") return "grey";
  if (s === "inactive") return "grey";
  if (s === "maintenance") return "amber";
  if (s === "on leave" || s === "training" || s === "probation") return "amber";
  if (s === "available" || s === "active" || s === "assigned") return "green";
  return "grey";
}
