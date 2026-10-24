"use client";

import { useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Hot = { code: string; name: string; mk: string; close: number; chg: number | null; p5: number | null; valYi: number; rank: number; sector: string | null; noShort: boolean };
type Cand = Hot & { lo: number; hi: number };
type Sig = { date: string; code: string; name: string; gap: number; p5: number; prev: number; open: number; high: number; close: number; ret: number; openHigh: boolean; sector: string | null; rank: number; top3: boolean };
/** [價格, 股數, 相對昨收 %, 在當日高低區間的位置 0～1, 可能成交的小時] */
type Fill = [number, number, number, number, number[]];
type Trade = { date: string; code: string; name: string; per: "d" | "m" | "r"; pnl: number | null; note: string; side: "short" | "short*" | "long" | "?"; rank: number | null;
  pc: number; o: number; h: number; l: number; c: number; gap: number; hi: number; lo: number; chg: number; prev: number; p5: number; vr: number | null; ixGap: number; ixChg: number;
  sell: Fill[]; buy: Fill[]; bars: [string, number, number, number, number][] };
type Share = [string, number][];
type Stats = { n: number; days: number; from: string; to: string; daily: { n: number; win: number; avg: number; max: number; min: number; sum: number };
  prev: Share; p5: Share; gap: Share; vr: Share; rank: Share; sellVsPc: number; sellVsOpen: number; buyVsPc: number; sellFirstHour: number; buyAfterNoon: number;
  sellPos: number; buyPos: number; closeVsOpen: number; win: { n: number; closePos: number; closeVsOpen: number };
  loss: { n: number; closePos: number; closeVsOpen: number; limitUp: number; list: [string, string, number, number][] }; long: [string, string, number, number, number | null][]; sides: Record<string, number> };
type G = { group: string; n: number; avg: number; med: number; win: number; net: number };
type Bt = { updatedAt: string; cost: number; from: string; to: string; n: number; groups: G[]; years: G[]; bGroups: G[]; bRise: Record<string, number>;
  aRisk: { up3: number; up5: number; dn3: number }; intraday?: G[]; intraFrom?: string; intraTo?: string };
type Sum = { n: number; avg: number | null; win: number | null; net: number | null };
type Data = { updatedAt: string; asof: string; next: string; rule: { top: number; gap: [number, number]; run5: number; limit: number; cost: number };
  cand: Cand[]; hot: Hot[]; recent: Sig[]; summary: Sum & { top3: Sum; days: number; from: string; to: string };
  trades: { source: string; trades: Trade[]; stats: Stats; months: { m: string; pnl: number; amt: number }[]; quotes: string[] }; backtest: Bt };
type View = "cand" | "recent" | "trades" | "bt";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const gain = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const wan = (v: number) => `${v > 0 ? "+" : ""}${(v / 1e4).toLocaleString(undefined, { maximumFractionDigits: 0 })} 萬`;
const hours = (w: number[]) => (w.length ? `${String(Math.min(...w)).padStart(2, "0")}～${String(Math.max(...w) + 1).padStart(2, "0")} 時` : "時間不明");
const SELL = "#f59e0b", BUY = "#06b6d4";
const SIDE: Record<Trade["side"], [string, string]> = {
  short: ["先賣後買", "bg-[#f59e0b]/15 text-[#f59e0b]"], "short*": ["先賣（推估）", "bg-[#f59e0b]/10 text-[#d9a441]"],
  long: ["先買後賣", "bg-[#06b6d4]/15 text-[#06b6d4]"], "?": ["不明", "bg-[#475569]/30 text-[#8b97ab]"],
};

/** 當天走勢：小時 K 線；橘線＝賣出價、青線＝買進價、虛線＝昨收 */
function TradeChart({ t }: { t: Trade }) {
  const W = 360, H = 170, L = 6, R = 52, T = 8, B = 18;
  const sells = t.sell.map((s) => s[0]), buys = t.buy.map((b) => b[0]);
  const prices = [t.h, t.l, t.pc, ...sells, ...buys];
  const max = Math.max(...prices), min = Math.min(...prices), pad = (max - min) * 0.06 || 1;
  const y = (p: number) => T + ((max + pad - p) / (max - min + 2 * pad)) * (H - T - B);
  const n = Math.max(t.bars.length, 1), cw = (W - L - R) / n;
  const x = (i: number) => L + cw * (i + 0.5);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
      <line x1={L} x2={W - R} y1={y(t.pc)} y2={y(t.pc)} stroke="#475569" strokeDasharray="3 3" />
      <text x={W - R + 3} y={y(t.pc) + 3} fontSize="8" fill="#7c8aa0">昨收</text>
      {t.bars.length ? t.bars.map((b, i) => (
        <g key={b[0]}>
          <line x1={x(i)} x2={x(i)} y1={y(b[2])} y2={y(b[3])} stroke="#94a3b8" />
          <rect x={x(i) - cw * 0.28} width={cw * 0.56} y={Math.min(y(b[1]), y(b[4]))} height={Math.max(Math.abs(y(b[1]) - y(b[4])), 1)} fill={b[4] >= b[1] ? "#f05252" : "#22c55e"} opacity="0.85" />
          <text x={x(i)} y={H - 5} fontSize="8" fill="#7c8aa0" textAnchor="middle">{b[0]}</text>
        </g>
      )) : <text x={L} y={H - 5} fontSize="8" fill="#7c8aa0">（沒有小時線）</text>}
      {sells.map((p, i) => <line key={`s${i}`} x1={L} x2={W - R} y1={y(p)} y2={y(p)} stroke={SELL} strokeWidth="0.8" opacity="0.85" />)}
      {buys.map((p, i) => <line key={`b${i}`} x1={L} x2={W - R} y1={y(p)} y2={y(p)} stroke={BUY} strokeWidth="0.8" opacity="0.85" />)}
      {!!sells.length && <text x={W - R + 3} y={y(Math.max(...sells)) + 3} fontSize="8" fill={SELL}>賣 {Math.max(...sells)}</text>}
      {!!buys.length && <text x={W - R + 3} y={y(Math.min(...buys)) + 3} fontSize="8" fill={BUY}>買 {Math.min(...buys)}</text>}
    </svg>
  );
}

function Bars({ title, rows, color = "#f59e0b" }: { title: string; rows: Share; color?: string }) {
  return (
    <div>
      <div className="text-[11px] text-[#8b97ab] mb-1.5">{title}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-center gap-2 text-[11px] mb-1">
          <span className="w-20 shrink-0 text-slate-400">{k}</span>
          <div className="flex-1 h-2 rounded bg-[#141c2e]"><div className="h-2 rounded" style={{ width: `${v}%`, background: color }} /></div>
          <span className="w-9 text-right font-mono text-slate-300">{v}%</span>
        </div>
      ))}
    </div>
  );
}

export default function G85Dashboard() {
  const { data, error } = useStaticJson<Data>("85g.json");
  const wl = useWatchlist();
  const [view, setView] = useState<View>("cand");
  const [showHot, setShowHot] = useState(false);
  const [pick, setPick] = useState<Trade | null>(null);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const bt = data.backtest, ru = data.rule, s = data.summary, ts = data.trades.stats, tr = data.trades.trades;
  const main = bt.groups?.find((g) => g.group.startsWith("A："));
  const bMain = bt.bGroups?.find((g) => g.group.startsWith("B 指數"));
  const cur = pick ?? tr.find((t) => t.bars.length && t.side === "short") ?? tr[0];
  const stock = (code: string, name: string, mk?: string) => (
    <span className="whitespace-nowrap">
      <button onClick={(e) => { e.stopPropagation(); wl.toggle(code); }} className={`mr-1.5 ${wl.has(code) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
      <span className="text-slate-200">{name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{code}</span>
      {mk === "上櫃" && <span className="ml-1 text-[10px] text-[#7c8aa0]">櫃</span>}
    </span>
  );
  const cHot: Column<Hot>[] = [
    { key: "rank", label: "成交排名", align: "right", sort: (r) => r.rank, render: (r) => num(r.rank, "text-[#8b97ab]") },
    { key: "name", label: "股票", render: (r) => <>{stock(r.code, r.name, r.mk)}{r.noShort && <span className="ml-1.5 rounded bg-[#475569]/30 px-1 text-[10px] text-[#8b97ab]">暫停先賣</span>}</> },
    { key: "sector", label: "族群", render: (r) => <span className="text-xs text-slate-400">{r.sector ?? "—"}</span> },
    { key: "close", label: "收盤", align: "right", sort: (r) => r.close, render: (r) => num(r.close) },
    { key: "chg", label: "今日", align: "right", sort: (r) => r.chg, render: (r) => num(pct(r.chg), (r.chg ?? 0) >= ru.limit ? "text-[#f05252] font-semibold" : gain(r.chg)) },
    { key: "p5", label: "近 5 日", align: "right", sort: (r) => r.p5, render: (r) => num(pct(r.p5, 1), (r.p5 ?? 0) >= ru.run5 ? "text-[#f05252] font-semibold" : gain(r.p5)) },
    { key: "valYi", label: "成交（億）", align: "right", sort: (r) => r.valYi, render: (r) => num(r.valYi) },
  ];
  const cCand: Column<Cand>[] = [
    ...cHot,
    { key: "band", label: `明天開在這區間＝開高 ${ru.gap[0]}～${ru.gap[1]}%`, align: "right", render: (r) => num(`${r.lo} ～ ${r.hi}`, "text-[#f59e0b]") },
  ];
  const cSig: Column<Sig>[] = [
    { key: "date", label: "日期", sort: (r) => r.date, render: (r) => num(md(r.date)) },
    { key: "name", label: "股票", render: (r) => <>{stock(r.code, r.name)}{r.top3 && <span className="ml-1 rounded bg-[#f59e0b]/15 px-1 text-[10px] text-[#f59e0b]">最熱</span>}</> },
    { key: "rank", label: "前日成交排名", align: "right", sort: (r) => r.rank, render: (r) => num(r.rank, "text-[#8b97ab]") },
    { key: "prev", label: "前日", align: "right", sort: (r) => r.prev, render: (r) => num(pct(r.prev, 1), r.prev >= ru.limit ? "text-[#f05252]" : "text-slate-400") },
    { key: "p5", label: "前 5 日", align: "right", sort: (r) => r.p5, render: (r) => num(pct(r.p5, 1)) },
    { key: "gap", label: "開盤", align: "right", sort: (r) => r.gap, render: (r) => num(pct(r.gap), "text-[#f05252]") },
    { key: "oh", label: "開盤＝最高", align: "right", sort: (r) => (r.openHigh ? 1 : 0), render: (r) => (r.openHigh ? <span className="text-[#22c55e]">✓</span> : <span className="text-[#475569]">—</span>) },
    { key: "ret", label: "開盤賣→收盤買", align: "right", sort: (r) => r.ret, render: (r) => num(pct(r.ret), r.ret > 0 ? "text-[#f05252]" : "text-[#22c55e]") },
  ];
  const fills = (f: Fill[], color: string) => f.length
    ? <span className="font-mono text-[11px] whitespace-nowrap" style={{ color }} title={f.map((x) => `${x[0]} × ${x[1].toLocaleString()} 股（${pct(x[2], 1)}，${hours(x[4])}）`).join("\n")}>
        {pct(f.reduce((a, x) => a + x[2], 0) / f.length, 1)}<span className="ml-1 text-[10px] text-[#7c8aa0]">{hours([...new Set(f.flatMap((x) => x[4]))])}</span></span>
    : <span className="text-[#475569]">—</span>;
  const cTr: Column<Trade>[] = [
    { key: "date", label: "日期", sort: (t) => t.date, render: (t) => num(t.date.slice(2).replace(/-/g, "/")) },
    { key: "name", label: "股票", render: (t) => <span className="whitespace-nowrap"><span className="text-slate-200">{t.name}</span><span className="ml-1 font-mono text-[10px] text-[#7c8aa0]">{t.code}</span></span> },
    { key: "side", label: "方向", sort: (t) => t.side, render: (t) => <span className={`rounded px-1.5 py-0.5 text-[10px] whitespace-nowrap ${SIDE[t.side][1]}`}>{SIDE[t.side][0]}</span> },
    { key: "prev", label: "前日", align: "right", sort: (t) => t.prev, render: (t) => num(pct(t.prev, 1), t.prev >= 9.5 ? "text-[#f05252]" : "text-slate-400") },
    { key: "p5", label: "前 5 日", align: "right", sort: (t) => t.p5, render: (t) => num(pct(t.p5, 1), "text-slate-400") },
    { key: "gap", label: "開盤", align: "right", sort: (t) => t.gap, render: (t) => num(pct(t.gap, 1), gain(t.gap)) },
    { key: "chg", label: "收盤", align: "right", sort: (t) => t.chg, render: (t) => num(pct(t.chg, 1), gain(t.chg)) },
    { key: "sell", label: "賣出（時段）", align: "right", render: (t) => fills(t.sell, SELL) },
    { key: "buy", label: "買進（時段）", align: "right", render: (t) => fills(t.buy, BUY) },
    { key: "pnl", label: "損益", align: "right", sort: (t) => t.pnl, render: (t) => t.pnl == null ? <span className="text-[#475569]">—</span>
      : <span className="font-mono whitespace-nowrap"><span className={gain(t.pnl)}>{wan(t.pnl)}</span>{t.per !== "d" && <span className="ml-1 text-[10px] text-[#7c8aa0]">{t.per === "m" ? "本月" : "區間"}</span>}</span> },
  ];
  const cG: Column<G>[] = [
    { key: "group", label: "分組", render: (g) => <span className="text-slate-200 whitespace-pre">{g.group}</span> },
    { key: "n", label: "筆數", align: "right", render: (g) => num(g.n.toLocaleString()) },
    { key: "avg", label: "平均報酬", align: "right", render: (g) => num(pct(g.avg), g.avg > 0 ? "text-[#f05252]" : "text-[#22c55e]") },
    { key: "med", label: "中位數", align: "right", render: (g) => num(pct(g.med)) },
    { key: "win", label: "勝率", align: "right", render: (g) => num(`${g.win}%`) },
    { key: "net", label: `扣成本 ${bt.cost}%`, align: "right", render: (g) => num(pct(g.net), g.net > 0 ? "text-[#f05252]" : "text-[#22c55e]") },
  ];
  const shorts = (ts.sides.short ?? 0) + (ts.sides["short*"] ?? 0);

  return (
    <div>
      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] leading-relaxed text-slate-300 space-y-2">
        <h3 className="text-sm text-white font-semibold">策略精神</h3>
        <p>85g（IG @85ga_stock）是專做日內波的當沖交易員，每天額度 2000～4000 萬，自稱「依靠族群性、籌碼跟量價」。
          我們把他 {ts.from.slice(0, 7).replace("-", "/")}～{ts.to.slice(0, 7).replace("-", "/")} 公開的 {ts.n} 張對帳單逐筆對照當天小時 K：
          <b className="text-white">{Math.round(shorts / ts.n * 100)}% 是「現股當沖先賣後買」</b>，{ts.sellFirstHour}% 的賣單成交在 09:00～10:00、{ts.buyAfterNoon}% 的買回在 12:00 之後。
          {ts.daily.n} 張「當日損益」裡 {ts.daily.win} 張賺錢（勝率 {Math.round(ts.daily.win / ts.daily.n * 100)}%），平均每天 {wan(ts.daily.avg)}。</p>
        <p><b className="text-[#f59e0b]">打法 A｜強勢股開高走低（主力）</b>：前一天就很熱的股票（成交金額前 {ru.top} 名，<b className="text-white">前一天漲停或近 5 日漲 ≥ {ru.run5}%</b>），
          隔天<b className="text-white">開高 {ru.gap[0]}～{ru.gap[1]}%</b> → 開盤第一個小時趁衝高分批賣（他平均賣在比開盤高 {ts.sellVsOpen}%、當天高低區間的 {Math.round(ts.sellPos * 100)}% 位置），
          中午後到收盤前在低檔分批買回（平均買在區間 {Math.round(ts.buyPos * 100)}% 的位置、比昨收 {pct(ts.buyVsPc, 1)}）。</p>
        <p><b className="text-[#06b6d4]">打法 B｜大跌開低反彈（偶爾）</b>：指數大跌、熱門股開在跌停附近時先買、拉高賣（例：晟田開跌停 43.7 買、48 賣，當天 +336 萬）。他也說「開低走低我不會空」。</p>
        <p className="text-xs text-[#8b97ab]">什麼時候會輸：{ts.loss.n} 次先賣後買的虧損日，股價收在當天區間 {Math.round(ts.loss.closePos * 100)}% 的高檔、收盤比開盤還高 {ts.loss.closeVsOpen}%——
          也就是「強勢股真的強」的日子（例如 2026 年 1～5 月記憶體大多頭時的華邦電、旺宏、南亞科）。所以開盤後如果不跌、一路創高就要停損，不能凹。紀律：不加碼、少追價、月初營收公布期不追高、沒量的日子不做。</p>
      </section>

      <KpiRow>
        <Kpi label={`${md(data.next)} 觀察（A 打法候選）`} value={data.cand.length} unit="檔" sub={data.cand.slice(0, 4).map((c) => c.name).join("、") || "—"} color="text-[#f59e0b]" />
        <Kpi label={`近 ${s.days} 天：每天最熱 3 檔的 A 訊號`} value={pct(s.top3.avg)} color={gain(s.top3.avg)} sub={`${s.top3.n} 筆・勝率 ${s.top3.win ?? "—"}%`} />
        <Kpi label="5 年回測：A 條件" value={main ? pct(main.avg) : "—"} color={gain(main?.avg)} sub={main ? `${main.n.toLocaleString()} 筆・勝率 ${main.win}%・扣成本 ${pct(main.net)}` : undefined} />
        <Kpi label={`85g 公開的 ${ts.daily.n} 天當日損益`} value={wan(ts.daily.sum)} color="text-[#f05252]" sub={`勝率 ${Math.round(ts.daily.win / ts.daily.n * 100)}%`} />
      </KpiRow>

      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <Pills<View> value={view} onChange={setView} options={[
          { value: "cand", label: `明日觀察（${data.cand.length}）` }, { value: "recent", label: `近期訊號（${data.recent.length}）` },
          { value: "trades", label: `實單解析（${tr.length}）` }, { value: "bt", label: "回測" }]} />
        <span className="text-[11px] text-[#7c8aa0]">依 {md(data.asof)} 收盤</span>
      </div>

      {view === "cand" && (
        <div className="space-y-4">
          <p className="text-xs text-[#8b97ab]">今天成交金額前 {ru.top} 名、今天漲停或近 5 日漲 ≥ {ru.run5}% 的股票。明天開盤落在右邊的價格區間（開高 {ru.gap[0]}～{ru.gap[1]}%）就是打法 A 的標的：
            09:00～10:00 趁衝高分批賣、不追價；中午後在低檔分批買回；開盤後一路創高就停損。他一天通常只打 1～2 檔最熱、成交最大的。</p>
          {data.cand.length ? <SortTable<Cand> rows={data.cand} columns={cCand} rowKey={(r) => r.code} initialSort={{ key: "rank", desc: false }} />
            : <Empty>今天沒有符合條件的熱門強勢股，明天沒有 A 打法候選。</Empty>}
          <button onClick={() => setShowHot(!showHot)} className="text-xs text-[#4f8cff] hover:underline">{showHot ? "收起" : "展開"}今天成交金額前 {ru.top} 名（指數大跌開低時，打法 B 從這裡挑）</button>
          {showHot && <SortTable<Hot> rows={data.hot} columns={cHot} rowKey={(r) => r.code} initialSort={{ key: "rank", desc: false }} />}
        </div>
      )}

      {view === "recent" && (
        <div className="space-y-3">
          <p className="text-xs text-[#8b97ab]">{s.from} ～ {s.to}，每天符合 A 條件的股票，開盤賣、收盤買回的結果（正＝賺）。全部 {s.n} 筆平均 {pct(s.avg)}、勝率 {s.win}%；
            只看每天成交金額最大的 3 檔（標「最熱」）{s.top3.n} 筆平均 {pct(s.top3.avg)}、勝率 {s.top3.win}%，扣成本 {pct(s.top3.net)}。</p>
          {data.recent.length ? <SortTable<Sig> rows={data.recent} columns={cSig} rowKey={(r) => r.date + r.code} initialSort={{ key: "date", desc: true }} limit={80} />
            : <Empty>近期沒有符合條件的訊號。</Empty>}
        </div>
      )}

      {view === "trades" && (
        <div className="space-y-5">
          <p className="text-xs text-[#8b97ab]">{data.trades.source}。每張對帳單只露出部分成交；用買賣價對照當天小時 K 推估成交時段與先後順序（「先賣（推估）」＝只看到賣單或順序較難判斷，但賣在開盤第一小時）。
            月／區間對帳單的損益是整段期間的合計，不是當天。</p>
          <section className="grid gap-4 md:grid-cols-3 rounded-xl border border-[#243247] bg-[#0d1220] p-5">
            <Bars title="前一天的漲跌" rows={ts.prev} />
            <Bars title="前 5 日漲幅" rows={ts.p5} />
            <Bars title="當天開盤（相對昨收）" rows={ts.gap} />
            <Bars title="前一日成交金額排名" rows={ts.rank} color="#4f8cff" />
            <Bars title="前一日量比（對 20 日均量）" rows={ts.vr} color="#4f8cff" />
            <div className="text-[12px] text-slate-300 space-y-1.5">
              <div className="text-[11px] text-[#8b97ab] mb-1.5">進出場位置（先賣後買的 {shorts} 筆，中位數）</div>
              <p>賣出：昨收 <b className="font-mono" style={{ color: SELL }}>{pct(ts.sellVsPc, 1)}</b>、開盤 <b className="font-mono" style={{ color: SELL }}>{pct(ts.sellVsOpen, 1)}</b>，{ts.sellFirstHour}% 在 09～10 時</p>
              <p>買回：昨收 <b className="font-mono" style={{ color: BUY }}>{pct(ts.buyVsPc, 1)}</b>，{ts.buyAfterNoon}% 在 12 時之後</p>
              <p>賺錢日收盤比開盤 <b className="font-mono text-[#22c55e]">{pct(ts.win.closeVsOpen, 1)}</b>；賠錢日 <b className="font-mono text-[#f05252]">{pct(ts.loss.closeVsOpen, 1)}</b></p>
            </div>
          </section>
          {cur && (
            <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <TradeChart t={cur} />
              <div className="text-[12px] text-slate-300 space-y-1.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-white">{cur.date}</span>{stock(cur.code, cur.name)}
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${SIDE[cur.side][1]}`}>{SIDE[cur.side][0]}</span>
                  {cur.pnl != null && <span className={`font-mono ${gain(cur.pnl)}`}>{wan(cur.pnl)}{cur.per !== "d" && <span className="ml-1 text-[10px] text-[#7c8aa0]">（{cur.per === "m" ? "本月合計" : "區間合計"}）</span>}</span>}
                </div>
                <p className="font-mono text-[11px] text-[#8b97ab]">前日 {pct(cur.prev, 1)}・前 5 日 {pct(cur.p5, 1)}・量比 {cur.vr ?? "—"}・前日成交第 {cur.rank ?? "—"} 名・指數開 {pct(cur.ixGap)}</p>
                <p className="font-mono text-[11px] text-[#8b97ab]">開 {pct(cur.gap, 1)}・高 {pct(cur.hi, 1)}・低 {pct(cur.lo, 1)}・收 {pct(cur.chg, 1)}</p>
                {cur.sell.map((f, i) => <p key={`s${i}`} className="font-mono text-[11px]" style={{ color: SELL }}>賣 {f[0]} × {f[1].toLocaleString()}（{pct(f[2], 1)}，區間 {Math.round(f[3] * 100)}%，{hours(f[4])}）</p>)}
                {cur.buy.map((f, i) => <p key={`b${i}`} className="font-mono text-[11px]" style={{ color: BUY }}>買 {f[0]} × {f[1].toLocaleString()}（{pct(f[2], 1)}，區間 {Math.round(f[3] * 100)}%，{hours(f[4])}）</p>)}
                {cur.note && <p className="text-[11px] text-[#7c8aa0]">{cur.note}</p>}
                <p className="text-[10px] text-[#7c8aa0]">點下方表格任一列切換。</p>
              </div>
            </section>
          )}
          <SortTable<Trade> rows={tr} columns={cTr} rowKey={(t) => t.date + t.code + t.per} initialSort={{ key: "date", desc: true }} limit={60} onRowClick={(t) => setPick(t)} />
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
            <h3 className="text-sm text-white font-semibold mb-2">公開的月對帳單（現沖，2026 年）</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {data.trades.months.map((m) => (
                <div key={m.m} className="rounded-lg bg-[#141c2e] p-3">
                  <div className="text-[11px] text-[#8b97ab]">{Number(m.m.slice(5))} 月</div>
                  <div className="font-mono text-lg text-[#f05252]">+{(m.pnl / 1e4).toFixed(0)} 萬</div>
                  <div className="text-[10px] font-mono text-[#7c8aa0]">成交 {(m.amt / 1e8).toFixed(1)} 億・每趟 {(m.pnl / m.amt * 100 * 2).toFixed(2)}%</div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-[#7c8aa0]">每趟＝損益 ÷（成交總價金 ÷ 2），約等於每一次當沖的平均淨報酬，約 0.4～0.9%；2025 全年現沖 +4,261 萬、成交 210 億（每趟約 0.4%）。和回測 A 打法扣成本後 +0.4% 同一個量級。</p>
          </section>
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] text-slate-300 space-y-1.5">
            <h3 className="text-sm text-white font-semibold mb-1">他在貼文裡說的</h3>
            {data.trades.quotes.map((q) => <p key={q}>・{q}</p>)}
          </section>
        </div>
      )}

      {view === "bt" && bt.groups && (
        <div className="space-y-6">
          <p className="text-xs text-[#8b97ab]">{bt.from} ～ {bt.to}，每天「前一日成交金額前 {ru.top} 名」的熱門股共 {bt.n.toLocaleString()} 筆，Yahoo Finance 日線。打法 A＝開盤賣、收盤買回；打法 B＝開盤買、收盤賣。
            成本：現股當沖證交稅 0.15%＋手續費約 0.09% ≈ {bt.cost}%。回測只能用開盤／收盤，他實際賣在開盤後的衝高、買在低檔，績效會比回測好。</p>
          <h3 className="text-sm text-white font-semibold">打法 A：強勢股開高走低（開盤賣、收盤買回）</h3>
          <SortTable<G> rows={bt.groups} columns={cG} rowKey={(g) => g.group} />
          <SortTable<G> rows={bt.years} columns={cG} rowKey={(g) => g.group} />
          {!!bt.intraday?.length && (
            <>
              <h3 className="text-sm text-white font-semibold">進場時機（近 60 天 5 分 K：{bt.intraFrom} ～ {bt.intraTo}）</h3>
              <SortTable<G> rows={bt.intraday} columns={cG} rowKey={(g) => g.group} />
            </>
          )}
          <h3 className="text-sm text-white font-semibold">打法 B：大跌開低反彈（開盤買、收盤賣）</h3>
          <SortTable<G> rows={bt.bGroups} columns={cG} rowKey={(g) => g.group} />
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] leading-relaxed text-slate-300 space-y-2">
            <h3 className="text-sm text-white font-semibold">回測重點</h3>
            <p>1. 熱門股本身就有「開盤後往下」的傾向，但扣成本後幾乎打平，所以要挑「前一天漲停或近 5 日大漲」的強勢股：A 條件平均 {main ? pct(main.avg) : "—"}、勝率 {main?.win}%，2021～2026 每一年都是正的。</p>
            <p>2. 開高 4～9.5% 的平均更高但勝率只有五成出頭（少數大跌拉高平均）；開低的強勢股不要放空（扣成本為負）；開漲停的不要碰（勝率兩成）。</p>
            <p>3. 他的優勢在「賣在開盤後的衝高、買在下午低檔」：對帳單中位數賣在比開盤高 {ts.sellVsOpen}%、買回在當天區間 {Math.round(ts.buyPos * 100)}% 的低檔，所以實際每趟報酬（約 0.4～0.9%）比回測的開盤賣、收盤買回還好。</p>
            <p>4. 風險：A 條件的股票有 {bt.aRisk?.up3}% 的時候盤中會從開盤再漲 3% 以上；他的虧損日都是「收在高檔、收盤比開盤高」的強勢日，一定要設停損、不加碼。</p>
            <p>5. 打法 B 平均 {bMain ? pct(bMain.avg) : "—"}，但勝率 {bMain?.win}%，靠少數大反彈；開盤後拉高 ≥ 2% 的機率 {bt.bRise?.["2"]}%，拉高就分批賣，不要抱到收盤。</p>
          </section>
        </div>
      )}

      <Note>
        A 打法要用「現股當沖先賣後買」，標的必須可先賣後買（沒有被暫停），帳戶要有當沖資格；也可以用個股期。近期訊號是用每日開盤／收盤回算的結果，實際成交會有滑價。
        對帳單解讀為推估（截圖只露出部分成交、看不到實際成交時間），不代表原作者的真實下單邏輯。
      </Note>
    </div>
  );
}
