import React from "react";
import { RightCard, StatusPill, InlineField, ROLE_CAN_EDIT_COMPLIANCE } from "./driverCCUtils";
import EvidenceActions from "./EvidenceActions";

export default function TruckRegistrationCard({ data, role, onSaved }) {
  const r = data.primary_registration;
  const vs = data.compliance_intelligence?.vehicle_summary;
  const s = (vs?.components || []).find((c) => c.component === "registration");
  const evidence = data.documents?.registration_evidence || null;
  const canEdit = ROLE_CAN_EDIT_COMPLIANCE.has(role);
  return (
    <RightCard title="Truck Registration" testid="ci-registration" section="registration">
      {r ? (
        <>
          <InlineField label="Rego" value={r.registration_number} testid="ci-registration-number" mono />
          <InlineField label="State" value={r.state} testid="ci-registration-state" />
          <InlineField label="Expiry" value={r.expiry_date} testid="ci-registration-expiry" />
          <div className="pt-1"><StatusPill status={s?.status || "Compliant"} compact testid="ci-registration-status" /></div>
          <EvidenceActions
            evidenceDoc={evidence}
            canEdit={canEdit}
            acceptHint=".pdf,image/*"
            uploadPayload={{
              title: `Vehicle Registration — ${r.registration_number || r.id}`,
              document_type: "Vehicle Registration",
              entity_type: "VehicleRegistration",
              entity_id: r.id,
              relationship_type: "Evidence",
              is_primary: "true",
              sensitivity: "Standard",
            }}
            onChanged={onSaved}
            testidPrefix="ci-registration-ev"
          />
        </>
      ) : (
        <div data-testid="ci-registration-empty" className="text-xs text-slate-400 italic">No primary vehicle assigned.</div>
      )}
    </RightCard>
  );
}
