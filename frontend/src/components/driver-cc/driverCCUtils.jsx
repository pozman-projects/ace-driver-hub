/**
 * EB-09.1 · Shared primitives + constants + helpers for the Driver Command Centre.
 * Extracted from the monolithic DriverCommandCentre.jsx during EB-09.1 refactor.
 * No behaviour change — pure component extraction.
 */
import React from "react";
import { Link } from "react-router-dom";
import { PencilSimple } from "@phosphor-icons/react";

// ── Role gates ───────────────────────────────────────────────────────────────
export const ROLE_CAN_EDIT_ACCOUNT = new Set(["Admin", "Manager"]);
export const ROLE_CAN_EDIT = new Set(["Admin", "Manager", "Allocator"]);

// ── Status helpers ───────────────────────────────────────────────────────────
export function statusVariant(status) {
  if (!status) return "neutral";
  const s = status.toLowerCase();
  if (["expired", "missing", "not ready", "rejected", "critical"].some((k) => s.includes(k))) return "danger";
  if (["due soon", "expiring", "partial", "under review", "on leave"].some((k) => s.includes(k))) return "warn";
  if (["compliant", "ok", "active", "ready"].some((k) => s.includes(k))) return "ok";
  return "neutral";
}

export function StatusPill({ status, compact, testid }) {
  const map = {
    Compliant: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Active: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Ready: "bg-emerald-50 text-emerald-700 border-emerald-200",
    "Due Soon": "bg-amber-50 text-amber-700 border-amber-200",
    "On Leave": "bg-amber-50 text-amber-700 border-amber-200",
    Partial: "bg-amber-50 text-amber-700 border-amber-200",
    "Under Review": "bg-blue-50 text-blue-700 border-blue-200",
    Expired: "bg-red-50 text-red-700 border-red-200",
    Missing: "bg-red-50 text-red-700 border-red-200",
    "Not Ready": "bg-red-50 text-red-700 border-red-200",
    Rejected: "bg-red-50 text-red-700 border-red-200",
    Inactive: "bg-slate-100 text-slate-700 border-slate-200",
    Archived: "bg-slate-100 text-slate-500 border-slate-200",
    "Not Applicable": "bg-slate-50 text-slate-500 border-slate-200",
  };
  const cls = map[status] || "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span
      data-testid={testid || `pill-${status || "unknown"}`}
      className={`inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.15em] ${compact ? "px-2 py-0.5" : "px-3 py-1"} rounded-full border ${cls}`}
    >
      <span className="inline-flex h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {status || "Unknown"}
    </span>
  );
}

// ── Layout primitives ────────────────────────────────────────────────────────
export function ManagementRow({ children }) {
  return <div className="grid grid-cols-1 md:grid-cols-3 gap-4">{children}</div>;
}

export function ManagementCard({
  title, subtitle, testid, section, canEdit = true, editing, onEditToggle,
  saving, dirty, onSave, onCancel, footer, children,
}) {
  const askIfDirty = (proceed) => {
    if (dirty && !window.confirm("Discard unsaved changes on this card?")) return;
    proceed();
  };
  return (
    <div
      className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col h-full min-h-[220px]"
      data-testid={testid}
      data-section={section}
    >
      <div className="px-4 pt-4 pb-3 border-b border-slate-100 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{title}</div>
          {subtitle && <div className="text-[11px] text-slate-500 mt-0.5 truncate">{subtitle}</div>}
        </div>
        {canEdit && (
          editing ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                data-testid={`${testid}-cancel`}
                onClick={() => askIfDirty(onCancel)}
                className="text-[11px] px-2 py-1 rounded text-slate-600 hover:text-slate-900"
              >Cancel</button>
              <button
                type="button"
                data-testid={`${testid}-save`}
                disabled={saving}
                onClick={onSave}
                className="text-[11px] px-2.5 py-1 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
              >{saving ? "Saving…" : "Save"}</button>
            </div>
          ) : (
            <button
              type="button"
              data-testid={`${testid}-edit`}
              onClick={onEditToggle}
              className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-900"
            ><PencilSimple size={11} weight="bold" /> Edit</button>
          )
        )}
      </div>
      <div className="px-4 py-3 text-sm space-y-2 flex-1">{children}</div>
      {footer && <div className="px-4 py-3 border-t border-slate-100 text-xs text-slate-500">{footer}</div>}
    </div>
  );
}

export function RightCard({ title, testid, section, children }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={testid} data-section={section}>
      <div className="text-[10px] uppercase tracking-[0.22em] text-cyan-700 mb-2 flex items-center gap-1.5">
        <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
        {title}
      </div>
      <div className="space-y-1.5 text-sm">{children}</div>
    </div>
  );
}

export function InlineField({ label, value, testid, mono }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3 items-baseline">
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">{label}</div>
      <div data-testid={testid} className={`text-sm text-slate-900 ${mono ? "font-mono" : ""} break-words`}>
        {value == null || value === "" ? <span className="text-slate-300">—</span> : value}
      </div>
    </div>
  );
}

export function EditInput({ label, value, onChange, type = "text", testid }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mb-1">{label}</div>
      <input
        type={type}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testid}
        className="w-full border border-slate-200 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500"
      />
    </label>
  );
}

export function ToggleRow({ label, value, onChange, testid }) {
  return (
    <label className="flex items-center justify-between text-sm py-1">
      <span className="text-slate-700">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        data-testid={testid}
        onClick={() => onChange(!value)}
        className={`w-9 h-5 rounded-full transition-colors ${value ? "bg-cyan-500" : "bg-slate-300"}`}
      >
        <span className={`block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${value ? "translate-x-4" : "translate-x-0.5"} mt-0.5`} />
      </button>
    </label>
  );
}

export function HeaderBadge({ label, value, variant = "neutral", testid, linkTo }) {
  const cls = {
    ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
    warn: "border-amber-200 bg-amber-50 text-amber-800",
    danger: "border-red-200 bg-red-50 text-red-800",
    neutral: "border-slate-200 bg-white text-slate-800",
  }[variant];
  const Inner = (
    <div className={`rounded-lg border ${cls} px-3 py-1.5 min-w-[130px]`} data-testid={testid}>
      <div className="text-[9px] uppercase tracking-[0.2em] opacity-80">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
    </div>
  );
  return linkTo ? <Link to={linkTo}>{Inner}</Link> : Inner;
}

export function MiniStat({ label, value, variant = "neutral", testid }) {
  const cls = variant === "warn" ? "border-amber-200 text-amber-800 bg-amber-50"
    : variant === "ok" ? "border-emerald-200 text-emerald-800 bg-emerald-50"
    : "border-slate-200 text-slate-800 bg-slate-50";
  return (
    <div data-testid={testid} className={`border rounded px-2 py-1.5 ${cls}`}>
      <div className="text-[9px] uppercase tracking-[0.15em] opacity-80">{label}</div>
      <div className="text-sm font-semibold">{value ?? 0}</div>
    </div>
  );
}
