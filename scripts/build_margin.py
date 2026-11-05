"""
融資斷頭監控 → public/data/margin.json

推估融資成本：data/strategy/margin_seed.json（backfill_margin.py 從 2021 年底逐日重播的平均成本）當起點，
再用 data/daily 每天的融資買進／賣出／現償接著重播（新增部位以當天均價計）。沒有 seed 時從 data/daily 第一天開始（較不準）。
  推估維持率＝收盤 ÷（平均成本 × 融資成數），上市 6 成、上櫃 5 成；130% 追繳線
  追繳價＝維持率剛好 130% 的股價＝1.3 × 成本 × 成數；距追繳＝追繳價 ÷ 收盤 − 1
  融資戶損益＝收盤 ÷ 成本 − 1
  熱門股：20 日均成交值 ≥ 5 億、融資 ≥ 100 張
  判讀（近 20 日融資增減 × 股價漲跌）：追價（資增價漲）、攤平（資增價跌）、洗籌（資減價漲）、斷頭（資減價跌且維持率 < 140%）、減碼（其他資減價跌）
大盤推估維持率：全部有融資的股票，融資市值合計 ÷ 融資借款合計（上市、上櫃分開），歷史走勢接在 margin_hist.json 後面
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from build_strategy import TPE, _load

RATIO = {0: 0.6, 1: 0.5}
CALL = 130.0
HOT_VAL, HOT_BAL = 5e8, 100


def replay(days: list[dict], data_dir: Path):
    """→ (cost {代號: [平均成本, 餘額]}, 每天大盤推估維持率 [[日期, 上市, 上櫃]], 是否用了 seed)"""
    seed = _load(data_dir / "strategy" / "margin_seed.json", {}) or {}
    dates = [d["date"] for d in days]
    start = 0
    cost: dict[str, list] = {}
    used = False
    if seed.get("asof") in dates:
        cost = {c: [v[0], v[1]] for c, v in seed["cost"].items()}
        start = dates.index(seed["asof"]) + 1
        used = True
    prev_close = {c: v[5] for c, v in days[start - 1]["q"].items() if v and v[5]} if start else {}
    series = []
    for d in days[start:]:
        mm = d.get("m") or {}
        val = {0: 0.0, 1: 0.0}
        loan = {0: 0.0, 1: 0.0}
        for c, q in d["q"].items():
            if not q or not q[5]:
                continue
            pc = prev_close.get(c)
            prev_close[c] = q[5]
            st = cost.get(c)
            # 除權（配股）、減資、分割：參考價和前一天收盤差太多時，成本同比例調整（現金股利不影響維持率的借款，但參考價變動也一併套用）
            if st and pc and q[6] is not None:
                ref = q[5] - q[6]
                if ref > 0 and abs(ref / pc - 1) > 0.003:
                    st[0] *= ref / pc
            x = mm.get(c)
            if x is None:
                continue
            px = q[8] / (q[7] * 1000) if q[7] and q[8] else q[5]
            if st is None or st[1] <= 0:
                st = cost[c] = [px, x[0]]
            else:
                if len(x) >= 8 and x[5] is not None and x[6] is not None and x[7] is not None:
                    keep, buy = max(st[1] - x[6] - x[7], 0), x[5]
                else:
                    keep, buy = (st[1], x[1]) if x[1] > 0 else (st[1] + x[1], 0)
                tot = keep + buy
                st[0] = (st[0] * keep + px * buy) / tot if tot > 0 else px
                st[1] = x[0]
            if x[0] > 0 and not c.startswith("0"):
                val[q[1]] += q[5] * x[0]
                loan[q[1]] += st[0] * RATIO[q[1]] * x[0]
        if mm:
            series.append([d["date"], round(val[0] / loan[0] * 100, 1) if loan[0] else None, round(val[1] / loan[1] * 100, 1) if loan[1] else None])
    return cost, series, used


def tag(dm: float, chg: float | None, maint: float | None) -> str | None:
    if chg is None or not dm:
        return None
    if dm > 0:
        return "追價" if chg > 0 else "攤平"
    if chg > 0:
        return "洗籌"
    return "斷頭" if maint is not None and maint < 140 else "減碼"


def build(data_dir: Path, public_dir: Path):
    days = [d for d in (_load(p, {}) for p in sorted((data_dir / "daily").glob("20*.json"))) if d.get("q")]
    m_days = [d for d in days if d.get("m")]
    if not m_days:
        return
    cost, series, used = replay(days, data_dir)
    hist = (_load(data_dir / "strategy" / "margin_hist.json", {}) or {}).get("series", []) if used else []
    seen = {r[0] for r in series}
    series = [r for r in hist if r[0] not in seen] + series
    last = m_days[-1]
    li = days.index(last)
    q, mm = last["q"], last["m"]
    d20 = m_days[-21] if len(m_days) > 20 else m_days[0]
    p20 = days[max(0, li - 20)]["q"]
    rows = []
    for c, x in mm.items():
        v = q.get(c)
        st = cost.get(c)
        if not v or not v[5] or not st or not x[0]:
            continue
        mk = v[1]
        avg = st[0]
        maint = v[5] / (avg * RATIO[mk]) * 100
        call = CALL / 100 * avg * RATIO[mk]
        vals = [(dd["q"].get(c) or [0] * 9)[8] or 0 for dd in days[max(0, li - 19): li + 1]]
        aval = sum(vals) / len(vals) if vals else 0
        dm = x[0] - (d20["m"].get(c) or [0])[0]
        c20 = (p20.get(c) or [None] * 6)[5]
        chg20 = round((v[5] / c20 - 1) * 100, 1) if c20 else None
        rows.append({"code": c, "name": v[0], "mk": "上櫃" if mk else "上市", "etf": c.startswith("0"), "close": v[5],
                     "maint": round(maint, 1), "call": round(call, 2), "dist": round((call / v[5] - 1) * 100, 1),
                     "cost": round(avg, 2), "pnl": round((v[5] / avg - 1) * 100, 1), "bal": x[0], "dm20": dm,
                     "amt": round(x[0] * 1000 * v[5] / 1e8, 2), "aval": round(aval / 1e8, 2), "chg20": chg20,
                     "hot": aval >= HOT_VAL and x[0] >= HOT_BAL, "tag": tag(dm, chg20, maint)})
    rows.sort(key=lambda r: r["maint"])
    stocks = [r for r in rows if not r["etf"]]
    lt = series[-1] if series else [None, None, None]
    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "date": last["date"], "seed": used,
           "start": (_load(data_dir / "strategy" / "margin_seed.json", {}) or {}).get("start") if used else days[0]["date"],
           "market": {"tw": lt[1], "otc": lt[2], "series": series},
           "count": {"below": sum(r["maint"] < CALL for r in stocks if r["hot"]), "near": sum(CALL <= r["maint"] < 145 for r in stocks if r["hot"]),
                     "hot": sum(r["hot"] for r in stocks)},
           "rows": rows}
    (public_dir / "margin.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"融資斷頭監控：{last['date']} 大盤推估維持率 上市 {lt[1]}%、上櫃 {lt[2]}%，熱門股 {out['count']['hot']} 檔中 {out['count']['below']} 檔低於 130%"
          f"（{'有' if used else '沒有'}長期成本 seed）")
