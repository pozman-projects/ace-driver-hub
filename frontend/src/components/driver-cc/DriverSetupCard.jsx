import React, { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CaretRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ROLE_CAN_EDIT, ManagementCard, InlineField, EditInput } from "./driverCCUtils";

export default function DriverSetupCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const canEdit = ROLE_CAN_EDIT.has(role);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});

  const startEdit = () => {
    const f = {
      start_date: d.start_date || "",
      driver_status: d.driver_status || "Active",
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
      toast.success("Driver setup saved");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally { setSaving(false); }
  };

  const contract = data.documents?.driver_contract;
  const allocSource = (data.allocation_events || []).find((e) => e.identifier_type === "Driver Code");
  const src = allocSource
    ? (allocSource.automatic ? "Automatic" : allocSource.manual_override ? "Manual override" : "System")
    : "—";

  return (
    <ManagementCard
      testid="card-driver-setup"
      section="driver-setup"
      title="Driver Setup"
      subtitle="Identifiers, status, contract"
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
          <EditInput label="Start Date" type="date" value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} testid="edit-start-date" />
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">Status</div>
            <select
              value={form.driver_status}
              onChange={(e) => setForm({ ...form, driver_status: e.target.value })}
              data-testid="edit-driver-status"
              className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm"
            >
              {["Active", "Inactive", "On Leave", "Archived"].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </>
      ) : (
        <>
          <InlineField label="Driver Code" value={d.driver_code} testid="field-driver-code" mono />
          <InlineField label="Dispatch #" value={d.dispatch_number} testid="field-dispatch-number" mono />
          <InlineField label="Start Date" value={d.start_date} testid="field-start-date" />
          <InlineField label="Status" value={d.driver_status} testid="field-driver-status" />
          <InlineField label="Allocation" value={src} testid="field-allocation-source" />
          <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Contract</div>
            <div className="text-sm">
              {contract ? (
                <Link
                  to={`/documents?doc=${contract.id}`}
                  data-testid="driver-contract-link"
                  className="text-cyan-700 hover:underline inline-flex items-center gap-1"
                >
                  Open contract <CaretRight size={11} />
                </Link>
              ) : <span data-testid="driver-contract-empty" className="text-slate-300">Not on file</span>}
            </div>
          </div>
          <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
            <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">History</div>
            <Link to="/administration/numbering" data-testid="allocation-history-link" className="text-cyan-700 hover:underline text-sm">
              {(data.allocation_events || []).length} events · Numbering admin
            </Link>
          </div>
        </>
      )}
    </ManagementCard>
  );
}
