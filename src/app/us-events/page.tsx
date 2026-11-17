import PageShell from "@/components/PageShell";
import UsEventsDashboard from "@/components/intel/UsEventsDashboard";

export default function Page() {
  return (
    <PageShell title="美國事件夜盤" subtitle="CPI、PPI、非農、FOMC、PCE、零售銷售、GDP、ISM 公布前後，台指期夜盤的 1 分鐘走勢：歷次平均、高於／低於預期分開比較，以及每一次的實際反應。" badge="US Events × TX Night">
      <UsEventsDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：TradingView 經濟行事曆、期交所期貨每筆成交資料、永豐 Shioaji 1 分 K（只查行情）。歷史走勢不代表未來，僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
