"use client";

import { useMemo, useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Row = { code: string; name: string; close: number; disp: boolean; black: boolean; fin?: boolean; dSh: number; dAmt: number; vol10: number; dtr: number;
  turn: number; oi: number; oiBig: number; oiSmall: number; bVal: number; sVal: number; bShare: number | null; sShare: number | null;
  invX: number | null; oiX: number | null; bX: number | null; sX: number | null; basis: number | null; basisSrc: { day: number; settle: number };
  dir: [string, string, string]; same: boolean; ctrl: number; ctrlSh: number; ctrlX: number | null; amihud: number | null };
type Data = { updatedAt: string; date: string; ltDate: string; dtDate?: string | null; month: string; start: string; settle: string; daysLeft: number; days: number;
  basisDays: number; rows: Row[] };
type Preset = "ctrlUp" | "ctrlDown" | "inv" | "oi";

const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const num = (v: React.ReactNode, cls = "text-slate-300") => <span className={`font-mono ${cls}`}>{v}</span>;
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const sg = (v: number, d = 0) => `${v > 0 ? "+" : ""}${v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const x = (v: number | null, d = 2) => (v == null ? "—" : v.toFixed(d));
const pct = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);
const tag = (t: string) => {
  const c = t === "溢" || t === "多" ? "bg-[#f05252]/15 text-[#f05252]" : "bg-[#22c55e]/15 text-[#22c55e]";
  return <span className={`rounded px-1.5 py-0.5 text-[10px] ${c}`}>{t}</span>;
};
const PRESET: Record<Preset, { key: string; desc: boolean }> = {
  ctrlUp: { key: "ctrlX", desc: false }, ctrlDown: { key: "ctrlX", desc: true },
  inv: { key: "invX", desc: true }, oi: { key: "oiX", desc: true },
};

export default function SettlementDashboard() {
  const { data, error } = useStaticJson<Data>("settlement.json");
  const wl = useWatchlist();
  const [preset, setPreset] = useState<Preset>("ctrlUp");
  const [same, setSame] = useState(false);
  const [hideBlack, setHideBlack] = useState(true);
  const [hideDisp, setHideDisp] = useState(false);
  const [hideFin, setHideFin] = useState(true);
  const rows = useMemo(() => (data?.rows ?? []).filter((r) => (!same || r.same) && (!hideBlack || !r.black) && (!hideDisp || !r.disp) && (!hideFin || !r.fin)), [data, same, hideBlack, hideDisp, hideFin]);
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;

  const cols: Column<Row>[] = [
    { key: "name", label: "股票", render: (r) => (
      <span className="whitespace-nowrap">
        <button onClick={() => wl.toggle(r.code)} className={`mr-1.5 ${wl.has(r.code) ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}`}>★</button>
        <span className="text-slate-200">{r.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{r.code}</span>
        {r.disp && <span className="ml-1 rounded bg-[#f59e0b]/15 px-1 text-[10px] text-[#f59e0b]">處置</span>}
        {r.black && <span className="ml-1 rounded bg-[#475569]/30 px-1 text-[10px] text-[#8b97ab]">黑名單</span>}
      </span>) },
    { key: "ctrlX", label: "控盤倍數", align: "right", sort: (r) => r.ctrlX, render: (r) => num(x(r.ctrlX), `font-semibold ${tone(r.ctrlX)}`) },
    { key: "ctrlSh", label: "控盤張數", align: "right", sort: (r) => r.ctrlSh, render: (r) => num(sg(r.ctrlSh), tone(r.ctrlSh)) },
    { key: "ctrl", label: "控盤金額(M)", align: "right", sort: (r) => r.ctrl, render: (r) => num(sg(r.ctrl, 1), tone(r.ctrl)) },
    { key: "same", label: "同向", sort: (r) => (r.same ? 1 : 0), render: (r) => (r.same ? <span className="text-[#4f8cff] font-semibold">v</span> : null) },
    { key: "dir", label: "折溢價／特法／自營", render: (r) => <span className="inline-flex gap-1">{r.dir.map((t, i) => <span key={i}>{tag(t)}</span>)}</span> },
    { key: "basis", label: "平均折溢價", align: "right", sort: (r) => r.basis, render: (r) => (
      <span title={`永豐 1 分 K 整日平均 ${r.basisSrc.day} 天、期交所結算價估 ${r.basisSrc.settle} 天`}>
        {num(r.basis == null ? "—" : `${sg(r.basis * 100, 2)}%`, tone(r.basis))}
        {r.basisSrc.settle > 0 && <span className="ml-0.5 text-[10px] text-[#7c8aa0]">*</span>}
      </span>) },
    { key: "dSh", label: "自營買賣超(張)", align: "right", sort: (r) => r.dSh, render: (r) => num(sg(r.dSh), tone(r.dSh)) },
    { key: "dAmt", label: "自營金額(M)", align: "right", sort: (r) => r.dAmt, render: (r) => num(sg(r.dAmt, 1), tone(r.dAmt)) },
    { key: "turn", label: "換手量(張)", align: "right", sort: (r) => r.turn, render: (r) => num(Math.round(r.turn).toLocaleString()) },
    { key: "invX", label: "自營庫存倍數", align: "right", sort: (r) => r.invX, render: (r) => num(x(r.invX), tone(r.invX)) },
    { key: "oiX", label: "未平倉倍數", align: "right", sort: (r) => r.oiX, render: (r) => num(x(r.oiX)) },
    { key: "bX", label: "特法多倍數", align: "right", sort: (r) => r.bX, render: (r) => num(x(r.bX), "text-[#f05252]") },
    { key: "sX", label: "特法空倍數", align: "right", sort: (r) => r.sX, render: (r) => num(x(r.sX), "text-[#22c55e]") },
    { key: "bVal", label: "特法多價值(M)", align: "right", sort: (r) => r.bVal, render: (r) => num((r.bVal / 1e6).toFixed(1)) },
    { key: "sVal", label: "特法空價值(M)", align: "right", sort: (r) => r.sVal, render: (r) => num((r.sVal / 1e6).toFixed(1)) },
    { key: "bShare", label: "特法多佔比", align: "right", sort: (r) => r.bShare, render: (r) => num(pct(r.bShare), "text-[#8b97ab]") },
    { key: "sShare", label: "特法空佔比", align: "right", sort: (r) => r.sShare, render: (r) => num(pct(r.sShare), "text-[#8b97ab]") },
    { key: "oi", label: "期貨未平倉(大期)", align: "right", sort: (r) => r.oi, render: (r) => (
      <span title={`大期 ${r.oiBig.toLocaleString()} 口、小期 ${r.oiSmall.toLocaleString()} 口（÷20 折算）`}>{num(r.oi.toLocaleString(undefined, { maximumFractionDigits: 1 }))}</span>) },
    { key: "vol10", label: "10 日均量", align: "right", sort: (r) => r.vol10, render: (r) => num(r.vol10.toLocaleString(), "text-[#8b97ab]") },
    { key: "dtr", label: "當沖比", align: "right", sort: (r) => r.dtr, render: (r) => num(`${r.dtr.toFixed(1)}%`, "text-[#8b97ab]") },
    { key: "close", label: "收盤", align: "right", sort: (r) => r.close, render: (r) => num(r.close.toLocaleString()) },
    { key: "amihud", label: "Amihud", align: "right", sort: (r) => r.amihud, render: (r) => num(x(r.amihud), "text-[#8b97ab]") },
  ];
  const toggle = (on: boolean, set: (v: boolean) => void, label: string) => (
    <button onClick={() => set(!on)} className={`rounded-lg border px-3 py-1.5 text-xs ${on ? "border-[#4f8cff] bg-[#4f8cff]/10 text-[#4f8cff]" : "border-[#243247] text-[#8b97ab] hover:text-slate-300"}`}>
      {on ? "✓ " : ""}{label}
    </button>
  );

  return (
    <div>
      <KpiRow>
        <Kpi label={`${data.month.slice(0, 4)}/${data.month.slice(4)} 結算日`} value={md(data.settle)} sub={`本期 ${md(data.start)} 起`} />
        <Kpi label="距結算" value={data.daysLeft} unit="個交易日" color={data.daysLeft <= 1 ? "text-[#f59e0b]" : "text-white"} sub={`資料到 ${md(data.date)}`} />
        <Kpi label="本期已累積" value={data.days} unit="天" sub={`大額交易人 ${md(data.ltDate)}`} />
        <Kpi label="整日平均折溢價" value={`${data.basisDays}/${data.days}`} unit="天" sub="缺的日子用期交所結算價估" />
      </KpiRow>

      {data.dtDate && data.dtDate !== data.date && (
        <div className="mb-4 rounded-lg border border-[#f59e0b]/30 bg-[#f59e0b]/[0.06] p-3 text-xs text-[#fcd34d]">
          {md(data.date)} 的當沖資料還沒公布（證交所／櫃買約晚上 9 點多），換手量暫用 {md(data.dtDate)} 的當沖比計算；每天 22:00 前會更新成當天的。
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Pills<Preset> value={preset} onChange={setPreset} options={[
          { value: "ctrlUp", label: "控盤倍數（往下控）" }, { value: "ctrlDown", label: "控盤倍數（往上拉）" },
          { value: "inv", label: "自營庫存倍數" }, { value: "oi", label: "未平倉倍數" }]} />
        {toggle(same, setSame, "只看同向")}
        {toggle(hideBlack, setHideBlack, "隱藏黑名單")}
        {toggle(hideDisp, setHideDisp, "隱藏處置股")}
        {toggle(hideFin, setHideFin, "排除金融股")}
        <span className="text-xs text-[#7c8aa0]">{rows.length} 檔</span>
      </div>

      <SortTable key={preset} rows={rows} columns={cols} initialSort={PRESET[preset]} rowKey={(r) => r.code} rank limit={50} />

      <div className="mt-6 space-y-1">
        <Note>
          本期＝上次結算隔天到本次結算日（每月第三個星期三，遇休市順延）。自營買賣超＝本期每天自營商買賣超加總；換手量＝近 10 日均量 ×（1 − 當沖比）× 27%（12:30 後的量）。
          未平倉倍數＝（大期 OI ＋ 小期 OI ÷ 20）× 2 ÷ 換手量；特法多／空倍數＝前十大特定法人買／賣方未沖銷價值 ÷ 收盤 ÷ 1000 ÷ 換手量（期交所大額交易人表，即將結算月份）。
        </Note>
        <Note>
          控盤金額＝ −（（特法空方價值 − 特法多方價值）＋ 自營買賣超金額）；控盤倍數＝控盤張數 ÷ 換手量，負值越大＝結算時越可能往下壓、正值越大＝往上拉。
          同向＝（溢價、特法空、自營多）或（折價、特法多、自營空）：套利部位與外資期貨方向一致，結算日反向平倉的力道最大。
          平均折溢價＝本期每天「整日平均折溢價」的平均：每天 09:05～13:24 股期近月有成交的每一分鐘，期貨價 ÷ 當下現貨價 − 1，取當天平均（永豐 1 分 K；標 * 的有部分日子用期交所結算價估）。
          黑名單維護在 data/settlement/blacklist.json。
        </Note>
      </div>
    </div>
  );
}
