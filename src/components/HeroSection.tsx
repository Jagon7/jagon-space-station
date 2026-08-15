import Link from "next/link";
import { TrendingUp, Shield, Bell, BarChart2 } from "lucide-react";
import type { MarketSummary, SectorPerformance } from "@/lib/types";

const features = [
  { icon: TrendingUp, label: "強勢訊號偵測",   desc: "即時鎖定每日漲停股，解析族群輪動脈絡" },
  { icon: BarChart2,  label: "資金流向偵察",   desc: "券差、主動ETF持股異動，籌碼動向全握" },
  { icon: Shield,     label: "風險威脅評估",   desc: "提前計算處置門檻機率，化解潛在風險" },
  { icon: Bell,       label: "情報截收系統",   desc: "每 5 分鐘全頻掃描，重訊零時差抵達" },
];

const moodColor: Record<string, string> = {
  強勢: "text-[#ef4444]", 偏強: "text-[#f97316]",
  中性: "text-[#f59e0b]", 偏弱: "text-[#00d4aa]", 弱勢: "text-[#22c55e]",
};

type Props = { summary: MarketSummary; topSector?: SectorPerformance };

export default function HeroSection({ summary, topSector }: Props) {
  const sectorUp = (topSector?.changePercent ?? 0) >= 0;
  const stats = [
    { label: "鎖定漲停", value: String(summary.limitUpCount), unit: "檔", color: "text-[#00d4aa]", border: "border-[#00d4aa]/20", href: undefined as string | undefined },
    {
      label: "強勢族群",
      value: topSector ? topSector.name : "—",
      unit: topSector ? `${sectorUp ? "+" : ""}${topSector.changePercent.toFixed(2)}%` : "",
      color: topSector ? (sectorUp ? "text-[#ef4444]" : "text-[#22c55e]") : "text-[#3b82f6]",
      border: "border-[#3b82f6]/20",
      href: "/sectors" as string | undefined,
    },
    { label: "處置威脅", value: String(summary.dispositionCount), unit: "檔", color: "text-[#f59e0b]", border: "border-[#f59e0b]/20", href: undefined as string | undefined },
    { label: "截收公告", value: String(summary.announcementCount || "—"), unit: "則", color: "text-[#a78bfa]", border: "border-[#a78bfa]/20", href: undefined as string | undefined },
  ];

  return (
    <section className="relative overflow-hidden pt-16 pb-12 px-4">
      <div className="absolute inset-0 grid-scanline opacity-40 pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[320px] bg-[#00d4aa]/4 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute top-20 right-10 w-[300px] h-[300px] bg-[#3b82f6]/3 rounded-full blur-3xl pointer-events-none" />

      <div className="relative max-w-7xl mx-auto">

        {/* Mission badge */}
        <div className="flex justify-center mb-8">
          <div className="inline-flex items-center gap-3 px-4 py-1.5 rounded-full border border-[#00d4aa]/25 bg-[#00d4aa]/5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00d4aa] animate-pulse" />
            <span className="text-[11px] text-[#00d4aa] font-mono tracking-[0.15em] uppercase">
              Mission Active · {summary.date} 資料已同步
            </span>
          </div>
        </div>

        {/* Headline */}
        <div className="text-center mb-5">
          <p className="text-[11px] font-mono text-slate-600 tracking-[0.3em] uppercase mb-3">
            Taiwan Stock Intelligence Hub
          </p>
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-white leading-tight">
            整合全域訊號
            <br />
            <span className="text-[#00d4aa]">構築你的情報制高點</span>
          </h1>
        </div>

        <p className="text-center text-slate-400 text-base sm:text-lg max-w-2xl mx-auto mb-4 leading-relaxed">
          Jagon Space Station 將台股每日漲停、籌碼異動、處置預警與公告情報，
          <br className="hidden sm:block" />
          壓縮為一個精準儀表板——<strong className="text-slate-300">情報優勢，即是勝勢。</strong>
        </p>

        {/* Market mood */}
        <div className="flex items-center justify-center gap-3 mb-10">
          <div className="h-px w-16 bg-gradient-to-r from-transparent to-[#1e2a3a]" />
          <span className={`text-sm font-bold font-mono ${moodColor[summary.marketMood] ?? "text-slate-400"}`}>
            今日氣氛：{summary.marketMood}
          </span>
          <div className="h-px w-16 bg-gradient-to-l from-transparent to-[#1e2a3a]" />
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-12">
          {stats.map((s) => {
            const card = (
              <div className={`rounded-xl border ${s.border} bg-[#0d1220] p-4 text-center card-hover ${s.href ? "cursor-pointer" : ""}`}>
                <div className={`text-3xl font-bold font-mono ${s.color} mb-1`}>
                  {s.value}
                  <span className="text-sm font-normal ml-1 opacity-70">{s.unit}</span>
                </div>
                <div className="text-[11px] text-slate-500 tracking-wide uppercase font-mono">{s.label}</div>
              </div>
            );
            return s.href ? (
              <Link key={s.label} href={s.href} className="block">{card}</Link>
            ) : (
              <div key={s.label}>{card}</div>
            );
          })}
        </div>

        {/* Features */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {features.map((f) => (
            <div key={f.label} className="flex items-start gap-3 p-4 rounded-xl border border-[#1e2a3a] bg-[#0d1220] card-hover group">
              <div className="w-9 h-9 rounded-lg bg-[#1e2a3a] flex items-center justify-center flex-shrink-0 group-hover:bg-[#00d4aa]/10 transition-colors">
                <f.icon className="w-4 h-4 text-[#00d4aa]" />
              </div>
              <div>
                <div className="text-sm font-semibold text-white">{f.label}</div>
                <div className="text-xs text-slate-500 mt-0.5 leading-relaxed">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
