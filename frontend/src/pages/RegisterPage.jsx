import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
        closeDialog();
        return data;
      } else if (mode === "edit") {
        const { data } = await api.put(`${cfg.api}/${record.id}`, payload);
        setItems((p) => p.map((it) => (it.id === data.id ? data : it)));
        toast.success("Updated");
        closeDialog();
        return data;
      }
      closeDialog();
      return null;
    } catch (e) {
      // Re-raise so RecordDialog can release reservations
      throw e;
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
  const isDrivers = cfg.slug === "drivers";
  const isCreate = mode === "create";
  const [form, setForm] = useState(() =>
    Object.fromEntries(
      cfg.fields.map((f) => [
        f.key,
        record?.[f.key] != null ? record[f.key] : (f.type === "select" && f.options?.length ? "" : ""),
      ])
    )
  );
  const [submitting, setSubmitting] = useState(false);

  // ── EB-08 reservation lifecycle (drivers · create only) ───────────
  const [dcRes, setDcRes] = useState(null);      // {reservation_id, identifier_value, expires_at, automatic, sequence_advanced, manual_override}
  const [dispRes, setDispRes] = useState(null);
  const [resError, setResError] = useState(null); // { kind, message } — blocks save
  const dcResRef = useRef(null);
  const dispResRef = useRef(null);
  useEffect(() => { dcResRef.current = dcRes; }, [dcRes]);
  useEffect(() => { dispResRef.current = dispRes; }, [dispRes]);

  const releaseNow = useCallback(async (reason) => {
    const dc = dcResRef.current;
    const dp = dispResRef.current;
    if (dc?.reservation_id) {
      try { await api.post("/numbering/driver-code/release", { reservation_id: dc.reservation_id, reason }); } catch { /* fire-and-forget */ }
    }
    if (dp?.reservation_id) {
      try { await api.post("/numbering/dispatch/release", { reservation_id: dp.reservation_id, reason }); } catch { /* fire-and-forget */ }
    }
    dcResRef.current = null;
    dispResRef.current = null;
    setDcRes(null);
    setDispRes(null);
  }, []);

  // Release on unmount / route change / cancel
  useEffect(() => {
    return () => {
      // Fire-and-forget release; the ref carries the latest state
      const dc = dcResRef.current;
      const dp = dispResRef.current;
      if (dc?.reservation_id) {
        api.post("/numbering/driver-code/release", { reservation_id: dc.reservation_id, reason: "Dialog closed" }).catch(() => {});
      }
      if (dp?.reservation_id) {
        api.post("/numbering/dispatch/release", { reservation_id: dp.reservation_id, reason: "Dialog closed" }).catch(() => {});
      }
    };
  }, []);

  const closeAndRelease = useCallback(() => {
    // Fire-and-forget, unmount effect also runs — safe
    onClose();
  }, [onClose]);

  const handle = async (e) => {
    e.preventDefault();
    if (isView) return;

    // 0/13 client-side guard (belt & braces — reserve endpoint also blocks)
    if (isDrivers && form.dispatch_number != null && form.dispatch_number !== "") {
      const n = parseInt(String(form.dispatch_number).trim(), 10);
      if (n === 0 || n === 13) {
        toast.error(`Dispatch Number ${n} is permanently reserved and cannot be allocated.`);
        return;
      }
    }

    // Block save if a reservation has expired without a fresh one
    if (isDrivers && isCreate && resError) {
      toast.error(resError.message || "Please re-select the identifier before saving.");
      return;
    }

    // Build the sanitised payload
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

    // ── EB-08 · reserve any missing values just-in-time ──
    let createdDcRes = null;
    let createdDispRes = null;
    if (isDrivers && isCreate) {
      try {
        const dcVal = clean.driver_code != null ? String(clean.driver_code).trim() : "";
        const dc = dcResRef.current;
        if (dcVal && (!dc || String(dc.identifier_value) !== dcVal)) {
          // The user typed a manual value that isn't the current reservation
          if (dc?.reservation_id) {
            await api.post("/numbering/driver-code/release", { reservation_id: dc.reservation_id, reason: "Manual override before save" }).catch(() => {});
            setDcRes(null); dcResRef.current = null;
          }
          const isIntDc = /^\d+$/.test(dcVal);
          if (isIntDc) {
            const { data } = await api.post("/numbering/driver-code/reserve", {
              value: dcVal, manual_override: true, historical: true,
            });
            createdDcRes = data;
            setDcRes(data); dcResRef.current = data;
          }
          // Non-int codes are historical identity strings — no reservation
        }
        const dispVal = clean.dispatch_number != null ? String(clean.dispatch_number).trim() : "";
        const dp = dispResRef.current;
        if (dispVal && (!dp || String(dp.identifier_value) !== dispVal)) {
          if (dp?.reservation_id) {
            await api.post("/numbering/dispatch/release", { reservation_id: dp.reservation_id, reason: "Manual override before save" }).catch(() => {});
            setDispRes(null); dispResRef.current = null;
          }
          const { data } = await api.post("/numbering/dispatch/reserve", {
            value: dispVal, manual_override: true,
          });
          createdDispRes = data;
          setDispRes(data); dispResRef.current = data;
        }
      } catch (err) {
        const detail = err?.response?.data?.detail;
        if (err?.response?.status === 409) {
          toast.error(`Conflict: ${detail || "another user reserved this value"}. Refreshing suggestions.`);
          setResError({ kind: "conflict", message: detail || "Reservation conflict — pick another value." });
          // Force fresh suggestions
          try { window.dispatchEvent(new Event("numbering:refresh")); } catch { /* ignore */ }
        } else {
          toast.error(detail || "Reservation failed");
        }
        setSubmitting(false);
        return;
      }
    }

    // ── Snapshot reservations & clear refs BEFORE onSubmit ──
    // This prevents the unmount cleanup effect (which reads the refs) from
    // firing spurious /release calls in parallel with our /consume calls once
    // the parent closes the dialog on a successful save.
    const dcSnapshot = isDrivers && isCreate ? dcResRef.current : null;
    const dpSnapshot = isDrivers && isCreate ? dispResRef.current : null;
    if (isDrivers && isCreate) {
      dcResRef.current = null;
      dispResRef.current = null;
    }

    // ── Perform the create/edit ──
    let created = null;
    try {
      created = await onSubmit(mode, record, clean);
    } catch (err) {
      // Save failed — restore refs so releaseNow() can free them, then release
      if (isDrivers && isCreate) {
        dcResRef.current = dcSnapshot;
        dispResRef.current = dpSnapshot;
      }
      await releaseNow("Driver save failed");
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
      setSubmitting(false);
      return;
    }

    // ── Consume reservations on success (using local snapshots) ──
    if (isDrivers && isCreate) {
      const driverId = created?.id;
      // Note: consume can no-op safely (409 on double-consume tolerated)
      if (dcSnapshot?.reservation_id && driverId) {
        try {
          await api.post("/numbering/driver-code/consume", { reservation_id: dcSnapshot.reservation_id, driver_id: driverId });
        } catch { /* keep going — audit event is best-effort here */ }
      }
      if (dpSnapshot?.reservation_id && driverId) {
        try {
          await api.post("/numbering/dispatch/consume", { reservation_id: dpSnapshot.reservation_id, driver_id: driverId });
        } catch { /* keep going */ }
      }
      setDcRes(null);
      setDispRes(null);
    }

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
                      isCreate={isCreate}
                      reservation={dcRes}
                      onReserve={setDcRes}
                      onFill={(v) => setForm((p) => ({ ...p, [f.key]: v }))}
                      onResError={setResError}
                    />
                  )}
                  {cfg.slug === "drivers" && f.key === "dispatch_number" && !isView && (
                    <DispatchAssist
                      value={form[f.key] || ""}
                      driverId={record?.id}
                      isCreate={isCreate}
                      reservation={dispRes}
                      onReserve={setDispRes}
                      onFill={(v) => setForm((p) => ({ ...p, [f.key]: v }))}
                      onResError={setResError}
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


// EB-08 · Driver Code assistant — Suggest + reserve; sequence-impact readout
function DriverCodeAssist({ value, isCreate, reservation, onReserve, onFill, onResError }) {
  const [suggestion, setSuggestion] = React.useState(null);
  const [sequence, setSequence] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const refresh = React.useCallback(() => {
    api.get("/numbering/driver-code/suggestion").then(({ data }) => setSuggestion(data)).catch(() => {});
    api.get("/numbering/driver-code/sequence").then(({ data }) => setSequence(data)).catch(() => {});
  }, []);
  React.useEffect(() => { refresh(); }, [refresh]);
  React.useEffect(() => {
    const h = () => refresh();
    window.addEventListener("numbering:refresh", h);
    return () => window.removeEventListener("numbering:refresh", h);
  }, [refresh]);

  const parsedVal = value ? parseInt(String(value).trim(), 10) : NaN;
  const isIntShaped = !Number.isNaN(parsedVal) && String(parsedVal) === String(value).trim();
  const seqVal = sequence?.value ?? 0;
  const willAdvance = isIntShaped && parsedVal > seqVal;
  const isHistorical = isIntShaped && parsedVal <= seqVal;
  const isAuto = !!reservation?.automatic && String(reservation.identifier_value) === String(value).trim();

  const clickSuggest = async () => {
    if (busy || !isCreate) return;
    setBusy(true);
    try {
      // If we already hold a reservation, release it first
      if (reservation?.reservation_id) {
        await api.post("/numbering/driver-code/release", { reservation_id: reservation.reservation_id, reason: "Re-suggest" }).catch(() => {});
      }
      const { data } = await api.post("/numbering/driver-code/reserve", {});
      onReserve(data);
      onFill(String(data.identifier_value));
      onResError && onResError(null);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(detail || "Could not reserve automatic Driver Code");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 space-y-1.5" data-testid="driver-code-assist">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <button
          type="button"
          onClick={clickSuggest}
          disabled={!suggestion || busy || !isCreate}
          data-testid="driver-code-suggest"
          className="inline-flex items-center gap-1 border border-slate-200 hover:border-cyan-400 rounded-full px-2 py-0.5 text-slate-700 hover:text-cyan-800 disabled:opacity-40"
        >
          {busy ? "Reserving…" : `Suggest${suggestion ? ` → ${suggestion.suggested_driver_code}` : ""}`}
        </button>
        {isAuto && (
          <span data-testid="driver-code-automatic-badge"
            className="inline-flex text-[9px] font-semibold uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700">
            Automatic
          </span>
        )}
        {!isAuto && value && isHistorical && (
          <span data-testid="driver-code-manual-badge"
            className="inline-flex text-[9px] font-semibold uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border border-amber-200 bg-amber-50 text-amber-700">
            Historical Manual
          </span>
        )}
        {!isAuto && value && willAdvance && (
          <span data-testid="driver-code-live-badge"
            className="inline-flex text-[9px] font-semibold uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border border-red-200 bg-red-50 text-red-700">
            Live Manual Override
          </span>
        )}
        {reservation?.expires_at && isAuto && (
          <ReservationCountdown reservationId={reservation.reservation_id}
            expiresAt={reservation.expires_at} onExpire={() => {
              onReserve(null);
              onFill("");
              onResError && onResError({ kind: "expired", message: "Driver Code reservation expired — re-suggest before saving." });
              refresh();
            }} testid="driver-code-countdown" />
        )}
      </div>
      {willAdvance && (
        <div data-testid="driver-code-warn-advance" className="text-[11px] text-red-700">
          Warning: this value is above the live sequence ({seqVal}) — saving may advance the sequence.
        </div>
      )}
      {isHistorical && !isAuto && (
        <div data-testid="driver-code-historical-note" className="text-[11px] text-slate-500">
          Historical value — sequence pointer will not advance.
        </div>
      )}
    </div>
  );
}

// EB-08 · Dispatch Number assistant — reusable pool, next-new, reserve on select
function DispatchAssist({ value, driverId, isCreate, reservation, onReserve, onFill, onResError }) {
  const [avail, setAvail] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const refresh = React.useCallback(() => {
    api.get("/numbering/dispatch/available").then(({ data }) => setAvail(data)).catch(() => {});
  }, []);
  React.useEffect(() => { refresh(); }, [refresh]);
  React.useEffect(() => {
    const h = () => refresh();
    window.addEventListener("numbering:refresh", h);
    return () => window.removeEventListener("numbering:refresh", h);
  }, [refresh]);
  const parsedVal = value ? parseInt(String(value).trim(), 10) : NaN;
  const isReserved = parsedVal === 0 || parsedVal === 13;

  const reserveValue = async (n) => {
    if (busy || !isCreate) return;
    setBusy(true);
    try {
      if (reservation?.reservation_id) {
        await api.post("/numbering/dispatch/release", { reservation_id: reservation.reservation_id, reason: "Re-select" }).catch(() => {});
      }
      const { data } = await api.post("/numbering/dispatch/reserve", { value: String(n), driver_id: driverId });
      onReserve(data);
      onFill(String(data.dispatch_number));
      onResError && onResError(null);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 409) {
        toast.error(`Conflict: ${detail}. Refreshing available list.`);
        onResError && onResError({ kind: "conflict", message: detail });
        onFill("");
        refresh();
      } else {
        toast.error(detail || "Could not reserve Dispatch Number");
      }
    } finally {
      setBusy(false);
    }
  };

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
            key={n} type="button" disabled={busy || !isCreate}
            onClick={() => reserveValue(n)}
            data-testid={`dispatch-reuse-${n}`}
            className="border border-slate-200 hover:border-cyan-400 rounded-full px-2 py-0.5 text-slate-700 hover:text-cyan-800 disabled:opacity-40"
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
          onClick={() => avail?.next_new && reserveValue(avail.next_new)}
          disabled={!avail?.next_new || busy || !isCreate}
          data-testid="dispatch-next-new"
          className="border border-slate-200 hover:border-cyan-400 rounded-full px-2 py-0.5 text-slate-700 hover:text-cyan-800 disabled:opacity-40"
        >
          {busy ? "Reserving…" : (avail?.next_new || "—")}
        </button>
        <span className="text-slate-400">Reserved</span>
        <span className="border border-red-200 bg-red-50 text-red-700 rounded-full px-2 py-0.5">0</span>
        <span className="border border-red-200 bg-red-50 text-red-700 rounded-full px-2 py-0.5">13</span>
        {reservation?.expires_at && (
          <ReservationCountdown reservationId={reservation.reservation_id}
            expiresAt={reservation.expires_at} onExpire={() => {
              onReserve(null);
              onFill("");
              onResError && onResError({ kind: "expired", message: "Dispatch Number reservation expired — re-select before saving." });
              refresh();
            }} testid="dispatch-countdown" />
        )}
      </div>
    </div>
  );
}

// EB-08 · Live countdown chip. Fires onExpire once when the timer reaches 0.
function ReservationCountdown({ reservationId, expiresAt, onExpire, testid }) {
  const [now, setNow] = React.useState(() => Date.now());
  const firedRef = React.useRef(false);
  React.useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  React.useEffect(() => { firedRef.current = false; }, [reservationId]);
  const expiresMs = new Date(expiresAt).getTime();
  const remaining = Math.max(0, Math.floor((expiresMs - now) / 1000));
  React.useEffect(() => {
    if (remaining === 0 && !firedRef.current) {
      firedRef.current = true;
      onExpire && onExpire();
    }
  }, [remaining, onExpire]);
  const m = Math.floor(remaining / 60);
  const s = String(remaining % 60).padStart(2, "0");
  return (
    <span
      data-testid={testid}
      title={`Reservation ${reservationId} expires at ${new Date(expiresAt).toLocaleTimeString()}`}
      className={`inline-flex text-[10px] font-medium px-2 py-0.5 rounded-full border ${remaining < 60 ? "border-red-200 bg-red-50 text-red-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}
    >
      {remaining === 0 ? "expired" : `${m}:${s} left`}
    </span>
  );
}
