export const dynamic = "force-dynamic";

import PageShell from "@/components/PageShell";
import { getEtfFlow, getLastUpdated } from "@/lib/data-loader";
import type { EtfFlowItem, EtfFlowChange } from "@/lib/types";
import {
  TrendingUp, TrendingDown, PlusCircle, MinusCircle, Info,
  ChevronDown, ChevronUp,
} from "lucide-react";

// ── 工具函式 ────────────────────────────────────────────────
function fmt(n: number, unit = "元"): string {
  const abs = Math.abs(n);
  const str =
    abs >= 1e8 ? `${(n / 1e8).toFixed(2)}億` :
    abs >= 1e4 ? `${(n / 1e4).toFixed(0)}萬` :
    n.toLocaleString();
  return unit === "張" ? `${(n / 1000).toFixed(0)}張` : str;
}

function ActionBadge({ action }: { action: EtfFlowChange["action"] }) {
  const meta = {
    new:    { label: "新增成分股", icon: PlusCircle,  color: "text-[#22c55e]", bg: "bg-[#22c55e]/10 border-[#22c55e]/30" },
    remove: { label: "剔除成分股", icon: MinusCircle, color: "text-slate-400",  bg: "bg-slate-800/40 border-slate-600/30" },
    buy:    { label: "加碼",       icon: TrendingUp,  color: "text-[#ef4444]", bg: "bg-red-900/20 border-red-700/30" },
    sell:   { label: "減碼",       icon: TrendingDown, color: "text-[#3b82f6]", bg: "bg-blue-900/20 border-blue-700/30" },
  }[action];
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border ${meta.color} ${meta.bg}`}>
      <Icon className="w-3 h-3" />
      {meta.label}
    </span>
  );
}

function DiffCell({ diff, diffValue }: { diff: number; diffValue: number }) {
  const isPos = diff >= 0;
  const color = isPos ? "text-[#ef4444]" : "text-[#3b82f6]";
  const Icon  = isPos ? ChevronUp : ChevronDown;
  return (
    <td className={`px-4 py-3 text-right whitespace-nowrap ${color}`}>
      <div className="flex items-center justify-end gap-1">
        <Icon className="w-3 h-3" />
        <span className="font-mono text-xs font-semibold">{Math.abs(diff).toLocaleString()}</span>
      </div>
      <div className="font-mono text-[10px] text-slate-500">
        {isPos ? "+" : "-"}{fmt(Math.abs(diffValue))}
      </div>
    </td>
  );
}

function EtfSection({ etf }: { etf: EtfFlowItem }) {
  const sorted = [...etf.changes].sort((a, b) => Math.abs(b.diffValue) - Math.abs(a.diffValue));
  const buyCount  = etf.changes.filter(c => c.diffShares > 0).length;
  const sellCount = etf.changes.filter(c => c.diffShares < 0).length;
  const totalBuyVal  = etf.changes.filter(c => c.diffShares > 0).reduce((s, c) => s + c.diffValue, 0);
  const totalSellVal = etf.changes.filter(c => c.diffShares < 0).reduce((s, c) => s + Math.abs(c.diffValue), 0);
  const catColor =
    etf.category === "主動型" ? "text-[#a78bfa] bg-[#a78bfa]/10" :
    etf.category === "市值型" ? "text-[#3b82f6] bg-[#3b82f6]/10" :
    "text-[#22c55e] bg-[#22c55e]/10";

  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
      {/* ETF header */}
      <div className="px-5 py-4 border-b border-[#1e2a3a] flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-lg font-bold text-white">{etf.etfCode}</span>
          <span className="text-sm text-slate-300">{etf.etfName}</span>
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${catColor}`}>{etf.category}</span>
        </div>
        <div className="flex items-center gap-4 ml-auto text-xs font-mono text-slate-500">
          <span>淨值 <span className="text-slate-300">{etf.navPerUnit}</span></span>
          <span className="text-[#ef4444]">買 {buyCount} 檔 +{fmt(totalBuyVal)}</span>
          <span className="text-[#3b82f6]">賣 {sellCount} 檔 -{fmt(totalSellVal)}</span>
          <span className="text-slate-600">異動 {etf.changes.length} 筆</span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] font-mono text-slate-600 uppercase tracking-wider border-b border-[#1e2a3a]">
              <th className="text-left px-4 py-2.5">股號</th>
              <th className="text-left px-4 py-2.5">名稱</th>
              <th className="text-center px-4 py-2.5">動作</th>
              <th className="text-right px-4 py-2.5">前日持股</th>
              <th className="text-right px-4 py-2.5">當日持股</th>
              <th className="text-right px-4 py-2.5">增減股數 / 金額</th>
              <th className="text-right px-4 py-2.5">收盤</th>
              <th className="text-right px-4 py-2.5">持股比重</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => (
              <tr
                key={c.code}
                className={`border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#1e2a3a]/20 transition-colors ${
                  c.action === "remove" ? "opacity-60" : ""
                }`}
              >
                <td className="px-4 py-3 font-mono text-slate-500 whitespace-nowrap">{c.code}</td>
                <td className="px-4 py-3 text-slate-200 whitespace-nowrap">{c.name}</td>
                <td className="px-4 py-3 text-center whitespace-nowrap">
                  <ActionBadge action={c.action} />
                </td>
                <td className="px-4 py-3 text-right font-mono text-slate-500 text-xs whitespace-nowrap">
                  {c.prevShares > 0 ? c.prevShares.toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3 text-right font-mono text-slate-300 text-xs whitespace-nowrap">
                  {c.currShares > 0 ? c.currShares.toLocaleString() : "—"}
                </td>
                <DiffCell diff={c.diffShares} diffValue={c.diffValue} />
                <td className="px-4 py-3 text-right font-mono text-slate-400 whitespace-nowrap">
                  {c.closePrice.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right font-mono whitespace-nowrap">
                  {c.weight > 0 ? (
                    <span className="text-slate-300">{c.weight.toFixed(2)}%</span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── 個股彙總視圖 ─────────────────────────────────────────────
type StockAgg = {
  code: string; name: string;
  totalDiffShares: number; totalDiffValue: number;
  buyEtfs: string[]; sellEtfs: string[];
};

function buildStockAgg(items: EtfFlowItem[]): StockAgg[] {
  const map = new Map<string, StockAgg>();
  for (const etf of items) {
    for (const c of etf.changes) {
      if (!map.has(c.code)) {
        map.set(c.code, { code: c.code, name: c.name, totalDiffShares: 0, totalDiffValue: 0, buyEtfs: [], sellEtfs: [] });
      }
      const agg = map.get(c.code)!;
      agg.totalDiffShares += c.diffShares;
      agg.totalDiffValue  += c.diffValue;
      if (c.diffShares > 0) { if (!agg.buyEtfs.includes(etf.etfCode))  agg.buyEtfs.push(etf.etfCode); }
      else                  { if (!agg.sellEtfs.includes(etf.etfCode)) agg.sellEtfs.push(etf.etfCode); }
    }
  }
  return [...map.values()].sort((a, b) => Math.abs(b.totalDiffValue) - Math.abs(a.totalDiffValue));
}

// ── Page ────────────────────────────────────────────────────
export default async function EtfFlowPage() {
  const [flow, updatedAt] = await Promise.all([getEtfFlow(), getLastUpdated()]);
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });

  if (!flow) {
    return (
      <PageShell title="ETF 成分股動態" subtitle="資料載入中" badge="ETF Flow">
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-8 text-center text-sm text-slate-600 font-mono">
          請等待 Actions 執行後重新整理
        </div>
      </PageShell>
    );
  }

  const stockAgg = buildStockAgg(flow.data);
  const capEtfs      = flow.data.filter(e => e.category === "市值型");
  const highDivEtfs  = flow.data.filter(e => e.category === "高股息");
  const activeEtfs   = flow.data.filter(e => e.category === "主動型");
  const totalBuyVal  = flow.data.reduce((s, e) => s + e.changes.filter(c => c.diffShares > 0).reduce((a, c) => a + c.diffValue, 0), 0);
  const totalSellVal = flow.data.reduce((s, e) => s + e.changes.filter(c => c.diffShares < 0).reduce((a, c) => a + Math.abs(c.diffValue), 0), 0);

  return (
    <PageShell
      title="ETF 成分股動態"
      subtitle={`${flow.date} · ${flow.data.length} 檔 ETF · 資料更新 ${updatedTime}`}
      badge="ETF Flow"
    >
      {/* 說明 */}
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 mb-6 flex gap-3">
        <Info className="w-4 h-4 text-[#22c55e] flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-400 leading-relaxed space-y-1">
          <p>
            <span className="text-white font-semibold">追蹤邏輯</span>：
            每日比較各 ETF 申購買回清單（PCF）與前一日的持股股數差異，
            正數代表 ETF 當日淨買入，負數代表淨賣出。
          </p>
          <p>
            <span className="text-[#22c55e]">新增成分股</span> = 前日持股為零，今日首次納入 ／
            <span className="text-slate-400 ml-1">剔除成分股</span> = 今日持股歸零 ／
            <span className="text-[#ef4444] ml-1">加碼</span> = 持股股數增加 ／
            <span className="text-[#3b82f6] ml-1">減碼</span> = 持股股數減少
          </p>
          <p className="text-slate-600">
            資料來源：群益投信 / 復華投信 / 國泰投信 / 元大投信 / 統一投信 官網申購買回清單 · 僅供參考，不構成投資建議。
          </p>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
        {[
          { label: "追蹤 ETF",   value: `${flow.data.length} 檔`,     color: "text-slate-200" },
          { label: "ETF 合計買入", value: `+${fmt(totalBuyVal)}`,       color: "text-[#ef4444]" },
          { label: "ETF 合計賣出", value: `-${fmt(totalSellVal)}`,      color: "text-[#3b82f6]" },
          { label: "主動型 ETF",  value: `${activeEtfs.length} 檔`,    color: "text-[#a78bfa]" },
          { label: "市值型 ETF",  value: `${capEtfs.length} 檔`,       color: "text-[#3b82f6]" },
        ].map((k) => (
          <div key={k.label} className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 text-center">
            <div className={`text-xl font-bold font-mono ${k.color}`}>{k.value}</div>
            <div className="text-[11px] text-slate-500 font-mono mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {/* ── 個股彙總 ── */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-sm font-semibold text-white">個股 ETF 買賣超彙總</h2>
          <span className="text-[10px] font-mono text-slate-400 bg-[#1e2a3a] px-2 py-0.5 rounded border border-[#1e2a3a]">
            {stockAgg.length} 檔有異動
          </span>
        </div>
        <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-mono text-slate-600 uppercase tracking-wider border-b border-[#1e2a3a]">
                  <th className="text-left px-4 py-3">股號</th>
                  <th className="text-left px-4 py-3">名稱</th>
                  <th className="text-right px-4 py-3">ETF 合計增減股數</th>
                  <th className="text-right px-4 py-3">換算金額</th>
                  <th className="text-left px-4 py-3">買入 ETF</th>
                  <th className="text-left px-4 py-3">賣出 ETF</th>
                </tr>
              </thead>
              <tbody>
                {stockAgg.map((s) => (
                  <tr key={s.code} className="border-b border-[#1e2a3a]/50 last:border-0 hover:bg-[#1e2a3a]/20 transition-colors">
                    <td className="px-4 py-3 font-mono text-slate-500 whitespace-nowrap">{s.code}</td>
                    <td className="px-4 py-3 text-slate-200 whitespace-nowrap">{s.name}</td>
                    <td className={`px-4 py-3 text-right font-mono font-semibold whitespace-nowrap ${s.totalDiffShares >= 0 ? "text-[#ef4444]" : "text-[#3b82f6]"}`}>
                      {s.totalDiffShares >= 0 ? "+" : ""}{s.totalDiffShares.toLocaleString()}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono text-xs whitespace-nowrap ${s.totalDiffValue >= 0 ? "text-[#ef4444]" : "text-[#3b82f6]"}`}>
                      {s.totalDiffValue >= 0 ? "+" : ""}{fmt(s.totalDiffValue)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {s.buyEtfs.map(e => (
                          <span key={e} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-red-900/20 text-[#ef4444] border border-red-700/30">{e}</span>
                        ))}
                        {s.buyEtfs.length === 0 && <span className="text-slate-700 text-xs">—</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {s.sellEtfs.map(e => (
                          <span key={e} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-900/20 text-[#3b82f6] border border-blue-700/30">{e}</span>
                        ))}
                        {s.sellEtfs.length === 0 && <span className="text-slate-700 text-xs">—</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── 市值型 ETF ── */}
      {capEtfs.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-sm font-semibold text-white">市值型 ETF</h2>
            <span className="text-[10px] font-mono text-[#3b82f6] bg-[#3b82f6]/10 px-2 py-0.5 rounded border border-[#3b82f6]/30">
              {capEtfs.length} 檔
            </span>
          </div>
          <div className="space-y-4">
            {capEtfs.map(etf => <EtfSection key={etf.etfCode} etf={etf} />)}
          </div>
        </div>
      )}

      {/* ── 高股息 ETF ── */}
      {highDivEtfs.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-sm font-semibold text-white">高股息 ETF</h2>
            <span className="text-[10px] font-mono text-[#22c55e] bg-[#22c55e]/10 px-2 py-0.5 rounded border border-[#22c55e]/30">
              {highDivEtfs.length} 檔
            </span>
          </div>
          <div className="space-y-4">
            {highDivEtfs.map(etf => <EtfSection key={etf.etfCode} etf={etf} />)}
          </div>
        </div>
      )}

      {/* ── 主動型 ETF ── */}
      {activeEtfs.length > 0 && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-sm font-semibold text-white">主動型 ETF</h2>
            <span className="text-[10px] font-mono text-[#a78bfa] bg-[#a78bfa]/10 px-2 py-0.5 rounded border border-[#a78bfa]/30">
              {activeEtfs.length} 檔
            </span>
          </div>
          <div className="space-y-4">
            {activeEtfs.map(etf => <EtfSection key={etf.etfCode} etf={etf} />)}
          </div>
        </div>
      )}

      <div className="mt-6 pt-4 border-t border-[#1e2a3a] text-[10px] font-mono text-slate-700 text-center">
        資料來源：群益投信 · 復華投信 · 國泰投信 · 元大投信 · 統一投信 官網申購買回清單 · 僅供研究參考，不構成投資建議
      </div>
    </PageShell>
  );
}
