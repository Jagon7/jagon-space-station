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
type Data = {
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
        CDS（信用違約交換）利差沒有免費公開資料，這裡用 ICE BofA 公司債利差（OAS）代替，高收益債利差和 CDX HY 的走勢高度一致。
        美股資料為前一個交易日收盤，FRED 利差通常晚一天公布。
      </Note>
    </div>
  );
}
