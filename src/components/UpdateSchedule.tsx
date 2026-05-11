import { Clock } from "lucide-react";

const schedule = [
  {
    time: "16:45",
    label: "漲停訊號 & 氣氛評估",
    desc: "收盤後即時整理全市場漲停名單，解析族群輪動與氣氛強弱評分",
    color: "#00d4aa",
    dot: "bg-[#00d4aa]",
    dotBorder: "border-[#00d4aa]",
  },
  {
    time: "19:00",
    label: "處置威脅名單",
    desc: "依主管機關標準精算各股達處置門檻的量化機率，提前部署防線",
    color: "#f59e0b",
    dot: "bg-[#f59e0b]",
    dotBorder: "border-[#f59e0b]",
  },
  {
    time: "20:08",
    label: "券差資料同步",
    desc: "更新融券餘額差異，解讀籌碼鬆緊，偵察潛在軋空動能",
    color: "#3b82f6",
    dot: "bg-[#3b82f6]",
    dotBorder: "border-[#3b82f6]",
  },
  {
    time: "22:30",
    label: "主動 ETF 持股異動",
    desc: "截收主動型 ETF 最新建倉與減碼動向，追蹤法人資金佈局",
    color: "#a78bfa",
    dot: "bg-[#a78bfa]",
    dotBorder: "border-[#a78bfa]",
  },
  {
    time: "全天候",
    label: "情報截收雷達",
    desc: "每 5 分鐘全頻掃描重訊、財報、庫藏股公告，零時差情報入站",
    color: "#22c55e",
    dot: "bg-[#22c55e]",
    dotBorder: "border-[#22c55e]",
  },
];

export default function UpdateSchedule() {
  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-14">
      <div className="mb-6 flex items-center gap-2">
        <Clock className="w-4 h-4 text-[#00d4aa]" />
        <div>
          <p className="text-[10px] font-mono text-slate-600 tracking-[0.25em] uppercase mb-0.5">Mission Timeline</p>
          <h2 className="text-lg font-bold text-white">每日情報入站節奏</h2>
        </div>
      </div>

      <div className="relative">
        <div className="hidden md:block absolute left-[88px] top-4 bottom-4 w-px bg-gradient-to-b from-[#00d4aa]/40 via-[#3b82f6]/20 to-transparent" />

        <div className="space-y-3">
          {schedule.map((item, i) => (
            <div key={i} className="flex gap-6 items-start group">
              <div className="hidden md:block w-16 flex-shrink-0 text-right pt-3.5">
                <span className="text-xs font-mono font-bold" style={{ color: item.color }}>
                  {item.time}
                </span>
              </div>

              <div className="hidden md:flex flex-col items-center relative z-10 pt-4">
                <div
                  className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${item.dot}`}
                  style={{ borderColor: item.color }}
                />
              </div>

              <div className="flex-1 rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4 card-hover">
                <div className="flex items-start gap-3">
                  <div className="md:hidden w-10 flex-shrink-0">
                    <span className="text-xs font-mono font-bold" style={{ color: item.color }}>
                      {item.time}
                    </span>
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{item.label}</div>
                    <div className="text-xs text-slate-500 mt-0.5 leading-relaxed">{item.desc}</div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
