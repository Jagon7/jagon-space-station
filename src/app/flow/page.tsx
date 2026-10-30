import PageShell from "@/components/PageShell";
import FlowDashboard from "@/components/flow/FlowDashboard";

export default function Page() {
  return (
    <PageShell title="即時資金流" subtitle="盤中每分鐘更新：成交金額前 200 大個股的逐筆成交，依內外盤分成主動買（外盤）與主動賣（內盤），按產業彙整主動買賣淨額，並每 15 分鐘切片看資金往哪裡移動。" badge="Live Money Flow">
      <FlowDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：永豐金證券 Shioaji 即時行情（逐筆成交內外盤）。只涵蓋前一交易日成交金額前 200 名（約占市場成交九成），延遲約 1 分鐘。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
