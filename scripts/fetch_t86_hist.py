#!/usr/bin/env python3
"""
研究用：指定日期、指定個股的上市三大法人買賣超（證交所 T86）
讀 data/research/new_high_need.json {日期: [代號...]}（research_new_high.py --need 產生）
寫 data/research/new_high_inst.json {日期: {代號: [外資, 投信] 買賣超股數}}；已抓過的日期跳過，每 50 天存一次
證交所連續抓太快會被擋，每次間隔 3 秒；在 GitHub Actions 上跑（research.yml，job=t86）
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_rebound_data import t86  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
NEED = DATA / "research" / "new_high_need.json"
OUT = DATA / "research" / "new_high_inst.json"


def main():
    need = json.loads(NEED.read_text(encoding="utf-8"))
    try:
        have = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        have = {}
    todo = [d for d in sorted(need) if d not in have]
    print(f"{len(need)} 天，要抓 {len(todo)} 天", flush=True)
    t0, fails = time.time(), 0
    for n, d in enumerate(todo, 1):
        if time.time() - t0 > float(os.environ.get("T86_MAX_SEC", 5 * 3600)):
            print("時間到，下次接著抓", flush=True)
            break
        j = t86(d.replace("-", ""))
        if j is None:
            fails += 1
            print(d, "失敗", flush=True)
            if fails >= 10:
                break
            time.sleep(60)
            continue
        have[d] = {c: [v[0], v[1]] for c in need[d] if (v := j.get(c))}
        if n % 50 == 0:
            OUT.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
            print(n, d, flush=True)
        time.sleep(3)
    OUT.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
    print(f"共 {len(have)} 天", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
