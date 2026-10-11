import PageShell from "@/components/PageShell";
import AtmosphereDashboard from "@/components/market/AtmosphereDashboard";

export default function Page() {
  return (
    <PageShell
      title="市場氣氛評估"
      subtitle="每天收盤後把漲跌家數、漲跌停、站上月線比例、新高新低、量能、融資六個面向合成 0～100 的氣氛分數，看市場現在是過熱還是冰點。"
      badge="Market Atmosphere"
    >
      <AtmosphereDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">
        資料來源：臺灣證券交易所、證券櫃檯買賣中心每日收盤行情與融資融券餘額。分數是相對過去約半年的百分位，僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
