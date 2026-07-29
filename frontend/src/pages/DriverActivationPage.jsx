/**
 * EB-10 · Full Activation Checklist page — /drivers/:driverId/activation
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { StatusPill } from "../components/driver-cc/driverCCUtils";
import {
  ArrowsClockwise, ShieldCheck, CheckCircle, Warning, X, Clock,
  CaretLeft, PencilSimple, ArrowClockwise,
} from "@phosphor-icons/react";

const FILTERS = ["All", "Outstanding", "Mandatory", "Automatic", "Manual", "Overridden", "Blocked", "Complete"];

export default function DriverActivationPage() {
  const { driverId } = useParams();
  const { user } = useAuth();
  const role = user?.role || "ReadOnly";
  const canActivate = ["Admin", "Manager"].includes(role);
  const canApproveOverride = ["Admin", "Manager"].includes(role);
  const canRequestOverride = ["Admin", "Manager", "Allocator", "Compliance"].includes(role);
  const canManual = role !== "ReadOnly";

  const [data, setData] = useState(null);
  const [driver, setDriver] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("All");
  const [overrideItem, setOverrideItem] = useState(null);
  const [manualItem, setManualItem] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [{ data: act }, { data: drv }] = await Promise.all([
        api.get(`/drivers/${driverId}/activation`),
        api.get(`/drivers/${driverId}`),
      ]);
      setData(act);
      setDriver(drv);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Load failed");
    } finally { setLoading(false); }
  }, [driverId]);

  useEffect(() => { refresh(); }, [refresh]);

  const rec = data?.record;
  const items = data?.items || [];
  const overrides = data?.overrides || [];
  const readiness = rec?.readiness_status || "Not Assessed";

  const filtered = useMemo(() => {
    const f = filter;
    return items.filter((it) => {
      if (f === "All") return true;
      if (f === "Outstanding") return it.applicable && it.completion_status !== "Complete" && it.completion_status !== "Not Applicable" && it.completion_status !== "Override Active";
      if (f === "Mandatory") return it.mandatory && it.applicable;
      if (f === "Automatic") return ["Automatic", "Conditional Automatic"].includes(it.completion_type);
      if (f === "Manual") return ["Manual", "Conditional Manual"].includes(it.completion_type);
      if (f === "Overridden") return it.completion_status === "Override Active";
      if (f === "Blocked") return it.completion_status === "Blocked";
      if (f === "Complete") return it.completion_status === "Complete";
      return true;
    });
  }, [items, filter]);

  const grouped = useMemo(() => {
    const g = {};
    for (const it of filtered) (g[it.category] ??= []).push(it);
    return g;
  }, [filtered]);

  const start = async () => {
    setBusy(true);
    try {
      await api.post(`/drivers/${driverId}/activation/start`);
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Start failed");
    } finally { setBusy(false); }
  };
  const recalc = async () => {
    setBusy(true);
    try {
      await api.post(`/drivers/${driverId}/activation/recalculate`);
      await refresh();
      toast.success("Recalculated");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed");
    } finally { setBusy(false); }
  };
  const activate = async () => {
    if (!window.confirm(`Activate driver?\n\nReadiness: ${readiness}\nOverrides active: ${rec?.override_count || 0}\nOutstanding optional items may remain.\n\nThis sets Driver Status to Active.`)) return;
    setBusy(true);
    try {
      await api.post(`/drivers/${driverId}/activation/activate`, { reason: "Activated from checklist page", set_driver_status_active: true });
      await refresh();
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
      await api.post(`/drivers/${driverId}/activation/deactivate`, { reason });
      await refresh();
      toast.success("Driver deactivated");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Deactivate failed");
    } finally { setBusy(false); }
  };
  const reactivate = async () => {
    setBusy(true);
    try {
      await api.post(`/drivers/${driverId}/activation/reactivate`, { reason: "Reactivated" });
      await refresh();
      toast.success("Driver reactivated");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Reactivate failed");
    } finally { setBusy(false); }
  };

  const manualComplete = async (it, note) => {
    try {
      await api.put(`/driver-activation-items/${it.driver_activation_item_id}/manual-complete`, { manual_note: note });
      toast.success("Item completed");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed");
    }
  };
  const manualReopen = async (it) => {
    try {
      await api.put(`/driver-activation-items/${it.driver_activation_item_id}/manual-reopen`);
      toast.success("Item reopened");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed");
    }
  };
  const approveOverride = async (ovrId) => {
    try {
      await api.post(`/activation-overrides/${ovrId}/approve`);
      toast.success("Override approved");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Approve failed");
    }
  };
  const rejectOverride = async (ovrId) => {
    try {
      await api.post(`/activation-overrides/${ovrId}/reject`);
      toast.success("Override rejected");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Reject failed");
    }
  };
  const revokeOverride = async (ovrId) => {
    if (!window.confirm("Revoke this active override?")) return;
    try {
      await api.post(`/activation-overrides/${ovrId}/revoke`);
      toast.success("Override revoked");
      await refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Revoke failed");
    }
  };

  if (loading) return <FullPageLoader />;

  if (!rec) {
    return (
      <div className="min-h-screen bg-slate-50">
        <AppHeader showBack />
        <div className="max-w-4xl mx-auto p-8" data-testid="activation-empty">
          <h1 className="text-2xl font-semibold text-slate-900 mb-2">Activation not started</h1>
          <p className="text-slate-600 mb-4">This driver does not yet have an activation record.</p>
          <button data-testid="activation-start" onClick={start} disabled={busy} className="px-4 py-2 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50">
            Start Activation
          </button>
        </div>
      </div>
    );
  }

  const activated = rec.status === "Activated";
  const deactivated = rec.status === "Deactivated";
  const pendingOverrides = overrides.filter((o) => o.status === "Requested");
  const activeOverrides = overrides.filter((o) => ["Active", "Approved"].includes(o.status));

  return (
    <div className="min-h-screen bg-slate-50" data-testid="driver-activation-page">
      <AppHeader showBack />
      <main className="w-full mx-auto px-4 lg:px-8 py-6" style={{ maxWidth: 1920 }}>
        {/* Header */}
        <section className="mb-6 bg-white border border-slate-200 rounded-xl p-5 flex flex-wrap items-start justify-between gap-4" data-testid="activation-header">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-1">
              <Link to={`/drivers/${driverId}`} className="hover:text-slate-900 inline-flex items-center gap-1"><CaretLeft size={10} /> Back to profile</Link>
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold text-slate-900" data-testid="activation-driver-name">
              {driver?.full_name} <span className="text-slate-400 font-normal text-lg">· {driver?.driver_code}</span>
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <StatusPill status={readiness} testid="activation-readiness-pill" />
              <span className="text-xs text-slate-600" data-testid="activation-counters">
                {rec.completed_item_count}/{rec.applicable_item_count} items · {rec.mandatory_completed_count}/{rec.mandatory_item_count} mandatory
              </span>
              <span className="text-xs text-slate-600" data-testid="activation-overrides-count">
                {activeOverrides.length} active override{activeOverrides.length === 1 ? "" : "s"}
              </span>
              {rec.last_calculated_at && (
                <span className="text-[10px] text-slate-400 flex items-center gap-1"><Clock size={10} /> {new Date(rec.last_calculated_at).toLocaleString()}</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={recalc} disabled={busy} data-testid="activation-recalc-btn" className="text-xs px-3 py-1.5 rounded border border-slate-200 text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-50">
              <ArrowsClockwise size={13} /> Recalculate
            </button>
            {canActivate && !activated && !deactivated && (
              <button onClick={activate} disabled={busy || !["Ready", "Ready with Override"].includes(readiness)} data-testid="activation-activate-btn"
                className="text-xs px-3 py-1.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 inline-flex items-center gap-1 disabled:opacity-40">
                <ShieldCheck size={13} weight="bold" /> Activate Driver
              </button>
            )}
            {canActivate && activated && (
              <button onClick={deactivate} disabled={busy} data-testid="activation-deactivate-btn" className="text-xs px-3 py-1.5 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-40">
                Deactivate
              </button>
            )}
            {canActivate && deactivated && (
              <button onClick={reactivate} disabled={busy} data-testid="activation-reactivate-btn" className="text-xs px-3 py-1.5 rounded bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-40 inline-flex items-center gap-1">
                <ArrowClockwise size={13} /> Reactivate
              </button>
            )}
          </div>
        </section>

        {/* Pending override queue */}
        {pendingOverrides.length > 0 && (
          <section className="mb-6" data-testid="pending-overrides-section">
            <h2 className="text-sm font-semibold text-slate-800 mb-2">Pending override requests</h2>
            <ul className="space-y-2">
              {pendingOverrides.map((o) => (
                <li key={o.activation_override_id} className="bg-amber-50 border border-amber-200 rounded p-3 text-sm flex flex-wrap items-center justify-between gap-2"
                    data-testid={`pending-override-${o.activation_override_id}`}>
                  <div className="min-w-0">
                    <div className="font-medium text-amber-900">{o.reason}</div>
                    <div className="text-[10px] uppercase tracking-[0.15em] text-amber-700 mt-0.5">
                      Requested by {o.requested_by} · Expires {new Date(o.expires_at).toLocaleDateString()}
                    </div>
                  </div>
                  {canApproveOverride && (
                    <div className="flex items-center gap-2">
                      <button data-testid={`override-approve-${o.activation_override_id}`} onClick={() => approveOverride(o.activation_override_id)} className="text-[11px] px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700">Approve</button>
                      <button data-testid={`override-reject-${o.activation_override_id}`} onClick={() => rejectOverride(o.activation_override_id)} className="text-[11px] px-2 py-1 rounded bg-slate-800 text-white hover:bg-slate-900">Reject</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-1.5" data-testid="activation-filters">
          {FILTERS.map((f) => (
            <button key={f} onClick={() => setFilter(f)} data-testid={`filter-${f.toLowerCase()}`}
              className={`text-[11px] px-2.5 py-1 rounded-full border ${filter === f ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
              {f}
            </button>
          ))}
        </div>

        {/* Grouped items */}
        <div className="space-y-4">
          {Object.entries(grouped).map(([cat, list]) => (
            <div key={cat} className="bg-white border border-slate-200 rounded-xl" data-testid={`category-${cat.replace(/\s+/g, '-').toLowerCase()}`}>
              <div className="px-4 py-2 border-b border-slate-100 text-[10px] uppercase tracking-[0.22em] text-slate-500">{cat} · {list.length}</div>
              <ul>
                {list.map((it) => (
                  <ItemRow
                    key={it.driver_activation_item_id}
                    it={it}
                    canManual={canManual}
                    canRequestOverride={canRequestOverride}
                    activeOverride={activeOverrides.find((o) => o.driver_activation_item_id === it.driver_activation_item_id)}
                    onManualComplete={() => setManualItem(it)}
                    onManualReopen={() => manualReopen(it)}
                    onOverrideRequest={() => setOverrideItem(it)}
                    onOverrideRevoke={(ovrId) => revokeOverride(ovrId)}
                  />
                ))}
              </ul>
            </div>
          ))}
          {filtered.length === 0 && (
            <div data-testid="items-empty" className="text-sm text-slate-500 italic text-center py-8">No items match this filter.</div>
          )}
        </div>
      </main>

      {overrideItem && (
        <OverrideDialog
          item={overrideItem}
          onClose={() => setOverrideItem(null)}
          onSubmit={async (payload) => {
            try {
              await api.post(`/driver-activation-items/${overrideItem.driver_activation_item_id}/override-request`, payload);
              toast.success("Override requested");
              setOverrideItem(null);
              await refresh();
            } catch (e) {
              toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed");
            }
          }}
        />
      )}
      {manualItem && (
        <ManualCompleteDialog
          item={manualItem}
          onClose={() => setManualItem(null)}
          onSubmit={async (note) => {
            await manualComplete(manualItem, note);
            setManualItem(null);
          }}
        />
      )}
    </div>
  );
}

function ItemRow({ it, canManual, canRequestOverride, activeOverride, onManualComplete, onManualReopen, onOverrideRequest, onOverrideRevoke }) {
  const isManual = ["Manual", "Conditional Manual"].includes(it.completion_type);
  const complete = it.completion_status === "Complete" || it.completion_status === "Override Active";
  const blocked = it.completion_status === "Blocked";
  const overridden = it.completion_status === "Override Active";

  return (
    <li className="px-4 py-2.5 border-t border-slate-100 flex items-start gap-3 flex-wrap" data-testid={`row-${it.item_key}`}>
      <div className="mt-0.5 shrink-0">
        {complete ? <CheckCircle size={16} weight="fill" className="text-emerald-500" />
          : blocked ? <X size={16} weight="fill" className="text-red-500" />
          : <Warning size={16} weight="fill" className={it.mandatory ? "text-red-500" : "text-amber-500"} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center flex-wrap gap-1.5">
          <span className="text-sm font-medium text-slate-900">{it.label_snapshot}</span>
          {it.mandatory && <span className="text-[9px] uppercase tracking-[0.15em] border border-red-200 bg-red-50 text-red-700 rounded-full px-1.5">Mandatory</span>}
          {!it.mandatory && <span className="text-[9px] uppercase tracking-[0.15em] border border-slate-200 bg-slate-50 text-slate-500 rounded-full px-1.5">Optional</span>}
          <span className="text-[9px] uppercase tracking-[0.15em] border border-slate-200 bg-slate-50 text-slate-600 rounded-full px-1.5">{isManual ? "Manual" : "Automatic"}</span>
          {it.evidence_required && <span className="text-[9px] uppercase tracking-[0.15em] border border-blue-200 bg-blue-50 text-blue-700 rounded-full px-1.5">Evidence</span>}
          {overridden && activeOverride && (
            <span className="text-[9px] uppercase tracking-[0.15em] border border-amber-300 bg-amber-100 text-amber-800 rounded-full px-1.5">
              Override until {new Date(activeOverride.expires_at).toLocaleDateString()}
            </span>
          )}
        </div>
        <div className="text-[11px] text-slate-500 mt-0.5">{it.source_explanation || "—"}</div>
        {it.last_checked_at && <div className="text-[10px] text-slate-400 mt-0.5">Last checked {new Date(it.last_checked_at).toLocaleString()}</div>}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <StatusPill status={it.completion_status} compact testid={`status-${it.item_key}`} />
        {isManual && it.applicable && canManual && !complete && (
          <button data-testid={`complete-${it.item_key}`} onClick={onManualComplete} className="text-[11px] px-2 py-1 rounded bg-slate-900 text-white hover:bg-slate-800">Complete</button>
        )}
        {isManual && it.applicable && canManual && complete && (
          <button data-testid={`reopen-${it.item_key}`} onClick={onManualReopen} className="text-[11px] px-2 py-1 rounded border border-slate-200 text-slate-700 hover:bg-slate-50">Reopen</button>
        )}
        {!blocked && it.applicable && canRequestOverride && it.override_allowed && !overridden && !complete && (
          <button data-testid={`override-${it.item_key}`} onClick={onOverrideRequest} className="text-[11px] px-2 py-1 rounded border border-amber-200 text-amber-700 hover:bg-amber-50">Request override</button>
        )}
        {overridden && activeOverride && canRequestOverride && (
          <button data-testid={`revoke-${it.item_key}`} onClick={() => onOverrideRevoke(activeOverride.activation_override_id)} className="text-[11px] px-2 py-1 rounded border border-red-200 text-red-700 hover:bg-red-50">Revoke</button>
        )}
      </div>
    </li>
  );
}

function OverrideDialog({ item, onClose, onSubmit }) {
  const maxDays = item.override_max_days || 30;
  const [reason, setReason] = useState("");
  const [days, setDays] = useState(Math.min(7, maxDays));
  const [ack, setAck] = useState(false);
  const [saving, setSaving] = useState(false);
  return (
    <div className="fixed inset-0 bg-black/40 grid place-items-center z-50" data-testid="override-dialog">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-5">
        <h3 className="text-base font-semibold text-slate-900 mb-1">Request override</h3>
        <p className="text-xs text-slate-500 mb-3">{item.label_snapshot}</p>
        <label className="block mb-2">
          <span className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Reason (min 6 chars)</span>
          <textarea data-testid="override-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm h-20 mt-1" />
        </label>
        <label className="block mb-2">
          <span className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Expiry days (max {maxDays})</span>
          <input data-testid="override-days" type="number" min="1" max={maxDays} value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm mt-1" />
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-700 mb-3">
          <input data-testid="override-ack" type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          I acknowledge the operational risk of this override.
        </label>
        <div className="flex items-center justify-end gap-2">
          <button data-testid="override-cancel" onClick={onClose} className="text-[11px] px-3 py-1.5 rounded text-slate-600 hover:text-slate-900">Cancel</button>
          <button
            data-testid="override-submit"
            disabled={saving || reason.length < 6 || !ack || days < 1 || days > maxDays}
            onClick={async () => { setSaving(true); try { await onSubmit({ reason, risk_acknowledgement: ack, requested_expiry_days: days }); } finally { setSaving(false); } }}
            className="text-[11px] px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40"
          >Request</button>
        </div>
      </div>
    </div>
  );
}

function ManualCompleteDialog({ item, onClose, onSubmit }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <div className="fixed inset-0 bg-black/40 grid place-items-center z-50" data-testid="manual-complete-dialog">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-5">
        <h3 className="text-base font-semibold text-slate-900 mb-1">Complete manual item</h3>
        <p className="text-xs text-slate-500 mb-3">{item.label_snapshot}</p>
        <label className="block mb-3">
          <span className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Note (optional)</span>
          <textarea data-testid="manual-note" value={note} onChange={(e) => setNote(e.target.value)} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm h-20 mt-1" />
        </label>
        <div className="flex items-center justify-end gap-2">
          <button data-testid="manual-cancel" onClick={onClose} className="text-[11px] px-3 py-1.5 rounded text-slate-600 hover:text-slate-900">Cancel</button>
          <button data-testid="manual-submit" disabled={saving} onClick={async () => { setSaving(true); try { await onSubmit(note); } finally { setSaving(false); } }}
            className="text-[11px] px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40">Complete</button>
        </div>
      </div>
    </div>
  );
}

function FullPageLoader() {
  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <div className="max-w-5xl mx-auto p-8 space-y-3">
        {[1,2,3,4,5,6,7].map((i) => (
          <div key={i} className="h-14 bg-white rounded-xl border border-slate-200 animate-pulse" />
        ))}
      </div>
    </div>
  );
}
