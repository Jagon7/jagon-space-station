import PageShell from "@/components/PageShell";
import EventsDashboard from "@/components/fund/EventsDashboard";

export default function Page() {
  return (
    <PageShell
      title="重大事件"
      subtitle="除權息、股東會、法人說明會行事曆：未來 30 天哪些公司有事件，現金股利與殖利率試算。"
      badge="Corporate Events"
    >
      <EventsDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-slate-600">
        資料來源：證交所與櫃買中心除權除息預告表、股東會公告，公開資訊觀測站法人說明會一覽表。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
