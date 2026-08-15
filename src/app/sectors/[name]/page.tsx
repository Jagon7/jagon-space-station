export const dynamic = "force-dynamic";

import PageShell from "@/components/PageShell";
import { getSectorStocks, getSectorPerformance, getLastUpdated } from "@/lib/data-loader";
import { TrendingUp, TrendingDown } from "lucide-react";

export default async function SectorStocksPage({ params }: { params: Promise<{ name: string }> }) {
  const { name: encodedName } = await params;
  const name = decodeURIComponent(encodedName);

  const [sectorStocks, sectorPerf, updatedAt] =
    await Promise.all([getSectorStocks(), getSectorPerformance(), getLastUpdated()]);
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });

  const stocks = sectorStocks[name] ?? [];
  const perf = sectorPerf.find((s) => s.name === name);
  const upCount = stocks.filter((s) => s.changePercent > 0).length;
  const downCount = stocks.filter((s) => s.changePercent < 0).length;

  return (
    <PageShell
      title={`${name}族群個股`}
      subtitle={`${stocks.length} 檔個股 · 更新 ${updatedTime}`}
      badge="Sector Stocks"
      back="/sectors"
    >
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 text-center">
          <div className={`text-2xl font-bold font-mono ${perf && perf.changePercent >= 0 ? "text-[#ef4444]" : "text-[#22c55e]"}`}>
            {perf ? `${perf.changePercent >= 0 ? "+" : ""}${perf.changePercent.toFixed(2)}%` : "—"}
          </div>
          <div className="text-[11px] text-slate-500 font-mono mt-1">族群指數漲跌</div>
        </div>
        <div className="rounded-xl border border-[#ef4444]/20 bg-[#ef4444]/5 p-4 text-center">
          <div className="text-2xl font-bold font-mono text-[#ef4444]">{upCount}</div>
          <div className="text-[11px] text-slate-500 font-mono mt-1">上漲檔數</div>
        </div>
        <div className="rounded-xl border border-[#22c55e]/20 bg-[#22c55e]/5 p-4 text-center">
          <div className="text-2xl font-bold font-mono text-[#22c55e]">{downCount}</div>
          <div className="text-[11px] text-slate-500 font-mono mt-1">下跌檔數</div>
        </div>
      </div>

      {stocks.length === 0 ? (
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-8 text-center text-sm text-slate-600 font-mono">
          查無此族群資料，請等待 Actions 執行後重新整理
        </div>
      ) : (
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-mono text-slate-600 uppercase tracking-wider border-b border-[#1e2a3a]">
                  <th className="text-left px-4 py-3">股號</th>
                  <th className="text-left px-4 py-3">名稱</th>
                  <th className="text-center px-3 py-3">市場</th>
                  <th className="text-right px-4 py-3">漲跌幅</th>
                  <th className="text-right px-4 py-3">收盤</th>
                  <th className="text-right px-4 py-3">成交金額</th>
                </tr>
              </thead>
              <tbody>
                {stocks.map((s) => {
                  const isUp = s.changePercent >= 0;
                  const color = isUp ? "text-[#ef4444]" : "text-[#22c55e]";
                  const Icon = isUp ? TrendingUp : TrendingDown;
                  return (
                    <tr
                      key={s.code}
                      className="border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#1e2a3a]/20 transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-slate-500 whitespace-nowrap">{s.code}</td>
                      <td className="px-4 py-3 text-slate-200 whitespace-nowrap">{s.name}</td>
                      <td className="px-3 py-3 text-center">
                        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                          s.market === "上市" ? "text-[#3b82f6] bg-[#3b82f6]/10" : "text-[#a78bfa] bg-[#a78bfa]/10"
                        }`}>
                          {s.market}
                        </span>
                      </td>
                      <td className={`px-4 py-3 text-right font-mono font-semibold whitespace-nowrap ${color}`}>
                        <span className="inline-flex items-center gap-1">
                          <Icon className="w-3.5 h-3.5" />
                          {isUp ? "+" : ""}{s.changePercent.toFixed(2)}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-slate-300 whitespace-nowrap">
                        {s.closePrice.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-slate-400 whitespace-nowrap">
                        {(s.tradeValue / 1e8).toFixed(2)} 億
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="mt-6 pt-4 border-t border-[#1e2a3a] text-[10px] font-mono text-slate-700 text-center">
        資料來源：TWSE / TPEx 開放資料平台 · 僅供研究參考，不構成投資建議
      </div>
    </PageShell>
  );
}
