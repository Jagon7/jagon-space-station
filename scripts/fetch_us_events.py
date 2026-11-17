#!/usr/bin/env python3
"""
美國重要經濟事件歷史（TradingView economic-calendar；有公布時間、實際值、預估值、前值）

存 data/intel/us_events.json {"updatedAt", "events": [{"key", "t"（台灣時間）, "period", "main", "actual", "forecast", "previous", "items": {標題: [實際, 預估, 前值]}}]}
同一個時間點公布的同類數據併成一筆（例如 CPI 的年增、月增、核心一起公布）；main 是判斷「高於／低於預期」用的那一項
用法：python scripts/fetch_us_events.py [--since 2017-05-01]（第一次全抓；之後只更新最近 90 天＋未來 45 天）
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
PATH = DATA / "intel" / "us_events.json"
TPE = timezone(timedelta(hours=8))

# key: (中文名稱, 這類事件包含的標題（開頭比對）, 判斷高低於預期用的主指標（依序找第一個有的）)
KINDS = {
    "cpi": ("CPI", ("Inflation Rate MoM", "Inflation Rate YoY", "Core Inflation Rate MoM", "Core Inflation Rate YoY"),
            ("Core Inflation Rate MoM", "Inflation Rate MoM")),
    "ppi": ("PPI", ("PPI MoM", "PPI YoY", "Core PPI MoM", "Core PPI YoY"), ("PPI MoM",)),
    "nfp": ("非農就業", ("Non Farm Payrolls", "Unemployment Rate", "Average Hourly Earnings MoM"), ("Non Farm Payrolls",)),
    "fomc": ("FOMC 利率決策", ("Interest Rate", "Fed Interest Rate Decision"), ("Interest Rate", "Fed Interest Rate Decision")),
    "pce": ("PCE", ("Core PCE Price Index MoM", "Core PCE Price Index YoY", "PCE Price Index MoM", "PCE Price Index YoY"),
            ("Core PCE Price Index MoM", "PCE Price Index MoM")),
    "retail": ("零售銷售", ("Retail Sales MoM", "Retail Sales Ex Autos MoM"), ("Retail Sales MoM",)),
    "gdp": ("GDP（初值）", ("GDP Growth Rate QoQ Adv",), ("GDP Growth Rate QoQ Adv",)),
    "ism": ("ISM 製造業", ("ISM Manufacturing PMI",), ("ISM Manufacturing PMI",)),
}


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def kind_of(title: str) -> str | None:
    for k, (_, titles, _) in KINDS.items():
        for t in titles:
            # 「Inflation Rate MoM」不能吃到「Core Inflation Rate MoM」：要完全相同，或是 GDP 那種後面還有字的
            if title == t or (k == "gdp" and title.startswith(t)):
                return k
    return None


def fetch_range(s: date, e: date) -> list[dict]:
    for i in range(4):
        try:
            r = requests.get("https://economic-calendar.tradingview.com/events", timeout=40,
                             headers={"Origin": "https://www.tradingview.com", "User-Agent": "Mozilla/5.0"},
                             params={"from": f"{s}T00:00:00.000Z", "to": f"{e}T00:00:00.000Z", "countries": "US"})
            return r.json().get("result", [])
        except (requests.RequestException, ValueError) as ex:
            log(f"{s} 失敗：{ex}")
            time.sleep(5 * (i + 1))
    return []


def group(raw: list[dict]) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for e in raw:
        k = kind_of(e.get("title") or "")
        if not k:
            continue
        t = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(TPE).isoformat(timespec="minutes")
        g = out.setdefault((k, t), {"key": k, "t": t, "period": e.get("period"), "items": {}})
        g["items"][e["title"]] = [e.get("actual"), e.get("forecast"), e.get("previous")]
    for g in out.values():
        mains = KINDS[g["key"]][2]
        m = next((x for x in mains if x in g["items"]), None) or next((x for x in g["items"] if x.startswith(mains[0])), None)
        g["main"] = m
        g["actual"], g["forecast"], g["previous"] = g["items"].get(m, [None, None, None]) if m else (None, None, None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2017-05-01")
    a = ap.parse_args()
    try:
        old = json.loads(PATH.read_text(encoding="utf-8")).get("events", [])
    except (OSError, ValueError):
        old = []
    today = datetime.now(TPE).date()
    s = date.fromisoformat(a.since) if not old else today - timedelta(days=90)
    end = today + timedelta(days=45)
    ev = {(e["key"], e["t"]): e for e in old if e["t"][:10] < s.isoformat()}
    raw = []
    d = s
    while d < end:
        nxt = min(d + timedelta(days=31), end)
        raw += fetch_range(d, nxt)
        d = nxt
        time.sleep(1)
    ev.update(group(raw))
    events = sorted(ev.values(), key=lambda e: e["t"])
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "kinds": {k: v[0] for k, v in KINDS.items()},
                                "events": events}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    cnt = {}
    for e in events:
        cnt[e["key"]] = cnt.get(e["key"], 0) + 1
    log(f"美國事件：{len(events)} 筆（{cnt}），{events[0]['t'][:10] if events else ''} ～ {events[-1]['t'][:10] if events else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
