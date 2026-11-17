import PageShell from "@/components/PageShell";
import DaytradeReviewDashboard from "@/components/strategy/DaytradeReviewDashboard";

export default function Page() {
  return (
    <PageShell title="當沖復盤" subtitle="85g 開高走低、高週轉＋漲停、高當沖比＋開高走低三個當沖策略：每天推薦的標的收盤後逐檔檢討是否如預期，累積實績，並每週用最新資料回測修正參數。" badge="Day-Trade Review">
      <DaytradeReviewDashboard />
    </PageShell>
  );
}
