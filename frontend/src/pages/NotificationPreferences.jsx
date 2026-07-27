import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import { EVENT_TYPES, CHANNELS, SEVERITIES, DIGEST_MODES } from "../lib/notifications";
import { ArrowClockwise, Plus } from "@phosphor-icons/react";

/**
 * EB-07b — Notification Preferences.
 *
 * Ordinary users cannot fully disable Critical alerts — enforced by the
 * backend and reflected here with a warning.
 */
export default function NotificationPreferences() {
  const [prefs, setPrefs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newPref, setNewPref] = useState({
    event_type: EVENT_TYPES[0], channel: "In App",
    is_enabled: true, minimum_severity: "Information",
    digest_mode: "Immediate",
  });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/notification-preferences/me");
      setPrefs(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const upsert = async (payload) => {
    setSaving(true);
    try {
      await api.put("/notification-preferences/me", payload);
      toast.success("Preference saved");
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setSaving(false); }
  };

  return (
    <section className="space-y-5" data-testid="notification-preferences">
      <div className="bg-blue-50 border border-blue-200 text-blue-800 text-xs rounded-lg px-4 py-3 leading-relaxed">
        <strong>Development mode:</strong> Email and SMS deliveries are simulated —
        no external message is sent. Digest sending is not yet active.
        <br />
        Critical alerts cannot be completely disabled by ordinary users.
      </div>

      <div className="bg-white border border-slate-200 rounded-xl shadow-sm">
        <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">
            My preferences
          </div>
          <button onClick={refresh} data-testid="prefs-refresh" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
            <ArrowClockwise size={12} /> Refresh
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Existing prefs table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {["Event", "Channel", "Enabled", "Min severity", "Digest", ""].map((h) => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400 text-sm">Loading…</td></tr>}
                {!loading && prefs.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-500 text-sm">No preferences yet — using system defaults.</td></tr>}
                {!loading && prefs.map((p) => (
                  <tr key={p.notification_preference_id} data-testid={`pref-row-${p.notification_preference_id}`} className="border-b border-slate-100 last:border-0">
                    <td className="px-3 py-2 text-xs text-slate-800">{p.event_type}</td>
                    <td className="px-3 py-2 text-xs text-slate-700">{p.channel}</td>
                    <td className="px-3 py-2 text-xs">
                      <input type="checkbox" checked={!!p.is_enabled}
                        data-testid={`pref-enabled-${p.notification_preference_id}`}
                        onChange={() => upsert({ ...p, is_enabled: !p.is_enabled })} />
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-700">{p.minimum_severity}</td>
                    <td className="px-3 py-2 text-xs text-slate-700">{p.digest_mode}</td>
                    <td className="px-3 py-2 text-right">
                      <button onClick={() => setNewPref(p)}
                        data-testid={`pref-edit-${p.notification_preference_id}`}
                        className="text-xs text-slate-500 hover:text-slate-900">Edit</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="border-t border-slate-100 pt-4">
            <div className="text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">Add or update a preference</div>
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-2">
              <select value={newPref.event_type} onChange={(e) => setNewPref((p) => ({ ...p, event_type: e.target.value }))}
                data-testid="pref-new-event" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs bg-white">
                {EVENT_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
              <select value={newPref.channel} onChange={(e) => setNewPref((p) => ({ ...p, channel: e.target.value }))}
                data-testid="pref-new-channel" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs bg-white">
                {CHANNELS.map((c) => <option key={c}>{c}</option>)}
              </select>
              <select value={newPref.minimum_severity} onChange={(e) => setNewPref((p) => ({ ...p, minimum_severity: e.target.value }))}
                data-testid="pref-new-min-severity" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs bg-white">
                {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
              </select>
              <select value={newPref.digest_mode} onChange={(e) => setNewPref((p) => ({ ...p, digest_mode: e.target.value }))}
                data-testid="pref-new-digest" className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs bg-white">
                {DIGEST_MODES.map((m) => <option key={m}>{m}</option>)}
              </select>
              <label className="inline-flex items-center gap-2 text-xs">
                <input type="checkbox" checked={newPref.is_enabled}
                  data-testid="pref-new-enabled"
                  onChange={(e) => setNewPref((p) => ({ ...p, is_enabled: e.target.checked }))} />
                Enabled
              </label>
            </div>
            <div className="mt-3 flex justify-end">
              <button
                data-testid="pref-save"
                disabled={saving}
                onClick={() => upsert(newPref)}
                className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-1.5 text-xs font-medium disabled:opacity-40"
              >
                <Plus size={12} weight="bold" /> Save preference
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
