"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, FileText, Star } from "lucide-react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";

type News = { date: string; title: string; kind: "ai" | "news"; points: string[]; url: string };
type Conf = {
  date: string; code: string; name: string; mk: string; time: string; place: string; summary: string;
  pdf: string | null; pdfEn: string | null; pdfOld: string | null; ir: string | null; react: number | null; news: News[]; body: string;
};
type Data = { updatedAt: string; today: string; rows: Conf[] };
type Tab = "upcoming" | "past";
type Range = "7" | "14" | "45";

const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}（${WEEK[new Date(d).getDay()]}）`;
const addDays = (d: string, n: number) => new Date(Date.parse(d) + n * 86400e3).toISOString().slice(0, 10);
const until = (d: string, today: string) => {
  const n = Math.round((Date.parse(d) - Date.parse(today)) / 86400e3);
  return n === 0 ? "今天" : n === 1 ? "明天" : `${n} 天後`;
};

/** AI 摘要全文：依「一、二、」大段與「Q1」問答斷行，方便閱讀 */
function Body({ text }: { text: string }) {
  const parts = text.split(/(?=[一二三四五六七八九十]、)|(?=【[^】]*Q&A[^】]*】)|(?=Q\d+[：:])/).filter((x) => x.trim());
  return (
    <div className="mt-3 max-h-96 overflow-y-auto rounded-lg border border-[#243247] bg-[#0a0f1a] p-3 space-y-2">
      {parts.map((p, i) => <p key={i} className="text-[12.5px] leading-relaxed text-slate-300 whitespace-pre-wrap">{p.trim()}</p>)}
    </div>
  );
}

function Points({ c }: { c: Conf }) {
  const pts = c.news.flatMap((n) => n.points).filter((p, i, a) => a.indexOf(p) === i).slice(0, 6);
  if (!pts.length) return null;
  return (
    <ul className="mt-3 space-y-1.5">
      {pts.map((p, i) => <li key={i} className="text-[13px] leading-relaxed text-slate-300 pl-3 relative before:content-['•'] before:absolute before:left-0 before:text-[#a78bfa]">{p}</li>)}
    </ul>
  );
}

function Card({ c, today, starred, onStar }: { c: Conf; today: string; starred: boolean; onStar: () => void }) {
  const [open, setOpen] = useState(false);
  const past = c.date < today;
  return (
    <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={onStar} title={starred ? "移出自選" : "加入自選"} className={starred ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}>
              <Star className="w-3.5 h-3.5" fill={starred ? "currentColor" : "none"} />
            </button>
            <span className="text-base text-white font-semibold">{c.name}</span>
            <span className="font-mono text-xs text-[#8b97ab]">{c.code}</span>
            {c.mk && <span className="text-[10px] text-[#7c8aa0]">{c.mk}</span>}
            {!past && <span className="text-[11px] px-1.5 py-px rounded border border-[#a78bfa]/40 text-[#a78bfa] bg-[#a78bfa]/10">{until(c.date, today)}</span>}
          </div>
          <div className="mt-1 text-xs text-[#8b97ab] font-mono">{md(c.date)} {c.time}{c.place ? `・${c.place}` : ""}</div>
        </div>
        {past && c.react != null && (
          <div className="text-right shrink-0">
            <div className="text-[11px] text-[#8b97ab]">隔日股價</div>
            <div className={`font-mono text-lg font-bold ${c.react >= 0 ? "text-[#f05252]" : "text-[#22c55e]"}`}>{c.react >= 0 ? "+" : ""}{c.react}%</div>
          </div>
        )}
      </div>
      {c.summary && <p className="mt-2 text-xs leading-relaxed text-[#8b97ab]">{c.summary}</p>}
      <Points c={c} />
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px]">
        {c.pdf && <a href={c.pdf} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#4f8cff] hover:underline"><FileText className="w-3 h-3" />簡報（中）</a>}
        {c.pdfOld && <a href={c.pdfOld} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#8b97ab] hover:text-[#4f8cff]"><FileText className="w-3 h-3" />上次法說簡報</a>}
        {c.ir && <a href={c.ir} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#4f8cff] hover:underline"><ExternalLink className="w-3 h-3" />公司 IR／直播</a>}
        {c.pdfEn && <a href={c.pdfEn} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#4f8cff] hover:underline"><FileText className="w-3 h-3" />簡報（英）</a>}
        {c.news.map((n) => (
          <a key={n.url} href={n.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#8b97ab] hover:text-[#4f8cff] max-w-full">
            <span className="truncate max-w-[16rem]">{n.kind === "ai" ? "AI 摘要" : n.title}</span><ExternalLink className="w-3 h-3 shrink-0" />
          </a>
        ))}
      </div>
      {c.body && (
        <button onClick={() => setOpen(!open)} className="mt-3 inline-flex items-center gap-1 text-xs text-[#a78bfa] hover:underline">
          {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          {open ? "收起" : "展開"}法說會完整摘要（含問答）
        </button>
      )}
      {open && c.body && <Body text={c.body} />}
    </div>
  );
}

export default function ConfDashboard() {
  const { data, error } = useStaticJson<Data>("intel/conf.json");
  const wl = useWatchlist();
  const [tab, setTab] = useState<Tab>("upcoming");
  const [range, setRange] = useState<Range>("14");
  const [mine, setMine] = useState(false);
  const [q, setQ] = useState<string | null>(null);

  const rows = useMemo(() => {
    if (!data) return [];
    const t = data.today;
    let rs = tab === "upcoming"
      ? data.rows.filter((c) => c.date >= t && c.date <= addDays(t, Number(range)))
      : data.rows.filter((c) => c.date < t).reverse();
    if (tab === "past" && !q && !mine) rs = rs.filter((c) => c.news.length || c.pdf);
    if (mine) rs = rs.filter((c) => wl.has(c.code));
    if (q) rs = data.rows.filter((c) => c.code === q).reverse();
    return rs;
  }, [data, tab, range, mine, q, wl]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const t = data.today;
  const week = data.rows.filter((c) => c.date >= t && c.date <= addDays(t, 7));
  const soon = data.rows.filter((c) => c.date === t || c.date === addDays(t, 1));
  const done = data.rows.filter((c) => c.date < t && c.date >= addDays(t, -30) && c.news.length);
  const mineSoon = data.rows.filter((c) => c.date >= t && c.date <= addDays(t, 30) && wl.has(c.code));
  const groups: [string, Conf[]][] = [];
  for (const c of rows.slice(0, 200)) {
    const g = groups.at(-1);
    if (g && g[0] === c.date) g[1].push(c); else groups.push([c.date, [c]]);
  }
  const suggestions = [...new Map(data.rows.map((c) => [c.code, { code: c.code, name: c.name }])).values()];

  return (
    <div>
      <Note>
        <b>即將舉行</b>來自公開資訊觀測站的法說會公告（日期、時間、地點、說明會內容）；<b>已舉行</b>整理法說後的新聞重點與鉅亨網「法說會 AI 摘要」，
        並附上法說隔一個交易日的股價反應。簡報檔在公司上傳後才會出現。
      </Note>
      <KpiRow>
        <Kpi label="7 天內法說會" value={week.length} unit="家" />
        <Kpi label="今明兩天" value={soon.length} unit="家" sub={soon.slice(0, 3).map((c) => c.name).join("、")} />
        <Kpi label="近 30 天已整理要點" value={done.length} unit="場" />
        <Kpi label="自選股 30 天內法說" value={mineSoon.length} unit="家" color="text-[#f59e0b]" sub={mineSoon.slice(0, 3).map((c) => c.name).join("、")} />
      </KpiRow>
      <div className="flex flex-col-reverse sm:flex-row sm:items-end justify-between gap-3 border-b border-[#243247] mb-5">
        <div className="flex gap-6">
          {([["upcoming", "即將舉行"], ["past", "近期法說要點"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => { setTab(k); setQ(null); }}
              className={`pb-3 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors ${tab === k ? "border-[#4f8cff] text-white" : "border-transparent text-[#8b97ab] hover:text-slate-300"}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="w-full sm:w-auto pb-2">
          <SearchBox placeholder="查單一公司，例如 2330" items={suggestions} onPick={(c) => setQ(c || null)} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {tab === "upcoming" && !q && <Pills<Range> value={range} onChange={setRange} options={[{ value: "7", label: "7 天內" }, { value: "14", label: "14 天內" }, { value: "45", label: "45 天內" }]} />}
        <button onClick={() => setMine(!mine)} className={`px-3 py-1.5 text-xs rounded-lg border ${mine ? "border-[#f59e0b]/60 text-[#f59e0b] bg-[#f59e0b]/10" : "border-[#243247] text-slate-400"}`}>
          ★ 只看自選股
        </button>
        {q && <button onClick={() => setQ(null)} className="text-xs text-[#8b97ab] hover:text-[#4f8cff]">← 顯示全部</button>}
      </div>
      {!rows.length ? <Empty>{tab === "upcoming" ? "這段期間沒有公告的法說會。" : "還沒有整理到法說要點。"}</Empty> : (
        <div className="space-y-6">
          {groups.map(([d, cs]) => (
            <div key={d}>
              <div className="mb-2 text-xs font-mono text-[#8b97ab]">{md(d)}・{cs.length} 家{d >= t ? `・${until(d, t)}` : ""}</div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {cs.map((c) => <Card key={c.code + c.date} c={c} today={t} starred={wl.has(c.code)} onStar={() => wl.toggle(c.code)} />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
