import React from "react";
import { RightCard, StatusPill, InlineField, ROLE_CAN_EDIT_COMPLIANCE } from "./driverCCUtils";
import EvidenceActions from "./EvidenceActions";

// FA-04 · Truck Insurance N/A presentation.
// Semantics:
//   Case A  no primary vehicle             → Not Applicable, explanatory only
//   Case B  primary vehicle, no insurance  → canonical Missing state
//   Case C  primary vehicle + insurance    → canonical provider / policy / status
// No activation change. No schema change. No new evidence endpoint. No fake entity.
export default function TruckInsuranceCard({ data, role, onSaved }) {
  const i = data.primary_insurance;
  const vehicle = data.vehicle;
  const vehicleComponents = data.compliance_intelligence?.vehicle_summary?.components || [];
  const insuranceComp = vehicleComponents.find((c) => c.component === "insurance");
  const evidence = data.documents?.insurance_evidence || null;
  const canEdit = ROLE_CAN_EDIT_COMPLIANCE.has(role);

  // ── Case A · No primary vehicle ────────────────────────────────────
  if (!vehicle) {
    return (
      <RightCard title="Truck Insurance" testid="ci-insurance" section="insurance">
        <div className="pt-0.5">
          <StatusPill status="Not Applicable" compact testid="ci-insurance-status" />
        </div>
        <div
          data-testid="ci-insurance-na-reason"
          className="text-xs text-slate-500 mt-2"
        >
          No primary vehicle assigned
        </div>
        <p
          data-testid="ci-insurance-na-helper"
          className="text-[11px] text-slate-400 italic mt-1"
        >
          Truck Insurance will be assessed once a primary vehicle is assigned.
        </p>
      </RightCard>
    );
  }

  // ── Case C · Primary vehicle + current insurance ───────────────────
  if (i) {
    return (
      <RightCard title="Truck Insurance" testid="ci-insurance" section="insurance">
        <InlineField label="Provider" value={i.provider} testid="ci-insurance-provider" />
        <InlineField label="Policy" value={i.policy_number} testid="ci-insurance-policy" mono />
        <InlineField label="Cover" value={i.cover_type} testid="ci-insurance-cover" />
        <InlineField label="Expiry" value={i.expiry_date} testid="ci-insurance-expiry" />
        <div className="pt-1">
          <StatusPill status={insuranceComp?.status || "Compliant"} compact testid="ci-insurance-status" />
        </div>
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
      </RightCard>
    );
  }

  // ── Case B · Primary vehicle but no current insurance ──────────────
  // Reuse the canonical vehicle_summary insurance component status
  // (Missing / Incomplete / etc). No fake entity, no evidence controls.
  const status = insuranceComp?.status || "Missing";
  return (
    <RightCard title="Truck Insurance" testid="ci-insurance" section="insurance">
      <div className="pt-0.5">
        <StatusPill status={status} compact testid="ci-insurance-status" />
      </div>
      <div
        data-testid="ci-insurance-missing-reason"
        className="text-xs text-slate-500 mt-2"
      >
        No current Truck Insurance policy
      </div>
    </RightCard>
  );
}
