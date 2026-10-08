import { Suspense } from "react";
import PageShell from "@/components/PageShell";
import EtfDashboard from "@/components/etf/EtfDashboard";

export default function EtfHoldingsPage() {
  return (
    <PageShell
      title="ETF 怎麼換股，資金就怎麼流"
      subtitle="追蹤 90 檔台股 ETF（含主動式）每天公告的完整持股：查一檔股票被哪些 ETF 持有、前一份到最新一份哪些 ETF 買賣了哪些股票，或看全體上市櫃 ETF 的規模排行與資金流向。"
      badge="ETF Holdings"
    >
      <Suspense fallback={<div className="py-16 text-center text-sm text-slate-500 font-mono">載入中…</div>}>
        <EtfDashboard />
      </Suspense>
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">
        資料來源：各投信公告之 ETF 每日持股（PCF／投資組合）；ETF 規模為證交所 ETF 淨值揭露；股價為臺灣證券交易所、證券櫃檯買賣中心收盤行情。
        海外持股以股數表示、不估算金額。每個交易日自動更新，本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
