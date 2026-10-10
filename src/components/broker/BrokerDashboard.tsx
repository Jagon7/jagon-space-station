"use client";

import { useEffect, useMemo, useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox, SortTable, type Column } from "@/components/data-ui";

type Index = { dates: string[]; branches: string[]; firstDate: Record<string, string | null> };
// [dayIdx, buyAmt(仟元), sellAmt, buyLots, sellLots]
type Cell = [number, number | null, number | null, number | null, number | null];
type BranchFile = { label: string; dates: string[]; names: Record<string, string>; rows: Record<string, Cell[]> };
type Period = "1" | "5" | "10" | "20" | "60";
type Unit = "amt" | "lots";
type Agg = {
  code: string; net: number; netLots: number; amt: number; days: number; buyDays: number;
  branches: Set<string>; last: string; perDay: Map<number, [number, number]>;
};

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const wan = (v: number) => {
  const x = v / 10; // 仟元 → 萬元
  return Math.abs(x) >= 10000 ? `${(x / 10000).toFixed(2)}億` : `${Math.round(x).toLocaleString()}萬`;
};
const signed = (s: string, v: number) => (v > 0 ? `+${s}` : s);
const color = (v: number) => (v > 0 ? "text-[#ef4444]" : v < 0 ? "text-[#22c55e]" : "text-slate-400");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;

/** 選「全部分點」時要載入每個分點的檔案 */
function useBranchFiles(ids: number[]) {
  const [files, setFiles] = useState<Record<number, BranchFile>>({});
  const key = ids.join(",");
  useEffect(() => {
    let alive = true;
    for (const i of ids) {
      if (files[i]) continue;
      fetch(`${BASE}/data/broker/${i}.json`, { cache: "no-cache" })
        .then((r) => r.json())
        .then((d: BranchFile) => alive && setFiles((f) => ({ ...f, [i]: d })))
        .catch(() => {});
    }
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return ids.every((i) => files[i]) ? ids.map((i) => files[i]) : null;
}

export default function BrokerDashboard() {
  const index = useStaticJson<Index>("broker/index.json");
  // 可複選分點；記住上次的選擇（只存在這台瀏覽器）
  const [picked, setPickedState] = useState<number[]>(() => {
    try {
      const v = JSON.parse(localStorage.getItem("broker.picked") ?? "null");
      if (Array.isArray(v) && v.every((x) => Number.isInteger(x))) return v;
    } catch {}
    return [0];
  });
  const setPicked = (v: number[]) => {
    const sorted = [...new Set(v)].sort((a, b) => a - b);
    setPickedState(sorted);
    try { localStorage.setItem("broker.picked", JSON.stringify(sorted)); } catch {}
  };
  const [period, setPeriod] = useState<Period>("5");
  const [unit, setUnit] = useState<Unit>("amt");
  const [stock, setStock] = useState("");

  const ids = index.data ? picked.filter((i) => i < index.data!.branches.length) : [];
  const multi = ids.length > 1;
  const files = useBranchFiles(ids);

  const dates = useMemo(() => index.data?.dates ?? [], [index.data]);
  const n = Number(period);
  const from = Math.max(0, dates.length - n);

  const { buys, sells, names } = useMemo(() => {
    const m = new Map<string, Agg>();
    const names: Record<string, string> = {};
    for (const f of files ?? []) {
      Object.assign(names, f.names);
      for (const [code, cells] of Object.entries(f.rows)) {
        for (const [di, ba, sa, bl, sl] of cells) {
          if (di < from) continue;
          const net = ba != null && sa != null ? ba - sa : 0;
          const netLots = bl != null && sl != null ? bl - sl : 0;
          const a = m.get(code) ?? { code, net: 0, netLots: 0, amt: 0, days: 0, buyDays: 0, branches: new Set<string>(), last: "", perDay: new Map() };
          a.net += net;
          a.netLots += netLots;
          a.amt += (ba ?? 0) + (sa ?? 0);
          const pd = a.perDay.get(di) ?? [0, 0];
          a.perDay.set(di, [pd[0] + net, pd[1] + netLots]);
          a.branches.add(f.label);
          if (dates[di] > a.last) a.last = dates[di];
          m.set(code, a);
        }
      }
    }
    const v = (a: Agg) => (unit === "amt" ? a.net : a.netLots);
    // 上榜天數、買超天數以交易日計（全部分點時同一天各分點合併）
    for (const a of m.values()) {
      a.days = a.perDay.size;
      a.buyDays = [...a.perDay.values()].filter(([n, l]) => (unit === "amt" ? n : l) > 0).length;
    }
    const all = [...m.values()].filter((a) => v(a) !== 0);
    return {
      buys: all.filter((a) => v(a) > 0).sort((a, b) => v(b) - v(a)),
      sells: all.filter((a) => v(a) < 0).sort((a, b) => v(a) - v(b)),
      names,
    };
  }, [files, from, unit, dates]);

  const suggestions = useMemo(() => Object.entries(names).map(([code, name]) => ({ code, name })), [names]);

  if (index.error) return <Empty>分點資料尚未產生。</Empty>;
  if (!index.data) return <Empty>載入中…</Empty>;
  if (!dates.length) return <Empty>分點資料尚未產生，下一次排程抓取後就會出現。</Empty>;

  const allIds = index.data.branches.map((_, i) => i);
  const label = !ids.length ? "未選分點" : ids.length === allIds.length ? "全部追蹤分點"
    : ids.length <= 2 ? ids.map((i) => index.data!.branches[i]).join("＋") : `${ids.length} 個分點`;
  const toggle = (i: number) => setPicked(ids.includes(i) ? ids.filter((x) => x !== i) : [...ids, i]);
  const v = (a: Agg) => (unit === "amt" ? a.net : a.netLots);
  const fmt = (a: Agg) => (unit === "amt" ? signed(wan(a.net), a.net) : signed(`${a.netLots.toLocaleString()} 張`, a.netLots));
  const buyTotal = buys.reduce((s, a) => s + a.net, 0);
  const sellTotal = sells.reduce((s, a) => s + a.net, 0);

  const cols: Column<Agg>[] = [
    {
      key: "stock", label: "股票", sort: (a) => a.code,
      render: (a) => (
        <button onClick={() => setStock(a.code)} className="inline-flex items-center gap-2 hover:text-[#00d4aa]">
          <span className="text-slate-200">{names[a.code] ?? a.code}</span>
          <span className="font-mono text-xs text-slate-500">{a.code}</span>
        </button>
      ),
    },
    { key: "net", label: unit === "amt" ? "累積買賣超" : "累積買賣超（張）", align: "right", sort: (a) => Math.abs(v(a)), render: (a) => <span className={color(v(a))}>{fmt(a)}</span> },
    {
      key: "other", label: unit === "amt" ? "張數" : "金額", align: "right",
      render: (a) => <span className="text-slate-400">{unit === "amt" ? `${signed(a.netLots.toLocaleString(), a.netLots)} 張` : signed(wan(a.net), a.net)}</span>,
    },
    { key: "days", label: "買超／上榜天數", align: "right", sort: (a) => a.buyDays, render: (a) => <span className="text-slate-400">{a.buyDays}／{a.days}</span> },
    ...(multi ? [{ key: "br", label: "分點數", align: "right" as const, sort: (a: Agg) => a.branches.size, render: (a: Agg) => <span className="text-slate-300" title={[...a.branches].join("、")}>{a.branches.size}</span> }] : []),
    { key: "last", label: "最近上榜", align: "right", sort: (a) => a.last, render: (a) => <span className="text-slate-500">{md(a.last)}</span> },
  ];

  return (
    <div>
      <Note>
        追蹤指定券商分點每天買賣了哪些股票。資料來自券商網站的「分點進出」排行，每個分點每天只列買超、賣超各前 50 名（金額與張數排行分別取），
        所以累積數字是這些上榜紀錄的加總，不是完整成交明細。金額以「萬」顯示，紅色為買超、綠色為賣超。
      </Note>

      <div className="flex flex-wrap items-center gap-1.5 mb-4">
        {index.data.branches.map((b, i) => (
          <button
            key={b}
            onClick={() => toggle(i)}
            aria-pressed={ids.includes(i)}
            className={`px-3 py-1 rounded-md text-xs border ${ids.includes(i) ? "border-[#00d4aa]/60 bg-[#00d4aa]/10 text-white" : "border-[#1e2a3a] text-slate-400 hover:text-slate-200"}`}
          >{ids.includes(i) ? "✓ " : ""}{b}</button>
        ))}
        <span className="mx-1 text-slate-700">|</span>
        <button onClick={() => setPicked(allIds)} className="px-2.5 py-1 rounded-md text-xs border border-[#1e2a3a] text-slate-400 hover:text-[#00d4aa]">全選</button>
        <button onClick={() => setPicked([])} className="px-2.5 py-1 rounded-md text-xs border border-[#1e2a3a] text-slate-400 hover:text-[#00d4aa]">清除</button>
        <span className="text-[11px] text-slate-500 ml-1">可複選，多個分點會合併計算</span>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <Pills<Period> value={period} onChange={setPeriod} options={[
          { value: "1", label: "最新一日" }, { value: "5", label: "近 5 日" }, { value: "10", label: "近 10 日" },
          { value: "20", label: "近 20 日" }, { value: "60", label: "近 60 日" },
        ]} />
        <Pills<Unit> value={unit} onChange={setUnit} options={[{ value: "amt", label: "依金額" }, { value: "lots", label: "依張數" }]} />
        <span className="text-xs text-slate-500 font-mono">{md(dates[from])} ～ {md(dates.at(-1)!)}（{dates.length - from} 個交易日）</span>
      </div>

      {!ids.length ? <Empty>請至少選一個分點。</Empty> : !files ? <Empty>載入中…</Empty> : (
        <>
          <KpiRow>
            <Kpi label="分點" value={label} />
            <Kpi label="累積買超" value={signed(wan(buyTotal), buyTotal)} sub={`· ${buys.length} 檔`} color="text-[#ef4444]" />
            <Kpi label="累積賣超" value={wan(sellTotal)} sub={`· ${sells.length} 檔`} color="text-[#22c55e]" />
            <Kpi label="淨買賣超" value={signed(wan(buyTotal + sellTotal), buyTotal + sellTotal)} color={color(buyTotal + sellTotal)} />
          </KpiRow>

          <div className="mb-8">
            <SearchBox placeholder="查個股在這些分點的每日買賣" items={suggestions} onPick={setStock} />
            {stock && <StockDetail code={stock} name={names[stock] ?? stock} files={files} dates={dates} from={from} onClose={() => setStock("")} />}
          </div>

          <div className="grid xl:grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-semibold text-[#ef4444] mb-2">累積買超</h3>
              {buys.length ? <SortTable rows={buys} columns={cols} rowKey={(a) => a.code} initialSort={{ key: "net", desc: true }} limit={30} rank /> : <Empty>沒有買超紀錄。</Empty>}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-[#22c55e] mb-2">累積賣超</h3>
              {sells.length ? <SortTable rows={sells} columns={cols} rowKey={(a) => a.code} initialSort={{ key: "net", desc: true }} limit={30} rank /> : <Empty>沒有賣超紀錄。</Empty>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function StockDetail({ code, name, files, dates, from, onClose }: {
  code: string; name: string; files: BranchFile[]; dates: string[]; from: number; onClose: () => void;
}) {
  const days = dates.slice(from).reverse();
  const byBranch = files.map((f) => {
    const m = new Map((f.rows[code] ?? []).map((c) => [c[0], c]));
    const cells = days.map((d) => m.get(dates.indexOf(d)));
    const total = cells.reduce((s, c) => s + (c && c[1] != null && c[2] != null ? c[1] - c[2] : 0), 0);
    return { label: f.label, cells, total };
  }).filter((b) => b.cells.some(Boolean));

  return (
    <div className="mt-4 rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4">
      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-lg font-bold text-white">{name}</span>
        <span className="font-mono text-sm text-slate-500">{code}</span>
        <button onClick={onClose} className="ml-auto text-xs text-slate-500 hover:text-[#00d4aa]">關閉</button>
      </div>
      {!byBranch.length ? <p className="text-sm text-slate-500">這段期間追蹤的分點都沒有買賣這檔股票（或未進前 50 名）。</p> : (
        <div className="overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr className="text-slate-500">
                <th className="text-left font-normal pr-4 py-1">分點</th>
                <th className="text-right font-normal pr-4 py-1">合計</th>
                {days.map((d) => <th key={d} className="text-right font-normal px-2 py-1 font-mono">{md(d)}</th>)}
              </tr>
            </thead>
            <tbody>
              {byBranch.map((b) => (
                <tr key={b.label} className="border-t border-[#1e2a3a]/60">
                  <td className="pr-4 py-1.5 text-slate-300 whitespace-nowrap">{b.label}</td>
                  <td className={`pr-4 py-1.5 text-right font-mono whitespace-nowrap ${color(b.total)}`}>{signed(wan(b.total), b.total)}</td>
                  {b.cells.map((c, i) => {
                    const net = c && c[1] != null && c[2] != null ? c[1] - c[2] : null;
                    return <td key={i} className={`px-2 py-1.5 text-right font-mono whitespace-nowrap ${net == null ? "text-slate-700" : color(net)}`}>{net == null ? "·" : signed(wan(net), net)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
