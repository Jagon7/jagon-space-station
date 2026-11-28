#!/usr/bin/env python3
"""
台指期日盤當沖：賺賠比 2:1（停利＝2 × 停損），一次最多 1 口、出場後才能再進場、每天筆數不限

資料：data/futures/day（台指期近月 1 分 K，2020/3 起）；data/futures/regime_rows.json（09:15 規則因子）；tx_regime_review.decide（線上規則）
交易：訊號在 1 分 K 收盤判斷，下一分鐘開盤進場；之後每分鐘檢查：同一分鐘同時碰到停損與停利 → 算停損（保守）；
      13:30 沒碰到就平倉；12:30 後不再進新單；每筆扣 COST 點
停損大小：固定點數 SL_PTS、或波動倍數 SL_ATR × ATR20（前 20 天日盤振幅平均）；停利＝2 × 停損
訊號：
  ORB     收盤由下往上穿過開盤區間（08:45～09:15）高點做多、由上往下穿過低點做空（可重複）
  DON15／DON30  收盤突破前 15／30 分鐘最高（做多）／最低（做空）
  FADE    碰到開盤區間高點做空、低點做多（均值回歸，可重複）
  VWAP    收盤由下往上穿過 VWAP + 0.2×ATR20 做多、由上往下穿過 VWAP − 0.2×ATR20 做空
  REGIME  09:15 線上規則：BO 日做 ORB、MR 日做 FADE、不做的日子不做
  GAPDIR  只做跟開盤跳空同方向的 DON15 訊號（開高只做多、開低只做空）
  REGIME_WF 同 REGIME，但 09:15 規則的參數每年只用「那年以前最近 500 天」選（跟線上每週調參同一套網格），沒有偷看未來
  RANDOM  每分鐘 5% 機率隨機進場、方向隨機（對照，看停損大小本身的期望值）
資料：research_tx_regime.load_dir 會清掉一分鐘就回來的錯誤成交、結算日 13:29 平倉（13:30 後是次月價）
選擇：停損大小與訊號只用 2020-22 選，看 2023-24、2025+
輸出 data/research/tx_scalp.json；用法：python scripts/research_tx_scalp.py
"""
from __future__ import annotations

import json
import os
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_tx_regime as rr  # noqa: E402
import tx_regime_review as trv  # noqa: E402

COST = 3.0
RR = 2.0
OR_M, LAST_ENTRY, EXIT = 30, 225, 285      # 09:15、12:30、13:30（分鐘，08:45＝0）
SL_PTS = [10, 15, 20, 30, 40, 50, 60, 80, 100]
SL_ATR = [0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75]
PARTS = (("2020-22", "2020", "2023"), ("2023-24", "2023", "2025"), ("2025+", "2025", "2100"))


def signals(bars: dict, kind: str, atr: float, plan, gap: float, rnd: random.Random):
    """回傳 {分鐘: 方向}（在該分鐘收盤判斷）"""
    ms = sorted(bars)
    orb = [bars[m] for m in range(OR_M) if m in bars]
    if len(orb) < 20:
        return {}
    orh, orl = max(b[1] for b in orb), min(b[2] for b in orb)
    out = {}
    pv = vol = 0.0
    prev_c = None
    vw_prev = None
    for m in ms:
        if m > LAST_ENTRY:
            break
        o, h, lo, c, v = bars[m][:5]
        pv += (h + lo + c) / 3 * v
        vol += v
        vw = pv / vol if vol else c
        if m >= OR_M and prev_c is not None:
            if kind in ("ORB", "REGIME_BO"):
                if c > orh >= prev_c:
                    out[m] = 1
                elif c < orl <= prev_c:
                    out[m] = -1
            elif kind in ("FADE", "REGIME_MR"):
                if h >= orh and prev_c < orh:
                    out[m] = -1
                elif lo <= orl and prev_c > orl:
                    out[m] = 1
            elif kind in ("DON15", "DON30", "GAPDIR"):
                n = 30 if kind == "DON30" else 15
                win = [bars[k] for k in range(m - n, m) if k in bars]
                if len(win) >= n - 2:
                    hh, ll = max(b[1] for b in win), min(b[2] for b in win)
                    if c > hh:
                        out[m] = 1
                    elif c < ll:
                        out[m] = -1
                    if kind == "GAPDIR" and m in out and out[m] * gap <= 0:
                        del out[m]
            elif kind == "VWAP":
                band = 0.2 * atr
                if vw_prev is not None:
                    if c > vw + band and prev_c <= vw_prev + band:
                        out[m] = 1
                    elif c < vw - band and prev_c >= vw_prev - band:
                        out[m] = -1
            elif kind == "RANDOM":
                if rnd.random() < 0.05:
                    out[m] = rnd.choice((1, -1))
        prev_c, vw_prev = c, vw
    return out


REASON = defaultdict(int)


def run_day(bars: dict, sig: dict, sl: float):
    """依序執行訊號（一次 1 口）；回傳每筆點數"""
    tp = RR * sl
    trades = []
    pos = None   # (方向, 進場價, 進場分鐘)
    ms = sorted(bars)
    pending = None
    for m in ms:
        if m > EXIT:
            break
        o, h, lo, c = bars[m][:4]
        if pos is None and pending is not None and m <= LAST_ENTRY + 1:
            pos = (pending, o, m)
            pending = None
        if pos is not None:
            d, e, _ = pos
            stop, take = e - d * sl, e + d * tp
            hit_sl = lo <= stop if d > 0 else h >= stop
            hit_tp = h >= take if d > 0 else lo <= take
            if hit_sl:
                trades.append(-sl - COST)
                REASON["sl"] += 1
                pos = None
            elif hit_tp:
                trades.append(tp - COST)
                REASON["tp"] += 1
                pos = None
            elif m == EXIT:
                trades.append((c - e) * d - COST)
                REASON["time"] += 1
                pos = None
        if pos is None and m in sig and m <= LAST_ENTRY:
            pending = sig[m]
    if pos is not None:
        last = bars[max(k for k in ms if k <= EXIT)][3]
        trades.append((last - pos[1]) * pos[0] - COST)
    return trades


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    p = trv.params()["current"]
    dates = sorted(d for d, b in day.items() if len(b) >= 250)
    hist, atr = [], {}
    for d in dates:
        b = day[d]
        if len(hist) >= 20:
            atr[d] = st.mean(hist[-20:])
        hist.append(max(x[1] for x in b.values()) - min(x[2] for x in b.values()))
    dates = [d for d in dates if d in atr and d in reg]
    rnd = random.Random(7)
    kinds = ["ORB", "DON15", "DON30", "FADE", "VWAP", "REGIME", "REGIME_WF", "GAPDIR", "RANDOM"]
    # 逐年選 09:15 規則參數（只用之前的資料）
    import itertools
    allrows = [reg[d] for d in sorted(reg)]
    wf = {}
    for y in sorted({d[:4] for d in dates}):
        prior = [r for r in allrows if r["date"] < f"{y}-01-01"][-trv.TUNE_DAYS:]
        if len(prior) < 120:
            wf[y] = dict(trv.DEFAULT)
        else:
            wf[y] = max((dict(zip(trv.GRID, c)) for c in itertools.product(*trv.GRID.values())),
                        key=lambda q: trv.evaluate(prior, q)["avg"])
        print(f"  {y} 年用的 09:15 規則參數：{wf[y]}（只用 {y} 年以前的資料選）")
    sigs = {}
    for k in kinds:
        sigs[k] = {}
        for d in dates:
            plan = trv.decide(reg[d], p)[1]
            if k == "REGIME_WF":
                plan = trv.decide(reg[d], {**wf[d[:4]], "overrides": []})[1]
            if k in ("REGIME", "REGIME_WF"):
                s = signals(day[d], "REGIME_BO", atr[d], plan, 0, rnd) if plan == "BO" else signals(day[d], "REGIME_MR", atr[d], plan, 0, rnd) if plan == "MR" else {}
            else:
                s = signals(day[d], k, atr[d], plan, reg[d]["gapATR"], rnd)
            sigs[k][d] = s
    out = {"cost": COST, "rr": RR, "res": []}
    print(f"{dates[0]}～{dates[-1]}，{len(dates)} 天；賺賠比 {RR:g}:1、每筆扣 {COST:g} 點")
    for k in kinds:
        for mode, grid in (("pts", SL_PTS), ("atr", SL_ATR)):
            for g in grid:
                line = {}
                for lab, a, b in PARTS:
                    ds = [d for d in dates if a <= d < b]
                    tr, per = [], []
                    for d in ds:
                        sl = g if mode == "pts" else g * atr[d]
                        t = run_day(day[d], sigs[k][d], sl)
                        tr += [x / sl for x in t] if mode == "atr" else t      # atr 模式另外記 R 倍數
                        per.append(sum(t))
                    if not tr:
                        continue
                    win = sum(1 for x in tr if x > 0) / len(tr) * 100
                    line[lab] = {"trades": len(tr), "perDay": round(len(tr) / len(ds), 2), "win": round(win, 1),
                                 "avg": round(st.mean(tr), 3), "dayPts": round(st.mean(per), 1)}
                out["res"].append({"kind": k, "mode": mode, "sl": g, "parts": line})
    # 2020-22 選最好的（每天平均點數）
    best = sorted(out["res"], key=lambda r: -(r["parts"].get("2020-22", {}).get("dayPts") or -1e9))
    print("\n依 2020-22 每天平均點數排名前 15（停損：點數或 ×ATR20；停利＝2 倍）：")
    for r in best[:15]:
        unit = "點" if r["mode"] == "pts" else "×ATR"
        print(f"  {r['kind']:7s} 停損 {r['sl']:g}{unit}：" + "｜".join(
            f"{lab} 每天 {v['dayPts']:+.1f} 點（{v['perDay']:.1f} 筆／天，勝率 {v['win']:.0f}%）" for lab, v in r["parts"].items()))
    print("\n各訊號的最佳停損（依 2020-22）與三段結果：")
    out["bestByKind"] = {}
    for k in kinds:
        rs = [r for r in out["res"] if r["kind"] == k]
        b = max(rs, key=lambda r: r["parts"].get("2020-22", {}).get("dayPts") or -1e9)
        out["bestByKind"][k] = b
        unit = "點" if b["mode"] == "pts" else "×ATR"
        print(f"  {k:7s} 停損 {b['sl']:g}{unit}（停利 {b['sl'] * RR:g}{unit}）：" + "｜".join(
            f"{lab} 每天 {v['dayPts']:+.1f} 點、{v['perDay']:.1f} 筆、勝率 {v['win']:.0f}%" for lab, v in b["parts"].items()))
    # 最佳組合的細節：每年、最大回落、出場原因
    for k in ("REGIME", "REGIME_WF"):
        for g in (0.2, 0.3, 0.4, 0.5):
            REASON.clear()
            per_year, eq, pk, mdd, tot = defaultdict(list), 0.0, 0.0, 0.0, []
            for d in dates:
                t = run_day(day[d], sigs[k][d], g * atr[d])
                per_year[d[:4]].append(sum(t))
                tot += t
                eq += sum(t)
                pk = max(pk, eq)
                mdd = max(mdd, pk - eq)
            n = sum(REASON.values()) or 1
            print(f"  {k} 停損 {g}×ATR：每年每天平均點數 " + "、".join(f"{y} {st.mean(v):+.1f}" for y, v in sorted(per_year.items()))
                  + f"｜累計 {eq:+,.0f} 點、最大回落 {mdd:,.0f} 點｜出場：停利 {REASON['tp'] / n * 100:.0f}%、停損 {REASON['sl'] / n * 100:.0f}%、13:30 {REASON['time'] / n * 100:.0f}%")
    (DATA / "research" / "tx_scalp.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
