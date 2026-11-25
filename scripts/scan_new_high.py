#!/usr/bin/env python3
"""
新高法每日掃描（回測：scripts/research_new_high.py；規則跟回測一樣，出場用回測較好的「拿 10 個交易日」）

  1 突破日：當天成交額前 50（上市＋上櫃、去掉 ETF）、收盤創一年新高（> 前 250 天最高收盤）、站上 120 日線、
           漲 ≥ 4% 且量 ≥ 20 日均量 2 倍（放量長紅）、同產業前 50 名裡近 20 天漲幅第一（龍頭）、加權指數 > 60 日線
  2 買點：突破後 1～3 天內第一根收黑或十字星（|收−開| ≤ 0.3%）、收盤仍 ≥ 突破前的高點、在 5 日線上 → 當天收盤（或隔天開盤）買
  3 賣出：訊號隔天開盤買、買進後第 10 個交易日收盤賣（訊號日 +11 個交易日）
價格用 Yahoo 還原權息日線（最近幾天用 data/daily 的官方行情補）；三大法人（外資＋投信，突破到買點合計，張）只列出參考
輸出 data/strategy/new_high.json：今天的新買點、等買點的突破股（明天的條件）、持有中（第幾天、預定賣出日）
用法：python scripts/scan_new_high.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "strategy" / "new_high.json"
TPE = timezone(timedelta(hours=8))
TOPN, LOOK, HOLD = 50, 20, 10


def ma(v, i, n):
    return sum(v[i - n + 1:i + 1]) / n if i >= n - 1 else None


def yahoo(code: str, mkt: int) -> list | None:
    sym = f"{code}.{'TWO' if mkt else 'TW'}"
    for i in range(3):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                             params={"range": "2y", "interval": "1d", "events": "div,split"})
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(res["timestamp"])
            off = (res.get("meta") or {}).get("gmtoffset") or 0
            rows = []
            for k, t in enumerate(res["timestamp"]):
                c, a = q["close"][k], adj[k]
                if not (c and a and q["open"][k] and q["high"][k] and q["low"][k]):
                    continue
                f = a / c
                rows.append([datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(),
                             q["open"][k] * f, q["high"][k] * f, q["low"][k] * f, a, q["volume"][k] or 0])
            return rows
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            time.sleep(3 * (i + 1))
    return None


def main():
    files = sorted(glob.glob(str(DATA / "daily" / "20*.json")))[-LOOK:]
    days = [json.loads(Path(f).read_text(encoding="utf-8")) for f in files]
    days = [d for d in days if d.get("q") and not d.get("partial")]
    if not days:
        print("沒有每日行情")
        return 1
    today = days[-1]["date"]
    # 每天成交額前 50（4 碼個股，不含 0 開頭 ETF）
    top, mkt_of, name = {}, {}, {}
    for d in days:
        xs = [(v[8] or 0, c) for c, v in d["q"].items() if len(c) == 4 and c.isdigit() and c[0] != "0" and v[5]]
        top[d["date"]] = [c for _, c in sorted(xs, reverse=True)[:TOPN]]
        for c, v in d["q"].items():
            mkt_of[c], name[c] = v[1], v[0]
    codes = sorted({c for t in top.values() for c in t})
    with ThreadPoolExecutor(4) as ex:
        hist = dict(zip(codes, ex.map(lambda c: yahoo(c, mkt_of.get(c, 0)), codes)))
    # 最近幾天用官方行情（data/daily）補上或覆蓋 Yahoo（Yahoo 當天常缺收盤）；還原因子：最近一次 Yahoo 的還原收盤 ÷ 官方收盤
    px = {}
    for c in codes:
        rows = {r[0]: r for r in (hist.get(c) or [])}
        if len(rows) < 260:
            continue
        for d in days:
            v = d["q"].get(c)
            if not v or not v[5]:
                continue
            o, h, lo, cl, vol = v[2], v[3], v[4], v[5], (v[7] or 0) * 1000
            k = rows[d["date"]][4] / cl if d["date"] in rows and cl else 1.0
            rows[d["date"]] = [d["date"], o * k, h * k, lo * k, cl * k, vol]
        r = [rows[x] for x in sorted(rows)]
        px[c] = {"d": [x[0] for x in r], "o": [x[1] for x in r], "h": [x[2] for x in r], "l": [x[3] for x in r],
                 "c": [x[4] for x in r], "v": [x[5] for x in r]}
        px[c]["idx"] = {x: i for i, x in enumerate(px[c]["d"])}
    # 大盤濾網
    tw = json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]
    twc = [r[4] for r in tw]
    mkt_ok = {r[0]: twc[i] > ma(twc, i, 60) for i, r in enumerate(tw) if i >= 60}
    for d in days:  # 加權指數最新一天沒進 Yahoo 檔時用每日行情的指數（ix＝[收盤, 漲跌%]）
        ix = d.get("ix")
        if d["date"] not in mkt_ok and d["date"] > tw[-1][0] and isinstance(ix, list) and ix and ix[0]:
            mkt_ok[d["date"]] = ix[0] > ma(twc + [ix[0]], len(twc), 60)
    # 產業
    from research_new_high import sector_map
    sec = sector_map(DATA)  # 官方產業別（題材類股會隨每天排序變動，不用）
    # 三大法人（張）
    inst = {}
    for d in days:
        fp = DATA / "insti" / f"{d['date']}.json"
        if fp.exists():
            inst[d["date"]] = json.loads(fp.read_text(encoding="utf-8"))
    dates = [d["date"] for d in days]
    breakouts = []
    for D in dates:
        ret20 = {}
        for c in top[D]:
            f = px.get(c)
            if f and D in f["idx"] and f["idx"][D] >= 20:
                i = f["idx"][D]
                ret20[c] = f["c"][i] / f["c"][i - 20] - 1
        best = defaultdict(lambda: (-9, None))
        for c, r in ret20.items():
            if sec.get(c) and r > best[sec[c]][0]:
                best[sec[c]] = (r, c)
        for c in top[D]:
            f = px.get(c)
            if not f or D not in f["idx"]:
                continue
            i = f["idx"][D]
            if i < 250:
                continue
            cl, v = f["c"], f["v"]
            prior = max(cl[i - 250:i])
            chg = (cl[i] / cl[i - 1] - 1) * 100
            av20 = ma(v, i - 1, 20)
            if not (cl[i] > prior and cl[i] > ma(cl, i, 120) and chg >= 4 and av20 and v[i] >= 2 * av20):
                continue
            leader = bool(sec.get(c)) and best[sec[c]][1] == c
            breakouts.append({"code": c, "name": name.get(c, c), "otc": mkt_of.get(c) == 1, "sector": sec.get(c), "date": D, "i": i,
                              "chg": round(chg, 1), "volX": round(v[i] / av20, 1), "prior": prior, "leader": leader, "mktOk": bool(mkt_ok.get(D))})
    import build_margin
    signals, watch, holding = [], [], []
    used = set()  # 同一個買點只算一次（合格的突破優先）
    for b in sorted(breakouts, key=lambda b: (not (b["leader"] and b["mktOk"]), b["date"])):
        f = px[b["code"]]
        o, cl, i = f["o"], f["c"], b["i"]
        status, buy = "等買點", None
        for k in (1, 2, 3):
            j = i + k
            if j >= len(cl):
                break
            if cl[j] < b["prior"]:
                status = "跌回前高之下（取消）"
                break
            m5 = ma(cl, j, 5)
            if (cl[j] <= o[j] or abs(cl[j] / o[j] - 1) <= 0.003) and m5 and cl[j] > m5:
                buy = j
                status = "買點"
                break
        if status == "等買點" and i + 3 < len(cl):
            status = "3 天內沒出現買點（取消）"
        qualified = b["leader"] and b["mktOk"]
        row = {k: b[k] for k in ("code", "name", "otc", "sector", "date", "chg", "volX", "leader", "mktOk")}
        row["prior"] = round(b["prior"], 2)
        row["qualified"] = qualified
        if buy is not None:
            if (b["code"], buy) in used:
                continue
            used.add((b["code"], buy))
            bd = f["d"][buy]
            sell = build_margin.add_trading_days(DATA, bd, HOLD + 1, [])  # 晚上看到、隔天開盤買 → 買進後第 10 個交易日收盤賣（回測：隔天開盤買版）
            ds = f["d"][i:buy + 1]
            ft = sum(sum((inst.get(x, {}).get(b["code"]) or [0, 0, 0, 0])[2:4]) for x in ds)
            row.update({"buy": bd, "buyClose": round(cl[buy], 2), "sell": sell, "inst": ft if all(x in inst for x in ds) else None,
                        "day": len(f["d"]) - 1 - buy, "ret": round((cl[-1] / cl[buy] - 1) * 100, 1)})
            if bd == today:
                signals.append(row)
            elif sell and sell >= today:
                holding.append(row)
        elif status == "等買點":
            j = len(cl) - 1
            # 明天的條件：收黑或十字、收盤 ≥ 前高、收盤 > 5 日線（含明天收盤的 5 日線 → 收盤 > 最近 4 天平均）
            row.update({"daysLeft": 3 - (j - i), "needAbove": round(max(b["prior"], sum(cl[j - 3:j + 1]) / 4), 2), "lastClose": round(cl[j], 2)})
            watch.append(row)
    doc = {"date": today, "updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "marketOk": bool(mkt_ok.get(today)),
           "hold": HOLD, "signals": signals, "watch": watch, "holding": holding,
           "breakouts": [{k: b[k] for k in ("code", "name", "date", "chg", "volX", "leader", "mktOk")} for b in breakouts if b["date"] == today]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{today} 大盤 {'> ' if doc['marketOk'] else '< '}60 日線；今天突破 {len(doc['breakouts'])} 檔、新買點 {len(signals)}"
          f"（合格 {sum(r['qualified'] for r in signals)}）、等買點 {len(watch)}、持有中 {len(holding)}")
    for r in signals + watch + holding:
        print(" ", r["code"], r["name"], r["date"], "合格" if r["qualified"] else "（不合格：" + ("非龍頭" if not r["leader"] else "大盤弱") + "）",
              r.get("buy", ""), r.get("sell", ""), r.get("needAbove", ""), r.get("ret", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
