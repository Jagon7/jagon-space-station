"use client";

import { useMemo, useState } from "react";
import { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";
import ExpandTable, { StockCell, type XColumn } from "@/components/ExpandTable";
import { pf, tone } from "./RevenueDashboard";

// [代號, 名稱, 市場, 單季EPS, 去年同季EPS, 累計EPS, 去年累計EPS, 毛利率, 營益率, 淨利率, 上季毛利率, 上季營益率, 上季淨利率, 三率三升, 營收年增%]
type R = [string, string, string, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number, number | null];
type Filter = "all" | "threeUp" | "epsUp" | "turn" | "loss";

const eps = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
const mg = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(1)}%`);
const diff = (a: number | null, b: number | null) => (a == null || b == null ? null : a - b);

function Detail({ code }: { code: string }) {
  const { data, error } = useStaticJson<{ n: string; h: [string, number | null, number | null, number | null, number | null, number | null][] }>(`fund/income/${code}.json`);
  if (!data) return <div className="py-8 text-center text-xs text-slate-500">{error ? "沒有歷史資料" : "載入中…"}</div>;
  const rows = data.h.map(([q, , g, o, n, e]) => ({ q: `${q.slice(2, 4)}Q${q.slice(-1)}`, g, o, n, e }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={250}>
        <ComposedChart data={rows} margin={{ top: 5, right: 0, bottom: 0, left: -5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" vertical={false} />
          <XAxis dataKey="q" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="e" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="m" orientation="right" unit="%" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #1e2a3a", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
            formatter={(v, n) => [typeof v === "number" ? (n === "EPS（元）" ? v.toFixed(2) : `${v.toFixed(1)}%`) : String(v), String(n)]} />
          <Legend formatter={(v) => <span className="text-xs text-slate-400">{v}</span>} />
          <Bar yAxisId="e" dataKey="e" name="EPS（元）" fill="#3b82f6" fillOpacity={0.75} />
          <Line yAxisId="m" dataKey="g" name="毛利率" stroke="#f59e0b" dot={false} strokeWidth={1.8} connectNulls />
          <Line yAxisId="m" dataKey="o" name="營益率" stroke="#00d4aa" dot={false} strokeWidth={1.8} connectNulls />
          <Line yAxisId="m" dataKey="n" name="淨利率" stroke="#a78bfa" dot={false} strokeWidth={1.8} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="text-[11px] text-slate-600">單季數字（由年初累計數相減而得）。藍柱：單季 EPS；線：三率（右軸）。</p>
    </div>
  );
}

export default function IncomeDashboard() {
  const { data, error } = useStaticJson<{ quarter: string; rows: R[] }>("fund/income.json");
  const [filter, setFilter] = useState<Filter>("all");
  const [only, setOnly] = useState<string | null>(null);
  const rows = useMemo(() => {
    const rs = data?.rows ?? [];
    if (only) return rs.filter((r) => r[0] === only);
    switch (filter) {
      case "threeUp": return rs.filter((r) => r[13]);
      case "epsUp": return rs.filter((r) => r[3] != null && r[4] != null && r[4] > 0 && r[3] / r[4] >= 1.3);
      case "turn": return rs.filter((r) => (r[3] ?? 0) > 0 && (r[4] ?? 0) < 0);
      case "loss": return rs.filter((r) => (r[3] ?? 0) < 0);
      default: return rs;
    }
  }, [data, filter, only]);

  if (!data) return <div className="py-16 text-center text-sm text-slate-500 font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>季報資料累積中。</Empty>;
  const all = data.rows;
  const q = data.quarter;

  const cols: XColumn<R>[] = [
    { key: "name", label: "公司", render: (r) => <span><StockCell code={r[0]} name={r[1]} mk={r[2]} />{r[13] ? <span className="ml-2 rounded px-1.5 py-px text-[10px] bg-[#ef4444]/15 text-[#ef4444]">三率三升</span> : null}</span> },
    { key: "eps", label: "單季 EPS", align: "right", sort: (r) => r[3], render: (r) => <span className={(r[3] ?? 0) < 0 ? "text-[#22c55e]" : "text-slate-100"}>{eps(r[3])}</span> },
    { key: "ly", label: "去年同季", align: "right", sort: (r) => r[4], render: (r) => <span className="text-slate-400">{eps(r[4])}</span> },
    { key: "yoy", label: "EPS 年增", align: "right", sort: (r) => (r[3] != null && r[4] ? ((r[3] - r[4]) / Math.abs(r[4])) * 100 : null),
      render: (r) => { const v = r[3] != null && r[4] ? ((r[3] - r[4]) / Math.abs(r[4])) * 100 : null; return <span className={tone(v)}>{pf(v)}</span>; } },
    { key: "ytd", label: "累計 EPS", align: "right", sort: (r) => r[5], render: (r) => <span className="text-slate-300">{eps(r[5])}<span className="text-slate-600 text-xs"> / {eps(r[6])}</span></span> },
    { key: "gm", label: "毛利率", align: "right", sort: (r) => r[7], render: (r) => <span className="text-slate-300">{mg(r[7])} <span className={`text-xs ${tone(diff(r[7], r[10]))}`}>{diff(r[7], r[10]) == null ? "" : (diff(r[7], r[10])! > 0 ? "▲" : "▼")}</span></span> },
    { key: "om", label: "營益率", align: "right", sort: (r) => r[8], render: (r) => <span className="text-slate-300">{mg(r[8])} <span className={`text-xs ${tone(diff(r[8], r[11]))}`}>{diff(r[8], r[11]) == null ? "" : (diff(r[8], r[11])! > 0 ? "▲" : "▼")}</span></span> },
    { key: "nm", label: "淨利率", align: "right", sort: (r) => r[9], render: (r) => <span className="text-slate-300">{mg(r[9])} <span className={`text-xs ${tone(diff(r[9], r[12]))}`}>{diff(r[9], r[12]) == null ? "" : (diff(r[9], r[12])! > 0 ? "▲" : "▼")}</span></span> },
    { key: "rev", label: "營收年增", align: "right", sort: (r) => r[14], render: (r) => <span className={tone(r[14])}>{pf(r[14])}</span> },
  ];

  return (
    <div>
      <Note>
        上市櫃公司最新一季財報（{q.slice(0, 4)} 年第 {q.slice(-1)} 季）的單季 EPS 與三率（毛利率、營益率、淨利率）。財報公布的是年初至該季的累計數，單季數字是用相減算出。
        ▲▼ 是和上一季相比；「三率三升」＝三個比率都比上一季高。金融業沒有毛利率，以「—」表示。點一列看近 3 年 12 季走勢。
      </Note>
      <KpiRow>
        <Kpi label="財報季別" value={`${q.slice(0, 4)} Q${q.slice(-1)}`} sub={`${all.length} 家`} />
        <Kpi label="EPS 較去年同季成長" value={all.filter((r) => r[3] != null && r[4] != null && r[3] > r[4]).length} unit="家" color="text-[#ef4444]" />
        <Kpi label="三率三升" value={all.filter((r) => r[13]).length} unit="家" color="text-[#f59e0b]" />
        <Kpi label="單季虧損" value={all.filter((r) => (r[3] ?? 0) < 0).length} unit="家" color="text-[#22c55e]" />
      </KpiRow>
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-3">
        <Pills<Filter> value={filter} onChange={(v) => { setFilter(v); setOnly(null); }} options={[
          { value: "all", label: "全部" }, { value: "threeUp", label: "三率三升" }, { value: "epsUp", label: "EPS 年增 ≥ 30%" },
          { value: "turn", label: "轉虧為盈" }, { value: "loss", label: "單季虧損" },
        ]} />
        <div className="lg:ml-auto"><SearchBox placeholder="查公司，例如 2330" items={all.map((r) => ({ code: r[0], name: r[1] }))} onPick={setOnly} /></div>
      </div>
      {only && <button onClick={() => setOnly(null)} className="mb-2 text-xs text-slate-500 hover:text-[#00d4aa]">← 回到列表</button>}
      {!rows.length ? <Empty>沒有符合條件的公司。</Empty> :
        <ExpandTable<R> key={`${filter}${only}`} rows={rows} columns={cols} rowKey={(r) => r[0]} detail={(r) => <Detail code={r[0]} />}
          initialSort={{ key: filter === "loss" ? "eps" : "eps", desc: filter !== "loss" }} />}
    </div>
  );
}
