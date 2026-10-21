import PageShell from "@/components/PageShell";
import ConfDashboard from "@/components/intel/ConfDashboard";

export default function Page() {
  return (
    <PageShell title="法說會" subtitle="即將舉行的法說會行事曆，以及近期法說的營運重點、展望與問答摘要。" badge="Investor Conferences">
      <ConfDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：公開資訊觀測站法人說明會公告與簡報、鉅亨網法說會報導與 AI 摘要；股價為證交所／櫃買中心收盤價。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
