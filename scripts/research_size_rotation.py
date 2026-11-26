#!/usr/bin/env python3
"""
大小型股輪動預測（量化 x AI 交易組簡報的想法）＋能不能用來優化「85g 開高走低」當沖（開盤放空、收盤回補＝賭黑K）

大型股＝0050（還原）；小型股＝上櫃普通股等權（前一天成交 ≥ 2,000 萬，避免冷門股）
標籤：隔天「小型股 − 大型股」收盤對收盤報酬 > 0 → 小型股贏
因子（兩組）：
  收盤時知道的：當天／5 日／20 日大小差、小型股當天開盤到收盤與隔夜、漲停家數（當天、3 日均、相對 60 日均）、
               上漲家數比例、上櫃成交比重（相對 20 日均）、台積電離 240 日高點、小型股 20 日波動、新台幣 1／5 日（落後一天）
  開盤前才知道的（給當沖用）：前一晚費半、那斯達克、VIX、台積電 ADR 報酬
模型：邏輯迴歸、LightGBM；逐年滾動（用之前所有年度訓練，預測下一年），2016 起樣本外
黑K事件（用 yahoo 日線重建 85g）：前一天成交金額前 50、前一天漲停或 5 日漲 ≥ 10%，隔天開高 0～4% → 開盤空、收盤補；
  漲到前一天收盤 +9% 停損（防券差）；成本 0.23%
檢驗：模型預測「大型股贏」的機率分三等份（門檻只用 2016-18 的樣本外預測決定），看三段期間（2016-18／2019-22／2023+）的黑K報酬；
     t 值用月份群聚（每個月「大型股機率高組 − 低組」的平均）
資料：data/research/yahoo_adj（個股還原日線）、data/research/yahoo（指數、匯率）、0050 還原日線快取到 data/research/size_etf.json
輸出 data/research/size_rotation.json；用法：python scripts/research_size_rotation.py
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics as st
import sys
import time
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
RES = DATA / "research"
COST = 0.23
PARTS = (("2016-18", "2016", "2019"), ("2019-22", "2019", "2023"), ("2023+", "2023", "2100"))


def etf0050():
    p = RES / "size_etf.json"
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - p.stat().st_mtime < 86400:
            return j
    except (OSError, ValueError):
        pass
    import requests
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/0050.TW", timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                     params={"period1": 1293840000, "period2": int(time.time()), "interval": "1d"}).json()["chart"]["result"][0]
    q, adj, off = r["indicators"]["quote"][0], r["indicators"]["adjclose"][0]["adjclose"], r["meta"]["gmtoffset"]
    rows = []
    for i, t in enumerate(r["timestamp"]):
        o, c, a = q["open"][i], q["close"][i], adj[i]
        if o and c and a:
            rows.append([datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(), o * a / c, a])
    p.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def yser(name):
    j = json.loads((RES / "yahoo" / f"{name}.json").read_text(encoding="utf-8"))["d"]
    return {r[0]: r[4] for r in j if r[4]}


def us_ret(ser: dict, keys: list, tw_day: str, prev_tw: str):
    """台股 tw_day 開盤前最近一次美股收盤的日報酬（美股日期 < 台股日期）；前一個台股交易日之後美股都休市＝ 0"""
    k = bisect_left(keys, tw_day) - 1
    if k < 1:
        return None
    return 0.0 if keys[k] < prev_tw else (ser[keys[k]] / ser[keys[k - 1]] - 1) * 100


def build():
    last = sorted(Path(x).stem for x in glob.glob(str(DATA / "daily" / "20*.json")))[-1]
    stocks = {}
    for f in glob.glob(str(RES / "yahoo_adj" / "*.json")):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        rows = [r for r in j["d"] if r[0] <= last and all(r[1:5]) and r[6]]
        if len(rows) > 100:
            stocks[j["code"]] = ("OTC" if j["mkt"] == 1 else "TSE", rows)
    # 每天每檔：(市場, 開還原, 高還原, 收還原, 昨收還原, 成交額, 5日前還原收, 昨成交額)
    day = defaultdict(dict)
    for code, (mk, rows) in stocks.items():
        for i in range(5, len(rows)):
            d, o, h, l, c, v, a = rows[i]
            k = a / c
            pa = rows[i - 1][6]
            day[d][code] = (mk, o * k, h * k, a, pa, c * v, rows[i - 5][6], rows[i - 1][4] * rows[i - 1][5])
    e = etf0050()
    big = {r[0]: r for r in e}
    days = sorted(d for d in day if d in big and len(day[d]) > 500)
    agg = {}
    for d in days:
        X = day[d]
        sm = [(x[3] / x[4] - 1, x[3] / x[1] - 1, x[1] / x[4] - 1) for x in X.values() if x[0] == "OTC" and x[7] >= 2e7]
        if len(sm) < 50:
            continue
        lu = sum(1 for x in X.values() if x[3] / x[4] >= 1.095 and x[3] >= x[2] * 0.999)
        adv = sum(1 for x in X.values() if x[3] > x[4]) / len(X)
        tvo = sum(x[5] for x in X.values() if x[0] == "OTC")
        tvt = sum(x[5] for x in X.values() if x[0] == "TSE")
        if tvo <= 0 or tvt <= 0:   # Yahoo 偶爾有成交量全是 0 的日子（颱風假、資料缺）
            continue
        agg[d] = {"s": st.mean(s[0] for s in sm) * 100, "s_id": st.mean(s[1] for s in sm) * 100, "s_on": st.mean(s[2] for s in sm) * 100,
                  "lu": lu, "adv": adv, "otc_sh": tvo / (tvo + tvt)}
    days = [d for d in days if d in agg]
    for i, d in enumerate(days):
        pd_ = days[i - 1] if i else None
        if pd_:
            agg[d]["b"] = (big[d][2] / big[pd_][2] - 1) * 100
            agg[d]["b_id"] = (big[d][2] / big[d][1] - 1) * 100
    tsmc = {r[0]: r[6] for r in stocks["2330"][1]}
    return days, agg, day, tsmc


def features(days, agg, tsmc):
    sox, ixic, vix, tsm, twd = yser("_SOX"), yser("_IXIC"), yser("_VIX"), yser("TSM"), yser("TWD=X")
    ks = {n: sorted(s) for n, s in (("sox", sox), ("ixic", ixic), ("vix", vix), ("tsm", tsm), ("twd", twd))}
    tk = sorted(tsmc)
    rows = []
    for i in range(260, len(days) - 1):
        d, n = days[i], days[i + 1]
        a = agg[d]
        if "b" not in a or "b" not in agg[n]:
            continue
        rel = [agg[days[j]]["s"] - agg[days[j]]["b"] for j in range(i - 19, i + 1)]
        lus = [agg[days[j]]["lu"] for j in range(i - 59, i + 1)]
        sh = [agg[days[j]]["otc_sh"] for j in range(i - 19, i + 1)]
        vol = st.pstdev(agg[days[j]]["s"] for j in range(i - 19, i + 1))
        k = bisect_left(tk, d)
        t240 = [tsmc[x] for x in tk[max(0, k - 239):k + 1]]
        tw0, tw1, tw5 = (twd.get(x) for x in (days[i - 1], days[i - 2], days[i - 6]))
        f = {"rel1": rel[-1], "rel5": sum(rel[-5:]), "rel20": sum(rel), "s_id": a["s_id"], "s_on": a["s_on"], "b": a["b"],
             "lu": a["lu"], "lu3": st.mean(lus[-3:]), "lu_rel": st.mean(lus[-3:]) / (st.mean(lus) + 1), "adv": a["adv"],
             "otc_sh": a["otc_sh"] / st.mean(sh), "tsmc240": tsmc[tk[k]] / max(t240) if k < len(tk) and tk[k] == d else None,
             "vol20": vol, "twd1": (tw0 / tw1 - 1) * 100 if tw0 and tw1 else None, "twd5": (tw0 / tw5 - 1) * 100 if tw0 and tw5 else None}
        pre = {"sox": us_ret(sox, ks["sox"], n, d), "ixic": us_ret(ixic, ks["ixic"], n, d), "vix": us_ret(vix, ks["vix"], n, d), "tsm": us_ret(tsm, ks["tsm"], n, d)}
        rows.append({"d": d, "n": n, "f": f, "pre": pre,
                     "y": agg[n]["s"] - agg[n]["b"], "y_id": agg[n]["s_id"] - agg[n]["b_id"]})
    return rows


def walk(rows, keys, model):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    X = np.array([[np.nan if v is None else v for v in ([r["f"][k] for k in keys if k in r["f"]] + [r["pre"][k] for k in keys if k in r["pre"]])] for r in rows], float)
    y = np.array([r["y"] > 0 for r in rows])
    yrs = np.array([int(r["n"][:4]) for r in rows])
    p = np.full(len(rows), np.nan)
    for Y in range(2016, yrs.max() + 1):
        tr, te = (yrs < Y) & (yrs >= 2012), yrs == Y
        if not te.any():
            continue
        if model == "lr":
            med = np.nanmedian(X[tr], axis=0)
            Xtr, Xte = np.where(np.isnan(X[tr]), med, X[tr]), np.where(np.isnan(X[te]), med, X[te])
            sc = StandardScaler().fit(Xtr)
            m = LogisticRegression(C=0.1, max_iter=1000).fit(sc.transform(Xtr), y[tr])
            p[te] = m.predict_proba(sc.transform(Xte))[:, 1]
        else:
            import lightgbm as lgb
            m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=50, subsample=0.8,
                                   subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0).fit(X[tr], y[tr])
            p[te] = m.predict_proba(X[te])[:, 1]
    return p


def events(days, day):
    """重建 85g：回傳 {事件日: [放空報酬 %, ...]}"""
    out = defaultdict(list)
    for i in range(1, len(days)):
        d, n = days[i - 1], days[i]
        X, Y = day[d], day[n]
        top = sorted(X, key=lambda c: -X[c][5])[:50]
        for c in top:
            x = X[c]
            if c not in Y or not (x[3] / x[4] >= 1.095 or x[3] / x[6] >= 1.10):
                continue
            mk, o, h, a, pa = Y[c][:5]
            gap = (o / pa - 1) * 100
            if not (0 <= gap <= 4):
                continue
            stop = pa * 1.09
            ex = stop if h >= stop else a
            out[n].append((o - ex) / o * 100 - COST)
    return out


def month_t(pairs):
    """pairs: [(月份, 差)] → 月份群聚 t"""
    by = defaultdict(list)
    for m, v in pairs:
        by[m].append(v)
    xs = [st.mean(v) for v in by.values()]
    return (st.mean(xs) / (st.stdev(xs) / math.sqrt(len(xs))), len(xs)) if len(xs) > 2 and st.stdev(xs) else (None, len(xs))


def main():
    days, agg, day, tsmc = build()
    rows = features(days, agg, tsmc)
    close_keys = list(rows[0]["f"])
    all_keys = close_keys + list(rows[0]["pre"])
    out = {"models": {}}
    print(f"樣本 {rows[0]['n']}～{rows[-1]['n']}，{len(rows)} 天；小型股贏的比例 {np.mean([r['y'] > 0 for r in rows]) * 100:.1f}%")
    preds = {}
    for name, keys in (("收盤因子", close_keys), ("收盤＋美股夜盤", all_keys)):
        for model in ("lr", "gbm"):
            p = walk(rows, keys, model)
            preds[(name, model)] = p
            line = {}
            for lab, a, b in PARTS:
                idx = [i for i, r in enumerate(rows) if a <= r["n"] < b and not np.isnan(p[i])]
                hit = np.mean([(p[i] > 0.5) == (rows[i]["y"] > 0) for i in idx])
                w = np.array([abs(rows[i]["y"]) for i in idx])
                whit = np.sum(w * np.array([(p[i] > 0.5) == (rows[i]["y"] > 0) for i in idx])) / w.sum()
                ls = [rows[i]["y"] if p[i] > 0.5 else -rows[i]["y"] for i in idx]
                line[lab] = {"n": len(idx), "hit": round(hit * 100, 1), "whit": round(whit * 100, 1),
                             "ls_bp": round(st.mean(ls) * 100, 1), "ls_ann": round(st.mean(ls) * 245, 1)}
            out["models"][f"{name}/{model}"] = line
            print(f"  {name:10s} {model:3s} " + "  ".join(f"{k}: 命中 {v['hit']}%（加權 {v['whit']}%）多空 {v['ls_bp']:+.1f}bp/天" for k, v in line.items()))
    # 黑K
    ev = events(days, day)
    print(f"\n85g 重建事件：{sum(len(v) for v in ev.values())} 筆、{len(ev)} 天")
    out["blackK"] = {}
    rmap = {r["n"]: i for i, r in enumerate(rows)}
    base = {lab: [x for d, v in ev.items() if a <= d < b for x in v] for lab, a, b in PARTS}
    print("  全部：" + "、".join(f"{lab} {st.mean(v):+.2f}%（{len(v)} 筆）" for lab, v in base.items()))
    # 先看上限：用「真的」隔天大小結果（不可能事先知道）
    for tag, key in (("事後：當天收盤大型股贏", "y"), ("事後：當天盤中大型股贏", "y_id")):
        s = {lab: ([x for d, v in ev.items() if a <= d < b and d in rmap and rows[rmap[d]][key] < 0 for x in v],
                   [x for d, v in ev.items() if a <= d < b and d in rmap and rows[rmap[d]][key] > 0 for x in v]) for lab, a, b in PARTS}
        print(f"  {tag}（上限參考）：" + "、".join(f"{lab} 大贏 {st.mean(g[0]):+.2f}% vs 小贏 {st.mean(g[1]):+.2f}%" for lab, g in s.items()))
    for (name, model), p in preds.items():
        pl = {r["n"]: 1 - p[i] for i, r in enumerate(rows) if not np.isnan(p[i])}  # 大型股贏的機率
        cal = sorted(pl[d] for d in pl if "2016" <= d < "2019")
        lo, hi = cal[len(cal) // 3], cal[2 * len(cal) // 3]
        res = {}
        for lab, a, b in PARTS:
            g = {"低": [], "中": [], "高": []}
            pairs = defaultdict(lambda: {"低": [], "高": []})
            for d, v in ev.items():
                if not (a <= d < b) or d not in pl:
                    continue
                k = "低" if pl[d] < lo else "高" if pl[d] >= hi else "中"
                g[k] += v
                if k != "中":
                    pairs[d[:7]][k] += v
            diff = [(m, st.mean(x["高"]) - st.mean(x["低"])) for m, x in pairs.items() if x["高"] and x["低"]]
            t, nm = month_t(diff)
            res[lab] = {k: {"n": len(v), "avg": round(st.mean(v), 3) if v else None, "win": round(np.mean([x > 0 for x in v]) * 100, 1) if v else None}
                        for k, v in g.items()}
            res[lab]["t"] = round(t, 2) if t else None
            res[lab]["months"] = nm
        out["blackK"][f"{name}/{model}"] = res
        print(f"  {name}/{model} 大型股機率 低／中／高：" + "  ".join(
            f"{lab} {res[lab]['低']['avg']:+.2f}/{res[lab]['中']['avg']:+.2f}/{res[lab]['高']['avg']:+.2f}%（t={res[lab]['t']}）" for lab, _, _ in PARTS))
    (RES / "size_rotation.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
