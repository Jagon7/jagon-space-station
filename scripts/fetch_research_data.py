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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    syms = ["^TWII", "^GSPC", "^VIX", "^SOX", "HYG", "LQD", "^N225", "^KS11"] if "--quick" in sys.argv else SYMS
    for s in syms:
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}", timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                             params={"period1": 1104537600, "period2": int(time.time()) + 86400, "interval": "1d"})
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            rows = []
            for i, t in enumerate(res["timestamp"]):
                c = q["close"][i]
                if c is None:
                    continue
                d = datetime.fromtimestamp(t + (res.get("meta", {}).get("gmtoffset") or 0), timezone.utc).date().isoformat()
                rows.append([d, q["open"][i], q["high"][i], q["low"][i], c, q["volume"][i]])
            (OUT / f"{s.replace('^', '_')}.json").write_text(json.dumps({"sym": s, "d": rows}, separators=(",", ":")), encoding="utf-8")
            print(s, len(rows), rows[0][0], rows[-1][0], flush=True)
        except Exception as e:  # noqa: BLE001
            print(s, "失敗", e, flush=True)
        time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
