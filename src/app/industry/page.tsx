import fs from "fs";
import path from "path";
import Link from "next/link";
import PageShell from "@/components/PageShell";
import IndustryDashboard, { type Industry, type Quotes } from "@/components/industry/IndustryDashboard";

function readJson<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", file), "utf-8")) as T;
  } catch {
    return null;
  }
}

export default function IndustryPage() {
  const chain = readJson<{ updatedAt: string; industries: Industry[]; names: Record<string, string> }>("industry/chain.json");
  const rankingDir = path.join(process.cwd(), "data", "ranking");
  const latest = fs.existsSync(rankingDir) ? fs.readdirSync(rankingDir).filter((f) => f.endsWith(".json")).sort().at(-1) : undefined;
  const day = latest ? readJson<{ date: string; rows: [string, string, string, number, number | null][] }>(`ranking/${latest}`) : null;

  const quotes: Quotes = {};
  if (chain && day) {
    const wanted = new Set(Object.keys(chain.names));
    for (const r of day.rows) if (wanted.has(r[0])) quotes[r[0]] = [r[1], r[4], r[3]];
  }

  return (
    <PageShell
      title="個股屬於哪些細產業"
      subtitle={`${chain?.industries.length ?? 0} 個產業，分上中下游與細類；用當日收盤看哪些細產業最強、最弱。`}
      badge="Industry Chain"
      back="/sectors"
    >
      <div className="mb-6 text-xs text-slate-500">
        官方類股的漲跌排行見 <Link href="/sectors" className="text-[#00d4aa] hover:underline">族群強弱</Link>。
      </div>
      {chain ? (
        <IndustryDashboard industries={chain.industries} quotes={quotes} names={chain.names} priceDate={day?.date ?? null} updatedAt={chain.updatedAt} />
      ) : (
        <div className="rounded-xl border border-dashed border-[#1e2a3a] py-12 text-center text-sm text-slate-500">產業分類資料尚未產生。</div>
      )}
    </PageShell>
  );
}
