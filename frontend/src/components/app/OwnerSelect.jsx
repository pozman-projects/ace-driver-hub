import React, { useEffect, useMemo, useRef, useState } from "react";
import { MagnifyingGlass, CaretDown, Check, X } from "@phosphor-icons/react";
import api from "../../lib/api";

/**
 * Searchable owner dropdown. Stores owner_id; displays owner name + type + ABN.
 * Mirrors DriverSelect structure so future refactors can converge.
 */
export default function OwnerSelect({
  value,
  onChange,
  required = false,
  testid = "owner-select",
  allowClear = true,
  owners: provided,
}) {
  const [owners, setOwners] = useState(provided || []);
  const [loading, setLoading] = useState(!provided);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef(null);

  useEffect(() => {
    if (provided) {
      setOwners(provided);
      return;
    }
    let active = true;
    api
      .get("/owners")
      .then((r) => active && setOwners(r.data || []))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [provided]);

  useEffect(() => {
    function onClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const selected = useMemo(
    () => owners.find((o) => o.id === value) || null,
    [owners, value]
  );

  const filtered = useMemo(() => {
    if (!query.trim()) return owners;
    const q = query.toLowerCase();
    return owners.filter((o) =>
      [o.name, o.abn, o.primary_contact_name, o.company_ref]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q))
    );
  }, [owners, query]);

  const pick = (o) => {
    onChange(o.id, o);
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
        className="w-full flex items-center justify-between gap-3 border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-white hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 focus:border-cyan-500 transition-colors"
      >
        {selected ? (
          <div className="flex items-center gap-2 min-w-0 text-left">
            <span className="font-medium text-slate-900 truncate">
              {selected.name}
            </span>
            {selected.owner_type && (
              <span className="text-[10px] uppercase tracking-[0.15em] text-slate-500 border border-slate-200 rounded-full px-1.5 py-0.5 whitespace-nowrap">
                {selected.owner_type}
              </span>
            )}
          </div>
        ) : (
          <span className="text-slate-400">
            {loading ? "Loading owners…" : "Select an owner…"}
          </span>
        )}
        <div className="flex items-center gap-1 shrink-0">
          {allowClear && selected && (
            <span
              role="button"
              onClick={clear}
              data-testid={`${testid}-clear`}
              className="p-1 text-slate-400 hover:text-slate-900 rounded"
            >
              <X size={14} />
            </span>
          )}
          <CaretDown size={14} className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
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
        <div className="absolute z-30 mt-2 left-0 right-0 bg-white border border-slate-200 rounded-lg shadow-lg max-h-80 flex flex-col overflow-hidden">
          <div className="p-2 border-b border-slate-100 relative">
            <MagnifyingGlass size={14} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search owners…"
              data-testid={`${testid}-search`}
              className="w-full pl-7 pr-2 py-1.5 text-sm border-0 focus:outline-none focus:ring-0 placeholder:text-slate-400"
            />
          </div>
          <div className="overflow-y-auto">
            {filtered.length === 0 && (
              <div className="px-4 py-6 text-sm text-slate-500 text-center">
                {loading ? "Loading…" : "No owners match this search."}
              </div>
            )}
            {filtered.map((o) => {
              const isActive = o.id === value;
              return (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => pick(o)}
                  data-testid={`${testid}-option-${o.id}`}
                  className={`w-full text-left px-4 py-2.5 flex items-center justify-between gap-3 hover:bg-slate-50 transition-colors ${
                    isActive ? "bg-slate-50" : ""
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-900 truncate">
                      {o.name}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {[o.owner_type, o.abn, o.primary_contact_name].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                  {isActive && <Check size={14} className="text-slate-900" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
