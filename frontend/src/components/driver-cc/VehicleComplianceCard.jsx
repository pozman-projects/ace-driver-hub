import React from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { RightCard, StatusPill, InlineField } from "./driverCCUtils";

/**
 * FA-01 · Vehicle Compliance right-rail card.
 * Answers: "Is the coupled vehicle set safe/legal to leave the yard today?"
 * Displays Worst Status Wins overall, then explicit Prime / Tray / Trailer
 * component rows using canonical data already surfaced on the DCC payload.
 * No new compliance calculator — consumes vehicle_summary + tray_equipment
 * + trailer_equipment already on the aggregator.
 */
export default function VehicleComplianceCard({ data }) {
  const vs = data.compliance_intelligence?.vehicle_summary;
  const extras = data.vehicle_compliance_extras || {};
  const vehicle = data.vehicle || null;
  const tray = data.tray_equipment || null;
  const trailer = data.trailer_equipment || null;
  const openDefects = (extras.open_defects || []).length;
  const overdueTasks = (extras.overdue_maintenance || []).length;

  if (!vs && !vehicle) {
    return (
      <RightCard title="Vehicle Compliance" testid="ci-vehicle-compliance" section="vehicle-compliance">
        <div data-testid="ci-vehicle-empty" className="text-xs text-slate-400 italic">No vehicle to monitor.</div>
      </RightCard>
    );
  }

  return (
    <RightCard title="Vehicle Compliance" testid="ci-vehicle-compliance" section="vehicle-compliance">
      <div className="pb-1 flex items-center justify-between">
        <StatusPill status={vs?.overall_status || "Compliant"} compact testid="ci-vehicle-worst-status" />
        <span className="text-[10px] text-slate-500">Worst Status Wins</span>
      </div>

      {/* Prime Mover row */}
      <div className="mt-2 border-t border-slate-100 pt-1.5" data-testid="ci-vc-prime-row">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-semibold">Prime</span>
          <StatusPill status={vs?.overall_status || (vehicle ? "Compliant" : "Missing")} compact testid="ci-vc-prime-status" />
        </div>
        <div className="text-[11px] text-slate-700 truncate" data-testid="ci-vc-prime-identity">
          {vehicle
            ? `${vehicle.registration_number || "—"} · ${vehicle.make || ""} ${vehicle.model || ""}`.trim()
            : <span className="italic text-slate-400">No prime mover assigned</span>}
        </div>
        <InlineField label="Last insp." value={extras.latest_inspection?.inspection_date} testid="ci-inspection-date" />
        <InlineField label="Result" value={extras.latest_inspection?.result} testid="ci-inspection-result" />
        <InlineField label="Next due" value={extras.latest_inspection?.next_inspection_due} testid="ci-inspection-next-due" />
        <InlineField label="Open defects" value={openDefects} testid="ci-defects-count" />
        <InlineField label="Overdue tasks" value={overdueTasks} testid="ci-maintenance-count" />
      </div>

      {/* Tray row */}
      <div className="mt-2 border-t border-slate-100 pt-1.5" data-testid="ci-vc-tray-row">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-semibold">Tray</span>
          {tray
            ? <StatusPill status={tray.equipment_status || "Compliant"} compact testid="ci-vc-tray-status" />
            : <span className="text-[10px] text-slate-400 italic" data-testid="ci-vc-tray-uncoupled">Uncoupled</span>}
        </div>
        {tray && (
          <div className="text-[11px] text-slate-700 truncate" data-testid="ci-vc-tray-identity">
            {tray.equipment_number || "—"}
            {tray.equipment_type ? ` · ${tray.equipment_type}` : ""}
          </div>
        )}
      </div>

      {/* Trailer row */}
      <div className="mt-2 border-t border-slate-100 pt-1.5" data-testid="ci-vc-trailer-row">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-semibold">Trailer</span>
          {trailer
            ? <StatusPill status={trailer.equipment_status || "Compliant"} compact testid="ci-vc-trailer-status" />
            : <span className="text-[10px] text-slate-400 italic" data-testid="ci-vc-trailer-uncoupled">Uncoupled</span>}
        </div>
        {trailer && (
          <div className="text-[11px] text-slate-700 truncate" data-testid="ci-vc-trailer-identity">
            {trailer.equipment_number || "—"}
            {trailer.equipment_type ? ` · ${trailer.equipment_type}` : ""}
          </div>
        )}
      </div>

      <div className="pt-2">
        <Link to="/compliance" data-testid="ci-open-vehicle-compliance" className="text-[11px] text-cyan-700 hover:underline">
          Open vehicle compliance <CaretRight size={10} className="inline" />
        </Link>
      </div>
    </RightCard>
  );
}
