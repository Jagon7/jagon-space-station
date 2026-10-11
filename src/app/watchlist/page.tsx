import PageShell from "@/components/PageShell";
import WatchlistDashboard from "@/components/fund/WatchlistDashboard";

export default function Page() {
  return (
    <PageShell
      title="自選股"
      subtitle="把常看的股票加入清單，每天一頁看完它們在全站觸發的訊號：技術、法人、融資券、營收、內部人、ETF、大戶、事件。"
      badge="Watchlist"
    >
      <WatchlistDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">訊號為各頁資料的自動彙整，本頁資訊僅供參考，不構成任何投資建議。</p>
    </PageShell>
  );
}
