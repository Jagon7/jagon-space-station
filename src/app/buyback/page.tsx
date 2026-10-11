import PageShell from "@/components/PageShell";
import BuybackDashboard from "@/components/fund/BuybackDashboard";

export default function Page() {
  return (
    <PageShell
      title="庫藏股"
      subtitle="公司買回自家股票的決議、價格區間與執行進度，看哪些公司在護盤、現價是否低於買回區間。"
      badge="Treasury Stock"
    >
      <BuybackDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">
        資料來源：公開資訊觀測站「上市（櫃）公司買回自己公司股份彙總統計表」。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
