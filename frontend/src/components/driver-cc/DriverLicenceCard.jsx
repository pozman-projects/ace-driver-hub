import React from "react";
import { RightCard, StatusPill, InlineField } from "./driverCCUtils";

export default function DriverLicenceCard({ data }) {
  const l = data.primary_licence;
  const s = (data.compliance_intelligence?.driver_summary?.components || []).find((c) => c.component === "primary_licence");
  return (
    <RightCard title="Driver Licence" testid="ci-licence" section="licence">
      {l ? (
        <>
          <InlineField label="Number" value={l.licence_number} testid="ci-licence-number" mono />
          <InlineField label="Class" value={l.licence_class} testid="ci-licence-class" />
          <InlineField label="State" value={l.state} testid="ci-licence-state" />
          <InlineField label="Expiry" value={l.expiry_date} testid="ci-licence-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-licence-status" /></div>
        </>
      ) : (
        <div data-testid="ci-licence-empty" className="text-xs text-slate-400 italic">No primary licence.</div>
      )}
    </RightCard>
  );
}
