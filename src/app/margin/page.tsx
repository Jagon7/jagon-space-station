import PageShell from "@/components/PageShell";
import MarginDashboard from "@/components/chips/MarginDashboard";

export default function Page() {
  return (
    <PageShell title="融資斷頭監控" subtitle="用證交所、櫃買中心每天公布的融資買進／賣出／償還，從 2021 年底逐日重播推估融資戶的平均成本，算出個股與大盤的推估融資維持率、追繳價，以及股價還要跌多少才碰到 130% 追繳線。" badge="Margin Call Watch">
      <MarginDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：證交所融資融券餘額（MI_MARGN）、櫃買中心融資融券餘額、每日收盤行情、Yahoo Finance 歷史收盤。推估值與券商實際計算（個別帳戶、整戶維持率、擔保品）會有差異，僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
