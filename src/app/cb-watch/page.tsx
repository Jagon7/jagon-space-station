import fs from "fs";
import path from "path";
import PageShell from "@/components/PageShell";
import CbDashboard, { type CbCase, type CbPre } from "@/components/cb/CbDashboard";

function readJson<T>(file: string, fallback: T): T {
  try {
    return JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", file), "utf-8")) as T;
  } catch {
    return fallback;
  }
}

// 靜態輸出：建置當天（台北）
const BUILD_DATE = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);

export default function CbWatchPage() {
  const doc = readJson<{ updatedAt: string | null; cases: CbCase[]; pre: CbPre[] }>("cb/cases.json", { updatedAt: null, cases: [], pre: [] });
  const priceDoc = readJson<{ days: Record<string, Record<string, number>> }>("etf/prices.json", { days: {} });
  const latest = Object.keys(priceDoc.days).sort().at(-1);
  const codes = new Set(doc.cases.map((c) => c.code).filter(Boolean) as string[]);
  const prices = Object.fromEntries(Object.entries(latest ? priceDoc.days[latest] : {}).filter(([c]) => codes.has(c)));

  return (
    <PageShell
      title="可轉債從圈購到掛牌"
      subtitle="把每檔可轉債（CB／EB）的詢圈、競拍、訂價與掛牌日排在同一條時間軸上，往前追到金管會申報中的案件。"
      badge="CB Watch"
    >
      <CbDashboard cases={doc.cases} pre={doc.pre} prices={prices} updatedAt={doc.updatedAt} buildDate={BUILD_DATE} />
    </PageShell>
  );
}
