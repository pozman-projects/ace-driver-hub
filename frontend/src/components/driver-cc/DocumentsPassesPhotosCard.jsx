import React from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { RightCard, MiniStat } from "./driverCCUtils";

export default function DocumentsPassesPhotosCard({ data, driverId }) {
  const s = data.documents?.stats || {};
  const recent = s.recent || [];
  return (
    <RightCard title="Documents, Passes & Photos" testid="ci-documents" section="documents">
      <div className="grid grid-cols-4 gap-2 text-center mb-2">
        <MiniStat label="Total" value={s.total} testid="doc-stat-total" />
        <MiniStat label="Active" value={s.active} variant="ok" testid="doc-stat-active" />
        <MiniStat label="Review" value={s.under_review} variant={s.under_review > 0 ? "warn" : "neutral"} testid="doc-stat-review" />
        <MiniStat label="Reject" value={s.rejected} variant={s.rejected > 0 ? "warn" : "neutral"} testid="doc-stat-reject" />
      </div>
      <ul className="space-y-1 text-xs">
        {recent.slice(0, 3).map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-2" data-testid={`doc-recent-${d.id}`}>
            <span className="truncate text-slate-800">{d.title || d.filename}</span>
            <span className="text-[10px] text-slate-500 truncate">{d.category || d.status}</span>
          </li>
        ))}
      </ul>
      <div className="pt-2 flex items-center justify-between text-[11px]">
        <Link to={`/documents?entity_type=Driver&entity_id=${driverId}`} data-testid="ci-open-documents" className="text-cyan-700 hover:underline">Open library <CaretRight size={10} className="inline" /></Link>
        <Link to={`/documents?entity_type=Driver&entity_id=${driverId}&status=Under Review`} data-testid="ci-open-review" className="text-cyan-700 hover:underline">Under review</Link>
      </div>
    </RightCard>
  );
}
