import fs from "fs";
import path from "path";
import PageShell from "@/components/PageShell";

type Level = "ok" | "warn" | "error";
type Check = { name: string; source: string; date: string | null; detail: string; level: Level; note?: string };

const DATA = path.join(process.cwd(), "data");

function read<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(path.join(DATA, file), "utf-8")) as T;
  } catch {
    return null;
  }
}

/** 兩個日期之間相差幾個平日（不含假日表，週末略過） */
function weekdaysBetween(from: string, to: string): number {
  let n = 0;
  const d = new Date(`${from}T00:00:00Z`);
  const end = new Date(`${to}T00:00:00Z`);
  while (d < end) {
    d.setUTCDate(d.getUTCDate() + 1);
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) n++;
  }
  return n;
}

function level(date: string | null, ref: string, count: number | null, tolerance = 0): Level {
  if (!date || count === 0) return "error";
  const lag = weekdaysBetween(date.slice(0, 10), ref);
  return lag <= tolerance ? "ok" : lag <= tolerance + 2 ? "warn" : "error";
}

const DOT: Record<Level, string> = { ok: "bg-[#00d4aa]", warn: "bg-[#f59e0b]", error: "bg-[#ef4444]" };
const LABEL: Record<Level, string> = { ok: "正常", warn: "延遲", error: "異常" };

function buildChecks() {
  const rankingDir = path.join(DATA, "ranking");
  const rankingDates = fs.existsSync(rankingDir) ? fs.readdirSync(rankingDir).map((f) => f.replace(".json", "")).sort() : [];
  const prices = read<{ days: Record<string, Record<string, number>> }>("etf/prices.json");
  const priceDates = Object.keys(prices?.days ?? {}).sort();
  // 最新交易日：以收盤行情的日期為準
  const ref = [rankingDates.at(-1), priceDates.at(-1)].filter(Boolean).sort().at(-1) ?? "";

  const daily: [string, string, string][] = [
    ["limit-up.json", "漲停訊號", "證交所、櫃買中心當日行情"],
    ["sector-stocks.json", "族群個股", "證交所、櫃買中心當日行情"],
    ["sector-performance.json", "族群強弱", "證交所類股指數"],
    ["market-summary.json", "大盤統計", "證交所"],
    ["notice.json", "注意股", "證交所、櫃買中心公告"],
    ["disposition.json", "處置股", "證交所、櫃買中心公告"],
    ["announcements.json", "重大訊息", "公開資訊觀測站"],
    ["cb-watch.json", "CB 詢圈（舊版清單）", "證券商業同業公會"],
    ["sfb-cb.json", "CB 申報案件", "金管會證期局"],
  ];
  const checks: Check[] = daily.map(([file, name, source]) => {
    const d = read<{ date?: string; data?: unknown }>(file);
    const items = d?.data;
    const count = Array.isArray(items) ? items.length : items && typeof items === "object" ? Object.keys(items).length : null;
    const tol = file === "sfb-cb.json" ? 3 : 0;
    return { name, source, date: d?.date ?? null, detail: count == null ? "—" : `${count.toLocaleString()} 筆`, level: level(d?.date ?? null, ref, count, tol) };
  });

  const aum = read<{ days: Record<string, Record<string, unknown>> }>("etf/aum.json");
  const aumDates = Object.keys(aum?.days ?? {}).sort();
  const cb = read<{ updatedAt: string; cases: unknown[] }>("cb/cases.json");
  const ind = read<{ updatedAt: string; industries: unknown[] }>("industry/chain.json");
  const sched = read<{ updatedAt: string; rows: unknown[] }>("etf/index_schedule.json");
  const latestRanking = rankingDates.length ? read<{ rows: unknown[] }>(`ranking/${rankingDates.at(-1)}.json`) : null;

  checks.push(
    { name: "成交排行", source: "證交所、櫃買中心當日行情", date: rankingDates.at(-1) ?? null, detail: `${latestRanking?.rows.length ?? 0} 檔・累積 ${rankingDates.length} 天`, level: level(rankingDates.at(-1) ?? null, ref, latestRanking?.rows.length ?? 0) },
    { name: "ETF 收盤價", source: "證交所、櫃買中心當日行情", date: priceDates.at(-1) ?? null, detail: `累積 ${priceDates.length} 天`, level: level(priceDates.at(-1) ?? null, ref, priceDates.length) },
    { name: "ETF 規模（AUM）", source: "證交所 ETF 淨值揭露", date: aumDates.at(-1) ?? null, detail: `${Object.keys(aum?.days?.[aumDates.at(-1) ?? ""] ?? {}).length} 檔・累積 ${aumDates.length} 天`, level: level(aumDates.at(-1) ?? null, ref, aumDates.length) },
    { name: "CB 時間軸", source: "證券商業同業公會、櫃買中心、金管會", date: cb?.updatedAt?.slice(0, 10) ?? null, detail: `${cb?.cases.length ?? 0} 件`, level: level(cb?.updatedAt ?? null, ref, cb?.cases.length ?? 0, 1) },
    { name: "指數審核日程", source: "臺灣指數公司、MSCI", date: sched?.updatedAt?.slice(0, 10) ?? null, detail: `${sched?.rows.length ?? 0} 筆`, level: level(sched?.updatedAt ?? null, ref, sched?.rows.length ?? 0, 5) },
    { name: "產業細分類", source: "櫃買中心產業價值鏈平台（每週一更新）", date: ind?.updatedAt ?? null, detail: `${ind?.industries.length ?? 0} 個產業`, level: level(ind?.updatedAt ?? null, ref, ind?.industries.length ?? 0, 7) },
  );

  // ── ETF 持股：逐檔 ──────────────────────────────────────
  type Status = { ok: boolean; date?: string; n?: number; error?: string | null; lastOk?: string };
  const status = read<{ updatedAt: string; etfs: Record<string, Status> }>("etf/status.json");
  const holdingsDir = path.join(DATA, "etf", "holdings");
  const etfs = fs.existsSync(holdingsDir)
    ? fs.readdirSync(holdingsDir).map((f) => {
        const doc = read<{ code: string; name: string; issuer: string; snapshots: { date: string }[] }>(`etf/holdings/${f}`)!;
        const st = status?.etfs[doc.code];
        const date = doc.snapshots.at(-1)?.date ?? null;
        // 各投信公告進度不同，落後一個交易日屬正常
        const lv: Level = st && !st.ok ? (level(date, ref, 1, 1) === "ok" ? "warn" : "error") : level(date, ref, 1, 1);
        return { code: doc.code, name: doc.name, issuer: doc.issuer, date, hist: doc.snapshots.length, n: st?.n, error: st?.ok === false ? st.error : null, level: lv };
      }).sort((a, b) => (a.level === b.level ? a.issuer.localeCompare(b.issuer) : a.level === "error" ? -1 : b.level === "error" ? 1 : a.level === "warn" ? -1 : 1))
    : [];

  return { ref, checks, etfs, etfCheckedAt: status?.updatedAt ?? null };
}

export default function HealthPage() {
  const { ref, checks, etfs, etfCheckedAt } = buildChecks();
  const count = (lv: Level) => checks.filter((c) => c.level === lv).length + etfs.filter((e) => e.level === lv).length;

  return (
    <PageShell
      title="資料健檢"
      subtitle={`以最新交易日 ${ref || "—"} 為基準，檢查每個資料來源有沒有按時更新。網站在每次排程抓取後重新產生。`}
      badge="Data Health"
    >
      <div className="grid grid-cols-3 gap-3 mb-8">
        {(["ok", "warn", "error"] as Level[]).map((lv) => (
          <div key={lv} className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] p-4">
            <div className="flex items-center gap-2 text-xs text-slate-500"><span className={`w-2 h-2 rounded-full ${DOT[lv]}`} />{LABEL[lv]}</div>
            <div className="font-mono text-2xl font-bold text-white mt-1">{count(lv)}</div>
          </div>
        ))}
      </div>

      <h2 className="text-base font-semibold text-white mb-3">資料來源</h2>
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-x-auto mb-10">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500 text-left">
              <th className="px-4 py-3 font-normal">狀態</th><th className="px-4 py-3 font-normal">資料</th>
              <th className="px-4 py-3 font-normal">來源</th><th className="px-4 py-3 font-normal text-right">資料日期</th>
              <th className="px-4 py-3 font-normal text-right">內容</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((c) => (
              <tr key={c.name} className="border-b border-[#1e2a3a]/60 last:border-0">
                <td className="px-4 py-2.5 whitespace-nowrap"><span className="inline-flex items-center gap-2 text-xs text-slate-400"><span className={`w-2 h-2 rounded-full ${DOT[c.level]}`} />{LABEL[c.level]}</span></td>
                <td className="px-4 py-2.5 text-slate-200 whitespace-nowrap">{c.name}</td>
                <td className="px-4 py-2.5 text-xs text-slate-500">{c.source}</td>
                <td className="px-4 py-2.5 text-right font-mono text-slate-300 whitespace-nowrap">{c.date ?? "—"}</td>
                <td className="px-4 py-2.5 text-right font-mono text-slate-400 whitespace-nowrap">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="text-base font-semibold text-white mb-1">ETF 持股（{etfs.length} 檔）</h2>
      <p className="text-xs text-slate-500 mb-3">
        各投信公告進度不同，資料日落後最新交易日一天屬正常。{etfCheckedAt && `最近一次抓取 ${etfCheckedAt.replace("T", " ").slice(0, 16)}。`}
      </p>
      <div className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e2a3a] text-[11px] text-slate-500 text-left">
              <th className="px-4 py-3 font-normal">狀態</th><th className="px-4 py-3 font-normal">ETF</th>
              <th className="px-4 py-3 font-normal">投信</th><th className="px-4 py-3 font-normal text-right">資料日</th>
              <th className="px-4 py-3 font-normal text-right">持股檔數</th><th className="px-4 py-3 font-normal text-right">歷史份數</th>
              <th className="px-4 py-3 font-normal">最近錯誤</th>
            </tr>
          </thead>
          <tbody>
            {etfs.map((e) => (
              <tr key={e.code} className="border-b border-[#1e2a3a]/60 last:border-0">
                <td className="px-4 py-2 whitespace-nowrap"><span className={`inline-block w-2 h-2 rounded-full ${DOT[e.level]}`} /></td>
                <td className="px-4 py-2 whitespace-nowrap"><span className="text-slate-200">{e.name}</span> <span className="font-mono text-xs text-slate-500">{e.code}</span></td>
                <td className="px-4 py-2 text-xs text-slate-400 whitespace-nowrap">{e.issuer}</td>
                <td className="px-4 py-2 text-right font-mono text-slate-300">{e.date ?? "—"}</td>
                <td className="px-4 py-2 text-right font-mono text-slate-400">{e.n ?? "—"}</td>
                <td className="px-4 py-2 text-right font-mono text-slate-400">{e.hist}</td>
                <td className="px-4 py-2 text-xs text-[#ef4444]/80 max-w-xs truncate" title={e.error ?? ""}>{e.error ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}
