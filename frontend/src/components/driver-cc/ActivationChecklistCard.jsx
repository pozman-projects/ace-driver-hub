import React from "react";
import { Warning, CheckCircle } from "@phosphor-icons/react";
import { ManagementCard, StatusPill } from "./driverCCUtils";

export default function ActivationChecklistCard({ data }) {
  const a = data.activation || {};
  const pct = a.mandatory_total ? Math.round((a.mandatory_done / a.mandatory_total) * 100) : 0;
  const readiness = a.readiness || "Not Ready";
  const variant = readiness === "Ready" ? "ok" : readiness === "Partial" ? "warn" : "danger";
  return (
    <ManagementCard
      testid="card-activation"
      section="activation"
      title="Driver Activation Checklist"
      subtitle="Evidence-validated readiness"
      canEdit={false}
    >
      <div className="flex items-center justify-between mb-2">
        <StatusPill status={readiness} testid="activation-readiness" />
        <span className="text-[11px] text-slate-500" data-testid="activation-progress">
          {a.mandatory_done}/{a.mandatory_total} mandatory · {pct}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-slate-100 rounded overflow-hidden mb-2">
        <div className={`h-full ${variant === "ok" ? "bg-emerald-500" : variant === "warn" ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <ul className="space-y-1 text-xs max-h-40 overflow-y-auto">
        {(a.items || []).slice(0, 8).map((it) => (
          <li key={it.item_key} className="flex items-start gap-2" data-testid={`activation-item-${it.item_key}`}>
            {it.complete ? (
              <CheckCircle size={13} weight="fill" className="text-emerald-500 mt-0.5 shrink-0" />
            ) : (
              <Warning size={13} weight="fill" className={`${it.mandatory ? "text-red-500" : "text-amber-500"} mt-0.5 shrink-0`} />
            )}
            <span className="min-w-0">
              <span className={`${it.complete ? "text-slate-700" : "text-slate-900"} font-medium`}>{it.label}</span>
              <div className="text-[10px] text-slate-500 truncate">{it.source} · {it.reason}</div>
            </span>
          </li>
        ))}
      </ul>
    </ManagementCard>
  );
}
