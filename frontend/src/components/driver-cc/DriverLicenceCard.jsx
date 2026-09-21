import React from "react";
import { RightCard, StatusPill, InlineField, ROLE_CAN_EDIT_COMPLIANCE } from "./driverCCUtils";
import EvidenceActions from "./EvidenceActions";

export default function DriverLicenceCard({ data, role, onSaved }) {
  const l = data.primary_licence;
  const s = (data.compliance_intelligence?.driver_summary?.components || []).find((c) => c.component === "primary_licence");
  const evidence = data.documents?.driver_licence_evidence || null;
  const canEdit = ROLE_CAN_EDIT_COMPLIANCE.has(role);
  return (
    <RightCard title="Driver Licence" testid="ci-licence" section="licence">
      {l ? (
        <>
          <InlineField label="Number" value={l.licence_number} testid="ci-licence-number" mono />
          <InlineField label="Class" value={l.licence_class} testid="ci-licence-class" />
          <InlineField label="State" value={l.state} testid="ci-licence-state" />
          <InlineField label="Expiry" value={l.expiry_date} testid="ci-licence-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-licence-status" /></div>
          <EvidenceActions
            evidenceDoc={evidence}
            canEdit={canEdit}
            acceptHint=".pdf,image/*"
            uploadPayload={{
              title: `Driver Licence — ${l.licence_number || l.id}`,
              document_type: "Driver Licence",
              entity_type: "DriverLicence",
              entity_id: l.id,
              relationship_type: "Evidence",
              is_primary: "true",
              sensitivity: "Confidential",
            }}
            onChanged={onSaved}
            testidPrefix="ci-licence-ev"
          />
        </>
      ) : (
        <div data-testid="ci-licence-empty" className="text-xs text-slate-400 italic">No primary licence.</div>
      )}
    </RightCard>
  );
}
