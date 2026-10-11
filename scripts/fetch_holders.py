#!/usr/bin/env python3
"""
集保股權分散表（每週）：大戶（千張、400 張以上）、散戶持股比例與股東人數。

資料來源：
  最新一週全部股票：集保開放資料 getOD.ashx?id=1-5（CSV）
  過去週別：集保「股權分散表查詢」qryStock（一次一檔一週），只回補成交值前 BACKFILL_TOP 名

輸出 JSS_DATA_DIR/holders/<YYYY-MM-DD>.json：{代號: [股東人數, 千張以上%, 400張以上%, 50張以下%, 千張以上人數]}
持股分級：1~15 依張數由小到大（15＝1000 張以上），16 差異調整，17 合計。
用法：python scripts/fetch_holders.py [--weeks 12] [--top 300] [--minutes 30]
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "holders"
TPE = timezone(timedelta(hours=8))
QRY = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
CODE = re.compile(r"\d{4}")

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"})


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return 0.0


def summarize(levels: dict[int, tuple[float, float]]) -> list:
    """levels: 分級 → (人數, 占比%)"""
    pct = lambda ks: round(sum(levels.get(k, (0, 0))[1] for k in ks), 2)  # noqa: E731
    return [int(levels.get(17, (0, 0))[0]), pct([15]), pct([12, 13, 14, 15]), pct(range(1, 9)), int(levels.get(15, (0, 0))[0])]


def latest_week():
    r = S.get("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5", timeout=120)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig", errors="replace")
    by: dict[str, dict[int, tuple[float, float]]] = {}
    day = None
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 6 or not row[0].strip().isdigit():
            continue
        day = row[0].strip()
        code = row[1].strip()
        if CODE.fullmatch(code):
            by.setdefault(code, {})[int(row[2])] = (num(row[3]), num(row[5]))
    if not day:
        raise RuntimeError("集保開放資料格式不符")
    d = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    doc = {c: summarize(v) for c, v in by.items()}
    path = OUT / f"{d}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    old.update(doc)
    path.write_text(json.dumps(old, separators=(",", ":")), encoding="utf-8")
    log(f"最新一週 {d}：{len(doc)} 檔")
    return d


def qry_session():
    r = S.get(QRY, timeout=60)
    tok = re.search(r'name="SYNCHRONIZER_TOKEN" value="([^"]+)"', r.text)
    dates = re.findall(r'<option[^>]*value="(\d{8})"', r.text)
    if not tok:
        raise RuntimeError("集保查詢頁沒有 token")
    return tok.group(1), dates


def qry(code: str, week: str, state: dict) -> list | None:
    for i in range(3):
        try:
            r = S.post(QRY, timeout=60, data={
                "SYNCHRONIZER_TOKEN": state["tok"], "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock", "method": "submit",
                "firDate": state["first"], "scaDate": week, "sqlMethod": "StockNo", "stockNo": code, "stockName": ""})
            m = re.search(r'name="SYNCHRONIZER_TOKEN" value="([^"]+)"', r.text)
            if m:
                state["tok"] = m.group(1)
            levels = {}
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
                c = [re.sub(r"<[^>]+>|\s|&nbsp;", "", x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                if len(c) >= 5 and c[0].isdigit():
                    levels[int(c[0])] = (num(c[2]), num(c[4]))
                elif len(c) >= 4 and c[0] in ("合計", "合　計"):
                    levels[17] = (num(c[1]), num(c[3]))
            if levels:
                if 17 not in levels:
                    levels[17] = (sum(v[0] for k, v in levels.items() if k <= 15), 100.0)
                return summarize(levels)
            return None
        except requests.RequestException:
            time.sleep(5 * (i + 1))
            try:
                state["tok"], _ = qry_session()
            except (requests.RequestException, RuntimeError):
                pass
    return None


def top_codes(n: int) -> list[str]:
    files = sorted((DATA_DIR / "daily").glob("20*.json"))
    if not files:
        return []
    q = json.loads(files[-1].read_text(encoding="utf-8"))["q"]
    return [c for c, v in sorted(q.items(), key=lambda kv: -(kv[1][8] or 0)) if CODE.fullmatch(c) and not c.startswith("0")][:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--top", type=int, default=300)
    ap.add_argument("--minutes", type=float, default=15)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        latest_week()
    except (requests.RequestException, RuntimeError) as e:
        log(f"✗ 最新一週：{e}")
    try:
        tok, dates = qry_session()
    except (requests.RequestException, RuntimeError) as e:
        log(f"✗ 集保查詢頁：{e}")
        return 0
    state = {"tok": tok, "first": dates[0] if dates else ""}
    codes = top_codes(a.top)
    n = 0
    for week in dates[1:a.weeks]:
        d = f"{week[:4]}-{week[4:6]}-{week[6:]}"
        path = OUT / f"{d}.json"
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        todo = [c for c in codes if c not in doc]
        for c in todo:
            if time.time() > deadline:
                break
            v = qry(c, week, state)
            if v:
                doc[c] = v
                n += 1
            time.sleep(0.6)
        path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        log(f"  {d}：{len(doc)} 檔")
        if time.time() > deadline:
            break
    log(f"本次回補 {n} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
