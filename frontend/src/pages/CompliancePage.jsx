import React, { useEffect, useMemo, useState } from "react";
import { useParams, Navigate, Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import DriverSelect from "../components/app/DriverSelect";
import { COMPLIANCE_TYPES, STATUS_STYLES, STATUS_DOT, expiryDisplayLabel } from "../lib/compliance";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Plus, MagnifyingGlass, X, Archive, PencilSimple, Warning, Paperclip } from "@phosphor-icons/react";
import { toast } from "sonner";

function GenericSelect({ items, value, onChange, required, testid, placeholder, labelFor }) {
  return (
    <select
      required={!!required}
      value={value || ""}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testid}
      className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
    >
      <option value="">{placeholder || "Select…"}</option>
      {items.map((it) => (
        <option key={it.id} value={it.id}>{labelFor(it)}</option>
      ))}
    </select>
  );
}

const labelForDriver = (d) => `${d.full_name || d.name}${d.driver_code ? " · " + d.driver_code : ""}`;
const labelForVehicle = (v) => `${v.registration_number || v.id}${v.make ? " · " + v.make : ""}${v.model ? " " + v.model : ""}`;
const labelForEquipment = (e) => `${e.equipment_number || e.id}${e.equipment_type ? " · " + e.equipment_type : ""}`;

const STATUSES = ["Compliant", "Due Soon", "Expired", "Missing", "Incomplete", "Under Review", "Not Applicable", "Archived"];

export default function CompliancePage() {
  const { slug } = useParams();
  const cfg = COMPLIANCE_TYPES[slug];
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [equipment, setEquipment] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dueFilter, setDueFilter] = useState("all"); // all | 30 | 90
  const [showArchived, setShowArchived] = useState(false);
  const [dialog, setDialog] = useState(null); // {mode, record?}

  useEffect(() => {
    if (!cfg) return;
    let alive = true;
    setLoading(true);
    setError(null);
    const params = showArchived ? "?include_archived=true" : "";
    Promise.allSettled([
      api.get(`${cfg.api}${params}`),
      api.get("/drivers"),
      api.get("/vehicles"),
      api.get("/equipment"),
    ]).then(([listR, dR, vR, eR]) => {
      if (!alive) return;
      if (listR.status === "fulfilled") setItems(listR.value.data || []);
      else setError(formatApiErrorDetail(listR.reason?.response?.data?.detail) || "Failed to load");
      if (dR.status === "fulfilled") setDrivers(dR.value.data || []);
      if (vR.status === "fulfilled") setVehicles(vR.value.data || []);
      if (eR.status === "fulfilled") setEquipment(eR.value.data || []);
    }).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [cfg, showArchived]);

  const lookups = useMemo(() => ({
    drivers: Object.fromEntries(drivers.map((d) => [d.id, d])),
    vehicles: Object.fromEntries(vehicles.map((v) => [v.id, v])),
    equipment: Object.fromEntries(equipment.map((e) => [e.id, e])),
  }), [drivers, vehicles, equipment]);

  const filtered = useMemo(() => {
    if (!cfg) return [];
    let list = items;
    if (statusFilter !== "all") list = list.filter((r) => r.status === statusFilter);
    if (dueFilter !== "all") {
      const horizon = parseInt(dueFilter, 10);
      const today = new Date();
      list = list.filter((r) => {
        if (!r.expiry_date) return false;
        const d = new Date(r.expiry_date);
        const days = Math.floor((d - today) / (1000 * 60 * 60 * 24));
        return days >= 0 && days <= horizon;
      });
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((r) => {
        const bits = [
          r.licence_number, r.policy_number, r.provider, r.registration_number_snapshot,
          r.reference_number, r.compliance_type, r.description, r.task_type, r.defect_number,
          r.status,
          lookups.drivers[r.driver_id]?.full_name,
          lookups.drivers[r.driver_id]?.driver_code,
          lookups.vehicles[r.vehicle_id]?.registration_number,
          lookups.equipment[r.equipment_id]?.equipment_number,
        ].filter(Boolean);
        return bits.some((v) => String(v).toLowerCase().includes(q));
      });
    }
    return list;
  }, [items, cfg, statusFilter, dueFilter, search, lookups]);

  if (!cfg) return <Navigate to="/compliance" replace />;

  const canWrite = user && user.role !== "ReadOnly";
  const canArchive = user && (user.role === "Admin" || user.role === "Manager");

  const openCreate = () => setDialog({ mode: "create" });
  const openEdit = (rec) => setDialog({ mode: "edit", record: rec });
  const openView = (rec) => setDialog({ mode: "view", record: rec });
  const closeDialog = () => setDialog(null);

  const create = async (payload) => {
    try {
      await api.post(cfg.api, payload);
      toast.success("Created");
      closeDialog();
      const { data } = await api.get(`${cfg.api}${showArchived ? "?include_archived=true" : ""}`);
      setItems(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const update = async (id, payload) => {
    try {
      await api.put(`${cfg.api}/${id}`, payload);
      toast.success("Updated");
      closeDialog();
      const { data } = await api.get(`${cfg.api}${showArchived ? "?include_archived=true" : ""}`);
      setItems(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const archive = async (rec) => {
    if (!window.confirm("Archive this record? History remains preserved.")) return;
    try {
      await api.delete(`${cfg.api}/${rec.id}`);
      const { data } = await api.get(`${cfg.api}${showArchived ? "?include_archived=true" : ""}`);
      setItems(data || []);
      toast.success("Archived");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid={`compliance-page-${slug}`}>
      <AppHeader showBack />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-5 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              <Link to="/compliance" className="hover:text-cyan-800">{cfg.heroLabel}</Link>
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
              {cfg.title}
              <span className="ml-3 text-sm text-slate-500 font-normal" data-testid="compliance-count">
                {loading ? "…" : `${filtered.length} / ${items.length}`}
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 max-w-xl leading-snug">{cfg.description}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-48">
              <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                data-testid="compliance-search"
                className="w-full pl-9 pr-3 py-2.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              data-testid="compliance-status-filter"
              className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
            >
              <option value="all">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select
              value={dueFilter}
              onChange={(e) => setDueFilter(e.target.value)}
              data-testid="compliance-due-filter"
              className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
            >
              <option value="all">Any expiry</option>
              <option value="30">Due within 30d</option>
              <option value="90">Due within 90d</option>
            </select>
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox" checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                data-testid="compliance-show-archived"
                className="rounded"
              />
              Show archived
            </label>
            {canWrite && (
              <button
                onClick={openCreate}
                data-testid="compliance-add-button"
                className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2.5 text-sm font-medium"
              >
                <Plus size={16} weight="bold" />
                Add
              </button>
            )}
          </div>
        </section>

        {error && (
          <div className="mb-4 flex items-center gap-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3" data-testid="compliance-error">
            <Warning size={16} weight="bold" />{error}
          </div>
        )}

        <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div className="uppercase tracking-[0.2em] font-semibold">Records</div>
            <div className="text-[11px]">{loading ? "Loading…" : `${filtered.length} shown`}</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="compliance-table">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {cfg.columns.map((c) => (
                    <th key={c.key} className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{c.label}</th>
                  ))}
                  <th className="text-right px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 w-40">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={cfg.columns.length + 1} className="px-6 py-14 text-center text-sm text-slate-400" data-testid="compliance-loading">Loading…</td></tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={cfg.columns.length + 1} className="px-6 py-14 text-center text-sm text-slate-500" data-testid="compliance-empty">No records match this filter.</td></tr>
                )}
                {!loading && filtered.map((row) => (
                  <tr key={row.id} className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors ${row.is_archived ? "opacity-60" : ""}`} data-testid={`compliance-row-${row.id}`}>
                    {cfg.columns.map((c) => (
                      <td key={c.key} className="px-6 py-3.5">
                        <CompCell col={c} row={row} lookups={lookups} entity={cfg.entity} />
                      </td>
                    ))}
                    <td className="px-6 py-3.5 text-right">
                      <div className="inline-flex items-center gap-1">
                        {row.evidence_document_id ? (
                          <Link
                            to={`/documents?doc=${row.evidence_document_id}`}
                            title="Primary Evidence Document"
                            data-testid={`compliance-evidence-${row.id}`}
                            className="p-1.5 rounded-md text-emerald-600 hover:text-emerald-800 hover:bg-emerald-50"
                          >
                            <Paperclip size={14} weight="bold" />
                          </Link>
                        ) : (
                          <span
                            title="No evidence attached"
                            data-testid={`compliance-evidence-missing-${row.id}`}
                            className="p-1.5 rounded-md text-slate-300"
                          >
                            <Paperclip size={14} />
                          </span>
                        )}
                        <button title="View" onClick={() => openView(row)} data-testid={`compliance-view-${row.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900 hover:bg-slate-100">
                          <MagnifyingGlass size={14} />
                        </button>
                        {canWrite && !row.is_archived && (
                          <button title="Edit" onClick={() => openEdit(row)} data-testid={`compliance-edit-${row.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-cyan-700 hover:bg-cyan-50">
                            <PencilSimple size={14} />
                          </button>
                        )}
                        {canArchive && !row.is_archived && (
                          <button title="Archive" onClick={() => archive(row)} data-testid={`compliance-archive-${row.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50">
                            <Archive size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {dialog && (
        <CompDialog
          cfg={cfg}
          mode={dialog.mode}
          record={dialog.record}
          drivers={drivers} vehicles={vehicles} equipment={equipment}
          onClose={closeDialog}
          onCreate={create}
          onUpdate={update}
        />
      )}
    </div>
  );
}

function CompCell({ col, row, lookups, entity }) {
  if (col.type === "driver_lookup") {
    const d = lookups.drivers[row.driver_id];
    return d ? (
      <Link to={`/drivers/${row.driver_id}`} className="text-slate-900 font-medium hover:underline">{labelForDriver(d)}</Link>
    ) : <span className="text-slate-300">—</span>;
  }
  if (col.type === "vehicle_lookup") {
    const v = lookups.vehicles[row.vehicle_id];
    return v ? <span className="text-slate-900 font-medium">{labelForVehicle(v)}</span> : <span className="text-slate-300">—</span>;
  }
  if (col.type === "equipment_lookup") {
    const e = lookups.equipment[row.equipment_id];
    return e ? <span className="text-slate-900 font-medium">{labelForEquipment(e)}</span> : <span className="text-slate-300">—</span>;
  }
  if (col.type === "bool") {
    return row[col.key] ? <span className="text-emerald-700 text-xs">Yes</span> : <span className="text-slate-400 text-xs">No</span>;
  }
  if (col.type === "status_badge") {
    return <StatusBadge status={row.status} />;
  }
  if (col.type === "severity_badge") {
    const s = row.severity;
    const map = {
      Critical: "bg-red-50 text-red-700 border-red-200",
      High: "bg-orange-50 text-orange-700 border-orange-200",
      Medium: "bg-amber-50 text-amber-700 border-amber-200",
      Low: "bg-slate-100 text-slate-600 border-slate-200",
    };
    return <span className={`inline-flex items-center text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${map[s] || map.Low}`}>{s || "—"}</span>;
  }
  if (col.type === "defect_status_badge") {
    const s = row.status;
    const map = {
      Open: "bg-red-50 text-red-700 border-red-200",
      "Under Review": "bg-blue-50 text-blue-700 border-blue-200",
      "Repair Scheduled": "bg-amber-50 text-amber-700 border-amber-200",
      Rectified: "bg-emerald-50 text-emerald-700 border-emerald-200",
      Closed: "bg-slate-100 text-slate-600 border-slate-200",
      Archived: "bg-slate-100 text-slate-500 border-slate-200",
    };
    return <span className={`inline-flex items-center text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${map[s] || map.Closed}`}>{s || "—"}</span>;
  }
  if (col.type === "maintenance_status_badge") {
    const s = row.status;
    const map = {
      Scheduled: "bg-blue-50 text-blue-700 border-blue-200",
      "Due Soon": "bg-amber-50 text-amber-700 border-amber-200",
      Overdue: "bg-red-50 text-red-700 border-red-200",
      "In Progress": "bg-cyan-50 text-cyan-700 border-cyan-200",
      Completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
      Cancelled: "bg-slate-100 text-slate-500 border-slate-200",
      Archived: "bg-slate-100 text-slate-500 border-slate-200",
    };
    return <span className={`inline-flex items-center text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${map[s] || map.Cancelled}`}>{s || "—"}</span>;
  }
  const v = row[col.key];
  return <span className="text-slate-700">{v || <span className="text-slate-300">—</span>}</span>;
}

export function StatusBadge({ status }) {
  // EB-R02C · Expiry-domain compliance records: display "Compliant" as "Current".
  const display = expiryDisplayLabel(status);
  const cls = STATUS_STYLES[display] || STATUS_STYLES[status] || STATUS_STYLES.Incomplete;
  const dot = STATUS_DOT[display] || STATUS_DOT[status] || STATUS_DOT.Incomplete;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${cls}`} data-testid={`status-badge-${status}`}>
      <span className={`inline-flex h-1.5 w-1.5 rounded-full ${dot}`} />
      {display || "Unknown"}
    </span>
  );
}

function CompDialog({ cfg, mode, record, drivers, vehicles, equipment, onClose, onCreate, onUpdate }) {
  const isView = mode === "view";
  const isEdit = mode === "edit";
  const fields = cfg.createFields;
  const [form, setForm] = useState(() =>
    Object.fromEntries(
      (fields || []).map((f) => [
        f.key,
        record?.[f.key] != null ? record[f.key] : (f.type === "checkbox" ? (f.default ?? false) : ""),
      ])
    )
  );
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (isView) return;
    const clean = {};
    for (const f of fields) {
      const v = form[f.key];
      if (f.type === "checkbox") { clean[f.key] = !!v; continue; }
      if (v === "" || v == null) continue;
      clean[f.key] = f.type === "number" ? Number(v) : v;
    }
    setSubmitting(true);
    if (isEdit) {
      // Do not send the entity id field on update — the record already has it
      const { driver_id, vehicle_id, equipment_id, ...rest } = clean;
      await onUpdate(record.id, rest);
    } else {
      await onCreate(clean);
    }
    setSubmitting(false);
  };

  const title = isView ? "View Record" : isEdit ? "Edit Record" : "New Record";

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6" data-testid="compliance-dialog" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-xl rounded-t-2xl sm:rounded-2xl shadow-xl border border-slate-200 max-h-[92vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">{title}</div>
            <div className="font-display font-semibold text-slate-900">{cfg.title}</div>
          </div>
          <button onClick={onClose} data-testid="compliance-dialog-close" className="p-2 text-slate-400 hover:text-slate-900 rounded-md hover:bg-slate-100">
            <X size={18} />
          </button>
        </div>

        {isView ? (
          <div className="px-6 py-5 space-y-3 overflow-y-auto text-sm">
            {Object.entries(record || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-slate-100 pb-2">
                <span className="text-[10px] uppercase tracking-[0.15em] text-slate-500">{k}</span>
                <span className="text-slate-800 text-right truncate max-w-[60%]">{typeof v === "boolean" ? (v ? "true" : "false") : (v ?? "—")}</span>
              </div>
            ))}
          </div>
        ) : (
          <form onSubmit={submit} className="px-6 py-5 space-y-4 overflow-y-auto">
            {fields.map((f) => {
              // In edit mode, hide the parent entity picker (immutable)
              if (isEdit && (f.type === "driver_select" || f.type === "vehicle_select" || f.type === "equipment_select")) {
                return null;
              }
              return (
                <div key={f.key}>
                  <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
                    {f.label}
                    {f.required && <span className="text-red-500 ml-1">*</span>}
                  </label>
                  {f.type === "driver_select" ? (
                    <DriverSelect value={form[f.key] || ""} onChange={(id) => setForm((p) => ({ ...p, [f.key]: id }))} required={!!f.required} drivers={drivers} testid={`compliance-field-${f.key}`} />
                  ) : f.type === "vehicle_select" ? (
                    <GenericSelect items={vehicles} value={form[f.key] || ""} onChange={(v) => setForm((p) => ({ ...p, [f.key]: v }))} required={!!f.required} placeholder="Select a vehicle…" labelFor={labelForVehicle} testid={`compliance-field-${f.key}`} />
                  ) : f.type === "equipment_select" ? (
                    <GenericSelect items={equipment} value={form[f.key] || ""} onChange={(v) => setForm((p) => ({ ...p, [f.key]: v }))} required={!!f.required} placeholder="Select equipment…" labelFor={labelForEquipment} testid={`compliance-field-${f.key}`} />
                  ) : f.type === "select" ? (
                    <select value={form[f.key] || ""} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))} required={!!f.required} data-testid={`compliance-field-${f.key}`} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20">
                      <option value="">Select…</option>
                      {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : f.type === "checkbox" ? (
                    <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                      <input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.checked }))} data-testid={`compliance-field-${f.key}`} className="rounded" />
                      {f.label}
                    </label>
                  ) : (
                    <input type={f.type || "text"} value={form[f.key] || ""} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))} required={!!f.required} data-testid={`compliance-field-${f.key}`} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20" />
                  )}
                </div>
              );
            })}
            <div className="pt-2 flex items-center justify-end gap-3 border-t border-slate-100 mt-6 pt-5">
              <button type="button" onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-4 py-2.5 rounded-lg">Cancel</button>
              <button type="submit" disabled={submitting} data-testid="compliance-dialog-submit" className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
                {submitting ? "Saving…" : isEdit ? "Save Changes" : "Save Record"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
