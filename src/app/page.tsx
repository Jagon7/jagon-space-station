export const dynamic = "force-dynamic";

import Navbar from "@/components/Navbar";
import HeroSection from "@/components/HeroSection";
import MarketSummaryCards from "@/components/MarketSummaryCards";
import UpdateSchedule from "@/components/UpdateSchedule";
import ResearchGrid from "@/components/ResearchGrid";
import Footer from "@/components/Footer";
import {
  getLimitUpStocks, getMarketSummary, getNoticeStocks,
  getDispositionStocks, getAnnouncements, getSectors, getLastUpdated,
} from "@/lib/data-loader";

export default async function Home() {
  const [stocks, summary, notice, disposition, announcements, sectors, updatedAt] =
    await Promise.all([
      getLimitUpStocks(), getMarketSummary(), getNoticeStocks(),
      getDispositionStocks(), getAnnouncements(), getSectors(), getLastUpdated(),
    ]);

  return (
    <>
      <Navbar />
      <main className="flex-1">
        <HeroSection summary={summary} />
        <MarketSummaryCards
          stocks={stocks}
          sectors={sectors}
          notice={notice}
          disposition={disposition}
          announcements={announcements}
          updatedAt={updatedAt}
        />
        <UpdateSchedule />
        <ResearchGrid />
      </main>
      <Footer />
    </>
  );
}
