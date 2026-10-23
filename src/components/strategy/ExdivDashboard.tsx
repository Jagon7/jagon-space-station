"use client";

import { useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Up = { date: string; code: string; name: string; mk: string; kind: string; cash: number; close: number; y: number | null; valYi: number; sf: boolean; dealer: number; noShort: boolean; ok: boolean; tomorrow: boolean };
type Pos = { date: string; code: string; name: string; y: number; sf: boolean; entry: number; last: number; ret: number; day: number; blacks: number; exit?: string };
type G = { group: string; n: number; avg: number; med: number; win: number; ctl: number | null; netFut: number; netStk: number; black3: number; path: number[] };
type Bt = { updatedAt: string; hold: number; costFut: number; costStk: number; from: string; to: string; n: number; groups: G[]; years: G[]; recent: [string, string, string, number, boolean, number, number][] };
type Data = { updatedAt: string; asof: string; next: string; minYield: number; hold: number; upcoming: Up[]; active: Pos[]; done: Pos[]; backtest: Bt };
type View = "up" | "active" | "done" | "bt";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const gain = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const yes = (b: boolean, t = "✓") => (b ? <span className="text-[#22c55e]">{t}</span> : <span className="text-[#475569]">—</span>);

export default function ExdivDashboard() {
  const { data, error } = useStaticJson<Data>("exdiv.json");
  const wl = useWatchlist();
  const [view, setView] = useState<View>("up");
  const [onlyOk, setOnlyOk] = useState(false);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const bt = data.backtest;
  const main = bt.groups?.find((g) => g.group.includes("有個股期") && g.group.includes("4%"));
  const ok = data.upcoming.filter((u) => u.ok);
  const tmr = ok.filter((u) => u.tomorrow);
  const stock = (code: string, name: string, mk?: string) => (
    <span className="whitespace-nowrap">
      <button onClick={(e) => { e.stopPropagation(); wl.toggle(code); }} className={`mr-1.5 ${wl.has(code) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
      <span className="text-slate-200">{name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{code}</span>
      {mk === "上櫃" && <span className="ml-1 text-[10px] text-[#7c8aa0]">櫃</span>}
    </span>
  );

  const cUp: Column<Up>[] = [
    { key: "date", label: "除息日", sort: (u) => u.date, render: (u) => num(<>{md(u.date)}{u.tomorrow && <span className="ml-1 text-[10px] text-[#f59e0b]">明天</span>}</>) },
    { key: "name", label: "股票", render: (u) => <>{stock(u.code, u.name, u.mk)}{u.ok && <span className="ml-1.5 rounded bg-[#f05252]/15 px-1 text-[10px] text-[#f05252]">符合</span>}</> },
    { key: "cash", label: "現金股利", align: "right", sort: (u) => u.cash, render: (u) => num(u.cash) },
    { key: "y", label: "殖利率", align: "right", sort: (u) => u.y, render: (u) => num(u.y == null ? "—" : `${u.y.toFixed(2)}%`, (u.y ?? 0) >= data.minYield ? "text-[#f59e0b] font-semibold" : "text-slate-300") },
    { key: "valYi", label: "日均成交（億）", align: "right", sort: (u) => u.valYi, render: (u) => num(u.valYi, u.valYi >= 0.5 ? "text-slate-300" : "text-[#475569]") },
    { key: "sf", label: "個股期", align: "right", sort: (u) => (u.sf ? 1 : 0), render: (u) => yes(u.sf) },
    { key: "noShort", label: "可現沖先賣", align: "right", sort: (u) => (u.noShort ? 0 : 1), render: (u) => yes(!u.noShort) },
    { key: "dealer", label: "自營商 10 日（張）", align: "right", sort: (u) => u.dealer, render: (u) => num(u.dealer > 0 ? `+${u.dealer.toLocaleString()}` : u.dealer.toLocaleString(), gain(u.dealer)) },
    { key: "close", label: "收盤", align: "right", sort: (u) => u.close, render: (u) => num(u.close) },
  ];
  const cPos = (active: boolean): Column<Pos>[] => [
    { key: "date", label: "除息日", sort: (p) => p.date, render: (p) => num(md(p.date)) },
    { key: "name", label: "股票", render: (p) => <>{stock(p.code, p.name)}{p.sf && <span className="ml-1 text-[10px] text-[#7c8aa0]">期</span>}</> },
    { key: "y", label: "殖利率", align: "right", sort: (p) => p.y, render: (p) => num(`${p.y.toFixed(2)}%`) },
    { key: "entry", label: "除息日開盤", align: "right", render: (p) => num(p.entry) },
    { key: "last", label: active ? "最新收盤" : "第 4 天收盤", align: "right", render: (p) => num(p.last) },
    { key: "ret", label: "放空報酬", align: "right", sort: (p) => p.ret, render: (p) => num(pct(p.ret), gain(p.ret)) },
    { key: "blacks", label: "收黑天數", align: "right", sort: (p) => p.blacks, render: (p) => num(`${p.blacks}/${p.day}`) },
    ...(active ? [{ key: "exit", label: "預計回補", align: "right" as const, render: (p: Pos) => num(p.exit ? md(p.exit) : "—", "text-[#f59e0b]") }] : []),
  ];
  const cG: Column<G>[] = [
    { key: "group", label: "分組", render: (g) => <span className="text-slate-200">{g.group}</span> },
    { key: "n", label: "事件數", align: "right", render: (g) => num(g.n.toLocaleString()) },
    { key: "avg", label: `放空 ${bt.hold} 日平均`, align: "right", render: (g) => num(pct(g.avg), gain(g.avg)) },
    { key: "win", label: "勝率", align: "right", render: (g) => num(`${g.win}%`) },
    { key: "ctl", label: "對照（非除息期間）", align: "right", render: (g) => num(pct(g.ctl), "text-[#8b97ab]") },
    { key: "net", label: "扣成本：個股期／融券", align: "right", render: (g) => <span className="font-mono whitespace-nowrap"><span className={gain(g.netFut)}>{pct(g.netFut)}</span><span className="text-[#475569]">／</span><span className={gain(g.netStk)}>{pct(g.netStk)}</span></span> },
    { key: "black3", label: "4 天中 ≥3 天收黑", align: "right", render: (g) => num(`${g.black3}%`) },
  ];
  const maxP = main ? Math.max(...main.path.map((x) => Math.abs(x)), 0.1) : 1;

  return (
    <div>
      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] leading-relaxed text-slate-300 space-y-2">
        <h3 className="text-sm text-white font-semibold">策略精神</h3>
        <p>大股東為了節稅，除息前透過 swap 把現股「借放」給自營商：大股東 swap 買、賣現貨，自營商 swap 賣、買現貨避險，大股東實質上還是持有。
          除息後 swap 結束，自營商在兩三天內把現貨賣掉，大股東再慢慢買回。所以高殖利率股除息後幾天容易連續收黑；我們像投信一樣在那裡接自營商的賣壓、同時做反向，等大股東買盤歸位。</p>
        <p>做法：近兩週要除息、殖利率高的股票，<b className="text-white">除息日開盤放空，持有 {data.hold} 個交易日（含除息日）收盤回補</b>。
          除息前後融券常暫停，有個股期的最方便（個股期會自動調整股利，成本也低）。</p>
      </section>

      <KpiRow>
        <Kpi label={`${md(data.next)} 除息・符合條件`} value={tmr.length} unit="檔" sub={tmr.map((u) => u.name).join("、") || "—"} color="text-[#f05252]" />
        <Kpi label="未來 14 天符合條件" value={ok.length} unit="檔" sub={`殖利率 ≥ ${data.minYield}%、日均成交 ≥ 0.5 億`} />
        <Kpi label="持有中（模擬）" value={data.active.length} unit="檔" sub={data.active.length ? `平均 ${pct(data.active.reduce((s, p) => s + p.ret, 0) / data.active.length)}` : undefined} />
        <Kpi label="回測：殖利率≥4%＋個股期" value={main ? pct(main.avg) : "—"} color={gain(main?.avg)} sub={main ? `${main.n} 筆・勝率 ${main.win}%・扣成本 ${pct(main.netFut)}` : undefined} />
      </KpiRow>

      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <Pills<View> value={view} onChange={setView} options={[
          { value: "up", label: `即將除息（${data.upcoming.length}）` }, { value: "active", label: `持有中（${data.active.length}）` },
          { value: "done", label: `近期出場（${data.done.length}）` }, { value: "bt", label: "回測" }]} />
        {view === "up" && <label className="flex items-center gap-1.5 text-xs text-slate-400"><input type="checkbox" checked={onlyOk} onChange={(e) => setOnlyOk(e.target.checked)} />只看符合條件</label>}
      </div>

      {view === "up" && ((onlyOk ? ok : data.upcoming).length
        ? <SortTable<Up> rows={onlyOk ? ok : data.upcoming} columns={cUp} rowKey={(u) => u.date + u.code} initialSort={{ key: "date", desc: false }} />
        : <Empty>未來 14 天沒有{onlyOk ? "符合條件的" : ""}除息股票（除息旺季在 6～9 月）。</Empty>)}
      {view === "active" && (data.active.length
        ? <SortTable<Pos> rows={data.active} columns={cPos(true)} rowKey={(p) => p.date + p.code} initialSort={{ key: "date", desc: true }} />
        : <Empty>目前沒有持有中的部位。</Empty>)}
      {view === "done" && (data.done.length
        ? <SortTable<Pos> rows={data.done} columns={cPos(false)} rowKey={(p) => p.date + p.code} initialSort={{ key: "date", desc: true }} />
        : <Empty>近 45 天沒有出場紀錄（本站除權息資料保留 45 天，更早的看「回測」）。</Empty>)}

      {view === "bt" && bt.groups && (
        <div className="space-y-6">
          <p className="text-xs text-[#8b97ab]">{bt.from} ～ {bt.to} 共 {bt.n.toLocaleString()} 次除息（日均成交 ≥ 5000 萬、純現金股利），Yahoo Finance 日線。對照組＝同一檔股票除息前後 30／60 個交易日任意 {bt.hold} 天放空，用來排除「本來就容易開高走低」的影響。</p>
          {main && (
            <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
              <h3 className="text-sm text-white font-semibold mb-1">平均走勢：{main.group}（{main.n} 筆）</h3>
              <p className="text-xs text-[#8b97ab] mb-4">從除息日開盤算起，每天收盤的平均漲跌（負＝下跌，放空賺）</p>
              <div className="grid grid-cols-7 gap-2 items-end h-32">
                {main.path.map((v, k) => (
                  <div key={k} className="flex flex-col items-center justify-start h-full">
                    <div className="w-full flex-1 flex flex-col justify-start">
                      <div className={`w-full rounded-b ${k < bt.hold ? "bg-[#22c55e]/70" : "bg-[#475569]/60"}`} style={{ height: `${(Math.abs(v) / maxP) * 100}%` }} />
                    </div>
                    <div className={`mt-1 text-[11px] font-mono ${gain(v)}`}>{pct(v)}</div>
                    <div className="text-[10px] text-[#7c8aa0]">{k === 0 ? "除息日" : `第 ${k + 1} 天`}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
          <SortTable<G> rows={bt.groups} columns={cG} rowKey={(g) => g.group} />
          <SortTable<G> rows={bt.years} columns={cG} rowKey={(g) => g.group} />
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] leading-relaxed text-slate-300 space-y-2">
            <h3 className="text-sm text-white font-semibold">回測重點</h3>
            <p>1. 效果確實存在：除息後 {bt.hold} 天放空平均賺 0.9%，對照組（非除息期間）大約 0%，2022～2026 每一年都成立。</p>
            <p>2. 殖利率越高越明顯：殖利率 ≥ 6% 平均 +1.5%、勝率 65%；殖利率 2～4% 只有 +0.6%。</p>
            <p>3. 跌幅主要在除息當天和之後兩天，第 3 天收盤附近最深，之後開始反彈，所以不建議抱太久。</p>
            <p>4. 有沒有個股期對報酬影響不大，主要是讓你放得了空（除息前後融券常暫停）、成本比較低。</p>
            <p>5. 自營商條件（2026 年、本站有法人資料的 508 次除息）：除息前 10 日自營商<b>淨買</b>的反而只有 +0.9%、淨賣的 +2.2%，和「自營商先買現貨、除息後倒貨」的假設相反。
              可能原因：本站只有自營商「自行＋避險」合計，看不到 swap 避險部位本身；也只有一個除息季的樣本。這個條件先只列出參考、不拿來篩選。</p>
          </section>
          <SortTable<[string, string, string, number, boolean, number, number]> rows={bt.recent.slice(0, 80)} rowKey={(r) => r[0] + r[1]} initialSort={{ key: "d", desc: true }} columns={[
            { key: "d", label: "除息日", sort: (r) => r[0], render: (r) => num(r[0]) },
            { key: "s", label: "股票（殖利率 ≥ 4%）", render: (r) => <>{stock(r[1], r[2])}{r[4] && <span className="ml-1 text-[10px] text-[#7c8aa0]">期</span>}</> },
            { key: "y", label: "殖利率", align: "right", sort: (r) => r[3], render: (r) => num(`${r[3].toFixed(2)}%`) },
            { key: "r", label: `放空 ${bt.hold} 日`, align: "right", sort: (r) => r[5], render: (r) => num(pct(r[5]), gain(r[5])) },
            { key: "b", label: "收黑天數", align: "right", sort: (r) => r[6], render: (r) => num(`${r[6]}/${bt.hold}`) },
          ]} />
        </div>
      )}

      <Note>
        「持有中／近期出場」是依策略規則用每日行情回算的模擬部位（除息日開盤放空、第 {data.hold} 個交易日收盤回補），不是實際交易紀錄。
        殖利率＝現金股利 ÷ 除息前收盤；成本：個股期來回約 0.1%、融券（手續費＋證交稅＋借券費）約 0.6%。
        自營商 10 日＝最近 10 個交易日自營商（自行買賣＋避險）淨買賣張數；可現沖先賣依證交所／櫃買中心今天的暫停先賣後買註記。
      </Note>
    </div>
  );
}
