#!/usr/bin/env python3
"""
當沖策略用 1 分 K 重新回測（data/research/intraday_1m，2024 起），和日線版比較

策略（第 t 天收盤選股，t+1 開盤空，13:25 回補）：
  85g（1～3%）   前一天成交前 50、漲停或 5 日漲 ≥ 8%，開高 1～3%
  85g（掛 +1%）  同上，開高 ≥ 1% 全部成交（實際掛單會發生的情況）
  高週轉＋漲停   週轉率前 20、收漲停、開平以上
  高當沖比       當沖比 ≥ 60%、收黑K但收漲
  散戶擁擠 A     週轉率前 10、當沖比 ≥ 60%、收紅K、開平以上（research_crowd_short.py）
  散戶擁擠 B     週轉率前 50、當沖比 ≥ 60%、收漲紅K、開高 1～3%
停損：漲到前一天收盤 +7.5%（build_strategy.DT_STOP）→ 用 1 分 K 實際觸價：那一分鐘最高 ≥ 停損價就以停損價回補，
      那一分鐘開盤就已經超過（跳空過去）以開盤價回補；開盤已超過 +7.5% 不做
日線版：同一批交易，停損假設剛好成交在 +7.5%、收盤價（含收盤集合競價）回補
成本 0.23%；輸出 data/research/intraday_dt.json；用法：python scripts/research_intraday_dt.py
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_strategy import DT_STOP  # noqa: E402
import research_crowd_short as cs  # noqa: E402
import research_intraday as ri  # noqa: E402

STOP_BP = round(DT_STOP * 100)
PARTS = (("2024", "2024", "2025"), ("2025+", "2025", "2100"))


def minute_short(m: dict):
    """開盤（09:00 第一分鐘開盤＝開盤價）空、13:25 回補；回傳（報酬 %, 停損了沒, 停損滑價 bp）"""
    if 0 not in m:
        return None
    e = m[0][0]
    if e >= STOP_BP or e <= -950:
        return None
    to = lambda p: ((1 + e / 1e4) - (1 + p / 1e4)) / (1 + e / 1e4) * 100  # noqa: E731
    for t in sorted(m):
        if t > ri.END:
            break
        o, h = m[t][0], m[t][1]
        if t > 0 and o >= STOP_BP:
            return to(o) - ri.COST, True, o - STOP_BP
        if h >= STOP_BP:
            return to(STOP_BP) - ri.COST, True, 0
    return to(ri.px_at(m, ri.END)) - ri.COST, False, 0


def main():
    bars = ri.load_bars()
    print(f"1 分 K：{len(bars)} 天、{sum(len(v) for v in bars.values())} 個日期×股票")
    rows = [r for r in cs.rows_all() if r["n"] >= "2024"]
    byd = defaultdict(list)
    for r in rows:
        byd[r["d"]].append(r)
    strat = defaultdict(list)
    for d, xs in byd.items():
        vr = {r["code"]: k for k, r in enumerate(sorted(xs, key=lambda r: -r["val"]), 1)}
        tr = {r["code"]: k for k, r in enumerate(sorted((r for r in xs if r["turn"]), key=lambda r: -r["turn"]), 1)}
        for r in xs:
            c, g = r["code"], r["gap"]
            hot = vr[c] <= 50 and (r["limit"] or r["r5"] >= 8)
            dt = r["dt"] if r["dt"] is not None else -1
            sel = {
                "85g（1～3%）": hot and 1 <= g < 3,
                "85g（掛 +1%）": hot and g >= 1,
                "高週轉＋漲停": tr.get(c, 999) <= 20 and r["limit"] and g >= 0,
                "高當沖比＋黑K收漲": dt >= 60 and r["black"] and r["ret"] >= 0,
                "散戶擁擠 A": tr.get(c, 999) <= 10 and dt >= 60 and not r["black"] and g >= 0,
                "散戶擁擠 B": tr.get(c, 999) <= 50 and dt >= 60 and not r["black"] and r["ret"] >= 0 and 1 <= g < 3,
            }
            b = (bars.get(r["n"]) or {}).get(c)
            for k, ok in sel.items():
                if not ok:
                    continue
                if b is None:
                    strat[k].append({"n": r["n"], "daily": r["r"], "m": None})
                    continue
                x = minute_short(b["m"])
                strat[k].append({"n": r["n"], "daily": r["r"], "m": x[0] if x else None, "stop": x[1] if x else None, "slip": x[2] if x else None})
    out = {}
    print(f"\n停損 +{DT_STOP:g}%；每筆淨報酬（扣 {ri.COST}%）。1 分 K 版只算有分鐘資料的交易，日線版是同一批交易")
    for k, ev in strat.items():
        have = [e for e in ev if e["m"] is not None and e["daily"] is not None]
        line = {}
        for lab, a, b in PARTS:
            xs = [e for e in have if a <= e["n"] < b]
            if not xs:
                continue
            allx = [e["daily"] for e in ev if a <= e["n"] < b and e["daily"] is not None and e["n"] >= min(x["n"] for x in xs)]
            line[lab] = {"n": len(xs), "all": sum(1 for e in ev if a <= e["n"] < b), "min": round(st.mean(e["m"] for e in xs), 3),
                         "dailyAll": round(st.mean(allx), 3) if allx else None,
                         "daily": round(st.mean(e["daily"] for e in xs), 3), "win": round(sum(e["m"] > 0 for e in xs) / len(xs) * 100, 1),
                         "stop": round(sum(e["stop"] for e in xs) / len(xs) * 100, 1),
                         "slip": round(st.mean(e["slip"] for e in xs if e["stop"]) / 100, 2) if any(e["stop"] for e in xs) else 0}
        out[k] = line
        print(f"  {k:12s}：" + "｜".join(f"{lab} 1 分 K {v['min']:+.2f}% vs 日線 {v['daily']:+.2f}%（{v['n']}/{v['all']} 筆有分鐘資料，勝 {v['win']:.0f}%，"
                                            f"停損 {v['stop']:.0f}%，停損跳空滑價平均 {v['slip']:.2f}%；同期間全部交易日線 {v['dailyAll']:+.2f}%）" for lab, v in line.items()))
    (DATA / "research" / "intraday_dt.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
