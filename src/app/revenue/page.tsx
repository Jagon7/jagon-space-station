import PageShell from "@/components/PageShell";
import RevenueDashboard from "@/components/fund/RevenueDashboard";

export default function Page() {
  return (
    <PageShell
      title="月營收"
      subtitle="上市櫃公司每月營收：月增、年增、累計年增，營收創新高與連續成長的公司一次列出，點開看 3 年走勢。"
      badge="Monthly Revenue"
    >
      <RevenueDashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：公開資訊觀測站「每月營業收入彙總表」。每月 10 日前公布，本頁每天更新。本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
