"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown, Search } from "lucide-react";

export function Kpi({ label, value, unit, sub, color = "text-white" }: {
  label: string; value: React.ReactNode; unit?: string; sub?: React.ReactNode; color?: string;
}) {
  return (
    <div className="px-5 py-4">
      <div className="text-[11px] text-slate-500 mb-1.5">{label}</div>
      <div className={`font-mono text-2xl font-bold ${color}`}>
        {value}
        {unit && <span className="text-xs font-normal text-slate-500 ml-1">{unit}</span>}
        {sub && <span className="text-xs font-normal text-slate-500 ml-1.5">{sub}</span>}
      </div>
    </div>
  );
}

export function KpiRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 divide-x divide-y lg:divide-y-0 divide-[#1e2a3a] rounded-xl border border-[#1e2a3a] bg-[#0d1220] mb-6 overflow-hidden">
      {children}
    </div>
  );
}

export function Pills<T extends string>({ value, options, onChange }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-[#1e2a3a] bg-[#0d1220] p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`px-3 py-1 text-xs rounded-md transition-colors ${
            value === o.value ? "bg-[#00d4aa]/15 text-[#00d4aa]" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function KindBadge({ k }: { k: "A" | "P" }) {
  return k === "A" ? (
    <span className="text-[10px] px-1.5 py-px rounded border border-[#f59e0b]/40 text-[#f59e0b] bg-[#f59e0b]/10">主動</span>
  ) : (
    <span className="text-[10px] px-1.5 py-px rounded border border-slate-600/50 text-slate-500">被動</span>
  );
}

export type Suggestion = { code: string; name: string; hint?: string };

export function SearchBox({ placeholder, items, onPick, initial = "" }: {
  placeholder: string; items: Suggestion[]; onPick: (code: string) => void; initial?: string;
}) {
  const [q, setQ] = useState(initial);
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => {
    const s = q.trim().toUpperCase();
    if (!s) return [];
    const starts = items.filter((it) => it.code.toUpperCase().startsWith(s) || it.name.toUpperCase().startsWith(s));
    const rest = items.filter((it) => !starts.includes(it) && (it.code.toUpperCase().includes(s) || it.name.toUpperCase().includes(s)));
    return [...starts, ...rest].slice(0, 8);
  }, [q, items]);

  const pick = (code: string) => {
    onPick(code);
    setQ("");
    setOpen(false);
  };

  return (
    <div className="relative w-full sm:w-80">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
      <input
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const exact = items.find((it) => it.code.toUpperCase() === q.trim().toUpperCase());
            if (exact) pick(exact.code);
            else if (matches[0]) pick(matches[0].code);
          }
        }}
        placeholder={placeholder}
        className="w-full rounded-lg border border-[#1e2a3a] bg-[#0d1220] pl-9 pr-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-[#00d4aa]/60"
      />
      {open && matches.length > 0 && (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-[#1e2a3a] bg-[#0d1220] shadow-xl overflow-hidden">
          {matches.map((m) => (
            <button
              key={m.code}
              onMouseDown={(e) => { e.preventDefault(); pick(m.code); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-[#1e2a3a]"
            >
              <span className="text-slate-200">{m.name}</span>
              <span className="font-mono text-xs text-slate-500">{m.code}</span>
              {m.hint && <span className="ml-auto text-[11px] text-slate-500">{m.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export type Column<R> = {
  key: string;
  label: string;
  align?: "left" | "right";
  sort?: (r: R) => number | string | null;
  render: (r: R) => React.ReactNode;
  className?: string;
};

export function SortTable<R>({ rows, columns, initialSort, rowKey, limit, onRowClick, rank }: {
  rows: R[]; columns: Column<R>[]; initialSort?: { key: string; desc: boolean };
  rowKey: (r: R) => string; limit?: number; onRowClick?: (r: R) => void; rank?: boolean;
}) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [showAll, setShowAll] = useState(false);
  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort?.key);
    if (!col?.sort || !sort) return rows;
    const get = col.sort;
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -c : c;
    });
  }, [rows, columns, sort]);
  const shown = limit && !showAll ? sorted.slice(0, limit) : sorted;

  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500">
              {rank && <th className="pl-4 py-3 font-normal text-left w-8">#</th>}
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const Icon = !c.sort ? null : !active ? ChevronsUpDown : sort!.desc ? ChevronDown : ChevronUp;
                return (
                  <th
                    key={c.key}
                    onClick={() => c.sort && setSort({ key: c.key, desc: active ? !sort!.desc : true })}
                    className={`px-4 py-3 font-normal whitespace-nowrap ${c.align === "right" ? "text-right" : "text-left"} ${
                      c.sort ? "cursor-pointer select-none hover:text-slate-300" : ""
                    } ${active ? "text-[#00d4aa]" : ""}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.label}
                      {Icon && <Icon className="w-3 h-3 opacity-70" />}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr
                key={rowKey(r)}
                onClick={onRowClick ? () => onRowClick(r) : undefined}
                className={`border-b border-[#1e2a3a]/60 last:border-0 hover:bg-[#111a2c] ${onRowClick ? "cursor-pointer" : ""}`}
              >
                {rank && <td className="pl-4 py-2.5 font-mono text-xs text-slate-600">{i + 1}</td>}
                {columns.map((c) => (
                  <td key={c.key} className={`px-4 py-2.5 whitespace-nowrap ${c.align === "right" ? "text-right font-mono" : ""} ${c.className ?? ""}`}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {limit && sorted.length > limit && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="w-full py-2.5 text-xs text-slate-500 hover:text-[#00d4aa] border-t border-[#1e2a3a]"
        >
          {showAll ? "收合" : `顯示全部 ${sorted.length} 筆`}
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-[#1e2a3a] py-12 text-center text-sm text-slate-500">{children}</div>
  );
}

export function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-xs leading-relaxed text-slate-500 mb-5 max-w-4xl">{children}</p>;
}
