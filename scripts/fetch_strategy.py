#!/usr/bin/env python3
"""
波段策略用的補充資料 → data/strategy/
  disposition.json  上市櫃處置股歷史（代號、處置起日、迄日），給「出量做多」排除近 10 日有處置的股票
    上市：證交所 announcement/punish（查詢期間）；上櫃：櫃買中心 bulletin/disposal（查詢期間）
    每次查最近 DAYS 天，和舊資料合併
  block.json        個股鉅額交易成交金額 {日期: {代號: 金額}}，給「出量做多」把成交金額換成「不含鉅額」
    證交所每日行情的成交金額含鉅額交易，原策略用不含鉅額的金額；上市逐日查 block/BFIAUU（每次最多補 BLOCK_MAX 天），
    上櫃用櫃買 openapi 的鉅額交易歷史（一次給整年，以名稱對應代號）
  shares.json       上市櫃已發行普通股數 {代號: 股數}，給週轉率（成交股數 ÷ 發行股數）用
    上市：openapi t187ap03_L；上櫃：openapi mopsfin_t187ap03_O
  daytrade.json     個股現股當沖成交股數 {日期: {"tw": {代號: 股數}, "tp": {...}, "x": [暫停先賣後買的代號]}}
    上市：exchangeReport/TWTB4U；上櫃：www/zh-tw/intraday/stat（每次最多補 BLOCK_MAX 天）
  stockfutures.json 期交所股票期貨標的清單 {"codes": [...]}（除權息黑K用：有個股期才方便放空）
  exdiv_hq.json     未來 14 天要除息股票的「總公司分點」近 30 天淨買賣（除權息黑K用）
    來源：富邦證券（MoneyDJ）個股主力進出 zco，區間內買超、賣超前 15 名分點（名稱沒有「-」的是券商總公司；外資券商另外算）
    {代號: {"from","to","hq": 總公司淨買超占成交%, "fx": 外資券商淨買超占成交%, "hqLots": 張, "top": [[分點, 淨買張], ...]}}
用法：python scripts/fetch_strategy.py [--days 90]
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
OUT = DATA_DIR / "strategy"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA})
PERIOD = re.compile(r"(\d{2,3})/(\d{1,2})/(\d{1,2})\s*[~～－-]\s*(\d{2,3})/(\d{1,2})/(\d{1,2})")


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def get_json(url, params):
    for i in range(3):
        try:
            r = S.get(url, params=params, timeout=60)
            if r.status_code == 200 and r.text.lstrip()[:1] == "{":
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(4 * (i + 1))
    return None


def period_of(row) -> tuple[str, str] | None:
    for cell in row:
        m = PERIOD.search(re.sub(r"<[^>]+>", " ", str(cell)))
        if m:
            y1, m1, d1, y2, m2, d2 = (int(x) for x in m.groups())
            return date(y1 + 1911, m1, d1).isoformat(), date(y2 + 1911, m2, d2).isoformat()
    return None


def code_of(row) -> str | None:
    for cell in row[1:4]:
        c = str(cell).strip()
        if re.fullmatch(r"[1-9]\d{3}", c):
            return c
    return None


def twse(start: date, end: date) -> list:
    out = []
    for url in ("https://www.twse.com.tw/rwd/zh/announcement/punish", "https://www.twse.com.tw/announcement/punish"):
        doc = get_json(url, {"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d"), "response": "json"})
        rows = (doc or {}).get("data") or ((doc or {}).get("tables") or [{}])[0].get("data") or []
        for r in rows:
            c, p = code_of(r), period_of(r)
            if c and p:
                out.append([c, *p])
        if out:
            break
    return out


def tpex(start: date, end: date) -> list:
    doc = get_json("https://www.tpex.org.tw/www/zh-tw/bulletin/disposal",
                   {"startDate": start.strftime("%Y/%m/%d"), "endDate": end.strftime("%Y/%m/%d"), "response": "json"})
    out = []
    for r in ((doc or {}).get("tables") or [{}])[0].get("data") or []:
        c, p = code_of(r), period_of(r)
        if c and p:
            out.append([c, *p])
    return out


BLOCK_MAX = int(os.environ.get("JSS_BACKFILL_MAX", "40"))


def blocks(known: dict) -> dict:
    """近 130 個交易日的鉅額交易金額 {日期: {"tw": {代號: 金額}, "tp": {...}}}；上市已有的日期不重抓"""
    days = sorted(p.stem for p in (DATA_DIR / "daily").glob("20*.json"))[-130:]
    out = {d: dict(known.get(d) or {}) for d in days}
    for d in [d for d in days if "tw" not in out[d]][-BLOCK_MAX:]:
        doc = get_json("https://www.twse.com.tw/rwd/zh/block/BFIAUU",
                       {"date": d.replace("-", ""), "selectType": "S", "response": "json"})
        if not doc or (doc.get("stat") != "OK" and doc.get("data") is None):
            continue
        tw: dict[str, float] = {}
        for r in doc.get("data") or []:
            try:
                tw[r[0].strip()] = tw.get(r[0].strip(), 0) + float(str(r[5]).replace(",", ""))
            except (IndexError, ValueError):
                pass
        out[d]["tw"] = tw
        time.sleep(2)
    # 上櫃：openapi 一次給整年歷史，只有名稱，用最近行情的上櫃名稱對應代號
    names = {}
    for p in sorted((DATA_DIR / "daily").glob("20*.json"))[-20:]:
        for c, v in (json.loads(p.read_text(encoding="utf-8")).get("q") or {}).items():
            if v and v[1]:
                names[str(v[0]).strip()] = c
    try:
        rows = S.get("https://www.tpex.org.tw/openapi/v1/tpex_daily_trade_block_day", timeout=60).json()
    except (requests.RequestException, ValueError):
        rows = []
    tp: dict[str, dict] = {}
    for r in rows if isinstance(rows, list) else []:
        t, c = str(r.get("TradingDate", "")), names.get(str(r.get("Name", "")).strip())
        if len(t) != 7 or not c:
            continue
        d = f"{int(t[:3]) + 1911}-{t[3:5]}-{t[5:]}"
        try:
            tp.setdefault(d, {})[c] = tp.get(d, {}).get(c, 0) + float(r.get("TradingValue") or 0)
        except ValueError:
            pass
    if tp:
        for d in out:
            out[d]["tp"] = tp.get(d, {})
    return out


def _int(x) -> int:
    try:
        return int(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def daytrade(known: dict) -> dict:
    days = sorted(p.stem for p in (DATA_DIR / "daily").glob("20*.json"))[-130:]
    out = {d: dict(known.get(d) or {}) for d in days}
    for key, url, params in (("tw", "https://www.twse.com.tw/exchangeReport/TWTB4U", lambda d: {"date": d.replace("-", ""), "selectType": "All", "response": "json"}),
                             ("tp", "https://www.tpex.org.tw/www/zh-tw/intraday/stat", lambda d: {"type": "Daily", "date": d.replace("-", "/"), "response": "json"})):
        for d in [d for d in days if key not in out[d]][-BLOCK_MAX:]:
            doc = get_json(url, params(d))
            tables = (doc or {}).get("tables") or []
            if len(tables) < 2:
                continue
            m, x = {}, set(out[d].get("x", []))
            for r in tables[1].get("data") or []:
                c = str(r[0]).strip()
                if not re.fullmatch(r"[1-9]\d{3}", c):
                    continue
                m[c] = _int(r[3])
                if str(r[2]).strip():
                    x.add(c)
            if m:
                out[d][key] = m
                out[d]["x"] = sorted(x)
            time.sleep(2)
    return out


FOREIGN_BROKER = re.compile(r"^(美商|港商|新加坡商|英商|法商|德商|瑞士商|荷商|日商|澳商)|摩根|花旗|美林|匯豐|大和|瑞銀|高盛|麥格理|野村|德意志|法銀|巴克萊|星展|匯立|瑞信|里昂|富瑞")


def broker_kind(name: str) -> str:
    return "fx" if FOREIGN_BROKER.search(name) else ("hq" if "-" not in name else "br")


def zco(code: str, d0: date, d1: date) -> list | None:
    """個股區間主力進出：[[買超分點, 買, 賣, 淨, 占比%, 賣超分點, 買, 賣, 淨, 占比%], ...]"""
    url = "https://fubon-ebrokerdj.fbs.com.tw/z/zc/zco/zco.djhtm"
    for i in range(3):
        try:
            r = S.get(url, params={"a": code, "e": f"{d0.year}-{d0.month}-{d0.day}", "f": f"{d1.year}-{d1.month}-{d1.day}"}, timeout=30)
            text = r.content.decode("big5", "ignore")
            if "買超券商" in text:
                break
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    else:
        return None
    return parse_zco(text)


def parse_zco(text: str) -> list:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S | re.I)
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if len(c) == 10 and re.fullmatch(r"[\d,]+", c[1]):
            out.append(c)
    return out


def hq_flow(rows: list) -> dict:
    n = lambda x: float(str(x).replace(",", "").replace("%", "") or 0)  # noqa: E731
    pct = {"hq": 0.0, "fx": 0.0, "br": 0.0}
    lots, top = 0.0, []
    for c in rows:
        for name, net, share, sign in ((c[0], c[3], c[4], 1), (c[5], c[8], c[9], -1)):
            if not name:
                continue
            k = broker_kind(name)
            pct[k] += sign * n(share)
            if k == "hq":
                lots += sign * n(net)
                top.append([name, int(sign * n(net))])
    top.sort(key=lambda x: -abs(x[1]))
    return {"hq": round(pct["hq"], 2), "fx": round(pct["fx"], 2), "hqLots": int(lots), "top": top[:6]}


def exdiv_hq() -> dict:
    ev = json.loads((DATA_DIR / "fund" / "events.json").read_text(encoding="utf-8")).get("exdiv", []) if (DATA_DIR / "fund" / "events.json").exists() else []
    today = datetime.now(TPE).date()
    d0 = today - timedelta(days=30)
    out = {}
    for r in ev:
        d, code, cash = r[0], r[1], r[5]
        if not cash or not re.fullmatch(r"[1-9]\d{3}", code) or not (today.isoformat() < d <= (today + timedelta(days=14)).isoformat()) or code in out:
            continue
        rows = zco(code, d0, today)
        if rows is not None:
            out[code] = {"exDate": d, "from": d0.isoformat(), "to": today.isoformat(), **hq_flow(rows)}
        time.sleep(0.8)
    return out


def stock_futures() -> list:
    try:
        text = S.get("https://www.taifex.com.tw/cht/2/stockLists", timeout=60).text
    except requests.RequestException:
        return []
    codes = set()
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) > 4 and re.fullmatch(r"\d{4}[A-Z]?|00\d{2,4}[A-Z]?", cells[2]) and "是股票期貨標的" in cells[4]:
            codes.add(cells[2])
    return sorted(codes)


def shares() -> dict:
    out = {}
    for url, code_k, sh_k in (("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "公司代號", "已發行普通股數或TDR原股發行股數"),
                              ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "SecuritiesCompanyCode", "IssueShares")):
        try:
            rows = S.get(url, timeout=60).json()
        except (requests.RequestException, ValueError):
            rows = []
        for r in rows if isinstance(rows, list) else []:
            try:
                n = int(str(r.get(sh_k, "")).replace(",", ""))
            except ValueError:
                continue
            if n > 0:
                out[str(r.get(code_k, "")).strip()] = n
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "disposition.json"
    try:
        old = json.loads(path.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        old = []
    end = datetime.now(TPE).date()
    start = end - timedelta(days=a.days)
    tw, tp = twse(start, end), tpex(start, end)
    # 目前處置中的名單（fetch_data 抓的）也併進來，避免查詢期間 API 失敗時漏掉
    try:
        cur = json.loads((DATA_DIR / "disposition.json").read_text(encoding="utf-8")).get("data", [])
        for x in cur:
            p = period_of([x.get("period", "")])
            if p:
                old.append([x["code"], *p])
    except (OSError, ValueError):
        pass
    items = sorted({tuple(x) for x in old + tw + tp})
    keep = (end - timedelta(days=400)).isoformat()
    items = [list(x) for x in items if x[2] >= keep]
    path.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "items": items},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"處置歷史：上市 {len(tw)}、上櫃 {len(tp)}，合計 {len(items)} 筆")
    bpath = OUT / "block.json"
    try:
        known = json.loads(bpath.read_text(encoding="utf-8")).get("days", {})
    except (OSError, ValueError):
        known = {}
    bl = blocks(known)
    bpath.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "days": bl},
                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    hq = exdiv_hq()
    (OUT / "exdiv_hq.json").write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "stocks": hq},
                                                  ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"除權息總公司分點：{len(hq)} 檔")
    sf = stock_futures()
    if len(sf) > 100:
        (OUT / "stockfutures.json").write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "codes": sf},
                                                          ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"個股期標的：{len(sf)} 檔")
    sh = shares()
    if len(sh) > 1000:  # API 失敗時保留舊檔
        (OUT / "shares.json").write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "shares": sh},
                                                    ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"發行股數：{len(sh)} 檔")
    dpath = OUT / "daytrade.json"
    try:
        dknown = json.loads(dpath.read_text(encoding="utf-8")).get("days", {})
    except (OSError, ValueError):
        dknown = {}
    dt = daytrade(dknown)
    dpath.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "days": dt},
                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"當沖：上市 {sum(1 for v in dt.values() if 'tw' in v)}、上櫃 {sum(1 for v in dt.values() if 'tp' in v)}／{len(dt)} 天")
    log(f"鉅額交易：{sum(1 for v in bl.values() if 'tw' in v)}/{len(bl)} 天有上市資料")
    return 0


if __name__ == "__main__":
    sys.exit(main())
