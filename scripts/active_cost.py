#!/usr/bin/env python3
"""
主動式 ETF 建倉成本回推 → data/etf/active_cost.json

做法：逐日抓每檔主動式 ETF 從掛牌起的持股（投信網站可查指定日期的那幾家），用每天的股數增減重播平均成本
  股數增加：增加的部分以當天收盤價買進，和原有部位加權平均成新成本
  股數減少：以平均成本出場（成本不變）；減到 0 就結束這段部位，之後重新買進算新的建倉
  不能查歷史的投信（富邦、凱基、台新、永豐、聯博）只能從網站開始抓持股那天起算，成本偏向近期價位
價格：Yahoo Finance 日收盤（含分割、減資調整，和現在的股價同一基準）

輸出 {"asof", "etfs": {代號: {"name", "issuer", "dated", "start", "rows": [[股票, 名稱, 股數, 平均成本, 建倉日, 建倉價, 權重, 5 日前股數, 20 日前股數]]}}}
每日原始持股存在 --cache（GitHub Actions cache），再跑只補新的日子
用法：python scripts/active_cost.py [--cache 目錄] [--yahoo 目錄] [--minutes 120] [代號 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import etf_sources as S  # noqa: E402
from backtest_exdiv import yahoo  # noqa: E402
from fetch_etf import DATA_DIR, ETF_DIR, ETF_LIST, log, read_json, write_json  # noqa: E402

FIRST = date(2025, 4, 1)   # 最早的主動式 ETF（00980A～00985A）2025 年 5 月掛牌
STOP_MISS = 20             # 往回抓連續這麼多個平日都沒資料，就當作已經到掛牌前


def weekdays_back(last: date, first: date) -> list[date]:
    out, d = [], last
    while d >= first:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def fetch_hist(code, name, issuer, cache: Path, last: date, deadline: float) -> dict:
    """{"asked": [...], "snaps": {日期: [[股票, 名稱, 股數, 權重]]}}；由近往遠抓，連續 STOP_MISS 天沒資料就停"""
    f = cache / f"{code}.json"
    doc = read_json(f, {"asked": [], "snaps": {}})
    asked, snaps = set(doc["asked"]), doc["snaps"]
    miss = 0
    for d in weekdays_back(last, FIRST):
        ds = d.isoformat()
        if ds not in asked:
            if time.time() > deadline:
                break
            try:
                s = S.SOURCES[issuer][1](code, name, start=d)
            except Exception:  # noqa: BLE001  那天沒資料（掛牌前、休市）或暫時失敗
                s = None
            # 最近幾天可能只是還沒公布，沒抓到就下次再試
            if (s and s["date"] == ds) or d < last - timedelta(days=7):
                asked.add(ds)
            if s and len(s["holdings"]) >= 5 and str(s["date"]) >= FIRST.isoformat():
                snaps[s["date"]] = [[x["code"], x["name"], x["shares"] or 0, x.get("weight")] for x in s["holdings"] if " " not in x["code"]]
        miss = 0 if ds in snaps else miss + 1
        if miss >= STOP_MISS:
            break
    snaps = {k: v for k, v in snaps.items() if k >= FIRST.isoformat()}
    write_json(f, {"asked": sorted(asked), "snaps": dict(sorted(snaps.items()))})
    return snaps


def closes(codes_mk: dict[str, int], ycache: Path) -> dict[str, list]:
    """{代號: [(日期, 收盤)] 依日期排序}"""
    ycache.mkdir(parents=True, exist_ok=True)

    def one(item):
        code, mk = item
        r = yahoo(code + (".TWO" if mk else ".TW"), ycache)
        if not r:
            return code, []
        q = r["indicators"]["quote"][0]
        return code, sorted((datetime.fromtimestamp(t, S.TPE).date().isoformat(), c) for t, c in zip(r["timestamp"], q["close"]) if c)

    with ThreadPoolExecutor(8) as ex:
        return dict(ex.map(one, codes_mk.items()))


def price_on(series: list, ds: str):
    """當天（或之前最近一天）的收盤"""
    lo, hi = 0, len(series)
    while lo < hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= ds:
            lo = mid + 1
        else:
            hi = mid
    return series[lo - 1][1] if lo else (series[0][1] if series else None)


def replay(snaps: dict[str, list], px: dict[str, list]) -> list:
    dates = sorted(snaps)
    pos: dict[str, list] = {}   # 股票 → [股數, 平均成本, 建倉日, 建倉價]
    hist: dict[str, dict[str, int]] = defaultdict(dict)
    for ds in dates:
        now = {r[0]: r[2] for r in snaps[ds]}
        for c in set(pos) | set(now):
            sh = now.get(c, 0)
            hist[c][ds] = sh
            st = pos.get(c)
            p = price_on(px.get(c) or [], ds)
            if not p:
                continue
            if st is None or st[0] <= 0:
                if sh > 0:
                    pos[c] = [sh, p, ds, p]
                continue
            if sh > st[0]:
                st[1] = (st[1] * st[0] + p * (sh - st[0])) / sh
            st[0] = sh
            if sh <= 0:
                pos.pop(c)
    last = snaps[dates[-1]]
    back = lambda n, c: hist[c].get(dates[-1 - n]) if len(dates) > n else None  # noqa: E731
    rows = []
    for c, name, sh, w in last:
        st = pos.get(c)
        if not st or sh <= 0:
            continue
        rows.append([c, name, sh, round(st[1], 3), st[2], round(st[3], 2), w, back(5, c), back(20, c)])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "jss-active"))
    ap.add_argument("--yahoo", default=str(Path.home() / ".cache" / "jss-yahoo"))
    ap.add_argument("--minutes", type=float, default=120)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    daily = sorted((DATA_DIR / "daily").glob("20*.json"))
    q = read_json(daily[-1], {}).get("q", {})
    last = datetime.now(S.TPE).date()
    targets = [t for t in ETF_LIST if t[3] == "active" and (not a.codes or t[0] in a.codes)]

    by_issuer = defaultdict(list)
    for t in targets:
        by_issuer[t[2]].append(t)

    def run_issuer(items):
        out = {}
        for code, name, issuer, _ in items:
            snaps = fetch_hist(code, name, issuer, cache, last, deadline) if issuer in S.DATED_SOURCES else {}
            # 網站每天抓的持股也併進來（不能查歷史的投信只有這些）
            for s in read_json(ETF_DIR / "holdings" / f"{code}.json", {}).get("snapshots", []):
                snaps.setdefault(s["date"], [[r[0], r[1], r[2] or 0, r[3]] for r in s["h"] if " " not in r[0]])
            out[code] = (name, issuer, snaps)
            log(f"  {code} {name}：{len(snaps)} 天" + (f"（{min(snaps)} 起）" if snaps else ""))
        return out

    got = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for part in pool.map(run_issuer, by_issuer.values()):
            got.update(part)

    codes = {r[0] for _, _, snaps in got.values() for rows in snaps.values() for r in rows if r[0] in q}
    log(f"抓 {len(codes)} 檔的歷史收盤")
    px = closes({c: q[c][1] for c in codes}, Path(a.yahoo))

    etfs = {}
    for code, (name, issuer, snaps) in got.items():
        # 台股部位太少的（海外主動式）不算
        if not snaps or len(snaps[max(snaps)]) < 5:
            continue
        rows = replay(snaps, px)
        if rows:
            etfs[code] = {"name": name, "issuer": S.SOURCES[issuer][0], "dated": issuer in S.DATED_SOURCES,
                          "start": min(snaps), "asof": max(snaps), "days": len(snaps), "rows": rows}
    write_json(ETF_DIR / "active_cost.json", {"updatedAt": datetime.now(S.TPE).isoformat(timespec="minutes"), "etfs": etfs})
    log(f"主動式 ETF 建倉成本：{len(etfs)} 檔、{sum(len(e['rows']) for e in etfs.values())} 個部位")
    return 0


if __name__ == "__main__":
    sys.exit(main())
