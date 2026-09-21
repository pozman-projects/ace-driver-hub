import React, { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ROLE_CAN_EDIT_SETUP, ManagementCard, InlineField, EditInput, ToggleRow, StatusPill } from "./driverCCUtils";

const TRACKED_LABELS = {
  owner_report_email_override: "Owner report override",
  driver_report_email_override: "Driver report override",
  send_daily_report_owner: "Daily to Owner",
  send_daily_report_driver: "Daily to Driver",
  display_on_dispatch: "Display on Dispatch",
};
function _fmt(v) {
  if (v === true) return "On";
  if (v === false) return "Off";
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

export default function CommunicationCard({ data, role, driverId, onSaved }) {
  const canEdit = ROLE_CAN_EDIT_SETUP.has(role);
  const prefs = data.communication_preferences;
  const driverEmail = data.driver?.email;
  const ownerEmail = data.owner?.contact_email || data.owner?.email;
  const otherDrivers = data.other_drivers_for_owner || [];
  const history = data.communication_history || [];
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});

  const startEdit = () => {
    const f = {
      owner_report_email_override: prefs?.owner_report_email_override || "",
      driver_report_email_override: prefs?.driver_report_email_override || "",
      send_daily_report_owner: !!prefs?.send_daily_report_owner,
      send_daily_report_driver: !!prefs?.send_daily_report_driver,
      display_on_dispatch: prefs ? !!prefs.display_on_dispatch : true,
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/drivers/${driverId}/communication-preferences`, form);
      toast.success("Communication preferences saved (delivery is simulated)");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  return (
    <ManagementCard
      testid="card-communication"
      section="communication"
      title="Communication & Integration"
      subtitle="Report delivery preferences"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
      footer={<span data-testid="comm-simulated-footer">Delivery is <strong>simulated only</strong>. Canonical emails remain source of truth.</span>}
    >
      {editing ? (
        <>
          <EditInput label="Owner report override" type="email" value={form.owner_report_email_override} onChange={(v) => setForm({ ...form, owner_report_email_override: v })} testid="edit-owner-report-email" />
          <EditInput label="Driver report override" type="email" value={form.driver_report_email_override} onChange={(v) => setForm({ ...form, driver_report_email_override: v })} testid="edit-driver-report-email" />
          <ToggleRow label="Daily report to Owner" value={form.send_daily_report_owner} onChange={(v) => setForm({ ...form, send_daily_report_owner: v })} testid="edit-toggle-owner-daily" />
          <ToggleRow label="Daily report to Driver" value={form.send_daily_report_driver} onChange={(v) => setForm({ ...form, send_daily_report_driver: v })} testid="edit-toggle-driver-daily" />
          <ToggleRow label="Display on Dispatch" value={form.display_on_dispatch} onChange={(v) => setForm({ ...form, display_on_dispatch: v })} testid="edit-toggle-display-dispatch" />
        </>
      ) : (
        <>
          <InlineField label="Owner email" value={ownerEmail || null} testid="field-owner-email" />
          <InlineField label="Owner report" value={prefs?.owner_report_email_override ? <span><em className="text-amber-700">override</em> {prefs.owner_report_email_override}</span> : (ownerEmail || null)} testid="field-owner-report" />
          <InlineField label="Driver email" value={driverEmail || null} testid="field-driver-email" />
          <InlineField label="Driver report" value={prefs?.driver_report_email_override ? <span><em className="text-amber-700">override</em> {prefs.driver_report_email_override}</span> : (driverEmail || null)} testid="field-driver-report" />
          <InlineField label="Daily owner" value={prefs?.send_daily_report_owner ? "On" : "Off"} testid="field-daily-owner" />
          <InlineField label="Daily driver" value={prefs?.send_daily_report_driver ? "On" : "Off"} testid="field-daily-driver" />
          <InlineField label="On dispatch" value={prefs?.display_on_dispatch === false ? "Hidden" : "Visible"} testid="field-display-dispatch" />

          {/* FA-02 · Other Drivers for this Owner (visibility only) */}
          <div className="pt-2 mt-2 border-t border-slate-100" data-testid="comm-other-drivers">
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-1">
              Other Drivers for this Owner
            </div>
            {otherDrivers.length === 0 ? (
              <div data-testid="comm-other-drivers-empty" className="text-[11px] italic text-slate-400">
                No other current Drivers for this Owner
              </div>
            ) : (
              <ul className="space-y-1" data-testid="comm-other-drivers-list">
                {otherDrivers.slice(0, 8).map((p) => (
                  <li key={p.id} className="flex items-center gap-2 text-[11px]"
                      data-testid={`comm-other-driver-${p.id}`}>
                    {p.dispatch_number && (
                      <span className="font-mono text-slate-500 tabular-nums shrink-0">
                        {p.dispatch_number}
                      </span>
                    )}
                    {p.driver_code && (
                      <span className="text-slate-500 shrink-0">{p.driver_code}</span>
                    )}
                    <Link to={`/drivers/${p.id}`}
                          className="text-cyan-700 hover:underline truncate flex-1"
                          data-testid={`comm-other-driver-link-${p.id}`}>
                      {p.full_name || "(unnamed)"}
                    </Link>
                    <StatusPill status={p.driver_status} compact testid={`comm-other-driver-status-${p.id}`} />
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* FA-02 · Recent preference change history (append-only) */}
          <div className="pt-2 mt-2 border-t border-slate-100" data-testid="comm-history">
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 mb-1">
              Recent changes
            </div>
            {history.length === 0 ? (
              <div data-testid="comm-history-empty" className="text-[11px] italic text-slate-400">
                No communication preference changes recorded
              </div>
            ) : (
              <ul className="space-y-1" data-testid="comm-history-list">
                {history.slice(0, 5).map((ev) => (
                  <li key={ev.id} className="text-[11px] text-slate-700"
                      data-testid={`comm-history-${ev.id}`}>
                    <div className="flex items-center gap-1 text-[10px] text-slate-500">
                      <span>{ev.changed_at ? new Date(ev.changed_at).toLocaleDateString() : "—"}</span>
                      <span>·</span>
                      <span className="truncate">{ev.changed_by || "system"}</span>
                    </div>
                    <div className="text-slate-700">
                      {(ev.changed_fields || []).map((f) => (
                        <span key={f} className="inline-block mr-2">
                          <span className="font-medium">{TRACKED_LABELS[f] || f}</span>
                          <span className="text-slate-500">
                            : {_fmt(ev.before?.[f])} → {_fmt(ev.after?.[f])}
                          </span>
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </ManagementCard>
  );
}
