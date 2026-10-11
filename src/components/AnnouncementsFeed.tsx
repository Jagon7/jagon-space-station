"use client";

import { useMemo, useState } from "react";
import { Radio } from "lucide-react";
import type { Announcement } from "@/lib/types";

const typeColors: Record<string, string> = {
  "法說會":   "text-[#4f8cff] bg-[#4f8cff]/10 border-[#4f8cff]/20",
  "重大訊息": "text-[#f05252] bg-red-900/20 border-red-700/30",
  "財報":     "text-[#38bdf8] bg-[#38bdf8]/10 border-[#38bdf8]/20",
  "庫藏股":   "text-[#f59e0b] bg-yellow-900/20 border-yellow-700/30",
};

export default function AnnouncementsFeed({ announcements }: { announcements: Announcement[] }) {
  const types = useMemo(() => {
    const present = Array.from(new Set(announcements.map((a) => a.type)));
    return ["全部", ...present];
  }, [announcements]);
  const [active, setActive] = useState("全部");

  const filtered = active === "全部" ? announcements : announcements.filter((a) => a.type === active);

  return (
    <>
      {/* Type filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        {types.map((t) => (
          <button
            key={t}
            onClick={() => setActive(t)}
            className={`px-3 py-1 rounded-full text-xs font-mono border transition-colors ${
              t === active
                ? "bg-[#4f8cff]/10 text-[#4f8cff] border-[#4f8cff]/30"
                : "bg-[#243247] text-slate-400 border-[#243247] hover:text-slate-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Feed */}
      <div className="rounded-xl border border-[#243247] bg-[#0d1220] overflow-hidden">
        <div className="px-5 py-3.5 border-b border-[#243247] flex items-center gap-2">
          <Radio className="w-4 h-4 text-[#4f8cff]" />
          <span className="text-sm font-semibold text-white">公告情報串流</span>
          <span className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-[#22c55e]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
            掃頻中
          </span>
        </div>

        {filtered.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-[#7c8aa0] font-mono">
            {announcements.length === 0 ? "請等待 Actions 執行後重新整理" : "此分類目前無公告"}
          </div>
        ) : (
          <div className="divide-y divide-[#243247]/50">
            {filtered.map((a, i) => (
              <div key={i} className="px-5 py-4 hover:bg-[#243247]/30 transition-colors flex items-start gap-4">
                <span className="font-mono text-xs text-[#7c8aa0] w-24 flex-shrink-0 mt-0.5">
                  {a.date.slice(5)} {a.time}
                </span>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-mono text-xs text-[#8b97ab]">{a.code}</span>
                    <span className="text-sm font-medium text-slate-100">{a.name}</span>
                    {a.important && (
                      <span className="flex items-center gap-1 text-[10px] font-mono text-[#f05252] bg-red-900/20 border border-red-700/30 px-1.5 py-0.5 rounded">
                        <span className="w-1 h-1 rounded-full bg-[#f05252] animate-pulse" />
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
        )}

        <div className="px-5 py-3 border-t border-[#243247]">
          <p className="text-xs text-[#7c8aa0] font-mono">
            資料來源：公開資訊觀測站（MOPS）每日重大訊息（上市 + 上櫃）
          </p>
        </div>
      </div>
    </>
  );
}
