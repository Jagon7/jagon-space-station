"use client";

import { Fragment, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";
import InsiderChart, { money, monthSides, type Company, type Mode } from "./InsiderChart";

// 事前申報：[日期, 代號, 公司, 市場, 身分, 姓名, 方式, 一般交易股數, 每日上限, 受讓人, 目前持股, 預定轉讓, 轉讓後, 有效期間, 最新收盤]
type Transfer = [string, string, string, string, string, string, string, number, number, string, number, number, number, string, number | null];
// 最新月異動：[代號, 名稱, 集中買股數, 集中賣股數, 淨額(估), 均價, 主要人物, 人數]
type Recent = [string, string, number, number, number | null, number | null, string, number];
// 歷史案例：[代號, 名稱, 方向(1買/-1賣), 起月, 迄月, 淨額, 均價, 主要人物, 人數, 結束後3個月%, 結束至今%]
type Case = [string, string, 1 | -1, string, string, number, number | null, string, number, number | null, number | null];
type Index = { latest: string | null; months: string[]; names: Record<string, string>; recent: Recent[]; cases: Case[]; transfers: Transfer[] };

type Tab = "recent" | "history";
type RecentView = "transfer" | "month";
type Days = "7" | "30" | "90";
type Method = "all" | "market" | "specific" | "other";
type Side = "all" | "buy" | "sell";
type MinAmt = "1e7" | "1e8" | "1e9";
type HistSort = "amount" | "recent";

const RED = "text-[#ef4444]", GREEN = "text-[#22c55e]";
const ym = (s: string | null) => (s ? `${s.slice(0, 4)}/${Number(s.slice(5, 7))}` : "—");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const lots = (v: number) => (v ? Math.round(v / 1000).toLocaleString() : "—");
const signed = (v: number) => (v ? `${v > 0 ? "+" : "−"}${money(Math.abs(v))}` : "0");
const pctFmt = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-slate-500" : v > 0 ? RED : GREEN);
const px = (v: number) => (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2));
const period = (a: string, b: string) => (a === b ? ym(a) : `${ym(a)} – ${a.slice(0, 4) === b.slice(0, 4) ? Number(b.slice(5, 7)) : ym(b)}`);

function methodKind(m: string): Exclude<Method, "all"> {
  if (/一般交易|盤後|鉅額|拍賣|標購/.test(m)) return "market";
  if (m.includes("洽特定人")) return "specific";
  return "other";
}
const METHOD_STYLE: Record<Exclude<Method, "all">, string> = {
  market: "bg-[#22c55e]/10 text-[#22c55e] border-[#22c55e]/30",
  specific: "bg-[#f59e0b]/10 text-[#f59e0b] border-[#f59e0b]/30",
  other: "bg-slate-500/10 text-slate-400 border-slate-500/30",
};
const shortMethod = (m: string) => m.replace(/\(每日得轉讓股數限制\)/, "").replace(/\s+/g, "");

function Tag({ kind, children }: { kind: Exclude<Method, "all">; children: React.ReactNode }) {
  return <span className={`inline-block rounded border px-1.5 py-px text-[11px] leading-4 ${METHOD_STYLE[kind]}`}>{children}</span>;
}

function SideTag({ side }: { side: number }) {
  return side > 0
    ? <span className="inline-block rounded px-1.5 py-px text-[11px] leading-4 bg-[#ef4444]/15 text-[#ef4444]">買進</span>
    : <span className="inline-block rounded px-1.5 py-px text-[11px] leading-4 bg-[#22c55e]/15 text-[#22c55e]">賣出</span>;
}

/** 一列一家公司，點了展開細節 */
function CompanyRow({ open, onToggle, head, children }: { open: boolean; onToggle: () => void; head: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className={`border-b border-[#1e2a3a]/70 last:border-0 ${open ? "bg-[#0a0f1a]" : ""}`}>
      <button onClick={onToggle} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#111a2c] transition-colors">
        {open ? <ChevronDown className="w-4 h-4 text-[#00d4aa] shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-600 shrink-0" />}
        <div className="flex-1 min-w-0">{head}</div>
      </button>
      {open && <div className="px-4 sm:px-8 pb-5 pt-1">{children}</div>}
    </div>
  );
}

function ListBox({ children, count, grid, labels }: { children: React.ReactNode; count: number; grid: string; labels: [string, boolean][] }) {
  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#1e2a3a] text-[11px] text-slate-500">
        <span className="w-4 shrink-0" />
        <div className={`hidden sm:grid flex-1 gap-x-4 ${grid}`}>
          {labels.map(([l, right], i) => <span key={i} className={right ? "text-right" : ""}>{i === 0 ? `${l}（${count} 家）` : l}</span>)}
        </div>
        <span className="sm:hidden">共 {count} 家公司・點一列看圖與細節</span>
      </div>
      {children}
    </div>
  );
}

function CompanyName({ code, name, mk }: { code: string; name: string; mk?: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-slate-100 font-medium">{name}</span>
      <span className="ml-1.5 font-mono text-xs text-slate-500">{code}</span>
      {mk === "otc" && <span className="ml-1 text-[10px] text-slate-600">櫃</span>}
    </span>
  );
}

/** 展開後：股價＋內部人買賣圖、月別明細 */
function CompanyDetail({ code, latest, hasData }: { code: string; latest: string | null; hasData: boolean }) {
  const co = useStaticJson<Company>(hasData ? `insider/${code}.json` : null);
  const [mode, setMode] = useState<Mode>("market");
  const [openM, setOpenM] = useState<string | null>(null);
  if (!hasData) return <p className="text-xs text-slate-500 py-2">這家公司近 2 年內部人沒有在集中市場買賣的申報紀錄。</p>;
  if (!co.data) return <div className="py-10 text-center text-xs text-slate-500 font-mono">{co.error ? "資料載入失敗" : "載入中…"}</div>;
  const months = Object.keys(co.data.m).sort().reverse().filter((m) => {
    const { b, s } = monthSides(co.data!.m[m], mode);
    return b || s;
  });
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <span className="text-xs text-slate-500">近 2 年股價與內部人每月買賣（紅＝淨買、綠＝淨賣；標註框是金額最大的幾個月）</span>
        <Pills<Mode> value={mode} onChange={setMode} options={[{ value: "market", label: "集中市場" }, { value: "all", label: "含贈與等" }]} />
      </div>
      {co.data.px.length > 1 ? <InsiderChart co={co.data} latest={latest} mode={mode} /> : <p className="text-xs text-slate-500">沒有股價資料。</p>}
      <div className="mt-3 overflow-x-auto rounded-lg border border-[#1e2a3a]">
        <table className="w-full text-sm whitespace-nowrap">
          <thead>
            <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500 text-right">
              <th className="px-3 py-2 font-normal text-left">月份</th><th className="px-3 py-2 font-normal">均價</th>
              <th className="px-3 py-2 font-normal">買進（張）</th><th className="px-3 py-2 font-normal">賣出（張）</th>
              <th className="px-3 py-2 font-normal">淨額（估）</th><th className="px-3 py-2 font-normal text-left">申報人</th>
            </tr>
          </thead>
          <tbody>
            {months.map((m) => {
              const mo = co.data!.m[m];
              const { b, s, buy, sell } = monthSides(mo, mode);
              const net = mo.avg ? (b - s) * mo.avg : null;
              const ppl = mo.rows.filter((r) => buy(r) || sell(r));
              return (
                <Fragment key={m}>
                  <tr onClick={() => setOpenM(openM === m ? null : m)} className="border-b border-[#1e2a3a]/60 hover:bg-[#111a2c] cursor-pointer text-right font-mono">
                    <td className="px-3 py-2 text-left text-slate-300">{ym(m)}</td>
                    <td className="px-3 py-2 text-slate-400">{mo.avg == null ? "—" : px(mo.avg)}</td>
                    <td className={`px-3 py-2 ${RED}`}>{lots(b)}</td>
                    <td className={`px-3 py-2 ${GREEN}`}>{lots(s)}</td>
                    <td className={`px-3 py-2 ${tone(net)}`}>{net == null ? "—" : signed(net)}</td>
                    <td className="px-3 py-2 text-left text-xs text-slate-500 font-sans whitespace-nowrap">
                      {ppl.slice(0, 2).map((r) => r[0].split("、")[0] + (r[1] && r[1].length <= 4 ? ` ${r[1]}` : "")).join("、")}
                      {ppl.length > 2 && ` 等 ${ppl.length} 人`}
                    </td>
                  </tr>
                  {openM === m && (
                    <tr className="border-b border-[#1e2a3a]/60 bg-[#080c16]">
                      <td colSpan={6} className="px-4 py-2">
                        <table className="w-full text-xs whitespace-nowrap">
                          <thead>
                            <tr className="text-slate-600 text-right">
                              <th className="py-1 font-normal text-left">身分</th><th className="py-1 font-normal text-left">姓名</th>
                              <th className="py-1 font-normal">集中買</th><th className="py-1 font-normal">其它增加</th>
                              <th className="py-1 font-normal">集中賣</th><th className="py-1 font-normal">其它減少</th><th className="py-1 font-normal">月底持股</th>
                            </tr>
                          </thead>
                          <tbody>
                            {mo.rows.map((r, i) => (
                              <tr key={i} className="text-right font-mono">
                                <td className="py-1 pr-2 text-left text-slate-400 font-sans whitespace-nowrap">{r[0]}</td>
                                <td className="py-1 pr-2 text-left text-slate-300 font-sans max-w-[14rem] truncate">{r[1] || "—"}</td>
                                <td className={`py-1 ${RED}`}>{lots(r[2])}</td><td className="py-1 text-[#ef4444]/60">{lots(r[3])}</td>
                                <td className={`py-1 ${GREEN}`}>{lots(r[4])}</td><td className="py-1 text-[#22c55e]/60">{lots(r[5])}</td>
                                <td className="py-1 text-slate-400">{lots(r[6])}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <p className="mt-1 text-[10px] text-slate-600">單位：張。「其它」含贈與、繼承、員工獎酬股票、信託移轉等。</p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------------- 近期公告 ---------------- */

function TransferList({ data, open, setOpen }: { data: Index; open: string | null; setOpen: (c: string | null) => void }) {
  const [days, setDays] = useState<Days>("30");
  const [method, setMethod] = useState<Method>("all");
  const [sort, setSort] = useState<"date" | "value">("date");
  const groups = useMemo(() => {
    const last = data.transfers[0]?.[0];
    if (!last) return [];
    const from = new Date(Date.parse(last) - (Number(days) - 1) * 86400e3).toISOString().slice(0, 10);
    const by = new Map<string, Transfer[]>();
    for (const t of data.transfers) {
      if (t[0] < from || (method !== "all" && methodKind(t[6]) !== method)) continue;
      by.set(t[1], [...(by.get(t[1]) ?? []), t]);
    }
    return [...by.entries()].map(([code, ts]) => {
      const shares = ts.reduce((s, t) => s + t[11], 0);
      const close = ts[0][14];
      const people = new Set(ts.map((t) => t[5])).size;
      const kinds = [...new Set(ts.map((t) => methodKind(t[6])))];
      const hold = ts.reduce((s, t) => s + t[10], 0);
      return { code, name: ts[0][2], mk: ts[0][3], ts, shares, value: close ? shares * close : null, people, kinds, latest: ts[0][0], ratio: hold ? shares / hold : null };
    }).sort((a, b) => (sort === "date" ? b.latest.localeCompare(a.latest) || (b.value ?? 0) - (a.value ?? 0) : (b.value ?? 0) - (a.value ?? 0)));
  }, [data, days, method, sort]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <Pills<Days> value={days} onChange={setDays} options={[{ value: "7", label: "近 7 天" }, { value: "30", label: "近 30 天" }, { value: "90", label: "近 90 天" }]} />
        <Pills<Method> value={method} onChange={setMethod} options={[{ value: "all", label: "全部方式" }, { value: "market", label: "市場賣出" }, { value: "specific", label: "洽特定人" }, { value: "other", label: "贈與・信託等" }]} />
        <Pills<"date" | "value"> value={sort} onChange={setSort} options={[{ value: "date", label: "依日期" }, { value: "value", label: "依金額" }]} />
      </div>
      {!groups.length ? <Empty>這段期間沒有符合條件的事前申報。</Empty> : (
        <ListBox count={groups.length} grid="sm:grid-cols-[minmax(9rem,1.2fr)_6.5rem_minmax(8rem,1fr)_7rem_6rem]" labels={[["公司", false], ["最新申報", false], ["方式・人數", false], ["預定轉讓", true], ["估計金額", true]]}>
          {groups.map((g) => (
            <CompanyRow key={g.code} open={open === g.code} onToggle={() => setOpen(open === g.code ? null : g.code)} head={
              <div className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(9rem,1.2fr)_6.5rem_minmax(8rem,1fr)_7rem_6rem] items-center gap-x-4 gap-y-1">
                <CompanyName code={g.code} name={g.name} mk={g.mk} />
                <span className="text-xs text-slate-400 font-mono text-right sm:text-left whitespace-nowrap">{md(g.latest)}{g.ts.length > 1 ? ` 等 ${g.ts.length} 筆` : ""}</span>
                <span className="flex flex-wrap gap-1">
                  {g.kinds.map((k) => <Tag key={k} kind={k}>{k === "market" ? "市場賣出" : k === "specific" ? "洽特定人" : "贈與・信託等"}</Tag>)}
                  <span className="text-[11px] text-slate-500 self-center">{g.people} 人</span>
                </span>
                <span className="text-right font-mono text-sm text-slate-200">{lots(g.shares)} <span className="text-[10px] text-slate-500">張</span></span>
                <span className="text-right font-mono text-sm text-[#22c55e]">{g.value ? money(g.value) : "—"}</span>
              </div>
            }>
              <div className="overflow-x-auto mb-4 rounded-lg border border-[#1e2a3a]">
                <table className="w-full text-xs whitespace-nowrap">
                  <thead>
                    <tr className="border-b border-[#1e2a3a] text-slate-500 text-right">
                      <th className="px-2 py-1.5 font-normal text-left">申報日</th><th className="px-2 py-1.5 font-normal text-left">身分</th>
                      <th className="px-2 py-1.5 font-normal text-left">姓名</th><th className="px-2 py-1.5 font-normal text-left">方式</th>
                      <th className="px-2 py-1.5 font-normal">預定轉讓（張）</th><th className="px-2 py-1.5 font-normal">占持股</th>
                      <th className="px-2 py-1.5 font-normal">轉讓後（張）</th><th className="px-2 py-1.5 font-normal text-left">受讓人</th>
                      <th className="px-2 py-1.5 font-normal text-left">有效期間</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.ts.map((t, i) => (
                      <tr key={i} className="border-b border-[#1e2a3a]/50 last:border-0 text-right font-mono">
                        <td className="px-2 py-1.5 text-left text-slate-400">{md(t[0])}</td>
                        <td className="px-2 py-1.5 text-left text-slate-400 font-sans whitespace-nowrap">{t[4].replace("本人", "")}</td>
                        <td className="px-2 py-1.5 text-left text-slate-200 font-sans max-w-[12rem] truncate" title={t[5]}>{t[5]}</td>
                        <td className="px-2 py-1.5 text-left font-sans whitespace-nowrap"><Tag kind={methodKind(t[6])}>{shortMethod(t[6])}</Tag></td>
                        <td className="px-2 py-1.5 text-slate-200">{lots(t[11])}</td>
                        <td className="px-2 py-1.5 text-slate-400">{t[10] ? `${((t[11] / t[10]) * 100).toFixed(0)}%` : "—"}</td>
                        <td className="px-2 py-1.5 text-slate-400">{lots(t[12])}</td>
                        <td className="px-2 py-1.5 text-left text-slate-500 font-sans max-w-[14rem] truncate" title={t[9]}>{t[9] || "—"}</td>
                        <td className="px-2 py-1.5 text-left text-slate-500 whitespace-nowrap">{t[13]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <CompanyDetail code={g.code} latest={data.latest} hasData={g.code in data.names} />
            </CompanyRow>
          ))}
        </ListBox>
      )}
    </div>
  );
}

function MonthList({ data, open, setOpen }: { data: Index; open: string | null; setOpen: (c: string | null) => void }) {
  const [side, setSide] = useState<Side>("all");
  const rows = data.recent.filter((r) => side === "all" || (side === "buy" ? r[2] > r[3] : r[3] > r[2]));
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <Pills<Side> value={side} onChange={setSide} options={[{ value: "all", label: "全部" }, { value: "buy", label: "淨買進" }, { value: "sell", label: "淨賣出" }]} />
        <span className="text-xs text-slate-500">{ym(data.latest)} 內部人在集中市場有買賣的公司，依金額排序</span>
      </div>
      {!rows.length ? <Empty>沒有符合條件的公司。</Empty> : (
        <ListBox count={rows.length} grid="sm:grid-cols-[minmax(9rem,1.2fr)_3rem_minmax(8rem,1fr)_10rem_6rem]" labels={[["公司", false], ["方向", false], ["主要申報人", false], ["買／賣（張）・均價", true], ["淨額（估）", true]]}>
          {rows.map((r) => (
            <CompanyRow key={r[0]} open={open === r[0]} onToggle={() => setOpen(open === r[0] ? null : r[0])} head={
              <div className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(9rem,1.2fr)_3rem_minmax(8rem,1fr)_10rem_6rem] items-center gap-x-4 gap-y-1">
                <CompanyName code={r[0]} name={r[1]} />
                <SideTag side={r[2] >= r[3] ? 1 : -1} />
                <span className="text-xs text-slate-400 truncate">{r[6]}</span>
                <span className="text-right font-mono text-xs text-slate-400 whitespace-nowrap">
                  <span className={RED}>{lots(r[2])}</span> / <span className={GREEN}>{lots(r[3])}</span> 張{r[5] ? `・均 ${r[5] >= 100 ? r[5].toFixed(0) : r[5]}` : ""}
                </span>
                <span className={`text-right font-mono text-sm ${tone(r[4])}`}>{r[4] == null ? "—" : signed(r[4])}</span>
              </div>
            }>
              <CompanyDetail code={r[0]} latest={data.latest} hasData />
            </CompanyRow>
          ))}
        </ListBox>
      )}
    </div>
  );
}

/* ---------------- 歷史案例 ---------------- */

function HistoryList({ data, open, setOpen }: { data: Index; open: string | null; setOpen: (c: string | null) => void }) {
  const [side, setSide] = useState<Side>("all");
  const [minAmt, setMinAmt] = useState<MinAmt>("1e8");
  const [sort, setSort] = useState<HistSort>("amount");
  const groups = useMemo(() => {
    const by = new Map<string, Case[]>();
    for (const c of data.cases) {
      if (Math.abs(c[5]) < Number(minAmt)) continue;
      if (side !== "all" && (side === "buy" ? c[2] < 0 : c[2] > 0)) continue;
      by.set(c[0], [...(by.get(c[0]) ?? []), c]);
    }
    return [...by.entries()].map(([code, cs]) => {
      const sorted = [...cs].sort((a, b) => b[4].localeCompare(a[4]));
      const top = [...cs].sort((a, b) => Math.abs(b[5]) - Math.abs(a[5]))[0];
      return { code, name: cs[0][1], cases: sorted, top, total: cs.reduce((s, c) => s + c[5], 0), last: sorted[0][4] };
    }).sort((a, b) => (sort === "amount" ? Math.abs(b.top[5]) - Math.abs(a.top[5]) : b.last.localeCompare(a.last) || Math.abs(b.top[5]) - Math.abs(a.top[5])));
  }, [data, side, minAmt, sort]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <Pills<Side> value={side} onChange={setSide} options={[{ value: "all", label: "買賣都看" }, { value: "buy", label: "內部人買進" }, { value: "sell", label: "內部人賣出" }]} />
        <Pills<MinAmt> value={minAmt} onChange={setMinAmt} options={[{ value: "1e7", label: "≥ 1000 萬" }, { value: "1e8", label: "≥ 1 億" }, { value: "1e9", label: "≥ 10 億" }]} />
        <Pills<HistSort> value={sort} onChange={setSort} options={[{ value: "amount", label: "依金額" }, { value: "recent", label: "依時間" }]} />
      </div>
      {!groups.length ? <Empty>沒有符合條件的案例。</Empty> : (
        <ListBox count={groups.length} grid="sm:grid-cols-[minmax(9rem,1.1fr)_3rem_minmax(9rem,1.3fr)_6rem_5rem_5rem]" labels={[["公司", false], ["方向", false], ["最大一次：期間・誰・均價", false], ["淨額（估）", true], ["之後3個月", true], ["至今", true]]}>
          {groups.map((g) => (
            <CompanyRow key={g.code} open={open === g.code} onToggle={() => setOpen(open === g.code ? null : g.code)} head={
              <div className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(9rem,1.1fr)_3rem_minmax(9rem,1.3fr)_6rem_5rem_5rem] items-center gap-x-4 gap-y-1">
                <span>
                  <CompanyName code={g.code} name={g.name} />
                  {g.cases.length > 1 && <span className="ml-2 text-[11px] text-slate-500">{g.cases.length} 次</span>}
                </span>
                <SideTag side={g.top[2]} />
                <span className="text-xs text-slate-400 truncate">
                  <span className="font-mono text-slate-300">{period(g.top[3], g.top[4])}</span>　{g.top[7]}{g.top[6] ? `・均 ${g.top[6] >= 100 ? g.top[6].toFixed(0) : g.top[6]}` : ""}
                </span>
                <span className={`text-right font-mono text-sm ${tone(g.top[5])}`}>{signed(g.top[5])}</span>
                <span className="text-right font-mono text-xs" title="案例結束後 3 個月的股價漲跌"><span className="text-slate-600 mr-1 sm:hidden">3M</span><span className={tone(g.top[9])}>{pctFmt(g.top[9])}</span></span>
                <span className="text-right font-mono text-xs" title="案例結束至今的股價漲跌"><span className="text-slate-600 mr-1 sm:hidden">至今</span><span className={tone(g.top[10])}>{pctFmt(g.top[10])}</span></span>
              </div>
            }>
              <div className="mb-4 rounded-lg border border-[#1e2a3a] overflow-x-auto">
                <table className="w-full text-xs whitespace-nowrap">
                  <thead>
                    <tr className="border-b border-[#1e2a3a] text-slate-500 text-right">
                      <th className="px-3 py-1.5 font-normal text-left">期間</th><th className="px-3 py-1.5 font-normal text-left">方向</th>
                      <th className="px-3 py-1.5 font-normal text-left">誰</th><th className="px-3 py-1.5 font-normal">均價</th>
                      <th className="px-3 py-1.5 font-normal">淨額（估）</th><th className="px-3 py-1.5 font-normal">之後 3 個月</th><th className="px-3 py-1.5 font-normal">至今</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.cases.map((c) => (
                      <tr key={c[3]} className="border-b border-[#1e2a3a]/50 last:border-0 text-right font-mono">
                        <td className="px-3 py-1.5 text-left text-slate-300">{period(c[3], c[4])}</td>
                        <td className="px-3 py-1.5 text-left"><SideTag side={c[2]} /></td>
                        <td className="px-3 py-1.5 text-left text-slate-400 font-sans whitespace-nowrap">{c[7]}</td>
                        <td className="px-3 py-1.5 text-slate-400">{c[6] ? px(c[6]) : "—"}</td>
                        <td className={`px-3 py-1.5 ${tone(c[5])}`}>{signed(c[5])}</td>
                        <td className={`px-3 py-1.5 ${tone(c[9])}`}>{pctFmt(c[9])}</td>
                        <td className={`px-3 py-1.5 ${tone(c[10])}`}>{pctFmt(c[10])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <CompanyDetail code={g.code} latest={data.latest} hasData />
            </CompanyRow>
          ))}
        </ListBox>
      )}
      <p className="mt-2 text-[11px] text-slate-600">
        案例：同一家公司內部人連續（中間最多隔一個月）同方向在集中市場買賣、單月淨額 1000 萬以上的月份合併成一次。
        「之後 3 個月」「至今」是從案例最後一個月的月底收盤價起算的股價漲跌。列表依每家公司最大的一次案例排序。
      </p>
    </div>
  );
}

/* ---------------- 主頁 ---------------- */

export default function InsiderDashboard() {
  const router = useRouter();
  const params = useSearchParams();
  const index = useStaticJson<Index>("insider/index.json");
  const [tab, setTabState] = useState<Tab>(params.get("tab") === "history" ? "history" : "recent");
  const [view, setView] = useState<RecentView>("transfer");
  const [open, setOpen] = useState<string | null>(params.get("stock"));
  const [search, setSearch] = useState<string | null>(null);

  const setTab = (t: Tab) => {
    setTabState(t);
    setOpen(null);
    const sp = new URLSearchParams(window.location.search);
    sp.set("tab", t);
    sp.delete("stock");
    router.replace(`?${sp.toString()}`, { scroll: false });
  };

  const suggestions = useMemo(() => {
    if (!index.data) return [];
    const m = new Map<string, string>(Object.entries(index.data.names));
    for (const t of index.data.transfers) if (!m.has(t[1])) m.set(t[1], t[2]);
    return [...m.entries()].map(([code, name]) => ({ code, name }));
  }, [index.data]);

  if (!index.data) {
    return <div className="py-16 text-center text-sm text-slate-500 font-mono">{index.error ? "資料載入失敗，請稍後重新整理。" : "載入中…"}</div>;
  }
  const d = index.data;
  if (!d.latest && !d.transfers.length) return <Empty>內部人持股異動資料還在回補中，稍後就會出現。</Empty>;
  const lastT = d.transfers[0]?.[0];
  const recentT = d.transfers.filter((t) => lastT && Date.parse(lastT) - Date.parse(t[0]) < 7 * 86400e3);
  const searchName = search ? suggestions.find((s) => s.code === search)?.name ?? search : "";

  return (
    <div>
      <KpiRow>
        <Kpi label="最新事前申報" value={lastT ? md(lastT) : "—"} sub={`近 7 天 ${new Set(recentT.map((t) => t[1])).size} 家`} />
        <Kpi label="近 7 天預定市場賣出" value={money(recentT.filter((t) => methodKind(t[6]) === "market").reduce((s, t) => s + t[11] * (t[14] ?? 0), 0))} color="text-[#22c55e]" sub="以最新收盤估" />
        <Kpi label={`${ym(d.latest)} 內部人淨買／淨賣`} value={<><span className={RED}>{d.recent.filter((r) => r[2] > r[3]).length}</span><span className="text-slate-600 mx-1">/</span><span className={GREEN}>{d.recent.filter((r) => r[3] > r[2]).length}</span></>} unit="家" />
        <Kpi label="歷史案例" value={d.cases.length} unit="次" sub={`${Object.keys(d.names).length} 家有紀錄`} />
      </KpiRow>

      <div className="flex flex-col-reverse sm:flex-row sm:items-end justify-between gap-3 border-b border-[#1e2a3a] mb-5">
        <div className="flex gap-6">
          {([["recent", "近期公告"], ["history", "歷史案例"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`pb-3 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors ${tab === k ? "border-[#00d4aa] text-white" : "border-transparent text-slate-500 hover:text-slate-300"}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="pb-3"><SearchBox placeholder="查單一公司，例如 2330" items={suggestions} onPick={setSearch} /></div>
      </div>

      {search && (
        <div className="mb-6 rounded-xl border border-[#00d4aa]/30 bg-[#0d1220] p-4">
          <div className="flex items-center justify-between mb-2">
            <CompanyName code={search} name={searchName} />
            <button onClick={() => setSearch(null)} className="text-xs text-slate-500 hover:text-[#00d4aa]">關閉 ✕</button>
          </div>
          <CompanyDetail key={search} code={search} latest={d.latest} hasData={search in d.names} />
        </div>
      )}

      {tab === "recent" ? (
        <>
          <Note>
            <b>事前申報轉讓</b>：董監事、經理人、大股東要轉讓持股，須在轉讓前 3 天申報，申報後 1 個月內有效（「一般交易」＝在市場上賣出；「洽特定人」＝私下轉給特定對象）。
            金額以最新收盤價估算，實際是否賣出、賣多少，要看之後的月度異動申報。
            <b> 最新月異動</b>：每月 15 日前申報上個月實際買賣的股數。
          </Note>
          <div className="mb-4">
            <Pills<RecentView> value={view} onChange={(v) => { setView(v); setOpen(null); }} options={[
              { value: "transfer", label: "事前申報轉讓" },
              { value: "month", label: `最新月異動（${ym(d.latest)}）` },
            ]} />
          </div>
          {view === "transfer" ? <TransferList data={d} open={open} setOpen={setOpen} /> : <MonthList data={d} open={open} setOpen={setOpen} />}
        </>
      ) : (
        <>
          <Note>
            過去 2 年內部人在集中市場較大規模的買進／賣出，一家公司一列，顯示金額最大的一次與之後股價表現；點開看每一次案例、股價圖與每月明細。
            申報只有股數，金額以當月平均收盤價估算。
          </Note>
          <HistoryList data={d} open={open} setOpen={setOpen} />
        </>
      )}
    </div>
  );
}
