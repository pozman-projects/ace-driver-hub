import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Warning, CheckCircle, ArrowsClockwise, CaretRight, ShieldCheck } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ManagementCard, StatusPill } from "./driverCCUtils";
import { useAuth } from "../../context/AuthContext";

/**
 * EB-10 upgrade of the Activation card.
 *
 * Fully backwards-compatible with EB-09 test-ids:
 *   card-activation, activation-readiness, activation-progress, activation-item-<key>
 *
 * New in EB-10 (backend-driven, no faked completion):
 *   activation-recalc, activation-open-checklist, activation-activate,
 *   activation-deactivate, activation-override-count
 */
export default function ActivationChecklistCard({ data }) {
  const { user } = useAuth();
  const driverId = data?.driver?.id;
  const canActivate = ["Admin", "Manager"].includes(user?.role);
  const [act, setAct] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!driverId) return;
    try {
      const { data: d } = await api.get(`/drivers/${driverId}/activation`);
      setAct(d);
    } catch {
      // fall back to the aggregator's summary if activation record cannot load
    }
  }, [driverId]);

  useEffect(() => { load(); }, [load]);

  const rec = act?.record;
  const readiness = rec?.readiness_status || data?.activation?.readiness || "Not Assessed";
  const applicable = rec?.applicable_item_count ?? data?.activation?.total_items ?? 0;
  const completed = rec?.completed_item_count ?? data?.activation?.completed_items ?? 0;
  const mandatoryTotal = rec?.mandatory_item_count ?? data?.activation?.mandatory_total ?? 0;
  const mandatoryDone = rec?.mandatory_completed_count ?? data?.activation?.mandatory_done ?? 0;
  const outstanding = rec?.outstanding_mandatory_count ?? (data?.activation?.mandatory_missing_items?.length ?? 0);
  const overrides = rec?.override_count ?? 0;
  const lastCalc = rec?.last_calculated_at;
  const pct = mandatoryTotal ? Math.round((mandatoryDone / mandatoryTotal) * 100) : 0;
  const variant = ["Ready", "Ready with Override", "Activated"].includes(readiness) ? "ok"
    : readiness === "Blocked" ? "danger" : "warn";

  const recalc = async () => {
    setBusy(true);
    try {
      const { data: d } = await api.post(`/drivers/${driverId}/activation/recalculate`);
      setAct(d);
      toast.success("Recalculated");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Recalculate failed");
    } finally { setBusy(false); }
  };

  const activate = async () => {
    if (!window.confirm(`Activate this driver?\n\nReadiness: ${readiness}\nOverrides active: ${overrides}\nOutstanding optional items may remain.\n\nThis sets Driver Status to Active.`)) return;
    setBusy(true);
    try {
      const { data: d } = await api.post(`/drivers/${driverId}/activation/activate`,
                                           { reason: "Activated from DCC", set_driver_status_active: true });
      setAct(d);
      toast.success("Driver activated");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Activate failed");
    } finally { setBusy(false); }
  };

  const deactivate = async () => {
    const reason = window.prompt("Deactivate driver. Enter reason:");
    if (!reason || reason.length < 3) return;
    setBusy(true);
    try {
      const { data: d } = await api.post(`/drivers/${driverId}/activation/deactivate`, { reason });
      setAct(d);
      toast.success("Driver deactivated");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Deactivate failed");
    } finally { setBusy(false); }
  };

  const activated = rec?.status === "Activated" || readiness === "Activated";

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
          {mandatoryDone}/{mandatoryTotal} mandatory · {pct}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-slate-100 rounded overflow-hidden mb-2">
        <div className={`h-full ${variant === "ok" ? "bg-emerald-500" : variant === "warn" ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="grid grid-cols-3 gap-2 mb-2 text-center text-[10px]">
        <MiniCounter testid="activation-applicable" label="Applicable" value={applicable} />
        <MiniCounter testid="activation-outstanding" label="Outstanding" value={outstanding} tone={outstanding ? "warn" : "ok"} />
        <MiniCounter testid="activation-override-count" label="Overrides" value={overrides} tone={overrides ? "warn" : "neutral"} />
      </div>
      {(data?.activation?.items || []).length > 0 && (
        <ul className="space-y-1 text-xs max-h-32 overflow-y-auto">
          {(data.activation.items || []).slice(0, 5).map((it) => (
            <li key={it.item_key} className="flex items-start gap-2" data-testid={`activation-item-${it.item_key}`}>
              {it.complete ? (
                <CheckCircle size={13} weight="fill" className="text-emerald-500 mt-0.5 shrink-0" />
              ) : (
                <Warning size={13} weight="fill" className={`${it.mandatory ? "text-red-500" : "text-amber-500"} mt-0.5 shrink-0`} />
              )}
              <span className="min-w-0">
                <span className="text-slate-900 font-medium">{it.label}</span>
                <div className="text-[10px] text-slate-500 truncate">{it.source} · {it.reason}</div>
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
          onClick={recalc}
          data-testid="activation-recalc"
          disabled={busy}
          className="text-[11px] px-2 py-1 rounded border border-slate-200 text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-50"
        ><ArrowsClockwise size={11} /> Recalculate</button>
        {canActivate && !activated && (
          <button
            onClick={activate}
            data-testid="activation-activate"
            disabled={busy || !["Ready", "Ready with Override"].includes(readiness)}
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
      {lastCalc && (
        <div className="text-[10px] text-slate-400 mt-1" data-testid="activation-last-calc">
          Last calculated: {new Date(lastCalc).toLocaleString()}
        </div>
      )}
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
