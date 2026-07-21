import React, { useEffect, useMemo, useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import DriverSelect from "../components/app/DriverSelect";
import OwnerSelect from "../components/app/OwnerSelect";
import { RELATIONSHIPS } from "../lib/relationships";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Plus, MagnifyingGlass, X, Archive, ArrowsClockwise, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

// Generic single-select combobox reused for owner/vehicle/equipment picks
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

const labelForOwner = (o) => `${o.name}${o.abn ? " · " + o.abn : ""}`;
const labelForVehicle = (v) => `${v.registration_number || v.id}${v.make ? " · " + v.make : ""}${v.model ? " " + v.model : ""}`;
const labelForEquipment = (e) => `${e.equipment_number || e.id} · ${e.equipment_type || ""}`;
const labelForDriver = (d) => `${d.full_name || d.name}${d.driver_code ? " · " + d.driver_code : ""}`;

export default function RelationshipPage() {
  const { slug } = useParams();
  const cfg = RELATIONSHIPS[slug];
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [owners, setOwners] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [equipment, setEquipment] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("all"); // all|active|history
  const [showArchived, setShowArchived] = useState(false);
  const [dialog, setDialog] = useState(null); // {mode: "create"|"reassign"|"view"|"edit", record?}

  useEffect(() => {
    if (!cfg) return;
    let alive = true;
    setLoading(true);
    setError(null);
    const params = showArchived ? "?include_archived=true" : "";
    Promise.allSettled([
      api.get(`${cfg.api}${params}`),
      api.get("/drivers"),
      api.get("/owners"),
      api.get("/vehicles"),
      api.get("/equipment"),
    ]).then(([listR, dR, oR, vR, eR]) => {
      if (!alive) return;
      if (listR.status === "fulfilled") setItems(listR.value.data || []);
      else setError(formatApiErrorDetail(listR.reason?.response?.data?.detail) || "Failed to load");
      if (dR.status === "fulfilled") setDrivers(dR.value.data || []);
      if (oR.status === "fulfilled") setOwners(oR.value.data || []);
      if (vR.status === "fulfilled") setVehicles(vR.value.data || []);
      if (eR.status === "fulfilled") setEquipment(eR.value.data || []);
    }).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [cfg, showArchived]);

  const lookupMaps = useMemo(() => ({
    drivers: Object.fromEntries(drivers.map((d) => [d.id, d])),
    owners: Object.fromEntries(owners.map((o) => [o.id, o])),
    vehicles: Object.fromEntries(vehicles.map((v) => [v.id, v])),
    equipment: Object.fromEntries(equipment.map((e) => [e.id, e])),
  }), [drivers, owners, vehicles, equipment]);

  const filtered = useMemo(() => {
    if (!cfg) return [];
    let list = items;
    if (activeFilter === "active") {
      list = list.filter((r) => r[cfg.activeField] === true);
    } else if (activeFilter === "history") {
      list = list.filter((r) => r[cfg.activeField] === false);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((r) => {
        const bits = [
          r.notes,
          r.relationship_type,
          r.start_date,
          r.end_date,
          lookupMaps.drivers[r.driver_id]?.full_name,
          lookupMaps.drivers[r.driver_id]?.driver_code,
          lookupMaps.owners[r.owner_id]?.name,
          lookupMaps.vehicles[r.vehicle_id]?.registration_number,
          lookupMaps.equipment[r.equipment_id]?.equipment_number,
        ].filter(Boolean);
        return bits.some((v) => String(v).toLowerCase().includes(q));
      });
    }
    return list;
  }, [items, cfg, activeFilter, search, lookupMaps]);

  if (!cfg) return <Navigate to="/" replace />;

  const canWrite = user && user.role !== "ReadOnly";
  const canArchive = user && (user.role === "Admin" || user.role === "Manager");

  const openCreate = () => setDialog({ mode: "create" });
  const openReassign = () => setDialog({ mode: "reassign" });
  const openView = (rec) => setDialog({ mode: "view", record: rec });
  const closeDialog = () => setDialog(null);

  const create = async (payload) => {
    try {
      const { data } = await api.post(cfg.api, payload);
      setItems((prev) => [data, ...prev]);
      toast.success("Created");
      closeDialog();
      // reload if create closed other actives — simpler: refetch list
      const params = showArchived ? "?include_archived=true" : "";
      const { data: refreshed } = await api.get(`${cfg.api}${params}`);
      setItems(refreshed || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const reassign = async (payload) => {
    try {
      await api.post(cfg.reassignApi, payload);
      toast.success("Reassigned");
      closeDialog();
      const params = showArchived ? "?include_archived=true" : "";
      const [rlist, req] = await Promise.all([
        api.get(`${cfg.api}${params}`),
        api.get("/equipment"),
      ]);
      setItems(rlist.data || []);
      setEquipment(req.data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const archive = async (rec) => {
    if (!window.confirm("Archive this record? History remains preserved.")) return;
    try {
      await api.delete(`${cfg.api}/${rec.id}`);
      const params = showArchived ? "?include_archived=true" : "";
      const [rlist, req] = await Promise.all([
        api.get(`${cfg.api}${params}`),
        api.get("/equipment"),
      ]);
      setItems(rlist.data || []);
      setEquipment(req.data || []);
      toast.success("Archived");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid={`relationship-page-${slug}`}>
      <AppHeader showBack />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-5 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              {cfg.heroLabel}
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
              {cfg.title}
              <span className="ml-3 text-sm text-slate-500 font-normal" data-testid="relationship-count">
                {loading ? "…" : `${filtered.length} / ${items.length}`}
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 max-w-xl leading-snug">{cfg.description}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-56">
              <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                data-testid="relationship-search"
                className="w-full pl-9 pr-3 py-2.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
              />
            </div>
            <select
              value={activeFilter}
              onChange={(e) => setActiveFilter(e.target.value)}
              data-testid="relationship-active-filter"
              className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
            >
              <option value="all">All</option>
              <option value="active">{cfg.activeLabel} only</option>
              <option value="history">Historical only</option>
            </select>
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox" checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                data-testid="relationship-show-archived"
                className="rounded"
              />
              Show archived
            </label>
            {canWrite && cfg.supportsReassign && (
              <button
                onClick={openReassign}
                data-testid="relationship-reassign-button"
                className="inline-flex items-center gap-2 border border-cyan-500 text-cyan-700 hover:bg-cyan-50 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors"
              >
                <ArrowsClockwise size={16} weight="bold" />
                Reassign
              </button>
            )}
            {canWrite && (
              <button
                onClick={openCreate}
                data-testid="relationship-add-button"
                className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors"
              >
                <Plus size={16} weight="bold" />
                Add
              </button>
            )}
          </div>
        </section>

        {error && (
          <div className="mb-4 flex items-center gap-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3" data-testid="relationship-error">
            <Warning size={16} weight="bold" />{error}
          </div>
        )}

        <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div className="uppercase tracking-[0.2em] font-semibold">Records</div>
            <div className="text-[11px]">{loading ? "Loading…" : `${filtered.length} shown`}</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="relationship-table">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {cfg.columns.map((c) => (
                    <th key={c.key} className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{c.label}</th>
                  ))}
                  <th className="text-right px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 w-24">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={cfg.columns.length + 1} className="px-6 py-14 text-center text-sm text-slate-400" data-testid="relationship-loading">Loading…</td></tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={cfg.columns.length + 1} className="px-6 py-14 text-center text-sm text-slate-500" data-testid="relationship-empty">No records match this filter.</td></tr>
                )}
                {!loading && filtered.map((row) => (
                  <tr key={row.id} className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors ${row.is_archived ? "opacity-60" : ""}`} data-testid={`relationship-row-${row.id}`}>
                    {cfg.columns.map((c) => (
                      <td key={c.key} className="px-6 py-3.5">
                        <RelCell col={c} row={row} lookups={lookupMaps} />
                      </td>
                    ))}
                    <td className="px-6 py-3.5 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button title="View" onClick={() => openView(row)} data-testid={`relationship-view-${row.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900 hover:bg-slate-100">
                          <MagnifyingGlass size={14} />
                        </button>
                        {canArchive && !row.is_archived && (
                          <button title="Archive" onClick={() => archive(row)} data-testid={`relationship-archive-${row.id}`} className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50">
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
        <RelDialog
          cfg={cfg}
          mode={dialog.mode}
          record={dialog.record}
          drivers={drivers} owners={owners} vehicles={vehicles} equipment={equipment}
          onClose={closeDialog}
          onCreate={create}
          onReassign={reassign}
        />
      )}
    </div>
  );
}

function RelCell({ col, row, lookups }) {
  if (col.type === "driver_lookup") {
    const d = lookups.drivers[row.driver_id];
    return <span className="text-slate-900 font-medium">{d ? labelForDriver(d) : "—"}</span>;
  }
  if (col.type === "owner_lookup") {
    const o = lookups.owners[row.owner_id];
    return <span className="text-slate-700">{o ? o.name : "—"}</span>;
  }
  if (col.type === "vehicle_lookup") {
    const v = lookups.vehicles[row.vehicle_id];
    return <span className="text-slate-700">{v ? labelForVehicle(v) : "—"}</span>;
  }
  if (col.type === "equipment_lookup") {
    const e = lookups.equipment[row.equipment_id];
    return <span className="text-slate-700">{e ? labelForEquipment(e) : "—"}</span>;
  }
  if (col.type === "current_badge") {
    return <StatusBadge active={row.is_current} activeLabel="Current" endLabel="Historical" />;
  }
  if (col.type === "active_badge") {
    return <StatusBadge active={row.is_active} activeLabel="Active" endLabel="Historical" />;
  }
  if (col.type === "bool") {
    return row[col.key] ? <span className="text-emerald-700 text-xs">Yes</span> : <span className="text-slate-400 text-xs">No</span>;
  }
  const v = row[col.key];
  return <span className="text-slate-700">{v || <span className="text-slate-300">—</span>}</span>;
}

function StatusBadge({ active, activeLabel, endLabel }) {
  const cls = active
    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${cls}`}>
      <span className={`inline-flex h-1.5 w-1.5 rounded-full ${active ? "bg-emerald-500" : "bg-slate-400"}`} />
      {active ? activeLabel : endLabel}
    </span>
  );
}

function RelDialog({ cfg, mode, record, drivers, owners, vehicles, equipment, onClose, onCreate, onReassign }) {
  const isView = mode === "view";
  const isReassign = mode === "reassign";
  const fields = isReassign ? cfg.reassignFields : cfg.createFields;
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
      clean[f.key] = v;
    }
    setSubmitting(true);
    if (isReassign) await onReassign(clean);
    else await onCreate(clean);
    setSubmitting(false);
  };

  const title = isView
    ? "View Record"
    : isReassign
    ? "Controlled Reassignment"
    : "New Record";

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6" data-testid="relationship-dialog" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-xl rounded-t-2xl sm:rounded-2xl shadow-xl border border-slate-200 max-h-[92vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">{title}</div>
            <div className="font-display font-semibold text-slate-900">{cfg.title}</div>
          </div>
          <button onClick={onClose} data-testid="relationship-dialog-close" className="p-2 text-slate-400 hover:text-slate-900 rounded-md hover:bg-slate-100">
            <X size={18} />
          </button>
        </div>

        {isView ? (
          <div className="px-6 py-5 space-y-3 overflow-y-auto text-sm">
            {Object.entries(record || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-slate-100 pb-2">
                <span className="text-[10px] uppercase tracking-[0.15em] text-slate-500">{k}</span>
                <span className="text-slate-800 text-right truncate">{typeof v === "boolean" ? (v ? "true" : "false") : (v ?? "—")}</span>
              </div>
            ))}
          </div>
        ) : (
          <form onSubmit={submit} className="px-6 py-5 space-y-4 overflow-y-auto">
            {fields.map((f) => (
              <div key={f.key}>
                <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
                  {f.label}
                  {f.required && <span className="text-red-500 ml-1">*</span>}
                </label>
                {f.type === "driver_select" ? (
                  <DriverSelect value={form[f.key] || ""} onChange={(id) => setForm((p) => ({ ...p, [f.key]: id }))} required={!!f.required} drivers={drivers} testid={`relationship-field-${f.key}`} />
                ) : f.type === "owner_select" ? (
                  <OwnerSelect value={form[f.key] || ""} onChange={(id) => setForm((p) => ({ ...p, [f.key]: id }))} required={!!f.required} owners={owners} testid={`relationship-field-${f.key}`} />
                ) : f.type === "vehicle_select" ? (
                  <GenericSelect items={vehicles} value={form[f.key] || ""} onChange={(v) => setForm((p) => ({ ...p, [f.key]: v }))} required={!!f.required} placeholder="Select a vehicle…" labelFor={labelForVehicle} testid={`relationship-field-${f.key}`} />
                ) : f.type === "equipment_select" ? (
                  <GenericSelect items={equipment} value={form[f.key] || ""} onChange={(v) => setForm((p) => ({ ...p, [f.key]: v }))} required={!!f.required} placeholder="Select equipment…" labelFor={labelForEquipment} testid={`relationship-field-${f.key}`} />
                ) : f.type === "select" ? (
                  <select value={form[f.key] || ""} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))} required={!!f.required} data-testid={`relationship-field-${f.key}`} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500">
                    <option value="">Select…</option>
                    {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : f.type === "checkbox" ? (
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                    <input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.checked }))} data-testid={`relationship-field-${f.key}`} className="rounded" />
                    {f.label}
                  </label>
                ) : (
                  <input type={f.type || "text"} value={form[f.key] || ""} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))} required={!!f.required} data-testid={`relationship-field-${f.key}`} className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500" />
                )}
              </div>
            ))}
            <div className="pt-2 flex items-center justify-end gap-3 border-t border-slate-100 mt-6 pt-5">
              <button type="button" onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-4 py-2.5 rounded-lg">Cancel</button>
              <button type="submit" disabled={submitting} data-testid="relationship-dialog-submit" className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
                {submitting ? "Saving…" : isReassign ? "Confirm Reassignment" : "Save Record"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
