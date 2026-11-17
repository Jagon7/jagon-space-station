"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Agg = { n: number; r5: number | null; r30: number | null; r60: number | null; toClose: number | null; abs30: number | null; abs60: number | null;
  up30: number | null; up60: number | null; upClose: number | null; pre60: number | null; path: (number | null)[] };
type Ev = { key: string; t: string; night: string; period: string | null; main: string | null; actual: number | null; forecast: number | null;
  previous: number | null; surprise: number | null; ref: number; pre60: number | null; r5: number | null; r15: number | null; r30: number | null;
  r60: number | null; toClose: number | null; hi60: number | null; lo60: number | null; items?: Record<string, (number | null)[]>; path: (number | null)[] };
type Up = { key: string; t: string; period: string | null; main: string | null; forecast: number | null; previous: number | null };
type Data = { updatedAt: string; offsets: number[]; kinds: Record<string, string>; stats: Record<string, { all: Agg; beat: Agg; miss: Agg; inline: Agg; from: string }>;
  events: Ev[]; upcoming: Up[]; nights: number; nightFrom: string | null; nightTo: string | null };

const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const hm = (t: string) => t.slice(11, 16);
const ymd = (t: string) => t.slice(0, 10).replaceAll("-", "/");
const wk = (t: string) => "日一二三四五六"[new Date(t).getDay()];
const ax = { tick: { fill: "#7c8aa0", fontSize: 11 }, stroke: "#334155" };
const off = (o: number) => (o === 0 ? "公布" : `${o > 0 ? "+" : ""}${o}分`);
// 「高於預期」對股市是利多還利空不一定：通膨類高於預期通常偏空、景氣類偏多，只標示方向
const INFL = new Set(["cpi", "ppi", "pce"]);

export default function UsEventsDashboard() {
  const { data, error } = useStaticJson<Data>("us-events.json");
  const [kind, setKind] = useState("cpi");
  const [pick, setPick] = useState<string | null>(null);
  const rows = useMemo(() => (data?.events ?? []).filter((e) => e.key === kind), [data, kind]);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const s = data.stats[kind];
  const picked = rows.find((r) => r.t === pick) ?? null;
  const series = data.offsets.map((o, i) => ({
    o, all: s?.all.path[i] ?? null, beat: s?.beat.path[i] ?? null, miss: s?.miss.path[i] ?? null, one: picked ? picked.path[i] : null,
  }));
  const kinds = Object.keys(data.stats);
  const beatLabel = INFL.has(kind) ? "高於預期（通膨升溫）" : "高於預期";
  const missLabel = INFL.has(kind) ? "低於預期（通膨降溫）" : "低於預期";

  const cols: Column<Ev>[] = [
    { key: "t", label: "公布（台灣時間）", sort: (r) => r.t, render: (r) => (
      <button onClick={() => setPick(pick === r.t ? null : r.t)} className={`whitespace-nowrap text-left ${pick === r.t ? "text-[#f59e0b]" : "text-slate-200 hover:text-[#4f8cff]"}`}>
        {ymd(r.t)}（{wk(r.t)}）<span className="ml-1 font-mono text-xs text-[#8b97ab]">{hm(r.t)}</span>
      </button>) },
    { key: "period", label: "期間", render: (r) => <span className="text-xs text-[#8b97ab]">{r.period ?? ""}</span> },
    { key: "act", label: "實際／預估", align: "right", render: (r) => (
      <span className="font-mono text-xs" title={r.main ?? ""}><span className="text-slate-200">{r.actual ?? "—"}</span><span className="text-[#7c8aa0]"> / {r.forecast ?? "—"}</span></span>) },
    { key: "surprise", label: "差異", align: "right", sort: (r) => r.surprise, render: (r) => num(r.surprise == null ? "—" : `${r.surprise > 0 ? "+" : ""}${+r.surprise.toFixed(3)}`,
      r.surprise == null || r.surprise === 0 ? "text-[#8b97ab]" : r.surprise > 0 ? "text-[#f59e0b]" : "text-[#4f8cff]") },
    { key: "pre60", label: "公布前 1 小時", align: "right", sort: (r) => r.pre60, render: (r) => num(pct(r.pre60), tone(r.pre60)) },
    { key: "r5", label: "+5 分", align: "right", sort: (r) => r.r5, render: (r) => num(pct(r.r5), tone(r.r5)) },
    { key: "r15", label: "+15 分", align: "right", sort: (r) => r.r15, render: (r) => num(pct(r.r15), tone(r.r15)) },
    { key: "r30", label: "+30 分", align: "right", sort: (r) => r.r30, render: (r) => num(pct(r.r30), tone(r.r30)) },
    { key: "r60", label: "+60 分", align: "right", sort: (r) => r.r60, render: (r) => num(pct(r.r60), tone(r.r60)) },
    { key: "hilo", label: "60 分內高／低", align: "right", sort: (r) => (r.hi60 ?? 0) - (r.lo60 ?? 0), render: (r) => (
      <span className="font-mono text-xs"><span className="text-[#f05252]">{pct(r.hi60)}</span><span className="text-[#7c8aa0]"> / </span><span className="text-[#22c55e]">{pct(r.lo60)}</span></span>) },
    { key: "toClose", label: "到夜盤收盤", align: "right", sort: (r) => r.toClose, render: (r) => num(pct(r.toClose), tone(r.toClose)) },
    { key: "ref", label: "公布前價位", align: "right", sort: (r) => r.ref, render: (r) => num(r.ref.toLocaleString(), "text-[#8b97ab]") },
  ];
  const aggRows = s ? [{ g: "全部", a: s.all }, { g: beatLabel, a: s.beat }, { g: missLabel, a: s.miss }, { g: "符合預期", a: s.inline }].filter((x) => x.a.n) : [];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Pills<string> value={kind} onChange={(k) => { setKind(k); setPick(null); }} options={kinds.map((k) => ({ value: k, label: data.kinds[k] ?? k }))} />
      </div>
      {s && (
        <KpiRow>
          <Kpi label={`${data.kinds[kind]} 樣本`} value={s.all.n} unit="次" sub={`${s.from.slice(0, 7).replace("-", "/")} 起`} />
          <Kpi label="公布後 30 分平均波動" value={s.all.abs30 != null ? `${s.all.abs30.toFixed(2)}%` : "—"} sub={`60 分 ${s.all.abs60?.toFixed(2) ?? "—"}%`} color="text-[#f59e0b]" />
          <Kpi label="公布後 60 分上漲機率" value={s.all.up60 != null ? `${s.all.up60.toFixed(0)}%` : "—"} sub={`平均 ${pct(s.all.r60)}`} color={tone(s.all.r60)} />
          <Kpi label="到夜盤收盤上漲機率" value={s.all.upClose != null ? `${s.all.upClose.toFixed(0)}%` : "—"} sub={`平均 ${pct(s.all.toClose)}`} color={tone(s.all.toClose)} />
        </KpiRow>
      )}

      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h3 className="text-sm font-semibold text-white">公布前後台指期夜盤平均走勢（相對公布前一刻）</h3>
          {picked && <button onClick={() => setPick(null)} className="text-xs text-[#f59e0b] hover:underline">清除 {ymd(picked.t)} 這次</button>}
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#1c2738" vertical={false} />
            <XAxis dataKey="o" tickFormatter={off} {...ax} ticks={[-60, -30, 0, 30, 60, 90, 120, 150, 180]} />
            <YAxis {...ax} unit="%" domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelFormatter={(o) => off(Number(o))}
              formatter={(v, n) => [pct(v as number), n === "all" ? "全部平均" : n === "beat" ? beatLabel : n === "miss" ? missLabel : picked ? ymd(picked.t) : ""]} />
            <Legend formatter={(v) => (v === "all" ? "全部平均" : v === "beat" ? beatLabel : v === "miss" ? missLabel : picked ? ymd(picked.t) : "")} wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine x={0} stroke="#64748b" strokeDasharray="4 4" />
            <ReferenceLine y={0} stroke="#334155" />
            <Line dataKey="all" stroke="#e2e8f0" dot={false} strokeWidth={2} connectNulls />
            <Line dataKey="beat" stroke="#f59e0b" dot={false} strokeWidth={1.5} connectNulls />
            <Line dataKey="miss" stroke="#4f8cff" dot={false} strokeWidth={1.5} connectNulls />
            {picked && <Line dataKey="one" stroke="#f05252" dot={false} strokeWidth={1.8} connectNulls />}
          </LineChart>
        </ResponsiveContainer>
        <p className="mt-2 text-[11px] text-[#7c8aa0]">點下面表格的日期，可以把那一次的走勢疊上來比較。</p>
      </section>

      {!!aggRows.length && (
        <div className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-[#243247] text-[11px] text-[#8b97ab]">
              {["分組", "次數", "公布前 1 小時", "+5 分", "+30 分", "+60 分", "60 分上漲率", "到收盤", "收盤上漲率"].map((h, i) => (
                <th key={h} className={`px-4 py-3 font-normal whitespace-nowrap ${i ? "text-right" : "text-left"}`}>{h}</th>))}
            </tr></thead>
            <tbody>{aggRows.map(({ g, a }) => (
              <tr key={g} className="border-b border-[#243247]/60 last:border-0">
                <td className="px-4 py-2.5 text-slate-200 whitespace-nowrap">{g}</td>
                <td className="px-4 py-2.5 text-right font-mono text-slate-300">{a.n}</td>
                {[a.pre60, a.r5, a.r30, a.r60].map((v, i) => <td key={i} className={`px-4 py-2.5 text-right font-mono ${tone(v)}`}>{pct(v)}</td>)}
                <td className="px-4 py-2.5 text-right font-mono text-slate-300">{a.up60 != null ? `${a.up60.toFixed(0)}%` : "—"}</td>
                <td className={`px-4 py-2.5 text-right font-mono ${tone(a.toClose)}`}>{pct(a.toClose)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-slate-300">{a.upClose != null ? `${a.upClose.toFixed(0)}%` : "—"}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}

      {!!data.upcoming.length && (
        <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4">
          <div className="text-sm text-white font-semibold mb-2">接下來三週</div>
          <div className="flex flex-wrap gap-2">{data.upcoming.map((u) => (
            <span key={u.key + u.t} className={`rounded-md px-2.5 py-1 text-xs ${u.key === kind ? "bg-[#4f8cff]/15" : "bg-[#141c2e]"}`}>
              <span className="text-slate-200">{data.kinds[u.key] ?? u.key}</span>
              <span className="ml-1.5 font-mono text-[#8b97ab]">{u.t.slice(5, 10).replace("-", "/")}（{wk(u.t)}）{hm(u.t)}</span>
              {u.forecast != null && <span className="ml-1.5 font-mono text-[#7c8aa0]">預估 {u.forecast}</span>}
            </span>))}</div>
        </section>
      )}

      <SortTable<Ev> rows={rows} columns={cols} rowKey={(r) => r.t} initialSort={{ key: "t", desc: true }} limit={60} />

      <div className="mt-6">
        <Note>
          事件時間與實際值／預估值來自 TradingView 經濟行事曆；台指期夜盤 1 分 K：最近 30 個交易日用期交所每筆成交（成交量最大的月份），更早用永豐 TXFR1 近月連續（{data.nightFrom?.slice(0, 7).replace("-", "/")} 起，共 {data.nights} 晚）。
          漲跌都相對「公布前最後一根 1 分 K 的收盤」。美國夏令時間 8:30 公布＝台灣 20:30，冬令＝21:30；FOMC 利率決策在台灣凌晨 2 點或 3 點，同樣落在夜盤。
          高於／低於預期依主指標：CPI 看核心 CPI 月增、PPI 看 PPI 月增、PCE 看核心 PCE 月增、非農看新增就業人數。
        </Note>
      </div>
    </div>
  );
}
