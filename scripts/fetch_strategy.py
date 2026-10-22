#!/usr/bin/env python3
"""
波段策略用的補充資料 → data/strategy/
  disposition.json  上市櫃處置股歷史（代號、處置起日、迄日），給「出量做多」排除近 10 日有處置的股票
    上市：證交所 announcement/punish（查詢期間）；上櫃：櫃買中心 bulletin/disposal（查詢期間）
    每次查最近 DAYS 天，和舊資料合併
用法：python scripts/fetch_strategy.py [--days 90]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "strategy"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA})
PERIOD = re.compile(r"(\d{2,3})/(\d{1,2})/(\d{1,2})\s*[~～－-]\s*(\d{2,3})/(\d{1,2})/(\d{1,2})")


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def get_json(url, params):
    for i in range(3):
        try:
            r = S.get(url, params=params, timeout=60)
            if r.status_code == 200 and r.text.lstrip()[:1] == "{":
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(4 * (i + 1))
    return None


def period_of(row) -> tuple[str, str] | None:
    for cell in row:
        m = PERIOD.search(re.sub(r"<[^>]+>", " ", str(cell)))
        if m:
            y1, m1, d1, y2, m2, d2 = (int(x) for x in m.groups())
            return date(y1 + 1911, m1, d1).isoformat(), date(y2 + 1911, m2, d2).isoformat()
    return None


def code_of(row) -> str | None:
    for cell in row[1:4]:
        c = str(cell).strip()
        if re.fullmatch(r"[1-9]\d{3}", c):
            return c
    return None


def twse(start: date, end: date) -> list:
    out = []
    for url in ("https://www.twse.com.tw/rwd/zh/announcement/punish", "https://www.twse.com.tw/announcement/punish"):
        doc = get_json(url, {"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d"), "response": "json"})
        rows = (doc or {}).get("data") or ((doc or {}).get("tables") or [{}])[0].get("data") or []
        for r in rows:
            c, p = code_of(r), period_of(r)
            if c and p:
                out.append([c, *p])
        if out:
            break
    return out


def tpex(start: date, end: date) -> list:
    doc = get_json("https://www.tpex.org.tw/www/zh-tw/bulletin/disposal",
                   {"startDate": start.strftime("%Y/%m/%d"), "endDate": end.strftime("%Y/%m/%d"), "response": "json"})
    out = []
    for r in ((doc or {}).get("tables") or [{}])[0].get("data") or []:
        c, p = code_of(r), period_of(r)
        if c and p:
            out.append([c, *p])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "disposition.json"
    try:
        old = json.loads(path.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        old = []
    end = datetime.now(TPE).date()
    start = end - timedelta(days=a.days)
    tw, tp = twse(start, end), tpex(start, end)
    # 目前處置中的名單（fetch_data 抓的）也併進來，避免查詢期間 API 失敗時漏掉
    try:
        cur = json.loads((DATA_DIR / "disposition.json").read_text(encoding="utf-8")).get("data", [])
        for x in cur:
            p = period_of([x.get("period", "")])
            if p:
                old.append([x["code"], *p])
    except (OSError, ValueError):
        pass
    items = sorted({tuple(x) for x in old + tw + tp})
    keep = (end - timedelta(days=400)).isoformat()
    items = [list(x) for x in items if x[2] >= keep]
    path.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "items": items},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"處置歷史：上市 {len(tw)}、上櫃 {len(tp)}，合計 {len(items)} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
