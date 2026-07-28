import React, { useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ROLE_CAN_EDIT, ManagementCard, InlineField, EditInput, ToggleRow } from "./driverCCUtils";

export default function CommunicationCard({ data, role, driverId, onSaved }) {
  const canEdit = ROLE_CAN_EDIT.has(role);
  const prefs = data.communication_preferences;
  const driverEmail = data.driver?.email;
  const ownerEmail = data.owner?.contact_email || data.owner?.email;
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
      footer={<span>Delivery is <strong>simulated only</strong>. Canonical emails remain source of truth.</span>}
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
        </>
      )}
    </ManagementCard>
  );
}
