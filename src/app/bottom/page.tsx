import PageShell from "@/components/PageShell";
import BottomDashboard from "@/components/strategy/BottomDashboard";

export default function Page() {
  return (
    <PageShell title="抄底雷達" subtitle="大跌之後什麼時候搶反彈比較安全：台股、美股、日股、韓股 2005 年以來的抄底訊號回測、跨市場止跌確認、用台指期／買權／個股期抄底的差別，以及現在的訊號狀態。" badge="Bottom Radar">
      <BottomDashboard />
    </PageShell>
  );
}
