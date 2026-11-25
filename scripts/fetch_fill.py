#!/usr/bin/env python3
"""
00918（特選臺灣優利高填息30指數）用的填息紀錄：每檔最近 20 次現金除息、有沒有完成填息

資料：Yahoo 日線（2005 起，含除息事件；收盤價已做分割／除權調整、未做除息調整）
填息定義（規則筆記，指數公司口徑）：
  還原報酬率數列＝除息日（含）到下一次除息日前一天的還原收盤價 ÷ 除息前一天還原收盤價（最近一次：到資料日）
  除息百分比＝1 ÷ (1 − 當次現金股利 ÷ 除息前一天未還原收盤價) − 1
  數列中任一天「還原報酬率 − 除息百分比 > 1」→ 完成填息；同一天多筆股利合併
對象：上市＋上櫃普通股，發行市值前 220 大（母體是前 150 大，多抓一些避免門檻附近漏掉）＋ 00918 現有成分股
輸出 data/rebalance/raw/fill.json {"asof": 日期, "d": {代號: [[除息日, 除息前收盤, 填息(1/0), 填息天數或 null, 現金股利], ...]}}
用法：python scripts/fetch_fill.py [代號 ...]
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "rebalance" / "raw" / "fill.json"
TPE = timezone(timedelta(hours=8))
KEEP = 20


def yahoo(code: str, mkt: str):
    sym = f"{code}.{'TWO' if mkt == 'OTC' else 'TW'}"
    for i in range(3):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                             params={"period1": 1104537600, "period2": int(time.time()) + 86400, "interval": "1d", "events": "div"})
            res = r.json()["chart"]["result"][0]
            off = (res.get("meta") or {}).get("gmtoffset") or 0
            day = lambda t: datetime.fromtimestamp(t + off, timezone.utc).date().isoformat()  # noqa: E731
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(res["timestamp"])
            px = [(day(t), c, a) for t, c, a in zip(res["timestamp"], q["close"], adj) if c and a]
            divs = {}
            for v in ((res.get("events") or {}).get("dividends") or {}).values():
                d = day(v["date"])
                divs[d] = divs.get(d, 0) + (v.get("amount") or 0)
            return px, divs
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            time.sleep(3 * (i + 1))
    return None, None


def fill_events(px: list, divs: dict) -> list:
    """px: [(日期, 未還原收盤, 還原收盤)]"""
    dates = [x[0] for x in px]
    idx = {d: i for i, d in enumerate(dates)}
    exd = sorted(d for d in divs if d in idx and idx[d] > 0 and divs[d] > 0)
    out = []
    for j, d in enumerate(exd):
        i = idx[d]
        raw_prev, adj_base = px[i - 1][1], px[i - 1][2]
        if not raw_prev or not adj_base or divs[d] >= raw_prev:
            continue
        pct = 1 / (1 - divs[d] / raw_prev) - 1
        end = idx[exd[j + 1]] if j + 1 < len(exd) else len(px)
        hit = next((k for k in range(i, end) if px[k][2] / adj_base - pct > 1), None)
        out.append([d, round(raw_prev, 2), 1 if hit is not None else 0, (hit - i) if hit is not None else None, round(divs[d], 4)])
    return out[-KEEP:]


def main():
    sys.path.insert(0, str(ROOT))
    from scripts.rebalance.public import Public
    pub = Public(DATA)
    basic = pub.basic()
    day = pub.px_days()[-1]
    p = pub.px(day)
    mc = {k: (v[0] or 0) * (basic[k].get("sh") or 0) for k, v in p.items()
          if k in basic and len(k) == 4 and k.isdigit() and basic[k].get("mk") in ("TSE", "OTC")}
    codes = sorted(mc, key=lambda k: -mc[k])[:220]
    codes = sorted(set(codes) | set(pub.etf("00918").get("weights", {})) | set(sys.argv[1:]))
    try:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"d": {}}
    with ThreadPoolExecutor(4) as ex:
        res = dict(zip(codes, ex.map(lambda k: yahoo(k, basic.get(k, {}).get("mk", "TSE")), codes)))
    n = 0
    for k, (px, divs) in res.items():
        if px:
            doc["d"][k] = fill_events(px, divs)
            n += 1
    doc["asof"] = day
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"填息紀錄 {n}／{len(codes)} 檔（{day}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
