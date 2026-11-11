#!/usr/bin/env python3
"""
訂單流研究（第一輪）：data/orderflow/features.json（成交金額前 100 名、每天的主動買賣特徵）× data/daily 收盤／開盤

每天把股票依因子分成五組（Q1 最低～Q5 最高），看各組之後的報酬：
  A. 全天主動淨額比 → 隔天報酬（收→收）、5 天報酬
  B. 大單（單筆 ≥ 500 萬）淨額比 → 隔天、5 天
  C. 開盤 30 分淨額比 → 當天 09:30 → 收盤
  D. 尾盤 30 分淨額比 → 隔天開盤跳空（收→開）
指標：Q5−Q1 每天的報酬差平均、t 值（以天為樣本）、Q5 贏 Q1 的天數比例、Rank IC（每天的 Spearman 相關）平均與 t 值
另外對照「當天漲跌幅」本身當因子，分辨訂單流是不是只是反映當天漲跌（短期反轉／動能）
輸出 data/orderflow/research.json
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
F = {k: i for i, k in enumerate(["amt", "net", "bigNet", "open30Net", "last30Net", "p0930", "p1325", "close"])}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va and vb else None


def tstat(xs):
    n = len(xs)
    if n < 3:
        return None
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m / (sd / math.sqrt(n)) if sd else None


def study(days, factor, target, min_n=50):
    """days: [(日期, {代號: (因子值, 報酬)})]"""
    qret = [[] for _ in range(5)]
    spreads, ics = [], []
    for d, m in days:
        pts = [(f, r) for f, r in m.values() if f is not None and r is not None]
        if len(pts) < min_n:
            continue
        pts.sort(key=lambda x: x[0])
        n = len(pts)
        groups = [pts[i * n // 5:(i + 1) * n // 5] for i in range(5)]
        means = [sum(r for _, r in g) / len(g) for g in groups]
        for i in range(5):
            qret[i].append(means[i])
        spreads.append(means[4] - means[0])
        ic = spearman([p[0] for p in pts], [p[1] for p in pts])
        if ic is not None:
            ics.append(ic)
    if not spreads:
        return None
    avg = lambda xs: sum(xs) / len(xs)  # noqa: E731
    return {"factor": factor, "target": target, "days": len(spreads),
            "q": [round(avg(x) * 100, 3) for x in qret],
            "spread": round(avg(spreads) * 100, 3), "t": round(tstat(spreads) or 0, 2),
            "win": round(sum(s > 0 for s in spreads) / len(spreads) * 100, 1),
            "ic": round(avg(ics), 4), "icT": round(tstat(ics) or 0, 2)}


def main():
    feat = load(DATA / "orderflow" / "features.json")["days"]
    daily = {}
    for p in sorted((DATA / "daily").glob("20*.json")):
        d = load(p)
        if d.get("q"):
            daily[d["date"]] = d["q"]
    dates = [d for d in sorted(feat) if d in daily]
    alld = sorted(daily)
    nxt = {d: alld[i + 1] for i, d in enumerate(alld[:-1])}
    nxt5 = {d: alld[i + 5] for i, d in enumerate(alld[:-5])}
    prev = {alld[i + 1]: d for i, d in enumerate(alld[:-1])}

    def close(d, c):
        v = daily.get(d, {}).get(c)
        return v[5] if v and v[5] else None

    def opn(d, c):
        v = daily.get(d, {}).get(c)
        return v[2] if v and v[2] else None

    def ret(a, b):
        return b / a - 1 if a and b else None

    sets = {k: [] for k in ("net1", "net5", "big1", "big5", "o30", "l30gap", "chg1", "chg5", "o30chg")}
    for d in dates:
        f = feat[d]
        rows = {k: {} for k in sets}
        for c, x in f.items():
            c0 = close(d, c)
            r1 = ret(c0, close(nxt.get(d), c)) if d in nxt else None
            r5 = ret(c0, close(nxt5.get(d), c)) if d in nxt5 else None
            gap = ret(c0, opn(nxt.get(d), c)) if d in nxt else None
            intra = ret(x[F["p0930"]], c0)
            today = ret(close(prev.get(d), c), c0) if d in prev else None
            open30chg = ret(opn(d, c), x[F["p0930"]])
            rows["net1"][c] = (x[F["net"]], r1)
            rows["net5"][c] = (x[F["net"]], r5)
            rows["big1"][c] = (x[F["bigNet"]], r1)
            rows["big5"][c] = (x[F["bigNet"]], r5)
            rows["o30"][c] = (x[F["open30Net"]], intra)
            rows["l30gap"][c] = (x[F["last30Net"]], gap)
            rows["chg1"][c] = (today, r1)
            rows["chg5"][c] = (today, r5)
            rows["o30chg"][c] = (open30chg, intra)
        for k in sets:
            sets[k].append((d, rows[k]))
    spec = [("net1", "全天主動淨額比", "隔天報酬（收→收）"), ("net5", "全天主動淨額比", "5 天報酬"),
            ("big1", "大單淨額比", "隔天報酬"), ("big5", "大單淨額比", "5 天報酬"),
            ("o30", "開盤 30 分淨額比", "當天 09:30→收盤"), ("l30gap", "尾盤 30 分淨額比", "隔天開盤跳空"),
            ("chg1", "（對照）當天漲跌幅", "隔天報酬"), ("chg5", "（對照）當天漲跌幅", "5 天報酬"),
            ("o30chg", "（對照）開盤 30 分漲跌幅", "當天 09:30→收盤")]
    out = []
    for k, fac, tgt in spec:
        r = study(sets[k], fac, tgt)
        if r:
            r["key"] = k
            out.append(r)
            print(f"{fac:<16} → {tgt:<14} 天數 {r['days']:>3}  Q1..Q5 {r['q']}  Q5−Q1 {r['spread']:+.3f}%  t {r['t']:+.2f}  "
                  f"勝率 {r['win']:.0f}%  IC {r['ic']:+.4f} (t {r['icT']:+.2f})")
    doc = {"period": [dates[0], dates[-1]], "days": len(dates), "universe": "近 20 日成交金額前 100 名", "results": out}
    (DATA / "orderflow" / "research.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
