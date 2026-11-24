#!/usr/bin/env python3
"""
研究用長期日線（Yahoo Finance，2005 起）→ data/research/yahoo/<代號>.json {"d": [[日期, 開, 高, 低, 收, 量], ...]}
台股大盤、國際股市、波動率、利率、匯率、台股權值股（個股期貨回測用）
用法：python scripts/fetch_research_data.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "yahoo"
SYMS = [
    "^TWII", "^N225", "^KS11", "^GSPC", "^IXIC", "^SOX", "^VIX", "^TNX", "DX-Y.NYB", "TWD=X", "TSM", "HYG", "LQD", "^HSI", "000001.SS",
    "2330.TW", "2454.TW", "2317.TW", "2308.TW", "2382.TW", "2303.TW", "3711.TW", "2881.TW", "2891.TW", "2412.TW", "3008.TW", "2603.TW", "0050.TW",
]


def session_closed(meta: dict, t: int) -> bool:
    """最新報價那一盤是否已收盤（收盤後才能用即時報價補收盤）。
    不能只看 currentTradingPeriod：過了午夜它會換成下一個交易日的時段，前一天的收盤就補不進來。
    做法：拿時段的收盤時刻（當地幾點幾分）套到最新成交那一天，現在已過收盤且最新成交在收盤前後 30 分鐘內才算。"""
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    end, off, rmt = reg.get("end") or 0, meta.get("gmtoffset") or 0, meta.get("regularMarketTime") or 0
    if not end or not rmt:
        return False
    day = lambda x: (x + off) // 86400  # noqa: E731
    if day(rmt) != day(t):
        return False  # 最新成交不是這根日 K 那天
    sess_end = day(rmt) * 86400 + (end + off) % 86400 - off
    return time.time() >= sess_end + 300 and rmt >= sess_end - 1800


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    syms = ["^TWII", "^GSPC", "^IXIC", "^VIX", "^SOX", "HYG", "LQD", "^N225", "^KS11"] if "--quick" in sys.argv else SYMS
    for s in syms:
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}", timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                             params={"period1": 1104537600, "period2": int(time.time()) + 86400, "interval": "1d"})
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            rows = []
            meta = res.get("meta") or {}
            for i, t in enumerate(res["timestamp"]):
                c = q["close"][i]
                if c is None and i == len(res["timestamp"]) - 1 and meta.get("regularMarketPrice") and session_closed(meta, t):
                    # Yahoo 最新一天的日線收盤常是空的：用即時報價欄位補（收盤後就是當天收盤）
                    c = meta["regularMarketPrice"]
                    q["high"][i] = q["high"][i] or meta.get("regularMarketDayHigh")
                    q["low"][i] = q["low"][i] or meta.get("regularMarketDayLow")
                if c is None:
                    continue
                d = datetime.fromtimestamp(t + (res.get("meta", {}).get("gmtoffset") or 0), timezone.utc).date().isoformat()
                rows.append([d, q["open"][i], q["high"][i], q["low"][i], c, q["volume"][i]])
            end = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end") or 0
            start = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("start") or 0
            if rows and start and (meta.get("regularMarketTime") or 0) < end and time.time() >= start:
                live = datetime.fromtimestamp((meta.get("regularMarketTime") or 0) + (meta.get("gmtoffset") or 0), timezone.utc).date().isoformat()
                if rows[-1][0] == live:
                    rows.pop()  # 還在盤中：最後一筆是即時價，不是收盤
            (OUT / f"{s.replace('^', '_')}.json").write_text(json.dumps({"sym": s, "d": rows}, separators=(",", ":")), encoding="utf-8")
            print(s, len(rows), rows[0][0], rows[-1][0], flush=True)
        except Exception as e:  # noqa: BLE001
            print(s, "失敗", e, flush=True)
        time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
