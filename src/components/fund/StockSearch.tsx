"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ComposedChart, Bar, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell } from "recharts";
import { useStaticJson } from "@/lib/static-json";
import { SearchBox } from "@/components/data-ui";
import { pf, tone } from "./RevenueDashboard";

type Index = Record<string, [string, string, string, number, number] | string>;
type Rev = { n: string; h: [string, number | null, number | null][] };
type Inc = { n: string; h: [string, number | null, number | null, number | null, number | null, number | null][] };
type Short = { cols: string[]; rows: (string | number | null)[][]; date: string };
type Core = { etfs: { c: string; n: string }[]; holders: Record<string, [number, number, number, number, number | null][]> };
type Events = { exdiv: (string | number | null)[][]; agm: string[][]; conf: string[][] };
type NextDay = { rows: (string | number | null)[][] };
type Insider = { names: Record<string, string>; cases: (string | number | null)[][] };

const TODAY = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const tip = { contentStyle: { background: "#0d1220", border: "1px solid #1e2a3a", fontSize: 12 }, labelStyle: { color: "#94a3b8" } };

function Card({ title, href, children }: { title: string; href?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {href && <Link href={href} className="text-[11px] text-slate-500 hover:text-[#00d4aa]">完整頁面 →</Link>}
      </div>
      {children}
    </div>
  );
}
const Muted = ({ children }: { children: React.ReactNode }) => <p className="text-xs text-slate-500 py-3">{children}</p>;

function Detail({ code, idx }: { code: string; idx: Index }) {
  const info = idx[code] as [string, string, string, number, number] | undefined;
  const rev = useStaticJson<Rev>(`fund/revenue/${code}.json`);
  const inc = useStaticJson<Inc>(`fund/income/${code}.json`);
  const short = useStaticJson<Short>("market/short.json");
  const core = useStaticJson<Core>("etf/core.json");
  const ev = useStaticJson<Events>("fund/events.json");
  const nd = useStaticJson<NextDay>("market/nextday.json");
  const ins = useStaticJson<Insider>("insider/index.json");

  const s = short.data?.rows.find((r) => r[0] === code);
  const holders = core.data?.holders[code] ?? [];
  const events = useMemo(() => !ev.data ? [] : [
    ...ev.data.exdiv.filter((r) => r[1] === code).map((r) => ({ d: r[0] as string, t: "除權息", x: r[5] ? `現金 ${r[5]} 元` : String(r[4]) })),
    ...ev.data.agm.filter((r) => r[1] === code).map((r) => ({ d: r[0], t: "股東會", x: r[4] })),
    ...ev.data.conf.filter((r) => r[1] === code).map((r) => ({ d: r[0], t: "法說會", x: `${r[4]} ${r[5]}` })),
  ].filter((e) => e.d >= TODAY).sort((a, b) => a.d.localeCompare(b.d)), [ev.data, code]);
  const limits = nd.data?.rows.filter((r) => r[1] === code) ?? [];
  const insCases = ins.data?.cases.filter((r) => r[0] === code) ?? [];

  if (!info) return <p className="text-sm text-slate-500 py-10 text-center">查無這檔股票。</p>;
  const [name, mk, ind, close, chg] = info;
  const revRows = (rev.data?.h ?? []).slice(-24).map(([m, v, y]) => ({ m: m.slice(2).replace("-", "/"), v: v == null ? null : v / 1e5, y }));
  const incRows = (inc.data?.h ?? []).map(([q, , g, , , e]) => ({ q: `${q.slice(2, 4)}Q${q.slice(-1)}`, e, g }));
  const lastRev = rev.data?.h.at(-1);

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-5">
        <h2 className="text-2xl font-bold text-white">{name}</h2>
        <span className="font-mono text-slate-400">{code}</span>
        <span className="text-xs text-slate-500">{mk}{ind ? `・${ind}` : ""}</span>
        <span className="font-mono text-xl text-slate-100">{close}</span>
        <span className={`font-mono ${tone(chg)}`}>{chg > 0 ? "+" : ""}{chg}（{pf(close - chg ? (chg / (close - chg)) * 100 : null)}）</span>
        <span className="text-[11px] text-slate-600">{String(idx._date ?? "")} 收盤</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="月營收（億元）" href="/revenue">
          {!revRows.length ? <Muted>沒有月營收資料。</Muted> : <>
            <div className="text-xs text-slate-400 mb-2">最新 {lastRev?.[0]}：{lastRev?.[1] != null ? (lastRev[1] / 1e5).toFixed(2) : "—"} 億，年增 <span className={tone(lastRev?.[2])}>{pf(lastRev?.[2])}</span></div>
            <ResponsiveContainer width="100%" height={160}>
              <ComposedChart data={revRows} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
                <XAxis dataKey="m" tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={16} />
                <YAxis yAxisId="v" tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="y" orientation="right" hide />
                <Tooltip {...tip} formatter={(v, n) => [typeof v === "number" ? v.toFixed(n === "v" ? 2 : 1) : String(v), n === "v" ? "營收（億）" : "年增%"]} />
                <Bar yAxisId="v" dataKey="v" fill="#3b82f6" fillOpacity={0.75} />
                <Line yAxisId="y" dataKey="y" stroke="#f59e0b" dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </>}
        </Card>
        <Card title="季報：單季 EPS 與毛利率" href="/quarterly">
          {!incRows.length ? <Muted>沒有財報資料。</Muted> : (
            <ResponsiveContainer width="100%" height={180}>
              <ComposedChart data={incRows} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
                <XAxis dataKey="q" tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="e" tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="g" orientation="right" hide />
                <Tooltip {...tip} formatter={(v, n) => [typeof v === "number" ? v.toFixed(n === "e" ? 2 : 1) : String(v), n === "e" ? "EPS" : "毛利率%"]} />
                <Bar yAxisId="e" dataKey="e">{incRows.map((r) => <Cell key={r.q} fill={(r.e ?? 0) >= 0 ? "#ef4444" : "#22c55e"} fillOpacity={0.75} />)}</Bar>
                <Line yAxisId="g" dataKey="g" stroke="#f59e0b" dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="融資融券與借券" href="/short">
          {!s ? <Muted>沒有融資券資料（可能不是信用交易標的）。</Muted> : (
            <div className="grid grid-cols-3 gap-3 text-center">
              {[["融資餘額", s[6], "張"], ["融券餘額", s[8], "張"], ["券資比", s[12], "%"], ["融券 5 日增減", s[10], "張"], ["借券賣出餘額", s[15], "張"], ["借券 5 日增減", s[16], "張"]].map(([l, v, u]) => (
                <div key={l as string}><div className="text-[11px] text-slate-500">{l}</div><div className="font-mono text-slate-200">{v == null ? "—" : `${(v as number).toLocaleString()}${u === "%" ? "%" : ""}`}</div></div>
              ))}
            </div>
          )}
        </Card>
        <Card title={`ETF 持有（${holders.length} 檔）`} href={`/etf-flow?stock=${code}`}>
          {!holders.length ? <Muted>目前沒有追蹤中的 ETF 持有。</Muted> : (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {[...holders].sort((a, b) => b[2] - a[2]).slice(0, 12).map((h) => (
                <div key={h[0]} className="flex justify-between text-xs"><span className="text-slate-300">{core.data!.etfs[h[0]]?.n} <span className="font-mono text-slate-500">{core.data!.etfs[h[0]]?.c}</span></span><span className="font-mono text-slate-400">{h[2].toFixed(2)}%</span></div>
              ))}
            </div>
          )}
        </Card>
        <Card title="近期事件" href="/events">
          {!events.length ? <Muted>未來沒有排定的除權息、股東會或法說會。</Muted> : events.map((e, i) => (
            <div key={i} className="flex gap-3 text-xs py-1"><span className="font-mono text-slate-400">{e.d}</span><span className="text-[#f59e0b]">{e.t}</span><span className="text-slate-300 truncate">{e.x}</span></div>
          ))}
        </Card>
        <Card title="內部人與漲停紀錄" href={`/insider?tab=history&stock=${code}`}>
          <div className="text-xs space-y-1.5">
            <div className="text-slate-400">近 2 年內部人大額買賣：{insCases.length ? insCases.slice(0, 3).map((c, i) => (
              <span key={i} className={`ml-2 ${Number(c[2]) > 0 ? "text-[#ef4444]" : "text-[#22c55e]"}`}>{String(c[3]).slice(2)}{Number(c[2]) > 0 ? " 買" : " 賣"}</span>)) : <span className="ml-1 text-slate-600">無</span>}</div>
            <div className="text-slate-400">近半年漲停 <span className="text-slate-200 font-mono">{limits.length}</span> 次{limits.length ? `，最近 ${limits.at(-1)![0]}` : ""}</div>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default function StockSearch() {
  const router = useRouter();
  const params = useSearchParams();
  const idx = useStaticJson<Index>("stocks.json");
  const [code, setCode] = useState(params.get("code") ?? "");
  const items = useMemo(() => Object.entries(idx.data ?? {}).filter(([k]) => k !== "_date")
    .map(([c, v]) => ({ code: c, name: (v as string[])[0], hint: (v as string[])[2] || undefined })), [idx.data]);
  const pick = (c: string) => { setCode(c); router.replace(`?code=${c}`, { scroll: false }); };

  return (
    <div>
      <div className="mb-6"><SearchBox placeholder="輸入股號或名稱，例如 2330 或 台積電" items={items} onPick={pick} /></div>
      {!idx.data ? <p className="text-sm text-slate-500 font-mono">{idx.error ? "資料載入失敗" : "載入中…"}</p>
        : code ? <Detail key={code} code={code} idx={idx.data} />
          : <p className="text-sm text-slate-500 py-10 text-center">輸入股票代號或名稱，整合月營收、季報、融資券、ETF 持有、事件、內部人與漲停紀錄。</p>}
    </div>
  );
}
