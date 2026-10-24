"use client";

import { useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Hot = { code: string; name: string; mk: string; close: number; chg: number | null; p5: number | null; valYi: number; rank: number; sector: string | null; noShort: boolean };
type Cand = Hot & { lo: number; hi: number };
type Sig = { date: string; code: string; name: string; gap: number; p5: number; open: number; high: number; close: number; ret: number; openHigh: boolean; sector: string | null };
type Bar = [string, number, number, number, number];
type Trade = { date: string; code: string; name: string; side: "short" | "long" | "unknown"; sell: number[]; buy: number[]; pnl: number | null; shot: string; note: string;
  pc: number; o: number; h: number; l: number; c: number; gap: number; hi: number; lo: number; chg: number; ixGap: number; ixChg: number; prev: number; p5: number; bars: Bar[] };
type G = { group: string; n: number; avg: number; med: number; win: number; net: number; hi?: number; lo?: number };
type Bt = { updatedAt: string; cost: number; from: string; to: string; n: number; groups: G[]; years: G[]; bGroups: G[]; bRise: Record<string, number>;
  aRisk: { up3: number; up5: number; dn3: number }; intraday?: G[]; intraFrom?: string; intraTo?: string };
type Data = { updatedAt: string; asof: string; next: string; rule: { top: number; gap: [number, number]; run5: number; cost: number };
  cand: Cand[]; hot: Hot[]; recent: Sig[]; summary: { n: number; avg: number | null; win: number | null; net: number | null; days: number; from: string; to: string };
  trades: { source: string; trades: Trade[]; months: { m: string; pnl: number; amt: number }[]; quotes: string[] }; backtest: Bt };
type View = "cand" | "recent" | "trades" | "bt";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const gain = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const SELL = "#f59e0b", BUY = "#06b6d4";

/** 當天走勢：有 5 分 K 畫收盤價折線，沒有就畫一根日 K；橘線＝賣出價、青線＝買進價、虛線＝昨收 */
function TradeChart({ t }: { t: Trade }) {
  const W = 320, H = 150, L = 4, R = 46, T = 8, B = 18;
  const prices = [t.h, t.l, t.pc, ...t.sell, ...t.buy, ...t.bars.flatMap((b) => [b[2], b[3]])];
  const max = Math.max(...prices), min = Math.min(...prices), pad = (max - min) * 0.06 || 1;
  const y = (p: number) => T + ((max + pad - p) / (max - min + 2 * pad)) * (H - T - B);
  const n = t.bars.length;
  const x = (i: number) => L + (i / Math.max(n - 1, 1)) * (W - L - R);
  const label = (p: number) => `${p >= 1000 ? p.toFixed(0) : p}（${pct((p / t.pc - 1) * 100, 1)}）`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
      <line x1={L} x2={W - R} y1={y(t.pc)} y2={y(t.pc)} stroke="#475569" strokeDasharray="3 3" />
      <text x={W - R + 3} y={y(t.pc) + 3} fontSize="8" fill="#7c8aa0">昨收</text>
      {n ? (
        <>
          <polyline fill="none" stroke="#94a3b8" strokeWidth="1.3" points={t.bars.map((b, i) => `${x(i)},${y(b[4])}`).join(" ")} />
          <line x1={x(0)} x2={x(0)} y1={y(t.bars[0][2])} y2={y(t.bars[0][3])} stroke="#94a3b8" />
          {["09:00", "10:30", "12:00", "13:25"].map((hm) => {
            const i = t.bars.findIndex((b) => b[0] >= hm);
            return i < 0 ? null : <text key={hm} x={x(i)} y={H - 5} fontSize="8" fill="#7c8aa0" textAnchor={hm === "09:00" ? "start" : hm === "13:25" ? "end" : "middle"}>{hm}</text>;
          })}
        </>
      ) : (
        <>
          <line x1={(W - R) / 2} x2={(W - R) / 2} y1={y(t.h)} y2={y(t.l)} stroke="#94a3b8" />
          <rect x={(W - R) / 2 - 10} width="20" y={Math.min(y(t.o), y(t.c))} height={Math.max(Math.abs(y(t.o) - y(t.c)), 1)} fill={t.c >= t.o ? "#f05252" : "#22c55e"} opacity="0.8" />
          <text x={(W - R) / 2 + 14} y={y(t.o) + 3} fontSize="8" fill="#94a3b8">開</text>
          <text x={(W - R) / 2 + 14} y={y(t.c) + 3} fontSize="8" fill="#94a3b8">收</text>
          <text x={L} y={H - 5} fontSize="8" fill="#7c8aa0">（這天沒有 5 分 K，畫日 K）</text>
        </>
      )}
      {t.sell.map((p, i) => <g key={`s${i}`}><line x1={L} x2={W - R} y1={y(p)} y2={y(p)} stroke={SELL} strokeWidth="0.8" opacity="0.8" />{i === t.sell.length - 1 && <text x={W - R + 3} y={y(p) + 3} fontSize="8" fill={SELL}>賣 {label(p).split("（")[0]}</text>}</g>)}
      {t.buy.map((p, i) => <g key={`b${i}`}><line x1={L} x2={W - R} y1={y(p)} y2={y(p)} stroke={BUY} strokeWidth="0.8" opacity="0.8" />{i === 0 && <text x={W - R + 3} y={y(p) + 3} fontSize="8" fill={BUY}>買 {label(p).split("（")[0]}</text>}</g>)}
    </svg>
  );
}

export default function G85Dashboard() {
  const { data, error } = useStaticJson<Data>("85g.json");
  const wl = useWatchlist();
  const [view, setView] = useState<View>("cand");
  const [showHot, setShowHot] = useState(false);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const bt = data.backtest, ru = data.rule, s = data.summary;
  const main = bt.groups?.find((g) => g.group.startsWith("A＋前 5 日漲 ≥ 10%（"));
  const bMain = bt.bGroups?.find((g) => g.group.startsWith("B 指數"));
  const tr = data.trades?.trades ?? [];
  const total = (data.trades?.months ?? []).reduce((a, m) => a + m.pnl, 0);
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
    { key: "chg", label: "今日", align: "right", sort: (r) => r.chg, render: (r) => num(pct(r.chg), gain(r.chg)) },
    { key: "p5", label: "近 5 日", align: "right", sort: (r) => r.p5, render: (r) => num(pct(r.p5, 1), (r.p5 ?? 0) >= ru.run5 ? "text-[#f05252] font-semibold" : gain(r.p5)) },
    { key: "valYi", label: "成交（億）", align: "right", sort: (r) => r.valYi, render: (r) => num(r.valYi) },
  ];
  const cCand: Column<Cand>[] = [
    ...cHot.slice(1, 7),
    { key: "band", label: `明天開在這區間＝開高 ${ru.gap[0]}～${ru.gap[1]}%`, align: "right", render: (r) => num(`${r.lo} ～ ${r.hi}`, "text-[#f59e0b]") },
  ];
  const cSig: Column<Sig>[] = [
    { key: "date", label: "日期", sort: (r) => r.date, render: (r) => num(md(r.date)) },
    { key: "name", label: "股票", render: (r) => stock(r.code, r.name) },
    { key: "sector", label: "族群", render: (r) => <span className="text-xs text-slate-400">{r.sector ?? "—"}</span> },
    { key: "p5", label: "前 5 日", align: "right", sort: (r) => r.p5, render: (r) => num(pct(r.p5, 1)) },
    { key: "gap", label: "開盤", align: "right", sort: (r) => r.gap, render: (r) => num(pct(r.gap), "text-[#f05252]") },
    { key: "oh", label: "開盤＝最高", align: "right", sort: (r) => (r.openHigh ? 1 : 0), render: (r) => (r.openHigh ? <span className="text-[#22c55e]">✓</span> : <span className="text-[#475569]">—</span>) },
    { key: "ret", label: "開盤賣→收盤買", align: "right", sort: (r) => r.ret, render: (r) => num(pct(r.ret), r.ret > 0 ? "text-[#f05252]" : "text-[#22c55e]") },
  ];
  const cG: Column<G>[] = [
    { key: "group", label: "分組", render: (g) => <span className="text-slate-200 whitespace-pre">{g.group}</span> },
    { key: "n", label: "筆數", align: "right", render: (g) => num(g.n.toLocaleString()) },
    { key: "avg", label: "平均報酬", align: "right", render: (g) => num(pct(g.avg), g.avg > 0 ? "text-[#f05252]" : "text-[#22c55e]") },
    { key: "med", label: "中位數", align: "right", render: (g) => num(pct(g.med)) },
    { key: "win", label: "勝率", align: "right", render: (g) => num(`${g.win}%`) },
    { key: "net", label: `扣成本 ${bt.cost}%`, align: "right", render: (g) => num(pct(g.net), g.net > 0 ? "text-[#f05252]" : "text-[#22c55e]") },
  ];

  return (
    <div>
      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] leading-relaxed text-slate-300 space-y-2">
        <h3 className="text-sm text-white font-semibold">策略精神</h3>
        <p>85g（IG @85ga_stock）是專做日內波的當沖交易員，每天額度 2000～4000 萬，自稱「主要依靠族群性、籌碼跟量價」。
          把 2026 年 6～9 月公開的對帳單對照當天 5 分 K 後發現：<b className="text-white">他大部分是「現股當沖先賣後買」</b>——賣出價集中在 09:00～09:30 的開高區，買回價集中在 13:00 之後的低檔。
          他自己說：「這開高走低的特性永遠都不會變」「指數開高時，開盤最高點的熱門股很容易一直跌」。</p>
        <p><b className="text-[#f59e0b]">打法 A｜開高走低（主力）</b>：前一天成交金額前 {ru.top} 名的熱門族群股（記憶體、光通訊、面板…），尤其<b className="text-white">前 5 日已漲 ≥ {ru.run5}%</b>，
          隔天<b className="text-white">開高 {ru.gap[0]}～{ru.gap[1]}%</b>（不碰開漲停）→ 開盤 30 分鐘內分批賣出（開盤就是最高、15 分鐘後跌破開盤價最理想），13:00 之後到收盤前分批買回。</p>
        <p><b className="text-[#06b6d4]">打法 B｜大跌開低反彈（輔助）</b>：指數開低 ≥ 1%，熱門小型股開很低（甚至跌停）時先買，等盤中拉高一段就分批賣——「指數大跌，開低 88% 一定會拉高一段」。
          但「開低走低我不會空」：開低的股票不追空。</p>
        <p className="text-xs text-[#8b97ab]">紀律：不加碼、少追價（V 轉容易大賠）；一路下跌先減碼；月初公布營收期間不追高；量縮、沒波動的日子不做；暫停先賣後買的股票不能做 A。</p>
      </section>

      <KpiRow>
        <Kpi label={`${md(data.next)} 觀察（A 打法候選）`} value={data.cand.length} unit="檔" sub={data.cand.slice(0, 4).map((c) => c.name).join("、") || "—"} color="text-[#f59e0b]" />
        <Kpi label={`近 ${s.days} 天 A 訊號（漲多＋開高）`} value={pct(s.avg)} color={gain(s.avg)} sub={`${s.n} 筆・勝率 ${s.win ?? "—"}%`} />
        <Kpi label="5 年回測：A＋前 5 日漲 ≥ 10%" value={main ? pct(main.avg) : "—"} color={gain(main?.avg)} sub={main ? `${main.n.toLocaleString()} 筆・勝率 ${main.win}%・扣成本 ${pct(main.net)}` : undefined} />
        <Kpi label="85g 公開月損益（6～9 月）" value={`+${(total / 1e4).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} unit="萬" color="text-[#f05252]" sub="4 個月" />
      </KpiRow>

      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <Pills<View> value={view} onChange={setView} options={[
          { value: "cand", label: `明日觀察（${data.cand.length}）` }, { value: "recent", label: `近期訊號（${data.recent.length}）` },
          { value: "trades", label: `實單解析（${tr.length}）` }, { value: "bt", label: "回測" }]} />
        <span className="text-[11px] text-[#7c8aa0]">依 {md(data.asof)} 收盤</span>
      </div>

      {view === "cand" && (
        <div className="space-y-4">
          <p className="text-xs text-[#8b97ab]">今天成交金額前 {ru.top} 名、近 5 日漲 ≥ {ru.run5}% 的股票。明天開盤如果落在右邊的價格區間（開高 {ru.gap[0]}～{ru.gap[1]}%），就是打法 A 的標的：
            開盤後先看 15 分鐘，跌破開盤價再賣；13:00 後買回。同族群多檔一起開高更好。</p>
          {data.cand.length ? <SortTable<Cand> rows={data.cand} columns={cCand} rowKey={(r) => r.code} initialSort={{ key: "p5", desc: true }} />
            : <Empty>今天的熱門股沒有近 5 日漲 ≥ {ru.run5}% 的，明天沒有 A 打法候選。</Empty>}
          <button onClick={() => setShowHot(!showHot)} className="text-xs text-[#4f8cff] hover:underline">{showHot ? "收起" : "展開"}今天成交金額前 {ru.top} 名（指數大跌開低時，打法 B 從這裡挑）</button>
          {showHot && <SortTable<Hot> rows={data.hot} columns={cHot} rowKey={(r) => r.code} initialSort={{ key: "rank", desc: false }} />}
        </div>
      )}

      {view === "recent" && (
        <div className="space-y-3">
          <p className="text-xs text-[#8b97ab]">{s.from} ～ {s.to}，每天符合 A 條件（前一日成交前 {ru.top}、前 5 日漲 ≥ {ru.run5}%、開高 {ru.gap[0]}～{ru.gap[1]}%）的股票，開盤賣、收盤買回的結果（正＝賺）。
            共 {s.n} 筆、平均 {pct(s.avg)}、勝率 {s.win}%、扣成本 {pct(s.net)}。</p>
          {data.recent.length ? <SortTable<Sig> rows={data.recent} columns={cSig} rowKey={(r) => r.date + r.code} initialSort={{ key: "date", desc: true }} limit={60} />
            : <Empty>近期沒有符合條件的訊號。</Empty>}
        </div>
      )}

      {view === "trades" && (
        <div className="space-y-4">
          <p className="text-xs text-[#8b97ab]">{data.trades.source}。截圖只露出部分成交，買賣價對照當天走勢判斷進出順序（橘線＝賣出、青線＝買進、虛線＝昨收）。</p>
          <div className="grid gap-4 md:grid-cols-2">
            {tr.map((t) => (
              <div key={t.date + t.code} className="rounded-xl border border-[#243247] bg-[#0d1220] p-4">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div>
                    <span className="font-mono text-sm text-white">{md(t.date)}</span>
                    <span className="ml-2">{stock(t.code, t.name)}</span>
                    <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] ${t.side === "short" ? "bg-[#f59e0b]/15 text-[#f59e0b]" : t.side === "long" ? "bg-[#06b6d4]/15 text-[#06b6d4]" : "bg-[#475569]/30 text-[#8b97ab]"}`}>
                      {t.side === "short" ? "A 先賣後買" : t.side === "long" ? "B 先買後賣" : "不明"}</span>
                  </div>
                  {t.pnl != null && <span className="font-mono text-sm text-[#f05252] whitespace-nowrap">+{t.pnl.toLocaleString()}</span>}
                </div>
                <div className="text-[11px] font-mono text-[#8b97ab] mb-2">
                  開 <span className={gain(t.gap)}>{pct(t.gap, 1)}</span>・高 <span className={gain(t.hi)}>{pct(t.hi, 1)}</span>・低 <span className={gain(t.lo)}>{pct(t.lo, 1)}</span>・收 <span className={gain(t.chg)}>{pct(t.chg, 1)}</span>
                  ｜指數開 <span className={gain(t.ixGap)}>{pct(t.ixGap)}</span>｜前 5 日 <span className={gain(t.p5)}>{pct(t.p5, 1)}</span>
                </div>
                <TradeChart t={t} />
                <div className="mt-1 text-[11px] font-mono">
                  {!!t.sell.length && <span className="mr-3" style={{ color: SELL }}>賣 {t.sell.map((p) => `${p}(${pct((p / t.pc - 1) * 100, 1)})`).join("、")}</span>}
                  {!!t.buy.length && <span style={{ color: BUY }}>買 {t.buy.map((p) => `${p}(${pct((p / t.pc - 1) * 100, 1)})`).join("、")}</span>}
                </div>
                <p className="mt-1.5 text-xs text-slate-400 leading-relaxed">{t.note}<span className="ml-1 text-[10px] text-[#7c8aa0]">（{t.shot}）</span></p>
              </div>
            ))}
          </div>
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
            <h3 className="text-sm text-white font-semibold mb-2">公開的月對帳單（現沖）</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {data.trades.months.map((m) => (
                <div key={m.m} className="rounded-lg bg-[#141c2e] p-3">
                  <div className="text-[11px] text-[#8b97ab]">{Number(m.m.slice(5))} 月</div>
                  <div className="font-mono text-lg text-[#f05252]">+{(m.pnl / 1e4).toFixed(0)} 萬</div>
                  <div className="text-[10px] font-mono text-[#7c8aa0]">成交 {(m.amt / 1e8).toFixed(1)} 億・報酬 {(m.pnl / m.amt * 100 * 2).toFixed(2)}%／筆</div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-[#7c8aa0]">報酬／筆＝損益 ÷（成交總價金 ÷ 2），約等於每一趟當沖的平均淨報酬；他每月約 0.3～0.9%，和回測 A 打法扣成本後 +0.4～0.9% 同一個量級。</p>
          </section>
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] text-slate-300 space-y-1.5">
            <h3 className="text-sm text-white font-semibold mb-1">他在貼文裡說的</h3>
            {data.trades.quotes.map((q) => <p key={q}>・{q}</p>)}
          </section>
        </div>
      )}

      {view === "bt" && bt.groups && (
        <div className="space-y-6">
          <p className="text-xs text-[#8b97ab]">{bt.from} ～ {bt.to}，每天「前一日成交金額前 50 名」的熱門股共 {bt.n.toLocaleString()} 筆，Yahoo Finance 日線。打法 A＝開盤賣、收盤買回；打法 B＝開盤買、收盤賣（都是一天內出場）。
            成本：現股當沖證交稅 0.15%＋手續費約 0.09% ≈ {bt.cost}%。</p>
          <h3 className="text-sm text-white font-semibold">打法 A：開高走低（開盤賣、收盤買回）</h3>
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
            <p>1. 熱門股本身就有「開盤後往下」的傾向（全部平均 +0.3%，扣成本後幾乎打平），所以單純開高放空不夠，要挑條件。</p>
            <p>2. 最有效的是<b className="text-white">「漲多＋開高」</b>：前 5 日漲 ≥ 10% 再開高 1.5～6%，開盤賣、收盤買回平均 {main ? pct(main.avg) : "—"}、勝率 {main?.win}%；
              前 5 日漲 ≥ 25% 更強。2022～2026 每一年都是正的（2025 年最弱）。</p>
            <p>3. 等 15 分鐘、確認跌破開盤價（開盤就是高點）再賣，勝率更高；如果 15 分鐘後還站在開盤價之上就不做，那一組勝率只有五成。設停損會少賺一點，但能避開軋空。</p>
            <p>4. 風險：符合 A 條件的股票有 {bt.aRisk?.up3}% 的時候盤中會從開盤再漲 3% 以上、{bt.aRisk?.up5}% 會漲 5% 以上，一定要分批、不加碼，這也是他說「少追價、不加碼」的原因。開漲停的不要碰（勝率只有兩成）。</p>
            <p>5. 打法 B 平均 {bMain ? pct(bMain.avg) : "—"}，但勝率只有 {bMain?.win}%（少數大反彈拉高平均）；開盤後拉高 ≥ 2% 的機率 {bt.bRise?.["2"]}%、≥ 3% 的機率 {bt.bRise?.["3"]}%，
              要用「拉高就分批賣」而不是抱到收盤。</p>
            <p>6. 他的公開月報酬約每筆 0.3～0.9%，和回測同量級；回測沒辦法模擬他「看族群、看隔日沖籌碼、看盤感」的部分，所以這頁是幫你找標的與時機，不是自動下單。</p>
          </section>
        </div>
      )}

      <Note>
        A 打法要用「現股當沖先賣後買」，標的必須是可先賣後買（沒有被暫停）的股票，且帳戶要有當沖資格；也可以用個股期。
        近期訊號是用每日開盤／收盤回算的結果，實際成交會有滑價。
      </Note>
    </div>
  );
}
