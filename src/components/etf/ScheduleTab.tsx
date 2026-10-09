"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import { Empty, Kpi, KpiRow, Note, Pills } from "@/components/data-ui";

// etfs: [code, name, aum, tracked]
type Row = {
  index: string; provider: string; announce: string; effective: string; etfs: [string, string, number, boolean][];
  add?: [string, string][]; del?: [string, string][];  // 已公告的定審結果：[代號, 名稱]
};
export type ScheduleData = { updatedAt: string | null; rows: Row[] };
type When = "upcoming" | "past";
type Prov = "all" | "臺灣指數公司" | "MSCI";

const WEEK = "日一二三四五六";
const noop = () => () => {};
const todayTpe = () => new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
const days = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 864e5);
const fmtDate = (d: string) => `${d.replaceAll("-", "/")}（${WEEK[new Date(`${d}T00:00:00Z`).getUTCDay()]}）`;
const short = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const yi = (v: number) => (v >= 1e12 ? `${(v / 1e12).toFixed(2)}兆` : `${Math.round(v / 1e8).toLocaleString()}億`);

function Changes({ r, onStock }: { r: Row; onStock: (code: string) => void }) {
  if (!r.add) return null;
  if (!r.add.length && !r.del?.length) return <div className="mt-2 text-[11px] text-slate-500">定審結果：成分股無異動</div>;
  const list = (label: string, xs: [string, string][], cls: string) => xs.length > 0 && (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs">
      <span className={`shrink-0 ${cls}`}>{label}（{xs.length}）</span>
      {xs.map(([code, name]) => (
        <button key={code} onClick={() => onStock(code)} className="text-slate-300 hover:text-[#00d4aa]">
          {name}<span className="font-mono text-slate-500 ml-0.5">{code}</span>
        </button>
      ))}
    </div>
  );
  return (
    <div className="mt-2 space-y-1">
      {list("納入", r.add, "text-[#ef4444]")}
      {list("刪除", r.del ?? [], "text-[#22c55e]")}
    </div>
  );
}

export default function ScheduleTab({ data, onEtf, onStock }: { data: ScheduleData; onEtf: (code: string) => void; onStock: (code: string) => void }) {
  const today = useSyncExternalStore(noop, todayTpe, () => "");
  const [when, setWhen] = useState<When>("upcoming");
  const [prov, setProv] = useState<Prov>("all");
  const [onlyEtf, setOnlyEtf] = useState(true);

  const rows = useMemo(
    () => data.rows.filter((r) => (prov === "all" || r.provider === prov) && (!onlyEtf || r.etfs.length)),
    [data, prov, onlyEtf],
  );
  if (!today) return null;
  const upcoming = rows.filter((r) => r.announce >= today);
  const past = rows.filter((r) => r.announce < today).reverse();
  const nextAnn = upcoming[0]?.announce;
  const nextEff = rows.filter((r) => r.effective >= today).map((r) => r.effective).sort()[0];
  const in30 = rows.filter((r) => r.announce >= today && days(today, r.announce) <= 30);

  const groups = new Map<string, Row[]>();
  for (const r of when === "upcoming" ? upcoming : past) groups.set(r.announce, [...(groups.get(r.announce) ?? []), r]);

  return (
    <div>
      <Note>
        臺灣指數公司每月公布的「指數定期審核日程表」，加上 MSCI 季度審核：各指數在哪一天收盤後公告成分股調整結果、哪一天生效，以及追蹤該指數的 ETF；
        已公告的臺灣指數公司定審會列出成分股納入、刪除名單（點股票可查哪些 ETF 持有）。
        被動式 ETF 通常在生效日前後幾天內完成換股，公告到生效之間是觀察資金進出的時間窗。追蹤 ETF 依證交所 ETF 基本資料的標的指數比對（上櫃 ETF 可能對不到）。
      </Note>
      <KpiRow>
        <Kpi label="下一個公告日" value={nextAnn ? short(nextAnn) : "—"} sub={nextAnn ? `${days(today, nextAnn)} 天後・${upcoming.filter((r) => r.announce === nextAnn).length} 個指數` : undefined} />
        <Kpi label="下一個生效日" value={nextEff ? short(nextEff) : "—"} sub={nextEff ? `${days(today, nextEff)} 天後` : undefined} />
        <Kpi label="30 天內審核" value={in30.length} unit="個指數" sub={`· ${new Set(in30.flatMap((r) => r.etfs.map((e) => e[0]))).size} 檔 ETF`} />
        <Kpi label="日程表更新" value={data.updatedAt ? short(data.updatedAt.slice(0, 10)) : "—"} />
      </KpiRow>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <Pills<When> value={when} onChange={setWhen} options={[{ value: "upcoming", label: "即將公告" }, { value: "past", label: "已公告" }]} />
        <Pills<Prov> value={prov} onChange={setProv} options={[{ value: "all", label: "全部" }, { value: "臺灣指數公司", label: "臺灣指數公司" }, { value: "MSCI", label: "MSCI" }]} />
        <label className="inline-flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
          <input type="checkbox" checked={onlyEtf} onChange={(e) => setOnlyEtf(e.target.checked)} className="accent-[#00d4aa]" />
          只看有 ETF 追蹤的指數
        </label>
      </div>

      {groups.size === 0 ? <Empty>沒有符合條件的審核。</Empty> : (
        <div className="space-y-4">
          {[...groups.entries()].map(([d, rs]) => {
            const eff = [...new Set(rs.map((r) => r.effective))];
            const n = days(today, d);
            return (
              <div key={d} className="rounded-xl border border-[#1e2a3a] bg-[#0d1220] overflow-hidden">
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-5 py-3 border-b border-[#1e2a3a]">
                  <span className="font-mono text-white">{fmtDate(d)} 收盤後公告</span>
                  <span className="text-xs text-slate-500">生效日 {eff.map(fmtDate).join("、")}</span>
                  <span className={`ml-auto text-xs font-mono ${n >= 0 ? "text-[#00d4aa]" : "text-slate-500"}`}>{n === 0 ? "今天" : n > 0 ? `${n} 天後` : `${-n} 天前`}</span>
                </div>
                {rs.map((r) => (
                  <div key={r.index + r.announce} className="px-5 py-3 border-b border-[#1e2a3a]/50 last:border-0">
                    <div className="flex items-center gap-2 text-sm text-slate-200">
                      {r.index}
                      <span className="text-[10px] px-1.5 rounded border border-slate-700 text-slate-500">{r.provider}</span>
                    </div>
                    <Changes r={r} onStock={onStock} />
                    {r.etfs.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {r.etfs.map(([code, name, aum, tracked]) => (
                          <button
                            key={code}
                            disabled={!tracked}
                            onClick={() => onEtf(code)}
                            title={tracked ? "查看持股變化" : "此 ETF 未追蹤持股"}
                            className={`text-[11px] px-2 py-0.5 rounded border ${tracked ? "border-[#00d4aa]/40 text-slate-200 hover:bg-[#00d4aa]/10" : "border-[#1e2a3a] text-slate-500 cursor-default"}`}
                          >
                            <span className="font-mono">{code}</span> {name}{aum > 0 && <span className="text-slate-500"> · {yi(aum)}</span>}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
