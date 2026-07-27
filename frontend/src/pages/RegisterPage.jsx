import React, { useEffect, useMemo, useState } from "react";
import { useParams, Navigate, Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import OwnerSelect from "../components/app/OwnerSelect";
import { REGISTERS, statusTone } from "../lib/registers";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  Plus,
  MagnifyingGlass,
  Archive,
  Pencil,
  Eye,
  X,
  Warning,
  User,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import NotificationBadge from "../components/app/NotificationBadge";

export default function RegisterPage() {
  const { slug } = useParams();
  const cfg = REGISTERS[slug];
  const { user } = useAuth();

  const [items, setItems] = useState([]);
  const [owners, setOwners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [showArchived, setShowArchived] = useState(false);
  const [dialog, setDialog] = useState(null); // { mode: "create"|"edit"|"view", record }
  const [notifsByEntity, setNotifsByEntity] = useState({});

  // Preserve hooks order — declare after cfg but before any early return
  const needsOwners = useMemo(
    () => !!cfg && cfg.fields.some((f) => f.type === "owner_select"),
    [cfg]
  );

  useEffect(() => {
    if (!cfg) return;
    let active = true;
    setLoading(true);
    setError(null);
    const calls = [api.get(`${cfg.api}?include_archived=${showArchived}`)];
    if (needsOwners) calls.push(api.get("/owners"));
    Promise.allSettled(calls)
      .then(([itemsRes, ownersRes]) => {
        if (!active) return;
        if (itemsRes.status === "fulfilled") {
          setItems(itemsRes.value.data || []);
        } else {
          setError(formatApiErrorDetail(itemsRes.reason?.response?.data?.detail) || "Failed to load records.");
        }
        if (ownersRes && ownersRes.status === "fulfilled") setOwners(ownersRes.value.data || []);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [cfg, showArchived, needsOwners]);

  // Fetch active notifications for this register's entity_type so we can
  // render compact per-row alert chips without N+1 requests.
  useEffect(() => {
    if (!cfg) return;
    const entityMap = { drivers: "Driver", vehicles: "Vehicle", equipment: "Equipment", owners: "Owner" };
    const entityType = entityMap[slug];
    if (!entityType) return;
    let alive = true;
    api.get("/notifications", { params: { entity_type: entityType } })
      .then(({ data }) => {
        if (!alive) return;
        const grouped = {};
        for (const n of data || []) {
          if (n.is_archived || n.status === "Resolved") continue;
          (grouped[n.entity_id] = grouped[n.entity_id] || []).push(n);
        }
        setNotifsByEntity(grouped);
      })
      .catch(() => alive && setNotifsByEntity({}));
    return () => { alive = false; };
  }, [cfg, slug]);

  const ownersById = useMemo(() => {
    const m = {};
    for (const o of owners) m[o.id] = o;
    return m;
  }, [owners]);

  const filtered = useMemo(() => {
    if (!cfg) return [];
    let list = items;
    if (statusFilter !== "all") {
      list = list.filter((it) => it[cfg.statusField] === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((it) => {
        const haystack = cfg.searchFields.map((k) => it[k]).filter(Boolean);
        // Include owner name via lookup for owner_id
        if (it.owner_id && ownersById[it.owner_id]) {
          haystack.push(ownersById[it.owner_id].name);
        }
        return haystack.some((v) => String(v).toLowerCase().includes(q));
      });
    }
    return list;
  }, [items, cfg, statusFilter, search, ownersById]);

  if (!cfg) return <Navigate to="/" replace />;

  const canWrite = user && user.role !== "ReadOnly";
  const canArchive = user && (user.role === "Admin" || user.role === "Manager");

  const openCreate = () => setDialog({ mode: "create", record: null });
  const openEdit = (rec) => setDialog({ mode: "edit", record: rec });
  const openView = (rec) => setDialog({ mode: "view", record: rec });
  const closeDialog = () => setDialog(null);

  const submit = async (mode, record, payload) => {
    try {
      if (mode === "create") {
        const { data } = await api.post(cfg.api, payload);
        setItems((p) => [data, ...p]);
        toast.success(`${cfg.title.slice(0, -1)} added`);
      } else if (mode === "edit") {
        const { data } = await api.put(`${cfg.api}/${record.id}`, payload);
        setItems((p) => p.map((it) => (it.id === data.id ? data : it)));
        toast.success("Updated");
      }
      closeDialog();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const archive = async (rec) => {
    if (!window.confirm(`Archive this ${cfg.title.slice(0, -1).toLowerCase()}? It will be hidden from the main list.`)) return;
    try {
      await api.delete(`${cfg.api}/${rec.id}`);
      setItems((p) => p.filter((it) => it.id !== rec.id));
      toast.success("Archived");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid={`register-page-${slug}`}>
      <AppHeader showBack />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        {/* Header */}
        <section className="mb-5 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              Foundation Register
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
              {cfg.title}
              <span
                className="ml-3 text-sm text-slate-500 font-normal"
                data-testid="register-count"
              >
                {loading ? "…" : `${filtered.length} / ${items.length}`}
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 max-w-xl leading-snug">
              {cfg.description}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-64">
              <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                data-testid="register-search"
                className="w-full pl-9 pr-3 py-2.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              data-testid="register-status-filter"
              className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
            >
              <option value="all">All Statuses</option>
              {cfg.statusOptions.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                data-testid="register-show-archived"
                className="rounded"
              />
              Show archived
            </label>
            {canWrite && (
              <button
                onClick={openCreate}
                data-testid="register-add-button"
                className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors whitespace-nowrap"
              >
                <Plus size={16} weight="bold" />
                Add {cfg.title.slice(0, -1)}
              </button>
            )}
          </div>
        </section>

        {/* States */}
        {error && (
          <div
            data-testid="register-error"
            className="mb-4 flex items-center gap-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3"
          >
            <Warning size={16} weight="bold" />
            {error}
          </div>
        )}

        {/* Table */}
        <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div className="uppercase tracking-[0.2em] font-semibold">
              Records
            </div>
            <div className="text-[11px]">
              {loading ? "Loading…" : `${filtered.length} shown`}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="register-table">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {cfg.columns.map((c) => (
                    <th
                      key={c.key}
                      className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500"
                    >
                      {c.label}
                    </th>
                  ))}
                  <th className="text-right px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 w-36">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={cfg.columns.length + 1} className="px-6 py-16 text-center text-sm text-slate-400" data-testid="register-loading">
                      Loading records…
                    </td>
                  </tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr>
                    <td colSpan={cfg.columns.length + 1} className="px-6 py-16 text-center text-sm text-slate-500" data-testid="register-empty">
                      {items.length === 0 && canWrite
                        ? `No records yet. Click "Add ${cfg.title.slice(0, -1)}" to create the first entry.`
                        : "No records match this filter."}
                    </td>
                  </tr>
                )}
                {!loading &&
                  filtered.map((row) => (
                    <tr
                      key={row.id}
                      data-testid={`register-row-${row.id}`}
                      className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors ${
                        row.is_archived ? "opacity-60" : ""
                      }`}
                    >
                      {cfg.columns.map((c) => (
                        <td key={c.key} className="px-6 py-3.5">
                          <Cell col={c} row={row} ownersById={ownersById} slug={slug} />
                        </td>
                      ))}
                      <td className="px-6 py-3.5 text-right">
                        <div className="inline-flex items-center gap-1">
                          {notifsByEntity[row.id]?.length > 0 && (
                            <NotificationBadge
                              testid={`register-alert-${row.id}`}
                              notifications={notifsByEntity[row.id]}
                              linkTo={`/notifications/all?entity_id=${row.id}`}
                              compact
                            />
                          )}
                          {slug === "drivers" && (
                            <Link
                              to={`/drivers/${row.id}`}
                              title="Open Driver Profile"
                              data-testid={`register-profile-${row.id}`}
                              className="p-1.5 rounded-md text-slate-400 hover:text-cyan-700 hover:bg-cyan-50 transition-colors"
                            >
                              <User size={16} />
                            </Link>
                          )}
                          <IconButton
                            onClick={() => openView(row)}
                            title="View"
                            testid={`register-view-${row.id}`}
                          >
                            <Eye size={16} />
                          </IconButton>
                          {canWrite && !row.is_archived && (
                            <IconButton
                              onClick={() => openEdit(row)}
                              title="Edit"
                              testid={`register-edit-${row.id}`}
                            >
                              <Pencil size={16} />
                            </IconButton>
                          )}
                          {canArchive && !row.is_archived && (
                            <IconButton
                              onClick={() => archive(row)}
                              title="Archive"
                              testid={`register-archive-${row.id}`}
                              destructive
                            >
                              <Archive size={16} />
                            </IconButton>
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
        <RecordDialog
          cfg={cfg}
          mode={dialog.mode}
          record={dialog.record}
          owners={owners}
          onClose={closeDialog}
          onSubmit={submit}
        />
      )}
    </div>
  );
}

function IconButton({ children, onClick, title, testid, destructive = false }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      data-testid={testid}
      className={`p-1.5 rounded-md transition-colors ${
        destructive
          ? "text-slate-400 hover:text-red-600 hover:bg-red-50"
          : "text-slate-400 hover:text-slate-900 hover:bg-slate-100"
      }`}
    >
      {children}
    </button>
  );
}

function Cell({ col, row, ownersById, slug }) {
  const value = row[col.key];
  if (col.type === "status") {
    const tone = statusTone(value);
    const cls =
      tone === "green"
        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
        : tone === "amber"
        ? "bg-amber-50 text-amber-700 border-amber-200"
        : "bg-slate-100 text-slate-600 border-slate-200";
    return (
      <span
        className={`inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${cls}`}
      >
        {value || "—"}
      </span>
    );
  }
  if (col.type === "owner_lookup") {
    const o = value ? ownersById[value] : null;
    if (!o) return <span className="text-slate-300">—</span>;
    return <span className="text-slate-700">{o.name}</span>;
  }
  if (slug === "drivers" && col.key === "full_name" && value) {
    return (
      <Link
        to={`/drivers/${row.id}`}
        data-testid={`register-name-link-${row.id}`}
        className="font-medium text-slate-900 hover:text-cyan-700 hover:underline"
      >
        {value}
      </Link>
    );
  }
  if (col.weight === "primary") {
    return <span className="font-medium text-slate-900">{value || <span className="text-slate-300">—</span>}</span>;
  }
  return <span className="text-slate-700">{value || <span className="text-slate-300">—</span>}</span>;
}

function RecordDialog({ cfg, mode, record, owners, onClose, onSubmit }) {
  const isView = mode === "view";
  const [form, setForm] = useState(() =>
    Object.fromEntries(
      cfg.fields.map((f) => [
        f.key,
        record?.[f.key] != null ? record[f.key] : (f.type === "select" && f.options?.length ? "" : ""),
      ])
    )
  );
  const [submitting, setSubmitting] = useState(false);

  const handle = async (e) => {
    e.preventDefault();
    if (isView) return;
    // EB-08 client-side guard: block permanently reserved dispatch numbers
    if (cfg.slug === "drivers" && form.dispatch_number) {
      const n = parseInt(String(form.dispatch_number).trim(), 10);
      if (n === 0 || n === 13) {
        toast.error(`Dispatch Number ${n} is permanently reserved and cannot be allocated.`);
        return;
      }
    }
    const clean = {};
    for (const f of cfg.fields) {
      const v = form[f.key];
      if (v === "" || v == null) continue;
      if (f.type === "number") {
        const n = Number(v);
        if (!Number.isNaN(n)) clean[f.key] = n;
      } else {
        clean[f.key] = v;
      }
    }
    setSubmitting(true);
    await onSubmit(mode, record, clean);
    setSubmitting(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6"
      onClick={onClose}
      data-testid="record-dialog"
    >
      <div
        className="bg-white w-full sm:max-w-xl rounded-t-2xl sm:rounded-2xl shadow-xl border border-slate-200 max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">
              {mode === "create" ? "New Record" : mode === "edit" ? "Edit Record" : "View Record"}
            </div>
            <div className="font-display font-semibold text-slate-900">
              {mode === "create" ? `Add ${cfg.title.slice(0, -1)}` : cfg.title.slice(0, -1)}
            </div>
          </div>
          <button
            onClick={onClose}
            data-testid="record-dialog-close"
            className="p-2 text-slate-400 hover:text-slate-900 rounded-md hover:bg-slate-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handle} className="px-6 py-5 space-y-4 overflow-y-auto">
          {cfg.fields.map((f) => (
            <div key={f.key}>
              <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
                {f.label}
                {f.required && !isView && <span className="text-red-500 ml-1">*</span>}
              </label>
              {f.type === "owner_select" ? (
                <OwnerSelect
                  value={form[f.key] || ""}
                  onChange={(id) => setForm((p) => ({ ...p, [f.key]: id }))}
                  required={!!f.required}
                  owners={owners}
                  testid={`record-field-${f.key}`}
                />
              ) : f.type === "select" ? (
                <select
                  disabled={isView}
                  required={!!f.required}
                  value={form[f.key] || ""}
                  onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                  data-testid={`record-field-${f.key}`}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 disabled:bg-slate-50 transition-colors"
                >
                  <option value="">Select…</option>
                  {f.options.map((o) => (
                    <option key={o} value={o}>{o}</option>
                  ))}
                </select>
              ) : (
                <>
                  <input
                    type={f.type || "text"}
                    disabled={isView}
                    required={!!f.required}
                    placeholder={f.placeholder || ""}
                    value={form[f.key] ?? ""}
                    onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    data-testid={`record-field-${f.key}`}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 disabled:bg-slate-50 transition-colors"
                  />
                  {cfg.slug === "drivers" && f.key === "driver_code" && !isView && (
                    <DriverCodeAssist
                      value={form[f.key] || ""}
                      onFill={(v, meta) => setForm((p) => ({ ...p, [f.key]: v, __driver_code_meta: meta }))}
                      currentMeta={form.__driver_code_meta}
                    />
                  )}
                  {cfg.slug === "drivers" && f.key === "dispatch_number" && !isView && (
                    <DispatchAssist
                      value={form[f.key] || ""}
                      driverId={record?.id}
                      onFill={(v) => setForm((p) => ({ ...p, [f.key]: v }))}
                    />
                  )}
                </>
              )}
            </div>
          ))}

          <div className="pt-2 flex items-center justify-end gap-3 border-t border-slate-100 mt-6 pt-5">
            <button
              type="button"
              onClick={onClose}
              data-testid="record-dialog-cancel"
              className="text-sm text-slate-600 hover:text-slate-900 px-4 py-2.5 rounded-lg transition-colors"
            >
              {isView ? "Close" : "Cancel"}
            </button>
            {!isView && (
              <button
                type="submit"
                disabled={submitting}
                data-testid="record-dialog-submit"
                className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors disabled:opacity-60"
              >
                {submitting ? "Saving…" : mode === "create" ? "Save Record" : "Save Changes"}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}


// EB-08 · Driver Code assistant — Suggest button + sequence-impact readout
function DriverCodeAssist({ value, onFill, currentMeta }) {
  const [suggestion, setSuggestion] = React.useState(null);
  const [sequence, setSequence] = React.useState(null);
  React.useEffect(() => {
    api.get("/numbering/driver-code/suggestion")
      .then(({ data }) => setSuggestion(data)).catch(() => {});
    api.get("/numbering/driver-code/sequence")
      .then(({ data }) => setSequence(data)).catch(() => {});
  }, []);
  const parsedVal = value ? parseInt(String(value).trim(), 10) : NaN;
  const isIntShaped = !Number.isNaN(parsedVal) && String(parsedVal) === String(value).trim();
  const seqVal = sequence?.value ?? 0;
  const willAdvance = isIntShaped && parsedVal > seqVal;
  const isHistorical = isIntShaped && parsedVal <= seqVal;
  const isAuto = suggestion && String(value).trim() === String(suggestion.suggested_driver_code);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]" data-testid="driver-code-assist">
      <button
        type="button"
        onClick={() => onFill(String(suggestion?.suggested_driver_code || ""), { automatic: true })}
        disabled={!suggestion}
        data-testid="driver-code-suggest"
        className="inline-flex items-center gap-1 border border-slate-200 hover:border-cyan-400 rounded-full px-2 py-0.5 text-slate-700 hover:text-cyan-800 disabled:opacity-40"
      >
        Suggest {suggestion ? `→ ${suggestion.suggested_driver_code}` : "…"}
      </button>
      {isAuto && (
        <span data-testid="driver-code-automatic-badge"
          className="inline-flex text-[9px] font-semibold uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700">
          Automatic
        </span>
      )}
      {!isAuto && value && (
        <span className="inline-flex text-[9px] font-semibold uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border border-amber-200 bg-amber-50 text-amber-700">
          Manual Override
        </span>
      )}
      {willAdvance && (
        <span data-testid="driver-code-warn-advance" className="text-amber-700">
          Warning: this value is above the live sequence ({seqVal}) — saving may advance the sequence.
        </span>
      )}
      {isHistorical && !isAuto && (
        <span data-testid="driver-code-historical-note" className="text-slate-500">
          Historical value — sequence pointer will not advance.
        </span>
      )}
    </div>
  );
}

// EB-08 · Dispatch Number assistant — reusable pool, next-new, 0/13 guard
function DispatchAssist({ value, driverId, onFill }) {
  const [avail, setAvail] = React.useState(null);
  const [reserved, setReserved] = React.useState(false);
  React.useEffect(() => {
    api.get("/numbering/dispatch/available")
      .then(({ data }) => setAvail(data)).catch(() => {});
  }, []);
  const parsedVal = value ? parseInt(String(value).trim(), 10) : NaN;
  const isReserved = parsedVal === 0 || parsedVal === 13;
  return (
    <div className="mt-2 space-y-1.5" data-testid="dispatch-assist">
      {isReserved && (
        <div data-testid="dispatch-reserved-warning" className="text-[11px] text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1">
          Dispatch Numbers 0 and 13 are permanently reserved and cannot be allocated.
        </div>
      )}
      <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
        <span className="uppercase tracking-[0.15em] text-slate-500 mr-1">Reusable</span>
        {(avail?.reusable || []).slice(0, 8).map((n) => (
          <button
            key={n} type="button"
            onClick={() => onFill(String(n))}
            data-testid={`dispatch-reuse-${n}`}
            className="border border-slate-200 hover:border-cyan-400 rounded-full px-2 py-0.5 text-slate-700 hover:text-cyan-800"
          >
            {n}
          </button>
        ))}
        {(!avail || !avail.reusable?.length) && (
          <span className="text-slate-400">None</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className="uppercase tracking-[0.15em] text-slate-500">Next new</span>
        <button type="button"
          onClick={() => avail?.next_new && onFill(String(avail.next_new))}
          disabled={!avail?.next_new}
          data-testid="dispatch-next-new"
          className="border border-slate-200 hover:border-cyan-400 rounded-full px-2 py-0.5 text-slate-700 hover:text-cyan-800 disabled:opacity-40"
        >
          {avail?.next_new || "—"}
        </button>
        <span className="text-slate-400">Reserved</span>
        <span className="border border-red-200 bg-red-50 text-red-700 rounded-full px-2 py-0.5">0</span>
        <span className="border border-red-200 bg-red-50 text-red-700 rounded-full px-2 py-0.5">13</span>
      </div>
    </div>
  );
}
