import PageShell from "@/components/PageShell";
import BrokerDashboard from "@/components/broker/BrokerDashboard";

export default function BrokerPage() {
  return (
    <PageShell
      title="重點分點買賣超"
      subtitle="每天追蹤指定券商分點買賣了哪些股票，看單日與近 N 日的累積買超、賣超，以及個股在各分點的每日進出。"
      badge="Broker Branches"
    >
      <BrokerDashboard />
      <p className="mt-10 text-[11px] text-slate-600">
        資料來源：富邦證券網站分點進出明細（MoneyDJ），每個分點每日只列買超、賣超前 50 名。追蹤分點清單在 scripts/fetch_broker.py 的 BRANCHES。
        本頁資訊僅供參考，不構成任何投資建議。
      </p>
    </PageShell>
  );
}
