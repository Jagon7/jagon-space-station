export const dynamic = "force-dynamic";

import PageShell from "@/components/PageShell";
import { LimitUpTrendChart, SectorTrendChart } from "@/components/charts/LimitUpChart";
import { getMarketSummary, getMarketHistory, getLastUpdated } from "@/lib/data-loader";

export default async function StatsPage() {
  const [summary, history, updatedAt] =
    await Promise.all([getMarketSummary(), getMarketHistory(), getLastUpdated()]);
  const { limitUpCount, sectorCount, dispositionCount, announcementCount, marketMood, taiexChange } = summary;
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });
  const moodColor = marketMood === "強勢" || marketMood === "偏強" ? "text-[#00d4aa]" : marketMood === "中性" ? "text-[#3b82f6]" : "text-[#ef4444]";
  const taiexColor = taiexChange >= 0 ? "text-[#ef4444]" : "text-[#22c55e]";
  const taiexSign = taiexChange >= 0 ? "+" : "";

  return (
    <PageShell
      title="統計戰報"
      subtitle={`${summary.date} · 整合盤面量化數據 · 更新 ${updatedTime}`}
      badge="Mission Stats"
    >
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        {[
          { label: "市場氣氛", value: marketMood,                    unit: "",  color: moodColor },
          { label: "加權指數", value: `${taiexSign}${taiexChange}%`, unit: "",  color: taiexColor },
          { label: "漲停檔數", value: String(limitUpCount),          unit: "檔", color: "text-[#00d4aa]" },
          { label: "觸及族群", value: String(sectorCount),           unit: "個", color: "text-[#3b82f6]" },
          { label: "今日公告", value: String(announcementCount),     unit: "則", color: "text-[#a78bfa]" },
        ].map((kpi) => (
          <div key={kpi.label} className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 text-center">
            <div className={`text-2xl font-bold font-mono ${kpi.color}`}>
              {kpi.value}
              {kpi.unit && <span className="text-sm font-normal ml-0.5 opacity-70">{kpi.unit}</span>}
            </div>
            <div className="text-[11px] text-slate-500 font-mono tracking-wide mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
        <LimitUpTrendChart history={history} />
        <SectorTrendChart history={history} />
      </div>

      {/* Disposition count */}
      <div className="rounded-xl border border-[#f59e0b]/20 bg-[#f59e0b]/5 p-5 flex items-center gap-4">
        <div className="text-4xl font-bold font-mono text-[#f59e0b]">{dispositionCount}</div>
        <div>
          <div className="text-sm font-semibold text-white">檔個股列入處置威脅監控</div>
          <div className="text-xs text-slate-500 mt-0.5">每日 19:00 自動更新（GitHub Actions → data-loader 即時讀取）</div>
        </div>
      </div>
    </PageShell>
  );
}
