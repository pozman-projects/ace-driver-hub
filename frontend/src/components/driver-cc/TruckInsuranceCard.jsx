import React from "react";
import { RightCard, StatusPill, InlineField, ROLE_CAN_EDIT } from "./driverCCUtils";
import EvidenceActions from "./EvidenceActions";

export default function TruckInsuranceCard({ data, role, onSaved }) {
  const i = data.primary_insurance;
  const s = (data.compliance_intelligence?.vehicle_summary?.components || []).find((c) => c.component === "insurance");
  const evidence = data.documents?.insurance_evidence || null;
  const canEdit = ROLE_CAN_EDIT.has(role);
  return (
    <RightCard title="Truck Insurance" testid="ci-insurance" section="insurance">
      {i ? (
        <>
          <InlineField label="Insurer" value={i.insurer} testid="ci-insurance-insurer" />
          <InlineField label="Policy" value={i.policy_number} testid="ci-insurance-policy" mono />
          <InlineField label="Cover" value={i.cover_type} testid="ci-insurance-cover" />
          <InlineField label="Expiry" value={i.expiry_date} testid="ci-insurance-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-insurance-status" /></div>
          <EvidenceActions
            evidenceDoc={evidence}
            canEdit={canEdit}
            acceptHint=".pdf,image/*"
            uploadPayload={{
              title: `Vehicle Insurance — ${i.policy_number || i.id}`,
              document_type: "Vehicle Insurance",
              entity_type: "VehicleInsurancePolicy",
              entity_id: i.id,
              relationship_type: "Evidence",
              is_primary: "true",
              sensitivity: "Standard",
            }}
            onChanged={onSaved}
            testidPrefix="ci-insurance-ev"
          />
        </>
      ) : (
        <div data-testid="ci-insurance-empty" className="text-xs text-slate-400 italic">No current policy.</div>
      )}
    </RightCard>
  );
}
