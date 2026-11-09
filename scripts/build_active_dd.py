"""
主動式 ETF 停損監控 → public/data/active_dd.json

讀 data/etf/active_cost.json（active_cost.py 回推的各檔主動式 ETF 每個部位平均建倉成本），配上最新收盤：
  DD＝收盤 ÷ 平均成本 − 1；投信風控常見做法是虧損約 40% 就要停損或檢討，-40% 價＝成本 × 0.6
  距停損＝停損價 ÷ 收盤 − 1（負的＝還要跌多少）
  跌破日：從最新一天往回找收盤連續低於 -40% 價（用目前的平均成本推算）的第一天；
  預估停損期限：投信停損規則不公開，假設跌破後 GRACE 個交易日內要處理（檢討或賣出）
  疑似停損：最新一天減碼 ≥ 50 張（或整個出清）、而且 DD 已到 -30% 以下的部位
  個股彙總：同一檔股票被幾檔主動式 ETF 持有、其中幾檔 DD 已到 -30%、-40%，合計可能被停損的張數與市值
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from build_margin import add_trading_days, streak_start
from build_strategy import TPE, _load

STOP = -40.0
WARN = -30.0
GRACE = 5


def live_sells(data_dir: Path, etfs: dict, q: dict) -> tuple[list, str | None]:
    """各檔主動 ETF 最新一份持股對前一份：減碼 ≥ 50 張或出清、而且 DD ≤ WARN 的部位；回傳 (清單, 所有 ETF 中最新的持股日)"""
    out, latest = [], None
    for code, e in etfs.items():
        snaps = (_load(data_dir / "etf" / "holdings" / f"{code}.json", {}) or {}).get("snapshots") or []
        if len(snaps) < 2:
            continue
        s0, s1 = snaps[-2], snaps[-1]
        latest = max(latest or "", s1["date"])
        h0 = {r[0]: (r[2] or 0, r[1]) for r in s0["h"] if " " not in r[0]}
        h1 = {r[0]: r[2] or 0 for r in s1["h"] if " " not in r[0]}
        cost = {x[0]: x[3] for x in e["rows"]}
        cost.update({x[0]: x[3] for x in e.get("closed") or []})
        en = e["name"].replace("主動", "")
        # 整檔被贖回時所有持股會等比例減少：用各持股股數變化的中位數當基準，只算超出基準的減碼
        ratios = sorted(h1.get(c, 0) / sh for c, (sh, _) in h0.items() if sh)
        base = min(1.0, ratios[len(ratios) // 2]) if ratios else 1.0
        for c, (sh0, name) in h0.items():
            d = h1.get(c, 0) - sh0 * base
            v, cs = q.get(c), cost.get(c)
            if d > -50000 or not v or not v[5] or not cs:
                continue
            dd = (v[5] / cs - 1) * 100
            if dd <= WARN:
                out.append({"etf": code, "etfName": en, "code": c, "name": v[0] or name, "dd": round(dd, 1), "c1": round(d / 1000),
                            "lots": round(h1.get(c, 0) / 1000), "out": c not in h1 or h1[c] == 0, "asof": s1["date"], "prev": s0["date"]})
    # 只留最新持股日的（有些投信比較晚公布，還停在前一天的就不算「最新一天」）
    return [x for x in out if x["asof"] == latest], latest


def compute(data_dir: Path) -> dict | None:
    src = _load(data_dir / "etf" / "active_cost.json", {}) or {}
    etfs = src.get("etfs") or {}
    if not etfs:
        return None
    days = [d for d in (_load(p, {}) for p in sorted((data_dir / "daily").glob("20*.json"))) if d.get("q")]
    if not days:
        return None
    last, li = days[-1], len(days) - 1
    dates = [d["date"] for d in days]
    q = last["q"]
    rows, agg, sells = [], {}, []
    for code, e in etfs.items():
        en = e["name"].replace("主動", "")
        # 最新一天整個出清、出清前已經虧損 30% 以上的（疑似停損）
        for c, name, sh, cost in e.get("closed") or []:
            v = q.get(c)
            if v and v[5] and cost and (v[5] / cost - 1) * 100 <= WARN and sh >= 50000:
                sells.append({"etf": code, "etfName": en, "code": c, "name": v[0] or name, "dd": round((v[5] / cost - 1) * 100, 1),
                              "c1": -round(sh / 1000), "lots": 0, "out": True, "asof": e["asof"]})
        for x in e["rows"]:
            c, name, sh, cost, first, first_px, w, sh5, sh20 = x[:9]
            sh1 = x[9] if len(x) > 9 else None
            v = q.get(c)
            if not v or not v[5] or not cost:
                continue
            close = v[5]
            dd = (close / cost - 1) * 100
            stop = cost * (1 + STOP / 100)
            lots = sh / 1000
            r = {"etf": code, "etfName": en, "code": c, "name": v[0] or name, "lots": round(lots),
                 "w": w, "cost": round(cost, 2), "first": first, "firstPx": first_px, "close": close, "dd": round(dd, 1),
                 "stop": round(stop, 2), "dist": round((stop / close - 1) * 100, 1),
                 "c5": round((sh - sh5) / 1000) if sh5 is not None else None, "c20": round((sh - sh20) / 1000) if sh20 is not None else None,
                 "c1": round((sh - sh1) / 1000) if sh1 is not None else None,
                 "val": round(sh * close / 1e8, 2), "dated": e["dated"]}
            if dd <= STOP:
                b = streak_start(days, li, c, stop)
                r["below"], r["due"] = b, add_trading_days(data_dir, b, GRACE, dates) if b else None
            rows.append(r)
            if r["c1"] and r["c1"] <= -50 and dd <= WARN:
                sells.append({"etf": code, "etfName": en, "code": c, "name": r["name"], "dd": r["dd"], "c1": r["c1"], "lots": r["lots"], "out": False, "asof": e["asof"]})
            if lots < 50:
                continue  # 不到 50 張的零星部位不算進個股彙總
            a = agg.setdefault(c, {"code": c, "name": r["name"], "close": close, "n": 0, "warn": 0, "stop": 0, "lots": 0, "riskLots": 0,
                                   "riskVal": 0.0, "costSum": 0.0, "c5": 0, "etfs": [], "due": None})
            a["n"] += 1
            if r.get("due") and (a["due"] is None or r["due"] < a["due"]):
                a["due"] = r["due"]
            a["lots"] += lots
            a["costSum"] += cost * sh
            a["c5"] += r["c5"] or 0
            a["etfs"].append([code, r["dd"], r["etfName"]])  # [ETF 代號, DD, 名稱]
            if dd <= WARN:
                a["warn"] += 1
                a["riskLots"] += lots
                a["riskVal"] += sh * close / 1e8
            if dd <= STOP:
                a["stop"] += 1
    stocks = []
    for a in agg.values():
        if not a["lots"]:
            continue
        avg = a.pop("costSum") / (a["lots"] * 1000)
        a["cost"] = round(avg, 2)
        a["dd"] = round((a["close"] / avg - 1) * 100, 1)
        a["lots"] = round(a["lots"])
        a["riskLots"] = round(a["riskLots"])
        a["riskVal"] = round(a["riskVal"], 2)
        a["vol"] = q[a["code"]][7] if q.get(a["code"]) else None
        a["etfs"].sort(key=lambda x: x[1])
        stocks.append(a)
    rows.sort(key=lambda r: r["dd"])
    stocks.sort(key=lambda a: (-a["warn"], a["dd"]))
    meta = [{"code": c, "name": e["name"], "issuer": e["issuer"], "dated": e["dated"], "start": e["start"], "asof": e["asof"],
             "n": len(e["rows"])} for c, e in sorted(etfs.items())]
    # 疑似停損改用每天 21:20 抓的最新持股（data/etf/holdings）比對前一份，不必等成本重算；成本用 active_cost 的平均成本
    live, latest = live_sells(data_dir, etfs, q)
    if latest:
        sells = live
    sells.sort(key=lambda x: x["c1"])
    asof = max([e["asof"] for e in etfs.values()] + ([latest] if latest else []))
    return {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "date": last["date"], "asof": asof, "stop": STOP, "warn": WARN, "grace": GRACE,
            "count": {"stop": sum(r["dd"] <= STOP for r in rows), "warn": sum(STOP < r["dd"] <= WARN for r in rows),
                      "stocks": sum(a["warn"] > 0 for a in stocks)},
            "etfs": meta, "rows": rows, "stocks": stocks, "sells": sells}


def build(data_dir: Path, public_dir: Path):
    out = compute(data_dir)
    if not out:
        return
    (public_dir / "active_dd.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"主動式 ETF 停損監控：{len(out['etfs'])} 檔 ETF、{len(out['rows'])} 個部位，DD ≤ -40% {out['count']['stop']} 個、"
          f"-30～-40% {out['count']['warn']} 個，疑似停損賣出 {len(out['sells'])} 筆")
