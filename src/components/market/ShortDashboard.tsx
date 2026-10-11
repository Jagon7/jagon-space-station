"use client";

import { Fragment, useMemo, useState } from "react";
import { ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";

// [代號, 名稱, 市場, 收盤, 5日%, 20日%, 融資餘額, 融資增減, 融券餘額, 融券增減, 券5日增減, 券20日增減, 券資比%, 回補天數, 資券相抵, 借券賣出餘額, 借券5日增減, 5日均量]
type R = [string, string, number, number, number | null, number | null, number, number, number, number, number | null, number | null, number | null, number | null, number, number, number | null, number];
type Data = { date: string; rows: R[] };
type Hist = { n: string; h: [string, number, number, number, number][] };
type View = "squeeze" | "ratio" | "sUp" | "sDown" | "sbl" | "cover";

const VIEWS: { value: View; label: string; desc: string }[] = [
  { value: "squeeze", label: "軋空候選", desc: "券資比 ≥ 10%、融券 ≥ 300 張，而且近 5 日股價上漲——空單正在被套、可能被迫回補（依券資比排序）" },
  { value: "ratio", label: "券資比排行", desc: "融券餘額 ÷ 融資餘額。越高代表看空的人相對越多，股價一旦上漲越容易出現軋空" },
  { value: "cover", label: "回補天數", desc: "融券餘額 ÷ 近 5 日平均成交量：空單要用幾天的成交量才能全部買回，越大越容易軋空" },
  { value: "sUp", label: "融券大增", desc: "近 5 日融券增加最多" },
  { value: "sDown", label: "融券回補", desc: "近 5 日融券減少最多（空單回補）" },
  { value: "sbl", label: "借券賣出增加", desc: "近 5 日借券賣出餘額增加最多（法人放空的主要管道）" },
];
const STOCK = /^[1-9]\d{3}$/;
const isSqueeze = (r: R) => (r[12] ?? 0) >= 10 && r[8] >= 300 && (r[4] ?? 0) > 0;
const fmt = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());
const sgn = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toLocaleString()}`);
const pf = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-slate-500" : v > 0 ? "text-[#ef4444]" : "text-[#22c55e]");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;

function Detail({ code }: { code: string }) {
  const { data, error } = useStaticJson<Hist>(`market/short/${code}.json`);
  if (!data) return <div className="py-8 text-center text-xs text-slate-500">{error ? "沒有歷史資料" : "載入中…"}</div>;
  const rows = data.h.map(([d, c, m, s, b]) => ({ d, c, m, s, b }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={rows} margin={{ top: 5, right: 0, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" />
        <XAxis dataKey="d" tickFormatter={md} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={20} />
        <YAxis yAxisId="v" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis yAxisId="p" orientation="right" domain={["auto", "auto"]} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ background: "#0d1220", border: "1px solid #1e2a3a", fontSize: 12 }} labelStyle={{ color: "#94a3b8" }}
          formatter={(v, n) => [typeof v === "number" ? v.toLocaleString() : String(v), String(n)]} />
        <Legend formatter={(v) => <span className="text-xs text-slate-400">{v}</span>} />
        <Bar yAxisId="v" dataKey="s" name="融券餘額（張）" fill="#22c55e" fillOpacity={0.7} />
        <Bar yAxisId="v" dataKey="b" name="借券賣出餘額（張）" fill="#a78bfa" fillOpacity={0.6} />
        <Line yAxisId="p" dataKey="c" name="收盤價" stroke="#e2e8f0" dot={false} strokeWidth={1.5} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function ShortDashboard() {
  const { data, error } = useStaticJson<Data>("market/short.json");
  const [view, setView] = useState<View>("squeeze");
  const [etf, setEtf] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [only, setOnly] = useState<string | null>(null);

  const rows = useMemo(() => {
    let rs = (data?.rows ?? []).filter((r) => etf || STOCK.test(r[0]));
    if (only) return (data?.rows ?? []).filter((r) => r[0] === only);
    const by = (f: (r: R) => number | null) => [...rs].filter((r) => f(r) != null).sort((a, b) => f(b)! - f(a)!);
    switch (view) {
      case "squeeze":
        rs = rs.filter(isSqueeze);
        return rs.sort((a, b) => (b[12] ?? 0) - (a[12] ?? 0));
      case "ratio": return by((r) => (r[8] >= 100 ? r[12] : null));
      case "cover": return by((r) => (r[8] >= 100 ? r[13] : null));
      case "sUp": return by((r) => r[10]);
      case "sDown": return by((r) => (r[10] == null ? null : -r[10]));
      case "sbl": return by((r) => r[16]);
    }
  }, [data, view, etf, only]);

  if (!data) return <div className="py-16 text-center text-sm text-slate-500 font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.rows.length) return <Empty>融資券資料累積中。</Empty>;
  const all = data.rows.filter((r) => STOCK.test(r[0]));
  const tot = (i: number) => all.reduce((s, r) => s + (r[i] as number), 0);
  const squeeze = all.filter(isSqueeze).length;
  const desc = VIEWS.find((v) => v.value === view)!.desc;

  return (
    <div>
      <Note>
        每天收盤後的融資融券餘額與借券賣出餘額（上市櫃，單位：張），看空方力道的消長、找可能被軋空的股票。
        資料日 {data.date}。券資比、回補天數排行只列融券 100 張以上的股票。點一列看近 60 天的融券、借券與股價。
      </Note>
      <KpiRow>
        <Kpi label="融券總餘額" value={fmt(tot(8))} unit="張" sub={sgn(tot(9))} />
        <Kpi label="融資總餘額" value={fmt(tot(6))} unit="張" sub={sgn(tot(7))} />
        <Kpi label="借券賣出總餘額" value={fmt(tot(15))} unit="張" />
        <Kpi label="軋空候選" value={squeeze} unit="檔" color="text-[#f59e0b]" />
      </KpiRow>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-2">
        <Pills<View> value={view} onChange={(v) => { setView(v); setOnly(null); setOpen(null); }} options={VIEWS.map(({ value, label }) => ({ value, label }))} />
        <div className="sm:ml-auto flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-slate-400"><input type="checkbox" checked={etf} onChange={(e) => setEtf(e.target.checked)} />含 ETF</label>
          <SearchBox placeholder="查個股，例如 2330" items={data.rows.map((r) => ({ code: r[0], name: r[1] }))} onPick={(c) => { setOnly(c); setOpen(c); }} />
        </div>
      </div>
      <p className="text-xs text-slate-500 mb-3">{only ? <button onClick={() => { setOnly(null); setOpen(null); }} className="hover:text-[#00d4aa]">← 回到排行</button> : desc}</p>

      {!rows.length ? <Empty>目前沒有符合條件的股票。</Empty> : (
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-x-auto">
          <table className="w-full text-sm whitespace-nowrap">
            <thead>
              <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500 text-right">
                <th className="pl-4 py-2.5 font-normal text-left w-8">#</th>
                <th className="px-3 py-2.5 font-normal text-left">股票</th><th className="px-3 py-2.5 font-normal">收盤</th>
                <th className="px-3 py-2.5 font-normal">5 日</th><th className="px-3 py-2.5 font-normal">20 日</th>
                <th className="px-3 py-2.5 font-normal">融資餘額</th><th className="px-3 py-2.5 font-normal">融券餘額</th>
                <th className="px-3 py-2.5 font-normal">券資比</th><th className="px-3 py-2.5 font-normal">券增減 1 日／5 日</th>
                <th className="px-3 py-2.5 font-normal">回補天數</th><th className="px-3 py-2.5 font-normal">借券賣出餘額</th><th className="px-3 py-2.5 font-normal">借券 5 日</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 100).map((r, i) => (
                <Fragment key={r[0]}>
                  <tr onClick={() => setOpen(open === r[0] ? null : r[0])} className="border-b border-[#1e2a3a]/60 hover:bg-[#111a2c] cursor-pointer text-right font-mono">
                    <td className="pl-4 py-2 text-left text-xs text-slate-600">{i + 1}</td>
                    <td className="px-3 py-2 text-left font-sans">
                      <span className="inline-flex items-center gap-1.5">
                        {open === r[0] ? <ChevronDown className="w-3.5 h-3.5 text-[#00d4aa]" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-600" />}
                        <span className="text-slate-200">{r[1]}</span><span className="font-mono text-xs text-slate-500">{r[0]}</span>
                        {r[2] === 1 && <span className="text-[10px] text-slate-600">櫃</span>}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-300">{r[3]}</td>
                    <td className={`px-3 py-2 ${tone(r[4])}`}>{pf(r[4])}</td>
                    <td className={`px-3 py-2 ${tone(r[5])}`}>{pf(r[5])}</td>
                    <td className="px-3 py-2 text-slate-400">{fmt(r[6])}</td>
                    <td className="px-3 py-2 text-slate-200">{fmt(r[8])}</td>
                    <td className={`px-3 py-2 ${(r[12] ?? 0) >= 30 ? "text-[#f59e0b] font-semibold" : "text-slate-300"}`}>{r[12] == null ? "—" : `${r[12]}%`}</td>
                    <td className="px-3 py-2"><span className={tone(r[9])}>{sgn(r[9])}</span><span className="text-slate-600"> / </span><span className={tone(r[10])}>{sgn(r[10])}</span></td>
                    <td className="px-3 py-2 text-slate-300">{r[13] ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-400">{fmt(r[15])}</td>
                    <td className={`px-3 py-2 ${tone(r[16])}`}>{sgn(r[16])}</td>
                  </tr>
                  {open === r[0] && (
                    <tr className="border-b border-[#1e2a3a]/60 bg-[#0a0f1a]"><td colSpan={12} className="px-4 py-3"><Detail code={r[0]} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {rows.length > 100 && <div className="px-4 py-2 text-[11px] text-slate-600 border-t border-[#1e2a3a]">只列前 100 檔，可用右上搜尋查其他股票</div>}
        </div>
      )}
    </div>
  );
}
