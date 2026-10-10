import Link from "next/link";
import {
  TrendingUp, BarChart2, Shield, Radio, DollarSign,
  FileText, Calendar, ArrowDownUp, Zap, Activity,
  PieChart, Search, Layers, Ticket, Users,
  UserCheck,
} from "lucide-react";

const modules = [
  {
    icon: TrendingUp,
    title: "漲停訊號鎖定",
    desc: "精確捕捉每日強勢股，族群分類與漲停時間分布一覽無遺",
    href: "/limit-up",
    accent: "#00d4aa",
  },
  {
    icon: Activity,
    title: "隔日績效追蹤",
    desc: "漲停股隔日開高走低 vs 續強的歷史勝率統計，數據說話",
    href: "/next-day",
    accent: "#3b82f6",
  },
  {
    icon: ArrowDownUp,
    title: "成交排行",
    desc: "上市櫃個股與 ETF 依成交金額排序，看今天的錢流向哪些股票、哪些族群",
    href: "/ranking",
    accent: "#00d4aa",
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
    accent: "#ef4444",
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
    badge: "20:08",
  },
  {
    icon: Shield,
    title: "處置威脅評估",
    desc: "量化處置機率，提前預警潛在管制名單，守住每一道防線",
    href: "/disposition",
    accent: "#ef4444",
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
    accent: "#00d4aa",
  },
  {
    icon: FileText,
    title: "季報偵查站",
    desc: "EPS 成長率篩選、季報公布時程掌握，業績行情不錯失",
    href: "/quarterly",
    accent: "#3b82f6",
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
    icon: Radio,
    title: "情報截收站",
    desc: "5 分鐘全頻掃描重大公告，零時差情報直達你的視線",
    href: "/announcements",
    accent: "#22c55e",
  },
  {
    icon: Search,
    title: "個股情報查詢",
    desc: "輸入股號或名稱，整合站內所有偵測資料，一鍵全覽",
    href: "/search",
    accent: "#00d4aa",
  },
];

export default function ResearchGrid() {
  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-16">
      <div className="mb-6">
        <p className="text-[10px] font-mono text-slate-600 tracking-[0.25em] uppercase mb-1">Mission Modules</p>
        <h2 className="text-lg font-bold text-white">偵測模組總覽</h2>
        <p className="text-sm text-slate-500 mt-0.5">{modules.length} 個情報模組，全面制霸台股關鍵訊號</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {modules.map((m) => (
          <Link
            key={m.href}
            href={m.href}
            className="group rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 card-hover flex flex-col gap-3"
          >
            <div className="flex items-start justify-between">
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: `${m.accent}14`, border: `1px solid ${m.accent}25` }}
              >
                <m.icon className="w-4 h-4" style={{ color: m.accent }} />
              </div>
              {m.badge && (
                <span className="text-[10px] font-mono text-slate-600 bg-[#1e2a3a] px-1.5 py-0.5 rounded tracking-wide">
                  {m.badge}
                </span>
              )}
            </div>
            <div>
              <div className="text-sm font-semibold text-white group-hover:text-[#00d4aa] transition-colors">
                {m.title}
              </div>
              <div className="text-xs text-slate-500 mt-1 leading-relaxed line-clamp-2">
                {m.desc}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
