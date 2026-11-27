#!/usr/bin/env python3
"""
散戶擁擠 → 隔天放空（高週轉、高當沖比的股票散戶多，散戶傾向先買後賣、長期虧錢 → 隔天容易收黑K）

資料：data/research/yahoo_adj（日線，還原權息）、data/research/dt_hist（當沖股數，2014 起；只存當沖買進 ≥ 3,000 萬的）、
      發行股數用現在的（data/rebalance 的 basic；增減資前後的週轉率會有誤差）
對象：每天成交 ≥ 1 億的普通股
因子（第 t 天收盤就知道）：週轉率（成交股數 ÷ 發行股數）、當沖比（當沖股數 ÷ 成交股數）、當天漲跌、收紅／黑K、
      收盤在當天高低區間的位置、近 5 日漲跌；第 t+1 天開盤跳空（進場前就知道）
交易：t+1 開盤空、收盤補；漲到 t 收盤 +7.5% 停損；開盤已超過 +7.5% 不做；成本 0.23%
做法：規則組合（週轉率門檻 × 當沖比門檻 × 當天漲跌 × K 棒 × 隔天開盤跳空）只用 2014-18 選，
      至少 300 筆、2014-18 每筆淨報酬最好的幾組，再看 2019-22、2023+；另外加大小型股過濾（大型股贏機率最低 1/3 的日子不做）
輸出 data/research/crowd_short.json；用法：python scripts/research_crowd_short.py
"""
from __future__ import annotations

import glob
import itertools
import json
import math
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_strategy import DT_STOP  # noqa: E402

COST = 0.23
PARTS = (("2014-18", "2014", "2019"), ("2019-22", "2019", "2023"), ("2023+", "2023", "2100"))


def rows_all():
    from scripts.rebalance.public import Public
    sh = {k: v.get("sh") for k, v in Public(DATA).basic().items()}
    dt = {}
    for f in glob.glob(str(DATA / "research" / "dt_hist" / "20*.json")):
        for d, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
            if v.get("tw") is not None or v.get("tp") is not None:
                dt[d] = {**(v.get("tw") or {}), **(v.get("tp") or {})}
    out = []
    for f in glob.glob(str(DATA / "research" / "yahoo_adj" / "*.json")):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        c, s = j["code"], sh.get(j["code"])
        R = [r for r in j["d"] if all(r[1:5]) and r[6]]
        for i in range(6, len(R) - 1):
            d, o, h, l, cl, v, a = R[i]
            if d < "2014" or cl * v < 1e8:
                continue
            k = a / cl
            pa = R[i - 1][6]
            ret = (a / pa - 1) * 100
            if abs(ret) > 10.5:
                continue
            n = R[i + 1]
            k1 = n[6] / n[4]
            o1, h1, c1 = n[1] * k1, n[2] * k1, n[6]
            gap = (o1 / a - 1) * 100
            stop = a * (1 + DT_STOP / 100)
            if gap >= DT_STOP or gap <= -9.5:
                r = None
            elif h1 >= stop:
                r = (o1 - stop) / o1 * 100 - COST
            else:
                r = (o1 - c1) / o1 * 100 - COST
            out.append({"d": d, "n": n[0], "code": c, "val": cl * v / 1e8, "turn": v / s * 100 if s else None,
                        "dt": (dt[d].get(c, 0) / v * 100) if d in dt else None, "ret": ret, "black": cl < o, "limit": ret >= 9.5 and cl >= h * 0.999,
                        "pos": (cl - l) / (h - l) if h > l else 0.5, "r5": (a / R[i - 5][6] - 1) * 100, "gap": gap, "r": r})
    return out


def month_t(pairs):
    by = defaultdict(list)
    for m, v in pairs:
        by[m].append(v)
    xs = [st.mean(v) for v in by.values()]
    return round(st.mean(xs) / (st.stdev(xs) / math.sqrt(len(xs))), 2) if len(xs) > 2 and st.stdev(xs) else None


def stats(ev):
    out = {}
    for lab, a, b in PARTS:
        xs = [e for e in ev if a <= e["n"] < b and e["r"] is not None]
        if xs:
            days = defaultdict(list)
            for e in xs:
                days[e["n"]].append(e["r"])
            daily = [st.mean(v) for v in days.values()]
            out[lab] = {"n": len(xs), "avg": round(st.mean(e["r"] for e in xs), 3), "win": round(sum(e["r"] > 0 for e in xs) / len(xs) * 100, 1),
                        "t": month_t([(e["n"][:7], e["r"]) for e in xs]), "days": len(days), "perDay": round(st.mean(daily), 3)}
    return out


def fmt(s):
    return "｜".join(f"{lab} {v['avg']:+.2f}%（{v['n']} 筆／{v['days']} 天，勝 {v['win']:.0f}%，t {v['t']}）" if v else f"{lab} —" for lab, v in s.items())


def main():
    rows = rows_all()
    print(f"{len(rows)} 筆（成交 ≥ 1 億的股票日）")
    # 每天的週轉率名次
    byd = defaultdict(list)
    for r in rows:
        if r["turn"] is not None:
            byd[r["d"]].append(r)
    for d, xs in byd.items():
        xs.sort(key=lambda r: -r["turn"])
        for k, r in enumerate(xs, 1):
            r["trank"] = k
    # 大小型股預測（逐年滾動樣本外，2016 起）
    try:
        import numpy as np
        import research_size_rotation as rs
        days_, agg, _, tsmc = rs.build()
        srows = rs.features(days_, agg, tsmc)
        keys = list(srows[0]["f"]) + list(srows[0]["pre"])
        p = rs.walk(srows, keys, "gbm")
        pl = {x["n"]: 1 - p[i] for i, x in enumerate(srows) if not np.isnan(p[i])}
        lo = json.loads((DATA / "strategy" / "size_model.json").read_text(encoding="utf-8"))["lo"]
    except Exception as e:  # noqa: BLE001
        print("大小型股預測略過：", e)
        pl, lo = {}, 0
    out = {"base": stats(rows)}
    print("對照：所有成交 ≥ 1 億的股票隔天開盤空：" + fmt(out["base"]))
    grid = {
        "trank": [10, 20, 50, 100, None],              # 週轉率前 N 名（None＝不限）
        "dt": [None, 40, 50, 60],                      # 當沖比 ≥（None＝不限）
        "ret": ["any", "up", "lim", "up_nolim", "5+", "down"],
        "candle": ["any", "black", "red"],
        "gap": ["any", ">=0", "0-3", "1-3"],
    }

    def ok(r, c):
        if c["trank"] and (r.get("trank") or 9999) > c["trank"]:
            return False
        if c["dt"] is not None and (r["dt"] is None or r["dt"] < c["dt"]):
            return False
        rt = r["ret"]
        if c["ret"] == "up" and rt < 0 or c["ret"] == "lim" and not r["limit"] or c["ret"] == "up_nolim" and (rt < 0 or r["limit"]) \
                or c["ret"] == "5+" and rt < 5 or c["ret"] == "down" and rt >= 0:
            return False
        if c["candle"] == "black" and not r["black"] or c["candle"] == "red" and r["black"]:
            return False
        g = r["gap"]
        if c["gap"] == ">=0" and g < 0 or c["gap"] == "0-3" and not (0 <= g < 3) or c["gap"] == "1-3" and not (1 <= g < 3):
            return False
        return True
    res = []
    keys = list(grid)
    for combo in itertools.product(*grid.values()):
        c = dict(zip(keys, combo))
        if c["trank"] is None and c["dt"] is None:
            continue   # 至少要有一個「散戶擁擠」條件
        tr = [r["r"] for r in rows if "2014" <= r["n"] < "2019" and r["r"] is not None and ok(r, c)]
        if len(tr) < 300:
            continue
        res.append((st.mean(tr), len(tr), c))
    res.sort(key=lambda x: -x[0])
    out["top"] = []
    print(f"\n試了 {len(res)} 組（2014-18 至少 300 筆）；依 2014-18 每筆淨報酬排名前 12 組，看後兩段：")
    for avg, n, c in res[:12]:
        ev = [r for r in rows if ok(r, c)]
        s = stats(ev)
        sf = stats([r for r in ev if pl.get(r["n"], 1) >= lo])
        out["top"].append({"rule": c, "stats": s, "sizeFilter": sf})
        print(f"  {c}")
        print(f"     全做　　：{fmt(s)}")
        print(f"     跳過小型股偏強日：{fmt(sf)}")
    (DATA / "research" / "crowd_short.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
