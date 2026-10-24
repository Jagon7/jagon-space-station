"""
首頁摘要 → public/data/home.json（小檔，首頁 build 時直接讀）
  把散在各頁的「今天最重要的東西」整理在一起：
  pulse   大盤脈搏：加權指數、市場氣氛、風險溫度、VIX、外資現貨／期貨、漲跌停
  alerts  需要注意的警示（紅＝危險、橘＝警戒），每則附連結
  actions 明日行動：波段策略進場與出場、高週轉＋漲停觀察、國際類股龍頭與台股預估
  week    下週重點大事：明天到下週日，依日期列出央行／重要經濟數據、大型美股財報、權值股法說會、
          台指期結算、休市、月營收截止、ETF 指數審核、除權息黑K候選
要在其他 build_*.py 之後跑（讀它們的輸出）
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from build_strategy import TPE, _load

STOCK = re.compile(r"[1-9]\d{3}")
WD = "一二三四五六日"
CONF_MIN_CAP = 3e11   # 法說會：市值 ≥ 3000 億
ETF_MIN_AUM = 3e10    # ETF 指數審核：追蹤的 ETF 規模 ≥ 300 億
US_TECH = {"NVDA", "AMD", "AVGO", "MU", "AAPL", "TSLA", "SMCI", "DELL", "ASML", "MSFT", "GOOGL", "GOOG", "META", "AMZN", "INTC", "QCOM",
           "ARM", "MRVL", "TSM", "KLAC", "LRCX", "AMAT", "TER", "STX", "WDC", "SNDK", "GLW", "ANET", "APH", "CSCO", "ORCL", "CRM",
           "ADBE", "TXN", "ADI", "NXPI", "ON", "MCHP", "HPE", "HPQ", "VRT", "CRWV", "COHR", "LITE", "CIEN", "PLTR", "NET", "SONY", "IBM"}
MACRO_HI = ("Interest Rate Decision", "Non Farm Payrolls", "Inflation Rate", "Core PCE", "GDP Growth Rate QoQ Adv", "ISM Manufacturing", "Unemployment Rate")
MACRO_ZH = [  # 長的先比對
    ("Fed Interest Rate Decision", "Fed 利率決策（FOMC）"), ("Fed Press Conference", "Fed 主席記者會"), ("FOMC Minutes", "FOMC 會議紀要"),
    ("BoJ Interest Rate Decision", "日銀利率決策"), ("ECB Interest Rate Decision", "ECB 利率決策"), ("ECB Press Conference", "ECB 記者會"),
    ("Deposit Facility Rate", "ECB 存款利率"), ("PBoC", "人行利率"), ("Loan Prime Rate", "中國 LPR"),
    ("Non Farm Payrolls", "非農就業"), ("Unemployment Rate", "失業率"), ("Core Inflation Rate", "核心 CPI"), ("Inflation Rate", "CPI"),
    ("Core PCE Price Index", "核心 PCE"), ("PCE Price Index", "PCE"), ("PPI", "PPI"), ("GDP Growth Rate", "GDP"),
    ("ISM Manufacturing PMI", "ISM 製造業 PMI"), ("ISM Services PMI", "ISM 服務業 PMI"), ("NBS Manufacturing PMI", "官方製造業 PMI"),
    ("Manufacturing PMI", "製造業 PMI"), ("Services PMI", "服務業 PMI"), ("Retail Sales", "零售銷售"), ("Durable Goods Orders", "耐久財訂單"),
    ("JOLTs Job Openings", "JOLTS 職缺"), ("Michigan Consumer Sentiment", "密大消費者信心"), ("Consumer Confidence", "消費者信心"),
    ("Personal Income", "個人所得"), ("Personal Spending", "個人支出"), ("Balance of Trade", "貿易收支"), ("Exports", "出口"),
    ("Industrial Production", "工業生產"), ("Initial Jobless Claims", "初領失業金"), ("Midterm Elections", "期中選舉"), ("Elections", "選舉"),
]
FLAG = {"US": "美", "CN": "中", "JP": "日", "EU": "歐", "TW": "台"}


def macro_zh(e: dict) -> str:
    t = e["title"]
    for k, v in MACRO_ZH:
        if k in t:
            extra = " 初值" if "Flash" in t or "Prel" in t or "Adv" in t else ""
            yoy = " 年增" if "YoY" in t else " 月增" if "MoM" in t and v not in ("耐久財訂單", "零售銷售") else ""
            return f"{FLAG.get(e['country'], e['country'])} {v}{yoy if v in ('CPI', '核心 CPI', 'PCE', '核心 PCE', 'PPI') else ''}{extra}" + (f"（{e['period']}）" if e.get("period") else "")
    return f"{FLAG.get(e['country'], e['country'])} {t}" + (f"（{e['period']}）" if e.get("period") else "")


def week_events(data_dir: Path, ex: dict, today: date) -> dict:
    start = today + timedelta(days=1)
    end = today + timedelta(days=7 - today.weekday() + 6)  # 下週日
    s, e = start.isoformat(), end.isoformat()
    days: dict[str, list] = {}

    def add(d, cat, text, hi=False, href=None):
        if s <= d <= e:
            days.setdefault(d, []).append({"cat": cat, "text": text, "hi": hi, "href": href})

    holidays = set((_load(data_dir / "calendar.json", {}) or {}).get("holidays", []))
    d = start
    while d <= end:
        iso = d.isoformat()
        if d.weekday() < 5 and iso in holidays:
            add(iso, "休市", "台股休市", True)
        if d.weekday() == 2 and 15 <= d.day <= 21:
            add(iso, "結算", "台指期／台指選擇權月結算", True, "/futures")
        if d.day == 10:
            add(iso, "營收", "上市櫃月營收公布截止", False, "/revenue")
        d += timedelta(days=1)

    wk = _load(data_dir / "intel" / "week.json", {}) or {}
    seen = set()
    for m in sorted(wk.get("macro", []), key=lambda m: m["t"]):
        hi = any(k in m["title"] for k in MACRO_HI)
        txt = macro_zh(m)
        if txt in seen or (m["country"] != "US" and not hi):  # 美國以外只留央行與重要數據
            continue
            continue
        seen.add(txt)
        add(m["t"][:10], "總經", f"{m['t'][11:16]} {txt}", hi)
    names = set()
    for x in sorted(wk.get("earnings", []), key=lambda x: -x["cap"]):
        nm = re.sub(r",? (Inc\.?|Corporation|Corp\.?|Holdings|plc|N\.V\.|Company|Technologies|Technology|Incorporated|Ltd\.?)\b.*", "", x["name"] or x["sym"]).strip().removesuffix(" and").removesuffix(".com")
        if nm in names or not (x["sym"] in US_TECH or x["cap"] >= 5e11):
            continue
        names.add(nm)
        # 美股盤後公布＝台股隔天反應
        add(x["date"], "財報", f"{x['sym']} {nm}" + (f"（{x['time']}）" if x["time"] else ""), x["sym"] in US_TECH and x["cap"] >= 3e11, "/global")

    sh = (_load(data_dir / "strategy" / "shares.json", {}) or {}).get("shares", {})
    daily = sorted((data_dir / "daily").glob("20*.json"))
    q = (_load(daily[-1], {}) or {}).get("q", {}) if daily else {}
    cap = lambda c: (sh.get(c) or 0) * ((q.get(c) or [0] * 9)[5] or 0)  # noqa: E731
    ev = _load(data_dir / "fund" / "events.json", {}) or {}
    conf_seen = set()
    for r in sorted(ev.get("conf", []), key=lambda r: -cap(r[1])):
        if cap(r[1]) >= CONF_MIN_CAP and (r[0], r[1]) not in conf_seen:
            conf_seen.add((r[0], r[1]))
            add(r[0], "法說", f"{r[2].rstrip('*')} {r[1]}" + (f" {r[4]}" if r[4] else ""), cap(r[1]) >= 1e12, "/conferences")
    for u in ex.get("upcoming", []):
        if u.get("ok"):
            add(u["date"], "除息", f"{u['name']} {u['code']} 除息（黑K候選，殖利率 {u['y']:.1f}%）", False, "/exdiv")

    aum = _load(data_dir / "etf" / "aum.json", {}) or {}
    ad = (aum.get("days") or {})
    last = ad[max(ad)] if ad else {}
    size = {c: (v[1] or 0) * (v[3] or 0) for c, v in last.items()}
    for r in (_load(data_dir / "etf" / "index_schedule.json", {}) or {}).get("rows", []):
        big = [c for c in r.get("etfs", []) if size.get(c, 0) >= ETF_MIN_AUM]
        if not big and r.get("provider") != "MSCI":
            continue
        nm = r["index"].replace("臺灣指數公司", "").replace("特選臺灣上市上櫃", "").replace("指數", "").strip()
        tag = "、".join(big[:4])
        add(r["announce"], "ETF", f"{nm} 審核公告" + (f"（{tag}）" if tag else ""), r.get("provider") == "MSCI", "/etf-flow")
        if r.get("effective") != r.get("announce"):
            add(r["effective"], "ETF", f"{nm} 調整生效" + (f"（{tag}）" if tag else ""), r.get("provider") == "MSCI", "/etf-flow")

    order = {"休市": 0, "結算": 1, "總經": 2, "財報": 3, "法說": 4, "ETF": 5, "除息": 6, "營收": 7}
    out = []
    for d in sorted(days):
        items = sorted(days[d], key=lambda x: (not x["hi"], order.get(x["cat"], 9)))
        dd = date.fromisoformat(d)
        out.append({"d": d, "wd": WD[dd.weekday()], "next": dd >= today + timedelta(days=7 - today.weekday()), "items": items})
    return {"from": s, "to": e, "days": out, "src": wk.get("updatedAt")}


def build(data_dir: Path, public_dir: Path):
    P = lambda rel: _load(public_dir / rel, {}) or {}  # noqa: E731
    atm = (P("market/atmosphere.json").get("days") or [{}])[-1]
    ins = P("chips/insti.json")
    fut = P("chips/futures.json").get("rows") or []
    risk = P("risk.json")
    strat = P("strategy.json")
    tv = P("turnover.json")
    intl = P("intel/intl.json")
    short = P("market/short.json")
    rep = P("intel/reports.json")

    # ── 大盤脈搏 ──
    vix = next((i for i in risk.get("indicators", []) if i["id"] == "vix"), None)
    m = (ins.get("market") or [None])[-1]
    f0, f1 = (fut[-1] if fut else None), (fut[-2] if len(fut) > 1 else None)
    pulse = {
        "date": atm.get("d"), "ix": atm.get("ix"), "ixPct": atm.get("ixPct"), "adv": atm.get("adv"), "dec": atm.get("dec"),
        "lu": atm.get("lu"), "ld": atm.get("ld"), "mood": atm.get("score"), "moodLabel": atm.get("label"),
        "temp": risk.get("temp"), "tempLabel": risk.get("tempLabel"), "temp5": risk.get("temp5"), "riskDate": risk.get("asof"),
        "vix": vix and vix["value"], "vixChg": vix and vix["chg1"],
        "foreign": m and m[1], "trust": m and m[2], "dealer": m and m[3], "instiOfficial": bool(m and len(m) >= 8 and m[7] == 1),
        "futF": f0 and f0[2], "futFChg": (f0[2] - f1[2]) if f0 and f1 and f0[2] is not None and f1[2] is not None else None,
    }

    # ── 警示 ──
    alerts = []
    for a in risk.get("alerts", []):
        alerts.append({"level": "red" if "危險" in a or "CDS" in a else "amber", "text": a, "href": "/risk"})
    if risk.get("tempLabel") in ("偏高", "高"):
        alerts.insert(0, {"level": "red" if risk["tempLabel"] == "高" else "amber", "text": f"市場風險溫度 {risk['temp']:.0f}（{risk['tempLabel']}）", "href": "/risk"})
    cols = short.get("cols") or []
    rows = [dict(zip(cols, r)) for r in short.get("rows", []) if STOCK.fullmatch(r[0])]
    low = sorted([r for r in rows if r.get("maint") is not None and r["maint"] < 130 and (r.get("mBal") or 0) >= 500], key=lambda r: r["maint"])
    if low:
        alerts.append({"level": "red", "text": f"融資維持率 < 130%：{len(low)} 檔（{'、'.join(r['name'] for r in low[:3])}…）", "href": "/short"})
    hi = sorted([r for r in rows if (r.get("ratio") or 0) > 50 and (r.get("mBal") or 0) >= 500], key=lambda r: -r["ratio"])
    if hi:
        alerts.append({"level": "amber", "text": f"券資比 > 50%：{len(hi)} 檔（{'、'.join(r['name'] for r in hi[:3])}）", "href": "/short"})
    disp = (_load(data_dir / "disposition.json", {}) or {}).get("data") or []
    if disp:
        alerts.append({"level": "amber", "text": f"處置中 {len(disp)} 檔", "href": "/disposition"})
    # 內部人近 7 天大額申報轉讓（≥1 億）
    ii = P("insider/index.json")
    since = (date.today() - timedelta(days=7)).isoformat()
    big: dict[str, float] = {}
    names = {}
    for t in ii.get("transfers", []):
        if t[0] >= since and any(k in (t[6] or "") for k in ("一般交易", "鉅額", "盤後", "洽特定人")):
            big[t[1]] = big.get(t[1], 0) + (t[11] or 0) * (t[14] or 0)
            names[t[1]] = t[2]
    big = {c: v for c, v in big.items() if v >= 1e8}
    if big:
        top = sorted(big, key=lambda c: -big[c])[:3]
        alerts.append({"level": "amber", "text": f"內部人大額申報轉讓（近 7 天 ≥1 億）：{len(big)} 家（{'、'.join(names[c] for c in top)}）", "href": "/insider"})
    ex = P("exdiv.json")
    week = week_events(data_dir, ex, datetime.now(TPE).date())
    cand = [u for u in ex.get("upcoming", []) if u.get("ok")]
    if cand:
        tm = [u["name"] for u in cand if u.get("tomorrow")]
        alerts.append({"level": "info", "text": f"除權息黑K：未來兩週候選 {len(cand)} 檔" + (f"，明天除息 {'、'.join(tm)}" if tm else ""), "href": "/exdiv"})
    rd = rep.get("date")
    nrep = [r for r in rep.get("rows", []) if r[0] == rd and r[9] == "broker"]
    if nrep:
        alerts.append({"level": "info", "text": f"{int(rd[5:7])}/{int(rd[8:10])} 新券商報告 {len(nrep)} 份", "href": "/reports"})

    # ── 明日行動 ──
    s1, s2 = strat.get("s1") or {}, strat.get("s2") or {}
    nxt = strat.get("next")
    exits = [h for s in (s1, s2) for h in s.get("holding", []) if h.get("exitDate") == nxt]
    strategy = {"asof": strat.get("asof"), "next": nxt,
                "s1": [{"code": p["code"], "name": p["name"], "v": p["ret5"]} for p in s1.get("picks", [])[:8]], "s1n": len(s1.get("picks", [])),
                "s2": [{"code": p["code"], "name": p["name"], "v": p.get("chipZ")} for p in s2.get("picks", [])[:5]], "s2n": len(s2.get("picks", [])),
                "exits": len(exits), "exitAvg": round(sum(h["ret"] for h in exits if h.get("ret") is not None) / len(exits), 2) if exits else None}
    ref = next((s for s in tv.get("stats", []) if s["group"].strip().endswith("當天漲停")), None)
    turnover = {"asof": tv.get("asof"), "next": tv.get("next"),
                "list": [{"code": r["code"], "name": r["name"], "t": r["turnover"], "dt": r.get("dt")} for r in tv.get("alert", [])],
                "o2c": ref and ref["o2c"], "black": ref and ref["black"],
                "top": [{"code": r["code"], "name": r["name"], "t": r["turnover"]} for r in (tv.get("today") or [])[:5]]}
    groups = []
    for g in intl.get("groups", []):
        if g["name"] in ("美股大盤", "美元兌台幣"):
            continue
        q = next((x for x in g.get("quotes", []) if x["sym"] == g.get("lead")), None) or (g.get("quotes") or [None])[0]
        if q and q.get("chg") is not None:
            react = [{"name": x["name"], "exp": x["exp"]} for x in (q.get("react") or []) if abs(x.get("exp") or 0) >= 0.3][:3]
            groups.append({"name": g["name"], "sym": q["sym"], "chg": q["chg"], "react": react})
    groups.sort(key=lambda x: -abs(x["chg"]))
    us = {q["sym"]: q for g in intl.get("groups", []) for q in g.get("quotes", []) if q["sym"] in ("^SOX", "^IXIC", "^GSPC", "TSM")}
    global_ = {"date": intl.get("usDate"), "idx": [{"name": n, "chg": us[s]["chg"]} for s, n in (("^GSPC", "S&P"), ("^IXIC", "那指"), ("^SOX", "費半"), ("TSM", "TSM ADR")) if s in us],
               "groups": groups[:5]}

    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "pulse": pulse, "alerts": alerts,
           "strategy": strategy, "turnover": turnover, "global": global_, "week": week}
    (public_dir / "home.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"首頁摘要：{len(alerts)} 則警示、波段 {strategy['s1n']}+{strategy['s2n']} 檔、高週轉觀察 {len(turnover['list'])} 檔、下週大事 {sum(len(d['items']) for d in week['days'])} 項")
