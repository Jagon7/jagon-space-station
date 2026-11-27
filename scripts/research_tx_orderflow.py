#!/usr/bin/env python3
"""
台指期 × 股票訂單流：前 100 大股票的主動買賣（永豐逐筆，data/orderflow/features.json）能不能預測台指期

全市場訂單流（成交金額加權）：
  NET 全天主動淨額比、BIG 大單（單筆 ≥ 500 萬）淨額比、O30 09:00～09:30 淨額比、L30 13:00～13:25 淨額比；另看台積電單獨
預測目標（台指期近月，data/futures/day、night）：
  同一天：O30 → 09:30～13:30 台指期報酬（盤中延續或反轉）
  尾盤：L30（13:25 就知道）→ 13:25～13:45 台指期、當晚夜盤（13:45→隔天 05:00）、隔天日盤開盤跳空、隔天日盤（開→收）
  隔天型態：NET／BIG／L30 → 隔天 BO、MR 損益（data/futures/regime_rows.json）
統計：三分位（用前半段資料決定門檻）比較高組 − 低組，前半／後半兩段都同方向才算；另列相關係數與 t
限制：訂單流只從 2026/5 開始（約 130 天），結論只能當初步
結果（2026/5～11，130 天）：全天淨額、大單淨額 → 夜盤、隔天跳空 t 約 2.3，但控制「當天台指漲跌」後 t 只剩 0.7～0.8，
  台指漲跌本身 t 3～4 → 訂單流沒有額外資訊，只是反映當天漲跌（動能）；開盤 30 分（全市場、台積電）對盤中台指都沒預測力
輸出 data/research/tx_orderflow.json；用法：python scripts/research_tx_orderflow.py
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_tx_regime as rr  # noqa: E402


def agg(day: dict):
    tot = sum(v[0] for v in day.values() if v and v[0])
    out = {}
    for k, i in (("NET", 1), ("BIG", 2), ("O30", 3), ("L30", 4)):
        xs = [(v[i], v[0]) for v in day.values() if v and v[0] and v[i] is not None]
        w = sum(a for _, a in xs)
        out[k] = sum(x * a for x, a in xs) / w * 100 if w else None
    t = day.get("2330")
    if t:
        out["TSMC_O30"], out["TSMC_L30"] = t[3] * 100 if t[3] is not None else None, t[4] * 100 if t[4] is not None else None
    out["amt"] = tot / 1e8
    return out


def px(bars: dict, m: int):
    ks = [k for k in bars if k <= m]
    return bars[max(ks)][3] if ks else None


def main():
    F = json.loads((DATA / "orderflow" / "features.json").read_text(encoding="utf-8"))["days"]
    day = rr.load_dir(DATA / "futures" / "day")
    night = rr.load_dir(DATA / "futures" / "night")
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    tdays = sorted(d for d in day if len(day[d]) >= 250)
    rows = []
    for d in sorted(F):
        if d not in tdays or len(F[d]) < 50:
            continue
        i = tdays.index(d)
        nxt = tdays[i + 1] if i + 1 < len(tdays) else None
        b = day[d]
        f = agg(F[d])
        p930, p1330, p1325, p1345 = px(b, 45), px(b, 285), px(b, 280), px(b, 299)
        y = {"in_930_1330": (p1330 / p930 - 1) * 100 if p930 and p1330 else None,
             "tail_1325_1345": (p1345 / p1325 - 1) * 100 if p1325 and p1345 else None}
        nb = night.get(d)
        if nb and p1345:
            y["night"] = (nb[max(nb)][3] / p1345 - 1) * 100
        if nxt:
            nbx = day[nxt]
            o = nbx[min(nbx)][0]
            y["gap"] = (o / p1345 - 1) * 100 if p1345 else None
            y["next_o2c"] = (px(nbx, 299) / o - 1) * 100
            if nxt in reg:
                y["next_bo"], y["next_mr"] = reg[nxt]["bo"], reg[nxt]["mr"]
        rows.append({"d": d, "f": f, "y": y})
    n = len(rows)
    half = rows[n // 2]["d"]
    print(f"{rows[0]['d']}～{rows[-1]['d']}，{n} 天（前半／後半以 {half} 分）")
    tests = [("O30", "in_930_1330"), ("TSMC_O30", "in_930_1330"),
             ("L30", "tail_1325_1345"), ("L30", "night"), ("L30", "gap"), ("L30", "next_o2c"), ("TSMC_L30", "gap"),
             ("NET", "night"), ("NET", "gap"), ("NET", "next_o2c"), ("BIG", "gap"), ("BIG", "next_o2c"),
             ("NET", "next_bo"), ("NET", "next_mr"), ("L30", "next_bo"), ("L30", "next_mr")]
    out = {"n": n, "from": rows[0]["d"], "to": rows[-1]["d"], "tests": []}
    for fk, yk in tests:
        xs = [(r["f"].get(fk), r["y"].get(yk), r["d"]) for r in rows if r["f"].get(fk) is not None and r["y"].get(yk) is not None]
        if len(xs) < 40:
            continue
        tr = sorted(x for x, _, d in xs if d < half)
        c1, c2 = tr[len(tr) // 3], tr[2 * len(tr) // 3]
        res = {}
        for lab, sel in (("前半", lambda d: d < half), ("後半", lambda d: d >= half), ("全部", lambda d: True)):
            g = [(x, yv) for x, yv, d in xs if sel(d)]
            lo = [yv for x, yv in g if x <= c1]
            hi = [yv for x, yv in g if x > c2]
            if len(lo) < 5 or len(hi) < 5:
                continue
            diff = st.mean(hi) - st.mean(lo)
            se = math.sqrt(st.variance(hi) / len(hi) + st.variance(lo) / len(lo))
            res[lab] = {"lo": round(st.mean(lo), 3), "hi": round(st.mean(hi), 3), "diff": round(diff, 3), "t": round(diff / se, 2) if se else None,
                        "corr": round(st.correlation([a for a, _ in g], [b for _, b in g]), 3), "n": len(g)}
        ok = "前半" in res and "後半" in res and res["前半"]["diff"] * res["後半"]["diff"] > 0 and abs(res["全部"]["t"] or 0) >= 2
        out["tests"].append({"factor": fk, "target": yk, "cut": [c1, c2], "res": res, "consistent": ok})
        unit = "點" if yk in ("next_bo", "next_mr") else "%"
        print(f"{'✓' if ok else ' '} {fk:9s} → {yk:15s}：" + "｜".join(f"{lab} 低 {v['lo']:+.3f} 高 {v['hi']:+.3f}{unit}（t {v['t']}，相關 {v['corr']}）" for lab, v in res.items()))
    (DATA / "research" / "tx_orderflow.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
