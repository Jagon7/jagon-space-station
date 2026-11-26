#!/usr/bin/env python3
"""
本週／下週重點大事（給盤前快報「今明重點」與週日晚上的「下兩週大事」推播）

來源：
  美國總經：data/intel/us_events.json（fetch_us_events.py，未來 45 天：CPI、PPI、PCE、非農、FOMC、零售、GDP、ISM）
  美股休市／提早收盤：scripts/us_market.py
  美股財報：Nasdaq 財報行事曆（api.nasdaq.com，公開），只留觀察名單或市值 ≥ 1 兆美元（半導體、AI、台積電供應鏈）
  台股：休市（data/calendar.json）、台指期月結算（第 3 個週三，遇休市順延）、MSCI 季度調整（2／5／8／11 月最後一個交易日收盤）、
       FTSE 臺灣 50／高股息（0050、0056 等，3／6／9／12 月第 3 個週五收盤）、月營收公布截止（每月 10 日，遇休市順延）
  台股個股：市值前 30 大自己辦的法說會（券商論壇不列）、除權息；成交 ≥ 3 億的 ETF 除息（data/fund/events.json）
  手動：config/events_manual.json [{"d": "YYYY-MM-DD", "time": "HH:MM", "title": "...", "note": "...", "star": true}]（央行理監事會等）
輸出 data/intel/week_events.json {"updatedAt", "from", "to", "events": [{"d", "time", "cat", "title", "note", "star"}]}
用法：python scripts/build_week_events.py [--days 15]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "intel" / "week_events.json"
TPE = timezone(timedelta(hours=8))
sys.path.insert(0, str(ROOT / "scripts"))
import us_market  # noqa: E402

WATCH = {"NVDA": "輝達", "TSM": "台積電 ADR", "AAPL": "蘋果", "MSFT": "微軟", "GOOGL": "Google", "GOOG": "Google", "AMZN": "亞馬遜",
         "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通", "AMD": "超微", "MU": "美光", "ORCL": "甲骨文", "QCOM": "高通", "INTC": "英特爾",
         "ASML": "艾司摩爾", "ARM": "安謀", "MRVL": "邁威爾", "DELL": "戴爾", "HPE": "慧與", "SMCI": "美超微", "CRWV": "CoreWeave",
         "ADBE": "Adobe", "CRM": "Salesforce", "NFLX": "Netflix", "AMAT": "應用材料", "LRCX": "科林研發", "KLAC": "科磊", "TXN": "德儀",
         "ON": "安森美", "NXPI": "恩智浦", "COST": "好市多", "WMT": "沃爾瑪", "JPM": "摩根大通", "PLTR": "Palantir", "ANET": "Arista",
         "SNPS": "新思", "CDNS": "益華"}
STAR_US = {"NVDA", "TSM", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AVGO", "MU", "ORCL", "AMD"}
STAR_MACRO = {"fomc", "cpi", "nfp", "pce"}
WK = "一二三四五六日"


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def tw_trading(d: date, hol: set) -> bool:
    return d.weekday() < 5 and d.isoformat() not in hol


def next_trading(d: date, hol: set) -> date:
    while not tw_trading(d, hol):
        d += timedelta(days=1)
    return d


def last_trading_of_month(y: int, m: int, hol: set) -> date:
    d = (date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(days=1)
    while not tw_trading(d, hol):
        d -= timedelta(days=1)
    return d


def nth_weekday(y, m, wd, n):
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def nasdaq_earnings(d: date):
    for i in range(3):
        try:
            r = requests.get("https://api.nasdaq.com/api/calendar/earnings", params={"date": d.isoformat()}, timeout=30,
                             headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            return ((r.json().get("data") or {}).get("rows")) or []
        except (requests.RequestException, ValueError):
            time.sleep(3 * (i + 1))
    return None


def mcap_top(n: int):
    """市值前 n 大（最新 data/daily 收盤 × data/strategy/shares.json）與 ETF 成交金額"""
    f = sorted(glob.glob(str(DATA / "daily" / "20*.json")))[-1]
    q = load(f, {}).get("q") or {}
    sh = (load(DATA / "strategy" / "shares.json", {}) or {}).get("shares", {})
    mc = {c: v[5] * sh[c] for c, v in q.items() if c in sh and v[5] and len(c) == 4 and c[0] != "0"}
    etf_val = {c: v[8] or 0 for c, v in q.items() if c.startswith("00")}
    return set(sorted(mc, key=lambda c: -mc[c])[:n]), etf_val


def build(days: int = 15, today: date | None = None):
    today = today or datetime.now(TPE).date()
    end = today + timedelta(days=days - 1)
    hol = set((load(DATA / "calendar.json", {}) or {}).get("holidays", []))
    ev = []

    def add(d: date, time_, cat, title, note="", star=False):
        if today <= d <= end:
            ev.append({"d": d.isoformat(), "time": time_, "cat": cat, "title": title, "note": note, "star": bool(star)})

    # 美國總經
    us = load(DATA / "intel" / "us_events.json", {})
    kinds = us.get("kinds") or {}
    for e in us.get("events") or []:
        t = datetime.fromisoformat(e["t"])
        note = "・".join(x for x in (f"預估 {e['forecast']}" if e.get("forecast") is not None else "",
                                      f"前值 {e['previous']}" if e.get("previous") is not None else "") if x)
        if e["key"] == "fomc" and e.get("previous") is not None:
            note = f"目前利率 {e['previous']}%"
        add(t.date(), t.strftime("%H:%M"), "美國", kinds.get(e["key"], e["key"]) + (f"（{e['period']}）" if e.get("period") else ""), note, e["key"] in STAR_MACRO)
    # 美股休市／提早收盤（美國日期＝台灣當天晚上）
    d = today
    while d <= end:
        s = us_market.status(d)
        if s and s[0] == "closed":
            add(d, "", "美國", f"美股休市（{s[1]}）", "夜盤美股段突破訊號暫停", True)
        elif s and s[0] == "early":
            add(d + timedelta(days=1), f"{us_market.tw_close_hour(d):02d}:00", "美國", f"美股提早收盤（{s[1]}）", f"美東 {d.month}/{d.day} 13:00 收盤；夜盤建議那時平倉", False)
        d += timedelta(days=1)
    # 美股財報
    d = today
    while d <= end:
        if d.weekday() < 5:
            rows = nasdaq_earnings(d)
            for r in rows or []:
                sym = (r.get("symbol") or "").upper()
                try:
                    cap = float(str(r.get("marketCap") or "0").replace("$", "").replace(",", "") or 0)
                except ValueError:
                    cap = 0
                if sym in WATCH or cap >= 1e12:
                    tm = r.get("time") or ""
                    when = "盤後（台灣隔天清晨）" if "after" in tm else "盤前（台灣當天晚上）" if "pre" in tm else ""
                    nm = WATCH.get(sym, r.get("name") or sym)
                    add(d, "", "美股財報", f"{nm}（{sym}）財報", "・".join(x for x in (when, f"EPS 預估 {r['epsForecast']}" if r.get("epsForecast") else "") if x),
                        sym in STAR_US)
        d += timedelta(days=1)
    # 台股：休市
    d = today
    while d <= end:
        if d.weekday() < 5 and d.isoformat() in hol:
            add(d, "", "台股", "台股休市", "", True)
        d += timedelta(days=1)
    # 結算、指數調整、月營收
    for y, m in sorted({(x.year, x.month) for x in (today, end, today + timedelta(days=31))}):
        add(next_trading(nth_weekday(y, m, 2, 3), hol), "13:30", "台股", "台指期月結算", "台指期、台指選擇權月合約到期（13:30 結算）", True)
        if m in (2, 5, 8, 11):
            add(last_trading_of_month(y, m, hol), "13:30", "台股", "MSCI 季度調整生效（收盤）", "被動資金在收盤集合競價換股，尾盤量大", True)
        if m in (3, 6, 9, 12):
            fr = nth_weekday(y, m, 4, 3)
            fr_t = fr if tw_trading(fr, hol) else next_trading(fr, hol)
            add(fr_t, "13:30", "台股", "FTSE 臺灣 50／高股息指數調整（收盤）", "0050、006208、0051" + ("、0056" if m in (6, 12) else "") + " 換股", True)
        add(next_trading(date(y, m, 10), hol), "", "台股", "上市櫃月營收公布截止", "", False)
    # 台股個股：大型股法說、除權息；大型 ETF 除息
    top, etf_val = mcap_top(30)
    fe = load(DATA / "fund" / "events.json", {})
    for r in fe.get("conf") or []:
        # 只留公司自己辦的（公布財報、營運說明）；「受邀參加 XX 證券論壇」的太多，不列
        if r[1] in top and not any(k in (r[6] or "") for k in ("受邀", "邀請", "邀約", "論壇")):
            add(date.fromisoformat(r[0]), r[4] or "", "台股法說", f"{r[2]}（{r[1]}）法說會", (r[6] or "")[:40], r[1] in ("2330", "2317", "2454"))
    for r in fe.get("exdiv") or []:
        c = r[1]
        big_etf = c.startswith("00") and etf_val.get(c, 0) >= 3e8
        if c in top or big_etf:
            amt = f"現金 {r[5]:g} 元" if r[5] else ""
            stk = f"股票 {r[6]:g} 元" if r[6] and r[6] > 0.01 else ""
            add(date.fromisoformat(r[0]), "", "除權息", f"{r[2]}（{c}）除{r[4]}", "・".join(x for x in (amt, stk) if x), c in ("2330", "0050", "0056", "00878", "00919"))
    # 手動
    for r in load(ROOT / "config" / "events_manual.json", []) or []:
        try:
            add(date.fromisoformat(r["d"]), r.get("time", ""), r.get("cat", "其他"), r["title"], r.get("note", ""), r.get("star", True))
        except (KeyError, ValueError):
            continue
    seen, out = set(), []
    for e in sorted(ev, key=lambda e: (e["d"], e["time"] or "99", e["cat"], e["title"])):
        k = (e["d"], e["title"])
        if k not in seen:
            seen.add(k)
            out.append(e)
    doc = {"updatedAt": datetime.now(TPE).strftime("%Y-%m-%dT%H:%M+08:00"), "from": today.isoformat(), "to": end.isoformat(), "events": out}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=15)
    a = ap.parse_args()
    doc = build(a.days)
    for e in doc["events"]:
        d = date.fromisoformat(e["d"])
        print(f"{'★' if e['star'] else ' '} {d:%m/%d}（{WK[d.weekday()]}）{e['time']:5s} [{e['cat']}] {e['title']}  {e['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
