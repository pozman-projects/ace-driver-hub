import React from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { RightCard, StatusPill, MiniStat } from "./driverCCUtils";

export default function ComplianceOverviewCard({ data, driverId }) {
  const ci = data.compliance_intelligence || {};
  const counts = data.alert_counts || {};
  // FA-01 · "n of n Compliant" primary count, aggregated across the
  // canonical driver + vehicle component summaries. No new calculator —
  // we consume the same components the right-rail cards use.
  const components = [
    ...(ci.driver_summary?.components || []),
    ...(ci.vehicle_summary?.components || []),
  ];
  const total = components.length;
  const compliantCount = components.filter((c) => c.status === "Compliant").length;
  const worst = ci.worst_status || "Compliant";
  return (
    <RightCard title="Compliance Overview" testid="ci-overview" section="ci-overview">
      <div className="flex items-baseline justify-between mb-1">
        <div className="text-lg font-semibold text-slate-900" data-testid="ci-compliant-count">
          {total > 0 ? `${compliantCount} of ${total} Compliant` : "No components tracked"}
        </div>
        <StatusPill status={worst} compact testid="ci-worst-status" />
      </div>
      <p className="text-[11px] text-slate-500" data-testid="ci-worst-explanation">
        {ci.explanation}
      </p>
      <div className="grid grid-cols-3 gap-2 mt-3 text-center">
        <MiniStat label="Active" value={counts.active} variant={counts.active > 0 ? "warn" : "ok"} testid="ci-count-active" />
        <MiniStat label="Ack" value={counts.acknowledged} testid="ci-count-ack" />
        <MiniStat label="Snoozed" value={counts.snoozed} testid="ci-count-snoozed" />
      </div>
      <div className="pt-2 flex items-center justify-between text-[11px]">
        <Link to={`/notifications/all?entity_type=Driver&entity_id=${driverId}`} data-testid="ci-open-notifications" className="text-cyan-700 hover:underline">
          Open notifications <CaretRight size={10} className="inline" />
        </Link>
        <Link to="/compliance" data-testid="ci-open-compliance" className="text-cyan-700 hover:underline">
          Compliance <CaretRight size={10} className="inline" />
        </Link>
      </div>
    </RightCard>
  );
}
