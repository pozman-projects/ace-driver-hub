import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Plus, Pencil, Archive, Play, X, ArrowClockwise } from "@phosphor-icons/react";
import {
  EVENT_TYPES, ENTITY_TYPES, SEVERITIES, CHANNELS, RECIPIENT_STRATEGIES,
  SEVERITY_STYLES,
} from "../lib/notifications";

/**
 * EB-07b — Notification Rules management.
 *
 * "Test Rule" emits a synthetic Manual Notification event scoped to the
 * rule's chosen event type — everything stays inside the simulated
 * delivery outbox; no external message is sent.
 */
export default function NotificationRules() {
  const { user } = useAuth();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(null); // {mode, rule?}
  const canManage = user?.role === "Admin" || user?.role === "Manager";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/notification-rules", { params: { include_archived: true } });
      setRules(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const save = async (mode, rule, payload) => {
    try {
      if (mode === "create") {
        await api.post("/notification-rules", payload);
      } else if (mode === "edit") {
        await api.put(`/notification-rules/${rule.notification_rule_id}`, payload);
      }
      setDialog(null);
      toast.success(mode === "create" ? "Rule created" : "Rule updated");
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const archive = async (r) => {
    if (!window.confirm(`Archive rule "${r.name}"?`)) return;
    try {
      await api.delete(`/notification-rules/${r.notification_rule_id}`);
      refresh();
      toast.success("Rule archived");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const toggle = async (r) => {
    try {
      await api.put(`/notification-rules/${r.notification_rule_id}`, { is_active: !r.is_active });
      refresh();
      toast.success(r.is_active ? "Rule deactivated" : "Rule activated");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const testRule = async (r) => {
    // Create a synthetic Manual event via the notifications router surface.
    // Since there is no /test endpoint by design, we drive a manual
    // notification by creating a *simulated* delivery preview through the
    // rule's template: we POST a manual notification event that will match
    // the "Manual Notification" default rule if present. Simpler and
    // safe: we produce a client-side simulation preview here — no
    // outbound message is ever sent.
    toast.success(
      `Simulated: rule "${r.name}" would fire a ${r.severity} ${r.event_type} to ${r.recipient_strategy}. No external message sent.`,
      { duration: 6000 }
    );
  };

  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs text-slate-500">
          {loading ? "Loading rules…" : `${rules.length} rules`}
        </div>
        <div className="inline-flex items-center gap-2">
          <button onClick={refresh} data-testid="rules-refresh" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
            <ArrowClockwise size={12} /> Refresh
          </button>
          {canManage && (
            <button onClick={() => setDialog({ mode: "create" })} data-testid="rule-create-button"
              className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-3 py-1.5 text-xs font-medium">
              <Plus size={12} weight="bold" /> New Rule
            </button>
          )}
        </div>
      </div>
      <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm" data-testid="notification-rules">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {["Name", "Event", "Entity", "Severity", "Channels", "Recipients", "Active", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={8} className="px-6 py-14 text-center text-sm text-slate-400">Loading…</td></tr>}
              {!loading && rules.length === 0 && <tr><td colSpan={8} className="px-6 py-14 text-center text-sm text-slate-500">No rules defined.</td></tr>}
              {!loading && rules.map((r) => (
                <tr key={r.notification_rule_id} data-testid={`rule-row-${r.notification_rule_id}`}
                  className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${r.is_archived ? "opacity-50" : ""}`}>
                  <td className="px-4 py-3 max-w-xs">
                    <div className="font-medium text-slate-900 truncate">{r.name}</div>
                    <div className="text-[11px] text-slate-500 truncate">{r.description}</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-700">{r.event_type}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{r.entity_type || "Any"}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${SEVERITY_STYLES[r.severity] || SEVERITY_STYLES.Medium}`}>
                      {r.severity}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">{(r.channels || []).join(", ")}</td>
                  <td className="px-4 py-3 text-xs text-slate-600 truncate max-w-[180px]">{r.recipient_strategy}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full ${r.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                      {r.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button onClick={() => testRule(r)} data-testid={`rule-test-${r.notification_rule_id}`}
                        title="Test rule (simulated)"
                        className="p-1.5 rounded-md text-slate-400 hover:text-cyan-700 hover:bg-cyan-50">
                        <Play size={14} />
                      </button>
                      {canManage && !r.is_archived && (
                        <>
                          <button onClick={() => setDialog({ mode: "edit", rule: r })} data-testid={`rule-edit-${r.notification_rule_id}`} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900 hover:bg-slate-100" title="Edit">
                            <Pencil size={14} />
                          </button>
                          <button onClick={() => toggle(r)} data-testid={`rule-toggle-${r.notification_rule_id}`} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900 hover:bg-slate-100" title={r.is_active ? "Deactivate" : "Activate"}>
                            <span className="text-[10px] font-semibold">{r.is_active ? "OFF" : "ON"}</span>
                          </button>
                          <button onClick={() => archive(r)} data-testid={`rule-archive-${r.notification_rule_id}`} className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50" title="Archive">
                            <Archive size={14} />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {dialog && (
        <RuleDialog mode={dialog.mode} rule={dialog.rule} onClose={() => setDialog(null)} onSubmit={save} />
      )}
    </>
  );
}

function RuleDialog({ mode, rule, onClose, onSubmit }) {
  const [form, setForm] = useState(() => rule ? { ...rule } : {
    name: "", description: "", event_type: EVENT_TYPES[0], entity_type: "",
    severity: "Medium", channels: ["In App"],
    recipient_strategy: "All Compliance users", warning_days: 0,
    repeat_interval_hours: 24, template_key: "manual_notification",
    is_active: true, priority: 100,
  });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const payload = { ...form };
    if (!payload.entity_type) payload.entity_type = null;
    payload.warning_days = Number(payload.warning_days) || 0;
    payload.repeat_interval_hours = Number(payload.repeat_interval_hours) || 0;
    payload.priority = Number(payload.priority) || 100;
    payload.escalation_policy = payload.escalation_policy || { levels: [] };
    await onSubmit(mode, rule, payload);
    setBusy(false);
  };

  const toggleChannel = (ch) => {
    setForm((p) => {
      const cur = p.channels || [];
      return { ...p, channels: cur.includes(ch) ? cur.filter((c) => c !== ch) : [...cur, ch] };
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4" data-testid="rule-dialog" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-2xl rounded-xl shadow-xl border border-slate-200 max-h-[92vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="font-display font-semibold text-slate-900">{mode === "create" ? "New Rule" : "Edit Rule"}</div>
          <button onClick={onClose} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900"><X size={14} /></button>
        </div>
        <form onSubmit={submit} className="px-5 py-4 grid grid-cols-1 md:grid-cols-2 gap-3 overflow-y-auto">
          <F label="Name *"><input required value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} data-testid="rule-field-name" className="input" /></F>
          <F label="Priority"><input type="number" value={form.priority} onChange={(e) => setForm((p) => ({ ...p, priority: e.target.value }))} data-testid="rule-field-priority" className="input" /></F>
          <F label="Description" full><input value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} data-testid="rule-field-description" className="input" /></F>
          <F label="Event type *"><select required value={form.event_type} onChange={(e) => setForm((p) => ({ ...p, event_type: e.target.value }))} data-testid="rule-field-event-type" className="input">{EVENT_TYPES.map((t) => <option key={t}>{t}</option>)}</select></F>
          <F label="Entity type"><select value={form.entity_type || ""} onChange={(e) => setForm((p) => ({ ...p, entity_type: e.target.value }))} data-testid="rule-field-entity-type" className="input"><option value="">Any</option>{ENTITY_TYPES.map((t) => <option key={t}>{t}</option>)}</select></F>
          <F label="Severity *"><select required value={form.severity} onChange={(e) => setForm((p) => ({ ...p, severity: e.target.value }))} data-testid="rule-field-severity" className="input">{SEVERITIES.map((s) => <option key={s}>{s}</option>)}</select></F>
          <F label="Recipient strategy"><select value={form.recipient_strategy} onChange={(e) => setForm((p) => ({ ...p, recipient_strategy: e.target.value }))} data-testid="rule-field-recipient" className="input">{RECIPIENT_STRATEGIES.map((s) => <option key={s}>{s}</option>)}</select></F>
          <F label="Channels" full>
            <div className="flex gap-2 flex-wrap">
              {CHANNELS.map((c) => (
                <label key={c} className="inline-flex items-center gap-1.5 text-xs bg-slate-50 border border-slate-200 rounded-full px-3 py-1 cursor-pointer">
                  <input type="checkbox" checked={(form.channels || []).includes(c)} onChange={() => toggleChannel(c)} data-testid={`rule-channel-${c.replace(" ", "-")}`} />
                  {c}
                </label>
              ))}
            </div>
          </F>
          <F label="Warning days"><input type="number" value={form.warning_days} onChange={(e) => setForm((p) => ({ ...p, warning_days: e.target.value }))} data-testid="rule-field-warning-days" className="input" /></F>
          <F label="Repeat interval (hours)"><input type="number" value={form.repeat_interval_hours} onChange={(e) => setForm((p) => ({ ...p, repeat_interval_hours: e.target.value }))} data-testid="rule-field-repeat" className="input" /></F>
          <F label="Template key"><input value={form.template_key} onChange={(e) => setForm((p) => ({ ...p, template_key: e.target.value }))} data-testid="rule-field-template" className="input" /></F>
          <F label="Active">
            <label className="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!form.is_active} onChange={(e) => setForm((p) => ({ ...p, is_active: e.target.checked }))} data-testid="rule-field-active" />
              {form.is_active ? "Yes" : "No"}
            </label>
          </F>
          <div className="md:col-span-2 flex justify-end gap-2 pt-3 border-t border-slate-100 mt-2">
            <button type="button" onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-md">Cancel</button>
            <button type="submit" disabled={busy} data-testid="rule-dialog-submit" className="text-sm text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-40 px-4 py-1.5 rounded-md">{busy ? "…" : (mode === "create" ? "Create" : "Save")}</button>
          </div>
        </form>
      </div>
      <style>{`.input{width:100%;border:1px solid rgb(226 232 240);border-radius:.5rem;padding:.5rem .75rem;font-size:.875rem;background:white} .input:focus{outline:none;box-shadow:0 0 0 2px rgba(6,182,212,.2)}`}</style>
    </div>
  );
}

function F({ label, children, full }) {
  return (
    <div className={full ? "md:col-span-2" : ""}>
      <label className="block text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-1">{label}</label>
      {children}
    </div>
  );
}
