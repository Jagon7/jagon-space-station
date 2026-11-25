#!/usr/bin/env python3
"""
當沖停損研究資料：熱門股「開盤放空」事件當天的盤中 K 線（永豐 Shioaji api.kbars，只查行情，不下單）

事件：data/research/dt_stop_events.json [[日期, 代號, 市場, 前一天成交額名次, 開盤跳空%, 前一天漲跌%, 前 5 日漲跌%, 前一天收盤], ...]
     （前一天成交額前 50 名、前一天漲停或前 5 日漲 ≥ 10%，開高 0～4%；或前一天漲停、開高 4～9.5%；2022 起）
輸出 data/research/dt_stop_bars.json.gz：{"日期|代號": {"b": 5 分 K [[開, 高, 低, 收, 量(張)], ...] 共 54 根（09:00～13:30，
     價格用「相對前一天收盤」的萬分之一表示，例：+523＝+5.23%），
     "lim": 第一次碰到漲停的分鐘（0＝09:00；沒碰到 null）, "lock": 鎖在漲停（最低＝最高＝漲停價）的分鐘數,
     "lockEnd": 13:25 以後是否鎖漲停（券差風險：收盤買不回來）, "hi1": 1 分 K 最高（萬分之一）}
新到舊抓，已有的跳過；每天永豐有流量上限，剩不到 60MB 就停（下次接著抓）
用法：python scripts/fetch_dt_stop.py [--minutes 300]
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

EV = DATA / "research" / "dt_stop_events.json"
OUT = DATA / "research" / "dt_stop_bars.json.gz"


def tick_limit(pc: float) -> float:
    """漲停價：前一天收盤 × 1.1，依台股升降單位無條件捨去"""
    up = pc * 1.1
    for lim, tick in ((10, 0.01), (50, 0.05), (100, 0.1), (500, 0.5), (1000, 1), (1e12, 5)):
        if up < lim:
            return round(int(up / tick + 1e-6) * tick, 2)
    return up


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=300)
    a = ap.parse_args()
    if not os.environ.get("SHIOAJI_API_KEY"):
        log("沒有永豐金鑰，略過")
        return 0
    deadline = time.time() + a.minutes * 60
    ev = json.loads(EV.read_text(encoding="utf-8"))
    try:
        have = json.loads(gzip.decompress(OUT.read_bytes()))
    except (OSError, ValueError):
        have = {}
    todo = [e for e in sorted(ev, key=lambda e: e[0], reverse=True) if f"{e[0]}|{e[1]}" not in have]
    log(f"事件 {len(ev)} 個，要抓 {len(todo)} 個")
    api = sj_login()
    shift, n, fails = None, 0, 0
    for e in todo:
        if time.time() > deadline:
            log("時間到")
            break
        d, code, pc = e[0], e[1], e[7]
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
            have[f"{d}|{code}"] = None  # 沒資料（停牌等）
            continue
        if shift is None:
            shift = 1 if min(mins) == 1 else 0  # K 棒時間是結束時間 → 往前移 1 分
            log(f"K 棒時間：{'結束時間，往前移 1 分' if shift else '開始時間'}")
        mins = {m - shift: v for m, v in mins.items()}
        lim = tick_limit(pc)
        bp = lambda p: round((p / pc - 1) * 10000)  # noqa: E731
        bars = []
        for s in range(0, 270, 5):
            g = [mins[m] for m in range(s, s + 5) if m in mins]
            if s == 265:  # 13:25～13:30 收盤集合競價併進最後一根
                g += [mins[m] for m in range(270, 272) if m in mins]
            if g:
                bars.append([bp(g[0][0]), bp(max(x[1] for x in g)), bp(min(x[2] for x in g)), bp(g[-1][3]), round(sum(x[4] for x in g))])
            else:
                bars.append(None)
        first = next((m for m in sorted(mins) if mins[m][1] >= lim - 1e-6), None)
        lock = sum(1 for v in mins.values() if v[2] >= lim - 1e-6)
        last = [mins[m] for m in sorted(mins) if m >= 265]
        have[f"{d}|{code}"] = {"b": bars, "lim": first, "lock": lock, "lockEnd": bool(last) and all(v[2] >= lim - 1e-6 for v in last),
                                "hi1": bp(max(v[1] for v in mins.values())), "limBp": bp(lim)}
        n += 1
        if n % 200 == 0:
            OUT.write_bytes(gzip.compress(json.dumps(have, separators=(",", ":")).encode()))
            u = api.usage()
            log(f"{n} 個（{d}），剩 {u.remaining_bytes / 1e6:.0f} MB")
            if u.remaining_bytes < 60e6:
                log("永豐流量快用完，停止")
                break
        time.sleep(0.05)
    OUT.write_bytes(gzip.compress(json.dumps(have, separators=(",", ":")).encode()))
    log(f"本次 {n} 個，累計 {sum(1 for v in have.values() if v)} 個")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
