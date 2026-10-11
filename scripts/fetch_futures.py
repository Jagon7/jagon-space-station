#!/usr/bin/env python3
"""
期貨選擇權籌碼（期交所）：三大法人台指期／小台未平倉、臺指選擇權買權賣權未平倉金額、Put/Call ratio、小台總未平倉（算散戶多空比）。

資料來源：期交所「三大法人－區分各期貨契約」「區分各選擇權契約買賣權」「臺指選擇權 Put/Call 比」「期貨每日交易行情」下載（CSV，可查期間，單次最多約一個月）。
輸出 JSS_DATA_DIR/futures/daily.json：{日期: {...}}，保留最近 KEEP 個交易日；每次重抓最近 10 天，缺的月份補齊。
用法：python scripts/fetch_futures.py [--months 7]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "futures" / "daily.json"
TPE = timezone(timedelta(hours=8))
BASE = "https://www.taifex.com.tw/cht/3/"
KEEP = 260
WHO = {"外資及陸資": "f", "外資": "f", "投信": "t", "自營商": "d"}

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"})


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def down(path: str, data: dict) -> list[dict]:
    for i in range(4):
        try:
            r = S.post(BASE + path, data=data, timeout=60)
            text = r.content.decode("big5hkscs", errors="replace")
            if r.status_code == 200 and "," in text.splitlines()[0]:
                return list(csv.DictReader(io.StringIO(text)))
        except (requests.RequestException, IndexError):
            pass
        time.sleep(10 * (i + 1))  # 查太快會遇到 Cloudflare 驗證頁，等一下再試
    raise RuntimeError(f"期交所下載失敗 {path} {data}")


def iso(s: str) -> str:
    y, m, d = s.strip().split("/")
    return f"{y}-{int(m):02d}-{int(d):02d}"


def part(fn):
    """單一資料失敗不影響同期間其他資料"""
    def wrap(*a):
        try:
            fn(*a)
        except RuntimeError as e:
            log(f"✗ {e}")
        time.sleep(3)
    return wrap


def fetch_range(a: date, b: date, db: dict):
    rng = {"queryStartDate": a.strftime("%Y/%m/%d"), "queryEndDate": b.strftime("%Y/%m/%d")}
    for f in (_insti, _options, _pc, _oi):
        part(f)(rng, db)


def _insti(rng, db):
    for cid, key in (("TXF", "txf"), ("MXF", "mtx")):  # 法人報表裡小台代碼是 MXF
        for r in down("futContractsDateDown", {**rng, "commodityId": cid}):
            who = WHO.get(r.get("身份別", "").strip())
            if who:
                rec = db.setdefault(iso(r["日期"]), {}).setdefault(key, {})
                rec[who] = [num(r["多空未平倉口數淨額"]), num(r["多空未平倉契約金額淨額(千元)"])]
        time.sleep(3)


def _options(rng, db):
    for r in down("callsAndPutsDateDown", {**rng, "commodityId": "TXO"}):
        who = WHO.get(r.get("身份別", "").strip())
        cp = "c" if r.get("買賣權別", "").strip().upper() == "CALL" else "p"
        if who:
            db.setdefault(iso(r["日期"]), {}).setdefault("txo", {}).setdefault(who, {})[cp] = [num(r["未平倉口數買賣淨額"]), num(r["未平倉契約金額買賣淨額(千元)"])]


def _pc(rng, db):
    for r in down("pcRatioDown", rng):
        db.setdefault(iso(r["日期"]), {})["pc"] = [num(r["買賣權成交量比率%"]), num(r["買賣權未平倉量比率%"])]


def _oi(rng, db):
    for cid, key in (("MTX", "mtxOI"), ("TX", "txfOI")):  # 行情檔的台指期代碼是 TX
        tot: dict[str, float] = {}
        px: dict[str, tuple[str, float]] = {}
        for r in down("futDataDown", {**rng, "down_type": "1", "commodity_id": cid}):
            if r.get("交易時段", "").strip() != "一般":
                continue
            month = r.get("到期月份(週別)", "").strip()
            if "/" in month or "W" in month:  # 價差、週契約不算
                continue
            d = iso(r["交易日期"])
            oi = num(r.get("未沖銷契約數"))
            if oi:
                tot[d] = tot.get(d, 0) + oi
            c = num(r.get("收盤價"))
            if c and (d not in px or month < px[d][0]):
                px[d] = (month, c)  # 最近月
        for d, v in tot.items():
            db.setdefault(d, {})[key] = v
        if cid == "TX":
            for d, (_, c) in px.items():
                db.setdefault(d, {})["px"] = c
        time.sleep(3)


def last_trading_day() -> date:
    """查詢迄日不能超過最後一個交易日，否則期交所回錯誤頁"""
    holidays = set()
    cal = DATA_DIR / "calendar.json"
    if cal.exists():
        holidays = set(json.loads(cal.read_text(encoding="utf-8")).get("holidays", []))
    now = datetime.now(TPE)
    d = now.date() if now.hour >= 15 else now.date() - timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in holidays:
        d -= timedelta(days=1)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=7)
    a = ap.parse_args()
    db = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    today = last_trading_day()
    have_months = {k[:7] for k in db}
    spans = []
    end = today
    for i in range(a.months):
        start = end.replace(day=1)
        if i == 0 or start.strftime("%Y-%m") not in have_months or not all(
                db[k].get("txo") and db[k].get("mtx") and db[k].get("pc") and db[k].get("px") for k in db if k.startswith(start.strftime("%Y-%m"))):
            spans.append((start, end))
        end = start - timedelta(days=1)
    if spans and spans[0][0] > today - timedelta(days=10):  # 月初時也重抓上個月底
        spans.append((today - timedelta(days=10), spans[0][0] - timedelta(days=1)))
    for s, e in spans:
        try:
            fetch_range(s, e, db)
            log(f"  {s} ~ {e}")
        except RuntimeError as ex:
            log(f"✗ {ex}")
    keep = sorted(k for k, v in db.items() if v.get("txf"))[-KEEP:]
    db = {k: db[k] for k in keep}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"期貨籌碼：{len(db)} 天（{keep[0] if keep else '—'} ~ {keep[-1] if keep else '—'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
