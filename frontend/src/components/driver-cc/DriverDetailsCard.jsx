import React, { useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ROLE_CAN_EDIT, ManagementCard, InlineField, EditInput } from "./driverCCUtils";

export default function DriverDetailsCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});
  const canEdit = ROLE_CAN_EDIT.has(role);

  const startEdit = () => {
    const f = {
      residential_address: d.residential_address || "",
      mobile_number: d.mobile_number || "",
      email: d.email || "",
      emergency_contact_name: d.emergency_contact_name || "",
      emergency_contact_phone: d.emergency_contact_phone || "",
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/drivers/${d.id}`, form);
      toast.success("Driver details saved");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ManagementCard
      testid="card-driver-details"
      section="driver-details"
      title="Driver Details"
      subtitle="Canonical identity + contact"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
    >
      {editing ? (
        <>
          <EditInput label="Residential Address" value={form.residential_address} onChange={(v) => setForm({ ...form, residential_address: v })} testid="edit-residential-address" />
          <EditInput label="Mobile Number" value={form.mobile_number} onChange={(v) => setForm({ ...form, mobile_number: v })} testid="edit-mobile-number" />
          <EditInput label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="edit-email" />
          <EditInput label="Emergency Name" value={form.emergency_contact_name} onChange={(v) => setForm({ ...form, emergency_contact_name: v })} testid="edit-emergency-name" />
          <EditInput label="Emergency Phone" value={form.emergency_contact_phone} onChange={(v) => setForm({ ...form, emergency_contact_phone: v })} testid="edit-emergency-phone" />
        </>
      ) : (
        <>
          <InlineField label="Address" value={d.residential_address} testid="field-residential-address" />
          <InlineField label="Mobile" value={d.mobile_number ? <a href={`tel:${d.mobile_number}`} className="text-cyan-700 hover:underline">{d.mobile_number}</a> : null} testid="field-mobile" />
          <InlineField label="Email" value={d.email ? <a href={`mailto:${d.email}`} className="text-cyan-700 hover:underline">{d.email}</a> : null} testid="field-email" />
          <InlineField label="Emergency" value={d.emergency_contact_name || null} testid="field-emergency-name" />
          <InlineField label="Emerg. Phone" value={d.emergency_contact_phone || null} testid="field-emergency-phone" />
        </>
      )}
    </ManagementCard>
  );
}
