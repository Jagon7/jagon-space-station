import Navbar from "@/components/Navbar";
import CommandCenter, { type Home as HomeData } from "@/components/home/CommandCenter";
import MarketSummaryCards from "@/components/MarketSummaryCards";
import EtfFlowCard from "@/components/EtfFlowCard";
import ResearchGrid from "@/components/ResearchGrid";
import Footer from "@/components/Footer";
import {
  getLimitUpStocks, getNoticeStocks,
  getDispositionStocks, getLastUpdated,
  getEtfFlow, getSectorPerformance, getHome,
} from "@/lib/data-loader";

export default async function Home() {
  const [stocks, notice, disposition, updatedAt, etfFlow, sectorPerf, home] =
    await Promise.all([
      getLimitUpStocks(), getNoticeStocks(),
      getDispositionStocks(), getLastUpdated(),
      getEtfFlow(), getSectorPerformance(), getHome<HomeData>(),
    ]);

  return (
    <>
      <Navbar />
      <main className="flex-1">
        {home && <CommandCenter h={home} />}
        <MarketSummaryCards
          stocks={stocks}
          sectorPerformance={sectorPerf}
          notice={notice}
          disposition={disposition}
          updatedAt={updatedAt}
        />
        {etfFlow && (
          <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <EtfFlowCard flow={etfFlow} />
            </div>
          </section>
        )}
        <ResearchGrid />
      </main>
      <Footer />
    </>
  );
}
