import Link from "next/link";
import { TrendingUp, TrendingDown, PlusCircle, MinusCircle, ArrowRight, PieChart } from "lucide-react";
import type { EtfFlowData, EtfFlowChange } from "@/lib/types";

function fmt(n: number): string {
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(1)}億`;
  if (Math.abs(n) >= 1e4) return `${(n / 1e4).toFixed(0)}萬`;
  return n.toLocaleString();
}

function ActionBadge({ action }: { action: EtfFlowChange["action"] }) {
  const meta = {
    new:    { label: "新增", icon: PlusCircle,  color: "text-[#22c55e]", bg: "bg-[#22c55e]/10 border-[#22c55e]/30" },
    remove: { label: "剔除", icon: MinusCircle, color: "text-slate-400",  bg: "bg-slate-800/40 border-slate-600/30" },
    buy:    { label: "加碼", icon: TrendingUp,  color: "text-[#ef4444]", bg: "bg-red-900/20 border-red-700/30" },
    sell:   { label: "減碼", icon: TrendingDown, color: "text-[#3b82f6]", bg: "bg-blue-900/20 border-blue-700/30" },
  }[action];
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[9px] font-mono px-1.5 py-0.5 rounded border ${meta.color} ${meta.bg}`}>
      <Icon className="w-2.5 h-2.5" />
      {meta.label}
    </span>
  );
}

type TopStock = {
  code: string;
  name: string;
  action: EtfFlowChange["action"];
  diffShares: number;
  diffValue: number;
  etfs: string[];
};

function buildTopStocks(flow: EtfFlowData): TopStock[] {
  const map = new Map<string, TopStock>();
  for (const etf of flow.data) {
    for (const c of etf.changes) {
      const key = c.code;
      if (!map.has(key)) {
        map.set(key, {
          code: c.code, name: c.name,
          action: c.action,
          diffShares: 0, diffValue: 0,
          etfs: [],
        });
      }
      const entry = map.get(key)!;
      entry.diffShares += c.diffShares;
      entry.diffValue  += c.diffValue;
      if (!entry.etfs.includes(etf.etfCode)) entry.etfs.push(etf.etfCode);
    }
  }
  return [...map.values()]
    .sort((a, b) => Math.abs(b.diffValue) - Math.abs(a.diffValue))
    .slice(0, 6);
}

export default function EtfFlowCard({ flow }: { flow: EtfFlowData }) {
  const topStocks = buildTopStocks(flow);
  const totalBuy  = flow.data.reduce((s, e) => s + e.changes.filter(c => c.diffShares > 0).reduce((a, c) => a + c.diffValue, 0), 0);
  const totalSell = flow.data.reduce((s, e) => s + e.changes.filter(c => c.diffShares < 0).reduce((a, c) => a + Math.abs(c.diffValue), 0), 0);
  const activeCount = flow.data.filter(e => e.category === "主動型").length;

  return (
    <div className="md:col-span-2 rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5 card-hover">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <PieChart className="w-4 h-4 text-[#22c55e]" />
          <h2 className="text-sm font-semibold text-white tracking-wide">ETF 成分股動態</h2>
          <span className="text-[10px] font-mono text-slate-500 bg-[#1e2a3a] px-1.5 py-0.5 rounded">
            {flow.data.length} 檔 ETF
          </span>
        </div>
        <Link href="/etf-flow" className="flex items-center gap-1 text-xs text-slate-500 hover:text-[#22c55e] transition-colors font-mono">
          展開詳情 <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="rounded-lg border border-[#1e2a3a] bg-[#0a0f1a] px-3 py-2">
          <div className="text-[10px] font-mono text-slate-500 mb-1">ETF 合計買入</div>
          <div className="text-sm font-bold font-mono text-[#ef4444]">+{fmt(totalBuy)}</div>
        </div>
        <div className="rounded-lg border border-[#1e2a3a] bg-[#0a0f1a] px-3 py-2">
          <div className="text-[10px] font-mono text-slate-500 mb-1">ETF 合計賣出</div>
          <div className="text-sm font-bold font-mono text-[#3b82f6]">-{fmt(totalSell)}</div>
        </div>
        <div className="rounded-lg border border-[#1e2a3a] bg-[#0a0f1a] px-3 py-2">
          <div className="text-[10px] font-mono text-slate-500 mb-1">主動型 ETF</div>
          <div className="text-sm font-bold font-mono text-[#a78bfa]">{activeCount} 檔</div>
        </div>
      </div>

      {/* Top stocks grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8">
        {topStocks.map((s, i) => (
          <div key={s.code} className={`flex items-center justify-between py-2 border-b border-[#1e2a3a]/50 ${i >= topStocks.length - (topStocks.length % 2 === 0 ? 2 : 1) ? "last:border-0 sm:[&:nth-last-child(2)]:border-0" : ""}`}>
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono text-xs text-slate-600 w-10 flex-shrink-0">{s.code}</span>
              <span className="text-sm text-slate-200 truncate">{s.name}</span>
              <ActionBadge action={s.diffShares >= 0 ? (s.diffShares === s.diffShares ? s.action : "buy") : "sell"} />
            </div>
            <div className="flex items-center gap-2 flex-shrink-0 ml-2">
              <span className="text-[10px] font-mono text-slate-600">{s.etfs.join(" ")}</span>
              <span className={`text-xs font-mono font-semibold ${s.diffValue >= 0 ? "text-[#ef4444]" : "text-[#3b82f6]"}`}>
                {s.diffValue >= 0 ? "+" : ""}{fmt(s.diffValue)}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 text-[10px] font-mono text-slate-700">
        資料日期 {flow.date} · 異動金額 = 增減張數 × 收盤價 · 資料來源：各投信官網申購買回清單
      </div>
    </div>
  );
}
