#!/usr/bin/env python3
"""
研究用：指定日期、指定個股的三大法人買賣超（上市：證交所 T86；上櫃：櫃買中心 insti/dailyTrade，2014 年底以前格式不同）
讀 data/research/new_high_need.json {日期: {"twse": [代號...], "tpex": [...]}}（research_new_high.py --need 產生）
寫 data/research/new_high_inst.json {日期: {代號: [外資, 投信] 買賣超股數}}（要的代號當天沒有法人進出記 [0, 0]；那天整份沒資料記 null）；
該日要的代號都已有就跳過，每 50 天存一次。證交所連續抓太快會被擋，每次間隔 3 秒；在 GitHub Actions 上跑（research.yml，job=t86）
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_rebound_data import t86  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
NEED = DATA / "research" / "new_high_need.json"
OUT = DATA / "research" / "new_high_inst.json"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}


def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return 0.0


def tpex(d: str) -> dict | None:
    """{代號: [外資, 投信]} 股數；新格式（24 欄以上）：外資合計淨買在第 10 欄、投信在第 13 欄；舊格式看欄位名稱"""
    for i in range(3):
        try:
            j = requests.get("https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade", headers=H, timeout=60,
                             params={"type": "Daily", "sect": "EW", "date": d.replace("-", "/"), "response": "json"}).json()
            out = {}
            for t in j.get("tables") or []:
                f = [str(x) for x in t.get("fields") or []]
                for r in t.get("data") or []:
                    if len(r) >= 24:
                        out[str(r[0]).strip()] = [num(r[10]), num(r[13])]
                    elif "外資及陸資淨買股數" in f and "投信淨買股數" in f:
                        out[str(r[0]).strip()] = [num(r[f.index("外資及陸資淨買股數")]), num(r[f.index("投信淨買股數")])]
            return out
        except (requests.RequestException, ValueError):
            time.sleep(10 * (i + 1))
    return None


def main():
    need = json.loads(NEED.read_text(encoding="utf-8"))
    try:
        have = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        have = {}
    todo = [d for d in sorted(need) if not set(need[d]["twse"] + need[d]["tpex"]) <= set(have.get(d, {}))]
    print(f"{len(need)} 天，要抓 {len(todo)} 天", flush=True)
    t0, fails = time.time(), 0
    for n, d in enumerate(todo, 1):
        if time.time() - t0 > float(os.environ.get("T86_MAX_SEC", 5 * 3600)):
            print("時間到，下次接著抓", flush=True)
            break
        got = {}
        for mkt, fn in (("twse", lambda: t86(d.replace("-", ""))), ("tpex", lambda: tpex(d))):
            if not need[d][mkt]:
                continue
            j = fn()
            if j is None:
                got = None
                break
            if not j:  # 交易日卻沒有資料（櫃買 2014 年底以前部分日子是空的）：記 null，回測當作沒有法人資料
                got.update({c: None for c in need[d][mkt]})
            else:
                got.update({c: [v[0] or 0, v[1] or 0] if (v := j.get(c)) else [0, 0] for c in need[d][mkt]})
            time.sleep(3)
        if got is None:
            fails += 1
            print(d, "失敗", flush=True)
            if fails >= 10:
                break
            time.sleep(60)
            continue
        have[d] = {**have.get(d, {}), **got}
        if n % 50 == 0:
            OUT.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
            print(n, d, flush=True)
    OUT.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
    print(f"共 {len(have)} 天", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
