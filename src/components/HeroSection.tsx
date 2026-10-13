import Link from "next/link";
import type { MarketSummary, SectorPerformance } from "@/lib/types";
import type { AtmosphereToday } from "@/lib/data-loader";

// 與氣氛評估頁同一套分級
const moodColor: Record<string, string> = {
  過熱: "text-[#f05252]", 偏多: "text-[#f97316]",
  中性: "text-[#f59e0b]", 偏空: "text-[#4ade80]", 冰點: "text-[#22c55e]",
};

type Props = { summary: MarketSummary; topSector?: SectorPerformance; atmosphere?: AtmosphereToday | null };

export default function HeroSection({ summary, topSector, atmosphere }: Props) {
  const sectorUp = (topSector?.changePercent ?? 0) >= 0;
  const stats = [
    { label: "鎖定漲停", value: String(summary.limitUpCount), unit: "檔", color: "text-[#4f8cff]", border: "border-[#4f8cff]/20", href: "/limit-up" as string | undefined },
    {
      label: "強勢族群",
      value: topSector ? topSector.name : "—",
      unit: topSector ? `${sectorUp ? "+" : ""}${topSector.changePercent.toFixed(2)}%` : "",
      color: topSector ? (sectorUp ? "text-[#f05252]" : "text-[#22c55e]") : "text-[#38bdf8]",
      border: "border-[#38bdf8]/20",
      href: "/sectors" as string | undefined,
    },
    { label: "處置威脅", value: String(summary.dispositionCount), unit: "檔", color: "text-[#f59e0b]", border: "border-[#f59e0b]/20", href: "/disposition" as string | undefined },
    { label: "截收公告", value: String(summary.announcementCount || "—"), unit: "則", color: "text-[#a78bfa]", border: "border-[#a78bfa]/20", href: "/announcements" as string | undefined },
  ];

  return (
    <section className="relative overflow-hidden pt-16 pb-12 px-4">
      <div className="absolute inset-0 grid-scanline opacity-40 pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[320px] bg-[#4f8cff]/4 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute top-20 right-10 w-[300px] h-[300px] bg-[#38bdf8]/3 rounded-full blur-3xl pointer-events-none" />

      <div className="relative max-w-7xl mx-auto">

        {/* Mission badge */}
        <div className="flex justify-center mb-8">
          <div className="inline-flex items-center gap-3 px-4 py-1.5 rounded-full border border-[#4f8cff]/25 bg-[#4f8cff]/5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#4f8cff] animate-pulse" />
            <span className="text-[11px] text-[#4f8cff] font-mono tracking-[0.15em] uppercase">
              Mission Active · {summary.date} 資料已同步
            </span>
          </div>
        </div>

        {/* Headline */}
        <div className="text-center mb-5">
          <p className="text-[11px] font-mono text-[#7c8aa0] tracking-[0.3em] uppercase mb-3">
            Taiwan Stock Intelligence Hub
          </p>
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-white leading-tight">
            整合全域訊號
            <br />
            <span className="text-[#4f8cff]">構築你的情報制高點</span>
          </h1>
        </div>

        <p className="text-center text-slate-400 text-base sm:text-lg max-w-2xl mx-auto mb-4 leading-relaxed">
          Jagon Space Station 將台股每日漲停、籌碼異動、處置預警與公告情報，
          <br className="hidden sm:block" />
          壓縮為一個精準儀表板——<strong className="text-slate-300">情報優勢，即是勝勢。</strong>
        </p>

        {/* Market mood */}
        <div className="flex items-center justify-center gap-3 mb-10">
          <div className="h-px w-16 bg-gradient-to-r from-transparent to-[#243247]" />
          {atmosphere?.label ? (
            <Link href="/atmosphere" className={`text-sm font-bold font-mono hover:underline ${moodColor[atmosphere.label] ?? "text-slate-400"}`}>
              今日氣氛：{atmosphere.label}（{atmosphere.score}）
            </Link>
          ) : (
            <span className="text-sm font-bold font-mono text-slate-400">今日氣氛：—</span>
          )}
          <div className="h-px w-16 bg-gradient-to-l from-transparent to-[#243247]" />
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
                <div className="text-[11px] text-[#8b97ab] tracking-wide uppercase font-mono">{s.label}</div>
              </div>
            );
            return s.href ? (
              <Link key={s.label} href={s.href} className="block">{card}</Link>
            ) : (
              <div key={s.label}>{card}</div>
            );
          })}
        </div>

      </div>
    </section>
  );
}
