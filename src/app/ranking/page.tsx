import PageShell from "@/components/PageShell";
import RankingDashboard from "@/components/ranking/RankingDashboard";

export default function RankingPage() {
  return (
    <PageShell
      title="今天的錢，流向哪裡"
      subtitle="依當日成交金額排序上市、上櫃個股與 ETF。成交金額集中在哪幾檔，往往比漲跌幅更早說明市場的注意力在哪裡。"
      badge="Turnover Ranking"
    >
      <RankingDashboard />
      <p className="mt-10 text-[11px] text-slate-600">
        資料來源：臺灣證券交易所、證券櫃檯買賣中心每日收盤行情；族群分類同族群強弱頁。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
