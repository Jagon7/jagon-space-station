export const dynamic = "force-dynamic";

import PageShell from "@/components/PageShell";
import { getCBIssuances, getLastUpdated } from "@/lib/data-loader";
import type { CBIssuance } from "@/lib/types";
import { Info, AlertCircle, Clock, CheckCircle2, FileText } from "lucide-react";

// ── 工具函式 ────────────────────────────────────────────────
function daysTo(dateStr?: string): number | null {
  if (!dateStr) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const target = new Date(dateStr); target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

function convPremium(conv?: number, close?: number): number | null {
  if (!conv || !close || close === 0) return null;
  return Math.round((conv - close) / close * 1000) / 10;
}

type Status = "listing_soon" | "bookbuilding" | "filed" | "listed";

function getStatus(item: CBIssuance): Status {
  const days = daysTo(item.listingDate);
  if (days === null) return "filed";
  if (days < 0)  return "listed";
  if (days <= 7) return "listing_soon";
  if (item.bookBuildDate && daysTo(item.bookBuildDate)! <= 0) return "bookbuilding";
  return "filed";
}

const STATUS_META: Record<Status, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  listing_soon: { label: "即將掛牌", color: "text-[#ef4444]", bg: "bg-[#ef4444]/10 border-[#ef4444]/30", icon: AlertCircle },
  bookbuilding: { label: "詢圈中",   color: "text-[#60a5fa]", bg: "bg-[#60a5fa]/10 border-[#60a5fa]/30", icon: Clock },
  filed:        { label: "申報中",   color: "text-slate-400",  bg: "bg-slate-800/40 border-slate-600/30",  icon: FileText },
  listed:       { label: "已掛牌",   color: "text-[#22c55e]",  bg: "bg-[#22c55e]/10 border-[#22c55e]/30",  icon: CheckCircle2 },
};

function StatusBadge({ status }: { status: Status }) {
  const m = STATUS_META[status];
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border ${m.color} ${m.bg}`}>
      <Icon className="w-3 h-3" />
      {m.label}
    </span>
  );
}

function DaysCell({ days, status }: { days: number | null; status: Status }) {
  if (days === null) return <td className="px-4 py-3 text-right font-mono text-slate-600">—</td>;
  if (status === "listed") {
    return (
      <td className="px-4 py-3 text-right font-mono text-slate-500 text-xs">
        {Math.abs(days)} 天前
      </td>
    );
  }
  const color = days <= 3 ? "text-[#ef4444] font-bold" : days <= 7 ? "text-[#f59e0b] font-semibold" : "text-slate-300";
  return (
    <td className={`px-4 py-3 text-right font-mono text-sm ${color}`}>
      {days} 天
    </td>
  );
}

function PremiumCell({ premium }: { premium: number | null }) {
  if (premium === null) return <td className="px-4 py-3 text-right font-mono text-slate-600">—</td>;
  const color = premium <= 3 ? "text-[#ef4444]" : premium <= 8 ? "text-[#f59e0b]" : "text-slate-400";
  return (
    <td className={`px-4 py-3 text-right font-mono text-xs ${color}`}>
      +{premium.toFixed(1)}%
    </td>
  );
}

// ── 排序：即將掛牌 → 詢圈中 → 申報中 → 已掛牌 ──────────────
const STATUS_ORDER: Record<Status, number> = {
  listing_soon: 0, bookbuilding: 1, filed: 2, listed: 3,
};

export default async function CBWatchPage() {
  const [items, updatedAt] =
    await Promise.all([getCBIssuances(), getLastUpdated()]);
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });

  const enriched = items
    .map((item) => ({
      ...item,
      status:  getStatus(item),
      days:    daysTo(item.listingDate),
      premium: convPremium(item.conversionPrice, item.closePrice),
    }))
    .sort((a, b) => {
      const so = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
      if (so !== 0) return so;
      return (a.days ?? 999) - (b.days ?? 999);
    });

  const counts = {
    listing_soon: enriched.filter((i) => i.status === "listing_soon").length,
    bookbuilding: enriched.filter((i) => i.status === "bookbuilding").length,
    filed:        enriched.filter((i) => i.status === "filed").length,
    listed:       enriched.filter((i) => i.status === "listed").length,
  };

  return (
    <PageShell
      title="CB 詢圈偵察站"
      subtitle={`${items.length} 件在追蹤 · 即將掛牌 ${counts.listing_soon} 件 · 更新 ${updatedTime}`}
      badge="CB Watch"
    >
      {/* 策略說明 */}
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 mb-6 flex gap-3">
        <Info className="w-4 h-4 text-[#3b82f6] flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-400 leading-relaxed space-y-1">
          <p>
            <span className="text-white font-semibold">策略邏輯</span>：公司申報發行 CB（可轉換公司債）通常會帶動現股上漲——
            機構法人為了搶 CB 額度往往拉抬股價，申報後即是進場時機。
          </p>
          <p>
            <span className="text-[#f59e0b] font-semibold">流程</span>：
            公司申報 → 主管機關審查（約 2～3 週）→ 詢圈定價（1～3 天）→ 掛牌上市。
            建議於 <span className="text-white">申報日後進場</span>，
            並在 <span className="text-[#ef4444]">掛牌前出場</span>，
            掛牌後 CB 持有人若有轉換利潤將賣壓股票。
          </p>
          <p>
            <span className="text-[#60a5fa] font-semibold">轉換溢價率</span>：
            (轉換價 − 現股價) ÷ 現股價 × 100。數值越低，CB 持有人轉換意願越高，對股價壓力越大；
            <span className="text-[#ef4444]">≤ 3%</span> 需特別留意掛牌後賣壓。
          </p>
          <p className="text-slate-600">資料來源：台灣證券商業同業公會、證交所、上櫃公司重大訊息，僅供參考，不構成投資建議。</p>
        </div>
      </div>

      {/* 摘要 KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[
          { label: "即將掛牌",  value: counts.listing_soon, color: "text-[#ef4444]", border: "border-[#ef4444]/20" },
          { label: "詢圈中",    value: counts.bookbuilding, color: "text-[#60a5fa]", border: "border-[#60a5fa]/20" },
          { label: "申報中",    value: counts.filed,        color: "text-slate-300", border: "border-[#1e2a3a]" },
          { label: "近期已掛牌", value: counts.listed,       color: "text-[#22c55e]", border: "border-[#22c55e]/20" },
        ].map((k) => (
          <div key={k.label} className={`rounded-xl border ${k.border} bg-[#0d1220] p-4 text-center`}>
            <div className={`text-2xl font-bold font-mono ${k.color}`}>{k.value}</div>
            <div className="text-[11px] text-slate-500 font-mono mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {/* 主表格 */}
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-max min-w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e2a3a] text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                <th className="text-left px-4 py-3">股號</th>
                <th className="text-left px-4 py-3">公司</th>
                <th className="text-left px-4 py-3">CB 期別</th>
                <th className="text-center px-3 py-3">市場</th>
                <th className="text-right px-4 py-3">申報日</th>
                <th className="text-right px-4 py-3">掛牌日</th>
                <th className="text-right px-4 py-3">距掛牌 ↑</th>
                <th className="text-right px-4 py-3">發行金額</th>
                <th className="text-right px-4 py-3">轉換價</th>
                <th className="text-right px-4 py-3">現股價</th>
                <th className="text-right px-4 py-3">溢價率</th>
                <th className="text-left px-4 py-3">主辦承銷商</th>
                <th className="text-left px-4 py-3">狀態</th>
              </tr>
            </thead>
            <tbody>
              {enriched.map((item) => (
                <tr
                  key={`${item.code}-${item.cbSeries}`}
                  className={`border-b border-[#1e2a3a]/50 last:border-0 transition-colors ${
                    item.status === "listing_soon"
                      ? "hover:bg-[#ef4444]/5"
                      : item.status === "listed"
                      ? "opacity-50 hover:opacity-70 hover:bg-[#1e2a3a]/20"
                      : "hover:bg-[#1e2a3a]/30"
                  }`}
                >
                  <td className="px-4 py-3 font-mono text-slate-500 whitespace-nowrap">{item.code}</td>
                  <td className="px-4 py-3 font-medium text-slate-100 whitespace-nowrap">{item.name}</td>
                  <td className="px-4 py-3 font-mono text-[#a78bfa] text-xs whitespace-nowrap">{item.cbSeries}</td>
                  <td className="px-3 py-3 text-center">
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                      item.market === "上市"
                        ? "text-[#3b82f6] bg-[#3b82f6]/10"
                        : "text-[#a78bfa] bg-[#a78bfa]/10"
                    }`}>
                      {item.market ?? "上市"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-500 text-xs whitespace-nowrap">
                    {item.filingDate}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300 text-xs whitespace-nowrap">
                    {item.listingDate ?? "—"}
                  </td>
                  <DaysCell days={item.days} status={item.status} />
                  <td className="px-4 py-3 text-right font-mono text-slate-300 whitespace-nowrap">
                    {item.amount != null ? `${item.amount} 億` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300 whitespace-nowrap">
                    {item.conversionPrice != null ? item.conversionPrice.toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-400 whitespace-nowrap">
                    {item.closePrice != null ? item.closePrice.toLocaleString() : "—"}
                  </td>
                  <PremiumCell premium={item.premium} />
                  <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                    {item.underwriter ?? "—"}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <StatusBadge status={item.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 border-t border-[#1e2a3a] flex items-center justify-between">
          <span className="text-xs text-slate-600 font-mono">共 {items.length} 件 CB 在追蹤</span>
          <span className="text-xs text-slate-600 font-mono">溢價率 = (轉換價 − 現股) ÷ 現股 · 資料來源：TWSA / TWSE / TPEx</span>
        </div>
      </div>
    </PageShell>
  );
}
