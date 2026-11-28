"""
空族群弱勢（當沖）→ public/data/group_weak.json

規則（scripts/research_dt_new.py 回測，2012 起三段都賺）：
  族群：MoneyDJ 產業分類併寬（scripts/theme_groups.py，例：記憶體一個族群；一檔可屬多個族群）；
        回測（+7.5% 停損、隔天開高 0～3%）比公開資訊觀測站產業別好：每筆 +0.60／+0.36／+0.30% vs +0.46／+0.17／+0.27%
        沒有 data/industry/moneydj.json 時退回公開資訊觀測站產業別
  今天：同族群有股票收漲停＝強勢股；
        同族群、前 60 天日報酬相關係數 ≥ 0.5（走勢相似）、今天漲 +2%～+9%（被帶上去、沒漲停）、成交 ≥ 5000 萬＝弱勢股
  明天：開盤 ≥ 今天收盤才放空（08:30～09:00 掛今天收盤價限價賣，開低不會成交），收盤回補；漲到今天收盤 +DT_STOP%（7.5%）停損
  不做：暫停先賣後買、明天處置中
  回測（隔天開高 0～3%）：每筆 +0.44／+0.19／+0.26%（2012-18／2019-22／2023+），勝率約 6 成；
        今天收盤就空會被隔天開盤軋（每筆約 −1%），所以要等隔天開盤
最多列 MAX 檔（成交金額大的優先）
"""
from __future__ import annotations

import json
import math
import re
import statistics as st
from datetime import datetime
from pathlib import Path

from build_strategy import DT_STOP, TPE, _load, limit_up, next_trading_day, tick
from theme_groups import groups as theme_groups

MAX = 10
CORR_MIN = 0.5
RET_LO, RET_HI = 2.0, 9.0
MIN_VAL = 5e7


def sector_map(data_dir: Path) -> dict:
    out = {}
    for fp in sorted((data_dir / "fund" / "revenue").glob("20*.json"))[-3:]:
        for c, v in (_load(fp, {}) or {}).items():
            if isinstance(v, list) and len(v) > 1 and v[1]:
                ind = re.sub(r"（.*?）|\(.*?\)", "", v[1]).strip()
                out[c] = ind[:-1] if ind.endswith("業") and len(ind) > 2 else ind
    return out


def build(data_dir: Path, public_dir: Path):
    days = []
    for f in sorted((data_dir / "daily").glob("20*.json"))[-62:]:
        doc = _load(f, {})
        if doc.get("q"):
            days.append((doc.get("date", f.stem), doc["q"]))
    if len(days) < 62:
        return
    last, q = days[-1]
    holidays = set((_load(data_dir / "calendar.json", {}) or {}).get("holidays", []))
    nxt = next_trading_day(last, holidays)
    tg = theme_groups(data_dir)
    if tg:
        mem_of: dict[str, list] = {}
        for g, cs in tg.items():
            for c in cs:
                mem_of.setdefault(c, []).append(g)
    else:
        mem_of = {c: [g] for c, g in sector_map(data_dir).items()}
    dtd = (_load(data_dir / "strategy" / "daytrade.json", {}) or {}).get("days", {})
    nox = set((dtd.get(last) or {}).get("x", []))
    disp: dict[str, list] = {}
    for c, a, b in (_load(data_dir / "strategy" / "disposition.json", {}) or {}).get("items", []):
        disp.setdefault(c, []).append((a, b))

    def rets(c):
        xs = []
        for k in range(1, len(days)):
            a, b = (days[k - 1][1].get(c) or [None] * 9)[5], (days[k][1].get(c) or [None] * 9)[5]
            xs.append((b / a - 1) if a and b else 0.0)
        return xs

    stocks = [c for c in q if len(c) == 4 and c.isdigit() and c[0] != "0" and q[c][5] and q[c][6] is not None and mem_of.get(c)]
    groups: dict[str, list] = {}
    for c in stocks:
        r = q[c]
        prev = r[5] - r[6]
        if prev <= 0:
            continue
        for g in mem_of[c]:
            groups.setdefault(g, []).append((c, r[6] / prev * 100, prev))
    cand = []
    for g, mem in groups.items():
        leaders = [(c, ret) for c, ret, prev in mem if q[c][5] >= limit_up(prev) - 1e-6 and q[c][5] >= (q[c][3] or 0) * 0.999]
        if not leaders:
            continue
        breadth = sum(ret > 0 for _, ret, _ in mem) / len(mem)
        lc = max(leaders, key=lambda x: q[x[0]][8] or 0)[0]
        lr = rets(lc)[:-1]
        for c, ret, prev in mem:
            if c == lc or not (RET_LO <= ret < RET_HI) or (q[c][8] or 0) < MIN_VAL:
                continue
            try:
                cor = st.correlation(lr, rets(c)[:-1])
            except st.StatisticsError:
                continue
            if cor < CORR_MIN:
                continue
            close = q[c][5]
            cand.append({"code": c, "name": q[c][0], "mk": "上櫃" if q[c][1] else "上市", "close": close, "ret": round(ret, 2),
                         "valYi": round((q[c][8] or 0) / 1e8, 1), "group": g, "leader": lc, "leaderName": q[lc][0], "nLU": len(leaders),
                         "breadth": round(breadth * 100), "corr": round(cor, 2),
                         "stop": round(math.floor(close * (1 + DT_STOP / 100) / tick(close * (1 + DT_STOP / 100)) + 1e-6) * tick(close * (1 + DT_STOP / 100)), 2),
                         "noShort": c in nox, "disposed": any(a <= nxt <= b or a <= last <= b for a, b in disp.get(c, []))})
    best: dict[str, dict] = {}   # 一檔屬多個族群 → 留相關係數最高的那個
    for x in cand:
        if x["code"] not in best or x["corr"] > best[x["code"]]["corr"]:
            best[x["code"]] = x
    cand = sorted(best.values(), key=lambda x: -x["valYi"])
    ok = [x for x in cand if not x["noShort"] and not x["disposed"]][:MAX]
    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "asof": last, "next": nxt,
           "rule": {"corr": CORR_MIN, "ret": [RET_LO, RET_HI], "minVal": MIN_VAL, "max": MAX}, "cand": ok, "all": cand}
    (public_dir / "group_weak.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"空族群弱勢：{last} 收盤，明天 {nxt} 候選 {len(ok)} 檔（全部 {len(cand)}）")
