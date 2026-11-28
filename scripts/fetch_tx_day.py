#!/usr/bin/env python3
"""
台指期（大台 TX）日盤 1 分 K（08:45～13:45），給「台指期當日型態（突破／均值回歸）」研究

來源：
  shioaji  永豐 api.kbars（TXFR1 近月連續，只查行情）：回補 2020/3 起
  taifex   期交所前 30 個交易日每筆成交：每天補最新的（成交量最大的月份）
分鐘序號 m＝（時刻 − 08:45）的分鐘數，0 ＝ 08:45～08:46，299 ＝ 13:44～13:45，300＝13:45 收盤那一刻
存 data/futures/day/<YYYY-MM>.json {日期: {"src", "contract", "bars": [[m, 開, 高, 低, 收, 口數], ...]}}
用法：python scripts/fetch_tx_day.py [--taifex] [--shioaji --since 2020-03-01 --minutes 20]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_tx_night import DATA, TPE, UA, log, sj_login  # noqa: E402

OUT = DATA / "futures" / "day"


def day_min(hh: int, mm: int):
    t = hh * 60 + mm - (8 * 60 + 45)
    return t if 0 <= t <= 300 else None


def load_month(ym: str) -> dict:
    try:
        return json.loads((OUT / f"{ym}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(days: dict[str, dict]):
    by: dict[str, dict] = {}
    for d, v in days.items():
        by.setdefault(d[:7], {})[d] = v
    OUT.mkdir(parents=True, exist_ok=True)
    for ym, add in by.items():
        doc = load_month(ym)
        for d, v in add.items():
            old = doc.get(d)
            if old and old.get("src") == "taifex" and v["src"] != "taifex":
                continue  # 期交所逐筆優先
            doc[d] = v
        for v in doc.values():
            v["bars"] = [[int(x) if float(x).is_integer() else x for x in b] for b in v["bars"]]
        (OUT / f"{ym}.json").write_text(json.dumps(dict(sorted(doc.items())), separators=(",", ":")), encoding="utf-8")


FULL = 250   # 日盤正常約 300 根；不足 FULL 根視為不完整（下載檔殘缺），下次重抓（跌停鎖死等真的沒成交的日子會一直重試，但只多一次請求）


def have_days() -> set[str]:
    out = set()
    for f in OUT.glob("20*.json") if OUT.exists() else []:
        out |= {d for d, v in load_month(f.stem).items() if len(v.get("bars") or []) >= FULL}
    return out


def taifex_day(d: date) -> dict | None:
    import requests
    url = f"https://www.taifex.com.tw/file/taifex/Dailydownload/DailydownloadCSV/Daily_{d:%Y_%m_%d}.zip"
    r = requests.get(url, headers=UA, timeout=120)
    if r.status_code != 200 or r.content[:2] != b"PK":
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    raw = z.read(z.namelist()[0]).decode("big5", errors="ignore")
    acc: dict[str, dict[int, list]] = {}
    ds = d.strftime("%Y%m%d")
    for row in csv.reader(io.StringIO(raw)):
        if len(row) < 6 or row[1].strip() != "TX" or row[0].strip() != ds:
            continue
        mon = row[2].strip()
        if "/" in mon or not mon.isdigit():
            continue
        t = row[3].strip().zfill(6)
        m = day_min(int(t[:2]), int(t[2:4]))
        if m is None:
            continue
        try:
            px, q = float(row[4]), int(float(row[5])) // 2
        except ValueError:
            continue
        b = acc.setdefault(mon, {}).get(m)
        if b is None:
            acc[mon][m] = [px, px, px, px, q]
        else:
            b[1] = max(b[1], px); b[2] = min(b[2], px); b[3] = px; b[4] += q
    if not acc:
        return None
    mon = max(acc, key=lambda k: sum(x[4] for x in acc[k].values()))
    bars = [[m, *acc[mon][m]] for m in sorted(acc[mon])]
    return {"src": "taifex", "contract": mon, "bars": bars} if len(bars) > 100 else None


def run_taifex(days: int = 35):
    have = set()
    for f in OUT.glob("20*.json") if OUT.exists() else []:
        have |= {d for d, v in load_month(f.stem).items() if v.get("src") == "taifex" and len(v.get("bars") or []) >= FULL}
    today = datetime.now(TPE).date()
    got = {}
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5 or d.isoformat() in have or (d == today and datetime.now(TPE).hour < 15):
            continue
        try:
            v = taifex_day(d)
        except Exception as e:  # noqa: BLE001
            log(f"{d} 下載失敗：{e}")
            continue
        if v:
            got[d.isoformat()] = v
            log(f"期交所 {d}：{v['contract']} {len(v['bars'])} 根")
        time.sleep(2)
    save(got)
    log(f"期交所日盤：新增 {len(got)} 天")


def run_shioaji(since: str, minutes: float):
    deadline = time.time() + minutes * 60
    api = sj_login()
    c = api.Contracts.Futures.TXF.TXFR1
    have = have_days()
    cur = datetime.now(TPE).date().replace(day=1)
    stop = date.fromisoformat(since)
    total = 0
    shift = None
    while cur >= stop and time.time() < deadline:
        e = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if sum(1 for d in have if d.startswith(cur.isoformat()[:7])) >= 15 and cur.month != datetime.now(TPE).month:
            cur = (cur - timedelta(days=1)).replace(day=1)
            continue
        try:
            k = api.kbars(contract=c, start=cur.isoformat(), end=e.isoformat())
        except Exception as ex:  # noqa: BLE001
            log(f"{cur:%Y-%m} 失敗：{ex}")
            break
        acc: dict[str, dict[int, list]] = {}
        for ts, o, h, lo, cl, v in zip(k.ts, k.Open, k.High, k.Low, k.Close, k.Volume):
            tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)
            m = day_min(tm.hour, tm.minute)
            if m is None:
                continue
            acc.setdefault(tm.date().isoformat(), {})[m] = [float(o), float(h), float(lo), float(cl), int(v)]
        if not acc:
            log(f"{cur:%Y-%m}：沒有日盤資料，停止")
            break
        if shift is None:
            firsts = [min(v) for v in acc.values()]
            # 永豐 K 棒時間是「結束時間」的話第一根會在 08:46（m＝1），往前移 1 分對齊
            shift = 1 if sorted(firsts)[len(firsts) // 2] == 1 else 0
            log(f"K 棒時間對齊：{'結束時間，往前移 1 分' if shift else '開始時間'}")
        got = {d: {"src": "shioaji", "contract": "TXFR1", "bars": [[m - shift, *bars[m]] for m in sorted(bars)]}
               for d, bars in acc.items() if d not in have and len(bars) > 100}
        save(got)
        have |= set(got)
        total += len(got)
        u = api.usage()
        log(f"{cur:%Y-%m}：{len(got)} 天（剩 {u.remaining_bytes / 1e6:.0f} MB）")
        if u.remaining_bytes < 30e6:
            log("永豐流量快用完，下次接著補")
            break
        cur = (cur - timedelta(days=1)).replace(day=1)
    log(f"永豐日盤：新增 {total} 天")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taifex", action="store_true")
    ap.add_argument("--shioaji", action="store_true")
    ap.add_argument("--since", default="2020-03-01")
    ap.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args()
    if a.taifex:
        run_taifex()
    if a.shioaji and os.environ.get("SHIOAJI_API_KEY"):
        run_shioaji(a.since, a.minutes)
    log(f"日盤資料共 {len(have_days())} 天")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
