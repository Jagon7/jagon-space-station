"""
00929 復華台灣科技優息（特選臺灣科技優息指數）12 月定期審核預估，照原試算表（00929_202612.xlsb）：

  產業母體            上市＋上櫃，產業別 24~31、22、35、36
  條件篩選 (全版      每檔：自由流通、全額交割、近 12 月／近 1 月成交金額、自由流通週轉率、市值、
                      波動度、平均股息殖利率、近 5 年股利變異係數、5 年 vs 近 3 月平均本益比、ROE
  條件篩選            流動性審核 → 五項財務指標（各取 90%）→ 依股利率排序 → 35 名內納入、66 名後剔除
  權重預估            股利率加權，上限 = min(10%, 5×(自由流通市值比重＋近 3 月成交值比重)/2, 發行市值 6%, 自由流通市值 15%)

原表的「最終納入／剔除」是人工判斷（含配息頻率考量）；這裡用原表欄位能推出的規則自動挑，
人工判斷可以寫在 config 的 manual 覆寫。
"""
from __future__ import annotations

import math

from .common import (NA, xl, add_months, aum_plan_auto, buffer_select, cap_redistribute, is_na, mean, priority_include,
                     rank_asc, rank_desc, trade_impact, xsum)

INDUSTRIES = {"24", "25", "26", "27", "28", "29", "30", "31", "22", "35", "36"}

DEFAULT = {
    "cutoff": "2026-12-09",          # 審核資料截止日
    "prev_cutoff": "2025-12-09",     # 前次截止日（前次股息殖利率用的收盤價日）
    "prev2_cutoff": "2024-12-10",
    "year": 2026,
    "lam": 0.94,                     # 指數平滑波動度 λ
    "vol_days": 252,
    "n_const": 50, "add_rank": 35, "del_rank": 65,  # 35 名內納入、既有成分股 65 名後刪除
    "max_changes": 16,               # 12 月定審至多替換 16 檔（6 月 24 檔）
    "december": True,
    "official": True,                # True：照編製規則（週轉率 8 個月、市值 ≥ 50 億、註 5 放寬上限）；False：照原試算表
    "ffturn_months": None,           # 自由流通週轉率 ≥ 3% 的月數門檻（None：official 用 8、原試算表用 7）
    "min_mcap": 5000,                # 發行市值 ≥ 50 億（百萬元）
    "aum_plan": "auto",              # 預擬資產（千元）："auto"＝AUM×1.2 無條件進位到 250 億；原表填 175000000
    "cap_max": 0.10, "cap_liq_mult": 5, "cap_issue": 0.06, "cap_ff": 0.15, "cap_rounds": 5,
    "manual": {},
}


# ---------------- 現金股利_OLD：各季平攤 ----------------

def _cnt(*v):
    return sum(0 if is_na(x) else 1 for x in v)


def spread_year(q1, q2, q3, q4, current=False):
    """一個年度的 [Q4, Q3, Q2, Q1] 平攤值（照原表 IFS；空白儲存格在 SUM 裡算 0，NA() 才是 #N/A）。"""
    v = lambda x: 0.0 if is_na(x) else x  # noqa: E731
    q = lambda x: NA if is_na(x) else x / 4  # noqa: E731

    def ifs(*pairs):
        for cond, val in pairs:
            if cond:
                return val
        return NA
    B, C, D, E = q1, q2, q3, q4
    if current:
        a = NA if is_na(E) else E
    else:
        a = ifs((_cnt(C, D) == 2, v(E)), (_cnt(B, C, D) == 0, q(E)),
                (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 0, NA),
                (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 1, v(E) / 2),
                (_cnt(B, C, D, E) == 3, v(E)), (_cnt(B, C, D, E) == 4, v(E)), (_cnt(B) == 1, v(E)), (_cnt(D) == 1, v(E)))
    b = ifs((_cnt(C, D) == 2, v(D)), (_cnt(B, C, D) == 0, q(E)),
            (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 0, NA),
            (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 1, v(E) / 2),
            (_cnt(B, C, D, E) == 3, v(D)), (_cnt(B, C, D, E) == 4, v(D)), (_cnt(B) == 1, v(D)), (_cnt(D) == 1, v(D)))
    c = ifs((_cnt(C, D) == 2, v(C)), (_cnt(B, C, D) == 0, q(E)),
            (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 0, v(C) / 2),
            (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 1, v(C) / 2),
            (_cnt(B, C, D, E) == 3, v(C)), (_cnt(B, C, D, E) == 4, v(C)), (_cnt(B) == 1, v(C)), (_cnt(D) == 1, v(C)))
    d = ifs((_cnt(C, D) == 2, v(B)), (_cnt(B, C, D) == 0, q(E)),
            (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 0, v(C) / 2),
            (_cnt(B, D) == 0 and _cnt(C) == 1 and _cnt(E) == 1, v(C) / 2),
            (_cnt(B, C, D, E) == 3, v(B)), (_cnt(B, C, D, E) == 4, v(B)), (_cnt(B) == 1, v(B)), (_cnt(D) == 1, v(B)))
    return [a, b, c, d]


def dividend_metrics(dv: dict, Y: int, p_now, p_prev, p_prev2, list_year: int | None = None):
    """回傳 (本次股息殖利率, 平均股息殖利率, 近5年股利變異係數, 配息頻率)。dv: {(年度,'Q1'..'Q4'): 現金股利}"""
    g = lambda y, q: dv.get((y, q))  # noqa: E731
    yrs = [Y - i for i in range(6)]
    sp = []
    for i, y in enumerate(yrs):
        sp += spread_year(g(y, "Q1"), g(y, "Q2"), g(y, "Q3"), g(y, "Q4"), current=(i == 0))
    AF, AG, AH, AI, AJ, AK, AL, AM, AN, AO, AP, AQ, AR, AS, AT, AU = sp[:16]
    if is_na(AI):
        BE = xsum([AJ, AK, AL, AM])
    elif is_na(AH):
        BE = xsum([AI, AJ, AK, AL])
    elif is_na(AG):
        BE = xsum([AH, AI, AJ, AK])
    elif is_na(AF):
        BE = xsum([AG, AH, AI, AJ])
    else:
        BE = xsum([AF, AG, AH, AI])
    BF = xsum([AN, AO, AP, AQ]) if is_na(AH) else xsum([AL, AM, AN, AO])
    BG = xsum([AR, AS, AT, AU]) if is_na(AH) else xsum([AP, AQ, AR, AS])
    div_ = lambda a, p: NA if (is_na(a) or not p) else a / p  # noqa: E731
    BI, BJ, BK = div_(BE, p_now), div_(BF, p_prev), div_(BG, p_prev2)
    avg = mean([BI, BJ, BK]) if not is_na(BI) else NA
    # AVERAGE 遇到 #N/A 會錯 → IFERROR 退到前兩個、再退到本次
    if any(is_na(x) for x in (BI, BJ, BK)):
        avg = mean([BI, BJ]) if not (is_na(BI) or is_na(BJ)) else BI
    # 近 5 年完整年度股利（去年起往前 5 年）：原表 現金股利_OLD BV:BZ／CA／BN:BP
    #   有資料的年度加總（季別空白當 0）；TEJ 對「有紀錄但沒配息」的年度給 0，公開資料沒有紀錄，
    #   所以從「第一次出現股利紀錄」或「上市櫃」的年度（取早的）起，之後沒紀錄的年度都當 0 元；
    #   至少 3 年才算，STDEV.P ÷ AVERAGE
    first = min((yy for (yy, _q) in dv), default=None)
    if list_year is not None:          # 上市櫃後沒配息的年度，TEJ 也是 0（例：2498 宏達電 2021～2024）
        first = list_year if first is None else min(first, list_year)
    ann = []
    for y in range(Y - 1, Y - 6, -1):
        vals = [g(y, q) for q in ("Q1", "Q2", "Q3", "Q4")]
        if first is not None and y >= first:
            ann.append(sum(0 if is_na(x) else x for x in vals))
    if len(ann) < 3:
        cv = NA
    else:
        m = sum(ann) / len(ann)
        sd = math.sqrt(sum((x - m) ** 2 for x in ann) / len(ann))
        cv = sd / m if m else NA
    freq = sum(1 for x in (g(Y, "Q1"), g(Y, "Q2"), g(Y - 1, "Q3"), g(Y - 1, "Q4")) if not is_na(x) and x > 0)
    return BI, avg, cv, freq


def ewma_vol(returns_pct: list, lam: float) -> float:
    """日報酬（%，新到舊）的指數平滑：Σ (1-λ)λ^i r_i² × N / 252（原表 SUM(...)*COUNTA(日期)/252）。"""
    if not returns_pct:
        return NA
    s = sum((1 - lam) * lam ** i * (r or 0) ** 2 for i, r in enumerate(returns_pct))
    return s * len(returns_pct) / 252


def roe_three(ni: dict, eq: dict, Y: int) -> int:
    """本次＝近四季淨利／最近權益；前次＝前一年同期四季／前一年 Q3 權益；前前次同理。三次都 > 0。"""
    def s(qs):
        return sum(ni.get(q) or 0 for q in qs)
    cur = [f"{Y}Q3", f"{Y}Q2", f"{Y}Q1", f"{Y - 1}Q4"]
    prv = [f"{Y - 1}Q3", f"{Y - 1}Q2", f"{Y - 1}Q1", f"{Y - 2}Q4"]
    pp = [f"{Y - 2}Q3", f"{Y - 2}Q2", f"{Y - 2}Q1", f"{Y - 3}Q4"]
    e0 = eq.get(f"{Y}Q3") if eq.get(f"{Y}Q3") is not None else eq.get(f"{Y}Q2")
    e1, e2 = eq.get(f"{Y - 1}Q3"), eq.get(f"{Y - 2}Q3")
    try:
        r = [s(cur) / e0, s(prv) / e1, s(pp) / e2]
    except (TypeError, ZeroDivisionError):
        return 0
    return 1 if all(x > 0 for x in r) else 0


# ---------------- 主流程 ----------------

def metrics(b: dict, c: dict) -> dict:
    Y = c["year"]
    out = {}
    for k in b["universe929"]:
        ins = b["insider"].get(k)
        price, mcap = b["close"].get(k), b["mcap"].get(k)
        if is_na(price) or is_na(mcap):
            continue
        insd = NA if ins is None else math.floor(ins + 1e-9) / 100   # 原表董監持股% 取到整數百分比（無條件捨去）
        ff = NA if ins is None else 1 - insd
        bi, avg, cv, freq = dividend_metrics(b["div"].get(k, {}), Y, price, b["px_prev"].get(k), b["px_prev2"].get(k),
                                              (b.get("list_year") or {}).get(k))
        pe5, pe3 = b["pe5"].get(k, NA), b["pe3"].get(k, NA)
        out[k] = {"code": k, "name": b["names"].get(k, ""),
                  "ff_ok": 1 if (ins is not None and insd <= 0.9) else 0,
                  "price": price, "mcap": mcap, "not_full": 0 if b["alt"].get(k) else 1, "ff": ff,
                  "ff10": 1 if (not is_na(ff) and xl(ff) >= 0.1) else 0,
                  "tv12": b["tv12_sum"].get(k), "tv1": b["tv1_sum"].get(k), "tv3avg": b["tv3_avg"].get(k),
                  "ffturn_ok": b["ffturn_ok"].get(k, 0), "vol": b["vol"].get(k, NA), "avg_yield": avg,
                  "cv": cv, "pe5": pe5, "pe3": pe3,
                  "pe_diff": NA if (is_na(pe5) or is_na(pe3)) else pe5 - pe3,
                  "roe_ok": roe_three(b["ni"].get(k, {}), b["equity"].get(k, {}), Y),
                  "yield": bi, "freq": freq}
    return out


def select(full: dict, old: dict, c: dict) -> dict:
    # 條件篩選：自由流通係數過關 → 非全額交割 → 自由流通 ≥ 10%
    L = [k for k in full if full[k]["ff_ok"] == 1 and full[k]["not_full"] == 1 and full[k]["ff10"] == 1]
    n = len(L)
    r12 = rank_desc({k: full[k]["tv12"] for k in L})
    r1 = rank_desc({k: full[k]["tv1"] for k in L})
    rm = rank_desc({k: full[k]["mcap"] for k in L})
    for k in L:
        f = full[k]
        f["top20_12m"] = 1 if (r12[k] is not None and r12[k] <= n * 0.2) else 0
        f["cond1"] = 1 if f["top20_12m"] + f["ffturn_ok"] >= 1 else 0
        f["cond2"] = 1 if (r1[k] is not None and r1[k] <= int(n * 0.8)) else 0
        f["top200"] = 1 if (rm[k] is not None and rm[k] <= 200
                            and (not c.get("official") or f["mcap"] >= c["min_mcap"])) else 0
        f["liq_ok"] = 1 if f["cond1"] + f["cond2"] + f["top200"] == 3 else 0
    th = {"tv12": next((full[k]["tv12"] for k in L if r12[k] == int(n * 0.2)), NA),
          "tv1": next((full[k]["tv1"] for k in L if r1[k] == int(n * 0.8)), NA),
          "mcap": next((full[k]["mcap"] for k in L if rm[k] == 200), NA)}
    AF = [k for k in L if full[k]["liq_ok"] == 1]
    m = len(AF)
    blank_rows = 199 - m   # 原表 COUNTBLANK($xx$2:$xx$200) 把名單以下的空白列也算進去

    def cut(field, asc, mode):
        vals = {k: full[k][field] for k in AF}
        rk = rank_asc(vals) if asc else rank_desc(vals)
        blanks = blank_rows + sum(1 for k in AF if is_na(vals[k]))
        if mode == "int_then_mul":          # INT(COUNTA-COUNTBLANK)*0.9
            lim = int(m - blanks) * 0.9
        elif mode == "int_all":             # INT((COUNTA-COUNTBLANK)*0.9)
            lim = int((m - blanks) * 0.9)
        else:                               # (COUNTA-COUNTBLANK)*0.9
            lim = (m - blanks) * 0.9
        return {k: (1 if (rk[k] is not None and rk[k] <= lim) else 0) for k in AF}, lim

    vol_ok, lv = cut("vol", True, "int_then_mul")
    yld_ok, ly = cut("avg_yield", False, "int_then_mul")
    cv_ok, lc = cut("cv", True, "int_all")
    pe_ok, lp = cut("pe_diff", False, "plain")
    for k in AF:
        f = full[k]
        f.update({"vol_ok": vol_ok[k], "yield_ok": yld_ok[k], "cv_ok": cv_ok[k], "pe_ok": pe_ok[k]})
        f["passes"] = vol_ok[k] + yld_ok[k] + cv_ok[k] + pe_ok[k] + f["roe_ok"]
    AY = [k for k in AF if full[k]["passes"] == 5]
    ranked = sorted((k for k in AY if not is_na(full[k]["yield"])), key=lambda k: -full[k]["yield"])
    rank = {k: i for i, k in enumerate(ranked, 1)}
    cond_del = [k for k in old if k not in rank]
    rank_del = [k for k in ranked if k in old and rank[k] > c["del_rank"]]
    man = c.get("manual") or {}
    if man.get("add") is not None and man.get("del") is not None:
        adds, dels, notes = list(man["add"]), list(man["del"]), ["人工覆寫"]
    else:
        # 編製規則 伍、一、2：35 名內納入、既有 65 名後刪除、36~65 名既有優先；12 月至多替換 16 檔（6 月 24 檔）
        final, notes = buffer_select(ranked, old, c["n_const"], c["add_rank"], c["del_rank"], c["max_changes"])
        if c.get("december", True):
            # 註 3：12 月定審優先納入最近 4 季配息 ≥ 2 次的公司
            final, n2 = priority_include(final, ranked, old, {k for k in ranked if (full[k].get("freq") or 0) >= 2},
                                         c["max_changes"])
            notes += n2
        adds = [k for k in final if k not in old]
        dels = [k for k in old if k not in final]
    final = [k for k in old if k not in dels] + adds
    return {"L": L, "thresholds": {**th, "vol": lv, "yield": ly, "cv": lc, "pe": lp}, "AF": AF,
            "ranked": [{"rank": rank[k], "code": k, "name": full[k]["name"], "yield": full[k]["yield"],
                        "exist": int(k in old), "freq": full[k]["freq"]} for k in ranked],
            "add": adds, "del": dels, "cond_del": cond_del, "rank_del": rank_del, "final": final, "notes": notes}


def weigh(final: list, full: dict, c: dict) -> dict:
    y = {k: full[k]["yield"] for k in final}
    ty = sum(y.values())
    w = {k: v / ty for k, v in y.items()}
    ffm = {k: full[k]["mcap"] * (full[k]["ff"] if not is_na(full[k]["ff"]) else 1) * 1000 for k in final}
    tf = sum(ffm.values())
    tv = {k: full[k]["tv3avg"] or 0 for k in final}
    tt = sum(tv.values())
    issue = {k: full[k]["mcap"] * 1000 for k in final}
    def caps(pi, pf, plan):
        return {k: min(c["cap_max"], c["cap_liq_mult"] * (ffm[k] / tf + tv[k] / tt) / 2,
                       issue[k] * pi / plan, ffm[k] * pf / plan) for k in final}
    pi, pf, plan = c["cap_issue"], c["cap_ff"], c["aum_plan"]
    cap = caps(pi, pf, plan)
    notes = []
    if c.get("official") and sum(cap.values()) < 1:
        # 註 5：發行市值上限每次放寬 0.5%（最多 10%）、自由流通市值上限每次放寬 1.25%；
        #       仍不行就把資產倍數以 0.05 為單位調降到 1 倍
        base = plan / 1.2
        mult = 1.2
        while sum(cap.values()) < 1 and pi < 0.10 - 1e-12:
            pi, pf = min(pi + 0.005, 0.10), pf + 0.0125
            cap = caps(pi, pf, plan)
        while sum(cap.values()) < 1 and mult > 1.0 + 1e-12:
            mult = round(mult - 0.05, 2)
            plan = base * mult
            cap = caps(pi, pf, plan)
        notes.append(f"上限放寬為發行市值 {pi:.1%}、自由流通市值 {pf:.2%}，資產倍數 {mult:g}")
    out = cap_redistribute(w, cap, c["cap_rounds"] if not c.get("official") else 200)
    return {"rows": [{"code": k, "name": full[k]["name"], "yield": y[k], "raw": w[k], "cap": cap[k], "final": out[k]}
                     for k in final], "final": out, "sum": sum(out.values()), "notes": notes}


def compute(b: dict, cfg: dict | None = None) -> dict:
    c = {**DEFAULT, **(cfg or {})}
    old = b["etf"]["00929"]["weights"]
    if c["aum_plan"] == "auto":
        c["aum_plan"] = aum_plan_auto(b["etf"]["00929"]["aum"] or 0)
    full = metrics(b, c)
    sel = select(full, old, c)
    w = weigh(sel["final"], full, c)
    oldw = {k: v / 100 for k, v in old.items()}
    impact = trade_impact(w["final"], oldw, (b["etf"]["00929"]["aum"] or 0) * 1000,
                          {k: v["price"] for k, v in full.items()}, b["turnover1"])
    sel["notes"] = sel["notes"] + w["notes"]
    return {"etf": "00929", "asof": b["asof"], "config": c, "universe": full, **sel, "weights": w, "impact": impact}


# ---------------- 公開資料 → 00929 需要的欄位 ----------------

def extras(pub, b: dict, c: dict) -> dict:
    from datetime import date
    c = {**DEFAULT, **(c or {})}
    basic = pub.basic()
    b["alt"] = {k: v.get("alt", 0) for k, v in basic.items()}
    b["list_year"] = {k: int(v["list"][:4]) for k, v in basic.items() if str(v.get("list", ""))[:4].isdigit()}
    b["universe929"] = sorted(k for k, v in basic.items() if v.get("ind") in INDUSTRIES and v["mk"] in ("TSE", "OTC")
                              and not v["n"].endswith("-創"))
    days = [d for d in pub.px_days() if d <= b["asof"]]
    a = date.fromisoformat(b["asof"])

    def window(months):
        # TEJ「近12月總成交值」「近3個月平均成交值」：從 (月數−1) 個月前的 1 號起算
        #   （資料日 2026-11-05 → 12 月：2025-12-01 起 224 天；3 月：2026-09-01 起），與原表逐檔一致；
        # 「近1月總成交值」則是往回推一個月（2026-10-06 起）
        if months == 1:
            s = add_months(a, -1).isoformat()
            return [d for d in days if d > s]
        s = add_months(a.replace(day=1), -(months - 1)).isoformat()
        return [d for d in days if d >= s]
    from collections import defaultdict
    acc = {12: defaultdict(float), 1: defaultdict(float), 3: defaultdict(float)}
    cnt3 = defaultdict(int)
    for mths in (12, 1, 3):
        for d in window(mths):
            for k, v in pub.px(d).items():
                acc[mths][k] += v[2] or 0
                if mths == 3:
                    cnt3[k] += 1
    b["tv12_sum"], b["tv1_sum"] = dict(acc[12]), dict(acc[1])
    b["tv3_avg"] = {k: v / cnt3[k] for k, v in acc[3].items() if cnt3[k]}
    # 自由流通週轉率：近 12 個完整月，每月成交量 ÷ (自由流通 × 股數) ≥ 3% 的月份 ≥ 7
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
    b["ffturn_ok"] = {}
    months_need = c["ffturn_months"] or (8 if c.get("official") else 7)   # 編製規則：12 個月中至少 8 個月
    for k, per in mv.items():
        sh, ins = basic.get(k, {}).get("sh"), b["insider"].get(k)
        if not sh or ins is None:
            continue
        ffs = (1 - math.floor(ins + 1e-9) / 100) * sh
        b["ffturn_ok"][k] = 1 if ffs and sum(1 for mo in months if per.get(mo, 0) / ffs >= 0.03) >= months_need else 0
    # 波動度：近 252 個交易日的日報酬（%）
    last = days[-c["vol_days"] - 1:]
    rets = defaultdict(list)
    prev = None
    for d in last:
        p = pub.px(d)
        if prev is not None:
            for k, v in p.items():
                chg = v[4] if len(v) > 4 else None
                if v[0] and chg is not None and (v[0] - chg):
                    rets[k].append(chg / (v[0] - chg) * 100)
                elif v[0] and prev.get(k) and prev[k][0]:
                    rets[k].append((v[0] / prev[k][0] - 1) * 100)
        prev = p
    b["vol"] = {k: ewma_vol(list(reversed(r)), c["lam"]) for k, r in rets.items()}
    # 前次、前前次截止日收盤價
    def close_on(day):
        cands = [d for d in pub.px_days() if d <= day]
        return {k: v[0] for k, v in pub.px(cands[-1]).items()} if cands else {}
    b["px_prev"], b["px_prev2"] = close_on(c["prev_cutoff"]), close_on(c["prev2_cutoff"])
    # 本益比：近 5 年（≥ 504 筆）與近 3 個月（≥ 21 筆）平均
    cut = date.fromisoformat(c["cutoff"])
    s5, s3 = add_months(cut, -60).isoformat(), add_months(cut, -3).isoformat()
    pe_all, pe_3 = defaultdict(list), defaultdict(list)
    for p in sorted((pub.raw / "pe").glob("20*.json")):
        if p.stem <= s5 or p.stem > b["asof"]:
            continue
        import json
        doc = json.loads(p.read_text(encoding="utf-8"))
        for k, v in doc.items():
            if v:
                pe_all[k].append(v)
                if p.stem > s3:
                    pe_3[k].append(v)
    b["pe5"] = {k: sum(v) / len(v) for k, v in pe_all.items() if len(v) >= 504}
    b["pe3"] = {k: sum(v) / len(v) for k, v in pe_3.items() if len(v) >= 21}
    return b
