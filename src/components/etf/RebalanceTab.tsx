"use client";

import { Fragment, useMemo, useState } from "react";
import { Empty, Kpi, KpiRow, Note, Pills } from "@/components/data-ui";

type Event = {
  start: string; end: string | null; days: number | null; add: string[]; del: string[]; kind: "regular" | "adhoc";
  eff?: string; relStart?: number; relEnd?: number | null;
};
type Etf = { c: string; n: string; i: string; index: string; hist: number; first: string | null; events: Event[] };
export type RebalanceData = { etfs: Etf[]; names: Record<string, string> };
type Filter = "with" | "all";

const md = (d: string | null | undefined) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : "—");
const rel = (n: number | null | undefined) => (n == null ? "?" : n > 0 ? `+${n}` : n === 0 ? "0" : `−${-n}`);
const med = (xs: number[]) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};

export default function RebalanceTab({ data, onStock }: { data: RebalanceData; onStock: (code: string) => void }) {
  const [filter, setFilter] = useState<Filter>("with");
  const [open, setOpen] = useState<string | null>(null);

  const rows = useMemo(() => data.etfs.map((e) => {
    const reg = e.events.filter((v) => v.kind === "regular" && v.days != null);
    const withRel = reg.filter((v) => v.relStart != null);
    return {
      e, reg,
      typDays: med(reg.map((v) => v.days!)),
      typStart: med(withRel.map((v) => v.relStart!)),
      typEnd: med(withRel.filter((v) => v.relEnd != null).map((v) => v.relEnd!)),
      last: e.events.at(-1),
    };
  }).sort((a, b) => (b.typDays ?? -1) - (a.typDays ?? -1)), [data]);

  const shown = filter === "with" ? rows.filter((r) => r.e.events.length) : rows;
  const allReg = rows.flatMap((r) => r.reg);
  const medDays = med(allReg.map((v) => v.days!));
  const medStart = med(allReg.filter((v) => v.relStart != null).map((v) => v.relStart!));

  return (
    <div>
      <Note>
        被動式 ETF 每次指數調整（換股）從開始到大致完成花了幾個交易日。由歷史持股的股數推算（扣掉申購贖回造成的整體增減）：
        刪除股開始減少、或新增股第一次出現＝開始；每檔都完成 85% 以上、整體完成 97% 以上＝完成（零星殘股不算）。
        「期間」是相對指數生效日的交易日差，例如「−1 ～ +6」＝生效日前 1 天開始、生效後第 6 天完成。只異動 1～2 檔的臨時調整另外標示，不算進「通常時長」。
        只有部分投信能回查歷史持股，其餘從開始追蹤起逐日累積。點一列看每次明細。
      </Note>
      <KpiRow>
        <Kpi label="有換股紀錄的 ETF" value={`${rows.filter((r) => r.e.events.length).length}/${rows.length}`} unit="檔被動式" />
        <Kpi label="定期調整次數" value={allReg.length} unit="次" />
        <Kpi label="通常時長（中位數）" value={medDays ?? "—"} unit="個交易日" />
        <Kpi label="通常開始" value={medStart == null ? "—" : rel(medStart)} sub="相對生效日" />
      </KpiRow>
      <div className="mb-4">
        <Pills<Filter> value={filter} onChange={setFilter} options={[{ value: "with", label: "有紀錄" }, { value: "all", label: "全部被動式" }]} />
      </div>
      {!shown.length ? <Empty>目前還沒有偵測到換股，持股歷史累積後就會出現。</Empty> : (
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500 text-left">
                <th className="px-4 py-3 font-normal">ETF</th><th className="px-4 py-3 font-normal">追蹤指數</th>
                <th className="px-4 py-3 font-normal text-right">定期調整</th><th className="px-4 py-3 font-normal text-right">通常時長</th>
                <th className="px-4 py-3 font-normal text-right">通常期間</th><th className="px-4 py-3 font-normal">最近一次</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(({ e, reg, typDays, typStart, typEnd, last }) => (
                <Fragment key={e.c}>
                  <tr onClick={() => setOpen(open === e.c ? null : e.c)} className="border-b border-[#1e2a3a]/60 hover:bg-[#111a2c] cursor-pointer">
                    <td className="px-4 py-2.5 whitespace-nowrap"><span className="text-slate-200">{e.n}</span> <span className="font-mono text-xs text-slate-500">{e.c}</span></td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 max-w-xs">{e.index || "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-300">{reg.length}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-200">{typDays == null ? "—" : `${typDays} 天`}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-400 whitespace-nowrap">{typStart == null ? "—" : `${rel(typStart)} ～ ${rel(typEnd)}`}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400 whitespace-nowrap">
                      {last ? `${md(last.start)}～${last.end ? md(last.end) : "進行中"}${last.days ? `・${last.days} 天` : ""}・${last.add.length} 進 ${last.del.length} 出` : `資料自 ${md(e.first)}・${e.hist} 份`}
                    </td>
                  </tr>
                  {open === e.c && (
                    <tr className="border-b border-[#1e2a3a]/60 bg-[#0a0f1a]">
                      <td colSpan={6} className="px-6 py-3">
                        {!e.events.length ? <p className="text-xs text-slate-500">資料自 {e.first}（{e.hist} 份），尚未偵測到換股。</p> : (
                          <div className="space-y-3">
                            {[...e.events].reverse().map((v) => (
                              <div key={v.start} className="text-xs">
                                <div className="flex flex-wrap gap-x-4 text-slate-300">
                                  <span className="font-mono">{v.start} ～ {v.end ?? "進行中"}</span>
                                  {v.days != null && <span>{v.days} 個交易日</span>}
                                  {v.eff && <span className="text-slate-500">生效日 {v.eff}・期間 {rel(v.relStart)} ～ {rel(v.relEnd)}</span>}
                                  {v.kind === "adhoc" && <span className="text-[#f59e0b]">臨時調整</span>}
                                </div>
                                {[["納入", v.add, "text-[#ef4444]"], ["刪除", v.del, "text-[#22c55e]"]].map(([label, codes, cls]) => (codes as string[]).length > 0 && (
                                  <div key={label as string} className="flex flex-wrap gap-x-2 mt-1">
                                    <span className={cls as string}>{label as string}</span>
                                    {(codes as string[]).map((c) => (
                                      <button key={c} onClick={() => onStock(c)} className="text-slate-400 hover:text-[#00d4aa]">
                                        {data.names[c] ?? c}<span className="font-mono text-slate-600 ml-0.5">{c}</span>
                                      </button>
                                    ))}
                                  </div>
                                ))}
                              </div>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
