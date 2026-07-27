import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import NotificationBadge from "../components/app/NotificationBadge";
import {
  Plus, ArrowUpRight, UploadSimple, X, ArrowClockwise, ArrowCounterClockwise,
  CheckCircle, Warning, ClockCounterClockwise,
} from "@phosphor-icons/react";

const STATUS_TONE = {
  "Uploaded": "bg-slate-100 text-slate-600 border-slate-200",
  "Inspecting": "bg-blue-50 text-blue-700 border-blue-200",
  "Mapping Required": "bg-amber-50 text-amber-700 border-amber-200",
  "Ready for Validation": "bg-blue-50 text-blue-700 border-blue-200",
  "Validating": "bg-blue-50 text-blue-700 border-blue-200",
  "Validation Failed": "bg-red-50 text-red-700 border-red-200",
  "Ready to Commit": "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Committing": "bg-blue-50 text-blue-700 border-blue-200",
  "Committed": "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Partially Committed": "bg-amber-50 text-amber-700 border-amber-200",
  "Commit Failed": "bg-red-50 text-red-700 border-red-200",
  "Rolled Back": "bg-slate-100 text-slate-500 border-slate-200",
  "Cancelled": "bg-slate-100 text-slate-500 border-slate-200",
  "Archived": "bg-slate-100 text-slate-500 border-slate-200",
};

export default function ImportCentre() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openNew, setOpenNew] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/imports");
      setJobs(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const canCreate = user && ["Admin", "Manager", "Compliance", "Allocator"].includes(user.role);

  const grouped = useMemo(() => ({
    active: jobs.filter((j) => ["Uploaded", "Inspecting", "Mapping Required", "Ready for Validation", "Validating", "Ready to Commit", "Committing"].includes(j.status)),
    failed: jobs.filter((j) => ["Validation Failed", "Commit Failed"].includes(j.status)),
    committed: jobs.filter((j) => ["Committed", "Partially Committed"].includes(j.status)),
    rolledback: jobs.filter((j) => j.status === "Rolled Back"),
  }), [jobs]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="import-centre-page">
      <AppHeader showBack />
      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-5 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
              Data Import &amp; Migration
            </div>
            <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
              Import Centre
              <span className="ml-3 text-sm text-slate-500 font-normal" data-testid="import-count">
                {loading ? "…" : `${jobs.length} jobs`}
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 max-w-2xl leading-snug">
              Guided XLSX / XLSM / CSV import into the canonical registers. Every commit follows a
              successful dry-run; created records are reversible for a period after commit.
            </p>
          </div>
          {canCreate && (
            <button onClick={() => setOpenNew(true)} data-testid="import-new-button"
              className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-4 py-2.5 text-sm font-medium">
              <Plus size={16} weight="bold" /> New Import
            </button>
          )}
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6" data-testid="import-summary-tiles">
          <SummaryTile label="In Progress" count={grouped.active.length} tone="blue" />
          <SummaryTile label="Committed" count={grouped.committed.length} tone="green" />
          <SummaryTile label="Failed / Blocked" count={grouped.failed.length} tone="red" />
          <SummaryTile label="Rolled Back" count={grouped.rolledback.length} tone="slate" />
        </section>

        <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div className="uppercase tracking-[0.2em] font-semibold">Recent import jobs</div>
            <button onClick={refresh} data-testid="import-refresh" className="inline-flex items-center gap-1 text-[11px] hover:text-slate-900">
              <ArrowClockwise size={12} /> Refresh
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="import-jobs-table">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {["Started", "Domain", "Mode", "Status", "Totals", "Created", "Updated", ""].map((h) => (
                    <th key={h} className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={8} className="px-6 py-14 text-center text-sm text-slate-400">Loading…</td></tr>
                )}
                {!loading && jobs.length === 0 && (
                  <tr><td colSpan={8} className="px-6 py-14 text-center text-sm text-slate-500" data-testid="import-empty">
                    No import jobs yet.{canCreate ? " Click New Import to start." : ""}
                  </td></tr>
                )}
                {!loading && jobs.map((j) => (
                  <tr key={j.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors" data-testid={`import-row-${j.id}`}>
                    <td className="px-6 py-3.5 text-xs text-slate-600">
                      <div>{new Date(j.started_at).toLocaleDateString()}</div>
                      <div className="text-[10px] text-slate-400">{new Date(j.started_at).toLocaleTimeString()}</div>
                    </td>
                    <td className="px-6 py-3.5 text-slate-900 font-medium capitalize">{j.target_domain}</td>
                    <td className="px-6 py-3.5 text-slate-700 text-xs">{j.mode}</td>
                    <td className="px-6 py-3.5">
                      <span className={`inline-flex items-center text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-0.5 rounded-full border ${STATUS_TONE[j.status] || ""}`}>
                        {j.status}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-600">
                      <div>{j.total_rows} rows</div>
                      <div className="text-[10px]">
                        <span className="text-emerald-700">{j.valid_rows}✓</span>{" · "}
                        <span className="text-amber-700">{j.warning_rows}!</span>{" · "}
                        <span className="text-red-700">{j.error_rows}✗</span>
                      </div>
                    </td>
                    <td className="px-6 py-3.5 text-emerald-700 text-sm font-medium">{j.created_rows}</td>
                    <td className="px-6 py-3.5 text-cyan-700 text-sm font-medium">{j.updated_rows}</td>
                    <td className="px-6 py-3.5 text-right">
                      <div className="inline-flex items-center gap-2">
                        <NotificationBadge entityType="ImportJob" entityId={j.id}
                          testid={`import-alert-${j.id}`}
                          linkTo={`/notifications/all?entity_type=ImportJob&entity_id=${j.id}`}
                          compact />
                        <button onClick={() => nav(`/imports/${j.id}`)} data-testid={`import-open-${j.id}`}
                          className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900">
                          Open <ArrowUpRight size={12} weight="bold" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {openNew && <NewImportDialog onClose={() => setOpenNew(false)} onCreated={(id) => { setOpenNew(false); nav(`/imports/${id}`); }} />}
    </div>
  );
}

function SummaryTile({ label, count, tone }) {
  const bg = tone === "blue" ? "bg-blue-50 text-blue-700"
    : tone === "green" ? "bg-emerald-50 text-emerald-700"
    : tone === "red" ? "bg-red-50 text-red-700"
    : "bg-slate-100 text-slate-500";
  return (
    <div className="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm">
      <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <div className="font-display text-2xl font-semibold text-slate-900">{count}</div>
        <span className={`inline-flex text-[10px] px-2 py-0.5 rounded-full font-medium uppercase tracking-[0.15em] ${bg}`}>{tone === "green" ? "✓" : tone === "red" ? "!" : "·"}</span>
      </div>
    </div>
  );
}

function NewImportDialog({ onClose, onCreated }) {
  const [templates, setTemplates] = useState([]);
  const [domain, setDomain] = useState("drivers");
  const [mode, setMode] = useState("Create and Update");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/import-templates").then(({ data }) => setTemplates(data || [])).catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = { target_domain: domain, mode };
      const trimmed = description.trim();
      if (trimmed) payload.description = trimmed;
      const { data } = await api.post("/imports", payload);
      onCreated(data.id);
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6" data-testid="new-import-dialog" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-xl border border-slate-200" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">Step 1 · Choose domain</div>
            <div className="font-display font-semibold text-slate-900">New Import</div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-900 rounded-md hover:bg-slate-100"><X size={18} /></button>
        </div>
        <form onSubmit={submit} className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">Target domain</label>
            <select value={domain} onChange={(e) => setDomain(e.target.value)} data-testid="new-import-domain"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white">
              {templates.map((t) => <option key={t.slug} value={t.slug}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">Mode</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)} data-testid="new-import-mode"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white">
              {["Create Only", "Update Existing", "Create and Update", "Reconcile Only"].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[11px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-2">
              Description <span className="text-slate-400 normal-case tracking-normal">(optional)</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              data-testid="new-import-description"
              rows={2}
              maxLength={500}
              placeholder="Short note about this import (source workbook, purpose, etc.)"
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
            />
          </div>
          <div className="flex justify-end gap-3 pt-2 border-t border-slate-100 mt-4">
            <button type="button" onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-4 py-2.5">Cancel</button>
            <button type="submit" disabled={busy} data-testid="new-import-submit"
              className="inline-flex items-center gap-2 bg-slate-900 text-white hover:bg-slate-800 rounded-lg px-5 py-2.5 text-sm font-medium disabled:opacity-60">
              {busy ? "Creating…" : "Create job"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
