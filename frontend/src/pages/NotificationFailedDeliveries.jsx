import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../lib/api";
import { ArrowClockwise, ArrowUpRight } from "@phosphor-icons/react";
import { formatDateTime } from "../lib/notifications";

/**
 * EB-07b — Failed deliveries / dead-letter view.
 *
 * Since EB-07a did not expose a public dead-letter listing endpoint, we
 * derive failed deliveries from the outbox filtered by Failed and Retry
 * Scheduled statuses. Retry action re-simulates via the outbox simulate-
 * success endpoint.
 */
export default function NotificationFailedDeliveries() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [failed, retry] = await Promise.all([
        api.get("/notification-outbox", { params: { status: "Failed" } }),
        api.get("/notification-outbox", { params: { status: "Retry Scheduled" } }),
      ]);
      setItems([...(failed.data || []), ...(retry.data || [])]);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const retryOne = async (id) => {
    try {
      await api.post(`/notification-outbox/${id}/simulate-success`);
      toast.success("Retried (simulated success)");
      refresh();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail));
    }
  };

  return (
    <section data-testid="failed-deliveries">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs text-slate-500">
          {loading ? "Loading…" : `${items.length} failed or retry-scheduled deliveries`}
        </div>
        <button onClick={refresh} data-testid="failed-refresh" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900">
          <ArrowClockwise size={12} /> Refresh
        </button>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                {["Channel", "Status", "Attempt", "Failure reason", "Next retry", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="px-4 py-14 text-center text-slate-400 text-sm">Loading…</td></tr>}
              {!loading && items.length === 0 && <tr><td colSpan={6} className="px-4 py-14 text-center text-slate-500 text-sm">No failed or retry-scheduled deliveries.</td></tr>}
              {!loading && items.map((d) => (
                <tr key={d.notification_delivery_id} data-testid={`failed-row-${d.notification_delivery_id}`}
                  className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-2 text-xs text-slate-700">{d.channel}</td>
                  <td className="px-4 py-2 text-xs">
                    <span className={`inline-flex text-[10px] font-medium uppercase tracking-[0.15em] px-2 py-0.5 rounded-full border ${d.delivery_status === "Failed" ? "bg-red-50 text-red-700 border-red-200" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
                      {d.delivery_status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">{d.attempt_number}</td>
                  <td className="px-4 py-2 text-xs text-slate-700 truncate max-w-[280px]">{d.failure_reason || "—"}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">{formatDateTime(d.next_retry_at)}</td>
                  <td className="px-4 py-2 text-right">
                    <button onClick={() => retryOne(d.notification_delivery_id)}
                      data-testid={`failed-retry-${d.notification_delivery_id}`}
                      className="inline-flex items-center gap-1 text-xs text-emerald-700 hover:text-emerald-900">
                      Retry <ArrowUpRight size={10} weight="bold" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
