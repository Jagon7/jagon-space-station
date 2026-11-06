"use client";

import { useMemo, useState } from "react";
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, Legend } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Row = { code: string; name: string; mk: string; etf: boolean; close: number; maint: number; call: number; dist: number; cost: number; pnl: number;
  bal: number; dm20: number; amt: number; aval: number; chg20: number | null; hot: boolean; tag: string | null; below?: string | null; force?: string | null };
type Data = { updatedAt: string; date: string; seed: boolean; start: string; k?: { tw: number; otc: number }; market: { tw: number | null; otc: number | null; series: [string, number | null, number | null][] };
  count: { below: number; near: number; hot: number }; rows: Row[] };
type Scope = "hot" | "all" | "etf";

const CALL = 130;
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const mColor = (m: number) => (m < CALL ? "text-[#f05252] font-semibold" : m < 145 ? "text-[#f59e0b] font-semibold" : m < 166 ? "text-slate-200" : "text-[#8b97ab]");
const TAG: Record<string, string> = { 斷頭: "bg-[#f05252]/15 text-[#f05252]", 攤平: "bg-[#f59e0b]/15 text-[#f59e0b]", 追價: "bg-[#4f8cff]/15 text-[#4f8cff]",
  洗籌: "bg-[#22c55e]/15 text-[#22c55e]", 減碼: "bg-[#475569]/30 text-[#8b97ab]" };
const ax = { tick: { fill: "#7c8aa0", fontSize: 11 }, stroke: "#334155" };
const drop = (m: number | null) => (m ? `${((1 - CALL / m) * 100).toFixed(1)}%` : "—");

export default function MarginDashboard() {
  const { data, error } = useStaticJson<Data>("margin.json");
  const wl = useWatchlist();
  const [scope, setScope] = useState<Scope>("hot");
  const [range, setRange] = useState<"1y" | "all">("1y");
  const rows = useMemo(() => (data?.rows ?? []).filter((r) => (scope === "etf" ? r.etf : !r.etf && (scope === "all" || r.hot))), [data, scope]);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const series = data.market.series.slice(range === "1y" ? -250 : 0).map(([d, tw, otc]) => ({ d, tw, otc }));
  const lows = (k: 1 | 2) => data.market.series.reduce<[string, number] | null>((a, r) => (r[k] != null && (!a || (r[k] as number) < a[1]) ? [r[0], r[k] as number] : a), null);
  const lowTw = lows(1), lowOtc = lows(2);
  const today = data.updatedAt.slice(0, 10);
  const cols: Column<Row>[] = [
    { key: "name", label: "股票", render: (r) => (
      <span className="whitespace-nowrap">
        <button onClick={() => wl.toggle(r.code)} className={`mr-1.5 ${wl.has(r.code) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
        <span className="text-slate-200">{r.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{r.code}</span>
        {r.mk === "上櫃" && <span className="ml-1 text-[10px] text-[#7c8aa0]">櫃</span>}
      </span>) },
    { key: "maint", label: "推估維持率", align: "right", sort: (r) => r.maint, render: (r) => num(`${r.maint.toFixed(0)}%`, mColor(r.maint)) },
    { key: "dist", label: "距追繳", align: "right", sort: (r) => -r.dist, render: (r) => r.dist >= 0
      ? <span className="font-mono text-[#f05252] whitespace-nowrap">已低於 {r.call.toLocaleString()}</span>
      : num(`再跌 ${(-r.dist).toFixed(1)}%`, -r.dist < 10 ? "text-[#f59e0b]" : "text-slate-300") },
    { key: "below", label: "跌破 130%", align: "right", sort: (r) => r.below ?? "9", render: (r) => num(r.below ? md(r.below) : "—", r.below ? "text-[#f05252]" : "text-[#8b97ab]") },
    { key: "force", label: "預計斷頭日", align: "right", sort: (r) => r.force ?? "9", render: (r) => r.force
      ? num(`${md(r.force)}${r.force <= today ? "（已到）" : ""}`, r.force <= today ? "text-[#f05252] font-semibold" : "text-[#f59e0b]") : num("—", "text-[#8b97ab]") },
    { key: "call", label: "追繳價", align: "right", sort: (r) => r.call, render: (r) => num(r.call.toLocaleString()) },
    { key: "close", label: "收盤", align: "right", sort: (r) => r.close, render: (r) => num(r.close.toLocaleString()) },
    { key: "cost", label: "推估融資成本", align: "right", sort: (r) => r.cost, render: (r) => num(r.cost.toLocaleString(), "text-[#8b97ab]") },
    { key: "pnl", label: "融資戶損益", align: "right", sort: (r) => r.pnl, render: (r) => num(`${r.pnl > 0 ? "+" : ""}${r.pnl.toFixed(1)}%`, tone(r.pnl)) },
    { key: "bal", label: "融資（張）", align: "right", sort: (r) => r.bal, render: (r) => num(r.bal.toLocaleString()) },
    { key: "dm20", label: "20 日增減", align: "right", sort: (r) => r.dm20, render: (r) => num(`${r.dm20 > 0 ? "+" : ""}${r.dm20.toLocaleString()}`, tone(r.dm20)) },
    { key: "amt", label: "融資市值（億）", align: "right", sort: (r) => r.amt, render: (r) => num(r.amt.toFixed(1)) },
    { key: "aval", label: "20 日均成交（億）", align: "right", sort: (r) => r.aval, render: (r) => num(r.aval.toFixed(1), "text-[#8b97ab]") },
    { key: "chg20", label: "近 20 日", align: "right", sort: (r) => r.chg20, render: (r) => num(r.chg20 == null ? "—" : `${r.chg20 > 0 ? "+" : ""}${r.chg20.toFixed(1)}%`, tone(r.chg20)) },
    { key: "tag", label: "判讀", render: (r) => (r.tag ? <span className={`rounded px-1.5 py-0.5 text-[10px] ${TAG[r.tag] ?? ""}`}>{r.tag}</span> : null) },
  ];

  return (
    <div>
      {!data.seed && (
        <div className="mb-4 rounded-lg border border-[#f59e0b]/30 bg-[#f59e0b]/[0.06] p-3 text-xs text-[#fcd34d]">
          長期融資成本還在回補中，目前只用 {md(data.start)} 以後的資料推估，成本偏向近期價位、維持率會偏低；回補完成後會自動改用 2021 年底起的完整重播。
        </div>
      )}
      <KpiRow>
        <Kpi label={`上市融資維持率（${md(data.date)}）`} value={data.market.tw != null ? `${data.market.tw}%` : "—"} color={data.market.tw != null && data.market.tw < 150 ? "text-[#f59e0b]" : "text-white"} sub={`再跌 ${drop(data.market.tw)} 到 130%`} />
        <Kpi label="上櫃融資維持率" value={data.market.otc != null ? `${data.market.otc}%` : "—"} color={data.market.otc != null && data.market.otc < 150 ? "text-[#f59e0b]" : "text-white"} sub={`再跌 ${drop(data.market.otc)} 到 130%`} />
        <Kpi label="熱門股已低於 130%" value={data.count.below} unit="檔" color="text-[#f05252]" sub={`共 ${data.count.hot} 檔熱門股`} />
        <Kpi label="熱門股 130～145%" value={data.count.near} unit="檔" color="text-[#f59e0b]" sub="接近追繳線" />
      </KpiRow>

      <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h3 className="text-sm font-semibold text-white">大盤融資維持率</h3>
          <Pills<"1y" | "all"> value={range} onChange={setRange} options={[{ value: "1y", label: "近一年" }, { value: "all", label: `全部（${data.market.series[0] ? data.market.series[0][0].slice(0, 7) : ""} 起）` }]} />
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
            <CartesianGrid stroke="#1c2738" vertical={false} />
            <XAxis dataKey="d" tickFormatter={(d: string) => (range === "all" ? d.slice(2, 7).replace("-", "/") : md(d))} {...ax} minTickGap={28} />
            <YAxis domain={[(lo: number) => Math.min(120, Math.floor(lo / 10) * 10), (hi: number) => Math.ceil(hi / 10) * 10]} {...ax} unit="%" />
            <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #243247", fontSize: 12 }} formatter={(v, n) => [`${v}%`, n === "tw" ? "上市" : "上櫃"]} labelFormatter={(d) => String(d)} />
            <Legend formatter={(v) => (v === "tw" ? "上市" : "上櫃")} wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine y={CALL} stroke="#f05252" strokeDasharray="4 4" label={{ value: "130% 追繳線", fill: "#f05252", fontSize: 11, position: "insideBottomRight" }} />
            <Line dataKey="tw" stroke="#4f8cff" dot={false} strokeWidth={1.6} connectNulls />
            <Line dataKey="otc" stroke="#f59e0b" dot={false} strokeWidth={1.6} connectNulls />
          </LineChart>
        </ResponsiveContainer>
        <p className="mt-2 text-[11px] text-[#7c8aa0]">
          {lowTw && <>期間最低：上市 {lowTw[1]}%（{lowTw[0]}）</>}{lowOtc && <>、上櫃 {lowOtc[1]}%（{lowOtc[0]}）</>}。
          大盤維持率 ＝ 全部融資股票的融資市值 ÷ 融資借款；剛用融資買進時約 166%（上市 6 成融資），跌破 130% 券商發追繳、兩天內沒補就可能被斷頭賣出。
        </p>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <Pills<Scope> value={scope} onChange={setScope} options={[
          { value: "hot", label: `熱門股（${data.count.hot}）` }, { value: "all", label: "全部個股" }, { value: "etf", label: "ETF" }]} />
        <span className="text-[11px] text-[#7c8aa0]">熱門股＝20 日均成交值 ≥ 5 億、融資 ≥ 100 張；預設依推估維持率由低到高</span>
      </div>
      <SortTable<Row> rows={rows} columns={cols} rowKey={(r) => r.code} initialSort={{ key: "maint", desc: false }} limit={100} />

      <Note>
        推估融資成本：從 {data.start} 起逐日重播融資買進（以當天均價加入）、融資賣出與現金償還（依平均成本出場），除權、減資時成本跟著調整。
        推估維持率＝收盤 ÷（成本 × 融資成數），上市 6 成、上櫃 5 成；追繳價＝維持率剛好 130% 的股價。
        大盤融資維持率＝全體融資餘額市值（含 ETF）÷ 證交所、櫃買中心公布的融資金額。個股成本再乘上校正係數（官方融資金額 ÷ 推估借款合計{data.k ? `，目前上市 ${data.k.tw}、上櫃 ${data.k.otc}` : ""}），讓個股加總和官方借款一致。
        跌破 130%＝收盤連續低於追繳價的第一天（以目前推估成本回推）；券商隔天發追繳通知、兩個營業日內要補繳，沒補的第 3 個交易日開盤起可處分，所以預計斷頭日＝跌破日之後第 3 個交易日（遇休市順延）。
        判讀依近 20 日融資增減 × 股價漲跌：追價（資增價漲）、攤平（資增價跌）、洗籌（資減價漲）、斷頭（資減價跌且維持率 &lt; 140%）、減碼（其他資減價跌）。
        實際維持率依個別帳戶、整戶擔保品而不同，這裡是全體融資戶的平均推估。
      </Note>
    </div>
  );
}
