"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Note } from "@/components/data-ui";

type Quote = { sym: string; date: string; close: number; chg: number | null; chg5: number | null; spark: number[]; th?: number; weekly?: boolean; alert?: boolean; react?: Mem[] };
type Mem = { code: string; name: string; corr: number | null; beta: number | null; member: boolean; exp?: number };
type Group = {
  id: string; name: string; theme: string; threshold: number; lead: string; quotes: Quote[];
  members: Mem[]; empirical: Mem[]; react: Mem[]; alert: boolean;
};
type Data = { usDate: string; twDate: string; sessions: number; groups: Group[] };

const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const SYM: Record<string, string> = {
  "^SOX": "費半", "^IXIC": "那指", "^GSPC": "S&P", "^DJI": "道瓊", "CL=F": "原油", "HG=F": "銅", "GC=F": "黃金", "TWD=X": "USD/TWD", TSM: "TSM ADR",
  "SI=F": "白銀", "PL=F": "白金", "^XAU": "金銀指數", "^HUI": "金蟲指數", BDI: "BDI 散裝", SCFI: "SCFI 貨櫃", BDRY: "BDRY 運價", BOAT: "BOAT 航運",
};

function Spark({ v, up }: { v: number[]; up: boolean }) {
  if (v.length < 2) return null;
  const lo = Math.min(...v), hi = Math.max(...v), w = 80, h = 24;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - ((x - lo) / (hi - lo || 1)) * h}`).join(" ");
  return <svg width={w} height={h} className="shrink-0"><polyline points={pts} fill="none" stroke={up ? "#f05252" : "#22c55e"} strokeWidth="1.5" /></svg>;
}

function MemTable({ rows, title }: { rows: Mem[]; title: string }) {
  return (
    <div>
      <div className="text-[11px] text-[#8b97ab] mb-1.5">{title}</div>
      <table className="w-full text-xs">
        <thead><tr className="text-[10px] text-[#7c8aa0] text-right"><th className="text-left font-normal py-1">股票</th><th className="font-normal">相關係數</th><th className="font-normal">β</th></tr></thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.code} className="border-t border-[#243247]/60 text-right font-mono">
              <td className="text-left py-1"><span className="text-slate-200 font-sans">{m.name}</span><span className="ml-1 text-[#7c8aa0]">{m.code}</span></td>
              <td className={(m.corr ?? 0) >= 0.4 ? "text-[#f59e0b]" : "text-slate-400"}>{m.corr ?? "—"}</td>
              <td className="text-slate-400">{m.beta ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupCard({ g }: { g: Group }) {
  const [open, setOpen] = useState(g.alert);
  const lead = g.quotes[0];
  // 有指數超過門檻時，用那個指數自己的 β 算開盤反應；否則用群組主指數
  const trig = g.quotes.filter((q) => q.alert && q.react?.length).sort((a, b) => Math.abs(b.chg ?? 0) - Math.abs(a.chg ?? 0))[0];
  const react = trig?.react ?? g.react;
  const basis = trig?.sym ?? g.lead;
  return (
    <div className={`rounded-xl border bg-[#0d1220] p-4 ${g.alert ? "border-[#f59e0b]/60" : "border-[#243247]"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-white font-semibold">{g.name}</span>
            {g.alert && <span className="text-[10px] font-bold px-1.5 py-px rounded bg-[#f59e0b] text-black">大幅波動</span>}
          </div>
          <div className="text-[11px] text-[#7c8aa0] mt-0.5">{g.theme}</div>
        </div>
        <div className={`font-mono text-xl font-bold ${tone(lead.chg)}`}>{pct(lead.chg)}</div>
      </div>
      <div className="mt-3 space-y-1.5">
        {g.quotes.map((q) => (
          <div key={q.sym} className={`flex items-center gap-3 text-xs font-mono rounded ${q.alert ? "bg-[#f59e0b]/10 -mx-1 px-1" : ""}`} title={`${q.date}${q.th ? `・提醒門檻 ±${q.th}%` : ""}`}>
            <span className="w-20 text-slate-300 truncate">{SYM[q.sym] ?? q.sym}{q.weekly && <span className="ml-1 text-[9px] text-[#7c8aa0]">週</span>}</span>
            <span className="w-20 text-right text-slate-400">{q.close.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
            <span className={`w-16 text-right ${tone(q.chg)}`}>{pct(q.chg)}</span>
            <span className={`w-20 text-right ${tone(q.chg5)}`}>{q.weekly ? "5週" : "5日"} {pct(q.chg5, 1)}</span>
            <Spark v={q.spark} up={(q.spark.at(-1) ?? 0) >= (q.spark[0] ?? 0)} />
          </div>
        ))}
      </div>
      {react.length > 0 && (
        <div className="mt-3">
          <div className="text-[11px] text-[#8b97ab] mb-1.5">台股開盤可能反應（β × {SYM[basis] ?? basis} 漲跌，依歷史估算）</div>
          <div className="flex flex-wrap gap-1.5">
            {react.slice(0, 10).map((m) => (
              <span key={m.code} className={`text-[11px] font-mono px-2 py-0.5 rounded border ${m.member ? "border-[#243247]" : "border-dashed border-[#243247]"} bg-[#0a0f1a]`}>
                <span className="text-slate-300 font-sans">{m.name}</span>
                <span className={`ml-1 ${tone(m.exp)}`}>{pct(m.exp, 1)}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      <button onClick={() => setOpen(!open)} className="mt-3 inline-flex items-center gap-1 text-xs text-[#4f8cff] hover:underline">
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}關聯台股
      </button>
      {open && (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <MemTable rows={g.members} title="產業對應成員" />
          <MemTable rows={g.empirical} title="實證高關聯（不在成員名單）" />
        </div>
      )}
    </div>
  );
}

export default function IntlDashboard() {
  const { data, error } = useStaticJson<Data>("intel/intl.json");
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  if (!data.groups.length) return <Empty>國際行情資料準備中。</Empty>;
  const alerts = data.groups.filter((g) => g.alert);
  return (
    <div>
      <Note>
        美股收盤在台北清晨，台股開盤會反應前一晚的國際走勢。每組列出美國對應標的與台股關聯股：<b>相關係數</b>是過去 {data.sessions} 個交易日
        「美股當天漲跌」與「台股隔天漲跌」的相關程度（越接近 1 越同步），<b>β</b> 是美股每漲 1% 台股隔天平均漲幾 %。
        「開盤可能反應」＝β × 美股漲跌，只是歷史平均，不代表一定如此。虛線框是名單外、但實際走勢高度連動的股票。
      </Note>
      <div className={`mb-5 rounded-xl border px-4 py-3 text-sm ${alerts.length ? "border-[#f59e0b]/60 bg-[#f59e0b]/10 text-white" : "border-[#243247] bg-[#0d1220] text-[#8b97ab]"}`}>
        美股 {md(data.usDate)} 收盤
        {alerts.length
          ? <>：<b>{alerts.flatMap((g) => g.quotes.filter((q) => q.alert).map((q) => `${SYM[q.sym] ?? q.sym} ${pct(q.chg)}`)).join("、")}</b> 波動超過門檻，留意台股開盤反應。</>
          : "：沒有類股波動超過門檻。"}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[...data.groups].sort((a, b) => Number(b.alert) - Number(a.alert) || Math.abs(b.quotes[0].chg ?? 0) - Math.abs(a.quotes[0].chg ?? 0)).map((g) => <GroupCard key={g.id} g={g} />)}
      </div>
    </div>
  );
}
