import React from "react";
import { RightCard, StatusPill, InlineField } from "./driverCCUtils";

export default function TruckRegistrationCard({ data }) {
  const r = data.primary_registration;
  const vs = data.compliance_intelligence?.vehicle_summary;
  const s = (vs?.components || []).find((c) => c.component === "registration");
  return (
    <RightCard title="Truck Registration" testid="ci-registration" section="registration">
      {r ? (
        <>
          <InlineField label="Rego" value={r.registration_number} testid="ci-registration-number" mono />
          <InlineField label="State" value={r.state} testid="ci-registration-state" />
          <InlineField label="Expiry" value={r.expiry_date} testid="ci-registration-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-registration-status" /></div>
        </>
      ) : (
        <div data-testid="ci-registration-empty" className="text-xs text-slate-400 italic">No primary vehicle assigned.</div>
      )}
    </RightCard>
  );
}
