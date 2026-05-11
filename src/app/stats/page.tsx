import PageShell from "@/components/PageShell";
import { LimitUpTrendChart, SectorTrendChart } from "@/components/charts/LimitUpChart";
import { mockMarketSummary } from "@/lib/mock-data";

export default function StatsPage() {
  const { limitUpCount, sectorCount, dispositionCount, announcementCount, marketMood, taiexChange } = mockMarketSummary;

  return (
    <PageShell
      title="統計戰報"
      subtitle="2026/05/07 · 整合盤面量化數據"
      badge="Mission Stats"
    >
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        {[
          { label: "市場氣氛", value: marketMood,              unit: "",  color: "text-[#00d4aa]" },
          { label: "加權指數", value: `+${taiexChange}%`,      unit: "",  color: "text-[#ef4444]" },
          { label: "漲停檔數", value: String(limitUpCount),    unit: "檔", color: "text-[#00d4aa]" },
          { label: "觸及族群", value: String(sectorCount),     unit: "個", color: "text-[#3b82f6]" },
          { label: "今日公告", value: String(announcementCount), unit: "則", color: "text-[#a78bfa]" },
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
        <LimitUpTrendChart />
        <SectorTrendChart />
      </div>

      {/* Disposition count */}
      <div className="rounded-xl border border-[#f59e0b]/20 bg-[#f59e0b]/5 p-5 flex items-center gap-4">
        <div className="text-4xl font-bold font-mono text-[#f59e0b]">{dispositionCount}</div>
        <div>
          <div className="text-sm font-semibold text-white">檔個股列入處置威脅監控</div>
          <div className="text-xs text-slate-500 mt-0.5">每日 19:00 更新評估結果，API 串接後即時同步</div>
        </div>
      </div>
    </PageShell>
  );
}
