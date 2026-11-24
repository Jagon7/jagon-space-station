#!/usr/bin/env python3
"""
收斂型配對交易掃描：兩個有經濟關聯的標的，價差偏離後會不會被拉回、扣成本後能不能賺

候選（都要有經濟上的理由，不做大海撈針）：
  ADR 溢價：台積電／TSM（1 ADR＝5 股）、聯電／UMC（5）、日月光投控／ASX（2）、中華電／CHT（10）——比較 ADR 換算台幣後 ÷ 台股
  同指數／高度重疊 ETF：0050／006208（都追蹤台灣 50）、0050／00692（公司治理 100）
  同產業／同集團股票：台塑四寶、金控、電信三雄、貨櫃三雄、記憶體、水泥、鋼鐵、AI 伺服器代工、IC 設計、食品…
  台積電相對加權（上一題：00631L 對 0050 的差距本質上就是這個）
方法（只用當時以前的資料）：
  價差 s＝log(A) − β·log(B)，β＝前 250 天的迴歸係數（ADR 固定 1）；z＝(s − 前 60 天平均) ÷ 前 60 天標準差
  |z| ≥ 2 進場（z 高：空 A 多 B；z 低：多 A 空 B），|z| ≤ 0.5 出場，最多抱 20 個交易日
  報酬＝兩腳各半資金的價差報酬（多頭腳報酬 − 空頭腳報酬）÷ 2，扣成本：
    股票每腳來回 0.43%（手續費 6 折 0.171% ＋ 證交稅 0.3%，空方再加借券年 2% 按持有天數）、ETF 每腳 0.23%、ADR 每腳 0.3%、
    加權指數用台指期替代每腳 0.02%
  半衰期：價差 AR(1) 的回歸半衰期（天）；2022 前挑、2022 後驗證，兩段都要賺
輸出 data/research/pairs.json；用法：python scripts/research_pairs.py
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
YS = DATA / "research" / "yahoo_stocks"
YX = DATA / "research" / "yahoo"
SPLIT = "2022-01-01"
COST = {"stk": 0.0043, "etf": 0.0023, "adr": 0.003, "idx": 0.0002}
BORROW = 0.02  # 空方借券年費

ADR = [("2330", "TSM", 5, "台積電 ADR 溢價"), ("2303", "UMC", 5, "聯電 ADR 溢價"), ("3711", "ASX", 2, "日月光投控 ADR 溢價"), ("2412", "CHT", 10, "中華電 ADR 溢價")]
ETF = [("0050.TW", "006208.TW", "0050／006208（同指數）"), ("0050.TW", "00692.TW", "0050／00692（高度重疊）")]
GROUPS = {
    "台塑四寶": ["1301", "1303", "1326", "6505"], "金控": ["2881", "2882", "2891", "2886", "2884", "2885", "2892", "2880", "5880", "2883", "2890"],
    "電信": ["2412", "3045", "4904"], "貨櫃航運": ["2603", "2609", "2615"], "記憶體": ["2408", "2344", "2337"], "水泥": ["1101", "1102"],
    "鋼鐵": ["2002", "2014", "2027"], "AI 伺服器代工": ["2317", "2382", "3231", "2356", "2324"], "IC 設計": ["2454", "2379", "3034"],
    "品牌電腦": ["2357", "2353", "2376", "2377"], "食品": ["1216", "1227"], "壽險金控": ["2882", "2881", "2891"],
}


def yahoo(sym: str) -> dict:
    p = YX / f"{sym.replace('^', '_')}.json"
    if p.exists() and time.time() - p.stat().st_mtime < 86400 * 3:
        return {r[0]: r[4] for r in json.loads(p.read_text(encoding="utf-8"))["d"] if r[4]}
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", headers={"User-Agent": "Mozilla/5.0"}, timeout=60,
                     params={"period1": 1262304000, "period2": int(time.time()), "interval": "1d"}).json()["chart"]["result"][0]
    q, off = r["indicators"]["quote"][0], (r.get("meta") or {}).get("gmtoffset") or 0
    adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    rows = [[datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(), q["open"][i], q["high"][i], q["low"][i], (adj or q["close"])[i], q["volume"][i]]
            for i, t in enumerate(r["timestamp"]) if q["close"][i]]
    p.write_text(json.dumps({"sym": sym, "d": rows}, separators=(",", ":")), encoding="utf-8")
    return {x[0]: x[4] for x in rows}


def stock(code: str) -> dict:
    p = YS / f"{code}.json"
    if not p.exists():
        return {}
    return {r[0]: r[4] for r in json.loads(p.read_text(encoding="utf-8"))["d"] if r[4]}


def clean(px: dict) -> dict:
    """去掉明顯錯誤的跳點（單日 > 60% 且隔天回來）"""
    ds = sorted(px)
    bad = {ds[i] for i in range(1, len(ds) - 1) if abs(math.log(px[ds[i]] / px[ds[i - 1]])) > 0.47 and abs(math.log(px[ds[i + 1]] / px[ds[i - 1]])) < 0.1}
    return {d: v for d, v in px.items() if d not in bad}


def ols(x, y):
    mx, my = st.mean(x), st.mean(y)
    vx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / vx if vx else 0
    return b, my - b * mx


def backtest(name, kind, ds, la, lb, fixed_beta=None, costs=("stk", "stk"), signal=None):
    """la、lb：log 價格（同日對齊，用來算損益）；signal：另外給的價差訊號（ADR 用前一晚的價格，避免偷看）"""
    n = len(ds)
    s = [None] * n
    for i in range(n):
        if signal is not None:
            s[i] = signal[i]
        elif fixed_beta is not None:
            s[i] = la[i] - fixed_beta * lb[i]
        elif i >= 250:
            b, _ = ols(lb[i - 250:i], la[i - 250:i])
            s[i] = la[i] - b * lb[i]
    trades, pos = [], None
    for i in range(n):
        if s[i] is None or i < 60 or any(x is None for x in s[i - 60:i]):
            continue
        w = s[i - 60:i]
        mu, sd = st.mean(w), st.pstdev(w)
        if not sd:
            continue
        z = (s[i] - mu) / sd
        if pos:
            side, i0, beta0 = pos
            held = i - i0
            if abs(z) <= 0.5 or held >= 20 or i == n - 1:
                ra, rb = math.exp(la[i] - la[i0]) - 1, math.exp(lb[i] - lb[i0]) - 1
                gross = (-ra + rb) / 2 if side < 0 else (ra - rb) / 2  # side<0：空 A 多 B
                cost = (COST[costs[0]] + COST[costs[1]]) / 2 + BORROW * held / 245 / 2
                trades.append({"date": ds[i0], "side": side, "held": held, "gross": gross, "net": gross - cost, "z0": pos_z})
                pos = None
            continue
        if z >= 2:
            pos, pos_z = (-1, i, None), z
        elif z <= -2:
            pos, pos_z = (1, i, None), z
    # 半衰期（2022 前）
    tr = [x for d, x in zip(ds, s) if x is not None and d < SPLIT]
    hl = None
    if len(tr) > 100:
        b, _ = ols(tr[:-1], [tr[i + 1] - tr[i] for i in range(len(tr) - 1)])
        hl = round(-math.log(2) / math.log(1 + b), 1) if -1 < b < 0 else None

    def summ(ts):
        if not ts:
            return {"n": 0}
        return {"n": len(ts), "avg": round(st.mean(t["net"] for t in ts) * 100, 3), "win": round(sum(t["net"] > 0 for t in ts) / len(ts) * 100),
                "gross": round(st.mean(t["gross"] for t in ts) * 100, 3), "held": round(st.mean(t["held"] for t in ts), 1),
                "worst": round(min(t["net"] for t in ts) * 100, 2), "sum": round(sum(t["net"] for t in ts) * 100, 1)}
    a = summ([t for t in trades if t["date"] < SPLIT])
    b = summ([t for t in trades if t["date"] >= SPLIT])
    cur = None
    if s[-1] is not None and all(x is not None for x in s[-61:-1]):
        w = s[-61:-1]
        cur = round((s[-1] - st.mean(w)) / (st.pstdev(w) or 1), 2)
    return {"name": name, "kind": kind, "hl": hl, "train": a, "test": b, "zNow": cur, "from": ds[0], "to": ds[-1],
            "pass": a.get("n", 0) >= 8 and b.get("n", 0) >= 5 and a.get("avg", -1) > 0 and b.get("avg", -1) > 0}


def align(*series):
    ds = sorted(set.intersection(*(set(x) for x in series)))
    return ds, [[math.log(x[d]) for d in ds] for x in series]


def main():
    res = []
    fx = clean(yahoo("TWD=X"))
    # ADR 溢價：台股收盤時只知道「前一晚」的 ADR（美股收盤在台股收盤之後），用它算溢價訊號；
    # 成交：台股那腳用當天台股收盤、ADR 那腳用當晚美股收盤（用同一天的 ADR 會偷看未來，曾得到勝率 99% 的假結果）
    import bisect
    for tw, us, ratio, lab in ADR:
        a, u = clean(stock(tw)), clean(yahoo(us))
        uds = sorted(d for d in u if d in fx)
        ds, la, lu_prev, lu_exec = [], [], [], []
        for d in sorted(a):
            k = bisect.bisect_left(uds, d)
            if 1 <= k < len(uds):
                ds.append(d)
                la.append(math.log(a[d]))
                lu_prev.append(math.log(u[uds[k - 1]] * fx[uds[k - 1]] / ratio))
                lu_exec.append(math.log(u[uds[k]] * fx[uds[k]] / ratio))
        if len(ds) > 500:
            res.append(backtest(lab, "ADR", ds, lu_exec, la, fixed_beta=1.0, costs=("adr", "stk"), signal=[x - y for x, y in zip(lu_prev, la)]))
    for x, y, lab in ETF:
        a, b = clean(yahoo(x)), clean(yahoo(y))
        ds, (la, lb) = align(a, b)
        if len(ds) > 500:
            res.append(backtest(lab, "ETF", ds, la, lb, costs=("etf", "etf")))
    tw = clean({r[0]: r[4] for r in json.loads((YX / "_TWII.json").read_text(encoding="utf-8"))["d"] if r[4]})
    ds, (la, lb) = align(clean(stock("2330")), tw)
    res.append(backtest("台積電／加權指數（台指期）", "指數", ds, la, lb, costs=("stk", "idx")))
    seen = set()
    for g, codes in GROUPS.items():
        px = {c: clean(stock(c)) for c in codes}
        for i, a in enumerate(codes):
            for b in codes[i + 1:]:
                if (a, b) in seen or not px[a] or not px[b]:
                    continue
                seen.add((a, b))
                ds, (la, lb) = align(px[a], px[b])
                if len(ds) > 800:
                    res.append(backtest(f"{g}：{a}／{b}", "產業", ds, la, lb))
    res.sort(key=lambda r: (-r["pass"], -(r["test"].get("avg") or -9)))
    names = {}
    try:
        for r in json.loads((DATA / "daily" / sorted(p.name for p in (DATA / "daily").glob("20*.json"))[-1]).read_text(encoding="utf-8"))["q"].items():
            names[r[0]] = r[1][0]
    except (OSError, ValueError, IndexError):
        pass
    print(f"掃描 {len(res)} 組；通過（2022 前與 2022 後都扣成本後賺錢、交易次數夠）{sum(r['pass'] for r in res)} 組")
    print("名稱                                   半衰期  2022前：次數 每筆淨利 勝率 ｜ 2022後：次數 每筆淨利 勝率 最差一筆 ｜ 現在 z")
    for r in res:
        a, b = r["train"], r["test"]
        nm = r["name"]
        for c, n in names.items():
            nm = nm.replace(f"{c}／", f"{n}{c}／").replace(f"／{c}", f"／{n}{c}") if c in nm and r["kind"] == "產業" else nm
        f = lambda s: f"{s['n']:3d} {s['avg']:+6.2f}% {s['win']:3d}%" if s.get("n") else "  0     —     — "  # noqa: E731
        print(f"{'✅' if r['pass'] else '  '} {nm:34s} {str(r['hl'] or '—'):>5s}  {f(a)} ｜ {f(b)} {str(b.get('worst', '—')):>6s} ｜ {r['zNow'] if r['zNow'] is not None else '—'}")
    (DATA / "research" / "pairs.json").write_text(json.dumps({"split": SPLIT, "cost": COST, "pairs": res}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
