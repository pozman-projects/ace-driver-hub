import React from "react";
import { RightCard, StatusPill, InlineField } from "./driverCCUtils";

export default function TruckInsuranceCard({ data }) {
  const i = data.primary_insurance;
  const s = (data.compliance_intelligence?.vehicle_summary?.components || []).find((c) => c.component === "insurance");
  return (
    <RightCard title="Truck Insurance" testid="ci-insurance" section="insurance">
      {i ? (
        <>
          <InlineField label="Insurer" value={i.insurer} testid="ci-insurance-insurer" />
          <InlineField label="Policy" value={i.policy_number} testid="ci-insurance-policy" mono />
          <InlineField label="Cover" value={i.cover_type} testid="ci-insurance-cover" />
          <InlineField label="Expiry" value={i.expiry_date} testid="ci-insurance-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-insurance-status" /></div>
        </>
      ) : (
        <div data-testid="ci-insurance-empty" className="text-xs text-slate-400 italic">No current policy.</div>
      )}
    </RightCard>
  );
}
