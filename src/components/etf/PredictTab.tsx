"use client";

import { useState } from "react";
import { Empty, Note, Pills } from "@/components/data-ui";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

type Pick = { code: string; name: string; w: number | null; lots: number | null; mult: number | null };
type WeightRow = { code: string; name?: string; final?: number; w?: number; cap?: number };
type ImpactRow = { code: string; name: string; old: number; new: number; dw: number; lots: number | null; multiple: number | null };
type Pred = {
  etf: string; name: string; asof: string; ready: boolean; missing?: string[]; notes: string[];
  add: Pick[]; del: Pick[]; weights: WeightRow[]; impact: ImpactRow[]; xlsx: string | null;
};
export type PredictData = { etfs: Pred[]; book?: string };

const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
const num = (v: number | null | undefined, d = 0) =>
  v == null ? "—" : v.toLocaleString("zh-TW", { maximumFractionDigits: d, minimumFractionDigits: d });

function PickTable({ title, rows, tone }: { title: string; rows: Pick[]; tone: "add" | "del" }) {
  const color = tone === "add" ? "text-[#ef4444]" : "text-[#22c55e]";
  return (
    <div className="rounded-xl border border-[#243247] bg-[#0d1220] overflow-hidden">
      <div className={`px-4 py-2.5 text-sm font-semibold border-b border-[#243247] ${color}`}>{title}（{rows.length}）</div>
      {rows.length === 0 ? (
        <div className="px-4 py-6 text-xs text-[#8b97ab]">無</div>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-[#8b97ab]">
            <tr>
              <th className="text-left px-4 py-2 font-normal">個股</th>
              <th className="text-right px-3 py-2 font-normal">預估權重</th>
              <th className="text-right px-3 py-2 font-normal">預估張數</th>
              <th className="text-right px-4 py-2 font-normal">換手量倍數</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code} className="border-t border-[#1b2638]">
                <td className="px-4 py-1.5 text-slate-200"><span className="font-mono">{r.code}</span> {r.name}</td>
                <td className="px-3 py-1.5 text-right font-mono">{pct(r.w)}</td>
                <td className={`px-3 py-1.5 text-right font-mono ${color}`}>{num(r.lots)}</td>
                <td className="px-4 py-1.5 text-right font-mono">{num(r.mult, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function PredictTab({ data }: { data: PredictData }) {
  const [code, setCode] = useState(data.etfs[0]?.etf ?? "");
  const p = data.etfs.find((e) => e.etf === code);
  if (!data.etfs.length || !p) return <Empty>還沒有換股預估資料。</Empty>;

  return (
    <div>
      <Note>
        依各指數編製規則，用證交所、櫃買中心、公開資訊觀測站的公開資料每天重算（財報季每天會納入當天新公布的財報）。
        「預估張數」= 權重調整 × ETF 規模 ÷ 股價；「換手量倍數」= 預估張數 ÷ 扣除當沖後的日成交量。
        計算過程可下載 Excel 對照。預估僅供參考，實際以指數公司公告為準。
      </Note>
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <Pills value={code} options={data.etfs.map((e) => ({ value: e.etf, label: `${e.etf} ${e.name ?? ""}` }))} onChange={setCode} />
        <span className="text-xs text-[#8b97ab] font-mono">資料日 {p.asof}</span>
        {data.book && (
          <a href={`${BASE}/data/${data.book}`} className="text-xs text-[#4f8cff] hover:underline" download>
            下載換股整理表（五檔 ETF）
          </a>
        )}
        {p.xlsx && (
          <a href={`${BASE}/data/${p.xlsx}`} className="text-xs text-[#4f8cff] hover:underline" download>
            下載計算過程（Excel）
          </a>
        )}
      </div>

      {!p.ready ? (
        <Empty>
          歷史資料補齊中，暫不預估。尚缺：{(p.missing ?? []).join("、")}
        </Empty>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 mb-5">
            <PickTable title="預估納入" rows={p.add} tone="add" />
            <PickTable title="預估剔除" rows={p.del} tone="del" />
          </div>
          {p.notes.length > 0 && (
            <ul className="mb-5 text-xs text-[#f59e0b] space-y-1">
              {p.notes.map((n) => <li key={n}>• {n}</li>)}
            </ul>
          )}
          <div className="rounded-xl border border-[#243247] bg-[#0d1220] overflow-x-auto">
            <div className="px-4 py-2.5 text-sm font-semibold border-b border-[#243247] text-slate-200">權重調整與預估影響（依換手量倍數排序）</div>
            <table className="w-full text-xs min-w-[640px]">
              <thead className="text-[#8b97ab]">
                <tr>
                  <th className="text-left px-4 py-2 font-normal">個股</th>
                  <th className="text-right px-3 py-2 font-normal">原有權重</th>
                  <th className="text-right px-3 py-2 font-normal">預估權重</th>
                  <th className="text-right px-3 py-2 font-normal">權重調整</th>
                  <th className="text-right px-3 py-2 font-normal">預估張數</th>
                  <th className="text-right px-4 py-2 font-normal">換手量倍數</th>
                </tr>
              </thead>
              <tbody>
                {p.impact.map((r) => (
                  <tr key={r.code} className="border-t border-[#1b2638]">
                    <td className="px-4 py-1.5 text-slate-200"><span className="font-mono">{r.code}</span> {r.name}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{pct(r.old)}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{pct(r.new)}</td>
                    <td className={`px-3 py-1.5 text-right font-mono ${r.dw > 0 ? "text-[#ef4444]" : r.dw < 0 ? "text-[#22c55e]" : ""}`}>
                      {pct(r.dw, 3)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono">{num(r.lots)}</td>
                    <td className="px-4 py-1.5 text-right font-mono">{num(r.multiple, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
