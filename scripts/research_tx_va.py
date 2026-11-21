#!/usr/bin/env python3
"""
驗證「期望值交易法」（網路截圖整理的規則）在台指期上的效果——5 分 K、日盤、大台一口扣 3 點

規則（依截圖文字實作，影片細節無法取得，部分用合理近似）：
  1 測狀態：ATR14（5 分 K）在最近 200 根裡的百分位，分 0-25／26-50／51-75／76-100 四檔；
            「這種波動持續多久」用「同一檔已連續幾根」近似（新切換的不做）
  2 看趨勢：前一天價值區（1 分 K 成交量分布，以 10 點為一格，從成交最多的價位往外擴到含 70% 成交量；VAH／VAL）；
            成交量分布呈鐘形（成交最多的價位在前一天高低區間的中間 30%～70%）
  3 等訊號：
            E1 突破：5 分 K 收盤由下往上突破 VAH + k×ATR（k＝0、0.3、0.6），做空對稱（VAL）
            E2 回測吞沒：最近 12 根有 ≥70% 收在 VAH 之上，今天這根是多方吞沒（吃掉前一根黑 K）且收在 VAH 之上，做空對稱
  4 下單：停損在最近 3 根最低點下方 1 點（結構低點），目標 2 倍風險（1:2），13:40 前沒碰到就平倉；同時最多一筆
  5 其他：連贏之後的第一單不做；凱利公式＝勝率 − 輸率 ÷ 盈虧比
看：每一檔波動的期望值（R＝每筆損益 ÷ 停損距離；點數已扣 3 點）、2020-24／2025 後兩段是否一致
輸出 data/research/tx_va.json；用法：python scripts/research_tx_va.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = 3.0
BIN = 10
BUCKETS = ((0, 25, "低 0-25"), (25, 50, "中 26-50"), (50, 75, "高 51-75"), (75, 101, "極端 76-100"))


def five_min(b: dict) -> list[list[float]]:
    out = []
    for s in range(0, 300, 5):
        g = [b[m] for m in range(s, s + 5) if m in b]
        if g:
            out.append([s, g[0][0], max(x[1] for x in g), min(x[2] for x in g), g[-1][3], sum(x[4] for x in g)])
    return out


def value_area(b: dict):
    vol = {}
    for x in b.values():
        k = int(round(x[3] / BIN))
        vol[k] = vol.get(k, 0) + x[4]
    if not vol:
        return None
    tot = sum(vol.values())
    ks = sorted(vol)
    pi = ks.index(max(vol, key=vol.get))
    lo = hi = pi
    acc = vol[ks[pi]]
    while acc < 0.7 * tot and (lo > 0 or hi < len(ks) - 1):  # 從成交最多的價位往量大的那一邊擴，直到含 70% 成交量
        up = vol[ks[hi + 1]] if hi < len(ks) - 1 else -1
        dn = vol[ks[lo - 1]] if lo > 0 else -1
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    poc = ks[pi]
    lo, hi = ks[lo], ks[hi]
    H, L = max(x[1] for x in b.values()), min(x[2] for x in b.values())
    return {"vah": hi * BIN + BIN / 2, "val": lo * BIN - BIN / 2, "poc": poc * BIN, "bell": H > L and 0.3 <= (poc * BIN - L) / (H - L) <= 0.7}


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    ds = sorted(d for d, b in day.items() if len(b) >= 250)
    # 5 分 K 連續序列（跨日），ATR14 與 200 根百分位
    bars = []
    for d in ds:
        for x in five_min(day[d]):
            bars.append([d] + x)
    trs, atr = [], []
    for i, x in enumerate(bars):
        pc = bars[i - 1][5] if i else x[2]  # [日期, 分, 開, 高, 低, 收, 量]
        trs.append(max(x[3], pc) - min(x[4], pc))
        atr.append(st.mean(trs[-14:]))
    pct, age = [], []
    for i in range(len(bars)):
        w = atr[max(0, i - 199):i + 1]
        pct.append(sum(v <= atr[i] for v in w) / len(w) * 100)
    bk = [next(lab for a, b_, lab in BUCKETS if a <= p < b_) for p in pct]
    run = 0
    for i in range(len(bars)):
        run = run + 1 if i and bk[i] == bk[i - 1] else 1
        age.append(run)
    idx = {}
    for i, x in enumerate(bars):
        idx.setdefault(x[0], []).append(i)
    trades = []
    variants = [("E1 突破 k=0", "E1", 0.0), ("E1 突破 k=0.3", "E1", 0.3), ("E1 突破 k=0.6", "E1", 0.6), ("E2 回測吞沒", "E2", 0.0)]
    for vn, kind, k in variants:
        for di in range(1, len(ds)):
            d = ds[di]
            va = value_area(day[ds[di - 1]])
            if not va or d not in idx:
                continue
            ii = idx[d]
            pos = None
            for j, i in enumerate(ii):
                _, s, o, h, l, c, v = bars[i]
                if pos:
                    side, ent, stop, tgt, meta = pos
                    hit_s = (l <= stop) if side > 0 else (h >= stop)
                    hit_t = (h >= tgt) if side > 0 else (l <= tgt)
                    if hit_s or hit_t or s >= 290:
                        ex = stop if hit_s else tgt if hit_t else c  # 同一根都碰到時保守算停損
                        risk = abs(ent - stop)
                        pts = (ex - ent) * side - COST
                        trades.append({**meta, "pts": pts, "R": pts / risk if risk else 0})
                        pos = None
                    continue
                if s < 15 or s > 255 or j < 12:  # 09:00～13:00 進場
                    continue
                prev = bars[ii[j - 1]]
                sig = 0
                if kind == "E1":
                    lvl_u, lvl_d = va["vah"] + k * atr[i], va["val"] - k * atr[i]
                    if c > lvl_u >= prev[5]:
                        sig = 1
                    elif c < lvl_d <= prev[5]:
                        sig = -1
                else:
                    last = [bars[x][5] for x in ii[j - 12:j]]
                    up = sum(x > va["vah"] for x in last) >= 0.7 * len(last)
                    dn = sum(x < va["val"] for x in last) >= 0.7 * len(last)
                    if up and prev[5] < prev[2] and c > o and c >= prev[2] and o <= prev[5] and c > va["vah"]:
                        sig = 1
                    elif dn and prev[5] > prev[2] and c < o and c <= prev[2] and o >= prev[5] and c < va["val"]:
                        sig = -1
                if not sig:
                    continue
                lows = [bars[x][4] for x in ii[j - 2:j + 1]]
                highs = [bars[x][3] for x in ii[j - 2:j + 1]]
                stop = (min(lows) - 1) if sig > 0 else (max(highs) + 1)
                risk = abs(c - stop)
                if risk < 5:
                    continue
                pos = (sig, c, stop, c + sig * 2 * risk, {"v": vn, "date": d, "bucket": bk[i], "age": age[i], "bell": va["bell"], "risk": risk})
    out = {"cost": COST, "variants": {}}
    parts = (("2020-24", lambda t: t["date"] < "2025-01-01"), ("2025 後", lambda t: t["date"] >= "2025-01-01"))

    def summ(ts):
        if len(ts) < 20:
            return None
        w = sum(t["pts"] > 0 for t in ts) / len(ts)
        return {"n": len(ts), "win": round(w * 100, 1), "R": round(st.mean(t["R"] for t in ts), 3), "pts": round(st.mean(t["pts"] for t in ts), 1),
                "kelly": round((w - (1 - w) / 2) * 100, 1)}

    f = lambda s: f"n{s['n']:4d} 勝率 {s['win']:4.1f}% 每筆 {s['R']:+.3f}R（{s['pts']:+6.1f} 點）凱利 {s['kelly']:+.1f}%" if s else "樣本不足"  # noqa: E731
    print(f"台指期日盤 5 分 K，{ds[0]}～{ds[-1]}；盈虧比 1:2 → 不計成本的打平勝率 33.3%；每筆扣 {COST} 點")
    for vn, _, _ in variants:
        ts = [t for t in trades if t["v"] == vn]
        o = {"all": [summ([t for t in ts if pf(t)]) for _, pf in parts], "bucket": {}, "filtered": {}}
        print(f"\n■ {vn}")
        print(f"  全部            ｜{f(o['all'][0])}｜{f(o['all'][1])}")
        for _, _, lab in BUCKETS:
            v = [summ([t for t in ts if t["bucket"] == lab and pf(t)]) for _, pf in parts]
            o["bucket"][lab] = v
            print(f"  波動 {lab:9s}｜{f(v[0])}｜{f(v[1])}")
        for lab, flt in (("高波動 51-75 且持續 ≥ 12 根", lambda t: t["bucket"] == "高 51-75" and t["age"] >= 12),
                         ("高波動 51-75 且剛切換（< 12 根）", lambda t: t["bucket"] == "高 51-75" and t["age"] < 12),
                         ("高波動 51-75＋前一天鐘形", lambda t: t["bucket"] == "高 51-75" and t["bell"]),
                         ("高波動 51-75＋前一天非鐘形", lambda t: t["bucket"] == "高 51-75" and not t["bell"])):
            v = [summ([t for t in ts if flt(t) and pf(t)]) for _, pf in parts]
            o["filtered"][lab] = v
            print(f"  {lab:26s}｜{f(v[0])}｜{f(v[1])}")
        # 連贏之後的第一單不做
        kept, last_win = [], False
        for t in sorted(ts, key=lambda t: t["date"]):
            if last_win:
                last_win = False
                continue
            kept.append(t)
            last_win = t["pts"] > 0
        v = [summ([t for t in kept if pf(t)]) for _, pf in parts]
        o["skipAfterWin"] = v
        print(f"  贏一筆後跳過下一筆        ｜{f(v[0])}｜{f(v[1])}")
        out["variants"][vn] = o
    (DATA / "research" / "tx_va.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
