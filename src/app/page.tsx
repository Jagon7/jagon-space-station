export const dynamic = "force-dynamic";

import Navbar from "@/components/Navbar";
import HeroSection from "@/components/HeroSection";
import MarketSummaryCards from "@/components/MarketSummaryCards";
import EtfFlowCard from "@/components/EtfFlowCard";
import UpdateSchedule from "@/components/UpdateSchedule";
import ResearchGrid from "@/components/ResearchGrid";
import Footer from "@/components/Footer";
import {
  getLimitUpStocks, getMarketSummary, getNoticeStocks,
  getDispositionStocks, getAnnouncements, getSectors, getLastUpdated,
  getEtfFlow,
} from "@/lib/data-loader";

export default async function Home() {
  const [stocks, summary, notice, disposition, announcements, sectors, updatedAt, etfFlow] =
    await Promise.all([
      getLimitUpStocks(), getMarketSummary(), getNoticeStocks(),
      getDispositionStocks(), getAnnouncements(), getSectors(), getLastUpdated(),
      getEtfFlow(),
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
        {etfFlow && (
          <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <EtfFlowCard flow={etfFlow} />
            </div>
          </section>
        )}
        <UpdateSchedule />
        <ResearchGrid />
      </main>
      <Footer />
    </>
  );
}
