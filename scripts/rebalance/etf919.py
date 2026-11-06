"""
00919 群益台灣精選高息（特選臺灣上市上櫃精選高股息指數）12 月定期審核預估。

完全照原試算表（919___2612.xlsx）的工作表：
  919條件篩選(全版)  每檔的市值、流動性、ROE、自由流通、預估股利率
  919條件篩選        市值前 300 → 篩選 → 依預估股利率排序 → 納入／剔除
  現金股利_平攤       近四季現金股利（半年配、年配平攤到各季）
  EPS                累積前三季 EPS 成長率（第三季還沒公布時用 7~9 月營收推估）
  權重               股利率分段 × 流動性 → 上限重分配 6 輪 → 下限 0.5%

原表「最終納入／最終剔除」是人工挑的；這裡用原表欄位推得出的規則自動挑（見 select()），
人工可以在 config 的 manual 覆寫。
"""
from __future__ import annotations

from .common import (NA, apply_floor, cap_redistribute, is_na, rank_desc, trade_impact, xsum)

DEFAULT = {
    "year": 2026,              # 審核年度（12 月審核用今年前三季）
    "top_mcap": 300,           # 市值前 300 大
    "liq_new": 80000,          # 非成分股：近 6 月、近 1 月日均成交金額都要 ≥ 8000 萬（千元）
    "liq_old": 60000,          # 成分股：≥ 6000 萬
    "ff_min": 0.10,            # 自由流通 ≥ 10%
    "n_const": 40,             # 成分股檔數
    "add_rank": 20,            # 排名前 20 的非成分股納入
    "del_rank": 60,            # 排名 61 以後的成分股剔除
    "max_changes": 8,          # 每次最多換幾檔（原表：條件剔除 6 檔 + 排名剔除 2 檔 = 8）
    "top50_min": 7,            # 至少 7 檔為母體市值前 50 大
    "top150_min": 20,          # 至少 20 檔為母體市值前 150 大
    "aum_plan": 750000000,     # 預擬資產（千元），原表 7500 億
    "cap_issue": 0.06,         # 發行市值 6%
    "cap_ff": 0.15,            # 自由流通市值 15%
    "cap_max": 0.15,           # 單一成分股 15%
    "floor": 0.005,            # 下限 0.5%
    "cap_rounds": 6,           # 原表重分配做 6 輪
    "band_first": 0.15,        # 股利率第一段寬 15%
    "band_step": 0.003,        # 之後每段 0.3%
    "band_count": 127,         # 原表 IFS 寫到 BH128
    "manual": {},              # {"add": [...], "del": [...]} 人工覆寫最終名單
}


# ---------------- 近四季現金股利（現金股利_平攤） ----------------

def _cnt(*v):
    return sum(0 if is_na(x) else 1 for x in v)


def four_q_dividend(dv: dict, Y: int):
    """
    dv: {(年度, 'Q1'..'Q4'): 每股現金股利}，TEJ 口徑：半年配的上半年放 Q2、下半年放 Q4；年配放 Q4。
    回傳 (近四季現金股利, 今年 Q3 開了沒)。照原表 L~U 欄的 IFS 寫法（含 #N/A 傳染）。
    """
    g = lambda y, q: dv.get((y, q))  # noqa: E731
    B, C, D, E, F, G, H, J = g(Y, "Q1"), g(Y - 1, "Q1"), g(Y, "Q2"), g(Y - 1, "Q2"), g(Y, "Q3"), g(Y - 1, "Q3"), g(Y - 1, "Q4"), g(Y, "Q4")

    def ifs(*pairs):
        for cond, val in pairs:
            if cond:
                return val
        return NA

    # 回傳儲存格參照時，空白儲存格在 SUM 裡算 0；只有原表明寫 NA() 的才是 #N/A
    v = lambda x: 0.0 if is_na(x) else x                       # noqa: E731
    half = lambda x: v(x) / 2                                  # noqa: E731
    q4 = lambda x: NA if is_na(x) else x / 4                   # IF(ISBLANK(x)=FALSE, x/4, NA())  # noqa: E731
    L = F if not is_na(F) else NA
    M = ifs((_cnt(D, F) == 2, v(D)), (_cnt(B, D, F) == 0, q4(J)),
            (_cnt(B, F) == 0 and _cnt(D) == 1 and _cnt(J) == 0, half(D)),
            (_cnt(B, F) == 0 and _cnt(D) == 1 and _cnt(J) == 1, half(D)),
            (_cnt(B, D, F, J) == 3, v(D)), (_cnt(B, D, F, J) == 4, v(D)), (_cnt(B) == 1, v(D)), (_cnt(F) == 1, v(D)))
    N = ifs((_cnt(D, F) == 2, v(B)), (_cnt(B, D, F) == 0, q4(J)),
            (_cnt(B, F) == 0 and _cnt(D) == 1 and _cnt(J) == 0, half(D)),
            (_cnt(B, F) == 0 and _cnt(D) == 1 and _cnt(J) == 1, half(D)),
            (_cnt(B, D, F, J) == 3, v(B)), (_cnt(B, D, F, J) == 4, v(B)), (_cnt(B) == 1, v(B)), (_cnt(F) == 1, v(B)))
    O = ifs((_cnt(E, G) == 2, v(H)), (_cnt(C, E, G) == 0, q4(H)),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 0, NA),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 1, half(H)),
            (_cnt(C, E, G, H) == 3, v(H)), (_cnt(C, E, G, H) == 4, v(H)), (_cnt(C) == 1, v(H)), (_cnt(G) == 1, v(H)))
    P = ifs((_cnt(E, G) == 2, v(G)), (_cnt(C, E, G) == 0, q4(H)),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 0, NA),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 1, half(H)),
            (_cnt(C, E, G, H) == 3, v(G)), (_cnt(C, E, G, H) == 4, v(G)), (_cnt(C) == 1, v(G)), (_cnt(G) == 1, v(G)))
    Q = ifs((_cnt(E, G) == 2, v(E)), (_cnt(C, E, G) == 0, q4(H)),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 0, half(E)),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 1, half(E)),
            (_cnt(C, E, G, H) == 3, v(E)), (_cnt(C, E, G, H) == 4, v(E)), (_cnt(C) == 1, v(E)), (_cnt(G) == 1, v(E)))
    R = ifs((_cnt(E, G) == 2, v(C)), (_cnt(C, E, G) == 0, q4(H)),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 0, half(E)),
            (_cnt(C, G) == 0 and _cnt(E) == 1 and _cnt(H) == 1, half(E)),
            (_cnt(C, E, G, H) == 3, v(C)), (_cnt(C, E, G, H) == 4, v(C)), (_cnt(C) == 1, v(C)), (_cnt(G) == 1, v(C)))
    if is_na(N):
        U = xsum([O, P, Q, R])
    elif is_na(M):
        U = xsum([N, O, P, Q])
    elif is_na(L):
        U = xsum([M, N, O, P])
    else:
        U = xsum([L, M, N, O])
    return U, (0 if is_na(F) else 1)


# ---------------- 累積前三季 EPS 成長率（EPS 工作表） ----------------

def eps_growth(eps: dict, rev: dict, Y: int):
    """
    eps: {'2026Q3': 單季 EPS, ...}；rev: {'2026-09': 單月營收(千元), ...}
    回傳 (卡上下限後成長率 AD, 第三季實際 EPS AB)；無法計算回傳 ""（原表空字串）。
    """
    e = lambda q: eps.get(q)  # noqa: E731
    r = lambda m: rev.get(m)  # noqa: E731
    B, C, D = e(f"{Y}Q3"), e(f"{Y}Q2"), e(f"{Y}Q1")
    F, G, H = e(f"{Y - 1}Q3"), e(f"{Y - 1}Q2"), e(f"{Y - 1}Q1")
    I, J, K, L, M, N = (r(f"{Y}-{m:02d}") for m in (9, 8, 7, 6, 5, 4))
    O, P, Q = (r(f"{Y - 1}-{m:02d}") for m in (9, 8, 7))
    z = lambda x: 0.0 if is_na(x) else x  # noqa: E731

    # Y：第三季 EPS 推估 = (7~9 月營收) / (4~6 月營收 / Q2 EPS)
    Y3 = None
    try:
        U = abs((z(L) + z(M) + z(N)) / C)
        V = z(K)
        W = J if not is_na(J) else z(P) * (1 + z(J) / Q - 1)
        X = I if not is_na(I) else z(O) * (1 + z(J) / P - 1)
        Y3 = (V + W + X) / U
    except (TypeError, ZeroDivisionError):
        Y3 = NA
    AB = B if not is_na(B) else ""
    if z(F) + z(G) + z(H) <= 0:
        return "", AB
    den = z(F) + z(F) + z(G)   # 原表寫 SUM(F,F,G)，照抄
    try:
        if AB != "":
            AC = (z(C) + z(D) + AB) / den - 1
        else:
            if is_na(Y3):
                return "", AB
            AC = (z(C) + z(D) + Y3) / den - 1
    except ZeroDivisionError:
        return "", AB
    return max(-1.0, min(1.0, AC)), AB


def roe_4q(ni: dict, eq: dict, Y: int):
    """ROE新!L = SUM(今年 Q3、Q2、Q1 淨利) / AVERAGE(去年 Q4 淨利, 今年 Q2 權益)（照原表）。"""
    vals = [ni.get(f"{Y}Q3"), ni.get(f"{Y}Q2"), ni.get(f"{Y}Q1")]
    a, b = ni.get(f"{Y - 1}Q4"), eq.get(f"{Y}Q2")
    avg = [v for v in (a, b) if not is_na(v)]
    if not avg or sum(avg) == 0:
        return NA
    return sum(v for v in vals if not is_na(v)) / (sum(avg) / len(avg))


# ---------------- 主流程 ----------------

def compute(b: dict, cfg: dict | None = None) -> dict:
    c = {**DEFAULT, **(cfg or {})}
    Y = c["year"]
    names = b["names"]
    old = b["etf"]["00919"]["weights"]          # {code: 權重%}
    aum_k = b["etf"]["00919"]["aum"]            # 千元

    # 919條件篩選(全版)
    full = {}
    for k in b["universe"]:
        ins = b["insider"].get(k)
        ff_ok = 0 if ins is None else (0 if (1 - _rounddown(ins / 100, 2)) < 0.10 else 1)
        price, mcap = b["close"].get(k), b["mcap"].get(k)
        if is_na(price) or is_na(mcap):
            continue
        a6, a1 = b["tv6m_avg"].get(k), b["tv1m_avg"].get(k)
        mn = min(v for v in (a6, a1) if not is_na(v)) if not (is_na(a6) and is_na(a1)) else NA
        exist = 1 if k in old else 0
        if is_na(mn):
            liq = 0
        else:
            liq = 1 if (exist and mn >= c["liq_old"]) or (not exist and mn >= c["liq_new"]) else 0
        roe = roe_4q(b["ni"].get(k, {}), b["equity"].get(k, {}), Y)
        ff = NA if ins is None else 1 - _rounddown(ins / 100, 2)
        div4, q3open = four_q_dividend(b["div"].get(k, {}), Y)
        yld = 0.0 if is_na(div4) or not price else div4 / price
        g, eps_q3 = eps_growth(b["eps"].get(k, {}), b["rev"].get(k, {}), Y)
        est = "" if g == "" else yld * (1 + g)
        full[k] = {"code": k, "name": names.get(k, ""), "ff_ok": ff_ok, "price": price, "mcap": mcap,
                   "exist": exist, "tv6m": a6, "tv1m": a1, "tv_min": mn, "liq_ok": liq, "roe": roe,
                   "roe_ok": 1 if (not is_na(roe) and roe > 0) else 0, "ff": ff,
                   "ff10": 1 if (not is_na(ff) and ff >= c["ff_min"]) else 0, "div4q": div4, "q3_open": q3open,
                   "yield": yld, "eps_g": g, "eps_q3": eps_q3, "est_yield": est}

    # 919條件篩選：自由流通係數條件通過的股票裡排市值
    pool = {k: v for k, v in full.items() if v["ff_ok"] == 1}
    rk = rank_desc({k: v["mcap"] for k, v in pool.items()})
    for k in full:
        full[k]["mcap_rank"] = rk.get(k)
    th_code = next((k for k, r in rk.items() if r == c["top_mcap"]), None)
    mcap_th = pool[th_code]["mcap"] if th_code else NA
    for k, v in full.items():
        v["top300"] = 1 if (v["mcap_rank"] is not None and v["mcap_rank"] <= c["top_mcap"]) else 0
        v["pass"] = 1 if (v["top300"] and v["liq_ok"] + v["roe_ok"] + v["ff10"] == 3) else 0

    cand = [k for k in pool if full[k]["pass"] == 1 and full[k]["est_yield"] != ""]
    cand.sort(key=lambda k: -full[k]["est_yield"])          # Excel SORT 遇同值保持原順序（代號順序）
    cand = cand[:251]                                         # 原表 SORT(AD2:AE252)
    for i, k in enumerate(cand, 1):
        full[k]["yield_rank"] = i
    ranked = [{"rank": i, **{x: full[k][x] for x in ("code", "name", "est_yield", "exist", "mcap_rank", "q3_open")}}
              for i, k in enumerate(cand, 1)]

    adds, dels, notes = select(full, cand, old, c)
    final = [k for k in old if k not in dels] + adds

    weights = weigh(final, full, b, c)
    price = {k: full[k]["price"] for k in full}
    old_w = {k: v / 100 for k, v in old.items()}
    impact = trade_impact(weights["final"], old_w, aum_k * 1000, price, b["turnover1"])
    return {
        "etf": "00919", "asof": b["asof"], "config": c, "mcap_threshold": mcap_th,
        "mcap_threshold_code": th_code, "universe": full, "ranked": ranked,
        "add": adds, "del": dels, "notes": notes, "final": final, "weights": weights, "impact": impact,
    }


def _rounddown(x, n):
    f = 10 ** n
    return int(x * f) / f if x >= 0 else -int(-x * f) / f


def select(full: dict, cand: list, old: dict, c: dict):
    """
    原表欄位：
      條件剔除   = 既有成分股不在合格排序名單（AX）
      20內納入   = 非成分股、排名 1~20（AY）
      61後剔除   = 成分股、排名 > 60（AX48）
      最終納入／剔除 = 人工（AZ、BA）。原表結果：條件剔除全部剔除，再從「61後剔除」挑排名最差的補到 8 檔，
                     納入取「20內納入」排名最前面的同樣檔數。
    """
    man = c.get("manual") or {}
    if man.get("add") is not None and man.get("del") is not None:
        return list(man["add"]), list(man["del"]), ["人工覆寫"]
    rank = {k: i for i, k in enumerate(cand, 1)}
    cond_del = [k for k in old if k not in rank]
    rank_del = sorted([k for k in old if k in rank and rank[k] > c["del_rank"]], key=lambda k: -rank[k])
    add_pool = [k for k in cand if k not in old and rank[k] <= c["add_rank"]]
    notes = []
    dels = list(cond_del)
    room = max(c["max_changes"] - len(dels), 0)
    dels += rank_del[:room]
    n = min(len(dels), len(add_pool)) if len(dels) >= len(add_pool) else len(dels)
    # 成分股檔數要維持 n_const：剔除幾檔就納入幾檔；合格的新股不夠時，剔除只留條件剔除＋可遞補的
    adds = add_pool[:n]
    if len(adds) < len(dels):
        notes.append(f"20 名內新股只有 {len(add_pool)} 檔，剔除 {len(dels)} 檔，需從 21 名後遞補")
        extra = [k for k in cand if k not in old and k not in adds]
        adds += extra[: len(dels) - len(adds)]
    # 市值結構：至少 7 檔前 50 大、20 檔前 150 大（原表 BD 欄檢查，BN/BU 欄人工調整）
    final = [k for k in old if k not in dels] + adds
    n50 = sum(1 for k in final if (full.get(k, {}).get("mcap_rank") or 9999) <= 50)
    n150 = sum(1 for k in final if (full.get(k, {}).get("mcap_rank") or 9999) <= 150)
    need = max(c["top50_min"] - n50, 0, c["top150_min"] - n150)
    if need:
        notes.append(f"市值結構不足（前50大 {n50} 檔、前150大 {n150} 檔），需人工調整 {need} 檔")
    return adds, dels, notes


def weigh(final: list, full: dict, b: dict, c: dict) -> dict:
    """權重工作表。"""
    yl = {k: full[k]["est_yield"] for k in final}
    tot = sum(yl.values())
    share = {k: yl[k] / tot for k in final}
    med = {k: b["tv6m_median"].get(k) for k in final}
    top = max(yl.values())
    bands = [top, top - c["band_first"]]
    while len(bands) < c["band_count"] + 1:
        bands.append(bands[-1] - c["band_step"])
    band_of = {}
    for k in final:
        for i in range(len(bands) - 1):
            if bands[i + 1] < yl[k] <= bands[i]:
                band_of[k] = i
                break
    bw = {i: sum(share[k] for k in final if band_of.get(k) == i) for i in set(band_of.values())}
    bl = {i: sum(med[k] or 0 for k in final if band_of.get(k) == i) for i in set(band_of.values())}
    raw = {}
    for k in final:
        i = band_of.get(k)
        raw[k] = NA if i is None or not bl[i] else (med[k] or 0) / bl[i] * bw[i]
    issue = {k: full[k]["mcap"] * 1000 for k in final}                      # 千元
    ffm = {k: issue[k] * (full[k]["ff"] if not is_na(full[k]["ff"]) else 1) for k in final}
    cap = {k: min(c["cap_max"], issue[k] * c["cap_issue"] / c["aum_plan"], ffm[k] * c["cap_ff"] / c["aum_plan"])
           for k in final}
    capped = cap_redistribute(raw, cap, c["cap_rounds"])
    floored = apply_floor(capped, c["floor"])
    rows = [{"code": k, "name": full[k]["name"], "yield": yl[k], "yield_share": share[k], "tv_median": med[k],
             "band": band_of.get(k), "raw": raw[k], "issue_mcap": issue[k], "ff_mcap": ffm[k], "cap": cap[k],
             "capped": capped[k], "final": floored[k]} for k in final]
    return {"rows": rows, "final": floored, "sum": sum(floored.values()), "bands": bands}
