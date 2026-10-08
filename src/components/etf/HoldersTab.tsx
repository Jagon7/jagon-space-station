"use client";

import { useMemo } from "react";
import type { CoreData, Holder } from "./data";
import { fmtLots, fmtPct, fmtSignedLots, fmtYi, isTw, mmdd, signColor } from "./data";
import { Empty, KindBadge, Kpi, KpiRow, SearchBox, SortTable, type Column, type Suggestion } from "./ui";

export function useStockSuggestions(core: CoreData): Suggestion[] {
  return useMemo(
    () => Object.entries(core.holders)
      .map(([code, hs]) => ({ code, name: core.names[code] ?? code, hint: `${hs.filter((h) => h[1] > 0).length} 檔 ETF`, n: hs.length }))
      .sort((a, b) => b.n - a.n),
    [core],
  );
}

export default function HoldersTab({ core, stock, setStock }: {
  core: CoreData; stock: string; setStock: (s: string) => void;
}) {
  const suggestions = useStockSuggestions(core);
  const holders = useMemo(() => (core.holders[stock] ?? []).filter((h) => h[1] > 0), [core, stock]);

  const mostHeld = useMemo(
    () => Object.entries(core.holders)
      .filter(([code]) => isTw(code))
      .map(([code, hs]) => [code, hs.filter((h) => h[1] > 0).length] as const)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 40),
    [core],
  );

  const totals = useMemo(() => {
    const shares = holders.reduce((s, h) => s + h[1], 0);
    const value = holders.reduce((s, h) => s + (h[3] ?? 0), 0);
    const comparable = holders.filter((h) => h[4] != null);
    const diff = comparable.reduce((s, h) => s + (h[4] ?? 0), 0);
    return { shares, value, diff, comparable: comparable.length };
  }, [holders]);

  const columns: Column<Holder>[] = [
    {
      key: "etf", label: "ETF", sort: (h) => core.etfs[h[0]].c,
      render: (h) => {
        const e = core.etfs[h[0]];
        return (
          <span className="inline-flex items-center gap-2">
            <span className="text-slate-200">{e.n}</span>
            <span className="font-mono text-xs text-slate-500">{e.c}</span>
            <KindBadge k={e.k} />
          </span>
        );
      },
    },
    { key: "date", label: "資料日", align: "right", sort: (h) => core.etfs[h[0]].d, render: (h) => <span className="text-slate-400">{mmdd(core.etfs[h[0]].d)}</span> },
    { key: "shares", label: "持股", align: "right", sort: (h) => h[1], render: (h) => <span className="text-slate-200">{fmtLots(h[1], stock)}</span> },
    { key: "weight", label: "權重", align: "right", sort: (h) => h[2], render: (h) => <span className="text-slate-300">{fmtPct(h[2])}</span> },
    { key: "value", label: "市值（億）", align: "right", sort: (h) => h[3], render: (h) => <span className="text-slate-200">{fmtYi(h[3])}</span> },
    {
      key: "diff", label: "較前一份", align: "right", sort: (h) => h[4],
      render: (h) => h[4] == null ? <span className="text-slate-600">—</span> : <span className={signColor(h[4])}>{h[4] === 0 ? "0" : fmtSignedLots(h[4], stock)}</span>,
    },
  ];

  return (
    <div>
      <div className="mb-6">
        <SearchBox placeholder="輸入股票代號或名稱，例如 2330" items={suggestions} onPick={setStock} />
      </div>

      {stock ? (
        <>
          <div className="flex items-baseline gap-3 mb-4">
            <h2 className="text-2xl font-bold text-white">{core.names[stock] ?? stock}</h2>
            <span className="font-mono text-sm text-slate-500">{stock}</span>
            {core.close[stock] && <span className="font-mono text-sm text-slate-500">收盤 {core.close[stock].toLocaleString()}</span>}
          </div>
          {holders.length ? (
            <>
              <KpiRow>
                <Kpi label="持有 ETF" value={holders.length} unit="檔" />
                <Kpi label="合計持股" value={fmtLots(totals.shares, stock).replace(/ (張|股)$/, "")} unit={isTw(stock) ? "張" : "股"} />
                <Kpi label="合計市值" value={isTw(stock) ? fmtYi(totals.value) : "—"} unit={isTw(stock) ? "億" : undefined} />
                <Kpi
                  label="較前一份合計增減"
                  value={fmtSignedLots(totals.diff, stock).replace(/ (張|股)$/, "")}
                  unit={isTw(stock) ? "張" : "股"}
                  sub={`（${totals.comparable} 檔可比）`}
                  color={signColor(totals.diff)}
                />
              </KpiRow>
              <SortTable rows={holders} columns={columns} rowKey={(h) => core.etfs[h[0]].c} initialSort={{ key: "value", desc: true }} />
            </>
          ) : (
            <Empty>追蹤中的 ETF 目前都沒有持有這檔股票。</Empty>
          )}
        </>
      ) : (
        <Empty>輸入股票代號或名稱，或從下方點選。</Empty>
      )}

      <section className="mt-10">
        <h3 className="text-base font-semibold text-white mb-1">被最多 ETF 持有的個股</h3>
        <p className="text-xs text-slate-500 mb-4">依持有的 ETF 檔數排序，點選即可查詢。</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {mostHeld.map(([code, n]) => (
            <button
              key={code}
              onClick={() => { setStock(code); window.scrollTo({ top: 0, behavior: "smooth" }); }}
              className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                code === stock ? "border-[#00d4aa]/60 bg-[#00d4aa]/10" : "border-[#1e2a3a] bg-[#0d1220] hover:border-[#00d4aa]/40"
              }`}
            >
              <div className="text-sm text-slate-200 truncate">{core.names[code] ?? code}</div>
              <div className="flex justify-between font-mono text-[11px] text-slate-500">
                <span>{code}</span><span className="text-[#00d4aa]">{n} 檔</span>
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
