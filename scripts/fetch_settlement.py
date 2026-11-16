#!/usr/bin/env python3
"""
結算策略（股票期貨月結算控盤）資料：期交所公開資料

  data/settlement/contracts.json   股期契約 → 標的股票（期交所 stockLists）{契約代號: [股票代號, 每口股數, 名稱]}
  data/settlement/lt/<日期>.json   當天各股期「即將結算月份」的全市場未沖銷部位、前十大交易人／前十大特定法人買賣方未沖銷部位
                                   （期交所 largeTraderFutDown）＋ 期貨結算價／收盤價（futDataDown，盤中報價快照抓不到時估折溢價用）
                                   {契約代號: [全市場OI, 前十大交易人買, 前十大交易人賣, 前十大特法買, 前十大特法賣, 結算價, 收盤價]}
結算日：每月第三個星期三（遇休市順延）；本期＝上次結算日隔天 ～ 本次結算日
用法：python scripts/fetch_settlement.py [--days 30]（補最近 N 天還沒抓的）
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "settlement"
TPE = timezone(timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0"}


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def holidays() -> set[str]:
    try:
        return set(json.loads((DATA / "calendar.json").read_text(encoding="utf-8")).get("holidays", []))
    except (OSError, ValueError):
        return set()


def settlement_day(y: int, m: int, hol: set[str]) -> date:
    """每月第三個星期三，遇休市順延到下一個交易日"""
    d = date(y, m, 1)
    d += timedelta(days=(2 - d.weekday()) % 7 + 14)
    while d.weekday() >= 5 or d.isoformat() in hol:
        d += timedelta(days=1)
    return d


def period(today: date, hol: set[str]) -> tuple[date, date, str]:
    """(本期起日＝上次結算隔天, 本期結算日, 結算月份 YYYYMM)；今天就是結算日也算本期"""
    s = settlement_day(today.year, today.month, hol)
    if today > s:
        y, m = (today.year + (today.month == 12), today.month % 12 + 1)
        s = settlement_day(y, m, hol)
    py, pm = (s.year - (s.month == 1), (s.month - 2) % 12 + 1)
    prev = settlement_day(py, pm, hol)
    return prev + timedelta(days=1), s, f"{s.year}{s.month:02d}"


def post(url: str, data: dict, tries: int = 4) -> bytes:
    for i in range(tries):
        try:
            r = requests.post(url, data=data, headers=UA, timeout=60)
            if r.status_code == 200 and len(r.content) > 300:
                return r.content
            log(f"  {url.rsplit('/', 1)[-1]} {data.get('queryStartDate')} → HTTP {r.status_code}，{len(r.content)} bytes")
            if r.status_code == 200:
                return b""  # 休市日：沒有資料
        except requests.RequestException as e:
            log(f"  連線失敗：{e}")
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"{url} 抓取失敗")


def fetch_contracts() -> dict:
    h = requests.get("https://www.taifex.com.tw/cht/2/stockLists", headers=UA, timeout=60).text
    out = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(c) > 11 and re.fullmatch(r"[A-Z0-9]{2,3}", c[0]) and "股票期貨標的" in c[4]:
            out[c[0]] = [c[2], int(c[11].replace(",", "") or 0), c[3]]
    return out


def fetch_day(d: date, month: str) -> dict:
    ds = d.strftime("%Y/%m/%d")
    raw = post("https://www.taifex.com.tw/cht/3/largeTraderFutDown", {"queryStartDate": ds, "queryEndDate": ds})
    if not raw:
        return {}
    out: dict[str, list] = {}
    for r in csv.reader(io.StringIO(raw.decode("big5", errors="ignore"))):
        if len(r) < 10 or r[3].strip() != month:
            continue
        code = r[1].strip()
        v = out.setdefault(code, [int(r[9] or 0), 0, 0, 0, 0, None, None])
        if r[4].strip() == "0":    # 全部交易人
            v[1], v[2] = int(r[7] or 0), int(r[8] or 0)
        elif r[4].strip() == "1":  # 特定法人
            v[3], v[4] = int(r[7] or 0), int(r[8] or 0)
    time.sleep(3)
    raw = post("https://www.taifex.com.tw/cht/3/futDataDown",
               {"down_type": "1", "commodity_id": "all", "queryStartDate": ds, "queryEndDate": ds})
    for r in csv.reader(io.StringIO(raw.decode("big5", errors="ignore"))):
        if len(r) < 18 or r[17].strip() != "一般" or r[2].strip() != month or not r[1].strip().endswith("F"):
            continue
        code = r[1].strip()[:-1]
        if code in out:
            for i, col in ((5, 10), (6, 6)):
                try:
                    out[code][i] = float(r[col])
                except ValueError:
                    pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    hol = holidays()
    now = datetime.now(TPE)
    today = now.date()
    (OUT / "lt").mkdir(parents=True, exist_ok=True)
    cpath = OUT / "contracts.json"
    try:
        old = json.loads(cpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    if not old.get("contracts") or old.get("updated", "") < (today - timedelta(days=6)).isoformat():
        c = fetch_contracts()
        if len(c) > 100:
            cpath.write_text(json.dumps({"updated": today.isoformat(), "contracts": c}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            log(f"股期契約：{len(c)} 個")
    got = 0
    for i in range(a.days, -1, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5 or d.isoformat() in hol or (d == today and now.hour < 15):
            continue
        f = OUT / "lt" / f"{d.isoformat()}.json"
        if f.exists() and d < today - timedelta(days=1):
            continue
        start, sday, month = period(d, hol)
        try:
            doc = fetch_day(d, month)
        except RuntimeError as e:
            log(f"{d}：{e}")
            continue
        if doc:
            f.write_text(json.dumps({"date": d.isoformat(), "month": month, "rows": doc}, separators=(",", ":")), encoding="utf-8")
            got += 1
            log(f"{d}：{len(doc)} 個契約（結算月 {month}）")
        time.sleep(3)
    start, sday, month = period(today, hol)
    log(f"本期 {start} ～ {sday}（{month}），本次新增 {got} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
