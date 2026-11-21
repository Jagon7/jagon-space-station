"""
抄底雷達 → public/data/bottom.json
來源：data/research/bottom_multi.json（多市場訊號回測、現況、台股歷次大跌走勢）、data/research/dip_instruments.json（抄底工具比較）
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from build_strategy import _load


def _inst(ts, n):
    def s(xs):
        xs = [x for x in xs if x is not None]
        if not xs:
            return None
        return {"avg": round(st.mean(xs), 1), "med": round(st.median(xs), 1), "win": round(sum(x > 0 for x in xs) / len(xs) * 100), "worst": round(min(xs), 1)}
    return {
        "fut": s([t[f"fut{n}"] for t in ts]), "futM": s([t[f"fut{n}"] / 0.075 for t in ts]),
        "futCall": sum(1 for t in ts if -t[f"futLow{n}"] / 100 / 0.075 > 0.25),
        "futStop": s([(-4 if t[f"futLow{n}"] <= -4 else t[f"fut{n}"]) for t in ts]),
        "atm": s([t.get(f"atm{n}") for t in ts]), "otm": s([t.get(f"otm{n}") for t in ts]),
        "sf": s([t[f"sf{n}"] for t in ts]), "sfM": s([t[f"sf{n}"] / 0.135 for t in ts if t[f"sf{n}"] is not None]),
        "n": len(ts),
    }


def build(data_dir: Path, public_dir: Path):
    m = _load(data_dir / "research" / "bottom_multi.json", {}) or {}
    if not m:
        return
    di = (_load(data_dir / "research" / "dip_instruments.json", {}) or {}).get("signals") or {}
    inst = {name: {str(n): _inst(ts, n) for n in (5, 10, 20)} for name, ts in di.items()}
    doc = {**m, "instruments": inst, "instDates": {k: [t["date"] for t in v] for k, v in di.items()},
           "stocks": _load(data_dir / "research" / "rebound_stocks.json", {}) or None}
    (public_dir / "bottom.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"抄底雷達：{len(m.get('markets', {}))} 個市場、{len(m.get('episodes', []))} 次台股大跌")
