import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Warning, CheckCircle, ArrowsClockwise, CaretRight, ShieldCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ManagementCard, StatusPill } from "./driverCCUtils";
import { useAuth } from "../../context/AuthContext";

/**
 * MR-04B-FIX Defect 2 · DCC Activation card.
 *
 * ONE source of truth: `GET /api/drivers/{id}/blueprint-readiness`.
 * Displays the EXACT seven canonical Blueprint V1 items — no slicing, no
 * frontend calculation. The aggregator also embeds the same result under
 * `data.activation`, which is used as the initial payload while the direct
 * fetch resolves.
 */
export default function ActivationChecklistCard({ data }) {
  const { user } = useAuth();
  const driverId = data?.driver?.id;
  const canActivate = ["Admin", "Manager"].includes(user?.role);

  // Embedded canonical readiness from the aggregator (always the same shape).
  const embedded = data?.activation || null;
  const [readinessData, setReadinessData] = useState(embedded);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setReadinessData(embedded); }, [embedded]);

  const refreshCanonical = useCallback(async () => {
    if (!driverId) return null;
    try {
      const { data: d } = await api.get(`/drivers/${driverId}/blueprint-readiness`);
      setReadinessData(d);
      return d;
    } catch {
      return null;
    }
  }, [driverId]);

  useEffect(() => { refreshCanonical(); }, [refreshCanonical]);

  const readiness = readinessData?.readiness || "Not Assessed";
  const items = Array.isArray(readinessData?.items) ? readinessData.items : [];
  const missingCount = Array.isArray(readinessData?.missing) ? readinessData.missing.length : items.filter((i) => !i.complete).length;
  const completeCount = items.filter((i) => i.complete).length;
  const total = items.length;
  const pct = total ? Math.round((completeCount / total) * 100) : 0;
  const variant = readiness === "Ready" ? "ok" : "danger";

  const activate = async () => {
    if (!window.confirm(`Activate this driver?\n\nBlueprint V1 readiness: ${readiness}\nComplete: ${completeCount}/${total}\n\nThis sets Driver Status to Active.`)) return;
    setBusy(true);
    try {
      await api.post(`/drivers/${driverId}/activation/activate`,
                     { reason: "Activated from DCC", set_driver_status_active: true });
      toast.success("Driver activated");
      await refreshCanonical();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "DRIVER_NOT_READY") {
        toast.error(`Driver not ready — ${detail.missing?.length || 0} item(s) missing`);
      } else {
        toast.error(formatApiErrorDetail(detail) || "Activate failed");
      }
    } finally { setBusy(false); }
  };

  const deactivate = async () => {
    const reason = window.prompt("Deactivate driver. Enter reason:");
    if (!reason || reason.length < 3) return;
    setBusy(true);
    try {
      await api.post(`/drivers/${driverId}/activation/deactivate`, { reason });
      toast.success("Driver deactivated");
      await refreshCanonical();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Deactivate failed");
    } finally { setBusy(false); }
  };

  const activated = data?.driver?.driver_status === "Active";

  return (
    <ManagementCard
      testid="card-activation"
      section="activation"
      title="Blueprint V1 · Activation Readiness"
      subtitle="Canonical seven-item gate"
      canEdit={false}
    >
      <div className="flex items-center justify-between mb-2">
        <StatusPill status={readiness} testid="activation-readiness" />
        <span className="text-[11px] text-slate-500" data-testid="activation-progress">
          {completeCount}/{total} · {pct}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-slate-100 rounded overflow-hidden mb-2">
        <div className={`h-full ${variant === "ok" ? "bg-emerald-500" : "bg-red-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="grid grid-cols-2 gap-2 mb-2 text-center text-[10px]">
        <MiniCounter testid="activation-complete-count" label="Complete" value={completeCount} tone={completeCount === total ? "ok" : "neutral"} />
        <MiniCounter testid="activation-missing-count" label="Missing" value={missingCount} tone={missingCount ? "warn" : "ok"} />
      </div>
      {items.length > 0 && (
        <ul className="space-y-1 text-xs" data-testid="activation-items-list">
          {items.map((it) => (
            <li key={it.key} className="flex items-start gap-2" data-testid={`activation-item-${it.key}`}>
              {it.complete ? (
                <CheckCircle size={13} weight="fill" className="text-emerald-500 mt-0.5 shrink-0" />
              ) : (
                <Warning size={13} weight="fill" className="text-red-500 mt-0.5 shrink-0" />
              )}
              <span className="min-w-0">
                <span className="text-slate-900 font-medium">{it.label}</span>
                <div className="text-[10px] text-slate-500 truncate">{it.status} · {it.reason}</div>
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="pt-2 border-t border-slate-100 mt-2 flex items-center gap-2 flex-wrap">
        <Link
          to={`/drivers/${driverId}/activation`}
          data-testid="activation-open-checklist"
          className="text-[11px] px-2 py-1 rounded bg-slate-900 text-white hover:bg-slate-800 inline-flex items-center gap-1"
        >Open checklist <CaretRight size={10} /></Link>
        <button
          onClick={refreshCanonical}
          data-testid="activation-recalc"
          disabled={busy}
          className="text-[11px] px-2 py-1 rounded border border-slate-200 text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-50"
        ><ArrowsClockwise size={11} /> Refresh</button>
        {canActivate && !activated && (
          <button
            onClick={activate}
            data-testid="activation-activate"
            disabled={busy || readiness !== "Ready"}
            className="text-[11px] px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700 inline-flex items-center gap-1 disabled:opacity-40"
          ><ShieldCheck size={11} weight="bold" /> Activate</button>
        )}
        {canActivate && activated && (
          <button
            onClick={deactivate}
            data-testid="activation-deactivate"
            disabled={busy}
            className="text-[11px] px-2 py-1 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-40"
          >Deactivate</button>
        )}
      </div>
    </ManagementCard>
  );
}

function MiniCounter({ label, value, tone = "neutral", testid }) {
  const cls = tone === "warn" ? "text-amber-700 border-amber-200 bg-amber-50"
    : tone === "ok" ? "text-emerald-700 border-emerald-200 bg-emerald-50"
    : "text-slate-700 border-slate-200 bg-slate-50";
  return (
    <div data-testid={testid} className={`rounded border ${cls} px-1.5 py-1`}>
      <div className="uppercase tracking-[0.15em] opacity-80">{label}</div>
      <div className="text-sm font-semibold">{value ?? 0}</div>
    </div>
  );
}
