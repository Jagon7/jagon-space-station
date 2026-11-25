"""
00713 元大台灣高息低波（臺灣指數公司特選高股息低波動指數）6／12 月定審預估——照編製規則與規則筆記

採樣：上市普通股，排除全額交割、KY、創新板；發行市值前 250 大
流動性（非成分股，二擇一；成分股直接通過）：近 6 個完整月成交金額中位數 > 2,000 萬元，或中位數排名屬採樣母體前 25%
指標篩選（五項都要過；名額＝通過市值與流動性者的檔數 × 比例，無條件捨去）：
  股利率＝前一完整年度現金股利 ÷ 計算日收盤價：遞減前 60% 且 < 30%
  營運穩定度＝近 8 季稅後淨利標準差 ÷ 最近一季權益：遞增前 80%（空值不過）
  權益報酬率＝最近一季稅後淨利 ÷ 權益：遞減前 80%
  價格動能＝收盤價 ÷ 252 個交易日前收盤 − 1：遞減前 90% 或 ≥ −30%（空值不過）
  股利發放品質＝近 3 個完整年度現金股利發放率平均：> 0 且 ≤ 120%
綜合分數＝RANK(股利率↓)、RANK(ROE↓)、RANK(最近一季 EPS ÷ 股價↓)、RANK(最近一季營運現金流 ÷ 市值↓)、RANK(252 日報酬標準差↑) 的平均，越小越好
選股：35 名內納入、既有 65 名後刪除、36～65 名既有優先，至多替換 15 檔，共 50 檔；同分比市值
  市值前 100 大不足 25 檔：A（準成分、>100、既有）／B（準成分、>100、非既有）換 C（非準成分、≤100、既有）／D（非準成分、≤100、非既有），
  每次選總分變動最小的組合
權重：最小變異數（252 日還原報酬共變異數），上下限：
  流動量＝min(近 20 日日均成交值, 近 6 個月日均成交值)，占比＝流動量 ÷ 合計
  上限＝min(max(min(10%, 5×占比), 2%), 既有：max(min(原權重×1.5, 10%), 1%))
  下限＝既有且上限 ≥ max(原權重×0.5, 1%) → max(原權重×0.5, 1%)；否則 max(1%, 0.2×占比)
  再依預擬規模（AUM 無條件進位到 250 億）：建倉天數＝規模×權重÷流動量；非前 100 大且建倉 > 15 天 → 發行市值 3%、自由流通 6%，
  否則 5%、10%；最終上限＝min(10%, 兩者)，超過的比例重分配
營運現金流資料：data/rebalance/raw/ocf（scripts/fetch_ocf.py）；沒有時該項排名從缺（用其餘四項平均）
"""
from __future__ import annotations

import math

from .common import NA, is_na, rank_asc, rank_desc

DEFAULT = {"n_univ": 250, "n_const": 50, "add_rank": 35, "del_rank": 65, "max_changes": 15, "top100_min": 25,
           "liq_min": 20000, "liq_top": 0.25}   # 成交金額單位：千元（2,000 萬＝20,000 千元）


def _q_prev(q: str, k: int = 1) -> str:
    y, n = int(q[:4]), int(q[-1])
    for _ in range(k):
        n -= 1
        if n == 0:
            y, n = y - 1, 4
    return f"{y}Q{n}"


def _std(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else NA


def compute(b: dict, cfg: dict | None = None) -> dict:
    c = {**DEFAULT, **(cfg or {})}
    names, old = b["names"], {k: v / 100 for k, v in b["etf"]["00713"]["weights"].items()}
    Y = int(b["asof"][:4])
    lq = b["latest_q"]
    pool = [k for k in b["universe"] if b["mkt"].get(k) == "TSE" and not b["alt"].get(k) and len(k) == 4 and k.isdigit()
            and "-KY" not in names.get(k, "") and not names.get(k, "").endswith("-創") and not is_na(b["mcap"].get(k))]
    rk = rank_desc({k: b["mcap"][k] for k in pool})
    univ = [k for k in pool if rk[k] <= c["n_univ"]]
    med = {k: b["tv6_median"].get(k, 0) for k in pool}
    rmed = rank_desc(med)
    n_top = math.floor(len(pool) * c["liq_top"])
    rows, passed = {}, []
    for k in univ:
        price = b["close"].get(k)
        liq = 1 if (k in old or med[k] > c["liq_min"] or rmed[k] <= n_top) else 0
        dv = b["div_year"].get(k, {}).get(Y - 1)
        yld = dv / price if dv is not None and price else NA
        ni = b["ni_q"].get(k, {})
        last8 = [ni.get(_q_prev(lq, i)) for i in range(8)]
        eq = b["eq_q"].get(k, {}).get(lq)
        stab = _std(last8) / eq if all(v is not None for v in last8) and eq else NA
        roe = ni.get(lq) / eq if ni.get(lq) is not None and eq else NA
        mom = b["mom"].get(k, NA)
        pay = [p / 100 for p in (b["payout"].get(k, {}).get(y) for y in (Y - 1, Y - 2, Y - 3)) if p is not None]
        payq = sum(pay) / len(pay) if len(pay) == 3 else NA
        eps = b["eps"].get(k, {}).get(lq)
        ep = eps / price if eps is not None and price else NA
        ocf = b["ocf_q"].get(k)
        ocfm = ocf / (b["mcap"][k] * 1000) if ocf is not None and b["mcap"].get(k) else NA   # 千元 ÷ 千元
        vol = b["vol252"].get(k, NA)
        rows[k] = {"code": k, "name": names.get(k, ""), "price": price, "mcap": b["mcap"][k], "mcap_rank": rk[k],
                   "exist": int(k in old), "tv6_med": med[k], "liq_ok": liq, "yield": yld, "stab": stab, "roe": roe,
                   "mom": mom, "payout3": payq, "ep": ep, "ocf_mcap": ocfm, "vol": vol}
        if liq:
            passed.append(k)
    n = len(passed)
    ry = rank_desc({k: rows[k]["yield"] for k in passed if not is_na(rows[k]["yield"])})
    rs = rank_asc({k: rows[k]["stab"] for k in passed if not is_na(rows[k]["stab"])})
    rr = rank_desc({k: rows[k]["roe"] for k in passed if not is_na(rows[k]["roe"])})
    rm = rank_desc({k: rows[k]["mom"] for k in passed if not is_na(rows[k]["mom"])})
    for k in passed:
        r = rows[k]
        r["y_ok"] = int(k in ry and ry[k] <= math.floor(n * 0.6) and r["yield"] < 0.3)
        r["stab_ok"] = int(k in rs and rs[k] <= math.floor(n * 0.8))
        r["roe_ok"] = int(k in rr and rr[k] <= math.floor(n * 0.8))
        r["mom_ok"] = int(k in rm and (rm[k] <= math.floor(n * 0.9) or r["mom"] >= -0.3))
        r["pay_ok"] = int(not is_na(r["payout3"]) and 0 < r["payout3"] <= 1.2)
        r["pass"] = int(all(r[x] for x in ("y_ok", "stab_ok", "roe_ok", "mom_ok", "pay_ok")) and not is_na(r["vol"]))
    elig = [k for k in passed if rows[k]["pass"]]
    ranks = {"yield": rank_desc({k: rows[k]["yield"] for k in elig}), "roe": rank_desc({k: rows[k]["roe"] for k in elig}),
             "ep": rank_desc({k: rows[k]["ep"] for k in elig if not is_na(rows[k]["ep"])}),
             "ocf": rank_desc({k: rows[k]["ocf_mcap"] for k in elig if not is_na(rows[k]["ocf_mcap"])}),
             "vol": rank_asc({k: rows[k]["vol"] for k in elig})}
    have_ocf = len(ranks["ocf"]) >= 0.5 * len(elig)
    for k in elig:
        parts = [ranks[x].get(k) for x in ("yield", "roe", "ep", "vol")] + ([ranks["ocf"].get(k)] if have_ocf else [])
        parts = [p if p is not None else len(elig) for p in parts]   # 缺值給最後一名
        rows[k]["score"] = sum(parts) / len(parts)
    order = sorted(elig, key=lambda k: (rows[k]["score"], -rows[k]["mcap"]))
    for i, k in enumerate(order, 1):
        rows[k]["rank"] = i
    notes = [] if have_ocf else ["營運現金流量資料還沒抓齊：綜合分數暫用其餘四項"]
    # 緩衝區
    final = [k for k in order[:c["add_rank"]]]
    for k in order[c["add_rank"]:c["del_rank"]]:
        if len(final) >= c["n_const"]:
            break
        if k in old:
            final.append(k)
    for k in order[c["add_rank"]:c["del_rank"]]:
        if len(final) >= c["n_const"]:
            break
        if k not in final:
            final.append(k)
    adds = [k for k in final if k not in old]
    if len(adds) > c["max_changes"]:
        # 註 5：優先取至多 35 檔既有成分股，非既有補滿
        ex = [k for k in order if k in old][:c["n_const"] - c["max_changes"]]
        ne = [k for k in order if k not in old][:c["n_const"] - len(ex)]
        final = ex + ne
        notes.append(f"替換超過 {c['max_changes']} 檔：取既有成分股前 {len(ex)} 檔＋非既有 {len(ne)} 檔")
    # 市值前 100 大至少 25 檔
    top100 = {k for k in pool if rk[k] <= 100}
    guard = 0
    while sum(1 for k in final if k in top100) < c["top100_min"] and guard < 50:
        guard += 1
        A = [k for k in final if k not in top100 and k in old]
        B = [k for k in final if k not in top100 and k not in old]
        C = [k for k in order if k not in final and k in top100 and k in old]
        D = [k for k in order if k not in final and k in top100 and k not in old]
        best = None
        if A and C:
            a, cc = max(A, key=lambda k: (rows[k]["score"], -rows[k]["mcap"])), min(C, key=lambda k: (rows[k]["score"], -rows[k]["mcap"]))
            best = (abs(rows[a]["score"] - rows[cc]["score"]), 0, a, cc)
        if B and D:
            bb, d = max(B, key=lambda k: (rows[k]["score"], -rows[k]["mcap"])), min(D, key=lambda k: (rows[k]["score"], -rows[k]["mcap"]))
            cand = (abs(rows[bb]["score"] - rows[d]["score"]), 1, bb, d)
            best = cand if best is None or cand < best else best
        if best is None:
            break
        final = [best[3] if k == best[2] else k for k in final]
        notes.append(f"市值前 100 大不足 {c['top100_min']} 檔：{best[2]} 換 {best[3]}")
    # 權重
    w, wrows = weights(final, rows, b, old, c)
    return {"universe": rows, "final": final, "add": [k for k in final if k not in old], "del": [k for k in old if k not in final],
            "ranked": [rows[k] for k in order], "weights": {"final": w, "rows": wrows}, "notes": notes, "config": c}


def min_variance(cov, lb, ub, iters=50000):
    """min w'Σw，sum(w)=1，lb ≤ w ≤ ub（投影梯度法；投影到「盒子 ∩ 總和＝1」用二分法找平移量）"""
    import numpy as np
    S, lo_b, hi_b = np.array(cov, float), np.array(lb, float), np.array(ub, float)
    n = len(lo_b)

    def project(v):
        lo, hi = float((v - hi_b).min()) - 1, float((v - lo_b).max()) + 1
        for _ in range(200):
            t = (lo + hi) / 2
            if np.clip(v - t, lo_b, hi_b).sum() > 1:
                lo = t
            else:
                hi = t
        return np.clip(v - (lo + hi) / 2, lo_b, hi_b)
    step = 1 / (2 * float(np.linalg.eigvalsh(S).max()) or 1.0)
    w = project(np.full(n, 1 / n))
    for _ in range(iters):
        nw = project(w - step * 2 * S @ w)
        if np.abs(nw - w).max() < 1e-13:
            w = nw
            break
        w = nw
    return [float(x) for x in w]


def weights(final, rows, b, old, c):
    liq = {k: min(v for v in (b["tv20_avg"].get(k), b["tv6_avg"].get(k)) if v) if (b["tv20_avg"].get(k) or b["tv6_avg"].get(k)) else 0
           for k in final}
    tot = sum(liq.values()) or 1
    share = {k: liq[k] / tot for k in final}
    ub, lb = {}, {}
    for k in final:
        u1 = max(min(0.10, 5 * share[k]), 0.02)
        u2 = max(min(old[k] * 1.5, 0.10), 0.01) if k in old else u1
        ub[k] = min(u1, u2)
        l1 = max(0.01, 0.2 * share[k])
        if k in old and ub[k] >= max(0.5 * old[k], 0.01):
            lb[k] = max(0.5 * old[k], 0.01)
        else:
            lb[k] = l1
        lb[k] = min(lb[k], ub[k])
    rets = {k: b["rets252"].get(k, []) for k in final}
    import numpy as np
    T = min(len(v) for v in rets.values()) if rets else 0
    cov = (np.cov(np.array([rets[k][-T:] for k in final], float)) * 252).tolist()
    w0 = min_variance(cov, [lb[k] for k in final], [ub[k] for k in final])
    w = dict(zip(final, w0))
    # 預擬規模與建倉天數上限
    aum = b["etf"]["00713"].get("aum") or 0   # 千元
    plan = math.ceil(aum / 25_000_000) * 25_000_000 if aum else 0
    cap = {}
    for k in final:
        days = plan * w[k] / liq[k] if liq[k] else 999
        small = rows[k]["mcap_rank"] > 100 and days > 15
        issue = (0.03 if small else 0.05) * rows[k]["mcap"] * 1000 / plan if plan else 1
        ins = b["insider"].get(k)
        ffm = rows[k]["mcap"] * 1000 * (1 - math.floor((ins or 0) + 1e-9) / 100)
        ff = (0.06 if small else 0.10) * ffm / plan if plan else 1
        cap[k] = min(0.10, issue, ff)
    for _ in range(200):
        over = {k: w[k] - cap[k] for k in final if w[k] > cap[k] + 1e-12}
        if not over:
            break
        free = [k for k in final if w[k] < cap[k] - 1e-12]
        fs = sum(w[k] for k in free) or 1
        ex = sum(over.values())
        for k in over:
            w[k] = cap[k]
        for k in free:
            w[k] += ex * w[k] / fs
    wrows = [{"code": k, "name": rows[k]["name"], "liq": liq[k], "liq_share": share[k], "lb": lb[k], "ub": ub[k],
              "mv": dict(zip(final, w0))[k], "cap": cap[k], "final": w[k], "old": old.get(k, 0)} for k in final]
    return w, wrows


def extras(pub, b: dict, c: dict | None = None) -> dict:
    """00713 需要的額外欄位（見檔頭說明）"""
    import json
    from collections import defaultdict
    from datetime import date
    from statistics import median, pstdev

    from .common import add_months
    basic = pub.basic()
    b["mkt"] = {k: v.get("mk") for k, v in basic.items()}
    b["alt"] = {k: v.get("alt", 0) for k, v in basic.items()}
    cum = pub.fin_cum()
    b["ni_q"] = pub.single_quarter(cum, "ni")
    b["eq_q"] = {}
    for q, doc in cum.items():
        for k, v in doc.items():
            if v.get("eq") is not None:
                b["eq_q"].setdefault(k, {})[q] = v.get("eqp") if v.get("eqp") is not None else v["eq"]
    b["latest_q"] = max(q for q, doc in cum.items() if len(doc) > 500)
    b["div_year"] = {}
    for k, d in b["div"].items():
        for (y, _q), x in d.items():
            b["div_year"].setdefault(k, {})[y] = b["div_year"].get(k, {}).get(y, 0) + (x or 0)
    days = [d for d in pub.px_days() if d <= b["asof"]]
    a = date.fromisoformat(b["asof"])
    start6 = add_months(a.replace(day=1), -5).isoformat()
    tv6 = defaultdict(list)
    for d in days:
        if d >= start6:
            for k, v in pub.px(d).items():
                tv6[k].append(v[2] or 0)
    b["tv6_median"] = {k: median(v) for k, v in tv6.items()}
    b["tv6_avg"] = {k: sum(v) / len(v) for k, v in tv6.items()}
    tv20 = defaultdict(list)
    for d in days[-20:]:
        for k, v in pub.px(d).items():
            tv20[k].append(v[2] or 0)
    b["tv20_avg"] = {k: sum(v) / len(v) for k, v in tv20.items()}
    # 252 日：價格動能（未還原）與還原日報酬（漲跌以參考價計，等同除權息還原）
    win = days[-253:]
    p0, p1 = pub.px(win[0]), pub.px(win[-1])
    b["mom"] = {k: p1[k][0] / p0[k][0] - 1 for k in p1 if k in p0 and p0[k][0] and p1[k][0]}
    rets = defaultdict(list)
    for d in win[1:]:
        for k, v in pub.px(d).items():
            chg = v[4] if len(v) > 4 else None
            if v[0] and chg is not None and (v[0] - chg):
                rets[k].append(chg / (v[0] - chg))
    b["rets252"] = dict(rets)
    b["vol252"] = {k: pstdev(r) * (len(r) / (len(r) - 1)) ** 0.5 for k, r in rets.items() if len(r) >= 126}
    # 營運現金流（單季）：data/rebalance/raw/ocf/<季>.json（累計，千元）
    lq = b["latest_q"]

    def ocf(q):
        try:
            return json.loads((pub.raw / "ocf" / f"{q}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    cur, prev = ocf(lq), ocf(_q_prev(lq))
    b["ocf_q"] = {k: (v if lq.endswith("Q1") else v - prev[k]) for k, v in cur.items()
                  if v is not None and (lq.endswith("Q1") or prev.get(k) is not None)}
    return b
