"use client";

import { useMemo, useState } from "react";

// [身分, 姓名, 集中買, 其它增, 集中賣, 其它減, 月底持股]（股）
export type Row = [string, string, number, number, number, number, number];
export type Month = { avg: number | null; rows: Row[] };
export type Company = { n: string; mk: string; px: [string, number][]; m: Record<string, Month> };
export type Mode = "market" | "all";

const W = 1000, PT = 16, PH = 300, GAP = 26, BH = 110, H = PT + PH + GAP + BH + 22, PL = 8, PR = 56;
const TODAY = new Date().toISOString().slice(0, 10);
const RED = "#ef4444", GREEN = "#22c55e";

const ROLE_ORDER = ["董事長", "副董事長", "總經理", "董事", "監察人", "大股東", "副總經理", "協理", "經理", "財務", "會計"];
const roleRank = (r: string) => {
  const i = ROLE_ORDER.findIndex((k) => r.startsWith(k));
  return i < 0 ? ROLE_ORDER.length + (r.includes("配偶") ? 1 : 0) : i + (r.includes("配偶") || r.includes("他人") ? 0.5 : 0);
};

export const money = (v: number) => {
  const a = Math.abs(v);
  return a >= 1e8 ? `${(v / 1e8).toFixed(a >= 1e10 ? 0 : 1)}億` : a >= 1e4 ? `${Math.round(v / 1e4).toLocaleString()}萬` : `${Math.round(v)}`;
};
const priceFmt = (p: number) => (p >= 100 ? p.toFixed(0) : p.toFixed(p >= 10 ? 1 : 2));

export function monthSides(m: Month, mode: Mode) {
  const buy = (r: Row) => r[2] + (mode === "all" ? r[3] : 0);
  const sell = (r: Row) => r[4] + (mode === "all" ? r[5] : 0);
  const b = m.rows.reduce((s, r) => s + buy(r), 0), s = m.rows.reduce((t, r) => t + sell(r), 0);
  return { b, s, buy, sell };
}

/** 標註文字：「董事長 等 2 人」—— 取該方向（買或賣）職位最高的人 */
function who(m: Month, side: "b" | "s", mode: Mode) {
  const { buy, sell } = monthSides(m, mode);
  const f = side === "b" ? buy : sell;
  const ppl = m.rows.filter((r) => f(r) > 0);
  if (!ppl.length) return "";
  const best = (r: Row) => r[0].split("、").sort((a, b) => roleRank(a) - roleRank(b))[0];
  const top = [...ppl].sort((a, b) => roleRank(best(a)) - roleRank(best(b)) || f(b) - f(a))[0];
  const names = new Set(ppl.map((r) => r[1] || r[0]));
  return names.size > 1 ? `${best(top)} 等 ${names.size} 人` : `${best(top)}${top[1] && top[1].length <= 4 ? ` ${top[1]}` : ""}`;
}

export default function InsiderChart({ co, latest, mode }: { co: Company; latest: string | null; mode: Mode }) {
  const [hover, setHover] = useState<string | null>(null);

  const g = useMemo(() => {
    const px = co.px;
    const monthsAll = Object.keys(co.m).sort();
    const start = px.length ? px[0][0] : monthsAll[0] + "-01";
    const t0 = Date.parse(start), t1 = Date.parse(TODAY);
    const x = (d: string) => PL + ((Date.parse(d) - t0) / (t1 - t0)) * (W - PL - PR);
    const closes = px.map((p) => p[1]);
    const lo = Math.min(...closes), hi = Math.max(...closes);
    const pad = (hi - lo) * 0.08 || hi * 0.05 || 1;
    const y = (p: number) => PT + PH - ((p - (lo - pad)) / (hi + pad - (lo - pad))) * PH;
    const path = px.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");

    const months = monthsAll.filter((m) => m + "-01" >= start.slice(0, 7) + "-01").map((ym) => {
      const mo = co.m[ym];
      const { b, s } = monthSides(mo, mode);
      const avg = mo.avg;
      const net = avg ? (b - s) * avg : 0;
      return { ym, mo, b, s, avg, buyAmt: avg ? b * avg : 0, sellAmt: avg ? s * avg : 0, net, mid: x(`${ym}-15`) };
    });
    const maxAmt = Math.max(1, ...months.map((m) => Math.max(m.buyAmt, m.sellAmt)));
    const monthW = (W - PL - PR) / Math.max(1, (t1 - t0) / (30.4 * 86400e3));

    // 金額最大的幾個月加標註框，彼此太近就上下錯開
    const notes = [...months].filter((m) => m.avg && m.net).sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, 7)
      .sort((a, b) => a.mid - b.mid);
    const placed: { m: (typeof months)[number]; bx: number; by: number; cy: number; text1: string; text2: string }[] = [];
    for (const m of notes) {
      const buy = m.net > 0;
      const cy = y(m.avg!);
      const text1 = who(m.mo, buy ? "b" : "s", mode);
      const text2 = `均 ${priceFmt(m.avg!)}・${buy ? "淨買" : "淨賣"} ${money(Math.abs(m.net))}`;
      const bw = 128, bh = 36;
      const bx = Math.min(W - PR - bw, Math.max(PL, m.mid - bw / 2));
      let by = buy ? cy - 58 : cy + 22;
      for (const p of placed) {
        if (Math.abs(p.bx - bx) < bw + 4 && Math.abs(p.by - by) < bh + 4) by = buy ? p.by - bh - 6 : p.by + bh + 6;
      }
      by = Math.min(PT + PH - bh, Math.max(PT, by));
      placed.push({ m, bx, by, cy, text1, text2 });
    }

    const ticks: { x: number; label: string }[] = [];
    for (let d = new Date(start.slice(0, 7) + "-01T00:00:00Z"); d.getTime() <= t1; d.setUTCMonth(d.getUTCMonth() + 1)) {
      const mm = d.getUTCMonth() + 1;
      if (mm === 1 || mm === 4 || mm === 7 || mm === 10) {
        ticks.push({ x: x(d.toISOString().slice(0, 10)), label: mm === 1 ? `${d.getUTCFullYear()}` : `${mm}月` });
      }
    }
    const pTicks = Array.from({ length: 5 }, (_, i) => lo - pad + ((hi + pad - (lo - pad)) * (i + 0.5)) / 5);
    // 尚未申報：最新申報月份之後到今天
    const unrepX = latest ? x(new Date(Date.UTC(+latest.slice(0, 4), +latest.slice(5, 7), 1)).toISOString().slice(0, 10)) : null;
    return { x, y, path, months, maxAmt, monthW, placed, ticks, pTicks, unrepX };
  }, [co, latest, mode]);

  const baseY = PT + PH + GAP + BH / 2;
  const bar = (v: number) => (v / g.maxAmt) * (BH / 2 - 4);
  const bw = Math.max(3, Math.min(14, g.monthW * 0.32));
  const hm = g.months.find((m) => m.ym === hover);

  return (
    <div className="relative">
      <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[680px] h-auto select-none" onMouseLeave={() => setHover(null)}>
        {g.unrepX != null && g.unrepX < W - PR && (
          <g>
            <rect x={g.unrepX} y={PT} width={W - PR - g.unrepX} height={PH + GAP + BH} fill="#1e2a3a" opacity={0.35} />
            <text x={(g.unrepX + W - PR) / 2} y={PT + 14} textAnchor="middle" fontSize={11} fill="#64748b">尚未申報</text>
          </g>
        )}
        {g.pTicks.map((p) => (
          <g key={p}>
            <line x1={PL} x2={W - PR} y1={g.y(p)} y2={g.y(p)} stroke="#1e2a3a" strokeDasharray="2 4" />
            <text x={W - PR + 6} y={g.y(p) + 4} fontSize={11} fill="#64748b">{priceFmt(p)}</text>
          </g>
        ))}
        {g.ticks.map((t) => (
          <g key={t.x}>
            <line x1={t.x} x2={t.x} y1={PT} y2={PT + PH + GAP + BH} stroke="#1e2a3a" opacity={0.6} />
            <text x={t.x + 3} y={H - 6} fontSize={11} fill="#64748b">{t.label}</text>
          </g>
        ))}
        <path d={g.path} fill="none" stroke="#94a3b8" strokeWidth={1.4} />

        {/* 月別買賣金額 */}
        <line x1={PL} x2={W - PR} y1={baseY} y2={baseY} stroke="#334155" />
        <text x={W - PR + 6} y={PT + PH + GAP + 10} fontSize={10} fill="#64748b">買 {money(g.maxAmt)}</text>
        <text x={W - PR + 6} y={PT + PH + GAP + BH} fontSize={10} fill="#64748b">賣</text>
        {g.months.map((m) => (
          <g key={m.ym}>
            {m.buyAmt > 0 && <rect x={m.mid - bw / 2} y={baseY - bar(m.buyAmt)} width={bw} height={Math.max(1, bar(m.buyAmt))} fill={RED} opacity={0.85} />}
            {m.sellAmt > 0 && <rect x={m.mid - bw / 2} y={baseY} width={bw} height={Math.max(1, bar(m.sellAmt))} fill={GREEN} opacity={0.85} />}
          </g>
        ))}

        {/* 價格線上的買賣點 */}
        {g.months.filter((m) => m.avg && m.net).map((m) => (
          <circle key={m.ym} cx={m.mid} cy={g.y(m.avg!)} r={Math.min(9, 3 + Math.sqrt(Math.abs(m.net) / g.maxAmt) * 6)}
            fill={m.net > 0 ? RED : GREEN} fillOpacity={0.75} stroke="#0d1220" />
        ))}
        {g.placed.map(({ m, bx, by, cy, text1, text2 }) => {
          const c = m.net > 0 ? RED : GREEN;
          return (
            <g key={`n${m.ym}`}>
              <line x1={m.mid} y1={cy} x2={Math.min(Math.max(m.mid, bx + 4), bx + 124)} y2={m.net > 0 ? by + 36 : by} stroke={c} strokeOpacity={0.6} />
              <rect x={bx} y={by} width={128} height={36} rx={4} fill="#0d1220" stroke={c} strokeOpacity={0.8} />
              <text x={bx + 6} y={by + 14} fontSize={11} fill="#e2e8f0">{text1}</text>
              <text x={bx + 6} y={by + 29} fontSize={11} fill={c}>{text2}</text>
            </g>
          );
        })}

        {/* 滑鼠移到月份上看明細 */}
        {g.months.map((m) => (
          <rect key={`h${m.ym}`} x={m.mid - g.monthW / 2} y={PT} width={g.monthW} height={PH + GAP + BH} fill="transparent"
            onMouseEnter={() => setHover(m.ym)} onClick={() => setHover(m.ym)} />
        ))}
        {hm && <line x1={hm.mid} x2={hm.mid} y1={PT} y2={PT + PH + GAP + BH} stroke="#00d4aa" strokeOpacity={0.4} />}
      </svg>
      </div>
      <div className="mt-1 min-h-[20px] text-xs text-slate-400 font-mono">
        {hm ? (
          <>
            {hm.ym.replace("-", "/")}　均價 {hm.avg ? priceFmt(hm.avg) : "—"}
            <span className="text-[#ef4444]">買 {Math.round(hm.b / 1000).toLocaleString()} 張{hm.buyAmt ? `（${money(hm.buyAmt)}）` : ""}</span>
            <span className="text-[#22c55e]">賣 {Math.round(hm.s / 1000).toLocaleString()} 張{hm.sellAmt ? `（${money(hm.sellAmt)}）` : ""}</span>
          </>
        ) : <span className="text-slate-600">滑鼠移到圖上看各月明細</span>}
      </div>
    </div>
  );
}
