"use client";

import { useMemo, useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { Empty, Kpi, KpiRow, Note, Pills, SearchBox } from "@/components/data-ui";

type ExDiv = [string, string, string, string, string, number | null, number | null, number | null, number | null];
type Agm = [string, string, string, string, string, string];
type Conf = [string, string, string, string, string, string, string];
type Data = { updatedAt: string; exdiv: ExDiv[]; agm: Agm[]; conf: Conf[] };
type Kind = "all" | "exdiv" | "agm" | "conf";
type Range = "7" | "30" | "past";
type Ev = { date: string; kind: Exclude<Kind, "all">; code: string; name: string; mk: string; main: string; sub: string };

const KIND: Record<Ev["kind"], { label: string; cls: string }> = {
  exdiv: { label: "除權息", cls: "bg-[#f05252]/15 text-[#f05252]" },
  agm: { label: "股東會", cls: "bg-[#38bdf8]/15 text-[#60a5fa]" },
  conf: { label: "法說會", cls: "bg-[#a78bfa]/15 text-[#a78bfa]" },
};
const WD = ["日", "一", "二", "三", "四", "五", "六"];
const TODAY = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const addDays = (d: string, n: number) => new Date(Date.parse(d) + n * 86400e3).toISOString().slice(0, 10);

export default function EventsDashboard() {
  const { data, error } = useStaticJson<Data>("fund/events.json");
  const [kind, setKind] = useState<Kind>("all");
  const [range, setRange] = useState<Range>("30");
  const [only, setOnly] = useState<string | null>(null);

  const events = useMemo<Ev[]>(() => {
    if (!data) return [];
    const ev: Ev[] = [
      ...data.exdiv.map(([date, code, name, mk, k, cash, stock, price, yld]): Ev => ({
        date, kind: "exdiv", code, name, mk,
        main: [k.includes("息") || cash ? `現金 ${cash ?? "待公告"} 元` : "", stock ? `配股 ${Math.round(stock * 1000)} 股/張` : ""].filter(Boolean).join("・") || k,
        sub: yld ? `殖利率 ${yld}%（以收盤 ${price} 試算）` : "",
      })),
      ...data.agm.map(([date, code, name, mk, k, place]): Ev => ({ date, kind: "agm", code, name, mk, main: k || "股東會", sub: place })),
      ...data.conf.map(([date, code, name, mk, time, place, summary]): Ev => ({ date, kind: "conf", code, name, mk, main: `${time} ${place}`, sub: summary })),
    ];
    return ev.sort((a, b) => a.date.localeCompare(b.date) || a.kind.localeCompare(b.kind) || a.code.localeCompare(b.code));
  }, [data]);

  const shown = useMemo(() => {
    let ev = events;
    if (only) return ev.filter((e) => e.code === only);
    if (kind !== "all") ev = ev.filter((e) => e.kind === kind);
    if (range === "past") return ev.filter((e) => e.date < TODAY).reverse();
    return ev.filter((e) => e.date >= TODAY && e.date <= addDays(TODAY, Number(range)));
  }, [events, kind, range, only]);
  const byDate = useMemo(() => {
    const m = new Map<string, Ev[]>();
    for (const e of shown) m.set(e.date, [...(m.get(e.date) ?? []), e]);
    return [...m.entries()];
  }, [shown]);

  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const upcoming = events.filter((e) => e.date >= TODAY && e.date <= addDays(TODAY, 7));

  return (
    <div>
      <Note>
        近期會影響股價的公司事件：除權息（含現金股利與殖利率試算）、股東會、法人說明會。資料來自證交所、櫃買中心與公開資訊觀測站，每天更新；
        已過去的事件保留約 45 天。殖利率＝現金股利 ÷ 最新收盤價。
      </Note>
      <KpiRow>
        <Kpi label="未來 7 天事件" value={upcoming.length} unit="件" />
        <Kpi label="除權息" value={upcoming.filter((e) => e.kind === "exdiv").length} unit="家" color="text-[#f05252]" sub="7 天內" />
        <Kpi label="股東會" value={upcoming.filter((e) => e.kind === "agm").length} unit="家" color="text-[#60a5fa]" sub="7 天內" />
        <Kpi label="法說會" value={upcoming.filter((e) => e.kind === "conf").length} unit="家" color="text-[#a78bfa]" sub="7 天內" />
      </KpiRow>
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-4">
        <Pills<Kind> value={kind} onChange={(v) => { setKind(v); setOnly(null); }} options={[{ value: "all", label: "全部" }, { value: "exdiv", label: "除權息" }, { value: "agm", label: "股東會" }, { value: "conf", label: "法說會" }]} />
        <Pills<Range> value={range} onChange={(v) => { setRange(v); setOnly(null); }} options={[{ value: "7", label: "未來 7 天" }, { value: "30", label: "未來 30 天" }, { value: "past", label: "已過去" }]} />
        <div className="lg:ml-auto"><SearchBox placeholder="查公司的事件" items={[...new Map(events.map((e) => [e.code, { code: e.code, name: e.name }])).values()]} onPick={setOnly} /></div>
      </div>
      {only && <button onClick={() => setOnly(null)} className="mb-3 text-xs text-[#8b97ab] hover:text-[#4f8cff]">← 回到行事曆</button>}
      {!byDate.length ? <Empty>這段期間沒有事件。</Empty> : (
        <div className="space-y-4">
          {byDate.map(([d, evs]) => (
            <div key={d} className="rounded-xl border border-[#243247] bg-[#0d1220] overflow-hidden">
              <div className={`flex items-baseline gap-3 px-4 py-2.5 border-b border-[#243247] ${d === TODAY ? "bg-[#4f8cff]/10" : "bg-[#0a0f1a]"}`}>
                <span className="font-mono text-sm text-white">{Number(d.slice(5, 7))}/{Number(d.slice(8))}</span>
                <span className="text-xs text-[#8b97ab]">週{WD[new Date(`${d}T00:00:00Z`).getUTCDay()]}{d === TODAY ? "・今天" : ""}</span>
                <span className="ml-auto text-xs text-[#8b97ab]">{evs.length} 件</span>
              </div>
              <div className="divide-y divide-[#243247]/60">
                {evs.map((e, i) => (
                  <div key={i} className="grid grid-cols-[4rem_1fr] sm:grid-cols-[4.5rem_11rem_1fr] gap-x-3 gap-y-1 px-4 py-2.5 items-start">
                    <span className={`justify-self-start rounded px-1.5 py-0.5 text-[11px] ${KIND[e.kind].cls}`}>{KIND[e.kind].label}</span>
                    <span className="whitespace-nowrap">
                      <span className="text-slate-200">{e.name}</span><span className="ml-1.5 font-mono text-xs text-[#8b97ab]">{e.code}</span>
                      {e.mk === "上櫃" && <span className="ml-1 text-[10px] text-[#7c8aa0]">櫃</span>}
                    </span>
                    <div className="col-span-2 sm:col-span-1 min-w-0">
                      <div className="text-sm text-slate-300">{e.main}</div>
                      {e.sub && <div className="text-xs text-[#8b97ab] line-clamp-2" title={e.sub}>{e.sub}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
