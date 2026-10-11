import PageShell from "@/components/PageShell";
import NextDayDashboard from "@/components/market/NextDayDashboard";

export default function Page() {
  return (
    <PageShell
      title="漲停隔日追蹤"
      subtitle="每天收盤漲停的股票，隔天開高還是開低、收紅還是收黑？依連板數、一字鎖、市場、成交值分組統計歷史勝率。"
      badge="Next-Day Tracker"
    >
      <NextDayDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：臺灣證券交易所、證券櫃檯買賣中心每日收盤行情。漲停由前一日收盤價推算，新上市股票、處置股等特殊情況可能有誤差。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
