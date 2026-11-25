#!/usr/bin/env python3
"""
研究用：上市＋上櫃月營收歷史（公開資訊觀測站 t21sc03 彙總頁，2011-01 起）→ data/research/revenue_hist.json
  {"YYYY-MM": {代號: [當月營收, 去年同月營收]}}（千元）；已有且家數夠的月份跳過
  2013 年起（IFRS）網址 t21sc03_{民國年}_{月}_{0 國內／1 國外}.html；更早的只有 t21sc03_{民國年}_{月}.html
  解析不出來的月份，存一份原始頁 data/research/revenue_sample_<月份>.html 方便看格式
觀測站擋雲端主機以外的少，在 GitHub Actions 上跑（research.yml，job=revenue）
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_fundamentals as ff  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "revenue_hist.json"


def parse(page: str) -> dict:
    """每列：代號 名稱 當月 上月 去年當月 …；只取當月、去年當月"""
    doc = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        c = ff.cells(tr)
        if len(c) >= 5 and re.fullmatch(r"\d{4}[A-Z]?", c[0]):
            cur, ly = ff.num(c[2]), ff.num(c[4])
            if cur is not None:
                doc[c[0]] = [cur, ly]
    return doc


def get(url: str) -> str | None:
    """找不到（404 等）就回 None 不重試；被擋或網路錯誤才重試"""
    for i in range(3):
        try:
            r = ff.S.get(url, timeout=60)
        except ff.requests.RequestException:
            time.sleep(10 * (i + 1))
            continue
        if r.status_code != 200:
            return None
        for enc in ("utf-8", "big5hkscs", "cp950"):
            try:
                text = r.content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = r.content.decode("utf-8", "replace")
        if "FOR SECURITY REASONS" in text or "查詢過於頻繁" in text:
            time.sleep(30 * (i + 1))
            continue
        return text
    return None


def month(y: int, m: int) -> tuple[dict, str | None]:
    doc, sample = {}, None
    for mk in ("sii", "otc"):
        urls = [f"{ff.OV}nas/t21/{mk}/t21sc03_{y - 1911}_{m}_{k}.html" for k in (0, 1)]
        if y < 2013:
            urls = [f"{ff.OV}nas/t21/{mk}/t21sc03_{y - 1911}_{m}.html"] + urls
        for u in urls:
            page = get(u)
            if page is None:
                continue
            part = parse(page)
            if not part and sample is None and len(page) > 2000:
                sample = page
            doc.update(part)
            time.sleep(1.5)
    return doc, sample


def main():
    try:
        have = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        have = {}
    end = os.environ.get("REV_END", "2023-08")  # 之後的月份已在 data/fund/revenue
    y, m = 2011, 1
    t0 = time.time()
    while f"{y}-{m:02d}" <= end:
        key = f"{y}-{m:02d}"
        if len(have.get(key, {})) < 1200:
            doc, sample = month(y, m)
            print(key, len(doc), flush=True)
            if len(doc) >= 500:
                have[key] = doc
                OUT.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
            elif sample:
                (DATA / "research" / f"revenue_sample_{key}.html").write_text(sample[:200000], encoding="utf-8")
        if time.time() - t0 > 4.5 * 3600:
            break
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    OUT.write_text(json.dumps(have, separators=(",", ":")), encoding="utf-8")
    print("共", len(have), "個月", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
