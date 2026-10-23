import PageShell from "@/components/PageShell";
import RiskDashboard from "@/components/intel/RiskDashboard";

export default function Page() {
  return (
    <PageShell title="市場風險監控" subtitle="VIX、VVIX、期限結構、債市波動、信用利差（CDS 替代）、金融壓力與美元，整合成一個風險溫度，搭配台股期權籌碼。" badge="Risk Monitor">
      <RiskDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：Yahoo Finance（Cboe VIX／VVIX／VIX9D／VIX3M／SKEW、ICE BofA MOVE、美元指數）、FRED 聖路易聯準銀行（ICE BofA 公司債利差、10Y−2Y、金融壓力指數）、期交所。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
