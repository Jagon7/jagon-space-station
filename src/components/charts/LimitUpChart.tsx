"use client";

import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, LineChart, Line, Legend,
} from "recharts";
import type { MarketHistoryEntry } from "@/lib/types";

const MOOD_SCORE: Record<MarketHistoryEntry["marketMood"], number> = {
  "強勢": 90, "偏強": 70, "中性": 50, "偏弱": 30, "弱勢": 10,
};

const SECTOR_COLORS = ["#00d4aa", "#3b82f6", "#a78bfa", "#f59e0b", "#ef4444"];

function CustomTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#0d1220] border border-[#1e2a3a] rounded-lg p-3 text-xs shadow-xl">
      <p className="text-slate-400 mb-2 font-mono">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex gap-2 items-center" style={{ color: p.color }}>
          <span className="w-2 h-2 rounded-full inline-block" style={{ background: p.color }} />
          {p.name}: <span className="font-semibold">{p.value}</span>
        </p>
      ))}
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="h-[200px] flex items-center justify-center text-xs text-slate-600 font-mono">
      {label}
    </div>
  );
}

export function LimitUpTrendChart({ history }: { history: MarketHistoryEntry[] }) {
  const data = history.map((h) => ({
    date: h.date.slice(5),
    count: h.limitUpCount,
    mood: MOOD_SCORE[h.marketMood] ?? 50,
  }));

  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5">
      <div className="mb-4">
        <p className="text-[10px] font-mono text-slate-600 tracking-[0.2em] uppercase mb-0.5">Signal Trend</p>
        <h3 className="text-sm font-semibold text-white">近 {data.length} 日漲停訊號強度</h3>
      </div>
      {data.length < 2 ? (
        <EmptyState label="歷史資料累積中，明日起可見趨勢" />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="countGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#00d4aa" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#00d4aa" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="moodGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" />
            <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              formatter={(v) => <span className="text-xs text-slate-400">{v}</span>}
              wrapperStyle={{ paddingTop: 8 }}
            />
            <Area type="monotone" dataKey="count" name="漲停檔數" stroke="#00d4aa" strokeWidth={2} fill="url(#countGrad)" dot={{ fill: "#00d4aa", r: 3 }} />
            <Area type="monotone" dataKey="mood" name="氣氛分數" stroke="#3b82f6" strokeWidth={2} fill="url(#moodGrad)" dot={{ fill: "#3b82f6", r: 3 }} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export function SectorTrendChart({ history }: { history: MarketHistoryEntry[] }) {
  // 取歷史窗內出現過的族群，依累積漲停家數取前 5 名作為圖表線條
  const totals = new Map<string, number>();
  for (const h of history) {
    for (const s of h.topSectors) {
      totals.set(s.name, (totals.get(s.name) ?? 0) + s.count);
    }
  }
  const sectorKeys = Array.from(totals.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name]) => name);

  const data = history.map((h) => {
    const row: Record<string, string | number> = { date: h.date.slice(5) };
    for (const key of sectorKeys) row[key] = 0;
    for (const s of h.topSectors) {
      if (sectorKeys.includes(s.name)) row[s.name] = s.count;
    }
    return row;
  });

  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5">
      <div className="mb-4">
        <p className="text-[10px] font-mono text-slate-600 tracking-[0.2em] uppercase mb-0.5">Sector Radar</p>
        <h3 className="text-sm font-semibold text-white">族群資金輪動趨勢</h3>
      </div>
      {data.length < 2 || sectorKeys.length === 0 ? (
        <EmptyState label="歷史資料累積中，明日起可見趨勢" />
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" />
            <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              formatter={(v) => <span className="text-xs text-slate-400">{v}</span>}
              wrapperStyle={{ paddingTop: 8 }}
            />
            {sectorKeys.map((key, i) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={key}
                stroke={SECTOR_COLORS[i % SECTOR_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
