#!/usr/bin/env python3
"""
台股休市日（給資料健檢算「最近應開盤日」與落後幾個交易日）。

資料來源：證交所 OpenAPI「有價證券集中交易市場開（休）市日期」。
表上也會列「開始交易」「最後交易」這種有交易的日子，那些不算休市。
輸出 JSS_DATA_DIR/calendar.json：{"updatedAt", "holidays": ["YYYY-MM-DD", ...]}（只列平日的休市日）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "calendar.json"
TPE = timezone(timedelta(hours=8))
URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"


def roc(s: str) -> date | None:
    s = s.strip()
    try:
        return date(int(s[:-4]) + 1911, int(s[-4:-2]), int(s[-2:]))
    except ValueError:
        return None


def main():
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    rows = r.json()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"holidays": []}
    days = set(old.get("holidays", []))
    for row in rows:
        d = roc(str(row.get("Date", "")))
        text = f"{row.get('Name', '')}{row.get('Description', '')}"
        if not d or d.weekday() >= 5 or "開始交易" in text or "最後交易" in text:
            continue
        days.add(d.isoformat())
    if not days:
        print("✗ 沒有取得休市日")
        return 1
    OUT.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "holidays": sorted(days)},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"休市日：{len(days)} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
