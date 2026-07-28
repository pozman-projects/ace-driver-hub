import React from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { ManagementCard, InlineField } from "./driverCCUtils";

export default function CarrierEquipmentCard({ data }) {
  const v = data.vehicle;
  const dva = data.vehicle_assignment;
  const equipment = data.equipment_assignments || [];
  return (
    <ManagementCard
      testid="card-car-carrier"
      section="car-carrier"
      title="Car Carrier & Equipment"
      subtitle="Vehicle + tray + trailer"
      canEdit={false}
    >
      {v ? (
        <>
          <InlineField label="Vehicle" value={<Link to="/registers/vehicles" className="text-cyan-700 hover:underline">{v.registration_number}</Link>} testid="field-vehicle-rego" mono />
          <InlineField label="Make/Model" value={[v.make, v.model].filter(Boolean).join(" ") || null} testid="field-vehicle-make" />
          <InlineField label="Config" value={v.carrier_config || v.body_type || null} testid="field-vehicle-config" />
          <InlineField label="Since" value={dva?.effective_from} testid="field-vehicle-since" />
        </>
      ) : (
        <div data-testid="vehicle-empty" className="text-xs text-slate-400 italic">No primary vehicle assignment.</div>
      )}
      <div className="pt-2 border-t border-slate-100 mt-2">
        <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Equipment</div>
        {equipment.length === 0 ? (
          <div data-testid="equipment-empty" className="text-xs text-slate-400 italic">No active equipment.</div>
        ) : (
          <ul className="space-y-1">
            {equipment.slice(0, 4).map((row) => (
              <li key={row.assignment?.id || row.assignment?.driver_equipment_assignment_id} className="flex items-center justify-between text-xs">
                <span className="truncate font-mono text-slate-800">
                  {row.equipment?.equipment_number || row.assignment?.equipment_number_snapshot}
                </span>
                <span className="text-slate-500 truncate ml-2">{row.equipment?.equipment_type}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="pt-2">
        <Link to="/relationships/driver-vehicle" data-testid="carrier-reassign-link" className="text-[11px] text-cyan-700 hover:underline">
          Change assignment <CaretRight size={10} className="inline" />
        </Link>
      </div>
    </ManagementCard>
  );
}
