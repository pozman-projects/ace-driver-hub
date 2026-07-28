import React, { useMemo, useState } from "react";
import { toast } from "sonner";
import { NoteBlank, PushPin } from "@phosphor-icons/react";
import api, { formatApiErrorDetail } from "../../lib/api";
import { ManagementCard } from "./driverCCUtils";

export default function DriverNotesCard({ data, role, driverId, onChanged }) {
  const notes = data.notes || [];
  const canWrite = role !== "ReadOnly";
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ note_type: "General", title: "", content: "", is_pinned: false });
  const [saving, setSaving] = useState(false);

  const categories = useMemo(() => {
    const base = ["General", "Operations", "Incident", "Management", "Other"];
    if (["Compliance", "Manager", "Admin"].includes(role)) base.push("Compliance");
    if (["Manager", "Admin"].includes(role)) base.push("Accounts");
    return base;
  }, [role]);

  const save = async () => {
    if (!form.content.trim()) { toast.error("Content required"); return; }
    setSaving(true);
    try {
      await api.post(`/drivers/${driverId}/notes`, form);
      toast.success("Note added");
      setAdding(false);
      setForm({ note_type: "General", title: "", content: "", is_pinned: false });
      await onChanged?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Could not add note");
    } finally { setSaving(false); }
  };

  return (
    <ManagementCard
      testid="card-notes"
      section="notes"
      title="Notes"
      subtitle={`${notes.length} visible`}
      canEdit={false}
    >
      {adding ? (
        <div className="space-y-2 border border-slate-200 rounded p-2 bg-slate-50">
          <select
            data-testid="note-type"
            value={form.note_type}
            onChange={(e) => setForm({ ...form, note_type: e.target.value })}
            className="w-full border border-slate-200 rounded px-2 py-1 text-sm bg-white"
          >
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input
            data-testid="note-title"
            placeholder="Title (optional)"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="w-full border border-slate-200 rounded px-2 py-1 text-sm bg-white"
          />
          <textarea
            data-testid="note-content"
            placeholder="Content"
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            className="w-full border border-slate-200 rounded px-2 py-1 text-sm bg-white h-20"
          />
          <label className="flex items-center gap-2 text-xs text-slate-700">
            <input type="checkbox" checked={form.is_pinned} onChange={(e) => setForm({ ...form, is_pinned: e.target.checked })} data-testid="note-pin" /> Pin
          </label>
          <div className="flex items-center gap-2">
            <button data-testid="note-save" disabled={saving} onClick={save} className="text-[11px] px-3 py-1 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50">{saving ? "Saving…" : "Save note"}</button>
            <button data-testid="note-cancel" onClick={() => setAdding(false)} className="text-[11px] px-3 py-1 rounded text-slate-600 hover:text-slate-900">Cancel</button>
          </div>
        </div>
      ) : (
        <>
          {notes.length === 0 ? (
            <div data-testid="notes-empty" className="text-xs text-slate-400 italic">No notes visible for your role.</div>
          ) : (
            <ul className="space-y-2 max-h-40 overflow-y-auto">
              {notes.slice(0, 4).map((n) => (
                <li key={n.driver_note_id} className="border-l-2 border-slate-200 pl-2" data-testid={`note-${n.driver_note_id}`}>
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-0.5">
                    {n.is_pinned && <PushPin size={10} weight="fill" className="text-amber-500" />}
                    <span>{n.note_type}</span>
                    <span>· {new Date(n.updated_at).toLocaleDateString()}</span>
                  </div>
                  {n.title && <div className="text-xs font-semibold text-slate-900">{n.title}</div>}
                  <div className="text-xs text-slate-700 line-clamp-2">{n.content}</div>
                </li>
              ))}
            </ul>
          )}
          {canWrite && (
            <div className="pt-2">
              <button data-testid="note-add" onClick={() => setAdding(true)} className="text-[11px] text-cyan-700 hover:underline inline-flex items-center gap-1">
                <NoteBlank size={11} /> Add note
              </button>
            </div>
          )}
        </>
      )}
    </ManagementCard>
  );
}
