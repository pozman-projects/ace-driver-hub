import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import {
  ArrowClockwise, ArrowUpRight, Bell, CheckCircle, Clock, Envelope,
  Gear, ListChecks, MagnifyingGlass, Play, ShieldWarning, SlidersHorizontal,
  Warning, X,
} from "@phosphor-icons/react";
import {
  SEVERITY_STYLES, SEVERITY_DOT, STATUS_STYLES, SEVERITIES, STATUSES,
  EVENT_TYPES, ENTITY_TYPES, MAX_SNOOZE_HOURS, SNOOZE_PRESETS,
  humanTime, formatDateTime, sourceLink,
} from "../lib/notifications";
import NotificationRules from "./NotificationRules";
import NotificationPreferences from "./NotificationPreferences";
import NotificationOutbox from "./NotificationOutbox";
import NotificationFailedDeliveries from "./NotificationFailedDeliveries";
import NotificationJobs from "./NotificationJobs";

const TABS = [
  { slug: "my", label: "My", icon: Bell, group: "list" },
  { slug: "all", label: "All", icon: ListChecks, group: "list" },
  { slug: "critical", label: "Critical & High", icon: ShieldWarning, group: "list" },
  { slug: "snoozed", label: "Snoozed", icon: Clock, group: "list" },
  { slug: "resolved", label: "Resolved", icon: CheckCircle, group: "list" },
  { slug: "rules", label: "Rules", icon: SlidersHorizontal, group: "admin" },
  { slug: "preferences", label: "Preferences", icon: Gear, group: "admin" },
  { slug: "outbox", label: "Delivery Outbox", icon: Envelope, group: "admin" },
  { slug: "failed", label: "Failed Deliveries", icon: Warning, group: "admin" },
  { slug: "jobs", label: "Job History", icon: Play, group: "admin" },
];

export default function NotificationsCentre() {
  const { user } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const { view } = useParams();
  const current = TABS.find((t) => t.slug === view) || TABS[0];
  const [overview, setOverview] = useState(null);
  const [detail, setDetail] = useState(null);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    api.get("/notifications/overview").then(({ data }) => setOverview(data)).catch(() => {});
    api.get("/notifications/counts").then(({ data }) => setUnread(data?.unread || 0)).catch(() => {});
  }, [location.pathname]);

  const openDetail = (notification_id) => setDetail(notification_id);
  const closeDetail = () => setDetail(null);

  const isAdmin = user?.role === "Admin" || user?.role === "Manager";
  const showAdmin = isAdmin || user?.role === "Compliance";

  return (
    <div className="min-h-screen bg-slate-50" data-testid="notifications-centre">
      <AppHeader showBack />
      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-6">
        <section className="mb-4">
          <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1 flex items-center gap-2">
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" />
            Notifications
          </div>
          <h1 className="font-display text-2xl lg:text-3xl font-semibold tracking-tight text-slate-900 leading-tight">
            Notifications Centre
            <span className="ml-3 text-sm text-slate-500 font-normal">
              {current.label}
            </span>
          </h1>
        </section>

        <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-5" data-testid="notification-summary">
          <SummaryTile label="Active" count={overview?.by_status?.Active ?? 0} tone="green" />
          <SummaryTile label="Unread" count={unread} tone="cyan" />
          <SummaryTile label="Critical" count={overview?.by_severity?.Critical ?? 0} tone="red" />
          <SummaryTile label="High" count={overview?.by_severity?.High ?? 0} tone="orange" />
          <SummaryTile label="Snoozed" count={overview?.by_status?.Snoozed ?? 0} tone="slate" />
          <SummaryTile label="Delivery Failures" count={overview?.delivery_failures ?? 0} tone="red" />
        </section>

        <nav
          data-testid="notifications-tabs"
          className="mb-5 border-b border-slate-200 flex flex-wrap items-center gap-1"
        >
          {TABS.filter((t) => t.group === "list" || showAdmin).map((t) => {
            const Icon = t.icon;
            const active = t.slug === current.slug;
            return (
              <Link
                key={t.slug}
                to={`/notifications/${t.slug}`}
                data-testid={`notif-tab-${t.slug}`}
                className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium uppercase tracking-[0.15em] border-b-2 transition-colors ${
                  active
                    ? "border-cyan-500 text-cyan-700"
                    : "border-transparent text-slate-500 hover:text-slate-900"
                }`}
              >
                <Icon size={14} weight={active ? "bold" : "regular"} />
                {t.label}
              </Link>
            );
          })}
        </nav>

        {current.group === "list" && (
          <ListView slug={current.slug} onOpen={openDetail} />
        )}
        {current.slug === "rules" && showAdmin && <NotificationRules />}
        {current.slug === "preferences" && <NotificationPreferences />}
        {current.slug === "outbox" && showAdmin && <NotificationOutbox />}
        {current.slug === "failed" && showAdmin && <NotificationFailedDeliveries />}
        {current.slug === "jobs" && showAdmin && <NotificationJobs />}
      </main>

      {detail && (
        <NotificationDetailDrawer
          notificationId={detail}
          onClose={closeDetail}
          onChanged={() => {
            // Trigger overview refresh
            api.get("/notifications/overview").then(({ data }) => setOverview(data)).catch(() => {});
          }}
        />
      )}
    </div>
  );
}

function _unreadTotal() { return 0; /* deprecated stub retained for compatibility */ }

function SummaryTile({ label, count, tone }) {
  const bg = tone === "green" ? "bg-emerald-50 text-emerald-700"
    : tone === "red" ? "bg-red-50 text-red-700"
    : tone === "orange" ? "bg-orange-50 text-orange-700"
    : tone === "cyan" ? "bg-cyan-50 text-cyan-700"
    : "bg-slate-100 text-slate-600";
  return (
    <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 shadow-sm" data-testid={`summary-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <div className="font-display text-2xl font-semibold text-slate-900">{count}</div>
        <span className={`inline-flex text-[10px] px-2 py-0.5 rounded-full font-medium uppercase tracking-[0.15em] ${bg}`}>·</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- list view
function ListView({ slug, onOpen }) {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [eventTypeFilter, setEventTypeFilter] = useState("all");
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      const url = slug === "my" ? "/notifications/my-notifications" : "/notifications";
      if (slug !== "my") {
        if (statusFilter !== "all") params.status = statusFilter;
        if (severityFilter !== "all") params.severity = severityFilter;
        if (eventTypeFilter !== "all") params.event_type = eventTypeFilter;
        if (entityTypeFilter !== "all") params.entity_type = entityTypeFilter;
        if (unreadOnly) params.unread_only = true;
        if (includeArchived) params.include_archived = true;
      }
      const { data } = await api.get(url, { params });
      let list = data || [];
      if (slug === "critical") list = list.filter((n) => n.severity === "Critical" || n.severity === "High");
      else if (slug === "snoozed") list = list.filter((n) => n.status === "Snoozed");
      else if (slug === "resolved") list = list.filter((n) => n.status === "Resolved");
      setItems(list);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [slug, statusFilter, severityFilter, eventTypeFilter, entityTypeFilter, unreadOnly, includeArchived]);

  useEffect(() => { refresh(); }, [refresh]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter((n) =>
      String(n.title || "").toLowerCase().includes(q) ||
      String(n.message || "").toLowerCase().includes(q) ||
      String(n.entity_type || "").toLowerCase().includes(q)
    );
  }, [items, search]);

  const showFilters = slug !== "my";
  const includeArchivedAllowed = slug === "resolved" || slug === "all";

  return (
    <>
      {showFilters && (
        <section className="mb-4 flex flex-wrap items-center gap-2" data-testid="notification-list-filters">
          <div className="relative">
            <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title / message / entity…"
              data-testid="notif-search"
              className="pl-8 pr-3 py-2 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 w-56"
            />
          </div>
          <FilterSelect testid="filter-status" value={statusFilter} onChange={setStatusFilter} options={["all", ...STATUSES]} label="All statuses" />
          <FilterSelect testid="filter-severity" value={severityFilter} onChange={setSeverityFilter} options={["all", ...SEVERITIES]} label="All severities" />
          <FilterSelect testid="filter-event-type" value={eventTypeFilter} onChange={setEventTypeFilter} options={["all", ...EVENT_TYPES]} label="All event types" />
          <FilterSelect testid="filter-entity-type" value={entityTypeFilter} onChange={setEntityTypeFilter} options={["all", ...ENTITY_TYPES]} label="All entities" />
          <label className="inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
            <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)}
              data-testid="filter-unread" className="rounded" />
            Unread only
          </label>
          {includeArchivedAllowed && (
            <label className="inline-flex items-center gap-2 text-xs text-slate-600 cursor-pointer select-none">
              <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)}
                data-testid="filter-archived" className="rounded" />
              Include archived
            </label>
          )}
          <button onClick={refresh} data-testid="notif-refresh"
            className="ml-auto inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
            <ArrowClockwise size={12} /> Refresh
          </button>
        </section>
      )}

      <section className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm" data-testid="notification-list">
        <div className="px-6 py-3 border-b border-slate-200 flex items-center justify-between text-xs text-slate-500">
          <div className="uppercase tracking-[0.2em] font-semibold">Notifications</div>
          <div className="text-[11px]">{loading ? "Loading…" : `${filtered.length} shown`}</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="notification-table">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {["Severity", "Title", "Entity", "Status", "First triggered", "Last triggered", ""].map((h) => (
                  <th key={h} className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={7} className="px-6 py-14 text-center text-sm text-slate-400" data-testid="notification-list-loading">Loading…</td></tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr><td colSpan={7} className="px-6 py-14 text-center text-sm text-slate-500" data-testid="notification-list-empty">No notifications match this view.</td></tr>
              )}
              {!loading && filtered.map((n) => (
                <tr key={n.notification_id || n.id}
                  data-testid={`notif-row-${n.notification_id || n.id}`}
                  className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors ${n.is_read ? "" : "bg-cyan-50/20"}`}>
                  <td className="px-6 py-3.5">
                    <span className={`inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${SEVERITY_STYLES[n.severity] || SEVERITY_STYLES.Medium}`}>
                      <span className={`inline-flex h-1.5 w-1.5 rounded-full ${SEVERITY_DOT[n.severity] || "bg-slate-400"}`} aria-hidden="true" />
                      {n.severity}
                    </span>
                  </td>
                  <td className="px-6 py-3.5 max-w-md">
                    <button
                      onClick={() => onOpen(n.notification_id)}
                      data-testid={`notif-open-${n.notification_id}`}
                      className="text-left"
                    >
                      <div className="text-sm font-medium text-slate-900 truncate">{n.title}</div>
                      <div className="text-[11px] text-slate-500 truncate">{n.message}</div>
                    </button>
                  </td>
                  <td className="px-6 py-3.5 text-xs text-slate-600">{n.entity_type}</td>
                  <td className="px-6 py-3.5">
                    <span className={`inline-flex text-[11px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${STATUS_STYLES[n.status] || ""}`}>
                      {n.status}
                    </span>
                    {!n.is_read && <span className="ml-2 inline-flex h-1.5 w-1.5 rounded-full bg-cyan-500" title="Unread" />}
                  </td>
                  <td className="px-6 py-3.5 text-xs text-slate-500">{humanTime(n.first_triggered_at)}</td>
                  <td className="px-6 py-3.5 text-xs text-slate-500">{humanTime(n.last_triggered_at)}</td>
                  <td className="px-6 py-3.5 text-right">
                    <button
                      onClick={() => onOpen(n.notification_id)}
                      data-testid={`notif-view-${n.notification_id}`}
                      className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900"
                    >
                      View <ArrowUpRight size={12} weight="bold" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function FilterSelect({ value, onChange, options, label, testid }) {
  return (
    <select
      value={value} onChange={(e) => onChange(e.target.value)}
      data-testid={testid}
      className="border border-slate-200 rounded-lg px-2 py-2 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
    >
      <option value="all">{label}</option>
      {options.filter((o) => o !== "all").map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// ---------------------------------------------------------------- detail drawer
function NotificationDetailDrawer({ notificationId, onClose, onChanged }) {
  const { user } = useAuth();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState(null); // ack | snooze | resolve

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/notifications/${notificationId}`);
      setData(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [notificationId]);

  useEffect(() => { refresh(); }, [refresh]);

  const canAck = user?.role !== "ReadOnly";
  const canSnooze = user?.role !== "ReadOnly";
  const canResolve = ["Admin", "Manager", "Compliance"].includes(user?.role);
  const canReopen = ["Admin", "Manager"].includes(user?.role);

  const markRead = async () => {
    await api.put(`/notifications/${notificationId}/read`);
    toast.success("Marked read");
    refresh(); onChanged?.();
  };

  const runAck = async (note) => {
    try {
      await api.post(`/notifications/${notificationId}/acknowledge`, { note: note || "" });
      toast.success("Acknowledged — source compliance status unchanged");
      setAction(null); refresh(); onChanged?.();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };
  const runSnooze = async (hours, reason) => {
    try {
      await api.post(`/notifications/${notificationId}/snooze`, { hours, reason });
      toast.success(`Snoozed for ${hours}h — source status unchanged`);
      setAction(null); refresh(); onChanged?.();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };
  const runResolve = async (reason) => {
    try {
      await api.post(`/notifications/${notificationId}/resolve`, { reason });
      toast.success("Resolved");
      setAction(null); refresh(); onChanged?.();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };
  const runReopen = async () => {
    try {
      await api.post(`/notifications/${notificationId}/reopen`);
      toast.success("Reopened");
      refresh(); onChanged?.();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  const src = data ? sourceLink(data) : null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex justify-end" data-testid="notification-detail" onClick={onClose}>
      <div className="w-full sm:max-w-[560px] bg-white shadow-xl border-l border-slate-200 h-full overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-slate-200 px-6 py-4 flex items-start justify-between z-10">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mb-1">Notification detail</div>
            {loading ? (
              <div className="font-display font-semibold text-slate-400">Loading…</div>
            ) : data ? (
              <>
                <div className="font-display font-semibold text-slate-900 truncate" data-testid="detail-title">{data.title}</div>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${SEVERITY_STYLES[data.severity] || SEVERITY_STYLES.Medium}`}>
                    {data.severity}
                  </span>
                  <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${STATUS_STYLES[data.status] || ""}`}>
                    {data.status}
                  </span>
                </div>
              </>
            ) : null}
          </div>
          <button onClick={onClose} data-testid="detail-close" className="p-2 rounded-md text-slate-400 hover:text-slate-900 hover:bg-slate-100">
            <X size={16} />
          </button>
        </div>

        {data && (
          <div className="p-6 space-y-5">
            <p className="text-sm text-slate-800 leading-relaxed" data-testid="detail-message">{data.message}</p>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <MetaRow label="Entity type" value={data.entity_type} />
              <MetaRow label="Entity id" value={<code className="text-[10px]">{data.entity_id}</code>} />
              <MetaRow label="First triggered" value={formatDateTime(data.first_triggered_at)} />
              <MetaRow label="Last triggered" value={formatDateTime(data.last_triggered_at)} />
              <MetaRow label="Next repeat" value={formatDateTime(data.next_repeat_at)} />
              <MetaRow label="Priority" value={data.priority} />
              {data.resolved_at && <MetaRow label="Resolved" value={formatDateTime(data.resolved_at)} />}
              {data.resolved_by && <MetaRow label="Resolved by" value={data.resolved_by} />}
            </div>

            <div className="flex flex-wrap items-center gap-2 border-y border-slate-100 py-3">
              {src && (
                <button
                  onClick={() => { onClose(); nav(src); }}
                  data-testid="detail-open-source"
                  className="inline-flex items-center gap-1 bg-slate-900 hover:bg-slate-800 text-white text-xs px-3 py-1.5 rounded-md"
                >
                  Open source <ArrowUpRight size={12} weight="bold" />
                </button>
              )}
              {!data.is_read && (
                <button onClick={markRead} data-testid="detail-mark-read"
                  className="inline-flex items-center gap-1 border border-slate-200 text-slate-700 hover:text-slate-900 hover:border-slate-400 text-xs px-3 py-1.5 rounded-md">
                  Mark read
                </button>
              )}
              {canAck && data.status !== "Resolved" && (
                <button onClick={() => setAction("ack")} data-testid="detail-ack-btn"
                  className="inline-flex items-center gap-1 border border-slate-200 text-blue-700 hover:text-blue-900 hover:border-blue-300 text-xs px-3 py-1.5 rounded-md">
                  Acknowledge
                </button>
              )}
              {canSnooze && data.status !== "Resolved" && (
                <button onClick={() => setAction("snooze")} data-testid="detail-snooze-btn"
                  className="inline-flex items-center gap-1 border border-slate-200 text-slate-700 hover:text-slate-900 hover:border-slate-400 text-xs px-3 py-1.5 rounded-md">
                  Snooze
                </button>
              )}
              {canResolve && data.status !== "Resolved" && (
                <button onClick={() => setAction("resolve")} data-testid="detail-resolve-btn"
                  className="inline-flex items-center gap-1 border border-emerald-200 text-emerald-700 hover:text-emerald-900 hover:border-emerald-400 text-xs px-3 py-1.5 rounded-md">
                  Resolve
                </button>
              )}
              {canReopen && data.status === "Resolved" && (
                <button onClick={runReopen} data-testid="detail-reopen-btn"
                  className="inline-flex items-center gap-1 border border-slate-200 text-slate-700 hover:text-slate-900 hover:border-slate-400 text-xs px-3 py-1.5 rounded-md">
                  Reopen
                </button>
              )}
            </div>

            <p className="text-[11px] text-slate-500 italic">
              Acknowledgement and snooze track operator awareness — they do not
              alter the underlying compliance record or its status.
            </p>

            <HistoryBlock label="Recipients" data-testid="detail-recipients"
              rows={data.recipients} render={(r) => (
                <div className="flex items-center justify-between gap-3">
                  <div className="text-slate-800 truncate">{r.display_name || r.email_address || r.mobile_number || "—"}</div>
                  <div className="text-[10px] text-slate-500 uppercase tracking-[0.15em]">{r.channel}</div>
                </div>
              )} />

            <HistoryBlock label="Delivery attempts" data-testid="detail-deliveries"
              rows={data.deliveries} render={(d) => (
                <div>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">
                      {d.channel} · {d.provider} · attempt {d.attempt_number}
                    </div>
                    <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-1.5 py-0.5 rounded border ${_deliveryTone(d.delivery_status)}`}>
                      {d.delivery_status}
                    </span>
                  </div>
                  {d.rendered_subject && <div className="text-xs text-slate-800 mt-1 truncate">{d.rendered_subject}</div>}
                  {d.rendered_body && <div className="text-[11px] text-slate-500 line-clamp-2">{d.rendered_body}</div>}
                  {d.failure_reason && <div className="text-[10px] text-red-600 mt-1">{d.failure_reason}</div>}
                </div>
              )} />

            <HistoryBlock label="Acknowledgements" data-testid="detail-acks"
              rows={data.acknowledgements} render={(a) => (
                <div>
                  <div className="text-xs text-slate-800">{a.acknowledged_by}</div>
                  <div className="text-[10px] text-slate-500">{formatDateTime(a.acknowledged_at)}</div>
                  {a.note && <div className="text-[11px] text-slate-600 italic mt-1">&ldquo;{a.note}&rdquo;</div>}
                </div>
              )} />

            <HistoryBlock label="Snoozes" data-testid="detail-snoozes"
              rows={data.snoozes} render={(s) => (
                <div>
                  <div className="text-xs text-slate-800">By {s.snoozed_by}</div>
                  <div className="text-[10px] text-slate-500">until {formatDateTime(s.snooze_until)}</div>
                  {s.reason && <div className="text-[11px] text-slate-600 italic mt-1">{s.reason}</div>}
                </div>
              )} />

            <HistoryBlock label="Escalations" data-testid="detail-escalations"
              rows={data.escalations} render={(e) => (
                <div>
                  <div className="text-xs text-slate-800">{e.escalation_level} · {e.from_severity} → {e.to_severity}</div>
                  <div className="text-[10px] text-slate-500">{formatDateTime(e.triggered_at)}</div>
                  {e.trigger_reason && <div className="text-[11px] text-slate-600 italic mt-1">{e.trigger_reason}</div>}
                </div>
              )} />
          </div>
        )}

        {action === "ack" && (
          <ActionDialog title="Acknowledge notification" onClose={() => setAction(null)}
            confirmLabel="Acknowledge" onConfirm={(f) => runAck(f.note)} fields={[
              { key: "note", label: "Note (optional)", type: "text" },
            ]}
            note="Acknowledgement does not resolve the source condition." testid="ack-dialog" />
        )}
        {action === "snooze" && data && (
          <SnoozeDialog notification={data} onClose={() => setAction(null)}
            onConfirm={runSnooze} />
        )}
        {action === "resolve" && (
          <ActionDialog title="Resolve notification" onClose={() => setAction(null)}
            confirmLabel="Resolve" onConfirm={(f) => runResolve(f.reason)} fields={[
              { key: "reason", label: "Resolution reason", type: "text", required: true },
            ]}
            note="Resolving closes this alert. Source records remain unchanged."
            testid="resolve-dialog" />
        )}
      </div>
    </div>
  );
}

function MetaRow({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">{label}</div>
      <div className="text-slate-800 mt-0.5">{value || "—"}</div>
    </div>
  );
}

function HistoryBlock({ label, rows, render, testid }) {
  const list = rows || [];
  return (
    <div data-testid={testid}>
      <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">{label} ({list.length})</div>
      {list.length === 0 ? (
        <div className="text-[11px] text-slate-400">None yet.</div>
      ) : (
        <div className="space-y-2">
          {list.map((r, i) => (
            <div key={r.job_id || r.id || r.notification_id || r.dead_letter_id || `row-${i}`} className="border border-slate-100 rounded-lg px-3 py-2">{render(r)}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function ActionDialog({ title, fields, confirmLabel, onConfirm, onClose, note, testid }) {
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  return (
    <div className="fixed inset-0 z-[60] bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4" data-testid={testid} onClick={onClose}>
      <div className="bg-white w-full sm:max-w-md rounded-xl shadow-xl border border-slate-200" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="font-display font-semibold text-slate-900 text-sm">{title}</div>
          <button onClick={onClose} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900"><X size={14} /></button>
        </div>
        <div className="px-5 py-4 space-y-3">
          {note && <div className="text-[11px] text-slate-500 italic">{note}</div>}
          {fields.map((f) => (
            <div key={f.key}>
              <label className="block text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-1">{f.label}{f.required && <span className="text-red-500 ml-1">*</span>}</label>
              <input
                type={f.type || "text"} value={form[f.key] || ""}
                onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                data-testid={`${testid}-field-${f.key}`}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
              />
            </div>
          ))}
        </div>
        <div className="px-5 py-4 border-t border-slate-100 flex justify-end gap-2">
          <button onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-md">Cancel</button>
          <button
            data-testid={`${testid}-confirm`}
            disabled={busy || fields.some((f) => f.required && !form[f.key])}
            onClick={async () => { setBusy(true); await onConfirm(form); setBusy(false); }}
            className="text-sm text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-1.5 rounded-md"
          >{busy ? "…" : confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

function SnoozeDialog({ notification, onClose, onConfirm }) {
  const [hours, setHours] = useState(24);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const max = MAX_SNOOZE_HOURS[notification.severity] || 168;

  const presets = SNOOZE_PRESETS.filter((p) => p.hours <= max);
  return (
    <div className="fixed inset-0 z-[60] bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4" data-testid="snooze-dialog" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-md rounded-xl shadow-xl border border-slate-200" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="font-display font-semibold text-slate-900 text-sm">Snooze notification</div>
          <button onClick={onClose} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900"><X size={14} /></button>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div className="text-[11px] text-slate-500 italic">
            Snoozing hides the alert temporarily. It does not change the source
            compliance record. Maximum snooze for <strong>{notification.severity}</strong> is <strong>{max}h</strong>.
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-1">Preset</label>
            <div className="flex flex-wrap gap-2">
              {presets.map((p) => (
                <button key={p.hours} type="button" onClick={() => setHours(p.hours)}
                  data-testid={`snooze-preset-${p.hours}`}
                  className={`text-xs border rounded-full px-3 py-1 ${hours === p.hours ? "border-cyan-500 bg-cyan-50 text-cyan-700" : "border-slate-200 text-slate-600 hover:border-slate-400"}`}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-1">Hours</label>
            <input type="number" value={hours} min={1} max={max}
              onChange={(e) => setHours(Math.max(1, Math.min(max, parseInt(e.target.value || "0", 10))))}
              data-testid="snooze-hours"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            {hours > max && (
              <div className="text-[10px] text-red-600 mt-1">Maximum {max}h for {notification.severity}.</div>
            )}
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500 mb-1">Reason (optional)</label>
            <input value={reason} onChange={(e) => setReason(e.target.value)}
              data-testid="snooze-reason"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
        <div className="px-5 py-4 border-t border-slate-100 flex justify-end gap-2">
          <button onClick={onClose} className="text-sm text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-md">Cancel</button>
          <button
            data-testid="snooze-confirm"
            disabled={busy || hours < 1 || hours > max}
            onClick={async () => { setBusy(true); await onConfirm(hours, reason); setBusy(false); }}
            className="text-sm text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-1.5 rounded-md"
          >{busy ? "…" : "Snooze"}</button>
        </div>
      </div>
    </div>
  );
}

function _deliveryTone(status) {
  if (status === "Sent" || status === "Delivered") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "Simulated") return "bg-blue-50 text-blue-700 border-blue-200";
  if (status === "Failed") return "bg-red-50 text-red-700 border-red-200";
  if (status === "Retry Scheduled") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}
