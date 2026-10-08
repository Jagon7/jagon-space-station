"use client";

import { useMemo, useState } from "react";
import type { ActiveData, CoreData } from "./data";
import { fmtSignedLots, fmtYi, mmdd } from "./data";
import { Empty, Kpi, KpiRow, Note, Pills, SortTable, type Column } from "@/components/data-ui";

type Agg = { code: string; diff: number; value: number; etfs: Set<number> };
type Period = "1" | "5" | "10" | "20";
type Mode = "raw" | "adj";

export default function ActiveTab({ core, active, onStock }: {
  core: CoreData; active: ActiveData; onStock: (code: string) => void;
}) {
  const activeIdx = useMemo(
    () => core.etfs.map((e, i) => [e, i] as const).filter(([e]) => e.k === "A").map(([, i]) => i),
    [core],
  );
  const [period, setPeriod] = useState<Period>("1");
  const [mode, setMode] = useState<Mode>("raw");
  const [picked, setPicked] = useState<Set<number>>(() => new Set(activeIdx));

  const { buys, sells, used } = useMemo(() => {
    const n = Number(period);
    const m = new Map<string, Agg>();
    let used = 0;
    for (const idx of picked) {
      const evs = (active.events[idx] ?? []).slice(-n);
      if (evs.length) used++;
      for (const [, , , rows] of evs) {
        for (const [code, raw, adj, close] of rows) {
          const d = mode === "raw" ? raw : adj;
          if (!d) continue;
          const a = m.get(code) ?? { code, diff: 0, value: 0, etfs: new Set<number>() };
          a.diff += d;
          a.value += close ? (d * close) / 1e8 : 0;
          a.etfs.add(idx);
          m.set(code, a);
        }
      }
    }
    const all = [...m.values()].filter((a) => a.diff !== 0);
    return {
      buys: all.filter((a) => a.diff > 0).sort((a, b) => b.value - a.value),
      sells: all.filter((a) => a.diff < 0).sort((a, b) => a.value - b.value),
      used,
    };
  }, [active, picked, period, mode]);

  const latest = activeIdx.map((i) => core.etfs[i].d).sort().at(-1);
  const buyVal = buys.reduce((s, a) => s + a.value, 0);
  const sellVal = sells.reduce((s, a) => s + a.value, 0);
  const consensus = [...buys].sort((a, b) => b.etfs.size - a.etfs.size || b.value - a.value)[0];

  const cols = (sign: 1 | -1): Column<Agg>[] => [
    {
      key: "stock", label: "股票", sort: (a) => a.code,
      render: (a) => (
        <button onClick={() => onStock(a.code)} className="inline-flex items-center gap-2 hover:text-[#00d4aa]">
          <span className="text-slate-200">{core.names[a.code] ?? active.names[a.code] ?? a.code}</span>
          <span className="font-mono text-xs text-slate-500">{a.code}</span>
        </button>
      ),
    },
    { key: "n", label: sign > 0 ? "買進 ETF 數" : "賣出 ETF 數", align: "right", sort: (a) => a.etfs.size, render: (a) => <span className="text-slate-300">{a.etfs.size}</span> },
    { key: "diff", label: "合計增減", align: "right", sort: (a) => Math.abs(a.diff), render: (a) => <span className={sign > 0 ? "text-[#ef4444]" : "text-[#22c55e]"}>{fmtSignedLots(a.diff, a.code)}</span> },
    { key: "value", label: "金額（億）", align: "right", sort: (a) => Math.abs(a.value), render: (a) => <span className={sign > 0 ? "text-[#ef4444]" : "text-[#22c55e]"}>{fmtYi(a.value, true)}</span> },
  ];

  const toggle = (i: number) => {
    const s = new Set(picked);
    if (s.has(i)) s.delete(i); else s.add(i);
    setPicked(s);
  };

  return (
    <div>
      <Note>
        主動式 ETF（代號 A 結尾）每次公布持股，與自己前一次比較的股數增減，依個股加總成買賣超；金額 = 增減股數 × 該日收盤價。
        「扣除申購贖回」：先把前一次持股依受益單位數變化等比例放大縮小，再算增減，剩下的才是經理人主動調整。只計台股。
      </Note>
      <KpiRow>
        <Kpi label="主動式 ETF" value={`${used}/${activeIdx.length}`} unit="檔" sub={`· 最新 ${mmdd(latest)}`} />
        <Kpi label="合計買超金額" value={fmtYi(buyVal, true)} unit="億" sub={`· ${buys.length} 檔`} color="text-[#ef4444]" />
        <Kpi label="合計賣超金額" value={fmtYi(sellVal, true)} unit="億" sub={`· ${sells.length} 檔`} color="text-[#22c55e]" />
        <Kpi
          label="最多 ETF 同時買進"
          value={consensus ? (core.names[consensus.code] ?? consensus.code) : "—"}
          sub={consensus ? `${consensus.etfs.size} 檔 ETF` : undefined}
        />
      </KpiRow>

      <div className="flex flex-wrap gap-3 mb-4">
        <Pills<Period> value={period} onChange={setPeriod} options={[
          { value: "1", label: "最新一次" }, { value: "5", label: "近 5 次" }, { value: "10", label: "近 10 次" }, { value: "20", label: "近 20 次" },
        ]} />
        <Pills<Mode> value={mode} onChange={setMode} options={[
          { value: "raw", label: "原始增減" }, { value: "adj", label: "扣除申購贖回" },
        ]} />
      </div>

      <div className="flex flex-wrap gap-1.5 mb-6">
        <button onClick={() => setPicked(new Set(activeIdx))} className="px-2.5 py-1 rounded-md text-xs border border-[#1e2a3a] text-slate-400 hover:text-[#00d4aa]">全選</button>
        <button onClick={() => setPicked(new Set())} className="px-2.5 py-1 rounded-md text-xs border border-[#1e2a3a] text-slate-400 hover:text-[#00d4aa]">全不選</button>
        {activeIdx.map((i) => {
          const e = core.etfs[i];
          const on = picked.has(i);
          return (
            <button
              key={i}
              onClick={() => toggle(i)}
              title={`資料日 ${e.d}`}
              className={`px-2.5 py-1 rounded-md text-xs border transition-colors ${
                on ? "border-[#00d4aa]/50 bg-[#00d4aa]/10 text-slate-200" : "border-[#1e2a3a] text-slate-600"
              }`}
            >
              <span className="font-mono">{e.c}</span> {e.n.replace(/^主動/, "")}
            </button>
          );
        })}
      </div>

      {!buys.length && !sells.length ? (
        <Empty>所選期間還沒有可比較的持股變化。</Empty>
      ) : (
        <div className="grid xl:grid-cols-2 gap-4">
          <div>
            <h3 className="text-sm font-semibold text-[#ef4444] mb-2">買超</h3>
            <SortTable rows={buys} columns={cols(1)} rowKey={(a) => a.code} initialSort={{ key: "value", desc: true }} limit={30} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[#22c55e] mb-2">賣超</h3>
            <SortTable rows={sells} columns={cols(-1)} rowKey={(a) => a.code} initialSort={{ key: "value", desc: true }} limit={30} />
          </div>
        </div>
      )}
    </div>
  );
}
