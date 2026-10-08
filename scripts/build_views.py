#!/usr/bin/env python3
"""建置網站前產生前端用的靜態 JSON（public/data/），只用標準函式庫。"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_etf_views  # noqa: E402


def build_ranking():
    src, out = DATA_DIR / "ranking", ROOT / "public" / "data" / "ranking"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    dates = []
    for p in sorted(src.glob("*.json")):
        shutil.copy(p, out / p.name)
        dates.append(p.stem)
    (out / "index.json").write_text(json.dumps({"dates": dates}), encoding="utf-8")
    print(f"成交排行：{len(dates)} 天 → public/data/ranking")


if __name__ == "__main__":
    build_etf_views.build()
    build_ranking()
