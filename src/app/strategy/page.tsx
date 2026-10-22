import PageShell from "@/components/PageShell";
import StrategyDashboard from "@/components/strategy/StrategyDashboard";

export default function Page() {
  return (
    <PageShell title="十日波段策略" subtitle="出量做多、輿情籌碼兩個波段策略：每天收盤後算出明天要進場的標的、持有中部位與到期出場，並推播到 LINE。" badge="Swing Strategies">
      <StrategyDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：證交所／櫃買中心每日行情、三大法人、處置股公告；鉅亨網台股新聞。策略定義來自使用者提供的研究報告，本站依公開資料重現，結果可能與原始回測不同。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
