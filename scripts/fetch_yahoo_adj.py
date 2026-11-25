#!/usr/bin/env python3
"""
研究用：上市＋上櫃個股日線（Yahoo，2011 起），含還原權息收盤
代號清單：data/daily 最新一天的上市（.TW）＋上櫃（.TWO）個股（4 碼、不含 0 開頭的 ETF）→ 只有現在還掛牌的（下市股缺，有存活者偏差）
存 data/research/yahoo_adj/<代號>.json：{"code","mkt"(0 上市/1 上櫃),"d": [[日期, 開, 高, 低, 收, 量(股), 還原收盤], ...]}
已抓過且到最近一週的不重抓；用法：python scripts/fetch_yahoo_adj.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "yahoo_adj"


def one(code: str, mkt: int) -> str:
    fp = OUT / f"{code}.json"
    if fp.exists():
        try:
            last = json.loads(fp.read_text(encoding="utf-8"))["d"][-1][0]
            if (datetime.now().date() - datetime.fromisoformat(last).date()).days <= 7:
                return "略過"
        except (ValueError, KeyError, IndexError):
            pass
    sym = f"{code}.{'TWO' if mkt else 'TW'}"
    for i in range(3):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                             params={"period1": 1293840000, "period2": int(time.time()) + 86400, "interval": "1d", "events": "div,split"})
            if r.status_code == 404:
                return "沒有資料"
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(res["timestamp"])
            off = (res.get("meta") or {}).get("gmtoffset") or 0
            rows = []
            for k, t in enumerate(res["timestamp"]):
                c = q["close"][k]
                if c is None or q["open"][k] is None or adj[k] is None:
                    continue
                d = datetime.fromtimestamp(t + off, timezone.utc).date().isoformat()
                rows.append([d, q["open"][k], q["high"][k], q["low"][k], c, q["volume"][k] or 0, adj[k]])
            fp.write_text(json.dumps({"code": code, "mkt": mkt, "d": rows}, separators=(",", ":")), encoding="utf-8")
            return f"{len(rows)} 天"
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            time.sleep(5 * (i + 1))
    return "失敗"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f = sorted(x for x in glob.glob(str(DATA / "daily" / "20*.json")))[-1]
    q = json.loads(Path(f).read_text(encoding="utf-8"))["q"]
    codes = sorted((c, v[1]) for c, v in q.items() if len(c) == 4 and c.isdigit() and c[0] != "0")
    print(f"{len(codes)} 檔（{Path(f).stem}）", flush=True)
    fails = []
    with ThreadPoolExecutor(4) as ex:
        for n, ((c, m), r) in enumerate(zip(codes, ex.map(lambda x: one(*x), codes)), 1):
            if r == "失敗":
                fails.append(c)
            if n % 200 == 0:
                print(n, c, r, flush=True)
    print(f"完成；失敗 {len(fails)}：{fails[:30]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
