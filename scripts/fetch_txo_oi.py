#!/usr/bin/env python3
"""
TXO 每日各履約價未平倉（研究「選擇權未平倉大的履約價會不會吸住／擋住台指期」用）

來源：期交所 optDataDown（每日行情，一次 8 天，太長會逾時）；只留一般交易時段
存 data/research/txo_oi/<YYYY-MM>.json：{日期: {到期別: {履約價: [買權未平倉, 賣權未平倉, 買權結算價, 賣權結算價]}}}
  到期別：月選 "202611"、週選 "202611W4"、週五週選 "202611F3"（依期交所寫法）
原始 CSV 不保留（一個月約 150MB）；已抓過的月份不重抓（當月會補新的日期）
用法：python scripts/fetch_txo_oi.py [--from 2020-03-01] [--to 今天]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "txo_oi"


def num(x):
    x = str(x).strip().replace(",", "")
    try:
        return float(x) if x not in ("", "-") else None
    except ValueError:
        return None


def download(a: date, b: date) -> str:
    for i in range(5):
        try:
            r = requests.post("https://www.taifex.com.tw/cht/3/optDataDown", headers={"User-Agent": "Mozilla/5.0"}, timeout=120,
                              data={"down_type": "1", "commodity_id": "TXO", "queryStartDate": a.strftime("%Y/%m/%d"), "queryEndDate": b.strftime("%Y/%m/%d")})
            if r.status_code == 200:
                t = r.content.decode("big5", errors="ignore")
                if "交易日期" in t[:200]:
                    return t
                if len(r.content) < 3000:  # 這段期間都休市
                    return ""
        except requests.RequestException:
            pass
        time.sleep(15 * (i + 1))
    raise RuntimeError(f"下載失敗 {a}～{b}")


def parse(txt: str, out: dict):
    for row in csv.reader(io.StringIO(txt)):
        if len(row) < 18 or row[17].strip() != "一般" or row[1].strip() != "TXO":
            continue
        d = row[0].strip().replace("/", "-")
        exp = row[2].strip()
        k = num(row[3])
        cp = row[4].strip()
        oi, settle = num(row[11]), num(row[10])
        if k is None or cp not in ("買權", "賣權"):
            continue
        v = out.setdefault(d, {}).setdefault(exp, {}).setdefault(str(int(k)), [0, 0, None, None])
        i = 0 if cp == "買權" else 1
        v[i] = int(oi or 0)
        v[2 + i] = settle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", default="2020-03-01")
    ap.add_argument("--to", dest="d1", default=date.today().isoformat())
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    m = date.fromisoformat(a.d0).replace(day=1)
    end = date.fromisoformat(a.d1)
    while m <= end:
        nm = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        f = OUT / f"{m:%Y-%m}.json"
        have = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        last = min(nm - timedelta(days=1), end)
        if have and (nm <= end or max(have) >= (end - timedelta(days=1)).isoformat()):
            m = nm
            continue
        s = date.fromisoformat(max(have)) + timedelta(days=1) if have else m
        t0 = time.time()
        while s <= last:
            e = min(s + timedelta(days=7), last)
            parse(download(s, e), have)
            s = e + timedelta(days=1)
            time.sleep(3)
        f.write_text(json.dumps(have, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{m:%Y-%m}：{len(have)} 天、{time.time() - t0:.0f} 秒", flush=True)
        m = nm
    return 0


if __name__ == "__main__":
    sys.exit(main())
