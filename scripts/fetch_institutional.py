#!/usr/bin/env python3
"""
三大法人（外資、投信、自營商）個股買賣超，每天一份，可回補。

資料來源：
  上市：證交所 T86（三大法人買賣超日報）
  上櫃：櫃買中心 insti/dailyTrade

輸出 JSS_DATA_DIR/insti/<YYYY-MM-DD>.json：{代號: [名稱, 市場(0上市/1上櫃), 外資, 投信, 自營商, 合計]}（單位：張）
交易日以 data/daily 已有的日期為準（沒有就用平日），每次補齊最近 DAYS 天中缺的。
用法：python scripts/fetch_institutional.py [--days 130] [--minutes 20]
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
OUT = DATA_DIR / "insti"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
CODE = re.compile(r"\d{4}|00\d{2,4}[A-Z]?")
KEEP = 140

S = requests.Session()
S.headers.update({"User-Agent": UA})


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def lots(v) -> int:
    try:
        return round(float(str(v).replace(",", "").strip()) / 1000)
    except ValueError:
        return 0


def get_json(url, params):
    for i in range(4):
        try:
            r = S.get(url, params=params, timeout=60)
            if r.status_code == 200 and r.text.strip()[:1] == "{":
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(4 * (i + 1))
    raise RuntimeError(f"抓取失敗 {url} {params}")


def twse(d: date) -> dict | None:
    doc = get_json("https://www.twse.com.tw/rwd/zh/fund/T86", {"date": d.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"})
    if doc.get("stat") != "OK":
        return None
    t = (doc.get("tables") or [doc])[0]
    f = [re.sub(r"\s+", "", x) for x in (t.get("fields") or [])]
    data = t.get("data") or []
    if not f or not data:
        return None
    ic = 0
    ifor = [i for i, x in enumerate(f) if "買賣超" in x and ("外陸資" in x or "外資自營商" in x)]
    itr = next((i for i, x in enumerate(f) if x.startswith("投信買賣超")), None)
    idl = next((i for i, x in enumerate(f) if x == "自營商買賣超股數"), None)
    itot = next((i for i, x in enumerate(f) if x.startswith("三大法人買賣超")), None)
    out = {}
    for r in data:
        code = str(r[ic]).strip()
        if CODE.fullmatch(code):
            out[code] = [str(r[1]).strip(), 0, sum(lots(r[i]) for i in ifor), lots(r[itr]) if itr is not None else 0,
                         lots(r[idl]) if idl is not None else 0, lots(r[itot]) if itot is not None else 0]
    return out


def tpex(d: date) -> dict | None:
    doc = get_json("https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade",
                   {"type": "Daily", "sect": "EW", "date": d.strftime("%Y/%m/%d"), "response": "json"})
    if str(doc.get("date", "")) != d.strftime("%Y%m%d") or not doc.get("tables"):
        return None
    out = {}
    for r in doc["tables"][0].get("data") or []:
        code = str(r[0]).strip()
        # 欄位：外資(不含自營) 3 欄、外資自營 3 欄、外資合計 3 欄、投信 3 欄、自營自行 3 欄、自營避險 3 欄、自營合計 3 欄、三大法人合計
        if CODE.fullmatch(code) and len(r) >= 24:
            out[code] = [str(r[1]).strip(), 1, lots(r[10]), lots(r[13]), lots(r[22]), lots(r[23])]
    return out


def trading_days(n: int) -> list[date]:
    daily = sorted(p.stem for p in (DATA_DIR / "daily").glob("20*.json"))
    days = [date.fromisoformat(x) for x in daily[-n:]]
    now = datetime.now(TPE)
    d = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    # 今天（或最近平日）行情還沒進 daily 時也試著抓
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    if not days or d > days[-1]:
        days.append(d)
    return days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=130)
    ap.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for d in reversed(trading_days(a.days)):
        path = OUT / f"{d.isoformat()}.json"
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("_ok"):
                continue
        if time.time() > deadline:
            break
        try:
            tw = twse(d)
            time.sleep(2)
            tp = tpex(d)
            time.sleep(1)
        except RuntimeError as e:
            log(f"✗ {d}：{e}")
            continue
        if not tw and not tp:
            log(f"  {d}：還沒有資料")
            continue
        doc = {**(tw or {}), **(tp or {})}
        doc["_ok"] = tw is not None and tp is not None
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        n += 1
        log(f"  {d}：{len(doc) - 1} 檔{'' if doc['_ok'] else '（缺 ' + ('上市' if tw is None else '上櫃') + '）'}")
    for old in sorted(OUT.glob("20*.json"))[:-KEEP]:
        old.unlink()
    log(f"本次 {n} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
