"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { ActiveData, AumData, CoreData } from "./data";
import { useEtfJson } from "./data";
import HoldersTab from "./HoldersTab";
import ChangesTab from "./ChangesTab";
import ActiveTab from "./ActiveTab";
import AumTab from "./AumTab";
import ScheduleTab, { type ScheduleData } from "./ScheduleTab";

const TABS = [
  { key: "holders", label: "個股持有查詢" },
  { key: "changes", label: "每日持股變化" },
  { key: "active", label: "主動式買賣超" },
  { key: "aum", label: "AUM 排行" },
  { key: "schedule", label: "指數審核行事曆" },
] as const;
type Tab = (typeof TABS)[number]["key"];

function Loading({ error }: { error?: boolean }) {
  return (
    <div className="py-16 text-center text-sm text-slate-500 font-mono">
      {error ? "資料載入失敗，請稍後重新整理。" : "載入中…"}
    </div>
  );
}

export default function EtfDashboard() {
  const router = useRouter();
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "holders");
  const [stock, setStock] = useState(params.get("stock") ?? "");
  const [query, setQuery] = useState(params.get("q") ?? "");

  const core = useEtfJson<CoreData>("core.json");
  const active = useEtfJson<ActiveData>(tab === "active" ? "active.json" : null);
  const aum = useEtfJson<AumData>(tab === "aum" ? "aum.json" : null);
  const schedule = useEtfJson<ScheduleData>(tab === "schedule" ? "schedule.json" : null);

  // 沒指定時預設查被最多 ETF 持有的個股
  const defaultStock = useMemo(() => {
    if (!core.data) return "";
    const top = Object.entries(core.data.holders).sort((a, b) => b[1].length - a[1].length)[0];
    return top ? top[0] : "";
  }, [core.data]);

  const sync = useCallback((next: { tab?: Tab; stock?: string; q?: string }) => {
    const sp = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(next)) {
      if (v) sp.set(k, v); else sp.delete(k);
    }
    router.replace(`?${sp.toString()}`, { scroll: false });
  }, [router]);

  const go = (t: Tab) => { setTab(t); sync({ tab: t }); };
  const pickStock = (s: string) => { setStock(s); setTab("holders"); sync({ tab: "holders", stock: s }); };
  const pickQuery = (q: string) => { setQuery(q); sync({ q }); };
  const etfChanges = (code: string) => { setQuery(code); setTab("changes"); sync({ tab: "changes", q: code }); };

  return (
    <div>
      <div className="flex gap-1 sm:gap-6 border-b border-[#1e2a3a] mb-6 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => go(t.key)}
            className={`px-2 sm:px-0 pb-3 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors ${
              tab === t.key ? "border-[#00d4aa] text-white" : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {!core.data ? <Loading error={core.error} /> : (
        <>
          {tab === "holders" && <HoldersTab core={core.data} stock={stock || defaultStock} setStock={(s) => { setStock(s); sync({ stock: s }); }} />}
          {tab === "changes" && <ChangesTab core={core.data} query={query} setQuery={pickQuery} />}
          {tab === "active" && (active.data ? <ActiveTab core={core.data} active={active.data} onStock={pickStock} /> : <Loading error={active.error} />)}
          {tab === "aum" && (aum.data ? <AumTab aum={aum.data} onEtf={etfChanges} /> : <Loading error={aum.error} />)}
          {tab === "schedule" && (schedule.data ? <ScheduleTab data={schedule.data} onEtf={etfChanges} onStock={pickStock} /> : <Loading error={schedule.error} />)}
        </>
      )}
    </div>
  );
}
