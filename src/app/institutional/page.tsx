import PageShell from "@/components/PageShell";
import InstitutionalDashboard from "@/components/chips/InstitutionalDashboard";

export default function Page() {
  return (
    <PageShell
      title="三大法人買賣超"
      subtitle="外資、投信、自營商每天買賣哪些股票：當日與 5／20／60 日累積、連續買超天數、土洋同買與對作，全市場法人每日進出金額。"
      badge="Institutional Investors"
    >
      <InstitutionalDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：臺灣證券交易所三大法人買賣超日報、證券櫃檯買賣中心三大法人買賣明細。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
