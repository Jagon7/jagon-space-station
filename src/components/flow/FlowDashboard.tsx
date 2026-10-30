"use client";

import { useEffect, useState } from "react";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

export type Sector = { name: string; net: number; out: number; in: number; amt: number; n: number; slices: number[] };
export type Stock = { code: string; name: string; sector: string; close: number | null; chg: number; amt: number; out: number; in: number; net: number };
export type Flow = { updatedAt: string; date: string; status: "pre" | "live" | "closed"; n: number; cover: number | null; sliceMin: number; slices: string[];
  total: { net: number; out: number; in: number }; sectors: Sector[]; stocks: Stock[] };
type View = "sector" | "slice" | "stock";

// 盤中資料放在 repo 的 live 分支（每分鐘覆蓋）。raw.githubusercontent 會快取 5 分鐘，改讀 GitHub API（快取 60 秒）；
// 未登入每個 IP 每小時 60 次，所以每 90 秒讀一次；API 被限流時退回 raw
const API = "https://api.github.com/repos/Jagon7/jagon-space-station/contents/flow.json?ref=live";
const RAW = "https://raw.githubusercontent.com/Jagon7/jagon-space-station/live/flow.json";
/** 讀盤中資金流，每 90 秒自動更新（首頁卡片與 /flow 頁共用） */
export function useFlow() {
  const [data, setData] = useState<Flow | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let stop = false;
    const load = () => fetch(API, { headers: { Accept: "application/vnd.github.raw+json" }, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : fetch(RAW, { cache: "no-store" }).then((x) => (x.ok ? x.json() : Promise.reject()))))
      .then((d: Flow) => { if (!stop) { setData(d); setErr(false); } })
      .catch(() => { if (!stop) setErr(true); });
    load();
    const id = setInterval(load, 90000);
    return () => { stop = true; clearInterval(id); };
  }, []);
  return { data, err };
}

const yi = (v: number, d = 1) => `${v > 0 ? "+" : ""}${v.toFixed(d)} 億`;
const tone = (v: number) => (v > 0 ? "text-[#f05252]" : v < 0 ? "text-[#22c55e]" : "text-[#8b97ab]");
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;

export function Bar({ v, max }: { v: number; max: number }) {
  const w = max ? Math.min(Math.abs(v) / max, 1) * 50 : 0;
  return (
    <div className="relative h-3 w-full rounded bg-[#141c2e]">
      <div className="absolute top-0 h-3 w-px bg-[#475569]" style={{ left: "50%" }} />
      <div className={`absolute top-0 h-3 rounded ${v >= 0 ? "bg-[#f05252]/70" : "bg-[#22c55e]/70"}`} style={v >= 0 ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }} />
    </div>
  );
}

export default function FlowDashboard() {
  const { data, err } = useFlow();
  const [view, setView] = useState<View>("sector");
  const [pick, setPick] = useState<string | null>(null);
  const wl = useWatchlist();
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{err ? "還沒有資料（盤中資金流在交易日 09:00 後開始更新）" : "載入中…"}</div>;
  const t = new Date(data.updatedAt);
  const hm = t.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Taipei" });
  const secs = data.sectors.filter((s) => s.amt > 0);
  const maxNet = Math.max(...secs.map((s) => Math.abs(s.net)), 1);
  const top = secs[0], bottom = secs[secs.length - 1];
  const stocks = pick ? data.stocks.filter((s) => s.sector === pick) : data.stocks;
  const maxSlice = Math.max(...secs.flatMap((s) => s.slices.map(Math.abs)), 1);
  const status = data.status === "live" ? <span className="text-[#22c55e]">● 盤中更新中</span> : data.status === "pre" ? "盤前" : "已收盤";

  const cSec: Column<Sector>[] = [
    { key: "name", label: "產業", render: (s) => <button onClick={() => { setPick(s.name); setView("stock"); }} className="text-slate-200 hover:text-[#4f8cff]">{s.name}<span className="ml-1.5 text-[10px] text-[#7c8aa0]">{s.n} 檔</span></button> },
    { key: "bar", label: "主動買賣淨額", render: (s) => <div className="w-48"><Bar v={s.net} max={maxNet} /></div> },
    { key: "net", label: "淨額", align: "right", sort: (s) => s.net, render: (s) => num(yi(s.net), tone(s.net)) },
    { key: "out", label: "外盤（主動買）", align: "right", sort: (s) => s.out, render: (s) => num(s.out.toFixed(1)) },
    { key: "in", label: "內盤（主動賣）", align: "right", sort: (s) => s.in, render: (s) => num(s.in.toFixed(1)) },
    { key: "amt", label: "成交（億）", align: "right", sort: (s) => s.amt, render: (s) => num(s.amt.toFixed(0), "text-[#8b97ab]") },
    { key: "ratio", label: "淨額／成交", align: "right", sort: (s) => (s.amt ? s.net / s.amt : 0), render: (s) => num(s.amt ? `${((s.net / s.amt) * 100).toFixed(1)}%` : "—", tone(s.net)) },
  ];
  const cStk: Column<Stock>[] = [
    { key: "name", label: "股票", render: (s) => (
      <span className="whitespace-nowrap">
        <button onClick={() => wl.toggle(s.code)} className={`mr-1.5 ${wl.has(s.code) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
        <span className="text-slate-200">{s.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{s.code}</span>
      </span>) },
    { key: "sector", label: "產業", render: (s) => <span className="text-xs text-slate-400">{s.sector}</span> },
    { key: "close", label: "成交", align: "right", sort: (s) => s.close, render: (s) => num(s.close ?? "—") },
    { key: "chg", label: "漲跌", align: "right", sort: (s) => s.chg, render: (s) => num(`${s.chg > 0 ? "+" : ""}${s.chg.toFixed(2)}%`, tone(s.chg)) },
    { key: "net", label: "主動買賣淨額", align: "right", sort: (s) => s.net, render: (s) => num(yi(s.net, 2), tone(s.net)) },
    { key: "out", label: "外盤", align: "right", sort: (s) => s.out, render: (s) => num(s.out.toFixed(2)) },
    { key: "in", label: "內盤", align: "right", sort: (s) => s.in, render: (s) => num(s.in.toFixed(2)) },
    { key: "amt", label: "成交（億）", align: "right", sort: (s) => s.amt, render: (s) => num(s.amt.toFixed(1), "text-[#8b97ab]") },
  ];

  return (
    <div>
      <KpiRow>
        <Kpi label={`${data.date.slice(5).replace("-", "/")}・${hm} 更新`} value={<span className="text-base">{status}</span>} sub={`${data.n} 檔・涵蓋市場成交約 ${data.cover ?? "—"}%`} />
        <Kpi label="全部主動買賣淨額" value={yi(data.total.net)} color={tone(data.total.net)} sub={`外盤 ${data.total.out.toFixed(0)}・內盤 ${data.total.in.toFixed(0)} 億`} />
        <Kpi label="資金流入最多" value={top ? yi(top.net) : "—"} color={tone(top?.net ?? 0)} sub={top?.name} />
        <Kpi label="資金流出最多" value={bottom ? yi(bottom.net) : "—"} color={tone(bottom?.net ?? 0)} sub={bottom?.name} />
      </KpiRow>

      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <Pills<View> value={view} onChange={(v) => { setView(v); if (v !== "stock") setPick(null); }} options={[
          { value: "sector", label: "產業排行" }, { value: "slice", label: `每 ${data.sliceMin} 分鐘` }, { value: "stock", label: pick ? `${pick} 個股` : "個股" }]} />
        {pick && <button onClick={() => setPick(null)} className="text-xs text-[#4f8cff] hover:underline">看全部個股</button>}
      </div>

      {view === "sector" && (secs.length ? <SortTable<Sector> rows={secs} columns={cSec} rowKey={(s) => s.name} initialSort={{ key: "net", desc: true }} />
        : <Empty>還沒有成交資料。</Empty>)}

      {view === "slice" && (data.slices.length ? (
        <div className="overflow-x-auto rounded-xl border border-[#243247] bg-[#0d1220]">
          <table className="w-full text-[12px] font-mono">
            <thead><tr className="text-[#8b97ab] text-[11px]">
              <th className="text-left font-normal px-3 py-2 sticky left-0 bg-[#0d1220]">產業</th>
              {data.slices.map((l) => <th key={l} className="font-normal px-2 py-2 text-right whitespace-nowrap">{l}</th>)}
              <th className="font-normal px-3 py-2 text-right">合計</th>
            </tr></thead>
            <tbody>
              {secs.map((s) => (
                <tr key={s.name} className="border-t border-[#1c2738]">
                  <td className="px-3 py-1.5 text-slate-200 whitespace-nowrap sticky left-0 bg-[#0d1220]">{s.name}</td>
                  {s.slices.map((v, i) => {
                    const a = Math.min(Math.abs(v) / maxSlice, 1);
                    return <td key={i} className="px-2 text-right" style={{ background: v > 0 ? `rgba(240,82,82,${a * 0.45})` : v < 0 ? `rgba(34,197,94,${a * 0.45})` : undefined }}>
                      <span className={Math.abs(v) < 0.05 ? "text-[#475569]" : "text-slate-200"}>{v.toFixed(1)}</span></td>;
                  })}
                  <td className={`px-3 text-right ${tone(s.net)}`}>{s.net.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <Empty>第一個 {data.sliceMin} 分鐘切片還沒結束。</Empty>)}

      {view === "stock" && <SortTable<Stock> rows={stocks} columns={cStk} rowKey={(s) => s.code} initialSort={{ key: "net", desc: true }} limit={pick ? undefined : 60} />}

      <Note>
        主動買賣淨額＝外盤成交金額（成交在賣價，買方主動）− 內盤成交金額（成交在買價，賣方主動），單位億元。紅色＝資金主動流入、綠色＝主動流出。
        每 {data.sliceMin} 分鐘切片是該時段內新增的淨額；網頁每 90 秒自動更新。只看前一日成交金額前 200 大，冷門股不在內。
      </Note>
    </div>
  );
}
