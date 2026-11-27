#!/usr/bin/env python3
"""
研究用：個股盤中 1 分 K（永豐 Shioaji api.kbars，只查行情，不下單）
清單：data/research/intraday_need.json [[日期, 代號, 前一天收盤], ...]（scripts/intraday_need.py 產生）
輸出 data/research/intraday_1m/<YYYY-MM>.json.gz {"日期|代號": [前一天收盤, [[分, 開, 高, 低, 收, 量(張)], ...]]}
  分＝0 是 09:00（K 棒時間已換成開始時間）；價格用「相對前一天收盤」的萬分之一（例 +523＝+5.23%）；沒資料記 null
新到舊抓，已有的跳過；永豐每天有流量上限，剩不到 60MB 就停（下次接著抓）
在 GitHub Actions 跑（research.yml job=intraday）；用法：python scripts/fetch_intraday_1m.py [--minutes 300]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_tx_night import DATA, log, sj_login  # noqa: E402

NEED = DATA / "research" / "intraday_need.json"
OUT = DATA / "research" / "intraday_1m"


def load_month(ym: str) -> dict:
    p = OUT / f"{ym}.json.gz"
    try:
        return json.loads(gzip.decompress(p.read_bytes()))
    except (OSError, ValueError):
        return {}


def save_month(ym: str, doc: dict):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{ym}.json.gz").write_bytes(gzip.compress(json.dumps(doc, separators=(",", ":")).encode()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=300)
    a = ap.parse_args()
    if not os.environ.get("SHIOAJI_API_KEY"):
        log("沒有永豐金鑰，略過")
        return 0
    deadline = time.time() + a.minutes * 60
    need = json.loads(NEED.read_text(encoding="utf-8"))
    months: dict[str, dict] = {}
    for d, _, _ in need:
        if d[:7] not in months:
            months[d[:7]] = load_month(d[:7])
    todo = [e for e in need if f"{e[0]}|{e[1]}" not in months[e[0][:7]]]
    log(f"清單 {len(need)} 個，要抓 {len(todo)} 個")
    api = sj_login()
    shift, n, fails = None, 0, 0
    dirty = set()
    for d, code, pc in todo:
        if time.time() > deadline:
            log("時間到")
            break
        ym = d[:7]
        try:
            c = api.Contracts.Stocks[code]
            k = api.kbars(contract=c, start=d, end=d)
        except Exception as ex:  # noqa: BLE001
            fails += 1
            log(f"{d} {code} 失敗：{ex}")
            if fails > 30:
                break
            continue
        mins = {}
        for ts, o, h, lo, cl, v in zip(k.ts, k.Open, k.High, k.Low, k.Close, k.Volume):
            tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)  # 永豐的 ts 是台灣時間當成 UTC
            if tm.date().isoformat() != d:
                continue
            m = (tm.hour - 9) * 60 + tm.minute
            if 0 <= m <= 271:
                mins[m] = (float(o), float(h), float(lo), float(cl), int(v))
        if len(mins) < 100:
            months[ym][f"{d}|{code}"] = None
            dirty.add(ym)
            continue
        if shift is None:
            shift = 1 if min(mins) == 1 else 0
            log(f"K 棒時間：{'結束時間，往前移 1 分' if shift else '開始時間'}")
        bp = lambda p: round((p / pc - 1) * 10000)  # noqa: E731
        months[ym][f"{d}|{code}"] = [pc, [[m - shift, bp(o), bp(h), bp(lo), bp(cl), v] for m, (o, h, lo, cl, v) in sorted(mins.items())]]
        dirty.add(ym)
        n += 1
        if n % 300 == 0:
            for x in dirty:
                save_month(x, months[x])
            dirty.clear()
            u = api.usage()
            log(f"{n} 個（{d}），剩 {u.remaining_bytes / 1e6:.0f} MB")
            if u.remaining_bytes < 60e6:
                log("永豐流量快用完，停止")
                break
        time.sleep(0.05)
    for x in dirty:
        save_month(x, months[x])
    tot = sum(1 for m in months.values() for v in m.values() if v)
    log(f"本次 {n} 個，累計 {tot} 個")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
