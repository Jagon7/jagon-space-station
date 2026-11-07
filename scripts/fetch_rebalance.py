#!/usr/bin/env python3
"""
ETF 換股預估（0050／0051／0056／00919／00929）需要的公開資料，取代原本從 TEJ 匯出的工作表。

只用官方公開資料，全部有快取、增量抓取；每家來源之間固定間隔，遇到「查詢過於頻繁／FOR SECURITY REASONS」
就停止該來源（不換 UA、不繞過），下次排程再接著補：

  px/<日期>.json        每日收盤行情（含無成交的股票）
                        {代號: [收盤, 成交股數, 成交金額(千元，無條件捨去，同 TEJ), 市場 TSE|OTC, 漲跌（除權息日以參考價計）]}
                        來源：證交所 MI_INDEX（ALLBUT0999）、櫃買中心 afterTrading/dailyQuotes（含定價）
  basic.json            發行股數、產業別、上市日期、市場、變更交易（全額交割）
                        來源：證交所 OpenAPI t187ap03_L、TWT85U；櫃買 OpenAPI mopsfin_t187ap03_O、tpex_cmode
  insider/<YYYY-MM>.json 董監事、經理人、大股東持股合計（%）
                        來源：OpenAPI t187ap11_L、mopsfin_t187ap11_O（依姓名去重後加總 ÷ 發行股數）
  foreign/<日期>.json    外資持股、尚可投資比率、投資上限（FTSE 外資持股上限審核用）
                        來源：證交所 MI_QFIIS、櫃買 insti/qfii
  fin/<YYYY>Q<n>.json    各季（年初至該季累計）淨利、歸屬母公司淨利、EPS、資產、權益、股本
                        來源：公開資訊觀測站 t163sb04／t163sb05（彙總報表）＋ OpenAPI 當季最新財報
                        （財報季每天都有公司新公布，每天重抓 OpenAPI 合併進去）
  div/<YYYY>.json        除權息公告（依股利所屬期間）：公開資訊觀測站 t108sb27
  div_board.json         董事會已決議、還沒除息的股利（上市）：OpenAPI t187ap45_L
  div_board_otc.json     董事會已決議的股利（上櫃，市值 ≥ 50 億＋00919／00929 成分股）：公開資訊觀測站「股利分派情形」
                         t05st09_2 逐家查，每家 3 天重查一次 {代號: {"t": 查詢日, "r": [[代號, 所屬年度, 季別, 現金, 進度, 董事會日, 期間原文]]}}
  pe/<日期>.json         個股本益比（00929 五年平均本益比用）：證交所 BWIBBU_d、櫃買 peQryDate

月營收沿用 fetch_fundamentals.py 的 data/fund/revenue，ETF 持股與規模沿用 fetch_etf.py 的 data/etf。
  daytrade/<日期>.json   當沖成交股數（證交所 TWTB4U、櫃買 intraday/stat）；沒有時沿用 data/strategy/daytrade.json

用法：python scripts/fetch_rebalance.py [--minutes 25] [px basic insider foreign fin div div_board_otc pe]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "rebalance" / "raw"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
TWSE = "https://www.twse.com.tw/"
TPEX = "https://www.tpex.org.tw/"
TWSE_API = "https://openapi.twse.com.tw/v1/"
TPEX_API = "https://www.tpex.org.tw/openapi/v1/"
MOPS = "https://mopsov.twse.com.tw/mops/web/"

PX_DAYS = 760        # 每日行情保留約 25 個月（FTSE 年度流動性看前一年 3 月起、00929 前前次截止日收盤價）
PE_YEARS = 5         # 00929 近 5 年平均本益比
FIN_QUARTERS = 24    # 00929 近 5 年 ROE、00919 近兩年 EPS
DIV_YEARS = 7        # 00929 近 5 年股利（公告年度比所屬年度晚一年，多抓兩年）
GAP = {"twse": 4.0, "tpex": 2.5, "mops": 3.0, "api": 1.0}

S = requests.Session()
S.headers.update({"User-Agent": UA})
DEADLINE = [0.0]
BLOCKED: set[str] = set()   # 本次執行被擋下的來源，之後不再打
_last: dict[str, float] = defaultdict(float)


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
    s = str(v).replace(",", "").replace("%", "").strip()
    if s in ("", "--", "-", "---", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _decode(content: bytes) -> str:
    for enc in ("utf-8", "big5hkscs", "cp950"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", "replace")


def get(src: str, method: str, url: str, **kw):
    """限速＋重試；遇到流量限制頁面就把整個來源標成本次停用（不繞過）。"""
    if src in BLOCKED:
        return None
    for i in range(3):
        wait = GAP[src] - (time.time() - _last[src])
        if wait > 0:
            time.sleep(wait)
        _last[src] = time.time()
        try:
            r = S.request(method, url, timeout=120, **kw)
        except requests.RequestException as e:
            log(f"  {src} 連線失敗（{e.__class__.__name__}），稍後重試")
            time.sleep(10 * (i + 1))
            continue
        text = _decode(r.content)
        if "FOR SECURITY REASONS" in text or "查詢過於頻繁" in text or r.status_code in (403, 429):
            log(f"  ✗ {src} 回應流量限制，本次停止抓 {src}，下次排程再補")
            BLOCKED.add(src)
            return None
        if r.status_code == 200:
            return text
        time.sleep(10 * (i + 1))
    return None


def get_json(src, url, **kw):
    t = get(src, "GET", url, **kw)
    if t is None:
        return None
    try:
        return json.loads(t)
    except ValueError:
        return None


def mops(api: str, data: dict) -> str | None:
    base = {"encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1", "isQuery": "Y"}
    return get("mops", "POST", MOPS + api, data={**base, **data}, headers={"Referer": MOPS + "index"})


def clean(c: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c)).replace("\xa0", " ")).strip()


def tables(page: str):
    for t in re.findall(r"<table[^>]*>.*?</table>", page, re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
        out = []
        for tr in rows:
            out.append(([clean(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", tr, re.S)],
                        [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]))
        yield out


def is_stock(code: str) -> bool:
    return bool(re.fullmatch(r"[1-9]\d{3}", code))


def holidays() -> set[str]:
    return set(read_json(DATA_DIR / "calendar.json", {}).get("holidays", []))


def trading_days(n_days: int) -> list[date]:
    """近 n_days 個日曆天內的平日（扣掉休市日），新到舊。今天 15:00 以前不含今天。"""
    now = datetime.now(TPE)
    d = now.date() if now.hour >= 15 else now.date() - timedelta(days=1)
    hol = holidays()
    out = []
    for i in range(n_days):
        x = d - timedelta(days=i)
        if x.weekday() < 5 and x.isoformat() not in hol:
            out.append(x)
    return out


# ---------------- 每日行情 ----------------

def _twse_px(d: date):
    doc = get_json("twse", TWSE + "rwd/zh/afterTrading/MI_INDEX",
                   params={"date": d.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"})
    if doc is None:
        return None
    if doc.get("stat") != "OK":
        return {}
    out = {}
    for t in doc.get("tables") or []:
        f = t.get("fields") or []
        if "證券代號" not in f or "成交金額" not in f:
            continue
        ic, iv, ia, ip = f.index("證券代號"), f.index("成交股數"), f.index("成交金額"), f.index("收盤價")
        isg, idf = f.index("漲跌(+/-)"), f.index("漲跌價差")
        for r in t.get("data") or []:
            c = str(r[ic]).strip()
            if is_stock(c):
                sign = -1 if "-" in re.sub(r"<[^>]+>", "", str(r[isg])).replace("color:", "") else 1
                diff = num(r[idf])
                out[c] = [num(r[ip]), int(num(r[iv]) or 0), int((num(r[ia]) or 0) // 1000), "TSE",
                          None if diff is None else sign * diff]
    return out


def _tpex_px(d: date):
    # dailyQuotes 含定價交易（跟 TEJ 日成交值一致）；afterTrading/otc 不含定價，會偏低
    doc = get_json("tpex", TPEX + "www/zh-tw/afterTrading/dailyQuotes",
                   params={"date": d.strftime("%Y/%m/%d"), "type": "EW", "response": "json"})
    if doc is None:
        return None
    out = {}
    for t in doc.get("tables") or []:
        f = [x.strip() for x in (t.get("fields") or [])]
        if "代號" not in f:
            continue
        ic = f.index("代號")
        ip = next(i for i, x in enumerate(f) if x.startswith("收盤"))
        iv = next(i for i, x in enumerate(f) if x.startswith("成交股數"))
        ia = next(i for i, x in enumerate(f) if x.startswith("成交金額"))
        ich = next(i for i, x in enumerate(f) if x.startswith("漲跌"))
        for r in t.get("data") or []:
            c = str(r[ic]).strip()
            if is_stock(c):
                out[c] = [num(r[ip]), int(num(r[iv]) or 0), int((num(r[ia]) or 0) // 1000), "OTC", num(r[ich])]
    return out


def px(recent: int | None = None):
    skip = set(read_json(OUT / "px" / "_skip.json", []))
    days = [d for d in trading_days(PX_DAYS) if d.isoformat() not in skip][:recent]
    todo = [d for d in days if not (OUT / "px" / f"{d}.json").exists()]
    log(f"每日行情：缺 {len(todo)} 天")
    for d in todo:
        if late() or {"twse", "tpex"} & BLOCKED:
            break
        a, b = _twse_px(d), _tpex_px(d)
        if a is None or b is None:
            continue
        if not a and not b:
            skip.add(d.isoformat())        # 休市
            continue
        if not a or not b:
            continue                      # 只抓到一邊，下次再補
        write_json(OUT / "px" / f"{d}.json", {**a, **b})
        log(f"  {d}：{len(a)} + {len(b)} 檔")
    write_json(OUT / "px" / "_skip.json", sorted(skip))
    keep = {d.isoformat() for d in trading_days(PX_DAYS + 30)}
    for p in (OUT / "px").glob("20*.json"):
        if p.stem not in keep:
            p.unlink()


# ---------------- 基本資料 ----------------

def basic():
    doc = {}
    a = get_json("api", TWSE_API + "opendata/t187ap03_L") or []
    for x in a:
        c = x.get("公司代號", "").strip()
        if is_stock(c):
            doc[c] = {"n": x.get("公司簡稱", "").strip(), "mk": "TSE", "ind": x.get("產業別", "").strip(),
                      "list": x.get("上市日期", "").strip(), "sh": num(x.get("已發行普通股數或TDR原股發行股數")),
                      "pref": num(x.get("特別股"))}
    b = get_json("api", TPEX_API + "mopsfin_t187ap03_O") or []
    for x in b:
        c = x.get("SecuritiesCompanyCode", "").strip()
        if is_stock(c):
            doc[c] = {"n": x.get("CompanyAbbreviation", "").strip(), "mk": "OTC",
                      "ind": x.get("SecuritiesIndustryCode", "").strip(), "list": x.get("DateOfListing", "").strip(),
                      "sh": num(x.get("IssueShares")), "pref": num(x.get("PreferredStock.shares"))}
    if len(a) < 500 or len(b) < 500:
        log(f"✗ 基本資料不完整（上市 {len(a)}、上櫃 {len(b)}），沿用舊檔")
        return
    alt = set()
    for x in get_json("api", TWSE_API + "exchangeReport/TWT85U") or []:
        alt.add(str(x.get("Code", "")).strip())
    for x in get_json("api", TPEX_API + "tpex_cmode") or []:
        if "Ｙ" in str(x.get("AlteredTrading", "")) or "Y" in str(x.get("AlteredTrading", "")):
            alt.add(str(x.get("SecuritiesCompanyCode", "")).strip())
    for c in doc:
        doc[c]["alt"] = 1 if c in alt else 0
    write_json(OUT / "basic.json", {"date": datetime.now(TPE).date().isoformat(), "d": doc})
    log(f"基本資料：{len(doc)} 檔，變更交易 {len(alt)} 檔")


# ---------------- 董監持股 ----------------

def _insider_rows(src_url: str) -> list:
    for _ in range(3):                      # 檔案很大（10MB），偶爾傳一半斷掉：重試
        rows = get_json("api", src_url)
        if rows and len(rows) > 3000:
            return rows
        time.sleep(20)
    return []


def insider():
    """上市、上櫃分開抓；某一邊抓失敗就沿用上一份檔案裡那一邊的數字（不讓整份只剩一個市場）。"""
    basic = read_json(OUT / "basic.json", {}).get("d", {})
    sh = {c: v["sh"] for c, v in basic.items()}
    prev_files = sorted((OUT / "insider").glob("20*.json"))
    prev = read_json(prev_files[-1], {}) if prev_files else {}
    doc, ym, ok = {}, {}, {}
    for mk, url in (("TSE", TWSE_API + "opendata/t187ap11_L"), ("OTC", TPEX_API + "mopsfin_t187ap11_O")):
        rows = _insider_rows(url)
        ok[mk] = bool(rows)
        by = defaultdict(dict)
        for x in rows:
            c = str(x.get("公司代號", "")).strip()
            name = str(x.get("姓名", "")).strip()
            hold = num(x.get("目前持股")) or 0
            if not is_stock(c) or not name:
                continue
            # 同一人（同一法人）可能同時是董事、經理人、大股東，或一個法人有多位代表人：依姓名去重
            by[c][name] = max(by[c].get(name, 0), hold)
            ym[c] = str(x.get("資料年月", "")).strip()
        if rows:
            doc.update({c: round(sum(v.values()) / sh[c] * 100, 4) for c, v in by.items() if sh.get(c)})
        else:
            log(f"✗ 董監持股（{mk}）抓不到，沿用上一份")
            doc.update({c: v for c, v in prev.items() if basic.get(c, {}).get("mk") == mk})
    if not any(ok.values()) or not ym:
        log("✗ 董監持股兩個市場都抓不到，沿用舊檔")
        return
    roc = max(ym.values())
    tag = f"{int(roc[:-2]) + 1911}-{roc[-2:]}"
    write_json(OUT / "insider" / f"{tag}.json", doc)
    n_tse = sum(1 for c in doc if basic.get(c, {}).get("mk") == "TSE")
    log(f"董監持股 {tag}：{len(doc)} 檔（上市 {n_tse}）")


# ---------------- 外資持股 ----------------

def foreign():
    d = trading_days(10)
    for x in d:
        path = OUT / "foreign" / f"{x}.json"
        if path.exists():
            return
        a = get_json("twse", TWSE + "rwd/zh/fund/MI_QFIIS",
                     params={"date": x.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"})
        b = get_json("tpex", TPEX + "www/zh-tw/insti/qfii", params={"date": x.strftime("%Y/%m/%d"), "response": "json"})
        if not a or a.get("stat") != "OK" or not b:
            continue
        doc = {}
        f = a["fields"]
        for r in a["data"]:
            c = str(r[0]).strip()
            if is_stock(c):
                # [發行股數, 尚可投資比率%, 外資持股比率%, 投資上限比率%]
                doc[c] = [num(r[f.index("發行股數")]), num(r[f.index("外資及陸資尚可投資比率")]),
                          num(r[f.index("全體外資及陸資持股比率")]), num(r[f.index("外資及陸資共用法令投資上限比率")])]
        for t in b.get("tables") or []:
            for r in t.get("data") or []:
                c = str(r[1]).strip()
                if is_stock(c):
                    doc[c] = [num(r[3]), num(r[6]), num(r[7]), num(r[8])]
        write_json(path, doc)
        log(f"外資持股 {x}：{len(doc)} 檔")
        return


# ---------------- 財報 ----------------

def _quarters(n: int) -> list[tuple[int, int]]:
    d = datetime.now(TPE).date()
    y, q = d.year, (d.month - 1) // 3
    if q == 0:
        y, q = y - 1, 4
    out = []
    for _ in range(n):
        out.append((y, q))
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out


def _pick(head, *keys, exclude=()):
    for k in keys:
        for i, h in enumerate(head):
            if k in h and not any(x in h for x in exclude):
                return i
    return None


INC_KEYS = {
    "ni": (("本期淨利", "本期稅後淨利", "淨利（淨損）"), ("歸屬", "綜合", "繼續", "停業", "前")),
    "nip": (("歸屬於母公司業主",), ("綜合",)),
    "eps": (("基本每股盈餘",), ()),
}
BAL_KEYS = {
    "assets": (("資產總計", "資產總額", "資產合計"), ()),
    "eq": (("權益總計", "權益總額", "權益合計"), ("負債及",)),
    "eqp": (("歸屬於母公司業主之權益",), ()),
    "cap": (("股本",), ("待註銷", "預收", "以外")),
}


def _merge_table(doc: dict, head: list, rows: list, keys: dict):
    head = [h.replace(" ", "") for h in head]
    ic = _pick(head, "公司代號", "公司代碼")
    if ic is None:
        return
    idx = {k: _pick(head, *ks, exclude=ex) for k, (ks, ex) in keys.items()}
    for c in rows:
        if len(c) < len(head) or not is_stock(c[ic]):
            continue
        e = doc.setdefault(c[ic], {})
        for k, i in idx.items():
            if i is not None and num(c[i]) is not None:
                e[k] = num(c[i])


def _mops_fin(y: int, q: int) -> dict | None:
    doc = {}
    for mk in ("sii", "otc"):
        for api, keys in (("ajax_t163sb04", INC_KEYS), ("ajax_t163sb05", BAL_KEYS)):
            page = mops(api, {"TYPEK": mk, "year": str(y - 1911), "season": f"{q:02d}"})
            if page is None:
                return None
            for t in tables(page):
                if not t:
                    continue
                head = t[0][0]
                _merge_table(doc, head, [r[1] for r in t[1:]], keys)
    return doc


INC_KEYS_Q = {k + "_q": v for k, v in INC_KEYS.items()}


def _openapi_fin() -> tuple[str, dict]:
    """
    OpenAPI 只有「最新一季」，但每天更新（財報季每天都有新公司）。
    OpenAPI 綜合損益表也是年初至今累計（2026Q3 實測 403 家中 381 家大於 Q2 累計）；沿用欄名 ni_q／nip_q／eps_q，
    public.fin_cum 在彙總表還沒有該季時直接當累計數用。
    """
    doc, tag = {}, None
    inds = ("ci", "basi", "bd", "fh", "ins", "mim")
    for kind, keys in (("06", INC_KEYS_Q), ("07", BAL_KEYS)):
        for ind in inds:
            for base, path in ((TWSE_API, f"opendata/t187ap{kind}_L_{ind}"), (TPEX_API, f"mopsfin_t187ap{kind}_O_{ind}")):
                rows = get_json("api", base + path) or []
                for x in rows:
                    y = str(x.get("年度") or x.get("Year") or "").strip()
                    s = str(x.get("季別") or x.get("Season") or "").strip()
                    if not y or not s:
                        continue
                    t = f"{int(y) + 1911}Q{int(s)}"
                    if tag is None or t > tag:
                        tag = t
                    if t != tag:
                        continue
                    head = list(x.keys())
                    vals = [str(v) for v in x.values()]
                    code_key = "公司代號" if "公司代號" in x else "SecuritiesCompanyCode"
                    head = ["公司代號" if h == code_key else h for h in head]
                    _merge_table(doc, head, [vals], keys)
    return tag, doc


def fin(latest_only: bool = False):
    tag, latest = _openapi_fin()
    if tag:
        path = OUT / "fin" / f"{tag}.json"
        old = read_json(path, {})
        for c, v in latest.items():
            old.setdefault(c, {}).update(v)
        write_json(path, old)
        log(f"財報 {tag}（OpenAPI 最新）：{len(latest)} 家，累計 {len(old)} 家")
    if latest_only:
        return
    for i, (y, q) in enumerate(_quarters(FIN_QUARTERS)):
        path = OUT / "fin" / f"{y}Q{q}.json"
        have = read_json(path, {})
        # 最近兩季：申報期間可能還有公司補件，每週一重抓一次彙總表
        refresh = i < 2 and datetime.now(TPE).weekday() == 0
        if (len(have) > 1500 and not refresh) or late() or "mops" in BLOCKED:
            continue
        doc = _mops_fin(y, q)
        if doc is None:
            continue
        for c, v in have.items():
            doc.setdefault(c, {}).update({k: x for k, x in v.items() if k not in doc.get(c, {})})
        if doc:
            write_json(path, doc)
            log(f"財報 {y}Q{q}（公開資訊觀測站）：{len(doc)} 家")


# ---------------- 股利 ----------------

PERIOD = re.compile(r"(\d+)年(?:度)?")
CN = {"一": 1, "二": 2, "三": 3, "四": 4}


def parse_period(s: str):
    """
    股利所屬期間 → (所屬年度, 'Q1'..'Q4')（TEJ 口徑：上半年放 Q2、下半年與年度放 Q4）。
    認得：'114年'、'114年度'、'115年第1季'、'115年第一季'、'114年上半年(度)'、'前半年'、'下半年'、'後半年'、
          以及日期區間 '115/01/01~115/06/30'（看結束月份）。
    """
    t = str(s).replace(" ", "").replace("\u3000", "")
    m = re.search(r"(\d{2,3})/(\d{1,2})/\d{1,2}\s*[~～-]\s*(\d{2,3})/(\d{1,2})/\d{1,2}", t)
    if m:
        y, em = int(m.group(3)) + 1911, int(m.group(4))
        return y, f"Q{(em - 1) // 3 + 1}"
    m = PERIOD.search(t)
    if not m:
        return None
    y = int(m.group(1)) + 1911
    rest = t[m.end():]
    q = re.search(r"第([一二三四1-4])季", rest)
    if q:
        return y, f"Q{CN.get(q.group(1), q.group(1))}"
    if re.search(r"上半|前半|半年度|上期|前期", rest) and not re.search(r"下半|後半", rest):
        return y, "Q2"
    return y, "Q4"


def roc_date(s: str) -> str | None:
    m = re.match(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", str(s).strip())
    if not m:
        return None
    return f"{int(m.group(1)) + 1911}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


_DIV_DONE: set[int] = set()   # 本次執行已更新的年度（避免重抓）


def div(recent_only: bool = False):
    this = datetime.now(TPE).year
    for y in range(this, this - (1 if recent_only else DIV_YEARS), -1):
        path = OUT / "div" / f"{y}.json"
        if path.exists() and y < this - 1 or late() or "mops" in BLOCKED:
            continue
        if y in _DIV_DONE:
            continue
        doc = []
        ok = True
        for mk in ("sii", "otc"):
            page = mops("ajax_t108sb27", {"TYPEK": mk, "year": str(y - 1911), "qryType": "1"})
            if page is None:
                ok = False
                break
            for t in tables(page):
                for head, c in t:
                    if len(c) < 15 or not is_stock(c[0]):
                        continue
                    p = parse_period(c[2])
                    if not p:
                        continue
                    # 欄位：0 代號 1 名稱 2 股利所屬期間 3 基準日 4 盈餘轉增資配股 5 公積轉增資配股 6 除權交易日
                    #       7 盈餘分配現金股利 8 公積發放現金 9 特別股現金股利 10 除息交易日 11 發放日 … 16 公告日期
                    cash = (num(c[7]) or 0) + (num(c[8]) or 0)
                    stock = (num(c[4]) or 0) + (num(c[5]) or 0)
                    # [代號, 所屬年度, 所屬季別, 現金股利, 股票股利, 除息日, 除權日, 公告日, 股利所屬期間原文]
                    doc.append([c[0], p[0], p[1], cash, stock, roc_date(c[10]), roc_date(c[6]), roc_date(c[16]), c[2]])
        if ok and doc:
            _DIV_DONE.add(y)
            write_json(path, doc)
            log(f"除權息公告 {y}：{len(doc)} 筆")
    board = []
    for x in get_json("api", TWSE_API + "opendata/t187ap45_L") or []:
        p = parse_period(str(x.get("股利年度", "")) + "年" + (
            "" if "年度" in str(x.get("股利所屬年(季)度", "")) else str(x.get("股利所屬年(季)度", ""))))
        c = str(x.get("公司代號", "")).strip()
        if not p or not is_stock(c):
            continue
        cash = sum(num(x.get(k)) or 0 for k in ("股東配發-盈餘分配之現金股利(元/股)", "股東配發-法定盈餘公積發放之現金(元/股)",
                                                 "股東配發-資本公積發放之現金(元/股)"))
        board.append([c, p[0], p[1], cash, str(x.get("決議（擬議）進度", "")), str(x.get("董事會（擬議）股利分派日", ""))])
    # 櫃買 OpenAPI mopsfin_t187ap39_O 停在 2021 年（出表日期 110 年），不能用；上櫃另由 div_board_otc() 逐家查
    if board:
        write_json(OUT / "div_board.json", board)
        log(f"董事會決議股利：{len(board)} 筆")


# ---------------- 上櫃董事會決議股利（股利分派情形，逐家查） ----------------

OTC_BOARD_MIN_CAP = 5e9     # 只查市值 ≥ 50 億的上櫃公司（00929 門檻；00919 市值前 300 大也都在內）
OTC_BOARD_REFRESH = 3       # 每家幾天重查一次（董事會隨時可能決議）
OTC_BOARD_PER_RUN = 100     # 每次最多查幾家（限速 3 秒／次，約 5 分鐘）
OTC_BOARD_SAMPLES = 3       # 每次在 log 印出前幾家的表格欄位，方便核對網頁格式


def _grid(table_html: str) -> list[list[tuple[str, str]]]:
    """HTML 表格展開成格子（處理 rowspan／colspan），每格 (th|td, 文字)。"""
    grid: list[list[tuple[str, str]]] = []
    pending: dict[tuple[int, int], tuple[str, str]] = {}
    for r, tr in enumerate(re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)):
        row: list[tuple[str, str]] = []
        cells = re.findall(r"<(t[hd])([^>]*)>(.*?)</t[hd]>", tr, re.S | re.I)
        it = iter(cells)
        c = 0
        while True:
            while (r, c) in pending:
                row.append(pending.pop((r, c)))
                c += 1
            nxt = next(it, None)
            if nxt is None:
                break
            tag, attrs, body = nxt
            cs = int((re.search(r'colspan\s*=\s*"?(\d+)', attrs, re.I) or [0, 1])[1])
            rs = int((re.search(r'rowspan\s*=\s*"?(\d+)', attrs, re.I) or [0, 1])[1])
            cell = (tag.lower(), clean(body))
            for k in range(cs):
                row.append(cell)
                for dr in range(1, rs):
                    pending[(r + dr, c + k)] = cell
            c += cs
        grid.append(row)
    return grid


def parse_t05st09_2(page: str, code: str, sample: bool = False) -> list | None:
    """
    股利分派情形 → [[代號, 所屬年度, 所屬季別, 現金股利, 決議進度, 董事會日, 股利所屬期間原文], ...]
    欄位用表頭文字找（多層表頭展開後合併），找不到必要欄位回 None（格式變了，不要寫進資料）。
    """
    found_table = False
    out = []
    for t in re.findall(r"<table[^>]*>.*?</table>", page, re.S | re.I):
        g = _grid(t)
        head_rows = [row for row in g if row and all(tag == "th" for tag, _ in row)]
        body_rows = [row for row in g if any(tag == "td" for tag, _ in row)]
        if not head_rows or not body_rows:
            continue
        width = max(len(row) for row in head_rows)
        heads = []
        for j in range(width):
            parts = []
            for row in head_rows:
                if j < len(row) and (not parts or parts[-1] != row[j][1]):
                    parts.append(row[j][1])
            heads.append(re.sub(r"\s+", "", "|".join(parts)))   # 表頭文字中間有換行空白（「盈餘分配 之現金股利」）

        def col(*keys, avoid=()):
            for j, h in enumerate(heads):
                if all(k in h for k in keys) and not any(a in h for a in avoid):
                    return j
            return None

        i_period = col("股利所屬", "期間")
        if i_period is None:
            i_period = col("股利所屬年")
        i_status = col("決議", "進度")
        i_board = col("董事會", "日")
        i_cash = [j for j in (col("盈餘分配之現金股利"), col("法定盈餘公積", "現金"), col("資本公積", "現金"))
                  if j is not None]
        if sample:
            log(f"  [樣本 {code}] 表頭：{heads}")
            for row in body_rows[:2]:
                log(f"  [樣本 {code}] 資料：{[v for _, v in row]}")
        if i_period is None or not i_cash:
            continue
        found_table = True
        for row in body_rows:
            v = [x for _, x in row]
            if len(v) <= max([i_period, *i_cash]):
                continue
            p = parse_period(v[i_period])
            if not p:
                continue
            cash = sum(num(v[j]) or 0 for j in i_cash)
            out.append([code, p[0], p[1], cash,
                        v[i_status] if i_status is not None and i_status < len(v) else "",
                        v[i_board] if i_board is not None and i_board < len(v) else "", v[i_period]])
    if not found_table:
        return [] if "查無" in page or "無符合" in page else None
    return out


def _otc_board_targets() -> list[str]:
    """市值 ≥ 50 億的上櫃公司，加上 00919／00929 現有的上櫃成分股；市值大的先查。"""
    basic = read_json(OUT / "basic.json", {}).get("d", {})
    pxs = sorted((OUT / "px").glob("20*.json"))
    px_last = read_json(pxs[-1], {}) if pxs else {}
    held = set()
    for etf in ("00919", "00929"):
        snaps = read_json(DATA_DIR / "etf" / "holdings" / f"{etf}.json", {}).get("snapshots") or []
        if snaps:
            held |= {h[0] for h in snaps[-1].get("h", [])}
    cap = {}
    for c, b in basic.items():
        if b.get("mk") != "OTC":
            continue
        close = (px_last.get(c) or [None])[0]
        cap[c] = (close or 0) * (b.get("sh") or 0)
    return sorted((c for c, v in cap.items() if v >= OTC_BOARD_MIN_CAP or c in held), key=lambda c: -cap[c])


def div_board_otc():
    path = OUT / "div_board_otc.json"
    doc = read_json(path, {})
    today = datetime.now(TPE).date()
    roc = today.year - 1911
    targets = _otc_board_targets()
    stale = [c for c in targets
             if (today - date.fromisoformat((doc.get(c) or {}).get("t", "2000-01-01"))).days >= OTC_BOARD_REFRESH]
    log(f"上櫃股利分派情形：{len(targets)} 家要追蹤，{len(stale)} 家待更新")
    n = bad = 0
    for c in stale[:OTC_BOARD_PER_RUN]:
        if late() or "mops" in BLOCKED:
            break
        page = mops("ajax_t05st09_2", {"TYPEK": "all", "isnew": "false", "queryName": "co_id", "inpuType": "co_id",
                                         "co_id": c, "date1": str(roc - 1), "date2": str(roc), "qryType": "1"})
        if page is None:
            continue
        rows = parse_t05st09_2(page, c, sample=n < OTC_BOARD_SAMPLES)
        n += 1
        if rows is None:
            bad += 1
            if bad <= OTC_BOARD_SAMPLES:
                log(f"  {c} 找不到股利表，原始內容：{clean(page)[:600]}")
            if bad >= 5 and bad == n:      # 前幾家全都解析不出來：格式不對，停止以免白打
                log("  ✗ 股利分派情形格式無法解析，本次停止")
                break
            continue
        doc[c] = {"t": today.isoformat(), "r": rows}
    if n:
        write_json(path, doc)
    log(f"上櫃股利分派情形：查 {n} 家，解析失敗 {bad} 家，累計 {len(doc)} 家")


# ---------------- 當沖股數（換手量 = 成交量 − 當沖） ----------------

def daytrade():
    """證交所 TWTB4U、櫃買 intraday/stat：近 5 個交易日的當沖成交股數（晚上 7 點前跑，不等 fetch_strategy）。"""
    for d in trading_days(10)[:5]:
        path = OUT / "daytrade" / f"{d}.json"
        if path.exists():
            continue
        doc = {}
        for src, url, params in (
                ("twse", TWSE + "exchangeReport/TWTB4U", {"date": d.strftime("%Y%m%d"), "selectType": "All", "response": "json"}),
                ("tpex", TPEX + "www/zh-tw/intraday/stat", {"type": "Daily", "date": d.strftime("%Y/%m/%d"), "response": "json"})):
            j = get_json(src, url, params=params)
            tbs = (j or {}).get("tables") or []
            if len(tbs) < 2:
                continue
            for r in tbs[1].get("data") or []:
                c = str(r[0]).strip()
                if is_stock(c):
                    doc[c] = int(num(r[3]) or 0)
        if len(doc) > 500:
            write_json(path, doc)
            log(f"當沖 {d}：{len(doc)} 檔")


# ---------------- 本益比 ----------------

def pe():
    skip = set(read_json(OUT / "pe" / "_skip.json", []))
    days = [d for d in trading_days(PE_YEARS * 366 + 10) if d.isoformat() not in skip]
    todo = [d for d in days if not (OUT / "pe" / f"{d}.json").exists()]
    log(f"本益比：缺 {len(todo)} 天")
    for d in todo:
        if late() or {"twse", "tpex"} & BLOCKED:
            break
        a = get_json("twse", TWSE + "rwd/zh/afterTrading/BWIBBU_d",
                     params={"date": d.strftime("%Y%m%d"), "selectType": "ALL", "response": "json"})
        b = get_json("tpex", TPEX + "www/zh-tw/afterTrading/peQryDate",
                     params={"date": d.strftime("%Y/%m/%d"), "response": "json"})
        if a is None or b is None:
            continue
        doc = {}
        if a.get("stat") == "OK":
            f = a.get("fields") or []
            ic, ip = f.index("證券代號"), f.index("本益比")
            for r in a.get("data") or []:
                if is_stock(str(r[ic]).strip()):
                    doc[str(r[ic]).strip()] = num(r[ip])
        for t in b.get("tables") or []:
            for r in t.get("data") or []:
                if is_stock(str(r[0]).strip()):
                    doc[str(r[0]).strip()] = num(r[2])
        if not doc:
            skip.add(d.isoformat())
            continue
        write_json(OUT / "pe" / f"{d}.json", doc)
    write_json(OUT / "pe" / "_skip.json", sorted(skip))


# 先抓「今天」要用的（晚上 7 點要出結果），剩下的時間再補歷史資料
JOBS = {
    "basic": basic, "insider": insider,
    "px_today": lambda: px(recent=5), "daytrade": daytrade, "foreign": foreign,
    "fin_today": lambda: fin(latest_only=True), "div_today": lambda: div(recent_only=True),
    "div_board_otc": div_board_otc,
    "px": px, "fin": fin, "div": div, "pe": pe,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=25)
    ap.add_argument("jobs", nargs="*")
    a = ap.parse_args()
    DEADLINE[0] = time.time() + a.minutes * 60
    for name in a.jobs or list(JOBS):
        try:
            JOBS[name]()
        except Exception as e:  # 單一來源失敗不影響其他
            log(f"✗ {name}：{e.__class__.__name__} {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
