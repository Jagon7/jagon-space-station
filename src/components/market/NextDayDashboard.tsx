"use client";

import { useMemo, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

// [日期, 代號, 名稱, 市場, 收盤, 成交值(億), 連板數, 一字鎖, 隔日開%, 高%, 低%, 收%, 隔日續漲停, 3日後收%]
type Row = [string, string, string, number, number, number, number, number, number | null, number | null, number | null, number | null, number | null, number | null];
type Data = { rows: Row[]; days: string[] };
type Range = "20" | "60" | "120";
type View = "stats" | "day";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const pf = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-slate-400" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

function stats(rows: Row[]) {
  const done = rows.filter((r) => r[11] != null);
  const n = done.length;
  return {
    n,
    up: n ? (done.filter((r) => r[11]! > 0).length / n) * 100 : null,
    open: avg(done.map((r) => r[8]!).filter((x) => x != null)),
    close: avg(done.map((r) => r[11]!)),
    again: n ? (done.filter((r) => r[12]).length / n) * 100 : null,
    fade: n ? (done.filter((r) => (r[8] ?? 0) > 0 && r[11]! < r[8]!).length / n) * 100 : null,
    c3: avg(done.map((r) => r[13]).filter((x): x is number => x != null)),
  };
}

const GROUPS: [string, (r: Row) => boolean][] = [
  ["全部", () => true],
  ["首次漲停（1 板）", (r) => r[6] === 1],
  ["2 連板", (r) => r[6] === 2],
  ["3 連板以上", (r) => r[6] >= 3],
  ["一字鎖漲停", (r) => r[7] === 1],
  ["非一字（盤中打開過或晚鎖）", (r) => r[7] === 0],
  ["上市", (r) => r[3] === 0],
  ["上櫃", (r) => r[3] === 1],
  ["成交值 < 1 億", (r) => r[5] < 1],
  ["成交值 1～5 億", (r) => r[5] >= 1 && r[5] < 5],
  ["成交值 ≥ 5 億", (r) => r[5] >= 5],
];

export default function NextDayDashboard() {
  const { data, error } = useStaticJson<Data>("market/nextday.json");
  const [range, setRange] = useState<Range>("60");
  const [view, setView] = useState<View>("stats");
  const [day, setDay] = useState<string | null>(null);

  const { rows, dates, daily } = useMemo(() => {
    if (!data) return { rows: [] as Row[], dates: [] as string[], daily: [] as { d: string; v: number | null; n: number }[] };
    const dates = [...new Set(data.rows.map((r) => r[0]))].sort();
    const since = dates.at(-Number(range)) ?? dates[0];
    const rows = data.rows.filter((r) => r[0] >= since);
    const daily = dates.filter((d) => d >= since).map((d) => {
      const rs = rows.filter((r) => r[0] === d && r[11] != null);
      return { d, v: avg(rs.map((r) => r[11]!)), n: rows.filter((r) => r[0] === d).length };
    });
    return { rows, dates, daily };
  }, [data, range]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>行情資料累積中。</Empty>;
  const s = stats(rows);
  const latest = dates.at(-1)!;
  const selDay = day ?? latest;
  const dayRows = data.rows.filter((r) => r[0] === selDay);

  const cols: Column<Row>[] = [
    { key: "name", label: "股票", render: (r) => <span><span className="text-slate-200">{r[2]}</span> <span className="font-mono text-xs text-[#8b97ab]">{r[1]}</span>{r[3] === 1 && <span className="ml-1 text-[10px] text-[#7c8aa0]">櫃</span>}</span> },
    { key: "streak", label: "連板", align: "right", sort: (r) => r[6], render: (r) => <span className={r[6] >= 2 ? "text-[#f59e0b]" : "text-slate-400"}>{r[6]}{r[7] ? " 一字" : ""}</span> },
    { key: "close", label: "漲停價", align: "right", sort: (r) => r[4], render: (r) => <span className="text-slate-300">{r[4]}</span> },
    { key: "value", label: "成交值（億）", align: "right", sort: (r) => r[5], render: (r) => <span className="text-slate-400">{r[5].toFixed(2)}</span> },
    { key: "open", label: "隔日開盤", align: "right", sort: (r) => r[8], render: (r) => <span className={tone(r[8])}>{pf(r[8])}</span> },
    { key: "high", label: "最高", align: "right", sort: (r) => r[9], render: (r) => <span className={tone(r[9])}>{pf(r[9])}</span> },
    { key: "low", label: "最低", align: "right", sort: (r) => r[10], render: (r) => <span className={tone(r[10])}>{pf(r[10])}</span> },
    { key: "c1", label: "隔日收盤", align: "right", sort: (r) => r[11], render: (r) => <span className={tone(r[11])}>{pf(r[11])}{r[12] ? " ▲停" : ""}</span> },
    { key: "c3", label: "3 日後", align: "right", sort: (r) => r[13], render: (r) => <span className={tone(r[13])}>{pf(r[13])}</span> },
  ];

  return (
    <div>
      <Note>
        追蹤每天收盤漲停的上市櫃普通股，隔一個交易日的開盤、最高、最低、收盤相對漲停價的漲跌，以及 3 個交易日後的表現。
        「隔日收紅」＝隔天收盤高於漲停價；「開高走低」＝隔天開高、但收盤低於開盤；「一字鎖」＝當天開高低收都在漲停價。漲停是用前一日收盤價 ×1.1 依升降單位推算。
      </Note>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Pills<View> value={view} onChange={setView} options={[{ value: "stats", label: "歷史勝率統計" }, { value: "day", label: "每日漲停股" }]} />
        {view === "stats" && <Pills<Range> value={range} onChange={setRange} options={[{ value: "20", label: "近 20 日" }, { value: "60", label: "近 60 日" }, { value: "120", label: "近 120 日" }]} />}
      </div>

      {view === "stats" ? (
        <>
          <KpiRow>
            <Kpi label="樣本（檔次）" value={s.n.toLocaleString()} sub={`${daily.length} 個交易日`} />
            <Kpi label="隔日收紅機率" value={s.up == null ? "—" : `${s.up.toFixed(1)}%`} color={(s.up ?? 0) >= 50 ? "text-[#f05252]" : "text-[#22c55e]"} />
            <Kpi label="隔日平均開盤／收盤" value={<><span className={tone(s.open)}>{pf(s.open)}</span><span className="text-[#7c8aa0] mx-1 text-base">/</span><span className={tone(s.close)}>{pf(s.close)}</span></>} />
            <Kpi label="續漲停／開高走低" value={<><span className="text-[#f05252]">{s.again?.toFixed(0)}%</span><span className="text-[#7c8aa0] mx-1 text-base">/</span><span className="text-[#22c55e]">{s.fade?.toFixed(0)}%</span></>} />
          </KpiRow>

          <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 mb-6">
            <div className="text-sm text-white font-semibold mb-3">每天漲停股隔日平均收盤漲跌</div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={daily} margin={{ top: 5, right: 5, bottom: 0, left: -20 }} onClick={(e) => { const l = (e as { activeLabel?: string } | null)?.activeLabel; if (l) { setDay(l); setView("day"); } }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#243247" vertical={false} />
                <XAxis dataKey="d" tickFormatter={md} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={20} />
                <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} unit="%" />
                <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
                  formatter={(v, _n, p) => [`${typeof v === "number" ? v.toFixed(2) : v}%（${(p.payload as { n: number }).n} 檔漲停）`, "隔日平均收盤"]} />
                <Bar dataKey="v" cursor="pointer">
                  {daily.map((d) => <Cell key={d.d} fill={(d.v ?? 0) >= 0 ? "#f05252" : "#22c55e"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className="text-[11px] text-[#7c8aa0] mt-1">點任一天的柱子看當天漲停股的隔日明細。</p>
          </div>

          <div className="rounded-xl border border-[#243247] bg-[#0d1220] overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr className="border-b border-[#243247] text-[11px] text-[#8b97ab] text-right">
                  <th className="px-4 py-2.5 font-normal text-left">分類</th><th className="px-4 py-2.5 font-normal">檔次</th>
                  <th className="px-4 py-2.5 font-normal">隔日收紅</th><th className="px-4 py-2.5 font-normal">平均開盤</th>
                  <th className="px-4 py-2.5 font-normal">平均收盤</th><th className="px-4 py-2.5 font-normal">續漲停</th>
                  <th className="px-4 py-2.5 font-normal">開高走低</th><th className="px-4 py-2.5 font-normal">3 日後平均</th>
                </tr>
              </thead>
              <tbody>
                {GROUPS.map(([name, f]) => {
                  const g = stats(rows.filter(f));
                  return (
                    <tr key={name} className="border-b border-[#243247]/60 last:border-0 text-right font-mono">
                      <td className="px-4 py-2 text-left font-sans text-slate-200">{name}</td>
                      <td className="px-4 py-2 text-slate-400">{g.n}</td>
                      <td className={`px-4 py-2 ${(g.up ?? 50) >= 50 ? "text-[#f05252]" : "text-[#22c55e]"}`}>{g.up == null ? "—" : `${g.up.toFixed(1)}%`}</td>
                      <td className={`px-4 py-2 ${tone(g.open)}`}>{pf(g.open)}</td>
                      <td className={`px-4 py-2 ${tone(g.close)}`}>{pf(g.close)}</td>
                      <td className="px-4 py-2 text-slate-300">{g.again == null ? "—" : `${g.again.toFixed(0)}%`}</td>
                      <td className="px-4 py-2 text-slate-300">{g.fade == null ? "—" : `${g.fade.toFixed(0)}%`}</td>
                      <td className={`px-4 py-2 ${tone(g.c3)}`}>{pf(g.c3)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <select value={selDay} onChange={(e) => setDay(e.target.value)}
              className="rounded-lg border border-[#243247] bg-[#0d1220] px-3 py-2 text-sm text-slate-200 font-mono">
              {[...dates].reverse().map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <span className="text-xs text-[#8b97ab]">
              {dayRows.length} 檔漲停{selDay === latest ? "・最新一天，隔日表現明天收盤後更新" : ""}
            </span>
          </div>
          {!dayRows.length ? <Empty>這天沒有漲停股。</Empty> :
            <SortTable<Row> key={selDay} rows={dayRows} columns={cols} rowKey={(r) => r[1]} initialSort={{ key: "value", desc: true }} rank />}
        </>
      )}
    </div>
  );
}
