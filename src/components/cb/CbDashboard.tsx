"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import { Empty, Kpi, KpiRow, SortTable, type Column } from "@/components/data-ui";

export type CbCase = {
  id: string; sn: string; method: "詢圈" | "競拍"; company: string; code: string | null; short: string;
  lead: string; type: string; kind: "CB" | "EB"; units: number | null; saleUnits: number | null;
  start: string | null; end: string | null; premiumLo: number | null; premiumHi: number | null; minPrice: number | null;
  bondCode?: string; bondName?: string; issueDate?: string | null; listDate?: string | null; convPrice?: number | null;
  priceDateEst?: string; listDateEst?: string;
};
export type CbPre = {
  code: string; name: string; market: string; status: string; cbType: string; amount: number | null;
  filingDate: string | null; effectiveDate: string | null; underwriter: string | null;
};

type Stage = "upcoming" | "open" | "pending" | "listed";
type Tab = "overview" | "pre" | "active" | "bookbuilding" | "auction" | "listed";
type Event = { date: string; label: string; c: CbCase; est: boolean };

const WEEK = "日一二三四五六";
const md = (d?: string | null) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : "—");
const listOf = (c: CbCase) => c.listDate ?? c.listDateEst ?? null;
const title = (c: CbCase) => c.bondName || c.short || c.company.replace(/(股份)?有限公司.*$/, "");

function todayTpe() {
  return new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
}

function stageOf(c: CbCase, today: string): Stage {
  if (c.start && today < c.start) return "upcoming";
  if (c.end && today <= c.end) return "open";
  const l = listOf(c);
  if (l && today < l) return "pending";
  return "listed";
}

const STAGE_LABEL: Record<Stage, [string, string]> = {
  upcoming: ["即將開始", "text-sky-300 border-sky-400/40 bg-sky-400/10"],
  open: ["進行中", "text-[#f59e0b] border-[#f59e0b]/40 bg-[#f59e0b]/10"],
  pending: ["待掛牌", "text-[#a78bfa] border-[#a78bfa]/40 bg-[#a78bfa]/10"],
  listed: ["已掛牌", "text-slate-400 border-slate-600/50"],
};

function StageBadge({ s }: { s: Stage }) {
  const [label, cls] = STAGE_LABEL[s];
  return <span className={`text-[10px] px-1.5 py-px rounded border ${cls}`}>{label}</span>;
}

function DateCell({ actual, est }: { actual?: string | null; est?: string | null }) {
  if (actual) return <span className="text-slate-300">{md(actual)}</span>;
  if (est) return <span className="italic text-slate-500" title="尚未公告，依慣例推估">{md(est)}</span>;
  return <span className="text-slate-600">—</span>;
}

const noop = () => () => {};

export default function CbDashboard({ cases, pre, prices, updatedAt, buildDate }: {
  cases: CbCase[]; pre: CbPre[]; prices: Record<string, number>; updatedAt: string | null; buildDate: string;
}) {
  // 靜態頁面：建置時用建置日，瀏覽器載入後改用當天日期重新判斷階段
  const today = useSyncExternalStore(noop, todayTpe, () => buildDate);
  const [tab, setTab] = useState<Tab>("overview");
  const staged = useMemo(() => cases.map((c) => ({ c, s: stageOf(c, today) })), [cases, today]);
  const active = staged.filter((x) => x.s === "open" || x.s === "upcoming").map((x) => x.c);
  const pending = staged.filter((x) => x.s === "pending").map((x) => x.c);
  const listed = staged.filter((x) => x.s === "listed").map((x) => x.c);
  const year = today.slice(0, 4);

  const tabs: [Tab, string, number | null][] = [
    ["overview", "總覽", null],
    ["pre", "籌備中", pre.length],
    ["active", "進行中", active.length + pending.length],
    ["bookbuilding", "詢價圈購", cases.filter((c) => c.method === "詢圈").length],
    ["auction", "競價拍賣", cases.filter((c) => c.method === "競拍").length],
    ["listed", "已掛牌", listed.length],
  ];

  return (
    <div>
      <div className="flex gap-1 sm:gap-6 border-b border-[#1e2a3a] mb-6 overflow-x-auto">
        {tabs.map(([k, label, n]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`px-2 sm:px-0 pb-3 text-sm whitespace-nowrap border-b-2 -mb-px ${
              tab === k ? "border-[#00d4aa] text-white" : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            {label}{n != null && <span className="ml-1 font-mono text-xs text-slate-500">{n}</span>}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <KpiRow>
            <Kpi label="籌備中（審查／已生效）" value={`${pre.filter((p) => p.status === "審查中").length} / ${pre.filter((p) => p.status === "生效").length}`} />
            <Kpi label="詢圈／競拍中・即將開始" value={`${active.filter((c) => c.method === "詢圈").length}・${active.filter((c) => c.method === "競拍").length}`} />
            <Kpi label="已訂價、待掛牌" value={pending.length} unit="件" />
            <Kpi label={`${year} 年已掛牌`} value={listed.filter((c) => (listOf(c) ?? "").startsWith(year)).length} unit="件" />
          </KpiRow>
          <Upcoming cases={cases} today={today} />
          <h3 className="text-base font-semibold text-white mt-10 mb-1">最近發行</h3>
          <p className="text-xs text-slate-500 mb-4">轉換價為櫃買中心發行資料；「現價／轉換價」＝ 現股收盤價 ÷ 轉換價，大於 100% 表示已有轉換價值。</p>
          <CaseTable cases={[...cases].filter((c) => c.convPrice).sort((a, b) => (b.issueDate ?? "").localeCompare(a.issueDate ?? "")).slice(0, 12)} prices={prices} today={today} />
        </>
      )}
      {tab === "pre" && <PreTable pre={pre} />}
      {tab === "active" && (active.length + pending.length ? <CaseTable cases={[...active, ...pending]} prices={prices} today={today} /> : <Empty>目前沒有進行中的案件。</Empty>)}
      {tab === "bookbuilding" && <CaseTable cases={cases.filter((c) => c.method === "詢圈")} prices={prices} today={today} limit={60} />}
      {tab === "auction" && <CaseTable cases={cases.filter((c) => c.method === "競拍")} prices={prices} today={today} limit={60} />}
      {tab === "listed" && <CaseTable cases={listed} prices={prices} today={today} limit={60} />}

      <div className="mt-8 text-[11px] leading-relaxed text-slate-600 space-y-1">
        <p>流程：董事會決議 → 金管會申報生效 → 詢價圈購（議定溢價率）或 競價拍賣（以價格得標）→ 訂價／開標 → 繳款 → 上櫃掛牌。</p>
        <p>斜體灰字日期是還沒公告時依慣例推估（訂價基準日 ≈ 圈購截止後 2 個營業日、競拍開標 ≈ 截止後 1 個營業日，掛牌 ≈ 訂價後 7 個營業日），以正式公告為準。</p>
        <p>來源：證券商業同業公會承銷公告（詢價圈購、競價拍賣清單）、櫃買中心轉(交)換公司債發行資料、金管會證期局申報案件。{updatedAt && `資料更新 ${updatedAt.replace("T", " ").slice(0, 16)}`}</p>
      </div>
    </div>
  );
}

function Upcoming({ cases, today }: { cases: CbCase[]; today: string }) {
  const end = new Date(new Date(`${today}T00:00:00Z`).getTime() + 14 * 864e5).toISOString().slice(0, 10);
  const events: Event[] = [];
  for (const c of cases) {
    const push = (d: string | null | undefined, label: string, est = false) => {
      if (d && d >= today && d <= end) events.push({ date: d, label, c, est });
    };
    push(c.start, c.method === "詢圈" ? "圈購開始" : "投標開始");
    push(c.end, c.method === "詢圈" ? "圈購截止" : "投標截止");
    if (!c.convPrice) push(c.priceDateEst, c.method === "詢圈" ? "訂價" : "開標", true);
    push(c.listDate ?? c.listDateEst, "掛牌", !c.listDate);
  }
  const byDay = new Map<string, Event[]>();
  for (const e of events.sort((a, b) => a.date.localeCompare(b.date))) byDay.set(e.date, [...(byDay.get(e.date) ?? []), e]);

  const color = (l: string) =>
    l.includes("截止") ? "text-[#f59e0b]" : l === "掛牌" ? "text-[#00d4aa]" : l.includes("開始") ? "text-sky-300" : "text-[#a78bfa]";

  return (
    <section>
      <h3 className="text-base font-semibold text-white mb-1">接下來兩週</h3>
      <p className="text-xs text-slate-500 mb-4">圈購／投標、訂價與掛牌時程。</p>
      {byDay.size === 0 ? <Empty>未來兩週沒有排定的時程。</Empty> : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[...byDay.entries()].map(([d, evs]) => {
            const dt = new Date(`${d}T00:00:00Z`);
            return (
              <div key={d} className={`rounded-xl border bg-[#0d1220] p-4 ${d === today ? "border-[#00d4aa]/50" : "border-[#1e2a3a]"}`}>
                <div className="flex items-baseline gap-2 mb-3">
                  <span className="font-mono text-lg text-white">{md(d)}</span>
                  <span className="text-xs text-slate-500">週{WEEK[dt.getUTCDay()]}{d === today ? "・今天" : ""}</span>
                </div>
                <div className="space-y-2">
                  {evs.map((e, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className={`text-[11px] w-14 shrink-0 ${color(e.label)} ${e.est ? "italic opacity-70" : ""}`}>{e.label}{e.est ? "*" : ""}</span>
                      <span className="text-slate-200 truncate">{title(e.c)}</span>
                      {e.c.code && <span className="font-mono text-[11px] text-slate-500">{e.c.code}</span>}
                      <span className="ml-auto text-[10px] text-slate-500">{e.c.method}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-2 text-[11px] text-slate-600">* 推估日期</p>
    </section>
  );
}

function CaseTable({ cases, prices, today, limit }: { cases: CbCase[]; prices: Record<string, number>; today: string; limit?: number }) {
  if (!cases.length) return <Empty>沒有案件。</Empty>;
  const parity = (c: CbCase) => (c.convPrice && c.code && prices[c.code] ? prices[c.code] / c.convPrice : null);
  const columns: Column<CbCase>[] = [
    {
      key: "co", label: "公司", sort: (c) => c.code ?? c.company,
      render: (c) => (
        <span className="inline-flex items-center gap-2">
          <span className="text-slate-200">{title(c)}</span>
          {c.code && <span className="font-mono text-xs text-slate-500">{c.code}</span>}
          {c.kind === "EB" && <span className="text-[10px] px-1 rounded border border-slate-600 text-slate-400">交換債</span>}
          {c.type.startsWith("有擔保") && <span className="text-[10px] text-slate-500">有擔</span>}
          <StageBadge s={stageOf(c, today)} />
        </span>
      ),
    },
    { key: "m", label: "方式", render: (c) => <span className="text-xs text-slate-400">{c.method}</span> },
    { key: "period", label: "圈購／投標期間", align: "right", sort: (c) => c.start, render: (c) => <span className="text-slate-400">{md(c.start)}～{md(c.end)}</span> },
    {
      key: "term", label: "溢價率／最低價", align: "right",
      render: (c) => <span className="text-slate-300">{c.method === "詢圈" ? (c.premiumLo ? `${c.premiumLo}%～${c.premiumHi}%` : "—") : (c.minPrice ?? "—")}</span>,
    },
    { key: "units", label: "張數", align: "right", sort: (c) => c.units, render: (c) => <span className="text-slate-300">{c.units?.toLocaleString() ?? "—"}</span> },
    { key: "conv", label: "轉換價", align: "right", sort: (c) => c.convPrice ?? null, render: (c) => <span className="text-slate-200">{c.convPrice ?? "—"}</span> },
    {
      key: "parity", label: "現價／轉換價", align: "right", sort: parity,
      render: (c) => {
        const p = parity(c);
        return p == null ? <span className="text-slate-600">—</span> : <span className={p >= 1 ? "text-[#ef4444]" : "text-slate-400"}>{(p * 100).toFixed(1)}%</span>;
      },
    },
    { key: "list", label: "掛牌", align: "right", sort: listOf, render: (c) => <DateCell actual={c.listDate} est={c.listDateEst} /> },
    { key: "lead", label: "主辦承銷商", render: (c) => <span className="text-xs text-slate-500">{c.lead.replace(/(綜合)?證券.*$/, "")}</span> },
  ];
  return <SortTable rows={cases} columns={columns} rowKey={(c) => c.id} initialSort={{ key: "period", desc: true }} limit={limit} />;
}

function PreTable({ pre }: { pre: CbPre[] }) {
  if (!pre.length) return <Empty>目前沒有申報中、尚未詢圈／競拍的案件。</Empty>;
  const columns: Column<CbPre>[] = [
    {
      key: "co", label: "公司", sort: (p) => p.code,
      render: (p) => (
        <span className="inline-flex items-center gap-2">
          <span className="text-slate-200">{p.name}</span>
          <span className="font-mono text-xs text-slate-500">{p.code}</span>
          <span className="text-[10px] text-slate-500">{p.market}</span>
        </span>
      ),
    },
    {
      key: "status", label: "狀態", sort: (p) => p.status,
      render: (p) => <span className={`text-[10px] px-1.5 py-px rounded border ${p.status === "生效" ? "text-[#00d4aa] border-[#00d4aa]/40" : "text-[#f59e0b] border-[#f59e0b]/40"}`}>{p.status}</span>,
    },
    { key: "type", label: "種類", render: (p) => <span className="text-xs text-slate-400">{p.cbType}</span> },
    { key: "amt", label: "金額（億）", align: "right", sort: (p) => p.amount, render: (p) => <span className="text-slate-200">{p.amount ?? "—"}</span> },
    { key: "filed", label: "申報日", align: "right", sort: (p) => p.filingDate, render: (p) => <span className="text-slate-400">{p.filingDate ?? "—"}</span> },
    { key: "eff", label: "生效日", align: "right", sort: (p) => p.effectiveDate, render: (p) => <span className="text-slate-400">{p.effectiveDate ?? "—"}</span> },
    { key: "uw", label: "承銷商", render: (p) => <span className="text-xs text-slate-500">{p.underwriter ?? "—"}</span> },
  ];
  return (
    <>
      <p className="text-xs text-slate-500 mb-4">金管會證期局申報案件中，審查中或已生效、但還沒開始詢價圈購或競價拍賣的國內可轉債。</p>
      <SortTable rows={pre} columns={columns} rowKey={(p) => `${p.code}-${p.filingDate}`} initialSort={{ key: "filed", desc: true }} />
    </>
  );
}
