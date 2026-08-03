import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, FileArrowDown, FilePdf, ArrowClockwise, Archive,
  CheckCircle, Warning, ClockCounterClockwise, Eye, DownloadSimple,
} from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("ace_token")}` } });

const ROLE_START = ["Allocator", "Compliance", "Manager", "Admin"];
const ROLE_PROFILE = ["Compliance", "Manager", "Admin"];
const ROLE_ARCHIVE = ["Manager", "Admin"];
const ROLE_REGEN = ["Allocator", "Compliance", "Manager", "Admin"];


function useCurrentUserRole() {
  const [role, setRole] = useState(null);
  useEffect(() => {
    axios.get(`${API}/auth/me`, auth())
      .then(r => setRole(r.data?.role))
      .catch(() => setRole(null));
  }, []);
  return role;
}


function typeBadge(t) {
  if (t === "Driver Start Sheet") {
    return { icon: <FileArrowDown size={13} />, text: "Start Sheet",
             color: "bg-cyan-50 text-cyan-800 border-cyan-200" };
  }
  return { icon: <FilePdf size={13} />, text: "Profile PDF",
           color: "bg-indigo-50 text-indigo-800 border-indigo-200" };
}

function statusStyle(s) {
  return s === "Completed" ? "bg-emerald-100 text-emerald-800"
    : s === "Failed" ? "bg-rose-100 text-rose-800"
    : s === "Generating" ? "bg-amber-100 text-amber-800"
    : s === "Archived" ? "bg-slate-100 text-slate-500"
    : "bg-slate-100 text-slate-700";
}


export default function DriverExportsPage() {
  const { driverId } = useParams();
  const navigate = useNavigate();
  const role = useCurrentUserRole();
  const [rows, setRows] = useState([]);
  const [driver, setDriver] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({});                     // per-job or per-version

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ex, dr] = await Promise.all([
        axios.get(`${API}/drivers/${driverId}/exports`, auth()),
        axios.get(`${API}/drivers/${driverId}`, auth()).catch(() => ({ data: null })),
      ]);
      setRows(ex.data || []);
      setDriver(dr.data);
    } catch (err) {
      toast.error(`Could not load export history: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  }, [driverId]);

  useEffect(() => { load(); }, [load]);

  const setBusyKey = (k, v) => setBusy(prev => ({ ...prev, [k]: v }));

  const generate = async (type) => {
    const key = `gen-${type}`;
    if (busy[key]) return;
    setBusyKey(key, true);
    try {
      const res = await axios.post(`${API}/drivers/${driverId}/exports/${type}`,
        { confirm: true }, auth());
      const v = res.data?.version;
      toast.success(`${type === "start-sheet" ? "Start Sheet" : "Profile PDF"} v${v?.version_number} generated`);
      await load();
    } catch (err) {
      toast.error(`Generation failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setBusyKey(key, false);
    }
  };

  const regenerate = async (jobId) => {
    if (busy[jobId]) return;
    setBusyKey(jobId, true);
    try {
      const res = await axios.post(`${API}/driver-exports/${jobId}/regenerate`, {}, auth());
      toast.success(`Regenerated · v${res.data?.version?.version_number}`);
      await load();
    } catch (err) {
      toast.error(`Regenerate failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setBusyKey(jobId, false);
    }
  };

  const archive = async (versionId) => {
    if (busy[versionId]) return;
    if (!window.confirm("Archive this version? It will remain accessible but be marked as archived.")) return;
    setBusyKey(versionId, true);
    try {
      await axios.post(`${API}/driver-export-versions/${versionId}/archive`, {}, auth());
      toast.success("Version archived");
      await load();
    } catch (err) {
      toast.error(`Archive failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setBusyKey(versionId, false);
    }
  };

  const openBlob = async (versionId, mode) => {
    try {
      const res = await axios.get(`${API}/driver-export-versions/${versionId}/${mode}`,
        { ...auth(), responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      if (mode === "preview") {
        window.open(url, "_blank", "noopener,noreferrer");
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = res.headers["content-disposition"]?.match(/filename="([^"]+)"/)?.[1] || `export-v${versionId.slice(0, 6)}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      const msg = err.response?.status === 403
        ? "You are not authorised to access this export."
        : err.response?.data?.detail || err.message;
      toast.error(msg);
    }
  };

  const canStart = role && ROLE_START.includes(role);
  const canProfile = role && ROLE_PROFILE.includes(role);
  const canArchive = role && ROLE_ARCHIVE.includes(role);
  const canRegen = role && ROLE_REGEN.includes(role);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" data-testid="driver-exports-page">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
          <div>
            <button onClick={() => navigate(`/drivers/${driverId}/command-centre`)}
                    data-testid="btn-back-to-dcc"
                    className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 mb-2">
              <ArrowLeft size={12} /> Back to Driver Command Centre
            </button>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight" data-testid="page-title">
              Driver Export History
            </h1>
            <div className="text-sm text-slate-600 mt-1">
              {driver?.full_name || driver?.name || "Driver"} · <span className="font-mono text-slate-500">{driver?.driver_code || driverId?.slice(0, 8)}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => generate("start-sheet")}
                    disabled={!canStart || busy["gen-start-sheet"]}
                    data-testid="btn-new-start-sheet"
                    className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed text-white px-3 py-1.5 text-xs font-medium">
              <FileArrowDown size={13} /> {busy["gen-start-sheet"] ? "Generating…" : "New Start Sheet"}
            </button>
            <button onClick={() => generate("profile-pdf")}
                    disabled={!canProfile || busy["gen-profile-pdf"]}
                    data-testid="btn-new-profile-pdf"
                    className="inline-flex items-center gap-1.5 rounded-md bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-3 py-1.5 text-xs font-medium">
              <FilePdf size={13} /> {busy["gen-profile-pdf"] ? "Generating…" : "New Profile PDF"}
            </button>
          </div>
        </div>

        {loading && <div className="text-sm text-slate-500" data-testid="exports-loading">Loading exports…</div>}

        {!loading && rows.length === 0 && (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-10 text-center"
               data-testid="exports-empty">
            <ClockCounterClockwise size={24} className="mx-auto text-slate-400 mb-2" />
            <div className="text-sm text-slate-600">No exports generated for this Driver yet.</div>
            <div className="text-xs text-slate-400 mt-1">Use the buttons above to generate the first Start Sheet or Profile PDF.</div>
          </div>
        )}

        {rows.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full divide-y divide-slate-200 text-sm" data-testid="exports-table">
              <thead className="bg-slate-50">
                <tr className="text-left text-[10px] uppercase tracking-[0.14em] text-slate-500">
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Version</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Requested</th>
                  <th className="px-3 py-2">Pages · Size</th>
                  <th className="px-3 py-2">Verification</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map(({ job, current_version }) => {
                  const tb = typeBadge(job.export_type);
                  const v = current_version;
                  return (
                    <tr key={job.driver_export_job_id}
                        data-testid={`export-row-${job.driver_export_job_id}`}
                        className={v?.is_archived ? "opacity-60" : ""}>
                      <td className="px-3 py-2">
                        <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] ${tb.color}`}>
                          {tb.icon} {tb.text}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium text-slate-900">v{v?.version_number ?? "—"}</div>
                        {v?.is_archived && <div className="text-[10px] text-slate-400" data-testid={`archived-flag-${job.driver_export_job_id}`}>Archived</div>}
                      </td>
                      <td className="px-3 py-2">
                        <span data-testid={`export-status-${job.driver_export_job_id}`}
                              className={`text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full ${statusStyle(job.status)}`}>
                          {job.status}
                        </span>
                        {job.status === "Failed" && job.failure_reason && (
                          <div className="text-[10px] text-rose-700 mt-1" data-testid={`fail-reason-${job.driver_export_job_id}`}>{job.failure_reason}</div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-700">
                        <div className="text-xs">{(job.completed_at || job.requested_at || "").slice(0, 16).replace("T", " ")}</div>
                        <div className="text-[10px] text-slate-500">by {job.requested_by}</div>
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-700">
                        {v ? (
                          <>
                            <div>{v.page_count} pages</div>
                            <div className="text-[10px] text-slate-500">{Math.round((v.file_size || 0) / 1024)} KB</div>
                          </>
                        ) : <span className="text-slate-400">—</span>}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-slate-600">
                        {v?.verification_reference || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center justify-end gap-1.5">
                          {v && job.status === "Completed" && (
                            <>
                              <button onClick={() => openBlob(v.driver_export_version_id, "preview")}
                                      data-testid={`btn-preview-${v.driver_export_version_id}`}
                                      className="inline-flex items-center gap-1 rounded border border-slate-200 hover:bg-slate-50 px-2 py-1 text-[11px]">
                                <Eye size={11} /> Preview
                              </button>
                              <button onClick={() => openBlob(v.driver_export_version_id, "download")}
                                      data-testid={`btn-download-${v.driver_export_version_id}`}
                                      className="inline-flex items-center gap-1 rounded border border-slate-200 hover:bg-slate-50 px-2 py-1 text-[11px]">
                                <DownloadSimple size={11} /> Download
                              </button>
                            </>
                          )}
                          {canRegen && (
                            <button onClick={() => regenerate(job.driver_export_job_id)}
                                    disabled={busy[job.driver_export_job_id]}
                                    data-testid={`btn-regenerate-${job.driver_export_job_id}`}
                                    className="inline-flex items-center gap-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-50 px-2 py-1 text-[11px]">
                              <ArrowClockwise size={11} /> Regenerate
                            </button>
                          )}
                          {canArchive && v && !v.is_archived && (
                            <button onClick={() => archive(v.driver_export_version_id)}
                                    disabled={busy[v.driver_export_version_id]}
                                    data-testid={`btn-archive-${v.driver_export_version_id}`}
                                    className="inline-flex items-center gap-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-50 px-2 py-1 text-[11px] text-slate-500">
                              <Archive size={11} /> Archive
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-6 text-[11px] text-slate-500 leading-relaxed">
          Generated exports are immutable historical snapshots. Regenerating creates a fresh version — prior versions remain
          available to authorised roles. Financial fields are only present in versions generated by Manager or Admin roles.
        </div>
      </div>
    </div>
  );
}
