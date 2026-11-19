#!/usr/bin/env python3
"""
加權指數與類股指數盤中 1 分 K（永豐 Shioaji api.kbars，只查行情）→ data/market/index1m/<YYYY-MM>.json
格式同 fetch_index_intraday.py（證交所 5 秒資料在雲端常被擋，改用永豐）：
  {日期: {"t": [每分鐘加權指數收盤，09:00～13:30 共 271 筆], "s": {類股名稱: [09:00, 09:15, 09:30, 10:00, 13:30 的指數]}}}
用法：python scripts/fetch_index_sj.py [--since 2020-03-01] [--minutes 30]（新到舊，每次查一個月）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_tx_night import DATA, TPE, log, sj_login  # noqa: E402

OUT = DATA / "market" / "index1m"
CHECK = [0, 15, 30, 60, 270]


def load(ym):
    try:
        return json.loads((OUT / f"{ym}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bars_by_day(k) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for ts, c in zip(k.ts, k.Close):
        tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)
        m = (tm.hour - 9) * 60 + tm.minute
        if 0 <= m <= 271 and c:
            out.setdefault(tm.date().isoformat(), {})[m] = float(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2020-03-01")
    ap.add_argument("--minutes", type=float, default=30)
    a = ap.parse_args()
    if not os.environ.get("SHIOAJI_API_KEY"):
        log("沒有永豐金鑰，略過")
        return 0
    deadline = time.time() + a.minutes * 60
    api = sj_login()
    tse = api.Contracts.Indexs.TSE
    items = []
    for c in tse:
        if isinstance(c, str):
            c = tse[c]
        items.append(c)
    main_c = next((c for c in items if getattr(c, "code", "") == "001"), None)
    secs = [c for c in items if c is not main_c]
    log(f"指數：加權 {'有' if main_c else '沒有'}，其他 {len(secs)} 個（例：{[getattr(c, 'name', '') for c in secs[:5]]}）")
    if not main_c:
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    have = set()
    for f in OUT.glob("20*.json"):
        have |= set(load(f.stem))
    cur = datetime.now(TPE).date().replace(day=1)
    stop = date.fromisoformat(a.since)
    shift = None
    while cur >= stop and time.time() < deadline:
        e = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        ym = cur.isoformat()[:7]
        if sum(1 for d in have if d.startswith(ym)) >= 15 and ym != datetime.now(TPE).strftime("%Y-%m"):
            cur = (cur - timedelta(days=1)).replace(day=1)
            continue
        main_days = bars_by_day(api.kbars(contract=main_c, start=cur.isoformat(), end=e.isoformat()))
        if not main_days:
            log(f"{ym}：沒有加權指數資料，停止")
            break
        if shift is None:
            firsts = sorted(min(v) for v in main_days.values())
            shift = 1 if firsts[len(firsts) // 2] == 1 else 0  # K 棒時間是結束時間 → 往前移 1 分
            log(f"K 棒時間對齊：{'結束時間，往前移 1 分' if shift else '開始時間'}")
        sec_days = {}
        for c in secs:
            try:
                sec_days[getattr(c, "name", c.code)] = bars_by_day(api.kbars(contract=c, start=cur.isoformat(), end=e.isoformat()))
            except Exception as ex:  # noqa: BLE001
                log(f"{getattr(c, 'name', '')} 失敗：{ex}")
        doc = load(ym)
        n = 0
        for d, mb in main_days.items():
            if len(mb) < 200:
                continue
            mb = {m - shift: v for m, v in mb.items()}
            t, last = [], None
            for m in range(271):
                last = mb.get(m, last)
                t.append(last)
            s = {}
            for name, days in sec_days.items():
                sb = {m - shift: v for m, v in (days.get(d) or {}).items()}
                if len(sb) < 100:
                    continue
                s[name] = [sb.get(max((x for x in sb if x <= m), default=-1)) for m in CHECK]
            doc[d] = {"t": t, "s": s}
            n += 1
        (OUT / f"{ym}.json").write_text(json.dumps(dict(sorted(doc.items())), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        have |= set(doc)
        u = api.usage()
        log(f"{ym}：{n} 天、類股 {len(sec_days)} 個（剩 {u.remaining_bytes / 1e6:.0f} MB）")
        if u.remaining_bytes < 30e6:
            break
        cur = (cur - timedelta(days=1)).replace(day=1)
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
