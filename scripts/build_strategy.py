"""
兩個十日波段策略 → public/data/strategy.json
  每天收盤後用「到今天為止」的資料算出明天（T）的進場名單；T 日收盤前半小時進場、持有 10 個交易日、第 11 天開盤後半小時出場。
  也用本站累積的歷史資料回算每天的訊號，列出持有中部位與已出場的績效（進場用收盤價、出場用開盤價近似）。

① 出量做多（完整依原始定義）
   前段＝T-25～T-6 共 20 日成交金額；近五日＝T-5～T-1
   放量Z＝(近五日均額－前段均額)／前段標準差 ≥ 1；近五日至少 3 天 > 前段均額＋1 個標準差
   時間量穩Z＝－(前段 CV 在 T-65～T-6 這 60 個滾動 CV 中的 z 分數)，CV＝20 日成交金額標準差／平均
   市場量穩Z＝時間量穩Z 在全市場（昨日成交金額 > 5000 萬）的標準化；兩者都 ≥ 1
   五日報酬 > 0、昨日成交金額 > 5000 萬、近 10 日沒有處置、T 日收盤不是漲停
   成交金額一律扣掉當天的鉅額交易（data/strategy/block.json）
② 輿情籌碼（公開資料代理版）
   籌碼好：近 20 日（T-21～T-2）「散戶賣超」強度高於全市場均值＋1 個標準差
           原策略用券商分點分類的散戶淨賣超；公開資料沒有分點分類，這裡用「三大法人淨買超 ＝ 散戶與其他人淨賣超」代理，
           強度＝20 日三大法人淨買超張數／20 日成交張數
   輿情好：T-1 日個股正面新聞「首次出現」（當天正面新聞數 ≥ 1 且高於前 20 日平均＋2 個標準差，前一天沒有）
           原策略用 UC 的網路輿情旗標；這裡用鉅亨網台股新聞標題的正負面字詞判斷
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

STOCK = re.compile(r"[1-9]\d{3}")
TPE = timezone(timedelta(hours=8))
COST = 0.00357  # 手續費＋證交稅 35.7bp
HOLD = 10


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _mean(xs):
    return sum(xs) / len(xs)


def _std(xs, ddof=1):
    if len(xs) <= ddof:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - ddof))


def tick(p: float) -> float:
    return 0.01 if p < 10 else 0.05 if p < 50 else 0.1 if p < 100 else 0.5 if p < 500 else 1 if p < 1000 else 5


def limit_up(prev: float) -> float:
    raw = prev * 1.1
    t = tick(raw)
    return round(math.floor(raw / t + 1e-6) * t, 2)


def next_trading_day(d: str, holidays: set) -> str:
    x = date.fromisoformat(d) + timedelta(days=1)
    while x.weekday() >= 5 or x.isoformat() in holidays:
        x += timedelta(days=1)
    return x.isoformat()


def add_trading_days(d: str, n: int, holidays: set) -> str:
    for _ in range(n):
        d = next_trading_day(d, holidays)
    return d


def build(data_dir: Path, public_dir: Path):
    files = sorted((data_dir / "daily").glob("20*.json"))
    days = []
    for f in files:
        doc = _load(f, {})
        if doc.get("q"):
            days.append((doc.get("date", f.stem), doc["q"]))
    if len(days) < 90:
        print("策略：行情資料不足 90 天，略過")
        return
    holidays = set((_load(data_dir / "calendar.json", {}) or {}).get("holidays", []))
    dates = [d for d, _ in days]
    n = len(days)  # 索引 n 代表「下一個交易日」T
    codes = sorted({c for _, q in days for c in q if STOCK.fullmatch(c)})
    names = {c: v[0] for _, q in days for c, v in q.items()}
    mkt = {c: ("上櫃" if v[1] else "上市") for c, v in days[-1][1].items()}
    # 成交金額扣掉鉅額交易（原策略用「成交金額_不含鉅額」；交易所每日行情的金額含鉅額）
    blk = (_load(data_dir / "strategy" / "block.json", {}) or {}).get("days", {})

    def net(d, c, q):
        x = (q.get(c) or [None] * 9)[8]
        if x is None:
            return None
        b = blk.get(d) or {}
        return max(0.0, x - (b.get("tw") or {}).get(c, 0) - (b.get("tp") or {}).get(c, 0))

    val = {c: [net(d, c, q) for d, q in days] for c in codes}
    close = {c: [((q.get(c) or [None] * 9)[5]) for _, q in days] for c in codes}
    opn = {c: [((q.get(c) or [None] * 9)[2]) for _, q in days] for c in codes}
    chg = {c: [((q.get(c) or [None] * 9)[6]) for _, q in days] for c in codes}
    vol = {c: [((q.get(c) or [None] * 9)[7]) for _, q in days] for c in codes}

    def ok(x):
        return x is not None and x >= 0

    # 20 日滾動 CV
    cv = {}
    for c in codes:
        v = val[c]
        arr = [None] * n
        for k in range(19, n):
            w = v[k - 19: k + 1]
            if all(ok(x) for x in w):
                m = _mean(w)
                if m > 0:
                    arr[k] = _std(w) / m
        cv[c] = arr

    # 處置期間
    disp: dict[str, list] = {}
    for c, a, b in (_load(data_dir / "strategy" / "disposition.json", {}) or {}).get("items", []):
        disp.setdefault(c, []).append((a, b))

    def disposed(c, d0, d1):
        return any(a <= d1 and b >= d0 for a, b in disp.get(c, []))

    def date_of(i):
        return dates[i] if i < n else next_trading_day(dates[-1], holidays)

    # ---------------------------------------------------------------- ① 出量做多
    def s1_at(i):
        rows = []
        for c in codes:
            v = val[c]
            if i - 85 < 0:
                return []
            win = v[i - 25: i]
            if not all(ok(x) for x in win):
                continue
            pre = v[i - 25: i - 5]
            pm, ps = _mean(pre), _std(pre)
            if pm <= 0 or ps <= 0:
                continue
            cvs = cv[c][i - 65: i - 5]
            if any(x is None for x in cvs):
                continue
            sd = _std(cvs)
            if sd <= 0:
                continue
            tz = -(cv[c][i - 6] - _mean(cvs)) / sd
            p1, p6 = close[c][i - 1], close[c][i - 6]
            if not p1 or not p6 or v[i - 1] <= 5e7:
                continue
            rows.append((c, tz, pm, ps, p1, p6))
        if len(rows) < 2:
            return []
        tzs = [r[1] for r in rows]
        mu, sg = _mean(tzs), _std(tzs, 0)
        out = []
        for c, tz, pm, ps, p1, p6 in rows:
            mz = (tz - mu) / sg if sg > 0 else 0
            if tz < 1 or mz < 1:
                continue
            v = val[c]
            rec = v[i - 5: i]
            zv = (_mean(rec) - pm) / ps
            cnt = sum(1 for x in rec if x > pm + ps)
            r5 = p1 / p6 - 1
            if zv < 1 or cnt < 3 or r5 <= 0:
                continue
            if disposed(c, dates[i - 10], dates[i - 1]):
                continue
            out.append({"code": c, "name": names.get(c, c), "mk": mkt.get(c, ""), "close": p1, "valueYi": round(v[i - 1] / 1e8, 2),
                        "zvol": round(zv, 2), "days": cnt, "tz": round(tz, 2), "mz": round(mz, 2), "ret5": round(r5 * 100, 2)})
        return sorted(out, key=lambda x: -x["zvol"])

    # ---------------------------------------------------------------- ② 輿情籌碼（代理）
    insti = {}
    for f in sorted((data_dir / "insti").glob("20*.json")):
        insti[f.stem] = {c: v[5] for c, v in (_load(f, {}) or {}).items() if not c.startswith("_")}
    news = (_load(data_dir / "intel" / "news.json", {}) or {}).get("items", [])
    di = {d: k for k, d in enumerate(dates)}
    pos = {}  # (代號, 交易日索引) → 正面新聞數；titles 留著顯示
    titles: dict[tuple, list] = {}
    first_news = None
    for nid, ts, cs, title, sc in news:
        d = datetime.fromtimestamp(ts, TPE).date().isoformat()
        while d not in di and d <= dates[-1]:  # 假日的新聞算到下一個交易日
            d = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
        if d not in di:
            continue
        k = di[d]
        first_news = k if first_news is None else min(first_news, k)
        if sc > 0:
            for c in cs:
                pos[(c, k)] = pos.get((c, k), 0) + 1
                titles.setdefault((c, k), []).append(title)

    def appear(c, k):
        if first_news is None or k - first_news < 5:  # 新聞資料還不夠，無法判斷「突然出現」
            return None
        x = pos.get((c, k), 0)
        hist = [pos.get((c, j), 0) for j in range(max(first_news, k - 20), k)]
        return x >= 1 and x > _mean(hist) + 2 * _std(hist)

    def s2_at(i):
        if i - 21 < 0:
            return []
        rows = []
        for c in codes:
            if not val[c][i - 2] or val[c][i - 2] <= 5e7:
                continue
            ks = range(i - 21, i - 1)
            if any(dates[k] not in insti or c not in insti[dates[k]] or not ok(vol[c][k]) for k in ks):
                continue
            tv = sum(vol[c][k] for k in ks)
            if tv <= 0:
                continue
            rows.append((c, sum(insti[dates[k]][c] for k in ks) / tv))
        if len(rows) < 2:
            return []
        xs = [r[1] for r in rows]
        mu, sg = _mean(xs), _std(xs, 0)
        out = []
        for c, s in rows:
            if not (s > 0 and sg > 0 and s > mu + sg):
                continue
            a1, a2 = appear(c, i - 1), appear(c, i - 2)
            if not a1 or a2 is None or a2:
                continue
            out.append({"code": c, "name": names.get(c, c), "mk": mkt.get(c, ""), "close": close[c][i - 1],
                        "valueYi": round(val[c][i - 1] / 1e8, 2) if val[c][i - 1] else None,
                        "chip": round(s * 100, 2), "chipZ": round((s - mu) / sg, 2),
                        "news": titles.get((c, i - 1), [])[:3]})
        return sorted(out, key=lambda x: -x["chipZ"])

    # ---------------------------------------------------------------- 回算、持倉、績效
    def track(fn, start):
        hist, holding = [], []
        for i in range(start, n):
            for p in fn(i):
                c = p["code"]
                e = close[c][i]
                if not e or (close[c][i - 1] and e >= limit_up(close[c][i - 1]) - 1e-6 and (chg[c][i] or 0) > 0):
                    continue  # 進場日收盤漲停買不到
                rec = {"date": dates[i], "code": c, "name": p["name"], "entry": e}
                j = i + HOLD
                if j < n and opn[c][j]:
                    rec.update({"exitDate": dates[j], "exit": opn[c][j], "ret": round((opn[c][j] / e - 1 - COST) * 100, 2)})
                    # 同期間全市場（同母體）等權平均，算超額
                    rs = [opn[x][j] / close[x][i] - 1 for x in codes if close[x][i] and opn[x][j] and val[x][i - 1] and val[x][i - 1] > 5e7]
                    rec["excess"] = round(rec["ret"] - (_mean(rs) * 100 if rs else 0), 2)
                    hist.append(rec)
                else:
                    last = close[c][n - 1]
                    rec.update({"exitDate": add_trading_days(dates[i], HOLD, holidays), "last": last,
                                "ret": round((last / e - 1) * 100, 2) if last else None, "day": n - 1 - i})
                    holding.append(rec)
        rs = [h["ret"] for h in hist]
        stats = {"n": len(rs), "avg": round(_mean(rs), 2) if rs else None, "win": round(sum(1 for r in rs if r > 0) / len(rs) * 100, 1) if rs else None,
                 "excess": round(_mean([h["excess"] for h in hist]), 2) if hist else None,
                 "from": dates[start] if start < n else None}
        return sorted(hist, key=lambda h: h["date"], reverse=True), sorted(holding, key=lambda h: h["date"], reverse=True), stats

    s1_start = 85
    s1_hist, s1_hold, s1_stats = track(s1_at, s1_start)
    s2_start = max(22, (first_news or n) + 7)
    s2_hist, s2_hold, s2_stats = track(s2_at, s2_start) if s2_start < n else ([], [], {"n": 0})
    out = {
        "asof": dates[-1], "next": date_of(n), "updatedAt": datetime.now(TPE).isoformat(timespec="minutes"),
        "newsFrom": dates[first_news] if first_news is not None else None,
        "s1": {"picks": s1_at(n), "holding": s1_hold, "history": s1_hist[:200], "stats": s1_stats},
        "s2": {"picks": s2_at(n), "holding": s2_hold, "history": s2_hist[:200], "stats": s2_stats},
    }
    (public_dir / "strategy.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"波段策略：{dates[-1]} → {out['next']}，出量做多 {len(out['s1']['picks'])} 檔（持有 {len(s1_hold)}）、"
          f"輿情籌碼 {len(out['s2']['picks'])} 檔（持有 {len(s2_hold)}）→ public/data/strategy.json")
