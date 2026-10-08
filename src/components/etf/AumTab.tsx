"use client";

import { useMemo, useState } from "react";
import type { AumData, AumRow } from "./data";
import { fmtMoney, mmdd, signColor } from "./data";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

const CATS = ["全部", "國內股票", "主動式", "國外股票", "債券", "槓桿反向", "期貨商品"] as const;
type Cat = (typeof CATS)[number];

const yi = (v: number | null) => (v == null ? "—" : (v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 }));
const signedYi = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${yi(v)}`);

export default function AumTab({ aum, onEtf }: { aum: AumData; onEtf: (code: string) => void }) {
  const [cat, setCat] = useState<Cat>("全部");
  const rows = useMemo(() => aum.rows.filter((r) => cat === "全部" || r[2] === cat), [aum, cat]);
  const total = rows.reduce((s, r) => s + r[3], 0);
  const flow = rows.reduce((s, r) => s + r[7], 0);
  const top10 = [...rows].sort((a, b) => b[3] - a[3]).slice(0, 10).reduce((s, r) => s + r[3], 0);

  if (!aum.rows.length) return <Empty>ETF 規模資料尚未產生，下一次排程抓取後就會出現。</Empty>;

  const columns: Column<AumRow>[] = [
    {
      key: "etf", label: "ETF", sort: (r) => r[0],
      render: (r) => (
        <span className="inline-flex items-center gap-2">
          <span className="text-slate-200">{r[1]}</span>
          <span className="font-mono text-xs text-slate-500">{r[0]}</span>
          {r[11] && (
            <button onClick={() => onEtf(r[0])} className="text-[10px] px-1.5 rounded border border-[#00d4aa]/40 text-[#00d4aa] hover:bg-[#00d4aa]/10">持股</button>
          )}
        </span>
      ),
    },
    { key: "cat", label: "類型", render: (r) => <span className="text-xs text-slate-400">{r[2]}</span> },
    {
      key: "aum", label: "基金規模", align: "right", sort: (r) => r[3],
      render: (r) => (
        <div>
          <div className="text-slate-200">{fmtMoney(r[3])}</div>
          <div className="text-[10px] text-slate-600">佔{cat === "全部" ? "全體" : "此類"} {total ? ((r[3] / total) * 100).toFixed(2) : 0}%</div>
        </div>
      ),
    },
    { key: "nav", label: "淨值", align: "right", sort: (r) => r[4], render: (r) => <span className="text-slate-300">{r[4].toFixed(2)}</span> },
    { key: "units", label: "受益單位（億）", align: "right", sort: (r) => r[5], render: (r) => <span className="text-slate-400">{(r[5] / 1e8).toFixed(2)}</span> },
    { key: "flow", label: "當日流入（億）", align: "right", sort: (r) => r[7], render: (r) => <span className={signColor(r[7])}>{signedYi(r[7])}</span> },
    { key: "flow5", label: `近 ${aum.nFlow} 日流入（億）`, align: "right", sort: (r) => r[8], render: (r) => <span className={signColor(r[8])}>{signedYi(r[8])}</span> },
    { key: "daum", label: "規模變化（億）", align: "right", sort: (r) => r[9], render: (r) => <span className={signColor(r[9])}>{signedYi(r[9])}</span> },
    { key: "prem", label: "折溢價", align: "right", sort: (r) => r[10], render: (r) => <span className={signColor(r[10])}>{r[10] == null ? "—" : `${r[10] > 0 ? "+" : ""}${r[10].toFixed(2)}%`}</span> },
  ];

  return (
    <div>
      <Note>
        全體上市櫃 ETF 的基金規模（AUM）= 已發行受益單位數 × 前一營業日單位淨值。資金流入 = 受益單位增減 × 單位淨值，也就是申購減掉贖回的金額。
        資料來源為證交所 ETF 淨值揭露，每個交易日更新。標「持股」的 ETF 有每日持股明細可查。
      </Note>
      <KpiRow>
        <Kpi label="ETF 檔數" value={rows.length} unit="檔" sub={`· ${mmdd(aum.date)}`} />
        <Kpi label="總規模" value={fmtMoney(total)} />
        <Kpi label="當日淨流入" value={fmtMoney(flow, true)} color={signColor(flow)} />
        <Kpi label="前 10 大佔比" value={total ? `${((top10 / total) * 100).toFixed(1)}%` : "—"} sub="規模集中度" />
      </KpiRow>
      <div className="mb-4 overflow-x-auto">
        <Pills<Cat> value={cat} onChange={setCat} options={CATS.map((c) => ({ value: c, label: c }))} />
      </div>
      <SortTable rows={rows} columns={columns} rowKey={(r) => r[0]} initialSort={{ key: "aum", desc: true }} limit={100} rank />
    </div>
  );
}
