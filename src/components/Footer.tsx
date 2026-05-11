import { Satellite } from "lucide-react";
import Link from "next/link";

export default function Footer() {
  return (
    <footer className="border-t border-[#1e2a3a] bg-[#080c1a] mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">

          {/* Brand */}
          <div className="md:col-span-2">
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-7 h-7 rounded-lg bg-[#00d4aa]/10 border border-[#00d4aa]/30 flex items-center justify-center">
                <Satellite className="w-4 h-4 text-[#00d4aa]" />
              </div>
              <div className="flex flex-col leading-none">
                <span className="font-bold text-white text-sm tracking-widest uppercase">Jagon</span>
                <span className="text-[9px] text-[#00d4aa]/60 tracking-[0.2em] uppercase font-mono">Space Station</span>
              </div>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed max-w-xs">
              整合台股每日全域訊號的情報制高站——漲停、籌碼、處置預警、公告截收，
              一站在握，情報優勢即是勝勢。
            </p>
          </div>

          {/* Links */}
          <div>
            <h3 className="text-[10px] font-mono font-semibold text-slate-500 uppercase tracking-[0.2em] mb-3">即時戰情</h3>
            <ul className="space-y-2">
              {[
                { label: "氣氛評估", href: "/atmosphere" },
                { label: "漲停訊號", href: "/limit-up" },
                { label: "隔日追蹤", href: "/next-day" },
                { label: "統計戰報", href: "/stats" },
              ].map((item) => (
                <li key={item.href}>
                  <Link href={item.href} className="text-xs text-slate-500 hover:text-[#00d4aa] transition-colors">
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-[10px] font-mono font-semibold text-slate-500 uppercase tracking-[0.2em] mb-3">籌碼雷達</h3>
            <ul className="space-y-2">
              {[
                { label: "券差偵察", href: "/short" },
                { label: "處置威脅", href: "/disposition" },
                { label: "主動 ETF", href: "/etf" },
                { label: "情報截收", href: "/announcements" },
              ].map((item) => (
                <li key={item.href}>
                  <Link href={item.href} className="text-xs text-slate-500 hover:text-[#00d4aa] transition-colors">
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Disclaimer */}
        <div className="border-t border-[#1e2a3a] pt-6 space-y-2">
          <p className="text-[11px] text-slate-600 leading-relaxed">
            <strong className="text-slate-500">免責聲明：</strong>
            本站所有資訊僅供參考，不構成任何投資建議。投資有風險，進場需審慎評估。
            所有數據均來自公開資訊，本站不對資料正確性與即時性負責，使用者應自行研究判斷。
          </p>
          <p className="text-[11px] text-slate-700 font-mono">
            © 2026 Jagon Space Station · Data Source: TWSE / MOPS
          </p>
        </div>
      </div>
    </footer>
  );
}
