import type { LimitUpStock, DispositionStock, Announcement, MarketSummary, CBIssuance } from "./types";

export const mockMarketSummary: MarketSummary = {
  date: "2026-05-07",
  limitUpCount: 48,
  sectorCount: 14,
  noticeCount: 5,
  dispositionCount: 3,
  announcementCount: 127,
  marketMood: "強勢",
  taiexChange: 1.23,
};

export const mockLimitUpStocks: LimitUpStock[] = [
  { code: "2330", name: "台積電",   sector: "半導體",    change: 10, volume: 45820, limitTime: "09:02", openPrice: 920, closePrice: 1012 },
  { code: "2317", name: "鴻海",     sector: "電子製造",  change: 10, volume: 32100, limitTime: "09:15", openPrice: 188, closePrice: 206 },
  { code: "3711", name: "日月光",   sector: "封測",      change: 10, volume: 28500, limitTime: "09:07", openPrice: 148, closePrice: 162 },
  { code: "2454", name: "聯發科",   sector: "IC設計",    change: 10, volume: 19200, limitTime: "09:31", openPrice: 1150, closePrice: 1265 },
  { code: "6505", name: "台塑化",   sector: "石化",      change: 10, volume: 12400, limitTime: "10:02", openPrice: 88,  closePrice: 96 },
  { code: "3034", name: "聯詠",     sector: "IC設計",    change: 10, volume: 9800,  limitTime: "09:55", openPrice: 420, closePrice: 462 },
  { code: "2379", name: "瑞昱",     sector: "IC設計",    change: 10, volume: 8700,  limitTime: "11:20", openPrice: 580, closePrice: 638 },
  { code: "2382", name: "廣達",     sector: "AI伺服器",  change: 10, volume: 33400, limitTime: "09:08", openPrice: 380, closePrice: 418 },
  { code: "2308", name: "台達電",   sector: "電源",      change: 10, volume: 14500, limitTime: "09:44", openPrice: 352, closePrice: 387 },
  { code: "6669", name: "緯穎",     sector: "AI伺服器",  change: 10, volume: 11200, limitTime: "09:12", openPrice: 2400, closePrice: 2640 },
];

export const mockDispositionStocks: DispositionStock[] = [
  { code: "2603", name: "長榮", count: 1, condition: "連續三次", period: "115/05/07～115/05/20", endDate: "2026-05-20", announceDate: "115/05/06" },
  { code: "9910", name: "豐泰", count: 1, condition: "連續三次", period: "115/05/07～115/05/20", endDate: "2026-05-20", announceDate: "115/05/06" },
];

export const mockAnnouncements: Announcement[] = [
  { time: "20:35", code: "2330", name: "台積電",   type: "法說會",   important: true,  content: "Q2 營收預估超預期" },
  { time: "19:12", code: "6547", name: "高端疫苗", type: "財報",     important: false, content: "113Q1 EPS 公告" },
  { time: "18:44", code: "2317", name: "鴻海",     type: "重大訊息", important: true,  content: "取得大型 AI 伺服器訂單" },
  { time: "17:20", code: "3711", name: "日月光",   type: "庫藏股",   important: false, content: "買回 5000 張計畫" },
  { time: "16:55", code: "2382", name: "廣達",     type: "重大訊息", important: true,  content: "與 NVIDIA 深化合作協議" },
  { time: "16:30", code: "2308", name: "台達電",   type: "財報",     important: false, content: "113Q1 EPS 2.8 元" },
];

export const mockSectorTrend = [
  { date: "05/01", aiServer: 6, semiconductor: 5, pcb: 3, panel: 2 },
  { date: "05/02", aiServer: 5, semiconductor: 6, pcb: 4, panel: 3 },
  { date: "05/05", aiServer: 7, semiconductor: 4, pcb: 5, panel: 2 },
  { date: "05/06", aiServer: 9, semiconductor: 7, pcb: 3, panel: 4 },
  { date: "05/07", aiServer: 8, semiconductor: 7, pcb: 5, panel: 4 },
];

export const mockCBIssuances: CBIssuance[] = [
  {
    code: "6176", name: "瑞儀光電", cbSeries: "瑞儀二",
    filingDate: "2026-04-15", bookBuildDate: "2026-05-06", listingDate: "2026-05-12",
    amount: 8, conversionPrice: 48.5, closePrice: 45.2,
    market: "上市", underwriter: "元大證券",
  },
  {
    code: "3529", name: "力旺電子", cbSeries: "力旺二",
    filingDate: "2026-04-20", bookBuildDate: "2026-05-08", listingDate: "2026-05-15",
    amount: 15, conversionPrice: 620, closePrice: 598,
    market: "上市", underwriter: "凱基證券",
  },
  {
    code: "6188", name: "廣明光電", cbSeries: "廣明一",
    filingDate: "2026-04-22", bookBuildDate: "2026-05-09", listingDate: "2026-05-19",
    amount: 6, conversionPrice: 85.3, closePrice: 81.6,
    market: "上櫃", underwriter: "統一證券",
  },
  {
    code: "3042", name: "晶技",     cbSeries: "晶技三",
    filingDate: "2026-04-24", bookBuildDate: "2026-05-12", listingDate: "2026-05-23",
    amount: 20, conversionPrice: 105.8, closePrice: 99.3,
    market: "上市", underwriter: "富邦證券",
  },
  {
    code: "2356", name: "英業達",   cbSeries: "英業達三",
    filingDate: "2026-04-28", listingDate: "2026-05-28",
    amount: 50, conversionPrice: 52.5, closePrice: 49.8,
    market: "上市", underwriter: "中信證券",
  },
  {
    code: "8150", name: "矽統",     cbSeries: "矽統一",
    filingDate: "2026-04-30", listingDate: "2026-06-02",
    amount: 12, conversionPrice: 78.2, closePrice: 74.6,
    market: "上櫃", underwriter: "群益證券",
  },
  {
    code: "3481", name: "群創光電", cbSeries: "群創三",
    filingDate: "2026-05-06", listingDate: "2026-06-10",
    amount: 80, conversionPrice: 18.3, closePrice: 17.5,
    market: "上市", underwriter: "國泰證券",
  },
  {
    code: "3045", name: "台灣大哥大", cbSeries: "台灣大三",
    filingDate: "2026-04-10", bookBuildDate: "2026-04-28", listingDate: "2026-05-06",
    amount: 200, conversionPrice: 118.5, closePrice: 112.8,
    market: "上市", underwriter: "元大證券",
  },
];

export const mockLimitUpTrend = [
  { date: "05/01", count: 32, mood: 65 },
  { date: "05/02", count: 28, mood: 58 },
  { date: "05/05", count: 41, mood: 74 },
  { date: "05/06", count: 55, mood: 85 },
  { date: "05/07", count: 48, mood: 79 },
];
