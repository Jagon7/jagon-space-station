"use client";

import { useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Pick1 = { code: string; name: string; mk: string; close: number; valueYi: number; zvol: number; days: number; tz: number; mz: number; ret5: number };
type Pick2 = { code: string; name: string; mk: string; close: number; valueYi: number | null; chip: number; chipZ: number; news: string[] };
type Hold = { date: string; code: string; name: string; entry: number; exitDate: string; last?: number; exit?: number; ret: number | null; excess?: number; day?: number };
type Side<P> = { picks: P[]; holding: Hold[]; history: Hold[]; stats: { n: number; avg: number | null; win: number | null; excess: number | null; from: string | null } };
type Data = { asof: string; next: string; updatedAt: string; newsFrom: string | null; s1: Side<Pick1>; s2: Side<Pick2> };
type Tab = "s1" | "s2";
type View = "picks" | "holding" | "history";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const Stock = ({ code, name, mk, star, onStar }: { code: string; name: string; mk?: string; star: boolean; onStar: () => void }) => (
  <span className="whitespace-nowrap">
    <button onClick={(e) => { e.stopPropagation(); onStar(); }} className={`mr-1.5 ${star ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
    <span className="text-slate-200">{name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{code}</span>
    {mk === "上櫃" && <span className="ml-1 text-[10px] text-[#7c8aa0]">櫃</span>}
  </span>
);

const RULES: Record<Tab, { title: string; idea: string; rules: string[]; report: string; proxy?: string }> = {
  s1: {
    title: "出量做多（十日波段）",
    idea: "一段時間成交量穩定的股票，突然放量（而且不是只放一天），之後常有一段趨勢；進場後外資持續買、散戶持續賣。",
    rules: [
      "量穩（跟自己比）：過去 20 日成交金額的變異係數（CV＝標準差 ÷ 平均），比自己過去 60 個 CV 的平均低 1 個標準差以上（時間量穩 Z ≥ 1）",
      "量穩（跟市場比）：上面的分數在全市場（昨日成交金額 > 5000 萬）中標準化後也 ≥ 1",
      "放量：近 5 日平均成交金額 ≥ 前段 20 日（T-25～T-6）平均＋1 個標準差（放量 Z ≥ 1）",
      "放量持續：近 5 日至少 3 天單日成交金額超過同一門檻",
      "近 5 日報酬 > 0（排除放量下跌）、昨日成交金額 > 5000 萬、近 10 日沒有處置、進場日收盤沒有漲停",
    ],
    report: "原始回測 2020/04～2026/07：Sharpe 1.70，投組每日報酬 29bp、超額 17bp；平均每天新進 4.4 檔、持有約 44 檔。",
  },
  s2: {
    title: "輿情籌碼（十日波段，優化版）",
    idea: "乾柴需要烈火：過去一段時間籌碼已經轉好（散戶持續賣、籌碼往大戶集中），這時候正面輿情突然出現，就是點火的燃料。",
    rules: [
      "籌碼好：近 20 日（T-21～T-2）散戶賣超強度＝散戶淨賣超 ÷ 換手量，高於全市場均值＋1 個標準差",
      "輿情好：昨天個股正面輿情「首次出現」（前一天沒有）",
      "母體：前一日成交金額 > 5000 萬；進場日收盤沒有漲停",
    ],
    report: "原始回測 2022/04～2026/07：優化版 Sharpe 1.71，投組每日報酬 24bp、超額 12bp；平均每天新進 2.4 檔、持有約 24 檔。",
    proxy: "原策略的「散戶分點淨賣超」與「網路輿情旗標」是 UC Brain 的分點分類與 NLP 資料，公開來源拿不到。本站用替代資料：散戶淨賣超 ≈ 三大法人淨買超（台股每筆成交有買有賣，法人買超即散戶與其他人賣超），換手量用成交張數；正面輿情用鉅亨網台股新聞標題的正負面字詞判斷。訊號會比原策略少、也可能有差異，請當作參考。",
  },
};

export default function StrategyDashboard() {
  const { data, error } = useStaticJson<Data>("strategy.json");
  const wl = useWatchlist();
  const [tab, setTab] = useState<Tab>("s1");
  const [view, setView] = useState<View>("picks");
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const side = data[tab] as Side<Pick1 | Pick2>;
  const r = RULES[tab];
  const st = side.stats;
  const hold = side.holding;
  const exitTomorrow = hold.filter((h) => h.exitDate === data.next);
  const holdAvg = hold.filter((h) => h.ret != null).length ? hold.reduce((s, h) => s + (h.ret ?? 0), 0) / hold.filter((h) => h.ret != null).length : null;
  const star = (c: string) => ({ star: wl.has(c), onStar: () => wl.toggle(c) });

  const c1: Column<Pick1>[] = [
    { key: "name", label: "股票", render: (p) => <Stock code={p.code} name={p.name} mk={p.mk} {...star(p.code)} /> },
    { key: "close", label: "收盤", align: "right", sort: (p) => p.close, render: (p) => <span className="font-mono text-slate-300">{p.close}</span> },
    { key: "valueYi", label: "成交金額（億）", align: "right", sort: (p) => p.valueYi, render: (p) => <span className="font-mono text-slate-300">{p.valueYi}</span> },
    { key: "zvol", label: "放量 Z", align: "right", sort: (p) => p.zvol, render: (p) => <span className="font-mono text-[#f59e0b]">{p.zvol}</span> },
    { key: "days", label: "放量天數", align: "right", sort: (p) => p.days, render: (p) => <span className="font-mono text-slate-300">{p.days}/5</span> },
    { key: "tz", label: "量穩 Z（自身／市場）", align: "right", sort: (p) => p.mz, render: (p) => <span className="font-mono text-slate-300">{p.tz}／{p.mz}</span> },
    { key: "ret5", label: "近 5 日", align: "right", sort: (p) => p.ret5, render: (p) => <span className={`font-mono ${tone(p.ret5)}`}>{pct(p.ret5, 1)}</span> },
  ];
  const c2: Column<Pick2>[] = [
    { key: "name", label: "股票", render: (p) => <Stock code={p.code} name={p.name} mk={p.mk} {...star(p.code)} /> },
    { key: "close", label: "收盤", align: "right", sort: (p) => p.close, render: (p) => <span className="font-mono text-slate-300">{p.close}</span> },
    { key: "chip", label: "籌碼強度", align: "right", sort: (p) => p.chipZ, render: (p) => <span className="font-mono text-[#f59e0b]">{p.chip}%<span className="text-[10px] text-[#8b97ab] ml-1">Z {p.chipZ}</span></span> },
    { key: "news", label: "觸發的正面新聞", render: (p) => <span className="text-xs text-slate-300 whitespace-normal">{p.news.join("／") || "—"}</span> },
  ];
  const ch: Column<Hold>[] = [
    { key: "name", label: "股票", render: (h) => <Stock code={h.code} name={h.name} {...star(h.code)} /> },
    { key: "date", label: "進場日", align: "right", sort: (h) => h.date, render: (h) => <span className="font-mono text-slate-300">{md(h.date)}</span> },
    { key: "entry", label: "進場價", align: "right", render: (h) => <span className="font-mono text-slate-300">{h.entry}</span> },
    view === "holding"
      ? { key: "last", label: "最新收盤", align: "right", render: (h) => <span className="font-mono text-slate-300">{h.last ?? "—"}</span> }
      : { key: "exit", label: "出場價", align: "right", render: (h) => <span className="font-mono text-slate-300">{h.exit ?? "—"}</span> },
    { key: "ret", label: view === "holding" ? "目前報酬" : "報酬（扣成本）", align: "right", sort: (h) => h.ret, render: (h) => <span className={`font-mono ${tone(h.ret)}`}>{pct(h.ret)}</span> },
    view === "holding"
      ? { key: "exitDate", label: "預計出場", align: "right", sort: (h) => h.exitDate, render: (h) => <span className={`font-mono ${h.exitDate === data.next ? "text-[#f59e0b]" : "text-slate-300"}`}>{md(h.exitDate)}{h.exitDate === data.next ? " 明天" : ""}</span> }
      : { key: "excess", label: "超額", align: "right", sort: (h) => h.excess ?? null, render: (h) => <span className={`font-mono ${tone(h.excess)}`}>{pct(h.excess)}</span> },
  ];

  return (
    <div>
      <div className="flex gap-6 border-b border-[#243247] mb-5">
        {(["s1", "s2"] as const).map((k) => (
          <button key={k} onClick={() => setTab(k)}
            className={`pb-3 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors ${tab === k ? "border-[#4f8cff] text-white" : "border-transparent text-[#8b97ab] hover:text-slate-300"}`}>
            {RULES[k].title}<span className="ml-1.5 text-[11px] font-mono text-[#7c8aa0]">{data[k].picks.length}</span>
          </button>
        ))}
      </div>
      <div className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-5">
        <div className="text-sm text-white font-semibold mb-1">策略邏輯</div>
        <p className="text-[13px] text-slate-300 leading-relaxed">{r.idea}</p>
        <ul className="mt-3 space-y-1.5">
          {r.rules.map((x) => <li key={x} className="text-[13px] leading-relaxed text-slate-300 pl-3 relative before:content-['•'] before:absolute before:left-0 before:text-[#4f8cff]">{x}</li>)}
        </ul>
        <p className="mt-3 text-xs text-[#8b97ab]">進出場：T 日收盤前半小時進場，持有 10 個交易日，第 10 個交易日後開盤半小時出場。{r.report}</p>
        {r.proxy && <p className="mt-2 text-xs leading-relaxed text-[#f59e0b]/90">⚠ {r.proxy}</p>}
      </div>
      <KpiRow>
        <Kpi label={`${md(data.next)} 進場名單`} value={side.picks.length} unit="檔" sub={`依 ${md(data.asof)} 收盤資料`} color="text-[#4f8cff]" />
        <Kpi label="持有中（依策略回算）" value={hold.length} unit="檔" sub={holdAvg == null ? undefined : `平均 ${pct(holdAvg, 1)}`} />
        <Kpi label="明天到期出場" value={exitTomorrow.length} unit="檔" color="text-[#f59e0b]" />
        <Kpi label="本站回算績效（10 日）" value={st.avg == null ? "—" : pct(st.avg)} color={tone(st.avg)}
          sub={st.n ? `${st.n} 筆・勝率 ${st.win}%・超額 ${pct(st.excess)}` : "資料累積中"} />
      </KpiRow>
      <div className="flex items-center justify-between gap-3 mb-3">
        <Pills<View> value={view} onChange={setView} options={[{ value: "picks", label: `明日進場（${side.picks.length}）` }, { value: "holding", label: `持有中（${hold.length}）` }, { value: "history", label: `已出場（${side.history.length}）` }]} />
        <span className="text-[11px] text-[#7c8aa0]">每天收盤資料到齊後更新並推播 LINE</span>
      </div>
      {view === "picks" && (side.picks.length
        ? (tab === "s1"
          ? <SortTable<Pick1> rows={data.s1.picks} columns={c1} rowKey={(p) => p.code} initialSort={{ key: "zvol", desc: true }} />
          : <SortTable<Pick2> rows={data.s2.picks} columns={c2} rowKey={(p) => p.code} initialSort={{ key: "chip", desc: true }} />)
        : <Empty>{md(data.next)} 沒有符合條件的標的。</Empty>)}
      {view !== "picks" && ((view === "holding" ? hold : side.history).length
        ? <SortTable<Hold> rows={view === "holding" ? hold : side.history} columns={ch} rowKey={(h) => h.date + h.code} initialSort={{ key: view === "holding" ? "exitDate" : "date", desc: view !== "holding" }} />
        : <Empty>{tab === "s2" && data.newsFrom ? `新聞資料從 ${md(data.newsFrom)} 開始累積，回算紀錄還不夠。` : "還沒有紀錄。"}</Empty>)}
      <Note>
        「持有中／已出場」是依策略規則用本站歷史資料回算的模擬部位（進場價用當日收盤、出場價用第 10 個交易日後的開盤，報酬已扣手續費＋證交稅 0.357%；超額＝減去同期全市場等權平均），
        不是實際交易紀錄。本站行情資料從 2026/04 開始，回算期間短，數字僅供參考。
      </Note>
    </div>
  );
}
