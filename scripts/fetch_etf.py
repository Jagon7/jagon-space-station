#!/usr/bin/env python3
"""
抓台股 ETF 每日持股、全體 ETF 規模（AUM）與收盤價，累積成歷史。

用法：
    python scripts/fetch_etf.py                 # 全部
    python scripts/fetch_etf.py 0050 00981A     # 只抓指定 ETF
    python scripts/fetch_etf.py --issuer ctbc   # 只抓某家投信
    python scripts/fetch_etf.py --no-holdings   # 只更新 AUM 與收盤價
    python scripts/fetch_etf.py --before 2026-10-08   # 補抓該日以前最近一份（僅支援查日期的投信）

輸出（JSS_DATA_DIR，預設 ./data）：
    etf/holdings/<代號>.json   每檔最近 KEEP_SNAPSHOTS 份持股
    etf/aum.json               全體上市櫃 ETF 每日規模（最近 KEEP_DAYS 天）
    etf/prices.json            個股每日收盤價與名稱（最近 KEEP_DAYS 天）
    etf/status.json            本次各 ETF 抓取結果
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import etf_sources as S  # noqa: E402

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
ETF_DIR = DATA_DIR / "etf"
KEEP_SNAPSHOTS = 30
KEEP_DAYS = 30
MIN_HOLDINGS = 5

# (代號, 名稱, 投信, 類型 passive/active)。凱基、玉山靠名稱對應內部代碼，名稱用交易所簡稱。
ETF_LIST = [
    # 市值型 / 高股息 / 主題
    ("0050", "元大台灣50", "yuanta", "passive"),
    ("0056", "元大高股息", "yuanta", "passive"),
    ("00713", "元大台灣高息低波", "yuanta", "passive"),
    ("00850", "元大臺灣ESG永續", "yuanta", "passive"),
    ("00940", "元大台灣價值高息", "yuanta", "passive"),
    ("0051", "元大中型100", "yuanta", "passive"),
    ("0053", "元大電子", "yuanta", "passive"),
    ("0055", "元大MSCI金融", "yuanta", "passive"),
    ("006201", "元大富櫃50", "yuanta", "passive"),
    ("006203", "元大MSCI台灣", "yuanta", "passive"),
    ("006208", "富邦台50", "fubon", "passive"),
    ("0052", "富邦科技", "fubon", "passive"),
    ("0057", "富邦摩台", "fubon", "passive"),
    ("00692", "富邦公司治理", "fubon", "passive"),
    ("00730", "富邦臺灣優質高息", "fubon", "passive"),
    ("00733", "富邦臺灣中小", "fubon", "passive"),
    ("00892", "富邦台灣半導體", "fubon", "passive"),
    ("00900", "富邦特選高股息30", "fubon", "passive"),
    ("009802", "富邦旗艦50", "fubon", "passive"),
    ("009809", "富邦淨零ESG50", "fubon", "passive"),
    ("00878", "國泰永續高股息", "cathay", "passive"),
    ("00881", "國泰台灣科技龍頭", "cathay", "passive"),
    ("00922", "國泰台灣領袖50", "cathay", "passive"),
    ("00701", "國泰股利精選30", "cathay", "passive"),
    ("00919", "群益台灣精選高息", "capital", "passive"),
    ("00927", "群益半導體收益", "capital", "passive"),
    ("00946", "群益科技高息成長", "capital", "passive"),
    ("00923", "群益台ESG低碳50", "capital", "passive"),
    ("00929", "復華台灣科技優息", "fuhhwa", "passive"),
    ("00731", "復華富時高息低波", "fuhhwa", "passive"),
    ("00891", "中信關鍵半導體", "ctbc", "passive"),
    ("00896", "中信綠能及電動車", "ctbc", "passive"),
    ("00934", "中信成長高股息", "ctbc", "passive"),
    ("00894", "中信小資高價30", "ctbc", "passive"),
    ("00912", "中信臺灣智慧50", "ctbc", "passive"),
    ("00928", "中信上櫃ESG 30", "ctbc", "passive"),
    ("00915", "凱基優選高股息30", "kgi", "passive"),
    ("009816", "凱基台灣TOP50", "kgi", "passive"),
    ("00952", "凱基台灣AI50", "kgi", "passive"),
    ("00938", "凱基優選30", "kgi", "passive"),
    ("00935", "野村臺灣新科技50", "nomura", "passive"),
    ("00944", "野村趨勢動能高息", "nomura", "passive"),
    ("00939", "統一台灣高息動能", "president", "passive"),
    ("00947", "台新臺灣IC設計", "taishin", "passive"),
    ("00904", "台新臺灣半導體30", "taishin", "passive"),
    ("00936", "台新永續高息中小", "taishin", "passive"),
    ("00962", "台新AI優息動能", "taishin", "passive"),
    ("00930", "永豐ESG低碳高息", "sinopac", "passive"),
    ("00901", "永豐智能車供應鏈", "sinopac", "passive"),
    ("00907", "永豐優息存股", "sinopac", "passive"),
    ("006204", "永豐臺灣加權", "sinopac", "passive"),
    ("00888", "永豐台灣ESG", "sinopac", "passive"),
    ("00728", "第一金工業30", "firstsec", "passive"),
    ("00918", "大華優利高填息30", "uob", "passive"),
    ("00961", "FT臺灣永續高息", "franklin", "passive"),
    ("00905", "FT臺灣Smart", "franklin", "passive"),
    ("009803", "玉山市值動能50", "esun", "passive"),
    ("009804", "聯邦台精彩50", "union", "passive"),
    ("009808", "華南永昌優選50", "hnitc", "passive"),
    # 主動式
    ("00400A", "主動國泰動能高息", "cathay", "active"),
    ("00401A", "主動摩根台灣鑫收", "jpmorgan", "active"),
    ("00402A", "主動安聯美國科技", "allianz", "active"),
    ("00403A", "主動統一升級50", "president", "active"),
    ("00404A", "主動聯博動能50", "ab", "active"),
    ("00405A", "主動富邦台灣龍耀", "fubon", "active"),
    ("00406A", "主動中信台灣收益", "ctbc", "active"),
    ("00407A", "主動凱基台灣", "kgi", "active"),
    ("00408A", "主動第一金優股息", "firstsec", "active"),
    ("00409A", "主動復華全球50", "fuhhwa", "active"),
    ("00410A", "主動永豐科技趨勢", "sinopac", "active"),
    ("00411A", "主動統一前沿科技", "president", "active"),
    ("00980A", "主動野村臺灣優選", "nomura", "active"),
    ("00981A", "主動統一台股增長", "president", "active"),
    ("00982A", "主動群益台灣強棒", "capital", "active"),
    ("00983A", "主動中信ARK創新", "ctbc", "active"),
    ("00984A", "主動安聯台灣高息", "allianz", "active"),
    ("00985A", "主動野村台灣50", "nomura", "active"),
    ("00986A", "主動台新龍頭成長", "taishin", "active"),
    ("00987A", "主動台新優勢成長", "taishin", "active"),
    ("00988A", "主動統一全球創新", "president", "active"),
    ("00989A", "主動摩根美國科技", "jpmorgan", "active"),
    ("00990A", "主動元大AI新經濟", "yuanta", "active"),
    ("00991A", "主動復華未來50", "fuhhwa", "active"),
    ("00992A", "主動群益科技創新", "capital", "active"),
    ("00993A", "主動安聯台灣", "allianz", "active"),
    ("00994A", "主動第一金台股優", "firstsec", "active"),
    ("00995A", "主動中信台灣卓越", "ctbc", "active"),
    ("00997A", "主動群益美國增長", "capital", "active"),
    ("00998A", "主動復華金融股息", "fuhhwa", "active"),
    ("00999A", "主動野村臺灣高息", "nomura", "active"),
]


def log(msg: str):
    print(f"[{datetime.now(S.TPE):%H:%M:%S}] {msg}", flush=True)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


# ── 持股 ─────────────────────────────────────────────────────
def fetch_one(code, name, issuer, start=None):
    fn = S.SOURCES[issuer][1]
    last = None
    for attempt in range(2):
        try:
            s = fn(code, name, start=start) if start else fn(code, name)
            if len(s["holdings"]) < MIN_HOLDINGS:
                raise S.SourceError(f"只抓到 {len(s['holdings'])} 檔，疑似不完整")
            return s, None
        except Exception as e:  # noqa: BLE001  單檔失敗不影響其他
            last = e
            time.sleep(2 + attempt * 3)
    return None, f"{type(last).__name__}: {last}"


def save_snapshot(code, name, issuer, kind, snap):
    path = ETF_DIR / "holdings" / f"{code}.json"
    doc = read_json(path, {})
    snaps = {s["date"]: s for s in doc.get("snapshots", [])}
    snaps[snap["date"]] = {
        "date": snap["date"], "aum": snap["aum"], "units": snap["units"], "nav": snap["nav"],
        "h": [[h["code"], h["name"], h["shares"], h["weight"]] for h in snap["holdings"]],
    }
    keep = sorted(snaps.values(), key=lambda s: s["date"])[-KEEP_SNAPSHOTS:]
    write_json(path, {"code": code, "name": name, "issuer": S.SOURCES[issuer][0], "kind": kind, "snapshots": keep})


def fetch_holdings(targets, start=None):
    by_issuer = defaultdict(list)
    for t in targets:
        by_issuer[t[2]].append(t)

    status = read_json(ETF_DIR / "status.json", {}).get("etfs", {})

    def run_issuer(items):
        out = []
        for code, name, issuer, kind in items:  # 同一家依序抓，避免被擋
            snap, err = fetch_one(code, name, issuer, start)
            out.append((code, name, issuer, kind, snap, err))
        return out

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [r for batch in pool.map(run_issuer, by_issuer.values()) for r in batch]

    ok = 0
    now = datetime.now(S.TPE).isoformat(timespec="seconds")
    for code, name, issuer, kind, snap, err in results:
        prev = status.get(code, {})
        if snap:
            save_snapshot(code, name, issuer, kind, snap)
            ok += 1
            status[code] = {"ok": True, "date": snap["date"], "n": len(snap["holdings"]),
                            "checkedAt": now, "lastOk": now, "error": None}
            log(f"  ✓ {code} {name}：{snap['date']} {len(snap['holdings'])} 檔")
        else:
            status[code] = {**prev, "ok": False, "checkedAt": now, "error": err}
            log(f"  ✗ {code} {name}：{err}")
    if not start:  # 補抓歷史不動「最新狀態」
        write_json(ETF_DIR / "status.json", {"updatedAt": now, "etfs": status})
    log(f"持股：{ok}/{len(results)} 檔成功")
    return ok


# ── 收盤價（證交所 + 櫃買）──────────────────────────────────
HEADERS = {"User-Agent": S.UA, "Accept": "application/json"}


def _get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60, **kw)
            if r.status_code == 200 and r.text.strip()[:1] in "[{":
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (i + 1))
    return None


def _keep_code(c: str) -> bool:
    """只留股票與 ETF（排除權證、債券等），控制檔案大小。"""
    import re
    return bool(re.fullmatch(r"\d{4}|00\d{2,4}[A-Z]?", c))


def fetch_prices():
    doc = read_json(ETF_DIR / "prices.json", {"names": {}, "days": {}})
    closes, names, day = {}, {}, None
    twse = _get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL") or []
    for r in twse:
        c, p = str(r.get("Code", "")).strip(), S.to_num(r.get("ClosingPrice"))
        if _keep_code(c):
            names[c] = str(r.get("Name", "")).strip()
            if p:
                closes[c] = p
        if r.get("Date") and not day:
            day = S.to_iso(r["Date"])
    tpex = _get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes") or []
    for r in tpex:
        c, p = str(r.get("SecuritiesCompanyCode", "")).strip(), S.to_num(r.get("Close"))
        if _keep_code(c):
            names[c] = str(r.get("CompanyName", "")).strip()
            if p:
                closes[c] = p
        if r.get("Date") and not day:
            day = S.to_iso(r["Date"])
    if not closes:
        log("收盤價：證交所與櫃買都抓不到，略過")
        return
    day = day or datetime.now(S.TPE).date().isoformat()
    doc["names"].update(names)
    doc["days"][day] = closes
    doc["days"] = dict(sorted(doc["days"].items())[-KEEP_DAYS:])
    write_json(ETF_DIR / "prices.json", doc)
    log(f"收盤價：{day} 上市 {len(twse)} / 上櫃 {len(tpex)} 筆")


# ── 全體 ETF 規模（證交所 ETF 淨值揭露）─────────────────────
def fetch_aum():
    payload = None
    for i in range(3):
        try:
            r = requests.get(f"https://mis.twse.com.tw/stock/data/all_etf.txt?_={int(time.time() * 1000)}",
                             headers={**HEADERS, "Referer": "https://mis.twse.com.tw/stock/etf_nav.jsp?ex=tse"},
                             timeout=60)
            payload = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            log(f"AUM：第 {i + 1} 次抓取失敗 {e}")
            time.sleep(5 * (i + 1))
    if not payload:
        return
    types = {}
    for r in _get("https://openapi.twse.com.tw/v1/opendata/t187ap47_L") or []:
        types[str(r.get("基金代號", "")).strip()] = str(r.get("基金類型", ""))
    rows, day = {}, None
    for blk in payload.get("a1") or []:
        for m in blk.get("msgArray") or []:
            code = str(m.get("a") or "").strip()
            units, nav = S.to_num(m.get("c")), S.to_num(m.get("h"))
            if not code or not units or not nav:
                continue
            day = S.to_iso(m.get("i")) if m.get("i") else day
            rows[code] = [str(m.get("b") or "").strip(), units, S.to_num(m.get("d")) or 0.0, nav, S.to_num(m.get("g"))]
    if len(rows) < 50 or not day:
        log(f"AUM：只有 {len(rows)} 筆，資料可能不完整，略過")
        return
    doc = read_json(ETF_DIR / "aum.json", {"types": {}, "days": {}})
    doc["types"].update({k: v for k, v in types.items() if v})
    doc["cols"] = ["name", "units", "unitsChange", "nav", "premium"]
    doc["days"][day] = rows
    doc["days"] = dict(sorted(doc["days"].items())[-KEEP_DAYS:])
    write_json(ETF_DIR / "aum.json", doc)
    log(f"AUM：{day} {len(rows)} 檔")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--issuer")
    ap.add_argument("--no-holdings", action="store_true")
    ap.add_argument("--before", help="YYYY-MM-DD：補抓這天以前（不含）最近一份持股")
    a = ap.parse_args()
    start = None
    if a.before:
        start = datetime.strptime(a.before, "%Y-%m-%d").date() - timedelta(days=1)

    if not a.no_holdings:
        targets = [t for t in ETF_LIST
                   if (not a.codes or t[0] in a.codes) and (not a.issuer or t[2] == a.issuer)
                   and (not start or t[2] in S.DATED_SOURCES)]
        log(f"持股：開始抓 {len(targets)} 檔")
        fetch_holdings(targets, start)
    if not a.codes and not a.issuer and not start:
        fetch_prices()
        fetch_aum()
    return 0


if __name__ == "__main__":
    sys.exit(main())
