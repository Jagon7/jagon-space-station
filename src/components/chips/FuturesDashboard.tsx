"use client";

import { useMemo, useState } from "react";
import { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine, Cell, Legend } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills } from "@/components/data-ui";

// [日期, 台指期近月收盤, 外資台指淨OI, 投信, 自營, 外資淨OI金額(千元), 外資小台淨OI, 散戶小台多空比%, 外資買權淨OI金額, 外資賣權淨OI金額, P/C成交量比, P/C未平倉比]
type Row = [string, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null];
type Range = "60" | "120" | "all";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const sg = (v: number | null | undefined, unit = "") => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toLocaleString()}${unit}`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-slate-400" : v > 0 ? "text-[#ef4444]" : "text-[#22c55e]");
const tip = { contentStyle: { background: "#0d1220", border: "1px solid #1e2a3a", fontSize: 12 }, labelStyle: { color: "#94a3b8" } };
const ax = { tick: { fill: "#475569", fontSize: 11 }, axisLine: false, tickLine: false } as const;

export default function FuturesDashboard() {
  const { data, error } = useStaticJson<{ rows: Row[] }>("chips/futures.json");
  const [range, setRange] = useState<Range>("120");
  const rows = useMemo(() => {
    const rs = (data?.rows ?? []).filter((r) => r[2] != null);
    return range === "all" ? rs : rs.slice(-Number(range));
  }, [data, range]);

  if (!data) return <div className="py-16 text-center text-sm text-slate-500 font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!rows.length) return <Empty>期貨籌碼資料累積中。</Empty>;
  const cur = rows.at(-1)!, prev = rows.at(-2);
  const optNet = cur[8] != null && cur[9] != null ? Math.round((cur[8] - cur[9]) / 1e5) / 10 : null; // 億元
  const chart = rows.map((r) => ({ d: r[0], px: r[1], f: r[2], retail: r[7], pc: r[11], call: r[8] == null ? null : r[8] / 1e5, put: r[9] == null ? null : r[9] / 1e5 }));

  return (
    <div>
      <Note>
        期交所每天公布的法人期貨、選擇權部位。<b>外資台指期淨未平倉</b>是外資在台指期貨上的多空口數（正＝偏多）；
        <b>散戶小台多空比</b>＝（小台總未平倉 − 三大法人淨部位）換算的散戶多空，常被當作反向指標（散戶越偏多、行情越容易回檔）；
        <b>P/C 未平倉比</b>＝賣權 ÷ 買權未平倉，越高代表越多人買保護。外資選擇權淨額＝買權淨未平倉金額 − 賣權淨未平倉金額（正＝偏多）。
      </Note>
      <KpiRow>
        <Kpi label={`${md(cur[0])} 外資台指期淨未平倉`} value={sg(cur[2])} unit="口" color={tone(cur[2])} sub={prev?.[2] != null && cur[2] != null ? `較前日 ${sg(cur[2] - prev[2])}` : undefined} />
        <Kpi label="散戶小台多空比" value={cur[7] == null ? "—" : `${cur[7] > 0 ? "+" : ""}${cur[7].toFixed(1)}%`} color={tone(cur[7] == null ? null : -cur[7])} sub="反向指標" />
        <Kpi label="P/C 未平倉比" value={cur[11] == null ? "—" : `${cur[11].toFixed(1)}%`} sub={cur[10] == null ? undefined : `成交量比 ${cur[10].toFixed(1)}%`} />
        <Kpi label="外資選擇權淨額" value={optNet == null ? "—" : `${optNet > 0 ? "+" : ""}${optNet} 億`} color={tone(optNet)} />
      </KpiRow>
      <div className="flex justify-end mb-3">
        <Pills<Range> value={range} onChange={setRange} options={[{ value: "60", label: "近 60 日" }, { value: "120", label: "近 120 日" }, { value: "all", label: "全部" }]} />
      </div>
      <div className="grid grid-cols-1 gap-4 mb-6">
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5">
          <div className="text-sm text-white font-semibold mb-3">外資台指期淨未平倉（口）與台指期價格</div>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chart} margin={{ top: 5, right: 0, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" vertical={false} />
              <XAxis dataKey="d" tickFormatter={md} {...ax} minTickGap={24} />
              <YAxis yAxisId="f" {...ax} />
              <YAxis yAxisId="p" orientation="right" domain={["auto", "auto"]} {...ax} />
              <Tooltip {...tip} formatter={(v, n) => [typeof v === "number" ? v.toLocaleString() : String(v), n === "f" ? "外資淨未平倉（口）" : "台指期"]} />
              <ReferenceLine yAxisId="f" y={0} stroke="#334155" />
              <Bar yAxisId="f" dataKey="f">{chart.map((r) => <Cell key={r.d} fill={(r.f ?? 0) >= 0 ? "#ef4444" : "#22c55e"} fillOpacity={0.7} />)}</Bar>
              <Line yAxisId="p" dataKey="px" stroke="#e2e8f0" dot={false} strokeWidth={1.5} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5">
            <div className="text-sm text-white font-semibold mb-3">散戶小台多空比與 P/C 未平倉比（%）</div>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={chart} margin={{ top: 5, right: 0, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" vertical={false} />
                <XAxis dataKey="d" tickFormatter={md} {...ax} minTickGap={24} />
                <YAxis yAxisId="r" {...ax} />
                <YAxis yAxisId="pc" orientation="right" domain={["auto", "auto"]} {...ax} />
                <Tooltip {...tip} formatter={(v, n) => [`${typeof v === "number" ? v.toFixed(1) : v}%`, n === "retail" ? "散戶多空比" : "P/C 未平倉比"]} />
                <Legend formatter={(v) => <span className="text-xs text-slate-400">{v === "retail" ? "散戶小台多空比（左）" : "P/C 未平倉比（右）"}</span>} />
                <ReferenceLine yAxisId="r" y={0} stroke="#334155" />
                <Line yAxisId="r" dataKey="retail" stroke="#f59e0b" dot={false} strokeWidth={1.6} connectNulls />
                <Line yAxisId="pc" dataKey="pc" stroke="#a78bfa" dot={false} strokeWidth={1.6} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5">
            <div className="text-sm text-white font-semibold mb-3">外資臺指選擇權淨未平倉金額（億元）</div>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={chart} margin={{ top: 5, right: 0, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" vertical={false} />
                <XAxis dataKey="d" tickFormatter={md} {...ax} minTickGap={24} />
                <YAxis {...ax} />
                <Tooltip {...tip} formatter={(v, n) => [`${typeof v === "number" ? v.toFixed(2) : v} 億`, n === "call" ? "買權" : "賣權"]} />
                <Legend formatter={(v) => <span className="text-xs text-slate-400">{v === "call" ? "買權淨額（正＝看多）" : "賣權淨額（正＝看空）"}</span>} />
                <ReferenceLine y={0} stroke="#334155" />
                <Line dataKey="call" stroke="#ef4444" dot={false} strokeWidth={1.6} connectNulls />
                <Line dataKey="put" stroke="#22c55e" dot={false} strokeWidth={1.6} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-x-auto">
        <table className="w-full text-sm whitespace-nowrap">
          <thead>
            <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500 text-right">
              <th className="px-3 py-2.5 font-normal text-left">日期</th><th className="px-3 py-2.5 font-normal">台指期</th>
              <th className="px-3 py-2.5 font-normal">外資台指淨 OI</th><th className="px-3 py-2.5 font-normal">投信</th><th className="px-3 py-2.5 font-normal">自營</th>
              <th className="px-3 py-2.5 font-normal">外資小台</th><th className="px-3 py-2.5 font-normal">散戶多空比</th><th className="px-3 py-2.5 font-normal">P/C 未平倉</th>
            </tr>
          </thead>
          <tbody>
            {[...rows].reverse().slice(0, 20).map((r, i, arr) => (
              <tr key={r[0]} className="border-b border-[#1e2a3a]/60 last:border-0 text-right font-mono">
                <td className="px-3 py-2 text-left text-slate-300">{r[0]}</td>
                <td className="px-3 py-2 text-slate-300">{r[1]?.toLocaleString() ?? "—"}</td>
                <td className={`px-3 py-2 ${tone(r[2])}`}>{sg(r[2])}{arr[i + 1]?.[2] != null && r[2] != null ? <span className="text-[10px] text-slate-500 ml-1">({sg(r[2] - arr[i + 1][2]!)})</span> : null}</td>
                <td className={`px-3 py-2 ${tone(r[3])}`}>{sg(r[3])}</td>
                <td className={`px-3 py-2 ${tone(r[4])}`}>{sg(r[4])}</td>
                <td className={`px-3 py-2 ${tone(r[6])}`}>{sg(r[6])}</td>
                <td className={`px-3 py-2 ${tone(r[7] == null ? null : -r[7])}`}>{r[7] == null ? "—" : `${r[7].toFixed(1)}%`}</td>
                <td className="px-3 py-2 text-slate-300">{r[11] == null ? "—" : `${r[11].toFixed(1)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
