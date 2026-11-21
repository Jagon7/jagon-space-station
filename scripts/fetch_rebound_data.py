#!/usr/bin/env python3
"""
抄底個股研究資料：台股歷次大回檔（2012 起、跌幅 ≥ 15%）低點前後的上市個股行情與籌碼（證交所）

每一波（低點＝T）抓：
  行情 MI_INDEX（每日收盤行情）：波段高點日、T−9～T+5 每天、T+20、T+60
  三大法人 T86：T−9～T+5 每天
  融資融券 MI_MARGN：波段高點日、T
  外資持股 MI_QFIIS：T（[外資持股比率%, 當時發行股數]，融資使用率、市值用當時的股數）
存 data/research/rebound/<種類>_<YYYYMMDD>.json（只留需要的欄位）；已抓過的不重抓
用法：python scripts/fetch_rebound_data.py（GitHub Actions 上跑；證交所連續抓太快會被擋，每次間隔 4 秒）
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "research" / "rebound"
H = {"User-Agent": "Mozilla/5.0"}


def num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def get(urls):
    for i in range(3):
        for u in urls:
            try:
                r = requests.get(u, headers=H, timeout=60)
                j = r.json()
                if j.get("stat") == "OK" or j.get("tables") or j.get("data"):
                    return j
                if "沒有符合" in str(j.get("stat", "")) or "很抱歉" in str(j.get("stat", "")):
                    return {}
            except (requests.RequestException, ValueError):
                pass
            time.sleep(4)
        time.sleep(20 * (i + 1))
    return None


def quotes(d):
    j = get([f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={d}&type=ALLBUT0999&response=json",
             f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={d}&type=ALLBUT0999"])
    if j is None:
        return None
    tabs = j.get("tables") or [{"title": k, "fields": j.get(f.replace("data", "fields")), "data": j[f]} for k, f in
                                (("每日收盤行情", "data9"), ("每日收盤行情", "data8"), ("每日收盤行情", "data5")) if j.get(f)]
    for t in tabs:
        if "每日收盤行情" in str(t.get("title", "")) and t.get("data"):
            f = t["fields"]
            ic, iv, iva, ih, il = f.index("收盤價"), f.index("成交股數"), f.index("成交金額"), f.index("最高價"), f.index("最低價")
            return {r[0].strip(): [r[1].strip(), num(r[ic]), num(r[iv]), num(r[iva]), num(r[ih]), num(r[il])] for r in t["data"]}
    return {}


def t86(d):
    j = get([f"https://www.twse.com.tw/fund/T86?response=json&date={d}&selectType=ALLBUT0999",
             f"https://www.twse.com.tw/rwd/zh/fund/T86?date={d}&selectType=ALLBUT0999&response=json"])
    if j is None:
        return None
    f = j.get("fields") or []
    data = j.get("data") or []
    if not f and j.get("tables"):
        f, data = j["tables"][0]["fields"], j["tables"][0]["data"]

    def idx(*keys):
        for k in keys:
            for i, x in enumerate(f):
                if k in x:
                    return i
        return None
    i_f = idx("外陸資買賣超股數", "外資買賣超股數")
    i_t = idx("投信買賣超股數")
    i_d = idx("自營商買賣超股數")
    return {r[0].strip(): [num(r[i_f]) if i_f is not None else None, num(r[i_t]) if i_t is not None else None,
                           num(r[i_d]) if i_d is not None else None] for r in data}


def margin(d):
    j = get([f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d}&selectType=ALL&response=json",
             f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={d}&selectType=ALL"])
    if j is None:
        return None
    for t in j.get("tables") or []:
        if "彙總" in str(t.get("title", "")) and t.get("data"):
            f = t["fields"]
            i = f.index("今日餘額")  # 第一個「今日餘額」是融資
            j2 = [k for k, x in enumerate(f) if x == "今日餘額"]
            return {r[0].strip(): [num(r[i]), num(r[j2[1]]) if len(j2) > 1 else None] for r in t["data"]}
    if j.get("data"):
        return {r[0].strip(): [num(r[6]), num(r[12])] for r in j["data"]}
    return {}


def qfii(d):
    j = get([f"https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date={d}&selectType=ALLBUT0999&response=json",
             f"https://www.twse.com.tw/fund/MI_QFIIS?response=json&date={d}&selectType=ALLBUT0999"])
    if j is None:
        return None
    f = j.get("fields") or []
    data = j.get("data") or []
    if not f and j.get("tables"):
        f, data = j["tables"][0]["fields"], j["tables"][0]["data"]
    i = next((k for k, x in enumerate(f) if "持股比率" in x and "全體" in x), None)
    if i is None:
        i = next((k for k, x in enumerate(f) if "持股比率" in x), None)
    k = next((n for n, x in enumerate(f) if x.strip() == "發行股數"), None)
    return {r[0].strip(): [num(r[i]), num(r[k]) if k is not None else None] for r in data} if i is not None else {}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bm = json.loads((DATA / "research" / "bottom_multi.json").read_text(encoding="utf-8"))
    sw = [x for x in bm["swings"]["^TWII"]["list"] if x["drop"] <= -15 and x["trough"] >= "2012-06-01"]
    tw = [r[0] for r in json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]]
    jobs = []
    for e in sw:
        t = tw.index(e["trough"])
        days = [tw[k] for k in range(t - 9, t + 6) if k < len(tw)]
        for d in days + [e["peak"]] + [tw[k] for k in (t + 20, t + 60) if k < len(tw)]:
            jobs.append(("q", d))
        for d in days:
            jobs.append(("t", d))
        jobs += [("m", e["peak"]), ("m", e["trough"]), ("f", e["trough"])]
    fn = {"q": quotes, "t": t86, "m": margin, "f": qfii}
    seen = set()
    for kind, d in jobs:
        key = f"{kind}_{d.replace('-', '')}"
        p = OUT / f"{key}.json"
        old = kind == "f" and p.exists() and p.read_text(encoding="utf-8")[:300].find("[") < 0  # 舊格式沒有發行股數，重抓
        if key in seen or (p.exists() and p.stat().st_size > 100 and not old):
            seen.add(key)
            continue
        seen.add(key)
        v = fn[kind](d.replace("-", ""))
        if v:
            p.write_text(json.dumps(v, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{key}：{len(v) if v else v}", flush=True)
        time.sleep(4)
    (OUT / "episodes.json").write_text(json.dumps(sw, ensure_ascii=False), encoding="utf-8")
    print(f"{len(sw)} 波：" + "、".join(f"{e['trough']}（{e['drop']}%）" for e in sw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
