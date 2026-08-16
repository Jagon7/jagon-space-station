#!/usr/bin/env python3
"""
台股資料抓取器 — Jagon Space Station 資料層
每日收盤後執行，輸出 JSON 至 Next.js data/ 目錄

資料來源：
  - TWSE OpenAPI  (上市)
  - TPEx OpenAPI  (上櫃)
  - TWSE 處置名單
  - TWSE 大盤統計
"""
import os, sys, json, re, time, datetime
from pathlib import Path
import requests

# ── 設定 ─────────────────────────────────────────────────────
JSS_DATA_DIR = Path(
    os.environ.get("JSS_DATA_DIR",
                   Path.home() / "Desktop" / "jagon-space-station" / "data")
)
JSS_DATA_DIR.mkdir(parents=True, exist_ok=True)

TODAY    = datetime.date.today()
TODAY_AD = TODAY.strftime("%Y-%m-%d")
TODAY_RC = str(TODAY.year - 1911)                # e.g. "115"
TODAY_YMD = f"{TODAY_RC}{TODAY.month:02d}{TODAY.day:02d}"  # e.g. "1150509"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; JSS-fetcher/1.0)"})

LIMIT_UP_MIN = 9.0    # 最低漲幅門檻（考慮 tick 捨入）
LIMIT_UP_MAX = 11.0   # 超過此值視為新掛牌/復牌異常，排除

# ── 產業別 → 族群名稱 ─────────────────────────────────────────
# 來源：TWSE 上市公司產業別代碼（t187ap03_L）
INDUSTRY_MAP = {
    "01": "水泥",      "02": "食品",      "03": "塑膠",
    "04": "紡織纖維",  "05": "電機機械",  "06": "電器電纜",
    "08": "玻璃陶瓷",  "09": "造紙",      "10": "鋼鐵",
    "11": "橡膠",      "12": "汽車",      "14": "建材營造",
    "15": "航運",      "16": "觀光餐旅",  "17": "金融保險",
    "18": "貿易百貨",  "20": "其他",      "21": "化工",
    "22": "生技醫療",  "23": "油電燃氣",  "24": "半導體",
    "25": "電腦週邊",  "26": "光電",      "27": "通信網路",
    "28": "電子零組件","29": "電子通路",  "30": "資訊服務",
    "31": "其他電子",  "35": "綠能環保",  "36": "數位雲端",
    "37": "運動休閒",  "38": "居家生活",  "91": "存託憑證",
}

def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def save(filename: str, data: dict):
    path = JSS_DATA_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✓ {filename} 已寫入（{path}）")

HAD_CRITICAL_FAILURE = False

def save_guarded(filename: str, items: list) -> list:
    """
    寫入前比對舊檔：如果這次抓到空的、但舊檔案有資料，判定為抓取異常
    （來源改版/連線失敗等），保留舊資料不覆蓋，並標記本次執行失敗，
    讓 GitHub Actions 顯示紅叉、觸發失敗通知信，而不是悄悄寫入空資料。
    """
    global HAD_CRITICAL_FAILURE
    path = JSS_DATA_DIR / filename
    if not items and path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            if prev.get("data"):
                log(f"✗ {filename} 本次抓取為空但舊檔有 {len(prev['data'])} 筆，判定抓取異常，保留舊資料")
                HAD_CRITICAL_FAILURE = True
                return prev["data"]
        except Exception:
            pass
    save(filename, {"date": TODAY_AD, "data": items})
    return items

def fetch(url: str, timeout: int = 20) -> dict | list | None:
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"✗ fetch 失敗 {url[:60]}... → {e}")
        return None

def fetch_csv(url: str, timeout: int = 20) -> list[dict]:
    """TWSE 部分 rwd/afterTrading 報表無論 URL 帶不帶 response=json 都固定回 CSV，不是 JSON"""
    import csv, io
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return list(csv.DictReader(io.StringIO(r.text)))
    except Exception as e:
        log(f"✗ fetch_csv 失敗 {url[:60]}... → {e}")
        return []

def fetch_post(url: str, data: dict = None, timeout: int = 20) -> dict | None:
    try:
        r = SESSION.post(url, data=data or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"✗ fetch_post 失敗 {url[:60]}... → {e}")
        return None

# ── 工具函式 ────────────────────────────────────────────────
def parse_price(s: str) -> float:
    try:
        return float(str(s).replace(",", "").strip())
    except:
        return 0.0

def calc_change_pct(close: float, change: float) -> float:
    if close <= 0 or change == 0:
        return 0.0
    prev = close - change
    if prev <= 0:
        return 0.0
    return round(change / prev * 100, 2)

def roc_to_ad(roc_date: str) -> str:
    """'1150508' → '2026-05-08'"""
    s = str(roc_date).strip()
    if len(s) == 7:
        year = int(s[:3]) + 1911
        return f"{year}-{s[3:5]}-{s[5:7]}"
    return TODAY_AD

# ── 三大法人買賣超 ────────────────────────────────────────────
def _parse_insti_num(s) -> int:
    """解析千分位整數，轉換成張（股數 ÷ 1000）"""
    try:
        return int(str(s).replace(",", "").replace("+", "").strip()) // 1000
    except:
        return 0

def fetch_institutional() -> dict[str, dict]:
    """
    回傳 {股號: {foreign, trust, dealer, total}} 單位：張
    先嘗試當日，無資料時退回前一個交易日（最多往前 5 日）
    """
    log("抓取三大法人買賣超...")

    def _recent_date_str(offset: int) -> str:
        d = TODAY - datetime.timedelta(days=offset)
        return d.strftime("%Y%m%d")

    result: dict[str, dict] = {}

    # ── 上市 TWSE T86 ──
    for days_back in range(0, 6):
        date_str = _recent_date_str(days_back)
        data = fetch(f"https://www.twse.com.tw/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999")
        if data and data.get("stat") == "OK" and data.get("data"):
            for row in data["data"]:
                try:
                    code = str(row[0]).strip()
                    if not _is_stock_code(code):
                        continue
                    result[code] = {
                        "foreign": _parse_insti_num(row[4]),
                        "trust":   _parse_insti_num(row[10]),
                        "dealer":  _parse_insti_num(row[11]),
                        "total":   _parse_insti_num(row[18]) if len(row) > 18 else 0,
                    }
                except (IndexError, ValueError):
                    continue
            log(f"  上市三大法人：{date_str}，{len(result)} 檔")
            break

    # ── 上櫃 TPEx insti/dailyTrade ──
    roc_today = f"{TODAY_RC}/{TODAY.month:02d}/{TODAY.day:02d}"
    tpex_count = 0
    for days_back in range(0, 6):
        d = TODAY - datetime.timedelta(days=days_back)
        roc_date = f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"
        data = fetch_post("https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade",
                          {"type": "Daily", "date": roc_date, "sect": "EW"})
        rows = (data or {}).get("tables", [{}])[0].get("data", [])
        if rows:
            for row in rows:
                code = str(row[0]).strip()
                if not _is_stock_code(code):
                    continue
                # 外資合計[10]、自營自行[13]+避險[16]、投信[19]、三大[23]
                result[code] = {
                    "foreign": _parse_insti_num(row[10]),
                    "trust":   _parse_insti_num(row[19]),
                    "dealer":  _parse_insti_num(row[13]) + _parse_insti_num(row[16]),
                    "total":   _parse_insti_num(row[23]),
                }
                tpex_count += 1
            log(f"  上櫃三大法人：{roc_date}，{tpex_count} 檔")
            break

    return result

# ── 建立股號 → 產業別 對照表 ────────────────────────────────
def build_sector_map() -> dict[str, str]:
    log("載入公司產業別資料...")
    result = {}

    # 上市公司
    data = fetch("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
    if data:
        for row in data:
            code = row.get("公司代號", "").strip()
            ind  = row.get("產業別", "").strip()
            if code:
                result[code] = INDUSTRY_MAP.get(ind, "其他")

    # 上櫃公司（TPEx）
    data = fetch("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_listed_companies")
    if data:
        for row in data:
            code = row.get("SecuritiesCompanyCode", "").strip()
            ind  = row.get("IndustryCode", "").strip()
            if code:
                result[code] = INDUSTRY_MAP.get(ind, "其他")

    log(f"  產業別對照表：{len(result)} 筆")
    return result

# ── 全市場報價 ──────────────────────────────────────────────
def fetch_all_stocks(sector_map: dict, insti_map: dict = None) -> list[dict]:
    """全市場（上市+上櫃）當日報價，含族群、漲跌幅 — 漲停清單跟族群個股排行共用同一份，避免重複打 API"""
    log("抓取全市場報價...")
    stocks = []

    # ── 上市 (TWSE) ──
    # openapi.twse.com.tw 更新較慢（隔日），改用 www.twse.com.tw 當天即時
    # 這個 report 端點無論有沒有帶 response=json 一律回 CSV（Content-Type: text/csv），
    # 舊版用 fetch()/r.json() 每次都會解析失敗、整個上市股票（含台積電這種量體）
    # 從沒進過族群/漲停清單，一直只有上櫃資料
    twse = fetch_csv("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json")
    for row in twse:
        code = (row.get("證券代號") or "").strip()
        if not code.isdigit():
            continue
        close = parse_price(row.get("收盤價", 0))
        chg   = parse_price(row.get("漲跌價差", 0))
        vol   = int(parse_price(row.get("成交股數", 0)) / 1000)  # 股 → 張
        tv    = parse_price(row.get("成交金額", 0))
        pct   = calc_change_pct(close, chg)
        insti = (insti_map or {}).get(code, {})
        stocks.append({
            "code":       code,
            "name":       (row.get("證券名稱") or "").strip(),
            "sector":     sector_map.get(code, "其他"),
            "change":     pct,
            "volume":     vol,
            "tradeValue": tv,
            "closePrice": close,
            "openPrice":  parse_price(row.get("開盤價", 0)),
            "limitTime":  "--:--",
            "market":     "上市",
            "instiForeign": insti.get("foreign", None),
            "instiTrust":   insti.get("trust",   None),
            "instiDealer":  insti.get("dealer",  None),
            "instiTotal":   insti.get("total",   None),
            "reason":     "",
        })

    # ── 上櫃 (TPEx) ──
    tpex = fetch("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes")
    if tpex:
        for row in tpex:
            code  = row.get("SecuritiesCompanyCode", "").strip()
            if not code.isdigit():
                continue
            close = parse_price(row.get("Close", 0))
            chg   = parse_price(row.get("Change", 0))
            vol   = int(parse_price(row.get("TradingShares", 0)) / 1000)
            tv    = parse_price(row.get("TransactionAmount", 0))
            pct   = calc_change_pct(close, chg)
            insti = (insti_map or {}).get(code, {})
            stocks.append({
                "code":       code,
                "name":       row.get("CompanyName", "").strip(),
                "sector":     sector_map.get(code, "其他"),
                "change":     pct,
                "volume":     vol,
                "tradeValue": tv,
                "closePrice": close,
                "openPrice":  parse_price(row.get("Open", close)),
                "limitTime":  "--:--",
                "market":     "上櫃",
                "instiForeign": insti.get("foreign", None),
                "instiTrust":   insti.get("trust",   None),
                "instiDealer":  insti.get("dealer",  None),
                "instiTotal":   insti.get("total",   None),
                "reason":     "",
            })

    # 依當日成交金額由大到小排序
    stocks.sort(key=lambda s: -s["tradeValue"])
    log(f"  全市場報價：{len(stocks)} 檔（上市+上櫃）")
    return stocks

def filter_limit_up(all_stocks: list[dict]) -> list[dict]:
    stocks = [s for s in all_stocks if LIMIT_UP_MIN <= s["change"] <= LIMIT_UP_MAX]
    log(f"  漲停股：{len(stocks)} 檔（上市+上櫃）")
    return stocks

def build_sector_stocks(all_stocks: list[dict]) -> dict[str, list[dict]]:
    """族群個股排行 — 依族群分組，組內依漲跌幅由大到小排序"""
    from collections import defaultdict
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in all_stocks:
        grouped[s["sector"]].append({
            "code":          s["code"],
            "name":          s["name"],
            "market":        s["market"],
            "changePercent": s["change"],
            "closePrice":    s["closePrice"],
            "volume":        s["volume"],
            "tradeValue":    s["tradeValue"],
        })
    for lst in grouped.values():
        lst.sort(key=lambda s: s["changePercent"], reverse=True)
    log(f"  族群個股排行：{len(grouped)} 個族群")
    return dict(grouped)

# ── 族群統計 ────────────────────────────────────────────────
def summarize_sectors(stocks: list[dict]) -> list[dict]:
    from collections import Counter
    cnt = Counter(s["sector"] for s in stocks if s["sector"] != "其他")
    result = []
    for sector, count in cnt.most_common(10):
        momentum = "strong" if count >= 6 else "normal" if count >= 3 else "weak"
        result.append({"name": sector, "count": count, "momentum": momentum})
    return result

# TWSE 官方類股指數名稱跟 INDUSTRY_MAP 顯示名稱少數幾個對不上，手動對齊
SECTOR_INDEX_ALIAS = {"化工": "化學", "電腦週邊": "電腦及週邊設備"}

def fetch_sector_performance() -> list[dict]:
    """
    全市場族群強弱排行 — 用 TWSE 官方類股指數當日漲跌幅（不是漲停家數），
    這是市值加權的真實族群表現，比自己算個股平均漲跌幅更準也更快。
    """
    log("抓取類股指數漲跌...")
    data = fetch("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX") or []

    by_name: dict[str, float] = {}
    for row in data:
        name = row.get("指數", "")
        if not name.endswith("類指數") or "報酬" in name:
            continue
        try:
            # 漲跌百分比字串本身就帶負號（"-1.45"），漲跌欄位只是輔助標記，
            # 不需要也不該再依它二次翻負號
            by_name[name[:-3]] = float(row.get("漲跌百分比", 0) or 0)
        except (TypeError, ValueError):
            continue

    results = []
    for sector_name in dict.fromkeys(INDUSTRY_MAP.values()):
        twse_name = SECTOR_INDEX_ALIAS.get(sector_name, sector_name)
        if twse_name in by_name:
            results.append({"name": sector_name, "changePercent": by_name[twse_name]})

    results.sort(key=lambda s: s["changePercent"], reverse=True)
    log(f"族群強弱：{len(results)} 個族群")
    return results

# ── 大盤統計 ────────────────────────────────────────────────
def _fetch_taiex_change() -> float:
    """加權指數當日漲跌百分比（號稱 0.0 是沒抓到，不是真的平盤）"""
    data = fetch("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX") or []
    for row in data:
        if row.get("指數") == "發行量加權股價指數":
            try:
                # 漲跌百分比字串本身就帶負號，不需要再依漲跌欄位二次翻負號
                return float(row.get("漲跌百分比", 0) or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0

def fetch_market_summary(limit_up_count: int, sector_count: int) -> dict:
    log("抓取大盤統計...")
    limit_up_total = limit_up_count
    taiex_change   = _fetch_taiex_change()
    mood           = "中性"

    # 氣氛判斷用純股票漲停家數（與清單一致）
    if limit_up_total >= 60:
        mood = "強勢"
    elif limit_up_total >= 40:
        mood = "偏強"
    elif limit_up_total >= 20:
        mood = "中性"
    elif limit_up_total >= 10:
        mood = "偏弱"
    else:
        mood = "弱勢"

    return {
        "date":             TODAY_AD,
        "limitUpCount":     limit_up_total,
        "sectorCount":      sector_count,
        "dispositionCount": 0,   # 由處置模組填入
        "announcementCount": 0,
        "marketMood":       mood,
        "taiexChange":      taiex_change,
    }

def _is_stock_code(code: str) -> bool:
    """只保留 4 位純數字（一般股票），排除 ETF / 權證 / 可轉債等"""
    return code.isdigit() and len(code) == 4

def _parse_roc_period_end(period: str) -> str:
    """'115/05/07～115/05/20' 或 '115/05/07~115/05/20' → '2026-05-20'"""
    # 支援全形 ～ 與半形 ~
    end_roc = period.replace("～", "~").split("~")[-1].strip()
    try:
        parts = end_roc.split("/")
        return f"{int(parts[0]) + 1911}-{parts[1]}-{parts[2]}"
    except:
        return "9999-12-31"

def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()

# ── 注意股：上市 (TWSE) ──────────────────────────────────────
def _fetch_twse_notice() -> list[dict]:
    data = fetch("https://www.twse.com.tw/announcement/notice?response=json")
    if not data or data.get("stat") != "OK":
        return []
    stocks = []
    for row in data.get("data", []):
        try:
            code  = str(row[1]).strip()
            if not _is_stock_code(code):
                continue
            stocks.append({
                "code":        code,
                "name":        str(row[2]).strip(),
                "noticeCount": int(row[3]) if row[3] else 1,
                "info":        str(row[4]).strip(),
                "date":        str(row[5]).strip(),
                "closePrice":  parse_price(row[6]) if len(row) > 6 else 0,
                "market":      "上市",
            })
        except:
            continue
    return stocks

# ── 注意股：上櫃 (TPEx) ──────────────────────────────────────
def _fetch_tpex_notice() -> list[dict]:
    # fields: ['編號','證券代號','證券名稱','累計','注意交易資訊','公告日期','收盤價','本益比','link']
    data = fetch_post("https://www.tpex.org.tw/www/zh-tw/bulletin/attention")
    if not data:
        return []
    rows = data.get("tables", [{}])[0].get("data", [])
    stocks = []
    for row in rows:
        try:
            code = str(row[1]).strip()
            if not _is_stock_code(code):
                continue
            stocks.append({
                "code":        code,
                "name":        str(row[2]).strip(),
                "noticeCount": int(row[3]) if row[3] else 1,
                "info":        _strip_html(str(row[4])),
                "date":        str(row[5]).strip(),
                "closePrice":  parse_price(row[6]) if len(row) > 6 else 0,
                "market":      "上櫃",
            })
        except:
            continue
    return stocks

def fetch_notice_stocks() -> list[dict]:
    log("抓取注意股名單（上市 + 上櫃）...")
    twse = _fetch_twse_notice()
    tpex = _fetch_tpex_notice()
    stocks = twse + tpex
    log(f"  注意股：{len(stocks)} 檔（上市 {len(twse)} + 上櫃 {len(tpex)}）")
    return stocks

# ── 處置股：上市 (TWSE) ──────────────────────────────────────
def _fetch_twse_disposition() -> list[dict]:
    data = fetch("https://www.twse.com.tw/announcement/punish?response=json")
    if not data or data.get("stat") != "OK":
        return []
    stocks = []
    for row in data.get("data", []):
        try:
            code = str(row[2]).strip()
            if not _is_stock_code(code):
                continue
            period = str(row[6]).strip()
            stocks.append({
                "code":         code,
                "name":         str(row[3]).strip(),
                "count":        int(row[4]) if row[4] else 1,
                "condition":    str(row[5]).strip(),
                "period":       period,
                "endDate":      _parse_roc_period_end(period),
                "announceDate": str(row[1]).strip(),
                "market":       "上市",
            })
        except:
            continue
    return stocks

# ── 處置股：上櫃 (TPEx) ──────────────────────────────────────
def _fetch_tpex_disposition() -> list[dict]:
    import re
    # fields: ['編號','公布日期','證券代號','證券名稱','累計','處置起訖時間','處置原因','處置內容',...]
    data = fetch_post("https://www.tpex.org.tw/www/zh-tw/bulletin/disposal")
    if not data:
        return []
    rows = data.get("tables", [{}])[0].get("data", [])
    stocks = []
    for row in rows:
        try:
            code = str(row[2]).strip()
            if not _is_stock_code(code):
                continue
            # name 欄位可能含連結，如 '川寶(../../...)' → 只取前段
            raw_name = str(row[3])
            name = re.sub(r"\(.*?\)", "", raw_name).strip()
            period = str(row[5]).strip()
            stocks.append({
                "code":         code,
                "name":         name,
                "count":        int(row[4]) if row[4] else 1,
                "condition":    _strip_html(str(row[6])),
                "period":       period,
                "endDate":      _parse_roc_period_end(period),
                "announceDate": str(row[1]).strip(),
                "market":       "上櫃",
            })
        except:
            continue
    return stocks

def fetch_disposition_stocks() -> list[dict]:
    log("抓取處置股名單（上市 + 上櫃）...")
    twse = _fetch_twse_disposition()
    tpex = _fetch_tpex_disposition()
    stocks = twse + tpex

    # 同一股票可能有多筆（舊期間未到期 + 新期間），只保留 endDate 最晚的那筆
    latest: dict[str, dict] = {}
    for s in stocks:
        key = s["code"]
        if key not in latest or s["endDate"] > latest[key]["endDate"]:
            latest[key] = s
    stocks = list(latest.values())

    # 處置快結束的排前面
    stocks.sort(key=lambda s: s["endDate"])
    log(f"  處置股：{len(stocks)} 檔（上市 {len(twse)} + 上櫃 {len(tpex)}）")
    return stocks

# ── 漲停原因：Google News + Claude ────────────────────────────
def _google_news_headlines(code: str, name: str) -> list[str]:
    import xml.etree.ElementTree as ET, urllib.parse
    q = urllib.parse.quote(f"{name} 漲停")
    url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        r = SESSION.get(url, timeout=8)
        root = ET.fromstring(r.content)
        return [item.findtext("title", "") for item in root.findall(".//item")][:4]
    except:
        return []

def fetch_limit_up_reasons(stocks: list[dict]) -> dict[str, str]:
    """
    每檔漲停股：Google News 抓標題 → Claude Haiku 歸納一句原因
    需要 ANTHROPIC_API_KEY 環境變數，缺少時回傳空字典
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log("⚠ ANTHROPIC_API_KEY 未設定，漲停原因略過")
        return {}

    try:
        import anthropic
    except ImportError:
        log("⚠ anthropic 套件未安裝，執行 pip install anthropic")
        return {}

    log(f"抓取漲停原因（Google News × {len(stocks)} 檔 → Claude）...")

    # 1. 並行抓各股新聞
    news_map: dict[str, list[str]] = {}
    for s in stocks:
        news_map[s["code"]] = _google_news_headlines(s["code"], s["name"])

    # 2. 組成 prompt
    lines = [
        f"今日（{TODAY_AD}）台股漲停。根據以下各股新聞標題，",
        "為每支股票寫一句漲停主因（繁體中文，12字以內，不要冠股名）：\n",
    ]
    for s in stocks:
        lines.append(f"【{s['code']} {s['name']}】")
        news = news_map.get(s["code"], [])
        if news:
            for h in news[:3]:
                lines.append(f"  · {h}")
        else:
            lines.append("  · （今日無相關新聞）")
    lines.append(
        f"\n以 JSON 格式回覆，鍵為股號字串，值為原因字串：\n"
        '{"3034":"原因","8210":"原因",...}'
    )

    # 3. 呼叫 Claude Haiku
    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system="你只輸出純 JSON，不加任何 markdown、說明或換行以外的文字。",
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        text = resp.content[0].text.strip()
        log(f"  Claude 回應（前 200 字）：{text[:200]}")

        # 依序嘗試解析，容錯 markdown fence 或前後文字
        reasons: dict[str, str] = {}
        candidates = [
            text,
            re.sub(r"```(?:json)?\s*|\s*```", "", text).strip(),
        ]
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            candidates.append(m.group())

        for candidate in candidates:
            try:
                reasons = json.loads(candidate)
                break
            except Exception:
                continue

        if not reasons:
            log("✗ Claude 回傳內容無法解析為 JSON，漲停原因略過")
        return reasons

    except Exception as e:
        log(f"✗ Claude 呼叫失敗：{e}")

    return {}

# ── CB 詢圈：輔助函式 ─────────────────────────────────────────
def _clean_legal_name(name: str) -> str:
    for suffix in ["股份有限公司", "有限公司", "（創新板）", "(創新板)", "－KY", "-KY"]:
        name = name.replace(suffix, "")
    return name.strip()

def _match_code(legal_name: str, name_map: dict) -> tuple | None:
    """法人全稱 → (股號, 簡稱)。最長子字串優先；唯一前兩字首碼為備援。"""
    clean = _clean_legal_name(legal_name)
    best = max(
        ((c, n) for c, n in name_map.items() if len(n) >= 2 and n in clean),
        key=lambda x: len(x[1]),
        default=None,
    )
    if best:
        return best
    prefix = clean[:2]
    cands = [(c, n) for c, n in name_map.items() if n.startswith(prefix)]
    return cands[0] if len(cands) == 1 else None

def _build_code_meta() -> dict:
    """回傳 {股號: {name, price, market}}，涵蓋上市 + 上櫃所有股票。"""
    meta: dict[str, dict] = {}
    twse = fetch("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    if twse:
        for r in twse:
            c = r.get("Code", "").strip()
            if _is_stock_code(c):
                meta[c] = {
                    "name":   r.get("Name", "").strip(),
                    "price":  parse_price(r.get("ClosingPrice", 0)),
                    "market": "上市",
                }
    tpex = fetch("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes")
    if tpex:
        for r in tpex:
            c = r.get("SecuritiesCompanyCode", "").strip()
            if _is_stock_code(c):
                meta[c] = {
                    "name":   r.get("CompanyName", "").strip(),
                    "price":  parse_price(r.get("Close", 0)),
                    "market": "上櫃",
                }
    return meta

def _parse_ad_slash(date_str: str) -> str:
    """'2026/01/07' → '2026-01-07'"""
    try:
        parts = date_str.strip().split("/")
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    except:
        return ""

# ── CB 詢圈：主抓取函式 ────────────────────────────────────────
def fetch_cb_issuances() -> list[dict]:
    log("抓取 CB 詢圈資料（TWSA 詢圈公告）...")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log("⚠ 需要安裝 beautifulsoup4：pip install beautifulsoup4")
        return []

    base_url = "https://web.twsa.org.tw/edoc2/default.aspx"
    hdrs = {"Referer": base_url, "Accept": "text/html,application/xhtml+xml"}

    # Step 1: GET 取得 ViewState
    try:
        r1 = SESSION.get(base_url, headers=hdrs, timeout=20)
        r1.raise_for_status()
    except Exception as e:
        log(f"✗ TWSA GET 失敗：{e}")
        return []

    soup1 = BeautifulSoup(r1.content, "html.parser")

    def _hidden(name: str) -> str:
        tag = soup1.find("input", {"name": name, "type": "hidden"})
        return tag.get("value", "") if tag else ""

    post_data = {
        "__VIEWSTATE":           _hidden("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR":  _hidden("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION":     _hidden("__EVENTVALIDATION"),
        "__EVENTTARGET":         "ctl00$cphMain$rblReportType",
        "__EVENTARGUMENT":       "",
        "ctl00$cphMain$rblReportType": "BookBuilding",
        "ctl00$cphMain$ddlYear": str(TODAY.year),   # AD year e.g. 2026
    }

    # Step 2: POST 取得詢圈清單
    try:
        r2 = SESSION.post(base_url, data=post_data, headers=hdrs, timeout=20)
        r2.raise_for_status()
    except Exception as e:
        log(f"✗ TWSA POST 失敗：{e}")
        return []

    soup2 = BeautifulSoup(r2.content, "html.parser")

    # GridView 固定 ID
    table = soup2.find("table", id="ctl00_cphMain_gvResult")
    if not table:
        log("✗ TWSA：找不到 ctl00_cphMain_gvResult 表格")
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        log("✗ TWSA：表格無資料列")
        return []

    # 欄位索引（依實際 header 動態對應）
    # 實際 headers: 序號 發行公司 主辦承銷商 發行性質 承銷股數(千股/張) 詢圈銷售股數(千股/張) 圈購期間 價格(元) 公告檔
    header_cells = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    log(f"  TWSA 欄位：{header_cells}")

    def col(candidates: list, default: int) -> int:
        for name in candidates:
            for i, h in enumerate(header_cells):
                if name in h:
                    return i
        return default

    idx_serial = col(["序號"], 0)
    idx_name   = col(["發行公司", "公司名稱"], 1)
    idx_uw     = col(["承銷商"], 2)
    idx_type   = col(["發行性質", "有價證券種類", "種類"], 3)
    idx_shares = col(["承銷股數"], 4)
    idx_period = col(["圈購期間"], 6)

    meta = _build_code_meta()
    name_map = {c: v["name"] for c, v in meta.items()}
    cutoff = (TODAY - datetime.timedelta(days=90)).isoformat()

    results = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue

        def cell(i: int) -> str:
            return cells[i].get_text(strip=True) if i < len(cells) else ""

        issue_type = cell(idx_type)
        if "轉換公司債" not in issue_type:
            continue

        legal_name  = cell(idx_name)
        underwriter = cell(idx_uw)
        period      = cell(idx_period)   # e.g. "2026/01/07~2026/01/09" (AD format)

        # 圈購起訖日
        bb_start = bb_end = ""
        if period:
            parts = period.replace("～", "~").split("~")
            bb_start = _parse_ad_slash(parts[0]) if len(parts) >= 1 else ""
            bb_end   = _parse_ad_slash(parts[1]) if len(parts) >= 2 else ""

        # 預估掛牌日：定價日（圈購結束後首個工作日）+ 7 天 → 順延至當週或下週五
        # 根據歷史觀察，台灣 CB 掛牌通常在定價後第一個可用週五
        listing_date = ""
        if bb_end:
            try:
                d = datetime.date.fromisoformat(bb_end)
                # 定價日 = 圈購結束後首個工作日
                pricing = d + datetime.timedelta(days=1)
                while pricing.weekday() >= 5:
                    pricing += datetime.timedelta(days=1)
                # 目標日 = 定價日 + 7 天，順延至最近的週五
                target = pricing + datetime.timedelta(days=7)
                days_to_fri = (4 - target.weekday()) % 7   # Friday = weekday 4
                listing_date = (target + datetime.timedelta(days=days_to_fri)).isoformat()
            except:
                pass

        # 超過 90 天前已掛牌者略過
        if listing_date and listing_date < cutoff:
            continue
        if not listing_date and bb_start and bb_start < cutoff:
            continue

        # 承銷股數 (張) → 億元（1張 = NT$100,000；1000張 = 1億）
        amount = None
        try:
            amount = round(float(cell(idx_shares).replace(",", "")) / 1000, 2)
        except:
            pass

        # CB 次別（由序號推算，格式 115001 → 序號年內第1次）
        serial = cell(idx_serial)
        cb_num = serial[3:] if len(serial) >= 4 else ""
        cb_series = f"第{int(cb_num)}次" if cb_num.isdigit() else ""

        # 比對股號
        match = _match_code(legal_name, name_map)
        code       = match[0] if match else ""
        short_name = match[1] if match else _clean_legal_name(legal_name)
        close_px   = meta.get(code, {}).get("price") if code else None
        market     = meta.get(code, {}).get("market", "") if code else ""

        results.append({
            "code":            code,
            "name":            short_name,
            "cbSeries":        cb_series,
            "filingDate":      bb_start,    # TWSA 無申報日，以圈購開始日代替
            "bookBuildDate":   bb_start,
            "listingDate":     listing_date,
            "amount":          amount,
            "conversionPrice": None,         # 定價後才確定，TWSA 不提供
            "closePrice":      close_px,
            "market":          market,
            "underwriter":     underwriter,
        })

    # 最近要掛牌的排最前面
    results.sort(key=lambda x: x["listingDate"] or "9999-12-31")
    log(f"  CB 詢圈：{len(results)} 筆")
    return results

# ── 公告（MOPS 每日重大訊息）───────────────────────────────────
def _format_mops_time(raw: str) -> str:
    s = str(raw).strip().zfill(6)
    if len(s) < 6 or not s.isdigit():
        return "--:--"
    return f"{s[:2]}:{s[2:4]}"

def fetch_announcements() -> list[dict]:
    """MOPS 每日重大訊息（上市 t187ap04_L + 上櫃 mopsfin_t187ap04_O）"""
    log("抓取 MOPS 重大訊息...")
    results = []

    sources = [
        ("https://openapi.twse.com.tw/v1/opendata/t187ap04_L", "公司代號", "公司名稱"),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O", "SecuritiesCompanyCode", "CompanyName"),
    ]
    for url, code_key, name_key in sources:
        data = fetch(url) or []
        for row in data:
            code = str(row.get(code_key, "")).strip()
            # TWSE 那份的欄位名稱帶了個尾隨空白："主旨 "
            subject = str(row.get("主旨") or row.get("主旨 ") or "").strip()
            if not code or not subject:
                continue
            results.append({
                "time":      _format_mops_time(row.get("發言時間", "")),
                "date":      roc_to_ad(row.get("發言日期", "")),
                "code":      code,
                "name":      str(row.get(name_key, "")).strip(),
                "type":      "重大訊息",
                "important": False,
                "content":   " ".join(subject.split()),
            })

    results.sort(key=lambda a: (a["date"], a["time"]), reverse=True)
    log(f"  重大訊息：{len(results)} 則")
    return results

# ── FSC 申報案件彙總表（轉換公司債）─────────────────────────────
def fetch_sfb_cb() -> list[dict]:
    log("抓取 FSC 申報案件 CB 資料（sfb.gov.tw）...")
    import re as _re, io as _io
    try:
        import openpyxl
    except ImportError:
        log("✗ openpyxl 未安裝，FSB CB 略過")
        return []

    # 動態找最新 115 年度申報案件彙總表 xlsx
    try:
        r = SESSION.get("https://www.sfb.gov.tw/ch/home.jsp?id=1016&parentpath=0,6,52", timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        log(f"✗ SFB 頁面抓取失敗 → {e}")
        return []

    roc_year = str(TODAY.year - 1911)
    pattern = (
        r'https://www\.fsc\.gov\.tw/userfiles/file/'
        + roc_year + r'\d+'
        + r'%E7%94%B3%E5%A0%B1%E6%A1%88%E4%BB%B6%E5%BD%99%E7%B8%BD%E8%A1%A8\.xlsx'
    )
    matches = _re.findall(pattern, html)
    if not matches:
        log(f"✗ 找不到 {roc_year}年度申報案件 Excel URL")
        return []

    excel_url = matches[-1]
    log(f"  Excel: {excel_url}")

    try:
        r = SESSION.get(excel_url, timeout=30)
        r.raise_for_status()
        wb = openpyxl.load_workbook(_io.BytesIO(r.content))
    except Exception as e:
        log(f"✗ Excel 下載/解析失敗 → {e}")
        return []

    ws = wb.active
    results = []
    for row in ws.iter_rows(min_row=4, values_only=True):
        if not row[5] or "轉換公司債" not in str(row[5]):
            continue
        code        = str(row[0]).strip() if row[0] else ""
        market      = str(row[1]).strip() if row[1] else ""
        status      = str(row[2]).strip() if row[2] else "審查中"
        name        = str(row[3]).strip() if row[3] else ""
        underwriter = str(row[4]).strip() if row[4] else None
        cb_type     = str(row[5]).strip() if row[5] else ""
        amount_raw  = row[6]
        currency    = str(row[7]).strip() if row[7] else "台幣"
        filing_date    = roc_to_ad(str(row[9]))  if row[9]  else None
        effective_date = roc_to_ad(str(row[13])) if row[13] else None
        withdraw_date  = roc_to_ad(str(row[15])) if row[15] else None

        # 金額：台幣→億元，外幣→百萬元
        amount_b = None
        if amount_raw:
            try:
                v = float(str(amount_raw).replace(",", ""))
                amount_b = round(v / (1e8 if currency == "台幣" else 1e6), 1)
            except Exception:
                pass

        results.append({
            "code":          code,
            "name":          name,
            "market":        market,
            "status":        status,
            "cbType":        cb_type,
            "amount":        amount_b,
            "currency":      currency,
            "filingDate":    filing_date,
            "effectiveDate": effective_date,
            "withdrawDate":  withdraw_date,
            "underwriter":   underwriter,
        })

    log(f"  FSC CB：{len(results)} 筆")
    return results

# ── ETF 成分股動態 ────────────────────────────────────────────
# 各投信申購買回清單（PCF）資料來源設定
# 每日盤後更新，透過比較昨日 vs 今日持股股數計算增減
ETF_CONFIG = {
    # 市值型 ETF
    "0050": {
        "name": "元大台灣50",       "category": "市值型",
        "source": "yuanta",         # 元大投信
        "product_id": "0050",
    },
    # 高股息 ETF
    "00919": {
        "name": "群益台灣精選高息", "category": "高股息",
        "source": "capital",        # 群益投信
        "product_id": "195",
    },
    "00929": {
        "name": "復華台灣科技優息", "category": "高股息",
        "source": "fuhhwa",         # 復華投信 — ETF detail page ID
        "product_id": "ETF21",
    },
    "00878": {
        "name": "國泰永續高股息",   "category": "高股息",
        "source": "cathay",         # 國泰投信
        "product_id": "CN",
    },
    "0056": {
        "name": "元大高股息",       "category": "高股息",
        "source": "yuanta",         # 元大投信
        "product_id": "0056",
    },
    "00940": {
        "name": "元大台灣價值高息", "category": "高股息",
        "source": "yuanta",         # 元大投信
        "product_id": "00940",
    },
    "00713": {
        "name": "元大台灣高息低波", "category": "高股息",
        "source": "yuanta",         # 元大投信
        "product_id": "00713",
    },
    # 主動型 ETF
    "00981A": {
        "name": "統一台股增長",     "category": "主動型",
        "source": "sinotrust",      # 統一投信 — ezmoney.com.tw fundCode
        "product_id": "49YTW",
    },
    "00403A": {
        "name": "統一台股升級50",   "category": "主動型",
        "source": "sinotrust",      # 統一投信 — ezmoney.com.tw fundCode
        "product_id": "63YTW",
    },
    "00982A": {
        "name": "群益台灣強棒",     "category": "主動型",
        "source": "capital",        # 群益投信
        "product_id": "399",
    },
}

def _parse_shares(s) -> int:
    """解析股數字串 → int，容錯"""
    try:
        return int(str(s).replace(",", "").replace(" ", ""))
    except:
        return 0

def _fetch_capital_pcf(product_id: str, date_str: str = "") -> dict:
    """
    群益投信 申購買回清單 — Playwright 攔截 /api/etf/buyback（WAF 防護繞過）
    回傳 {"stocks": {stocNo: shares}, "navPerUnit": float, "totalUnits": int, "pcfDate": str}
    """
    import asyncio
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("  ✗ playwright 未安裝：pip install playwright && python -m playwright install chromium")
        return {}

    async def _run():
        captured = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            async def on_response(response):
                if "/api/etf/buyback" in response.url and response.status == 200:
                    try:
                        captured["data"] = await response.json()
                    except Exception:
                        pass

            page.on("response", on_response)
            try:
                await page.goto(
                    f"https://www.capitalfund.com.tw/etf/product/detail/{product_id}/buyback",
                    timeout=30000, wait_until="networkidle",
                )
                await asyncio.sleep(2)
            except Exception as e:
                log(f"  群益 Playwright 導航失敗 product_id={product_id}: {e}")
            finally:
                await browser.close()
        return captured.get("data")

    try:
        raw = asyncio.run(_run())
    except Exception as e:
        log(f"  群益 PCF asyncio 失敗: {e}")
        return {}

    if not raw or raw.get("code") != 200:
        log(f"  群益 PCF 回應異常 product_id={product_id}")
        return {}

    api_data  = raw.get("data", {})
    pcf_meta  = api_data.get("pcf", {})
    stocks_raw = api_data.get("stocks", [])

    stocks: dict[str, int] = {}
    for s in stocks_raw:
        code   = str(s.get("stocNo", "")).strip()
        shares = int(s.get("share") or 0)
        if code and shares > 0:
            stocks[code] = shares

    return {
        "stocks":     stocks,
        "navPerUnit": float(pcf_meta.get("pUnit") or 0),
        "totalUnits": int(pcf_meta.get("totUnit") or 0),
        "pcfDate":    str(pcf_meta.get("date1") or TODAY_AD),
    }

def _fetch_yuanta_pcf(product_id: str, date_str: str = "") -> dict:
    """
    元大投信 申購買回清單 — 解析 Nuxt SSR HTML（/tradeInfo/pcf/{productId}）
    Nuxt 壓縮的 window.__NUXT__ 函式參數表 → 解碼 StockWeights[].{code,qty}
    回傳 {"stocks": {code: shares}, "navPerUnit": float, "totalUnits": int, "pcfDate": str}
    """
    import re as _re

    url = f"https://www.yuantaetfs.com/tradeInfo/pcf/{product_id}"
    try:
        r = SESSION.get(url, timeout=25,
                        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except Exception as e:
        log(f"  元大 PCF 頁面失敗 {product_id}: {e}")
        return {}

    content = r.text
    nuxt_start = content.find("window.__NUXT__=(function(")
    if nuxt_start < 0:
        log(f"  元大 PCF 找不到 __NUXT__ {product_id}")
        return {}

    # Build variable → value mapping from Nuxt IIFE compression
    m = _re.search(r"window\.__NUXT__\s*=\s*\(function\(([^)]+?)\)\{",
                   content[nuxt_start:nuxt_start + 80000])
    if not m:
        return {}
    params = [p.strip() for p in m.group(1).split(",")]
    body_end = content.find("}(", nuxt_start + len(m.group(0)))
    args_start = body_end + 2
    depth, i = 1, args_start
    while i < len(content) and depth > 0:
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
        i += 1
    args_str = content[args_start:i - 1]

    # Parse top-level comma-separated args (handle strings/brackets)
    args, current, d2, in_s, s_ch, esc = [], "", 0, False, "", False
    for ch in args_str:
        if esc:
            current += ch; esc = False
        elif ch == "\\" and in_s:
            current += ch; esc = True
        elif in_s:
            current += ch
            if ch == s_ch:
                in_s = False
        elif ch in "\"'":
            in_s = True; s_ch = ch; current += ch
        elif ch in "([{":
            d2 += 1; current += ch
        elif ch in ")]}":
            d2 -= 1; current += ch
        elif ch == "," and d2 == 0:
            args.append(current.strip()); current = ""
        else:
            current += ch
    if current:
        args.append(current.strip())

    mapping = dict(zip(params, args))

    def decode(var: str) -> str:
        v = mapping.get(var, "")
        if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
            return v[1:-1]
        return v

    # Extract StockWeights
    block = content[nuxt_start:nuxt_start + 400000]
    entries = _re.findall(
        r"\{code:([^,}]+),ym:[^,]+,name:([^,}]+),ename:[^,}]+,weights:[\d.]+,qty:(\d+)\}",
        block
    )
    stocks: dict[str, int] = {}
    for code_var, _name_var, qty_str in entries:
        code = decode(code_var)
        if code and _re.match(r"^\d{4,5}$", code):
            stocks[code] = int(qty_str)

    if not stocks:
        log(f"  元大 PCF 無股票資料 {product_id}")
        return {}

    # NAV & PCF date from fr.PCF
    nav = 0.0
    total_units = 0
    pcf_date = TODAY_AD
    pcf_m = _re.search(r"fr\.PCF=\{([^}]+)\}", block)
    if pcf_m:
        pcf_str = pcf_m.group(1)
        nav_m = _re.search(r"nav:(\w+)", pcf_str)
        if nav_m:
            try:
                nav = float(decode(nav_m.group(1)))
            except:
                pass
        unit_m = _re.search(r"osunit:(\d+)", pcf_str)
        if unit_m:
            total_units = int(unit_m.group(1))
        date_m = _re.search(r'anndate:"(\d{8})"', pcf_str)
        if date_m:
            d = date_m.group(1)
            pcf_date = f"{d[:4]}-{d[4:6]}-{d[6:]}"

    return {"stocks": stocks, "navPerUnit": nav, "totalUnits": total_units, "pcfDate": pcf_date}

def _fetch_cathay_pcf(product_id: str, date_str: str = "") -> dict:
    """
    國泰投信 申購買回清單 — cwapi.cathaysite.com.tw (無 WAF)
    先取 Guest JWT，再呼叫 GetBuySale（NAV/units）與 GetStocksList（成分股）
    回傳 {"stocks": {code: shares}, "navPerUnit": float, "totalUnits": int, "pcfDate": str}

    注意：GetStocksList 在盤後有一段時間回傳空值，約凌晨前後才發布（次一交易日籃子）
    建議排程時間：早上 6:00-9:00（開盤前）
    """
    api_base = "https://cwapi.cathaysite.com.tw"
    hdrs = {
        "Content-Type":  "application/json",
        "Origin":        "https://www.cathaysite.com.tw",
        "User-Agent":    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }

    # 1. 取得 Guest JWT token（無需登入）
    try:
        r = SESSION.post(f"{api_base}/api/Login/GuestRegister", json={},
                         headers=hdrs, timeout=15)
        token = r.json().get("result", "")
    except Exception as e:
        log(f"  國泰 GuestRegister 失敗: {e}")
        return {}

    if token:
        hdrs["authorization"] = f"Bearer {token}"

    # 2. GetBuySale — PCF 摘要（NAV / 發行單位數 / 日期）
    nav = 0.0
    total_units = 0
    pcf_date = TODAY_AD
    try:
        r = SESSION.get(f"{api_base}/api/BuySale/GetBuySale",
                        params={"fundCode": product_id}, headers=hdrs, timeout=15)
        meta = (r.json().get("result") or {})
        try:
            nav = float(str(meta.get("nav") or 0).replace(",", ""))
        except:
            pass
        try:
            total_units = int(str(meta.get("totUnit") or 0).replace(",", ""))
        except:
            pass
        # preDateC 是發佈日（今日），date 是下一交易日
        raw_date = meta.get("preDateC") or meta.get("date") or ""
        if raw_date:
            pcf_date = raw_date.replace("/", "-")
    except Exception as e:
        log(f"  國泰 GetBuySale 失敗 product_id={product_id}: {e}")

    # 3. GetStocksList — 成分股股數（盤後發布，盤中可能為空）
    stocks: dict[str, int] = {}
    try:
        r = SESSION.get(f"{api_base}/api/BuySale/GetStocksList",
                        params={"fundCode": product_id}, headers=hdrs, timeout=15)
        items = r.json().get("result") or []
        for item in items:
            code   = str(item.get("stockCode") or item.get("StockCode") or "").strip()
            shares = _parse_shares(item.get("share") or item.get("Share") or item.get("shares") or 0)
            if code and shares > 0:
                stocks[code] = shares
    except Exception as e:
        log(f"  國泰 GetStocksList 失敗 product_id={product_id}: {e}")

    if not stocks:
        log(f"  國泰 PCF 無股票資料 product_id={product_id}（可能尚未發布）")
        return {}

    return {"stocks": stocks, "navPerUnit": nav, "totalUnits": total_units, "pcfDate": pcf_date}

def _fetch_fuhhwa_pcf(product_id: str, date_str: str = "") -> dict:
    """
    復華投信 申購買回清單 — 直接解析 SSR HTML（/ETF/etf_detail/{etfId}）
    product_id = 復華 ETF 頁面 ID，例如 "ETF21" for 00929
    回傳 {"stocks": {code: shares}, "navPerUnit": float, "totalUnits": int, "pcfDate": str}
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log("  ✗ beautifulsoup4 未安裝：pip install beautifulsoup4")
        return {}
    import re as _re

    url = f"https://www.fhtrust.com.tw/ETF/etf_detail/{product_id}"
    try:
        r = SESSION.get(url, timeout=20,
                        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except Exception as e:
        log(f"  復華 PCF 頁面取得失敗 {product_id}: {e}")
        return {}

    soup = BeautifulSoup(r.content, "html.parser")

    # 找含「股數」欄位的表格（現金申購買回清單股票部分）
    stocks: dict[str, int] = {}
    pcf_date = TODAY_AD
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "股數" not in headers or "證券代號" not in headers:
            continue
        for row in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) >= 3 and cells[0]:
                code   = cells[0].strip()
                shares = _parse_shares(cells[2])
                if code and shares > 0:
                    stocks[code] = shares
        break

    # NAV per unit
    nav = 0.0
    m = _re.search(r"每受益權單位淨資產價值[（\(]元[）\)].*?(\d[\d,\.]+)\s*<", r.text, _re.DOTALL)
    if m:
        try:
            nav = float(m.group(1).replace(",", ""))
        except:
            pass

    # Total units (基金在外流通單位數)
    total_units = 0
    m2 = _re.search(r"基金在外流通單位數.*?(\d[\d,]+)", r.text, _re.DOTALL)
    if m2:
        try:
            total_units = int(m2.group(1).replace(",", ""))
        except:
            pass

    # PCF date: first AD date in the 現金申購買回清單 section
    for section in soup.find_all("section"):
        if "現金申購買回" in section.get_text():
            dates_found = _re.findall(r"(\d{4}/\d{2}/\d{2})", str(section))
            if dates_found:
                pcf_date = dates_found[0].replace("/", "-")
            break

    if not stocks:
        log(f"  復華 PCF 無股票資料 {product_id}")
        return {}
    return {"stocks": stocks, "navPerUnit": nav, "totalUnits": total_units, "pcfDate": pcf_date}

def _fetch_sinotrust_pcf(product_id: str, date_str: str = "") -> dict:
    """
    統一投信 申購買回清單 — ezmoney.com.tw（Playwright 攔截 /ETF/Transaction/GetPCF）
    product_id 為 ezmoney fundCode（49YTW=00981A, 63YTW=00403A）
    回傳 {"stocks": {code: shares}, "navPerUnit": float, "totalUnits": int, "pcfDate": str}
    """
    import asyncio, re as _re
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("  ✗ playwright 未安裝：pip install playwright && python -m playwright install chromium")
        return {}

    async def _run():
        captured = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            async def on_response(response):
                if "/ETF/Transaction/GetPCF" in response.url and response.status == 200:
                    try:
                        captured["data"] = await response.json()
                    except Exception:
                        pass

            page.on("response", on_response)
            try:
                await page.goto(
                    f"https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode={product_id}",
                    timeout=30000, wait_until="networkidle",
                )
                await asyncio.sleep(2)
            except Exception as e:
                log(f"  統一 Playwright 導航失敗 product_id={product_id}: {e}")
            finally:
                await browser.close()
        return captured.get("data")

    def _parse_dotnet_date(s) -> str:
        """'/Date(1779724800000)/' 或 '2026-05-26T00:00:00' → '2026-05-26'（台灣時區）"""
        import datetime as _dt
        s = str(s or "")
        m = _re.search(r"/Date\((\d+)\)/", s)
        if m:
            ts = int(m.group(1)) // 1000
            d = _dt.datetime.utcfromtimestamp(ts) + _dt.timedelta(hours=8)  # Taiwan UTC+8
            return d.strftime("%Y-%m-%d")
        if "T" in s:
            return s.split("T")[0]
        return s[:10] if s else TODAY_AD

    try:
        raw = asyncio.run(_run())
    except Exception as e:
        log(f"  統一 PCF asyncio 失敗: {e}")
        return {}

    if not raw:
        log(f"  統一 PCF 無資料 product_id={product_id}")
        return {}

    # 解析 PCF 摘要
    nav = 0.0
    total_units = 0
    pcf_date = TODAY_AD
    for item in raw.get("pcf", []):
        code = item.get("PCFCode", "")
        amt  = item.get("Amount", 0) or 0
        if code == "P_UNIT":
            try:
                nav = float(amt)
            except:
                pass
        elif code == "OUT_UNIT":
            try:
                total_units = int(amt)
            except:
                pass
        if not pcf_date and item.get("TranDate"):
            pcf_date = _parse_dotnet_date(item["TranDate"])

    # 取 TranDate from first pcf item
    if raw.get("pcf"):
        tran = raw["pcf"][0].get("TranDate", "")
        if tran:
            pcf_date = _parse_dotnet_date(tran)

    # 解析成分股
    stocks: dict[str, int] = {}
    for asset in raw.get("asset", []):
        if asset.get("AssetCode") != "ST":
            continue
        for detail in asset.get("Details", []):
            code   = str(detail.get("DetailCode") or "").strip()
            shares = int(detail.get("Share") or 0)
            if code and shares > 0:
                stocks[code] = shares

    if not stocks:
        log(f"  統一 PCF 無股票資料 product_id={product_id}")
        return {}

    return {"stocks": stocks, "navPerUnit": nav, "totalUnits": total_units, "pcfDate": pcf_date}

# 正常 ETF 成分股籃子至少有幾十檔，低於這個數字視為截斷/異常回應
MIN_PCF_STOCKS = 5

def _fetch_pcf(source: str, product_id: str, date_str: str) -> dict[str, int]:
    """
    根據投信代碼分發到對應抓取函式；結果過小（含 0 檔）重試一次
    （投信官網偶爾回空，或回傳被截斷的部分內容而非真的空 —
    後者不會被 `if not stocks` 擋到，之前 00713 就曾只抓到 1 檔就被當成正常資料）
    """
    fn = {
        "capital":   _fetch_capital_pcf,
        "yuanta":    _fetch_yuanta_pcf,
        "cathay":    _fetch_cathay_pcf,
        "fuhhwa":    _fetch_fuhhwa_pcf,
        "sinotrust": _fetch_sinotrust_pcf,
    }.get(source)
    if not fn:
        return {}
    result = fn(product_id, date_str)
    if len(result.get("stocks", {})) < MIN_PCF_STOCKS:
        time.sleep(3)
        retry = fn(product_id, date_str)
        if len(retry.get("stocks", {})) >= len(result.get("stocks", {})):
            result = retry
    if 0 < len(result.get("stocks", {})) < MIN_PCF_STOCKS:
        log(f"  ⚠ {product_id} PCF 只抓到 {len(result['stocks'])} 檔，疑似截斷，視為失敗")
        return {}
    return result

def _get_close_prices(codes: list[str]) -> dict[str, float]:
    """批次取得收盤價，從 TWSE STOCK_DAY_ALL"""
    prices = {}
    try:
        data = fetch("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL") or []
        for row in data:
            code = str(row.get("Code", "")).strip()
            if code in codes:
                try:
                    prices[code] = float(str(row.get("ClosingPrice", "0")).replace(",", ""))
                except:
                    pass
    except Exception as e:
        log(f"  收盤價查詢失敗: {e}")
    return prices

def _get_stock_names(codes: list[str]) -> dict[str, str]:
    """從 TWSE 取得股票名稱"""
    names = {}
    try:
        data = fetch("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL") or []
        for row in data:
            code = str(row.get("Code", "")).strip()
            if code in codes:
                names[code] = str(row.get("Name", code)).strip()
    except:
        pass
    return names

def fetch_etf_flow() -> dict:
    """
    抓取各 ETF 申購買回清單，比對前一日差異，輸出成分股買賣超
    前日資料存在 JSS_DATA_DIR/etf-pcf-prev.json
    """
    log("ETF 成分股動態：開始抓取...")

    prev_file = JSS_DATA_DIR / "etf-pcf-prev.json"
    # prev_data: {etfCode: {"date": str, "stocks": {code: shares}}}
    prev_data: dict[str, dict] = {}
    if prev_file.exists():
        try:
            prev_data = json.loads(prev_file.read_text(encoding="utf-8"))
        except:
            pass

    today_data: dict[str, dict] = {}   # same shape as prev_data
    etf_items  = []
    all_codes  = set()

    for etf_code, cfg in ETF_CONFIG.items():
        log(f"  抓取 {etf_code} {cfg['name']}...")
        result = _fetch_pcf(cfg["source"], cfg["product_id"], TODAY_AD)
        stocks = result.get("stocks", {}) if result else {}
        if not stocks:
            log(f"  ⚠ {etf_code} PCF 無資料，略過")
            continue
        today_data[etf_code] = {
            "date":       result.get("pcfDate", TODAY_AD),
            "navPerUnit": result.get("navPerUnit", 0.0),
            "totalUnits": result.get("totalUnits", 0),
            "stocks":     stocks,
        }
        all_codes.update(stocks.keys())

    # 批次取收盤價 & 名稱
    all_codes_list = list(all_codes)
    prices = _get_close_prices(all_codes_list)
    names  = _get_stock_names(all_codes_list)

    for etf_code, cfg in ETF_CONFIG.items():
        today_entry = today_data.get(etf_code)
        if not today_entry:
            continue
        curr = today_entry["stocks"]
        prev = prev_data.get(etf_code, {}).get("stocks", {})

        # 所有出現過的股號（今日 ∪ 昨日）
        all_stock_codes = set(curr) | set(prev)
        changes = []

        for code in sorted(all_stock_codes):
            c_shares = curr.get(code, 0)
            p_shares = prev.get(code, 0)
            diff     = c_shares - p_shares
            if diff == 0:
                continue

            close      = prices.get(code, 0.0)
            diff_value = int(diff * close)

            if p_shares == 0 and c_shares > 0:
                action = "new"
            elif c_shares == 0 and p_shares > 0:
                action = "remove"
            elif diff > 0:
                action = "buy"
            else:
                action = "sell"

            total_val = sum(curr.get(cd, 0) * prices.get(cd, 0) for cd in curr)
            weight = round(c_shares * close / total_val * 100, 2) if total_val > 0 else 0.0

            changes.append({
                "code":       code,
                "name":       names.get(code, code),
                "action":     action,
                "prevShares": p_shares,
                "currShares": c_shares,
                "diffShares": diff,
                "closePrice": close,
                "diffValue":  diff_value,
                "weight":     weight,
            })

        if not changes:
            log(f"  {etf_code}: 今日無異動（與昨日相同）")
            continue

        etf_items.append({
            "etfCode":    etf_code,
            "etfName":    cfg["name"],
            "category":   cfg["category"],
            "navPerUnit": today_entry.get("navPerUnit", 0.0),
            "totalUnits": today_entry.get("totalUnits", 0),
            "changes":    changes,
        })
        log(f"  {etf_code}: {len(changes)} 筆異動")

    # 今日資料存為明日的「前日」
    if today_data:
        prev_file.write_text(json.dumps(today_data, ensure_ascii=False), encoding="utf-8")

    log(f"ETF 成分股動態：共 {len(etf_items)} 檔 ETF 有異動")
    return {"date": TODAY_AD, "data": etf_items}

# ── 統計戰報：每日快照累積成歷史序列 ─────────────────────────
HISTORY_MAX_DAYS = 30

def update_market_history(market: dict, sectors: list[dict]) -> list[dict]:
    path = JSS_DATA_DIR / "market-history.json"
    try:
        history = json.loads(path.read_text(encoding="utf-8")).get("data", [])
    except Exception:
        history = []

    top_sectors = sorted(sectors, key=lambda s: s.get("count", 0), reverse=True)[:5]
    entry = {
        "date":         TODAY_AD,
        "limitUpCount": market["limitUpCount"],
        "marketMood":   market["marketMood"],
        "taiexChange":  market["taiexChange"],
        "topSectors":   [{"name": s["name"], "count": s["count"]} for s in top_sectors],
    }

    history = [h for h in history if h.get("date") != TODAY_AD]
    history.append(entry)
    history.sort(key=lambda h: h["date"])
    history = history[-HISTORY_MAX_DAYS:]

    save("market-history.json", {"date": TODAY_AD, "data": history})
    return history

# ── 主流程 ──────────────────────────────────────────────────
def main():
    if "--etf-only" in sys.argv:
        # 國泰(cathay) PCF 要到近午夜才發布，19:00 主排程常抓不到；
        # 這個模式給隔天開盤前的第二次排程單獨補抓 ETF 成分股動態用，
        # 不動 last-updated.json（那個代表「全站」資料新鮮度）。
        log(f"=== JSS ETF-only 資料抓取開始 {TODAY_AD} ===")
        etf_flow = fetch_etf_flow()
        save("etf-flow.json", etf_flow)
        log(f"=== 完成（ETF-only）=== ETF異動ETF：{len(etf_flow['data'])} 檔")
        return

    log(f"=== JSS 資料抓取開始 {TODAY_AD} ===")
    log(f"輸出目錄：{JSS_DATA_DIR}")

    sector_map    = build_sector_map()
    insti_map     = fetch_institutional()
    all_stocks    = fetch_all_stocks(sector_map, insti_map)
    limit_stocks  = filter_limit_up(all_stocks)
    sector_stocks = build_sector_stocks(all_stocks)
    sectors       = summarize_sectors(limit_stocks)
    market        = fetch_market_summary(len(limit_stocks), len(sectors))
    notice        = fetch_notice_stocks()
    disposition   = fetch_disposition_stocks()
    cb_issuances  = fetch_cb_issuances()
    sfb_cb        = fetch_sfb_cb()
    announcements = fetch_announcements()
    etf_flow      = fetch_etf_flow()
    sector_perf   = fetch_sector_performance()

    market["noticeCount"]       = len(notice)
    market["dispositionCount"]  = len(disposition)
    market["announcementCount"] = len(announcements)
    market_history = update_market_history(market, sectors)

    # ── 寫檔 ──
    save("limit-up.json",      {"date": TODAY_AD, "data": limit_stocks})
    save("sectors.json",       {"date": TODAY_AD, "data": sectors})
    save("market-summary.json", market)
    save("notice.json",        {"date": TODAY_AD, "data": notice})
    save("disposition.json",   {"date": TODAY_AD, "data": disposition})
    cb_issuances = save_guarded("cb-watch.json", cb_issuances)
    sfb_cb       = save_guarded("sfb-cb.json",   sfb_cb)
    save("announcements.json", {"date": TODAY_AD, "data": announcements})
    save("etf-flow.json",      etf_flow)
    save("sector-performance.json", {"date": TODAY_AD, "data": sector_perf})
    save("sector-stocks.json", {"date": TODAY_AD, "data": sector_stocks})
    save("last-updated.json",  {"updatedAt": datetime.datetime.utcnow().isoformat() + "Z", "date": TODAY_AD})

    log(f"=== 完成 ===")
    log(f"  漲停：{len(limit_stocks)} 檔 | 族群：{len(sectors)} 個 | 注意：{len(notice)} 檔 | 處置：{len(disposition)} 檔 | CB詢圈：{len(cb_issuances)} 筆 | ETF異動ETF：{len(etf_flow['data'])} 檔 | 統計戰報歷史：{len(market_history)} 天")

    if HAD_CRITICAL_FAILURE:
        log("=== 有抓取異常，結束時回傳失敗（讓 Actions 顯示紅叉並寄通知信）===")
        sys.exit(1)

if __name__ == "__main__":
    main()
