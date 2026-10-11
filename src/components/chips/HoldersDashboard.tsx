"use client";

import { useMemo, useState } from "react";
import { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";
import ExpandTable, { StockCell, type XColumn } from "@/components/ExpandTable";

// [代號, 名稱, 股東人數, 千張大戶%, 週變化, 4週變化, 400張以上%, 50張以下%, 散戶4週變化, 人數4週變化, 週數]
type R = [string, string, number, number, number | null, number | null, number, number, number | null, number | null, number];
type View = "up" | "down" | "concentrate" | "all";

const pp = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-slate-500" : v > 0 ? "text-[#ef4444]" : "text-[#22c55e]");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;

function Detail({ code }: { code: string }) {
  const { data, error } = useStaticJson<[string, number, number, number, number][]>(`chips/holders/${code}.json`);
  if (!data) return <div className="py-8 text-center text-xs text-slate-500">{error ? "只有一週資料，下週起可看變化" : "載入中…"}</div>;
  const rows = data.map(([d, p, a, b, c]) => ({ d, p, a, b, c }));
  return (
    <ResponsiveContainer width="100%" height={230}>
      <ComposedChart data={rows} margin={{ top: 5, right: 0, bottom: 0, left: -5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" vertical={false} />
        <XAxis dataKey="d" tickFormatter={md} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis yAxisId="pct" unit="%" domain={["auto", "auto"]} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis yAxisId="n" orientation="right" domain={["auto", "auto"]} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #1e2a3a", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
          formatter={(v, n) => [typeof v === "number" ? (n === "股東人數" ? v.toLocaleString() : `${v.toFixed(2)}%`) : String(v), String(n)]} />
        <Legend formatter={(v) => <span className="text-xs text-slate-400">{v}</span>} />
        <Bar yAxisId="n" dataKey="p" name="股東人數" fill="#475569" fillOpacity={0.5} />
        <Line yAxisId="pct" dataKey="a" name="千張大戶" stroke="#ef4444" strokeWidth={2} dot />
        <Line yAxisId="pct" dataKey="b" name="400 張以上" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
        <Line yAxisId="pct" dataKey="c" name="50 張以下" stroke="#22c55e" strokeWidth={1.5} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function HoldersDashboard() {
  const { data, error } = useStaticJson<{ week: string; weeks: string[]; rows: R[] }>("chips/holders.json");
  const [view, setView] = useState<View>("up");
  const [only, setOnly] = useState<string | null>(null);
  const multi = (data?.weeks.length ?? 0) >= 2;
  const rows = useMemo(() => {
    const rs = data?.rows ?? [];
    if (only) return rs.filter((r) => r[0] === only);
    if (!multi || view === "all") return rs;
    if (view === "up") return rs.filter((r) => (r[4] ?? 0) > 0);
    if (view === "down") return rs.filter((r) => (r[4] ?? 0) < 0);
    return rs.filter((r) => (r[5] ?? 0) > 0 && (r[9] ?? 0) < 0);
  }, [data, view, only, multi]);

  if (!data) return <div className="py-16 text-center text-sm text-slate-500 font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>集保資料累積中。</Empty>;

  const cols: XColumn<R>[] = [
    { key: "name", label: "股票", render: (r) => <StockCell code={r[0]} name={r[1]} /> },
    { key: "p1000", label: "千張大戶", align: "right", sort: (r) => r[3], render: (r) => <span className="text-slate-100">{r[3].toFixed(2)}%</span> },
    { key: "w1", label: "週變化", align: "right", sort: (r) => r[4], render: (r) => <span className={tone(r[4])}>{pp(r[4])}</span> },
    { key: "w4", label: "4 週變化", align: "right", sort: (r) => r[5], render: (r) => <span className={tone(r[5])}>{pp(r[5])}</span> },
    { key: "p400", label: "400 張以上", align: "right", sort: (r) => r[6], render: (r) => <span className="text-slate-300">{r[6].toFixed(2)}%</span> },
    { key: "retail", label: "50 張以下", align: "right", sort: (r) => r[7], render: (r) => <span className="text-slate-400">{r[7].toFixed(2)}%</span> },
    { key: "r4", label: "散戶 4 週", align: "right", sort: (r) => r[8], render: (r) => <span className={tone(r[8] == null ? null : -r[8])}>{pp(r[8])}</span> },
    { key: "people", label: "股東人數", align: "right", sort: (r) => r[2], render: (r) => <span className="text-slate-400">{r[2].toLocaleString()}</span> },
    { key: "pd", label: "人數 4 週", align: "right", sort: (r) => r[9], render: (r) => <span className={tone(r[9] == null ? null : -r[9])}>{r[9] == null ? "—" : `${r[9] > 0 ? "+" : ""}${r[9].toLocaleString()}`}</span> },
  ];

  return (
    <div>
      <Note>
        集保中心每週公布各股的股權分散表。「千張大戶」＝持有 1000 張以上的股東合計持股比例；「50 張以下」視為散戶。
        大戶比例上升、股東人數減少＝籌碼集中。最新一週涵蓋全部上市櫃股票；過去幾週目前只回補成交值前 300 名，之後每週累積。
      </Note>
      <KpiRow>
        <Kpi label="資料週" value={md(data.week)} sub={`共 ${data.weeks.length} 週`} />
        <Kpi label="千張大戶週增加" value={multi ? data.rows.filter((r) => (r[4] ?? 0) > 0).length : "—"} unit="檔" color="text-[#ef4444]" />
        <Kpi label="千張大戶週減少" value={multi ? data.rows.filter((r) => (r[4] ?? 0) < 0).length : "—"} unit="檔" color="text-[#22c55e]" />
        <Kpi label="籌碼集中（4 週）" value={multi ? data.rows.filter((r) => (r[5] ?? 0) > 0 && (r[9] ?? 0) < 0).length : "—"} unit="檔" color="text-[#f59e0b]" />
      </KpiRow>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        {multi && <Pills<View> value={view} onChange={(v) => { setView(v); setOnly(null); }} options={[{ value: "up", label: "大戶增加" }, { value: "down", label: "大戶減少" }, { value: "concentrate", label: "籌碼集中" }, { value: "all", label: "全部" }]} />}
        <div className="ml-auto"><SearchBox placeholder="查個股" items={data.rows.map((r) => ({ code: r[0], name: r[1] }))} onPick={setOnly} /></div>
      </div>
      {only && <button onClick={() => setOnly(null)} className="mb-2 text-xs text-slate-500 hover:text-[#00d4aa]">← 回到列表</button>}
      {!rows.length ? <Empty>沒有符合條件的股票。</Empty> :
        <ExpandTable<R> key={`${view}${only}`} rows={rows} columns={cols} rowKey={(r) => r[0]} detail={(r) => <Detail code={r[0]} />}
          initialSort={{ key: !multi ? "p1000" : view === "down" ? "w1" : view === "concentrate" ? "w4" : "w1", desc: view !== "down" }} />}
    </div>
  );
}
