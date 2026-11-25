#!/usr/bin/env python3
"""
00713（特選高息低波）用的營運現金流量：公開資訊觀測站 t164sb05（個別公司現金流量表），逐家查
  對象：上市普通股（非 KY、非創新板、非全額交割）發行市值前 300 大＋00713 現有成分股
  季別：最近已結束的兩季（年初至今累計，單季＝本季累計 − 上季累計；第 1 季就是累計）
輸出 data/rebalance/raw/ocf/<YYYY>Q<n>.json {代號: 營業活動之淨現金流入（流出）累計（千元）}；已有的不重抓
觀測站擋雲端主機以外的少，在 GitHub Actions 上跑（rebalance-pred.yml）；遇到「查詢過於頻繁」就停，下次接著抓
用法：python scripts/fetch_ocf.py [--minutes 20]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_rebalance as fr  # noqa: E402

DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "rebalance" / "raw" / "ocf"
TPE = timezone(timedelta(hours=8))
LABEL = re.compile(r"營業活動之淨現金流(入|出)")


def quarters(n=2):
    d = datetime.now(TPE).date()
    y, q = d.year, (d.month - 1) // 3
    if q == 0:
        y, q = y - 1, 4
    out = []
    for _ in range(n):
        out.append((y, q))
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out


def parse(page: str):
    for t in fr.tables(page):
        for th, td in t:
            cells = th + td
            if cells and LABEL.search(cells[0]):
                for v in cells[1:]:
                    s = v.replace(",", "").strip()
                    neg = s.startswith("(") and s.endswith(")")
                    s = s.strip("()")
                    try:
                        x = float(s)
                        return -x if neg else x
                    except ValueError:
                        continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    from scripts.rebalance.public import Public
    pub = Public(DATA)
    basic = pub.basic()
    day = pub.px_days()[-1]
    p = pub.px(day)
    pool = {k: (v[0] or 0) * (basic[k].get("sh") or 0) for k, v in p.items()
            if k in basic and basic[k].get("mk") == "TSE" and fr.is_stock(k) and not basic[k].get("alt")
            and "-KY" not in basic[k].get("n", "") and not basic[k].get("n", "").endswith("-創")}
    codes = set(sorted(pool, key=lambda k: -pool[k])[:300]) | set(pub.etf("00713").get("weights", {}))
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for y, q in quarters(2):
        path = OUT / f"{y}Q{q}.json"
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        todo = sorted(c for c in codes if c not in doc)
        print(f"{y}Q{q}：已有 {len(doc)}，要查 {len(todo)}", flush=True)
        for c in todo:
            if time.time() > deadline:
                break
            page = fr.mops("ajax_t164sb05", {"TYPEK": "all", "co_id": c, "year": str(y - 1911), "season": f"{q:02d}",
                                             "queryName": "co_id", "inpuType": "co_id", "isnew": "false", "keyword4": "",
                                             "code1": "", "TYPEK2": "", "checkbtn": ""})
            if page is None:
                print("觀測站拒絕或連不上，停止", flush=True)
                path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
                return 0
            v = parse(page)
            doc[c] = v   # None＝查不到（還沒公布或格式不同），也記下避免重查；下一輪會重查 None 的
            n += 1
            if n % 25 == 0:
                path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
                print(n, c, v, flush=True)
            time.sleep(2.5)
        # 值是 None 的下次再查
        doc_out = {k: v for k, v in doc.items() if v is not None}
        path.write_text(json.dumps(doc_out, separators=(",", ":")), encoding="utf-8")
        print(f"{y}Q{q}：{len(doc_out)} 家", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
