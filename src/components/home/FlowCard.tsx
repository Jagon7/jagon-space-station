"use client";

import Link from "next/link";
import { Activity, ArrowRight } from "lucide-react";
import { Bar, useFlow } from "@/components/flow/FlowDashboard";

const yi = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)} 億`;
const tone = (v: number) => (v > 0 ? "text-[#f05252]" : v < 0 ? "text-[#22c55e]" : "text-[#8b97ab]");

/** 首頁的即時資金流：各產業主動買賣淨額（流入前 6、流出前 6），每 90 秒自動更新 */
export default function FlowCard() {
  const { data } = useFlow();
  if (!data) return null;
  const secs = data.sectors.filter((s) => s.amt > 0);
  const inflow = secs.filter((s) => s.net > 0).slice(0, 6);
  const outflow = secs.filter((s) => s.net < 0).slice(-6).reverse();
  const max = Math.max(...secs.map((s) => Math.abs(s.net)), 1);
  const hm = new Date(data.updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Taipei" });
  const last = data.slices.length ? data.slices[data.slices.length - 1] : null;
  const row = (s: (typeof secs)[number]) => (
    <Link key={s.name} href="/flow" className="grid grid-cols-[5.5rem_1fr_4.5rem] items-center gap-2 rounded px-1 py-1 hover:bg-white/5 text-[13px]">
      <span className="text-slate-200 truncate">{s.name}</span>
      <Bar v={s.net} max={max} />
      <span className={`text-right font-mono text-xs ${tone(s.net)}`}>{yi(s.net)}</span>
    </Link>
  );
  return (
    <div className="rounded-xl border border-[#243247] bg-[#0d1220] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#f59e0b]" />
          <h3 className="text-sm font-semibold text-white">即時資金流</h3>
          <span className="text-[11px] text-[#8b97ab]">
            {data.status === "live" ? <span className="text-[#22c55e]">● 盤中</span> : data.status === "pre" ? "盤前" : "已收盤"}・{Number(data.date.slice(5, 7))}/{Number(data.date.slice(8, 10))} {hm}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-[#8b97ab]">全市場主動買賣 <span className={`font-mono ${tone(data.total.net)}`}>{yi(data.total.net)}</span></span>
          <Link href="/flow" className="flex items-center gap-1 text-xs text-[#8b97ab] hover:text-[#4f8cff] font-mono">詳情 <ArrowRight className="w-3 h-3" /></Link>
        </div>
      </div>
      <div className="grid gap-x-8 gap-y-1 md:grid-cols-2">
        <div>
          <div className="text-[11px] text-[#8b97ab] mb-1">主動買超（資金流入）</div>
          {inflow.length ? inflow.map(row) : <p className="text-xs text-[#7c8aa0]">沒有產業淨流入</p>}
        </div>
        <div>
          <div className="text-[11px] text-[#8b97ab] mb-1">主動賣超（資金流出）</div>
          {outflow.length ? outflow.map(row) : <p className="text-xs text-[#7c8aa0]">沒有產業淨流出</p>}
        </div>
      </div>
      <p className="mt-2 text-[10px] text-[#7c8aa0]">外盤（主動買）− 內盤（主動賣）成交金額，前 200 大個股按產業加總；每 90 秒自動更新{last ? `，最新 15 分鐘切片 ${last}` : ""}。</p>
    </div>
  );
}
