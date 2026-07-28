import React from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { RightCard, StatusPill, InlineField } from "./driverCCUtils";

export default function VehicleComplianceCard({ data }) {
  const vs = data.compliance_intelligence?.vehicle_summary;
  const extras = data.vehicle_compliance_extras || {};
  return (
    <RightCard title="Vehicle Compliance" testid="ci-vehicle-compliance" section="vehicle-compliance">
      {vs ? (
        <>
          <div className="pb-1"><StatusPill status={vs.overall_status || "Compliant"} compact testid="ci-vehicle-worst-status" /></div>
          <InlineField label="Last insp." value={extras.latest_inspection?.inspection_date} testid="ci-inspection-date" />
          <InlineField label="Result" value={extras.latest_inspection?.result} testid="ci-inspection-result" />
          <InlineField label="Open defects" value={(extras.open_defects || []).length} testid="ci-defects-count" />
          <InlineField label="Overdue tasks" value={(extras.overdue_maintenance || []).length} testid="ci-maintenance-count" />
          <div className="pt-1">
            <Link to="/compliance" data-testid="ci-open-vehicle-compliance" className="text-[11px] text-cyan-700 hover:underline">Open vehicle compliance <CaretRight size={10} className="inline" /></Link>
          </div>
        </>
      ) : (
        <div data-testid="ci-vehicle-empty" className="text-xs text-slate-400 italic">No vehicle to monitor.</div>
      )}
    </RightCard>
  );
}
