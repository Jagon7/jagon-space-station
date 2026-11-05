"""
融資斷頭監控 → public/data/margin.json

推估融資成本：data/strategy/margin_seed.json（backfill_margin.py 從 2021 年底逐日重播的平均成本）當起點，
再用 data/daily 每天的融資買進／賣出／現償接著重播（新增部位以當天均價計）。沒有 seed 時從 data/daily 第一天開始（較不準）。
  推估維持率＝收盤 ÷（平均成本 × 融資成數），上市 6 成、上櫃 5 成；130% 追繳線
  追繳價＝維持率剛好 130% 的股價＝1.3 × 成本 × 成數；距追繳＝追繳價 ÷ 收盤 − 1
  融資戶損益＝收盤 ÷ 成本 − 1
  熱門股：20 日均成交值 ≥ 5 億、融資 ≥ 100 張
  判讀（近 20 日融資增減 × 股價漲跌）：追價（資增價漲）、攤平（資增價跌）、洗籌（資減價漲）、斷頭（資減價跌且維持率 < 140%）、減碼（其他資減價跌）
大盤維持率：全部有融資的股票（含 ETF）融資市值合計 ÷ 交易所公布的融資金額（上市、上櫃分開），和 toalpha、財經媒體的算法一樣；
  沒有官方金額的日子才用推估借款。歷史走勢接在 margin_hist.json 後面
個股校正：推估成本 × 校正係數 k（官方融資金額 ÷ 推估借款合計，上市、上櫃分開），讓個股加總和官方借款一致
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
    """→ (cost {代號: [平均成本, 餘額]}, 每天大盤維持率 [[日期, 上市, 上櫃]], 是否用了 seed)"""
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
            if x[0] > 0:
                val[q[1]] += q[5] * x[0] * 1000
                loan[q[1]] += st[0] * RATIO[q[1]] * x[0] * 1000
        if mm:
            off = d.get("off") or {}
            amt = {0: (off.get("twse") or {}).get("mAmt"), 1: (off.get("tpex") or {}).get("mAmt")}
            row = [d["date"]]
            for m in (0, 1):
                # 有交易所公布的融資金額就用官方：融資市值 ÷ 融資金額；沒有才用推估成本
                if amt[m] and val[m]:
                    row.append(round(val[m] / amt[m] * 100, 1))
                else:
                    row.append(round(val[m] / loan[m] * 100, 1) if loan[m] else None)
            series.append(row)
    return cost, series, used


def calib(cost: dict, days: list[dict]) -> dict:
    """校正係數 k＝官方融資金額 ÷ 推估借款合計（最近一天有融資明細和官方金額的；上市、上櫃分開）"""
    k = {0: 1.0, 1: 1.0}
    for d in reversed(days):
        off = d.get("off") or {}
        amt = {0: (off.get("twse") or {}).get("mAmt"), 1: (off.get("tpex") or {}).get("mAmt")}
        if not d.get("m") or not (amt[0] or amt[1]):
            continue
        loan = {0: 0.0, 1: 0.0}
        for c, x in d["m"].items():
            v, st = d["q"].get(c), cost.get(c)
            if v and st and x[0] > 0:
                loan[v[1]] += st[0] * RATIO[v[1]] * x[0] * 1000
        for m in (0, 1):
            if amt[m] and loan[m]:
                k[m] = amt[m] / loan[m]
        return k
    return k


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
    k = calib(cost, days)
    hist = (_load(data_dir / "strategy" / "margin_hist.json", {}) or {}).get("series", []) if used else []
    seen = {r[0] for r in series}
    series = [r for r in hist if r[0] not in seen] + series
    # 每日檔有官方融資金額的日子，一律用官方算法覆蓋：融資市值（含 ETF）÷ 融資金額
    offi = {}
    for d in m_days:
        off = d.get("off") or {}
        amt = [(off.get("twse") or {}).get("mAmt"), (off.get("tpex") or {}).get("mAmt")]
        if not (amt[0] or amt[1]):
            continue
        val = [0.0, 0.0]
        for c, x in d["m"].items():
            v = d["q"].get(c)
            if v and v[5] and x[0] > 0:
                val[v[1]] += v[5] * x[0] * 1000
        offi[d["date"]] = [round(val[m] / amt[m] * 100, 1) if amt[m] and val[m] else None for m in (0, 1)]
    for r in series:
        for i, x in enumerate(offi.get(r[0]) or []):
            if x is not None:
                r[i + 1] = x
    # 回補歷史偶有單日異常（某天 Yahoo 收盤或官方金額有誤）：只有那一天偏離前後兩天 5% 以上、前後兩天又很接近的，當成缺值
    for i in range(1, len(series) - 1):
        for j in (1, 2):
            a, x, b = series[i - 1][j], series[i][j], series[i + 1][j]
            if a and x and b and abs(b / a - 1) < 0.03 and min(abs(x / a - 1), abs(x / b - 1)) > 0.05 and series[i][0] not in offi:
                series[i][j] = None
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
        avg = st[0] * k[mk]
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
           "k": {"tw": round(k[0], 3), "otc": round(k[1], 3)},
           "start": (_load(data_dir / "strategy" / "margin_seed.json", {}) or {}).get("start") if used else days[0]["date"],
           "market": {"tw": lt[1], "otc": lt[2], "series": series},
           "count": {"below": sum(r["maint"] < CALL for r in stocks if r["hot"]), "near": sum(CALL <= r["maint"] < 145 for r in stocks if r["hot"]),
                     "hot": sum(r["hot"] for r in stocks)},
           "rows": rows}
    (public_dir / "margin.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"融資斷頭監控：{last['date']} 大盤融資維持率 上市 {lt[1]}%、上櫃 {lt[2]}%，熱門股 {out['count']['hot']} 檔中 {out['count']['below']} 檔低於 130%"
          f"（{'有' if used else '沒有'}長期成本 seed）")
