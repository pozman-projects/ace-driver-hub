/**
 * EB-R01C · Vehicle Compliance summary view.
 *
 * Minimal operational entry point. Consumes canonical compliance data
 * only via /api/compliance/overview?entity_type=vehicle. Does NOT create
 * records, business logic or a new data store. Drills through to the
 * existing canonical compliance record pages.
 *
 * Prime Mover / Tray / Trailer roll-ups derive from canonical
 * `vehicle_type` on vehicles_register. Where a component is not yet
 * exposed as a canonical output, the tile shows "Not yet available"
 * per Blueprint — no temporary inference logic.
 */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Truck, ShieldCheck, Wrench, Warning, Toolbox } from "@phosphor-icons/react";
import AppHeader from "../components/app/AppHeader";
import api from "../lib/api";

const STATUS_STYLE = {
  Compliant: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Warning: "bg-amber-50 text-amber-700 border-amber-200",
  Expired: "bg-red-50 text-red-700 border-red-200",
  Missing: "bg-slate-100 text-slate-700 border-slate-300",
  Unknown: "bg-slate-100 text-slate-500 border-slate-200",
};

function StatusBadge({ status, testid }) {
  const s = status || "Unknown";
  return (
    <span
      data-testid={testid}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-[0.15em] border ${STATUS_STYLE[s] || STATUS_STYLE.Unknown}`}
    >
      {s}
    </span>
  );
}

export default function VehicleCompliancePage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [totals, setTotals] = useState({});

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const r = await api.get("/compliance/overview", { params: { entity_type: "vehicle" } });
        if (!active) return;
        setRows(r.data?.vehicles || []);
        setTotals(r.data?.totals?.vehicles || {});
      } catch (e) {
        if (active) setError(e?.response?.data?.detail || "Unable to load vehicle compliance");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  // Canonical /api/compliance/overview currently returns per-vehicle
  // overall_status (used in the table below) and totals only. It does
  // NOT return a canonical Prime Mover aggregate nor a fleet Overall
  // aggregate. Per EB-R01C-FIX, no local status calculation is
  // performed here — those tiles show "Not yet available" until the
  // canonical service exposes them.

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <div
        data-testid="vehicle-compliance-page"
        className="max-w-[1400px] mx-auto px-6 pt-6 pb-16"
      >
        <div className="mb-4">
          <div className="text-[10px] uppercase tracking-[0.25em] text-cyan-600 mb-1">
            Operations · Fleet
          </div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">
            Vehicle Compliance
          </h1>
          <p className="text-sm text-slate-500 mt-1 max-w-2xl">
            Fleet-level operational compliance status. Data is sourced from
            canonical compliance services — no records are created here.
          </p>
        </div>

        {/* Component roll-up strip */}
        <section
          data-testid="vehicle-compliance-rollup"
          className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5"
        >
          <div
            data-testid="rollup-prime-mover"
            className="bg-white border border-slate-200 rounded-xl p-4"
          >
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-1.5">
              Prime Mover
            </div>
            <span
              data-testid="prime-mover-status"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-[0.15em] border bg-slate-100 text-slate-500 border-slate-200"
            >
              Not yet available
            </span>
            <div className="text-[11px] text-slate-500 mt-2">
              Prime Mover is not an explicit canonical aggregate output yet.
            </div>
          </div>
          <div
            data-testid="rollup-tray"
            className="bg-white border border-slate-200 rounded-xl p-4"
          >
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-1.5">
              Tray
            </div>
            <span
              data-testid="tray-status"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-[0.15em] border bg-slate-100 text-slate-500 border-slate-200"
            >
              Not yet available
            </span>
            <div className="text-[11px] text-slate-500 mt-2">
              Tray is not an explicit canonical component output yet.
            </div>
          </div>
          <div
            data-testid="rollup-trailer"
            className="bg-white border border-slate-200 rounded-xl p-4"
          >
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-1.5">
              Trailer
            </div>
            <span
              data-testid="trailer-status"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-[0.15em] border bg-slate-100 text-slate-500 border-slate-200"
            >
              Not yet available
            </span>
            <div className="text-[11px] text-slate-500 mt-2">
              Trailer is not an explicit canonical component output yet.
            </div>
          </div>
          <div
            data-testid="rollup-overall"
            className="bg-white border border-slate-200 rounded-xl p-4"
          >
            <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-1.5">
              Overall Vehicle Compliance
            </div>
            <span
              data-testid="overall-status"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase tracking-[0.15em] border bg-slate-100 text-slate-500 border-slate-200"
            >
              Not yet available
            </span>
            <div className="text-[11px] text-slate-500 mt-2">
              A canonical fleet-level aggregate is not yet exposed. Per-vehicle canonical overall_status is shown in the table below.
            </div>
          </div>
        </section>

        {/* Drill-down links */}
        <section
          data-testid="vehicle-compliance-drilldowns"
          className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2 mb-5"
        >
          {[
            { to: "/compliance/records/vehicle-registrations", label: "Registrations", icon: Truck, testid: "drilldown-vehicle-registrations" },
            { to: "/compliance/records/vehicle-insurance", label: "Insurance", icon: ShieldCheck, testid: "drilldown-vehicle-insurance" },
            { to: "/compliance/records/vehicle-inspections", label: "Inspections", icon: ShieldCheck, testid: "drilldown-vehicle-inspections" },
            { to: "/compliance/records/vehicle-defects", label: "Defects", icon: Warning, testid: "drilldown-vehicle-defects" },
            { to: "/compliance/records/vehicle-maintenance-tasks", label: "Maintenance Tasks", icon: Wrench, testid: "drilldown-vehicle-maintenance-tasks" },
          ].map((l) => {
            const Icon = l.icon;
            return (
              <Link
                key={l.to}
                to={l.to}
                data-testid={l.testid}
                className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-[12px] flex items-center gap-2 hover:border-cyan-300 hover:shadow group"
              >
                <div className="p-1.5 bg-cyan-50 text-cyan-700 rounded-md group-hover:bg-cyan-500 group-hover:text-white transition-colors">
                  <Icon size={14} />
                </div>
                <span className="truncate flex-1">{l.label}</span>
                <ArrowUpRight size={12} className="text-slate-300 group-hover:text-cyan-600" />
              </Link>
            );
          })}
        </section>

        {/* Per-vehicle table */}
        <section
          data-testid="vehicle-compliance-list"
          className="bg-white border border-slate-200 rounded-xl overflow-hidden"
        >
          <div className="px-4 py-2.5 flex items-center gap-3 border-b border-slate-100">
            <Toolbox size={16} className="text-slate-500" />
            <div className="text-[10px] uppercase tracking-[0.25em] font-semibold text-slate-600">
              Vehicles ({rows.length})
            </div>
            <div className="ml-auto text-[10px] text-slate-400 uppercase tracking-[0.2em]">
              Source: canonical /api/compliance/overview
            </div>
          </div>
          {loading && (
            <div data-testid="vehicle-compliance-loading" className="p-6 text-sm text-slate-500">
              Loading canonical vehicle compliance…
            </div>
          )}
          {error && (
            <div data-testid="vehicle-compliance-error" className="p-6 text-sm text-red-600">
              {error}
            </div>
          )}
          {!loading && !error && rows.length === 0 && (
            <div data-testid="vehicle-compliance-empty" className="p-6 text-sm text-slate-500">
              No canonical vehicles found.
            </div>
          )}
          {!loading && !error && rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium uppercase tracking-[0.15em] text-[10px]">Vehicle</th>
                    <th className="text-left px-4 py-2 font-medium uppercase tracking-[0.15em] text-[10px]">Type</th>
                    <th className="text-left px-4 py-2 font-medium uppercase tracking-[0.15em] text-[10px]">Overall</th>
                    <th className="text-left px-4 py-2 font-medium uppercase tracking-[0.15em] text-[10px]">Components</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((v) => (
                    <tr key={v.id} data-testid={`vehicle-row-${v.id}`}>
                      <td className="px-4 py-2 text-slate-900 font-medium">
                        {v.registration_number || v.vin || v.id}
                      </td>
                      <td className="px-4 py-2 text-slate-600">
                        {v.vehicle_type || "—"}
                      </td>
                      <td className="px-4 py-2">
                        <StatusBadge status={v.overall_status} testid={`row-overall-${v.id}`} />
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex flex-wrap gap-1">
                          {(v.components || []).map((c) => (
                            <span
                              key={c.component}
                              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] border border-slate-200 bg-white text-slate-600"
                            >
                              {c.label || c.component}: <StatusBadge status={c.status} />
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Totals footer */}
        {!loading && !error && Object.keys(totals).length > 0 && (
          <div
            data-testid="vehicle-compliance-totals"
            className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500"
          >
            {Object.entries(totals).map(([k, v]) => (
              <span key={k} className="px-2 py-1 rounded border border-slate-200 bg-white">
                {k}: <strong className="text-slate-900">{v}</strong>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
