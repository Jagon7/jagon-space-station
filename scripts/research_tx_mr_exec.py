#!/usr/bin/env python3
"""
台指期 MR（均值回歸）執行細節回測：今天（2026-11-25）的疑問——訊息只說「碰高點放空、碰低點做多」，
沒說只做第一筆、幾點前要進場、做完能不能再做反向

規則（data/futures/regime_params.json 目前參數；09:15 判斷是 MR 的日子）：
  開盤區間 OR＝08:45～09:15 的高低；09:15 之後
  V0 現行：先碰到哪一邊就做那一邊（碰高點空、碰低點多），一天一筆；目標 OR 中點，停損 OR 外 0.5 倍寬度，13:30 出場
  V1 做完一筆後，另一邊被碰到可以再做一筆（共兩筆）
  V2 進場期限：第一次碰到在 09:30／09:45／10:00／10:30／11:00 之後就不做
  V3 確認後進場：碰到邊界後，等一根 5 分 K 收回 OR 裡面才進場（用那根收盤價），停損同 V0
  V4 停損後反手：MR 停損就改做突破方向（停損放 OR 中點），13:30 出場
  V5 停損放寬到 OR 外 1 倍寬度
另外列出每筆 MR 最大未實現虧損（進場到出場之間最不利的價位）
兩段：2020-24／2025 後；每筆扣 3 點
輸出 data/research/tx_mr_exec.json；用法：python scripts/research_tx_mr_exec.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402
import tx_regime_review as rv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OR_M, EXIT_M, COST = rr.OR_M, rr.EXIT_M, rr.COST
T = lambda m: f"{(8 * 60 + 45 + m) // 60:02d}:{(8 * 60 + 45 + m) % 60:02d}"  # noqa: E731


def mr_trade(bars, orh, orl, start, side=None, stop_k=0.5, confirm=False, deadline=EXIT_M, reverse=False):
    """從分鐘 start 開始找第一次碰邊界（side 指定只做哪一邊）；回傳 (損益, 進場分, 出場分, 方向, 最大未實現虧損) 或 None"""
    w, mid = orh - orl, (orh + orl) / 2
    pos = None
    touched = None
    mae = 0.0
    for m in range(start, EXIT_M + 1):
        b = bars.get(m)
        if not b:
            continue
        o, h, lo, c = b[0], b[1], b[2], b[3]
        if pos is None:
            if m > deadline:
                return None
            hit_hi, hit_lo = h >= orh and side in (None, -1), lo <= orl and side in (None, 1)
            if not confirm:
                if hit_hi:
                    pos = [-1, max(o, orh), orh + stop_k * w, mid, m, False]
                elif hit_lo:
                    pos = [1, min(o, orl), orl - stop_k * w, mid, m, False]
                if pos:
                    # 同一根就碰到停損或目標：保守算停損
                    pass
                else:
                    continue
            else:
                if touched is None:
                    touched = -1 if hit_hi else 1 if hit_lo else None
                    continue
                if (m - OR_M) % 5 == 4:  # 5 分 K 收盤
                    if touched == -1 and c < orh:
                        pos = [-1, c, orh + stop_k * w, mid, m, False]
                    elif touched == 1 and c > orl:
                        pos = [1, c, orl - stop_k * w, mid, m, False]
                    if (touched == -1 and h >= orh + stop_k * w) or (touched == 1 and lo <= orl - stop_k * w):
                        return None  # 還沒收回就已經衝過停損位置：不做
                continue
        d, ent, stop, tgt, m0, rev = pos
        mae = min(mae, ((lo if d > 0 else h) - ent) * d)
        if (d > 0 and lo <= stop) or (d < 0 and h >= stop):
            pnl = (stop - ent) * d
            if reverse and not rev:
                # 反手做突破方向，停損 OR 中點，13:30 出場
                pos = [-d, stop, mid, None, m, True]
                first = pnl
                continue
            return (pnl - COST if not rev else first + pnl - 2 * COST), m0, m, d, mae
        if tgt is not None and ((d > 0 and h >= tgt) or (d < 0 and lo <= tgt)):
            return (tgt - ent) * d - COST, m0, m, d, mae
    if pos is None:
        return None
    d, ent, stop, tgt, m0, rev = pos
    last = bars[max(k for k in bars if k <= EXIT_M)][3]
    pnl = (last - ent) * d
    return (pnl - COST if not rev else first + pnl - 2 * COST), m0, EXIT_M, d, mae


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    rows = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    p = rv.params()["current"]
    days = []
    for d, r in sorted(rows.items()):
        if d not in day or rv.decide(r, p)[1] != "MR":
            continue
        bars = day[d]
        orb = [bars[m] for m in range(OR_M) if m in bars]
        if len(orb) < 20:
            continue
        days.append((d, bars, max(b[1] for b in orb), min(b[2] for b in orb)))
    print(f"MR 日 {len(days)} 天（{days[0][0]}～{days[-1][0]}）；每筆扣 {COST} 點")
    variants = {
        "V0 現行：先碰哪邊做哪邊、一天一筆": lambda b, h, l: [mr_trade(b, h, l, OR_M)],
        "V1 做完可再做另一邊（最多兩筆）": None,
        "V2 09:30 前碰到才做": lambda b, h, l: [mr_trade(b, h, l, OR_M, deadline=44)],
        "V2 09:45 前碰到才做": lambda b, h, l: [mr_trade(b, h, l, OR_M, deadline=59)],
        "V2 10:00 前碰到才做": lambda b, h, l: [mr_trade(b, h, l, OR_M, deadline=74)],
        "V2 10:30 前碰到才做": lambda b, h, l: [mr_trade(b, h, l, OR_M, deadline=105)],
        "V2 11:00 前碰到才做": lambda b, h, l: [mr_trade(b, h, l, OR_M, deadline=135)],
        "V3 碰到後等 5 分 K 收回區間內才進": lambda b, h, l: [mr_trade(b, h, l, OR_M, confirm=True)],
        "V4 停損後反手做突破": lambda b, h, l: [mr_trade(b, h, l, OR_M, reverse=True)],
        "V5 停損放寬到區間外 1 倍": lambda b, h, l: [mr_trade(b, h, l, OR_M, stop_k=1.0)],
    }

    def v1(b, h, l):
        t1 = mr_trade(b, h, l, OR_M)
        if not t1:
            return [None]
        t2 = mr_trade(b, h, l, t1[2] + 1, side=-t1[3] if False else (1 if t1[3] < 0 else -1))
        return [t1, t2]
    variants["V1 做完可再做另一邊（最多兩筆）"] = v1
    out = {"days": len(days), "variants": {}}
    for name, fn in variants.items():
        res = {}
        for d, b, h, l in days:
            ts = [t for t in fn(b, h, l) if t]
            res[d] = (sum(t[0] for t in ts), len(ts), min([t[4] for t in ts], default=0), ts)
        row = {}
        for pn, pf in (("2020-24", lambda d: d < "2025-01-01"), ("2025-", lambda d: d >= "2025-01-01"), ("全部", lambda d: True)):
            xs = [v for d, v in res.items() if pf(d)]
            pts = [v[0] for v in xs]
            traded = [v for v in xs if v[1]]
            row[pn] = {"days": len(xs), "traded": len(traded), "avg": round(st.mean(pts), 1), "sum": round(sum(pts)),
                       "win": round(sum(v[0] > 0 for v in traded) / max(1, len(traded)) * 100, 1),
                       "worst": round(min(pts)), "mae": round(st.mean(v[2] for v in traded), 1) if traded else None}
        out["variants"][name] = row
        print(f"\n■ {name}")
        for pn, x in row.items():
            print(f"   {pn:7s} {x['days']} 天、有做 {x['traded']} 天、每天平均 {x['avg']:+.1f} 點（合計 {x['sum']:+,}）、勝率 {x['win']}%、"
                  f"最差一天 {x['worst']:+,} 點、平均最大未實現虧損 {x['mae']} 點")
        if "2026-11-25" in res:
            v = res["2026-11-25"]
            print("   今天：" + "；".join(f"{'空' if t[3] < 0 else '多'} {T(t[1])} 進 {T(t[2])} 出 {t[0]:+.0f} 點（最大未實現 {t[4]:+.0f}）" for t in v[3]))
    # 進場時間分布（V0）
    tm = [(d, mr_trade(b, h, l, OR_M)) for d, b, h, l in days]
    buckets = {"09:15-09:30": (30, 45), "09:30-10:00": (45, 75), "10:00-10:30": (75, 105), "10:30-11:00": (105, 135), "11:00 後": (135, 999)}
    out["entryTime"] = {}
    print("\n現行規則（V0）進場時間分布：")
    for k, (a, z) in buckets.items():
        seg = []
        for pn, pf in (("2020-24", lambda d: d < "2025-01-01"), ("2025-", lambda d: d >= "2025-01-01")):
            xs = [t[0] for d_, t in tm if t and a <= t[1] < z and pf(d_)]
            if xs:
                seg.append(f"{pn} {len(xs)} 筆 平均 {st.mean(xs):+.1f} 點 勝率 {sum(x > 0 for x in xs) / len(xs) * 100:.0f}%")
                out["entryTime"].setdefault(k, {})[pn] = {"n": len(xs), "avg": round(st.mean(xs), 1)}
        print(f"  {k}：" + "｜".join(seg))
    (DATA / "research" / "tx_mr_exec.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
