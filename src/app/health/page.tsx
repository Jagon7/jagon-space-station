import fs from "fs";
import path from "path";
import PageShell from "@/components/PageShell";
import HealthTable, { type Level, type Row } from "@/components/HealthTable";

const DATA = path.join(process.cwd(), "data");
// 網站在每次排程抓取後重新產生，建置時間就是檢查時間
const BUILT = new Date();

function read<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(path.join(DATA, file), "utf-8")) as T;
  } catch {
    return null;
  }
}
const list = (dir: string) => (fs.existsSync(path.join(DATA, dir)) ? fs.readdirSync(path.join(DATA, dir)).filter((f) => f.endsWith(".json")).sort() : []);
const iso = (d: Date) => d.toISOString().slice(0, 10);
const tpeNow = () => new Date(BUILT.getTime() + 8 * 3600e3); // 用 UTC 欄位表示台北時間

/** 交易日曆：資料裡出現過的交易日 ＋ 證交所休市日表；兩者都沒涵蓋的平日當成交易日 */
function calendar(known: Set<string>) {
  const holidays = new Set(read<{ holidays: string[] }>("calendar.json")?.holidays ?? []);
  const sorted = [...known].sort();
  const first = sorted[0], last = sorted.at(-1);
  const isTrading = (d: string) => {
    const wd = new Date(`${d}T00:00:00Z`).getUTCDay();
    if (wd === 0 || wd === 6 || holidays.has(d)) return false;
    if (known.has(d)) return true;
    // 已有資料涵蓋的區間內，沒有任何資料的平日 → 休市（例如颱風假、補假）
    return !(first && last && d > first && d < last);
  };
  // 最近應開盤日：台北時間 18:00 以後算今天，否則從昨天往回找
  const now = tpeNow();
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  if (now.getUTCHours() < 18) d.setUTCDate(d.getUTCDate() - 1);
  while (!isTrading(iso(d))) d.setUTCDate(d.getUTCDate() - 1);
  const expected = iso(d);
  /** date 之後到最近應開盤日之間有幾個交易日 */
  const lag = (date: string | null) => {
    if (!date) return null;
    let n = 0;
    const x = new Date(`${date.slice(0, 10)}T00:00:00Z`);
    for (let i = 0; i < 400; i++) {
      x.setUTCDate(x.getUTCDate() + 1);
      const s = iso(x);
      if (s > expected) break;
      if (isTrading(s)) n++;
    }
    return n;
  };
  return { expected, lag };
}

function byLag(lag: number | null, okUpTo: number, warnUpTo = okUpTo): Level {
  if (lag == null) return "error";
  return lag <= okUpTo ? "ok" : lag <= warnUpTo ? "warn" : "error";
}
const lagNote = (lag: number | null, okUpTo: number) => (lag == null ? "沒有資料" : lag > okUpTo ? `落後 ${lag} 個交易日` : "");

function buildRows() {
  const prices = read<{ days: Record<string, unknown> }>("etf/prices.json");
  const priceDates = Object.keys(prices?.days ?? {}).sort();
  const rankingDates = list("ranking").map((f) => f.replace(".json", ""));
  const brokerFiles = list("broker");
  const known = new Set([...priceDates, ...rankingDates, ...brokerFiles.map((f) => f.replace(".json", ""))]);
  const { expected, lag } = calendar(known);
  const rows: Row[] = [];
  const push = (r: Omit<Row, "lag"> & { lag?: number | null }) => rows.push({ lag: null, ...r });

  // ── 行情與每日資料 ───────────────────────────────
  const priceLag = lag(priceDates.at(-1) ?? null);
  push({ level: byLag(priceLag, 0, 1), item: "行情", name: "收盤價（證交所＋櫃買）", date: priceDates.at(-1) ?? null, lag: priceLag, count: null, note: lagNote(priceLag, 0) || `累積 ${priceDates.length} 天` });
  const rk = rankingDates.length ? read<{ rows: unknown[] }>(`ranking/${rankingDates.at(-1)}.json`) : null;
  const rkLag = lag(rankingDates.at(-1) ?? null);
  push({ level: !rk?.rows.length ? "error" : byLag(rkLag, 0, 1), item: "行情", name: "成交排行", date: rankingDates.at(-1) ?? null, lag: rkLag, count: rk?.rows.length ?? 0, note: lagNote(rkLag, 0) });
  const aum = read<{ days: Record<string, Record<string, unknown>> }>("etf/aum.json");
  const aumDates = Object.keys(aum?.days ?? {}).sort();
  const aumLag = lag(aumDates.at(-1) ?? null);
  push({ level: byLag(aumLag, 1, 2), item: "ETF", name: "ETF 規模（AUM）", date: aumDates.at(-1) ?? null, lag: aumLag, count: Object.keys(aum?.days?.[aumDates.at(-1) ?? ""] ?? {}).length, note: lagNote(aumLag, 1) });

  const daily: [string, string][] = [
    ["limit-up.json", "漲停訊號"], ["sector-stocks.json", "族群個股"], ["sector-performance.json", "族群強弱"],
    ["market-summary.json", "大盤統計"], ["notice.json", "注意股"], ["disposition.json", "處置股"],
    ["announcements.json", "重大訊息"], ["sfb-cb.json", "CB 申報案件"],
  ];
  for (const [file, name] of daily) {
    const d = read<{ date?: string; data?: unknown }>(file);
    const items = d?.data;
    const count = Array.isArray(items) ? items.length : items && typeof items === "object" ? Object.keys(items).length : null;
    const l = lag(d?.date ?? null);
    push({ level: byLag(l, 0, 1), item: "每日", name, date: d?.date ?? null, lag: l, count, note: lagNote(l, 0) });
  }

  // ── 每日全市場行情（氣氛評估／隔日追蹤／券差偵察） ──
  {
    const files = list("daily").filter((f) => f.startsWith("20"));
    const last = files.length ? read<{ date: string; q: Record<string, unknown>; m: Record<string, unknown>; s: Record<string, unknown>; partial?: string[] | null }>(`daily/${files.at(-1)}`) : null;
    const l = lag(last?.date ?? null);
    push({ level: !last ? "error" : last.partial ? "warn" : byLag(l, 0, 1), item: "行情", name: "全市場開高低收（上市＋上櫃）", date: last?.date ?? null, lag: l, count: last ? Object.keys(last.q).length : 0, note: last?.partial ? `缺 ${last.partial.join("、")}` : lagNote(l, 0) || `累積 ${files.length} 天` });
    const mDay = [...files].reverse().map((f) => read<{ date: string; m: Record<string, unknown>; s: Record<string, unknown> }>(`daily/${f}`)).find((d) => d && Object.keys(d.m).length);
    const ml = lag(mDay?.date ?? null);
    push({ level: byLag(ml, 1, 2), item: "籌碼", name: "融資融券餘額", date: mDay?.date ?? null, lag: ml, count: mDay ? Object.keys(mDay.m).length : 0, note: lagNote(ml, 1) });
    push({ level: !mDay || !Object.keys(mDay.s).length ? "warn" : byLag(ml, 1, 2), item: "籌碼", name: "借券賣出餘額", date: mDay?.date ?? null, lag: ml, count: mDay ? Object.keys(mDay.s).length : 0, note: mDay && !Object.keys(mDay.s).length ? "這天沒有借券資料" : "" });
  }

  // ── 基礎情報（月營收、季報、自結、庫藏股、事件） ──
  {
    const now = tpeNow();
    const rev = list("fund/revenue").map((f) => f.replace(".json", ""));
    // 每月 10 日公布上個月營收；12 日以後應該要有上個月
    const dueRev = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - (now.getUTCDate() >= 12 ? 1 : 2), 1)).toISOString().slice(0, 7);
    const revN = rev.length ? Object.keys(read<Record<string, unknown>>(`fund/revenue/${rev.at(-1)}.json`) ?? {}).length : 0;
    push({ level: rev.at(-1) && rev.at(-1)! >= dueRev ? "ok" : "warn", item: "基本面", name: "月營收", date: rev.at(-1) ?? null, count: revN, note: rev.at(-1) && rev.at(-1)! >= dueRev ? `共 ${rev.length} 個月` : `應已有 ${dueRev}` });
    const inc = list("fund/income").map((f) => f.replace(".json", "")).sort();
    push({ level: inc.length ? "ok" : "error", item: "基本面", name: "季報（綜合損益）", date: inc.at(-1) ?? null, count: inc.length ? Object.keys(read<Record<string, unknown>>(`fund/income/${inc.at(-1)}.json`) ?? {}).length : 0, note: `共 ${inc.length} 季` });
    const sr = list("fund/selfreport").map((f) => f.replace(".json", "")).filter((f) => f.includes("-")).sort();
    push({ level: sr.length ? "ok" : "warn", item: "基本面", name: "自結損益（月）", date: sr.at(-1) ?? null, count: sr.length ? Object.keys(read<Record<string, unknown>>(`fund/selfreport/${sr.at(-1)}.json`) ?? {}).length : 0, note: "" });
    const ev = read<{ updatedAt: string; exdiv: unknown[]; agm: unknown[]; conf: unknown[] }>("fund/events.json");
    const el = lag(ev?.updatedAt?.slice(0, 10) ?? null);
    push({ level: byLag(el, 1, 3), item: "基本面", name: "除權息／股東會／法說會", date: ev?.updatedAt?.slice(0, 10) ?? null, lag: el, count: ev ? ev.exdiv.length + ev.agm.length + ev.conf.length : 0, note: ev ? `除權息 ${ev.exdiv.length}、股東會 ${ev.agm.length}、法說會 ${ev.conf.length}` : "" });
    const bb = read<unknown[]>("fund/buyback.json");
    push({ level: bb?.length ? "ok" : "warn", item: "基本面", name: "庫藏股", date: null, count: bb?.length ?? 0, note: "近 2 年決議" });
  }

  // ── 券商報告、法說會新聞、國際行情 ──
  {
    const rp = read<{ updatedAt: string; items: { date: string; kind: string }[] }>("intel/reports.json");
    const rd = rp?.items[0]?.date ?? null;
    const rl = lag(rd);
    push({ level: !rp ? "error" : byLag(rl, 2, 4), item: "情報", name: "券商報告", date: rd, lag: rl, count: rp?.items.filter((x) => x.kind === "broker").length ?? 0, note: rp ? `抓取 ${rp.updatedAt.slice(5, 16).replace("T", " ")}` : "" });
    const cn = read<{ items: { date: string }[] }>("intel/confnews.json");
    push({ level: cn?.items.length ? "ok" : "warn", item: "情報", name: "法說會要點（新聞／AI 摘要）", date: cn?.items[0]?.date ?? null, count: cn?.items.length ?? 0, note: "" });
    const nw = read<{ items: [string, number, string[], string, number][] }>("intel/news.json");
    const nd = nw?.items.length ? new Date(nw.items.at(-1)![1] * 1000 + 8 * 3600e3).toISOString().slice(0, 10) : null;
    push({ level: nw?.items.length ? byLag(lag(nd), 1, 3) : "error", item: "策略", name: "個股新聞輿情（輿情籌碼策略）", date: nd, lag: lag(nd), count: nw?.items.length ?? 0, note: "" });
    const dp = read<{ updatedAt: string; items: unknown[] }>("strategy/disposition.json");
    push({ level: dp?.items.length ? "ok" : "warn", item: "策略", name: "處置股歷史（出量做多策略）", date: dp?.updatedAt?.slice(0, 10) ?? null, count: dp?.items.length ?? 0, note: "" });
    const shr = read<{ updatedAt: string; shares: Record<string, number> }>("strategy/shares.json");
    const shn = shr ? Object.keys(shr.shares).length : 0;
    push({ level: shn > 1500 ? "ok" : "warn", item: "策略", name: "已發行股數（週轉率）", date: shr?.updatedAt?.slice(0, 10) ?? null, count: shn, note: "" });
    const dtr = read<{ updatedAt: string; days: Record<string, { tw?: unknown; tp?: unknown }> }>("strategy/daytrade.json");
    const dtn = dtr ? Object.values(dtr.days).filter((x) => x.tw && x.tp).length : 0;
    push({ level: dtn > 100 ? "ok" : "warn", item: "策略", name: "個股當沖成交（週轉率頁）", date: dtr?.updatedAt?.slice(0, 10) ?? null, count: dtn, note: "" });
    const blk = read<{ updatedAt: string; days: Record<string, unknown> }>("strategy/block.json");
    push({ level: blk ? "ok" : "warn", item: "策略", name: "鉅額交易（出量做多扣除用）", date: blk?.updatedAt?.slice(0, 10) ?? null, count: blk ? Object.keys(blk.days).length : 0, note: "" });
    const us = read<{ updatedAt: string; series: Record<string, [string, number][]> }>("intel/us.json");
    const ud = us ? Object.values(us.series).map((v) => v.at(-1)?.[0] ?? "").sort().at(-1) ?? null : null;
    const ul = lag(ud);
    push({ level: !us ? "error" : byLag(ul, 1, 3), item: "情報", name: "美股／國際行情", date: ud, lag: ul, count: us ? Object.keys(us.series).length : 0, note: "美股日期比台股晚一天屬正常" });
  }

  // ── 籌碼：三大法人、期貨、集保 ──
  {
    const it = list("insti").filter((f) => f.startsWith("20"));
    const il = lag(it.at(-1)?.replace(".json", "") ?? null);
    const icount = it.length ? Object.keys(read<Record<string, unknown>>(`insti/${it.at(-1)}`) ?? {}).length - 1 : 0;
    push({ level: byLag(il, 0, 1), item: "籌碼", name: "三大法人買賣超", date: it.at(-1)?.replace(".json", "") ?? null, lag: il, count: icount, note: lagNote(il, 0) || `累積 ${it.length} 天` });
    const fu = read<Record<string, unknown>>("futures/daily.json") ?? {};
    const fd = Object.keys(fu).sort().at(-1) ?? null;
    const fl = lag(fd);
    push({ level: byLag(fl, 0, 1), item: "籌碼", name: "期貨選擇權籌碼", date: fd, lag: fl, count: Object.keys(fu).length, note: lagNote(fl, 0) });
    const hw = list("holders").map((f) => f.replace(".json", "")).sort();
    const hl = lag(hw.at(-1) ?? null);
    push({ level: byLag(hl, 6, 10), item: "籌碼", name: "集保大戶持股（每週）", date: hw.at(-1) ?? null, lag: hl, count: hw.length ? Object.keys(read<Record<string, unknown>>(`holders/${hw.at(-1)}.json`) ?? {}).length : 0, note: lagNote(hl, 6) || `共 ${hw.length} 週` });
  }

  // ── 週期性資料 ───────────────────────────────────
  const cb = read<{ updatedAt: string; cases: unknown[] }>("cb/cases.json");
  const cbLag = lag(cb?.updatedAt?.slice(0, 10) ?? null);
  push({ level: !cb?.cases.length ? "error" : byLag(cbLag, 1, 3), item: "CB", name: "CB 圈購到掛牌時間軸", date: cb?.updatedAt?.slice(0, 10) ?? null, lag: cbLag, count: cb?.cases.length ?? 0, note: lagNote(cbLag, 1) });
  const ind = read<{ updatedAt: string; industries: unknown[] }>("industry/chain.json");
  const indLag = lag(ind?.updatedAt ?? null);
  push({ level: byLag(indLag, 6, 10), item: "產業", name: "產業細分類（每週一更新）", date: ind?.updatedAt ?? null, lag: indLag, count: ind?.industries.length ?? 0, note: lagNote(indLag, 6) });
  const sched = read<{ updatedAt: string; rows: { provider: string; effective: string }[] }>("etf/index_schedule.json");
  const schLag = lag(sched?.updatedAt?.slice(0, 10) ?? null);
  for (const prov of ["臺灣指數公司", "MSCI"]) {
    const rs = (sched?.rows ?? []).filter((r) => r.provider.includes(prov));
    const upcoming = rs.filter((r) => r.effective >= expected).length;
    push({ level: !rs.length ? "error" : byLag(schLag, 2, 5), item: "指數", name: `${prov} 審核日程`, date: sched?.updatedAt?.slice(0, 10) ?? null, lag: schLag, count: rs.length, note: lagNote(schLag, 2) || `未來 ${upcoming} 筆` });
  }

  // ── 內部人 ───────────────────────────────────────
  const irb = list("insider/irb").map((f) => f.replace(".json", ""));
  const latestM = irb.at(-1) ?? null;
  {
    // 次月 15 日申報截止，月底前應該要有上個月的資料
    const now = tpeNow();
    const due = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - (now.getUTCDate() >= 25 ? 1 : 2), 1)).toISOString().slice(0, 7);
    const ok = latestM != null && latestM >= due;
    push({ level: ok ? "ok" : "warn", item: "內部人", name: "每月持股異動申報", date: latestM, count: list("insider/co").length, note: ok ? `共 ${irb.length} 個月` : `應已有 ${due} 的資料` });
  }
  const tr = list("insider/transfer").map((f) => f.replace(".json", ""));
  const trLag = lag(tr.at(-1) ?? null);
  const trCount = tr.length ? (read<unknown[]>(`insider/transfer/${tr.at(-1)}.json`) ?? []).length : 0;
  push({ level: byLag(trLag, 1, 2), item: "內部人", name: "事前申報轉讓（日報）", date: tr.at(-1) ?? null, lag: trLag, count: trCount, note: lagNote(trLag, 1) || `已收 ${tr.length} 天` });
  {
    const px = list("insider/px");
    let newest: string | null = null;
    for (const f of px.slice(0, 40)) {
      const t = read<{ t: string }>(`insider/px/${f}`)?.t;
      if (t && (!newest || t > newest)) newest = t;
    }
    const l = lag(newest);
    push({ level: byLag(l, 4, 7), item: "內部人", name: "股價（畫圖用，每 3 天更新）", date: newest, lag: l, count: px.length, note: lagNote(l, 4) });
  }

  // ── 分點 ─────────────────────────────────────────
  const brokerDocs = brokerFiles.slice(-20).map((f) => read<{ date: string; branches: Record<string, unknown[]> }>(`broker/${f}`)).filter(Boolean) as { date: string; branches: Record<string, unknown[]> }[];
  const labels = [...new Set(brokerDocs.flatMap((d) => Object.keys(d.branches)))];
  for (const label of labels) {
    const last = [...brokerDocs].reverse().find((d) => (d.branches[label]?.length ?? 0) > 0);
    const l = lag(last?.date ?? null);
    push({ level: byLag(l, 0, 1), item: "分點", name: label, date: last?.date ?? null, lag: l, count: last?.branches[label].length ?? 0, note: lagNote(l, 0) });
  }

  // ── ETF 持股：逐檔 ────────────────────────────────
  type Status = { ok: boolean; error?: string | null };
  const status = read<{ etfs: Record<string, Status> }>("etf/status.json");
  for (const f of list("etf/holdings")) {
    const doc = read<{ code: string; name: string; issuer: string; kind: string; snapshots: { date: string; h: [string, string, number, number | null][] }[] }>(`etf/holdings/${f}`);
    if (!doc) continue;
    const snap = doc.snapshots.at(-1);
    const l = lag(snap?.date ?? null);
    const w = snap ? snap.h.reduce((s, h) => s + (h[3] ?? 0), 0) : null;
    const st = status?.etfs[doc.code];
    // 多數投信當天晚上公告，部分隔天早上才公告：落後 1 天正常，2 天以上是漏抓
    let lv = byLag(l, 1);
    const notes = [lagNote(l, 1)];
    if (st && !st.ok && st.error) { notes.push(`最近一次抓取失敗：${st.error}`); if (lv === "ok") lv = "warn"; }
    else if (st?.ok && l != null && l > 1) notes.push("抓取成功，但投信網站上的資料日還沒更新");
    if (w != null && w > 0 && (w < 80 || w > 110)) { notes.push(`權重加總 ${w.toFixed(1)}%`); if (lv === "ok") lv = "warn"; }
    push({ level: lv, item: `ETF ${doc.code}`, name: `${doc.name}（${doc.issuer}）`, date: snap?.date ?? null, lag: l, count: snap?.h.length ?? 0, weight: w && w > 0 ? w : null, note: notes.filter(Boolean).join("；") });
  }

  return { rows, expected, latestPrice: priceDates.at(-1) ?? null };
}

const SCHEDULE: [string, string][] = [
  ["平日 15:47", "收盤行情、漲停、成交排行、族群、注意／處置、可轉債、月營收／季報／自結／庫藏股／重大事件"],
  ["平日 18:17", "同上再跑一次：補三大法人、期貨選擇權、注意／處置（約 16:30～18:00 公布）"],
  ["平日 21:20", "ETF 持股、分點買賣超、內部人、集保大戶、指數審核"],
  ["平日 21:37", "同 15:47 再跑一次：補融資融券、借券（約 21:00 公布）"],
  ["平日 23:43／23:52", "兩組都再跑一次補漏"],
  ["隔天 08:05／11:35", "ETF 等：補抓較晚公布的投信持股"],
  ["週六 10:13", "補週五漏掉的資料"],
  ["清晨 04:17～08:37", "美股收盤後抓國際行情、券商報告；有新券商報告就推播"],
  ["週一到週五 08:00", "盤前快報：台指期夜盤、富台指、美股主要指數、類股龍頭與台股預估反應"],
  ["白天每 3 小時", "券商報告、法說會新聞；有新的券商報告就推播"],
  ["資料到齊後", "每日推播（行情、法人、融資券都是當天的才發；隔天 09:27 保底）"],
];

export default function HealthPage() {
  const { rows, expected, latestPrice } = buildRows();
  const t = tpeNow().toISOString().replace("T", " ").slice(0, 16);
  return (
    <PageShell title="每天的資料都有抓到嗎？" subtitle={`檢查時間 ${t}（台北）・最近應開盤日 ${expected}・最新股價 ${latestPrice ?? "—"}`} badge="Data Health">
      <HealthTable rows={rows} />
      <p className="mt-4 text-[11px] leading-relaxed text-[#7c8aa0]">
        落後＝資料日之後已經過了幾個交易日（依證交所休市日表，休市日不算）。多數投信當天晚上公告持股，部分隔天早上才公告，所以 ETF 落後 1 天屬正常；落後 2 天以上就是漏抓。
        權重加總明顯偏離 100%（低於 80% 或高於 110%）代表持股檔可能抓不完整。這一頁在每次排程抓取資料後重新產生。
      </p>
      <div className="mt-8 rounded-xl border border-[#243247] bg-[#0d1220] overflow-x-auto">
        <div className="px-4 pt-4 text-sm font-semibold text-white">每日更新排程（台北時間）</div>
        <p className="px-4 pt-1 text-[11px] leading-relaxed text-[#7c8aa0]">
          GitHub 的排程常延後好幾小時、偶爾跳過，所以每天排好幾次；每次只補還沒抓到的資料，資料源一公布、下一次排程就會補上。
        </p>
        <table className="w-full text-sm mt-2">
          <tbody>
            {SCHEDULE.map(([time, what]) => (
              <tr key={time} className="border-t border-[#243247]/60 align-top">
                <td className="px-4 py-2 font-mono text-[#4f8cff] whitespace-nowrap">{time}</td>
                <td className="px-4 py-2 text-slate-300">{what}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}
