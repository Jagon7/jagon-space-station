import PageShell from "@/components/PageShell";
import ActiveStopDashboard from "@/components/etf/ActiveStopDashboard";

export default function Page() {
  return (
    <PageShell title="主動ETF停損監控" subtitle="逐日追蹤每檔主動式 ETF 從掛牌起的持股增減，回推每個部位的建倉日、建倉價與平均成本，對照最新收盤算出 DD，找出接近 -40% 停損線、可能被投信陸續賣出的個股。" badge="Active ETF Stop-Loss">
      <ActiveStopDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：各投信網站公布的主動式 ETF 每日持股、證交所／櫃買中心每日收盤、Yahoo Finance 歷史收盤。成本為推估值，投信實際停損規則不公開，僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
