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


def build_broker():
    """分點買賣超：每個分點一個檔（前端選分點才載入），index.json 列分點與日期。"""
    src, out = DATA_DIR / "broker", ROOT / "public" / "data" / "broker"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    days = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(src.glob("*.json"))]
    labels = []
    for d in days:
        for b in d["branches"]:
            if b not in labels:
                labels.append(b)
    dates = [d["date"] for d in days]
    for i, label in enumerate(labels):
        rows: dict[str, list] = {}
        names: dict[str, str] = {}
        for di, d in enumerate(days):
            for code, name, ba, sa, bs, ss in d["branches"].get(label, []):
                names[code] = name
                rows.setdefault(code, []).append([di, ba, sa, bs, ss])
        (out / f"{i}.json").write_text(json.dumps({"label": label, "dates": dates, "names": names, "rows": rows},
                                                  ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    covered = {label: [d["date"] for d in days if label in d["branches"]] for label in labels}
    (out / "index.json").write_text(json.dumps({"dates": dates, "branches": labels,
                                                "firstDate": {k: (v[0] if v else None) for k, v in covered.items()}},
                                               ensure_ascii=False), encoding="utf-8")
    print(f"分點：{len(labels)} 個分點、{len(dates)} 天 → public/data/broker")


if __name__ == "__main__":
    build_etf_views.build()
    build_ranking()
    build_broker()
