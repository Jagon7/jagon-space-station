"""
券報、法說會、國際類股 → public/data/intel/
  reports.json  券商報告：依日期新到舊，附潛在漲幅（目標價／最新收盤）、上次目標價（文中沒寫就找同券商前一次）
  conf.json     法說會：即將舉行（MOPS 公告）＋近期已舉行（附新聞要點、AI 摘要、簡報連結、隔日股價反應）
  intl.json     國際類股：各群組美股標的最新漲跌、台股成員與實證關聯（隔日報酬相關係數、β），以及開盤可能反應清單
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOCK = re.compile(r"[1-9]\d{3}|0050")
# 泛稱（不是特定一家券商），不能拿前一筆當「上次目標價」
GENERIC = {"法人", "外資", "美系外資", "日系外資", "歐系外資", "港系外資", "陸系外資", "本土投顧", "國內投顧", "官股投顧", "大咖投顧"}


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _w(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _daily(data_dir: Path, n: int = 140):
    days = []
    for f in sorted((data_dir / "daily").glob("20*.json"))[-n:]:
        d = _load(f, {})
        if d.get("q"):
            days.append((d.get("date", f.stem), d["q"]))
    return days


# ---------------------------------------------------------------- 券報
def build_reports(data_dir: Path, out: Path, days):
    src = _load(data_dir / "intel" / "reports.json", {}) or {}
    items = src.get("items", [])
    last = days[-1][1] if days else {}
    names = {c: v[0] for c, v in last.items()}
    # 同券商同檔的上一次目標價（舊到新）
    hist: dict[tuple, list] = {}
    for r in sorted(items, key=lambda r: (r["date"], r["id"])):
        hist.setdefault((r["code"], r["broker"]), []).append(r)
    rows = []
    for r in items:
        h = hist.get((r["code"], r["broker"]), [])
        prev = r.get("prev")
        if prev is None and r["broker"] not in GENERIC:
            older = [x for x in h if x["date"] < r["date"] and x["target"] != r["target"]]
            prev = older[-1]["target"] if older else None
        px = (last.get(r["code"]) or [None] * 6)[5]
        up = round((r["target"] / px - 1) * 100, 1) if px and r.get("target") else None
        rows.append([r["date"], r["code"], names.get(r["code"], r.get("name")), r["broker"], r.get("rating"), r.get("target"), prev,
                     up, px, r["kind"], r.get("title"), r.get("points") or [], r.get("url"), r["id"]])
    rows.sort(key=lambda x: (x[0], x[9] == "broker"), reverse=True)
    # 每檔最新共識（FactSet）與近 30 天券商最高／最低目標價
    since = (date.today() - timedelta(days=30)).isoformat()
    per: dict[str, dict] = {}
    for x in rows:
        p = per.setdefault(x[1], {"name": x[2], "n": 0, "hi": None, "lo": None, "cons": None})
        if x[9] == "consensus":
            p["cons"] = p["cons"] or x[5]
        elif x[0] >= since and x[5]:
            p["n"] += 1
            p["hi"] = max(p["hi"] or x[5], x[5])
            p["lo"] = min(p["lo"] or x[5], x[5])
    _w(out / "reports.json", {"updatedAt": src.get("updatedAt"), "date": days[-1][0] if days else None,
                              "cols": ["date", "code", "name", "broker", "rating", "target", "prev", "upside", "close", "kind",
                                       "title", "points", "url", "id"],
                              "rows": rows, "per": per})
    print(f"券報：{len(rows)} 筆（券商 {sum(1 for x in rows if x[9] == 'broker')}）→ public/data/intel/reports.json")


# ---------------------------------------------------------------- 法說會
def build_conf(data_dir: Path, out: Path, days):
    ev = _load(data_dir / "fund" / "events.json", {}) or {}
    news = (_load(data_dir / "intel" / "confnews.json", {}) or {}).get("items", [])
    today = date.today().isoformat()
    dates = [d for d, _ in days]
    close = {d: {c: v[5] for c, v in q.items()} for d, q in days}

    def reaction(code: str, d: str):
        """法說當天收盤 → 下一個交易日收盤（盤後法說看隔天反應）"""
        i = next((k for k, x in enumerate(dates) if x >= d), None)
        if i is None or i + 1 >= len(dates):
            return None
        a, b = close[dates[i]].get(code), close[dates[i + 1]].get(code)
        return round((b / a - 1) * 100, 2) if a and b else None

    by_code: dict[str, list] = {}
    for n in news:
        by_code.setdefault(n["code"], []).append(n)
    rows, used = [], set()
    lo = (date.today() - timedelta(days=75)).isoformat()
    hi = (date.today() + timedelta(days=45)).isoformat()
    for r in ev.get("conf", []):
        d, code = r[0], r[1]
        if not (lo <= d <= hi):
            continue
        # 這場法說前 2 天到後 6 天的新聞（AI 摘要排前面）
        rel = [n for n in by_code.get(code, []) if (date.fromisoformat(d) - timedelta(days=2)).isoformat() <= n["date"]
               <= (date.fromisoformat(d) + timedelta(days=6)).isoformat()] if d <= today else \
              [n for n in by_code.get(code, []) if n["date"] >= (date.fromisoformat(today) - timedelta(days=7)).isoformat()]
        rel.sort(key=lambda n: (n["kind"] != "ai", n["date"]))
        used.update(n["id"] for n in rel)
        rows.append({"date": d, "code": code, "name": r[2], "mk": r[3], "time": r[4], "place": r[5], "summary": r[6],
                     "pdf": r[7] if len(r) > 7 else None, "pdfEn": r[8] if len(r) > 8 else None,
                     "react": reaction(code, d) if d < today else None,
                     "news": [{k: n[k] for k in ("date", "title", "kind", "points", "url")} for n in rel[:4]],
                     "body": next((n["body"] for n in rel if n.get("body")), "")[:5000]})
    # MOPS 沒有（例如受邀參加券商論壇、或 MOPS 抓取失敗）但有法說新聞的
    extra: dict[str, dict] = {}
    for n in sorted(news, key=lambda n: n["date"]):
        if n["id"] in used or n["date"] < lo:
            continue
        e = extra.setdefault(n["code"] + n["date"][:7], {"date": n["date"], "code": n["code"], "name": n["name"], "mk": "", "time": "",
                                                         "place": "", "summary": "", "pdf": None, "pdfEn": None,
                                                         "react": reaction(n["code"], n["date"]), "news": [], "body": ""})
        e["news"].append({k: n[k] for k in ("date", "title", "kind", "points", "url")})
        if n.get("body") and not e["body"]:
            e["body"] = n["body"][:5000]
    rows += [e for e in extra.values() if e["date"] <= today]
    rows.sort(key=lambda x: x["date"])
    _w(out / "conf.json", {"updatedAt": ev.get("updatedAt"), "today": today, "rows": rows})
    print(f"法說會：{len(rows)} 場（有要點 {sum(1 for x in rows if x['news'])}）→ public/data/intel/conf.json")


# ---------------------------------------------------------------- 國際類股
def _corr_beta(xs: list[float], ys: list[float]):
    n = len(xs)
    if n < 30:
        return None, None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return None, None
    return round(sxy / math.sqrt(sxx * syy), 2), round(sxy / sxx, 2)


def build_intl(data_dir: Path, out: Path, days):
    cfg = _load(ROOT / "config" / "intl_groups.json", {}) or {}
    us = (_load(data_dir / "intel" / "us.json", {}) or {}).get("series", {})
    if not us or not days:
        return
    # 台股每天的報酬
    dates = [d for d, _ in days]
    ret: dict[str, dict[str, float]] = {}
    val: dict[str, float] = {}
    names = {c: v[0] for c, v in days[-1][1].items()}
    for i in range(1, len(days)):
        d, q = days[i]
        pq = days[i - 1][1]
        for c, v in q.items():
            if not STOCK.fullmatch(c):
                continue
            p0 = (pq.get(c) or [None] * 6)[5]
            if p0 and v[5]:
                ret.setdefault(c, {})[d] = (v[5] / p0 - 1) * 100
    for c, v in days[-1][1].items():
        if STOCK.fullmatch(c):
            vals = [(q.get(c) or [0] * 9)[8] or 0 for _, q in days[-20:]]
            val[c] = sum(vals) / len(vals) / 1e8
    # 美股每個交易日報酬；台股 T 日對應「T 之前最後一個美股交易日」
    usret: dict[str, dict[str, float]] = {}
    for sym, rows in us.items():
        r = {}
        for k in range(1, len(rows)):
            if rows[k - 1][1]:
                r[rows[k][0]] = (rows[k][1] / rows[k - 1][1] - 1) * 100
        usret[sym] = r

    def pair(sym: str, code: str):
        ur, tr = usret.get(sym, {}), ret.get(code, {})
        ud = sorted(ur)
        xs, ys = [], []
        j = 0
        for d in dates[1:]:
            while j + 1 < len(ud) and ud[j + 1] < d:
                j += 1
            if ud and ud[j] < d and d in tr:
                xs.append(ur[ud[j]])
                ys.append(tr[d])
        return _corr_beta(xs, ys)

    liquid = [c for c, v in val.items() if v >= 3 and c in ret and not c.startswith("00")]  # 近 20 日均成交值 ≥ 3 億，不含 ETF
    groups = []
    for g in cfg.get("groups", []):
        tick = [t for t in g["tickers"] if t in us]
        if not tick:
            continue
        lead = tick[0]
        quotes = []
        for t in tick:
            s = us[t]
            last, prev = s[-1], s[-2] if len(s) > 1 else None
            p5 = s[-6] if len(s) > 5 else None
            quotes.append({"sym": t, "date": last[0], "close": last[1],
                           "chg": round((last[1] / prev[1] - 1) * 100, 2) if prev else None,
                           "chg5": round((last[1] / p5[1] - 1) * 100, 2) if p5 else None,
                           "spark": [x[1] for x in s[-30:]]})
        mem = []
        for c in g["members"]:
            co, be = pair(lead, c)
            mem.append({"code": c, "name": names.get(c, c), "corr": co, "beta": be, "member": True})
        # 實證關聯：流動性夠的股票裡相關係數最高、又不在成員名單的
        emp = []
        for c in liquid:
            if c in g["members"]:
                continue
            co, be = pair(lead, c)
            if co is not None and co >= 0.3:
                emp.append({"code": c, "name": names.get(c, c), "corr": co, "beta": be, "member": False})
        emp.sort(key=lambda x: -x["corr"])
        mem.sort(key=lambda x: -(x["corr"] or -1))
        q0 = quotes[0]
        react = sorted(([{**m, "exp": round(m["beta"] * q0["chg"], 2)} for m in mem + emp[:8]
                         if m["beta"] is not None and q0["chg"] is not None and (m["corr"] or 0) >= 0.2]),
                       key=lambda x: -abs(x["exp"]))
        groups.append({"id": g["id"], "name": g["name"], "theme": g.get("theme", ""), "threshold": g.get("threshold", 3),
                       "lead": lead, "quotes": quotes, "members": mem, "empirical": emp[:10], "react": react[:12],
                       "alert": q0["chg"] is not None and abs(q0["chg"]) >= g.get("threshold", 3)})
    us_date = max(s[-1][0] for s in us.values())
    _w(out / "intl.json", {"usDate": us_date, "twDate": dates[-1], "sessions": len(dates) - 1, "groups": groups})
    print(f"國際類股：{len(groups)} 組，美股 {us_date}，觸發 {sum(1 for g in groups if g['alert'])} 組 → public/data/intel/intl.json")


def build(data_dir: Path, public_dir: Path):
    out = public_dir / "intel"
    days = _daily(data_dir)
    build_reports(data_dir, out, days)
    build_conf(data_dir, out, days)
    build_intl(data_dir, out, days)
