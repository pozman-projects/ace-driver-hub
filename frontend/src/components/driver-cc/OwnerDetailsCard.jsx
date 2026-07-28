import React from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { ManagementCard, InlineField } from "./driverCCUtils";

export default function OwnerDetailsCard({ data }) {
  const owner = data.owner;
  const dor = data.owner_relationship;
  return (
    <ManagementCard
      testid="card-owner-details"
      section="owner-details"
      title="Owner Details"
      subtitle="Read-only relationship view"
      canEdit={false}
    >
      {owner ? (
        <>
          <InlineField label="Name" value={<Link to="/registers/owners" className="text-cyan-700 hover:underline">{owner.name}</Link>} testid="field-owner-name" />
          <InlineField label="Type" value={owner.owner_type} testid="field-owner-type" />
          <InlineField label="Mobile" value={owner.contact_phone || owner.phone} testid="field-owner-mobile" />
          <InlineField label="Email" value={owner.contact_email || owner.email} testid="field-owner-email-canonical" />
          <InlineField label="Relation" value={dor?.relationship_type} testid="field-relationship-type" />
          <InlineField label="Since" value={dor?.effective_from} testid="field-relationship-since" />
          <div className="pt-2">
            <Link to="/relationships/driver-owner" data-testid="owner-change-link" className="text-[11px] text-cyan-700 hover:underline">
              Change relationship <CaretRight size={10} className="inline" />
            </Link>
          </div>
        </>
      ) : (
        <div data-testid="owner-empty" className="text-xs text-slate-400 italic">No current owner relationship.</div>
      )}
    </ManagementCard>
  );
}
