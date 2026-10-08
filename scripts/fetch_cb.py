#!/usr/bin/env python3
"""
可轉債（CB / EB）從籌備、詢圈／競拍到掛牌的時間軸資料。

來源（皆為公開資料）：
  1. 證券商業同業公會 承銷公告 web.twsa.org.tw/edoc2：「詢價圈購」「競價拍賣」清單
     （圈購／投標期間、溢價率區間、最低承銷價、張數）
  2. 櫃買中心 OpenAPI bond_ISSBD5_data：實際發行日、上櫃日、發行時轉換價、債券簡稱
  3. data/sfb-cb.json（fetch_data.py 抓的金管會申報案件）：送件、生效等籌備階段

輸出 JSS_DATA_DIR/cb/cases.json：{"updatedAt", "cases": [...], "pre": [...]}
"""
from __future__ import annotations

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
OUT = DATA_DIR / "cb" / "cases.json"
TPE = timezone(timedelta(hours=8))
EDOC = "https://web.twsa.org.tw/edoc2/default.aspx"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

S = requests.Session()
S.headers.update({"User-Agent": UA})


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def iso(s: str) -> str | None:
    m = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s.strip()) if s else None
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    d = re.sub(r"\D", "", s or "")
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else None


def num(s):
    try:
        return float(str(s).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def add_bdays(d: str, n: int) -> str:
    x = date.fromisoformat(d)
    while n > 0:
        x += timedelta(days=1)
        if x.weekday() < 5:
            n -= 1
    return x.isoformat()


def get_json(url):
    for i in range(3):
        try:
            r = S.get(url, timeout=60)
            if r.status_code == 200 and r.text.strip()[:1] in "[{":
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (i + 1))
    return None


# ── 公司名稱 → 代號 ─────────────────────────────────────────
def company_map() -> tuple[dict[str, str], dict[str, str]]:
    full, short = {}, {}
    for url, kc, kn, ks in [
        ("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "公司代號", "公司名稱", "公司簡稱"),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "SecuritiesCompanyCode", "CompanyName", "CompanyAbbreviation"),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R", "SecuritiesCompanyCode", "CompanyName", "CompanyAbbreviation"),
    ]:
        for r in get_json(url) or []:
            c = str(r.get(kc, "")).strip()
            if re.fullmatch(r"\d{4}", c):
                full[str(r.get(kn, "")).strip()] = c
                short[c] = str(r.get(ks, "")).strip()
    # 備援：ETF 頁累積的個股簡稱
    try:
        names = json.loads((DATA_DIR / "etf" / "prices.json").read_text(encoding="utf-8")).get("names", {})
        for c, n in names.items():
            if re.fullmatch(r"\d{4}", c):
                short.setdefault(c, n)
    except (OSError, ValueError):
        pass
    return full, short


def _norm(s: str) -> str:
    for a, b in (("臺", "台"), ("啓", "啟"), ("投資控股", "投控"), ("（", "("), ("）", ")")):
        s = s.replace(a, b)
    return s


def match_code(name: str, full: dict, short: dict) -> str | None:
    name = re.sub(r"\((第.+次|創新板)\)$", "", name.strip())
    if name in full:
        return full[name]
    normed = {_norm(k): v for k, v in full.items()}
    if _norm(name) in normed:
        return normed[_norm(name)]
    m = re.search(r"\(([^()]+)\)", name)  # 'JPP Holding Company Limited(經寶精密控股股份有限公司-KY)'
    base = _norm(re.sub(r"(股份)?有限公司$", "", (m.group(1) if m else name).replace("-KY", "")))
    best = None
    for c, s in short.items():
        s2 = _norm(s.rstrip("*").replace("-KY", "").replace("-創", ""))
        if len(s2) >= 2 and base.startswith(s2) and (best is None or len(s2) > len(short[best])):
            best = c
    return best


# ── 證券商業同業公會承銷公告 ─────────────────────────────────
def edoc_report(report: str, year: int) -> list[list[str]]:
    r = S.get(EDOC, timeout=60)
    hidden = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', r.text))
    data = {**hidden, "__EVENTTARGET": "ctl00$cphMain$rblReportType", "__EVENTARGUMENT": "",
            "ctl00$cphMain$rblReportType": report, "ctl00$cphMain$ddlYear": str(year)}
    t = S.post(EDOC, data=data, headers={"Referer": EDOC}, timeout=90).text
    if year != datetime.now(TPE).year:  # 切換年度要再送一次（年度下拉也會 postback）
        hidden = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', t))
        data = {**hidden, "__EVENTTARGET": "ctl00$cphMain$ddlYear", "__EVENTARGUMENT": "",
                "ctl00$cphMain$rblReportType": report, "ctl00$cphMain$ddlYear": str(year)}
        t = S.post(EDOC, data=data, headers={"Referer": EDOC}, timeout=90).text
    m = re.search(r'id="ctl00_cphMain_gvResult".*?</table>', t, re.S)
    if not m:
        raise RuntimeError(f"{report} {year}：找不到結果表格")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S):
        cells = [re.sub(r"<[^>]+>", "", html.unescape(c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        rows.append(cells)
    return rows


def parse_period(s: str):
    parts = [iso(p) for p in s.replace("～", "~").split("~")]
    return (parts + [None, None])[:2]


def bond_kind(t: str) -> str:
    return "EB" if "交換" in t else "CB"


def edoc_cases(years, full, short) -> list[dict]:
    cases = []
    for year in years:
        for report, method in (("BookBuilding", "詢圈"), ("Auction", "競拍")):
            try:
                rows = edoc_report(report, year)
            except Exception as e:  # noqa: BLE001
                log(f"✗ 承銷公告 {report} {year}：{e}")
                continue
            head = rows[0] if rows else []
            col = lambda k: next((i for i, h in enumerate(head) if k in h), None)  # noqa: E731
            i_sn, i_co, i_lead, i_type = col("序號"), col("發行公司"), col("承銷商"), col("發行性質")
            i_units, i_sale = col("承銷股數"), (col("詢圈銷售") if method == "詢圈" else col("競拍股數"))
            i_period = col("圈購期間") if method == "詢圈" else col("投標期間")
            i_price = col("價格")
            n = 0
            for r in rows[1:]:
                if len(r) < len(head) - 2 or "公司債" not in r[i_type]:
                    continue
                start, end = parse_period(r[i_period])
                price = r[i_price] if i_price is not None else ""
                lo = hi = minp = None
                if method == "詢圈":
                    ps = [num(x) for x in re.findall(r"[\d.]+", price)]
                    lo, hi = (ps + [None, None])[:2] if ps else (None, None)
                else:
                    minp = num(price)
                code = match_code(r[i_co], full, short)
                cases.append({
                    "id": f"{method}-{r[i_sn]}-{year}", "sn": r[i_sn], "method": method, "company": r[i_co],
                    "code": code, "short": short.get(code or "", ""), "lead": re.sub(r"(股份)?有限公司$", "", r[i_lead]),
                    "type": r[i_type], "kind": bond_kind(r[i_type]),
                    "units": num(r[i_units]), "saleUnits": num(r[i_sale]) if i_sale is not None else None,
                    "start": start, "end": end, "premiumLo": lo, "premiumHi": hi, "minPrice": minp,
                })
                n += 1
            log(f"  承銷公告 {report} {year}：{n} 件")
            time.sleep(1)
    # 同一案在清單重複出現時只留一筆
    uniq = {}
    for c in cases:
        uniq[(c["method"], c["company"], c["start"], c["type"])] = c
    return list(uniq.values())


# ── 櫃買中心發行資料 ─────────────────────────────────────────
def issued_bonds() -> list[dict]:
    out = []
    for r in get_json("https://www.tpex.org.tw/openapi/v1/bond_ISSBD5_data") or []:
        code = str(r.get("IssuerCode", "")).strip()
        if not re.fullmatch(r"\d{4}", code) or not r.get("BondCode"):
            continue
        out.append({
            "code": code, "bondCode": str(r["BondCode"]).strip(), "bondName": str(r.get("ShortName", "")).strip(),
            "issueDate": iso(r.get("IssueDate", "")), "listDate": iso(r.get("ListingDate", "")),
            "convPrice": num(r.get("Conversion/ExchangePriceAtIssuance")) or None,
            "amount": num(r.get("IssueAmount")), "maturity": iso(r.get("MaturityDate", "")),
        })
    return out


def link_issues(cases, bonds):
    """詢圈／競拍案配上實際發行的債券：同代號、發行日在截止後 0～45 天內最近的一筆。"""
    used = set()
    for c in sorted(cases, key=lambda c: c["end"] or ""):
        if not c["code"] or not c["end"]:
            continue
        cands = [b for b in bonds if b["code"] == c["code"] and b["bondCode"] not in used and b["issueDate"]
                 and c["end"] <= b["issueDate"] <= add_bdays(c["end"], 30)]
        if cands:
            b = min(cands, key=lambda b: b["issueDate"])
            used.add(b["bondCode"])
            c.update({k: b[k] for k in ("bondCode", "bondName", "issueDate", "listDate", "convPrice")})


def estimate(c):
    """還沒公告的日期依慣例推估：訂價基準日 ≈ 截止後 2 個營業日、掛牌 ≈ 訂價後 7 個營業日。"""
    if not c["end"]:
        return
    c["priceDateEst"] = add_bdays(c["end"], 1 if c["method"] == "競拍" else 2)
    if not c.get("listDate"):
        c["listDateEst"] = add_bdays(c["priceDateEst"], 7)


def pre_stage(cases):
    """金管會申報中／已生效、但還沒進入詢圈或競拍的案子。"""
    try:
        sfb = json.loads((DATA_DIR / "sfb-cb.json").read_text(encoding="utf-8")).get("data", [])
    except (OSError, ValueError):
        return []
    out = []
    for r in sfb:
        if r.get("status") not in ("審查中", "生效") or "海外" in (r.get("cbType") or ""):
            continue
        filed = r.get("filingDate") or ""
        started = any(c["code"] == r.get("code") and (c["start"] or "") >= filed for c in cases)
        if not started:
            out.append({k: r.get(k) for k in ("code", "name", "market", "status", "cbType", "amount",
                                                "filingDate", "effectiveDate", "underwriter")})
    return out


def main():
    today = datetime.now(TPE).date()
    full, short = company_map()
    log(f"公司對照：{len(full)} 筆全名、{len(short)} 筆簡稱")
    cases = edoc_cases([today.year - 1, today.year] if today.month <= 3 else [today.year], full, short)
    if not cases:
        log("✗ 承銷公告沒有資料，保留上次結果")
        return 0
    bonds = issued_bonds()
    log(f"櫃買發行資料：{len(bonds)} 筆")
    link_issues(cases, bonds)
    for c in cases:
        estimate(c)
    cases.sort(key=lambda c: c["start"] or "", reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"),
                               "cases": cases, "pre": pre_stage(cases)},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    nocode = [c["company"] for c in cases if not c["code"]]
    log(f"CB：{len(cases)} 件（對不到代號 {len(nocode)} 件{'：' + '、'.join(nocode[:8]) if nocode else ''}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
