import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { CaretRight, FileArrowDown, FilePdf, ClockCounterClockwise, Warning } from "@phosphor-icons/react";
import axios from "axios";
import { toast } from "sonner";
import { ManagementCard } from "./driverCCUtils";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });

const ROLE_START = ["Allocator", "Compliance", "Manager", "Admin"];
const ROLE_PROFILE = ["Compliance", "Manager", "Admin"];

function StatusBadge({ status }) {
  const kind = status === "Completed" ? "bg-emerald-100 text-emerald-800"
    : status === "Failed" ? "bg-rose-100 text-rose-800"
    : status === "Generating" ? "bg-amber-100 text-amber-800"
    : status === "Archived" ? "bg-slate-100 text-slate-500"
    : "bg-slate-100 text-slate-700";
  return <span data-testid={`export-status-${status?.toLowerCase() || "unknown"}`}
                className={`text-[9.5px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full ${kind}`}>{status}</span>;
}

export default function AdminUtilitiesCard({ driverId, role, data }) {
  const canManage = ["Admin", "Manager"].includes(role);
  const canStart = ROLE_START.includes(role);
  const canProfile = ROLE_PROFILE.includes(role);

  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState({ start: false, profile: false });

  // Load latest exports (limit 4 for card view)
  const reload = async () => {
    if (!driverId) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API}/drivers/${driverId}/exports`, auth());
      setHistory(res.data || []);
    } catch (err) {
      // history may 403 for ReadOnly in some future config — ignore
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { reload(); }, [driverId]);

  const generate = async (type) => {
    const key = type === "start-sheet" ? "start" : "profile";
    if (generating[key]) return;                            // double-click guard
    setGenerating(prev => ({ ...prev, [key]: true }));
    try {
      const res = await axios.post(`${API}/drivers/${driverId}/exports/${type}`, { confirm: true }, auth());
      const v = res.data?.version;
      toast.success(`${type === "start-sheet" ? "Start Sheet" : "Profile PDF"} v${v?.version_number} generated · ${v?.page_count} page${v?.page_count === 1 ? "" : "s"}`);
      reload();
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      toast.error(`Generation failed: ${msg}`);
    } finally {
      setGenerating(prev => ({ ...prev, [key]: false }));
    }
  };

  const openBlob = async (versionId, mode) => {
    try {
      const res = await axios.get(`${API}/driver-export-versions/${versionId}/${mode}`,
        { ...auth(), responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      if (mode === "preview") {
        window.open(url, "_blank", "noopener,noreferrer");
        // Revoke after a short delay so the new tab has time to consume the URL
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = res.headers["content-disposition"]?.match(/filename="([^"]+)"/)?.[1] || `export-v${versionId.slice(0, 6)}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      toast.error(`Could not ${mode}: ${err.response?.data?.detail || err.message}`);
    }
  };

  const utilities = [
    { key: "docs", label: "Open Document Library", to: `/documents?entity_type=Driver&entity_id=${driverId}`, available: true, testid: "util-open-docs" },
    { key: "upload", label: "Upload supporting document", to: `/documents?entity_type=Driver&entity_id=${driverId}&upload=1`, available: true, testid: "util-upload" },
    { key: "imports", label: "Open Import Centre", to: "/imports", available: canManage, testid: "util-imports" },
    { key: "numbering", label: "Numbering admin", to: "/administration/numbering", available: true, testid: "util-numbering" },
    { key: "notifications", label: "Driver alerts", to: `/notifications/all?entity_type=Driver&entity_id=${driverId}`, available: true, testid: "util-notifications" },
  ];

  const readiness = data?.activation?.readiness;
  const activeOverrideCount = data?.activation?.override ? 1 : 0;
  const mandatoryMissing = (data?.activation?.mandatory_missing_items || []).length;
  const showOverrideWarn = activeOverrideCount > 0
    || readiness === "Ready with Override";
  const showBlockersWarn = mandatoryMissing > 0
    || readiness === "Activation Blocked"
    || readiness === "Blocked"
    || readiness === "Not Ready";

  return (
    <ManagementCard
      testid="card-admin-utilities"
      section="admin"
      title="Administration & Utilities"
      subtitle="Related tools & exports"
      canEdit={false}
    >
      {/* Export Actions */}
      <div className="space-y-2 mb-3" data-testid="export-actions">
        {(showOverrideWarn || showBlockersWarn) && (
          <div className="text-[10.5px] leading-tight bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5 text-amber-800 flex items-start gap-1.5"
               data-testid="export-warning">
            <Warning size={12} className="mt-[1px] shrink-0" />
            <span>
              {showBlockersWarn && <span data-testid="warn-blockers"><b>{mandatoryMissing > 0 ? `${mandatoryMissing} mandatory item(s) outstanding.` : "Activation not ready."}</b> </span>}
              {showOverrideWarn && <span data-testid="warn-overrides"><b>Active override present.</b> </span>}
              Exports will note these truthfully.
            </span>
          </div>
        )}

        <button
          onClick={() => generate("start-sheet")}
          disabled={!canStart || generating.start}
          data-testid="btn-generate-start-sheet"
          className="w-full inline-flex items-center justify-between gap-2 rounded-md border border-slate-200 hover:border-cyan-400 hover:bg-cyan-50 disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-1.5 text-xs font-medium text-slate-800 transition-colors">
          <span className="inline-flex items-center gap-1.5">
            <FileArrowDown size={13} /> Generate Driver Start Sheet
          </span>
          {generating.start
            ? <span className="text-[10px] text-slate-500" data-testid="gen-start-loading">Generating…</span>
            : <CaretRight size={11} />}
        </button>

        <button
          onClick={() => generate("profile-pdf")}
          disabled={!canProfile || generating.profile}
          data-testid="btn-generate-profile-pdf"
          className="w-full inline-flex items-center justify-between gap-2 rounded-md border border-slate-200 hover:border-cyan-400 hover:bg-cyan-50 disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-1.5 text-xs font-medium text-slate-800 transition-colors">
          <span className="inline-flex items-center gap-1.5">
            <FilePdf size={13} /> Generate Driver Profile PDF
          </span>
          {generating.profile
            ? <span className="text-[10px] text-slate-500" data-testid="gen-profile-loading">Generating…</span>
            : <CaretRight size={11} />}
        </button>

        <Link to={`/drivers/${driverId}/exports`}
              data-testid="btn-open-export-history"
              className="w-full inline-flex items-center justify-between gap-2 rounded-md border border-slate-200 hover:border-cyan-400 hover:bg-cyan-50 px-2.5 py-1.5 text-xs font-medium text-slate-800 transition-colors">
          <span className="inline-flex items-center gap-1.5">
            <ClockCounterClockwise size={13} /> Open Export History
          </span>
          <CaretRight size={11} />
        </Link>
      </div>

      {/* Recent exports summary */}
      {history.length > 0 && (
        <div className="mb-3 space-y-1" data-testid="recent-exports">
          <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">Recent exports</div>
          {history.slice(0, 3).map((entry) => {
            const v = entry.current_version;
            const type = entry.job.export_type === "Driver Start Sheet" ? "Start Sheet" : "Profile PDF";
            return (
              <div key={entry.job.driver_export_job_id}
                   data-testid={`recent-export-${entry.job.driver_export_job_id}`}
                   className="flex items-center justify-between gap-2 text-[11px] text-slate-700 border border-slate-100 rounded-md px-2 py-1">
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{type} · v{v?.version_number ?? "—"}</div>
                  <div className="text-[9.5px] text-slate-500 truncate">
                    {entry.job.requested_by} · {(entry.job.completed_at || entry.job.requested_at || "").slice(0, 16).replace("T", " ")}
                  </div>
                </div>
                <StatusBadge status={entry.job.status} />
                {v && entry.job.status === "Completed" && (
                  <button onClick={() => openBlob(v.driver_export_version_id, "preview")}
                          data-testid={`recent-preview-${v.driver_export_version_id}`}
                          className="text-[10px] text-cyan-700 hover:underline shrink-0">Preview</button>
                )}
              </div>
            );
          })}
          {loading && <div className="text-[10px] text-slate-400" data-testid="recent-loading">Loading…</div>}
        </div>
      )}

      <ul className="space-y-1.5">
        {utilities.filter(u => u.available).map((u) => (
          <li key={u.key}>
            <Link to={u.to} data-testid={u.testid} className="text-sm text-cyan-700 hover:underline inline-flex items-center gap-1">
              <CaretRight size={11} /> {u.label}
            </Link>
          </li>
        ))}
      </ul>
    </ManagementCard>
  );
}
