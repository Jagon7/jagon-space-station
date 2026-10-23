import PageShell from "@/components/PageShell";
import ExdivDashboard from "@/components/strategy/ExdivDashboard";

export default function Page() {
  return (
    <PageShell title="除權息黑K" subtitle="高殖利率股除息後，自營商 swap 結束倒貨、股價常連續收黑：列出近兩週要除息的候選股、模擬持有中的部位，附 5 年回測。" badge="Ex-Dividend Fade">
      <ExdivDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：證交所／櫃買中心除權息預告與每日行情、期交所股票期貨標的清單、三大法人；回測使用 Yahoo Finance 日線與股利紀錄。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
