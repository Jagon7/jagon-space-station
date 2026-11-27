#!/usr/bin/env python3
"""
盤中即時資金流（flow_live.py）盤後驗證：用永豐逐筆完整資料（orderflow_ticks.py → data/orderflow/features.json）重算對照

標準答案：每檔每天所有逐筆成交依內外盤分類（沒有標記的用當下委買委賣價判斷），13:30 收盤集合競價不算
  主動淨額（億）＝ 主動淨額比 × 已分類成交金額
比對（兩邊都有的股票，約前 100 大）：
  個股   主動淨額的相關係數、方向一致率、平均誤差（億）
  產業   依即時頁的產業加總後的方向一致率、相關係數
  全部   合計淨額（即時 vs 逐筆）
  成交額 即時已分類金額 ÷ 逐筆已分類金額（> 100% 表示即時多算了，例如收盤集合競價）
判定：個股相關 ≥ 0.9 且方向一致 ≥ 85% 為好；相關 < 0.7 或方向一致 < 75% 列為注意（validate_data.py 會讀）
  v2（2026-11-28 起：收盤集合競價不算主動買賣）之前的日子另外標示
輸出 data/flow/validation.json {"days": {日期: {...}}}；用法：python scripts/validate_flow.py
"""
from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "flow" / "validation.json"
TPE = timezone(timedelta(hours=8))
GOOD = (0.9, 85)
WARN = (0.7, 75)


def corr(a, b):
    try:
        return round(st.correlation(a, b), 3)
    except (st.StatisticsError, ValueError):
        return None


def judge(c, s):
    if c is None:
        return "warn"
    if c >= GOOD[0] and s >= GOOD[1]:
        return "good"
    if c < WARN[0] or s < WARN[1]:
        return "warn"
    return "ok"


def validate_day(flow: dict, ticks: dict) -> dict | None:
    live = {s["code"]: s for s in flow.get("stocks") or []}
    pairs = []
    for c, v in ticks.items():
        s = live.get(c)
        if not s or not v or not v[0] or v[1] is None:
            continue
        pairs.append((c, s["sector"], s["net"], v[1] * v[0] / 1e8, s["out"] + s["in"], v[0] / 1e8))
    if len(pairs) < 20:
        return None
    a, b = [p[2] for p in pairs], [p[3] for p in pairs]
    sign = sum((x > 0) == (y > 0) for x, y in zip(a, b)) / len(a) * 100
    sec = defaultdict(lambda: [0.0, 0.0])
    for _, sc, x, y, _, _ in pairs:
        sec[sc][0] += x
        sec[sc][1] += y
    big = {k: v for k, v in sec.items() if abs(v[1]) >= 5}   # 淨額 ≥ 5 億的產業才比方向（太小的正負沒意義）
    s_sign = sum((v[0] > 0) == (v[1] > 0) for v in big.values()) / len(big) * 100 if big else None
    worst = sorted(pairs, key=lambda p: -abs(p[2] - p[3]))[:5]
    c = corr(a, b)
    return {"v": flow.get("v", 1), "n": len(pairs), "corr": c, "sign": round(sign, 1), "mae": round(st.mean(abs(x - y) for x, y in zip(a, b)), 2),
            "liveNet": round(sum(a), 1), "tickNet": round(sum(b), 1),
            "amtRatio": round(sum(p[4] for p in pairs) / sum(p[5] for p in pairs) * 100, 1),
            "secCorr": corr([v[0] for v in sec.values()], [v[1] for v in sec.values()]), "secSign": round(s_sign, 1) if s_sign is not None else None,
            "secN": len(big), "worst": [[p[0], round(p[2], 2), round(p[3], 2)] for p in worst], "level": judge(c, sign)}


def main():
    ticks = json.loads((DATA / "orderflow" / "features.json").read_text(encoding="utf-8")).get("days", {})
    try:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"days": {}}
    n = 0
    for f in sorted(glob.glob(str(DATA / "flow" / "20*.json"))):
        d = Path(f).stem
        if d not in ticks:
            continue
        r = validate_day(json.loads(Path(f).read_text(encoding="utf-8")), ticks[d])
        if r:
            doc["days"][d] = r
            n += 1
    days = sorted(doc["days"])
    recent = [doc["days"][d] for d in days[-20:]]
    doc["summary"] = {"days": len(recent), "corr": round(st.mean(r["corr"] for r in recent if r["corr"] is not None), 3) if recent else None,
                      "sign": round(st.mean(r["sign"] for r in recent), 1) if recent else None,
                      "amtRatio": round(st.mean(r["amtRatio"] for r in recent), 1) if recent else None,
                      "latest": days[-1] if days else None}
    doc["updatedAt"] = datetime.now(TPE).isoformat(timespec="minutes")
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")
    for d in days[-10:]:
        r = doc["days"][d]
        print(f"{d} v{r['v']} {r['n']} 檔：相關 {r['corr']}、方向一致 {r['sign']}%、誤差 {r['mae']} 億、合計 即時 {r['liveNet']:+} vs 逐筆 {r['tickNet']:+} 億、"
              f"成交額比 {r['amtRatio']}%、產業方向一致 {r['secSign']}%（{r['secN']} 個）→ {r['level']}")
    print(f"驗證 {n} 天；近 {doc['summary']['days']} 天平均相關 {doc['summary']['corr']}、方向一致 {doc['summary']['sign']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
