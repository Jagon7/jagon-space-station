"use client";

import { useMemo, useState } from "react";
import { Empty, Kpi, KpiRow, SearchBox } from "@/components/data-ui";

export type Sub = { id: string; name: string; codes: string[] };
export type IndNode = { id: string; name: string; stream: string; subs: Sub[] };
export type Industry = { id: string; name: string; nodes: IndNode[] };
/** code → [name, changePct | null, close | null] */
export type Quotes = Record<string, [string, number | null, number | null]>;

const pctColor = (v: number | null) => (v == null || v === 0 ? "text-slate-400" : v > 0 ? "text-[#ef4444]" : "text-[#22c55e]");
const fmtPct = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);

function avg(codes: string[], quotes: Quotes): { avg: number | null; n: number; up: number } {
  const xs = codes.map((c) => quotes[c]?.[1]).filter((v): v is number => v != null);
  return { avg: xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : null, n: xs.length, up: xs.filter((v) => v > 0).length };
}

type SubStat = { ind: Industry; node: IndNode; sub: Sub; avg: number | null; n: number };

export default function IndustryDashboard({ industries, quotes, names, priceDate, updatedAt }: {
  industries: Industry[]; quotes: Quotes; names: Record<string, string>; priceDate: string | null; updatedAt: string | null;
}) {
  const [indId, setIndId] = useState(industries[0]?.id ?? "");
  const [stock, setStock] = useState("");

  const subs: SubStat[] = useMemo(
    () => industries.flatMap((ind) => ind.nodes.flatMap((node) => node.subs.map((sub) => ({ ind, node, sub, ...avg(sub.codes, quotes) })))),
    [industries, quotes],
  );
  const ranked = subs.filter((s) => s.n >= 3 && s.avg != null).sort((a, b) => b.avg! - a.avg!);
  // 同名細類只留一個（不同產業可能共用相同公司清單）
  const dedupe = (xs: SubStat[]) => {
    const seen = new Set<string>();
    return xs.filter((x) => (seen.has(x.sub.name + x.n) ? false : (seen.add(x.sub.name + x.n), true)));
  };
  const strongest = dedupe(ranked).slice(0, 12);
  const weakest = dedupe([...ranked].reverse()).slice(0, 12);

  const indStats = useMemo(
    () => industries.map((ind) => ({ ind, ...avg([...new Set(ind.nodes.flatMap((n) => n.subs.flatMap((s) => s.codes)))], quotes) })),
    [industries, quotes],
  );
  const stockCount = new Set(subs.flatMap((s) => s.sub.codes)).size;
  const upSubs = subs.filter((s) => s.n > 0 && (s.avg ?? 0) > 0).length;
  const quotedSubs = subs.filter((s) => s.n > 0).length;

  const suggestions = useMemo(
    () => Object.entries(names).filter(([c]) => /^\d{4}$/.test(c)).map(([code, name]) => ({ code, name })),
    [names],
  );
  const memberships = stock ? subs.filter((s) => s.sub.codes.includes(stock)) : [];
  const current = industries.find((i) => i.id === indId);

  const subList = (title: string, xs: SubStat[]) => (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e2a3a] text-sm font-semibold text-white">{title}</div>
      {xs.map((s) => (
        <button
          key={`${s.ind.id}-${s.sub.id}`}
          onClick={() => setIndId(s.ind.id)}
          className="w-full flex items-center gap-2 px-4 py-2 text-sm border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#111a2c] text-left"
        >
          <span className="text-slate-200 truncate">{s.sub.name}</span>
          <span className="text-[11px] text-slate-500 shrink-0">{s.ind.name}・{s.n} 檔</span>
          <span className={`ml-auto font-mono ${pctColor(s.avg)}`}>{fmtPct(s.avg)}</span>
        </button>
      ))}
    </div>
  );

  return (
    <div>
      <KpiRow>
        <Kpi label="產業" value={industries.length} />
        <Kpi label="細類" value={subs.length} />
        <Kpi label="有細分類的個股" value={stockCount.toLocaleString()} />
        <Kpi label="今日上漲細類" value={`${upSubs}／${quotedSubs}`} />
      </KpiRow>

      <section className="mb-10">
        <h3 className="text-base font-semibold text-white mb-1">查個股</h3>
        <p className="text-xs text-slate-500 mb-3">一檔股票可能同時屬於多個產業鏈細類，括號是該細類今日平均漲跌。</p>
        <SearchBox placeholder="輸入代號或名稱" items={suggestions} onPick={setStock} />
        {stock && (
          <div className="mt-4 rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4">
            <div className="flex items-baseline gap-3 mb-3">
              <span className="text-lg font-bold text-white">{names[stock] ?? stock}</span>
              <span className="font-mono text-sm text-slate-500">{stock}</span>
              {quotes[stock] && <span className={`font-mono text-sm ${pctColor(quotes[stock][1])}`}>{fmtPct(quotes[stock][1])}</span>}
            </div>
            {memberships.length ? (
              <div className="flex flex-wrap gap-2">
                {memberships.map((m) => (
                  <button
                    key={`${m.ind.id}-${m.sub.id}`}
                    onClick={() => setIndId(m.ind.id)}
                    className="rounded-lg border border-[#1e2a3a] px-3 py-1.5 text-xs text-slate-300 hover:border-[#00d4aa]/50"
                  >
                    {m.ind.name}・{m.node.stream && `${m.node.stream}・`}{m.node.name !== m.sub.name && `${m.node.name}・`}{m.sub.name}
                    <span className={`ml-1.5 font-mono ${pctColor(m.avg)}`}>({fmtPct(m.avg)})</span>
                  </button>
                ))}
              </div>
            ) : <p className="text-sm text-slate-500">產業價值鏈平台沒有這檔股票的分類。</p>}
          </div>
        )}
      </section>

      <section className="mb-10">
        <h3 className="text-base font-semibold text-white mb-1">今日細產業強弱</h3>
        <p className="text-xs text-slate-500 mb-4">{priceDate ?? "—"}・細類內個股漲跌幅簡單平均（至少 3 檔有報價），點選可展開該產業。</p>
        <div className="grid lg:grid-cols-2 gap-4">
          {subList("最強", strongest)}
          {subList("最弱", weakest)}
        </div>
      </section>

      <section>
        <h3 className="text-base font-semibold text-white mb-1">瀏覽產業</h3>
        <p className="text-xs text-slate-500 mb-4">括號是該產業今日平均漲跌。</p>
        <div className="flex flex-wrap gap-1.5 mb-6">
          {indStats.map(({ ind, avg: a }) => (
            <button
              key={ind.id}
              onClick={() => setIndId(ind.id)}
              className={`px-2.5 py-1 rounded-md text-xs border transition-colors ${
                ind.id === indId ? "border-[#00d4aa]/60 bg-[#00d4aa]/10 text-white" : "border-[#1e2a3a] text-slate-400 hover:text-slate-200"
              }`}
            >
              {ind.name}<span className={`ml-1 font-mono ${pctColor(a)}`}>{fmtPct(a)}</span>
            </button>
          ))}
        </div>
        {current ? <Chain ind={current} quotes={quotes} names={names} onStock={setStock} /> : <Empty>請選擇產業。</Empty>}
      </section>

      <p className="mt-10 text-[11px] text-slate-600">
        分類來源：櫃買中心產業價值鏈資訊平台{updatedAt && `（更新 ${updatedAt}）`}；漲跌幅為臺灣證券交易所、證券櫃檯買賣中心 {priceDate ?? ""} 收盤行情，興櫃公司不計入平均。
      </p>
    </div>
  );
}

function Chain({ ind, quotes, names, onStock }: { ind: Industry; quotes: Quotes; names: Record<string, string>; onStock: (c: string) => void }) {
  const streams = [...new Set(ind.nodes.map((n) => n.stream || "—"))];
  return (
    <div className={`grid gap-4 ${streams.length >= 3 ? "lg:grid-cols-3" : streams.length === 2 ? "lg:grid-cols-2" : ""}`}>
      {streams.map((st) => (
        <div key={st}>
          <div className="text-xs font-mono tracking-widest text-[#00d4aa] mb-2">{st}</div>
          <div className="space-y-3">
            {ind.nodes.filter((n) => (n.stream || "—") === st).map((n) => (
              <div key={n.id} className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-3">
                <div className="text-sm font-semibold text-white mb-2">{n.name}</div>
                {n.subs.map((s) => {
                  const a = avg(s.codes, quotes);
                  const sorted = [...s.codes].sort((x, y) => (quotes[y]?.[1] ?? -99) - (quotes[x]?.[1] ?? -99));
                  return (
                    <details key={s.id} className="group border-t border-[#1e2a3a]/60 first:border-0">
                      <summary className="flex items-center gap-2 py-1.5 text-xs cursor-pointer list-none">
                        <span className="text-slate-300">{s.name}</span>
                        <span className="text-slate-600">{s.codes.length} 檔</span>
                        <span className={`ml-auto font-mono ${pctColor(a.avg)}`}>{fmtPct(a.avg)}</span>
                      </summary>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 pb-2 pl-1">
                        {sorted.map((c) => (
                          <button key={c} onClick={() => onStock(c)} className="text-[11px] text-slate-400 hover:text-[#00d4aa]">
                            {names[c] ?? c} <span className={`font-mono ${pctColor(quotes[c]?.[1] ?? null)}`}>{quotes[c] ? fmtPct(quotes[c][1]) : "興櫃"}</span>
                          </button>
                        ))}
                      </div>
                    </details>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
