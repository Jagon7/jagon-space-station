#!/usr/bin/env python3
"""
美股異常大額選擇權（台股相關美股）：Nasdaq 選擇權報價（公開、延遲約 15 分鐘）的每個合約當日累計成交

每天美股收盤後（台灣清晨）抓一次，每個合約算：
  成交金額（權利金）≈ 成交量 × 最後成交價 × 100；成交量 ÷ 未平倉（未平倉是前一天的，> 1 代表多半是新建倉）
  主動方向（粗估）：最後價靠近賣價＝偏買方追價、靠近買價＝偏賣方；到期天數、價內外
異常（任一；一週內到期的不算，0DTE 多半是短線投機）：
  新建倉大單：成交金額 ≥ 1,000 萬美元且成交量 ≥ 2 倍未平倉
  超大額：成交金額 ≥ 3,000 萬美元且成交量 ≥ 未平倉（以新建倉為主，不是換倉）
  長天期（≥ 1 年）：成交金額 ≥ 500 萬美元且成交量 ≥ 未平倉
  個股整體：買權（或賣權）總成交金額 ≥ 近 20 天平均 2 倍且 ≥ 5,000 萬美元
限制：免費資料只有每個合約的當日合計，沒有逐筆成交時間、掃單／大宗、買賣方（付費的 OPRA 逐筆資料才有）
輸出 data/intel/options_flow.json（最新一天）、data/intel/options_hist.json（各股每天買權／賣權總成交金額，給基準用）
用法：python scripts/fetch_options_flow.py [代號 ...]
"""
from __future__ import annotations

import json
import os
import re
import statistics as st
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "intel" / "options_flow.json"
HIST = DATA / "intel" / "options_hist.json"
TPE = timezone(timedelta(hours=8))
TICKERS = ["NVDA", "TSM", "AMD", "AVGO", "MU", "AAPL", "TSLA", "SMCI", "DELL", "ASML", "MSFT", "GOOGL", "META", "AMZN", "INTC", "QCOM", "ARM", "MRVL"]
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
     "Accept": "application/json"}
NEW_MIN, BIG_MIN, LEAP_MIN, TOTAL_MIN = 10e6, 30e6, 5e6, 50e6
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def num(x) -> float:
    try:
        return float(str(x).replace(",", "").replace("$", ""))
    except ValueError:
        return 0.0


def chain(sym: str) -> dict | None:
    for i in range(3):
        try:
            r = requests.get(f"https://api.nasdaq.com/api/quote/{sym}/option-chain", headers=H, timeout=60,
                             params={"assetclass": "stocks", "limit": "6000", "fromdate": "all", "todate": "undefined", "excode": "oprac",
                                     "callput": "callput", "money": "all", "type": "all"})
            j = r.json()
            if j.get("data") and j["data"].get("table"):
                return j["data"]
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (i + 1))
    return None


def parse(sym: str, d: dict) -> dict:
    lt = d.get("lastTrade") or ""
    m = re.search(r"\$([\d.,]+).*AS OF ([A-Z]{3}) (\d+), (\d{4}) (\d+):(\d+) ([AP]M)", lt)
    spot = num(m.group(1)) if m else None
    asof, final = None, False
    if m:
        hh = int(m.group(5)) % 12 + (12 if m.group(7) == "PM" else 0)
        asof = date(int(m.group(4)), MONTHS[m.group(2)], int(m.group(3))).isoformat()
        final = hh * 60 + int(m.group(6)) >= 16 * 60  # 美東 16:00 收盤後的資料才是全天
    exp, rows = None, []
    for x in d["table"]["rows"]:
        if x.get("expirygroup"):
            try:
                exp = datetime.strptime(x["expirygroup"], "%B %d, %Y").date().isoformat()
            except ValueError:
                exp = None
            continue
        if not exp:
            continue
        k = num(x.get("strike"))
        for cp, pre in (("C", "c_"), ("P", "p_")):
            v, oi, last = num(x.get(pre + "Volume")), num(x.get(pre + "Openinterest")), num(x.get(pre + "Last"))
            if not v or not last:
                continue
            bid, ask = num(x.get(pre + "Bid")), num(x.get(pre + "Ask"))
            side = None
            if ask > bid > 0:
                pos = (last - bid) / (ask - bid)
                side = "買方" if pos >= 0.75 else "賣方" if pos <= 0.25 else "中間"
            prem = v * last * 100
            dte = (date.fromisoformat(exp) - date.fromisoformat(asof)).days if asof else None
            rows.append({"cp": cp, "exp": exp, "k": k, "vol": int(v), "oi": int(oi), "last": last, "bid": bid, "ask": ask, "prem": round(prem),
                         "voi": round(v / oi, 2) if oi else None, "side": side, "dte": dte,
                         "otm": round((k / spot - 1) * 100 * (1 if cp == "C" else -1), 1) if spot else None})
    callp = sum(r["prem"] for r in rows if r["cp"] == "C")
    putp = sum(r["prem"] for r in rows if r["cp"] == "P")
    flags = []
    for r in rows:
        if (r["dte"] or 0) < 7:
            continue  # 一週內到期（含當天到期的 0DTE）多半是短線投機，不算
        why = []
        if r["prem"] >= NEW_MIN and r["vol"] >= 2 * max(1, r["oi"]):
            why.append("新建倉大單")
        if r["prem"] >= BIG_MIN and r["vol"] >= max(1, r["oi"]):
            why.append("超大額")
        if (r["dte"] or 0) >= 365 and r["prem"] >= LEAP_MIN and r["vol"] >= max(1, r["oi"]):
            why.append("長天期")
        if why:
            flags.append({**r, "why": why})
    top = sorted(rows, key=lambda r: -r["prem"])[:25]
    return {"sym": sym, "spot": spot, "asof": asof, "final": final, "lastTrade": lt, "callPrem": round(callp), "putPrem": round(putp),
            "callVol": sum(r["vol"] for r in rows if r["cp"] == "C"), "putVol": sum(r["vol"] for r in rows if r["cp"] == "P"),
            "top": top, "flags": sorted(flags, key=lambda r: -r["prem"])}


def main():
    syms = [a.upper() for a in sys.argv[1:]] or TICKERS
    try:
        hist = json.loads(HIST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    out = {}
    for s in syms:
        d = chain(s)
        if not d:
            print(f"{s}：抓不到")
            continue
        o = parse(s, d)
        # 個股整體異常：買權／賣權總成交金額對近 20 天
        h = [x for x in hist.get(s, []) if x[0] < (o["asof"] or "")][-20:]
        for key, idx, lab in (("callPrem", 1, "買權"), ("putPrem", 2, "賣權")):
            base = st.mean(x[idx] for x in h) if len(h) >= 5 else None
            o[key + "Base"] = round(base) if base else None
            o[key + "X"] = round(o[key] / base, 2) if base else None
            if base and o[key] >= 2 * base and o[key] >= TOTAL_MIN:
                o.setdefault("totalFlags", []).append(f"{lab}總成交 {o[key] / 1e6:,.0f}M 美元，是近 20 天平均的 {o[key] / base:.1f} 倍")
        if o["final"] and o["asof"]:
            hist[s] = [x for x in hist.get(s, []) if x[0] != o["asof"]] + [[o["asof"], o["callPrem"], o["putPrem"]]]
            hist[s] = sorted(hist[s])[-90:]
        out[s] = o
        print(f"{s} {o['asof']}{'' if o['final'] else '（盤中）'}：買權 {o['callPrem'] / 1e6:,.0f}M／賣權 {o['putPrem'] / 1e6:,.0f}M 美元，異常合約 {len(o['flags'])} 筆"
              + (f"；{'；'.join(o['totalFlags'])}" if o.get("totalFlags") else ""))
        time.sleep(1.5)
    if not out:
        return 1
    asof = max((o["asof"] or "") for o in out.values())
    doc = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "asof": asof, "final": all(o["final"] for o in out.values() if o["asof"] == asof),
           "rules": {"newMin": NEW_MIN, "bigMin": BIG_MIN, "leapMin": LEAP_MIN, "totalMin": TOTAL_MIN}, "tickers": out}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    HIST.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
