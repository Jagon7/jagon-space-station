#!/usr/bin/env python3
"""
台指期日盤＋夜盤、一個時段可以做多筆：開盤區間（OR）突破／均值回歸的各種打法回測

時段（每個時段各自用自己的 OR）：
  日盤：OR 08:45～09:15，09:15 後進場，13:30 出場
  夜盤前段：OR 15:00～15:30，15:30 後進場，美股開盤前 1 分鐘出場（夏令 21:29、冬令 22:29）
  夜盤美股段：OR＝美股開盤後 30 分鐘（夏令 21:30～22:00、冬令 22:30～23:00），之後進場，04:59 出場
打法（每筆扣 3 點；同一根 1 分 K 同時碰到停損和目標，保守算停損）：
  BO1   突破一筆：先突破哪邊做哪邊，停損 OR 另一側，時段結束出場
  BO_SAR 突破＋停損反手：被停損就反手（停損放原本那一側），最多 3 筆
  BO_RE 突破再進場：被停損後，價格再突破任一邊就再做一次，最多 3 筆
  MR1   均值回歸一筆：進場後 15 分鐘內先碰到哪邊做哪邊（碰高空、碰低多），目標 OR 中點，停損 OR 外 0.5 倍寬度
  MR_RE 均值回歸多筆：前一筆結束後，進場後 60 分鐘內再碰到邊界就再做，最多 3 筆
  MR_BO MR 被停損就改做突破方向（停損 OR 中點），時段結束出場
另看「窄 OR（寬度 ≤ 過去 20 天同時段 OR 寬度中位數）」與「寬 OR」分開的表現，判斷這個時段該打 BO 還是 MR
分三段：2020-22、2023-24、2025 後；每段看每天平均點數、勝率、最差一天、年化夏普（每天平均 ÷ 標準差 × √250）
輸出 data/research/tx_multi.json；用法：python scripts/research_tx_multi.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = 3.0
PARTS = (("2020-22", "2020", "2023"), ("2023-24", "2023", "2025"), ("2025-", "2025", "2100"))


def us_dst(d: date) -> bool:
    """美國夏令時間：3 月第二個週日～11 月第一個週日"""
    y = d.year
    mar = date(y, 3, 8) + timedelta(days=(6 - date(y, 3, 8).weekday()) % 7)
    nov = date(y, 11, 1) + timedelta(days=(6 - date(y, 11, 1).weekday()) % 7)
    return mar <= d < nov


def run(bars: dict, orh: float, orl: float, start: int, end: int, kind: str):
    """回傳 [(損益點, 進場分, 出場分)]"""
    w, mid = orh - orl, (orh + orl) / 2
    trades, pos = [], None  # pos = [方向, 進場, 停損, 目標, 進場分, 型態]
    max_n = 1 if kind in ("BO1", "MR1", "MR_BO") else 3
    mr_until = start + (15 if kind in ("MR1", "MR_BO") else 60)
    flipped = False
    last_c = None
    for m in range(start, end + 1):
        b = bars.get(m)
        if not b:
            continue
        o, h, lo, c = b[0], b[1], b[2], b[3]
        last_c = c
        if pos is None:
            if len(trades) >= max_n:
                break
            if kind.startswith("BO"):
                if kind == "BO_RE" or not trades:
                    if h > orh:
                        pos = [1, max(o, orh), orl, None, m, "BO"]
                    elif lo < orl:
                        pos = [-1, min(o, orl), orh, None, m, "BO"]
            elif m <= mr_until:
                if h >= orh:
                    pos = [-1, max(o, orh), orh + 0.5 * w, mid, m, "MR"]
                elif lo <= orl:
                    pos = [1, min(o, orl), orl - 0.5 * w, mid, m, "MR"]
            if pos is None:
                continue
        d, ent, stop, tgt, m0, typ = pos
        if (d > 0 and lo <= stop) or (d < 0 and h >= stop):
            trades.append(((stop - ent) * d - COST, m0, m))
            pos = None
            if kind == "BO_SAR" and len(trades) < max_n:
                pos = [-d, stop, ent, None, m, "BO"]  # 反手，停損放原本進場那一側
            elif kind == "MR_BO" and not flipped:
                flipped = True
                pos = [-d, stop, mid, None, m, "BO"]
                max_n = 2
            continue
        if tgt is not None and ((d > 0 and h >= tgt) or (d < 0 and lo <= tgt)):
            trades.append(((tgt - ent) * d - COST, m0, m))
            pos = None
    if pos is not None and last_c is not None:
        trades.append(((last_c - pos[1]) * pos[0] - COST, pos[4], end))
    return trades


def sessions():
    day = rr.load_dir(DATA / "futures" / "day")
    night = rr.load_dir(DATA / "futures" / "night")
    out = {"日盤": [], "夜盤前段": [], "夜盤美股段": []}
    for d, b in sorted(day.items()):
        if len(b) >= 250 and 29 in b:
            out["日盤"].append((d, b, 0, 30, 285))
    for d, b in sorted(night.items()):
        if len(b) < 600:
            continue
        us = 390 if us_dst(date.fromisoformat(d)) else 450  # 21:30／22:30 距 15:00 的分鐘數
        out["夜盤前段"].append((d, b, 0, 30, us - 1))
        out["夜盤美股段"].append((d, b, us, us + 30, 839))
    return out


def stats(xs):
    if len(xs) < 30:
        return None
    sd = st.pstdev(xs)
    return {"n": len(xs), "avg": round(st.mean(xs), 1), "win": round(sum(x > 0 for x in xs) / len(xs) * 100, 1),
            "worst": round(min(xs)), "sharpe": round(st.mean(xs) / sd * 250 ** 0.5, 2) if sd else None}


def main():
    S = sessions()
    kinds = ["BO1", "BO_SAR", "BO_RE", "MR1", "MR_RE", "MR_BO"]
    names = {"BO1": "突破一筆", "BO_SAR": "突破＋停損反手（最多 3 筆）", "BO_RE": "突破再進場（最多 3 筆）",
             "MR1": "均值回歸一筆（15 分鐘內碰到）", "MR_RE": "均值回歸多筆（60 分鐘內，最多 3 筆）", "MR_BO": "MR 停損改做突破"}
    out = {"cost": COST, "sessions": {}}
    for sn, items in S.items():
        # OR 寬度與過去 20 天中位數
        rows = []
        hist = []
        for d, b, s0, s1, end in items:
            orb = [b[m] for m in range(s0, s1) if m in b]
            if len(orb) < 20:
                continue
            orh, orl = max(x[1] for x in orb), min(x[2] for x in orb)
            w = orh - orl
            narrow = w <= st.median(hist[-20:]) if len(hist) >= 20 else None
            hist.append(w)
            res = {k: run(b, orh, orl, s1, end, k) for k in kinds}
            rows.append({"d": d, "narrow": narrow, "res": res})
        print(f"\n■ {sn}：{len(rows)} 天（{rows[0]['d']}～{rows[-1]['d']}）")
        out["sessions"][sn] = {"days": len(rows), "kinds": {}}
        for k in kinds:
            o = {}
            line = []
            for gname, gf in (("全部", lambda r: True), ("窄 OR", lambda r: r["narrow"] is True), ("寬 OR", lambda r: r["narrow"] is False)):
                per = {}
                for pn, a, z in PARTS:
                    xs = [sum(t[0] for t in r["res"][k]) for r in rows if gf(r) and a <= r["d"] < z]
                    per[pn] = stats(xs)
                o[gname] = per
                line.append(f"{gname}：" + "｜".join(f"{pn} {v['avg']:+.1f}（勝 {v['win']:.0f}%、夏普 {v['sharpe']}）" if v else f"{pn} —"
                                                   for pn, v in per.items()))
            ntr = st.mean(len(r["res"][k]) for r in rows)
            o["tradesPerDay"] = round(ntr, 2)
            out["sessions"][sn]["kinds"][k] = o
            print(f"  {names[k]}（平均每天 {ntr:.2f} 筆）")
            for ln in line:
                print("     " + ln)
    (DATA / "research" / "tx_multi.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
