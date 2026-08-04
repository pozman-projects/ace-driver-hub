import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import {
  Cube, Database, ArrowClockwise, ShieldCheck, Warning, Play,
  Archive, ArrowCounterClockwise, MagnifyingGlass, FileText, FloppyDisk,
} from "@phosphor-icons/react";
import { formatDateTime } from "../lib/notifications";

/**
 * EB-13 — Private Object Storage Administration.
 *
 * Single-page administration surface for the private object-storage
 * abstraction. Read-first for Managers, action-gated for Admin.
 *
 *  - Storage health card
 *  - Retention policies (create / update / archive)
 *  - Storage objects list (with filters)
 *  - Migration jobs (queue + execute)
 *  - Reconciliation runs
 */
export default function StorageAdmin() {
  const { user } = useAuth();

  const [health, setHealth] = useState(null);
  const [config, setConfig] = useState(null);
  const [policies, setPolicies] = useState([]);
  const [objects, setObjects] = useState([]);
  const [migrations, setMigrations] = useState([]);
  const [recons, setRecons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);
  const [filter, setFilter] = useState({ q: "", status: "" });
  const [newPolicy, setNewPolicy] = useState(null);

  const canManage = user?.role === "Manager" || user?.role === "Admin";
  const canAdmin = user?.role === "Admin";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [h, c, p, o, m, r] = await Promise.all([
        api.get("/storage/health"),
        api.get("/storage/configuration-status"),
        api.get("/storage/retention-policies"),
        api.get("/storage/objects"),
        canManage ? api.get("/storage/migrations") : Promise.resolve({ data: [] }),
        canManage ? api.get("/storage/reconciliation") : Promise.resolve({ data: [] }),
      ]);
      setHealth(h.data);
      setConfig(c.data);
      setPolicies(p.data || []);
      setObjects(o.data || []);
      setMigrations(m.data || []);
      setRecons(r.data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load storage");
    } finally { setLoading(false); }
  }, [canManage]);

  useEffect(() => { refresh(); }, [refresh]);

  const runJob = async (kind) => {
    setRunning(kind);
    try {
      if (kind === "reconciliation") {
        await api.post("/storage/reconciliation");
        toast.success("Reconciliation complete");
      } else if (kind === "migration") {
        const { data } = await api.post("/storage/migrations", {
          source_backend: "local", target_backend: "s3",
          scope: "Migration Workbooks",
        });
        toast.success(`Migration job queued (${data.storage_migration_job_id?.slice(0, 8)})`);
      }
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setRunning(null); }
  };

  const executeMigration = async (jobId) => {
    setRunning(`exec-${jobId}`);
    try {
      const { data } = await api.post(`/storage/migrations/${jobId}/execute`);
      toast.success(`Migrated ${data.migrated_objects} / Failed ${data.failed_objects}`);
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setRunning(null); }
  };

  const objectAction = async (objId, action) => {
    try {
      await api.post(`/storage/objects/${objId}/${action}`);
      toast.success(`Object ${action}d`);
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const savePolicy = async () => {
    if (!newPolicy?.name || !newPolicy?.retention_class) {
      toast.error("Name and retention class are required");
      return;
    }
    try {
      await api.post("/storage/retention-policies", {
        name: newPolicy.name,
        retention_class: newPolicy.retention_class,
        retention_days: Number(newPolicy.retention_days) || 730,
        archive_after_days: Number(newPolicy.archive_after_days) || 365,
        deletion_allowed: !!newPolicy.deletion_allowed,
        legal_hold_supported: !!newPolicy.legal_hold_supported,
      });
      toast.success("Policy created");
      setNewPolicy(null);
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const filteredObjects = useMemo(() => {
    const q = filter.q.toLowerCase();
    return objects.filter(o => {
      if (filter.status && o.status !== filter.status) return false;
      if (!q) return true;
      const label = o.entity_type ? o.entity_type :
        o.migration_workbook_id ? "Migration Workbook" :
        o.document_id ? "Document" : "";
      const blob = `${o.original_file_name || ""} ${o.entity_type || ""} ${label} ${o.retention_class || ""} ${o.content_type || ""} ${o.provider || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [objects, filter]);

  const totals = useMemo(() => {
    const by = { Available: 0, Missing: 0, Quarantined: 0, Archived: 0, "Verification Failed": 0 };
    objects.forEach(o => { by[o.status] = (by[o.status] || 0) + 1; });
    const bytes = objects.reduce((s, o) => s + (o.file_size || 0), 0);
    return { total: objects.length, by, bytes };
  }, [objects]);

  // Route guard: ReadOnly users are redirected to /hub - storage admin is
  // Manager/Admin only. Backend also enforces the same guard.
  if (user && user.role === "ReadOnly") {
    return <Navigate to="/hub" replace />;
  }

  return (
    <div className="min-h-screen bg-neutral-50">
      <AppHeader />
      <div className="max-w-[1400px] mx-auto px-6 py-8" data-testid="storage-admin-page">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-neutral-900 flex items-center gap-2">
              <Cube weight="duotone" className="text-indigo-600" />
              Storage Administration
            </h1>
            <p className="text-neutral-500 mt-1 text-sm">
              EB-13 · Private object-storage abstraction. All uploads, exports and evidence route through this service.
            </p>
          </div>
          <button
            data-testid="storage-refresh-btn"
            onClick={refresh}
            className="px-3 py-2 rounded-lg text-sm border border-neutral-200 bg-white hover:bg-neutral-100 flex items-center gap-2"
          >
            <ArrowClockwise weight="bold" /> Refresh
          </button>
        </div>

        {/* Health + Config strip */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="p-4 rounded-xl border border-neutral-200 bg-white" data-testid="storage-tile-adapter">
            <div className="text-xs text-neutral-500 uppercase">Adapter</div>
            <div className="text-lg font-semibold flex items-center gap-2 mt-1">
              <ShieldCheck weight="fill" className={health?.adapter?.ok ? "text-emerald-600" : "text-rose-600"} />
              {health?.adapter?.provider || "—"} · {health?.adapter?.ok ? "OK" : "Degraded"}
            </div>
            <div className="text-xs text-neutral-500 mt-2">
              Backend: <span className="font-mono">{config?.backend || "?"}</span>
            </div>
          </div>
          <div className="p-4 rounded-xl border border-neutral-200 bg-white" data-testid="storage-tile-total">
            <div className="text-xs text-neutral-500 uppercase">Objects</div>
            <div className="text-3xl font-semibold mt-1">{totals.total}</div>
            <div className="text-xs text-neutral-500 mt-2">
              {(totals.bytes / 1024 / 1024).toFixed(1)} MiB total
            </div>
          </div>
          <div className="p-4 rounded-xl border border-neutral-200 bg-white" data-testid="storage-tile-missing">
            <div className="text-xs text-neutral-500 uppercase">Missing / Failed</div>
            <div className={`text-3xl font-semibold mt-1 ${(totals.by.Missing || 0) + (totals.by["Verification Failed"] || 0) > 0 ? "text-rose-600" : ""}`}>
              {(totals.by.Missing || 0) + (totals.by["Verification Failed"] || 0)}
            </div>
            <div className="text-xs text-neutral-500 mt-2">
              Quarantined: {totals.by.Quarantined || 0}
            </div>
          </div>
          <div className="p-4 rounded-xl border border-neutral-200 bg-white" data-testid="storage-tile-config">
            <div className="text-xs text-neutral-500 uppercase">Signed URL TTL</div>
            <div className="text-3xl font-semibold mt-1">
              {config?.signed_url_ttl ? `${config.signed_url_ttl}s` : "—"}
            </div>
            <div className="text-xs text-neutral-500 mt-2">
              Max upload: {config?.max_upload_bytes ? `${Math.round(config.max_upload_bytes / 1024 / 1024)} MiB` : "—"}
            </div>
          </div>
        </div>

        {/* Jobs strip */}
        {canManage && (
          <div className="mb-8 p-4 rounded-xl border border-neutral-200 bg-white flex items-center gap-3 flex-wrap" data-testid="storage-jobs-strip">
            <div className="text-sm font-semibold text-neutral-700 mr-3">Storage jobs:</div>
            <button
              data-testid="storage-run-reconciliation"
              disabled={running === "reconciliation"}
              onClick={() => runJob("reconciliation")}
              className="px-3 py-2 rounded-lg text-sm border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 flex items-center gap-2 disabled:opacity-50"
            >
              <Play weight="fill" /> Run Reconciliation
            </button>
            <button
              data-testid="storage-queue-migration"
              disabled={running === "migration"}
              onClick={() => runJob("migration")}
              className="px-3 py-2 rounded-lg text-sm border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 flex items-center gap-2 disabled:opacity-50"
            >
              <Database weight="fill" /> Queue Migration (Workbooks → S3)
            </button>
            <div className="text-xs text-neutral-500 ml-auto">
              Do not use real cloud credentials in preview environments.
            </div>
          </div>
        )}

        {/* Objects table */}
        <section className="mb-8" data-testid="storage-objects-section">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h2 className="text-lg font-semibold text-neutral-900">Storage Objects</h2>
            <div className="flex items-center gap-2">
              <div className="relative">
                <MagnifyingGlass className="absolute left-2 top-2.5 text-neutral-400" size={16} />
                <input
                  data-testid="storage-objects-search"
                  className="pl-8 pr-3 py-2 rounded-lg text-sm border border-neutral-200 bg-white"
                  placeholder="Search filename / entity / class"
                  value={filter.q}
                  onChange={(e) => setFilter({ ...filter, q: e.target.value })}
                />
              </div>
              <select
                data-testid="storage-objects-status"
                className="px-2 py-2 rounded-lg text-sm border border-neutral-200 bg-white"
                value={filter.status}
                onChange={(e) => setFilter({ ...filter, status: e.target.value })}
              >
                <option value="">All statuses</option>
                <option>Available</option><option>Missing</option>
                <option>Quarantined</option><option>Archived</option>
                <option>Verification Failed</option>
              </select>
            </div>
          </div>
          <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Filename</th>
                  <th className="text-left px-3 py-2">Entity</th>
                  <th className="text-left px-3 py-2">Retention</th>
                  <th className="text-left px-3 py-2">Provider</th>
                  <th className="text-left px-3 py-2">Size</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">Created</th>
                  <th className="text-right px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={8} className="px-3 py-6 text-center text-neutral-500">Loading…</td></tr>
                )}
                {!loading && filteredObjects.length === 0 && (
                  <tr><td colSpan={8} className="px-3 py-6 text-center text-neutral-500">No objects match.</td></tr>
                )}
                {filteredObjects.map((o) => (
                  <tr key={o.storage_object_id} className="border-t border-neutral-100" data-testid={`storage-row-${o.storage_object_id}`}>
                    <td className="px-3 py-2 max-w-[240px] truncate">
                      <FileText className="inline mr-1 text-neutral-400" size={14} />
                      {o.original_file_name || "—"}
                    </td>
                    <td className="px-3 py-2 text-neutral-600">
                      {o.entity_type ? `${o.entity_type} · ${(o.entity_id || "").slice(0, 8)}` :
                       o.migration_workbook_id ? "Migration Workbook" :
                       o.document_id ? "Document" : "—"}
                    </td>
                    <td className="px-3 py-2 text-neutral-600">{o.retention_class}</td>
                    <td className="px-3 py-2 text-neutral-600">{o.provider}</td>
                    <td className="px-3 py-2 text-neutral-600">{o.file_size ? `${(o.file_size / 1024).toFixed(1)} KiB` : "—"}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs ${
                        o.status === "Available" ? "bg-emerald-50 text-emerald-700" :
                        o.status === "Missing" ? "bg-rose-50 text-rose-700" :
                        o.status === "Quarantined" ? "bg-amber-50 text-amber-700" :
                        o.status === "Archived" ? "bg-neutral-100 text-neutral-600" :
                        "bg-neutral-100 text-neutral-600"
                      }`}>{o.status}</span>
                    </td>
                    <td className="px-3 py-2 text-neutral-500 text-xs whitespace-nowrap">
                      {formatDateTime(o.created_at)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {canManage && o.status === "Available" && (
                        <button
                          data-testid={`storage-verify-${o.storage_object_id}`}
                          onClick={() => objectAction(o.storage_object_id, "verify")}
                          className="mr-1 px-2 py-1 rounded text-xs border border-neutral-200 hover:bg-neutral-100"
                          title="Verify checksum"
                        ><ShieldCheck size={14} /></button>
                      )}
                      {canManage && !o.is_archived && (
                        <button
                          data-testid={`storage-archive-${o.storage_object_id}`}
                          onClick={() => objectAction(o.storage_object_id, "archive")}
                          className="mr-1 px-2 py-1 rounded text-xs border border-neutral-200 hover:bg-neutral-100"
                          title="Archive"
                        ><Archive size={14} /></button>
                      )}
                      {canManage && o.status === "Archived" && (
                        <button
                          data-testid={`storage-restore-${o.storage_object_id}`}
                          onClick={() => objectAction(o.storage_object_id, "restore")}
                          className="mr-1 px-2 py-1 rounded text-xs border border-neutral-200 hover:bg-neutral-100"
                          title="Restore"
                        ><ArrowCounterClockwise size={14} /></button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Migrations + Reconciliation side by side */}
        {canManage && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <section data-testid="storage-migrations-section">
              <h2 className="text-lg font-semibold text-neutral-900 mb-3">Migration Jobs</h2>
              <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
                    <tr>
                      <th className="text-left px-3 py-2">Scope</th>
                      <th className="text-left px-3 py-2">Status</th>
                      <th className="text-left px-3 py-2">Migrated</th>
                      <th className="text-right px-3 py-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {migrations.length === 0 && (
                      <tr><td colSpan={4} className="px-3 py-4 text-center text-neutral-500">No migration jobs.</td></tr>
                    )}
                    {migrations.slice(0, 10).map((m) => (
                      <tr key={m.storage_migration_job_id} className="border-t border-neutral-100" data-testid={`migration-row-${m.storage_migration_job_id}`}>
                        <td className="px-3 py-2">{m.scope}</td>
                        <td className="px-3 py-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${
                            m.status === "Completed" ? "bg-emerald-50 text-emerald-700" :
                            m.status === "Failed" ? "bg-rose-50 text-rose-700" :
                            "bg-neutral-100 text-neutral-600"
                          }`}>{m.status}</span>
                        </td>
                        <td className="px-3 py-2 text-neutral-600">
                          {m.migrated_objects || 0} / {m.total_objects || 0}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {m.status === "Queued" && (
                            <button
                              data-testid={`migration-execute-${m.storage_migration_job_id}`}
                              disabled={running === `exec-${m.storage_migration_job_id}`}
                              onClick={() => executeMigration(m.storage_migration_job_id)}
                              className="px-2 py-1 rounded text-xs border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                            >Execute</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section data-testid="storage-reconciliation-section">
              <h2 className="text-lg font-semibold text-neutral-900 mb-3">Reconciliation Runs</h2>
              <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
                    <tr>
                      <th className="text-left px-3 py-2">Started</th>
                      <th className="text-left px-3 py-2">Type</th>
                      <th className="text-left px-3 py-2">Healthy</th>
                      <th className="text-left px-3 py-2">Missing</th>
                      <th className="text-left px-3 py-2">Orphan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recons.length === 0 && (
                      <tr><td colSpan={5} className="px-3 py-4 text-center text-neutral-500">No runs yet.</td></tr>
                    )}
                    {recons.slice(0, 10).map((r) => (
                      <tr key={r.storage_reconciliation_run_id} className="border-t border-neutral-100" data-testid={`recon-row-${r.storage_reconciliation_run_id}`}>
                        <td className="px-3 py-2 text-xs text-neutral-500">{formatDateTime(r.started_at)}</td>
                        <td className="px-3 py-2">{r.run_type}</td>
                        <td className="px-3 py-2 text-emerald-700">{r.healthy_count}</td>
                        <td className={`px-3 py-2 ${r.missing_count > 0 ? "text-rose-700 font-semibold" : "text-neutral-600"}`}>{r.missing_count}</td>
                        <td className={`px-3 py-2 ${r.orphan_count > 0 ? "text-amber-700 font-semibold" : "text-neutral-600"}`}>{r.orphan_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}

        {/* Retention policies */}
        <section className="mb-8" data-testid="storage-retention-section">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-neutral-900">Retention Policies</h2>
            {canAdmin && (
              <button
                data-testid="storage-add-policy-btn"
                onClick={() => setNewPolicy({
                  name: "", retention_class: "Operational Document",
                  retention_days: 730, archive_after_days: 365,
                  deletion_allowed: false, legal_hold_supported: false
                })}
                className="px-3 py-2 rounded-lg text-sm border border-neutral-200 bg-white hover:bg-neutral-100"
              >+ Add policy</button>
            )}
          </div>
          <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-neutral-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Name</th>
                  <th className="text-left px-3 py-2">Class</th>
                  <th className="text-left px-3 py-2">Retention (days)</th>
                  <th className="text-left px-3 py-2">Archive after</th>
                  <th className="text-left px-3 py-2">Delete allowed</th>
                  <th className="text-left px-3 py-2">Legal hold</th>
                </tr>
              </thead>
              <tbody>
                {policies.map(p => (
                  <tr key={p.storage_retention_policy_id} className="border-t border-neutral-100" data-testid={`policy-row-${p.storage_retention_policy_id}`}>
                    <td className="px-3 py-2 font-medium">{p.name}</td>
                    <td className="px-3 py-2 text-neutral-600">{p.retention_class}</td>
                    <td className="px-3 py-2">{p.retention_days}</td>
                    <td className="px-3 py-2">{p.archive_after_days}</td>
                    <td className="px-3 py-2">{p.deletion_allowed ? "Yes" : "No"}</td>
                    <td className="px-3 py-2">{p.legal_hold_supported ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Add policy modal */}
        {newPolicy && (
          <div className="fixed inset-0 z-30 bg-black/40 flex items-center justify-center" data-testid="storage-new-policy-modal">
            <div className="bg-white rounded-xl border border-neutral-200 w-[520px] max-w-full p-5 space-y-3">
              <div className="text-lg font-semibold">New retention policy</div>
              <label className="block text-xs text-neutral-500">Name
                <input
                  data-testid="policy-name-input"
                  className="w-full mt-1 px-3 py-2 rounded-lg border border-neutral-200"
                  value={newPolicy.name}
                  onChange={e => setNewPolicy({ ...newPolicy, name: e.target.value })}
                />
              </label>
              <label className="block text-xs text-neutral-500">Retention class
                <select
                  data-testid="policy-class-select"
                  className="w-full mt-1 px-3 py-2 rounded-lg border border-neutral-200"
                  value={newPolicy.retention_class}
                  onChange={e => setNewPolicy({ ...newPolicy, retention_class: e.target.value })}
                >
                  <option>Operational Document</option>
                  <option>Compliance Evidence</option>
                  <option>Generated Export</option>
                  <option>Migration Source</option>
                  <option>Temporary Upload</option>
                  <option>Archived Historical</option>
                </select>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-neutral-500">Retention days
                  <input type="number"
                    data-testid="policy-retention-days"
                    className="w-full mt-1 px-3 py-2 rounded-lg border border-neutral-200"
                    value={newPolicy.retention_days}
                    onChange={e => setNewPolicy({ ...newPolicy, retention_days: e.target.value })}
                  />
                </label>
                <label className="block text-xs text-neutral-500">Archive after days
                  <input type="number"
                    className="w-full mt-1 px-3 py-2 rounded-lg border border-neutral-200"
                    value={newPolicy.archive_after_days}
                    onChange={e => setNewPolicy({ ...newPolicy, archive_after_days: e.target.value })}
                  />
                </label>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <label className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={newPolicy.deletion_allowed}
                    onChange={e => setNewPolicy({ ...newPolicy, deletion_allowed: e.target.checked })} />
                  Deletion allowed
                </label>
                <label className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={newPolicy.legal_hold_supported}
                    onChange={e => setNewPolicy({ ...newPolicy, legal_hold_supported: e.target.checked })} />
                  Legal hold
                </label>
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  data-testid="policy-cancel"
                  onClick={() => setNewPolicy(null)}
                  className="px-3 py-2 rounded-lg text-sm border border-neutral-200"
                >Cancel</button>
                <button
                  data-testid="policy-save"
                  onClick={savePolicy}
                  className="px-3 py-2 rounded-lg text-sm bg-indigo-600 text-white hover:bg-indigo-700 flex items-center gap-1"
                ><FloppyDisk weight="fill" /> Save</button>
              </div>
            </div>
          </div>
        )}

        <div className="text-xs text-neutral-400 mt-6">
          Preview environment · local adapter · no real cloud credentials are stored in this build.
        </div>
      </div>
    </div>
  );
}
