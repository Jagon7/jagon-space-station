"use client";

import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, ChevronUp, ChevronsUpDown } from "lucide-react";

export type XColumn<R> = {
  key: string;
  label: string;
  align?: "left" | "right";
  sort?: (r: R) => number | string | null | undefined;
  render: (r: R) => React.ReactNode;
};

/** 可排序、點一列展開細節的表格 */
export default function ExpandTable<R>({ rows, columns, rowKey, detail, initialSort, limit = 100 }: {
  rows: R[]; columns: XColumn<R>[]; rowKey: (r: R) => string; detail: (r: R) => React.ReactNode;
  initialSort?: { key: string; desc: boolean }; limit?: number;
}) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [open, setOpen] = useState<string | null>(null);
  const [all, setAll] = useState(false);
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
  const shown = all ? sorted : sorted.slice(0, limit);

  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm whitespace-nowrap">
          <thead>
            <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500">
              <th className="pl-4 py-2.5 font-normal text-left w-8">#</th>
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const Icon = !c.sort ? null : !active ? ChevronsUpDown : sort!.desc ? ChevronDown : ChevronUp;
                return (
                  <th key={c.key} onClick={() => c.sort && setSort({ key: c.key, desc: active ? !sort!.desc : true })}
                    className={`px-3 py-2.5 font-normal ${c.align === "right" ? "text-right" : "text-left"} ${c.sort ? "cursor-pointer select-none hover:text-slate-300" : ""} ${active ? "text-[#00d4aa]" : ""}`}>
                    <span className="inline-flex items-center gap-1">{c.label}{Icon && <Icon className="w-3 h-3 opacity-70" />}</span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => {
              const k = rowKey(r);
              const isOpen = open === k;
              return (
                <Fragment key={k}>
                  <tr onClick={() => setOpen(isOpen ? null : k)} className={`border-b border-[#1e2a3a]/60 cursor-pointer hover:bg-[#111a2c] ${isOpen ? "bg-[#0a0f1a]" : ""}`}>
                    <td className="pl-4 py-2 text-xs text-slate-600">
                      <span className="inline-flex items-center gap-1">{isOpen ? <ChevronDown className="w-3.5 h-3.5 text-[#00d4aa]" /> : <ChevronRight className="w-3.5 h-3.5" />}{i + 1}</span>
                    </td>
                    {columns.map((c) => (
                      <td key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right font-mono" : ""}`}>{c.render(r)}</td>
                    ))}
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-[#1e2a3a]/60 bg-[#0a0f1a]">
                      <td colSpan={columns.length + 1} className="px-4 py-3 whitespace-normal">{detail(r)}</td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {sorted.length > limit && (
        <button onClick={() => setAll(!all)} className="w-full py-2.5 text-xs text-slate-500 hover:text-[#00d4aa] border-t border-[#1e2a3a]">
          {all ? "收合" : `顯示全部 ${sorted.length} 筆`}
        </button>
      )}
    </div>
  );
}

export function StockCell({ code, name, mk }: { code: string; name: string; mk?: string }) {
  return (
    <span>
      <span className="text-slate-200">{name}</span>
      <span className="ml-1.5 font-mono text-xs text-slate-500">{code}</span>
      {mk === "上櫃" && <span className="ml-1 text-[10px] text-slate-600">櫃</span>}
    </span>
  );
}
