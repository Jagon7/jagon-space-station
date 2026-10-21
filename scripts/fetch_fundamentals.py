#!/usr/bin/env python3
"""
基礎情報：月營收、季報（綜合損益）、自結損益、庫藏股、近期事件（除權息、股東會、法說會）。

資料來源：公開資訊觀測站（mopsov 舊版查詢頁，可查指定期間）、證交所／櫃買中心 OpenAPI。
每個項目都有快取：過去的月份／季度抓過就不重抓，只重抓最近一兩期（可能還有公司在補申報）。

輸出 JSS_DATA_DIR/fund/：
  revenue/<YYYY-MM>.json   {代號: [名稱, 產業, 市場, 當月營收, 去年當月, 當月累計, 去年累計, 備註]}  單位：千元
  income/<YYYY>Q<n>.json   {代號: [名稱, 市場, 營收, 毛利, 營業利益, 稅前, 母公司淨利, EPS]}  年初至該季累計，千元
  selfreport/<YYYY-MM>.json、selfreport/<YYYY>Q<n>.json
                           {代號: [名稱, 市場, 當期營業損益, 累計營業損益, 當期稅前, 累計稅前, 說明]}  千元
  buyback.json             [[代號, 名稱, 市場, 董事會日, 目的, 預定股數, 價格下限, 上限, 起, 迄, 完畢, 已買回股數, 平均價, 佔股本%]]
  events.json              {"updatedAt", "exdiv": [...], "agm": [...], "conf": [...]}
用法：python scripts/fetch_fundamentals.py [--minutes 20] [revenue income selfreport buyback events]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "fund"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
OV = "https://mopsov.twse.com.tw/"
MARKETS = (("sii", "上市"), ("otc", "上櫃"))
REV_MONTHS = 37
INCOME_QUARTERS = 13
SELF_MONTHS = 25
SELF_QUARTERS = 9

S = requests.Session()
S.headers.update({"User-Agent": UA})
DEADLINE = [0.0]


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def late() -> bool:
    return time.time() > DEADLINE[0]


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def num(v):
    v = str(v).replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def clean(c: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c)).replace("\xa0", " ")).strip()


def cells(tr: str, tag="td") -> list[str]:
    return [clean(c) for c in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", tr, re.S)]


def fetch(method, url, **kw) -> str:
    for i in range(4):
        try:
            r = S.request(method, url, timeout=90, **kw)
            if r.status_code == 200:
                for enc in ("utf-8", "big5hkscs", "cp950"):
                    try:
                        text = r.content.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    text = r.content.decode("utf-8", "replace")
                if "FOR SECURITY REASONS" not in text and "查詢過於頻繁" not in text:
                    return text
        except requests.RequestException:
            pass
        time.sleep(6 * (i + 1))
    raise RuntimeError(f"抓取失敗 {url}")


def ajax(api: str, data: dict) -> str:
    base = {"encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1", "isQuery": "Y"}
    time.sleep(2)
    return fetch("POST", OV + "mops/web/" + api, data={**base, **data}, headers={"Referer": OV + "mops/web/index"})


def months_back(n: int, lag_days: int = 10) -> list[tuple[int, int]]:
    """最近 n 個「應該已公布」的月份（新到舊）。"""
    d = (datetime.now(TPE) - timedelta(days=lag_days)).date().replace(day=1) - timedelta(days=1)
    out = []
    for _ in range(n):
        out.append((d.year, d.month))
        d = d.replace(day=1) - timedelta(days=1)
    return out


def quarters_back(n: int) -> list[tuple[int, int]]:
    d = datetime.now(TPE).date()
    y, q = d.year, (d.month - 1) // 3  # 本季還沒結束，從上一季開始
    if q == 0:
        y, q = y - 1, 4
    out = []
    for _ in range(n):
        out.append((y, q))
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out


# ---------- 月營收 ----------

def revenue():
    for i, (y, m) in enumerate(months_back(REV_MONTHS)):
        path = OUT / "revenue" / f"{y}-{m:02d}.json"
        if path.exists() and i >= 2 or late():
            continue
        doc = {}
        for mk, label in MARKETS:
            try:
                page = fetch("GET", f"{OV}nas/t21/{mk}/t21sc03_{y - 1911}_{m}_0.html")
            except RuntimeError as e:
                log(f"✗ 月營收 {y}-{m:02d} {mk}：{e}")
                continue
            # 每個產業一張表，表前有「產業別：xxx」
            for ind, body in re.findall(r"產業別：([^<]+)<.*?<table[^>]*>(.*?)</table>\s*</td>", page, re.S):
                for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
                    c = cells(tr)
                    # 代號 名稱 當月 上月 去年當月 …（中間的百分比欄有時少一格）… 當月累計 去年累計 累計增減% 備註
                    if len(c) >= 9 and re.fullmatch(r"\d{4}[A-Z]?", c[0]):
                        note = c[-1] if num(c[-1]) is None and c[-1] != "-" else ""
                        tail = c[:-1] if num(c[-1]) is None else c
                        doc[c[0]] = [c[1], ind.strip(), label, num(c[2]), num(c[4]), num(tail[-3]), num(tail[-2]), note]
            time.sleep(1)
        if len(doc) > 500:
            write_json(path, doc)
            log(f"  月營收 {y}-{m:02d}：{len(doc)} 家")
        else:
            log(f"  月營收 {y}-{m:02d}：只有 {len(doc)} 家，可能還沒公布")


# ---------- 綜合損益（季報） ----------

def _col(head, *keys, exclude=()):
    for k in keys:
        for i, h in enumerate(head):
            if k in h and not any(x in h for x in exclude):
                return i
    return None


def income():
    for i, (y, q) in enumerate(quarters_back(INCOME_QUARTERS)):
        path = OUT / "income" / f"{y}Q{q}.json"
        if path.exists() and i >= 2 or late():
            continue
        doc = {}
        for mk, label in MARKETS:
            try:
                page = ajax("ajax_t163sb04", {"TYPEK": mk, "year": str(y - 1911), "season": f"{q:02d}"})
            except RuntimeError as e:
                log(f"✗ 季報 {y}Q{q} {mk}：{e}")
                continue
            for t in re.findall(r"<table[^>]*hasBorder.*?</table>", page, re.S):
                rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
                if not rows:
                    continue
                head = [h.replace(" ", "") for h in cells(rows[0], "th")]
                ic = _col(head, "公司代號")
                if ic is None:
                    continue
                irev = _col(head, "營業收入", "淨收益", "收益", "收入", exclude=("利息", "以外", "其他", "營業外"))
                igp = _col(head, "營業毛利（毛損）淨額", "營業毛利（毛損）")
                iop = _col(head, "營業利益")
                ipre = _col(head, "稅前")
                inet = _col(head, "歸屬於母公司業主", exclude=("綜合",))
                if inet is None:
                    inet = _col(head, "本期淨利", "本期稅後淨利")
                ieps = _col(head, "基本每股盈餘")
                for tr in rows[1:]:
                    c = cells(tr)
                    if len(c) < len(head) or not re.fullmatch(r"\d{4}[A-Z]?", c[ic]):
                        continue
                    g = lambda j: num(c[j]) if j is not None else None  # noqa: E731
                    doc[c[ic]] = [c[ic + 1], label, g(irev), g(igp), g(iop), g(ipre), g(inet), g(ieps)]
        if len(doc) > 300:
            write_json(path, doc)
            log(f"  季報 {y}Q{q}：{len(doc)} 家")
        else:
            log(f"  季報 {y}Q{q}：只有 {len(doc)} 家，可能還沒公布")


# ---------- 自結損益 ----------

def _selfreport_page(page: str, label: str, doc: dict):
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        c = cells(tr)
        if len(c) >= 6 and re.fullmatch(r"\d{4}[A-Z]?", c[0]):
            doc[c[0]] = [c[1], label, num(c[2]), num(c[3]), num(c[4]), num(c[5]), c[6] if len(c) > 6 else ""]


def selfreport():
    url = "ajax_t138sb01"
    jobs = [(f"{y}-{m:02d}", {"CK2": "1", "YM1": f"{y - 1911}{m:02d}"}) for y, m in months_back(SELF_MONTHS, lag_days=0)]
    jobs += [(f"{y}Q{q}", {"CK2": "3", "YM3": f"{y - 1911}{q:02d}"}) for y, q in quarters_back(SELF_QUARTERS)]
    recent = {jobs[0][0], jobs[1][0], f"{quarters_back(1)[0][0]}Q{quarters_back(1)[0][1]}"}
    for key, params in jobs:
        path = OUT / "selfreport" / f"{key}.json"
        if path.exists() and key not in recent or late():
            continue
        doc = {}
        for ck1, label in (("1", "上市"), ("2", "上櫃")):
            try:
                page = fetch("POST", OV + "mops/web/" + url, headers={"Referer": OV + "mops/web/t138sb01"},
                             data={"encodeURIComponent": "1", "firstin": "1", "step": "1", "first": "1", "CK1": ck1, **params})
            except RuntimeError as e:
                log(f"✗ 自結 {key} {label}：{e}")
                continue
            _selfreport_page(page, label, doc)
            time.sleep(2)
        write_json(path, doc)
        log(f"  自結損益 {key}：{len(doc)} 家")


# ---------- 庫藏股 ----------

def buyback():
    path = OUT / "buyback.json"
    old = {(r[0], r[3]): r for r in read_json(path, [])}
    today = datetime.now(TPE).date()
    # 過去兩年，每 3 個月一段；已有資料時只重抓最近 9 個月（看執行進度）
    spans, end = [], today
    for _ in range(8 if not old else 3):
        start = end - timedelta(days=90)
        spans.append((start, end))
        end = start - timedelta(days=1)
    roc = lambda d: f"{d.year - 1911}{d.month:02d}{d.day:02d}"  # noqa: E731
    for a, b in spans:
        if late():
            break
        for mk, label in MARKETS:
            try:
                page = ajax("ajax_t35sc09", {"TYPEK": mk, "d1": roc(a), "d2": roc(b), "RD": "1"})
            except RuntimeError as e:
                log(f"✗ 庫藏股 {a}~{b} {mk}：{e}")
                continue
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
                c = cells(tr)
                if len(c) >= 19 and re.fullmatch(r"\d+", c[0]) and re.fullmatch(r"\d{4}[A-Z]?", c[1]):
                    old[(c[1], c[3])] = [c[1], c[2], label, c[3], c[4], num(c[6]), num(c[7]), num(c[8]), c[9], c[10],
                                         c[11], num(c[13]), num(c[17]), num(c[18])]
    rows = sorted(old.values(), key=lambda r: r[3], reverse=True)
    write_json(path, rows)
    log(f"  庫藏股：{len(rows)} 筆")


# ---------- 近期事件 ----------

def roc_date(s: str) -> str | None:
    m = re.match(r"(\d{2,3})[/年](\d{1,2})[/月](\d{1,2})", s.strip())
    if m:
        return f"{int(m.group(1)) + 1911}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(\d{3})(\d{2})(\d{2})$", s.strip())
    return f"{int(m.group(1)) + 1911}-{m.group(2)}-{m.group(3)}" if m else None


def events():
    path = OUT / "events.json"
    old = read_json(path, {})
    today = datetime.now(TPE).date().isoformat()
    keep_from = (datetime.now(TPE).date() - timedelta(days=45)).isoformat()
    out = {"exdiv": {}, "agm": {}, "conf": {}}
    for k in out:  # 保留近 45 天已過的事件
        for r in old.get(k, []):
            if r[0] >= keep_from:
                out[k][(r[0], r[1])] = r

    # 除權息預告：[日期, 代號, 名稱, 市場, 權/息, 現金股利, 配股率]
    try:
        d = json.loads(fetch("GET", "https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json"))
        for r in d.get("data", []):
            dt = roc_date(r[0])
            if dt and re.fullmatch(r"\d{4}[A-Z]?", r[1]):
                out["exdiv"][(dt, r[1])] = [dt, r[1], r[2], "上市", r[3], num(clean(r[7])), num(r[4])]
    except (RuntimeError, ValueError) as e:
        log(f"✗ 上市除權息：{e}")
    try:
        d = json.loads(fetch("GET", "https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost"))
        for r in d:
            dt = roc_date(str(r.get("ExRrightsExDividendDate") or r.get("ExDividendDate") or ""))
            code = str(r.get("SecuritiesCompanyCode", "")).strip()
            if dt and re.fullmatch(r"\d{4}[A-Z]?", code):
                cash = num(r.get("CashDividend") or r.get("CashDividendPerShare") or "")
                stock = num(r.get("StockDividendRatio") or r.get("EarningsDistributionRatio") or "")
                kind = str(r.get("ExRightsExDividend") or r.get("Type") or ("息" if cash else "權"))
                out["exdiv"][(dt, code)] = [dt, code, str(r.get("CompanyName", "")).strip(), "上櫃", kind, cash, stock]
    except (RuntimeError, ValueError) as e:
        log(f"✗ 上櫃除權息：{e}")

    # 股東會：[日期, 代號, 名稱, 市場, 常會/臨時會, 地點]
    for url, label in (("https://openapi.twse.com.tw/v1/opendata/t187ap41_L", "上市"),
                       ("https://www.tpex.org.tw/openapi/v1/t187ap41_O", "上櫃")):
        try:
            for r in json.loads(fetch("GET", url)):
                vals = {k: str(v) for k, v in r.items()}
                dkey = next((k for k in vals if "股東會日期" in k or "開會日期" in k), None)
                code = (vals.get("公司代號") or vals.get("SecuritiesCompanyCode") or "").strip()
                dt = roc_date(vals.get(dkey, "")) if dkey else None
                if dt and dt >= today and re.fullmatch(r"\d{4}[A-Z]?", code):
                    kind = next((v for k, v in vals.items() if "常會" in k or "股東會類別" in k or "臨時" in k), "")
                    place = next((v for k, v in vals.items() if "地點" in k), "")
                    out["agm"][(dt, code)] = [dt, code, (vals.get("公司名稱") or vals.get("CompanyName") or "").strip(), label, kind, place]
        except (RuntimeError, ValueError) as e:
            log(f"✗ 股東會 {label}：{e}")

    # 法說會：上個月、本月與下個月 [日期, 代號, 名稱, 市場, 時間, 地點, 摘要, 中文簡報, 英文簡報]
    now = datetime.now(TPE).date()
    prev_m = now.replace(day=1) - timedelta(days=1)
    next_m = now.replace(day=28) + timedelta(days=5)
    for y, m in ((prev_m.year, prev_m.month), (now.year, now.month), (next_m.year, next_m.month)):
        for mk, label in MARKETS:
            try:
                page = ajax("ajax_t100sb02_1", {"TYPEK": mk, "year": str(y - 1911), "month": f"{m:02d}"})
            except RuntimeError as e:
                log(f"✗ 法說會 {y}-{m} {mk}：{e}")
                continue
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
                c = cells(tr)
                if len(c) >= 6 and re.fullmatch(r"\d{4}[A-Z]?", c[0]):
                    dt = roc_date(c[2])
                    if dt:
                        # 簡報檔：列裡的 .pdf 連結（href 或 window.open），第一個中文、第二個英文
                        pdfs = re.findall(r"""(?:href=|open\()\s*['"]([^'"]+?\.pdf)""", tr, re.I)
                        pdfs = [u if u.startswith("http") else OV.rstrip("/") + "/" + u.lstrip("/") for u in pdfs]
                        out["conf"][(dt, c[0])] = [dt, c[0], c[1], label, c[3], c[4][:60], c[5][:300],
                                                   pdfs[0] if pdfs else None, pdfs[1] if len(pdfs) > 1 else None]
    doc = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes")}
    for k, v in out.items():
        doc[k] = sorted(v.values())
    write_json(path, doc)
    log(f"  事件：除權息 {len(doc['exdiv'])}、股東會 {len(doc['agm'])}、法說會 {len(doc['conf'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*", default=["revenue", "income", "selfreport", "buyback", "events"])
    ap.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args()
    DEADLINE[0] = time.time() + a.minutes * 60
    for p in a.parts:
        log(f"── {p}")
        try:
            globals()[p]()
        except Exception as e:  # noqa: BLE001  單一項目失敗不影響其他
            log(f"✗ {p} 失敗：{e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
