"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Star, X } from "lucide-react";
import { useStaticJson } from "@/lib/static-json";
import { useWatchlist } from "@/lib/watchlist";
import { Note, Pills, SearchBox } from "@/components/data-ui";

type Sig = [string, string, number];
type Signals = { date: string; quotes: Record<string, [string, number, number | null]>; sig: Record<string, Sig[]> };
type Index = Record<string, [string, string, string, number, number] | string>;
type Cat = "all" | string;

const CAT_STYLE: Record<number, string> = { 1: "bg-[#f05252]/12 text-[#f87171] border-[#f05252]/30", [-1]: "bg-[#22c55e]/12 text-[#4ade80] border-[#22c55e]/30", 0: "bg-slate-500/10 text-slate-300 border-slate-500/30" };
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-slate-400" : v > 0 ? "text-[#f05252]" : "text-[#22c55e]");

function SigChips({ items }: { items: Sig[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map(([cat, text, d], i) => (
        <span key={i} className={`rounded border px-1.5 py-0.5 text-[11px] leading-4 ${CAT_STYLE[d] ?? CAT_STYLE[0]}`}>
          <span className="opacity-60 mr-1">{cat}</span>{text}
        </span>
      ))}
    </div>
  );
}

export default function WatchlistDashboard() {
  const sig = useStaticJson<Signals>("signals.json");
  const idx = useStaticJson<Index>("stocks.json");
  const { list, toggle, save } = useWatchlist();
  const [cat, setCat] = useState<Cat>("all");
  const [copied, setCopied] = useState(false);

  const items = useMemo(() => Object.entries(idx.data ?? {}).filter(([k]) => k !== "_date")
    .map(([c, v]) => ({ code: c, name: (v as string[])[0] })), [idx.data]);
  const name = (c: string) => sig.data?.quotes[c]?.[0] ?? (idx.data?.[c] as string[] | undefined)?.[0] ?? c;

  const watched = list.map((c) => ({ c, s: sig.data?.sig[c] ?? [], q: sig.data?.quotes[c] ?? null, ix: idx.data?.[c] as [string, string, string, number, number] | undefined }))
    .sort((a, b) => b.s.length - a.s.length);
  const hot = useMemo(() => !sig.data ? [] : Object.entries(sig.data.sig)
    .map(([c, s]) => ({ c, s: s.filter((x) => cat === "all" || x[0] === cat) }))
    .filter((x) => x.s.length >= (cat === "all" ? 3 : 1))
    .sort((a, b) => b.s.length - a.s.length || a.c.localeCompare(b.c)).slice(0, 40), [sig.data, cat]);
  const cats = useMemo(() => [...new Set(Object.values(sig.data?.sig ?? {}).flat().map((x) => x[0]))], [sig.data]);

  const copy = async () => {
    try { await navigator.clipboard.writeText(list.join(",")); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
  };

  return (
    <div>
      <Note>
        把常看的股票加入自選股（只存在這台瀏覽器，換電腦或清除瀏覽資料會不見），這頁每天整理它們在全站觸發的訊號：
        技術面、漲停、三大法人、融資券、月營收、內部人申報轉讓、ETF 加減碼、大戶持股、除權息／股東會／法說會、庫藏股。
        {sig.data && ` 資料日 ${sig.data.date}。`}紅＝偏多、綠＝偏空、灰＝中性。
      </Note>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
        <SearchBox placeholder="加入自選股，輸入代號或名稱" items={items} onPick={(c) => { if (!list.includes(c)) toggle(c); }} />
        {list.length > 0 && (
          <div className="flex gap-3 text-xs text-[#8b97ab]">
            <button onClick={copy} className="hover:text-[#4f8cff]">{copied ? "已複製 ✓" : "複製清單（給推播用）"}</button>
            <button onClick={() => { if (confirm("清空自選股？")) save([]); }} className="hover:text-[#f05252]">清空</button>
          </div>
        )}
      </div>

      {!list.length ? (
        <div className="rounded-xl border border-dashed border-[#243247] bg-[#0d1220] p-8 text-center mb-8">
          <Star className="w-6 h-6 text-[#7c8aa0] mx-auto mb-2" />
          <p className="text-sm text-slate-400">還沒有自選股。用上面的搜尋加入，或在「個股查詢」頁按 ☆。</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-10">
          {watched.map(({ c, s, q, ix }) => (
            <div key={c} className="rounded-xl border border-[#243247] bg-[#0d1220] p-4">
              <div className="flex items-baseline gap-2 mb-2">
                <Link href={`/search?code=${c}`} className="text-slate-100 font-semibold hover:text-[#4f8cff]">{name(c)}</Link>
                <span className="font-mono text-xs text-[#8b97ab]">{c}</span>
                {q ? <><span className="font-mono text-sm text-slate-200 ml-2">{q[1]}</span><span className={`font-mono text-xs ${tone(q[2])}`}>{q[2] == null ? "" : `${q[2] > 0 ? "+" : ""}${q[2].toFixed(2)}%`}</span></>
                  : ix && <span className="font-mono text-sm text-slate-200 ml-2">{ix[3]}</span>}
                <button onClick={() => toggle(c)} title="移除" className="ml-auto text-[#7c8aa0] hover:text-[#f05252]"><X className="w-4 h-4" /></button>
              </div>
              {s.length ? <SigChips items={s} /> : <p className="text-xs text-[#7c8aa0]">今天沒有特別的訊號。</p>}
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mb-3">
        <h3 className="text-sm font-semibold text-white mr-2">今天訊號最多的股票</h3>
        <Pills<Cat> value={cat} onChange={setCat} options={[{ value: "all", label: "全部" }, ...cats.map((x) => ({ value: x, label: x }))]} />
      </div>
      <div className="rounded-xl border border-[#243247] bg-[#0d1220] divide-y divide-[#243247]/60">
        {hot.map(({ c, s }) => (
          <div key={c} className="flex flex-col sm:flex-row sm:items-start gap-2 px-4 py-3">
            <div className="flex items-center gap-2 sm:w-48 shrink-0">
              <button onClick={() => toggle(c)} title={list.includes(c) ? "移出自選" : "加入自選"} className={list.includes(c) ? "text-[#f59e0b]" : "text-[#7c8aa0] hover:text-[#f59e0b]"}>
                <Star className="w-4 h-4" fill={list.includes(c) ? "currentColor" : "none"} />
              </button>
              <Link href={`/search?code=${c}`} className="text-slate-200 hover:text-[#4f8cff]">{name(c)}</Link>
              <span className="font-mono text-xs text-[#8b97ab]">{c}</span>
            </div>
            <SigChips items={s} />
          </div>
        ))}
      </div>
    </div>
  );
}
