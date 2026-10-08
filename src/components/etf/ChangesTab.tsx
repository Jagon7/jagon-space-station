"use client";

import { useMemo, useState } from "react";
import type { ChangeRow, CoreData } from "./data";
import { fmtLots, fmtPct, fmtSignedLots, fmtYi, isTw, mmdd, signColor } from "./data";
import { useStockSuggestions } from "./HoldersTab";
import { Empty, KindBadge, Kpi, KpiRow, Note, Pills, SearchBox, SortTable, type Column } from "@/components/data-ui";

type Kind = "all" | "A" | "P";
type StockRow = { etf: number; row: ChangeRow };
type NetRow = { code: string; diff: number; value: number; buyers: number; sellers: number };

export default function ChangesTab({ core, query, setQuery }: {
  core: CoreData; query: string; setQuery: (q: string) => void;
}) {
  const [kind, setKind] = useState<Kind>("all");
  const stockSugg = useStockSuggestions(core);
  const items = useMemo(() => [
    ...core.etfs.map((e) => ({ code: e.c, name: e.n, hint: "ETF" })),
    ...stockSugg.map((s) => ({ ...s, hint: "個股" })),
  ], [core, stockSugg]);

  const changes = useMemo(
    () => core.changes.filter(([i]) => kind === "all" || core.etfs[i].k === kind),
    [core, kind],
  );
  const etfIdx = core.etfs.findIndex((e) => e.c === query);
  const isEtf = etfIdx >= 0;

  const kindPills = (
    <Pills<Kind> value={kind} onChange={setKind} options={[
      { value: "all", label: "全部 ETF" }, { value: "A", label: "主動式" }, { value: "P", label: "被動式" },
    ]} />
  );

  return (
    <div>
      <Note>
        輸入股票代號，列出所有買賣這檔股票的 ETF；輸入 ETF 代號，列出這檔 ETF 買賣的所有股票。
        每檔 ETF 與自己的前一份持股比較（各投信公告進度不同，資料日可能不一樣），股數為原始增減，包含申購贖回造成的變動。
        金額以該 ETF 資料日的收盤價估算。
      </Note>
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center mb-6">
        <SearchBox placeholder="輸入股票或 ETF 代號" items={items} onPick={setQuery} />
        {kindPills}
        {query && (
          <button onClick={() => setQuery("")} className="text-xs text-slate-500 hover:text-[#00d4aa]">清除查詢</button>
        )}
      </div>

      {!query && <Overview core={core} changes={changes} setQuery={setQuery} />}
      {query && isEtf && <EtfView core={core} idx={etfIdx} />}
      {query && !isEtf && <StockView core={core} code={query} changes={changes} />}
    </div>
  );
}

function StockView({ core, code, changes }: { core: CoreData; code: string; changes: [number, ChangeRow[]][] }) {
  const rows: StockRow[] = useMemo(
    () => changes.flatMap(([etf, rs]) => rs.filter((r) => r[0] === code).map((row) => ({ etf, row }))),
    [changes, code],
  );
  const buy = rows.filter((r) => r.row[2] > r.row[1]);
  const sell = rows.filter((r) => r.row[2] < r.row[1]);
  const diff = rows.reduce((s, r) => s + r.row[2] - r.row[1], 0);
  const value = rows.reduce((s, r) => s + (r.row[5] ?? 0), 0);

  const columns: Column<StockRow>[] = [
    { key: "etf", label: "ETF", sort: (r) => core.etfs[r.etf].c, render: (r) => <EtfCell core={core} idx={r.etf} /> },
    { key: "period", label: "比較期間", align: "right", render: (r) => <span className="text-slate-400">{mmdd(core.etfs[r.etf].pd)} → {mmdd(core.etfs[r.etf].d)}</span> },
    { key: "prev", label: "前一份", align: "right", sort: (r) => r.row[1], render: (r) => <span className="text-slate-400">{fmtLots(r.row[1], code)}</span> },
    { key: "curr", label: "最新", align: "right", sort: (r) => r.row[2], render: (r) => <span className="text-slate-200">{fmtLots(r.row[2], code)}</span> },
    { key: "diff", label: "增減", align: "right", sort: (r) => r.row[2] - r.row[1], render: (r) => <span className={signColor(r.row[2] - r.row[1])}>{fmtSignedLots(r.row[2] - r.row[1], code)}</span> },
    { key: "value", label: "估計金額（億）", align: "right", sort: (r) => r.row[5] == null ? null : Math.abs(r.row[5]), render: (r) => <span className={signColor(r.row[5])}>{fmtYi(r.row[5], true)}</span> },
    { key: "w", label: "權重", align: "right", render: (r) => <span className="text-slate-400">{fmtPct(r.row[3])} → {fmtPct(r.row[4])}</span> },
  ];

  return (
    <>
      <div className="flex items-baseline gap-3 mb-4">
        <h2 className="text-2xl font-bold text-white">{core.names[code] ?? code}</h2>
        <span className="font-mono text-sm text-slate-500">{code}</span>
        {core.close[code] && <span className="font-mono text-sm text-slate-500">收盤 {core.close[code].toLocaleString()}</span>}
      </div>
      <KpiRow>
        <Kpi label="買進的 ETF" value={buy.length} unit="檔" sub={`（新增 ${buy.filter((r) => r.row[1] === 0).length}）`} color="text-[#ef4444]" />
        <Kpi label="賣出的 ETF" value={sell.length} unit="檔" sub={`（剔除 ${sell.filter((r) => r.row[2] === 0).length}）`} color="text-[#22c55e]" />
        <Kpi label="合計增減" value={fmtSignedLots(diff, code).replace(/ (張|股)$/, "")} unit={isTw(code) ? "張" : "股"} color={signColor(diff)} />
        <Kpi label="估計淨金額" value={isTw(code) ? fmtYi(value, true) : "—"} unit={isTw(code) ? "億" : undefined} color={signColor(value)} />
      </KpiRow>
      {rows.length ? (
        <SortTable rows={rows} columns={columns} rowKey={(r) => core.etfs[r.etf].c} initialSort={{ key: "value", desc: true }} />
      ) : (
        <Empty>最新一份持股中，沒有 ETF 買賣這檔股票。</Empty>
      )}
    </>
  );
}

function EtfView({ core, idx }: { core: CoreData; idx: number }) {
  const e = core.etfs[idx];
  const rows = core.changes.find(([i]) => i === idx)?.[1] ?? [];
  const buys = rows.filter((r) => r[2] > r[1]);
  const sells = rows.filter((r) => r[2] < r[1]);
  const buyVal = buys.reduce((s, r) => s + (r[5] ?? 0), 0);
  const sellVal = sells.reduce((s, r) => s + (r[5] ?? 0), 0);

  const columns: Column<ChangeRow>[] = [
    {
      key: "stock", label: "股票", sort: (r) => r[0],
      render: (r) => (
        <span className="inline-flex items-center gap-2">
          <span className="text-slate-200">{core.names[r[0]] ?? r[0]}</span>
          <span className="font-mono text-xs text-slate-500">{r[0]}</span>
          {r[1] === 0 && <span className="text-[10px] px-1.5 rounded bg-[#ef4444]/15 text-[#ef4444]">新增</span>}
          {r[2] === 0 && <span className="text-[10px] px-1.5 rounded bg-[#22c55e]/15 text-[#22c55e]">剔除</span>}
        </span>
      ),
    },
    { key: "prev", label: "前一份", align: "right", sort: (r) => r[1], render: (r) => <span className="text-slate-400">{fmtLots(r[1], r[0])}</span> },
    { key: "curr", label: "最新", align: "right", sort: (r) => r[2], render: (r) => <span className="text-slate-200">{fmtLots(r[2], r[0])}</span> },
    { key: "diff", label: "增減", align: "right", sort: (r) => r[2] - r[1], render: (r) => <span className={signColor(r[2] - r[1])}>{fmtSignedLots(r[2] - r[1], r[0])}</span> },
    { key: "value", label: "估計金額（億）", align: "right", sort: (r) => r[5] == null ? null : Math.abs(r[5]), render: (r) => <span className={signColor(r[5])}>{fmtYi(r[5], true)}</span> },
    { key: "w", label: "權重", align: "right", render: (r) => <span className="text-slate-400">{fmtPct(r[3])} → {fmtPct(r[4])}</span> },
  ];

  return (
    <>
      <div className="flex items-baseline gap-3 mb-4 flex-wrap">
        <h2 className="text-2xl font-bold text-white">{e.n}</h2>
        <span className="font-mono text-sm text-slate-500">{e.c}</span>
        <KindBadge k={e.k} />
        <span className="font-mono text-sm text-slate-500">{e.i}投信 · {mmdd(e.pd)} → {mmdd(e.d)}</span>
      </div>
      <KpiRow>
        <Kpi label="買進" value={buys.length} unit="檔" sub={`（新增 ${buys.filter((r) => r[1] === 0).length}）`} color="text-[#ef4444]" />
        <Kpi label="賣出" value={sells.length} unit="檔" sub={`（剔除 ${sells.filter((r) => r[2] === 0).length}）`} color="text-[#22c55e]" />
        <Kpi label="買進金額" value={fmtYi(buyVal, true)} unit="億" color="text-[#ef4444]" />
        <Kpi label="賣出金額" value={fmtYi(sellVal, true)} unit="億" color="text-[#22c55e]" />
      </KpiRow>
      {e.pd == null ? (
        <Empty>這檔 ETF 目前只有一份持股，下一個交易日起才能比較。</Empty>
      ) : rows.length ? (
        <SortTable rows={rows} columns={columns} rowKey={(r) => r[0]} initialSort={{ key: "value", desc: true }} />
      ) : (
        <Empty>與前一份持股相比沒有變動。</Empty>
      )}
    </>
  );
}

function Overview({ core, changes, setQuery }: {
  core: CoreData; changes: [number, ChangeRow[]][]; setQuery: (q: string) => void;
}) {
  const net: NetRow[] = useMemo(() => {
    const m = new Map<string, NetRow>();
    for (const [, rows] of changes) {
      for (const r of rows) {
        if (!isTw(r[0])) continue;
        const x = m.get(r[0]) ?? { code: r[0], diff: 0, value: 0, buyers: 0, sellers: 0 };
        x.diff += r[2] - r[1];
        x.value += r[5] ?? 0;
        if (r[2] > r[1]) x.buyers++; else x.sellers++;
        m.set(r[0], x);
      }
    }
    return [...m.values()];
  }, [changes]);
  const topBuy = [...net].filter((r) => r.value > 0).sort((a, b) => b.value - a.value).slice(0, 15);
  const topSell = [...net].filter((r) => r.value < 0).sort((a, b) => a.value - b.value).slice(0, 15);
  const withChanges = changes.filter(([, rs]) => rs.length).sort((a, b) => b[1].length - a[1].length);

  if (!changes.length) {
    return <Empty>目前還沒有可以比較的前一份持股，下一個交易日起就會出現每日變化。</Empty>;
  }

  const list = (title: string, rows: NetRow[], color: string) => (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
      <div className={`px-4 py-3 border-b border-[#1e2a3a] text-sm font-semibold ${color}`}>{title}</div>
      {rows.map((r, i) => (
        <button key={r.code} onClick={() => setQuery(r.code)} className="w-full flex items-center gap-3 px-4 py-2 text-sm hover:bg-[#111a2c] border-b border-[#1e2a3a]/50 last:border-0">
          <span className="w-5 font-mono text-xs text-slate-600">{i + 1}</span>
          <span className="text-slate-200">{core.names[r.code] ?? r.code}</span>
          <span className="font-mono text-xs text-slate-500">{r.code}</span>
          <span className="ml-auto font-mono text-xs text-slate-500">{r.buyers} 買 / {r.sellers} 賣</span>
          <span className={`w-20 text-right font-mono ${color}`}>{fmtYi(r.value, true)} 億</span>
        </button>
      ))}
    </div>
  );

  return (
    <>
      <div className="grid lg:grid-cols-2 gap-4 mb-8">
        {list("ETF 合計買超（估計金額）", topBuy, "text-[#ef4444]")}
        {list("ETF 合計賣超（估計金額）", topSell, "text-[#22c55e]")}
      </div>
      <h3 className="text-base font-semibold text-white mb-1">有持股異動的 ETF</h3>
      <p className="text-xs text-slate-500 mb-4">括號內為異動股票檔數，點選即可查詢。</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
        {withChanges.map(([i, rs]) => (
          <button key={i} onClick={() => setQuery(core.etfs[i].c)} className="rounded-lg border border-[#1e2a3a] bg-[#0d1220] px-3 py-2 text-left hover:border-[#00d4aa]/40">
            <div className="text-sm text-slate-200 truncate">{core.etfs[i].n}</div>
            <div className="flex justify-between font-mono text-[11px] text-slate-500">
              <span>{core.etfs[i].c}</span><span className="text-[#00d4aa]">{rs.length}</span>
            </div>
          </button>
        ))}
      </div>
    </>
  );
}

function EtfCell({ core, idx }: { core: CoreData; idx: number }) {
  const e = core.etfs[idx];
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-slate-200">{e.n}</span>
      <span className="font-mono text-xs text-slate-500">{e.c}</span>
      <KindBadge k={e.k} />
    </span>
  );
}
