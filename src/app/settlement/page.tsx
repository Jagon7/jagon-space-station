import PageShell from "@/components/PageShell";
import SettlementDashboard from "@/components/strategy/SettlementDashboard";

export default function Page() {
  return (
    <PageShell title="結算策略" subtitle="每月股票期貨結算日前，用本期平均折溢價、自營商買賣超（套利庫存）與前十大特定法人期貨未平倉價值，推估哪些股票在結算日可能被控盤、往哪個方向。每天收盤後自動更新。" badge="Settlement Play">
      <SettlementDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：期交所大額交易人未沖銷部位、期貨每日行情、股票期貨標的清單；證交所／櫃買中心三大法人買賣超、每日收盤行情、現股當沖；永豐 Shioaji 歷史逐筆（只查行情）。推估值僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
