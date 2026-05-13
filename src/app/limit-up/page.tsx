export const dynamic = "force-dynamic";

import PageShell from "@/components/PageShell";
import { LimitUpTrendChart, SectorTrendChart } from "@/components/charts/LimitUpChart";
import { getLimitUpStocks, getMarketSummary, getLastUpdated } from "@/lib/data-loader";

function InstiCell({ value, bold }: { value?: number | null; bold?: boolean }) {
  if (value == null) return <td className="px-3 py-3 text-right font-mono text-slate-700 text-xs">—</td>;
  const color = value > 0 ? "text-[#ef4444]" : value < 0 ? "text-[#22c55e]" : "text-slate-500";
  const sign  = value > 0 ? "+" : "";
  return (
    <td className={`px-3 py-3 text-right font-mono text-xs ${color} ${bold ? "font-semibold" : ""}`}>
      {sign}{value.toLocaleString()}
    </td>
  );
}

export default async function LimitUpPage() {
  const [stocks, summary, updatedAt] =
    await Promise.all([getLimitUpStocks(), getMarketSummary(), getLastUpdated()]);
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });

  const sectors = Array.from(new Set(stocks.map((s) => s.sector)));

  return (
    <PageShell
      title="漲停訊號鎖定"
      subtitle={`${summary.date} · ${summary.limitUpCount} 檔訊號入站 · 更新 ${updatedTime}`}
      badge="Limit-Up Signal"
    >
      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
        <LimitUpTrendChart />
        <SectorTrendChart />
      </div>

      {/* Sector filter tabs */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button className="px-3 py-1 rounded-full text-xs font-mono bg-[#00d4aa]/10 text-[#00d4aa] border border-[#00d4aa]/30">
          全部 {stocks.length}
        </button>
        {sectors.slice(0, 8).map((s) => (
          <button
            key={s}
            className="px-3 py-1 rounded-full text-xs font-mono bg-[#1e2a3a] text-slate-400 border border-[#1e2a3a] hover:border-[#00d4aa]/20 hover:text-slate-200 transition-colors"
          >
            {s}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-max min-w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e2a3a] text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                <th className="text-left px-4 py-3">股號</th>
                <th className="text-left px-4 py-3">名稱</th>
                <th className="text-left px-4 py-3">族群</th>
                <th className="text-center px-3 py-3">市場</th>
                <th className="text-right px-4 py-3">漲幅</th>
                <th className="text-right px-4 py-3">成交金額 ↓</th>
                <th className="text-right px-4 py-3">收盤</th>
                <th className="text-right px-3 py-3 text-[#60a5fa]">外資</th>
                <th className="text-right px-3 py-3 text-[#a78bfa]">投信</th>
                <th className="text-right px-3 py-3 text-[#34d399]">自營</th>
                <th className="text-right px-3 py-3 text-[#f59e0b]">三大</th>
                <th className="text-left px-4 py-3">漲停原因</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((s) => (
                <tr
                  key={s.code}
                  className="border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#1e2a3a]/30 transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-slate-500">{s.code}</td>
                  <td className="px-4 py-3 font-medium text-slate-100 whitespace-nowrap">{s.name}</td>
                  <td className="px-4 py-3">
                    <span className="tag-neutral">{s.sector}</span>
                  </td>
                  <td className="px-3 py-3 text-center">
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                      s.market === "上市"
                        ? "text-[#3b82f6] bg-[#3b82f6]/10"
                        : "text-[#a78bfa] bg-[#a78bfa]/10"
                    }`}>
                      {s.market ?? "上市"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-[#ef4444]">
                    +{s.change.toFixed(2)}%
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300">
                    {s.tradeValue
                      ? `${(s.tradeValue / 1e8).toFixed(2)} 億`
                      : `${s.volume.toLocaleString()} 張`}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-200">
                    {s.closePrice.toLocaleString()}
                  </td>
                  <InstiCell value={s.instiForeign} />
                  <InstiCell value={s.instiTrust} />
                  <InstiCell value={s.instiDealer} />
                  <InstiCell value={s.instiTotal} bold />
                  <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
                    {s.reason || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 border-t border-[#1e2a3a] flex items-center justify-between">
          <span className="text-xs text-slate-600 font-mono">共 {stocks.length} 筆訊號 · {summary.date}</span>
          <span className="text-xs text-slate-600 font-mono">三大法人單位：張 · 資料來源：TWSE / TPEx</span>
        </div>
      </div>
    </PageShell>
  );
}
