#!/usr/bin/env python3
"""
驗證用：把原本 TEJ 版試算表的「原始資料工作表」讀進來，餵給公開資料版的計算程式，
再跟試算表裡算好的結果逐項比對。用來確認計算邏輯跟 Excel 一模一樣（輸入相同 → 輸出相同）。

用法：python -m scripts.rebalance.verify_tej 919 path/to/919___2612.xlsx
需要：pip install python-calamine
"""
from __future__ import annotations

import sys
from datetime import datetime

from python_calamine import CalamineWorkbook

from . import etf919


def _sheet(wb, name):
    return wb.get_sheet_by_name(name).to_python()


def _code(s):
    s = str(s).strip()
    return s.split(" ")[0] if " " in s else s


def _name(s):
    s = str(s).strip()
    return s.split(" ", 1)[1] if " " in s else ""


def _num(v):
    if v in ("", None):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _qkey(d):
    if isinstance(d, str):
        d = datetime.fromisoformat(d[:10])
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def load_919(path: str) -> tuple[dict, CalamineWorkbook]:
    wb = CalamineWorkbook.from_path(path)
    b = {"names": {}, "close": {}, "mcap": {}, "insider": {}, "tv6m_avg": {}, "tv1m_avg": {}, "tv6m_median": {},
         "turnover1": {}, "ni": {}, "equity": {}, "eps": {}, "rev": {}, "div": {}, "etf": {}}
    px = _sheet(wb, "股價")
    b["asof"] = str(px[1][1])[:10]
    b["universe"] = [_code(r[6]) for r in px[2:] if len(r) > 6 and r[6] not in ("", None)]
    for r in px[2:]:
        if not r[0]:
            continue
        k = _code(r[0])
        b["names"][k] = _name(r[0])
        b["close"][k] = _num(r[1])
        b["mcap"][k] = _num(r[2])
    for r in _sheet(wb, "董監持股"):
        if r and r[0] and _num(r[1]) is not None:
            b["insider"][_code(r[0])] = _num(r[1])
    tv = _sheet(wb, "成交值")
    for r in tv[2:]:
        if not r[0]:
            continue
        k = _code(r[0])
        b["tv6m_avg"][k] = _num(r[1])
        b["tv1m_avg"][k] = _num(r[2])
        b["tv6m_median"][k] = _num(r[163]) if len(r) > 163 else None
    for r in _sheet(wb, "換手量")[2:]:
        if r[0]:
            b["turnover1"][_code(r[0])] = _num(r[5])
    roe = _sheet(wb, "ROE新")
    qs = [_qkey(d) for d in roe[1][1:5]]
    for r in roe[2:]:
        if not r[0]:
            continue
        k = _code(r[0])
        b["ni"][k] = {q: _num(v) for q, v in zip(qs, r[1:5]) if _num(v) is not None}
        b["equity"][k] = {q: _num(v) for q, v in zip(qs, r[5:9]) if _num(v) is not None}
    eps = _sheet(wb, "EPS")
    eq = [_qkey(d) for d in eps[1][1:8]]
    em = [str(d)[:7] for d in eps[1][8:17]]
    for r in eps[2:]:
        if not r[0]:
            continue
        k = _code(r[0])
        b["eps"][k] = {q: _num(v) for q, v in zip(eq, r[1:8]) if _num(v) is not None}
        b["rev"][k] = {m: _num(v) for m, v in zip(em, r[8:17]) if _num(v) is not None}
    dv = _sheet(wb, "現金股利_平攤")
    Y = int(str(dv[1][1])[:4])
    slots = [(Y, "Q1"), (Y - 1, "Q1"), (Y, "Q2"), (Y - 1, "Q2"), (Y, "Q3"), (Y - 1, "Q3"), (Y - 1, "Q4"), (Y - 2, "Q4"), (Y, "Q4")]
    for r in dv[2:]:
        if not r[0]:
            continue
        b["div"][_code(r[0])] = {s: _num(v) for s, v in zip(slots, r[1:10]) if _num(v) is not None}
    w = _sheet(wb, "919原始權重")
    b["etf"]["00919"] = {"weights": {_code(r[3]): _num(r[7]) for r in w[1:] if r[2] == "股票" and _num(r[7]) is not None},
                         "aum": _num(w[2][15])}
    return b, wb


def check_919(path: str):
    b, wb = load_919(path)
    res = etf919.compute(b, {"year": int(b["asof"][:4])})
    bad = 0

    def cmp(label, mine, theirs, tol=1e-9):
        nonlocal bad
        if theirs in ("", None) and mine in ("", None):
            return
        try:
            ok = abs(float(mine) - float(theirs)) <= tol * max(1, abs(float(theirs)))
        except (TypeError, ValueError):
            ok = str(mine) == str(theirs)
        if not ok:
            bad += 1
            if bad <= 40:
                print(f"  ✗ {label}: 公開版={mine!r} 試算表={theirs!r}")

    full = _sheet(wb, "919條件篩選(全版)")
    n = 0
    for r in full[1:]:
        if not r[0]:
            continue
        k = _code(r[0])
        u = res["universe"].get(k)
        if not u:
            continue
        n += 1
        cmp(f"{k} 市值", u["mcap"], r[3])
        cmp(f"{k} 流動性", u["liq_ok"], r[11])
        cmp(f"{k} ROE", u["roe"], r[12] if r[12] != "" else None)
        cmp(f"{k} 自由流通", u["ff"], r[14])
        cmp(f"{k} 近四季股利", u["div4q"], r[18] if r[18] != "" else None)
        cmp(f"{k} EPS成長", u["eps_g"], r[20])
        cmp(f"{k} 預估股利率", u["est_yield"], r[21])
    print(f"919條件篩選(全版)：比對 {n} 檔，{bad} 項不同")
    s = _sheet(wb, "919條件篩選")
    theirs = [_code(r[32]) for r in s[1:] if len(r) > 32 and r[32]]
    mine = [x["code"] for x in res["ranked"]]
    print(f"預估股利率排序：試算表 {len(theirs)} 檔、公開版 {len(mine)} 檔，前 {min(len(theirs), len(mine))} 名"
          f"{'完全相同' if theirs == mine[:len(theirs)] else '不同'}")
    if theirs != mine[:len(theirs)]:
        for i, (a, c) in enumerate(zip(mine, theirs)):
            if a != c:
                print(f"   第 {i + 1} 名：公開版 {a}，試算表 {c}")
                break
    t_add = [_code(r[51]) for r in s[1:] if len(r) > 51 and r[51]]
    t_del = [_code(r[52]) for r in s[1:] if len(r) > 52 and r[52]]
    print(f"納入：試算表 {t_add}\n      公開版 {res['add']}")
    print(f"剔除：試算表 {t_del}\n      公開版 {res['del']}")
    wsh = _sheet(wb, "權重")
    tw = {_code(r[0]): _num(r[3]) for r in wsh[1:41] if r[0]}
    bad_w = 0
    for k, v in tw.items():
        m = res["weights"]["final"].get(k)
        if m is None or abs(m - v) > 1e-9:
            bad_w += 1
            print(f"  ✗ 權重 {k}: 公開版={m} 試算表={v}")
    print(f"預估權重：{len(tw)} 檔，{bad_w} 檔不同；合計 {res['weights']['sum']:.6f}")
    return bad + bad_w


def load_ftse(path: str):
    """0050_0051_0056 試算表的原始資料 → bundle（FTSE IW、IBES 用表內的值覆寫，驗證邏輯是否一致）。"""
    wb = CalamineWorkbook.from_path(path)
    data = _sheet(wb, "data")
    hdr = data[0]
    b = {"names": {}, "universe": [], "mkt": {}, "mcap": {}, "iw_override": {}, "foreign": {}, "annual_liq": {},
         "new_liq": {}, "listing": {}, "alt": {}, "insider": {}, "etf": {}, "close": {}, "tv6m_avg": {},
         "mkt_6m_ago": {}, "ltr": {}, "eta": {}, "fy_div": {}, "turnover5": {}, "ibes": {}, "div": {}, "eps": {},
         "rev": {}}
    cfg = {"usd_twd": _num(data[1][4]), "prev_calc": str(hdr[20])[:10], "listing_cutoff": str(hdr[24])[:10]}
    for r in data[1:]:
        if not r[0]:
            continue
        k = _code(r[0])
        b["universe"].append(k)
        b["names"][k] = _name(r[0])
        b["mkt"][k] = "TSE"
        b["mcap"][k] = _num(r[3])
        b["iw_override"][k] = _num(r[8])
        b.setdefault("ff_override", {})[k] = _num(r[5])
        b["foreign"][k] = {"fol": _num(r[7]), "headroom": _num(r[9])}
        b["alt"][k] = int(_num(r[6]) or 0)
        b["annual_liq"][k] = int(_num(r[13]) or 0)
        b["new_liq"][k] = int(_num(r[14]) or 0)
        b["listing"][k] = str(r[15])[:10] if r[15] else None
    for name, code, aum_row in (("0050既有成分股", "0050", 2), ("0051既有成分股", "0051", 3), ("0056既有成分股", "0056", 4)):
        w = _sheet(wb, name)
        b["etf"][code] = {"weights": {_code(r[3]): _num(r[7]) for r in w[1:] if r[2] == "股票" and _num(r[7]) is not None},
                          "aum": _num(_sheet(wb, "AUM")[aum_row][1])}
    for r in _sheet(wb, "TEJ_")[2:]:
        if r[0]:
            k = _code(r[0])
            b["close"][k] = _num(r[1])
            b["tv6m_avg"][k] = _num(r[2])
            b["fy_div"][k] = _num(r[11])
            b["names"].setdefault(k, _name(r[0]))
    b["asof"] = str(_sheet(wb, "TEJ_")[1][1])[:10]
    for r in _sheet(wb, "六個月前市場別")[2:]:
        if r[0]:
            b["mkt_6m_ago"][_code(r[0])] = r[1]
    for r in _sheet(wb, "Local Total Return")[2:]:
        if r[0] and len(r) > 185:
            b["ltr"][_code(r[0])] = _num(r[185])
    for r in _sheet(wb, "Equity-to-Assets")[2:]:
        if r[0] and len(r) > 16:
            b["eta"][_code(r[0])] = (_num(r[15]), _num(r[16]))
    for r in _sheet(wb, "換手量")[2:]:
        if r[0] and len(r) > 15:
            b["turnover5"][_code(r[0])] = _num(r[15])
    brokers = {str(int(_num(r[9]))): _num(r[10]) for r in _sheet(wb, "LSEG")[1:] if len(r) > 10 and _num(r[9])}
    for r in _sheet(wb, "IBES")[1:]:
        if r[1] and _num(r[2]) is not None:
            k = _code(r[1])
            b["ibes"][k] = {"dps1": _num(r[2]), "dps2": _num(r[3]), "brokers": brokers.get(k, 0)}
    return b, cfg, wb


def check_ftse(path: str):
    from . import ftse
    b, cfg, wb = load_ftse(path)
    res = ftse.compute(b, cfg)
    bad = 0
    d = _sheet(wb, "data")
    nd = 0
    for r in d[1:]:
        if r[0]:
            k = _code(r[0])
            if res["universe"][k]["eligible"] != int(_num(r[17]) or 0):
                nd += 1
                if nd <= 10:
                    print(f"  ✗ 母體 {k}: 公開版={res['universe'][k]['eligible']} 試算表={r[17]}")
    print(f"母體篩選：{len(d) - 1} 檔，{nd} 檔不同")
    bad += nd
    s = _sheet(wb, "0050_0051")
    for code, col in (("0050", 20), ("0051", 31)):
        theirs = {_code(r[col]) for r in s[1:] if len(r) > col and r[col] and r[col] not in ("最終納入",)}
        mine = set(res[code]["final"])
        print(f"{code} 預測成分股：試算表 {len(theirs)} 檔、公開版 {len(mine)} 檔；"
              f"只在試算表 {sorted(theirs - mine)}，只在公開版 {sorted(mine - theirs)}")
        bad += len(theirs ^ mine)
    for sheet, code in (("0050權重", "0050"), ("0051權重", "0051")):
        rows = [r for r in _sheet(wb, sheet)[1:] if r[0] and r[0] != "證券代碼" and _num(r[4]) is not None]
        uni = res["universe"]
        # 試算表權重頁的「公眾流通量」若跟 data 頁不同，代表那格沒重算（舊值）
        stale = [(_code(r[0]), r[3], uni[_code(r[0])]["ff"]) for r in rows if abs(r[3] - uni[_code(r[0])]["ff"]) > 1e-9]
        nb = sum(1 for r in rows if abs(res[code]["weights"].get(_code(r[0]), -1) - _num(r[5])) > 1e-9)
        if stale:
            tot = sum(r[2] * r[3] for r in rows)
            same = sum(1 for r in rows if abs(r[2] * r[3] / tot - _num(r[5])) < 1e-12)
            print(f"{code} 權重：試算表「{sheet}」有 {len(stale)} 格公眾流通量跟 data 頁不同（未重算）：{stale}；"
                  f"用該頁的值重算 {same}/{len(rows)} 檔一致，用 data 頁的值則 {nb} 檔不同")
        else:
            print(f"{code} 權重：{nb} 檔不同")
            bad += nb
    s6 = _sheet(wb, "0056_6月")
    theirs = {_code(r[42]) for r in s6[1:] if len(r) > 42 and r[42]}
    mine = set(res["0056"]["final"])
    print(f"0056 預測成分股：試算表 {len(theirs)} 檔、公開版 {len(mine)} 檔；只在試算表 {sorted(theirs - mine)}，只在公開版 {sorted(mine - theirs)}")
    bad += len(theirs ^ mine)
    nb = 0
    for r in _sheet(wb, "0056權重")[1:]:
        if r[0] and _num(r[60]) is not None:
            m = res["0056"]["weights"].get(_code(r[0]))
            if m is None or abs(m - _num(r[60])) > 1e-9:
                nb += 1
                if nb <= 5:
                    print(f"  ✗ 0056 權重 {_code(r[0])}: 公開版={m} 試算表={_num(r[60])}")
    print(f"0056 權重：{nb} 檔不同")
    return bad + nb


def check_929(path: str):
    """00929：用 xlsb 裡的原始資料重算各項指標，再用試算表的「條件篩選 (全版」值跑選股與權重，逐項比對。"""
    from . import etf929
    wb = CalamineWorkbook.from_path(path)
    full_t = {}
    rows = _sheet(wb, "條件篩選 (全版")
    for r in rows[1:]:
        if r[0]:
            full_t[_code(r[0])] = r
    Y = 2026
    # 1) 股利指標
    old = _sheet(wb, "現金股利_OLD")
    px = {_code(r[0]): (_num(r[1]), _num(r[2]), _num(r[3])) for r in _sheet(wb, "現金股利")[2:] if r[0]}
    bad = {"yield": 0, "avg": 0, "cv": 0, "freq": 0}
    n = 0
    for r in old[2:]:
        if not r[0]:
            continue
        k = _code(r[0])
        dv = {}
        for i, y in enumerate(range(Y, Y - 6, -1)):
            for j, q in enumerate(("Q1", "Q2", "Q3", "Q4")):
                v = _num(r[1 + i * 4 + j])
                if v is not None:
                    dv[(y, q)] = v
        p = px.get(k, (None, None, None))
        bi, avg, cv, freq = etf929.dividend_metrics(dv, Y, *p)
        t_bi, t_avg, t_cv, t_freq = _num(r[60]), _num(r[63]), _num(r[67]), _num(r[70])
        n += 1
        for key, a, t in (("yield", bi, t_bi), ("avg", avg, t_avg), ("cv", cv, t_cv), ("freq", freq, t_freq)):
            if (a is None) != (t is None) or (a is not None and abs(a - t) > 1e-9 * max(1, abs(t))):
                bad[key] += 1
    print(f"股利指標：{n} 檔；不同：{bad}")
    # 2) 波動度
    dr = _sheet(wb, "日報酬")
    nb = nv = 0
    for r in dr[2:]:
        if not r[0] or len(r) < 509:
            continue
        rets = [_num(x) or 0 for x in r[1:253]]
        mine = etf929.ewma_vol(rets, 0.94)
        t = _num(r[ci_("SP") - 1])
        nv += 1
        if t is not None and abs(mine - t) > 1e-9 * max(1, t):
            nb += 1
    print(f"波動度：{nv} 檔，{nb} 檔不同")
    # 3) 用試算表的全版值跑選股
    full = {}
    for k, r in full_t.items():
        g = lambda i: _num(r[i]) if r[i] != "" else None  # noqa: E731
        full[k] = {"code": k, "name": _name(r[0]), "ff_ok": int(g(1) or 0), "price": g(2), "mcap": g(3),
                   "not_full": int(g(4) or 0), "ff": g(5), "ff10": int(g(6) or 0), "tv12": g(7), "tv1": g(8),
                   "ffturn_ok": int(g(12) or 0), "vol": g(25), "avg_yield": g(28), "cv": g(31), "pe5": g(34),
                   "pe3": g(35), "pe_diff": g(36), "roe_ok": int(g(39) or 0), "yield": g(41), "freq": 0}
    tv3 = {_code(r[0]): _num(r[3]) for r in _sheet(wb, "成交值")[2:] if r[0]}
    for k in full:
        full[k]["tv3avg"] = tv3.get(k)
    orig = {_code(r[3]): _num(r[7]) for r in _sheet(wb, "原始成分股")[1:] if r[2] == "股票"}
    sel = etf929.select(full, orig, etf929.DEFAULT)
    s = _sheet(wb, "條件篩選")
    t_rank = [_code(r[55]) for r in s[1:] if len(r) > 55 and r[55]]
    mine = [x["code"] for x in sel["ranked"]]
    same = t_rank == mine[:len(t_rank)]
    print(f"合格股利率排序：試算表 {len(t_rank)} 檔、公開版 {len(mine)} 檔，{'完全相同' if same else '不同'}")
    if not same:
        for i, (a, b_) in enumerate(zip(mine, t_rank)):
            if a != b_:
                print(f"   第 {i + 1} 名：公開版 {a}，試算表 {b_}")
                break
    t_final = {_code(r[73]) for r in s[1:] if len(r) > 73 and r[73]}
    print(f"最終名單：試算表 {len(t_final)} 檔；公開版 {len(sel['final'])} 檔；只在試算表 {sorted(t_final - set(sel['final']))}"
          f"，只在公開版 {sorted(set(sel['final']) - t_final)}")
    # 4) 用試算表的最終名單算權重
    w = etf929.weigh(sorted(t_final, key=lambda k: list(t_final).index(k)), full, etf929.DEFAULT)
    ws_ = _sheet(wb, "權重預估(以250E為單位)")
    nbw = 0
    for r in ws_[1:]:
        if r[0] and _num(r[3]) is not None and not (_num(r[3]) == 0 and _code(r[0]) not in w["final"]):
            m = w["final"].get(_code(r[0]))
            if m is None or abs(m - _num(r[3])) > 1e-9:
                nbw += 1
                if nbw <= 5:
                    print(f"  ✗ 權重 {_code(r[0])}: 公開版={m} 試算表={_num(r[3])}")
    print(f"權重（同一份名單）：{nbw} 檔不同，合計 {w['sum']:.6f}")
    return sum(bad.values()) + nb + nbw


def ci_(col):
    from openpyxl.utils import column_index_from_string
    return column_index_from_string(col)


if __name__ == "__main__":
    which, path = sys.argv[1], sys.argv[2]
    if which == "919":
        sys.exit(1 if check_919(path) else 0)
    if which == "ftse":
        sys.exit(1 if check_ftse(path) else 0)
    if which == "929":
        sys.exit(1 if check_929(path) else 0)
