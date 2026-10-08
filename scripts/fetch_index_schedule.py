#!/usr/bin/env python3
"""
ETF 追蹤指數的定期審核日程：哪個指數哪天公告成分股調整、哪天生效，以及追蹤它的 ETF。

來源（皆為公開資料）：
  1. 臺灣指數公司「指數定期審核日程表」每月 PDF（taiwanindex.com.tw，類別：指數定審期程表）
  2. MSCI 未來八次指數審核日期 ir_dates.csv（MSCI 台灣系列指數）
  3. 證交所 ETF 基本資料 openapi t187ap47_L 的「標的指數/追蹤指數名稱」（上市 ETF；上櫃 ETF 對不到）

輸出 JSS_DATA_DIR/etf/index_schedule.json：
    {"updatedAt", "rows": [{"index", "provider", "announce", "effective", "etfs": [code]}]}
需要 pdfplumber。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "etf" / "index_schedule.json"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
TIP_LIST = "https://taiwanindex.com.tw/downloads/technical_notice"
KEEP_PAST_DAYS = 60


def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60, **kw)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"抓取失敗 {url}")


def norm(name: str) -> str:
    """指數名稱比對用：ETF 基本資料常省略「臺灣指數公司特選」「上市上櫃」「報酬」等字。"""
    s = re.sub(r"\s+", "", name or "").upper()
    for a, b in (("臺", "台"), ("報酬", ""), ("股價", ""), ("(", ""), (")", ""), ("（", ""), ("）", "")):
        s = s.replace(a, b)
    for prefix in ("台灣指數公司", "特選", "台灣上市上櫃", "台灣全市場", "上市上櫃", "台灣"):
        if s.startswith(prefix) and len(s) > len(prefix) + 3:
            s = s[len(prefix):]
    return s


# ── 臺灣指數公司 ─────────────────────────────────────────────
def tip_rows() -> list[dict]:
    import pdfplumber

    page = get(TIP_LIST, params={"category_id": 3, "page": 1}).text
    files = []
    for block in re.findall(r'<table class="d-lg-none[^>]*>(.*?)</table>', page, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)]
        link = re.search(r'href="([^"]*TechnicalNotices/\d+/tw)"', block)
        if link and cells and "日程表" in "".join(cells):
            files.append((cells[0], link.group(1)))
    rows = []
    for file_date, url in files[:4]:  # 最新四份涵蓋前兩個月到下個月
        pdf = pdfplumber.open(io.BytesIO(get(url).content))
        for pg in pdf.pages:
            for table in pg.extract_tables():
                for r in table:
                    cells = [c for c in r if c]
                    dates = [c for c in cells if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", c.strip())]
                    if len(dates) >= 2 and "指數" in cells[0]:
                        rows.append({"index": re.sub(r"\s+", " ", cells[0].replace("\n", "")).strip(), "provider": "臺灣指數公司",
                                     "announce": dates[0].replace("/", "-"), "effective": dates[-1].replace("/", "-")})
        time.sleep(1)
    for r in rows:
        r["announce"], r["effective"] = (date.fromisoformat("-".join(f"{int(x):02d}" for x in d.split("-"))).isoformat()
                                         for d in (r["announce"], r["effective"]))
    return rows


# ── MSCI ────────────────────────────────────────────────────
def msci_rows() -> list[dict]:
    text = get("https://app2.msci.com/eqb/pressreleases/archive/ir_dates.csv").text
    out = []
    for m in re.finditer(r"\|(\d{2})-(\d{2})-(\d{4})\|(\d{2})-(\d{2})-(\d{4})", text):
        out.append({"index": "MSCI 季度指數審核", "provider": "MSCI",
                    "announce": f"{m.group(3)}-{m.group(1)}-{m.group(2)}", "effective": f"{m.group(6)}-{m.group(4)}-{m.group(5)}"})
    return out


def etf_indexes() -> dict[str, str]:
    r = get("https://openapi.twse.com.tw/v1/opendata/t187ap47_L")
    out = {}
    for x in r.json():
        idx = str(x.get("標的指數/追蹤指數名稱", "")).strip()
        if idx and idx != "不適用":
            out[str(x.get("基金代號", "")).strip()] = idx
    return out


def main():
    prev = {}
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    rows = []
    try:
        rows += tip_rows()
    except Exception as e:  # noqa: BLE001
        print(f"臺灣指數公司日程表失敗：{e}")
        rows += [r for r in prev.get("rows", []) if r["provider"] == "臺灣指數公司"]
    try:
        rows += msci_rows()
    except Exception as e:  # noqa: BLE001
        print(f"MSCI 審核日期失敗：{e}")
        rows += [r for r in prev.get("rows", []) if r["provider"] == "MSCI"]
    try:
        etfs = etf_indexes()
    except Exception as e:  # noqa: BLE001
        print(f"ETF 標的指數失敗：{e}")
        etfs = prev.get("etfIndex", {})

    by_index: dict[str, list[str]] = {}
    for code, idx in etfs.items():
        by_index.setdefault(norm(idx), []).append(code)
    msci_etfs = sorted(c for c, idx in etfs.items() if "MSCI" in idx.upper() and ("台灣" in idx or "臺灣" in idx))
    cutoff = (datetime.now(TPE).date() - timedelta(days=KEEP_PAST_DAYS)).isoformat()
    uniq = {}
    for r in rows:
        if r["effective"] < cutoff:
            continue
        r["etfs"] = msci_etfs if r["provider"] == "MSCI" else sorted(by_index.get(norm(r["index"]), []))
        uniq[(r["index"], r["announce"])] = r
    out_rows = sorted(uniq.values(), key=lambda r: (r["announce"], -len(r["etfs"]), r["index"]))
    if not out_rows:
        print("指數審核日程：沒有資料，保留上次結果")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "rows": out_rows,
                               "etfIndex": etfs}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"指數審核日程：{len(out_rows)} 筆，其中 {sum(1 for r in out_rows if r['etfs'])} 筆有 ETF 追蹤")
    return 0


if __name__ == "__main__":
    sys.exit(main())
