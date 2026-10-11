import PageShell from "@/components/PageShell";
import FuturesDashboard from "@/components/chips/FuturesDashboard";

export default function Page() {
  return (
    <PageShell
      title="期貨選擇權籌碼"
      subtitle="外資台指期多空部位、散戶小台多空比、臺指選擇權 Put/Call 比與外資選擇權部位，看大盤多空氣氛。"
      badge="Futures & Options"
    >
      <FuturesDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：臺灣期貨交易所三大法人交易資訊、Put/Call 比、期貨每日交易行情。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
