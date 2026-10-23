import PageShell from "@/components/PageShell";
import ShortDashboard from "@/components/market/ShortDashboard";

export default function Page() {
  return (
    <PageShell
      title="券差偵察"
      subtitle="融資融券與借券賣出餘額每日消長：融資維持率、融資使用率、券資比、回補天數，找出可能斷頭殺盤或被軋空的股票。"
      badge="Short Interest"
    >
      <ShortDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：臺灣證券交易所、證券櫃檯買賣中心融資融券餘額與信用額度總量管制餘額表（借券賣出）。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
