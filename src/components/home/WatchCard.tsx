"use client";

import Link from "next/link";
import { ArrowRight, Star } from "lucide-react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";

type Sig = { date: string; quotes: Record<string, [string, number, number | null]>; sig: Record<string, [string, string, number][]> };

/** 首頁的自選股快覽：收盤、漲跌、最重要的兩則訊號（自選股存在這台瀏覽器） */
export default function WatchCard() {
  const wl = useWatchlist();
  const { data } = useStaticJson<Sig>(wl.list.length ? "signals.json" : null);
  return (
    <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2"><Star className="w-4 h-4 text-[#f59e0b]" /><h3 className="text-sm font-semibold text-white">我的自選股</h3>
          {!!wl.list.length && <span className="text-[11px] text-[#8b97ab]">{wl.list.length} 檔{data ? `・${Number(data.date.slice(5, 7))}/${Number(data.date.slice(8, 10))} 收盤` : ""}</span>}</div>
        <Link href="/watchlist" className="flex items-center gap-1 text-xs text-[#8b97ab] hover:text-[#4f8cff] font-mono">詳情 <ArrowRight className="w-3 h-3" /></Link>
      </div>
      {!wl.list.length ? (
        <p className="text-xs text-[#7c8aa0]">還沒有自選股。在任何頁面的股票旁按 ★ 就會加入，這裡會顯示收盤、漲跌與最新訊號。</p>
      ) : !data ? (
        <p className="text-xs text-[#7c8aa0]">載入中…</p>
      ) : (
        <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
          {wl.list.slice(0, 12).map((c) => {
            const q = data.quotes[c];
            const s = (data.sig[c] ?? []).slice(0, 2);
            const chg = q?.[2];
            return (
              <Link key={c} href={`/search/?code=${c}`} className="block rounded-md px-2 py-1.5 hover:bg-white/5">
                <div className="flex items-center justify-between text-sm">
                  <span><span className="text-slate-200">{q?.[0] ?? c}</span><span className="ml-1.5 font-mono text-[11px] text-[#7c8aa0]">{c}</span></span>
                  <span className="font-mono text-xs">{q ? <><span className="text-slate-300">{q[1]}</span><span className={`ml-2 ${chg == null || chg === 0 ? "text-[#8b97ab]" : chg > 0 ? "text-[#f05252]" : "text-[#22c55e]"}`}>{chg == null ? "—" : `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}</span></> : "—"}</span>
                </div>
                {!!s.length && <div className="text-[11px] text-[#8b97ab] truncate">{s.map(([cat, text, d]) => <span key={text} className="mr-2"><span className={d > 0 ? "text-[#f05252]" : d < 0 ? "text-[#22c55e]" : ""}>{d > 0 ? "▲" : d < 0 ? "▼" : "・"}</span>{cat}｜{text}</span>)}</div>}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
