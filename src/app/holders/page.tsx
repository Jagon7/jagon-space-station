import PageShell from "@/components/PageShell";
import HoldersDashboard from "@/components/chips/HoldersDashboard";

export default function Page() {
  return (
    <PageShell
      title="大戶持股"
      subtitle="集保股權分散表：千張大戶與散戶持股比例、股東人數每週變化，找籌碼集中的股票。"
      badge="Major Shareholders"
    >
      <HoldersDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：臺灣集中保管結算所集保戶股權分散表（每週）。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
