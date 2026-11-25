#!/usr/bin/env python3
"""
台指期當日型態研究：今天比較適合突破（BO）還是均值回歸（MR）？

資料：data/futures/day/（日盤 1 分 K）、data/futures/night/（夜盤）、data/intel/us_events.json
開盤區間 OR＝08:45～09:15（前 30 分鐘）；09:15 之後每天各做一筆：
  BO：先突破 OR 高點做多（先跌破 OR 低點做空），停損在 OR 另一側，13:30 出場
  MR：09:15～09:30 先碰到 OR 高點做空（先碰到 OR 低點做多），目標 OR 中間，停損＝OR 外再 0.5 個 OR 寬度，13:30 出場；
      09:30 前都沒碰到就不做；一天只做一筆，停利或停損後另一邊被碰到也不做
  （兩個都扣 COST 點成本；09:15 前已經突破的不算，從 09:15 收盤價開始看）
  BO 日＝BO 損益 > MR 損益
指標（開盤前可知）：跳空／ATR、開盤在昨天區間外、夜盤振幅與單邊程度、昨天振幅（窄幅）、昨天是不是趨勢日、波動水準、前一晚美國事件、結算日
指標（09:15 可知）：OR 寬度／ATR、跳空 30 分鐘內有沒有回補、前 30 分鐘穿越 VWAP 次數、前 30 分鐘量能／20 日同時段、09:15 收在 OR 的位置
輸出 data/futures/regime_research.json；用法：python scripts/research_tx_regime.py [--split 2025-01-01]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OR_M = 30          # 開盤區間分鐘數（08:45～09:15）
EXIT_M = 285       # 13:30
COST = 3.0         # 點（手續費＋稅＋滑價，大台一口來回約 2～3 點）
MR_LAST_FROM = "2026-11-26"  # 這天起的訊號才套用 MR 進場期限（之前的復盤紀錄用舊規則：不限時）
MR_LAST = 44       # MR 只在 09:15～09:29 第一次碰到邊界才做（scripts/research_tx_mr_exec.py：09:30 以後才碰到的兩段都虧）


def load_dir(d: Path) -> dict:
    out = {}
    for f in sorted(d.glob("20*.json")) if d.exists() else []:
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            out[k] = {b[0]: b[1:] for b in v["bars"]}
    return out


def vwap_path(bars: dict, upto: int):
    pv = vol = 0.0
    out = []
    for m in range(0, upto + 1):
        b = bars.get(m)
        if b:
            tp = (b[1] + b[2] + b[3]) / 3
            pv += tp * max(b[4], 1)
            vol += max(b[4], 1)
        out.append(pv / vol if vol else None)
    return out


def simulate(bars: dict, orh: float, orl: float, mr_last: int | None = None):
    """09:15 之後：BO 與 MR 各一筆的損益（點）；mr_last：MR 最晚進場分鐘（None＝MR_LAST；舊規則不限時用 EXIT_M）"""
    mr_last = MR_LAST if mr_last is None else mr_last
    w = orh - orl
    mid = (orh + orl) / 2
    bo = mr = None
    bo_pos = mr_pos = None  # (方向, 進場價, 停損, 目標)
    last = None
    for m in range(OR_M, EXIT_M + 1):
        b = bars.get(m)
        if not b:
            continue
        o, h, lo, c = b[0], b[1], b[2], b[3]
        last = c
        # BO
        if bo is None and bo_pos is None:
            if h > orh:
                bo_pos = (1, max(o, orh), orl)
            elif lo < orl:
                bo_pos = (-1, min(o, orl), orh)
        elif bo is None and bo_pos is not None:
            d, ent, stop = bo_pos
            if (d > 0 and lo <= stop) or (d < 0 and h >= stop):
                bo = (stop - ent) * d
        # MR（09:30 前沒碰到邊界就不做）
        if mr is None and mr_pos is None and m <= mr_last:
            if h >= orh:
                mr_pos = (-1, max(o, orh), orh + 0.5 * w, mid)
            elif lo <= orl:
                mr_pos = (1, min(o, orl), orl - 0.5 * w, mid)
        elif mr is None and mr_pos is not None:
            d, ent, stop, tgt = mr_pos
            if (d > 0 and lo <= stop) or (d < 0 and h >= stop):
                mr = (stop - ent) * d
            elif (d > 0 and h >= tgt) or (d < 0 and lo <= tgt):
                mr = (tgt - ent) * d
    if bo is None and bo_pos is not None and last is not None:
        bo = (last - bo_pos[1]) * bo_pos[0]
    if mr is None and mr_pos is not None and last is not None:
        mr = (last - mr_pos[1]) * mr_pos[0]
    return (bo - COST if bo is not None else 0.0), (mr - COST if mr is not None else 0.0), bo_pos is not None, mr_pos is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="2025-01-01", help="之前＝建模，之後＝驗證")
    a = ap.parse_args()
    day = load_dir(DATA / "futures" / "day")
    night = load_dir(DATA / "futures" / "night")
    ev = json.loads((DATA / "intel" / "us_events.json").read_text(encoding="utf-8")).get("events", []) if (DATA / "intel" / "us_events.json").exists() else []
    ev_nights = {}
    for e in ev:
        t = datetime.fromisoformat(e["t"])
        nd = (t.date() if t.hour >= 15 else t.date() - timedelta(days=1)).isoformat()
        ev_nights.setdefault(nd, set()).add(e["key"])
    dates = sorted(d for d, b in day.items() if len(b) >= 250 and OR_M in b)
    rows = []
    hist = []  # (日期, 高, 低, 收, 開, 效率)
    or_vol_hist = []
    for d in dates:
        bars = day[d]
        ms = sorted(bars)
        o = bars[ms[0]][0]
        hi = max(b[1] for b in bars.values())
        lo = min(b[2] for b in bars.values())
        cl = bars[ms[-1]][3]
        orb = [bars[m] for m in range(0, OR_M) if m in bars]
        if len(hist) >= 20 and orb:
            prev = hist[-1]
            atr = st.mean(h[1] - h[2] for h in hist[-20:])
            orh, orl = max(b[1] for b in orb), min(b[2] for b in orb)
            orv = sum(b[4] for b in orb)
            p915 = orb[-1][3]
            vw = vwap_path(bars, OR_M - 1)
            crosses = sum(1 for m in range(1, OR_M) if bars.get(m) and bars.get(m - 1) and vw[m] and vw[m - 1]
                          and (bars[m][3] - vw[m]) * (bars[m - 1][3] - vw[m - 1]) < 0)
            filled = any(b[2] <= prev[3] <= b[1] for b in orb)
            nk = max((k for k in night if k < d), default=None)
            nb = night.get(nk) if nk and (date.fromisoformat(d) - date.fromisoformat(nk)).days <= 4 else None
            if nb:
                n_hi, n_lo = max(b[1] for b in nb.values()), min(b[2] for b in nb.values())
                n_o, n_c = nb[min(nb)][0], nb[max(nb)][3]
                n_rng = (n_hi - n_lo) / atr
                n_dir = abs(n_c - n_o) / (n_hi - n_lo) if n_hi > n_lo else 0
            else:
                n_rng = n_dir = None
            bo, mr, bo_tr, mr_tr = simulate(bars, orh, orl)
            eff = abs(cl - p915) / (hi - lo) if hi > lo else 0
            f = {
                "date": d, "bo": round(bo, 1), "mr": round(mr, 1), "boDay": bo > mr, "eff": round(eff, 3),
                "gapATR": round((o - prev[3]) / atr, 3),
                "absGapATR": round(abs(o - prev[3]) / atr, 3),
                "openOutside": o > prev[1] or o < prev[2],
                "prevRangeATR": round((prev[1] - prev[2]) / atr, 3),
                "nr7": (prev[1] - prev[2]) <= min(h[1] - h[2] for h in hist[-7:]),
                "prevEff": round(prev[5], 3),
                "atrPct": round(atr / prev[3] * 100, 3),
                "nightRangeATR": round(n_rng, 3) if n_rng is not None else None,
                "nightDir": round(n_dir, 3) if n_dir is not None else None,
                "usEvent": bool(ev_nights.get(nk)) if nk else False,
                "settle": date.fromisoformat(d).weekday() == 2 and 15 <= date.fromisoformat(d).day <= 21,
                "orATR": round((orh - orl) / atr, 3),
                "gapFilled30": filled,
                "vwapCross30": crosses,
                "rvol30": round(orv / st.mean(or_vol_hist[-20:]), 3) if len(or_vol_hist) >= 20 and st.mean(or_vol_hist[-20:]) else None,
                "pos915": round((p915 - orl) / (orh - orl), 3) if orh > orl else 0.5,
            }
            rows.append(f)
            or_vol_hist.append(orv)
        elif orb:
            or_vol_hist.append(sum(b[4] for b in orb))
        hist.append((d, hi, lo, cl, o, abs(cl - o) / (hi - lo) if hi > lo else 0))

    def summary(rs):
        if not rs:
            return {"n": 0}
        return {"n": len(rs), "boDay": round(sum(r["boDay"] for r in rs) / len(rs) * 100, 1),
                "bo": round(st.mean(r["bo"] for r in rs), 1), "mr": round(st.mean(r["mr"] for r in rs), 1),
                "boWin": round(sum(r["bo"] > 0 for r in rs) / len(rs) * 100, 1), "mrWin": round(sum(r["mr"] > 0 for r in rs) / len(rs) * 100, 1)}

    feats = ["absGapATR", "gapATR", "prevRangeATR", "prevEff", "atrPct", "nightRangeATR", "nightDir", "orATR", "vwapCross30", "rvol30", "pos915"]
    flags = ["openOutside", "nr7", "usEvent", "settle", "gapFilled30"]
    train = [r for r in rows if r["date"] < a.split]
    test = [r for r in rows if r["date"] >= a.split]
    res = {"all": summary(rows), "train": summary(train), "test": summary(test), "from": rows[0]["date"] if rows else None,
           "to": rows[-1]["date"] if rows else None, "split": a.split, "cost": COST, "features": {}, "flags": {}}
    for k in feats:
        xs = sorted(r[k] for r in train if r[k] is not None)
        if len(xs) < 30:
            continue
        q1, q2 = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        out = {"cut": [q1, q2]}
        for name, rs in (("train", train), ("test", test)):
            rs = [r for r in rs if r[k] is not None]
            out[name] = [summary([r for r in rs if r[k] <= q1]), summary([r for r in rs if q1 < r[k] <= q2]), summary([r for r in rs if r[k] > q2])]
        res["features"][k] = out
    for k in flags:
        res["flags"][k] = {name: [summary([r for r in rs if not r[k]]), summary([r for r in rs if r[k]])] for name, rs in (("train", train), ("test", test))}
    (DATA / "futures" / "regime_rows.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    (DATA / "futures" / "regime_research.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("all", "train", "test", "from", "to")}, ensure_ascii=False))
    for k, v in res["features"].items():
        print(f"{k:14s} cut {v['cut']}")
        for name in ("train", "test"):
            print("   ", name, " | ".join(f"n={s['n']} BO日{s.get('boDay')}% BO{s.get('bo')} MR{s.get('mr')}" for s in v[name]))
    for k, v in res["flags"].items():
        print(f"{k:14s}", " || ".join(f"{name}: 否 BO日{v[name][0].get('boDay')}% BO{v[name][0].get('bo')} MR{v[name][0].get('mr')} n{v[name][0]['n']} / 是 BO日{v[name][1].get('boDay')}% BO{v[name][1].get('bo')} MR{v[name][1].get('mr')} n{v[name][1]['n']}" for name in ("train", "test")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
