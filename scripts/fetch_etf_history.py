#!/usr/bin/env python3
"""
被動式 ETF 的長期歷史持股（給「換股調整時長」用），只抓能查指定日期的投信。

做法（避免逐日抓一年多）：
  1. 粗掃：過去 DAYS 天，每 STEP 個平日查一次持股。
  2. 相鄰兩次成分股名單不同的區間，逐日補齊，並往前、往後多抓 MARGIN 個平日看換股的起訖。
  3. 重複 2 直到沒有新的區間。查過的日子記在 asked，下次執行只補新的。

輸出 JSS_DATA_DIR/etf/history/<代號>.json：
    {"asked": [查過的日期], "snaps": {持股基準日: [[股票代號, 股數], ...]}}  只存台股
用法：python scripts/fetch_etf_history.py [--days 430] [--minutes 40] [代號 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import etf_sources as S  # noqa: E402
from fetch_etf import ETF_DIR, ETF_LIST, log, read_json, write_json  # noqa: E402

STEP = 5
MARGIN = 8


def weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def members(rows) -> frozenset:
    return frozenset(c for c, _ in rows)


class History:
    def __init__(self, code: str):
        self.path = ETF_DIR / "history" / f"{code}.json"
        doc = read_json(self.path, {})
        self.asked: set[str] = set(doc.get("asked", []))
        self.snaps: dict[str, list] = doc.get("snaps", {})

    def save(self):
        write_json(self.path, {"asked": sorted(self.asked), "snaps": dict(sorted(self.snaps.items()))})


def query(code, name, issuer, d: date, h: History):
    if d.isoformat() in h.asked:
        return
    try:
        s = S.SOURCES[issuer][1](code, name, start=d)
    except Exception:  # noqa: BLE001  那天沒資料或暫時失敗，記下來避免重抓
        s = None
    h.asked.add(d.isoformat())
    if s and len(s["holdings"]) >= 5:
        h.snaps[s["date"]] = [[x["code"], x["shares"] or 0] for x in s["holdings"] if " " not in x["code"]]


def run_etf(code, name, issuer, first: date, last: date, deadline: float):
    h = History(code)
    days = weekdays(first, last)
    # 粗掃的日子固定對齊（以 2020-01-06 起算的第幾個平日），每天執行時不會換一批新的日子重抓
    epoch = date(2020, 1, 6)
    grid = [d for d in days if (len(weekdays(epoch, d)) - 1) % STEP == 0]
    for d in grid[::-1]:  # 由近往遠粗掃
        if time.time() > deadline:
            break
        query(code, name, issuer, d, h)
    for _ in range(4):  # 逐步補齊有變動的區間
        dates = sorted(h.snaps)
        todo = set()
        for a, b in zip(dates, dates[1:]):
            if members(h.snaps[a]) != members(h.snaps[b]):
                da, db = date.fromisoformat(a), date.fromisoformat(b)
                for d in weekdays(da - timedelta(days=MARGIN * 7 // 5), db + timedelta(days=MARGIN * 7 // 5)):
                    if first <= d <= last and d.isoformat() not in h.asked:
                        todo.add(d)
        if not todo or time.time() > deadline:
            break
        for d in sorted(todo):
            if time.time() > deadline:
                break
            query(code, name, issuer, d, h)
    h.save()
    return code, len(h.snaps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--days", type=int, default=430)
    ap.add_argument("--minutes", type=float, default=40)
    a = ap.parse_args()

    deadline = time.time() + a.minutes * 60
    last = datetime.now(S.TPE).date() - timedelta(days=1)
    first = last - timedelta(days=a.days)
    targets = [t for t in ETF_LIST if t[3] == "passive" and t[2] in S.DATED_SOURCES and (not a.codes or t[0] in a.codes)]
    by_issuer = defaultdict(list)
    for t in targets:
        by_issuer[t[2]].append(t)
    log(f"歷史持股：{len(targets)} 檔被動式 ETF，{first} ～ {last}")

    def run_issuer(items):
        return [run_etf(code, name, issuer, first, last, deadline) for code, name, issuer, _ in items]

    with ThreadPoolExecutor(max_workers=6) as pool:
        for batch in pool.map(run_issuer, by_issuer.values()):
            for code, n in batch:
                log(f"  {code}：{n} 份")
    return 0


if __name__ == "__main__":
    sys.exit(main())
