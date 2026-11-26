#!/usr/bin/env python3
"""
大小型股預測（每天 08:25，給當沖空策略過濾用）：今天「大型股（0050）贏過小型股（上櫃等權）」的機率

研究：scripts/research_size_rotation.py（2016 起逐年滾動樣本外；預測「大型股贏」機率最低 1/3 的日子，
  85g 開高走低、高週轉＋漲停開盤空收盤補平均約 0% 甚至虧損，其他日子 +0.3～0.7%，三段期間都成立）
因子：收盤時的大小股強弱、漲停家數、上漲家數比例、上櫃成交比重、台積電離 240 日高點、小型股波動、新台幣，
     加上前一晚美股（費半、那斯達克、VIX、台積電 ADR）
模型：LightGBM（200 棵、8 葉），樹存成 JSON 用純 Python 算，Actions 不用裝套件
門檻：低／高＝2023 起樣本外預測的 1/3、2/3 分位（線上預測也是樣本外，分布才對得上）

用法：
  python scripts/size_signal.py fit     # 重新訓練（需要 data/research/yahoo_adj，fetch_yahoo_adj.py；建議每年一次）
  python scripts/size_signal.py         # 每天：data/daily＋Yahoo（0050、台積電、匯率、美股）→ data/strategy/size_signal.json＋size_journal.json
  python scripts/size_signal.py check   # 比對線上算的因子和研究版（重疊日期）
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
MODEL = DATA / "strategy" / "size_model.json"
OUT = DATA / "strategy" / "size_signal.json"
JOURNAL = DATA / "strategy" / "size_journal.json"
TPE = timezone(timedelta(hours=8))
YSYM = {"2330": "2330.TW", "twd": "TWD=X", "sox": "^SOX", "ixic": "^IXIC", "vix": "^VIX", "tsm": "TSM"}


# ---------- 樹模型 ----------
def _node(n, x):
    while "leaf_value" not in n:
        v = x[n["split_feature"]]
        miss = n.get("missing_type", "None")
        isnan = v is None or (isinstance(v, float) and math.isnan(v))
        if miss == "NaN" and isnan or miss == "Zero" and (isnan or v == 0):
            go_left = n["default_left"]
        else:
            if isnan:
                v = 0.0
            go_left = v <= n["threshold"]
        n = n["left_child"] if go_left else n["right_child"]
    return n["leaf_value"]


def predict(model: dict, x: list) -> float:
    """回傳「小型股贏」的機率"""
    s = sum(_node(t["tree_structure"], x) for t in model["trees"])
    return 1 / (1 + math.exp(-s))


def fit():
    sys.path.insert(0, str(ROOT / "scripts"))
    import lightgbm as lgb
    import numpy as np
    import research_size_rotation as r
    days, agg, day, tsmc = r.build()
    rows = r.features(days, agg, tsmc)
    keys = list(rows[0]["f"]) + list(rows[0]["pre"])
    X = np.array([[np.nan if v is None else v for v in ([x["f"][k] for k in keys if k in x["f"]] + [x["pre"][k] for k in keys if k in x["pre"]])] for x in rows], float)
    y = np.array([x["y"] > 0 for x in rows])
    m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=50, subsample=0.8,
                           subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0).fit(X, y)
    oos = r.walk(rows, keys, "gbm")
    pl = sorted(1 - oos[i] for i, x in enumerate(rows) if x["n"] >= "2023" and not np.isnan(oos[i]))
    dump = m.booster_.dump_model()
    model = {"features": keys, "trees": dump["tree_info"], "trainedTo": rows[-1]["n"], "n": len(rows),
             "lo": pl[len(pl) // 3], "hi": pl[2 * len(pl) // 3], "fittedAt": datetime.now(TPE).strftime("%Y-%m-%d")}
    # 純 Python 版和 LightGBM 對答案
    ref = m.predict_proba(X[-300:])[:, 1]
    mine = [predict(model, [None if math.isnan(v) else v for v in row]) for row in X[-300:]]
    err = max(abs(a - b) for a, b in zip(ref, mine))
    assert err < 1e-6, f"樹模型計算不一致 {err}"
    MODEL.write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")
    print(f"訓練到 {model['trainedTo']}（{len(rows)} 天）；大型股機率門檻 低 < {model['lo']:.3f}、高 ≥ {model['hi']:.3f}；最大誤差 {err:.1e}")
    return 0


# ---------- 每天的因子 ----------
def yahoo(sym: str, days_back: int = 500):
    import requests
    for i in range(3):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", timeout=30, headers={"User-Agent": "Mozilla/5.0"},
                             params={"period1": int(time.time()) - days_back * 86400, "period2": int(time.time()) + 86400, "interval": "1d"})
            res = r.json()["chart"]["result"][0]
            off = res["meta"].get("gmtoffset") or 0
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            out = {}
            for t, c, a in zip(res["timestamp"], q["close"], adj):
                if c and a:
                    out[datetime.fromtimestamp(t + off, timezone.utc).date().isoformat()] = a
            return out
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            time.sleep(3 * (i + 1))
    return {}


def daily_agg(before: str):
    """data/daily → 每天的小型股等權報酬、漲停家數、上漲比例、上櫃成交比重（定義同研究版）"""
    files = sorted(f for f in glob.glob(str(DATA / "daily" / "20*.json")) if Path(f).stem < before)
    agg, prev_val = {}, {}
    for f in files:
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        q = j.get("q") or {}
        sm, lu, up, n, tvo, tvt, val = [], 0, 0, 0, 0.0, 0.0, {}
        e = q.get("0050")
        b = (e[6] / (e[5] - e[6]) * 100) if e and e[5] and e[6] is not None and e[5] - e[6] > 0 else None
        for c, v in q.items():
            if len(c) != 4 or not c.isdigit() or c[0] == "0":
                continue
            try:
                mk, o, h, l, cl, chg, value = v[1], v[2], v[3], v[4], v[5], v[6], v[8]
            except (IndexError, TypeError):
                continue
            if not (o and h and l and cl) or chg is None:
                continue
            pc = cl - chg
            if pc <= 0:
                continue
            val[c] = value or 0
            n += 1
            up += cl > pc
            lu += cl / pc >= 1.095 and cl >= h * 0.999
            if mk == 1:
                tvo += value or 0
                if prev_val.get(c, 0) >= 2e7:
                    sm.append((cl / pc - 1, cl / o - 1, o / pc - 1))
            else:
                tvt += value or 0
        prev_val = val
        if len(sm) >= 50 and tvo > 0 and tvt > 0 and b is not None:
            agg[Path(f).stem] = {"b": b, "s": st.mean(x[0] for x in sm) * 100, "s_id": st.mean(x[1] for x in sm) * 100,
                                 "s_on": st.mean(x[2] for x in sm) * 100, "lu": lu, "adv": up / n, "otc_sh": tvo / (tvo + tvt)}
    return agg


def us_ret(ser: dict, today: str):
    ks = sorted(ser)
    k = bisect_left(ks, today) - 1
    return (ser[ks[k]] / ser[ks[k - 1]] - 1) * 100 if k >= 1 else None


def live_features(today: str, agg: dict | None = None, ys: dict | None = None):
    agg = agg if agg is not None else daily_agg(today)
    ys = ys if ys is not None else {k: yahoo(s) for k, s in YSYM.items()}
    days = sorted(agg)   # 0050 報酬直接用 data/daily 的漲跌（除息日是對參考價，等於還原報酬）
    if len(days) < 60:
        raise SystemExit(f"data/daily 只有 {len(days)} 天，至少要 60 天")
    d = days[-1]
    a = agg[d]
    rel = [agg[x]["s"] - agg[x]["b"] for x in days[-20:]]
    lus = [agg[x]["lu"] for x in days[-60:]]
    sh = [agg[x]["otc_sh"] for x in days[-20:]]
    ts = ys["2330"]
    tk = [x for x in sorted(ts) if x <= d]
    twd = ys["twd"]
    tw0, tw1, tw5 = (twd.get(days[-k]) for k in (2, 3, 7))
    f = {"rel1": rel[-1], "rel5": sum(rel[-5:]), "rel20": sum(rel), "s_id": a["s_id"], "s_on": a["s_on"], "b": a["b"],
         "lu": a["lu"], "lu3": st.mean(lus[-3:]), "lu_rel": st.mean(lus[-3:]) / (st.mean(lus) + 1), "adv": a["adv"],
         "otc_sh": a["otc_sh"] / st.mean(sh), "tsmc240": ts[tk[-1]] / max(ts[x] for x in tk[-240:]) if tk and tk[-1] >= days[-3] else None,
         "vol20": st.pstdev(agg[x]["s"] for x in days[-20:]),
         "twd1": (tw0 / tw1 - 1) * 100 if tw0 and tw1 else None, "twd5": (tw0 / tw5 - 1) * 100 if tw0 and tw5 else None}
    pre = {k: us_ret(ys[k], today) for k in ("sox", "ixic", "vix", "tsm")}
    return d, {**f, **pre}


def tier(model, p_large):
    return "低" if p_large < model["lo"] else "高" if p_large >= model["hi"] else "中"


def run():
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    now = datetime.now(TPE).date()
    today = now.isoformat()
    try:
        hol = set(json.loads((DATA / "calendar.json").read_text(encoding="utf-8")).get("holidays", []))
    except (OSError, ValueError):
        hol = set()
    if now.weekday() >= 5 or today in hol:
        print("今天休市")
        return 0
    asof, f = live_features(today)
    x = [f.get(k) for k in model["features"]]
    p_large = 1 - predict(model, x)
    t = tier(model, p_large)
    doc = {"date": today, "asof": asof, "pLarge": round(p_large, 4), "tier": t, "lo": model["lo"], "hi": model["hi"],
           "features": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()},
           "updatedAt": datetime.now(TPE).strftime("%Y-%m-%dT%H:%M+08:00")}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        jr = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        jr = {}
    jr[today] = {"asof": asof, "pLarge": doc["pLarge"], "tier": t}
    JOURNAL.write_text(json.dumps(dict(sorted(jr.items())[-500:]), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{today}（依 {asof} 收盤＋前一晚美股）：大型股贏的機率 {p_large:.1%} → {t}"
          f"（門檻 {model['lo']:.3f}／{model['hi']:.3f}）；缺值 {[k for k, v in f.items() if v is None]}")
    return 0


def check():
    """線上版（data/daily）和研究版（yahoo_adj）的因子在重疊日期比對"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import research_size_rotation as r
    days, agg, day, tsmc = r.build()
    rows = {x["n"]: x for x in r.features(days, agg, tsmc)}
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    ys = {k: yahoo(s, 900) for k, s in YSYM.items()}
    full = daily_agg("9999")
    dd = sorted(full)
    diffs = []
    for n in [x for x in sorted(rows) if x > dd[0]][-40:]:
        sub = {k: dict(v) for k, v in full.items() if k < n}
        try:
            _, f = live_features(n, sub, ys)
        except SystemExit:
            continue
        ref = {**rows[n]["f"], **rows[n]["pre"]}
        pl_live = 1 - predict(model, [f.get(k) for k in model["features"]])
        pl_ref = 1 - predict(model, [ref.get(k) for k in model["features"]])
        diffs.append((n, pl_live, pl_ref, tier(model, pl_live), tier(model, pl_ref),
                      {k: (round(f[k], 3) if f[k] is not None else None, round(ref[k], 3) if ref[k] is not None else None) for k in model["features"]
                       if f.get(k) is None or ref.get(k) is None or abs(f[k] - ref[k]) > 0.05 * (abs(ref[k]) + 0.1)}))
    same = sum(a[3] == a[4] for a in diffs)
    for n, a, b, ta, tb, bad in diffs[-15:]:
        print(n, f"線上 {a:.3f}{ta} 研究 {b:.3f}{tb}", bad)
    print(f"分組一致 {same}/{len(diffs)}；機率平均差 {st.mean(abs(a[1] - a[2]) for a in diffs):.3f}")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    sys.exit({"fit": fit, "check": check}.get(mode, run)())
