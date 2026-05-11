import PageShell from "@/components/PageShell";
import { mockAnnouncements } from "@/lib/mock-data";
import { Radio } from "lucide-react";

const typeColors: Record<string, string> = {
  "法說會":   "text-[#00d4aa] bg-[#00d4aa]/10 border-[#00d4aa]/20",
  "重大訊息": "text-[#ef4444] bg-red-900/20 border-red-700/30",
  "財報":     "text-[#3b82f6] bg-[#3b82f6]/10 border-[#3b82f6]/20",
  "庫藏股":   "text-[#f59e0b] bg-yellow-900/20 border-yellow-700/30",
};

export default function AnnouncementsPage() {
  return (
    <PageShell
      title="情報截收站"
      subtitle={`2026/05/07 · 已截收 ${mockAnnouncements.length} 則公告 · 每 5 分鐘全頻掃描`}
      badge="Intelligence Intercept"
    >
      {/* Type filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        {["全部", "重大訊息", "財報", "法說會", "庫藏股"].map((t) => (
          <button
            key={t}
            className={`px-3 py-1 rounded-full text-xs font-mono border transition-colors ${
              t === "全部"
                ? "bg-[#00d4aa]/10 text-[#00d4aa] border-[#00d4aa]/30"
                : "bg-[#1e2a3a] text-slate-400 border-[#1e2a3a] hover:text-slate-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Feed */}
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
        <div className="px-5 py-3.5 border-b border-[#1e2a3a] flex items-center gap-2">
          <Radio className="w-4 h-4 text-[#00d4aa]" />
          <span className="text-sm font-semibold text-white">公告情報串流</span>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-[#22c55e]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
            掃頻中
          </span>
        </div>

        <div className="divide-y divide-[#1e2a3a]/50">
          {mockAnnouncements.map((a, i) => (
            <div key={i} className="px-5 py-4 hover:bg-[#1e2a3a]/30 transition-colors flex items-start gap-4">
              <span className="font-mono text-xs text-slate-600 w-12 flex-shrink-0 mt-0.5">{a.time}</span>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="font-mono text-xs text-slate-500">{a.code}</span>
                  <span className="text-sm font-medium text-slate-100">{a.name}</span>
                  {a.important && (
                    <span className="flex items-center gap-1 text-[10px] font-mono text-[#ef4444] bg-red-900/20 border border-red-700/30 px-1.5 py-0.5 rounded">
                      <span className="w-1 h-1 rounded-full bg-[#ef4444] animate-pulse" />
                      重大
                    </span>
                  )}
                </div>
                {a.content && (
                  <p className="text-xs text-slate-400 leading-relaxed">{a.content}</p>
                )}
              </div>

              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border flex-shrink-0 ${typeColors[a.type] ?? "text-slate-400 bg-slate-800/30 border-slate-600/30"}`}>
                {a.type}
              </span>
            </div>
          ))}
        </div>

        <div className="px-5 py-3 border-t border-[#1e2a3a]">
          <p className="text-xs text-slate-600 font-mono">
            資料來源：公開資訊觀測站（MOPS）· API 串接後即時顯示全部公告
          </p>
        </div>
      </div>
    </PageShell>
  );
}
