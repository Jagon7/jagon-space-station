#!/usr/bin/env python3
"""
抄底研究（多市場版）：台股、美股（S&P500、那斯達克、費半）、日股、韓股

目的：①樣本變多，看哪些抄底訊號在各市場都有效（比只看台股可靠）②國際市場先止跌，台股會不會跟著反彈
每個市場、每天收盤：跌幅（距 60 日高）、RSI、布林、乖離、連跌、VIX、反轉 K、前一晚美股（亞洲市場用）、年線方向
未來：5／10／20／40 日報酬、20 日內再跌幅度（MAE）、20 日內再破底
只在回檔中（跌幅 ≥ 8%）評估、同一波 20 天內只算第一次；建模 2005～2017、驗證 2018～
跨市場：台股訊號當天，其他市場近 3 天也出現止跌確認的數量
輸出 data/research/bottom_multi.json（網頁「抄底雷達」用）
"""
from __future__ import annotations

import bisect
import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
SPLIT = "2018-01-01"
COOLDOWN = 20
MARKETS = {  # 代號: (名稱, 前一晚美股參考)
    "^TWII": ("台股加權", "^GSPC"), "^GSPC": ("美股 S&P500", None), "^IXIC": ("美股那斯達克", None), "^SOX": ("費城半導體", None),
    "^N225": ("日經 225", "^GSPC"), "^KS11": ("韓國綜合", "^GSPC"),
}


def yd(sym):
    return [r for r in json.loads((DATA / "research" / "yahoo" / f"{sym.replace('^', '_')}.json").read_text(encoding="utf-8"))["d"] if r[1] and r[4]]


def rsi(c, n=14):
    out = [None] * len(c)
    g = l = 0.0
    for i in range(1, len(c)):
        ch = c[i] - c[i - 1]
        up, dn = max(ch, 0), max(-ch, 0)
        if i <= n:
            g += up / n
            l += dn / n
            if i == n:
                out[i] = 100 - 100 / (1 + g / l) if l else 100
        else:
            g = (g * (n - 1) + up) / n
            l = (l * (n - 1) + dn) / n
            out[i] = 100 - 100 / (1 + g / l) if l else 100
    return out


class Series:
    def __init__(self, sym):
        rows = yd(sym)
        self.d = [r[0] for r in rows]
        self.c = {r[0]: r[4] for r in rows}

    def at(self, day, back=0):
        i = bisect.bisect_right(self.d, day) - 1 - back
        return self.c[self.d[i]] if i >= 0 else None

    def before(self, day, back=0):
        """台灣日期 day 之前（不含當天）的最近一個交易日收盤：亞洲市場看「前一晚」美股用"""
        i = bisect.bisect_left(self.d, day) - 1 - back
        return self.c[self.d[i]] if i >= 0 else None


def build(sym, vix: Series, us: dict):
    rows = yd(sym)
    d = [r[0] for r in rows]; o = [r[1] for r in rows]; h = [r[2] for r in rows]; lo = [r[3] for r in rows]; c = [r[4] for r in rows]
    rs = rsi(c)
    ovn = MARKETS[sym][1]
    out = []
    for i in range(260, len(c)):
        hi60 = max(h[i - 59:i + 1])
        ma20 = st.mean(c[i - 19:i + 1]); sd20 = st.pstdev(c[i - 19:i + 1])
        ma5 = st.mean(c[i - 4:i + 1])
        ma200 = st.mean(c[i - 199:i + 1]); ma200_60 = st.mean(c[i - 259:i - 59])
        day = d[i]
        v = vix.at(day) if ovn is None else vix.before(day)
        vmax = max((x for x in ((vix.at(day, k) if ovn is None else vix.before(day, k)) for k in range(10)) if x is not None), default=None)
        streak, k = 0, i
        while k > 0 and c[k] < c[k - 1]:
            streak += 1
            k -= 1
        r = {"date": day, "close": c[i], "dd": (c[i] / hi60 - 1) * 100, "rsi": rs[i], "z20": (c[i] - ma20) / sd20 if sd20 else 0,
             "bias20": (c[i] / ma20 - 1) * 100, "ret1": (c[i] / c[i - 1] - 1) * 100, "streak": streak, "upDay": c[i] > c[i - 1],
             "aboveMa5": c[i] > ma5, "keyRev": c[i] > h[i - 1] and c[i - 1] < c[i - 2], "ma200s": (ma200 / ma200_60 - 1) * 100,
             "vix": v, "vixOff": (1 - v / vmax) * 100 if v and vmax else None}
        if ovn:
            a, b = us[ovn].before(day), us[ovn].before(day, 1)
            r["usPrev"] = (a / b - 1) * 100 if a and b else None
        for n in (5, 10, 20, 40):
            if i + n < len(c):
                r[f"r{n}"] = (c[i + n] / c[i] - 1) * 100
        if i + 20 < len(c):
            w = lo[i + 1:i + 21]
            r["mae20"] = (min(w) / c[i] - 1) * 100
            r["newLow20"] = min(w) < lo[i]
        out.append(r)
    return out


SIGNALS = {
    "knife": ("接刀：深跌（≥12%）當天收黑直接買", lambda r: r["dd"] <= -12 and not r["upDay"]),
    "dd20": ("跌幅 ≥ 20%", lambda r: r["dd"] <= -20),
    "rsi25": ("RSI14 < 25", lambda r: (r["rsi"] or 50) < 25),
    "z25": ("跌破布林 −2.5σ", lambda r: r["z20"] <= -2.5),
    "vix30": ("VIX ≥ 30", lambda r: (r["vix"] or 0) >= 30),
    "keyRev": ("深跌＋關鍵反轉（收盤站上昨高）", lambda r: r["dd"] <= -12 and r["keyRev"]),
    "up5": ("深跌＋收紅站上 5 日線", lambda r: r["dd"] <= -12 and r["upDay"] and r["aboveMa5"]),
    "A": ("A：深跌＋前一晚美股大漲（≥1.5%）", lambda r: r["dd"] <= -12 and (r.get("usPrev") or 0) >= 1.5),
    "B": ("B：深跌＋收紅＋VIX 從 10 日高點回落 ≥10%", lambda r: r["dd"] <= -12 and r["upDay"] and (r["vixOff"] or 0) >= 10 and (r["vix"] or 0) >= 22),
    "A+": ("A＋年線仍向上", lambda r: r["dd"] <= -12 and (r.get("usPrev") or 0) >= 1.5 and r["ma200s"] > 0),
    "B+": ("B＋年線仍向上", lambda r: r["dd"] <= -12 and r["upDay"] and (r["vixOff"] or 0) >= 10 and (r["vix"] or 0) >= 22 and r["ma200s"] > 0),
}


def picks(rows, f):
    out, last = [], -99
    for i, r in enumerate(rows):
        if r["dd"] > -8 or "r20" not in r or "mae20" not in r or not f(r) or i - last < COOLDOWN:
            continue
        out.append(r)
        last = i
    return out


def summ(ps):
    if not ps:
        return {"n": 0}
    return {"n": len(ps), "r5": round(st.mean(p["r5"] for p in ps), 2), "r10": round(st.mean(p["r10"] for p in ps), 2),
            "r20": round(st.mean(p["r20"] for p in ps), 2), "r40": round(st.mean(p.get("r40", p["r20"]) for p in ps), 2),
            "win20": round(sum(p["r20"] > 0 for p in ps) / len(ps) * 100), "mae20": round(st.mean(p["mae20"] for p in ps), 2),
            "worst": round(min(p["mae20"] for p in ps), 2), "newLow": round(sum(p["newLow20"] for p in ps) / len(ps) * 100)}


def main():
    vix = Series("^VIX")
    us = {"^GSPC": Series("^GSPC")}
    data = {s: build(s, vix, us) for s in MARKETS}
    out = {"split": SPLIT, "markets": {s: v[0] for s, v in MARKETS.items()}, "signals": {k: v[0] for k, v in SIGNALS.items()},
           "table": {}, "pooled": {}, "cross": {}, "now": {}, "episodes": []}
    for s, rows in data.items():
        out["table"][s] = {}
        for k, (_, f) in SIGNALS.items():
            ps = picks(rows, f)
            out["table"][s][k] = {"train": summ([p for p in ps if p["date"] < SPLIT]), "test": summ([p for p in ps if p["date"] >= SPLIT]),
                                  "dates": [p["date"] for p in ps if p["date"] >= "2018-01-01"]}
    # 全部市場合併：哪些訊號在各地都有效
    for k, (_, f) in SIGNALS.items():
        allp = [p for s, rows in data.items() if s != "^IXIC" for p in picks(rows, f)]  # 那斯達克跟 S&P 太像，合併時不重複算
        out["pooled"][k] = {"train": summ([p for p in allp if p["date"] < SPLIT]), "test": summ([p for p in allp if p["date"] >= SPLIT])}
    # 跨市場：台股深跌時，其他市場（美、日、韓、費半）近 3 天有幾個出現止跌確認（收紅＋站上 5 日線）
    idx = {s: {r["date"]: r for r in rows} for s, rows in data.items()}
    others = ["^GSPC", "^SOX", "^N225", "^KS11"]

    def confirm_count(day):
        n = 0
        for s in others:
            ds = sorted(x for x in idx[s] if x <= day)[-3:]
            if any(idx[s][x]["upDay"] and idx[s][x]["aboveMa5"] for x in ds):
                n += 1
        return n
    tw = data["^TWII"]
    for lab, f in (("台股深跌當天，其他 4 市場近 3 天 ≥ 3 個已止跌", lambda r: r["dd"] <= -12 and confirm_count(r["date"]) >= 3),
                   ("台股深跌當天，其他市場 ≤ 1 個止跌", lambda r: r["dd"] <= -12 and confirm_count(r["date"]) <= 1),
                   ("台股訊號 A／B＋其他市場 ≥ 3 個止跌", lambda r: (SIGNALS["A"][1](r) or SIGNALS["B"][1](r)) and confirm_count(r["date"]) >= 3)):
        ps = picks(tw, f)
        out["cross"][lab] = {"train": summ([p for p in ps if p["date"] < SPLIT]), "test": summ([p for p in ps if p["date"] >= SPLIT])}
    # 各市場最新狀態
    for s, rows in data.items():
        r = rows[-1]
        out["now"][s] = {"date": r["date"], "close": r["close"], "dd": round(r["dd"], 2), "rsi": round(r["rsi"] or 0, 1), "bias20": round(r["bias20"], 2),
                         "vix": r["vix"], "vixOff": round(r["vixOff"] or 0, 1), "ma200s": round(r["ma200s"], 2), "upDay": r["upDay"], "ret1": round(r["ret1"], 2),
                         "usPrev": round(r["usPrev"], 2) if r.get("usPrev") is not None else None,
                         "fired": [k for k, (_, f) in SIGNALS.items() if r["dd"] <= -8 and f(r) and k != "knife"]}
    out["now"]["^TWII"]["confirmOthers"] = confirm_count(tw[-1]["date"])
    # 台股歷次大跌（跌幅首次 ≥ 15%）：前 20 天到後 60 天的走勢（相對當天收盤）
    closes = {r["date"]: r["close"] for r in tw}
    days = [r["date"] for r in tw]
    last = -99
    for i, r in enumerate(tw):
        if r["dd"] <= -15 and i - last > 60:
            last = i
            path = [round((tw[j]["close"] / r["close"] - 1) * 100, 2) if 0 <= j < len(tw) else None for j in range(i - 20, i + 61)]
            low_k = min(range(i, min(len(tw), i + 61)), key=lambda j: tw[j]["close"])
            out["episodes"].append({"date": r["date"], "dd": round(r["dd"], 1), "ma200s": round(r["ma200s"], 1), "path": path,
                                    "lowIn": low_k - i, "lowPct": round((tw[low_k]["close"] / r["close"] - 1) * 100, 1),
                                    "r20": round(r.get("r20", 0), 1), "r60": round((tw[min(len(tw) - 1, i + 60)]["close"] / r["close"] - 1) * 100, 1)})
    (DATA / "research" / "bottom_multi.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # 印出重點
    print("各訊號：全市場合併（建模／驗證）")
    for k, v in out["pooled"].items():
        a, b = v["train"], v["test"]
        print(f"  {k:6s} {SIGNALS[k][0]:28s} n={a['n']:3d}/{b['n']:3d} R20 {a.get('r20', 0):+5.1f}/{b.get('r20', 0):+5.1f} 勝 {a.get('win20', 0):3.0f}/{b.get('win20', 0):3.0f}% 再跌 {a.get('mae20', 0):+5.1f}/{b.get('mae20', 0):+5.1f} 破底 {a.get('newLow', 0):3.0f}/{b.get('newLow', 0):3.0f}%")
    print("跨市場")
    for k, v in out["cross"].items():
        a, b = v["train"], v["test"]
        print(f"  {k}: n={a['n']}/{b['n']} R20 {a.get('r20', 0):+.1f}/{b.get('r20', 0):+.1f} 勝 {a.get('win20', 0)}/{b.get('win20', 0)}% 再跌 {a.get('mae20', 0):+.1f}/{b.get('mae20', 0):+.1f}")
    print("現在", json.dumps(out["now"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
