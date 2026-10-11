"use client";

import { useMemo, useState } from "react";
import { ComposedChart, Line, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceArea } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills } from "@/components/data-ui";

type Day = {
  d: string; ix: number | null; ixPct: number | null; adv: number; dec: number; unch: number; lu: number; ld: number;
  above20: number | null; nh: number | null; nl: number | null; value: number; mBal: number | null; mChg: number | null;
  sBal: number | null; fut5?: number | null; parts: Record<string, number>; score: number | null; label: string | null;
};
type Range = "60" | "120" | "all";

const PARTS: [string, string, (d: Day) => string][] = [
  ["breadth", "上漲家數比", (d) => `${d.adv} 漲 / ${d.dec} 跌`],
  ["limits", "漲停 − 跌停", (d) => `${d.lu} 漲停 / ${d.ld} 跌停`],
  ["trend", "站上月線比例", (d) => (d.above20 == null ? "—" : `${d.above20}%`)],
  ["highs", "20 日新高 − 新低", (d) => (d.nh == null ? "—" : `${d.nh} 新高 / ${d.nl} 新低`)],
  ["turnover", "量能（對比 20 日均量）", (d) => `${d.value.toLocaleString()} 億`],
  ["margin", "融資增減", (d) => (d.mChg == null ? "—" : `${d.mChg > 0 ? "+" : ""}${d.mChg.toLocaleString()} 張`)],
  ["futures", "外資期貨（5 日）", (d) => (d.fut5 == null ? "—" : `${d.fut5 > 0 ? "+" : ""}${d.fut5.toLocaleString()} 口`)],
];
const COLOR = (s: number | null) => (s == null ? "#64748b" : s >= 80 ? "#f05252" : s >= 60 ? "#f97316" : s >= 40 ? "#38bdf8" : s >= 20 ? "#22c55e" : "#10b981");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const signed = (v: number | null, digits = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`);

function Gauge({ score, label }: { score: number; label: string }) {
  const CX = 100, CY = 92, R = 78;
  const pt = (v: number, r = R) => { const a = Math.PI * (1 - v / 100); return [CX + r * Math.cos(a), CY - r * Math.sin(a)]; };
  const seg = (from: number, to: number, c: string) => {
    const [x1, y1] = pt(from), [x2, y2] = pt(to);
    return <path d={`M ${x1} ${y1} A ${R} ${R} 0 0 1 ${x2} ${y2}`} stroke={c} strokeWidth={14} fill="none" opacity={0.85} />;
  };
  const [nx, ny] = pt(score, 60);
  return (
    <svg viewBox="0 0 200 150" className="w-full max-w-[260px]">
      {seg(0, 20, "#10b981")}{seg(20, 40, "#22c55e")}{seg(40, 60, "#38bdf8")}{seg(60, 80, "#f97316")}{seg(80, 100, "#f05252")}
      <line x1={CX} y1={CY} x2={nx} y2={ny} stroke="#e2e8f0" strokeWidth={3} strokeLinecap="round" />
      <circle cx={CX} cy={CY} r={5} fill="#e2e8f0" />
      <text x={14} y={110} fontSize={9} fill="#64748b">冰點</text>
      <text x={186} y={110} fontSize={9} fill="#64748b" textAnchor="end">過熱</text>
      <text x={CX} y={128} textAnchor="middle" fontSize={28} fontWeight={700} fill={COLOR(score)}>{score}</text>
      <text x={CX} y={146} textAnchor="middle" fontSize={13} fill="#cbd5e1">{label}</text>
    </svg>
  );
}

export default function AtmosphereDashboard() {
  const { data, error } = useStaticJson<{ days: Day[] }>("market/atmosphere.json");
  const [range, setRange] = useState<Range>("120");
  const [pick, setPick] = useState<string | null>(null);
  const days = useMemo(() => data?.days.filter((d) => d.score != null) ?? [], [data]);
  const withMa = useMemo(() => days.map((d, i) => {
    const w = days.slice(Math.max(0, i - 4), i + 1);
    return { ...d, ma5: Math.round(w.reduce((a, x) => a + x.score!, 0) / w.length) };
  }), [days]);
  const shown = range === "all" ? withMa : withMa.slice(-Number(range));
  const hasIx = shown.some((d) => d.ix != null);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!days.length) return <Empty>行情資料累積中。</Empty>;
  const cur = days.find((d) => d.d === pick) ?? days.at(-1)!;
  const prev = days[days.indexOf(cur) - 1];
  const avg5 = Math.round(days.slice(Math.max(0, days.indexOf(cur) - 4), days.indexOf(cur) + 1).reduce((s, d) => s + d.score!, 0) / Math.min(5, days.indexOf(cur) + 1));

  return (
    <div>
      <Note>
        把每天盤面的七個面向——上漲家數比、漲停減跌停、站上月線比例、創 20 日新高減新低、量能、融資增減、外資台指期淨未平倉 5 日變化——各自換算成「在過去這段期間排第幾百分位」，再平均成 0～100 的氣氛分數。
        80 以上「過熱」、60～80「偏多」、40～60「中性」、20～40「偏空」、20 以下「冰點」。上市櫃普通股都算在內（不含 ETF）。
      </Note>

      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4 mb-6">
        <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 flex flex-col items-center">
          <div className="text-xs text-[#8b97ab] mb-2 font-mono">{cur.d}{pick ? "（點選的日子）" : "（最新）"}</div>
          <Gauge score={cur.score!} label={cur.label!} />
          <div className="mt-3 grid grid-cols-3 gap-3 w-full text-center">
            <div><div className="text-[10px] text-[#8b97ab]">前一日</div><div className="font-mono text-sm" style={{ color: COLOR(prev?.score ?? null) }}>{prev?.score ?? "—"}</div></div>
            <div><div className="text-[10px] text-[#8b97ab]">5 日平均</div><div className="font-mono text-sm" style={{ color: COLOR(avg5) }}>{avg5}</div></div>
            <div><div className="text-[10px] text-[#8b97ab]">加權指數</div><div className={`font-mono text-sm ${(cur.ixPct ?? 0) >= 0 ? "text-[#f05252]" : "text-[#22c55e]"}`}>{cur.ixPct == null ? "—" : `${signed(cur.ixPct)}%`}</div></div>
          </div>
          {pick && <button onClick={() => setPick(null)} className="mt-3 text-xs text-[#8b97ab] hover:text-[#4f8cff]">回到最新一天</button>}
        </div>
        <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
          <div className="text-xs text-[#8b97ab] mb-3">七個面向（百分位，越高越熱）</div>
          <div className="space-y-3">
            {PARTS.map(([k, name, fmt]) => {
              const v = cur.parts[k];
              return (
                <div key={k} className="grid grid-cols-[8.5rem_1fr_3rem] sm:grid-cols-[10rem_1fr_3rem_11rem] items-center gap-3">
                  <span className="text-sm text-slate-300">{name}</span>
                  <div className="h-2.5 rounded-full bg-[#243247] overflow-hidden">
                    {v != null && <div className="h-full rounded-full" style={{ width: `${Math.max(3, v)}%`, background: COLOR(v) }} />}
                  </div>
                  <span className="font-mono text-sm text-right" style={{ color: COLOR(v ?? null) }}>{v ?? "—"}</span>
                  <span className="hidden sm:block text-xs text-[#8b97ab] font-mono text-right">{fmt(cur)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <KpiRow>
        <Kpi label="漲停／跌停" value={<><span className="text-[#f05252]">{cur.lu}</span><span className="text-[#7c8aa0] mx-1">/</span><span className="text-[#22c55e]">{cur.ld}</span></>} unit="檔" />
        <Kpi label="上漲／下跌家數" value={<><span className="text-[#f05252]">{cur.adv}</span><span className="text-[#7c8aa0] mx-1">/</span><span className="text-[#22c55e]">{cur.dec}</span></>} />
        <Kpi label="成交值（上市櫃普通股）" value={cur.value.toLocaleString()} unit="億" />
        <Kpi label="融資增減" value={cur.mChg == null ? "—" : `${cur.mChg > 0 ? "+" : ""}${cur.mChg.toLocaleString()}`} unit="張" color={(cur.mChg ?? 0) >= 0 ? "text-[#f05252]" : "text-[#22c55e]"} />
      </KpiRow>

      <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 mb-6">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <span className="text-sm text-white font-semibold">氣氛分數與加權指數</span>
          <Pills<Range> value={range} onChange={setRange} options={[{ value: "60", label: "近 60 日" }, { value: "120", label: "近 120 日" }, { value: "all", label: "全部" }]} />
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={shown} margin={{ top: 5, right: 0, bottom: 0, left: -20 }}
            onClick={(e) => { const l = (e as { activeLabel?: string } | null)?.activeLabel; if (l) setPick(l); }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#243247" />
            <ReferenceArea yAxisId="s" y1={80} y2={100} fill="#f05252" fillOpacity={0.06} />
            <ReferenceArea yAxisId="s" y1={0} y2={20} fill="#10b981" fillOpacity={0.06} />
            <XAxis dataKey="d" tickFormatter={md} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={24} />
            <YAxis yAxisId="s" domain={[0, 100]} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
            {hasIx && <YAxis yAxisId="ix" orientation="right" domain={["auto", "auto"]} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} width={60} />}
            <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
              formatter={(v, n) => [typeof v === "number" ? v.toLocaleString() : String(v), n === "score" ? "氣氛分數" : n === "ma5" ? "5 日平均" : "加權指數"]} />
            <Area yAxisId="s" type="monotone" dataKey="score" stroke="#38bdf8" strokeOpacity={0.45} fill="#38bdf8" fillOpacity={0.1} strokeWidth={1} dot={false} />
            <Line yAxisId="s" type="monotone" dataKey="ma5" stroke="#f59e0b" strokeWidth={2.2} dot={false} />
            {hasIx && <Line yAxisId="ix" type="monotone" dataKey="ix" stroke="#e2e8f0" strokeWidth={1.2} dot={false} connectNulls />}
          </ComposedChart>
        </ResponsiveContainer>
        <p className="text-[11px] text-[#7c8aa0] mt-1">藍色為每日氣氛分數、橘線為 5 日平均（左軸），白線為加權指數（右軸）。點圖上任一天可看當天的七個面向。</p>
      </div>

      <div className="rounded-xl border border-[#243247] bg-[#0d1220] overflow-x-auto">
        <table className="w-full text-sm whitespace-nowrap">
          <thead>
            <tr className="border-b border-[#243247] text-[11px] text-[#8b97ab] text-right">
              <th className="px-3 py-2.5 font-normal text-left">日期</th><th className="px-3 py-2.5 font-normal">分數</th><th className="px-3 py-2.5 font-normal text-left">氣氛</th>
              <th className="px-3 py-2.5 font-normal">加權指數</th><th className="px-3 py-2.5 font-normal">漲／跌家數</th><th className="px-3 py-2.5 font-normal">漲停／跌停</th>
              <th className="px-3 py-2.5 font-normal">站上月線</th><th className="px-3 py-2.5 font-normal">新高／新低</th><th className="px-3 py-2.5 font-normal">成交值（億）</th><th className="px-3 py-2.5 font-normal">融資增減（張）</th>
            </tr>
          </thead>
          <tbody>
            {[...days].reverse().slice(0, 30).map((d) => (
              <tr key={d.d} onClick={() => { setPick(d.d); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                className={`border-b border-[#243247]/60 last:border-0 text-right font-mono cursor-pointer hover:bg-[#111a2c] ${d.d === cur.d ? "bg-[#111a2c]" : ""}`}>
                <td className="px-3 py-2 text-left text-slate-300">{d.d}</td>
                <td className="px-3 py-2 font-semibold" style={{ color: COLOR(d.score) }}>{d.score}</td>
                <td className="px-3 py-2 text-left font-sans" style={{ color: COLOR(d.score) }}>{d.label}</td>
                <td className={`px-3 py-2 ${(d.ixPct ?? 0) >= 0 ? "text-[#f05252]" : "text-[#22c55e]"}`}>{d.ixPct == null ? "—" : `${signed(d.ixPct)}%`}</td>
                <td className="px-3 py-2"><span className="text-[#f05252]">{d.adv}</span> / <span className="text-[#22c55e]">{d.dec}</span></td>
                <td className="px-3 py-2"><span className="text-[#f05252]">{d.lu}</span> / <span className="text-[#22c55e]">{d.ld}</span></td>
                <td className="px-3 py-2 text-slate-300">{d.above20 == null ? "—" : `${d.above20}%`}</td>
                <td className="px-3 py-2 text-slate-400">{d.nh ?? "—"} / {d.nl ?? "—"}</td>
                <td className="px-3 py-2 text-slate-300">{d.value.toLocaleString()}</td>
                <td className={`px-3 py-2 ${(d.mChg ?? 0) >= 0 ? "text-[#f05252]" : "text-[#22c55e]"}`}>{d.mChg == null ? "—" : `${d.mChg > 0 ? "+" : ""}${d.mChg.toLocaleString()}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
