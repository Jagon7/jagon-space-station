import PageShell from "@/components/PageShell";
import IncomeDashboard from "@/components/fund/IncomeDashboard";

export default function Page() {
  return (
    <PageShell
      title="季報偵查"
      subtitle="最新一季財報的單季 EPS、毛利率、營益率、淨利率，找出三率三升、獲利大幅成長與轉虧為盈的公司。"
      badge="Quarterly Earnings"
    >
      <IncomeDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：公開資訊觀測站「綜合損益表彙總表」。財報申報期限：Q1 5/15、Q2 8/14、Q3 11/14、年報 3/31（金融業略晚）。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
