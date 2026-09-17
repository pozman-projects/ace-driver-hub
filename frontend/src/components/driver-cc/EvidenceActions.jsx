/**
 * EB-R03B-II · Inline evidence upload / replace controls for DCC cards.
 *
 * Small helper that renders Present/Missing + Open/Upload/Replace using
 * canonical Documents endpoints:
 *
 *   Upload  →  POST /api/documents/upload   (multipart, is_primary=true,
 *                                            wires evidence_document_id on
 *                                            the compliance record when the
 *                                            entity_type is one of
 *                                            EVIDENCE_HOLDERS)
 *   Replace →  POST /api/documents/{id}/versions  (preserves version history)
 *   Open    →  GET  /api/documents/{id}/preview   (blob → new window)
 *
 * The parent card owns the "canEdit" check. This helper is presentation-only.
 * No file/blob is ever stored on the parent record.
 */
import React, { useRef, useState } from "react";
import { toast } from "sonner";
import { CloudArrowUp, ArrowsClockwise, FileArrowDown } from "@phosphor-icons/react";
import api, { formatApiErrorDetail } from "../../lib/api";

export function EvidencePill({ present, testid }) {
  return (
    <span
      data-testid={testid}
      className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.14em] px-2 py-0.5 rounded-full border ${
        present
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : "bg-slate-100 text-slate-500 border-slate-200"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${present ? "bg-emerald-500" : "bg-slate-400"}`} />
      {present ? "Present" : "Missing"}
    </span>
  );
}

async function openDocumentInNewWindow(documentId) {
  const res = await api.get(`/documents/${documentId}/preview`, { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const w = window.open(url, "_blank", "noopener,noreferrer");
  // Best-effort revoke; blob is only needed while the tab loads it.
  if (w) setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/**
 * Props:
 *   evidenceDoc          — the current canonical Document (or null / undefined)
 *   canEdit              — bool; hide mutation actions when false
 *   uploadPayload        — plain object of extra multipart fields (entity_type,
 *                          entity_id, document_type, title, is_primary,
 *                          relationship_type, sensitivity ...) — required for
 *                          the Upload path only
 *   acceptHint           — HTML accept="" hint (e.g. "image/*" or ".pdf,image/*")
 *   onChanged            — async callback after successful mutation so the
 *                          parent DCC page can refresh its payload
 *   testidPrefix         — prefix for data-testid attributes
 */
export default function EvidenceActions({
  evidenceDoc,
  canEdit,
  uploadPayload,
  acceptHint = ".pdf,image/*",
  onChanged,
  testidPrefix,
}) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const present = !!evidenceDoc?.id;
  const docId = evidenceDoc?.id;

  const trigger = () => inputRef.current?.click();

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (present) {
        // Replace: canonical version endpoint. Preserves history.
        form.append("change_note", `Replaced via DCC (${new Date().toISOString()})`);
        await api.post(`/documents/${docId}/versions`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        toast.success("Evidence replaced");
      } else {
        // Upload: canonical create-with-file. Wires evidence_document_id
        // where the entity_type is one of EVIDENCE_HOLDERS on the backend.
        Object.entries(uploadPayload || {}).forEach(([k, v]) => {
          if (v !== undefined && v !== null && v !== "") form.append(k, String(v));
        });
        await api.post(`/documents/upload`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        toast.success("Evidence uploaded");
      }
      await onChanged?.();
    } catch (err) {
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        toast.error("You do not have permission to upload evidence");
      } else {
        toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Upload failed");
      }
    } finally {
      setBusy(false);
    }
  };

  const onOpen = async () => {
    if (!docId) return;
    try {
      await openDocumentInNewWindow(docId);
    } catch (err) {
      const status = err?.response?.status;
      if (status === 401 || status === 403) toast.error("You cannot preview this evidence");
      else if (status === 404 || status === 410) toast.error("Evidence file not found");
      else toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Open failed");
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 pt-2" data-testid={`${testidPrefix}-actions`}>
      <EvidencePill present={present} testid={`${testidPrefix}-pill`} />
      {present && (
        <button
          type="button"
          onClick={onOpen}
          data-testid={`${testidPrefix}-open`}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded border border-cyan-200 bg-white text-cyan-700 hover:bg-cyan-50"
        >
          <FileArrowDown size={11} /> Open
        </button>
      )}
      {canEdit && (
        <button
          type="button"
          onClick={trigger}
          disabled={busy}
          data-testid={`${testidPrefix}-${present ? "replace" : "upload"}`}
          className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded border ${
            busy
              ? "border-slate-200 bg-slate-50 text-slate-400"
              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
          }`}
        >
          {present ? <ArrowsClockwise size={11} /> : <CloudArrowUp size={11} />}
          {busy ? "Uploading…" : present ? "Replace" : "Upload"}
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={acceptHint}
        onChange={onFile}
        className="hidden"
        data-testid={`${testidPrefix}-file-input`}
      />
    </div>
  );
}
