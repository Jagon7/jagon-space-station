#!/usr/bin/env python3
"""
85g 策略回測 → data/strategy/85g_bt.json（網站「85g 策略」頁的回測數字）

85g（IG @85ga_stock）是當沖交易員，每日額度 2000～4000 萬，公開的對帳單大多是「現股當沖先賣後買」：
  熱門族群股（記憶體、光通訊、面板…）開高時，開盤 30 分鐘內分批賣出，13:00 之後接近收盤買回 → 吃「開高走低」。
  另一種是指數大跌、熱門股開很低時先買，等盤中拉高一段賣出 → 吃「開低反彈」。
回測兩種打法（日線，約 5 年）：
  A 開高走低：前一日成交金額前 100 名、前一日漲停或前 5 日漲 ≥ 10% 的熱門股，開盤漲 0～4%，開盤賣、收盤買回
     （條件來自 85g 2024/12～2026/9 共 170 多張對帳單的統計：76% 是成交前 100 名、八成以上前一日漲停或近 5 日大漲、65% 開高 0～4%）
  B 開低反彈：指數開低 ≥ 1%，熱門股開盤跌 ≥ 3%，開盤買、收盤賣
  成本：現股當沖證交稅 0.15% ＋ 手續費約 0.09%（打折後）≈ 0.24%
另用近 60 天 5 分 K（--intraday）測「等 15 分鐘、跌破開盤價才賣」與停損的差別。
用法：python scripts/backtest_85g.py [--cache 暫存目錄] [--intraday]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics as st
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_exdiv import yahoo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TZ = timezone(timedelta(hours=8))
COST = 0.24
TOP = 100
GAP_LO, GAP_HI, RUN5, LIMIT = 0.0, 4.0, 10.0, 9.5


def hot(e):
    return e["prev"] >= LIMIT or e["p5"] >= RUN5


def ohlc(r: dict) -> dict:
    q = r["indicators"]["quote"][0]
    out = {}
    for t, o, h, l, c, v in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]):
        if o and h and l and c and v:
            out[datetime.fromtimestamp(t, TZ).date().isoformat()] = (o, h, l, c, v)
    return out


def top3(ev):
    by = collections.defaultdict(list)
    for e in ev:
        by[e["d"]].append(e)
    return [e for d in by.values() for e in sorted(d, key=lambda e: e["rank"])[:3]]


def stat(name, ev, side=-1):
    if len(ev) < 20:
        return None
    r = [side * e["oc"] for e in ev]
    return {"group": name, "n": len(ev), "avg": round(st.mean(r), 2), "med": round(st.median(r), 2),
            "win": round(sum(x > 0 for x in r) / len(r) * 100, 1), "net": round(st.mean(r) - COST, 2),
            "hi": round(st.mean(e["oh"] for e in ev), 2), "lo": round(st.mean(e["ol"] for e in ev), 2)}


def intraday(q_last: dict) -> list:
    """近 60 天 5 分 K：A 條件的事件，比較開盤賣與 09:15 跌破開盤價才賣"""
    daily = {}
    for f in sorted((DATA / "daily").glob("20*.json"))[-62:]:
        j = json.loads(f.read_text(encoding="utf-8"))
        daily[j.get("date", f.stem)] = j["q"]
    days = sorted(daily)
    tops = {d: [c for c in sorted((c for c in daily[d] if len(c) == 4 and c.isdigit() and c[0] != "0"), key=lambda c: -(daily[d][c][8] or 0))[:TOP]] for d in days}
    codes = sorted({c for t in tops.values() for c in t})

    def bars(c):
        mk = (daily[days[-1]].get(c) or q_last.get(c) or [None, 0])[1]
        out = subprocess.run(["curl", "-s", "-m", "30", "-A", "Mozilla/5.0",
                              f"https://query1.finance.yahoo.com/v8/finance/chart/{c}{'.TWO' if mk else '.TW'}?interval=5m&range=60d"],
                             capture_output=True, text=True).stdout
        try:
            r = json.loads(out)["chart"]["result"][0]
        except (ValueError, KeyError, TypeError, IndexError):
            return c, {}
        q = r["indicators"]["quote"][0]
        b = collections.defaultdict(list)
        for t, o, h, l, cl in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]):
            if o is not None:
                b[datetime.fromtimestamp(t, TZ).date().isoformat()].append((o, h, l, cl))
        return c, b

    with ThreadPoolExecutor(6) as ex:
        B = dict(ex.map(bars, codes))
    rows = []
    for i, d in enumerate(days):
        if i < 6:
            continue
        p = days[i - 1]
        for c in tops[p]:
            b = (B.get(c) or {}).get(d)
            pc, p5 = (daily[p].get(c) or [0] * 9)[5], (daily[days[i - 6]].get(c) or [0] * 9)[5]
            ppc = (daily[days[i - 2]].get(c) or [0] * 9)[5]
            if not b or len(b) < 40 or not pc or not p5 or not ppc:
                continue
            o = b[0][0]
            gap = (o / pc - 1) * 100
            if not GAP_LO <= gap < GAP_HI or not hot({"prev": (pc / ppc - 1) * 100, "p5": (pc / p5 - 1) * 100}):
                continue
            close = b[-1][3]
            hi15, px15 = max(x[1] for x in b[:3]), b[2][3]
            rs = -(close / px15 - 1) * 100
            for x in b[3:]:
                if x[1] >= hi15 * 1.01:
                    rs = -(hi15 * 1.01 / px15 - 1) * 100
                    break
            rows.append({"run": (pc / ppc - 1) * 100 >= LIMIT, "open": -(close / o - 1) * 100, "fail": px15 < o,
                         "r15": -(close / px15 - 1) * 100, "stop": rs})

    def s(name, ev, k):
        if len(ev) < 10:
            return None
        r = [e[k] for e in ev]
        return {"group": name, "n": len(ev), "avg": round(st.mean(r), 2), "med": round(st.median(r), 2),
                "win": round(sum(x > 0 for x in r) / len(r) * 100, 1), "net": round(st.mean(r) - COST, 2)}
    run = [e for e in rows if e["run"]]
    out = [s(f"A 條件（開高 {GAP_LO:g}～{GAP_HI:g}%）：09:00 開盤賣", rows, "open"),
           s("　└ 等 15 分鐘，跌破開盤價才賣（09:15）", [e for e in rows if e["fail"]], "r15"),
           s("　└ 同上，漲破前 15 分最高 +1% 停損", [e for e in rows if e["fail"]], "stop"),
           s("　└ 15 分鐘後還在開盤價之上（不做）", [e for e in rows if not e["fail"]], "r15"),
           s("其中前一日漲停：09:00 開盤賣", run, "open"),
           s("　└ 等 15 分鐘，跌破開盤價才賣", [e for e in run if e["fail"]], "r15"),
           s("　└ 同上＋停損", [e for e in run if e["fail"]], "stop")]
    return [x for x in out if x], (days[6] if len(days) > 6 else None), days[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "jss-yahoo"))
    ap.add_argument("--intraday", action="store_true", help="另測近 60 天 5 分 K 的進場時機")
    a = ap.parse_args()
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    daily = sorted((DATA / "daily").glob("20*.json"))
    q = json.loads(daily[-1].read_text(encoding="utf-8"))["q"]
    syms = {c: c + (".TWO" if v[1] else ".TW") for c, v in q.items() if len(c) == 4 and c.isdigit() and c[0] != "0"}
    with ThreadPoolExecutor(8) as ex:
        res = dict(zip(syms, ex.map(lambda s: yahoo(s, cache), syms.values())))
    ix = ohlc(yahoo("^TWII", cache))
    idays = sorted(ix)
    igap = {d: (ix[d][0] / ix[idays[i - 1]][3] - 1) * 100 for i, d in enumerate(idays) if i}
    stocks = {c: ohlc(r) for c, r in res.items() if r}
    val = collections.defaultdict(dict)
    for c, d in stocks.items():
        for day, (o, h, l, cl, v) in d.items():
            val[day][c] = cl * v
    top = {day: {c: k + 1 for k, c in enumerate(sorted(m, key=lambda c: -m[c])[:TOP])} for day, m in val.items()}
    ev = []
    for c, d in stocks.items():
        days = sorted(d)
        for i in range(6, len(days)):
            day, p = days[i], days[i - 1]
            if day not in igap or c not in top.get(p, {}):
                continue
            o, h, l, cl, v = d[day]
            pc = d[p][3]
            ev.append({"d": day, "c": c, "rank": top[p][c], "gap": (o / pc - 1) * 100, "prev": (pc / d[days[i - 2]][3] - 1) * 100, "p5": (pc / d[days[i - 6]][3] - 1) * 100,
                       "ig": igap[day], "oc": (cl / o - 1) * 100, "oh": (h / o - 1) * 100, "ol": (l / o - 1) * 100, "lim": o >= pc * 1.095})
    G = [e for e in ev if GAP_LO <= e["gap"] < GAP_HI]
    Ar = [e for e in G if hot(e)]
    groups = [stat(f"熱門股全部（前一日成交前 {TOP}，開盤賣、收盤買回）", ev),
              stat(f"開高 {GAP_LO:g}～{GAP_HI:g}%（不挑強勢）", G),
              stat(f"A：開高 {GAP_LO:g}～{GAP_HI:g}%＋前一日漲停或前 5 日漲 ≥ {RUN5:g}%", Ar),
              stat("A＋前一日漲停", [e for e in Ar if e["prev"] >= LIMIT]),
              stat("A＋當天符合條件中成交金額最大的 3 檔", top3(Ar)),
              stat("A＋前一日成交前 20 名", [e for e in Ar if e["rank"] <= 20]),
              stat("A＋前 5 日漲 ≥ 25%", [e for e in Ar if e["p5"] >= 25]),
              stat("A＋指數開高 ≥ 0.5%", [e for e in Ar if e["ig"] >= 0.5]),
              stat("A＋指數開低", [e for e in Ar if e["ig"] < 0]),
              stat("強勢股開高 4～9.5%", [e for e in ev if 4 <= e["gap"] < 9.5 and hot(e)]),
              stat("強勢股開低", [e for e in ev if e["gap"] < 0 and hot(e)]),
              stat("開漲停", [e for e in ev if e["lim"]])]
    years = [stat(f"{y} 年（A 條件）", [e for e in Ar if e["d"].startswith(y)]) for y in sorted({e["d"][:4] for e in Ar})]
    B = [e for e in ev if e["gap"] <= -3 and e["ig"] <= -1]
    bgroups = [stat("開低 ≥ 3%（指數不限）", [e for e in ev if e["gap"] <= -3], 1),
               stat("B 指數開低 ≥ 1%＋個股開低 ≥ 3%", B, 1),
               stat("B＋個股開低 ≥ 5%", [e for e in B if e["gap"] <= -5], 1)]
    brise = {k: round(sum(e["oh"] >= k for e in B) / len(B) * 100, 1) for k in (1, 2, 3, 5)} if B else {}
    arisk = {"up3": round(sum(e["oh"] >= 3 for e in Ar) / len(Ar) * 100, 1), "up5": round(sum(e["oh"] >= 5 for e in Ar) / len(Ar) * 100, 1),
             "dn3": round(sum(e["ol"] <= -3 for e in Ar) / len(Ar) * 100, 1)} if Ar else {}
    out = {"updatedAt": datetime.now(TZ).isoformat(timespec="minutes"), "cost": COST, "top": TOP, "gap": [GAP_LO, GAP_HI], "run5": RUN5,
           "from": min(e["d"] for e in ev), "to": max(e["d"] for e in ev), "n": len(ev),
           "groups": [g for g in groups if g], "years": [g for g in years if g], "bGroups": [g for g in bgroups if g], "bRise": brise, "aRisk": arisk}
    p = DATA / "strategy" / "85g_bt.json"
    if a.intraday:
        out["intraday"], out["intraFrom"], out["intraTo"] = intraday(q)
    else:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
            out.update({k: old[k] for k in ("intraday", "intraFrom", "intraTo") if k in old})
        except (OSError, ValueError):
            pass
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"85g 回測：{out['n']} 筆熱門股交易日（{out['from']} ~ {out['to']}）→ {p}")
    for g in out["groups"] + out["years"] + out["bGroups"] + out.get("intraday", []):
        print(f"  {g['group']:30s} n={g['n']:5d} 平均 {g['avg']:+.2f}% 勝率 {g['win']}% 扣成本 {g['net']:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
