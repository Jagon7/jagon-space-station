export type LimitUpStock = {
  code: string;
  name: string;
  sector: string;
  change: number;
  volume: number;
  tradeValue?: number;
  limitTime: string;
  openPrice: number;
  closePrice: number;
  market?: string;
  instiForeign?: number | null;
  instiTrust?: number | null;
  instiDealer?: number | null;
  instiTotal?: number | null;
  reason?: string;
};

export type SectorSummary = {
  name: string;
  count: number;
  momentum: "strong" | "normal" | "weak";
};

export type NoticeStock = {
  code: string;
  name: string;
  noticeCount: number;
  info: string;
  date: string;
  closePrice: number;
  market?: string;
};

export type DispositionStock = {
  code: string;
  name: string;
  count: number;
  condition: string;
  period: string;
  endDate: string;
  announceDate: string;
  market?: string;
};

export type Announcement = {
  time: string;
  code: string;
  name: string;
  type: string;
  important: boolean;
  content?: string;
};

export type CBIssuance = {
  code: string;             // 股號
  name: string;             // 公司名稱
  cbSeries: string;         // CB 期別，e.g. "英業達三"
  filingDate: string;       // 申報日 YYYY-MM-DD
  bookBuildDate?: string;   // 詢圈日 YYYY-MM-DD
  listingDate?: string;     // 掛牌日 YYYY-MM-DD
  amount?: number;          // 發行金額（億元）
  conversionPrice?: number; // 轉換價（元）
  closePrice?: number;      // 現股收盤價（元）
  market?: string;          // 上市 / 上櫃
  underwriter?: string;     // 主辦承銷商
};

export type SFBCBRecord = {
  code: string;
  name: string;
  market: string;
  status: string;           // 生效 / 審查中 / 自行撤回 / 廢止撤銷 / 退件
  cbType: string;           // 轉換公司債(無擔保) / 轉換公司債(海外無擔保)
  amount?: number | null;   // 億元(台幣) 或 百萬(外幣)
  currency: string;
  filingDate?: string | null;
  effectiveDate?: string | null;
  withdrawDate?: string | null;
  underwriter?: string | null;
};

export type MarketSummary = {
  date: string;
  limitUpCount: number;
  sectorCount: number;
  noticeCount: number;
  dispositionCount: number;
  announcementCount: number;
  marketMood: "強勢" | "偏強" | "中性" | "偏弱" | "弱勢";
  taiexChange: number;
};

export type EtfFlowAction = "new" | "remove" | "buy" | "sell";

export type EtfFlowChange = {
  code: string;
  name: string;
  action: EtfFlowAction;
  prevShares: number;
  currShares: number;
  diffShares: number;      // positive = bought, negative = sold
  closePrice: number;
  diffValue: number;       // diffShares * closePrice (TWD)
  weight: number;          // current weight % in ETF
};

export type EtfFlowItem = {
  etfCode: string;
  etfName: string;
  category: "高股息" | "主動型" | "市值型";
  navPerUnit: number;
  totalUnits: number;
  changes: EtfFlowChange[];
};

export type EtfFlowData = {
  date: string;
  data: EtfFlowItem[];
};

export type MarketHistoryEntry = {
  date: string;
  limitUpCount: number;
  marketMood: MarketSummary["marketMood"];
  taiexChange: number;
  topSectors: { name: string; count: number }[];
};

export type SectorPerformance = {
  name: string;
  changePercent: number;
};

export type SectorStock = {
  code: string;
  name: string;
  market: string;
  changePercent: number;
  closePrice: number;
  volume: number;
  tradeValue: number;
};
