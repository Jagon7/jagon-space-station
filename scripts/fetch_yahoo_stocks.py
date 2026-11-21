#!/usr/bin/env python3
"""
抄底選股研究用：上市個股日線（Yahoo，2011 起，含成交量；分割已調整、除息未調整）→ data/research/yahoo_stocks/<代號>.json
代號清單：data/research/rebound/q_*.json 裡出現過、低點當天成交 ≥ 5000 萬的上市股；已抓過且到最近一週的不重抓
用法：python scripts/fetch_yahoo_stocks.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "yahoo_stocks"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    codes = set()
    for f in glob.glob(str(DATA / "research" / "rebound" / "q_*.json")):
        for c, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
            if len(c) == 4 and c.isdigit() and c[0] != "0" and v[3] and v[3] >= 5e7:
                codes.add(c)
    ok = bad = 0
    for c in sorted(codes):
        p = OUT / f"{c}.json"
        if p.exists() and time.time() - p.stat().st_mtime < 5 * 86400:
            continue
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{c}.TW", timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                             params={"period1": 1293840000, "period2": int(time.time()) + 86400, "interval": "1d"})
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            off = (res.get("meta") or {}).get("gmtoffset") or 0
            rows = [[datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(), q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]]
                    for i, t in enumerate(res["timestamp"]) if q["close"][i] is not None and q["high"][i] is not None]
            p.write_text(json.dumps({"code": c, "d": rows}, separators=(",", ":")), encoding="utf-8")
            ok += 1
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(c, "失敗", e, flush=True)
        time.sleep(0.3)
    print(f"完成 {ok}、失敗 {bad}、共 {len(codes)} 檔", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
