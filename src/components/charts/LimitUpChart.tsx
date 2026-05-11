"use client";

import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, LineChart, Line, Legend,
} from "recharts";
import { mockLimitUpTrend, mockSectorTrend } from "@/lib/mock-data";

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

export function LimitUpTrendChart() {
  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5">
      <div className="mb-4">
        <p className="text-[10px] font-mono text-slate-600 tracking-[0.2em] uppercase mb-0.5">Signal Trend</p>
        <h3 className="text-sm font-semibold text-white">近 5 日漲停訊號強度</h3>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={mockLimitUpTrend} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
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
    </div>
  );
}

export function SectorTrendChart() {
  return (
    <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-5">
      <div className="mb-4">
        <p className="text-[10px] font-mono text-slate-600 tracking-[0.2em] uppercase mb-0.5">Sector Radar</p>
        <h3 className="text-sm font-semibold text-white">族群資金輪動趨勢</h3>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={mockSectorTrend} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2a3a" />
          <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(v) => <span className="text-xs text-slate-400">{v}</span>}
            wrapperStyle={{ paddingTop: 8 }}
          />
          <Line type="monotone" dataKey="aiServer"     name="AI伺服器"  stroke="#00d4aa" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="semiconductor" name="半導體"   stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="pcb"           name="PCB"      stroke="#a78bfa" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="panel"         name="面板光電" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
