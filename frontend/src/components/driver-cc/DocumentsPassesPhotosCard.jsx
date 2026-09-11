/**
 * EB-R03B · Documents, Passes & Photos featured card.
 *
 * Renders 10 Blueprint-mandated categories from the canonical Driver
 * Profile aggregator (`documents.stats.featured`). Presence / count /
 * quick-open only — no client-side compliance or expiry inference.
 * The Document Library remains the full repository.
 */
import React from "react";
import { Link } from "react-router-dom";
import { CaretRight, FileArrowDown, Check, X } from "@phosphor-icons/react";
import { RightCard, MiniStat } from "./driverCCUtils";

const CATEGORIES = [
  { key: "profile_photo",       library_type: "Profile Photo" },
  { key: "driver_licence",      library_type: "Driver Licence" },
  { key: "starting_documents",  library_type: "Starting Document" },
  { key: "other_documents",     library_type: null },
  { key: "truck_photos",        library_type: "Truck Photo", scope: "vehicle" },
  { key: "vehicle_registration",library_type: "Vehicle Registration" },
  { key: "vehicle_insurance",   library_type: "Vehicle Insurance" },
  { key: "rapid",               library_type: "Driver Pass", category: "RAPID" },
  { key: "prixcar",             library_type: "Driver Pass", category: "PrixCar" },
  { key: "additional_passes",   library_type: "Driver Pass" },
];

function PresenceBadge({ present, count }) {
  if (typeof count === "number" && count > 1) {
    return <span data-testid="feat-count" className="text-[10px] font-semibold text-slate-600 tabular-nums">{count}</span>;
  }
  return present
    ? <Check data-testid="feat-present" size={12} className="text-emerald-600" weight="bold" />
    : <X data-testid="feat-missing" size={12} className="text-slate-400" weight="bold" />;
}

export default function DocumentsPassesPhotosCard({ data, driverId }) {
  const s = data?.documents?.stats || {};
  const featured = s.featured || {};
  const vehicleId = featured.truck_photos?.vehicle_id || data?.vehicle?.id;
  return (
    <RightCard title="Documents, Passes & Photos" testid="ci-documents" section="documents">
      <div className="grid grid-cols-4 gap-2 text-center mb-2">
        <MiniStat label="Total" value={s.total ?? 0} testid="doc-stat-total" />
        <MiniStat label="Active" value={s.active ?? 0} variant="ok" testid="doc-stat-active" />
        <MiniStat label="Review" value={s.under_review ?? 0} variant={s.under_review > 0 ? "warn" : "neutral"} testid="doc-stat-review" />
        <MiniStat label="Reject" value={s.rejected ?? 0} variant={s.rejected > 0 ? "warn" : "neutral"} testid="doc-stat-reject" />
      </div>

      <ul className="divide-y divide-slate-100 border-t border-slate-100" data-testid="featured-doc-list">
        {CATEGORIES.map((c) => {
          const bucket = featured[c.key] || {};
          const count = bucket.count || 0;
          const current = bucket.current || null;
          const present = !!current || count > 0;
          const libParams = new URLSearchParams();
          if (c.scope === "vehicle" && vehicleId) {
            libParams.set("entity_type", "Vehicle");
            libParams.set("entity_id", vehicleId);
          } else {
            libParams.set("entity_type", "Driver");
            libParams.set("entity_id", driverId);
          }
          if (c.library_type) libParams.set("document_type", c.library_type);
          if (c.category) libParams.set("category", c.category);
          const isTruckWithoutVehicle = c.scope === "vehicle" && !vehicleId;
          return (
            <li key={c.key} className="flex items-center gap-2 py-1.5 text-[11px]" data-testid={`feat-row-${c.key}`}>
              <span className="w-4 flex justify-center"><PresenceBadge present={present} count={count} /></span>
              <span className="truncate text-slate-800 flex-1">{bucket.label || c.key}</span>
              {isTruckWithoutVehicle ? (
                <span className="text-[10px] text-slate-400 italic" data-testid={`feat-${c.key}-no-vehicle`}>No vehicle</span>
              ) : current ? (
                <Link
                  to={`/documents?${libParams.toString()}`}
                  data-testid={`feat-${c.key}-open`}
                  className="text-cyan-700 hover:underline inline-flex items-center gap-0.5"
                >
                  Open <FileArrowDown size={10} />
                </Link>
              ) : (
                <Link
                  to={`/documents?${libParams.toString()}`}
                  data-testid={`feat-${c.key}-add`}
                  className="text-slate-500 hover:text-cyan-700 hover:underline"
                >
                  Add
                </Link>
              )}
            </li>
          );
        })}
      </ul>

      <div className="pt-2 flex items-center justify-between text-[11px]">
        <Link
          to={`/documents?entity_type=Driver&entity_id=${driverId}`}
          data-testid="ci-open-documents"
          className="text-cyan-700 hover:underline"
        >
          View all documents <CaretRight size={10} className="inline" />
        </Link>
        <Link
          to={`/documents?entity_type=Driver&entity_id=${driverId}&status=Under Review`}
          data-testid="ci-open-review"
          className="text-cyan-700 hover:underline"
        >
          Under review
        </Link>
      </div>
    </RightCard>
  );
}
