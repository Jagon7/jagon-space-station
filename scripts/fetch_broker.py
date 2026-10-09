#!/usr/bin/env python3
"""
重點分點追蹤：每天抓指定券商分點買賣了哪些股票（金額與張數）。

資料來源：富邦證券網站「分點明細查詢」（MoneyDJ 系統，公開頁面）
  /z/zg/zgb/zgb0.djhtm?a=<券商>&b=<分點>&c=B|E&e=<日期>&f=<日期>
  c=B 金額（仟元）、c=E 張數；買超、賣超各列最多 50 檔，不是完整成交明細。

要追蹤的分點改 BRANCHES（名稱用富邦網站上的寫法，總公司就寫券商名稱，如「康和」）。
每次執行會補齊最近 BACKFILL 個平日中還沒抓過的日子，所以新增分點會自動回補。

輸出 JSS_DATA_DIR/broker/<YYYY-MM-DD>.json（保留最近 KEEP_DAYS 個交易日）：
    {"date", "branches": {顯示名稱: [[代號, 名稱, 買金額, 賣金額, 買張, 賣張], ...]}}
金額單位：仟元；某檔只出現在其中一種排行時，另一種為 null。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

# (顯示名稱, 富邦網站上的分點名稱)
BRANCHES = [
    ("富邦新店", "富邦-新店"),
    ("永豐內湖", "永豐金-內湖"),
    ("康和總公司", "康和"),
    ("元大松江", "元大-松江"),
    ("凱基信義", "凱基-信義"),
    ("凱基松山", "凱基-松山"),
    ("凱基三多", "凱基-三多"),
    ("兆豐中壢", "兆豐-中壢"),
    ("兆豐大安", "兆豐-大安"),
    ("台新五權西", "台新-五權西"),
]

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "broker"
SITE = "https://fubon-ebrokerdj.fbs.com.tw"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
BACKFILL = 20
KEEP_DAYS = 120
DELAY = 0.5

S = requests.Session()
S.headers.update({"User-Agent": UA})


def get(path, params=None) -> str:
    for i in range(3):
        try:
            r = S.get(SITE + path, params=params, timeout=30)
            if r.status_code == 200:
                return r.content.decode("cp950", errors="replace")
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"抓取失敗 {path} {params}")


def enc(x: str) -> str:
    """網站代號含英文字母時要編成 UTF-16 hex（9A00 → 0039004100300030）；清單裡的分點代號已是編碼後的形式。"""
    if x.isdigit() or re.fullmatch(r"(00[0-9a-fA-F]{2})+", x):
        return x
    return "".join(f"{ord(ch):04x}" for ch in x)


def branch_ids() -> dict[str, tuple[str, str]]:
    """分點名稱 → (券商代號, 分點代號)，取自網站的分點選單。"""
    js = get("/z/js/zbrokerjs.djjs")
    m = re.search(r"g_BrokerList\s*=\s*'([^']*)'", js)
    out = {}
    for group in (m.group(1).split(";") if m else []):
        items = group.split("!")
        if len(items) < 2 or "," not in items[0]:
            continue
        hq = items[0].split(",", 1)[0]
        for it in items[1:]:
            if "," in it:
                bid, name = it.split(",", 1)
                out.setdefault(name.strip(), (hq, bid))
    return out


def num(s: str):
    s = re.sub(r"<[^>]+>", "", s).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse(page: str):
    """→ (資料日期, {代號: [名稱, 買, 賣]})；買超、賣超兩張表合併。"""
    m = re.search(r"資料日期：\s*(\d{8})", page)
    day = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else None
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(tds) != 4:
            continue
        sm = re.search(r"GenLink2stk\('A[A-Z]?([^']+)','([^']*)'\)", tds[0]) or \
            re.search(r"Link2Stk\('([^']+)'\);\">(.*?)</a>", tds[0], re.S)
        if not sm:
            continue
        code = sm.group(1).strip()
        name = html.unescape(re.sub(r"<[^>]+>", "", sm.group(2))).strip()
        name = name[len(code):].strip() if name.startswith(code) else name
        buy, sell = num(tds[1]), num(tds[2])
        if buy is not None and sell is not None:
            out[code] = [name, buy, sell]
    return day, out


def fetch_day(hq: str, bid: str, day: str):
    y, m, d = (int(x) for x in day.split("-"))
    ds = f"{y}-{m}-{d}"
    res = {}
    for kind in ("B", "E"):  # B 金額、E 張數
        page_day, rows = parse(get("/z/zg/zgb/zgb0.djhtm", {"a": enc(hq), "b": enc(bid), "c": kind, "e": ds, "f": ds}))
        if page_day != day:  # 假日或資料還沒出來：網站回最近一個交易日
            return None
        res[kind] = rows
        time.sleep(DELAY)
    rows = []
    for code in sorted(set(res["B"]) | set(res["E"])):
        a, e = res["B"].get(code), res["E"].get(code)
        name = (a or e)[0]
        rows.append([code, name, a[1] if a else None, a[2] if a else None, e[1] if e else None, e[2] if e else None])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=BACKFILL)
    a = ap.parse_args()

    ids = branch_ids()
    targets = []
    for label, name in BRANCHES:
        if name in ids:
            targets.append((label, *ids[name]))
        else:
            print(f"✗ 找不到分點「{name}」")
    today = datetime.now(TPE).date()
    days, d = [], today
    while len(days) < a.days:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)

    OUT.mkdir(parents=True, exist_ok=True)
    for day in sorted(days):
        path = OUT / f"{day}.json"
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"date": day, "branches": {}}
        missing = [t for t in targets if t[0] not in doc["branches"]]
        if not missing:
            continue
        holiday = False
        for label, hq, bid in missing:
            try:
                rows = fetch_day(hq, bid, day)
            except RuntimeError as e:
                print(f"✗ {day} {label}：{e}")
                continue
            if rows is None:  # 這天沒有資料（假日或還沒公布），整天略過
                holiday = True
                break
            doc["branches"][label] = rows
        if holiday:
            print(f"  {day}：沒有資料，略過")
            continue
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {day}：{len(doc['branches'])} 個分點")
    for old in sorted(OUT.glob("*.json"))[:-KEEP_DAYS]:
        old.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
