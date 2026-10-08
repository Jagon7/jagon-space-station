"""
上市（證交所）＋上櫃（櫃買中心）當日收盤行情，含個股與 ETF。

fetch_quotes() → (交易日 'YYYY-MM-DD' | None, [Quote])
Quote = {"code", "name", "market": "上市"|"上櫃", "close", "change", "changePct", "volume"(張), "value"(元)}

證交所 openapi 的 STOCK_DAY_ALL 要隔天才更新，這裡用 www.twse.com.tw 的當日 CSV；
CSV 沒有日期欄，交易日以櫃買資料的 Date 為準（兩邊同一天收盤後更新）。
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import datetime, timedelta, timezone

import requests

TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
CODE_RE = re.compile(r"\d{4}|00\d{2,4}[A-Z]?")  # 股票與 ETF；排除權證、債券、特別股


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _get(url, as_json=True):
    for i in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            if r.status_code == 200:
                if not as_json:
                    r.encoding = "utf-8"
                    return r.text
                if r.text.strip()[:1] in "[{":
                    return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (i + 1))
    return None


def _quote(code, name, market, close, change, volume_shares, value):
    pct = None
    if close and change is not None and close - change > 0:
        pct = round(change / (close - change) * 100, 2)
    return {"code": code, "name": name.strip(), "market": market, "close": close, "change": change,
            "changePct": pct, "volume": round((volume_shares or 0) / 1000), "value": value or 0}


def fetch_twse() -> list[dict]:
    # 這個端點不論 response 參數一律回 CSV
    text = _get("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json", as_json=False) or ""
    lines = text.splitlines()
    head = next((i for i, ln in enumerate(lines) if "證券代號" in ln), None)
    out = []
    if head is None:
        return out
    for row in csv.DictReader(io.StringIO("\n".join(lines[head:]))):
        code = (row.get("證券代號") or "").strip().lstrip("=").strip('"')
        if not CODE_RE.fullmatch(code):
            continue
        close = _num(row.get("收盤價"))
        if not close:
            continue
        chg = _num(row.get("漲跌價差"))
        out.append(_quote(code, row.get("證券名稱") or "", "上市", close, chg,
                          _num(row.get("成交股數")), _num(row.get("成交金額"))))
    return out


def fetch_tpex() -> tuple[str | None, list[dict]]:
    data = _get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes") or []
    out, day = [], None
    for r in data:
        code = str(r.get("SecuritiesCompanyCode", "")).strip()
        if not CODE_RE.fullmatch(code):
            continue
        close = _num(r.get("Close"))
        if not close:
            continue
        if r.get("Date") and not day:
            d = re.sub(r"\D", "", str(r["Date"]))
            if len(d) == 7:
                day = f"{int(d[:3]) + 1911}-{d[3:5]}-{d[5:]}"
        out.append(_quote(code, r.get("CompanyName") or "", "上櫃", close, _num(r.get("Change")),
                          _num(r.get("TradingShares")), _num(r.get("TransactionAmount"))))
    return day, out


def guess_trade_day() -> str:
    """櫃買沒給日期時的備援：14:00 前視為前一個平日。"""
    now = datetime.now(TPE)
    d = now.date() if now.hour >= 14 else now.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def fetch_quotes() -> tuple[str | None, list[dict]]:
    twse = fetch_twse()
    day, tpex = fetch_tpex()
    if not twse and not tpex:
        return None, []
    return day or guess_trade_day(), twse + tpex
