"use client";

import { useState } from "react";
import { useStaticJson } from "@/lib/static-json";
import { Kpi, KpiRow, Note, Pills } from "@/components/data-ui";

type Res = { code: string; name: string; ref: number; open?: number; high?: number; close?: number; gap?: number; trig?: boolean; ret?: number; net?: number; mae?: number; status?: string };
type Live = { days: number; n: number; avg: number | null; win: number | null; sum: number | null };
type Ev = { n: number; days?: number; net?: number; win?: number; h1?: number | null; h2?: number | null };
type Data = {
  updatedAt: string; names: Record<string, string>; cost: number; params: Record<string, Record<string, number>>; tunedAt: string | null;
  eval: Record<string, { current: Ev; best: Ev; tried: number; from: string; to: string }>;
  history: { date: string; strategy: string; from: Record<string, number>; to: Record<string, number>; reason: string }[];
  live: Record<string, Record<string, Live>>;
  days: { date: string; sim: boolean; picks: Record<string, Res[]>; result?: Record<string, Res[]>; params?: Record<string, Record<string, number>> }[];
};

const KEYS = ["g85", "tvLimit", "dtFade"];
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
// 空單損益：賺＝紅（台股慣例紅賺）
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-[#8b97ab]" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`;
const PNAME: Record<string, string> = { top: "前幾名", gapLo: "開高下限%", gapHi: "開高上限%", run5: "5 日漲幅%", minVal: "成交≥億", dtMin: "當沖比≥%", minRet: "當天漲跌≥%", gapMin: "隔天開盤≥%", gapMax: "開高上限%" };
const pv = (k: string, v: number) => ((k === "gapMin" && v <= -99) || (k === "gapMax" && v >= 99) || v == null ? "不限" : String(v));

export default function DaytradeReviewDashboard() {
  const { data, error } = useStaticJson<Data>("daytrade-review.json");
  const [win, setWin] = useState<"5" | "20" | "60">("20");
  if (!data) return <div className="py-16 text-center text-sm text-[#8b97ab] font-mono">{error ? "資料載入失敗" : "載入中…"}</div>;
  const today = data.days.find((d) => d.result);

  return (
    <div>
      <KpiRow>
        {KEYS.map((k) => {
          const l = data.live[k]?.[win];
          return <Kpi key={k} label={`${data.names[k]}（近 ${win} 日）`} value={pct(l?.avg)} color={tone(l?.avg)}
            sub={l?.n ? `${l.n} 筆・勝率 ${l.win?.toFixed(0)}%・累計 ${pct(l.sum, 1)}` : "還沒有紀錄"} />;
        })}
        <Kpi label="最近調參" value={data.history[0] ? md(data.history[0].date) : "—"} sub={data.tunedAt ? `上次檢討 ${md(data.tunedAt.slice(0, 10))}（每週六）` : "尚未檢討"} />
      </KpiRow>
      <div className="mb-4 flex items-center gap-3">
        <Pills<"5" | "20" | "60"> value={win} onChange={setWin} options={[{ value: "5", label: "近 5 日" }, { value: "20", label: "近 20 日" }, { value: "60", label: "近 60 日" }]} />
        <span className="text-[11px] text-[#7c8aa0]">每筆＝放空開盤價、收盤回補，扣成本 {data.cost}%（證交稅 0.15%＋手續費 2.8 折）</span>
      </div>

      <section className="mb-6 grid gap-4 lg:grid-cols-3">
        {KEYS.map((k) => {
          const e = data.eval[k];
          return (
            <div key={k} className="rounded-xl border border-[#243247] bg-[#0d1220] p-4">
              <div className="text-sm font-semibold text-white mb-2">{data.names[k]}：目前參數</div>
              <div className="flex flex-wrap gap-1.5 mb-3">{Object.entries(data.params[k] ?? {}).map(([pk, v]) => (
                <span key={pk} className="rounded bg-[#141c2e] px-2 py-0.5 text-xs"><span className="text-[#8b97ab]">{PNAME[pk] ?? pk}</span> <span className="font-mono text-slate-200">{pv(pk, v)}</span></span>))}</div>
              {e && <div className="text-[11px] leading-relaxed text-[#8b97ab]">
                回測 {md(e.from)}～{md(e.to)}：{e.current.n} 筆、平均淨 <span className={`font-mono ${tone(e.current.net)}`}>{pct(e.current.net)}</span>、勝率 {e.current.win}%；
                前／後半段 <span className="font-mono">{pct(e.current.h1)}／{pct(e.current.h2)}</span>（試了 {e.tried} 組參數）
              </div>}
            </div>
          );
        })}
      </section>

      {!!data.history.length && (
        <section className="mb-6 rounded-xl border border-[#243247] bg-[#0d1220] p-4">
          <div className="text-sm font-semibold text-white mb-2">模型調整紀錄</div>
          <div className="space-y-2">{data.history.slice(0, 12).map((h, i) => (
            <div key={i} className="text-xs">
              <span className="font-mono text-[#8b97ab]">{h.date}</span><span className="ml-2 text-slate-200">{data.names[h.strategy]}</span>
              <span className="ml-2 font-mono text-[#f59e0b]">{Object.entries(h.to).filter(([pk, v]) => h.from[pk] !== v).map(([pk, v]) => `${PNAME[pk] ?? pk} ${pv(pk, h.from[pk])}→${pv(pk, v)}`).join("、")}</span>
              <div className="text-[11px] text-[#7c8aa0]">{h.reason}</div>
            </div>))}</div>
        </section>
      )}

      <h3 className="text-sm font-semibold text-white mb-2">每日復盤{today ? `（最新 ${md(today.date)}）` : ""}</h3>
      <div className="space-y-3">
        {data.days.map((d) => (
          <div key={d.date} className="rounded-xl border border-[#243247] bg-[#0d1220] p-4">
            <div className="mb-2 flex items-center gap-2 text-sm">
              <span className="font-mono text-white">{d.date}</span>
              {d.sim && <span className="rounded bg-[#475569]/30 px-1.5 text-[10px] text-[#8b97ab]">回補模擬</span>}
              {!d.result && <span className="rounded bg-[#4f8cff]/15 px-1.5 text-[10px] text-[#4f8cff]">待收盤</span>}
            </div>
            <div className="grid gap-3 lg:grid-cols-3">
              {KEYS.map((k) => {
                const rows = d.result?.[k] ?? d.picks?.[k];
                if (!rows) return <div key={k} />;
                const trig = (d.result?.[k] ?? []).filter((r) => r.trig);
                const avg = trig.length ? trig.reduce((s, r) => s + (r.net ?? 0), 0) / trig.length : null;
                return (
                  <div key={k}>
                    <div className="mb-1 flex justify-between text-[11px] text-[#8b97ab]"><span>{data.names[k]}</span>
                      {d.result && <span>{trig.length}/{rows.length} 觸發・<span className={`font-mono ${tone(avg)}`}>{pct(avg)}</span></span>}</div>
                    {!rows.length && <div className="text-xs text-[#7c8aa0]">沒有標的</div>}
                    {rows.map((r) => (
                      <div key={r.code} className="flex items-center justify-between py-0.5 text-xs">
                        <span><span className="text-slate-200">{r.name}</span><span className="ml-1 font-mono text-[10px] text-[#7c8aa0]">{r.code}</span></span>
                        {r.net == null ? <span className="text-[#7c8aa0]">{r.status ?? "—"}</span> : (
                          <span className="font-mono">
                            <span className="text-[#7c8aa0]">開 {pct(r.gap, 1)}</span>
                            {r.trig ? <span className={`ml-2 ${tone(r.net)}`}>{pct(r.net)}</span> : <span className="ml-2 text-[#7c8aa0]">{r.status?.startsWith("開跌停") ? "開跌停" : "未觸發"}</span>}
                          </span>)}
                      </div>))}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6">
        <Note>
          每天推播前把三個當沖策略的推薦名單記下來，收盤後用實際開盤、收盤價復盤：放空開盤價、收盤價回補，扣成本後的損益（未計滑價與漲跌停排隊）。
          85g 要開盤落在設定的開高區間才算觸發；其他兩個策略看隔天開盤跳空有沒有在設定的範圍（最少開高多少、開高超過多少就不做），開跌停放不了空的不算。
          每週六用近 120 個交易日重新回測各組參數：樣本夠、有訊號的天數不少於原本一半、前後半段都賺而且都比目前參數好、整體平均淨報酬至少多 0.1 個百分點，才換新參數，並記在調整紀錄。
          標「回補模擬」的日子是上線前用當時規則重建的名單，不是實際推播過的。
        </Note>
      </div>
    </div>
  );
}
