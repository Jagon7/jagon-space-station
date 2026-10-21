import PageShell from "@/components/PageShell";
import ReportsDashboard from "@/components/intel/ReportsDashboard";

export default function Page() {
  return (
    <PageShell title="券商研究報告" subtitle="外資與投顧最新報告的目標價、評等與重點，依時間排序；目標價與現價差距一眼看出潛在空間。" badge="Broker Research">
      <ReportsDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：鉅亨網台股新聞、Google 新聞彙整之媒體報導（經濟日報、工商時報、自由時報等），FactSet 共識取自鉅亨網 FactSet 快訊；股價為證交所／櫃買中心收盤價。報告內容為媒體轉述，以原始報告為準；本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
