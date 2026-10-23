import Link from "next/link";
import {
  TrendingUp, BarChart2, Shield, DollarSign,
  FileText, Calendar, ArrowDownUp, Zap, Activity,
  PieChart, Search, Layers, Ticket, Users,
  UserCheck, Star, Filter, Landmark, LineChart, Globe, Newspaper, Mic, Crosshair, RotateCw, Gauge,
} from "lucide-react";

const modules = [
  {
    icon: Crosshair,
    title: "十日波段策略",
    desc: "出量做多、輿情籌碼兩個策略的明日進場名單、持有中部位與到期出場，每天推播 LINE",
    href: "/strategy",
    accent: "#f05252",
  },
  {
    icon: RotateCw,
    title: "高週轉率黑K",
    desc: "每日週轉率排行，回測週轉率越高隔天是否越容易開高走低，附開盤空、收盤補的扣成本績效",
    href: "/turnover",
    accent: "#22c55e",
  },
  {
    icon: Gauge,
    title: "市場風險監控",
    desc: "VIX、VVIX、期限結構、MOVE、高收益債利差（CDS 替代）、金融壓力指數整合成風險溫度，每天盤前快報附上",
    href: "/risk",
    accent: "#f59e0b",
  },
  {
    icon: Globe,
    title: "國際類股連動",
    desc: "美股類股與龍頭股隔夜漲跌，對應台股哪些股票開盤可能跟著反應；每個交易日 08:00 推播盤前快報",
    href: "/global",
    accent: "#38bdf8",
  },
  {
    icon: Newspaper,
    title: "券商研究報告",
    desc: "外資與投顧最新目標價、評等、潛在漲幅與報告重點，新報告推播提醒",
    href: "/reports",
    accent: "#4f8cff",
  },
  {
    icon: Mic,
    title: "法說會",
    desc: "即將舉行的法說行事曆，以及近期法說的營運重點、展望與問答摘要",
    href: "/conferences",
    accent: "#a78bfa",
  },
  {
    icon: Star,
    title: "自選股",
    desc: "把常看的股票加入清單，一頁看完它們在全站觸發的技術、法人、營收、內部人、事件訊號",
    href: "/watchlist",
    accent: "#f59e0b",
  },
  {
    icon: Filter,
    title: "技術選股",
    desc: "站上月線季線、多頭排列、爆量、突破整理、創新高，訊號可複選",
    href: "/screener",
    accent: "#4f8cff",
  },
  {
    icon: Landmark,
    title: "三大法人",
    desc: "外資、投信、自營商個股買賣超，連續買超、土洋同買與對作",
    href: "/institutional",
    accent: "#38bdf8",
  },
  {
    icon: LineChart,
    title: "期貨選擇權籌碼",
    desc: "外資台指期多空、散戶小台多空比、P/C ratio",
    href: "/futures",
    accent: "#a78bfa",
  },
  {
    icon: PieChart,
    title: "大戶持股",
    desc: "集保千張大戶與散戶比例每週變化，找籌碼集中的股票",
    href: "/holders",
    accent: "#f05252",
  },
  {
    icon: TrendingUp,
    title: "漲停訊號鎖定",
    desc: "精確捕捉每日強勢股，族群分類與漲停時間分布一覽無遺",
    href: "/limit-up",
    accent: "#4f8cff",
  },
  {
    icon: Activity,
    title: "隔日績效追蹤",
    desc: "漲停股隔日開高走低 vs 續強的歷史勝率統計，數據說話",
    href: "/next-day",
    accent: "#38bdf8",
  },
  {
    icon: ArrowDownUp,
    title: "成交排行",
    desc: "上市櫃個股與 ETF 依成交金額排序，看今天的錢流向哪些股票、哪些族群",
    href: "/ranking",
    accent: "#4f8cff",
  },
  {
    icon: Layers,
    title: "產業細分類",
    desc: "47 個產業、上中下游 497 個細類，今日最強與最弱的細產業一目了然",
    href: "/industry",
    accent: "#f59e0b",
  },
  {
    icon: Ticket,
    title: "CB 圈購到掛牌",
    desc: "可轉債申報、詢圈／競拍、訂價、掛牌排在同一條時間軸，兩週內時程一次看",
    href: "/cb-watch",
    accent: "#a78bfa",
  },
  {
    icon: Users,
    title: "重點分點追蹤",
    desc: "每天追蹤 10 個指定券商分點的買賣超，近 N 日累積進出與個股逐日明細",
    href: "/broker",
    accent: "#f05252",
  },
  {
    icon: UserCheck,
    title: "內部人持股異動",
    desc: "董監事、經理人、大股東每月在市場買賣多少，疊在股價上看他們在什麼價位進出",
    href: "/insider",
    accent: "#38bdf8",
  },
  {
    icon: BarChart2,
    title: "戰情統計戰報",
    desc: "族群漲停頻率、氣氛指數歷史趨勢，全局視野不遺漏",
    href: "/stats",
    accent: "#a78bfa",
  },
  {
    icon: ArrowDownUp,
    title: "券差偵察系統",
    desc: "融券餘額消長追蹤，軋空潛力股即時浮現",
    href: "/short",
    accent: "#f59e0b",
    badge: "21:30",
  },
  {
    icon: Shield,
    title: "處置威脅評估",
    desc: "量化處置機率，提前預警潛在管制名單，守住每一道防線",
    href: "/disposition",
    accent: "#f05252",
    badge: "19:00",
  },
  {
    icon: PieChart,
    title: "主動 ETF 偵察",
    desc: "31 檔主動式 ETF 買賣超彙總，可扣除申購贖回，跟緊經理人的每一步",
    href: "/etf-flow?tab=active",
    accent: "#22c55e",
    badge: "21:30",
  },
  {
    icon: Activity,
    title: "ETF 持股查詢",
    desc: "90 檔台股 ETF 每日完整持股：查個股被哪些 ETF 持有、每日增減與 AUM 排行",
    href: "/etf-flow",
    accent: "#a78bfa",
    badge: "21:30",
  },
  {
    icon: DollarSign,
    title: "自結盈餘情報",
    desc: "上市櫃自行公布盈餘數據彙整，先市場一步掌握獲利動向",
    href: "/eps",
    accent: "#4f8cff",
  },
  {
    icon: FileText,
    title: "季報偵查站",
    desc: "EPS 成長率篩選、季報公布時程掌握，業績行情不錯失",
    href: "/quarterly",
    accent: "#38bdf8",
  },
  {
    icon: Calendar,
    title: "月營收雷達",
    desc: "每月 10 日公布，YoY / MoM 雙維比對，營收爆發一眼識別",
    href: "/revenue",
    accent: "#a78bfa",
  },
  {
    icon: Zap,
    title: "庫藏股追蹤",
    desc: "公司護盤動作即時偵測，信心買進信號精準標記",
    href: "/buyback",
    accent: "#f59e0b",
  },
  {
    icon: Search,
    title: "個股情報查詢",
    desc: "輸入股號或名稱，整合站內所有偵測資料，一鍵全覽",
    href: "/search",
    accent: "#4f8cff",
  },
];

export default function ResearchGrid() {
  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-16">
      <div className="mb-6">
        <p className="text-[10px] font-mono text-[#7c8aa0] tracking-[0.25em] uppercase mb-1">Mission Modules</p>
        <h2 className="text-lg font-bold text-white">所有功能</h2>
        <p className="text-sm text-[#8b97ab] mt-0.5">{modules.length} 個情報模組，，也可以從上方選單進入</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {modules.map((m) => (
          <Link
            key={m.href}
            href={m.href}
            className="group rounded-xl border border-[#243247] bg-[#0d1220] p-4 card-hover flex flex-col gap-3"
          >
            <div className="flex items-start justify-between">
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: `${m.accent}14`, border: `1px solid ${m.accent}25` }}
              >
                <m.icon className="w-4 h-4" style={{ color: m.accent }} />
              </div>
              {m.badge && (
                <span className="text-[10px] font-mono text-[#7c8aa0] bg-[#243247] px-1.5 py-0.5 rounded tracking-wide">
                  {m.badge}
                </span>
              )}
            </div>
            <div>
              <div className="text-sm font-semibold text-white group-hover:text-[#4f8cff] transition-colors">
                {m.title}
              </div>
              <div className="text-xs text-[#8b97ab] mt-1 leading-relaxed line-clamp-2">
                {m.desc}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
