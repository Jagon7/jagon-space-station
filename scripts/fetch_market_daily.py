#!/usr/bin/env python3
"""
每日全市場個股資料（給 氣氛評估／隔日追蹤／券差偵察 用）：開高低收、成交量值、融資融券、借券賣出。

資料來源（都可以查指定日期，所以能回補）：
  上市：證交所 MI_INDEX（每日收盤行情）、MI_MARGN（融資融券餘額）、TWT93U（信用額度總量管制餘額＝借券賣出）
  上櫃：櫃買中心 dailyQuotes、margin/balance、margin/sbl

每次執行補齊最近 DAYS 個平日中還沒抓過的交易日（休市日記在 skip 清單，不重抓）。
輸出 JSS_DATA_DIR/daily/<YYYY-MM-DD>.json：
  {"date",
   "q": {代號: [名稱, 市場(0 上市/1 上櫃), 開, 高, 低, 收, 漲跌, 成交張數, 成交金額(元)]},
   "m": {代號: [融資餘額, 融資增減, 融券餘額, 融券增減, 資券相抵]}           單位：張
   "s": {代號: [借券賣出前日餘額, 當日賣出, 當日還券, 當日餘額]},           單位：張
   "ix": [加權指數, 漲跌%], "ad": {"上漲": [家數, 漲停], "下跌": [...], "持平": [...], ...}}（上市股票）
用法：python scripts/fetch_market_daily.py [--days 130]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "daily"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
STOCK_RE = re.compile(r"\d{4}|00\d{2,4}[A-Z]?")  # 股票與 ETF
DAYS = 130
KEEP = 140

S = requests.Session()
S.headers.update({"User-Agent": UA})


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def num(v):
    try:
        return float(str(v).replace(",", "").replace("+", "").replace("X", "").strip())
    except (TypeError, ValueError):
        return None


def lots(v):
    x = num(v)
    return int(x) if x is not None else 0


def get_json(url, params):
    for i in range(4):
        try:
            r = S.get(url, params=params, timeout=60)
            if r.status_code == 200 and r.text.strip()[:1] == "{":
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(4 * (i + 1))
    raise RuntimeError(f"抓取失敗 {url} {params}")


def tables(doc) -> list[dict]:
    if doc.get("tables"):
        return doc["tables"]
    if doc.get("fields"):
        return [{"title": doc.get("title"), "fields": doc["fields"], "data": doc.get("data") or []}]
    return []


def pick(doc, *must) -> tuple[list[str], list[list]]:
    """找出欄位包含 must 的表格"""
    for t in tables(doc):
        f = [re.sub(r"\s+", "", str(x)) for x in (t.get("fields") or [])]
        if all(any(m in x for x in f) for m in must):
            return f, t.get("data") or []
    return [], []


def col(fields, *names, start=0):
    for i in range(start, len(fields)):
        if any(fields[i] == n or fields[i].startswith(n) for n in names):
            return i
    return None


# ---------- 上市 ----------

TWSE_EXTRA: dict = {}


def twse_quotes(d: date):
    doc = get_json("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
                   {"date": d.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"})
    if doc.get("stat") != "OK":
        return None  # 休市或還沒公布
    TWSE_EXTRA.clear()
    fi, irows = pick(doc, "指數", "收盤指數")
    for r in irows:
        if str(r[0]).strip() == "發行量加權股價指數":
            TWSE_EXTRA["ix"] = [num(r[1]), num(r[4]) if "-" not in str(r[2]) else -abs(num(r[4]) or 0)]
    fa, arows = pick(doc, "類型", "股票")
    ad = {}
    for r in arows:  # 上漲(漲停) "425(14)"
        m = re.match(r"([\d,]+)(?:\(([\d,]+)\))?", str(r[2]).strip())
        if m:
            ad[str(r[0]).strip()[:2]] = [lots(m.group(1)), lots(m.group(2) or 0)]
    if ad:
        TWSE_EXTRA["ad"] = ad
    f, rows = pick(doc, "證券代號", "收盤價")
    ic, iname, io_, ih, il, icl = (col(f, x) for x in ("證券代號", "證券名稱", "開盤價", "最高價", "最低價", "收盤價"))
    isign, ichg, ivol, ival = col(f, "漲跌(+/-)"), col(f, "漲跌價差"), col(f, "成交股數"), col(f, "成交金額")
    out = {}
    for r in rows:
        code = str(r[ic]).strip()
        close = num(r[icl])
        if not STOCK_RE.fullmatch(code) or not close:
            continue
        chg = num(r[ichg]) or 0.0
        if isign is not None and "-" in re.sub(r"<[^>]+>", "", str(r[isign])):
            chg = -abs(chg)
        out[code] = [str(r[iname]).strip(), 0, num(r[io_]), num(r[ih]), num(r[il]), close, round(chg, 2),
                     round((num(r[ivol]) or 0) / 1000), num(r[ival]) or 0]
    return out


def twse_margin(d: date):
    doc = get_json("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
                   {"date": d.strftime("%Y%m%d"), "selectType": "ALL", "response": "json"})
    f, rows = pick(doc, "代號", "今日餘額")
    if not rows:
        return {}
    ic = col(f, "代號")
    # 欄位：融資 買進 賣出 現金償還 前日餘額 今日餘額 限額 / 融券 買進 賣出 現券償還 前日餘額 今日餘額 限額 / 資券互抵
    prev = [i for i, x in enumerate(f) if x.startswith("前日餘額")]
    today = [i for i, x in enumerate(f) if x.startswith("今日餘額")]
    ioff = col(f, "資券互抵")
    out = {}
    for r in rows:
        code = str(r[ic]).strip()
        if not STOCK_RE.fullmatch(code) or len(prev) < 2 or len(today) < 2:
            continue
        mb, mp, sb, sp = lots(r[today[0]]), lots(r[prev[0]]), lots(r[today[1]]), lots(r[prev[1]])
        out[code] = [mb, mb - mp, sb, sb - sp, lots(r[ioff]) if ioff is not None else 0]
    return out


def twse_sbl(d: date):
    doc = get_json("https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U",
                   {"date": d.strftime("%Y%m%d"), "response": "json"})
    f, rows = pick(doc, "代號", "當日餘額")
    return parse_sbl(f, rows)


def parse_sbl(f, rows):
    """信用額度總量管制餘額表：前半段是融券、後半段是借券賣出（單位：股）"""
    if not rows:
        return {}
    ic = col(f, "股票代號", "代號")
    prev = [i for i, x in enumerate(f) if x.startswith("前日餘額")]
    if len(prev) < 2:
        return {}
    b = prev[1]  # 借券賣出：前日餘額、當日賣出、當日還券、當日調整、當日餘額
    out = {}
    for r in rows:
        code = str(r[ic]).strip()
        if not STOCK_RE.fullmatch(code):
            continue
        p, sell, ret, bal = (lots(r[b + k]) // 1000 for k in (0, 1, 2, 4))
        if p or sell or ret or bal:
            out[code] = [p, sell, ret, bal]
    return out


# ---------- 上櫃 ----------

def tpex_date(d: date) -> str:
    return d.strftime("%Y/%m/%d")


def tpex_quotes(d: date):
    doc = get_json("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes", {"date": tpex_date(d), "response": "json"})
    f, rows = pick(doc, "代號", "收盤")
    if not rows or str(doc.get("date", "")) != d.strftime("%Y%m%d"):
        return None
    ic, iname, icl, ichg, io_, ih, il = (col(f, x) for x in ("代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低"))
    ivol, ival = col(f, "成交股數"), col(f, "成交金額")
    out = {}
    for r in rows:
        code = str(r[ic]).strip()
        close = num(r[icl])
        if not STOCK_RE.fullmatch(code) or not close:
            continue
        out[code] = [str(r[iname]).strip(), 1, num(r[io_]), num(r[ih]), num(r[il]), close, num(r[ichg]) or 0.0,
                     round((num(r[ivol]) or 0) / 1000), num(r[ival]) or 0]
    return out


def tpex_margin(d: date):
    doc = get_json("https://www.tpex.org.tw/www/zh-tw/margin/balance", {"date": tpex_date(d), "response": "json"})
    f, rows = pick(doc, "代號", "資餘額")
    if not rows:
        return {}
    ic, imp, imb, isp, isb, ioff = (col(f, x) for x in ("代號", "前資餘額", "資餘額", "前券餘額", "券餘額", "資券相抵"))
    out = {}
    for r in rows:
        code = str(r[ic]).strip()
        if not STOCK_RE.fullmatch(code):
            continue
        mb, sb = lots(r[imb]), lots(r[isb])
        out[code] = [mb, mb - lots(r[imp]), sb, sb - lots(r[isp]), lots(r[ioff]) if ioff is not None else 0]
    return out


def tpex_sbl(d: date):
    doc = get_json("https://www.tpex.org.tw/www/zh-tw/margin/sbl", {"date": tpex_date(d), "response": "json"})
    f, rows = pick(doc, "代號", "當日餘額")
    return parse_sbl(f, rows)


def fetch_day(d: date):
    tw = twse_quotes(d)
    time.sleep(1.5)
    tp = tpex_quotes(d)
    if tw is None and tp is None:
        return None
    q = {**(tw or {}), **(tp or {})}
    m, s = {}, {}
    for fn, dst in ((twse_margin, m), (tpex_margin, m), (twse_sbl, s), (tpex_sbl, s)):
        time.sleep(1.5)
        try:
            dst.update(fn(d))
        except RuntimeError as e:
            log(f"  ✗ {d} {fn.__name__}：{e}")
    return {"date": d.isoformat(), "q": q, "m": m, "s": s, **(TWSE_EXTRA if tw else {}),
            "partial": [k for k, v in (("twse", tw), ("tpex", tp)) if v is None] or None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DAYS)
    ap.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    OUT.mkdir(parents=True, exist_ok=True)
    skip_path = OUT / "_skip.json"
    skip = set(json.loads(skip_path.read_text()) if skip_path.exists() else [])
    now = datetime.now(TPE)
    d = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    days = []
    while len(days) < a.days:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    n = 0
    for d in days:  # 新到舊
        path = OUT / f"{d.isoformat()}.json"
        if d.isoformat() in skip:
            continue
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if not old.get("partial") and old.get("m"):
                continue
        if time.time() > deadline:
            break
        try:
            doc = fetch_day(d)
        except RuntimeError as e:
            log(f"✗ {d}：{e}")
            continue
        if doc is None:
            if (now.date() - d).days > 3:  # 確定是休市日才記下來
                skip.add(d.isoformat())
            log(f"  {d}：沒有行情（休市或尚未公布）")
            continue
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        n += 1
        log(f"  {d}：{len(doc['q'])} 檔、融資券 {len(doc['m'])}、借券 {len(doc['s'])}{'（缺 ' + ','.join(doc['partial']) + '）' if doc['partial'] else ''}")
    skip_path.write_text(json.dumps(sorted(skip)), encoding="utf-8")
    files = sorted(p for p in OUT.glob("20*.json"))
    for old in files[:-KEEP]:
        old.unlink()
    log(f"本次新增 {n} 天，共 {len(files[-KEEP:])} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
