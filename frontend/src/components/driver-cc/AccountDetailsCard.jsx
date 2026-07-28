import React, { useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ROLE_CAN_EDIT_ACCOUNT, ManagementCard, InlineField, EditInput } from "./driverCCUtils";

export default function AccountDetailsCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const restricted = (data.restricted_fields || []).length > 0;
  const canEdit = ROLE_CAN_EDIT_ACCOUNT.has(role);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});

  const startEdit = () => {
    const f = {
      business_name: d.business_name || "",
      abn: d.abn || "",
      payroll_number: d.payroll_number || "",
      payment_percentage: d.payment_percentage ?? "",
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { ...form };
      if (payload.payment_percentage === "" || payload.payment_percentage == null) delete payload.payment_percentage;
      else payload.payment_percentage = Number(payload.payment_percentage);
      await api.put(`/drivers/${d.id}`, payload);
      toast.success("Account details saved");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  return (
    <ManagementCard
      testid="card-account-details"
      section="account-details"
      title="Account Details"
      subtitle="Business, ABN, payroll"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
      footer={restricted ? <span data-testid="account-restricted-note">Sensitive financial fields are hidden for your role.</span> : null}
    >
      {restricted && !editing ? (
        <div className="text-xs text-slate-500 italic">Restricted view — sensitive account fields are not returned by the server for your role.</div>
      ) : editing ? (
        <>
          <EditInput label="Business Name" value={form.business_name} onChange={(v) => setForm({ ...form, business_name: v })} testid="edit-business-name" />
          <EditInput label="ABN" value={form.abn} onChange={(v) => setForm({ ...form, abn: v })} testid="edit-abn" />
          <EditInput label="Payroll #" value={form.payroll_number} onChange={(v) => setForm({ ...form, payroll_number: v })} testid="edit-payroll" />
          <EditInput label="Payment %" type="number" value={form.payment_percentage} onChange={(v) => setForm({ ...form, payment_percentage: v })} testid="edit-payment-pct" />
        </>
      ) : (
        <>
          <InlineField label="Business" value={d.business_name} testid="field-business-name" />
          <InlineField label="ABN" value={d.abn} testid="field-abn" mono />
          <InlineField label="Payroll #" value={d.payroll_number} testid="field-payroll" mono />
          <InlineField label="Payment %" value={d.payment_percentage != null ? `${d.payment_percentage}%` : null} testid="field-payment-pct" />
        </>
      )}
    </ManagementCard>
  );
}
