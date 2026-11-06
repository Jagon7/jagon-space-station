"""
0050 元大台灣50（臺灣50指數）、0051 元大中型100（臺灣中型100指數）、0056 元大高股息（臺灣高股息指數）
定期審核預估，照原試算表（0050_0051_0056_2612.xlsx）的工作表：

  data              母體篩選：變更交易、公眾流通量、外資持股上限、年度流動性／新資格、上市滿 20 個交易日
  0050_0051         依全市值排名：0050 前 40 名納入、61 名後剔除；0051 前 130 名納入、171 名後剔除
  0050權重／0051權重 市值 × 公眾流通量（investability weight）
  0056_6月          母體＝預估的 0050＋0051；流動性、六個月總報酬、權益資產比、股利率排序
  0056權重          股利率加權 → 發行市值 6%、可投資市值 15% 上限（重分配 2 輪）

授權資料的處理（原表用的是 FTSE 成分股檔與 LSEG IBES，沒有公開來源）：
  * FTSE investability weight → 預設用公開資料「1 − 董監持股」與外資投資上限取小；
    若有 FTSE 檔，可放 config/rebalance/ftse_iw.csv（代號,IW）覆寫，結果就跟原表一致。
  * IBES 預估股利 → 預設用公開資料「近四季現金股利 × (1 + 累積 EPS 成長率)」替代（同 00919 的算法）；
    若有 LSEG 匯出，可放 config/rebalance/ibes.csv（代號,DPS1,DPS2,分析師家數）覆寫，照原表 DPS1×1/12 + DPS2×11/12。
"""
from __future__ import annotations

from .common import NA, cap_redistribute, is_na, trade_impact
from .etf919 import eps_growth, four_q_dividend

DEFAULT = {
    "usd_twd": 32.954,         # 原表 FTSE 檔換算的匯率；公開版用台銀／央行匯率也可以，只影響市值門檻
    "listing_cutoff": None,    # 「前 20 個交易日」：上市日要早於這天
    "prev_calc": None,         # 前次計算日：之後才上市的走新資格審核
    "n50": 50, "add50": 40, "del50": 61,
    "n100": 100, "add100": 130, "del100": 171,
    "n56": 50, "add56": 35, "del56": 66,
    "aum_plan_56": 975000000,  # 0056 預擬資產（千元），原表 9750 億
    "cap_rounds_56": 2,
    "dps_w1": 1 / 12, "dps_w2": 11 / 12,
}


# ---------------- 母體（data 工作表） ----------------

def universe(b: dict, c: dict, old50: dict, old51: dict) -> dict:
    out = {}
    fx = c["usd_twd"]
    for k in b["universe"]:
        if b["mkt"].get(k) not in ("TSE", "TIB"):
            continue
        mcap = b["mcap"].get(k)
        if is_na(mcap):
            continue
        cls = 1 if k in old50 else (2 if k in old51 else 0)
        ins = b["insider"].get(k)
        pub = NA if ins is None else round(1 - ins / 100, 2)
        ff = b["iw_override"].get(k) if k in b["iw_override"] else pub          # data!I（審核用）
        ffw = b.get("ff_override", {}).get(k, ff)                                # data!F（權重用）
        fol = b["foreign"].get(k, {}).get("fol")
        head = b["foreign"].get(k, {}).get("headroom")
        iw = NA if is_na(ff) else (min(fol, ff) if not is_na(fol) else ff)
        if is_na(iw):
            ff_ok = 0
        elif iw <= 0.05:
            ff_ok = 0
        elif cls and iw <= 0.15 and mcap < 2000 * fx:
            ff_ok = 0
        elif not cls and iw <= 0.15 and mcap < 2500 * fx:
            ff_ok = 0
        else:
            ff_ok = 1
        fol_ok = 0 if (cls == 0 and not is_na(head) and head < 0.20) else 1
        liq_ok = b["annual_liq"].get(k, 0)
        listed = b["listing"].get(k)
        new_ok = 0
        if listed and c["prev_calc"] and listed > c["prev_calc"]:
            new_ok = b["new_liq"].get(k, 0)
        list_ok = 1 if (listed and (not c["listing_cutoff"] or listed <= c["listing_cutoff"])) else 0
        alt = b["alt"].get(k, 0)
        ok = 1 if (alt == 0 and ff_ok and fol_ok and (liq_ok or new_ok) and list_ok) else 0
        out[k] = {"code": k, "name": b["names"].get(k, ""), "class": cls, "mcap": mcap, "ff": ffw, "fol": fol,
                  "headroom": head, "iw": iw, "ff_ok": ff_ok, "fol_ok": fol_ok, "annual_liq": liq_ok,
                  "new_liq": new_ok, "listed": listed, "list_ok": list_ok, "alt": alt, "eligible": ok}
    return out


def annual_liquidity(month_medians: dict, shares: dict, iw: dict, existing: set, days: dict) -> dict:
    """
    年度流動性：每月日成交量中位數 ÷ (總股數 × IW)；當月交易天數 < 5 不算。
    非成分股 12 個月中 ≥ 10 個月 ≥ 0.05%；成分股 12 個月中 ≥ 8 個月或近 6 個月中 ≥ 4 個月 ≥ 0.04%。
    month_medians: {代號: [T 月, T-1 月, …, T-11 月 中位數(股)]}
    """
    out = {}
    for k, meds in month_medians.items():
        sh, w = shares.get(k), iw.get(k)
        if not sh or is_na(w) or not w:
            out[k] = 0
            continue
        ex = k in existing
        th = 0.0004 if ex else 0.0005
        flags = []
        for i, m in enumerate(meds):
            if (days.get(k) or [0] * 12)[i] < 5 or is_na(m):
                flags.append(None)
            else:
                flags.append(1 if m / (sh * w) >= th else 0)
        f12 = [x for x in flags if x is not None]
        f6 = [x for x in flags[:6] if x is not None]
        r12 = sum(f12) / len(f12) if f12 else 0
        r6 = sum(f6) / len(f6) if f6 else 0
        out[k] = 1 if ((ex and (r12 >= 8 / 12 or r6 >= 4 / 6)) or (not ex and r12 >= 10 / 12)) else 0
    return out


# ---------------- 0050／0051 選股 ----------------

def _fill(keep: list, adds: list, dels: list, ranked: list, n: int, exclude: set):
    """維持檔數：新增多於剔除 → 剔除排名最差的續留股（超額剔除）；剔除多於新增 → 依排名遞補（遞補納入）。"""
    final = [k for k in keep if k not in dels] + [k for k in adds if k not in keep]
    rank = {k: i for i, k in enumerate(ranked, 1)}
    extra_del, extra_add = [], []
    while len(final) > n:
        worst = max((k for k in final if k not in adds), key=lambda k: rank.get(k, 1e9))
        final.remove(worst)
        extra_del.append(worst)
    for k in ranked:
        if len(final) >= n:
            break
        if k not in final and k not in exclude:
            final.append(k)
            extra_add.append(k)
    return final, extra_add, extra_del


def select_50_51(uni: dict, old50: dict, old51: dict, c: dict) -> dict:
    elig = [k for k, v in uni.items() if v["eligible"]]
    ranked = sorted(elig, key=lambda k: -uni[k]["mcap"])
    rank = {k: i for i, k in enumerate(ranked, 1)}
    # 0050
    add50 = [k for k in ranked if rank[k] <= c["add50"] and k not in old50]
    del50_rank = [k for k in ranked if rank[k] >= c["del50"] and k in old50]
    del50_cond = [k for k in old50 if k not in rank]
    final50, fill50, over50 = _fill(list(old50), add50, del50_rank + del50_cond, ranked, c["n50"], set())
    new50 = set(final50)
    # 0051：排除調整後 0050
    add51 = [k for k in ranked if rank[k] <= c["add100"] and k not in old50 and k not in new50 and k not in old51]
    del51_rank = [k for k in ranked if rank[k] >= c["del100"] and k in old51]
    del51_to50 = [k for k in old51 if k in new50]
    del51_cond = [k for k in old51 if k not in rank]
    from50 = [k for k in old50 if k not in new50 and k in rank and rank[k] < c["del100"]]  # 50 剔除 51 納入
    final51, fill51, over51 = _fill(list(old51), add51 + from50, del51_rank + del51_to50 + del51_cond,
                                    [k for k in ranked if k not in new50], c["n100"], new50)
    return {
        "ranked": [{"rank": rank[k], "code": k, "name": uni[k]["name"], "mcap": uni[k]["mcap"],
                    "in50": int(k in old50), "in51": int(k in old51)} for k in ranked],
        "0050": {"add": [k for k in final50 if k not in old50], "del": [k for k in old50 if k not in new50],
                 "cond_del": del50_cond, "fill": fill50, "over": over50, "final": final50},
        "0051": {"add": [k for k in final51 if k not in old51], "del": [k for k in old51 if k not in set(final51)],
                 "cond_del": del51_cond, "to50": del51_to50, "from50": from50, "fill": fill51, "over": over51,
                 "final": final51},
    }


def mcap_weights(final: list, uni: dict) -> dict:
    # 原表 0050權重!D＝data!F（公眾流通量；不跟外資上限取小）
    e = {k: uni[k]["mcap"] * (uni[k]["ff"] if not is_na(uni[k]["ff"]) else 1) for k in final}
    tot = sum(e.values())
    return {k: v / tot for k, v in e.items()}


# ---------------- 0056 ----------------

def select_56(b: dict, uni: dict, pool: list, old56: dict, c: dict) -> dict:
    Y = int(b["asof"][:4])
    rows = {}
    for k in pool:
        nm = b["names"].get(k, "")
        price = b["close"].get(k)
        ib = b["ibes"].get(k)
        if ib:
            dps = ib["dps1"] * c["dps_w1"] + ib["dps2"] * c["dps_w2"]
            yld, brokers, src = (dps / price if price else NA), ib.get("brokers", 0), "IBES"
        else:
            d4, _ = four_q_dividend(b["div"].get(k, {}), Y)
            g, _ = eps_growth(b["eps"].get(k, {}), b["rev"].get(k, {}), Y)
            if is_na(d4) or not price:
                yld = NA
            else:
                yld = d4 / price * (1 + (g if g != "" else 0))
            brokers, src = NA, "公開替代"
        rows[k] = {"code": k, "name": nm, "exist": int(k in old56), "nonky": 0 if nm.endswith("KY") else 1,
                   "yield": yld, "yield_src": src, "brokers": brokers, "tv6m": b["tv6m_avg"].get(k),
                   "mkt6m": b["mkt_6m_ago"].get(k), "ltr": b["ltr"].get(k), "eta": b["eta"].get(k, (NA, NA))[0],
                   "cseta": b["eta"].get(k, (NA, NA))[1], "fy_div": b["fy_div"].get(k)}
    vals = lambda f: sorted(v[f] for v in rows.values() if not is_na(v[f]))  # noqa: E731
    n = len(pool)
    small = lambda f, p: (vals(f)[int(n * p) - 1] if len(vals(f)) >= int(n * p) and int(n * p) >= 1 else NA)  # noqa: E731
    th_tv, th_ltr, th_eta, th_cs = small("tv6m", 0.1), small("ltr", 0.1), small("eta", 0.1), small("cseta", 0.05)
    for v in rows.values():
        v["liq_ok"] = 1 if v["exist"] or (not is_na(v["tv6m"]) and v["tv6m"] > th_tv) else 0
        if v["mkt6m"] != "TSE":
            v["ltr_ok"] = 0
        elif v["exist"]:
            v["ltr_ok"] = 1
        else:
            v["ltr_ok"] = 0 if (not is_na(v["ltr"]) and v["ltr"] <= th_ltr and v["ltr"] <= 0) else 1
        v["asset_ok"] = 1 if v["exist"] else (0 if (not is_na(v["eta"]) and not is_na(v["cseta"])
                                                    and v["eta"] <= th_eta and v["cseta"] <= th_cs) else 1)
        v["div_ok"] = 0 if (is_na(v["fy_div"]) or v["fy_div"] == 0) else 1
        v["broker_ok"] = 1 if (v["exist"] or is_na(v["brokers"]) or v["brokers"] >= 2) else 0
        v["pass"] = 1 if (v["nonky"] and not is_na(v["yield"]) and v["liq_ok"] and v["ltr_ok"] and v["asset_ok"]
                          and v["div_ok"] and v["broker_ok"]) else 0
    cand = sorted((k for k, v in rows.items() if v["pass"] and v["yield"]), key=lambda k: -rows[k]["yield"])
    rank = {k: i for i, k in enumerate(cand, 1)}
    add = [k for k in cand if rank[k] <= c["add56"] and k not in old56]
    dele = [k for k in cand if rank[k] >= c["del56"] and k in old56]
    cond = [k for k in old56 if k not in rank]
    final, fill, over = _fill(list(old56), add, dele + cond, cand, c["n56"], set())
    return {"rows": rows, "thresholds": {"tv6m": th_tv, "ltr": th_ltr, "eta": th_eta, "cseta": th_cs},
            "ranked": [{"rank": rank[k], **{x: rows[k][x] for x in ("code", "name", "yield", "yield_src", "exist")}}
                       for k in cand],
            "add": [k for k in final if k not in old56], "del": [k for k in old56 if k not in final],
            "cond_del": cond, "fill": fill, "over": over, "final": final}


def weights_56(final: list, rows: dict, uni: dict, b: dict, c: dict) -> dict:
    y = {k: rows[k]["yield"] for k in final}
    tot = sum(y.values())
    w = {k: v / tot for k, v in y.items()}
    issue = {k: b["mcap"][k] for k in final}                                        # 百萬
    inv = {k: issue[k] * (uni.get(k, {}).get("iw") or 1) for k in final}
    cap = {k: min(issue[k] * 0.06 * 1000 / c["aum_plan_56"], inv[k] * 0.15 * 1000 / c["aum_plan_56"]) for k in final}
    out = cap_redistribute(w, cap, c["cap_rounds_56"])
    return {"rows": [{"code": k, "yield": y[k], "raw": w[k], "cap": cap[k], "final": out[k]} for k in final],
            "final": out, "sum": sum(out.values())}


def compute(b: dict, cfg: dict | None = None) -> dict:
    c = {**DEFAULT, **(cfg or {})}
    e = b["etf"]
    old50, old51, old56 = e["0050"]["weights"], e["0051"]["weights"], e["0056"]["weights"]
    if "annual_liq" not in b:
        ff = {k: (b["iw_override"][k] if k in b.get("iw_override", {}) else
                  (NA if b["insider"].get(k) is None else round(1 - b["insider"][k] / 100, 2))) for k in b["universe"]}
        meds = b.get("month_medians", {})
        b["annual_liq"] = annual_liquidity(meds, b.get("shares", {}), ff, set(old50) | set(old51),
                                           b.get("month_days", {}))
        # 新上市（前次計算日之後）：有資料的月份都要 ≥ 0.05%
        b["new_liq"] = {}
        for k, m in meds.items():
            sh, w = b.get("shares", {}).get(k), ff.get(k)
            vals = [x for x, n in zip(m, b.get("month_days", {}).get(k, [])) if not is_na(x) and n >= 5]
            b["new_liq"][k] = 1 if (sh and w and vals and all(x / (sh * w) >= 0.0005 for x in vals)) else 0
    uni = universe(b, c, old50, old51)
    sel = select_50_51(uni, old50, old51, c)
    w50 = mcap_weights(sel["0050"]["final"], uni)
    w51 = mcap_weights(sel["0051"]["final"], uni)
    pool = sel["0050"]["final"] + sel["0051"]["final"]
    s56 = select_56(b, uni, pool, old56, c)
    w56 = weights_56(s56["final"], s56["rows"], uni, b, c)
    price = b["close"]
    out = {"asof": b["asof"], "config": c, "universe": uni, "ranked": sel["ranked"]}
    for code, s, w in (("0050", sel["0050"], w50), ("0051", sel["0051"], w51), ("0056", s56, w56["final"])):
        old = {k: v / 100 for k, v in e[code]["weights"].items()}
        out[code] = {**{k: v for k, v in s.items() if k not in ("rows",)}, "weights": w,
                     "impact": trade_impact(w, old, (e[code]["aum"] or 0) * 1000, price, b["turnover5"])}
    out["0056"]["rows"] = s56["rows"]
    out["0056"]["thresholds"] = s56["thresholds"]
    out["0056"]["weight_rows"] = w56["rows"]
    return out
