"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Pills, SortTable, type Column } from "@/components/data-ui";

// [code, name, market, close, changePct, value, volume, sector]
type Row = [string, string, "上市" | "上櫃", number, number | null, number, number, string];
type Day = { date: string; rows: Row[] };
type Market = "all" | "上市" | "上櫃";
type Kind = "all" | "stock" | "etf";
type Tab = "stocks" | "sectors";

const WEEK = "日一二三四五六";
const yi = (v: number) => {
  const x = v / 1e8;
  return x >= 100 ? Math.round(x).toLocaleString() : x >= 10 ? x.toFixed(1) : x.toFixed(2);
};
const pctColor = (v: number | null) => (v == null || v === 0 ? "text-slate-400" : v > 0 ? "text-[#ef4444]" : "text-[#22c55e]");
const fmtPct = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
const fmtPrice = (v: number) => (v >= 1000 ? v.toLocaleString() : v.toFixed(2));
const isEtf = (r: Row) => r[0].startsWith("00");

export default function RankingDashboard() {
  const index = useStaticJson<{ dates: string[] }>("ranking/index.json");
  const dates = index.data?.dates ?? [];
  const [picked, setPicked] = useState<string | null>(null);
  const date = picked ?? dates.at(-1) ?? null;
  const day = useStaticJson<Day>(date ? `ranking/${date}.json` : null);
  const [tab, setTab] = useState<Tab>("stocks");

  if (index.error) return <Empty>成交排行資料尚未產生。</Empty>;
  if (!index.data) return <Empty>載入中…</Empty>;
  if (!dates.length) return <Empty>成交排行資料尚未產生，下一次收盤後排程就會出現。</Empty>;

  const i = dates.indexOf(date!);
  const d = new Date(`${date}T00:00:00+08:00`);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-4 mb-6">
        <div className="flex gap-6 border-b border-[#1e2a3a]">
          {(["stocks", "sectors"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`pb-3 text-sm border-b-2 -mb-px ${tab === t ? "border-[#00d4aa] text-white" : "border-transparent text-slate-500 hover:text-slate-300"}`}
            >
              {t === "stocks" ? "個股排行" : "族群資金流向"}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2 font-mono text-sm">
          <button disabled={i <= 0} onClick={() => setPicked(dates[i - 1])} className="p-1.5 rounded border border-[#1e2a3a] disabled:opacity-30 hover:border-[#00d4aa]/50">
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-slate-200 px-2">{date?.replaceAll("-", "/")}（{WEEK[d.getDay()]}）</span>
          <button disabled={i >= dates.length - 1} onClick={() => setPicked(dates[i + 1])} className="p-1.5 rounded border border-[#1e2a3a] disabled:opacity-30 hover:border-[#00d4aa]/50">
            <ChevronRight className="w-4 h-4" />
          </button>
          <span className="text-[11px] text-slate-500 ml-2">{i === dates.length - 1 ? "最新交易日" : ""} · 每日收盤後自動更新</span>
        </div>
      </div>

      {!day.data ? <Empty>{day.error ? "這天的資料載入失敗。" : "載入中…"}</Empty> : (
        <>
          <Summary rows={day.data.rows} />
          {tab === "stocks" ? <StockRanking rows={day.data.rows} /> : <SectorFlow rows={day.data.rows} />}
        </>
      )}
    </div>
  );
}

function Summary({ rows }: { rows: Row[] }) {
  const total = rows.reduce((s, r) => s + r[5], 0);
  const twse = rows.filter((r) => r[2] === "上市").reduce((s, r) => s + r[5], 0);
  const top10 = rows.slice(0, 10).reduce((s, r) => s + r[5], 0);
  const stocks = rows.filter((r) => !isEtf(r));
  const up = stocks.filter((r) => (r[4] ?? 0) > 0).length;
  const down = stocks.filter((r) => (r[4] ?? 0) < 0).length;
  return (
    <KpiRow>
      <Kpi label="全市場成交金額" value={yi(total)} unit="億" />
      <Kpi label="上市 / 上櫃" value={`${yi(twse)} / ${yi(total - twse)}`} unit="億" />
      <Kpi label="前 10 名佔比" value={`${((top10 / total) * 100).toFixed(1)}%`} sub="資金集中度" />
      <Kpi label="上漲 / 下跌家數" value={<><span className="text-[#ef4444]">{up}</span><span className="text-slate-600"> / </span><span className="text-[#22c55e]">{down}</span></>} />
    </KpiRow>
  );
}

function StockRanking({ rows }: { rows: Row[] }) {
  const [market, setMarket] = useState<Market>("all");
  const [kind, setKind] = useState<Kind>("all");
  const total = rows.reduce((s, r) => s + r[5], 0);
  const shown = useMemo(
    () => rows.filter((r) => (market === "all" || r[2] === market) && (kind === "all" || (kind === "etf") === isEtf(r))),
    [rows, market, kind],
  );
  const max = shown[0]?.[5] ?? 1;

  const columns: Column<Row>[] = [
    {
      key: "name", label: "股票",
      render: (r) => (
        <span className="inline-flex items-center gap-2">
          <span className="text-slate-200">{r[1]}</span>
          <span className="font-mono text-xs text-slate-500">{r[0]}</span>
          <span className="text-[10px] px-1 rounded border border-slate-700 text-slate-500">{r[2] === "上市" ? "市" : "櫃"}</span>
          {r[7] && r[7] !== "ETF" && <span className="text-[11px] text-slate-500">{r[7]}</span>}
          {isEtf(r) && (
            <Link href={`/etf-flow?tab=changes&q=${r[0]}`} className="text-[10px] px-1.5 rounded border border-[#00d4aa]/40 text-[#00d4aa]">ETF</Link>
          )}
        </span>
      ),
    },
    { key: "close", label: "收盤", align: "right", sort: (r) => r[3], render: (r) => <span className="text-slate-200">{fmtPrice(r[3])}</span> },
    { key: "pct", label: "漲跌幅", align: "right", sort: (r) => r[4], render: (r) => <span className={pctColor(r[4])}>{fmtPct(r[4])}</span> },
    {
      key: "value", label: "成交金額（億）", align: "right", sort: (r) => r[5],
      render: (r) => (
        <div className="flex items-center justify-end gap-2">
          <div className="hidden sm:block w-24 h-1.5 rounded bg-[#1e2a3a] overflow-hidden">
            <div className="h-full bg-[#00d4aa]/60" style={{ width: `${Math.max(2, (r[5] / max) * 100)}%` }} />
          </div>
          <span className="text-slate-200 w-14">{yi(r[5])}</span>
        </div>
      ),
    },
    { key: "share", label: "佔市場", align: "right", sort: (r) => r[5], render: (r) => <span className="text-slate-400">{((r[5] / total) * 100).toFixed(2)}%</span> },
    { key: "vol", label: "成交量（張）", align: "right", sort: (r) => r[6], render: (r) => <span className="text-slate-400">{r[6].toLocaleString()}</span> },
  ];

  return (
    <>
      <div className="flex flex-wrap gap-3 mb-4">
        <Pills<Market> value={market} onChange={setMarket} options={[{ value: "all", label: "全部" }, { value: "上市", label: "上市" }, { value: "上櫃", label: "上櫃" }]} />
        <Pills<Kind> value={kind} onChange={setKind} options={[{ value: "all", label: "全部" }, { value: "stock", label: "個股" }, { value: "etf", label: "ETF" }]} />
      </div>
      <SortTable rows={shown} columns={columns} rowKey={(r) => r[0]} initialSort={{ key: "value", desc: true }} limit={100} rank />
    </>
  );
}

type Sector = { name: string; value: number; up: number; down: number; wPct: number; n: number; top: Row[] };

function SectorFlow({ rows }: { rows: Row[] }) {
  const stocks = rows.filter((r) => !isEtf(r));
  const total = stocks.reduce((s, r) => s + r[5], 0);
  const sectors = useMemo(() => {
    const m = new Map<string, Sector>();
    for (const r of stocks) {
      const name = r[7] || "其他";
      const x = m.get(name) ?? { name, value: 0, up: 0, down: 0, wPct: 0, n: 0, top: [] };
      x.value += r[5];
      x.wPct += (r[4] ?? 0) * r[5];
      x.n++;
      if ((r[4] ?? 0) > 0) x.up++;
      if ((r[4] ?? 0) < 0) x.down++;
      if (x.top.length < 3) x.top.push(r);
      m.set(name, x);
    }
    return [...m.values()].map((x) => ({ ...x, wPct: x.value ? x.wPct / x.value : 0 })).sort((a, b) => b.value - a.value);
  }, [stocks]);
  const max = sectors[0]?.value ?? 1;

  return (
    <>
      <p className="text-xs text-slate-500 mb-4">
        依族群加總個股成交金額（不含 ETF）。漲跌幅為成交金額加權平均，可看資金集中在哪些族群、是追價還是倒貨。
      </p>
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
        {sectors.map((s, i) => (
          <div key={s.name} className="grid grid-cols-12 items-center gap-3 px-4 py-3 border-b border-[#1e2a3a]/60 last:border-0">
            <div className="col-span-12 sm:col-span-3 flex items-center gap-3">
              <span className="w-5 font-mono text-xs text-slate-600">{i + 1}</span>
              <Link href={`/sectors/${encodeURIComponent(s.name)}`} className="text-slate-200 hover:text-[#00d4aa]">{s.name}</Link>
              <span className="text-[11px] text-slate-500">{s.n} 檔</span>
            </div>
            <div className="col-span-7 sm:col-span-4 flex items-center gap-2">
              <div className="flex-1 h-2 rounded bg-[#1e2a3a] overflow-hidden">
                <div className="h-full bg-[#00d4aa]/60" style={{ width: `${(s.value / max) * 100}%` }} />
              </div>
              <span className="font-mono text-sm text-slate-200 w-16 text-right">{yi(s.value)}億</span>
              <span className="font-mono text-xs text-slate-500 w-12 text-right">{((s.value / total) * 100).toFixed(1)}%</span>
            </div>
            <div className={`col-span-2 sm:col-span-1 font-mono text-sm text-right ${pctColor(s.wPct)}`}>{fmtPct(s.wPct)}</div>
            <div className="col-span-3 sm:col-span-1 font-mono text-xs text-right">
              <span className="text-[#ef4444]">{s.up}</span><span className="text-slate-600">/</span><span className="text-[#22c55e]">{s.down}</span>
            </div>
            <div className="hidden sm:flex col-span-3 gap-2 text-xs text-slate-400 truncate">
              {s.top.map((r) => (
                <span key={r[0]} className="truncate">{r[1]} <span className={pctColor(r[4])}>{fmtPct(r[4])}</span></span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
