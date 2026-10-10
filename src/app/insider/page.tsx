import { Suspense } from "react";
import PageShell from "@/components/PageShell";
import InsiderDashboard from "@/components/insider/InsiderDashboard";

export default function InsiderPage() {
  return (
    <PageShell
      title="內部人持股異動"
      subtitle="董監事、經理人與大股東每個月在市場上買賣了多少股票：疊在股價走勢上，看他們在什麼價位進出、誰在買誰在賣。"
      badge="Insider Trading"
    >
      <Suspense fallback={<div className="py-16 text-center text-sm text-slate-500 font-mono">載入中…</div>}>
        <InsiderDashboard />
      </Suspense>
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">
        資料來源：公開資訊觀測站「內部人持股異動事後申報表」與「董事、監察人、經理人及百分之十以上大股東股權異動彙總表」；股價為 Yahoo Finance 日收盤價。
        金額為股數乘以當月平均收盤價的估算值，並非實際成交金額。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
