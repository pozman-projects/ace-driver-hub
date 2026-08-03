import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Files, FileArrowUp, FunnelSimple, PlayCircle, CheckCircle, Warning,
  XCircle, ArrowRight, ClockCounterClockwise, Database, GitBranch,
} from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/migration-prep`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });


function Stat({ label, value, tone = "slate", testid }) {
  const t = { slate: "text-slate-700", ok: "text-emerald-700",
              warn: "text-amber-700", bad: "text-rose-700",
              info: "text-cyan-700" }[tone];
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold ${t}`}>{value}</div>
    </div>
  );
}


export default function MigrationPreparationHub() {
  const [wbs, setWbs] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [dryRuns, setDryRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [w, p, d] = await Promise.all([
          axios.get(`${API}/workbooks`, auth()),
          axios.get(`${API}/mapping-profiles`, auth()),
          axios.get(`${API}/dry-runs`, auth()),
        ]);
        setWbs(w.data || []); setProfiles(p.data || []); setDryRuns(d.data || []);
      } catch (err) {
        toast.error(`Could not load migration hub: ${err.response?.data?.detail || err.message}`);
      } finally { setLoading(false); }
    })();
  }, []);

  const approvedProfiles = profiles.filter(p => p.status === "Approved").length;
  const draftProfiles = profiles.filter(p => p.status === "Draft").length;
  const latest = dryRuns[0];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="migration-prep-hub">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-2 text-[11px] uppercase tracking-[0.15em] text-slate-500 inline-flex items-center gap-2">
          <Database size={13} />
          <span>EB-12 · Migration Preparation</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight" data-testid="page-title">Migration Preparation Hub</h1>
        <p className="text-sm text-slate-600 mt-1 max-w-2xl">
          Inspect sanitised workbooks, define mappings, dry-run against the canonical registers, review issues and reconciliation reports,
          and reach a Go / No-Go decision — <b>without changing a single canonical record</b>.
        </p>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-6">
          <Stat label="Workbooks" value={wbs.length} testid="stat-workbooks" />
          <Stat label="Approved profiles" value={approvedProfiles} tone="ok" testid="stat-approved" />
          <Stat label="Draft profiles" value={draftProfiles} tone="warn" testid="stat-drafts" />
          <Stat label="Dry runs" value={dryRuns.length} tone="info" testid="stat-dryruns" />
          <Stat label="Latest result" tone={latest?.status === "Preview Ready" ? "ok" : latest?.status === "Failed" ? "bad" : "slate"}
                value={latest?.status || "—"} testid="stat-latest" />
        </div>

        {/* Quick nav cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-6">
          <QuickCard to="/migration-preparation/workbooks" icon={<FileArrowUp size={16} />}
                      testid="nav-workbooks" title="Source Workbook Inventory"
                      subtitle="Upload sanitised fixtures, inspect sheets and archive." />
          <QuickCard to="/migration-preparation/mappings" icon={<GitBranch size={16} />}
                      testid="nav-mappings" title="Mapping Profiles"
                      subtitle="Author, review, version and approve mapping profiles." />
          <QuickCard to="/migration-preparation/dry-runs" icon={<PlayCircle size={16} />}
                      testid="nav-dry-runs" title="Dry Runs"
                      subtitle="Run non-destructive previews and inspect proposed changes." />
        </div>

        {/* Recent activity */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
          <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="recent-workbooks">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-semibold text-slate-800">Recent workbooks</div>
              <Link to="/migration-preparation/workbooks" className="text-[11px] text-cyan-700 hover:underline">
                See all <ArrowRight size={11} className="inline" />
              </Link>
            </div>
            <ul className="text-sm divide-y divide-slate-100">
              {wbs.slice(0, 4).map(w => (
                <li key={w.migration_source_workbook_id} className="py-2 flex items-start justify-between gap-2"
                    data-testid={`recent-wb-${w.migration_source_workbook_id}`}>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{w.display_name || w.original_file_name}</div>
                    <div className="text-[10.5px] text-slate-500 truncate">
                      {w.authority_level} · {w.detected_sheet_count} sheet(s) · {w.file_sha256?.slice(0, 8)}…
                    </div>
                  </div>
                  <span className="text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
                    {w.status}
                  </span>
                </li>
              ))}
              {wbs.length === 0 && !loading && <li className="py-2 text-xs text-slate-500">No workbooks yet.</li>}
            </ul>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="recent-dryruns">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-semibold text-slate-800">Recent dry runs</div>
              <Link to="/migration-preparation/dry-runs" className="text-[11px] text-cyan-700 hover:underline">
                See all <ArrowRight size={11} className="inline" />
              </Link>
            </div>
            <ul className="text-sm divide-y divide-slate-100">
              {dryRuns.slice(0, 4).map(d => (
                <li key={d.migration_dry_run_id} className="py-2 flex items-start justify-between gap-2"
                    data-testid={`recent-dr-${d.migration_dry_run_id}`}>
                  <div className="min-w-0 flex-1">
                    <Link to={`/migration-preparation/dry-runs/${d.migration_dry_run_id}`}
                          className="font-medium hover:underline">{d.name}</Link>
                    <div className="text-[10.5px] text-slate-500">
                      {d.row_count} rows · {d.blocking_issue_count} blocking · {d.warning_issue_count} warning
                    </div>
                  </div>
                  <span className={`text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full ${
                    d.status === "Preview Ready" ? "bg-emerald-100 text-emerald-800"
                      : d.status === "Failed" ? "bg-rose-100 text-rose-800"
                      : "bg-slate-100 text-slate-700"}`}>{d.status}</span>
                </li>
              ))}
              {dryRuns.length === 0 && !loading && <li className="py-2 text-xs text-slate-500">No dry runs yet.</li>}
            </ul>
          </div>
        </div>

        <div className="mt-8 text-[10.5px] text-slate-500 leading-relaxed">
          <b>Safety:</b> EB-12 has no commit endpoint. No canonical records, relationships, numbering sequences,
          compliance entries, activation records, or documents are mutated by anything on this page or its subroutes.
        </div>
      </div>
    </div>
  );
}


function QuickCard({ to, icon, title, subtitle, testid }) {
  return (
    <Link to={to} data-testid={testid}
          className="group rounded-lg border border-slate-200 bg-white p-4 hover:border-cyan-400 hover:shadow-sm transition-all">
      <div className="flex items-center gap-2 text-slate-800 font-semibold text-sm">
        {icon} {title}
      </div>
      <div className="text-xs text-slate-500 mt-1">{subtitle}</div>
      <div className="text-[11px] text-cyan-700 mt-2 inline-flex items-center gap-1 group-hover:gap-2 transition-all">
        Open <ArrowRight size={11} />
      </div>
    </Link>
  );
}
