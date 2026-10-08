import fs from "fs";
import path from "path";
import type {
  LimitUpStock, NoticeStock, DispositionStock, Announcement,
  MarketSummary, SectorSummary, CBIssuance, SFBCBRecord, EtfFlowData,
  MarketHistoryEntry, SectorPerformance, SectorStock, EtfFlowItem,
} from "./types";
import * as mock from "./mock-data";

const DATA_DIR = path.join(process.cwd(), "data");

type Dated<T> = { date: string; data: T };

// The site is statically exported, so data is read from ./data at build time.
// The deploy workflow rebuilds after every data fetch.
async function readJson<T>(filename: string): Promise<T | null> {
  try {
    const raw = fs.readFileSync(path.join(DATA_DIR, filename), "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function getLimitUpStocks(): Promise<LimitUpStock[]> {
  const file = await readJson<Dated<LimitUpStock[]>>("limit-up.json");
  return file?.data ?? mock.mockLimitUpStocks;
}

export async function getSectors(): Promise<SectorSummary[]> {
  const file = await readJson<Dated<SectorSummary[]>>("sectors.json");
  return file?.data ?? [];
}

export async function getMarketSummary(): Promise<MarketSummary> {
  const file = await readJson<MarketSummary>("market-summary.json");
  return file ?? mock.mockMarketSummary;
}

export async function getMarketHistory(): Promise<MarketHistoryEntry[]> {
  const file = await readJson<Dated<MarketHistoryEntry[]>>("market-history.json");
  return file?.data ?? [];
}

export async function getSectorPerformance(): Promise<SectorPerformance[]> {
  const file = await readJson<Dated<SectorPerformance[]>>("sector-performance.json");
  return file?.data ?? [];
}

export async function getSectorStocks(): Promise<Record<string, SectorStock[]>> {
  const file = await readJson<Dated<Record<string, SectorStock[]>>>("sector-stocks.json");
  return file?.data ?? {};
}

export async function getNoticeStocks(): Promise<NoticeStock[]> {
  const file = await readJson<Dated<NoticeStock[]>>("notice.json");
  return file?.data ?? [];
}

export async function getDispositionStocks(): Promise<DispositionStock[]> {
  const file = await readJson<Dated<DispositionStock[]>>("disposition.json");
  return file?.data ?? [];
}

export async function getAnnouncements(): Promise<Announcement[]> {
  const file = await readJson<Dated<Announcement[]>>("announcements.json");
  return file?.data ?? mock.mockAnnouncements;
}

export async function getCBIssuances(): Promise<CBIssuance[]> {
  const file = await readJson<Dated<CBIssuance[]>>("cb-watch.json");
  return file?.data ?? mock.mockCBIssuances;
}

export async function getSFBCBRecords(): Promise<SFBCBRecord[]> {
  const file = await readJson<Dated<SFBCBRecord[]>>("sfb-cb.json");
  return file?.data ?? [];
}

export async function getLastUpdated(): Promise<string> {
  const file = await readJson<{ updatedAt: string; date: string }>("last-updated.json");
  return file?.updatedAt ?? new Date().toISOString();
}

/** 首頁 ETF 卡片：由 public/data/etf/core.json（建置前 scripts/build_etf_views.py 產生）整理 */
export async function getEtfFlow(): Promise<EtfFlowData | null> {
  type Core = {
    etfs: { c: string; n: string; k: "A" | "P"; d: string; pd: string | null }[];
    names: Record<string, string>;
    close: Record<string, number>;
    changes: [number, [string, number, number, number | null, number | null, number | null][]][];
  };
  let core: Core;
  try {
    core = JSON.parse(fs.readFileSync(path.join(process.cwd(), "public", "data", "etf", "core.json"), "utf-8"));
  } catch {
    return null;
  }
  const data: EtfFlowItem[] = core.changes
    .filter(([, rows]) => rows.length)
    .map(([idx, rows]) => {
      const e = core.etfs[idx];
      return {
        etfCode: e.c, etfName: e.n, category: e.k === "A" ? "主動型" : "市值型",
        navPerUnit: 0, totalUnits: 0,
        changes: rows.filter(([code]) => !code.includes(" ")).map(([code, ps, cs, , cw, val]) => ({
          code, name: core.names[code] ?? code,
          action: ps === 0 ? "new" : cs === 0 ? "remove" : cs > ps ? "buy" : "sell",
          prevShares: ps, currShares: cs, diffShares: cs - ps,
          closePrice: core.close[code] ?? 0, diffValue: Math.round((val ?? 0) * 1e8), weight: cw ?? 0,
        })),
      };
    });
  if (!data.length) return null;
  const date = core.etfs.map((e) => e.d).sort().at(-1) ?? "";
  return { date, data };
}
