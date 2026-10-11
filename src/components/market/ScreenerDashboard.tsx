"use client";

import { useMemo, useState } from "react";
import { ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills } from "@/components/data-ui";
import ExpandTable, { StockCell, type XColumn } from "@/components/ExpandTable";

// [代號, 名稱, 市場(0上市/1上櫃), 收盤, 漲跌%, 成交量(張), 量比, 距月線%, 距季線%, 5日%, 20日%, 60日%, 成交值(億), 訊號索引[]]
type R = [string, string, number, number, number | null, number, number | null, number | null, number | null, number | null, number | null, number | null, number, number[]];
type Data = { date: string; signals: string[]; rows: R[] };
type Val = "0" | "1" | "5" | "20";

const SIG: Record<string, { label: string; desc: string; bear?: boolean }> = {
  ma20up: { label: "站上月線", desc: "昨天收在 20 日均線下，今天站上" },
  ma60up: { label: "站上季線", desc: "昨天收在 60 日均線下，今天站上" },
  bull: { label: "多頭排列", desc: "收盤 > 5 日 > 10 日 > 20 日 > 60 日均線" },
  volx2: { label: "爆量", desc: "成交量 ≥ 20 日均量 2 倍，且 ≥ 1000 張" },
  high_all: { label: "半年新高", desc: "收盤創近半年（資料範圍內）新高" },
  high60: { label: "60 日新高", desc: "收盤創近 60 個交易日新高" },
  breakout: { label: "突破整理", desc: "前 20 日高低差 < 15%，今天收盤突破 20 日高點" },
  ma60down: { label: "跌破季線", desc: "昨天在 60 日均線上，今天跌破", bear: true },
  low60: { label: "60 日新低", desc: "收盤創近 60 個交易日新低", bear: true },
};
const pf = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;

function Chart({ code }: { code: string }) {
  const { data, error } = useStaticJson<[string, number, number][]>(`market/px/${code}.json`);
  if (!data) return <div className="py-8 text-center text-xs text-[#8b97ab]">{error ? "沒有股價資料" : "載入中…"}</div>;
  const rows = data.map(([d, c, v], i) => {
    const m = (k: number) => (i + 1 >= k ? data.slice(i + 1 - k, i + 1).reduce((s, x) => s + x[1], 0) / k : null);
    return { d, c, v, m20: m(20), m60: m(60) };
  });
  return (
    <div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={rows} margin={{ top: 5, right: 0, bottom: 0, left: -5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#243247" vertical={false} />
          <XAxis dataKey="d" tickFormatter={md} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={24} />
          <YAxis yAxisId="p" domain={["auto", "auto"]} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="v" orientation="right" hide domain={[0, (max: number) => max * 4]} />
          <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
            formatter={(v, n) => [typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v), n === "c" ? "收盤" : n === "v" ? "成交量（張）" : n === "m20" ? "月線" : "季線"]} />
          <Bar yAxisId="v" dataKey="v" fill="#475569" fillOpacity={0.5} />
          <Line yAxisId="p" dataKey="c" stroke="#e2e8f0" dot={false} strokeWidth={1.6} />
          <Line yAxisId="p" dataKey="m20" stroke="#f59e0b" dot={false} strokeWidth={1.2} connectNulls />
          <Line yAxisId="p" dataKey="m60" stroke="#a78bfa" dot={false} strokeWidth={1.2} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="text-[11px] text-[#7c8aa0]">白：收盤；橘：月線（20 日）；紫：季線（60 日）；灰柱：成交量。</p>
    </div>
  );
}

export default function ScreenerDashboard() {
  const { data, error } = useStaticJson<Data>("market/screener.json");
  const [picked, setPicked] = useState<string[]>(["bull"]);
  const [val, setVal] = useState<Val>("1");
  const [mkt, setMkt] = useState<"all" | "0" | "1">("all");

  const rows = useMemo(() => {
    if (!data) return [];
    const idx = picked.map((k) => data.signals.indexOf(k));
    return data.rows.filter((r) => idx.every((i) => r[13].includes(i)) && r[12] >= Number(val) && (mkt === "all" || r[2] === Number(mkt)));
  }, [data, picked, val, mkt]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>行情資料累積中。</Empty>;
  const count = (k: string) => data.rows.filter((r) => r[13].includes(data.signals.indexOf(k))).length;
  const toggle = (k: string) => setPicked(picked.includes(k) ? picked.filter((x) => x !== k) : [...picked, k]);

  const cols: XColumn<R>[] = [
    { key: "name", label: "股票", render: (r) => <StockCell code={r[0]} name={r[1]} mk={r[2] ? "上櫃" : "上市"} /> },
    { key: "close", label: "收盤", align: "right", sort: (r) => r[3], render: (r) => <span className="text-slate-200">{r[3]}</span> },
    { key: "chg", label: "漲跌", align: "right", sort: (r) => r[4], render: (r) => <span className={tone(r[4])}>{pf(r[4])}</span> },
    { key: "value", label: "成交值（億）", align: "right", sort: (r) => r[12], render: (r) => <span className="text-slate-300">{r[12].toFixed(2)}</span> },
    { key: "vr", label: "量比", align: "right", sort: (r) => r[6], render: (r) => <span className={(r[6] ?? 0) >= 2 ? "text-[#f59e0b]" : "text-slate-400"}>{r[6] ?? "—"}</span> },
    { key: "m20", label: "距月線", align: "right", sort: (r) => r[7], render: (r) => <span className={tone(r[7])}>{pf(r[7])}</span> },
    { key: "m60", label: "距季線", align: "right", sort: (r) => r[8], render: (r) => <span className={tone(r[8])}>{pf(r[8])}</span> },
    { key: "r5", label: "5 日", align: "right", sort: (r) => r[9], render: (r) => <span className={tone(r[9])}>{pf(r[9])}</span> },
    { key: "r20", label: "20 日", align: "right", sort: (r) => r[10], render: (r) => <span className={tone(r[10])}>{pf(r[10])}</span> },
    { key: "r60", label: "60 日", align: "right", sort: (r) => r[11], render: (r) => <span className={tone(r[11])}>{pf(r[11])}</span> },
    { key: "sig", label: "訊號", render: (r) => <span className="flex gap-1">{r[13].map((i) => { const s = SIG[data.signals[i]]; return <span key={i} className={`rounded px-1.5 py-px text-[10px] ${s?.bear ? "bg-[#22c55e]/15 text-[#22c55e]" : "bg-[#f05252]/15 text-[#f05252]"}`}>{s?.label}</span>; })}</span> },
  ];

  return (
    <div>
      <Note>
        用每天收盤後的上市櫃普通股行情篩選技術訊號（資料約半年，「半年新高」以此範圍計算）。可以複選訊號（同時符合），再用成交值過濾掉冷門股。點一列看近半年走勢與月線、季線。
      </Note>
      <KpiRow>
        <Kpi label="資料日" value={md(data.date)} sub={`${data.rows.length} 檔`} />
        <Kpi label="多頭排列" value={count("bull")} unit="檔" color="text-[#f05252]" />
        <Kpi label="創 60 日新高／新低" value={<><span className="text-[#f05252]">{count("high60")}</span><span className="text-[#7c8aa0] mx-1">/</span><span className="text-[#22c55e]">{count("low60")}</span></>} unit="檔" />
        <Kpi label="爆量" value={count("volx2")} unit="檔" color="text-[#f59e0b]" />
      </KpiRow>
      <div className="flex flex-wrap gap-2 mb-3">
        {Object.entries(SIG).map(([k, s]) => (
          <button key={k} onClick={() => toggle(k)} title={s.desc}
            className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${picked.includes(k)
              ? s.bear ? "border-[#22c55e] bg-[#22c55e]/10 text-[#22c55e]" : "border-[#f05252] bg-[#f05252]/10 text-[#f05252]"
              : "border-[#243247] text-slate-400 hover:text-slate-200"}`}>
            {s.label} <span className="font-mono text-xs opacity-70">{count(k)}</span>
          </button>
        ))}
        {picked.length > 0 && <button onClick={() => setPicked([])} className="px-2 text-xs text-[#8b97ab] hover:text-[#4f8cff]">清除</button>}
      </div>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <Pills<Val> value={val} onChange={setVal} options={[{ value: "0", label: "不限成交值" }, { value: "1", label: "≥ 1 億" }, { value: "5", label: "≥ 5 億" }, { value: "20", label: "≥ 20 億" }]} />
        <Pills<"all" | "0" | "1"> value={mkt} onChange={setMkt} options={[{ value: "all", label: "上市櫃" }, { value: "0", label: "上市" }, { value: "1", label: "上櫃" }]} />
        <span className="text-xs text-[#8b97ab]">{picked.length ? picked.map((k) => SIG[k].desc).join("；") : "沒有選訊號＝全部股票"}</span>
      </div>
      {!rows.length ? <Empty>沒有同時符合條件的股票，試著少選一個訊號或放寬成交值。</Empty> :
        <ExpandTable<R> key={`${picked.join()}${val}${mkt}`} rows={rows} columns={cols} rowKey={(r) => r[0]} detail={(r) => <Chart code={r[0]} />} initialSort={{ key: "value", desc: true }} />}
    </div>
  );
}
