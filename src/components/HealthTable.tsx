"use client";

import { useState } from "react";

export type Level = "ok" | "warn" | "error";
export type Row = {
  level: Level; item: string; name: string; date: string | null; lag: number | null;
  count: number | null; weight?: number | null; note: string;
};

const DOT: Record<Level, string> = { ok: "bg-[#22c55e]", warn: "bg-[#f59e0b]", error: "bg-[#ef4444]" };
const TEXT: Record<Level, string> = { ok: "text-[#22c55e]", warn: "text-[#f59e0b]", error: "text-[#ef4444]" };
const LABEL: Record<Level, string> = { ok: "正常", warn: "留意", error: "異常" };
const ORDER: Record<Level, number> = { error: 0, warn: 1, ok: 2 };

export default function HealthTable({ rows }: { rows: Row[] }) {
  const n = (lv: Level) => rows.filter((r) => r.level === lv).length;
  const problems = rows.length - n("ok");
  const [onlyBad, setOnlyBad] = useState(problems > 0);
  const shown = (onlyBad ? rows.filter((r) => r.level !== "ok") : rows)
    .map((r, i) => ({ r, i })).sort((a, b) => ORDER[a.r.level] - ORDER[b.r.level] || a.i - b.i).map((x) => x.r);

  return (
    <div>
      <div className="grid grid-cols-2 lg:grid-cols-4 divide-x divide-y lg:divide-y-0 divide-[#1e2a3a] rounded-xl border border-[#1e2a3a] bg-[#0d1220] mb-8 overflow-hidden">
        {([["檢查項目", rows.length, "text-white"], ["正常", n("ok"), TEXT.ok], ["需留意", n("warn"), TEXT.warn], ["異常", n("error"), TEXT.error]] as const).map(([label, v, cls]) => (
          <div key={label} className="px-5 py-4">
            <div className="text-[11px] text-slate-500 mb-1.5">{label}</div>
            <div className={`font-mono text-3xl font-bold ${cls}`}>{v}</div>
          </div>
        ))}
      </div>

      <div className="flex gap-2 mb-4">
        {([[true, "只看有問題的"], [false, "全部"]] as const).map(([v, label]) => (
          <button key={label} onClick={() => setOnlyBad(v)}
            className={`px-4 py-2 rounded-lg text-sm border transition-colors ${onlyBad === v ? "border-[#00d4aa] text-[#00d4aa] bg-[#00d4aa]/10" : "border-[#1e2a3a] text-slate-400 hover:text-slate-200"}`}>
            {label}
          </button>
        ))}
      </div>

      {!shown.length ? (
        <div className="rounded-xl border border-[#22c55e]/30 bg-[#22c55e]/5 py-10 text-center text-sm text-[#22c55e]">全部 {rows.length} 項都正常 ✓</div>
      ) : (
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-x-auto">
          <table className="w-full text-sm whitespace-nowrap">
            <thead>
              <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500 text-left">
                <th className="px-4 py-3 font-normal">狀態</th><th className="px-4 py-3 font-normal">項目</th>
                <th className="px-4 py-3 font-normal">名稱</th><th className="px-4 py-3 font-normal">資料日</th>
                <th className="px-4 py-3 font-normal text-right">落後</th><th className="px-4 py-3 font-normal text-right">檔數</th>
                <th className="px-4 py-3 font-normal text-right">權重加總</th><th className="px-4 py-3 font-normal">說明</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={`${r.item}-${r.name}`} className="border-b border-[#1e2a3a]/60 last:border-0 hover:bg-[#111a2c]">
                  <td className="px-4 py-2.5"><span className={`inline-flex items-center gap-2 text-xs ${TEXT[r.level]}`}><span className={`w-2 h-2 rounded-full ${DOT[r.level]}`} />{LABEL[r.level]}</span></td>
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-300">{r.item}</td>
                  <td className="px-4 py-2.5 text-slate-200">{r.name}</td>
                  <td className="px-4 py-2.5 font-mono text-slate-300">{r.date ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-slate-400">{r.lag ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-slate-400">{r.count?.toLocaleString() ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-slate-400">{r.weight != null ? `${r.weight.toFixed(1)}%` : "—"}</td>
                  <td className="px-4 py-2.5 text-xs text-slate-400 whitespace-normal min-w-[14rem]">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
