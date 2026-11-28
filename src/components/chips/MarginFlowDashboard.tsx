"use client";

import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Daily = { d: string; twChg: number; tw: number; otcChg: number; otc: number; totChg: number; tot: number; mLots: number; sLots: number;
  exM: number; exS: number; exSBal: number; ixPct: number | null };
type RankRow = { code: string; name: string; mk: string; etf: boolean; close: number; bal: number; sBal: number; usage: number | null; ratio: number | null;
  spark: (number | null)[]; px?: number | null; dm?: number; dmAmt?: number; ds?: number; tag?: string | null };
type Data = {
  date: string; daily: Daily[]; sum5: number; sum20: number;
  level: { tw: { now: number; pct5y: number | null; max5y: number | null }; twEx: { now: number; pct5y: number | null; max5y: number | null };
    otc: { now: number; pctShort: number | null; since: string }; mLotsTw: number; amt: number };
  usage: { usage: number; usagePct: number | null; ratio: number; ratioPct: number | null; since: string; sBal: number; mBal: number };
  periods: { n: number; mChg: number; upDays: number; sLots: number; ixPct: number | null }[];
  extremes: { up: [string, number, number | null][]; down: [string, number, number | null][] };
  chart: [string, number, number | null, number][];
  rank: Record<string, Record<string, RankRow[]>> & { usage: RankRow[]; ratio: RankRow[] };
  counts: { usage50: number; usage30: number; ratio30: number };
};
type Kind = "mUp" | "mDown" | "sUp" | "sDown" | "usage" | "ratio";
type Period = "1" | "5" | "20";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const sgn = (v: number, d = 2) => `${v > 0 ? "+" : ""}${v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const lots = (v: number) => `${v > 0 ? "+" : ""}${v.toLocaleString()}`;
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const ax = { tick: { fill: "#7c8aa0", fontSize: 11 }, stroke: "#334155" };
const TAG: Record<string, string> = { 斷頭: "bg-[#f05252]/15 text-[#f05252]", 攤平: "bg-[#f59e0b]/15 text-[#f59e0b]", 追價: "bg-[#4f8cff]/15 text-[#4f8cff]",
  洗籌: "bg-[#22c55e]/15 text-[#22c55e]" };

function Spark({ xs }: { xs: (number | null)[] }) {
  const v = xs.filter((x): x is number => x != null);
  if (v.length < 2) return null;
  const lo = Math.min(...v), hi = Math.max(...v), w = 64, h = 18;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - (hi > lo ? ((x - lo) / (hi - lo)) * h : h / 2)}`).join(" ");
  const up = v[v.length - 1] >= v[0];
  return (
    <svg width={w} height={h} className="inline-block align-middle">
      <polyline points={pts} fill="none" stroke="#64748b" strokeWidth="1" />
      <circle cx={w} cy={pts.split(" ").at(-1)!.split(",")[1]} r="2" fill={up ? "#f05252" : "#22c55e"} />
    </svg>
  );
}

export default function MarginFlowDashboard() {
  const { data, error } = useStaticJson<Data>("chips/margin-flow.json");
  const wl = useWatchlist();
  const [more, setMore] = useState(false);
  const [kind, setKind] = useState<Kind>("mUp");
  const [period, setPeriod] = useState<Period>("1");
  const [withEtf, setWithEtf] = useState(false);
  if (error) return <Empty>融資資料尚未產生。</Empty>;
  if (!data) return <Empty>載入中…</Empty>;
  const L = data.level, U = data.usage;
  const daily = more ? data.daily : data.daily.slice(0, 20);
  const rows: RankRow[] = (kind === "usage" || kind === "ratio" ? data.rank[kind] : data.rank[period]?.[kind] ?? []).filter((r) => withEtf || !r.etf);
  const pLab = period === "1" ? "單日" : `近 ${period} 日`;

  const cols: Column<RankRow>[] = [
    { key: "name", label: "股票", render: (r) => (
      <span className="whitespace-nowrap">
        <button onClick={() => wl.toggle(r.code)} className={`mr-1.5 ${wl.has(r.code) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
        <span className="text-slate-200">{r.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{r.code}</span>
        {r.etf && <span className="ml-1 text-[10px] px-1 rounded border border-[#22c55e]/40 text-[#22c55e]">ETF</span>}
      </span>) },
    { key: "close", label: "收盤", align: "right", sort: (r) => r.close, render: (r) => num(r.close) },
    ...(kind === "usage" || kind === "ratio" ? [] : [{ key: "px", label: `${pLab}股價`, align: "right" as const, sort: (r: RankRow) => r.px ?? null,
      render: (r: RankRow) => num(r.px != null ? `${sgn(r.px)}%` : "—", tone(r.px)) }]),
    { key: "bal", label: "融資餘額（張）", align: "right", sort: (r) => r.bal, render: (r) => num(r.bal.toLocaleString()) },
    ...(kind === "sUp" || kind === "sDown"
      ? [{ key: "ds", label: `${pLab}融券增減（張）`, align: "right" as const, sort: (r: RankRow) => r.ds ?? 0, render: (r: RankRow) => num(lots(r.ds ?? 0), tone(r.ds)) },
        { key: "sBal", label: "融券餘額", align: "right" as const, sort: (r: RankRow) => r.sBal, render: (r: RankRow) => num(r.sBal.toLocaleString()) }]
      : kind === "usage" || kind === "ratio" ? []
        : [{ key: "dm", label: `${pLab}增減（張）`, align: "right" as const, sort: (r: RankRow) => r.dm ?? 0, render: (r: RankRow) => num(lots(r.dm ?? 0), tone(r.dm)) },
          { key: "dmAmt", label: `${pLab}增減（億）`, align: "right" as const, sort: (r: RankRow) => r.dmAmt ?? 0, render: (r: RankRow) => num(sgn(r.dmAmt ?? 0), tone(r.dmAmt)) }]),
    { key: "usage", label: "使用率", align: "right", sort: (r) => r.usage, render: (r) => num(r.usage != null ? `${r.usage.toFixed(1)}%` : "—") },
    { key: "ratio", label: "券資比", align: "right", sort: (r) => r.ratio, render: (r) => num(r.ratio != null ? `${r.ratio.toFixed(1)}%` : "—") },
    ...(kind === "usage" || kind === "ratio" ? [] : [{ key: "tag", label: "判讀", render: (r: RankRow) => r.tag
      ? <span className={`text-[11px] px-1.5 py-0.5 rounded ${TAG[r.tag]}`}>{r.tag}</span> : <span className="text-[#475569]">—</span> }]),
    { key: "spark", label: "20 日融資", render: (r) => <Spark xs={r.spark} /> },
  ];

  return (
    <div>
      <KpiRow>
        <Kpi label="上市融資水位（不含台積電）" value={`${L.twEx.now?.toFixed(2)}%`} sub={L.twEx.pct5y != null ? `近 5 年第 ${L.twEx.pct5y} 百分位` : ""} />
        <Kpi label="上市融資水位（含台積電）" value={`${L.tw.now?.toFixed(2)}%`} sub={L.tw.pct5y != null ? `近 5 年第 ${L.tw.pct5y} 百分位` : ""} />
        <Kpi label="上櫃融資水位" value={`${L.otc.now?.toFixed(2)}%`} sub={L.otc.pctShort != null ? `${md(L.otc.since)} 起第 ${L.otc.pctShort} 百分位` : ""} />
        <Kpi label="融資使用率／券資比" value={<span className="text-xl">{U.usage?.toFixed(1)}%／{U.ratio?.toFixed(1)}%</span>}
          sub={`使用率 ≥ 50%：${data.counts.usage50} 檔`} />
      </KpiRow>

      <div className="mb-8">
        <div className="flex flex-wrap items-baseline gap-2 mb-2">
          <h3 className="text-sm font-semibold text-white">每日融資餘額</h3>
          <span className="text-[11px] text-[#8b97ab]">證交所、櫃買中心公布的融資金額（新聞「融資減少 xx 億」同一個數字）・近 5 日合計
            <span className={`ml-1 font-mono ${tone(data.sum5)}`}>{sgn(data.sum5)} 億</span>・近 20 日 <span className={`font-mono ${tone(data.sum20)}`}>{sgn(data.sum20)} 億</span></span>
        </div>
        <div className="overflow-x-auto rounded-xl border border-[#243247] bg-[#0d1220]">
          <table className="w-full text-xs font-mono whitespace-nowrap">
            <thead className="text-[#8b97ab] text-[11px]">
              <tr>
                <th rowSpan={2} className="text-left font-normal px-3 py-2 sticky left-0 bg-[#0d1220]">日期</th>
                <th colSpan={2} className="font-normal px-2 pt-2">上市融資</th><th colSpan={2} className="font-normal px-2 pt-2">上櫃融資</th>
                <th colSpan={2} className="font-normal px-2 pt-2">合計</th>
                <th rowSpan={2} className="font-normal px-2 text-right">融資張數<br />增減</th><th rowSpan={2} className="font-normal px-2 text-right">融券張數<br />增減</th>
                <th colSpan={3} className="font-normal px-2 pt-2">扣除 ETF（張）</th>
                <th rowSpan={2} className="font-normal px-3 text-right">加權指數</th>
              </tr>
              <tr>
                {["增減(億)", "餘額(億)", "增減(億)", "餘額(億)", "增減(億)", "餘額(億)", "融資增減", "融券增減", "融券餘額"].map((h, i) =>
                  <th key={i} className="font-normal px-2 pb-2 text-right">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {daily.map((r) => (
                <tr key={r.d} className="border-t border-[#1c2738]">
                  <td className="px-3 py-1.5 text-slate-300 sticky left-0 bg-[#0d1220]">{r.d.replaceAll("-", "/")}</td>
                  <td className={`px-2 text-right ${tone(r.twChg)}`}>{sgn(r.twChg)}</td><td className="px-2 text-right text-slate-300">{r.tw.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                  <td className={`px-2 text-right ${tone(r.otcChg)}`}>{sgn(r.otcChg)}</td><td className="px-2 text-right text-slate-300">{r.otc.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                  <td className={`px-2 text-right font-semibold ${tone(r.totChg)}`}>{sgn(r.totChg)}</td><td className="px-2 text-right text-white font-semibold">{r.tot.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                  <td className={`px-2 text-right ${tone(r.mLots)}`}>{lots(r.mLots)}</td><td className={`px-2 text-right ${tone(r.sLots)}`}>{lots(r.sLots)}</td>
                  <td className={`px-2 text-right ${tone(r.exM)}`}>{lots(r.exM)}</td><td className={`px-2 text-right ${tone(r.exS)}`}>{lots(r.exS)}</td>
                  <td className="px-2 text-right text-slate-300">{r.exSBal.toLocaleString()}</td>
                  <td className={`px-3 text-right ${tone(r.ixPct)}`}>{r.ixPct != null ? `${sgn(r.ixPct)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.daily.length > 20 && (
          <button onClick={() => setMore(!more)} className="mt-2 text-xs text-[#4f8cff] hover:underline">{more ? "收起" : `更早 ${data.daily.length - 20} 個交易日`}</button>
        )}
      </div>

      <div className="mb-8 rounded-xl border border-[#243247] bg-[#0d1220] p-4">
        <h3 className="text-sm font-semibold text-white mb-1">融資餘額 vs 加權指數（近 250 個交易日）</h3>
        <p className="text-[11px] text-[#8b97ab] mb-3">黃線＝融資餘額（億，左軸）、紅虛線＝加權指數（右軸）、柱＝每日增減。指數漲融資不增＝散戶還沒進場；指數跌融資增＝攤平；指數跌融資大減＝斷頭出場</p>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.chart.map(([d, m, ix, c]) => ({ d, m, ix, c }))} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1c2738" />
              <XAxis dataKey="d" {...ax} tickFormatter={md} minTickGap={40} />
              <YAxis yAxisId="m" {...ax} width={52} domain={["auto", "auto"]} />
              <YAxis yAxisId="ix" orientation="right" {...ax} width={52} domain={["auto", "auto"]} />
              <YAxis yAxisId="c" hide domain={[(min: number) => min * 4, (max: number) => max * 4]} />
              <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelFormatter={(d) => String(d)} />
              <Bar yAxisId="c" dataKey="c" name="每日增減（億）" fill="#64748b" opacity={0.5} />
              <Line yAxisId="m" dataKey="m" name="融資餘額（億）" stroke="#f59e0b" dot={false} strokeWidth={1.5} />
              <Line yAxisId="ix" dataKey="ix" name="加權指數" stroke="#f05252" dot={false} strokeWidth={1} strokeDasharray="4 3" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-8">
        <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-4 overflow-x-auto">
          <h3 className="text-sm font-semibold text-white mb-2">各期間統計</h3>
          <table className="w-full text-xs font-mono whitespace-nowrap">
            <thead className="text-[#8b97ab] text-[11px]"><tr><th className="text-left font-normal py-1">期間</th><th className="text-right font-normal">融資增減（億）</th>
              <th className="text-right font-normal">增加天數</th><th className="text-right font-normal">融券增減（張）</th><th className="text-right font-normal">加權指數</th></tr></thead>
            <tbody>
              {data.periods.map((p) => (
                <tr key={p.n} className="border-t border-[#1c2738]">
                  <td className="py-1.5 text-slate-300">近 {p.n} 日</td><td className={`text-right ${tone(p.mChg)}`}>{sgn(p.mChg, 1)}</td>
                  <td className="text-right text-slate-300">{p.upDays}／{p.n}</td><td className={`text-right ${tone(p.sLots)}`}>{lots(p.sLots)}</td>
                  <td className={`text-right ${tone(p.ixPct)}`}>{p.ixPct != null ? `${sgn(p.ixPct, 1)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-4 overflow-x-auto">
          <h3 className="text-sm font-semibold text-white mb-2">近一年單日極端值</h3>
          <table className="w-full text-xs font-mono whitespace-nowrap">
            <thead className="text-[#8b97ab] text-[11px]"><tr><th className="text-left font-normal py-1">融資增加最多</th><th className="text-right font-normal">億</th><th className="text-right font-normal pr-4">指數</th>
              <th className="text-left font-normal">融資減少最多</th><th className="text-right font-normal">億</th><th className="text-right font-normal">指數</th></tr></thead>
            <tbody>
              {data.extremes.up.map((u, i) => {
                const d = data.extremes.down[i];
                return (
                  <tr key={u[0]} className="border-t border-[#1c2738]">
                    <td className="py-1.5 text-slate-300">{u[0].replaceAll("-", "/")}</td><td className="text-right text-[#f05252]">{sgn(u[1], 1)}</td>
                    <td className={`text-right pr-4 ${tone(u[2])}`}>{u[2] != null ? lots(u[2]) : "—"}</td>
                    <td className="text-slate-300">{d?.[0].replaceAll("-", "/")}</td><td className="text-right text-[#22c55e]">{d ? sgn(d[1], 1) : ""}</td>
                    <td className={`text-right ${tone(d?.[2])}`}>{d?.[2] != null ? lots(d[2]) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-white">個股融資融券排行</h3>
        <Pills<Kind> value={kind} onChange={setKind} options={[
          { value: "mUp", label: "融資增加" }, { value: "mDown", label: "融資減少" }, { value: "sUp", label: "融券增加" }, { value: "sDown", label: "融券減少" },
          { value: "usage", label: "使用率最高" }, { value: "ratio", label: "券資比最高" }]} />
        <label className="text-xs text-slate-400 inline-flex items-center gap-1"><input type="checkbox" checked={withEtf} onChange={(e) => setWithEtf(e.target.checked)} />含 ETF</label>
        {kind !== "usage" && kind !== "ratio" && (
          <Pills<Period> value={period} onChange={setPeriod} options={[{ value: "1", label: "單日" }, { value: "5", label: "近 5 日" }, { value: "20", label: "近 20 日" }]} />
        )}
      </div>
      {rows.length ? <SortTable<RankRow> rows={rows} columns={cols} rowKey={(r) => r.code} limit={50} rank /> : <Empty>沒有資料。</Empty>}

      <Note>
        融資水位＝融資餘額 ÷ 普通股總市值（收盤 × 股數）；上市的歷史市值用加權指數等比例推回，算近 5 年百分位；上櫃只有每日資料期間。使用率＝融資餘額 ÷ 融資限額；券資比＝融券 ÷ 融資（張）。
        增減（億）＝增減張數 × 收盤價；融資、融券增減排行依金額排序。判讀（期間股價 ±3%）：追價＝資增價漲、攤平＝資增價跌、洗籌＝資減價漲、斷頭＝資減價跌，只描述現象、不是預測。
        融資張數增減用交易所公布的「前日餘額」：交易所偶爾會修正前一天的餘額（例：2026/11/25 上市前日餘額上修約 10 萬張），和「今天 − 昨天公布的餘額」會不同。扣除 ETF＝排除 0 開頭代號。
      </Note>
    </div>
  );
}
