#!/usr/bin/env python3
"""
融資成本回補（推估融資維持率用）→ data/strategy/margin_seed.json、data/strategy/margin_hist.json

做法（參考 toalpha 的「推估融資成本」）：從 START 起逐日重播每檔股票的融資買賣，估算融資戶的平均成本
  每天：留下的部位＝前日餘額 − 融資賣出 − 現金償還（成本不變）；融資買進以當天收盤價加入，加權平均成新成本
  推估維持率＝收盤價 ÷（平均成本 × 融資成數），上市 6 成、上櫃 5 成；130% 是追繳線
資料：證交所 MI_MARGN、櫃買中心 margin/balance（每日融資買進／賣出／現償／餘額），Yahoo Finance 日收盤（含分割調整）

輸出：
  margin_seed.json  {"asof", "cost": {代號: [平均成本, 融資餘額]}}  build_market.py 從 asof 的隔天接著用每日資料重播
  margin_hist.json  {"series": [[日期, 上市維持率, 上櫃維持率]]}  大盤融資維持率走勢（融資市值 ÷ 交易所公布的融資金額）
每日原始融資資料存在 --cache（GitHub Actions cache），再跑只補新的日子
用法：python scripts/backfill_margin.py [--start 2021-11-15] [--cache 目錄] [--yahoo 目錄] [--minutes 280]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_exdiv import yahoo  # noqa: E402
from fetch_market_daily import TPE, log, margin_amt, tpex_margin, twse_margin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
RATIO = {0: 0.6, 1: 0.5}  # 上市、上櫃融資成數


def fetch_days(days, cache: Path, deadline: float):
    """每日融資資料：{"t": {代號: [餘額, 買進, 賣出, 現償]}, "o": {...}}；空的 t＝休市"""
    cache.mkdir(parents=True, exist_ok=True)
    got = {}
    for d in days:
        f = cache / f"{d.isoformat()}.json"
        if f.exists():
            doc = json.loads(f.read_text(encoding="utf-8"))
            # 舊的快取沒有官方融資金額，有時間就補抓
            if doc["t"] and "a" not in doc and time.time() < deadline:
                try:
                    doc["a"] = margin_amt(d)
                    f.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
                    log(f"{d}：補融資金額 {doc['a']}")
                except RuntimeError as e:
                    log(f"{d} 融資金額抓取失敗：{e}")
                time.sleep(2.5)
            got[d] = doc
            continue
        if time.time() > deadline:
            log(f"時間到，{d} 之後下次再補")
            break
        try:
            t = twse_margin(d)
            time.sleep(2.5)
            o = tpex_margin(d) if t else {}
            time.sleep(1)
        except RuntimeError as e:
            log(f"{d} 抓取失敗：{e}")
            time.sleep(10)
            continue
        doc = {"t": {c: [x[0], x[5], x[6], x[7]] for c, x in t.items() if len(x) >= 8},
               "o": {c: [x[0], x[5], x[6], x[7]] for c, x in o.items() if len(x) >= 8}}
        if t:
            try:
                time.sleep(1.5)
                doc["a"] = margin_amt(d)
            except RuntimeError as e:
                log(f"{d} 融資金額抓取失敗：{e}")
        f.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        got[d] = doc
        if t:
            log(f"{d}：上市 {len(t)}、上櫃 {len(o)}")
    return got


def closes(codes_mk: dict[str, int], ycache: Path):
    ycache.mkdir(parents=True, exist_ok=True)

    def one(item):
        code, mk = item
        r = yahoo(code + (".TWO" if mk else ".TW"), ycache)
        if not r:
            return code, {}
        q = r["indicators"]["quote"][0]
        out = {}
        for t, c in zip(r["timestamp"], q["close"]):
            if c:
                out[datetime.fromtimestamp(t, TPE).date().isoformat()] = c
        return code, out

    with ThreadPoolExecutor(8) as ex:
        return dict(ex.map(one, codes_mk.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-11-15")  # Yahoo 5 年日線的起點附近
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "jss-margin"))
    ap.add_argument("--yahoo", default=str(Path.home() / ".cache" / "jss-yahoo"))
    ap.add_argument("--minutes", type=int, default=280)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    daily = sorted((DATA / "daily").glob("20*.json"))
    last = json.loads(daily[-1].read_text(encoding="utf-8"))
    end = date.fromisoformat(last["date"])
    q = last["q"]
    days, d = [], date.fromisoformat(a.start)
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    raw = fetch_days(days, Path(a.cache), deadline)
    trade_days = [d for d in days if d in raw and raw[d]["t"]]
    if not trade_days:
        log("沒有資料")
        return 1
    if trade_days[-1] != end:
        log(f"資料只補到 {trade_days[-1]}，還沒到 {end}，下次執行會接著補；這次先不輸出")
        return 0
    mk = {c: v[1] for c, v in q.items()}
    codes = {c: mk[c] for c in set().union(*(raw[d]["t"].keys() | raw[d]["o"].keys() for d in trade_days[-5:])) if c in mk}
    log(f"抓 {len(codes)} 檔的歷史收盤")
    px = closes(codes, Path(a.yahoo))

    cost: dict[str, list] = {}
    lastp: dict[str, float] = {}
    series = []
    for d in trade_days:
        ds = d.isoformat()
        amt = raw[d].get("a") or [None, None]
        row = [ds]
        for m, key in ((0, "t"), (1, "o")):
            val = loan = bal_all = bal_known = 0.0
            for c, (bal, buy, sell, rep) in raw[d][key].items():
                bal_all += bal or 0
                pp = lastp.get(c)
                # Yahoo 偶爾整天缺收盤（例如 2025-08-01），缺的沿用前一天
                p = px.get(c, {}).get(ds) or pp
                if not p:
                    continue
                lastp[c] = p
                st = cost.get(c)
                if st is None or st[1] <= 0:
                    st = cost[c] = [p, bal]
                else:
                    keep = max(st[1] - (sell or 0) - (rep or 0), 0)
                    b = buy or 0
                    tot = keep + b
                    st[0] = (st[0] * keep + p * b) / tot if tot > 0 else p
                    st[1] = bal
                # Yahoo 偶爾有錯價：單日跳動超過 35% 的那天不算進大盤市值；
                # 減資股的歷史價會被 Yahoo 回推放大（例如光耀 2021 年變成 33 萬元），單檔市值超過整個市場融資金額 25% 的也不算
                if bal > 0 and not (pp and abs(p / pp - 1) > 0.35) and not (amt[m] and p * bal * 1000 > amt[m] * 0.25):
                    val += p * bal * 1000
                    loan += st[0] * RATIO[m] * bal * 1000
                    bal_known += bal
            # 大盤維持率＝融資市值 ÷ 官方融資金額（缺收盤的股票按張數比例扣掉）；沒有官方金額才用推估成本
            if amt[m] and bal_known and bal_all:
                row.append(round(val / (amt[m] * bal_known / bal_all) * 100, 1))
            else:
                row.append(round(val / loan * 100, 1) if loan else None)
        series.append(row)
    out = DATA / "strategy"
    out.mkdir(parents=True, exist_ok=True)
    seed = {"asof": trade_days[-1].isoformat(), "start": trade_days[0].isoformat(),
            "cost": {c: [round(v[0], 4), v[1]] for c, v in cost.items() if v[1] > 0}}
    (out / "margin_seed.json").write_text(json.dumps(seed, separators=(",", ":")), encoding="utf-8")
    (out / "margin_hist.json").write_text(json.dumps({"series": series}, separators=(",", ":")), encoding="utf-8")
    log(f"融資成本：{trade_days[0]} ~ {trade_days[-1]}（{len(trade_days)} 天）、{len(seed['cost'])} 檔；大盤推估維持率 上市 {series[-1][1]}%、上櫃 {series[-1][2]}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
