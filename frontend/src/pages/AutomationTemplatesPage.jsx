import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { ArrowClockwise, Plus, Copy, CheckCircle, Archive, Eye, XCircle } from "@phosphor-icons/react";

/**
 * EB-15 Close-out — Notification Template Studio.
 * List / create draft / edit draft / preview / approve / clone / archive.
 * Approved templates are immutable at the API level; UI enforces read-only.
 */
export default function AutomationTemplatesPage() {
  const { user } = useAuth();
  const canView = ["Allocator", "Compliance", "Manager", "Admin"].includes(user?.role);
  const canManage = user?.role === "Manager" || user?.role === "Admin";

  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/automation/notification-templates");
      setRows(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Failed to load templates");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const grouped = useMemo(() => {
    const out = {};
    rows.forEach((r) => {
      const key = `${r.template_key}::${r.channel}`;
      (out[key] ||= []).push(r);
    });
    Object.values(out).forEach((v) => v.sort((a, b) => b.version - a.version));
    return out;
  }, [rows]);

  if (user && !canView) return <Navigate to="/administration/automation" replace />;

  const act = async (template, kind) => {
    const id = template.notification_template_id;
    setBusy(`${kind}-${id}`);
    try {
      await api.post(`/automation/notification-templates/${id}/${kind}`);
      toast.success(`${kind} → ${template.template_key} v${template.version}`);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(null); }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader showBack />
      <main className="max-w-7xl mx-auto px-6 py-8" data-testid="automation-templates-page">
        <div className="flex items-baseline justify-between mb-6">
          <div>
            <h1 className="font-display text-2xl font-semibold text-slate-900">
              Notification Template Studio
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              <Link to="/administration/automation" className="text-cyan-700 hover:underline">
                ← Automation Hub
              </Link>
            </p>
          </div>
          <div className="flex gap-2">
            <button
              data-testid="templates-refresh"
              className="text-xs px-3 py-1.5 rounded-md border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-1.5"
              onClick={load} disabled={loading}
            ><ArrowClockwise size={14} weight="bold" /> Refresh</button>
            {canManage && (
              <button
                data-testid="templates-create"
                className="text-xs px-3 py-1.5 rounded-md border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100 flex items-center gap-1.5"
                onClick={() => setCreating(true)}
              ><Plus size={14} weight="bold" /> New Draft</button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(grouped).map(([key, versions]) => {
            const latest = versions[0];
            return (
              <div key={key} data-testid={`template-card-${latest.template_key}-${latest.channel}`}
                   className="bg-white border border-slate-200 rounded-xl p-4">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="font-mono text-xs text-slate-500">{latest.channel}</div>
                    <div className="font-display font-semibold text-slate-900">{latest.template_key}</div>
                  </div>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                    latest.status === "Approved" ? "bg-emerald-50 text-emerald-700"
                    : latest.status === "Draft" ? "bg-amber-50 text-amber-700"
                    : "bg-slate-100 text-slate-700"
                  }`}>{latest.status} · v{latest.version}</span>
                </div>
                <div className="text-xs text-slate-500 truncate mb-1">{latest.subject_template}</div>
                <div className="text-[11px] text-slate-500 font-mono">
                  {(latest.allowed_variables || []).map((v) => `{{${v}}}`).join(" ") || "no variables"}
                </div>
                <div className="mt-3 flex gap-1 flex-wrap">
                  <button
                    onClick={() => setSelected(latest)}
                    data-testid={`view-${latest.template_key}-${latest.version}`}
                    className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 flex items-center gap-1"
                  ><Eye size={11} weight="bold" /> Open</button>
                  {canManage && latest.status === "Draft" && (
                    <button
                      disabled={busy === `approve-${latest.notification_template_id}`}
                      onClick={() => act(latest, "approve")}
                      data-testid={`approve-${latest.template_key}-${latest.version}`}
                      className="text-xs px-2 py-1 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 flex items-center gap-1"
                    ><CheckCircle size={11} weight="bold" /> Approve</button>
                  )}
                  {canManage && (
                    <button
                      disabled={busy === `clone-${latest.notification_template_id}`}
                      onClick={() => act(latest, "clone")}
                      data-testid={`clone-${latest.template_key}-${latest.version}`}
                      className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 flex items-center gap-1"
                    ><Copy size={11} weight="bold" /> Clone</button>
                  )}
                  {canManage && (
                    <button
                      disabled={busy === `archive-${latest.notification_template_id}`}
                      onClick={() => act(latest, "archive")}
                      data-testid={`archive-${latest.template_key}-${latest.version}`}
                      className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 flex items-center gap-1"
                    ><Archive size={11} weight="bold" /> Archive</button>
                  )}
                </div>
                {versions.length > 1 && (
                  <div className="mt-2 text-[11px] text-slate-400">
                    {versions.length} versions
                  </div>
                )}
              </div>
            );
          })}
          {rows.length === 0 && !loading && (
            <div className="text-sm text-slate-500 p-4">No templates yet</div>
          )}
        </div>

        {selected && (
          <TemplateEditor
            template={selected} canManage={canManage}
            onClose={() => setSelected(null)} onSaved={load} />
        )}
        {creating && (
          <TemplateCreator
            onClose={() => setCreating(false)}
            onCreated={() => { setCreating(false); load(); }} />
        )}
      </main>
    </div>
  );
}

function TemplateEditor({ template, canManage, onClose, onSaved }) {
  const isDraft = template.status === "Draft";
  const editable = canManage && isDraft;
  const [subject, setSubject] = useState(template.subject_template);
  const [body, setBody] = useState(template.body_template);
  const [ctxJson, setCtxJson] = useState('{\n  "name": "Ficta",\n  "count": 3\n}');
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  const runPreview = async () => {
    let ctx = {};
    try { ctx = JSON.parse(ctxJson || "{}"); }
    catch { toast.error("Invalid JSON context"); return; }
    try {
      const { data } = await api.post("/automation/notification-templates/preview", {
        subject_template: subject, body_template: body,
        context: ctx, channel: template.channel,
      });
      setPreview(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/automation/notification-templates/${template.notification_template_id}`, {
        subject_template: subject, body_template: body,
      });
      toast.success("Draft saved");
      onSaved(); onClose();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4"
         onClick={onClose} data-testid="template-editor-modal">
      <div className="bg-white rounded-xl max-w-5xl w-full max-h-[90vh] overflow-auto p-6"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between mb-4">
          <div>
            <h3 className="font-display text-lg font-semibold" data-testid="template-editor-title">
              {template.template_key} · v{template.version} ·{" "}
              <span className={template.status === "Approved" ? "text-emerald-700" : "text-amber-700"}>
                {template.status}
              </span>
            </h3>
            <div className="text-xs text-slate-500 mt-1">
              Channel: {template.channel}
              {!editable && template.status === "Approved" && (
                <span className="ml-3 text-emerald-700 font-medium" data-testid="approved-lock-badge">
                  · locked (clone to edit)
                </span>
              )}
            </div>
          </div>
          <button onClick={onClose} data-testid="template-editor-close"
                  className="text-slate-500 hover:text-slate-900 text-sm">✕</button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="text-xs uppercase tracking-widest text-slate-500">Subject template</label>
            <input
              value={subject} onChange={(e) => setSubject(e.target.value)}
              disabled={!editable}
              data-testid="template-subject-input"
              className="w-full mt-1 px-3 py-2 border border-slate-300 rounded text-sm font-mono disabled:bg-slate-50"
            />
            <label className="text-xs uppercase tracking-widest text-slate-500 mt-4 block">Body template</label>
            <textarea
              value={body} onChange={(e) => setBody(e.target.value)}
              disabled={!editable}
              data-testid="template-body-input"
              rows={8}
              className="w-full mt-1 px-3 py-2 border border-slate-300 rounded text-sm font-mono disabled:bg-slate-50"
            />
            <label className="text-xs uppercase tracking-widest text-slate-500 mt-4 block">Preview context (JSON)</label>
            <textarea
              value={ctxJson} onChange={(e) => setCtxJson(e.target.value)}
              data-testid="template-context-input"
              rows={5}
              className="w-full mt-1 px-3 py-2 border border-slate-300 rounded text-xs font-mono"
            />
            <div className="mt-3 flex gap-2">
              <button
                onClick={runPreview}
                data-testid="template-preview-btn"
                className="text-xs px-3 py-1.5 rounded border border-cyan-300 bg-cyan-50 text-cyan-800 hover:bg-cyan-100"
              >Preview</button>
              {editable && (
                <button
                  disabled={saving}
                  onClick={save}
                  data-testid="template-save-btn"
                  className="text-xs px-3 py-1.5 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                >{saving ? "Saving…" : "Save Draft"}</button>
              )}
            </div>
          </div>

          <div className="bg-slate-50 rounded-lg p-4" data-testid="template-preview-panel">
            <div className="text-xs uppercase tracking-widest text-slate-500 mb-2">Preview</div>
            {!preview && (
              <div className="text-sm text-slate-500">
                Click <b>Preview</b> to see the rendered subject and body with your context.
              </div>
            )}
            {preview && (
              <>
                <div className="mb-3">
                  <div className="text-[11px] text-slate-500 uppercase">Subject</div>
                  <div className="font-semibold" data-testid="preview-subject">{preview.subject}</div>
                </div>
                <div className="mb-3">
                  <div className="text-[11px] text-slate-500 uppercase">Body (plain text)</div>
                  <pre className="text-xs bg-white p-3 rounded border border-slate-200 whitespace-pre-wrap"
                       data-testid="preview-body">{preview.body_text}</pre>
                </div>
                <div className="grid grid-cols-2 gap-3 text-[11px] mb-3">
                  <div>
                    <div className="text-slate-500 uppercase">SMS length</div>
                    <div className="font-semibold" data-testid="preview-sms-length">
                      {preview.sms_length} chars · {preview.sms_segments} segment{preview.sms_segments === 1 ? "" : "s"}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500 uppercase">Channel</div>
                    <div className="font-semibold">{preview.channel}</div>
                  </div>
                </div>
                <div className="mb-2">
                  <div className="text-[11px] text-slate-500 uppercase">Allowed variables</div>
                  <div className="font-mono text-xs">
                    {(preview.allowed_variables || []).map((v) => `{{${v}}}`).join(" ") || "—"}
                  </div>
                </div>
                {preview.missing_variables?.length > 0 && (
                  <div className="mb-2 p-2 rounded bg-amber-50 border border-amber-200"
                       data-testid="preview-missing-warning">
                    <div className="text-[11px] text-amber-800 uppercase flex items-center gap-1">
                      <XCircle size={12} /> Missing variables (rendered as [missing:X])
                    </div>
                    <div className="text-xs font-mono">{preview.missing_variables.join(", ")}</div>
                  </div>
                )}
                {preview.unknown_variables?.length > 0 && (
                  <div className="mb-2 p-2 rounded bg-rose-50 border border-rose-200"
                       data-testid="preview-unknown-warning">
                    <div className="text-[11px] text-rose-800 uppercase flex items-center gap-1">
                      <XCircle size={12} /> Unknown variables in context (ignored)
                    </div>
                    <div className="text-xs font-mono">{preview.unknown_variables.join(", ")}</div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TemplateCreator({ onClose, onCreated }) {
  const [key, setKey] = useState("");
  const [channel, setChannel] = useState("Email");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!key || !subject || !body) return toast.error("All fields required");
    setBusy(true);
    try {
      await api.post("/automation/notification-templates", {
        template_key: key, channel, subject_template: subject, body_template: body,
      });
      toast.success("Draft created");
      onCreated();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4"
         onClick={onClose} data-testid="template-creator-modal">
      <form onSubmit={submit}
            className="bg-white rounded-xl max-w-xl w-full p-6"
            onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between mb-4">
          <h3 className="font-display text-lg font-semibold">New Draft Template</h3>
          <button type="button" onClick={onClose} data-testid="template-creator-close"
                  className="text-slate-500 hover:text-slate-900 text-sm">✕</button>
        </div>
        <div className="space-y-3 text-sm">
          <label className="block">
            <span className="text-xs uppercase tracking-widest text-slate-500">Template key</span>
            <input
              data-testid="new-template-key"
              value={key} onChange={(e) => setKey(e.target.value)}
              placeholder="my_notification_key"
              className="w-full mt-1 px-3 py-2 border border-slate-300 rounded font-mono text-sm"
            />
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-widest text-slate-500">Channel</span>
            <select
              data-testid="new-template-channel"
              value={channel} onChange={(e) => setChannel(e.target.value)}
              className="w-full mt-1 px-3 py-2 border border-slate-300 rounded text-sm"
            >
              <option>Email</option><option>SMS</option><option>In-App</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-widest text-slate-500">Subject template</span>
            <input
              data-testid="new-template-subject"
              value={subject} onChange={(e) => setSubject(e.target.value)}
              placeholder="Hello {{name}}"
              className="w-full mt-1 px-3 py-2 border border-slate-300 rounded font-mono text-sm"
            />
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-widest text-slate-500">Body template</span>
            <textarea
              data-testid="new-template-body"
              value={body} onChange={(e) => setBody(e.target.value)}
              rows={5} placeholder="Body with {{variable}} placeholders"
              className="w-full mt-1 px-3 py-2 border border-slate-300 rounded font-mono text-sm"
            />
          </label>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose}
                  className="text-xs px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50">
            Cancel
          </button>
          <button type="submit" disabled={busy}
                  data-testid="new-template-submit"
                  className="text-xs px-3 py-1.5 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100">
            {busy ? "Creating…" : "Create Draft"}
          </button>
        </div>
      </form>
    </div>
  );
}
