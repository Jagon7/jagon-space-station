"use client";

import { useMemo, useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Row = { etf: string; etfName: string; code: string; name: string; lots: number; w: number | null; cost: number; first: string; firstPx: number;
  close: number; dd: number; stop: number; dist: number; c1?: number | null; below?: string | null; due?: string | null; c5: number | null; c20: number | null; val: number; dated: boolean };
type Stock = { code: string; name: string; close: number; n: number; warn: number; stop: number; lots: number; riskLots: number; riskVal: number;
  c5: number; etfs: [string, number, string?][]; cost: number; dd: number; vol: number | null };
type Etf = { code: string; name: string; issuer: string; dated: boolean; start: string; asof: string; n: number };
type Data = { updatedAt: string; date: string; stop: number; warn: number; grace?: number; count: { stop: number; warn: number; stocks: number };
  etfs: Etf[]; rows: Row[]; stocks: Stock[]; asof?: string;
  sells?: { etf: string; etfName: string; code: string; name: string; dd: number; c1: number; lots: number; out: boolean; asof: string; prev?: string }[] };
type View = "stock" | "pos";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const ymd = (d: string) => `${d.slice(2, 4)}/${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const sign = (v: number) => `${v > 0 ? "+" : ""}${v.toLocaleString()}`;

export default function ActiveStopDashboard() {
  const { data, error } = useStaticJson<Data>("active_dd.json");
  const wl = useWatchlist();
  const [view, setView] = useState<View>("stock");
  const [etf, setEtf] = useState("all");
  const [minW, setMinW] = useState(true);
  const ddColor = (d: number) => (!data ? "" : d <= data.stop ? "text-[#f05252] font-semibold" : d <= data.warn ? "text-[#f59e0b] font-semibold" : d < 0 ? "text-[#22c55e]" : "text-[#f05252]");
  const rows = useMemo(() => (data?.rows ?? []).filter((r) => (etf === "all" || r.etf === etf) && (!minW || r.lots >= 50)), [data, etf, minW]);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;

  const star = (code: string) => (
    <button onClick={() => wl.toggle(code)} className={`mr-1.5 ${wl.has(code) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
  );
  const ddCell = (d: number) => num(`${d > 0 ? "+" : ""}${d.toFixed(1)}%`, ddColor(d));
  const distCell = (dist: number, stop: number) => dist >= 0
    ? <span className="font-mono text-[#f05252] whitespace-nowrap">已低於 {stop.toLocaleString()}</span>
    : num(`再跌 ${(-dist).toFixed(1)}%`, -dist < 10 ? "text-[#f59e0b]" : "text-slate-300");

  const today = data.updatedAt.slice(0, 10);
  const sCols: Column<Stock>[] = [
    { key: "name", label: "股票", render: (r) => (
      <span className="whitespace-nowrap">{star(r.code)}<span className="text-slate-200">{r.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{r.code}</span></span>) },
    { key: "dd", label: "合計 DD", align: "right", sort: (r) => r.dd, render: (r) => ddCell(r.dd) },
    { key: "warn", label: "≤ -30% 的 ETF", align: "right", sort: (r) => r.warn * 100 + r.stop, render: (r) => num(`${r.warn} / ${r.n}`, r.stop ? "text-[#f05252]" : r.warn ? "text-[#f59e0b]" : "text-[#8b97ab]") },
    { key: "etfs", label: "各 ETF 的 DD", render: (r) => (
      <span className="flex flex-wrap gap-1 max-w-[340px]">
        {r.etfs.map(([c, d, n]) => <span key={c} title={n} className={`rounded bg-[#1c2738] px-1.5 py-0.5 font-mono text-[10px] ${ddColor(d)}`}>{c} {d.toFixed(0)}%</span>)}
      </span>) },
    { key: "close", label: "收盤", align: "right", sort: (r) => r.close, render: (r) => num(r.close.toLocaleString()) },
    { key: "cost", label: "加權成本", align: "right", sort: (r) => r.cost, render: (r) => num(r.cost.toLocaleString(), "text-[#8b97ab]") },
    { key: "lots", label: "合計持股（張）", align: "right", sort: (r) => r.lots, render: (r) => num(r.lots.toLocaleString()) },
    { key: "riskLots", label: "≤ -30% 部位（張）", align: "right", sort: (r) => r.riskLots, render: (r) => num(r.riskLots ? r.riskLots.toLocaleString() : "—", r.riskLots ? "text-[#f59e0b]" : "text-[#8b97ab]") },
    { key: "riskVal", label: "市值（億）", align: "right", sort: (r) => r.riskVal, render: (r) => num(r.riskVal ? r.riskVal.toFixed(1) : "—") },
    { key: "vol", label: "占當日成交", align: "right", sort: (r) => (r.vol ? r.riskLots / r.vol : 0), render: (r) => num(r.vol && r.riskLots ? `${((r.riskLots / r.vol) * 100).toFixed(0)}%` : "—", "text-[#8b97ab]") },
    { key: "c5", label: "5 日增減（張）", align: "right", sort: (r) => r.c5, render: (r) => num(r.c5 ? sign(r.c5) : "—", tone(r.c5)) },
  ];
  const pCols: Column<Row>[] = [
    { key: "name", label: "股票", render: (r) => (
      <span className="whitespace-nowrap">{star(r.code)}<span className="text-slate-200">{r.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{r.code}</span></span>) },
    { key: "etf", label: "ETF", render: (r) => <span className="whitespace-nowrap text-xs"><span className="font-mono text-slate-200">{r.etf}</span><span className="ml-1 text-[#7c8aa0]">{r.etfName}</span>{!r.dated && <span className="ml-1 text-[10px] text-[#f59e0b]" title="這家投信查不到歷史持股，成本從開始抓資料那天起算">*</span>}</span> },
    { key: "dd", label: "DD", align: "right", sort: (r) => r.dd, render: (r) => ddCell(r.dd) },
    { key: "dist", label: "距 -40%", align: "right", sort: (r) => -r.dist, render: (r) => distCell(r.dist, r.stop) },
    { key: "below", label: "跌破 -40%", align: "right", sort: (r) => r.below ?? "9", render: (r) => num(r.below ? md(r.below) : "—", r.below ? "text-[#f05252]" : "text-[#8b97ab]") },
    { key: "due", label: "預估停損期限", align: "right", sort: (r) => r.due ?? "9", render: (r) => r.due
      ? num(`${md(r.due)}${r.due <= today ? "（已到）" : ""}`, r.due <= today ? "text-[#f05252] font-semibold" : "text-[#f59e0b]") : num("—", "text-[#8b97ab]") },
    { key: "stop", label: "-40% 價", align: "right", sort: (r) => r.stop, render: (r) => num(r.stop.toLocaleString()) },
    { key: "close", label: "收盤", align: "right", sort: (r) => r.close, render: (r) => num(r.close.toLocaleString()) },
    { key: "cost", label: "平均成本", align: "right", sort: (r) => r.cost, render: (r) => num(r.cost.toLocaleString(), "text-[#8b97ab]") },
    { key: "first", label: "建倉日／價", align: "right", sort: (r) => r.first, render: (r) => num(`${ymd(r.first)}　${r.firstPx.toLocaleString()}`, "text-[#8b97ab] whitespace-nowrap") },
    { key: "w", label: "權重", align: "right", sort: (r) => r.w ?? 0, render: (r) => num(r.w != null ? `${r.w.toFixed(2)}%` : "—") },
    { key: "lots", label: "持股（張）", align: "right", sort: (r) => r.lots, render: (r) => num(r.lots.toLocaleString()) },
    { key: "c1", label: "最新增減", align: "right", sort: (r) => r.c1 ?? 0, render: (r) => num(r.c1 ? sign(r.c1) : "—", tone(r.c1)) },
    { key: "c5", label: "5 日增減", align: "right", sort: (r) => r.c5 ?? 0, render: (r) => num(r.c5 ? sign(r.c5) : "—", tone(r.c5)) },
    { key: "c20", label: "20 日增減", align: "right", sort: (r) => r.c20 ?? 0, render: (r) => num(r.c20 ? sign(r.c20) : "—", tone(r.c20)) },
    { key: "val", label: "市值（億）", align: "right", sort: (r) => r.val, render: (r) => num(r.val.toFixed(1)) },
  ];
  const undated = data.etfs.filter((e) => !e.dated);

  return (
    <div>
      <KpiRow>
        <Kpi label={`DD ≤ -40%（${md(data.date)}）`} value={data.count.stop} unit="個部位" color="text-[#f05252]" sub="可能陸續停損" />
        <Kpi label="DD -30% ～ -40%" value={data.count.warn} unit="個部位" color="text-[#f59e0b]" sub="接近停損線" />
        <Kpi label="受影響個股" value={data.count.stocks} unit="檔" color="text-white" sub="至少一檔 ETF 的 DD ≤ -30%" />
        <Kpi label="追蹤主動式 ETF" value={data.etfs.length} unit="檔" color="text-white" sub={`${data.rows.length} 個台股部位`} />
      </KpiRow>

      {(() => {
        const sells = (data.sells ?? []).filter((x) => x.asof === data.asof);
        return (
          <section className="mb-6 rounded-xl border border-[#f05252]/25 bg-[#f05252]/[0.04] p-4">
            <div className="flex flex-wrap items-baseline gap-2 mb-2">
              <h3 className="text-sm font-semibold text-white">最新一天疑似停損賣出</h3>
              <span className="text-[11px] text-[#8b97ab]">
                {data.asof ? md(data.asof) : "—"} 的持股{sells[0]?.prev ? `對比 ${md(sells[0].prev)}` : ""}・DD ≤ -30% 又減碼 ≥ 50 張或整個出清（扣除整檔贖回的等比例減少）
              </span>
            </div>
            {!sells.length ? <p className="text-xs text-[#7c8aa0]">{data.asof ? md(data.asof) : "最新一天"} 沒有疑似停損賣出的部位</p> : (
              <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                {sells.map((x) => (
                  <div key={x.etf + x.code} className="flex items-center justify-between gap-2 rounded-md bg-[#0d1220] px-3 py-2 text-[13px]">
                    <span className="min-w-0 truncate">
                      <span className="font-mono text-[#f59e0b]">{x.etf}</span>
                      <span className="ml-2 text-slate-200">{x.name}</span><span className="ml-1 font-mono text-[11px] text-[#7c8aa0]">{x.code}</span>
                    </span>
                    <span className="shrink-0 font-mono text-xs">
                      <span className="text-[#22c55e]">{x.out ? "出清" : `${x.c1.toLocaleString()} 張`}</span>
                      <span className={`ml-2 ${ddColor(x.dd)}`}>{x.dd.toFixed(0)}%</span>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        );
      })()}

      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <Pills<View> value={view} onChange={setView} options={[{ value: "stock", label: "個股彙總" }, { value: "pos", label: "各 ETF 部位" }]} />
        {view === "pos" && (
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <select value={etf} onChange={(e) => setEtf(e.target.value)} className="rounded border border-[#243247] bg-[#0d1220] px-2 py-1 text-slate-200">
              <option value="all">全部主動式 ETF</option>
              {data.etfs.map((e) => <option key={e.code} value={e.code}>{e.code} {e.name}</option>)}
            </select>
            <label className="flex items-center gap-1 text-[#8b97ab]"><input type="checkbox" checked={minW} onChange={(e) => setMinW(e.target.checked)} />隱藏 50 張以下零星部位</label>
          </div>
        )}
      </div>
      {view === "stock"
        ? <SortTable<Stock> rows={data.stocks} columns={sCols} rowKey={(r) => r.code} initialSort={{ key: "warn", desc: true }} limit={100} />
        : <SortTable<Row> rows={rows} columns={pCols} rowKey={(r) => `${r.etf}-${r.code}`} initialSort={{ key: "dd", desc: false }} limit={150} />}

      <Note>
        建倉成本：逐日抓每檔主動式 ETF 從掛牌起的持股，股數增加的部分以當天收盤價買進、和原部位加權平均；股數減少以平均成本出場（成本不變），減到 0 之後再買進算新的建倉。
        DD＝收盤 ÷ 平均成本 − 1；-40% 價＝平均成本 × 0.6。投信對單一持股虧損多半有停損或檢討機制，DD 接近 -40% 的部位可能陸續被賣出，同一檔股票被越多檔 ETF 套住，賣壓越集中。
        個股彙總不含 50 張以下的零星部位。「占當日成交」＝DD ≤ -30% 的部位合計張數 ÷ 當天成交量，越高代表停損賣壓相對越重。
        {undated.length > 0 && <>標 * 的 ETF（{undated.map((e) => e.code).join("、")}）投信網站查不到歷史持股，成本只能從 {undated[0].start} 開始抓資料那天的價位起算，DD 會偏小。</>}
        成本是用收盤價推估，和基金實際成交價、配股配息會有差異；各投信的停損規則不公開，-40% 只是常見的參考線。
      </Note>
    </div>
  );
}
