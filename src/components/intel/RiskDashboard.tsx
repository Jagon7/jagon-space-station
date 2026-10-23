"use client";

import { Area, AreaChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Note } from "@/components/data-ui";

type Ind = {
  id: string; name: string; group: string; unit: string; dec: number; dir: number; th: [number, number]; calm: number; core: boolean; desc: string;
  date: string; value: number; chg1: number | null; chg5: number | null; chg20: number | null; pct: number; level: "正常" | "警戒" | "危險"; score: number;
  spark: [string, number][];
};
type Tw = { id: string; name: string; unit: string; dec: number; desc: string; date: string; value: number; chg1: number | null; chg5: number | null; pct: number; spark: [string, number][] };
type Cds = { sym: string; name: string; date: string; value: number; chg1: number; chg5: number; chg20: number | null; pct: number; price: number; vol: number; lev: number; debtB: number; spark: [string, number][] };
type Data = {
  credit?: Cds[]; cdsJumps?: string[];
  updatedAt: string; asof: string; temp: number | null; tempLabel: string | null; temp5: number | null; tempHist: [string, number][];
  alerts: string[]; indicators: Ind[]; tw: Tw[];
};

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const LEVEL: Record<Ind["level"], string> = { 正常: "bg-[#1e293b] text-[#94a3b8]", 警戒: "bg-[#f59e0b]/15 text-[#f59e0b]", 危險: "bg-[#f05252]/15 text-[#f05252]" };
const TEMP_COLOR = (t: number) => (t >= 75 ? "#f05252" : t >= 55 ? "#f59e0b" : t >= 30 ? "#4f8cff" : "#22c55e");
const fmt = (v: number, dec: number, unit: string) => `${v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec })}${unit === "bp" ? " bp" : unit === "%" ? "%" : unit === "口" ? " 口" : ""}`;
const delta = (v: number | null, dec: number, dir = 1) => {
  if (v == null) return <span className="text-[#475569]">—</span>;
  const risky = v * dir > 0;
  return <span className={v === 0 ? "text-[#8b97ab]" : risky ? "text-[#f59e0b]" : "text-[#8b97ab]"}>{v > 0 ? "+" : ""}{v.toFixed(dec)}</span>;
};

function Spark({ data, th, color }: { data: [string, number][]; th?: [number, number]; color: string }) {
  const rows = data.map(([d, v]) => ({ d, v }));
  return (
    <ResponsiveContainer width="100%" height={56}>
      <LineChart data={rows} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
        <YAxis hide domain={["auto", "auto"]} />
        {th && <ReferenceLine y={th[0]} stroke="#f59e0b" strokeDasharray="3 3" strokeOpacity={0.5} />}
        {th && <ReferenceLine y={th[1]} stroke="#f05252" strokeDasharray="3 3" strokeOpacity={0.5} />}
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 11 }} labelFormatter={(_, p) => p?.[0]?.payload?.d ?? ""} formatter={(v) => [String(v), ""]} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function PctBar({ pct, label = "近一年百分位（越高越緊張）" }: { pct: number; label?: string }) {
  return (
    <div className="mt-2">
      <div className="flex justify-between text-[10px] text-[#7c8aa0]"><span>{label}</span><span className="font-mono">{pct.toFixed(0)}</span></div>
      <div className="mt-1 h-1.5 rounded-full bg-[#1e293b] overflow-hidden"><div className="h-full rounded-full" style={{ width: `${pct}%`, background: TEMP_COLOR(pct) }} /></div>
    </div>
  );
}

function Card({ i }: { i: Ind }) {
  const color = i.level === "危險" ? "#f05252" : i.level === "警戒" ? "#f59e0b" : "#4f8cff";
  return (
    <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-4 flex flex-col">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm text-slate-200 font-medium">{i.name}</div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${LEVEL[i.level]}`}>{i.level}</span>
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-mono font-semibold text-white">{fmt(i.value, i.dec, i.unit)}</span>
        <span className="text-[10px] text-[#7c8aa0] font-mono">{md(i.date)}</span>
      </div>
      <div className="mt-1 flex gap-3 text-[11px] font-mono text-[#7c8aa0]">
        <span>1日 {delta(i.chg1, i.dec, i.dir)}</span><span>5日 {delta(i.chg5, i.dec, i.dir)}</span><span>20日 {delta(i.chg20, i.dec, i.dir)}</span>
      </div>
      <Spark data={i.spark} th={i.th} color={color} />
      <div className="text-[10px] text-[#7c8aa0] font-mono">警戒 {fmt(i.th[0], i.dec, i.unit)}｜危險 {fmt(i.th[1], i.dec, i.unit)}</div>
      <PctBar pct={i.pct} />
      <p className="mt-2 text-[11px] leading-relaxed text-[#8b97ab]">{i.desc}</p>
    </div>
  );
}

export default function RiskDashboard() {
  const { data, error } = useStaticJson<Data>("risk.json");
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const t = data.temp ?? 0;
  const groups = ["波動率", "信用", "利率與美元"];
  const hist = data.tempHist.map(([d, v]) => ({ d: md(d), v }));
  return (
    <div className="space-y-8">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,320px)_1fr]">
        <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
          <div className="text-xs text-[#8b97ab]">市場風險溫度（{md(data.asof)} 美股收盤）</div>
          <div className="mt-2 flex items-baseline gap-3">
            <span className="text-5xl font-mono font-bold" style={{ color: TEMP_COLOR(t) }}>{data.temp?.toFixed(0) ?? "—"}</span>
            <span className="text-lg font-semibold" style={{ color: TEMP_COLOR(t) }}>{data.tempLabel}</span>
          </div>
          {data.temp5 != null && <div className="mt-1 text-xs text-[#8b97ab]">5 日前 <span className="font-mono">{data.temp5.toFixed(0)}</span>（{t - data.temp5 >= 0 ? "+" : ""}{(t - data.temp5).toFixed(0)}）</div>}
          <div className="mt-3 h-2 rounded-full bg-gradient-to-r from-[#22c55e] via-[#4f8cff] via-60% to-[#f05252] relative">
            <div className="absolute -top-1 h-4 w-1 rounded bg-white" style={{ left: `calc(${t}% - 2px)` }} />
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-[#7c8aa0]"><span>低</span><span>中性 30</span><span>偏高 55</span><span>高 75</span></div>
          <div className="mt-4 text-xs text-white font-semibold">目前警示</div>
          {data.alerts.length
            ? <ul className="mt-1 space-y-1">{data.alerts.map((a) => <li key={a} className="text-xs text-[#f59e0b]">⚠ {a}</li>)}</ul>
            : <div className="mt-1 text-xs text-[#8b97ab]">沒有指標超過警戒門檻</div>}
        </div>
        <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
          <div className="text-xs text-[#8b97ab] mb-2">近一年風險溫度</div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={hist} margin={{ top: 5, right: 10, bottom: 0, left: -25 }}>
              <defs><linearGradient id="rt" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f59e0b" stopOpacity={0.35} /><stop offset="100%" stopColor="#f59e0b" stopOpacity={0} /></linearGradient></defs>
              <XAxis dataKey="d" tick={{ fontSize: 10, fill: "#7c8aa0" }} interval={40} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#7c8aa0" }} ticks={[0, 30, 55, 75, 100]} />
              <ReferenceLine y={55} stroke="#f59e0b" strokeDasharray="3 3" strokeOpacity={0.4} />
              <ReferenceLine y={75} stroke="#f05252" strokeDasharray="3 3" strokeOpacity={0.4} />
              <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 11 }} formatter={(v) => [String(v), "風險溫度"]} />
              <Area type="monotone" dataKey="v" stroke="#f59e0b" strokeWidth={1.5} fill="url(#rt)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      {groups.map((g) => {
        const items = data.indicators.filter((i) => i.group === g);
        return items.length ? (
          <section key={g}>
            <h2 className="text-sm font-semibold text-white mb-3">{g}</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{items.map((i) => <Card key={i.id} i={i} />)}</div>
          </section>
        ) : null;
      })}

      {!!data.credit?.length && (
        <section>
          <h2 className="text-sm font-semibold text-white mb-1">科技廠信用風險（股價隱含 CDS）</h2>
          <p className="text-xs text-[#8b97ab] mb-3 leading-relaxed">
            單一公司 CDS 沒有免費報價，這裡用 CreditGrades 模型，由股價、波動度、每股負債估算 5 年期 CDS 利差（Oracle 約 170～210bp，和新聞報導的實際 CDS 相近）。
            負債少的公司模型值接近 0，看不出變化；5 日上升 ≥ 75bp，或上升 ≥ 25bp 且 ≥ 25% 會推播警示。
          </p>
          <div className="rounded-xl border border-[#243247] bg-[#0d1220] overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr className="border-b border-[#243247] text-[11px] text-[#8b97ab] text-right">
                  <th className="px-4 py-2.5 font-normal text-left">公司</th><th className="px-3 py-2.5 font-normal">隱含 CDS</th>
                  <th className="px-3 py-2.5 font-normal">1 日</th><th className="px-3 py-2.5 font-normal">5 日</th><th className="px-3 py-2.5 font-normal">20 日</th>
                  <th className="px-3 py-2.5 font-normal w-40">近一年</th><th className="px-3 py-2.5 font-normal">股價</th><th className="px-3 py-2.5 font-normal">波動度</th>
                  <th className="px-3 py-2.5 font-normal">總負債</th><th className="px-3 py-2.5 font-normal">槓桿</th>
                </tr>
              </thead>
              <tbody>
                {data.credit.filter((c) => c.value >= 5 || data.cdsJumps?.includes(c.sym)).map((c) => {
                  const hit = data.cdsJumps?.includes(c.sym);
                  const d = (v: number | null) => v == null ? <span className="text-[#475569]">—</span> : <span className={v > 0 ? "text-[#f59e0b]" : v < 0 ? "text-[#8b97ab]" : "text-[#475569]"}>{v > 0 ? "+" : ""}{v.toFixed(0)}</span>;
                  return (
                    <tr key={c.sym} className={`border-b border-[#243247]/60 text-right font-mono ${hit ? "bg-[#f05252]/5" : ""}`}>
                      <td className="px-4 py-2 text-left font-sans"><span className="text-slate-200">{c.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{c.sym}</span>{hit && <span className="ml-1.5 text-[10px] text-[#f05252]">⚠ 跳升</span>}</td>
                      <td className={`px-3 py-2 font-semibold ${c.value >= 300 ? "text-[#f05252]" : c.value >= 100 ? "text-[#f59e0b]" : "text-slate-200"}`}>{c.value.toFixed(0)} bp</td>
                      <td className="px-3 py-2">{d(c.chg1)}</td><td className="px-3 py-2">{d(c.chg5)}</td><td className="px-3 py-2">{d(c.chg20)}</td>
                      <td className="px-3 py-1 w-40"><Spark data={c.spark} color={hit ? "#f05252" : "#4f8cff"} /></td>
                      <td className="px-3 py-2 text-slate-300">{c.price.toFixed(2)}</td><td className="px-3 py-2 text-slate-400">{c.vol.toFixed(0)}%</td>
                      <td className="px-3 py-2 text-slate-400">{c.debtB.toFixed(0)}B</td><td className="px-3 py-2 text-slate-400">{c.lev.toFixed(0)}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {data.credit.some((c) => c.value < 5) && (
            <p className="mt-2 text-[11px] text-[#8b97ab]">負債相對市值很低、模型值接近 0（信用風險極低）：{data.credit.filter((c) => c.value < 5).map((c) => `${c.name}（${c.value.toFixed(1)}bp）`).join("、")}</p>
          )}
          <p className="mt-2 text-[11px] text-[#7c8aa0]">波動度＝EWMA 年化股價波動；槓桿＝0.5×每股負債 ÷（股價＋0.5×每股負債），越高代表股價下跌時越接近違約邊界。模型估計值僅供觀察變化方向，不是實際 CDS 報價。</p>
        </section>
      )}

      {!!data.tw.length && (
        <section>
          <h2 className="text-sm font-semibold text-white mb-3">台股端</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.tw.map((i) => (
              <div key={i.id} className="rounded-xl border border-[#243247] bg-[#0d1220] p-4">
                <div className="text-sm text-slate-200 font-medium">{i.name}</div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-mono font-semibold text-white">{fmt(i.value, i.dec, i.unit)}</span>
                  <span className="text-[10px] text-[#7c8aa0] font-mono">{md(i.date)}</span>
                </div>
                <div className="mt-1 flex gap-3 text-[11px] font-mono text-[#7c8aa0]"><span>1日 {delta(i.chg1, i.dec)}</span><span>5日 {delta(i.chg5, i.dec)}</span></div>
                <Spark data={i.spark} color="#38bdf8" />
                <PctBar pct={i.pct} label="近期百分位（本站資料期間）" />
                <p className="mt-2 text-[11px] leading-relaxed text-[#8b97ab]">{i.desc}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <Note>
        風險溫度＝各核心指標（VIX、VVIX、VIX 期限結構、MOVE、高收益債利差、投資級債利差、金融壓力指數、美元 20 日變化）的分數平均；
        每個指標的分數是「絕對水準」（平靜 0、警戒門檻 50、危險門檻 80）和「近一年百分位」各占一半。
        CDS（信用違約交換）利差沒有免費公開資料：整體信用用 ICE BofA 公司債利差（OAS）代替，高收益債利差和 CDX HY 的走勢高度一致；個別科技廠用 CreditGrades 股價隱含 CDS。
        有新的風險條件成立（溫度進入偏高／高、核心指標達警戒或危險、VIX 單日大漲 20%、高收益債利差 20 日擴大 50bp、科技廠隱含 CDS 跳升）會推播 LINE，夜間 23:00～07:30 留到早上再發。
        美股資料為前一個交易日收盤，FRED 利差通常晚一天公布。
      </Note>
    </div>
  );
}
