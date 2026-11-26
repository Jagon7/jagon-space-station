#!/usr/bin/env python3
"""
研究用：個股現股當沖歷史（2014 起），驗證「高當沖比＋開高走低」與大小型股預測過濾
來源：證交所 exchangeReport/TWTB4U、櫃買 www/zh-tw/intraday/stat（每個交易日一次）
  只留當沖買進金額 ≥ 3,000 萬的股票（策略要成交 ≥ 1 億、當沖比 ≥ 60%，用不到小的），檔案才不會太大
交易日：data/research/yahoo/_TWII.json
輸出 data/research/dt_hist/<年>.json {日期: {"tw": {代號: 當沖股數}, "tp": {...}}}；已抓的不重抓（沒資料的日子記成 {}）
證交所／櫃買擋雲端以外的主機，在 GitHub Actions 跑（research.yml job=dthist），到時間就停、下次接著抓
用法：python scripts/fetch_dt_hist.py [--minutes 300] [--from 2014-01-01]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "dt_hist"
MIN_BUY = 3e7
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"


def num(x) -> float:
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def get(url, params):
    for i in range(3):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (i + 1))
    return None


def one(d: str):
    """回傳 {"tw": {...}, "tp": {...}}；None＝連不上（下次重抓）"""
    out = {}
    for key, url, params in (("tw", "https://www.twse.com.tw/exchangeReport/TWTB4U", {"date": d.replace("-", ""), "selectType": "All", "response": "json"}),
                             ("tp", "https://www.tpex.org.tw/www/zh-tw/intraday/stat", {"type": "Daily", "date": d.replace("-", "/"), "response": "json"})):
        j = get(url, params)
        if j is None:
            return None
        tables = j.get("tables") or []
        rows = tables[1].get("data") if len(tables) >= 2 else (j.get("data") or [])
        m = {}
        for r in rows or []:
            c = str(r[0]).strip()
            if re.fullmatch(r"[1-9]\d{3}", c) and len(r) >= 5 and num(r[4]) >= MIN_BUY:
                m[c] = int(num(r[3]))
        out[key] = m
        time.sleep(2.5)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=300)
    ap.add_argument("--from", dest="start", default="2014-01-06")
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    days = [r[0] for r in json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"] if r[0] >= a.start]
    OUT.mkdir(parents=True, exist_ok=True)
    docs = {}
    for p in OUT.glob("20*.json"):
        docs[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    todo = [d for d in days if d not in docs.get(d[:4], {})]
    print(f"當沖歷史：{len(days)} 個交易日，要抓 {len(todo)} 天", flush=True)
    fails, n = 0, 0
    for d in reversed(todo):   # 新的先抓：近幾年最有用
        if time.time() > deadline:
            print("到時間，下次接著抓", flush=True)
            break
        x = one(d)
        if x is None:
            fails += 1
            if fails >= 8:
                print("連續連不上，可能被擋，停止", flush=True)
                break
            continue
        fails = 0
        docs.setdefault(d[:4], {})[d] = x
        n += 1
        if n % 20 == 0:
            print(d, len(x.get("tw", {})), len(x.get("tp", {})), flush=True)
            for y, v in docs.items():
                (OUT / f"{y}.json").write_text(json.dumps(dict(sorted(v.items())), separators=(",", ":")), encoding="utf-8")
    for y, v in docs.items():
        (OUT / f"{y}.json").write_text(json.dumps(dict(sorted(v.items())), separators=(",", ":")), encoding="utf-8")
    print(f"完成 {n} 天", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
