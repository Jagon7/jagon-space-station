"use client";

import { useMemo, useState } from "react";
import { ComposedChart, BarChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, ReferenceLine } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";
import ExpandTable, { StockCell, type XColumn } from "@/components/ExpandTable";

// [代號, 名稱, 市場, 收盤, 外1, 投1, 自1, 合1, 外5, 投5, 自5, 合5, 外20, 投20, 自20, 合20, 外60, 投60, 自60, 合60, 外資連買, 投信連買]
type R = (string | number | null)[];
type Data = { date: string; days: number; market: [string, number, number, number][]; rows: R[] };
type Period = "1" | "5" | "20" | "60";
type Who = "f" | "t" | "d" | "all";
type Special = "none" | "tStreak" | "fStreak" | "both" | "opposite";

const IDX: Record<Period, number> = { "1": 4, "5": 8, "20": 12, "60": 16 };
const OFF: Record<Who, number> = { f: 0, t: 1, d: 2, all: 3 };
const WHO_LABEL: Record<Who, string> = { f: "外資", t: "投信", d: "自營商", all: "三大法人" };
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const lots = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toLocaleString()}`);
const yi = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1)}億`);
const n = (r: R, i: number) => (r[i] as number | null) ?? null;

function Detail({ code }: { code: string }) {
  const { data, error } = useStaticJson<[string, number | null, number | null, number | null, number | null, number | null][]>(`chips/insti/${code}.json`);
  if (!data) return <div className="py-8 text-center text-xs text-[#8b97ab]">{error ? "沒有資料" : "載入中…"}</div>;
  const rows = data.map(([d, f, t, dl, , c]) => ({ d, f, t, dl, c }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={rows} margin={{ top: 5, right: 0, bottom: 0, left: -5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243247" vertical={false} />
        <XAxis dataKey="d" tickFormatter={md} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={20} />
        <YAxis yAxisId="v" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis yAxisId="p" orientation="right" domain={["auto", "auto"]} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
          formatter={(v, nm) => [typeof v === "number" ? v.toLocaleString() : String(v), String(nm)]} />
        <Legend formatter={(v) => <span className="text-xs text-slate-400">{v}</span>} />
        <ReferenceLine yAxisId="v" y={0} stroke="#334155" />
        <Bar yAxisId="v" dataKey="f" name="外資（張）" stackId="a" fill="#38bdf8" />
        <Bar yAxisId="v" dataKey="t" name="投信（張）" stackId="a" fill="#f59e0b" />
        <Bar yAxisId="v" dataKey="dl" name="自營商（張）" stackId="a" fill="#a78bfa" />
        <Line yAxisId="p" dataKey="c" name="收盤" stroke="#e2e8f0" dot={false} strokeWidth={1.5} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function InstitutionalDashboard() {
  const { data, error } = useStaticJson<Data>("chips/insti.json");
  const [period, setPeriod] = useState<Period>("1");
  const [who, setWho] = useState<Who>("f");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [special, setSpecial] = useState<Special>("none");
  const [only, setOnly] = useState<string | null>(null);

  const col = IDX[period] + OFF[who];
  const amt = (r: R, i: number) => { const v = n(r, i), p = n(r, 3); return v == null || p == null ? null : (v * p * 1000) / 1e8; };
  const rows = useMemo(() => {
    let rs = (data?.rows ?? []).filter((r) => /^[1-9]\d{3}$/.test(String(r[0])));
    if (only) return (data?.rows ?? []).filter((r) => r[0] === only);
    if (special === "tStreak") rs = rs.filter((r) => (n(r, 21) ?? 0) >= 3);
    else if (special === "fStreak") rs = rs.filter((r) => (n(r, 20) ?? 0) >= 3);
    else if (special === "both") rs = rs.filter((r) => (n(r, IDX[period]) ?? 0) > 0 && (n(r, IDX[period] + 1) ?? 0) > 0);
    else if (special === "opposite") rs = rs.filter((r) => (n(r, IDX[period]) ?? 0) * (n(r, IDX[period] + 1) ?? 0) < 0);
    else rs = rs.filter((r) => (side === "buy" ? (n(r, col) ?? 0) > 0 : (n(r, col) ?? 0) < 0));
    return rs;
  }, [data, col, side, special, period, only]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>三大法人資料累積中。</Empty>;
  const last = data.market.at(-1)!;
  const sum5 = (k: 1 | 2 | 3) => data.market.slice(-5).reduce((s, x) => s + x[k], 0);
  const chart = data.market.slice(-40).map(([d, f, t, dl]) => ({ d, f, t, dl }));
  const pl = period === "1" ? "當日" : `近 ${period} 日`;

  const cols: XColumn<R>[] = [
    { key: "name", label: "股票", render: (r) => <StockCell code={String(r[0])} name={String(r[1])} mk={r[2] ? "上櫃" : "上市"} /> },
    { key: "close", label: "收盤", align: "right", sort: (r) => n(r, 3), render: (r) => <span className="text-slate-300">{r[3] ?? "—"}</span> },
    { key: "main", label: `${WHO_LABEL[who]} ${pl}（張）`, align: "right", sort: (r) => n(r, col), render: (r) => <span className={`font-semibold ${tone(n(r, col))}`}>{lots(n(r, col))}</span> },
    { key: "amt", label: "估計金額", align: "right", sort: (r) => amt(r, col), render: (r) => <span className={tone(amt(r, col))}>{yi(amt(r, col))}</span> },
    { key: "f", label: `外資 ${pl}`, align: "right", sort: (r) => n(r, IDX[period]), render: (r) => <span className={tone(n(r, IDX[period]))}>{lots(n(r, IDX[period]))}</span> },
    { key: "t", label: `投信 ${pl}`, align: "right", sort: (r) => n(r, IDX[period] + 1), render: (r) => <span className={tone(n(r, IDX[period] + 1))}>{lots(n(r, IDX[period] + 1))}</span> },
    { key: "d", label: `自營 ${pl}`, align: "right", sort: (r) => n(r, IDX[period] + 2), render: (r) => <span className={tone(n(r, IDX[period] + 2))}>{lots(n(r, IDX[period] + 2))}</span> },
    { key: "fs", label: "外資連買", align: "right", sort: (r) => n(r, 20), render: (r) => <span className={tone(n(r, 20))}>{n(r, 20) ? `${n(r, 20)! > 0 ? "買" : "賣"} ${Math.abs(n(r, 20)!)} 天` : "—"}</span> },
    { key: "ts", label: "投信連買", align: "right", sort: (r) => n(r, 21), render: (r) => <span className={tone(n(r, 21))}>{n(r, 21) ? `${n(r, 21)! > 0 ? "買" : "賣"} ${Math.abs(n(r, 21)!)} 天` : "—"}</span> },
  ];

  return (
    <div>
      <Note>
        外資、投信、自營商每天在上市櫃個股的買賣超（單位：張；估計金額＝張數 × 最新收盤價）。「連買」＝連續買超（或賣超）幾個交易日。
        「土洋同買」＝外資和投信同時買超；「土洋對作」＝一買一賣。資料約 {data.days} 個交易日，點一列看該股每日法人進出。
      </Note>
      <KpiRow>
        <Kpi label={`${md(last[0])} 外資`} value={yi(last[1])} color={tone(last[1])} sub={`5 日 ${yi(sum5(1))}`} />
        <Kpi label={`${md(last[0])} 投信`} value={yi(last[2])} color={tone(last[2])} sub={`5 日 ${yi(sum5(2))}`} />
        <Kpi label={`${md(last[0])} 自營商`} value={yi(last[3])} color={tone(last[3])} sub={`5 日 ${yi(sum5(3))}`} />
        <Kpi label="投信連買 ≥ 3 天" value={data.rows.filter((r) => (n(r, 21) ?? 0) >= 3).length} unit="檔" color="text-[#f59e0b]" />
      </KpiRow>
      <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 mb-6">
        <div className="text-sm text-white font-semibold mb-3">全市場法人每日買賣超（億元，估計）</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chart} margin={{ top: 5, right: 5, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#243247" vertical={false} />
            <XAxis dataKey="d" tickFormatter={md} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={20} />
            <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
              formatter={(v, nm) => [`${typeof v === "number" ? v.toFixed(1) : v} 億`, nm === "f" ? "外資" : nm === "t" ? "投信" : "自營商"]} />
            <ReferenceLine y={0} stroke="#334155" />
            <Bar dataKey="f" fill="#38bdf8" />
            <Bar dataKey="t" fill="#f59e0b" />
            <Bar dataKey="dl" fill="#a78bfa" />
          </BarChart>
        </ResponsiveContainer>
        <p className="text-[11px] text-[#7c8aa0]">藍：外資；橘：投信；紫：自營商。</p>
      </div>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <Pills<Who> value={who} onChange={(v) => { setWho(v); setSpecial("none"); setOnly(null); }} options={[{ value: "f", label: "外資" }, { value: "t", label: "投信" }, { value: "d", label: "自營商" }, { value: "all", label: "合計" }]} />
        <Pills<"buy" | "sell"> value={side} onChange={(v) => { setSide(v); setSpecial("none"); setOnly(null); }} options={[{ value: "buy", label: "買超" }, { value: "sell", label: "賣超" }]} />
        <Pills<Period> value={period} onChange={(v) => { setPeriod(v); setOnly(null); }} options={[{ value: "1", label: "當日" }, { value: "5", label: "5 日" }, { value: "20", label: "20 日" }, { value: "60", label: "60 日" }]} />
        <Pills<Special> value={special} onChange={(v) => { setSpecial(v); setOnly(null); }} options={[{ value: "none", label: "—" }, { value: "tStreak", label: "投信連買 ≥ 3" }, { value: "fStreak", label: "外資連買 ≥ 3" }, { value: "both", label: "土洋同買" }, { value: "opposite", label: "土洋對作" }]} />
        <div className="ml-auto"><SearchBox placeholder="查個股" items={data.rows.map((r) => ({ code: String(r[0]), name: String(r[1]) }))} onPick={setOnly} /></div>
      </div>
      {only && <button onClick={() => setOnly(null)} className="mb-2 text-xs text-[#8b97ab] hover:text-[#4f8cff]">← 回到排行</button>}
      {!rows.length ? <Empty>沒有符合條件的股票。</Empty> :
        <ExpandTable<R> key={`${col}${side}${special}${only}`} rows={rows} columns={cols} rowKey={(r) => String(r[0])} detail={(r) => <Detail code={String(r[0])} />}
          initialSort={{ key: special === "tStreak" ? "ts" : special === "fStreak" ? "fs" : "amt", desc: side === "buy" || special !== "none" }} />}
    </div>
  );
}
