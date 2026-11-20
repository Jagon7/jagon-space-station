#!/usr/bin/env python3
"""
抄底研究：大跌之後，什麼訊號出現時進場搶反彈比較安全？

資料：加權指數（Yahoo ^TWII，2005 起）、美股 S&P500／費半、VIX、高收益債 HYG÷投資級債 LQD（信用風險）、
      台股大盤融資維持率（2021/11 起）、FOMC 利率決策（2017 起）
每天收盤進場（隔天開盤也可，差異很小），看之後：
  R5／R10／R20   5、10、20 個交易日後的報酬
  MAE20          20 個交易日內，從進場價往下最多再跌多少（用每日最低價）→「提早搶、沒反彈」的風險
  bottomIn20     20 天內有沒有跌破進場那天的低點
只在「回檔中」評估：距 60 日高點跌幅 ≥ 8%
訊號同一波（20 個交易日內）只算第一次，避免重複計算
建模 2005～2017、驗證 2018～2026（2018/10、2020/3、2022、2024/8、2025/4 都在驗證期）
輸出 data/research/bottom.json
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
SPLIT = "2018-01-01"
COOLDOWN = 20


def yd(sym):
    return json.loads((DATA / "research" / "yahoo" / f"{sym.replace('^', '_')}.json").read_text(encoding="utf-8"))["d"]


def asof(series_dates, series, d):
    import bisect
    i = bisect.bisect_right(series_dates, d) - 1
    return series[series_dates[i]] if i >= 0 else None


def rsi(closes, n=14):
    out = [None] * len(closes)
    g = l = 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
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


def build_rows():
    tw = [r for r in yd("^TWII") if r[1] and r[4]]
    dates = [r[0] for r in tw]
    o = [r[1] for r in tw]; h = [r[2] for r in tw]; lo = [r[3] for r in tw]; c = [r[4] for r in tw]; v = [r[5] or 0 for r in tw]
    rs = rsi(c)
    ext = {}
    for s in ("^GSPC", "^SOX", "^VIX", "HYG", "LQD", "^N225", "^KS11"):
        rows = yd(s)
        ext[s] = ({r[0]: r[4] for r in rows}, sorted(r[0] for r in rows))
    margin = {}
    try:
        mm = json.loads((ROOT / "public" / "data" / "margin.json").read_text(encoding="utf-8"))["market"]["series"]
        margin = {r[0]: r[1] for r in mm if r[1]}
    except (OSError, ValueError, KeyError):
        pass
    md = sorted(margin)
    ev = json.loads((DATA / "intel" / "us_events.json").read_text(encoding="utf-8")).get("events", [])
    cuts = sorted(e["t"][:10] for e in ev if e["key"] == "fomc" and isinstance(e.get("actual"), (int, float)) and isinstance(e.get("previous"), (int, float)) and e["actual"] < e["previous"])

    def ext_at(s, d, back=0):
        m, ks = ext[s]
        import bisect
        i = bisect.bisect_right(ks, d) - 1 - back
        return m[ks[i]] if i >= 0 else None

    rows = []
    for i in range(60, len(c)):
        d = dates[i]
        hi60 = max(h[i - 59:i + 1])
        dd = (c[i] / hi60 - 1) * 100
        ma20 = st.mean(c[i - 19:i + 1])
        sd20 = st.pstdev(c[i - 19:i + 1])
        ma5 = st.mean(c[i - 4:i + 1])
        vol20 = st.mean([x for x in v[i - 20:i] if x] or [0])
        vix = ext_at("^VIX", d)
        vix10 = max(x for x in (ext_at("^VIX", d, k) for k in range(10)) if x is not None) if vix else None
        hy = ext_at("HYG", d); lq = ext_at("LQD", d)
        hy20 = ext_at("HYG", d, 20); lq20 = ext_at("LQD", d, 20)
        spx = ext_at("^GSPC", d); spx1 = ext_at("^GSPC", d, 1)
        sox = ext_at("^SOX", d)
        sox_hi = max(x for x in (ext_at("^SOX", d, k) for k in range(0, 120, 5)) if x is not None) if sox else None
        mg = asof(md, margin, d) if md and d >= md[0] else None
        # 連續下跌天數
        streak = 0
        k = i
        while k > 0 and c[k] < c[k - 1]:
            streak += 1
            k -= 1
        fut = {}
        for n in (5, 10, 20, 40):
            if i + n < len(c):
                fut[f"r{n}"] = (c[i + n] / c[i] - 1) * 100
        if i + 1 < len(c):
            w = lo[i + 1:min(len(c), i + 21)]
            fut["mae20"] = (min(w) / c[i] - 1) * 100
            fut["newLow20"] = min(w) < lo[i]
            w10 = lo[i + 1:min(len(c), i + 11)]
            fut["mae10"] = (min(w10) / c[i] - 1) * 100
        rows.append({
            "date": d, "close": c[i], "dd": dd, "rsi": rs[i], "z20": (c[i] - ma20) / sd20 if sd20 else 0, "bias20": (c[i] / ma20 - 1) * 100,
            "ret1": (c[i] / c[i - 1] - 1) * 100, "ret5": (c[i] / c[i - 5] - 1) * 100, "streak": streak,
            "volx": v[i] / vol20 if vol20 and v[i] else None, "upDay": c[i] > c[i - 1],
            "keyRev": c[i] > h[i - 1] and c[i - 1] < c[i - 2],  # 收盤站上昨天高點（前一天還在跌）
            "aboveMa5": c[i] > ma5, "lowerTail": (min(o[i], c[i]) - lo[i]) / (h[i] - lo[i]) if h[i] > lo[i] else 0,
            "vix": vix, "vixOff": (1 - vix / vix10) * 100 if vix and vix10 else None,
            "credit20": ((hy / lq) / (hy20 / lq20) - 1) * 100 if hy and lq and hy20 and lq20 else None,
            "spx1": (spx / spx1 - 1) * 100 if spx and spx1 else None, "soxDD": (sox / sox_hi - 1) * 100 if sox and sox_hi else None,
            "margin": mg, "fedCut30": any(0 <= (datetime.fromisoformat(d) - datetime.fromisoformat(x)).days <= 30 for x in cuts),
            **fut,
        })
    return rows


SIGNALS = {
    # 名稱: (說明, 條件)
    "DD10": ("跌幅 ≥ 10%（距 60 日高）", lambda r: r["dd"] <= -10),
    "DD15": ("跌幅 ≥ 15%", lambda r: r["dd"] <= -15),
    "DD20": ("跌幅 ≥ 20%", lambda r: r["dd"] <= -20),
    "RSI25": ("RSI14 < 25", lambda r: r["rsi"] is not None and r["rsi"] < 25),
    "RSI20": ("RSI14 < 20", lambda r: r["rsi"] is not None and r["rsi"] < 20),
    "Z25": ("跌破 20 日布林 −2.5σ", lambda r: r["z20"] <= -2.5),
    "BIAS10": ("負乖離 20MA ≥ 10%", lambda r: r["bias20"] <= -10),
    "STREAK5": ("連跌 ≥ 5 天", lambda r: r["streak"] >= 5),
    "VOLX": ("爆量下跌（量 ≥ 20 日均 1.8 倍、收黑）", lambda r: (r["volx"] or 0) >= 1.8 and not r["upDay"]),
    "VIX30": ("VIX ≥ 30", lambda r: (r["vix"] or 0) >= 30),
    "VIX40": ("VIX ≥ 40", lambda r: (r["vix"] or 0) >= 40),
    "VIXOFF": ("VIX 從 10 日高點回落 ≥ 15%（仍 ≥ 25）", lambda r: (r["vixOff"] or 0) >= 15 and (r["vix"] or 0) >= 25),
    "KEYREV": ("關鍵反轉：收盤站上昨天高點", lambda r: r["keyRev"]),
    "UP2": ("止跌：收紅且站上 5 日線", lambda r: r["upDay"] and r["aboveMa5"]),
    "TAIL": ("長下影線（下影佔全天振幅 ≥ 60%）", lambda r: r["lowerTail"] >= 0.6),
    "SPXUP": ("前一晚美股 S&P 漲 ≥ 1.5%", lambda r: (r["spx1"] or 0) >= 1.5),
    "CREDIT": ("信用利差沒有再惡化（HYG÷LQD 20 日變化 ≥ −1%）", lambda r: r["credit20"] is not None and r["credit20"] >= -1),
    "MARGIN140": ("融資維持率 < 140%（2021 起）", lambda r: r["margin"] is not None and r["margin"] < 140),
    "FEDCUT": ("30 天內 Fed 降息（2017 起）", lambda r: r["fedCut30"]),
}


def evaluate(rows, cond, base_dd=-8.0):
    picks, last = [], None
    for idx, r in enumerate(rows):
        if r["dd"] > base_dd or "r20" not in r:
            continue
        if not cond(r):
            continue
        if last is not None and idx - last < COOLDOWN:
            continue
        picks.append(r)
        last = idx
    return picks


def summ(ps):
    if not ps:
        return {"n": 0}
    return {"n": len(ps), "r5": round(st.mean(p["r5"] for p in ps), 2), "r10": round(st.mean(p["r10"] for p in ps), 2),
            "r20": round(st.mean(p["r20"] for p in ps), 2), "win20": round(sum(p["r20"] > 0 for p in ps) / len(ps) * 100),
            "mae20": round(st.mean(p["mae20"] for p in ps), 2), "worstMae": round(min(p["mae20"] for p in ps), 2),
            "newLow": round(sum(p["newLow20"] for p in ps) / len(ps) * 100), "dates": [p["date"] for p in ps]}


def main():
    rows = build_rows()
    tr = [r for r in rows if r["date"] < SPLIT]
    te = [r for r in rows if r["date"] >= SPLIT]
    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "split": SPLIT, "signals": {}, "combos": {}}
    print(f"{rows[0]['date']} ～ {rows[-1]['date']}；回檔中（跌幅 ≥ 8%）才評估，同一波 20 天內只算第一次")
    base = lambda r: True  # noqa: E731
    for name, (lab, f) in [("BASE", ("回檔 ≥ 8% 的第一天（對照組）", base))] + list(SIGNALS.items()):
        a, b = summ(evaluate(tr, f)), summ(evaluate(te, f))
        out["signals"][name] = {"label": lab, "train": a, "test": b}
        fmt = lambda s: (f"n={s['n']:3d} R5 {s['r5']:+5.1f} R10 {s['r10']:+5.1f} R20 {s['r20']:+5.1f} 勝 {s['win20']:3.0f}% "  # noqa: E731
                         f"再跌 {s['mae20']:+5.1f}（最慘 {s['worstMae']:+5.1f}）破底 {s['newLow']:3.0f}%") if s["n"] else "n=0"
        print(f"{name:9s} {lab}\n   建模 {fmt(a)}\n   驗證 {fmt(b)}")
    combos = {
        "深跌＋止跌": lambda r: r["dd"] <= -12 and r["upDay"] and r["aboveMa5"],
        "深跌＋關鍵反轉": lambda r: r["dd"] <= -12 and r["keyRev"],
        "深跌＋VIX 回落": lambda r: r["dd"] <= -12 and (r["vixOff"] or 0) >= 15 and (r["vix"] or 0) >= 25,
        "深跌＋VIX 回落＋止跌": lambda r: r["dd"] <= -12 and (r["vixOff"] or 0) >= 10 and (r["vix"] or 0) >= 22 and r["upDay"],
        "超賣＋關鍵反轉": lambda r: (r["rsi"] or 50) < 30 and r["keyRev"] and r["dd"] <= -10,
        "深跌＋美股大漲": lambda r: r["dd"] <= -12 and (r["spx1"] or 0) >= 1.5,
        "深跌＋信用沒惡化＋止跌": lambda r: r["dd"] <= -12 and r["credit20"] is not None and r["credit20"] >= -1 and r["upDay"] and r["aboveMa5"],
        "接刀：深跌當天直接買": lambda r: r["dd"] <= -12 and not r["upDay"],
    }
    print("\n組合訊號")
    for name, f in combos.items():
        a, b = summ(evaluate(tr, f)), summ(evaluate(te, f))
        out["combos"][name] = {"train": a, "test": b}
        fmt = lambda s: (f"n={s['n']:3d} R5 {s['r5']:+5.1f} R10 {s['r10']:+5.1f} R20 {s['r20']:+5.1f} 勝 {s['win20']:3.0f}% "  # noqa: E731
                         f"再跌 {s['mae20']:+5.1f}（最慘 {s['worstMae']:+5.1f}）破底 {s['newLow']:3.0f}%") if s["n"] else "n=0"
        print(f"{name}\n   建模 {fmt(a)}\n   驗證 {fmt(b)}  {b.get('dates', [])}")
    cur = rows[-1]
    out["now"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in cur.items() if not k.startswith(("r", "mae", "newLow")) or k == "rsi"}
    print("\n最新：", json.dumps(out["now"], ensure_ascii=False))
    (DATA / "research" / "bottom.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "research" / "bottom_rows.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
