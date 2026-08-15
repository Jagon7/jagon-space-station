export const dynamic = "force-dynamic";

import Link from "next/link";
import PageShell from "@/components/PageShell";
import { getSectorPerformance, getLastUpdated } from "@/lib/data-loader";
import { TrendingUp, TrendingDown } from "lucide-react";

export default async function SectorsPage() {
  const [sectors, updatedAt] = await Promise.all([getSectorPerformance(), getLastUpdated()]);
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });

  const upCount = sectors.filter((s) => s.changePercent > 0).length;
  const downCount = sectors.filter((s) => s.changePercent < 0).length;
  const maxAbs = Math.max(1, ...sectors.map((s) => Math.abs(s.changePercent)));

  return (
    <PageShell
      title="族群強弱排行"
      subtitle={`${sectors.length} 個族群 · 更新 ${updatedTime}`}
      badge="Sector Ranking"
    >
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 mb-6 text-xs text-slate-400 leading-relaxed">
        <span className="text-white font-semibold">排名依據</span>：TWSE 官方類股指數當日漲跌幅（市值加權），
        不是統計漲停檔數，而是該族群實際的整體漲跌表現。
      </div>

      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="rounded-xl border border-[#ef4444]/20 bg-[#ef4444]/5 p-4 text-center">
          <div className="text-2xl font-bold font-mono text-[#ef4444]">{upCount}</div>
          <div className="text-[11px] text-slate-500 font-mono mt-1">上漲族群</div>
        </div>
        <div className="rounded-xl border border-[#22c55e]/20 bg-[#22c55e]/5 p-4 text-center">
          <div className="text-2xl font-bold font-mono text-[#22c55e]">{downCount}</div>
          <div className="text-[11px] text-slate-500 font-mono mt-1">下跌族群</div>
        </div>
      </div>

      {sectors.length === 0 ? (
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-8 text-center text-sm text-slate-600 font-mono">
          請等待 Actions 執行後重新整理
        </div>
      ) : (
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
          {sectors.map((s, i) => {
            const isUp = s.changePercent >= 0;
            const color = isUp ? "text-[#ef4444]" : "text-[#22c55e]";
            const barColor = isUp ? "bg-[#ef4444]/25" : "bg-[#22c55e]/25";
            const barWidth = `${(Math.abs(s.changePercent) / maxAbs) * 100}%`;
            const Icon = isUp ? TrendingUp : TrendingDown;
            return (
              <Link
                key={s.name}
                href={`/sectors/${encodeURIComponent(s.name)}`}
                className="flex items-center gap-4 px-5 py-3 border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#1e2a3a]/20 transition-colors"
              >
                <span className="w-6 text-xs font-mono text-slate-600 text-right flex-shrink-0">{i + 1}</span>
                <span className="w-20 text-sm text-slate-200 flex-shrink-0">{s.name}</span>
                <div className="flex-1 h-2 rounded-full bg-[#1e2a3a] overflow-hidden relative">
                  <div
                    className={`h-full rounded-full ${barColor}`}
                    style={{ width: barWidth, marginLeft: isUp ? "50%" : `${50 - (Math.abs(s.changePercent) / maxAbs) * 50}%` }}
                  />
                  <div className="absolute left-1/2 top-0 bottom-0 w-px bg-[#334155]" />
                </div>
                <span className={`w-20 flex items-center justify-end gap-1 font-mono text-sm font-semibold ${color}`}>
                  <Icon className="w-3.5 h-3.5" />
                  {isUp ? "+" : ""}{s.changePercent.toFixed(2)}%
                </span>
              </Link>
            );
          })}
        </div>
      )}

      <div className="mt-6 pt-4 border-t border-[#1e2a3a] text-[10px] font-mono text-slate-700 text-center">
        資料來源：TWSE 開放資料平台 · 僅供研究參考，不構成投資建議
      </div>
    </PageShell>
  );
}
