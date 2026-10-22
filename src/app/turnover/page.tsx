import PageShell from "@/components/PageShell";
import TurnoverDashboard from "@/components/strategy/TurnoverDashboard";

export default function Page() {
  return (
    <PageShell title="高週轉率黑K" subtitle="每天收盤後依週轉率（成交股數 ÷ 發行股數）排序全部上市櫃股票，並回測：週轉率越高，隔天是不是越容易開高走低、收黑K。" badge="Turnover Fade">
      <TurnoverDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：證交所／櫃買中心每日行情、上市櫃公司基本資料（已發行普通股數）、處置股公告。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
