import React, { useEffect, useMemo, useRef, useState } from "react";
import { MagnifyingGlass, CaretDown, Check, X } from "@phosphor-icons/react";
import api from "../../lib/api";

/**
 * Searchable driver dropdown. Stores driver_id; displays canonical
 * driver name + driver_number + company.
 *
 * Props:
 *  - value: string | "" (driver_id)
 *  - onChange: (driver_id, driver) => void
 *  - required?: boolean
 *  - testid?: string  (root testid; option testids derived from it)
 *  - allowClear?: boolean
 *  - drivers?: array — optional pre-fetched list; if not provided, fetches itself
 */
export default function DriverSelect({
  value,
  onChange,
  required = false,
  testid = "driver-select",
  allowClear = true,
  drivers: providedDrivers,
}) {
  const [drivers, setDrivers] = useState(providedDrivers || []);
  const [loading, setLoading] = useState(!providedDrivers);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef(null);

  useEffect(() => {
    if (providedDrivers) {
      setDrivers(providedDrivers);
      return;
    }
    let active = true;
    api
      .get("/modules/drivers")
      .then((r) => active && setDrivers(r.data || []))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [providedDrivers]);

  // close on outside click
  useEffect(() => {
    function onClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const selected = useMemo(
    () => drivers.find((d) => d.id === value) || null,
    [drivers, value]
  );

  const filtered = useMemo(() => {
    if (!query.trim()) return drivers;
    const q = query.toLowerCase();
    return drivers.filter((d) =>
      [d.name, d.driver_number, d.company, d.base, d.licence_number]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q))
    );
  }, [drivers, query]);

  const pick = (d) => {
    onChange(d.id, d);
    setOpen(false);
    setQuery("");
  };

  const clear = (e) => {
    e.stopPropagation();
    onChange("", null);
  };

  return (
    <div className="relative" ref={rootRef} data-testid={testid}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-testid={`${testid}-trigger`}
        className="w-full flex items-center justify-between gap-3 border border-gray-200 rounded-lg px-3 py-2.5 text-sm bg-white hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-900/10 focus:border-gray-900 transition-colors"
      >
        {selected ? (
          <div className="flex items-center gap-2 min-w-0 text-left">
            <span className="font-medium text-gray-900 truncate">
              {selected.name}
            </span>
            {selected.driver_number && (
              <span className="text-[10px] uppercase tracking-[0.15em] text-gray-500 border border-gray-200 rounded-full px-1.5 py-0.5 whitespace-nowrap">
                {selected.driver_number}
              </span>
            )}
            {selected.company && (
              <span className="text-xs text-gray-500 truncate hidden sm:inline">
                · {selected.company}
              </span>
            )}
          </div>
        ) : (
          <span className="text-gray-400">
            {loading ? "Loading drivers…" : "Select a driver…"}
          </span>
        )}
        <div className="flex items-center gap-1 shrink-0">
          {allowClear && selected && (
            <span
              role="button"
              onClick={clear}
              data-testid={`${testid}-clear`}
              className="p-1 text-gray-400 hover:text-gray-900 rounded"
            >
              <X size={14} />
            </span>
          )}
          <CaretDown
            size={14}
            className={`text-gray-400 transition-transform ${
              open ? "rotate-180" : ""
            }`}
          />
        </div>
      </button>

      {required && !value && (
        <input
          type="text"
          required
          value=""
          onChange={() => {}}
          tabIndex={-1}
          aria-hidden="true"
          className="absolute inset-0 opacity-0 pointer-events-none"
        />
      )}

      {open && (
        <div className="absolute z-30 mt-2 left-0 right-0 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 flex flex-col overflow-hidden">
          <div className="p-2 border-b border-gray-100 relative">
            <MagnifyingGlass
              size={14}
              className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400"
            />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search drivers…"
              data-testid={`${testid}-search`}
              className="w-full pl-7 pr-2 py-1.5 text-sm border-0 focus:outline-none focus:ring-0 placeholder:text-gray-400"
            />
          </div>
          <div className="overflow-y-auto">
            {filtered.length === 0 && (
              <div className="px-4 py-6 text-sm text-gray-500 text-center">
                {loading ? "Loading…" : "No drivers match this search."}
              </div>
            )}
            {filtered.map((d) => {
              const isActive = d.id === value;
              return (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => pick(d)}
                  data-testid={`${testid}-option-${d.id}`}
                  className={`w-full text-left px-4 py-2.5 flex items-center justify-between gap-3 hover:bg-gray-50 transition-colors ${
                    isActive ? "bg-gray-50" : ""
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">
                      {d.name}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {[d.driver_number, d.company, d.base]
                        .filter(Boolean)
                        .join(" · ") || d.email || ""}
                    </div>
                  </div>
                  {isActive && <Check size={14} className="text-gray-900" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
