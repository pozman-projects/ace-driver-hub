import React, { useEffect, useMemo, useState } from "react";
import { useParams, Navigate, useNavigate, Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import DriverSelect from "../components/app/DriverSelect";
import {
  findModule,
  humanLabel,
  hasDriverRelationship,
  resolveDriverName,
} from "../lib/modules";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Plus, MagnifyingGlass, Trash, X, ArrowUpRight } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function ModulePage() {
  const { slug } = useParams();
  const mod = findModule(slug);
  const { user } = useAuth();
  const navigate = useNavigate();

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [drivers, setDrivers] = useState([]);

  const needsDrivers = mod && (hasDriverRelationship(mod) || mod.slug === "drivers");

  useEffect(() => {
    if (!mod) return;
    let active = true;
    setLoading(true);
    const calls = [api.get(`/modules/${slug}`)];
    if (needsDrivers && mod.slug !== "drivers") {
      calls.push(api.get(`/modules/drivers`));
    }
    Promise.allSettled(calls)
      .then(([itemsRes, driversRes]) => {
        if (!active) return;
        if (itemsRes.status === "fulfilled") setItems(itemsRes.value.data || []);
        if (driversRes && driversRes.status === "fulfilled") setDrivers(driversRes.value.data || []);
        if (mod.slug === "drivers" && itemsRes.status === "fulfilled") {
          setDrivers(itemsRes.value.data || []);
        }
      })
      .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [slug, mod, needsDrivers]);

  const driversById = useMemo(() => {
    const m = {};
    for (const d of drivers) m[d.id] = d;
    return m;
  }, [drivers]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter((it) => {
      const driverName = resolveDriverName(it, mod, driversById);
      const haystack = [...Object.values(it), driverName];
      return haystack.some(
        (v) => v != null && String(v).toLowerCase().includes(q)
      );
    });
  }, [items, search, mod, driversById]);

  const handleCreate = async (payload) => {
    try {
      const { data } = await api.post(`/modules/${slug}`, payload);
      setItems((prev) => [data, ...prev]);
      // Also keep drivers list in sync if creating a driver
      if (mod.slug === "drivers") setDrivers((prev) => [data, ...prev]);
      setShowCreate(false);
      toast.success("Record added");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this record? This cannot be undone.")) return;
    try {
      await api.delete(`/modules/${slug}/${id}`);
      setItems((prev) => prev.filter((it) => it.id !== id));
      toast.success("Record deleted");
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  if (!mod) return <Navigate to="/" replace />;

  const canCreate = user && user.role !== "ReadOnly";
  const canDelete = user && (user.role === "Admin" || user.role === "Manager");

  return (
    <div className="min-h-screen bg-white" data-testid={`module-page-${slug}`}>
      <AppHeader showBack />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-10">
        {/* Module header */}
        <section className="mb-8 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-2">
              Operational Module
            </div>
            <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-tight text-gray-900">
              {mod.title}
            </h1>
            <p className="mt-3 text-gray-600 max-w-xl text-sm leading-relaxed">
              {mod.description}
            </p>
          </div>

          <div className="flex items-center gap-3 w-full lg:w-auto">
            <div className="relative flex-1 lg:w-72">
              <MagnifyingGlass
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search records…"
                data-testid="module-search-input"
                className="w-full pl-9 pr-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-900 transition-colors"
              />
            </div>
            {canCreate && (
              <button
                onClick={() => setShowCreate(true)}
                data-testid="module-add-button"
                className="inline-flex items-center gap-2 bg-gray-900 text-white hover:bg-gray-800 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors whitespace-nowrap"
              >
                <Plus size={16} weight="bold" />
                Add Record
              </button>
            )}
          </div>
        </section>

        {/* Table */}
        <section className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.2em] font-semibold text-gray-500">
              Records · {filtered.length}
            </div>
            <div className="text-[11px] text-gray-400">
              {loading ? "Loading…" : `Showing ${filtered.length} of ${items.length}`}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="module-table">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {mod.columns.map((c) => (
                    <th
                      key={c}
                      className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-gray-500"
                    >
                      {humanLabel(c)}
                    </th>
                  ))}
                  {canDelete && (
                    <th className="text-right px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-gray-500 w-20">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={mod.columns.length + (canDelete ? 1 : 0)}
                      className="px-6 py-16 text-center text-sm text-gray-500"
                    >
                      No records yet. {canCreate && "Click \"Add Record\" to create the first entry."}
                    </td>
                  </tr>
                )}
                {filtered.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50 transition-colors"
                    data-testid={`module-row-${item.id}`}
                  >
                    {mod.columns.map((c) => (
                      <td key={c} className="px-6 py-4 text-gray-800">
                        <Cell
                          column={c}
                          row={item}
                          module={mod}
                          driversById={driversById}
                          onNavigateDriver={(id) => navigate(`/drivers/${id}`)}
                        />
                      </td>
                    ))}
                    {canDelete && (
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleDelete(item.id)}
                          data-testid={`module-delete-${item.id}`}
                          className="inline-flex items-center justify-center p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                          title="Delete record"
                        >
                          <Trash size={16} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {showCreate && (
        <CreateDialog
          module={mod}
          drivers={drivers}
          onClose={() => setShowCreate(false)}
          onSubmit={handleCreate}
        />
      )}
    </div>
  );
}

function Cell({ column, row, module: mod, driversById, onNavigateDriver }) {
  // Virtual driver column — resolve via lookup, render as clickable link to profile.
  if (column === "driver") {
    const name = resolveDriverName(row, mod, driversById);
    const id = row.driver_id;
    if (!name) return <span className="text-gray-300">—</span>;
    if (id) {
      return (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onNavigateDriver(id);
          }}
          data-testid={`row-driver-link-${row.id}`}
          className="inline-flex items-center gap-1 text-gray-900 hover:text-gray-700 hover:underline underline-offset-2 transition-colors"
        >
          {name}
          <ArrowUpRight size={12} weight="bold" className="text-gray-400" />
        </button>
      );
    }
    return <span title="Unlinked legacy record">{name}</span>;
  }
  // Driver Hub: clicking the name opens the driver profile
  if (mod.slug === "drivers" && column === "name") {
    return (
      <Link
        to={`/drivers/${row.id}`}
        data-testid={`row-driver-link-${row.id}`}
        className="font-medium text-gray-900 hover:text-gray-700 hover:underline underline-offset-2 transition-colors"
        onClick={(e) => e.stopPropagation()}
      >
        {row.name}
      </Link>
    );
  }
  return row[column] || <span className="text-gray-300">—</span>;
}

function CreateDialog({ module: mod, drivers, onClose, onSubmit }) {
  const [form, setForm] = useState(
    Object.fromEntries(mod.fields.map((f) => [f.key, ""]))
  );
  const [submitting, setSubmitting] = useState(false);

  const handle = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    await onSubmit(form);
    setSubmitting(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-gray-900/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6"
      data-testid="create-dialog"
      onClick={onClose}
    >
      <div
        className="bg-white w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl shadow-xl border border-gray-200 max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5 border-b border-gray-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-1">
              New Record
            </div>
            <div className="font-display font-semibold text-gray-900">
              Add {mod.title.replace(/^Driver |^ACE /, "")}
            </div>
          </div>
          <button
            onClick={onClose}
            data-testid="create-dialog-close"
            className="p-2 text-gray-400 hover:text-gray-900 rounded-md hover:bg-gray-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handle} className="px-6 py-5 space-y-4 overflow-y-auto">
          {mod.fields.map((f) => (
            <div key={f.key}>
              <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-gray-500 mb-2">
                {f.label}
                {f.required && <span className="text-red-500 ml-1">*</span>}
              </label>
              {f.type === "driver_select" ? (
                <DriverSelect
                  value={form[f.key]}
                  onChange={(id) => setForm((p) => ({ ...p, [f.key]: id }))}
                  required={!!f.required}
                  testid={`create-field-${f.key}`}
                  drivers={drivers}
                />
              ) : (
                <input
                  type={f.type || "text"}
                  required={!!f.required}
                  placeholder={f.placeholder || ""}
                  value={form[f.key]}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, [f.key]: e.target.value }))
                  }
                  data-testid={`create-field-${f.key}`}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-900 transition-colors"
                />
              )}
            </div>
          ))}

          <div className="pt-2 flex items-center justify-end gap-3 border-t border-gray-100 mt-6 pt-5">
            <button
              type="button"
              onClick={onClose}
              data-testid="create-dialog-cancel"
              className="text-sm text-gray-600 hover:text-gray-900 px-4 py-2.5 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              data-testid="create-dialog-submit"
              className="inline-flex items-center gap-2 bg-gray-900 text-white hover:bg-gray-800 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors disabled:opacity-60"
            >
              {submitting ? "Saving…" : "Save Record"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
