import PageShell from "@/components/PageShell";
import SelfReportDashboard from "@/components/fund/SelfReportDashboard";

export default function Page() {
  return (
    <PageShell
      title="自結盈餘"
      subtitle="公司在正式財報前主動公告的每月／每季自結損益，最早看到獲利變化的地方。"
      badge="Self-reported Earnings"
    >
      <SelfReportDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：公開資訊觀測站「公告自結損益彙總表」。自結數字未經會計師查核，以正式財報為準。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
