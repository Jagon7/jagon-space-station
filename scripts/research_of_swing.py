#!/usr/bin/env python3
"""
訂單流挑波段標的（B：用 1 分 K 推估主動買／賣，Bulk Volume Classification）
資料：data/research/intraday_1m（intraday_need ⑤：2025 起每天成交金額前 120 名連續）＋ yahoo_adj 日線（還原）
每檔每天：
  每分鐘報酬 Δ（收盤對前一分鐘收盤）、當天分鐘報酬標準差 σ → 主動買比例 = Φ(Δ/σ)，買量 = 量×Φ，賣量 = 量×(1−Φ)
  OI＝(買−賣)/(買+賣)；大單 OI＝只看量 ≥ 當天分鐘量中位數 3 倍的分鐘；只用 09:00～13:25（不含收盤集合競價）
訊號（第 t 天收盤後算，t+1 起持有）：近 N 天（5／10／20）金額加權 OI；
  每天在 universe 內分五組，看之後 5／10／20 天相對 universe 平均的超額報酬（日線還原收盤）
  另看：「價格沒漲但 OI 高」（近 N 天漲跌在 −3%～+3%）＝吸籌；大單 OI；和日線 CMF 對照
t＝依月份平均的 t 值；輸出 data/research/of_swing.json
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_intraday as ri  # noqa: E402

END = 265
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))  # noqa: E731


def day_flow(m: dict):
    ts = sorted(t for t in m if t <= END)
    if len(ts) < 60:
        return None
    rets, vols = [], []
    prev = None
    for t in ts:
        o, h, l, c, v = m[t]
        base = prev if prev is not None else o
        rets.append(((1 + c / 1e4) / (1 + base / 1e4) - 1) * 1e4)
        vols.append(v)
        prev = c
    sd = st.pstdev(rets) or 1.0
    med = st.median(vols) or 1
    B = S = Bb = Sb = 0.0
    for r, v in zip(rets, vols):
        p = Phi(r / sd)
        B += v * p
        S += v * (1 - p)
        if v >= 3 * med:
            Bb += v * p
            Sb += v * (1 - p)
    if B + S <= 0:
        return None
    return {"oi": (B - S) / (B + S), "big": (Bb - Sb) / (Bb + Sb) if Bb + Sb > 0 else 0.0, "vol": B + S}


def main() -> int:
    bars = ri.load_bars()
    flow = defaultdict(dict)   # code -> date -> feat
    for d, stocks in bars.items():
        for c, s in stocks.items():
            f = day_flow(s["m"])
            if f:
                flow[c][d] = f
    px = {}
    for f in (ri.DATA / "research" / "yahoo_adj").glob("*.json"):
        j = json.loads(f.read_text(encoding="utf-8"))
        if j["code"] in flow:
            px[j["code"]] = j["d"]
    rows = defaultdict(list)   # date -> [(code, feats, fwd)]
    for c, rs in px.items():
        dates = [r[0] for r in rs]
        adj = [r[6] for r in rs]
        fl = flow[c]
        for i in range(20, len(rs) - 20):
            d = dates[i]
            if d < "2025" or d not in fl:
                continue
            feat = {}
            for n in (5, 10, 20):
                win = [fl.get(dates[k]) for k in range(i - n + 1, i + 1)]
                have = [w for w in win if w]
                if len(have) < max(3, int(n * 0.75)):
                    continue
                tv = sum(w["vol"] for w in have)
                feat[f"oi{n}"] = sum(w["oi"] * w["vol"] for w in have) / tv
                feat[f"big{n}"] = sum(w["big"] * w["vol"] for w in have) / tv
                feat[f"r{n}"] = adj[i] / adj[i - n] - 1
            if not feat:
                continue
            fwd = {h: adj[i + h] / adj[i] - 1 for h in (5, 10, 20)}
            rows[d].append((c, feat, fwd))
    out = {}

    def test(name, key, h, filt=lambda f: True, step=None):
        step = step or h
        days = sorted(rows)[::step]
        qs = defaultdict(list)
        for d in days:
            xs = [x for x in rows[d] if key in x[1] and filt(x[1])]
            if len(xs) < 25:
                continue
            mu = st.mean(x[2][h] for x in xs)
            xs.sort(key=lambda x: x[1][key])
            n = len(xs)
            for q in range(5):
                part = xs[q * n // 5:(q + 1) * n // 5]
                qs[q].append((d[:7], st.mean(x[2][h] for x in part) - mu))
        if not qs:
            return
        res = {}
        for q in range(5):
            vals = [v for _, v in qs[q]]
            res[f"Q{q + 1}"] = round(st.mean(vals) * 100, 2)
        spread = [a[1] - b[1] for a, b in zip(qs[4], qs[0])]
        res["Q5-Q1"] = round(st.mean(spread) * 100, 2)
        res["win"] = round(sum(x > 0 for x in spread) / len(spread) * 100)
        res["n"] = len(spread)
        res["t"] = round(st.mean(spread) / (st.stdev(spread) / math.sqrt(len(spread))), 2) if len(spread) > 2 and st.stdev(spread) else None
        out[name] = res
        print(f"  {name}：" + " ".join(f"{k} {v:+.2f}%" if k.startswith("Q") else f"{k} {v}" for k, v in res.items()))

    print(f"■ 訂單流（1 分 K 推估）挑波段：{sum(len(v) for v in rows.values())} 檔×日，{len(rows)} 天")
    for n in (5, 10, 20):
        for h in (5, 10, 20):
            test(f"OI{n} → 之後 {h} 天", f"oi{n}", h)
    for n in (5, 20):
        test(f"大單 OI{n} → 之後 10 天", f"big{n}", 10)
        test(f"OI{n} 價格沒動（±3%）→ 之後 10 天", f"oi{n}", 10, lambda f, n=n: abs(f[f"r{n}"]) <= 0.03)
        test(f"（對照）近 {n} 天報酬 → 之後 10 天", f"r{n}", 10)
    (ri.DATA / "research" / "of_swing.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
