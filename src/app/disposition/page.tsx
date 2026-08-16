export const dynamic = "force-dynamic";

import PageShell from "@/components/PageShell";
import { getNoticeStocks, getDispositionStocks, getLastUpdated } from "@/lib/data-loader";
import { AlertTriangle, ShieldAlert, Info, Timer } from "lucide-react";

function daysRemaining(endDate: string): number {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const end   = new Date(endDate); end.setHours(0, 0, 0, 0);
  return Math.round((end.getTime() - today.getTime()) / 86400000);
}

export default async function DispositionPage() {
  const [notice, disposition, updatedAt] =
    await Promise.all([getNoticeStocks(), getDispositionStocks(), getLastUpdated()]);
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });

  const expiringSoon = disposition
    .filter((s) => daysRemaining(s.endDate) <= 3)
    .sort((a, b) => daysRemaining(a.endDate) - daysRemaining(b.endDate));

  return (
    <PageShell
      title="注意 / 處置監控"
      subtitle={`注意 ${notice.length} 檔 · 處置 ${disposition.length} 檔 · 更新 ${updatedTime}`}
      badge="Notice & Disposition"
    >
      {/* 說明欄 */}
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 mb-6 flex gap-3">
        <Info className="w-4 h-4 text-[#3b82f6] flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-400 leading-relaxed space-y-1">
          <p><span className="text-[#f59e0b] font-semibold">注意股</span>：連續觸及漲跌幅、成交量異常等警示標準，尚未正式處置，每日收盤後公告。</p>
          <p><span className="text-[#ef4444] font-semibold">處置股</span>：已由主管機關正式公告，進入 5 分鐘撮合機制，需注意流動性風險。</p>
          <p className="text-slate-600">本站資料來源：台灣證券交易所公告，僅供參考，不構成任何投資建議。</p>
        </div>
      </div>

      {/* ── 即將出關（3 天內） ── */}
      {expiringSoon.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center gap-2 mb-3">
            <Timer className="w-4 h-4 text-[#22c55e]" />
            <h2 className="text-sm font-semibold text-white">即將出關</h2>
            <span className="text-[10px] font-mono text-[#22c55e] bg-[#22c55e]/10 border border-[#22c55e]/20 px-1.5 py-0.5 rounded">
              {expiringSoon.length} 檔 · 3 天內
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {expiringSoon.map((s) => {
              const days = daysRemaining(s.endDate);
              return (
                <div
                  key={`${s.code}-${s.announceDate}`}
                  className="rounded-xl border border-[#22c55e]/30 bg-[#22c55e]/5 p-4 flex items-center justify-between"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-slate-300">{s.code}</span>
                      <span className="font-semibold text-white">{s.name}</span>
                      {s.market && <span className="text-[10px] font-mono text-slate-600 bg-[#1e2a3a] px-1 py-0.5 rounded">{s.market}</span>}
                    </div>
                    <div className="text-[11px] text-slate-500 font-mono mt-1">至 {s.period.split(/[~～]/)[1] ?? s.endDate}</div>
                  </div>
                  <span className="text-lg font-bold font-mono text-[#22c55e] flex-shrink-0">
                    {days <= 0 ? "今日" : `${days}天`}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── 處置股 ── */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <ShieldAlert className="w-4 h-4 text-[#ef4444]" />
          <h2 className="text-sm font-semibold text-white">處置股</h2>
          <span className="text-[10px] font-mono text-[#ef4444] bg-[#ef4444]/10 border border-[#ef4444]/20 px-1.5 py-0.5 rounded">
            {disposition.length} 檔
          </span>
          <span className="text-[10px] font-mono text-slate-600 ml-1">現行處置期間內</span>
        </div>

        <div className="rounded-xl border border-[#ef4444]/20 bg-[#0d1220] overflow-hidden">
          {disposition.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e2a3a] text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-3">股號</th>
                    <th className="text-left px-4 py-3">名稱</th>
                    <th className="text-right px-4 py-3">剩餘天數</th>
                    <th className="text-left px-4 py-3">處置期間</th>
                    <th className="text-left px-4 py-3">處置條件</th>
                    <th className="text-right px-4 py-3">公告日</th>
                  </tr>
                </thead>
                <tbody>
                  {disposition.map((s) => {
                    const days = daysRemaining(s.endDate);
                    const urgent = days <= 2;
                    const soon   = days <= 5;
                    return (
                    <tr key={`${s.code}-${s.announceDate}`} className="border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#1e2a3a]/30 transition-colors">
                      <td className="px-4 py-3 font-mono text-slate-500">{s.code}</td>
                      <td className="px-4 py-3 font-medium text-slate-100">
                        {s.name}
                        {s.market && <span className="ml-2 text-[10px] font-mono text-slate-600 bg-[#1e2a3a] px-1 py-0.5 rounded">{s.market}</span>}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono font-semibold text-sm ${urgent ? "text-[#22c55e]" : soon ? "text-[#f59e0b]" : "text-slate-400"}`}>
                          {days <= 0 ? "今日到期" : `${days} 天`}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-slate-400">{s.period}</td>
                      <td className="px-4 py-3 text-xs text-slate-400">{s.condition}</td>
                      <td className="px-4 py-3 text-right font-mono text-slate-500">{s.announceDate}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="px-5 py-8 text-center text-sm text-slate-600 font-mono">
              目前無處置股
            </div>
          )}
        </div>
      </section>

      {/* ── 注意股 ── */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 text-[#f59e0b]" />
          <h2 className="text-sm font-semibold text-white">注意股</h2>
          <span className="text-[10px] font-mono text-[#f59e0b] bg-[#f59e0b]/10 border border-[#f59e0b]/20 px-1.5 py-0.5 rounded">
            {notice.length} 檔
          </span>
        </div>

        <div className="rounded-xl border border-[#f59e0b]/20 bg-[#0d1220] overflow-hidden">
          {notice.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e2a3a] text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                    <th className="text-left px-4 py-3">股號</th>
                    <th className="text-left px-4 py-3">名稱</th>
                    <th className="text-right px-4 py-3">累計次數</th>
                    <th className="text-left px-4 py-3">注意原因</th>
                    <th className="text-right px-4 py-3">公告日</th>
                    <th className="text-right px-4 py-3">收盤價</th>
                  </tr>
                </thead>
                <tbody>
                  {notice.map((s) => (
                    <tr key={s.code} className="border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#1e2a3a]/30 transition-colors">
                      <td className="px-4 py-3 font-mono text-slate-500">{s.code}</td>
                      <td className="px-4 py-3 font-medium text-slate-100">
                        {s.name}
                        {s.market && <span className="ml-2 text-[10px] font-mono text-slate-600 bg-[#1e2a3a] px-1 py-0.5 rounded">{s.market}</span>}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-[#f59e0b] font-semibold">{s.noticeCount}</td>
                      <td className="px-4 py-3 text-xs text-slate-400 max-w-xs truncate">{s.info}</td>
                      <td className="px-4 py-3 text-right font-mono text-slate-500">{s.date}</td>
                      <td className="px-4 py-3 text-right font-mono text-slate-300">{s.closePrice > 0 ? s.closePrice.toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="px-5 py-8 text-center text-sm text-slate-600 font-mono">
              今日無注意股公告
            </div>
          )}
        </div>
      </section>
    </PageShell>
  );
}
