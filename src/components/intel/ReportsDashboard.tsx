"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Star } from "lucide-react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";

// [日期, 代號, 名稱, 券商, 評等, 目標價, 上次目標價, 潛在漲幅%, 收盤, 種類, 標題, 亮點[], 連結, id]
type Row = [string, string, string, string, string | null, number | null, number | null, number | null, number | null,
  "broker" | "consensus", string, string[], string, string];
type Data = { updatedAt: string; date: string; rows: Row[]; per: Record<string, { name: string; n: number; hi: number | null; lo: number | null; cons: number | null }> };
type Kind = "broker" | "consensus" | "all";
type Range = "7" | "30" | "90";

const SEEN_KEY = "reports-seen";
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const price = (v: number | null) => (v == null ? "—" : v >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : String(v));
const TODAY = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const daysAgo = (n: number) => new Date(Date.parse(TODAY) - n * 86400e3).toISOString().slice(0, 10);
const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
const POS = /買進|加碼|增持|優於|跑贏|Buy|Outperform|Overweight/i;
const NEG = /減碼|劣於|賣出|Sell|Underweight|Underperform/i;

function Change({ prev, target }: { prev: number | null; target: number | null }) {
  if (target == null) return null;
  if (prev == null) return <span className="text-[11px] text-[#8b97ab]">首次／未註明前次</span>;
  if (prev === target) return <span className="text-[11px] text-[#8b97ab]">維持 {price(target)}</span>;
  const up = target > prev;
  return (
    <span className={`text-[11px] font-mono ${up ? "text-[#f05252]" : "text-[#22c55e]"}`}>
      {up ? "調升" : "調降"} {price(prev)} → {price(target)}（{up ? "+" : ""}{(((target - prev) / prev) * 100).toFixed(1)}%）
    </span>
  );
}

function Card({ r, isNew, starred, onStar }: { r: Row; isNew: boolean; starred: boolean; onStar: () => void }) {
  const [date, code, name, broker, rating, target, prev, up, close, kind, title, points, url] = r;
  const rc = rating ? (POS.test(rating) ? "text-[#f05252] border-[#f05252]/40 bg-[#f05252]/10" : NEG.test(rating) ? "text-[#22c55e] border-[#22c55e]/40 bg-[#22c55e]/10" : "text-[#f59e0b] border-[#f59e0b]/40 bg-[#f59e0b]/10") : "";
  return (
    <div className={`rounded-xl border bg-[#0d1220] p-4 ${isNew ? "border-[#4f8cff]/60" : "border-[#243247]"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {isNew && <span className="text-[10px] font-bold px-1.5 py-px rounded bg-[#4f8cff] text-white">NEW</span>}
            <button onClick={onStar} title={starred ? "移出自選" : "加入自選"} className={starred ? "text-[#f59e0b]" : "text-[#475569] hover:text-[#f59e0b]"}>
              <Star className="w-3.5 h-3.5" fill={starred ? "currentColor" : "none"} />
            </button>
            <span className="text-base text-white font-semibold">{name}</span>
            <span className="font-mono text-xs text-[#8b97ab]">{code}</span>
            <span className={`text-[11px] px-1.5 py-px rounded border ${kind === "consensus" ? "border-[#a78bfa]/40 text-[#a78bfa] bg-[#a78bfa]/10" : "border-[#4f8cff]/40 text-[#4f8cff] bg-[#4f8cff]/10"}`}>{broker}</span>
            {rating && <span className={`text-[11px] px-1.5 py-px rounded border ${rc}`}>{rating}</span>}
          </div>
          <div className="mt-1"><Change prev={prev} target={target} /></div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-[11px] text-[#8b97ab]">目標價</div>
          <div className="font-mono text-xl font-bold text-white">{price(target)}</div>
          <div className="text-[11px] font-mono">
            <span className="text-[#8b97ab]">現價 {price(close)}・</span>
            <span className={up == null ? "text-[#8b97ab]" : up >= 0 ? "text-[#f05252]" : "text-[#22c55e]"}>{up == null ? "—" : `${up >= 0 ? "+" : ""}${up}%`}</span>
          </div>
        </div>
      </div>
      {points.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {points.slice(0, 4).map((p, i) => (
            <li key={i} className="text-[13px] leading-relaxed text-slate-300 pl-3 relative before:content-['•'] before:absolute before:left-0 before:text-[#4f8cff]">{p}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex items-center justify-between gap-3 text-[11px] text-[#7c8aa0]">
        <span className="truncate">{md(date)}・{title}</span>
        {url && <a href={url} target="_blank" rel="noreferrer" className="shrink-0 inline-flex items-center gap-1 hover:text-[#4f8cff]">原文 <ExternalLink className="w-3 h-3" /></a>}
      </div>
    </div>
  );
}

export default function ReportsDashboard() {
  const { data, error } = useStaticJson<Data>("intel/reports.json");
  const wl = useWatchlist();
  const [kind, setKind] = useState<Kind>("broker");
  const [range, setRange] = useState<Range>("30");
  const [mine, setMine] = useState(false);
  const [q, setQ] = useState<string | null>(null);
  // 上次看過的最新一筆：比它新的標 NEW；離開頁面時才更新，避免一打開就被標成已讀
  const [seen, setSeen] = useState<string | null>(null);
  useEffect(() => {
    const read = () => {
      let v: string | null = null;
      try { v = localStorage.getItem(SEEN_KEY); } catch {}
      setSeen(v ?? "");
    };
    read();
  }, []);
  useEffect(() => {
    if (!data?.rows.length) return;
    const newest = data.rows.reduce((m, r) => (r[0] + r[13] > m ? r[0] + r[13] : m), "");
    const save = () => { try { localStorage.setItem(SEEN_KEY, newest); } catch {} };
    window.addEventListener("pagehide", save);
    return () => { save(); window.removeEventListener("pagehide", save); };
  }, [data]);

  const rows = useMemo(() => {
    let rs = data?.rows ?? [];
    if (kind !== "all") rs = rs.filter((r) => r[9] === kind);
    rs = rs.filter((r) => r[0] >= daysAgo(Number(range)));
    if (mine) rs = rs.filter((r) => wl.has(r[1]));
    if (q) rs = rs.filter((r) => r[1] === q);
    return rs;
  }, [data, kind, range, mine, q, wl]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const isNew = (r: Row) => seen !== null && seen !== "" && r[0] + r[13] > seen;
  const broker7 = data.rows.filter((r) => r[9] === "broker" && r[0] >= daysAgo(7));
  const ups = broker7.filter((r) => r[6] != null && r[5] != null && r[5] > r[6]).length;
  const downs = broker7.filter((r) => r[6] != null && r[5] != null && r[5] < r[6]).length;
  const newCount = data.rows.filter((r) => r[9] === "broker" && isNew(r)).length;
  const top = [...broker7].filter((r) => r[7] != null).sort((a, b) => b[7]! - a[7]!)[0];
  const groups: [string, Row[]][] = [];
  for (const r of rows.slice(0, 300)) {
    const g = groups.at(-1);
    if (g && g[0] === r[0]) g[1].push(r); else groups.push([r[0], [r]]);
  }
  const suggestions = [...new Map(data.rows.map((r) => [r[1], { code: r[1], name: r[2] }])).values()];

  return (
    <div>
      {newCount > 0 && (
        <div className="mb-5 rounded-xl border border-[#4f8cff]/50 bg-[#4f8cff]/10 px-4 py-3 text-sm text-white">
          🔔 自上次瀏覽後有 <b>{newCount}</b> 份新的券商報告（標示 NEW）
        </div>
      )}
      <Note>
        整理媒體報導的券商／投顧研究報告：目標價、評等、上次目標價與報告重點。<b>潛在漲幅</b>＝目標價 ÷ 最新收盤價 − 1。
        「FactSet 共識」是多家分析師的目標價中位數變動，不是單一券商。報告內容取自新聞轉述，細節以原文為準。
      </Note>
      <KpiRow>
        <Kpi label="近 7 天券商報告" value={broker7.length} unit="份" sub={`${new Set(broker7.map((r) => r[1])).size} 檔`} />
        <Kpi label="調升／調降目標價" value={<><span className="text-[#f05252]">{ups}</span><span className="text-[#7c8aa0] mx-1">/</span><span className="text-[#22c55e]">{downs}</span></>} sub="近 7 天" />
        <Kpi label="潛在漲幅最大" value={top ? `${top[7]! >= 0 ? "+" : ""}${top[7]}%` : "—"} color="text-[#f05252]" sub={top ? top[2] : undefined} />
        <Kpi label="最新報告" value={data.rows[0] ? md(data.rows[0][0]) : "—"} sub={newCount ? `${newCount} 份新` : undefined} />
      </KpiRow>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Pills<Kind> value={kind} onChange={setKind} options={[{ value: "broker", label: "券商報告" }, { value: "consensus", label: "FactSet 共識" }, { value: "all", label: "全部" }]} />
        <Pills<Range> value={range} onChange={setRange} options={[{ value: "7", label: "近 7 天" }, { value: "30", label: "近 30 天" }, { value: "90", label: "近 90 天" }]} />
        <button onClick={() => setMine(!mine)} className={`px-3 py-1.5 text-xs rounded-lg border ${mine ? "border-[#f59e0b]/60 text-[#f59e0b] bg-[#f59e0b]/10" : "border-[#243247] text-slate-400"}`}>
          ★ 只看自選股
        </button>
        <div className="w-full sm:w-auto sm:ml-auto">
          <SearchBox placeholder="查單一股票，例如 2330" items={suggestions} onPick={(c) => setQ(c || null)} />
        </div>
      </div>
      {q && <button onClick={() => setQ(null)} className="mb-3 text-xs text-[#8b97ab] hover:text-[#4f8cff]">← 顯示全部</button>}
      {!rows.length ? <Empty>這個條件下沒有報告。</Empty> : (
        <div className="space-y-6">
          {groups.map(([d, rs]) => (
            <div key={d}>
              <div className="mb-2 text-xs font-mono text-[#8b97ab]">{d}（{WEEK[new Date(d).getDay()]}）・{rs.length} 份</div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {rs.map((r) => <Card key={r[13]} r={r} isNew={isNew(r)} starred={wl.has(r[1])} onStar={() => wl.toggle(r[1])} />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
