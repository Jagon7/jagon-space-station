"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { Kpi, KpiRow, Note, Pills } from "@/components/data-ui";

type S = { n: number; r5?: number; r10?: number; r20?: number; r40?: number; win20?: number; mae20?: number; worst?: number; newLow?: number };
type Now = { date: string; close: number; dd: number; rsi: number; bias20: number; vix: number | null; vixOff: number; ma200s: number; upDay: boolean; ret1: number;
  usPrev: number | null; fired: string[]; confirmOthers?: number };
type Ep = { date: string; dd: number; ma200s: number; path: (number | null)[]; lowIn: number; lowPct: number; r20: number; r60: number };
type IS = { avg: number; med: number; win: number; worst: number } | null;
type Inst = { fut: IS; futM: IS; futCall: number; futStop: IS; atm: IS; otm: IS; sf: IS; sfM: IS; n: number };
type Data = { split: string; markets: Record<string, string>; signals: Record<string, string>; table: Record<string, Record<string, { train: S; test: S; dates: string[] }>>;
  pooled: Record<string, { train: S; test: S }>; cross: Record<string, { train: S; test: S }>; now: Record<string, Now>; episodes: Ep[];
  instruments: Record<string, Record<string, Inst>>; instDates: Record<string, string[]>;
  stocks?: { episodes: { peak: string; trough: string; drop: number }[];
    features: Record<string, { label: string; r20?: { avg: number; pos: number; n: number; lo: number; hi: number }; l20?: { avg: number; pos: number; n: number }; r60?: { avg: number; pos: number; n: number }; ctrl?: { avg: number; pos: number; n: number } }>;
    sectors: Record<string, { n: number; excess20: number; pos: number; eps: number }>; ssf: Record<string, { n: number; r20: number; r60: number; win20: number }>;
    repeat: [string, string, string, boolean, number][];
    now?: { date: string; cut: { drop: number; marginUse: number }; list: { code: string; name: string; mk: string; sector: string; ssf: boolean; close: number; drop: number; marginUse: number; value: number; goodSector: boolean; score?: number; last5?: number | null; trust10?: number | null; mcap?: number }[] };
    score?: { q: number[]; qPos: number[]; top10: number; top10Pos: number; old: number; oldPos: number; eps: unknown[] } } | null;
  swings?: Record<string, { list: { peak: string; trough: string; drop: number; days: number; r20: number; r60: number }[]; current: { peak: string; low: string; drop: number; days: number; now: number } | null; dd60: number }> };

const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const MK = ["^TWII", "^GSPC", "^IXIC", "^SOX", "^N225", "^KS11"];
const SIG_ORDER = ["A+", "B+", "A", "B", "up5", "keyRev", "vix30", "dd20", "rsi25", "z25", "knife"];
const COLORS = ["#f05252", "#f59e0b", "#4f8cff", "#22c55e", "#a78bfa", "#ec4899", "#06b6d4", "#eab308", "#94a3b8", "#14b8a6", "#f97316", "#8b5cf6", "#84cc16", "#e11d48", "#0ea5e9", "#d946ef", "#64748b"];
const INST: [keyof Inst, string][] = [["fut", "台指期（名目）"], ["futM", "台指期（保證金）"], ["futStop", "台指期＋−4% 停損"], ["atm", "價平買權"], ["otm", "價外 3% 買權"], ["sf", "個股期 9 檔（名目）"], ["sfM", "個股期（保證金）"]];

function Cell({ s }: { s: S }) {
  if (!s || !s.n) return <span className="text-[#7c8aa0]">—</span>;
  return (
    <span className="font-mono text-xs whitespace-nowrap">
      <span className="text-[#7c8aa0]">{s.n}次 </span>
      <span className={tone(s.r20)}>{pct(s.r20)}</span>
      <span className="text-slate-300"> {s.win20}%</span>
      <span className="text-[#22c55e]"> {pct(s.mae20)}</span>
    </span>
  );
}

export default function BottomDashboard() {
  const { data, error } = useStaticJson<Data>("bottom.json");
  const [mk, setMk] = useState("^TWII");
  const [sigInst, setSigInst] = useState("深跌＋VIX 回落＋止跌");
  const [hold, setHold] = useState<"5" | "10" | "20">("20");
  const [epSel, setEpSel] = useState<"all" | "up" | "down">("all");
  const [swMk, setSwMk] = useState("^TWII");
  const eps = useMemo(() => (data?.episodes ?? []).filter((e) => epSel === "all" || (epSel === "up" ? e.ma200s > 0 : e.ma200s <= 0)), [data, epSel]);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const tw = data.now["^TWII"];
  const aOk = tw.fired.includes("A"), bOk = tw.fired.includes("B");
  const series = Array.from({ length: 81 }, (_, i) => {
    const row: Record<string, number | null> = { t: i - 20 };
    eps.forEach((e) => { row[e.date] = e.path[i]; });
    return row;
  });
  const inst = data.instruments[sigInst]?.[hold];

  return (
    <div>
      <div className={`mb-4 rounded-xl border p-4 ${aOk || bOk ? "border-[#22c55e]/40 bg-[#22c55e]/[0.06]" : "border-[#f05252]/40 bg-[#f05252]/[0.06]"}`}>
        <div className={`text-base font-semibold mb-1 ${aOk || bOk ? "text-[#22c55e]" : "text-[#f05252]"}`}>
          {aOk || bOk ? "🟢 抄底訊號出現" : tw.dd <= -8 ? "🔴 回檔中，還沒有抄底訊號" : "⚪ 沒有在回檔"}（台股 {tw.date}）
        </div>
        <div className="text-xs text-slate-300 leading-relaxed">
          訊號 A（深跌＋前一晚美股大漲 ≥1.5%）：{aOk ? "✅" : "⬜"}　前一晚 S&P {pct(tw.usPrev, 2)}<br />
          訊號 B（深跌＋收紅＋VIX 從 10 日高點回落 ≥10%）：{bOk ? "✅" : "⬜"}　今天{tw.upDay ? "收紅" : "收黑"}、VIX {tw.vix?.toFixed(1)}（回落 {tw.vixOff.toFixed(0)}%）<br />
          年線（200 日均線）{tw.ma200s > 0 ? "仍向上" : "已向下"}（{pct(tw.ma200s)}）・其他市場（美、費半、日、韓）近 3 天止跌：{tw.confirmOthers ?? "—"}／4
        </div>
      </div>
      <KpiRow>
        <Kpi label="加權距 60 日高點" value={pct(tw.dd)} color={tw.dd <= -12 ? "text-[#22c55e]" : "text-white"} sub={`收盤 ${tw.close.toLocaleString(undefined, { maximumFractionDigits: 0 })}（${pct(tw.ret1, 2)}）`} />
        <Kpi label="RSI14／20 日乖離" value={`${tw.rsi.toFixed(0)}／${pct(tw.bias20)}`} />
        <Kpi label="VIX" value={tw.vix?.toFixed(1) ?? "—"} sub={`10 日高點回落 ${tw.vixOff.toFixed(0)}%`} />
        <Kpi label="年線方向" value={tw.ma200s > 0 ? "向上" : "向下"} color={tw.ma200s > 0 ? "text-[#f05252]" : "text-[#22c55e]"} sub="向下＝2008 型空頭，訊號容易失效" />
      </KpiRow>

      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] overflow-x-auto">
        <div className="px-4 pt-4 text-sm font-semibold text-white">各市場現況</div>
        <table className="w-full text-sm mt-2">
          <thead><tr className="border-b border-[#243247] text-[11px] text-[#8b97ab]">
            {["市場", "日期", "距 60 日高", "當天", "RSI14", "年線", "已出現的訊號"].map((h, i) => <th key={h} className={`px-4 py-2 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}
          </tr></thead>
          <tbody>{MK.map((s) => { const n = data.now[s]; return (
            <tr key={s} className="border-b border-[#243247]/60 last:border-0">
              <td className="px-4 py-2 text-slate-200">{data.markets[s]}</td>
              <td className="px-4 py-2 text-right font-mono text-xs text-[#8b97ab]">{n.date.slice(5)}</td>
              <td className={`px-4 py-2 text-right font-mono ${n.dd <= -12 ? "text-[#22c55e]" : "text-slate-300"}`}>{pct(n.dd)}</td>
              <td className={`px-4 py-2 text-right font-mono ${tone(n.ret1)}`}>{pct(n.ret1, 2)}</td>
              <td className="px-4 py-2 text-right font-mono text-slate-300">{n.rsi.toFixed(0)}</td>
              <td className={`px-4 py-2 text-right font-mono ${n.ma200s > 0 ? "text-[#f05252]" : "text-[#22c55e]"}`}>{n.ma200s > 0 ? "↑" : "↓"} {pct(n.ma200s)}</td>
              <td className="px-4 py-2 text-right text-xs text-[#f59e0b]">{n.fired.length ? n.fired.map((k) => data.signals[k]?.split("：")[0] ?? k).join("、") : "—"}</td>
            </tr>); })}</tbody>
        </table>
      </section>

      {data.swings?.[swMk] && (() => {
        const sw = data.swings![swMk];
        const drops = sw.list.map((x) => x.drop).sort((a, b) => a - b);
        const med = drops.length ? drops[Math.floor(drops.length / 2)] : 0;
        const B = [[-12, -10], [-15, -12], [-20, -15], [-25, -20], [-30, -25], [-40, -30], [-100, -40]];
        const maxN = Math.max(1, ...B.map(([lo, hi]) => drops.filter((d) => d > lo && d <= hi).length));
        const nowDrop = Math.min(sw.current?.now ?? 0, sw.dd60);
        return (
          <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-semibold text-white">過去回檔跌到多深才止跌反彈（收盤從波段高點跌 ≥ 10%、之後反彈 ≥ 10% 算一波）</div>
              <Pills<string> value={swMk} onChange={setSwMk} options={MK.filter((s) => data.swings![s]).map((s) => ({ value: s, label: data.markets[s] }))} />
            </div>
            <div className="mb-3 text-xs text-slate-300">
              2005 年起 {sw.list.length} 波，止跌時跌幅中位數 <span className="font-mono text-[#f59e0b]">{med.toFixed(1)}%</span>、最深 <span className="font-mono">{drops[0]?.toFixed(1)}%</span>；
              這一波{sw.current ? `從 ${sw.current.peak} 高點已跌 ${sw.current.now.toFixed(1)}%（${sw.current.days} 天）` : "目前不在 10% 以上的回檔中"}，距 60 日高點 {sw.dd60.toFixed(1)}%。
            </div>
            <div className="space-y-1">{B.map(([lo, hi]) => { const n = drops.filter((d) => d > lo && d <= hi).length; const here = nowDrop > lo && nowDrop <= hi; return (
              <div key={lo} className="grid grid-cols-[5.5rem_1fr_2.5rem] items-center gap-2 text-xs">
                <span className={`font-mono ${here ? "text-white font-semibold" : "text-[#8b97ab]"}`}>{-hi}～{lo <= -100 ? "" : -lo}%{here ? " ◀ 現在" : ""}</span>
                <div className="h-3 rounded-sm bg-[#141c2e]"><div className={`h-3 rounded-sm ${here ? "bg-white" : "bg-[#4f8cff]/70"}`} style={{ width: `${(n / maxN) * 100}%` }} /></div>
                <span className="font-mono text-right text-slate-300">{n} 次</span>
              </div>); })}</div>
            <div className="mt-3 max-h-56 overflow-y-auto">{[...sw.list].reverse().map((x) => (
              <div key={x.peak} className="flex flex-wrap justify-between gap-2 border-b border-[#243247]/40 py-1 font-mono text-[11px] text-[#8b97ab]">
                <span className="text-slate-300">{x.peak} → {x.trough}</span>
                <span>跌 <span className="text-[#22c55e]">{x.drop.toFixed(1)}%</span>（{x.days} 天）・之後 20 天 <span className={tone(x.r20)}>{pct(x.r20)}</span>、60 天 <span className={tone(x.r60)}>{pct(x.r60)}</span></span>
              </div>))}</div>
          </section>
        );
      })()}

      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4 overflow-x-auto">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold text-white">抄底訊號回測（20 天後報酬／勝率／進場後平均再跌）</div>
          <Pills<string> value={mk} onChange={setMk} options={[{ value: "pool", label: "全市場合併" }, ...MK.map((s) => ({ value: s, label: data.markets[s] }))]} />
        </div>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-[#243247] text-[11px] text-[#8b97ab]">
            <th className="px-3 py-2 font-normal text-left">訊號</th>
            <th className="px-3 py-2 font-normal text-right">2005～{data.split.slice(0, 4)}（建模）</th>
            <th className="px-3 py-2 font-normal text-right">{data.split.slice(0, 4)}～（驗證）</th>
            <th className="px-3 py-2 font-normal text-right">驗證期最慘再跌／再破底</th>
          </tr></thead>
          <tbody>{SIG_ORDER.map((k) => {
            const v = mk === "pool" ? data.pooled[k] : data.table[mk]?.[k];
            if (!v) return null;
            return (
              <tr key={k} className={`border-b border-[#243247]/60 last:border-0 ${k === "knife" ? "opacity-70" : ""}`}>
                <td className="px-3 py-2 text-xs text-slate-200">{data.signals[k]}</td>
                <td className="px-3 py-2 text-right"><Cell s={v.train} /></td>
                <td className="px-3 py-2 text-right"><Cell s={v.test} /></td>
                <td className="px-3 py-2 text-right font-mono text-xs text-[#8b97ab]">{v.test.n ? `${pct(v.test.worst)}／${v.test.newLow}%` : "—"}</td>
              </tr>
            );
          })}</tbody>
        </table>
        <p className="mt-2 text-[11px] text-[#7c8aa0]">格式：次數　20 天後平均報酬　勝率　進場後 20 天內平均最多再跌。只在距 60 日高點跌 ≥ 8% 時評估，同一波 20 天內只算第一次。「再破底」＝20 天內跌破進場那天的低點。</p>
      </section>

      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4">
        <div className="text-sm font-semibold text-white mb-2">跨市場：其他市場先止跌，台股抄底比較安全嗎？</div>
        <div className="space-y-1.5">{Object.entries(data.cross).map(([k, v]) => (
          <div key={k} className="flex flex-wrap items-center justify-between gap-2 text-xs"><span className="text-slate-300">{k}</span>
            <span>建模 <Cell s={v.train} />　驗證 <Cell s={v.test} /></span></div>))}</div>
      </section>

      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4 overflow-x-auto">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold text-white">用什麼工具抄底（2008～，選擇權用期交所實際結算價）</div>
          <div className="flex flex-wrap gap-2">
            <Pills<string> value={sigInst} onChange={setSigInst} options={Object.keys(data.instruments).map((k) => ({ value: k, label: k.replace("：深跌當天直接買", "") }))} />
            <Pills<"5" | "10" | "20"> value={hold} onChange={setHold} options={[{ value: "5", label: "5 天" }, { value: "10", label: "10 天" }, { value: "20", label: "20 天" }]} />
          </div>
        </div>
        {inst && (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-[#243247] text-[11px] text-[#8b97ab]">
              {["工具", "平均", "中位數", "勝率", "最差"].map((h, i) => <th key={h} className={`px-3 py-2 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}
            </tr></thead>
            <tbody>{INST.map(([k, lab]) => { const s = inst[k] as IS; return s ? (
              <tr key={k} className="border-b border-[#243247]/60 last:border-0 font-mono text-xs">
                <td className="px-3 py-2 font-sans text-slate-200">{lab}</td>
                <td className={`px-3 py-2 text-right ${tone(s.avg)}`}>{pct(s.avg)}</td>
                <td className={`px-3 py-2 text-right ${tone(s.med)}`}>{pct(s.med)}</td>
                <td className="px-3 py-2 text-right text-slate-300">{s.win}%</td>
                <td className="px-3 py-2 text-right text-[#22c55e]">{pct(s.worst)}</td>
              </tr>) : null; })}</tbody>
          </table>
        )}
        <p className="mt-2 text-[11px] text-[#7c8aa0]">
          {inst ? `${inst.n} 次訊號；台指期以保證金計（約名目 7.5%）時，持有期間有 ${inst.futCall} 次會被追繳。` : ""}
          價平買權最多只賠權利金（約指數 3%）、不會被追繳；價外買權平均被少數大賺撐高、中位數接近 0。個股期為台積電、聯發科、鴻海、台達電、廣達、聯電、日月光、大立光、長榮平均。
        </p>
      </section>

      {data.stocks && (() => {
        const sk = data.stocks!;
        const F = ["marginUse", "drop", "last5", "lifeDist", "ma60Dist", "ma240Dist", "mcap", "trust10", "dealer10", "fgn10", "fgnHold", "marginChg", "px", "trustPost5", "fgnPost5"];
        return (
          <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4 overflow-x-auto">
            <div className="text-sm font-semibold text-white mb-1">抄底選股：大跌低點後哪些股票反彈最強（上市股，{sk.features.drop?.r20?.n ?? sk.episodes.length} 次 ≥ 15% 回檔，2012 起）</div>
            <p className="mb-3 text-[11px] text-[#7c8aa0]">每一波把股票依特徵分五組，看「最高 1/5 − 最低 1/5」的 20 天反彈差；（x/9）＝幾波方向一致。「控制跌幅後」＝在跌幅相近的股票裡再比較，排除「跌越深彈越多」的影響。</p>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-[#243247] text-[11px] text-[#8b97ab]">
                {["特徵（低點當時可知）", "最高 1/5 − 最低 1/5（20 天）", "低點後 5 天才進場（15 天）", "60 天", "控制跌幅後"].map((h, i) => <th key={h} className={`px-3 py-2 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}
              </tr></thead>
              <tbody>{F.map((k) => { const f = sk.features[k]; if (!f) return null; const c = (x?: { avg: number; pos: number; n: number }) => x ? <span className={`font-mono text-xs ${tone(x.avg)}`}>{pct(x.avg)}<span className="text-[#7c8aa0]">（{x.pos}/{x.n}）</span></span> : <span className="text-[#7c8aa0]">—</span>; return (
                <tr key={k} className="border-b border-[#243247]/60 last:border-0">
                  <td className="px-3 py-2 text-xs text-slate-200">{f.label}</td>
                  <td className="px-3 py-2 text-right">{c(f.r20)}</td><td className="px-3 py-2 text-right">{c(f.l20)}</td><td className="px-3 py-2 text-right">{c(f.r60)}</td><td className="px-3 py-2 text-right">{c(f.ctrl)}</td>
                </tr>); })}</tbody>
            </table>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div>
                <div className="text-xs font-semibold text-white mb-1">產業：反彈 20 天超額報酬（贏大盤的波數）</div>
                <div className="space-y-0.5">{Object.entries(sk.sectors).sort((a, b) => b[1].excess20 - a[1].excess20).map(([s, v]) => (
                  <div key={s} className="flex justify-between font-mono text-[11px]"><span className="font-sans text-slate-300">{s}</span><span className={tone(v.excess20)}>{pct(v.excess20)}<span className="text-[#7c8aa0]">（{v.pos}/{v.eps}）</span></span></div>))}</div>
              </div>
              <div>
                <div className="text-xs font-semibold text-white mb-1">反彈常勝軍（各波反彈前 10% 出現 ≥ 3 次）</div>
                <div className="flex flex-wrap gap-1.5">{sk.repeat.map((r) => (
                  <span key={r[0]} className="rounded bg-[#141c2e] px-2 py-0.5 text-[11px]"><span className="text-slate-200">{r[1]}</span><span className="ml-1 font-mono text-[#7c8aa0]">{r[0]}</span><span className="ml-1 text-[#f59e0b]">×{r[4]}</span>{r[3] && <span className="ml-1 text-[#4f8cff]">期</span>}</span>))}</div>
                <div className="mt-3 text-xs font-semibold text-white mb-1">有沒有個股期貨</div>
                {Object.entries(sk.ssf).map(([k, v]) => <div key={k} className="flex justify-between font-mono text-[11px]"><span className="font-sans text-slate-300">{k}（{v.n}）</span><span>20 天 {pct(v.r20)}・60 天 {pct(v.r60)}・勝率 {v.win20}%</span></div>)}
              </div>
            </div>
            {sk.now && (
              <div className="mt-4">
                <div className="text-xs font-semibold text-white mb-1">現在的候選（{sk.now.date}：先篩近 60 天跌 ≥ {-sk.now.cut.drop}%、融資 ÷ 股本 ≥ {sk.now.cut.marginUse}%，再依綜合分數排序）</div>
                <div className="mb-2 rounded-lg border border-[#243247] bg-[#0b1020] p-2 text-[11px] leading-relaxed text-[#9aa6b8]">
                  <div><span className="text-[#22c55e]">有效（納入分數）</span>：融資使用率高（權重 2，9/9）、個股跌越深（1，8/9）、低點前 5 天急殺（1，8/9）、小市值（1，9/9）、投信低點前賣超（0.5，9/9）、電子／半導體／光電／電機產業（0.5）</div>
                  <div><span className="text-[#ef4444]">無效（不採用）</span>：外資買賣超與持股、融資砍多少／斷頭強度、主動式 ETF 是否賣光（樣本太少）、有沒有個股期、守住生命線或年線、低點後法人進場</div>
                  {sk.score && <div>驗證（2012 起 9 次低點，各波 20 天報酬 − 該波平均）：分數最高 1/5 {pct(sk.score.q[0], 1)}（{sk.score.qPos[0]}/9 為正）、最低 1/5 {pct(sk.score.q[4], 1)}（{sk.score.qPos[4]}/9）；篩選後再依分數排序，前半 7/9 波勝過後半</div>}
                </div>
                <div className="grid gap-x-4 sm:grid-cols-2 lg:grid-cols-3">{sk.now.list.slice(0, 30).map((x) => (
                  <div key={x.code} className="flex justify-between border-b border-[#243247]/40 py-1 text-[11px]">
                    <span><span className="text-slate-200">{x.name}</span><span className="ml-1 font-mono text-[#7c8aa0]">{x.code}</span>{x.ssf && <span className="ml-1 text-[#4f8cff]">期</span>}<span className="ml-1 text-[#7c8aa0]">{x.sector}</span></span>
                    <span className="font-mono">{x.score != null && <span className="text-white">{x.score.toFixed(1)} </span>}<span className="text-[#22c55e]">{pct(x.drop, 0)}</span><span className="text-[#f59e0b]"> 融 {x.marginUse.toFixed(1)}%</span></span>
                  </div>))}</div>
                <p className="mt-2 text-[11px] text-[#7c8aa0]">這是「選什麼」不是「什麼時候」：要等抄底訊號 A／B 出現再進場。高融資、跌深的股票反彈最猛，但如果大盤沒止跌，也會跌得最兇（融資斷頭賣壓）。</p>
              </div>
            )}
          </section>
        );
      })()}

      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold text-white">台股歷次大跌（首次跌幅 ≥ 15% 那天＝0）前後走勢</div>
          <Pills<"all" | "up" | "down"> value={epSel} onChange={setEpSel} options={[{ value: "all", label: "全部" }, { value: "up", label: "年線仍向上" }, { value: "down", label: "年線已向下" }]} />
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#1c2738" vertical={false} />
            <XAxis dataKey="t" tick={{ fill: "#7c8aa0", fontSize: 11 }} stroke="#334155" ticks={[-20, 0, 20, 40, 60]} tickFormatter={(t) => (t === 0 ? "0" : `${t > 0 ? "+" : ""}${t}天`)} />
            <YAxis tick={{ fill: "#7c8aa0", fontSize: 11 }} stroke="#334155" unit="%" />
            <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 11 }} formatter={(v, n) => [pct(v as number), String(n)]} labelFormatter={(t) => `第 ${t} 天`} />
            <ReferenceLine x={0} stroke="#64748b" strokeDasharray="4 4" />
            <ReferenceLine y={0} stroke="#334155" />
            {eps.map((e, i) => { const cur = e.date === data.episodes[data.episodes.length - 1]?.date; return <Line key={e.date} dataKey={e.date} stroke={cur ? "#ffffff" : COLORS[i % COLORS.length]} strokeWidth={cur ? 3 : 1.1} strokeOpacity={cur ? 1 : 0.75} dot={false} connectNulls />; })}
          </LineChart>
        </ResponsiveContainer>
        <div className="mt-2 grid gap-1 text-[11px] sm:grid-cols-2 lg:grid-cols-3">{eps.map((e) => (
          <div key={e.date} className="font-mono text-[#8b97ab]"><span className={e.date === data.episodes[data.episodes.length - 1]?.date ? "text-white font-semibold" : "text-slate-300"}>{e.date}{e.date === data.episodes[data.episodes.length - 1]?.date ? "（這次）" : ""}</span> 年線{e.ma200s > 0 ? "↑" : "↓"} 之後最低在第 {e.lowIn} 天（{pct(e.lowPct)}），60 天後 <span className={tone(e.r60)}>{pct(e.r60)}</span></div>))}</div>
      </section>

      <Note>
        研究結論（2005～2026，台、美、日、韓）：單一指標（跌幅、RSI、VIX、布林）出現時，20 天內再破底的機率 80～90%；深跌當天直接接刀，進場後平均還要再跌 6%。
        比較安全的是「深跌＋止跌確認」：訊號 A（前一晚美股大漲）、B（收紅＋VIX 回落），驗證期（2018 起）20 天勝率約 77～81%、平均再跌 5% 左右，年線仍向上時更好。
        2008 年這種年線已向下的空頭，訊號會一再失效、再跌 30～45%：進場要設停損（跌破訊號日低點）並分批。台指期槓桿高，抄底期間常被追繳；價平買權風險有限、報酬最好，但權利金貴。
        每週六自動重跑回測，傍晚 17:40 回檔中會推 LINE 狀態。歷史回測僅供參考，不構成投資建議。
      </Note>
    </div>
  );
}
