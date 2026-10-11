import PageShell from "@/components/PageShell";
import ScreenerDashboard from "@/components/market/ScreenerDashboard";

export default function Page() {
  return (
    <PageShell
      title="技術選股"
      subtitle="站上月線／季線、多頭排列、爆量、突破整理、創新高新低：每天收盤後掃描所有上市櫃股票，訊號可以複選。"
      badge="Technical Screener"
    >
      <ScreenerDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">
        資料來源：臺灣證券交易所、證券櫃檯買賣中心每日收盤行情（約半年）。技術訊號僅為統計篩選，本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
