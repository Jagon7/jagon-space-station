"use client";

import { useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Row = { code: string; name: string; mk: string; open: number; close: number; ret: number | null; lots: number; valueYi: number; turnover: number; disposed?: boolean };
type Stat = { group: string; n: number; days: number; black: number; o2c: number; c2c: number; gap: number; shortNet: number; shortNetDisc: number; dayWin: number };
type Pick = { code: string; name: string; turnover: number; ret: number | null; o2c: number; black: boolean; gap: number };
type Data = {
  asof: string; next: string; updatedAt: string; from: string; costFull: number; costDisc: number;
  today: Row[]; count: number; stats: Stat[]; deciles: Stat[]; history: { date: string; next: string; picks: Pick[] }[];
};
type View = "today" | "backtest" | "history";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const num = (v: number | string, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;

export default function TurnoverDashboard() {
  const { data, error } = useStaticJson<Data>("turnover.json");
  const wl = useWatchlist();
  const [view, setView] = useState<View>("today");
  const [day, setDay] = useState(0);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const all = data.stats.find((s) => s.group === "全部股票");
  const top = data.stats.find((s) => s.group === "前 20 名");
  const star = (c: string) => (
    <button onClick={(e) => { e.stopPropagation(); wl.toggle(c); }} className={`mr-1.5 ${wl.has(c) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
  );
  const stock = (code: string, name: string, mk?: string) => (
    <span className="whitespace-nowrap">{star(code)}<span className="text-slate-200">{name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{code}</span>
      {mk === "上櫃" && <span className="ml-1 text-[10px] text-[#7c8aa0]">櫃</span>}</span>
  );

  const cToday: Column<Row>[] = [
    { key: "name", label: "股票", render: (r) => <>{stock(r.code, r.name, r.mk)}{r.disposed && <span className="ml-1.5 text-[10px] text-[#f59e0b]">處置</span>}</> },
    { key: "turnover", label: "週轉率", align: "right", sort: (r) => r.turnover, render: (r) => num(`${r.turnover.toFixed(2)}%`, "text-[#f59e0b]") },
    { key: "close", label: "收盤", align: "right", sort: (r) => r.close, render: (r) => num(r.close) },
    { key: "ret", label: "漲跌幅", align: "right", sort: (r) => r.ret, render: (r) => num(pct(r.ret), tone(r.ret)) },
    { key: "k", label: "當日 K 棒", align: "right", sort: (r) => (r.close - r.open) / r.open, render: (r) => num(r.close > r.open ? "紅" : r.close < r.open ? "黑" : "平", tone(r.close - r.open)) },
    { key: "lots", label: "成交張數", align: "right", sort: (r) => r.lots, render: (r) => num(r.lots.toLocaleString()) },
    { key: "valueYi", label: "成交金額（億）", align: "right", sort: (r) => r.valueYi, render: (r) => num(r.valueYi) },
  ];
  const cStat: Column<Stat>[] = [
    { key: "group", label: "分組（依前一天週轉率）", render: (s) => <span className="text-slate-200 whitespace-pre">{s.group}</span> },
    { key: "n", label: "樣本", align: "right", render: (s) => num(s.n.toLocaleString()) },
    { key: "black", label: "隔日黑K率", align: "right", render: (s) => num(`${s.black}%`, all && s.black > all.black ? "text-[#22c55e]" : "text-slate-300") },
    { key: "gap", label: "開盤跳空", align: "right", render: (s) => num(pct(s.gap), tone(s.gap)) },
    { key: "o2c", label: "開→收", align: "right", render: (s) => num(pct(s.o2c), tone(s.o2c)) },
    { key: "c2c", label: "收→收", align: "right", render: (s) => num(pct(s.c2c), tone(s.c2c)) },
    { key: "short", label: "開盤空收盤補（全額／2.8 折）", align: "right", render: (s) => <span className="font-mono whitespace-nowrap"><span className={tone(s.shortNet)}>{pct(s.shortNet)}</span><span className="text-[#475569]">／</span><span className={tone(s.shortNetDisc)}>{pct(s.shortNetDisc)}</span></span> },
    { key: "dayWin", label: "組合開→收為負的天數", align: "right", render: (s) => num(`${s.dayWin}%`) },
  ];
  const h = data.history[day];
  const cHist: Column<Pick>[] = [
    { key: "name", label: "股票", render: (p) => stock(p.code, p.name) },
    { key: "turnover", label: "週轉率", align: "right", sort: (p) => p.turnover, render: (p) => num(`${p.turnover.toFixed(2)}%`, "text-[#f59e0b]") },
    { key: "ret", label: "當天漲跌", align: "right", sort: (p) => p.ret, render: (p) => num(pct(p.ret), tone(p.ret)) },
    { key: "gap", label: "隔天開盤", align: "right", sort: (p) => p.gap, render: (p) => num(pct(p.gap), tone(p.gap)) },
    { key: "o2c", label: "隔天開→收", align: "right", sort: (p) => p.o2c, render: (p) => num(pct(p.o2c), tone(p.o2c)) },
    { key: "black", label: "隔天", align: "right", sort: (p) => (p.black ? 1 : 0), render: (p) => num(p.black ? "黑K" : "紅／平", p.black ? "text-[#22c55e]" : "text-[#f05252]") },
  ];
  const hAvg = h ? h.picks.reduce((s, p) => s + p.o2c, 0) / (h.picks.length || 1) : null;
  const maxAbs = Math.max(...data.deciles.map((d) => Math.abs(d.o2c)), 0.01);

  return (
    <div>
      <KpiRow>
        <Kpi label={`${md(data.asof)} 週轉率最高`} value={data.today[0] ? `${data.today[0].turnover.toFixed(1)}%` : "—"} sub={data.today[0]?.name} color="text-[#f59e0b]" />
        <Kpi label="前 20 名隔日黑K率" value={top ? `${top.black}%` : "—"} sub={all ? `全市場 ${all.black}%` : undefined} color="text-[#22c55e]" />
        <Kpi label="前 20 名隔日開→收" value={top ? pct(top.o2c) : "—"} sub={all ? `全市場 ${pct(all.o2c)}` : undefined} color={tone(top?.o2c)} />
        <Kpi label="開盤放空、收盤回補（扣全額成本）" value={top ? pct(top.shortNet) : "—"} sub={top ? `手續費 2.8 折 ${pct(top.shortNetDisc)}` : undefined} color={tone(top?.shortNet)} />
      </KpiRow>
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <Pills<View> value={view} onChange={setView} options={[{ value: "today", label: `${md(data.asof)} 排行` }, { value: "backtest", label: "回測" }, { value: "history", label: "近期紀錄" }]} />
        <span className="text-[11px] text-[#7c8aa0]">週轉率＝成交股數 ÷ 已發行股數；每天收盤後更新</span>
      </div>

      {view === "today" && (data.today.length
        ? <SortTable<Row> rows={data.today} columns={cToday} rowKey={(r) => r.code} initialSort={{ key: "turnover", desc: true }} rank limit={100} />
        : <Empty>沒有資料。</Empty>)}

      {view === "backtest" && (
        <div className="space-y-6">
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
            <h3 className="text-sm text-white font-semibold mb-1">十分位：週轉率越高，隔天越容易開高走低</h3>
            <p className="text-xs text-[#8b97ab] mb-4">每天把所有股票依週轉率分成 10 組（第 1 組最高），看隔天的開盤到收盤報酬與黑K率。</p>
            <div className="space-y-1.5">
              {data.deciles.map((d, i) => (
                <div key={d.group} className="grid grid-cols-[3.5rem_1fr_4.5rem_4rem] items-center gap-2 text-xs">
                  <span className="text-[#8b97ab]">{i === 0 ? "最高" : i === 9 ? "最低" : `第 ${i + 1} 組`}</span>
                  <div className="relative h-4">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-[#243247]" />
                    <div className={`absolute inset-y-0.5 rounded-sm ${d.o2c < 0 ? "bg-[#22c55e]/70 right-1/2" : "bg-[#f05252]/70 left-1/2"}`} style={{ width: `${(Math.abs(d.o2c) / maxAbs) * 50}%` }} />
                  </div>
                  <span className={`font-mono text-right ${tone(d.o2c)}`}>{pct(d.o2c)}</span>
                  <span className="font-mono text-right text-slate-300">{d.black}%</span>
                </div>
              ))}
              <div className="grid grid-cols-[3.5rem_1fr_4.5rem_4rem] gap-2 text-[10px] text-[#7c8aa0]"><span /><span className="text-center">隔天開→收</span><span className="text-right">開→收</span><span className="text-right">黑K率</span></div>
            </div>
          </section>
          <SortTable<Stat> rows={data.stats} columns={cStat} rowKey={(s) => s.group} />
          <SortTable<Stat> rows={data.deciles} columns={cStat} rowKey={(s) => s.group} />
          <section className="rounded-xl border border-[#243247] bg-[#0d1220] p-5 text-[13px] leading-relaxed text-slate-300 space-y-2">
            <h3 className="text-sm text-white font-semibold">怎麼看</h3>
            <p>黑K率：隔天收盤低於開盤的比例（平盤不算黑K）。開→收：隔天從開盤到收盤的平均漲跌，負值越大越適合「開盤放空、收盤回補」。收→收：前一天收盤買進抱到隔天收盤的報酬。</p>
            <p>開盤空收盤補的淨報酬＝−(開→收) − 交易成本。全額成本 {data.costFull}%（當沖證交稅 0.15%＋手續費 0.1425%×2），2.8 折手續費約 {data.costDisc}%。</p>
            <p>高週轉股隔天平均「開高」（跳空為正）、盤中再走低，所以收→收不一定是負的；這個效果主要在開盤到收盤這一段。「全部股票」那一列是同期全市場的基準，回測期間大盤本身也偏開高走低，請比較兩者的差距。</p>
          </section>
        </div>
      )}

      {view === "history" && (data.history.length ? (
        <>
          <div className="flex gap-1.5 flex-wrap mb-3">
            {data.history.map((x, i) => (
              <button key={x.date} onClick={() => setDay(i)} className={`px-2.5 py-1 rounded-md text-xs font-mono ${i === day ? "bg-[#4f8cff] text-white" : "bg-[#141c2e] text-[#8b97ab] hover:text-slate-200"}`}>{md(x.date)}</button>
            ))}
          </div>
          {h && <p className="text-xs text-[#8b97ab] mb-2">{md(h.date)} 週轉率前 20 名（成交 ≥ 1 億），{md(h.next)} 的表現：平均開→收 <span className={`font-mono ${tone(hAvg)}`}>{pct(hAvg)}</span>，收黑 {h.picks.filter((p) => p.black).length}/{h.picks.length} 檔</p>}
          {h && <SortTable<Pick> rows={h.picks} columns={cHist} rowKey={(p) => p.code} initialSort={{ key: "turnover", desc: true }} rank />}
        </>
      ) : <Empty>還沒有紀錄。</Empty>)}

      <Note>
        回測期間 {data.from} 起（本站行情資料），樣本只有約半年，結論可能隨行情改變。週轉率用最新發行股數回算歷史，期間有增減資的股票會有小誤差；已排除 ETF 與隔天處置中的股票。
        開盤價、收盤價用每日行情的開收盤，實際成交會有滑價；放空需有信用帳戶或當沖資格，平盤以下放空有限制。
      </Note>
    </div>
  );
}
