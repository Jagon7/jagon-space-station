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

from .common import (NA, xl, aum_plan_auto, apply_floor, buffer_select, cap_redistribute, is_na, rank_desc,
                     trade_impact, xsum)

DEFAULT = {
    "year": 2026,              # 審核年度（12 月審核用今年前三季）
    "top_mcap": 300,           # 市值前 300 大
    "liq_new": 80000,          # 非成分股：近 6 月、近 1 月日均成交金額都要 ≥ 8000 萬（千元）
    "liq_old": 60000,          # 成分股：≥ 6000 萬
    "ff_min": 0.10,            # 自由流通 ≥ 10%
    "n_const": 40,             # 成分股檔數
    "add_rank": 20,            # 排名前 20 的非成分股納入
    "del_rank": 60,            # 排名 61 以後的成分股剔除
    "max_changes": 8,          # 12 月定審至多替換 8 檔（編製規則 伍、一、2）
    "december": True,          # 12 月定審（5 月定審沒有替換上限，且用股利率而非預估股利率）
    "top5_max": 0.65,          # 前五大權重合計上限
    "liq_min_count": 150,      # 流動性檢驗通過不足 150 檔時，依日均成交金額指標補齊
    "official": True,          # True：照編製規則（含註 5 上限無法滿足時降預擬規模、重分配到收斂）；False：照原試算表（6 輪）
    "top50_min": 7,            # 至少 7 檔為母體市值前 50 大
    "top150_min": 20,          # 至少 20 檔為母體市值前 150 大
    "aum_plan": "auto",        # 預擬資產（千元）："auto"＝AUM×1.2 無條件進位到 250 億；原表填 750000000
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
    if c["aum_plan"] == "auto":
        c["aum_plan"] = aum_plan_auto(aum_k)

    # 919條件篩選(全版)
    full = {}
    for k in b["universe"]:
        ins = b["insider"].get(k)
        ff_ok = 0 if ins is None else (0 if xl(1 - _rounddown(ins / 100, 2)) < 0.10 else 1)
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
                   "ff10": 1 if (not is_na(ff) and xl(ff) >= c["ff_min"]) else 0, "div4q": div4, "q3_open": q3open,
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
    if c.get("official"):
        # 流動性檢驗通過不足 150 檔時，依日平均成交金額指標由大到小補齊
        top = [k for k, v in full.items() if v["top300"]]
        ok = [k for k in top if full[k]["liq_ok"]]
        if len(ok) < c["liq_min_count"]:
            rest = sorted((k for k in top if not full[k]["liq_ok"] and not is_na(full[k]["tv_min"])),
                          key=lambda k: -full[k]["tv_min"])
            for k in rest[: c["liq_min_count"] - len(ok)]:
                full[k]["liq_ok"] = 1
    for k, v in full.items():
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
        "add": adds, "del": dels, "notes": notes + weights["notes"], "final": final, "weights": weights, "impact": impact,
    }


def _rounddown(x, n):
    f = 10 ** n
    return int(x * f) / f if x >= 0 else -int(-x * f) / f


def select(full: dict, cand: list, old: dict, c: dict):
    """
    臺灣精選高息指數編製規則 伍、一、2（V1.2.0）：
      排名 ≤ 20 納入；既有成分股排名 > 60 刪除；21~60 名既有成分股優先、依排名補滿 40 檔；
      12 月定審至多替換 8 檔（超過時依預估股利率取既有成分股至多 32 檔＋非既有補滿 40 檔，註 7）；
      再檢查至少 7 檔屬母體發行市值前 50 大、20 檔屬前 150 大，不足時在維持替換檔數下換股（註 7）。
    （原試算表的 AY「20內納入」、AX「61後剔除」、AZ／BA 人工挑選，就是這個程序的結果。）
    """
    man = c.get("manual") or {}
    if man.get("add") is not None and man.get("del") is not None:
        return list(man["add"]), list(man["del"]), ["人工覆寫"]
    final, notes = buffer_select(cand, old, c["n_const"], c["add_rank"], c["del_rank"],
                                 c["max_changes"] if c.get("december", True) else None)
    rank = {k: i for i, k in enumerate(cand, 1)}
    mr = lambda k: full.get(k, {}).get("mcap_rank") or 9999  # noqa: E731
    # 市值結構（原表 BH~BS 欄）：剔除「準成分股中非既有」裡市值排名最後的，換入「1~60 名非準成分股」裡市值最大的
    for top, need in ((50, c["top50_min"]), (150, c["top150_min"])):
        while sum(1 for k in final if mr(k) <= top) < need:
            ins = sorted((k for k in cand[: c["del_rank"]] if k not in final and mr(k) <= top), key=mr)
            swapped = False
            for x in ins:   # 維持替換檔數：同為既有／非既有之間互換
                outs = [k for k in final if mr(k) > top and (k in old) == (x in old)]
                if outs:
                    y = max(outs, key=mr)
                    final[final.index(y)] = x
                    notes.append(f"市值前 {top} 大不足 {need} 檔：以 {x}（市值第 {mr(x)} 名）替換 {y}（第 {mr(y)} 名）")
                    swapped = True
                    break
            if not swapped:
                notes.append(f"市值前 {top} 大不足 {need} 檔，且無可替換股票")
                break
    final.sort(key=lambda k: rank[k])
    adds = [k for k in final if k not in old]
    dels = [k for k in old if k not in final]
    return adds, dels, notes


def _caps(final, issue, ffm, c, plan):
    return {k: min(c["cap_max"], issue[k] * c["cap_issue"] / plan, ffm[k] * c["cap_ff"] / plan) for k in final}


def weigh(final: list, full: dict, b: dict, c: dict) -> dict:
    """權重工作表。"""
    yl = {k: full[k]["est_yield"] for k in final}
    tot = sum(v for v in yl.values() if v not in ("", None))
    if not final or not tot:   # 資料不足（例如歷史資料還在補）時不算權重
        return {"rows": [], "final": {}, "sum": 0.0, "bands": [], "aum_plan": c["aum_plan"],
                "notes": ["沒有可計算權重的成分股（資料不足）"]}
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
    plan = c["aum_plan"]
    cap = _caps(final, issue, ffm, c, plan)
    notes = []
    if c.get("official") and sum(cap.values()) < 1:
        # 註 5：無法滿足 b 時，改用可滿足 b 的「預擬資產管理規模」最大值
        lo, hi = 1.0, plan
        for _ in range(100):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if sum(_caps(final, issue, ffm, c, mid).values()) >= 1 else (lo, mid)
        plan = lo
        cap = _caps(final, issue, ffm, c, plan)
        notes.append(f"上限無法滿足，預擬資產管理規模改為 {plan / 1e5:,.0f} 億元")
    capped = cap_redistribute(raw, cap, c["cap_rounds"] if not c.get("official") else 200)
    if c.get("official"):
        # 前五大權重合計不得超過 65%：超過部分依其餘成分股權重比例分配
        top5 = sorted(capped, key=lambda k: -capped[k])[:5]
        t5 = sum(capped[k] for k in top5)
        if t5 > c["top5_max"]:
            f = c["top5_max"] / t5
            rest = [k for k in capped if k not in top5]
            rs = sum(capped[k] for k in rest)
            extra = t5 - c["top5_max"]
            capped = {k: (capped[k] * f if k in top5 else capped[k] + extra * capped[k] / rs) for k in capped}
            notes.append("前五大權重超過 65%，已等比例調降")
    floored = apply_floor(capped, c["floor"])
    rows = [{"code": k, "name": full[k]["name"], "yield": yl[k], "yield_share": share[k], "tv_median": med[k],
             "band": band_of.get(k), "raw": raw[k], "issue_mcap": issue[k], "ff_mcap": ffm[k], "cap": cap[k],
             "capped": capped[k], "final": floored[k]} for k in final]
    return {"rows": rows, "final": floored, "sum": sum(floored.values()), "bands": bands, "aum_plan": plan,
            "notes": notes}


# ======================================================================
# 5 月定審（原試算表 919___2606）：用「股利率」而非「預估股利率」，另有除息／季配 0 的排除條件
# ======================================================================

def four_q_dividend_may(dv: dict, Y: int):
    """
    原表 6 月版「現金股利_平攤」：B=去年Q1、C=前年Q1、D=去年Q2、E=前年Q2、F=去年Q3、G=前年Q3、
    H=去年Q4（含年配）、I=前年Q4、J=今年Q1。回傳 (近四季現金股利 U, 去年 Q4 股利開了沒 K)。
    （P 欄第一個條件取 C＝前年 Q1，照原表。）
    """
    g = lambda y, q: dv.get((y, q))  # noqa: E731
    B, C, D, F, H, J = g(Y - 1, "Q1"), g(Y - 2, "Q1"), g(Y - 1, "Q2"), g(Y - 1, "Q3"), g(Y - 1, "Q4"), g(Y, "Q1")
    v = lambda x: 0.0 if is_na(x) else x  # noqa: E731
    q4 = lambda x: NA if is_na(x) else x / 4  # noqa: E731

    def ifs(*pairs):
        for cond, val in pairs:
            if cond:
                return val
        return NA
    L = J if not is_na(J) else NA
    head = lambda first, mid_na, half: (  # noqa: E731
        (_cnt(D, F) == 2, first), (_cnt(B, D, F) == 0, q4(H)),
        (_cnt(B, F) == 0 and _cnt(D) == 1 and _cnt(H) == 0, mid_na),
        (_cnt(B, F) == 0 and _cnt(D) == 1 and _cnt(H) == 1, half))
    tail = lambda val: ((_cnt(B, D, F, H) == 3, val), (_cnt(B, D, F, H) == 4, val), (_cnt(B) == 1, val),  # noqa: E731
                        (_cnt(F) == 1, val))
    M = ifs(*head(v(H), NA, v(H) / 2), *tail(v(H)))
    N = ifs(*head(v(F), NA, v(H) / 2), *tail(v(F)))
    O = ifs(*head(v(D), v(D) / 2, v(D) / 2), *tail(v(D)))
    P = ifs(*head(v(C), v(D) / 2, v(D) / 2), *tail(v(B)))
    if is_na(N):
        U = xsum([O, P, 0.0, 0.0])
    elif is_na(M):
        U = xsum([N, O, P, 0.0])
    elif is_na(L):
        U = xsum([M, N, O, P])
    else:
        U = xsum([L, M, N, O])
    return U, (0 if is_na(H) else 1)


def roe_may(ni: dict, eq: dict, Y: int):
    """原表 6 月版 ROE：近四季（今年Q1、去年Q4、Q3、Q2）繼續營業單位損益 ÷ AVERAGE(去年Q2 權益, 今年Q1 權益)。"""
    qs = [f"{Y}Q1", f"{Y - 1}Q4", f"{Y - 1}Q3", f"{Y - 1}Q2"]
    avg = [x for x in (eq.get(f"{Y - 1}Q2"), eq.get(f"{Y}Q1")) if not is_na(x)]
    if not avg or sum(avg) == 0:
        return NA
    return sum(ni.get(q) or 0 for q in qs) / (sum(avg) / len(avg))


def est_annual_dividend(k: str, b: dict, Y: int):
    """
    去年 Q4（年配）股利還沒公布時的估計（原表「估」「毛利率估EPS」「月營收估EPS」）：
      近三年平均配發率 × 去年全年 EPS；全年 EPS 還沒有就用 前三季 EPS ＋ Q4 營收 × 近三年平均稅後淨利率 ÷ 股數
      （金融股有自結數就用自結）。
    """
    pay = [p for p in (b.get("payout", {}).get(k, {}).get(y) for y in (Y - 1, Y - 2, Y - 3)) if not is_na(p)]
    if not pay:
        return NA
    ratio = sum(pay) / len(pay) / 100
    eps = b["eps"].get(k, {})
    annual = b.get("eps_annual", {}).get(k, {}).get(Y - 1)
    if is_na(annual):
        if k in b.get("fin_selfreport_eps", {}):
            annual = b["fin_selfreport_eps"][k]
        else:
            t = sum(eps.get(f"{Y - 1}Q{n}") or 0 for n in (1, 2, 3))
            margin = b.get("net_margin_avg", {}).get(k)
            rev = b.get("rev", {}).get(k, {})
            q4rev = sum(rev.get(f"{Y - 1}-{m:02d}") or 0 for m in (10, 11, 12))
            sh = b.get("shares_k", {}).get(k)
            if is_na(margin) or not sh:
                return NA
            annual = t + q4rev * margin / sh
    return ratio * annual


MAY_DEFAULT = {
    "band_first": 0.003,             # 6 月版權重表第一段也是 0.3%（12 月版 15%）
    "eff_date": "2026-06-03",        # 生效日：年配息股在 去年底～生效日 之間除息就排除
    "exdiv_after": None,             # 預設＝去年 12/31
    "exclude": [],                   # 人工排除（原表 AE 欄排除 5009、4766、1102）
}


def compute_may(b: dict, cfg: dict | None = None) -> dict:
    c = {**DEFAULT, **MAY_DEFAULT, **(cfg or {}), "december": False}
    Y = c["year"]
    names = b["names"]
    old = b["etf"]["00919"]["weights"]
    aum_k = b["etf"]["00919"]["aum"]
    if c["aum_plan"] == "auto":
        c["aum_plan"] = aum_plan_auto(aum_k)
    exd_after = c["exdiv_after"] or f"{Y - 1}-12-31"
    full = {}
    for k in b["universe"]:
        ins = b["insider"].get(k)
        price, mcap = b["close"].get(k), b["mcap"].get(k)
        if is_na(price) or is_na(mcap):
            continue
        insd = NA if ins is None else round(ins / 100, 2)          # 6 月版 FIF 用 ROUND
        ff_ok = 0 if ins is None else (0 if xl(1 - insd) < 0.10 else 1)
        a6, a1 = b["tv6m_avg"].get(k), b["tv1m_avg"].get(k)
        mn = min(v for v in (a6, a1) if not is_na(v)) if not (is_na(a6) and is_na(a1)) else NA
        exist = 1 if k in old else 0
        liq = 0 if is_na(mn) else (1 if (exist and mn >= c["liq_old"]) or (not exist and mn >= c["liq_new"]) else 0)
        roe = roe_may(b["ni"].get(k, {}), b["equity"].get(k, {}), Y)
        ff = NA if ins is None else 1 - insd
        u, q4open = four_q_dividend_may(b["div"].get(k, {}), Y)
        div4 = u if q4open else est_annual_dividend(k, b, Y)
        yld = 0.0 if (is_na(div4) or not price) else div4 / price
        freq = b.get("freq", {}).get(k)
        exd = b.get("last_exdiv", {}).get(k) or ""
        q0 = 1 if k in b.get("quarterly_zero", set()) else 0
        if freq is None:
            div_ok = 0
        elif freq != "每年":
            div_ok = 1 if q0 == 0 else 0
        else:   # 原表：Y > 生效日 或 Y < 去年底（空白在 Excel 比較裡算「大於」→ 通過）
            div_ok = 1 if (exd == "" or exd > c["eff_date"] or exd < exd_after) else 0
        full[k] = {"code": k, "name": names.get(k, ""), "ff_ok": ff_ok, "price": price, "mcap": mcap, "exist": exist,
                   "tv6m": a6, "tv1m": a1, "tv_min": mn, "liq_ok": liq, "roe": roe,
                   "roe_ok": 1 if (not is_na(roe) and roe > 0) else 0, "ff": ff,
                   "ff10": 1 if (not is_na(ff) and xl(ff) >= c["ff_min"]) else 0, "q4_open": q4open, "div4q": div4,
                   "yield": yld, "est_yield": yld, "freq": freq, "last_exdiv": exd, "quarterly_zero": q0,
                   "div_ok": div_ok}
    pool = {k: v for k, v in full.items() if v["ff_ok"] == 1}
    rk = rank_desc({k: v["mcap"] for k, v in pool.items()})
    for k in full:
        full[k]["mcap_rank"] = rk.get(k)
        full[k]["top300"] = 1 if (rk.get(k) is not None and rk[k] <= c["top_mcap"]) else 0
    th_code = next((k for k, r in rk.items() if r == c["top_mcap"]), None)
    for k, v in full.items():
        v["pass"] = 1 if (v["top300"] and v["liq_ok"] + v["roe_ok"] + v["ff10"] == 3) else 0
    excl = set(c.get("exclude") or [])
    cand = [k for k in pool if full[k]["pass"] and full[k]["div_ok"] and k not in excl]
    cand.sort(key=lambda k: -full[k]["yield"])
    ranked = [{"rank": i, **{x: full[k][x] for x in ("code", "name", "yield", "exist", "mcap_rank", "freq")}}
              for i, k in enumerate(cand, 1)]
    adds, dels, notes = select(full, cand, old, c)
    final = [k for k in old if k not in dels] + adds
    weights = weigh(final, full, b, c)
    impact = trade_impact(weights["final"], {k: v / 100 for k, v in old.items()}, aum_k * 1000,
                          {k: full[k]["price"] for k in full}, b["turnover1"])
    return {"etf": "00919", "review": "5月", "asof": b["asof"], "config": c,
            "mcap_threshold": pool[th_code]["mcap"] if th_code else NA, "universe": full, "ranked": ranked,
            "add": adds, "del": dels, "notes": notes + weights["notes"], "final": final, "weights": weights,
            "impact": impact}
