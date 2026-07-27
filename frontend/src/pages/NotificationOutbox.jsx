import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import { CHANNELS } from "../lib/notifications";
import { ArrowClockwise, CheckCircle, X } from "@phosphor-icons/react";
import { formatDateTime } from "../lib/notifications";

const STATUSES = [
  "Pending", "Queued", "Simulated", "Sent", "Delivered",
  "Failed", "Retry Scheduled", "Cancelled", "Suppressed",
];

export default function NotificationOutbox() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [channelFilter, setChannelFilter] = useState("all");
  const [detail, setDetail] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (channelFilter !== "all") params.channel = channelFilter;
      const { data } = await api.get("/notification-outbox", { params });
      setItems(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, [statusFilter, channelFilter]);
  useEffect(() => { refresh(); }, [refresh]);

  const simulate = async (id, kind) => {
    try {
      await api.post(`/notification-outbox/${id}/simulate-${kind}`, { reason: `Manual ${kind}` });
      toast.success(`Simulated ${kind}`);
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  return (
    <section data-testid="notification-outbox">
      <div className="bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded-lg px-4 py-3 leading-relaxed mb-3">
        <strong>Development Simulation Only.</strong> No external email or SMS
        provider is contacted. Rendered subjects and bodies are shown for
        inspection. Provider credentials are never displayed.
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="text-xs text-slate-500">Status</label>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          data-testid="outbox-status-filter"
          className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs bg-white">
          <option value="all">All</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <label className="text-xs text-slate-500 ml-2">Channel</label>
        <select value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)}
          data-testid="outbox-channel-filter"
          className="border border-slate-200 rounded-lg px-2 py-1.5 text-xs bg-white">
          <option value="all">All</option>{CHANNELS.map((c) => <option key={c}>{c}</option>)}
        </select>
        <button onClick={refresh} data-testid="outbox-refresh" className="ml-auto inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
          <ArrowClockwise size={12} /> Refresh
        </button>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {["Channel", "Provider", "Recipient", "Rendered subject", "Status", "Attempt", "Attempted", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={8} className="px-4 py-14 text-center text-slate-400 text-sm">Loading…</td></tr>}
              {!loading && items.length === 0 && <tr><td colSpan={8} className="px-4 py-14 text-center text-slate-500 text-sm">No deliveries match this filter.</td></tr>}
              {!loading && items.map((d) => (
                <tr key={d.notification_delivery_id} data-testid={`outbox-row-${d.notification_delivery_id}`}
                  className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-2 text-xs text-slate-700">{d.channel}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">{d.provider}</td>
                  <td className="px-4 py-2 text-xs text-slate-700 truncate max-w-[160px]">{d.rendered_subject || "—"}</td>
                  <td className="px-4 py-2 text-xs text-slate-500 truncate max-w-[220px]">{d.rendered_body}</td>
                  <td className="px-4 py-2">
                    <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${_tone(d.delivery_status)}`}>
                      {d.delivery_status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">{d.attempt_number}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">{formatDateTime(d.attempted_at)}</td>
                  <td className="px-4 py-2 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button onClick={() => setDetail(d)} data-testid={`outbox-view-${d.notification_delivery_id}`}
                        className="text-xs text-slate-600 hover:text-slate-900 px-2 py-1 rounded">View</button>
                      <button onClick={() => simulate(d.notification_delivery_id, "success")} data-testid={`outbox-sim-success-${d.notification_delivery_id}`}
                        className="text-xs text-emerald-700 hover:text-emerald-900 px-2 py-1 rounded">Success</button>
                      <button onClick={() => simulate(d.notification_delivery_id, "failure")} data-testid={`outbox-sim-failure-${d.notification_delivery_id}`}
                        className="text-xs text-red-700 hover:text-red-900 px-2 py-1 rounded">Fail</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {detail && <OutboxDetail delivery={detail} onClose={() => setDetail(null)} />}
    </section>
  );
}

function _tone(status) {
  if (status === "Sent" || status === "Delivered") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "Simulated") return "bg-blue-50 text-blue-700 border-blue-200";
  if (status === "Failed") return "bg-red-50 text-red-700 border-red-200";
  if (status === "Retry Scheduled") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-slate-100 text-slate-600 border-slate-200";
}

function OutboxDetail({ delivery, onClose }) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4" data-testid="outbox-detail" onClick={onClose}>
      <div className="bg-white w-full sm:max-w-xl rounded-xl shadow-xl border border-slate-200 max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div className="font-display font-semibold text-slate-900">Delivery detail</div>
          <button onClick={onClose} className="p-1.5 rounded-md text-slate-400 hover:text-slate-900"><X size={14} /></button>
        </div>
        <div className="px-5 py-4 overflow-y-auto text-sm space-y-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Rendered subject</div>
            <div className="text-slate-800 text-sm">{delivery.rendered_subject || "—"}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Rendered body</div>
            <pre className="text-slate-700 text-xs whitespace-pre-wrap font-sans">{delivery.rendered_body || "—"}</pre>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <MetaRow label="Channel" value={delivery.channel} />
            <MetaRow label="Provider" value={delivery.provider} />
            <MetaRow label="Status" value={delivery.delivery_status} />
            <MetaRow label="Attempt" value={delivery.attempt_number} />
            <MetaRow label="Scheduled" value={formatDateTime(delivery.scheduled_at)} />
            <MetaRow label="Attempted" value={formatDateTime(delivery.attempted_at)} />
            <MetaRow label="Delivered" value={formatDateTime(delivery.delivered_at)} />
            <MetaRow label="Next retry" value={formatDateTime(delivery.next_retry_at)} />
            <MetaRow label="Failure" value={delivery.failure_reason || "—"} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetaRow({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.15em] text-slate-500">{label}</div>
      <div className="text-slate-800">{value || "—"}</div>
    </div>
  );
}
