import fs from "fs";
import path from "path";
import type {
  LimitUpStock, NoticeStock, DispositionStock, Announcement,
  MarketSummary, SectorSummary, CBIssuance, SFBCBRecord, EtfFlowData,
} from "./types";
import * as mock from "./mock-data";

const DATA_DIR = path.join(process.cwd(), "data");
const GITHUB_RAW = "https://raw.githubusercontent.com/Jagon7/taiwan-stock-radar/main/data";
const IS_PROD = process.env.NODE_ENV === "production";

type Dated<T> = { date: string; data: T };

async function readJson<T>(filename: string): Promise<T | null> {
  if (IS_PROD) {
    try {
      const res = await fetch(`${GITHUB_RAW}/${filename}`, {
        cache: "no-store",
      });
      if (!res.ok) return null;
      return res.json() as Promise<T>;
    } catch {
      return null;
    }
  }
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

export async function getEtfFlow(): Promise<EtfFlowData | null> {
  const file = await readJson<EtfFlowData>("etf-flow.json");
  return file ?? mock.mockEtfFlow;
}
