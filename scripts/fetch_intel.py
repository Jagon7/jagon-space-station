#!/usr/bin/env python3
"""
券報、法說會要點、國際類股行情 → data/intel/

資料來源：
  鉅亨網台股新聞（api.cnyes.com newslist/category/tw_stock，含內文）：
    - 券商／投顧報告：內文提到「目標價」的段落，解析券商、評等、目標價、前次目標價、亮點
    - FactSet 共識：「Factset 最新調查」快訊（目標價調升／調降、EPS 預估上修／下修）
    - 法說會：〈XX法說〉報導與【XX法說會AI摘要】（摘要全文從新聞頁的 articleBody 取）
  Yahoo Finance chart API：美股指數、個股、原物料日線（給國際類股頁與隔日開盤提醒）

輸出：
  data/intel/reports.json   {"items": [{id, date, code, name, broker, rating, target, prev, kind, title, points, url}]}
  data/intel/confnews.json  {"items": [{id, date, code, name, title, kind, points, body, url}]}
  data/intel/us.json        {"updatedAt", "series": {代號: [[日期, 收盤], ...]}}
  data/intel/week.json      未來兩週國際行事曆：重要經濟數據與央行會議（TradingView economic-calendar）、
                            大型美股財報（Nasdaq earnings calendar），給首頁「下週重點大事」
用法：python scripts/fetch_intel.py [--pages 30] [--backfill-days 0]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "intel"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA})
KEEP_DAYS = 180

# ---------------------------------------------------------------- 美股與國際標的
US_TICKERS = {
    "^SOX": "費城半導體", "^IXIC": "那斯達克", "^GSPC": "S&P 500", "^DJI": "道瓊",
    "TSM": "台積電 ADR", "NVDA": "NVIDIA", "AMD": "AMD", "AVGO": "Broadcom", "MU": "美光",
    "AAPL": "Apple", "TSLA": "Tesla", "SMCI": "Super Micro", "DELL": "Dell", "ASML": "ASML",
    "MSFT": "Microsoft", "GOOGL": "Alphabet", "META": "Meta", "AMZN": "Amazon", "INTC": "Intel",
    "QCOM": "Qualcomm", "ARM": "Arm", "MRVL": "Marvell", "XBI": "生技 ETF", "ZIM": "ZIM 航運",
    "CL=F": "原油", "HG=F": "銅", "GC=F": "黃金", "TWD=X": "美元兌台幣",
    # 貴金屬：白銀、白金期貨，費城金銀類股指數、金蟲指數
    "SI=F": "白銀", "PL=F": "白金", "^XAU": "費城金銀指數", "^HUI": "金蟲指數",
    # 航運：乾散貨運價期貨 ETF、全球航運 ETF、散裝與貨櫃船公司
    "BDRY": "乾散貨運價 ETF", "BOAT": "全球航運 ETF", "SBLK": "Star Bulk", "MATX": "Matson",
}


def log(msg):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def get_json(url, params=None, tries=3):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(3 * (i + 1))
    return None


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


MACRO_COUNTRIES = "US,CN,JP,EU,TW"
EARN_MIN_CAP = 1e11  # 美股財報：市值 ≥ 1000 億美元，或是國際類股頁追蹤的公司


def fetch_week(days: int = 14) -> dict:
    today = datetime.now(TPE).date()
    end = today + timedelta(days=days)
    macro = []
    try:
        r = S.get("https://economic-calendar.tradingview.com/events", timeout=30, headers={"Origin": "https://www.tradingview.com"},
                  params={"from": f"{today}T00:00:00.000Z", "to": f"{end}T00:00:00.000Z", "countries": MACRO_COUNTRIES})
        for e in r.json().get("result", []):
            if (e.get("importance") or 0) < 1:
                continue
            t = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(TPE)
            macro.append({"t": t.isoformat(timespec="minutes"), "country": e.get("country"), "title": e.get("title"),
                          "period": e.get("period"), "forecast": e.get("forecast"), "previous": e.get("previous")})
    except (requests.RequestException, ValueError, KeyError):
        pass
    earn = []
    d = today
    while d <= end:
        if d.weekday() < 5:
            out = subprocess.run(["curl", "-s", "-m", "30", "-A", "Mozilla/5.0", "-H", "Accept: application/json",
                                  f"https://api.nasdaq.com/api/calendar/earnings?date={d}"], capture_output=True, text=True).stdout
            try:
                rows = (json.loads(out).get("data") or {}).get("rows") or []
            except ValueError:
                rows = []
            for x in rows:
                try:
                    cap = float(x.get("marketCap", "").replace("$", "").replace(",", ""))
                except ValueError:
                    cap = 0
                if cap >= EARN_MIN_CAP or x.get("symbol") in US_TICKERS:
                    earn.append({"date": d.isoformat(), "sym": x["symbol"], "name": x.get("name"), "cap": cap,
                                 "time": {"time-pre-market": "盤前", "time-after-hours": "盤後"}.get(x.get("time"), "")})
            time.sleep(0.5)
        d += timedelta(days=1)
    return {"macro": macro, "earnings": earn}


def text_of(content: str) -> str:
    t = html.unescape(content or "")
    t = re.sub(r"<br\s*/?>|</p>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"[ \t　]+", " ", t).strip()


def sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[。！？])|\n+", t) if s and len(s.strip()) > 4]


def closes() -> dict[str, float]:
    files = sorted((DATA_DIR / "daily").glob("20*.json"))
    q = load(files[-1], {}).get("q", {}) if files else {}
    return {c: v[5] for c, v in q.items() if v[5]}


def plausible(code: str, tgt: float | None, px: dict[str, float]) -> bool:
    """目標價和現價差太多（< 0.5 倍或 > 2.5 倍）多半是抓錯股票或把 EPS 當目標價，丟掉"""
    p = px.get(code)
    return bool(tgt) and (not p or 0.5 <= tgt / p <= 2.5)


def stock_names() -> dict[str, str]:
    """名稱→代號（最新一天行情的上市櫃股票）"""
    files = sorted((DATA_DIR / "daily").glob("20*.json"))
    q = load(files[-1], {}).get("q", {}) if files else {}
    return {v[0]: c for c, v in q.items() if re.fullmatch(r"[1-9]\d{3}", c)}


# ---------------------------------------------------------------- 券商報告解析
FOREIGN = ("摩根士丹利", "大摩", "摩根大通", "小摩", "高盛", "美銀證券", "美銀", "美林", "花旗", "瑞銀", "麥格理", "野村",
           "滙豐", "匯豐", "里昂", "瑞穗", "杰富瑞", "德意志", "巴克萊", "大和", "伯恩斯坦", "摩根", "Morgan Stanley",
           "Goldman", "JPMorgan", "Citi", "UBS", "Nomura", "HSBC", "CLSA", "Jefferies", "Bernstein",
           "美系外資", "日系外資", "歐系外資", "港系外資", "陸系外資", "外資")
DOMESTIC = re.compile(r"((?:元大|凱基|富邦|國泰|群益|統一|永豐|兆豐|華南|第一金|台新|玉山|康和|宏遠|元富|日盛|中信|國票|福邦|亞東|合庫|"
                      r"土銀|彰銀|新光|德信|犇亞|大華|華信|宏爺|摩爾|台中銀|致和)(?:投顧|證券|證期|研究部|期貨)?|本土投顧|官股投顧|國內投顧|大咖投顧)")
RATING = re.compile(r"強力買進|逢低買進|買進|加碼|增持|優於大盤|跑贏大盤|中立|持有|區間操作|減碼|劣於大盤|賣出|"
                    r"Outperform|Overweight|Buy|Neutral|Hold|Underweight|Underperform|Sell")
NUM = r"([\d,]+(?:\.\d+)?)"
T_MOVE = re.compile(r"目標價(?:由|從|自)?\s*" + NUM + r"\s*元?\s*(?:大幅|一舉|一口氣)?(?:調升|上調|調高|上修|提高|拉高|調降|下調|下修|降低|調低)?\s*(?:至|到)\s*" + NUM)
T_ONE = re.compile(r"目標價(?:維持|為|訂為|訂在|設為|上看|喊|喊到|調升至|上調至|調高至|上修至|提高至|調降至|下調至|下修至|調低至|至|在)?\s*" + NUM + r"\s*元")
T_ONE2 = re.compile(r"(?:上看|喊|看到|看至)\s*" + NUM + r"\s*元.{0,6}目標價")


def _num(s: str) -> float | None:
    try:
        v = float(s.replace(",", ""))
        return v if 1 <= v <= 100000 else None
    except ValueError:
        return None


GENERIC = {"法人", "外資", "美系外資", "日系外資", "歐系外資", "港系外資", "陸系外資", "本土投顧", "國內投顧", "官股投顧", "大咖投顧"}
ALIAS = {"大摩": "摩根士丹利", "Morgan Stanley": "摩根士丹利", "小摩": "摩根大通", "JPMorgan": "摩根大通", "Goldman": "高盛",
         "美銀證券": "美銀", "美林": "美銀", "Citi": "花旗", "UBS": "瑞銀", "Nomura": "野村", "匯豐": "滙豐", "HSBC": "滙豐",
         "CLSA": "里昂", "Jefferies": "杰富瑞", "Bernstein": "伯恩斯坦"}


def norm_broker(b: str) -> str:
    b = re.sub(r"^(?:外資|美系外資|日系外資|歐系外資|港系外資)(?=.{2,})", "", b)
    b = re.sub(r"(證券|證期)$", "", b) if any(f in b for f in FOREIGN[:22]) else b
    return ALIAS.get(b, b)


def broker_of(sent: str, prev_sents: list[str]) -> str | None:
    b = _broker_of(sent, prev_sents)
    return norm_broker(b) if b else None


def _broker_of(sent: str, prev_sents: list[str]) -> str | None:
    m = re.search(r"([A-Z][A-Za-z&.]+(?: [A-Z][A-Za-z&.]+)* (?:Capital|Securities|Research|Partners))", sent)
    if m:
        return m.group(1)
    for s in [sent] + prev_sents[::-1]:
        m = DOMESTIC.search(s)
        f = next((b for b in FOREIGN if b in s), None)
        if m and (not f or s.find(m.group(1)) < s.find(f)):
            name = m.group(1)
            if name.endswith(("投信",)):
                continue
            return name
        if f:
            return f
    return None


def parse_reports(item: dict, names: dict[str, str], px: dict[str, float] | None = None) -> list[dict]:
    title = item.get("title") or ""
    nid = item["newsId"]
    date = datetime.fromtimestamp(item["publishAt"], TPE).date().isoformat()
    url = f"https://news.cnyes.com/news/id/{nid}"
    out = []

    # FactSet 共識快訊
    m = re.search(r"Factset 最新調查：(.+?)\((\d{4})-TW\)(.*)", title, re.I)
    if m:
        name, code, rest = m.group(1), m.group(2), m.group(3)
        mt = re.search(r"目標價(調升|調降)至" + NUM + r"元，幅度約" + NUM + "%", rest)
        me = re.search(r"EPS預估(上修|下修)至" + r"(-?[\d.]+)" + r"元，預估目標價為" + NUM + "元", rest)
        if mt:
            tgt, pct = _num(mt.group(2)), float(mt.group(3))
            prev = round(tgt / (1 + pct / 100 * (1 if mt.group(1) == "調升" else -1)), 1) if tgt else None
            out.append({"broker": "FactSet 共識", "target": tgt, "prev": prev, "rating": None,
                        "points": [f"市場共識目標價{mt.group(1)} {pct}%"], "code": code, "name": name})
        elif me:
            out.append({"broker": "FactSet 共識", "target": _num(me.group(3)), "prev": None, "rating": None,
                        "points": [f"市場共識 EPS 預估{me.group(1)}至 {me.group(2)} 元"], "code": code, "name": name})
        for o in out:
            o.update({"id": f"{nid}-{o['code']}-fs", "date": date, "kind": "consensus", "title": title, "url": url})
        return out

    body = text_of(item.get("content") or "")
    if "目標價" not in body and "目標價" not in title:
        return []
    mk = [(x.get("code"), x.get("name")) for x in (item.get("market") or []) if re.fullmatch(r"[1-9]\d{3}", str(x.get("code") or ""))]
    sents = sentences(body)
    seen = set()
    for i, s in enumerate(sents):
        if "目標價" not in s:
            continue
        mv, m1, m2 = T_MOVE.search(s), T_ONE.search(s), T_ONE2.search(s)
        prev = tgt = None
        if mv:
            prev, tgt = _num(mv.group(1)), _num(mv.group(2))
        elif m1:
            tgt = _num(m1.group(1))
            if re.search(r"目標價(?:維持|仍為|續維持)", s) or "維持目標價" in s:
                prev = tgt
        elif m2:
            tgt = _num(m2.group(1))
        if not tgt:
            continue
        # 哪一檔：句子裡提到的公司名稱優先，其次是新聞標的的第一檔
        code = name = None
        for c, n in mk:
            if n and n in s:
                code, name = c, n
                break
        if not code:
            for n, c in names.items():
                if len(n) >= 2 and n in s:
                    code, name = c, n
                    break
        if not code and mk:
            code, name = mk[0]
        if not code:
            continue
        if px is not None and not plausible(code, tgt, px):
            continue
        broker = broker_of(s, sents[max(0, i - 2): i]) or "法人"
        key = (code, broker, tgt)
        if key in seen:
            continue
        seen.add(key)
        r = RATING.search(s) or next((RATING.search(x) for x in sents[max(0, i - 1): i + 2] if RATING.search(x)), None)
        # 亮點：同一家券商在文中的其他句子（不含目標價那句），沒有就用目標價前後文
        # 泛稱（外資、法人）在文中太常出現，只取目標價前後文；具名券商才找全文提到它的句子
        pts = [] if broker in GENERIC else [x for x in sents if broker in x and x != s and "目標價" not in x][:3]
        if not pts and broker not in GENERIC:
            pts = [x for x in sents[max(0, i - 2): i + 3] if x != s][:2]
        pts = [x[:110] + ("…" if len(x) > 110 else "") for x in pts]
        out.append({"id": f"{nid}-{code}-{broker}-{tgt}", "date": date, "code": code, "name": name, "broker": broker,
                    "rating": r.group(0) if r else None, "target": tgt, "prev": prev, "kind": "broker",
                    "title": title, "points": [s[:140] + ("…" if len(s) > 140 else "")] + pts, "url": url})
    return out


# ---------------------------------------------------------------- 法說會新聞
def conf_code(title: str, item: dict, names: dict[str, str]) -> tuple[str | None, str | None]:
    """只認「〈XX法說〉」「【XX法說會AI摘要】」或標題裡「XX法說」緊接著公司名的；綜合報導（一次講好幾家）不算"""
    m = re.search(r"[〈【]([^〈〉【】]{2,12}?)法說(?:會AI摘要|會)?[〉】]", title)
    nm = m.group(1).strip() if m else None
    if not nm:
        if re.search(r"要聞|大事|焦點|盤前|盤後|速報|整理|一週|本周|本週|行事曆|懶人包", title):
            return None, None
        for x in item.get("market") or []:
            n = x.get("name") or ""
            if n and re.fullmatch(r"[1-9]\d{3}", str(x.get("code") or "")) and re.search(re.escape(n) + r"(?:第\d季)?(?:線上)?法說", title):
                return x["code"], n
        for n, c in names.items():
            if len(n) >= 2 and re.search(r"(?:^|[〉】》」\s：:])" + re.escape(n) + r"(?:第\d季)?(?:線上)?法說", title):
                return c, n
        return None, None
    if nm in names:
        return names[nm], nm
    for x in item.get("market") or []:
        if re.fullmatch(r"[1-9]\d{3}", str(x.get("code") or "")) and nm in (x.get("name") or ""):
            return x["code"], x.get("name")
    for n, c in names.items():
        if nm.startswith(n) or n.startswith(nm):
            return c, n
    return None, nm


def article_body(nid: int) -> str:
    """新聞頁 JSON-LD 的 articleBody（列表 API 的內文有時被截斷，法說會 AI 摘要要全文）"""
    try:
        r = S.get(f"https://news.cnyes.com/news/id/{nid}", timeout=30)
        m = re.search(r'"articleBody":"((?:[^"\\]|\\.)*)"', r.text)
        return json.loads(f'"{m.group(1)}"') if m else ""
    except (requests.RequestException, ValueError):
        return ""


JUNK = re.compile(r"免責聲明|授權轉載|原文連結|原文出處|獨立判斷|審慎評估|不構成.*建議|僅供參考")


def conf_points(body: str) -> list[str]:
    """AI 摘要是「小標：內容」的條列；一般報導取提到財務／展望的句子"""
    body = re.sub(r"[•●▪]", "", body)
    heads = re.findall(r"(?:^|[。\n\d.、])\s*([^。：:\n]{2,26})[：:]([^。]{6,90}。)", body)
    pts = []
    for h, t in heads:
        h = re.sub(r"^[一二三四五六七八九十]+、.*?(?:詳情|概況|展望|策略|計畫|重點)", "", h.strip()).strip()
        if h and not h.startswith(("Q", "回答", "問")) and not JUNK.search(h + t):
            pts.append(f"{h}：{t.strip()}")
        if len(pts) >= 6:
            break
    if len(pts) >= 3:
        return pts
    keys = ("營收", "毛利率", "獲利", "EPS", "展望", "第四季", "明年", "成長", "指引", "資本支出", "訂單", "產能", "需求")
    extra = [s for s in sentences(body) if any(k in s for k in keys) and not JUNK.search(s)]
    for s in extra:
        if s not in pts:
            pts.append(s[:120] + ("…" if len(s) > 120 else ""))
        if len(pts) >= 5:
            break
    return pts


# ---------------------------------------------------------------- 主流程
def scan_news(pages: int, names, reports: dict, confs: dict, stop_before: float, px: dict | None = None):
    n_new = 0
    for p in range(1, pages + 1):
        d = get_json("https://api.cnyes.com/media/api/v1/newslist/category/tw_stock", {"limit": 30, "page": p})
        items = ((d or {}).get("items") or {}).get("data") or []
        if not items:
            break
        for it in items:
            title = it.get("title") or ""
            for r in parse_reports(it, names, px):
                if r["id"] not in reports:
                    reports[r["id"]] = r
                    n_new += 1
            if "法說" in title and str(it["newsId"]) not in confs:
                code, name = conf_code(title, it, names)
                if not code:
                    continue
                ai = "AI摘要" in title
                body = article_body(it["newsId"]) if ai else text_of(it.get("content") or "")
                if ai:
                    time.sleep(0.5)
                confs[str(it["newsId"])] = {
                    "id": str(it["newsId"]), "date": datetime.fromtimestamp(it["publishAt"], TPE).date().isoformat(),
                    "code": code, "name": name, "title": title, "kind": "ai" if ai else "news",
                    "points": conf_points(body), "body": body[:6000] if ai else "",
                    "url": f"https://news.cnyes.com/news/id/{it['newsId']}"}
        if items[-1]["publishAt"] < stop_before:
            break
        time.sleep(0.6)
    return n_new


GN_QUERIES = ("目標價 外資", "目標價 投顧", "目標價 調升", "目標價 調降", "目標價 喊")
T_TITLE = re.compile(r"目標價[^\d，,。！]{0,8}?" + NUM + r"\s*元|" + NUM + r"\s*元[^\d，。]{0,4}目標價|(?:看|喊到?|上看|升至|調升至|調高至|降至)\s*" + NUM + r"\s*元")


def google_news(names: dict[str, str], reports: dict, px: dict[str, float], days: int = 14) -> int:
    """Google 新聞標題（經濟日報、工商、MoneyDJ、自由…）補足鉅亨沒有的券商報告；只收標題裡有股名與目標價的"""
    n = 0
    recent = {(r["code"], r["target"]) for r in reports.values()}
    by_len = sorted(names.items(), key=lambda kv: -len(kv[0]))
    for q in GN_QUERIES:
        try:
            r = S.get("https://news.google.com/rss/search", params={"q": q + f" when:{days}d", "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}, timeout=30)
        except requests.RequestException:
            continue
        for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            title = html.unescape((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1])
            link = html.unescape((re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1])
            pub = (re.search(r"<pubDate>(.*?)</pubDate>", it) or [None, ""])[1]
            head, _, src = title.rpartition(" - ")
            head = head or title
            m = T_TITLE.search(head)
            # FactSet 快訊鉅亨那邊已經有；「A、B 目標價至 X、Y 元」這種一次多檔的標題對不準，跳過
            if not m or "factset" in head.lower() or re.match(r"\s*元?、\s*[\d,]", head[m.end(): m.end() + 4]):
                continue
            tgt = _num(next(g for g in m.groups() if g))
            # 目標價前面最近的股名（隔太遠或中間出現「這檔」就不算，標題常把目標價講給另一檔）
            code = name = None
            best = None
            for nm, c in by_len:
                if len(nm) < 2:
                    continue
                for mm in re.finditer(re.escape(nm), head):
                    gap = m.start() - mm.end()
                    if 0 <= gap <= 16 and "這" not in head[mm.end(): m.start()] and (best is None or gap < best):
                        best, code, name = gap, c, nm
            if not tgt or not code or (code, tgt) in recent or not plausible(code, tgt, px):
                continue
            try:
                d = datetime.strptime(pub[5:16], "%d %b %Y").date().isoformat()
            except ValueError:
                continue
            broker = broker_of(head, []) or "法人"
            mv = T_MOVE.search(head)
            rid = f"gn-{code}-{broker}-{tgt}"
            if rid in reports:
                continue
            reports[rid] = {"id": rid, "date": d, "code": code, "name": name, "broker": broker,
                            "rating": (RATING.search(head) or [None])[0], "target": tgt, "prev": _num(mv.group(1)) if mv else None,
                            "kind": "broker", "title": head, "points": [f"{head}（{src}）" if src else head], "url": link}
            recent.add((code, tgt))
            n += 1
        time.sleep(1)
    return n


def backfill_conf(days: int, names, confs: dict):
    """用搜尋 API 回補較早的法說會 AI 摘要與〈XX法說〉報導（列表 API 只保留約兩週）"""
    since = time.time() - days * 86400
    for q in ("法說會AI摘要", "法說"):
        for p in range(1, 60):
            d = get_json("https://api.cnyes.com/media/api/v1/search", {"q": q, "limit": 20, "page": p})
            items = ((d or {}).get("items") or {}).get("data") or []
            if not items:
                break
            for it in items:
                title = re.sub(r"</?mark>", "", it.get("title") or "")
                nid = str(it["newsId"])
                if nid in confs or "法說" not in title or "-US" in title or it["publishAt"] < since:
                    continue
                if it.get("categoryName") and it["categoryName"] not in ("台股新聞", "台股"):
                    continue
                code, name = conf_code(title, {}, names)
                if not code:
                    continue
                body = article_body(int(nid))
                time.sleep(0.5)
                if not body:
                    continue
                confs[nid] = {"id": nid, "date": datetime.fromtimestamp(it["publishAt"], TPE).date().isoformat(),
                              "code": code, "name": name, "title": title, "kind": "ai" if "AI摘要" in title else "news",
                              "points": conf_points(body), "body": body[:6000] if "AI摘要" in title else "",
                              "url": f"https://news.cnyes.com/news/id/{nid}"}
            if items[-1]["publishAt"] < since:
                break
            time.sleep(0.6)


# 市場風險監控（Yahoo）：波動率、尾端風險、債市波動、美元、信用 ETF
RISK_TICKERS = {"^VIX": "VIX", "^VVIX": "VVIX", "^VIX9D": "VIX9D", "^VIX3M": "VIX3M", "^SKEW": "SKEW", "^MOVE": "MOVE",
                "DX-Y.NYB": "美元指數", "HYG": "高收益債 ETF", "LQD": "投資級債 ETF", "^TNX": "美 10 年債殖利率"}
# FRED：ICE BofA 高收益／投資級公司債利差（OAS，常用來代替 CDX 信用違約交換利差）、10Y−2Y、聖路易聯準金融壓力指數（週）
FRED_SERIES = {"BAMLH0A0HYM2": "高收益債利差", "BAMLC0A0CM": "投資級債利差", "T10Y2Y": "10Y−2Y 利差", "STLFSI4": "金融壓力指數"}


# 科技廠信用風險：單一公司 CDS 沒有免費資料，用股價、波動度與負債算 CreditGrades「股價隱含 CDS」（build_risk.py）
CDS_TICKERS = {"ORCL": "Oracle", "CRWV": "CoreWeave", "NBIS": "Nebius", "INTC": "Intel", "SMCI": "Super Micro", "DELL": "Dell",
               "MU": "美光", "AMD": "AMD", "AVGO": "Broadcom", "META": "Meta", "MSFT": "Microsoft", "GOOGL": "Alphabet",
               "AMZN": "Amazon", "NVDA": "NVIDIA"}


def fetch_credit(fund: dict):
    """Yahoo 財報時間序列：每季總負債、流通股數（給股價隱含 CDS 用）"""
    now = int(time.time())
    for sym in CDS_TICKERS:
        d = get_json(f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}",
                     {"type": "quarterlyTotalDebt,quarterlyOrdinarySharesNumber", "period1": now - 3 * 365 * 86400, "period2": now + 86400})
        try:
            out = {}
            for r in d["timeseries"]["result"]:
                k = r["meta"]["type"][0]
                out[{"quarterlyTotalDebt": "debt", "quarterlyOrdinarySharesNumber": "shares"}[k]] = \
                    [[x["asOfDate"], x["reportedValue"]["raw"]] for x in (r.get(k) or []) if x]
            if out.get("debt") and out.get("shares"):
                fund[sym] = out
        except (TypeError, KeyError):
            log(f"  ✗ {sym} 財報抓不到")
        time.sleep(0.4)


def fetch_fred(series: dict):
    for sid in FRED_SERIES:
        # FRED 對 Python requests 和瀏覽器 User-Agent 會擋（卡到逾時或斷線），用 curl 預設的 User-Agent 抓
        try:
            text = subprocess.run(["curl", "-sS", "-m", "60", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"],
                                  capture_output=True, text=True, timeout=90).stdout
            rows = []
            for line in text.splitlines()[1:]:
                d, _, v = line.partition(",")
                try:
                    rows.append([d, round(float(v), 4)])
                except ValueError:
                    pass
            if rows:
                series[sid] = rows[-800:]
        except (OSError, subprocess.SubprocessError):
            log(f"  ✗ FRED {sid} 抓不到")
            continue
        if not rows:
            log(f"  ✗ FRED {sid} 抓不到")
        time.sleep(0.5)


def fetch_us(series: dict, tickers=None, rng: str = "1y"):
    for sym in tickers or US_TICKERS:
        d = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}",
                     {"range": rng, "interval": "1d"})
        try:
            res = d["chart"]["result"][0]
            ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
            tz = res["meta"].get("gmtoffset", -14400)
            rows = [[datetime.fromtimestamp(t + tz, timezone.utc).date().isoformat(), round(c, 4)] for t, c in zip(ts, cl) if c]
            # 盤中抓到的最後一筆不是收盤：交易時段還沒結束就不收
            meta = res["meta"]
            per = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
            if rows and per and per.get("start", 0) <= time.time() < per.get("end", 0):
                rows = rows[:-1]
            if rows:
                series[sym] = rows
        except (TypeError, KeyError, IndexError):
            log(f"  ✗ {sym} 抓不到")
        time.sleep(0.4)


def fetch_indices(series: dict):
    """Yahoo 沒有的航運指數：波羅的海乾散貨指數 BDI（每日，Trading Economics）、上海出口貨櫃運價指數 SCFI（每週五，上海航運交易所）；逐日累積"""
    def put(sym: str, d: str, v: float):
        rows = [x for x in series.get(sym, []) if x[0] != d] + [[d, round(v, 4)]]
        series[sym] = sorted(rows)[-400:]

    try:
        r = S.get("https://tradingeconomics.com/commodity/baltic", timeout=30)
        m = re.search(r"Baltic Dry (?:rose|fell|increased|decreased|was unchanged|remained)[^\d]{0,40}?([\d,]+(?:\.\d+)?) Index Points on (\w+ \d{1,2}, \d{4})", r.text)
        if m:
            dd = datetime.strptime(m.group(2), "%B %d, %Y").date()
            v = float(m.group(1).replace(",", ""))
            put("BDI", dd.isoformat(), v)
            # 頁面寫「up 3.36% from the previous day」：還沒累積到前一天的話，用漲跌幅反推前一個平日
            mp = re.search(r"(up|down) ([\d.]+)% from the previous day", r.text)
            prev_d = dd - timedelta(days=3 if dd.weekday() == 0 else 1)
            if mp and not any(x[0] == prev_d.isoformat() for x in series.get("BDI", [])):
                pct = float(mp.group(2)) * (1 if mp.group(1) == "up" else -1)
                put("BDI", prev_d.isoformat(), v / (1 + pct / 100))
        else:
            log("  ✗ BDI 頁面格式不符")
    except (requests.RequestException, ValueError) as e:
        log(f"  ✗ BDI：{e}")
    d = get_json("https://en.sse.net.cn/currentIndex", {"indexName": "scfi"})
    try:
        row = next(x for x in d["data"]["lineDataList"] if x.get("dataItemTypeName") == "SCFI_T")
        put("SCFI", d["data"]["lastDate"], float(row["lastContent"]))
        put("SCFI", d["data"]["currentDate"], float(row["currentContent"]))
    except (TypeError, KeyError, StopIteration, ValueError):
        log("  ✗ SCFI 抓不到")


# ---------------------------------------------------------------- 個股新聞輿情（給「輿情籌碼」策略）
NEWS_CATS = ("tw_stock", "tw_stock_news", "headline")
POS = ("漲停", "大漲", "飆", "噴", "攻頂", "創新高", "新高", "創高", "看好", "看旺", "調升", "上調", "上修", "調高", "受惠", "強勁",
       "成長", "獲利", "大單", "買超", "利多", "轉盈", "優於預期", "超預期", "樂觀", "喊買", "加碼", "暢旺", "爆發", "翻倍",
       "擴產", "接單", "吃補", "報喜", "亮眼", "旺", "點火", "領漲", "衝", "勁揚", "大賺", "雙增", "雙升", "回溫",
       "讚", "力挺", "喊進", "站回", "助攻", "搶單", "熱銷", "供不應求", "漲價", "拿下", "打入", "獨家")
NEG = ("跌停", "大跌", "重挫", "暴跌", "下修", "調降", "下調", "衰退", "虧損", "賣超", "利空", "疲弱", "不如預期", "低於預期",
       "保守", "砍", "減碼", "示警", "處置", "崩", "失守", "跌破", "雙減", "下滑", "轉虧", "淡季", "裁員", "停工", "違約")


def sentiment(title: str) -> int:
    return sum(1 for w in POS if w in title) - sum(1 for w in NEG if w in title)


CJK = re.compile(r"[\u4e00-\u9fff]")


def names_in(title: str, by_len: list) -> set[str]:
    """標題裡出現的公司名：長名稱優先、不重疊；兩個字的簡稱要前後不是中文字（避免「長鑫科技」被當成鑫科）"""
    taken = [False] * len(title)
    out = set()
    for nm, c in by_len:
        for m in re.finditer(re.escape(nm), title):
            a, b = m.start(), m.end()
            if any(taken[a:b]):
                continue
            if len(nm) == 2 and ((a > 0 and CJK.match(title[a - 1])) or (b < len(title) and CJK.match(title[b]))):
                continue
            taken[a:b] = [True] * (b - a)
            out.add(c)
    return out


def collect_news(names: dict[str, str], pages: int) -> int:
    """台股新聞逐則存下（時間、提到的上市櫃股票、標題、正負面分數），保留 90 天"""
    path = OUT / "news.json"
    doc = load(path, {"items": []})
    have = {x[0] for x in doc["items"]}
    by_len = sorted(((n, c) for n, c in names.items() if len(n) >= 2), key=lambda kv: -len(kv[0]))
    n = 0
    for cat in NEWS_CATS:
        for p in range(1, pages + 1):
            d = get_json(f"https://api.cnyes.com/media/api/v1/newslist/category/{cat}", {"limit": 30, "page": p})
            items = ((d or {}).get("items") or {}).get("data") or []
            if not items:
                break
            fresh = 0
            for it in items:
                nid = str(it["newsId"])
                if nid in have:
                    continue
                title = it.get("title") or ""
                # 盤前盤後要聞、一週大事這類綜合報導，以及 FactSet 機器快訊，不算個股輿情
                if re.search(r"要聞|大事|盤前|盤後|速報|一週|本周|本週|懶人包|行事曆|摘要20|新聞摘要", title):
                    have.add(nid)
                    continue
                codes = {str(x.get("code")) for x in it.get("market") or [] if re.fullmatch(r"[1-9]\d{3}", str(x.get("code") or ""))}
                codes |= names_in(title, by_len)  # 標題提到的公司（鉅亨的標籤常漏）
                if not codes:
                    continue
                doc["items"].append([nid, it["publishAt"], sorted(codes), title, sentiment(title)])
                have.add(nid)
                fresh += 1
                n += 1
            if not fresh and p > 2:
                break
            time.sleep(0.5)
    cutoff = time.time() - 90 * 86400
    doc["items"] = sorted((x for x in doc["items"] if x[1] >= cutoff), key=lambda x: x[1])
    doc["updatedAt"] = datetime.now(TPE).isoformat(timespec="minutes")
    save(path, doc)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=12)
    ap.add_argument("--backfill-days", type=int, default=0)
    ap.add_argument("--skip-us", action="store_true")
    a = ap.parse_args()
    names = stock_names()
    px = closes()
    cutoff = (datetime.now(TPE) - timedelta(days=KEEP_DAYS)).date().isoformat()

    rp, cp = OUT / "reports.json", OUT / "confnews.json"
    reports = {r["id"]: r for r in load(rp, {}).get("items", [])}
    confs = {c["id"]: c for c in load(cp, {}).get("items", [])}
    last = max((r["date"] for r in reports.values()), default="2000-01-01")
    stop = datetime.fromisoformat(last).replace(tzinfo=TPE).timestamp() - 86400
    n = scan_news(a.pages, names, reports, confs, stop, px)
    g = google_news(names, reports, px, max(14, a.backfill_days))
    nn = collect_news(names, max(a.pages, 6))
    log(f"個股新聞：新增 {nn} 則")
    log(f"券報：鉅亨新增 {n} 筆、Google 新聞新增 {g} 筆，共 {len(reports)} 筆")
    if a.backfill_days:
        backfill_conf(a.backfill_days, names, confs)
    log(f"法說會新聞：共 {len(confs)} 則")
    now = datetime.now(TPE).isoformat(timespec="minutes")
    save(rp, {"updatedAt": now, "items": sorted((r for r in reports.values() if r["date"] >= cutoff), key=lambda r: r["date"], reverse=True)})
    save(cp, {"updatedAt": now, "items": sorted((c for c in confs.values() if c["date"] >= cutoff), key=lambda c: c["date"], reverse=True)})

    if not a.skip_us:
        up = OUT / "us.json"
        doc = load(up, {"series": {}})
        fetch_us(doc["series"])
        fetch_indices(doc["series"])
        doc["updatedAt"] = now
        save(up, doc)
        log(f"國際行情：{len(doc['series'])} 檔，最新 {max((v[-1][0] for v in doc['series'].values()), default='—')}")
        rk = OUT / "risk.json"
        rdoc = load(rk, {"series": {}})
        fetch_us(rdoc["series"], {**RISK_TICKERS, **CDS_TICKERS}, "2y")
        fetch_fred(rdoc["series"])
        fetch_credit(rdoc.setdefault("fund", {}))
        rdoc["updatedAt"] = now
        save(rk, rdoc)
        log(f"風險指標：{len(rdoc['series'])} 項")
        wk = fetch_week()
        if wk["macro"] or wk["earnings"]:  # 都抓不到就保留舊檔
            save(OUT / "week.json", {"updatedAt": now, **wk})
        log(f"國際行事曆：經濟數據 {len(wk['macro'])} 項、美股財報 {len(wk['earnings'])} 家")
    return 0


if __name__ == "__main__":
    sys.exit(main())
