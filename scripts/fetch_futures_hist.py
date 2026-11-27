#!/usr/bin/env python3
"""
研究用：期交所籌碼長期歷史（2020/3 起）→ data/research/futures_hist.json，格式同 data/futures/daily.json
  三大法人台指期／小台未平倉淨額、臺指選擇權買賣權未平倉、Put/Call ratio、台指期與小台總未平倉、台指期近月收盤
沿用 scripts/fetch_futures.py 的下載與解析；一次抓一個月，已抓齊的月份不重抓
期交所擋雲端以外的主機，在 GitHub Actions 跑（research.yml job=futhist）
用法：python scripts/fetch_futures_hist.py [--from 2020-03] [--minutes 300]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_futures as ff  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "futures_hist.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2020-03")
    ap.add_argument("--minutes", type=float, default=300)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    db = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    end = ff.last_trading_day()
    y, m = map(int, a.start.split("-"))
    months = []
    while date(y, m, 1) <= end:
        months.append((y, m))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    for y, m in reversed(months):   # 新的先抓
        if time.time() > deadline:
            ff.log("到時間，下次接著抓")
            break
        s = date(y, m, 1)
        e = min(end, (date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(days=1))
        ks = [k for k in db if k.startswith(f"{y}-{m:02d}")]
        if ks and all(db[k].get("txf") and db[k].get("txo") and db[k].get("pc") and db[k].get("px") for k in ks) and (y, m) != months[-1]:
            continue
        ff.fetch_range(s, e, db)
        ff.log(f"  {s} ~ {e}：{sum(1 for k in db if k.startswith(f'{y}-{m:02d}'))} 天")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(dict(sorted(db.items())), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ff.log(f"共 {len(db)} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
