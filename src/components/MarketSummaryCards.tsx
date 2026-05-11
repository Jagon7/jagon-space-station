import { TrendingUp, Users, AlertTriangle, Radio, ShieldAlert, ArrowRight } from "lucide-react";

function daysRemaining(endDate: string): number {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const end   = new Date(endDate); end.setHours(0, 0, 0, 0);
  return Math.round((end.getTime() - today.getTime()) / 86400000);
}
import Link from "next/link";
import type { LimitUpStock, NoticeStock, DispositionStock, Announcement, SectorSummary } from "@/lib/types";

type Props = {
  stocks:        LimitUpStock[];
  sectors:       SectorSummary[];
  notice:        NoticeStock[];
  disposition:   DispositionStock[];
  announcements: Announcement[];
  updatedAt:     string;
};

const momentumStyle = {
  strong: { bar: "bg-[#ef4444]", dot: "bg-[#ef4444]", tag: "text-[#ef4444] bg-red-900/30 border-red-700/30" },
  normal: { bar: "bg-[#f59e0b]", dot: "bg-[#f59e0b]", tag: "text-[#f59e0b] bg-yellow-900/30 border-yellow-700/30" },
  weak:   { bar: "bg-slate-600", dot: "bg-slate-600",  tag: "text-slate-400 bg-slate-800/40 border-slate-600/30" },
};

function CardHeader({ icon: Icon, title, href, badge, iconColor = "text-[#00d4aa]" }: {
  icon: React.ElementType; title: string; href: string; badge?: string; iconColor?: string;
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-2">
        <Icon className={`w-4 h-4 ${iconColor}`} />
        <h2 className="text-sm font-semibold text-white tracking-wide">{title}</h2>
        {badge && <span className="text-[10px] font-mono text-slate-500 bg-[#1e2a3a] px-1.5 py-0.5 rounded">{badge}</span>}
      </div>
      <Link href={href} className="flex items-center gap-1 text-xs text-slate-500 hover:text-[#00d4aa] transition-colors font-mono">
        展開詳情 <ArrowRight className="w-3 h-3" />
      </Link>
    </div>
  );
}

export default function MarketSummaryCards({ stocks, sectors, notice, disposition, announcements, updatedAt }: Props) {
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });
  const displayDate = new Date(updatedAt).toLocaleDateString("zh-TW", { year: "numeric", month: "2-digit", day: "2-digit" });
  const topStocks   = stocks.slice(0, 5);
  const maxCount    = sectors[0]?.count ?? 1;

  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
      <div className="mb-6">
        <p className="text-[10px] font-mono text-slate-600 tracking-[0.25em] uppercase mb-1">Daily Debrief</p>
        <h2 className="text-lg font-bold text-white">今日盤面戰情</h2>
        <p className="text-sm text-slate-500 mt-0.5">{displayDate} · 資料同步於 {updatedTime}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* 漲停訊號 */}
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5 card-hover">
          <CardHeader icon={TrendingUp} title="漲停訊號鎖定" href="/limit-up" badge={`${stocks.length} 檔`} />
          <div className="space-y-0.5">
            {topStocks.map((s) => (
              <div key={s.code} className="flex items-center justify-between py-2 border-b border-[#1e2a3a]/50 last:border-0">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-slate-600 w-10">{s.code}</span>
                  <span className="text-sm text-slate-200">{s.name}</span>
                  <span className="tag-neutral text-[10px]">{s.sector}</span>
                </div>
                <span className="text-sm font-mono font-semibold text-[#ef4444]">+{s.change.toFixed(2)}%</span>
              </div>
            ))}
            {stocks.length > 5 && (
              <div className="pt-2 text-center">
                <span className="text-xs text-slate-600">另有 {stocks.length - 5} 檔訊號 · </span>
                <Link href="/limit-up" className="text-xs text-[#00d4aa] hover:underline font-mono">進入模組</Link>
              </div>
            )}
          </div>
        </div>

        {/* 族群雷達 */}
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5 card-hover">
          <CardHeader icon={Users} title="資金族群雷達" href="/stats" badge={`${sectors.length} 族群`} />
          {sectors.length > 0 ? (
            <div className="space-y-3">
              {sectors.map((s) => {
                const style = momentumStyle[s.momentum];
                return (
                  <div key={s.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${style.dot}`} />
                      <span className="text-sm text-slate-300">{s.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 rounded-full bg-[#1e2a3a] w-24 overflow-hidden">
                        <div className={`h-full rounded-full ${style.bar}`} style={{ width: `${(s.count / maxCount) * 100}%` }} />
                      </div>
                      <span className={`text-xs font-mono border px-1.5 py-0.5 rounded ${style.tag}`}>{s.count} 檔</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-slate-600 font-mono">今日無明顯族群集中</p>
          )}
        </div>

        {/* 注意股 */}
        <div className="rounded-xl border border-[#f59e0b]/20 bg-[#0d1220] p-5 card-hover">
          <CardHeader icon={AlertTriangle} title="注意股" href="/disposition" badge={`${notice.length} 檔`} iconColor="text-[#f59e0b]" />
          {notice.length > 0 ? (
            <div className="space-y-0.5">
              {notice.slice(0, 5).map((s) => (
                <div key={s.code} className="flex items-center justify-between py-2 border-b border-[#1e2a3a]/50 last:border-0">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-slate-600 w-10">{s.code}</span>
                    <span className="text-sm text-slate-200">{s.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500 font-mono">累計 {s.noticeCount} 次</span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded text-[#f59e0b] bg-yellow-900/30">注意</span>
                  </div>
                </div>
              ))}
              {notice.length > 5 && (
                <div className="pt-2 text-center">
                  <Link href="/disposition" className="text-xs text-[#f59e0b] hover:underline font-mono">查看全部 {notice.length} 檔</Link>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-600 font-mono py-4 text-center">今日無注意股公告</p>
          )}
        </div>

        {/* 處置股 */}
        <div className="rounded-xl border border-[#ef4444]/20 bg-[#0d1220] p-5 card-hover">
          <CardHeader icon={ShieldAlert} title="處置股" href="/disposition" badge={`${disposition.length} 檔`} iconColor="text-[#ef4444]" />
          {disposition.length > 0 ? (
            <div className="space-y-0.5">
              {disposition.slice(0, 5).map((s) => {
                const days   = daysRemaining(s.endDate);
                const urgent = days <= 2;
                const soon   = days <= 5;
                return (
                <div key={`${s.code}-${s.announceDate}`} className="flex items-center justify-between py-2 border-b border-[#1e2a3a]/50 last:border-0">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-slate-600 w-10">{s.code}</span>
                    <span className="text-sm text-slate-200">{s.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-mono font-semibold ${urgent ? "text-[#22c55e]" : soon ? "text-[#f59e0b]" : "text-slate-500"}`}>
                      {days <= 0 ? "今日到期" : `剩 ${days} 天`}
                    </span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded text-[#ef4444] bg-red-900/30 flex-shrink-0">處置中</span>
                  </div>
                </div>
                );
              })}
              {disposition.length > 5 && (
                <div className="pt-2 text-center">
                  <Link href="/disposition" className="text-xs text-[#ef4444] hover:underline font-mono">查看全部 {disposition.length} 檔</Link>
                </div>
              )}
              <p className="text-[10px] text-slate-700 pt-1 font-mono">⚠ 已進入 5 分鐘撮合，流動性降低</p>
            </div>
          ) : (
            <p className="text-xs text-slate-600 font-mono py-4 text-center">目前無處置股</p>
          )}
        </div>

        {/* 情報截收 — 全寬 */}
        <div className="md:col-span-2 rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5 card-hover">
          <CardHeader icon={Radio} title="情報截收站" href="/announcements" badge="5 分鐘掃頻" />
          {announcements.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
              {announcements.slice(0, 6).map((a, i) => (
                <div key={i} className="flex items-start gap-3 py-2 border-b border-[#1e2a3a]/50 last:border-0 sm:[&:nth-last-child(2)]:border-0">
                  <span className="font-mono text-xs text-slate-600 w-10 flex-shrink-0 mt-0.5">{a.time}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-500">{a.code}</span>
                      <span className="text-sm text-slate-200 truncate">{a.name}</span>
                      {a.important && <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[#ef4444] animate-pulse" />}
                    </div>
                    <span className={`text-xs mt-0.5 inline-block ${a.important ? "text-[#f59e0b]" : "text-slate-500"}`}>{a.type}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-600 font-mono py-2 text-center">公告資料待接 MOPS API</p>
          )}
        </div>

      </div>
    </section>
  );
}
