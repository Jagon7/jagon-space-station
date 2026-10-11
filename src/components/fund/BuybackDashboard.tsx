"use client";

import { useMemo, useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills } from "@/components/data-ui";
import ExpandTable, { StockCell, type XColumn } from "@/components/ExpandTable";

// [代號, 名稱, 市場, 董事會日(民國), 目的, 預定股數, 價格下限, 上限, 起, 迄, 完畢, 已買回股數, 平均價, 佔股本%, 最新收盤]
type R = [string, string, string, string, string, number | null, number | null, number | null, string, string, string, number | null, number | null, number | null, number | null];
type Filter = "active" | "recent" | "all";

const PURPOSE: Record<string, string> = { "1": "轉讓員工", "2": "股權轉換", "3": "維護股東權益" };
const iso = (roc: string) => { const m = roc.match(/(\d+)\/(\d+)\/(\d+)/); return m ? `${Number(m[1]) + 1911}-${m[2]}-${m[3]}` : ""; };
const md = (roc: string) => { const s = iso(roc); return s ? `${s.slice(2, 4)}/${Number(s.slice(5, 7))}/${Number(s.slice(8))}` : "—"; };
const lots = (v: number | null | undefined) => (v == null ? "—" : Math.round(v / 1000).toLocaleString());
const TODAY = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const CUT_3M = new Date(Date.now() - 92 * 86400e3).toISOString().slice(0, 10);
const active = (r: R) => r[10] !== "Y" && iso(r[9]) >= TODAY && iso(r[8]) <= TODAY;

function position(r: R) {
  const p = r[14], lo = r[6], hi = r[7];
  if (p == null || lo == null || hi == null) return null;
  if (p < lo) return { text: "低於區間", cls: "text-[#f05252]" };
  if (p > hi) return { text: "高於上限", cls: "text-[#8b97ab]" };
  return { text: `區間內 ${Math.round(((p - lo) / (hi - lo || 1)) * 100)}%`, cls: "text-[#f59e0b]" };
}

export default function BuybackDashboard() {
  const { data, error } = useStaticJson<{ rows: R[] }>("fund/buyback.json");
  const [filter, setFilter] = useState<Filter>("active");
  const [support, setSupport] = useState(false);
  const rows = useMemo(() => {
    let rs = data?.rows ?? [];
    if (support) rs = rs.filter((r) => r[4] === "3");
    if (filter === "active") return rs.filter(active);
    if (filter === "recent") return rs.filter((r) => iso(r[3]) >= CUT_3M);
    return rs;
  }, [data, filter, support]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>庫藏股資料累積中。</Empty>;
  const all = data.rows;
  const act = all.filter(active);

  const cols: XColumn<R>[] = [
    { key: "name", label: "公司", render: (r) => <StockCell code={r[0]} name={r[1]} mk={r[2]} /> },
    { key: "board", label: "董事會", sort: (r) => iso(r[3]), render: (r) => <span className="font-mono text-xs text-slate-400">{md(r[3])}</span> },
    { key: "purpose", label: "目的", render: (r) => <span className={`text-xs ${r[4] === "3" ? "text-[#f59e0b]" : "text-slate-400"}`}>{PURPOSE[r[4]] ?? r[4]}</span> },
    { key: "shares", label: "預定買回（張）", align: "right", sort: (r) => r[5], render: (r) => <span className="text-slate-200">{lots(r[5])}</span> },
    { key: "range", label: "價格區間", align: "right", render: (r) => <span className="text-slate-400">{r[6]} ～ {r[7]}</span> },
    { key: "price", label: "最新收盤", align: "right", sort: (r) => r[14], render: (r) => { const p = position(r); return <span className="text-slate-200">{r[14] ?? "—"}{p && <span className={`ml-2 text-xs font-sans ${p.cls}`}>{p.text}</span>}</span>; } },
    { key: "period", label: "買回期間", render: (r) => <span className="font-mono text-xs text-slate-400">{md(r[8])} ～ {md(r[9])}</span> },
    { key: "status", label: "狀態", sort: (r) => (r[10] === "Y" ? 1 : 0), render: (r) => (r[10] === "Y"
      ? <span className="text-xs text-[#8b97ab]">完成 {r[5] && r[11] != null ? `${Math.round((r[11] / r[5]) * 100)}%` : ""}</span>
      : active(r) ? <span className="text-xs text-[#4f8cff]">執行中</span> : <span className="text-xs text-[#7c8aa0]">期滿</span>) },
  ];

  return (
    <div>
      <Note>
        公司董事會決議在市場上買回自家股票。「維護股東權益」通常是股價下跌時的護盤動作；「轉讓員工」是員工獎酬用。
        現價低於買回價格區間下限時，公司可能積極買進。資料來自公開資訊觀測站，期滿或完成後才會公告實際買回股數與均價。
      </Note>
      <KpiRow>
        <Kpi label="執行中" value={act.length} unit="家" color="text-[#4f8cff]" />
        <Kpi label="其中維護股東權益" value={act.filter((r) => r[4] === "3").length} unit="家" color="text-[#f59e0b]" />
        <Kpi label="現價低於區間下限" value={act.filter((r) => r[14] != null && r[6] != null && r[14] < r[6]).length} unit="家" color="text-[#f05252]" />
        <Kpi label="近 2 年紀錄" value={all.length} unit="筆" />
      </KpiRow>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <Pills<Filter> value={filter} onChange={setFilter} options={[{ value: "active", label: "執行中" }, { value: "recent", label: "近 3 個月決議" }, { value: "all", label: "全部" }]} />
        <label className="flex items-center gap-1.5 text-xs text-slate-400"><input type="checkbox" checked={support} onChange={(e) => setSupport(e.target.checked)} />只看維護股東權益（護盤）</label>
      </div>
      {!rows.length ? <Empty>沒有符合條件的庫藏股。</Empty> :
        <ExpandTable<R> key={`${filter}${support}`} rows={rows} columns={cols} rowKey={(r) => `${r[0]}-${r[3]}`} initialSort={{ key: "board", desc: true }}
          detail={(r) => (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div><div className="text-[#8b97ab]">預定買回</div><div className="text-slate-200 font-mono">{r[5]?.toLocaleString() ?? "—"} 股</div></div>
              <div><div className="text-[#8b97ab]">已買回</div><div className="text-slate-200 font-mono">{r[11] != null ? `${r[11].toLocaleString()} 股` : "執行中（期滿後公告）"}</div></div>
              <div><div className="text-[#8b97ab]">平均買回價</div><div className="text-slate-200 font-mono">{r[12] ?? "—"}</div></div>
              <div><div className="text-[#8b97ab]">佔已發行股數</div><div className="text-slate-200 font-mono">{r[13] != null ? `${r[13]}%` : "—"}</div></div>
            </div>
          )} />}
    </div>
  );
}
