export const dynamic = "force-dynamic";

import PageShell from "@/components/PageShell";
import AnnouncementsFeed from "@/components/AnnouncementsFeed";
import { getAnnouncements, getLastUpdated } from "@/lib/data-loader";

export default async function AnnouncementsPage() {
  const [announcements, updatedAt] = await Promise.all([getAnnouncements(), getLastUpdated()]);
  const updatedTime = new Date(updatedAt).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });

  return (
    <PageShell
      title="情報截收站"
      subtitle={`已截收 ${announcements.length} 則公告 · 更新 ${updatedTime}`}
      badge="Intelligence Intercept"
    >
      <AnnouncementsFeed announcements={announcements} />
    </PageShell>
  );
}
