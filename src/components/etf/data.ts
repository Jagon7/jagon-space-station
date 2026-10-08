"use client";

import { useStaticJson } from "@/lib/static-json";

// ── public/data/etf/*.json（由 scripts/build_etf_views.py 產生）的型別 ──
export type EtfInfo = {
  c: string; n: string; i: string; k: "A" | "P";
  d: string; pd: string | null; aum: number; cnt: number; ok: boolean; hist: number;
};
// [etfIdx, shares, weight, value(億), diffShares | null]
export type Holder = [number, number, number | null, number | null, number | null];
// [stock, prevShares, currShares, prevWeight, currWeight, diffValue(億)]
export type ChangeRow = [string, number, number, number | null, number | null, number | null];

export type CoreData = {
  priceDate: string | null;
  etfs: EtfInfo[];
  names: Record<string, string>;
  close: Record<string, number>;
  holders: Record<string, Holder[]>;
  changes: [number, ChangeRow[]][];
};

// [date, prevDate, unitsRatio, [[stock, rawDiff, adjDiff, close]]]
export type ActiveEvent = [string, string, number, [string, number, number, number | null][]];
export type ActiveData = { events: Record<string, ActiveEvent[]>; names: Record<string, string> };

// [code, name, category, aum, nav, units, unitsChange, flow, flow5, aumChange, premium, tracked]
export type AumRow = [string, string, string, number, number, number, number, number, number, number | null, number | null, boolean];
export type AumData = { date: string | null; prev: string | null; nFlow: number; rows: AumRow[] };

/** file 為 null 時不載入（分頁切到才抓） */
export function useEtfJson<T>(file: string | null) {
  return useStaticJson<T>(file ? `etf/${file}` : null);
}

// ── 格式 ─────────────────────────────────────────────────────
export const isTw = (code: string) => !code.includes(" ");

/** 股數 → 張（海外股票維持股數） */
export function fmtLots(shares: number, code = ""): string {
  if (!isTw(code)) return `${shares.toLocaleString()} 股`;
  const lots = shares / 1000;
  const abs = Math.abs(lots);
  return `${abs >= 100 ? Math.round(lots).toLocaleString() : abs >= 10 ? lots.toFixed(0) : abs >= 1 ? lots.toFixed(1).replace(/\.0$/, "") : lots.toFixed(2).replace(/0$/, "")} 張`;
}

export function fmtSignedLots(shares: number, code = ""): string {
  const s = fmtLots(shares, code);
  return shares > 0 ? `+${s}` : s;
}

/** 億元 */
export function fmtYi(v: number | null | undefined, signed = false): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const s = abs >= 1000 ? Math.round(v).toLocaleString() : abs >= 100 ? v.toFixed(1) : abs >= 1 ? v.toFixed(2) : v.toFixed(2);
  return signed && v > 0 ? `+${s}` : s;
}

/** 元 → 兆 / 億 */
export function fmtMoney(v: number | null | undefined, signed = false): string {
  if (v == null) return "—";
  const sign = signed && v > 0 ? "+" : "";
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${sign}${(v / 1e12).toFixed(2)}兆`;
  if (abs >= 1e8) return `${sign}${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: abs >= 1e10 ? 0 : 1 })}億`;
  if (abs >= 1e4) return `${sign}${(v / 1e4).toFixed(0)}萬`;
  return `${sign}${Math.round(v).toLocaleString()}`;
}

export const fmtPct = (w: number | null | undefined) => (w == null ? "—" : `${w.toFixed(2)}%`);
export const mmdd = (d: string | null | undefined) => (d ? `${d.slice(5, 7)}/${d.slice(8, 10)}` : "—");

/** 台股慣例：紅漲綠跌 */
export const signColor = (v: number | null | undefined) =>
  v == null || v === 0 ? "text-slate-400" : v > 0 ? "text-[#ef4444]" : "text-[#22c55e]";
