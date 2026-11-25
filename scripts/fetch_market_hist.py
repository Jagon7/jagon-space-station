#!/usr/bin/env python3
"""
研究用：大盤每日成交金額與融資餘額歷史（2012 起）→ data/research/market_hist.json
  {"turnover": {日期: 上市成交金額（億）}, "margin": {日期: [上市融資金額, 上櫃融資金額]（億，抓不到為 null）}}
  成交金額：證交所 FMTQIK（每月一次）；融資：證交所 MI_MARGN（selectType=MS）、櫃買中心 margin/balance（每天一次）
交易日用 data/research/yahoo/_TWII.json 的日期；已有的跳過；證交所擋雲端以外的連線較少，在 GitHub Actions 上跑（research.yml，job=market）
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_market_daily as fm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "market_hist.json"


def save(doc):
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")


def main():
    try:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"turnover": {}, "margin": {}}
    days = [r[0] for r in json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"] if r[0] >= "2012-01-01"]
    t0 = time.time()
    # 成交金額（每月）
    for ym in sorted({d[:7] for d in days}):
        if any(d.startswith(ym) for d in doc["turnover"]) and ym < days[-1][:7]:
            continue
        j = fm.get_json("https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK", {"date": ym.replace("-", "") + "01", "response": "json"})
        for t in fm.tables(j) if j.get("stat") == "OK" else []:
            for r in t.get("data") or []:
                y, m, dd = str(r[0]).strip().split("/")
                doc["turnover"][f"{int(y) + 1911}-{int(m):02d}-{int(dd):02d}"] = round(fm.num(r[2]) / 1e8, 1)
        time.sleep(2)
    save(doc)
    print("成交金額", len(doc["turnover"]), "天", flush=True)
    # 融資（每天）
    n = 0
    for d in reversed(days):
        if d in doc["margin"] and doc["margin"][d][0] is not None:
            continue
        if time.time() - t0 > 4.6 * 3600:
            print("時間到，下次接著抓", flush=True)
            break
        a = fm.margin_amt(date.fromisoformat(d))
        doc["margin"][d] = [round(a[0] / 1e8, 1) if a[0] else None, round(a[1] / 1e8, 1) if a[1] else None]
        n += 1
        if n % 100 == 0:
            save(doc)
            print(n, d, doc["margin"][d], flush=True)
        time.sleep(1.5)
    save(doc)
    print("融資", sum(1 for v in doc["margin"].values() if v[0] is not None), "天", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
