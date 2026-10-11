import { Suspense } from "react";
import PageShell from "@/components/PageShell";
import StockSearch from "@/components/fund/StockSearch";

export default function Page() {
  return (
    <PageShell
      title="個股情報查詢"
      subtitle="輸入股號或名稱，一頁看完站內所有資料：月營收、季報、融資券與借券、ETF 持有、近期事件、內部人買賣與漲停紀錄。"
      badge="Stock Lookup"
    >
      <Suspense fallback={<div className="py-16 text-center text-sm text-slate-500 font-mono">載入中…</div>}>
        <StockSearch />
      </Suspense>
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">本頁資訊僅供參考，不構成任何投資建議。</p>
    </PageShell>
  );
}
