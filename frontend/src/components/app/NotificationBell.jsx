import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bell, CheckCircle, X } from "@phosphor-icons/react";
import api, { formatApiErrorDetail } from "../../lib/api";
import { toast } from "sonner";
import {
  SEVERITY_DOT, SEVERITY_STYLES, sourceLink, humanTime,
} from "../../lib/notifications";

/**
 * Header notification bell for DCC.
 *
 * Shows an unread count badge and a red/orange indicator when Critical
 * or High notifications exist. Dropdown lists the 10 most recent
 * unresolved notifications with source-record deep-links and a
 * Mark-All-Read action for the current user's notifications.
 *
 * Polls /api/notifications/counts every 60s while mounted.
 */
export default function NotificationBell() {
  const nav = useNavigate();
  const [counts, setCounts] = useState({ active: 0, unread: 0, critical: 0, high: 0 });
  const [recent, setRecent] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);

  const refreshCounts = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications/counts");
      setCounts(data || { active: 0, unread: 0, critical: 0, high: 0 });
    } catch (e) {
      // Silent — the bell must never break the header
    }
  }, []);

  const refreshRecent = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/notifications", {
        params: { include_archived: false },
      });
      // Filter out resolved/archived for the recent dropdown, keep top 10
      const list = (data || [])
        .filter((n) => n.status !== "Resolved" && !n.is_archived)
        .slice(0, 10);
      setRecent(list);
    } catch (e) {
      // Silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshCounts();
    const id = setInterval(refreshCounts, 60_000);
    return () => clearInterval(id);
  }, [refreshCounts]);

  useEffect(() => {
    if (open) refreshRecent();
  }, [open, refreshRecent]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const markRead = async (id) => {
    try {
      await api.put(`/notifications/${id}/read`);
      setRecent((p) => p.map((n) => (n.notification_id === id ? { ...n, is_read: true } : n)));
      refreshCounts();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const markAllRead = async () => {
    try {
      const unread = recent.filter((n) => !n.is_read);
      await Promise.all(unread.map((n) => api.put(`/notifications/${n.notification_id}/read`)));
      setRecent((p) => p.map((n) => ({ ...n, is_read: true })));
      refreshCounts();
      toast.success(`Marked ${unread.length} read`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const openSource = (n) => {
    setOpen(false);
    const l = sourceLink(n);
    if (l) nav(l);
  };

  const criticalHigh = counts.critical + counts.high;
  const badgeTone = counts.critical > 0
    ? "bg-red-500 text-white"
    : counts.high > 0
    ? "bg-orange-400 text-slate-900"
    : "bg-cyan-400 text-slate-900";

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications — ${counts.unread} unread`}
        data-testid="notification-bell"
        className="relative inline-flex items-center justify-center h-9 w-9 rounded-lg text-slate-200 hover:text-white border border-slate-700 hover:border-cyan-400 transition-colors focus:outline-none focus:ring-2 focus:ring-cyan-400/40"
      >
        <Bell size={18} weight={counts.unread > 0 ? "fill" : "regular"} />
        {counts.unread > 0 && (
          <span
            data-testid="notification-bell-badge"
            className={`absolute -top-1 -right-1 min-w-[18px] h-[18px] text-[10px] font-semibold rounded-full px-1 grid place-items-center ${badgeTone}`}
          >
            {counts.unread > 99 ? "99+" : counts.unread}
          </span>
        )}
        {criticalHigh > 0 && (
          <span
            aria-hidden="true"
            className={`absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full ${counts.critical > 0 ? "bg-red-500" : "bg-orange-400"} animate-pulse`}
          />
        )}
      </button>

      {open && (
        <div
          data-testid="notification-dropdown"
          className="absolute right-0 top-11 z-50 w-[380px] max-h-[520px] bg-white text-slate-900 border border-slate-200 rounded-xl shadow-lg overflow-hidden"
        >
          <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
            <div>
              <div className="font-display font-semibold text-slate-900 text-sm">Notifications</div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                {counts.active} active · {counts.unread} unread · {counts.critical} critical
              </div>
            </div>
            <button
              onClick={markAllRead}
              data-testid="notification-mark-all-read"
              disabled={recent.every((n) => n.is_read)}
              className="text-[11px] text-cyan-700 hover:text-cyan-900 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1"
            >
              <CheckCircle size={12} weight="bold" />
              Mark all read
            </button>
          </div>

          <div className="max-h-[380px] overflow-y-auto">
            {loading && (
              <div className="px-6 py-10 text-center text-xs text-slate-400" data-testid="notification-dropdown-loading">
                Loading…
              </div>
            )}
            {!loading && recent.length === 0 && (
              <div className="px-6 py-10 text-center text-xs text-slate-500" data-testid="notification-dropdown-empty">
                No unresolved notifications.
              </div>
            )}
            {!loading && recent.map((n) => (
              <div
                key={n.notification_id}
                data-testid={`notification-dropdown-row-${n.notification_id}`}
                className={`px-4 py-3 border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors ${n.is_read ? "" : "bg-cyan-50/30"}`}
              >
                <div className="flex items-start gap-2">
                  <span className={`mt-1 inline-flex h-2 w-2 rounded-full ${SEVERITY_DOT[n.severity] || "bg-slate-300"}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`inline-flex text-[9px] font-medium uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border ${SEVERITY_STYLES[n.severity] || SEVERITY_STYLES.Medium}`}>
                        {n.severity}
                      </span>
                      <span className="text-[10px] text-slate-500">{humanTime(n.last_triggered_at)}</span>
                    </div>
                    <div className="text-xs font-medium text-slate-900 truncate">{n.title}</div>
                    <div className="text-[11px] text-slate-500 line-clamp-2">{n.message}</div>
                    <div className="mt-1.5 flex items-center gap-3 text-[10px]">
                      {sourceLink(n) && (
                        <button
                          onClick={() => openSource(n)}
                          data-testid={`notification-dropdown-source-${n.notification_id}`}
                          className="text-cyan-700 hover:text-cyan-900 font-medium"
                        >
                          Open source
                        </button>
                      )}
                      {!n.is_read && (
                        <button
                          onClick={() => markRead(n.notification_id)}
                          data-testid={`notification-dropdown-read-${n.notification_id}`}
                          className="text-slate-500 hover:text-slate-800"
                        >
                          Mark read
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="px-4 py-2 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
            <Link
              to="/notifications/all"
              data-testid="notification-view-all"
              onClick={() => setOpen(false)}
              className="text-xs text-slate-700 hover:text-slate-900 font-medium"
            >
              View all
            </Link>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-slate-400 hover:text-slate-700"
              aria-label="Close"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
