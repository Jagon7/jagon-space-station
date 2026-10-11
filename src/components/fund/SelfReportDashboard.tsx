"use client";

import { useMemo, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills } from "@/components/data-ui";
import ExpandTable, { StockCell, type XColumn } from "@/components/ExpandTable";
import { pf, tone } from "./RevenueDashboard";

// [代號, 名稱, 市場, 當期營業損益, 累計營業損益, 當期稅前, 累計稅前, 去年同期稅前, 去年累計稅前, 說明, 歷史[[期, 稅前, 營業損益]]]
type R = [string, string, string, number | null, number | null, number | null, number | null, number | null, number | null, string, [string, number | null, number | null][]];
type Block = { periods: string[]; data: Record<string, R[]> };
type Kind = "m" | "q";

const wan = (v: number | null | undefined) => (v == null ? "—" : Math.abs(v) >= 1e5 ? `${(v / 1e5).toFixed(2)}億` : `${Math.round(v / 10).toLocaleString()}萬`);
const label = (p: string) => (p.includes("Q") ? `${p.slice(0, 4)} Q${p.slice(-1)}` : `${p.slice(0, 4)}/${Number(p.slice(5))}`);
const growth = (a: number | null, b: number | null) => (a == null || b == null || b === 0 ? null : ((a - b) / Math.abs(b)) * 100);

function Detail({ r }: { r: R }) {
  const rows = r[10].map(([p, pre]) => ({ p: label(p), v: pre == null ? null : pre / 1e5 }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={rows} margin={{ top: 5, right: 5, bottom: 0, left: -5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#243247" vertical={false} />
          <XAxis dataKey="p" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={12} />
          <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
            formatter={(v) => [`${typeof v === "number" ? v.toFixed(2) : v} 億`, "稅前損益"]} />
          <Bar dataKey="v">{rows.map((x) => <Cell key={x.p} fill={(x.v ?? 0) >= 0 ? "#f05252" : "#22c55e"} fillOpacity={0.8} />)}</Bar>
        </BarChart>
      </ResponsiveContainer>
      {r[9] && <p className="mt-2 text-xs text-slate-400">公司說明：{r[9]}</p>}
    </div>
  );
}

export default function SelfReportDashboard() {
  const { data, error } = useStaticJson<{ m?: Block; q?: Block }>("fund/selfreport.json");
  const [kind, setKind] = useState<Kind>("m");
  const [period, setPeriod] = useState<string | null>(null);
  const block = data?.[kind];
  const cur = period && block?.data[period] ? period : block?.periods[0] ?? "";
  const rows = useMemo(() => block?.data[cur] ?? [], [block, cur]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.m && !data.q) return <Empty>自結損益資料累積中。</Empty>;

  const unit = kind === "m" ? "本月" : "本季";
  const cols: XColumn<R>[] = [
    { key: "name", label: "公司", render: (r) => <StockCell code={r[0]} name={r[1]} mk={r[2]} /> },
    { key: "pre", label: `${unit}稅前`, align: "right", sort: (r) => r[5], render: (r) => <span className={(r[5] ?? 0) < 0 ? "text-[#22c55e]" : "text-slate-100"}>{wan(r[5])}</span> },
    { key: "ly", label: "去年同期", align: "right", sort: (r) => r[7], render: (r) => <span className="text-slate-400">{wan(r[7])}</span> },
    { key: "yoy", label: "年增", align: "right", sort: (r) => growth(r[5], r[7]), render: (r) => <span className={tone(growth(r[5], r[7]))}>{pf(growth(r[5], r[7]))}</span> },
    { key: "ytd", label: "今年累計稅前", align: "right", sort: (r) => r[6], render: (r) => <span className="text-slate-300">{wan(r[6])}</span> },
    { key: "ytdyoy", label: "累計年增", align: "right", sort: (r) => growth(r[6], r[8]), render: (r) => <span className={tone(growth(r[6], r[8]))}>{pf(growth(r[6], r[8]))}</span> },
    { key: "op", label: `${unit}營業損益`, align: "right", sort: (r) => r[3], render: (r) => <span className="text-slate-400">{wan(r[3])}</span> },
  ];

  return (
    <div>
      <Note>
        部分上市櫃公司會在正式財報之前，每月或每季主動公告「自結損益」（公司自行結算、未經會計師查核）。財報要等季後一個多月，自結數字是最早看到獲利的地方。
        金額是稅前損益與營業損益（金融業沒有營業損益）。點一列看近 2 年每期稅前損益。
      </Note>
      <div className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <Pills<Kind> value={kind} onChange={(v) => { setKind(v); setPeriod(null); }} options={[
            ...(data.m ? [{ value: "m" as Kind, label: "月申報" }] : []),
            ...(data.q ? [{ value: "q" as Kind, label: "季申報" }] : []),
          ]} />
          {block && (
            <select value={cur} onChange={(e) => setPeriod(e.target.value)} className="rounded-lg border border-[#243247] bg-[#0d1220] px-3 py-2 text-sm text-slate-300 font-mono">
              {block.periods.map((p) => <option key={p} value={p}>{label(p)}（{block.data[p].length} 家）</option>)}
            </select>
          )}
        </div>
      </div>
      {block && (
        <KpiRow>
          <Kpi label="資料期間" value={label(cur)} sub={`${rows.length} 家公告`} />
          <Kpi label="稅前較去年同期成長" value={rows.filter((r) => (growth(r[5], r[7]) ?? 0) > 0).length} unit="家" color="text-[#f05252]" />
          <Kpi label="稅前虧損" value={rows.filter((r) => (r[5] ?? 0) < 0).length} unit="家" color="text-[#22c55e]" />
          <Kpi label="有說明差異原因" value={rows.filter((r) => r[9]).length} unit="家" />
        </KpiRow>
      )}
      {!rows.length ? <Empty>這期沒有公司公告自結損益。</Empty> :
        <ExpandTable<R> key={`${kind}${cur}`} rows={rows} columns={cols} rowKey={(r) => r[0]} detail={(r) => <Detail r={r} />} initialSort={{ key: "pre", desc: true }} />}
    </div>
  );
}
