"""
00918 大華優利高填息30（臺灣指數公司特選臺灣上市上櫃優選股利高填息30指數，編製規則 V1.0.0）6／12 月定審預估

選股（參、二）：
  採樣：上市＋上櫃普通股（非管理股票），發行市值前 150 大；自由流通量 ≥ 10%
  流動性（任一）：近 12 個日曆月成交金額總額前 20%；近 12 個月中至少 8 個月自由流通週轉率 ≥ 3%
  指標：近 4 季營業利益總和 > 0（金融業沒有營業利益，用稅前淨利）
  股利率＝近 4 季 EPS 總和 × 過去 3 年現金股利平均發放率（每年超出 0～1 視為 0）÷ 股價；遞減排序前 33% 為合格股票
  （⚠️ 2026-11-25 對照對方試算表：市值、成交金額門檻完全一致，填息比例 18 檔中 15 檔一致，但股利率口徑還對不上，待確認）
  合格股票（至少 3 次除息紀錄）依最近至多 15 次除息的填息比率（算法見 scripts/fetch_fill.py）遞減排序（同分再比股利率、自由流通市值），取前 30 檔
  不足 30 檔時合格門檻每次放寬 5%，最多 50%
權重（參、三）：基準權重＝股利率權重＋因子強度 100% × 因子權重 20% × 調整比例（自由流通市值相對強弱）
  調整比例：自由流通市值占比 − 1／N（規則只說「依自由流通市值相對強弱設算」，這裡用占比減平均；用對方試算表校正）
  上限：單檔 8%、不超過自由流通市值占比 5 倍（不足時逐步放寬倍數，仍不超過 8%）
資料：填息紀錄 data/rebalance/raw/fill.json（scripts/fetch_fill.py）；其他沿用 00919／00929 的公開資料
"""
from __future__ import annotations

import math

from .common import NA, cap_redistribute, is_na, rank_desc

DEFAULT = {
    "n_univ": 150, "n_const": 30, "ff_min": 0.10, "liq_top": 0.20, "ffturn_months": 8,
    "yield_top": 0.33, "fill_n": 15, "fill_min_events": 3,
    "factor_w": 0.20, "cap": 0.08, "ff_mult": 5.0,
}


def _single_quarters(cum: dict, field_idx: int) -> dict:
    """data/fund/income 累計數 → {代號: {季: 單季}}；field_idx：4 營業利益、5 稅前、7 EPS"""
    out = {}
    for q in sorted(cum):
        y, n = int(q[:4]), int(q[-1])
        for c, v in cum[q].items():
            x = v[field_idx] if v and len(v) > field_idx else None
            if x is None:
                continue
            if n == 1:
                out.setdefault(c, {})[q] = x
            else:
                pv = (cum.get(f"{y}Q{n - 1}") or {}).get(c)
                px = pv[field_idx] if pv and len(pv) > field_idx else None
                if px is not None:
                    out.setdefault(c, {})[q] = x - px
    return out


def last4(series: dict, latest: str):
    """最近 4 季（以 latest 為最新季；沒有就往前一季）總和與實際使用的最新季"""
    qs = sorted(series)
    if not qs:
        return NA, None
    end = max(q for q in qs if q <= latest) if any(q <= latest for q in qs) else None
    if end is None:
        return NA, None
    y, n = int(end[:4]), int(end[-1])
    need = []
    for _ in range(4):
        need.append(f"{y}Q{n}")
        n -= 1
        if n == 0:
            y, n = y - 1, 4
    if not all(q in series for q in need):
        return NA, end
    return sum(series[q] for q in need), end


def compute(b: dict, cfg: dict | None = None) -> dict:
    c = {**DEFAULT, **(cfg or {})}
    names, old = b["names"], b["etf"]["00918"]["weights"]
    Y = int(b["asof"][:4])
    latest_q = b["latest_q"]
    # 採樣：發行市值前 150 大
    pool = [k for k in b["universe"] if b["mkt"].get(k) in ("TSE", "OTC") and not b["alt"].get(k)
            and not is_na(b["mcap"].get(k)) and len(k) == 4 and k.isdigit()]
    rk = rank_desc({k: b["mcap"][k] for k in pool})
    univ = [k for k in pool if rk[k] <= c["n_univ"]]
    mcap_th = min(b["mcap"][k] for k in univ)
    tv = {k: b["tv12_sum"].get(k, 0) for k in univ}
    rtv = rank_desc(tv)
    n_liq = math.floor(len(univ) * c["liq_top"])
    tv_th = sorted(tv.values(), reverse=True)[n_liq - 1] if n_liq else NA
    rows = {}
    for k in univ:
        price = b["close"].get(k)
        ins = b["insider"].get(k)
        ff = NA if ins is None else 1 - math.floor(ins + 1e-9) / 100
        oi, oi_q = last4(b["oi_q"].get(k, {}), latest_q)
        if is_na(oi):
            oi, oi_q = last4(b["pti_q"].get(k, {}), latest_q)
        eps4, eps_q = last4(b["eps"].get(k, {}) or b["eps_q"].get(k, {}), latest_q)   # b["eps"]：正式財報＋金控自結數
        # 規則筆記：過去 3 年現金股利發放率，每年超出 0～1 的視為 0；12 月審核取去年往前 3 年（2026/12 → 2023～2025）
        pay = [p / 100 for p in (b["payout"].get(k, {}).get(y) for y in (Y - 1, Y - 2, Y - 3)) if p is not None]
        pay = [p if 0 <= p <= 1 else 0.0 for p in pay]
        payout = sum(pay) / len(pay) if pay else NA
        yld = NA if (is_na(eps4) or is_na(payout) or not price) else eps4 * payout / price
        ev = (b["fill"].get(k) or [])[-c["fill_n"]:]
        fill = sum(e[2] for e in ev) / len(ev) if len(ev) >= c["fill_min_events"] else NA
        liq = 1 if (rtv[k] <= n_liq or b["ffturn_n"].get(k, 0) >= c["ffturn_months"]) else 0
        ok = 1 if (not is_na(ff) and ff >= c["ff_min"] and liq and not is_na(oi) and oi > 0 and not is_na(yld)) else 0
        rows[k] = {"code": k, "name": names.get(k, ""), "price": price, "mcap": b["mcap"][k], "mcap_rank": rk[k],
                   "ff": ff, "ff_mcap": (b["mcap"][k] * ff) if not is_na(ff) else NA, "tv12": tv[k], "tv12_rank": rtv[k],
                   "ffturn_n": b["ffturn_n"].get(k, 0), "liq_ok": liq, "oi4": oi, "fin_q": oi_q, "q_open": int(oi_q == latest_q),
                   "eps4": eps4, "payout3": payout, "yield": yld, "fill": fill, "fill_n": len(ev), "exist": int(k in old),
                   "pass": ok}
    passed = [k for k in univ if rows[k]["pass"]]
    ry = rank_desc({k: rows[k]["yield"] for k in passed})
    for k in passed:
        rows[k]["yield_rank"] = ry[k]
    final, top, notes = [], c["yield_top"], []
    while True:
        n_q = math.ceil(len(passed) * top)
        qual = [k for k in passed if ry[k] <= n_q and not is_na(rows[k]["fill"])]
        qual.sort(key=lambda k: (-rows[k]["fill"], -rows[k]["yield"], -(rows[k]["ff_mcap"] or 0)))
        final = qual[:c["n_const"]]
        if len(final) >= c["n_const"] or top >= 0.5:
            break
        top = round(top + 0.05, 2)
        notes.append(f"合格股票不足 30 檔：股利率門檻放寬到前 {top:.0%}")
    y_th = min(rows[k]["yield"] for k in passed if ry[k] <= math.ceil(len(passed) * top)) if passed else NA
    for i, k in enumerate(final, 1):
        rows[k]["sel_rank"] = i
    # 權重
    N = len(final)
    ys = {k: rows[k]["yield"] for k in final}
    ffm = {k: rows[k]["ff_mcap"] for k in final}
    yw = {k: v / sum(ys.values()) for k, v in ys.items()}
    fw = {k: v / sum(ffm.values()) for k, v in ffm.items()}
    base = {k: max(0.0, yw[k] + c["factor_w"] * (fw[k] - 1 / N)) for k in final}
    tot = sum(base.values())
    base = {k: v / tot for k, v in base.items()}
    mult = c["ff_mult"]
    while True:
        cap = {k: min(c["cap"], mult * fw[k]) for k in final}
        if sum(cap.values()) >= 1 or mult > 100:
            break
        mult += 1
    if mult != c["ff_mult"]:
        notes.append(f"上限無法滿足：自由流通市值倍數放寬到 {mult:g} 倍")
    w = cap_redistribute(base, cap, 200)
    wrows = [{"code": k, "name": names.get(k, ""), "yield": ys[k], "yield_w": yw[k], "ff_w": fw[k], "base": base[k],
              "cap": cap[k], "final": w[k]} for k in final]
    return {"universe": rows, "final": final, "add": [k for k in final if k not in old], "del": [k for k in old if k not in final],
            "weights": {"final": w, "rows": wrows}, "notes": notes,
            "thresholds": {"mcap": mcap_th, "tv12": tv_th, "ffturn": c["ffturn_months"], "yield": y_th, "yield_top": top},
            "config": c}


def extras(pub, b: dict, c: dict | None = None) -> dict:
    """00918 需要的額外欄位：單季營業利益／稅前淨利／EPS、近 12 個日曆月成交金額、自由流通週轉率 ≥ 3% 的月數、填息紀錄"""
    import json
    from collections import defaultdict
    from datetime import date

    from .common import add_months
    c = {**DEFAULT, **(c or {})}
    basic = pub.basic()
    b["mkt"] = {k: v.get("mk") for k, v in basic.items()}
    b["alt"] = {k: v.get("alt", 0) for k, v in basic.items()}
    cum = {}
    for p in (pub.d / "fund" / "income").glob("20*Q*.json"):
        cum[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    b["oi_q"], b["pti_q"], b["eps_q"] = _single_quarters(cum, 4), _single_quarters(cum, 5), _single_quarters(cum, 7)
    b["latest_q"] = max(cum)
    days = [d for d in pub.px_days() if d <= b["asof"]]
    a = date.fromisoformat(b["asof"])
    # 近 12 個「日曆月」：資料日往前 12 個月（同 00929 的 TEJ 口徑：從 11 個月前的 1 號起）
    start = add_months(a.replace(day=1), -11).isoformat()
    tv = defaultdict(float)
    for d in days:
        if d >= start:
            for k, v in pub.px(d).items():
                tv[k] += v[2] or 0
    b["tv12_sum"] = dict(tv)
    # 自由流通週轉率：近 12 個完整月，每月成交量 ÷ (自由流通量 × 發行股數)
    months = []
    y, m = a.year, a.month
    for _ in range(12):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        months.append(f"{y}-{m:02d}")
    mv = defaultdict(lambda: defaultdict(float))
    for d in days:
        if d[:7] in months:
            for k, v in pub.px(d).items():
                mv[k][d[:7]] += v[1] or 0
    b["ffturn_n"] = {}
    for k, per in mv.items():
        sh, ins = basic.get(k, {}).get("sh"), b["insider"].get(k)
        if not sh or ins is None:
            continue
        ffs = (1 - math.floor(ins + 1e-9) / 100) * sh
        b["ffturn_n"][k] = sum(1 for mo in months if ffs and per.get(mo, 0) / ffs >= 0.03)
    try:
        b["fill"] = json.loads((pub.raw / "fill.json").read_text(encoding="utf-8")).get("d", {})
    except (OSError, ValueError):
        b["fill"] = {}
    return b
