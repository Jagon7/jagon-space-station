#!/usr/bin/env python3
"""
加權指數與類股指數盤中走勢（證交所 MI_5MINS_INDEX，每 5 秒；這裡取每分鐘最後一筆）

用途：台指期「價差」（期貨 − 加權指數）與盤中類股齊漲齊跌程度（廣度），研究突破盤／價差套利
存 data/market/index1m/<YYYY-MM>.json {日期: {"t": [每分鐘加權指數，09:00～13:30 共 271 筆],
                                             "s": {類股名稱: [09:00, 09:15, 09:30, 10:00, 13:30 的指數]}}}
用法：python scripts/fetch_index_intraday.py [--since 2020-03-01] [--minutes 120]（新到舊，已有的不重抓）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "market" / "index1m"
TPE = timezone(timedelta(hours=8))
CHECK = [0, 15, 30, 60, 270]  # 09:00、09:15、09:30、10:00、13:30


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def load(ym):
    try:
        return json.loads((OUT / f"{ym}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fetch(d: date):
    for i in range(4):
        try:
            r = requests.get("https://www.twse.com.tw/exchangeReport/MI_5MINS_INDEX",
                             params={"response": "json", "date": d.strftime("%Y%m%d")}, headers={"User-Agent": "Mozilla/5.0"}, timeout=40)
            j = r.json()
            break
        except (requests.RequestException, ValueError):
            time.sleep(20 * (i + 1))
    else:
        return None
    if j.get("stat") != "OK" or not j.get("data"):
        return {}
    fields = j["fields"]
    per_min: dict[int, list] = {}
    for row in j["data"]:
        hh, mm = int(row[0][:2]), int(row[0][3:5])
        m = (hh - 9) * 60 + mm
        if 0 <= m <= 270:
            per_min[m] = row  # 每分鐘最後一筆
    if len(per_min) < 200:
        return {}

    def num(x):
        try:
            return float(str(x).replace(",", ""))
        except ValueError:
            return None
    t, last = [], None
    for m in range(271):
        if m in per_min:
            last = num(per_min[m][1])
        t.append(last)
    secs = {}
    for k, name in enumerate(fields[1:], start=1):
        if name == "發行量加權股價指數":
            continue
        vals = []
        for m in CHECK:
            mm = max((x for x in per_min if x <= m), default=None)
            vals.append(num(per_min[mm][k]) if mm is not None else None)
        secs[name.replace("類指數", "").replace("指數", "")] = vals
    return {"t": t, "s": secs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2020-03-01")
    ap.add_argument("--minutes", type=float, default=120)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    OUT.mkdir(parents=True, exist_ok=True)
    trading = sorted(p.stem for p in (DATA / "futures" / "day").glob("*.json"))  # 只是用來加速：有台指期日盤的月份
    have = set()
    for f in OUT.glob("20*.json"):
        have |= set(load(f.stem))
    hol = set((json.loads((DATA / "calendar.json").read_text(encoding="utf-8")) or {}).get("holidays", [])) if (DATA / "calendar.json").exists() else set()
    d = datetime.now(TPE).date() - (timedelta(days=0) if datetime.now(TPE).hour >= 15 else timedelta(days=1))
    stop = date.fromisoformat(a.since)
    n = 0
    buf: dict[str, dict] = {}
    while d >= stop and time.time() < deadline:
        if d.weekday() < 5 and d.isoformat() not in hol and d.isoformat() not in have:
            v = fetch(d)
            if v is None:
                log(f"{d} 連不上，停止（可能被證交所暫時封鎖）")
                break
            if v:
                buf.setdefault(d.isoformat()[:7], {})[d.isoformat()] = v
                n += 1
            time.sleep(3.5)
            if n and n % 20 == 0:
                for ym, add in buf.items():
                    doc = load(ym); doc.update(add)
                    (OUT / f"{ym}.json").write_text(json.dumps(dict(sorted(doc.items())), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                buf = {}
                log(f"已抓 {n} 天，到 {d}")
        d -= timedelta(days=1)
    for ym, add in buf.items():
        doc = load(ym); doc.update(add)
        (OUT / f"{ym}.json").write_text(json.dumps(dict(sorted(doc.items())), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"本次新增 {n} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
