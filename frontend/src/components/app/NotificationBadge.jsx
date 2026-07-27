import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../../lib/api";
import { Warning } from "@phosphor-icons/react";
import { SEVERITY_DOT, highestSeverity } from "../../lib/notifications";

/**
 * Compact notification indicator used across canonical DCC modules.
 *
 * Fetches active (non-resolved, non-archived) notifications for the given
 * filter and renders a small chip showing:
 *   - the total active count
 *   - the worst severity dot
 *
 * The chip is a Link to the Notifications Centre filtered view. If the
 * caller has already loaded notifications (e.g. Hub aggregates), they can
 * pass `notifications` directly to avoid an extra fetch.
 */
export default function NotificationBadge({
  entityType,
  entityId,
  severity,
  status,
  eventType,
  label,
  linkTo,
  notifications,
  testid,
  compact = false,
}) {
  const [items, setItems] = useState(notifications || null);
  const [loading, setLoading] = useState(!notifications);

  useEffect(() => {
    if (notifications) {
      setItems(notifications);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    const params = {};
    if (entityType) params.entity_type = entityType;
    if (entityId) params.entity_id = entityId;
    if (severity) params.severity = severity;
    if (status) params.status = status;
    if (eventType) params.event_type = eventType;
    api.get("/notifications", { params })
      .then(({ data }) => {
        if (!alive) return;
        // Exclude resolved unless explicitly requested by status filter
        const list = (data || []).filter(
          (n) => !n.is_archived && (status === "Resolved" || n.status !== "Resolved")
        );
        setItems(list);
      })
      .catch(() => alive && setItems([]))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [entityType, entityId, severity, status, eventType, notifications]);

  const count = (items || []).length;
  const worst = highestSeverity(items || []);
  if (loading) {
    return (
      <span
        data-testid={testid ? `${testid}-loading` : "notification-badge-loading"}
        className="inline-flex items-center gap-1 text-[10px] text-slate-300"
      >
        …
      </span>
    );
  }
  if (count === 0) return null;

  const href = linkTo || _defaultLink({ entityType, entityId, severity, status });
  const dotCls = SEVERITY_DOT[worst] || "bg-slate-400";
  const tone = worst === "Critical"
    ? "bg-red-50 text-red-700 border-red-200"
    : worst === "High"
    ? "bg-orange-50 text-orange-800 border-orange-200"
    : worst === "Medium"
    ? "bg-amber-50 text-amber-800 border-amber-200"
    : "bg-slate-100 text-slate-700 border-slate-200";
  const content = (
    <span
      data-testid={testid || "notification-badge"}
      title={`${count} active ${count === 1 ? "alert" : "alerts"}${worst ? ` · worst ${worst}` : ""}`}
      className={`inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.15em] px-1.5 py-0.5 rounded-full border ${tone}`}
    >
      <span className={`inline-flex h-1.5 w-1.5 rounded-full ${dotCls}`} aria-hidden="true" />
      {!compact && <Warning size={10} weight="bold" />}
      <span>{count}{label ? ` ${label}` : ""}</span>
    </span>
  );
  return href ? (
    <Link
      to={href}
      data-testid={testid ? `${testid}-link` : "notification-badge-link"}
      className="inline-flex hover:opacity-80 transition-opacity"
    >
      {content}
    </Link>
  ) : content;
}

function _defaultLink({ entityType, entityId, severity, status }) {
  const params = new URLSearchParams();
  if (entityType) params.set("entity_type", entityType);
  if (entityId) params.set("entity_id", entityId);
  if (severity) params.set("severity", severity);
  if (status) params.set("status", status);
  const qs = params.toString();
  return qs ? `/notifications/all?${qs}` : "/notifications/all";
}
