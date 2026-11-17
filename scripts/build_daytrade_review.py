"""
當沖復盤 → public/data/daytrade-review.json：每天推薦標的的實際結果、近期實績、目前參數與調整紀錄（scripts/daytrade_lab.py）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from build_strategy import TPE, _load


def build(data_dir: Path, public_dir: Path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import daytrade_lab as lab
    j = _load(data_dir / "strategy" / "daytrade_journal.json", {}) or {}
    p = _load(data_dir / "strategy" / "daytrade_params.json", {}) or {}
    if not j:
        return
    live = {k: {w: lab.live_stats(j, k, w) for w in (5, 20, 60)} for k in lab.NAMES}
    days = [{"date": d, "sim": bool(v.get("sim")), "picks": v.get("picks"), "result": v.get("result"), "params": v.get("params")}
            for d, v in sorted(j.items(), reverse=True)[:60]]
    doc = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "names": lab.NAMES, "cost": lab.COST,
           "params": p.get("current") or {}, "tunedAt": p.get("tunedAt"), "eval": p.get("eval") or {},
           "history": list(reversed(p.get("history") or [])), "live": live, "days": days}
    (public_dir / "daytrade-review.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"當沖復盤：{len(j)} 天紀錄")
