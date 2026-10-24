import Link from "next/link";
import { AlertTriangle, ArrowRight, CalendarDays, Crosshair, Globe, Info, RotateCw, ShieldAlert } from "lucide-react";
import WatchCard from "./WatchCard";

export type Home = {
  updatedAt: string;
  pulse: {
    date: string | null; ix: number | null; ixPct: number | null; adv: number | null; dec: number | null; lu: number | null; ld: number | null;
    mood: number | null; moodLabel: string | null; temp: number | null; tempLabel: string | null; temp5: number | null; riskDate: string | null;
    vix: number | null; vixChg: number | null; foreign: number | null; trust: number | null; dealer: number | null; instiOfficial: boolean;
    futF: number | null; futFChg: number | null;
  };
  alerts: { level: "red" | "amber" | "info"; text: string; href: string }[];
  strategy: { asof: string | null; next: string | null; s1: { code: string; name: string; v: number }[]; s1n: number; s2: { code: string; name: string; v: number | null }[]; s2n: number; exits: number; exitAvg: number | null };
  turnover: { asof: string | null; next: string | null; list: { code: string; name: string; t: number; dt: number | null }[]; o2c: number | null; black: number | null; top: { code: string; name: string; t: number }[] };
  global: { date: string | null; idx: { name: string; chg: number }[]; groups: { name: string; sym: string; chg: number; react: { name: string; exp: number }[] }[] };
  week?: { from: string; to: string; days: { d: string; wd: string; next: boolean; items: { cat: string; text: string; hi: boolean; href: string | null }[] }[] };
};

const CAT: Record<string, string> = { 休市: "#f05252", 結算: "#f59e0b", 總經: "#a78bfa", 財報: "#06b6d4", 法說: "#4f8cff", ETF: "#22c55e", 除息: "#f97316", 營收: "#8b97ab" };

function Week({ w }: { w: NonNullable<Home["week"]> }) {
  return (
    <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <CalendarDays className="w-4 h-4 text-[#a78bfa]" /><h3 className="text-sm font-semibold text-white">下週重點大事</h3>
          <span className="text-[11px] text-[#8b97ab]">{md(w.from)}～{md(w.to)}・台北時間</span>
        </div>
        <div className="flex flex-wrap gap-2 text-[10px]">
          {Object.entries(CAT).map(([k, c]) => <span key={k} className="inline-flex items-center gap-1 text-[#8b97ab]"><span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />{k}</span>)}
        </div>
      </div>
      {!w.days.length ? <p className="text-xs text-[#7c8aa0]">這段期間沒有重大事件</p> : (
        <div className="grid gap-3 items-start sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {w.days.map((d) => (
            <div key={d.d} className={`rounded-lg border p-3 ${d.items.some((i) => i.hi) ? "border-[#a78bfa]/30 bg-[#a78bfa]/[0.03]" : "border-[#1c2738]"}`}>
              <div className="flex items-baseline gap-2 mb-1.5">
                <span className="font-mono text-sm font-semibold text-white">{md(d.d)}</span>
                <span className="text-[11px] text-[#8b97ab]">週{d.wd}{!d.next && "・本週"}</span>
              </div>
              <ul className="space-y-1">
                {d.items.map((i) => {
                  const body = (
                    <span className={`flex items-start gap-1.5 text-[12px] leading-snug ${i.hi ? "text-white font-medium" : "text-slate-400"}`}>
                      <span className="mt-[5px] w-1.5 h-1.5 shrink-0 rounded-full" style={{ background: CAT[i.cat] ?? "#8b97ab" }} />
                      <span><span className="text-[10px] mr-1" style={{ color: CAT[i.cat] ?? "#8b97ab" }}>{i.cat}</span>{i.text}</span>
                    </span>
                  );
                  return <li key={i.cat + i.text}>{i.href ? <Link href={i.href} className="block rounded hover:bg-white/5">{body}</Link> : body}</li>;
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
      <p className="mt-3 text-[10px] text-[#7c8aa0]">粗體＝重點。美股財報標「盤後」的，台股隔天才反應；總經數據時間為台北時間，晚上公布的影響隔天台股開盤。</p>
    </div>
  );
}

const md = (d?: string | null) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : "—");
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const sg = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}`);
const yi = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)} 億`);
const MOOD: Record<string, string> = { 過熱: "#f05252", 偏多: "#f97316", 中性: "#f59e0b", 偏空: "#4ade80", 冰點: "#22c55e" };
const TEMP = (t: number) => (t >= 75 ? "#f05252" : t >= 55 ? "#f59e0b" : t >= 30 ? "#4f8cff" : "#22c55e");

function Tile({ href, label, value, sub, color = "text-white", style }: { href: string; label: string; value: React.ReactNode; sub?: React.ReactNode; color?: string; style?: React.CSSProperties }) {
  return (
    <Link href={href} className="group rounded-xl border border-[#243247] bg-[#0d1220] p-4 card-hover block">
      <div className="text-[11px] text-[#8b97ab] flex items-center justify-between">{label}<ArrowRight className="w-3 h-3 opacity-0 group-hover:opacity-100 text-[#4f8cff] transition-opacity" /></div>
      <div className={`mt-1 text-2xl font-mono font-bold ${color}`} style={style}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] font-mono text-[#8b97ab] truncate">{sub}</div>}
    </Link>
  );
}

function Panel({ icon: Icon, title, href, sub, accent, children }: { icon: React.ElementType; title: string; href: string; sub?: string; accent: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 flex flex-col">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <div className="flex items-center gap-2"><Icon className="w-4 h-4" style={{ color: accent }} /><h3 className="text-sm font-semibold text-white">{title}</h3></div>
          {sub && <div className="mt-0.5 text-[11px] text-[#7c8aa0]">{sub}</div>}
        </div>
        <Link href={href} className="shrink-0 flex items-center gap-1 text-xs text-[#8b97ab] hover:text-[#4f8cff] font-mono">詳情 <ArrowRight className="w-3 h-3" /></Link>
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

const Chip = ({ name, code, right, cls = "text-slate-300" }: { name: string; code?: string; right?: string; cls?: string }) => (
  <span className="inline-flex items-center gap-1.5 rounded-md bg-[#141c2e] px-2 py-1 text-xs">
    <span className="text-slate-200">{name}</span>{code && <span className="font-mono text-[10px] text-[#7c8aa0]">{code}</span>}
    {right && <span className={`font-mono ${cls}`}>{right}</span>}
  </span>
);

export default function CommandCenter({ h }: { h: Home }) {
  const p = h.pulse;
  const upd = new Date(h.updatedAt);
  const alerts = h.alerts;
  const red = alerts.filter((a) => a.level === "red").length;
  const st = h.strategy, tv = h.turnover, gl = h.global;
  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-10 space-y-6">
      {/* 標題列 */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-mono text-[#7c8aa0] tracking-[0.25em] uppercase">Command Center</p>
          <h1 className="text-2xl font-bold text-white">今日指揮中心</h1>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-[#4f8cff]/25 bg-[#4f8cff]/5 px-3 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-[#4f8cff] animate-pulse" />
          <span className="text-[11px] font-mono text-[#4f8cff]">台股 {md(p.date)} 收盤・美股 {md(gl.date)}・更新 {upd.toLocaleString("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Taipei" })}</span>
        </div>
      </div>

      {/* 大盤脈搏 */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Tile href="/atmosphere" label="加權指數" value={p.ix ? p.ix.toLocaleString(undefined, { maximumFractionDigits: 0 }) : "—"}
          sub={<span><span className={tone(p.ixPct)}>{sg(p.ixPct)}%</span>・漲 {p.adv ?? "—"} 跌 {p.dec ?? "—"}</span>} />
        <Tile href="/atmosphere" label="市場氣氛" value={<>{p.mood ?? "—"}<span className="ml-2 text-base">{p.moodLabel}</span></>}
          style={{ color: MOOD[p.moodLabel ?? ""] ?? "#e2e8f0" }} sub={`漲停 ${p.lu ?? "—"}・跌停 ${p.ld ?? "—"}`} />
        <Tile href="/risk" label="市場風險溫度" value={<>{p.temp != null ? p.temp.toFixed(0) : "—"}<span className="ml-2 text-base">{p.tempLabel}</span></>}
          style={{ color: TEMP(p.temp ?? 0) }} sub={p.temp5 != null && p.temp != null ? `5 日前 ${p.temp5.toFixed(0)}（${sg(p.temp - p.temp5, 0)}）` : undefined} />
        <Tile href="/risk" label="VIX 恐慌指數" value={p.vix?.toFixed(2) ?? "—"} color={(p.vix ?? 0) >= 30 ? "text-[#f05252]" : (p.vix ?? 0) >= 20 ? "text-[#f59e0b]" : "text-white"}
          sub={<span>1 日 <span className={(p.vixChg ?? 0) > 0 ? "text-[#f59e0b]" : "text-[#8b97ab]"}>{sg(p.vixChg)}</span>・美股 {md(p.riskDate)}</span>} />
        <Tile href="/institutional" label={`外資現貨${p.instiOfficial ? "" : "（估）"}`} value={<span className={tone(p.foreign)}>{yi(p.foreign)}</span>}
          sub={<span>投信 <span className={tone(p.trust)}>{yi(p.trust)}</span>・自營 <span className={tone(p.dealer)}>{yi(p.dealer)}</span></span>} />
        <Tile href="/futures" label="外資台指期淨部位" value={<span className={tone(p.futF)}>{p.futF != null ? `${p.futF > 0 ? "+" : ""}${p.futF.toLocaleString()}` : "—"}</span>}
          sub={<span>口・1 日 <span className={tone(p.futFChg)}>{p.futFChg != null ? `${p.futFChg > 0 ? "+" : ""}${p.futFChg.toLocaleString()}` : "—"}</span></span>} />
      </div>

      {/* 警示 */}
      {!!alerts.length && (
        <div className={`rounded-xl border p-4 ${red ? "border-[#f05252]/30 bg-[#f05252]/[0.04]" : "border-[#f59e0b]/30 bg-[#f59e0b]/[0.04]"}`}>
          <div className="flex items-center gap-2 mb-2">
            <ShieldAlert className={`w-4 h-4 ${red ? "text-[#f05252]" : "text-[#f59e0b]"}`} />
            <h2 className="text-sm font-semibold text-white">需要注意</h2>
            <span className="text-[11px] text-[#8b97ab]">{alerts.length} 項{red ? `，其中 ${red} 項較嚴重` : ""}</span>
          </div>
          <div className="grid gap-1.5 md:grid-cols-2">
            {alerts.map((a) => (
              <Link key={a.text} href={a.href} className="group flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-white/5 text-[13px]">
                {a.level === "info" ? <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-[#4f8cff]" /> : <AlertTriangle className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${a.level === "red" ? "text-[#f05252]" : "text-[#f59e0b]"}`} />}
                <span className={a.level === "red" ? "text-[#fca5a5]" : a.level === "amber" ? "text-[#fcd34d]" : "text-slate-300"}>{a.text}</span>
                <ArrowRight className="w-3 h-3 mt-1 ml-auto shrink-0 opacity-0 group-hover:opacity-100 text-[#8b97ab]" />
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 明日行動 */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel icon={Crosshair} title="十日波段：明日進場" href="/strategy" accent="#4f8cff" sub={`${md(st.next)} 進場・依 ${md(st.asof)} 收盤`}>
          <div className="text-[11px] text-[#8b97ab] mb-1.5">出量做多 {st.s1n} 檔</div>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {st.s1.length ? st.s1.map((x) => <Chip key={x.code} name={x.name} code={x.code} right={`${sg(x.v, 1)}%`} cls={tone(x.v)} />) : <span className="text-xs text-[#7c8aa0]">沒有符合的股票</span>}
          </div>
          <div className="text-[11px] text-[#8b97ab] mb-1.5">輿情籌碼 {st.s2n} 檔</div>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {st.s2.length ? st.s2.map((x) => <Chip key={x.code} name={x.name} code={x.code} />) : <span className="text-xs text-[#7c8aa0]">沒有符合的股票</span>}
          </div>
          {st.exits > 0 && <div className="text-xs text-[#f59e0b]">⏰ {md(st.next)} 開盤出場 {st.exits} 檔{st.exitAvg != null && <>，平均 <span className={`font-mono ${tone(st.exitAvg)}`}>{sg(st.exitAvg)}%</span></>}</div>}
        </Panel>

        <Panel icon={RotateCw} title="高週轉＋漲停：開高走低觀察" href="/turnover" accent="#22c55e" sub={`${md(tv.next)} 觀察・依 ${md(tv.asof)} 收盤`}>
          {tv.list.length ? (
            <div className="space-y-1.5 mb-3">
              {tv.list.map((x) => (
                <div key={x.code} className="flex items-center justify-between text-sm">
                  <span><span className="text-slate-200">{x.name}</span><span className="ml-1.5 font-mono text-[11px] text-[#7c8aa0]">{x.code}</span></span>
                  <span className="font-mono text-xs"><span className="text-[#f59e0b]">週轉 {x.t.toFixed(1)}%</span>{x.dt != null && <span className="ml-2 text-[#8b97ab]">當沖 {x.dt.toFixed(0)}%</span>}</span>
                </div>
              ))}
            </div>
          ) : <div className="text-xs text-[#7c8aa0] mb-3">今天週轉率前 20 名沒有收漲停的股票</div>}
          {tv.o2c != null && <div className="text-[11px] text-[#8b97ab] mb-3">回測：隔天開→收平均 <span className={`font-mono ${tone(tv.o2c)}`}>{sg(tv.o2c)}%</span>，收黑機率 {tv.black?.toFixed(0)}%</div>}
          <div className="text-[11px] text-[#8b97ab] mb-1.5">今日週轉率前 5</div>
          <div className="flex flex-wrap gap-1.5">{tv.top.map((x) => <Chip key={x.code} name={x.name} right={`${x.t.toFixed(1)}%`} cls="text-[#f59e0b]" />)}</div>
        </Panel>

        <Panel icon={Globe} title="國際連動：台股開盤留意" href="/global" accent="#06b6d4" sub={`美股 ${md(gl.date)} 收盤`}>
          <div className="flex flex-wrap gap-1.5 mb-3">{gl.idx.map((x) => <Chip key={x.name} name={x.name} right={`${sg(x.chg)}%`} cls={tone(x.chg)} />)}</div>
          <div className="space-y-2">
            {gl.groups.map((g) => (
              <div key={g.name} className="text-[13px]">
                <div className="flex items-center justify-between"><span className="text-slate-200">{g.name}</span><span className={`font-mono ${tone(g.chg)}`}>{g.sym} {sg(g.chg)}%</span></div>
                {!!g.react.length && <div className="text-[11px] text-[#8b97ab]">{g.react.map((r) => <span key={r.name} className="mr-2">{r.name} <span className={tone(r.exp)}>{sg(r.exp, 1)}%</span></span>)}</div>}
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {h.week && <Week w={h.week} />}

      <WatchCard />
    </section>
  );
}
