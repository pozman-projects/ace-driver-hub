import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AppHeader from "../components/app/AppHeader";
import api, { formatApiErrorDetail } from "../lib/api";
import { Warning, Clock, CheckCircle, ArrowUpRight } from "@phosphor-icons/react";
import { toast } from "sonner";

const MODULE_LABELS = {
  licences: "Driver Licences",
  "truck-rego": "Driver Truck Rego",
  insurance: "Driver Insurance",
};

const FILTERS = [
  { key: "all", label: "All At Risk" },
  { key: "expired", label: "Expired" },
  { key: "expiring", label: "Expiring 30d" },
];

export default function Compliance() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [moduleFilter, setModuleFilter] = useState("all");

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .get("/compliance/expiring")
      .then((r) => active && setData(r.data))
      .catch((e) => toast.error(formatApiErrorDetail(e?.response?.data?.detail)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const records = data?.records || [];
  const totals = data?.totals || { expired: 0, expiring: 0, ok: 0 };
  const modules = data?.modules || {};

  const filtered = useMemo(() => {
    return records.filter((r) => {
      if (filter !== "all" && r.status !== filter) return false;
      if (moduleFilter !== "all" && r.module !== moduleFilter) return false;
      return true;
    });
  }, [records, filter, moduleFilter]);

  const tone =
    totals.expired > 0 ? "red" : totals.expiring > 0 ? "amber" : "green";
  const HeroIcon =
    tone === "red" ? Warning : tone === "amber" ? Clock : CheckCircle;
  const heroToneClass =
    tone === "red"
      ? "text-red-600 bg-red-50 border-red-200"
      : tone === "amber"
      ? "text-amber-600 bg-amber-50 border-amber-200"
      : "text-emerald-700 bg-emerald-50 border-emerald-200";

  return (
    <div className="min-h-screen bg-slate-50" data-testid="compliance-page">
      <AppHeader showBack />

      <main className="max-w-[1600px] mx-auto w-full px-6 lg:px-12 py-10">
        {/* Header */}
        <section className="mb-10 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <div className="flex items-start gap-5">
            <div className={`p-3 rounded-lg border ${heroToneClass}`}>
              <HeroIcon size={28} />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-2">
                Compliance Risk View
              </div>
              <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-semibold tracking-tight text-gray-900">
                Expiring Soon
              </h1>
              <p className="mt-3 text-gray-600 max-w-xl text-sm leading-relaxed">
                All licences, truck regos and insurance policies that are
                already expired or due within the next{" "}
                {data?.horizon_days ?? 30} days.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 lg:gap-4 lg:min-w-[420px]">
            <SummaryTile
              label="Expired"
              value={totals.expired}
              loaded={!loading}
              tone="red"
            />
            <SummaryTile
              label="Within 30d"
              value={totals.expiring}
              loaded={!loading}
              tone="amber"
            />
            <SummaryTile
              label="All Clear"
              value={totals.ok}
              loaded={!loading}
              tone="green"
            />
          </div>
        </section>

        {/* Filters */}
        <section className="mb-6 flex flex-wrap items-center gap-2 lg:gap-3">
          <span className="text-[10px] uppercase tracking-[0.2em] text-gray-500 mr-2">
            Filter
          </span>
          {FILTERS.map((f) => (
            <FilterChip
              key={f.key}
              label={f.label}
              active={filter === f.key}
              onClick={() => setFilter(f.key)}
              testid={`filter-status-${f.key}`}
            />
          ))}
          <div className="mx-3 h-5 w-px bg-gray-200 hidden sm:block" />
          <FilterChip
            label="All Modules"
            active={moduleFilter === "all"}
            onClick={() => setModuleFilter("all")}
            testid="filter-module-all"
          />
          {Object.keys(MODULE_LABELS).map((slug) => (
            <FilterChip
              key={slug}
              label={MODULE_LABELS[slug]}
              active={moduleFilter === slug}
              onClick={() => setModuleFilter(slug)}
              testid={`filter-module-${slug}`}
            />
          ))}
        </section>

        {/* Per-module summary chips */}
        <section className="mb-8 grid grid-cols-1 md:grid-cols-3 gap-4">
          {Object.keys(MODULE_LABELS).map((slug) => {
            const mod = modules[slug] || {
              expired: 0,
              expiring: 0,
              ok: 0,
              total: 0,
            };
            return (
              <Link
                key={slug}
                to={`/m/${slug}`}
                data-testid={`compliance-module-link-${slug}`}
                className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md hover:border-gray-300 transition-all group flex items-center justify-between"
              >
                <div>
                  <div className="text-[10px] uppercase tracking-[0.25em] text-gray-500 mb-1">
                    {MODULE_LABELS[slug]}
                  </div>
                  <div className="font-display text-2xl font-semibold text-gray-900">
                    {mod.total} records
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    <span className="text-red-600 font-medium">
                      {mod.expired}
                    </span>{" "}
                    expired ·{" "}
                    <span className="text-amber-600 font-medium">
                      {mod.expiring}
                    </span>{" "}
                    within 30d
                  </div>
                </div>
                <ArrowUpRight
                  size={18}
                  weight="bold"
                  className="text-gray-300 group-hover:text-gray-900 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all"
                />
              </Link>
            );
          })}
        </section>

        {/* Table */}
        <section
          className="bg-white border border-gray-200 rounded-xl overflow-hidden"
          data-testid="compliance-table-wrapper"
        >
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.2em] font-semibold text-gray-500">
              At-Risk Records · {filtered.length}
            </div>
            <div className="text-[11px] text-gray-400">
              {loading
                ? "Loading…"
                : `Showing ${filtered.length} of ${records.length}`}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="compliance-table">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {[
                    "Status",
                    "Module",
                    "Driver",
                    "Reference",
                    "Detail",
                    "Expiry Date",
                    "Days",
                    "",
                  ].map((h) => (
                    <th
                      key={h}
                      className="text-left px-6 py-3 text-[10px] uppercase tracking-[0.2em] font-semibold text-gray-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-6 py-16 text-center text-sm text-gray-500"
                    >
                      No records match this filter. All clear on this slice.
                    </td>
                  </tr>
                )}
                {filtered.map((r) => (
                  <tr
                    key={`${r.module}-${r.id}`}
                    data-testid={`compliance-row-${r.id}`}
                    className="border-b border-gray-100 last:border-0 hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="px-6 py-4 text-gray-700">
                      {MODULE_LABELS[r.module]}
                    </td>
                    <td className="px-6 py-4 text-gray-900 font-medium">
                      {r.driver_id ? (
                        <Link
                          to={`/drivers/${r.driver_id}`}
                          data-testid={`compliance-driver-link-${r.id}`}
                          className="hover:underline underline-offset-2"
                        >
                          {r.driver_name || r.title}
                        </Link>
                      ) : (
                        r.driver_name || r.title
                      )}
                    </td>
                    <td className="px-6 py-4 text-gray-600">
                      {r.subtitle || "—"}
                    </td>
                    <td className="px-6 py-4 text-gray-600">
                      {r.extra || "—"}
                    </td>
                    <td className="px-6 py-4 text-gray-700">
                      {r.expiry_date || "—"}
                    </td>
                    <td className="px-6 py-4">
                      {r.days_until == null ? (
                        <span className="text-gray-300">—</span>
                      ) : r.days_until < 0 ? (
                        <span className="text-red-600 font-medium">
                          {Math.abs(r.days_until)}d ago
                        </span>
                      ) : (
                        <span className="text-amber-600 font-medium">
                          in {r.days_until}d
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        to={`/m/${r.module}`}
                        data-testid={`compliance-open-${r.id}`}
                        className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 transition-colors"
                      >
                        Open
                        <ArrowUpRight size={12} weight="bold" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

function FilterChip({ label, active, onClick, testid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={
        active
          ? "px-3 py-1.5 rounded-full text-xs font-medium bg-gray-900 text-white border border-gray-900 transition-colors"
          : "px-3 py-1.5 rounded-full text-xs font-medium bg-white text-gray-600 border border-gray-200 hover:border-gray-400 hover:text-gray-900 transition-colors"
      }
    >
      {label}
    </button>
  );
}

function SummaryTile({ label, value, loaded, tone }) {
  const toneNumber =
    tone === "red"
      ? "text-red-600"
      : tone === "amber"
      ? "text-amber-600"
      : "text-emerald-700";
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-5 py-4">
      <div className="text-[10px] uppercase tracking-[0.2em] text-gray-500 mb-1.5">
        {label}
      </div>
      <div className={`font-display text-2xl font-semibold ${toneNumber}`}>
        {loaded ? value : "—"}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  if (status === "expired") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200">
        <span className="inline-flex h-1.5 w-1.5 rounded-full bg-red-500" />
        Expired
      </span>
    );
  }
  if (status === "expiring") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
        <span className="inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" />
        Due Soon
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
      <span className="inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
      OK
    </span>
  );
}
