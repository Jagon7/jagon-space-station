"""
美國事件 × 台指期夜盤走勢 → public/data/us-events.json

事件（data/intel/us_events.json）對到台指期夜盤 1 分 K（data/futures/night/）：
  公布時間（台灣時間）→ 夜盤日期與分鐘序號 m（0＝15:00）；基準價＝公布前最後一根 1 分 K 的收盤
  路徑：公布前 60 分 ～ 公布後 180 分，每 5 分一點，相對基準價的漲跌（%）
  指標：公布前 60 分漲跌、公布後 5／15／30／60 分、到夜盤收盤（05:00）、公布後 60 分內最大漲幅／跌幅
  高於／低於預期：主指標（例如 CPI 用核心 CPI 月增）實際值 − 預估值
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime, timedelta
from pathlib import Path

from build_strategy import TPE, _load

PRE, POST, STEP = 60, 180, 5
OFFS = list(range(-PRE, POST + 1, STEP))
END_M = 839  # 04:59 那根


def night_min(hh: int, mm: int):
    t = hh * 60 + mm
    if t >= 15 * 60:
        return t - 15 * 60
    if t <= 5 * 60:
        return t + 9 * 60
    return None


def build(data_dir: Path, public_dir: Path):
    ev = _load(data_dir / "intel" / "us_events.json", {}) or {}
    events = ev.get("events") or []
    ndir = data_dir / "futures" / "night"
    if not events or not ndir.exists():
        return
    nights: dict[str, dict] = {}
    for f in sorted(ndir.glob("20*.json")):
        for d, v in (_load(f, {}) or {}).items():
            if len(v.get("bars") or []) >= 300:  # 太短的（颱風、半天）不算
                nights[d] = {b[0]: b[1:] for b in v["bars"]}
    now = datetime.now(TPE)
    out_rows, upcoming = [], []
    for e in events:
        t = datetime.fromisoformat(e["t"])
        if t > now:
            if t < now + timedelta(days=21):
                upcoming.append({"key": e["key"], "t": e["t"], "period": e.get("period"), "main": e.get("main"),
                                 "forecast": e.get("forecast"), "previous": e.get("previous")})
            continue
        m = night_min(t.hour, t.minute)
        if m is None:
            continue
        nd = (t.date() if m < 9 * 60 else t.date() - timedelta(days=1)).isoformat()
        bars = nights.get(nd)
        if not bars:
            continue

        def close_at(k: int, back: bool = True):
            """第 k 分鐘（含）以前最後一根的收盤；back=False 找 k 以後第一根"""
            rng = range(k, max(-1, k - 30), -1) if back else range(k, min(END_M + 1, k + 30))
            for i in rng:
                if i in bars:
                    return bars[i][3]
            return None

        ref = close_at(m - 1)
        if not ref:
            continue
        pct = lambda p: round((p / ref - 1) * 100, 3) if p else None  # noqa: E731
        path = [pct(close_at(m + o - 1)) if m + o - 1 <= END_M and m + o - 1 >= 0 else None for o in OFFS]
        win = [bars[i] for i in range(m, min(END_M, m + 60) + 1) if i in bars]
        last = max(bars)
        act, fc = e.get("actual"), e.get("forecast")
        sur = round(act - fc, 4) if isinstance(act, (int, float)) and isinstance(fc, (int, float)) else None
        out_rows.append({
            "key": e["key"], "t": e["t"], "night": nd, "period": e.get("period"), "main": e.get("main"),
            "actual": act, "forecast": fc, "previous": e.get("previous"), "surprise": sur,
            "ref": ref, "pre60": round((ref / p0 - 1) * 100, 3) if (p0 := close_at(m - 61)) else None,
            "r5": pct(close_at(m + 4)), "r15": pct(close_at(m + 14)), "r30": pct(close_at(m + 29)), "r60": pct(close_at(m + 59)),
            "toClose": pct(bars[last][3]), "hi60": pct(max(b[1] for b in win)) if win else None,
            "lo60": pct(min(b[2] for b in win)) if win else None,
            "items": e.get("items"), "path": path,
        })

    def agg(rows):
        def mean(k):
            xs = [r[k] for r in rows if r.get(k) is not None]
            return round(st.mean(xs), 3) if xs else None

        def absmean(k):
            xs = [abs(r[k]) for r in rows if r.get(k) is not None]
            return round(st.mean(xs), 3) if xs else None

        def up(k):
            xs = [r[k] for r in rows if r.get(k) is not None]
            return round(sum(1 for x in xs if x > 0) / len(xs) * 100, 1) if xs else None
        path = []
        for i in range(len(OFFS)):
            xs = [r["path"][i] for r in rows if r["path"][i] is not None]
            path.append(round(st.mean(xs), 3) if xs else None)
        return {"n": len(rows), "r5": mean("r5"), "r30": mean("r30"), "r60": mean("r60"), "toClose": mean("toClose"),
                "abs30": absmean("r30"), "abs60": absmean("r60"), "up30": up("r30"), "up60": up("r60"), "upClose": up("toClose"),
                "pre60": mean("pre60"), "path": path}

    kinds = ev.get("kinds") or {}
    stats = {}
    for k in kinds:
        rows = [r for r in out_rows if r["key"] == k]
        if not rows:
            continue
        stats[k] = {"all": agg(rows), "beat": agg([r for r in rows if (r["surprise"] or 0) > 0]),
                    "miss": agg([r for r in rows if (r["surprise"] or 0) < 0]),
                    "inline": agg([r for r in rows if r["surprise"] == 0]),
                    "from": min(r["night"] for r in rows)}
    doc = {"updatedAt": now.isoformat(timespec="minutes"), "offsets": OFFS, "kinds": kinds, "stats": stats,
           "events": sorted(out_rows, key=lambda r: r["t"], reverse=True), "upcoming": upcoming,
           "nights": len(nights), "nightFrom": min(nights) if nights else None, "nightTo": max(nights) if nights else None}
    (public_dir / "us-events.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"美國事件夜盤：{len(out_rows)} 筆事件對到夜盤（夜盤 {doc['nightFrom']} ～ {doc['nightTo']}，{len(nights)} 晚），未來 {len(upcoming)} 筆")
