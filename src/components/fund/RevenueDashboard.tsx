"use client";

import { useMemo, useState } from "react";
import { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";
import ExpandTable, { StockCell, type XColumn } from "@/components/ExpandTable";

// [代號, 名稱, 產業, 市場, 當月營收(千元), 月增%, 年增%, 累計年增%, 創新高, 連續年增月數, 有資料月數, 備註]
type R = [string, string, string, string, number | null, number | null, number | null, number | null, number, number, number, string];
type Filter = "all" | "high" | "yoy20" | "streak" | "down";

export const yi = (v: number | null | undefined) => (v == null ? "—" : v >= 1e5 ? (v / 1e5).toFixed(v >= 1e7 ? 0 : 2) : (v / 1e5).toFixed(3));
export const pf = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
export const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-slate-500" : v > 0 ? "text-[#ef4444]" : "text-[#22c55e]");
const ym = (s: string) => `${s.slice(2, 4)}/${Number(s.slice(5, 7))}`;

function Detail({ code }: { code: string }) {
  const { data, error } = useStaticJson<{ n: string; h: [string, number | null, number | null][] }>(`fund/revenue/${code}.json`);
  if (!data) return <div className="py-8 text-center text-xs text-slate-500">{error ? "沒有歷史資料" : "載入中…"}</div>;
  const rows = data.h.map(([m, v, y]) => ({ m, v: v == null ? null : v / 1e5, y }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={rows} margin={{ top: 5, right: 0, bottom: 0, left: -5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" vertical={false} />
          <XAxis dataKey="m" tickFormatter={ym} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={16} />
          <YAxis yAxisId="v" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="y" orientation="right" unit="%" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #1e2a3a", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
            formatter={(v, n) => (n === "v" ? [`${typeof v === "number" ? v.toFixed(2) : v} 億`, "營收"] : [`${typeof v === "number" ? v.toFixed(1) : v}%`, "年增"])} />
          <Bar yAxisId="v" dataKey="v">{rows.map((r, i) => <Cell key={r.m} fill={i === rows.length - 1 ? "#00d4aa" : "#3b82f6"} fillOpacity={0.75} />)}</Bar>
          <Line yAxisId="y" dataKey="y" stroke="#f59e0b" strokeWidth={1.8} dot={false} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="text-[11px] text-slate-600">藍柱：每月營收（億元，最右綠柱為最新月）；橘線：年增率（右軸）。</p>
    </div>
  );
}

export default function RevenueDashboard() {
  const { data, error } = useStaticJson<{ month: string; rows: R[] }>("fund/revenue.json");
  const [filter, setFilter] = useState<Filter>("all");
  const [ind, setInd] = useState("");
  const [only, setOnly] = useState<string | null>(null);

  const rows = useMemo(() => {
    let rs = data?.rows ?? [];
    if (only) return rs.filter((r) => r[0] === only);
    if (ind) rs = rs.filter((r) => r[2] === ind);
    switch (filter) {
      case "high": return rs.filter((r) => r[8]);
      case "yoy20": return rs.filter((r) => (r[6] ?? -1) >= 20);
      case "streak": return rs.filter((r) => r[9] >= 6);
      case "down": return rs.filter((r) => (r[6] ?? 0) < 0);
      default: return rs;
    }
  }, [data, filter, ind, only]);
  const industries = useMemo(() => [...new Set((data?.rows ?? []).map((r) => r[2]))].sort(), [data]);

  if (!data) return <div className="py-16 text-center text-sm text-slate-500 font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>月營收資料累積中。</Empty>;
  const all = data.rows;
  const up = all.filter((r) => (r[6] ?? 0) > 0).length;
  const highs = all.filter((r) => r[8]).length;

  const cols: XColumn<R>[] = [
    { key: "name", label: "公司", render: (r) => <span><StockCell code={r[0]} name={r[1]} mk={r[3]} />{r[8] ? <span className="ml-2 rounded px-1.5 py-px text-[10px] bg-[#ef4444]/15 text-[#ef4444]">新高</span> : null}</span> },
    { key: "ind", label: "產業", render: (r) => <span className="text-xs text-slate-500">{r[2]}</span> },
    { key: "rev", label: "營收（億）", align: "right", sort: (r) => r[4], render: (r) => <span className="text-slate-200">{yi(r[4])}</span> },
    { key: "mom", label: "月增", align: "right", sort: (r) => r[5], render: (r) => <span className={tone(r[5])}>{pf(r[5])}</span> },
    { key: "yoy", label: "年增", align: "right", sort: (r) => r[6], render: (r) => <span className={tone(r[6])}>{pf(r[6])}</span> },
    { key: "ytd", label: "累計年增", align: "right", sort: (r) => r[7], render: (r) => <span className={tone(r[7])}>{pf(r[7])}</span> },
    { key: "streak", label: "連續年增", align: "right", sort: (r) => r[9], render: (r) => <span className={r[9] >= 6 ? "text-[#f59e0b]" : "text-slate-400"}>{r[9] ? `${r[9]} 個月` : "—"}</span> },
    { key: "note", label: "公司說明", render: (r) => <span className="text-xs text-slate-500 block max-w-[18rem] truncate" title={r[11]}>{r[11]}</span> },
  ];

  return (
    <div>
      <Note>
        上市櫃公司每月 10 日前公布上個月營收（合併營收，單位換算為億元）。「新高」＝本月營收高於近 3 年任何一個月；「連續年增」＝連續幾個月營收比去年同月高。點一列看 3 年營收走勢。
      </Note>
      <KpiRow>
        <Kpi label="資料月份" value={`${data.month.slice(0, 4)}/${Number(data.month.slice(5))}`} sub={`${all.length} 家已公布`} />
        <Kpi label="年增家數" value={up} unit="家" sub={`${((up / all.length) * 100).toFixed(0)}%`} color="text-[#ef4444]" />
        <Kpi label="營收創新高" value={highs} unit="家" color="text-[#f59e0b]" />
        <Kpi label="年增 ≥ 20%" value={all.filter((r) => (r[6] ?? -1) >= 20).length} unit="家" />
      </KpiRow>
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-3">
        <div className="shrink-0"><Pills<Filter> value={filter} onChange={(v) => { setFilter(v); setOnly(null); }} options={[
          { value: "all", label: "全部" }, { value: "high", label: "創新高" }, { value: "yoy20", label: "年增 ≥ 20%" },
          { value: "streak", label: "連續年增 ≥ 6 個月" }, { value: "down", label: "年減" },
        ]} /></div>
        <select value={ind} onChange={(e) => { setInd(e.target.value); setOnly(null); }} className="lg:w-44 rounded-lg border border-[#1e2a3a] bg-[#0d1220] px-3 py-2 text-sm text-slate-300">
          <option value="">全部產業</option>
          {industries.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <div className="lg:ml-auto"><SearchBox placeholder="查公司，例如 2330" items={all.map((r) => ({ code: r[0], name: r[1] }))} onPick={setOnly} /></div>
      </div>
      {only && <button onClick={() => setOnly(null)} className="mb-2 text-xs text-slate-500 hover:text-[#00d4aa]">← 回到列表</button>}
      {!rows.length ? <Empty>沒有符合條件的公司。</Empty> :
        <ExpandTable<R> key={`${filter}${ind}${only}`} rows={rows} columns={cols} rowKey={(r) => r[0]} detail={(r) => <Detail code={r[0]} />}
          initialSort={{ key: filter === "down" ? "yoy" : filter === "streak" ? "streak" : "rev", desc: filter !== "down" }} />}
    </div>
  );
}
