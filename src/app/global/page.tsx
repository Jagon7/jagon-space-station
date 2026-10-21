import PageShell from "@/components/PageShell";
import IntlDashboard from "@/components/intel/IntlDashboard";

export default function Page() {
  return (
    <PageShell title="國際類股連動" subtitle="美股類股、龍頭股與原物料前一晚的漲跌，對應到台股哪些股票開盤可能跟著反應。" badge="Global Linkage">
      <IntlDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：Yahoo Finance 美股、期貨與匯率日收盤；台股為證交所／櫃買中心收盤價。相關係數與 β 為歷史統計，僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
