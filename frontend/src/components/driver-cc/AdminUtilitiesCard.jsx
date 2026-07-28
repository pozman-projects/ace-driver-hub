import React from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { ManagementCard } from "./driverCCUtils";

export default function AdminUtilitiesCard({ data, driverId, role }) {
  const canManage = ["Admin", "Manager"].includes(role);
  const utilities = [
    { key: "docs", label: "Open Document Library", to: `/documents?entity_type=Driver&entity_id=${driverId}`, available: true, testid: "util-open-docs" },
    { key: "upload", label: "Upload supporting document", to: `/documents?entity_type=Driver&entity_id=${driverId}&upload=1`, available: true, testid: "util-upload" },
    { key: "imports", label: "Open Import Centre", to: "/imports", available: canManage, testid: "util-imports" },
    { key: "numbering", label: "Numbering admin", to: "/administration/numbering", available: true, testid: "util-numbering" },
    { key: "notifications", label: "Driver alerts", to: `/notifications/all?entity_type=Driver&entity_id=${driverId}`, available: true, testid: "util-notifications" },
  ];
  const unavailable = [
    { key: "start_sheet", label: "Generate Driver Start Sheet" },
    { key: "export", label: "Export Driver Profile" },
  ];
  return (
    <ManagementCard
      testid="card-admin-utilities"
      section="admin"
      title="Administration & Utilities"
      subtitle="Related tools & exports"
      canEdit={false}
    >
      <ul className="space-y-1.5">
        {utilities.filter(u => u.available).map((u) => (
          <li key={u.key}>
            <Link to={u.to} data-testid={u.testid} className="text-sm text-cyan-700 hover:underline inline-flex items-center gap-1">
              <CaretRight size={11} /> {u.label}
            </Link>
          </li>
        ))}
      </ul>
      <div className="pt-2 mt-2 border-t border-slate-100">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Coming soon</div>
        <ul className="space-y-1">
          {unavailable.map((u) => (
            <li key={u.key} className="text-xs text-slate-400 flex items-center gap-1.5">
              <span data-testid={`util-unavailable-${u.key}`}>{u.label}</span>
              <span className="text-[9px] uppercase tracking-[0.15em] border border-slate-200 rounded-full px-1.5 py-0.5">Unavailable</span>
            </li>
          ))}
        </ul>
      </div>
    </ManagementCard>
  );
}
