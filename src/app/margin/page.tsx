import PageShell from "@/components/PageShell";
import MarginDashboard from "@/components/chips/MarginDashboard";
import MarginFlowDashboard from "@/components/chips/MarginFlowDashboard";

export default function Page() {
  return (
    <PageShell title="融資融券" subtitle="每日融資餘額增減、融資水位與使用率、個股融資融券增減排行；用證交所、櫃買中心每天公布的融資買進／賣出／償還，從 2021 年底逐日重播推估融資戶的平均成本，再用官方公布的融資金額校正，算出個股推估融資維持率、大盤融資維持率、追繳價，以及股價還要跌多少才碰到 130% 追繳線。" badge="Margin Call Watch">
      <MarginFlowDashboard />
      <h2 className="mt-12 mb-4 text-base font-semibold text-white">融資維持率與斷頭監控</h2>
      <MarginDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：證交所融資融券餘額（MI_MARGN）、櫃買中心融資融券餘額、每日收盤行情、Yahoo Finance 歷史收盤。推估值與券商實際計算（個別帳戶、整戶維持率、擔保品）會有差異，僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
