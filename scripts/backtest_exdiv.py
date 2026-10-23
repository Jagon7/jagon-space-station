#!/usr/bin/env python3
"""
除權息黑K策略回測 → data/strategy/exdiv_bt.json（網站「除權息黑K」頁顯示的回測數字）

假設：大股東為了節稅，除息前透過 swap 把現股轉給自營商（自營商買現貨避險），除息後 swap 結束、自營商在幾天內把現貨賣掉，
      大股東再慢慢買回 → 高殖利率股除息後幾天容易連續收黑。做法：除息日開盤放空（個股期或融券），持有約 3～4 個交易日回補。

資料：Yahoo Finance 日線（約 5 年）與現金股利紀錄（含除息日、每股現金股利）；有配股（分割事件）的除權不算
  殖利率＝現金股利 ÷ 除息前一日收盤；只看除息前 20 日平均成交金額 ≥ 5000 萬的事件
  報酬＝除息日開盤放空、第 4 個交易日（除息日算第 1 天）收盤回補；對照組＝同一檔股票除息前後 30／60 個交易日任意 4 日
個股期：期交所股票期貨標的清單（現在的清單，回測會有一點倖存者偏差）
用法：python scripts/backtest_exdiv.py [--cache 暫存目錄]（全部重抓約 5～10 分鐘）
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TZ = timezone(timedelta(hours=8))
HOLD = 4
COST_FUT, COST_STK = 0.10, 0.60  # 來回成本（%）：個股期（手續費＋期交稅＋滑價）、融券（手續費＋證交稅＋借券費）
MIN_VAL = 5e7


def yahoo(sym: str, cache: Path) -> dict | None:
    f = cache / f"{sym}.json"
    if not f.exists():
        for _ in range(3):
            out = subprocess.run(["curl", "-s", "-m", "30", "-A", "Mozilla/5.0",
                                  f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d&events=div%7Csplit"],
                                 capture_output=True, text=True).stdout
            if '"timestamp"' in out:
                f.write_text(out)
                break
    try:
        return json.loads(f.read_text())["chart"]["result"][0]
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def parse(r: dict):
    q = r["indicators"]["quote"][0]
    days = [datetime.fromtimestamp(t, TZ).date().isoformat() for t in r["timestamp"]]
    rows = [(d, o, c, v) for d, o, c, v in zip(days, q["open"], q["close"], q["volume"]) if o and c and v]
    ev = r.get("events") or {}
    divs = {datetime.fromtimestamp(int(k), TZ).date().isoformat(): v["amount"] for k, v in (ev.get("dividends") or {}).items()}
    splits = {datetime.fromtimestamp(int(k), TZ).date().isoformat() for k in (ev.get("splits") or {})}
    return rows, divs, splits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "jss-yahoo"))
    a = ap.parse_args()
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    daily = sorted((DATA / "daily").glob("20*.json"))
    q = json.loads(daily[-1].read_text(encoding="utf-8"))["q"]
    syms = {c: c + (".TWO" if v[1] else ".TW") for c, v in q.items() if len(c) == 4 and c.isdigit() and c[0] != "0"}
    sf = set((json.loads((DATA / "strategy" / "stockfutures.json").read_text(encoding="utf-8")) or {}).get("codes", []))
    with ThreadPoolExecutor(8) as ex:
        res = dict(zip(syms, ex.map(lambda s: yahoo(s, cache), syms.values())))
    events = []
    for code, r in res.items():
        if not r:
            continue
        rows, divs, splits = parse(r)
        pos = {d: i for i, d in enumerate(r[0] for r in rows)}
        for d, amt in divs.items():
            i = pos.get(d)
            if d in splits or i is None or i < 21 or i + 7 >= len(rows):
                continue
            p0 = rows[i - 1][2]
            y = amt / p0 * 100
            val = st.mean(x[3] * x[2] for x in rows[i - 20:i])
            if not 0.5 <= y <= 30 or val < MIN_VAL:
                continue
            O = rows[i][1]
            path = [round((rows[i + k][2] / O - 1) * 100, 3) for k in range(7)]
            blacks = [rows[i + k][2] < rows[i + k][1] for k in range(HOLD)]
            ctl = [-(rows[j + HOLD - 1][2] / rows[j][1] - 1) * 100 for j in (i - 30, i + 30, i + 60) if 0 <= j and j + HOLD <= len(rows)]
            events.append({"code": code, "name": q[code][0], "date": d, "y": round(y, 2), "sf": code in sf, "short": round(-path[HOLD - 1], 2),
                           "path": path, "black": sum(blacks), "ctl": round(st.mean(ctl), 3) if ctl else None})

    def stat(name, ev):
        if len(ev) < 15:
            return None
        r = [e["short"] for e in ev]
        c = [e["ctl"] for e in ev if e["ctl"] is not None]
        return {"group": name, "n": len(ev), "avg": round(st.mean(r), 2), "med": round(st.median(r), 2), "win": round(sum(x > 0 for x in r) / len(r) * 100, 1),
                "ctl": round(st.mean(c), 2) if c else None, "netFut": round(st.mean(r) - COST_FUT, 2), "netStk": round(st.mean(r) - COST_STK, 2),
                "black3": round(sum(e["black"] >= 3 for e in ev) / len(ev) * 100, 1),
                "path": [round(st.mean(e["path"][k] for e in ev), 2) for k in range(7)]}

    groups = [stat("全部（日均成交 ≥ 5000 萬）", events)]
    for lo, hi in ((0, 2), (2, 4), (4, 6), (6, 99)):
        groups.append(stat(f"殖利率 {lo}～{hi}%" if hi < 99 else f"殖利率 ≥ {lo}%", [e for e in events if lo <= e["y"] < hi]))
    groups += [stat("殖利率 ≥ 4%", [e for e in events if e["y"] >= 4]),
               stat("殖利率 ≥ 4%＋有個股期", [e for e in events if e["y"] >= 4 and e["sf"]]),
               stat("殖利率 ≥ 5%＋有個股期", [e for e in events if e["y"] >= 5 and e["sf"]])]
    years = [stat(f"{y} 年（殖利率 ≥ 4%）", [e for e in events if e["y"] >= 4 and e["date"].startswith(y)]) for y in sorted({e["date"][:4] for e in events})]
    out = {"updatedAt": datetime.now(TZ).isoformat(timespec="minutes"), "hold": HOLD, "costFut": COST_FUT, "costStk": COST_STK,
           "from": min(e["date"] for e in events), "to": max(e["date"] for e in events), "n": len(events),
           "groups": [g for g in groups if g], "years": [g for g in years if g],
           "recent": sorted(([e["date"], e["code"], e["name"], e["y"], e["sf"], e["short"], e["black"]] for e in events if e["y"] >= 4),
                            reverse=True)[:150]}
    p = DATA / "strategy" / "exdiv_bt.json"
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"除權息黑K回測：{out['n']} 筆事件（{out['from']} ~ {out['to']}）→ {p}")
    for g in out["groups"] + out["years"]:
        print(f"  {g['group']:24s} n={g['n']:5d} 做空 {g['avg']:+.2f}% 勝率 {g['win']}% 對照 {g['ctl']:+.2f}% 扣期貨成本 {g['netFut']:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
