#!/usr/bin/env python3
"""
台指期日盤短打：每一分鐘預測「接下來先碰到停利還是停損」，機率夠高才進場（進場同時掛好停利／停損），一次 1 口、可重複進場

標記（triple barrier）：第 t 分鐘收盤後、t+1 開盤進場；做多：先碰到 +2s（停利）＝1，先碰到 −s（停損）或 13:30 都沒碰到＝0；做空對稱
      s＝K × ATR20（前 20 天日盤振幅平均），同一分鐘兩邊都碰到算停損
特徵（t 分鐘收盤就知道）：
  盤中：近 1／3／5／15／30 分報酬（÷ATR）、離 VWAP、離開盤區間高低點、離當天高低點、離昨收（÷ATR）、時間、
       近 5 分量 ÷ 當天平均量、近 15 分 1 分 K 振幅平均（÷ATR）
  期現貨（data/market/index1m，2020/8 起）：期貨 − 現貨 價差偏離（減前一天平均）、近 5 分現貨報酬 − 期貨報酬
  每天背景：跳空 ÷ATR、09:15 線上規則（BO＝1、MR＝−1、不做＝0；09:15 前＝0）、開盤區間寬 ÷ATR、前一天效率、夜盤單邊程度、
       前一晚費半報酬、ATR ÷ 指數
模型：LightGBM 分類，做多、做空各一個；逐年滾動（用之前所有年度訓練，預測下一年，2022 起樣本外）
交易模擬：09:15～12:30 每分鐘，空手時取做多／做空機率較大的一邊，≥ 門檻就進場；扣 COST 點
輸出 data/research/tx_ml.json；用法：python scripts/research_tx_ml.py
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_tx_regime as rr  # noqa: E402
import tx_regime_review as trv  # noqa: E402

COST = 3.0
RR = 2.0
START, LAST, EXIT = 30, 225, 285
KS = [0.15, 0.3]
THS = [0.35, 0.4, 0.45, 0.5, 0.55, 0.6]


def yser(name):
    j = json.loads((DATA / "research" / "yahoo" / f"{name}.json").read_text(encoding="utf-8"))["d"]
    return {r[0]: r[4] for r in j if r[4]}


def day_arrays(bars: dict):
    o = np.full(EXIT + 1, np.nan)
    h, l, c, v = o.copy(), o.copy(), o.copy(), np.zeros(EXIT + 1)
    last = None
    for m in range(EXIT + 1):
        b = bars.get(m)
        if b:
            o[m], h[m], l[m], c[m], v[m] = b[0], b[1], b[2], b[3], b[4]
            last = b[3]
        elif last is not None:
            o[m] = h[m] = l[m] = c[m] = last
    return o, h, l, c, v


def labels(o, h, l, c, s):
    """每個 t（START～LAST）：做多／做空的結果（1＝停利先到）、損益點數"""
    yl, ys, pl, ps = {}, {}, {}, {}
    for t in range(START, LAST + 1):
        e = o[t + 1]
        if np.isnan(e):
            continue
        hh, ll = h[t + 1:EXIT + 1], l[t + 1:EXIT + 1]
        for d, Y, P in ((1, yl, pl), (-1, ys, ps)):
            tp, sl = e + d * RR * s, e - d * s
            hit_tp = np.nonzero(hh >= tp)[0] if d > 0 else np.nonzero(ll <= tp)[0]
            hit_sl = np.nonzero(ll <= sl)[0] if d > 0 else np.nonzero(hh >= sl)[0]
            a = hit_tp[0] if len(hit_tp) else 9999
            b = hit_sl[0] if len(hit_sl) else 9999
            if b <= a and b < 9999:
                Y[t], P[t] = 0, -s - COST
            elif a < 9999:
                Y[t], P[t] = 1, RR * s - COST
            else:
                Y[t], P[t] = 0, (c[EXIT] - e) * d - COST
    return yl, ys, pl, ps


def main():
    import lightgbm as lgb
    day = rr.load_dir(DATA / "futures" / "day")
    night = rr.load_dir(DATA / "futures" / "night")
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    idx = {}
    for f in sorted((DATA / "market" / "index1m").glob("20*.json")):
        idx.update(json.loads(f.read_text(encoding="utf-8")))
    sox = yser("_SOX")
    sk = sorted(sox)
    p = trv.params()["current"]
    dates = sorted(d for d, b in day.items() if len(b) >= 250)
    rng = {d: max(x[1] for x in day[d].values()) - min(x[2] for x in day[d].values()) for d in dates}
    closes = {d: rr.LAST_CLOSE.get(d, day[d][max(day[d])][3]) for d in dates}   # 結算日用換月後收盤
    prev_basis = None
    X, meta = [], []      # meta: (日期, t, k 的標記與損益)
    LBL = {k: defaultdict(dict) for k in KS}
    for i, d in enumerate(dates):
        b = day[d]
        o, h, l, c, v = day_arrays(b)
        basis_today = None
        if d in idx:
            t_ = idx[d]["t"]
            bs = [c[k + 15] - t_[k] for k in range(min(271, len(t_))) if t_[k] and not np.isnan(c[k + 15])]
            basis_today = st.mean(bs) if len(bs) > 200 else None
        if i < 21 or d not in reg:
            prev_basis = basis_today
            continue
        atr = st.mean(rng[x] for x in dates[i - 20:i])
        pc = closes[dates[i - 1]]
        r = reg[d]
        plan = trv.decide(r, p)[1]
        planv = 1 if plan == "BO" else -1 if plan == "MR" else 0
        kx = np.searchsorted(sk, d) - 1
        soxr = (sox[sk[kx]] / sox[sk[kx - 1]] - 1) * 100 if kx >= 1 else 0.0
        orh, orl = np.nanmax(h[:30]), np.nanmin(l[:30])
        for K in KS:
            yl, ys, pl, ps = labels(o, h, l, c, K * atr)
            LBL[K][d] = (yl, ys, pl, ps)
        pv = np.nancumsum((h + l + c) / 3 * v)
        cv = np.cumsum(v)
        spot = idx.get(d, {}).get("t")
        for t in range(START, LAST + 1):
            if np.isnan(o[t + 1]):
                continue
            vw = pv[t] / cv[t] if cv[t] else c[t]
            f = [(c[t] - c[t - n]) / atr for n in (1, 3, 5, 15, 30)]
            f += [(c[t] - vw) / atr, (c[t] - orh) / atr, (c[t] - orl) / atr, (c[t] - np.nanmax(h[:t + 1])) / atr, (c[t] - np.nanmin(l[:t + 1])) / atr,
                  (c[t] - pc) / atr, t / 285, v[t - 4:t + 1].mean() / (v[:t + 1].mean() or 1), np.nanmean(h[t - 14:t + 1] - l[t - 14:t + 1]) / atr]
            bd = lead = np.nan
            if spot and t - 15 < len(spot) and t - 20 >= 0 and spot[t - 15] and spot[t - 20] and prev_basis is not None:
                bd = (c[t] - spot[t - 15] - prev_basis) / atr
                lead = (spot[t - 15] / spot[t - 20] - 1) * 100 - (c[t] / c[t - 5] - 1) * 100
            f += [bd, lead, r["gapATR"], planv, r["orATR"], r["prevEff"], r["nightDir"] if r["nightDir"] is not None else np.nan, soxr, r["atrPct"]]
            X.append(f)
            meta.append((d, t))
        prev_basis = basis_today
    X = np.array(X, float)
    yrs = np.array([int(m[0][:4]) for m in meta])
    print(f"樣本 {len(meta)} 分鐘（{meta[0][0]}～{meta[-1][0]}）")
    out = {"res": {}}
    for K in KS:
        yl = np.array([LBL[K][d][0].get(t, 0) for d, t in meta])
        ysh = np.array([LBL[K][d][1].get(t, 0) for d, t in meta])
        pL, pS = np.full(len(meta), np.nan), np.full(len(meta), np.nan)
        kw = dict(n_estimators=300, learning_rate=0.03, num_leaves=31, min_child_samples=200, subsample=0.8, subsample_freq=1,
                  colsample_bytree=0.8, verbose=-1, random_state=0)
        for Y in range(2022, yrs.max() + 1):
            tr, te = yrs < Y, yrs == Y
            pL[te] = lgb.LGBMClassifier(**kw).fit(X[tr], yl[tr]).predict_proba(X[te])[:, 1]
            pS[te] = lgb.LGBMClassifier(**kw).fit(X[tr], ysh[tr]).predict_proba(X[te])[:, 1]
        base_l, base_s = yl[yrs >= 2022].mean(), ysh[yrs >= 2022].mean()
        print(f"\n■ 停損 {K}×ATR、停利 {RR * K:g}×ATR：樣本外（2022 起）停利先到的比例 做多 {base_l:.1%}、做空 {base_s:.1%}（不挑時機的勝率）")
        # 逐日模擬（一次一口）
        pos_by_day = defaultdict(list)
        for j, (d, t) in enumerate(meta):
            if not np.isnan(pL[j]):
                pos_by_day[d].append((t, pL[j], pS[j]))
        res = {}
        for th in THS:
            per_year = defaultdict(lambda: {"pts": [], "tr": [], "days": 0})
            for d, rows in pos_by_day.items():
                yl_d, ys_d, pl_d, ps_d = LBL[K][d]
                busy_until = -1
                pts = []
                for t, a, b_ in sorted(rows):
                    if t <= busy_until:
                        continue
                    dirn = 1 if a >= b_ else -1
                    pr = a if dirn > 0 else b_
                    if pr < th:
                        continue
                    pnl = pl_d.get(t) if dirn > 0 else ps_d.get(t)
                    if pnl is None:
                        continue
                    pts.append(pnl)
                    # 部位持有到出場那一分鐘（重算出場時間）
                    busy_until = exit_minute(day[d], t, dirn, K, d, dates, rng)
                y = per_year[d[:4]]
                y["pts"].append(sum(pts))
                y["tr"] += pts
                y["days"] += 1
            line = {}
            for yv, z in sorted(per_year.items()):
                trs = z["tr"]
                line[yv] = {"perDay": round(sum(z["pts"]) / z["days"], 1), "trades": round(len(trs) / z["days"], 2),
                            "win": round(sum(x > 0 for x in trs) / len(trs) * 100, 1) if trs else None}
            res[th] = line
            print(f"  門檻 {th:.2f}：" + "｜".join(f"{yv} 每天 {z['perDay']:+.1f} 點、{z['trades']:.1f} 筆、勝率 {z['win']}%" for yv, z in line.items()))
        out["res"][K] = res
        if K == 0.3:
            # 折衷：方向照 09:15 規則（research_tx_scalp 的 REGIME 訊號），模型機率 ≥ 門檻才進場
            import random
            import research_tx_scalp as sc
            pm = {(d, t): (pL[j], pS[j]) for j, (d, t) in enumerate(meta) if not np.isnan(pL[j])}
            rnd = random.Random(7)
            for th in (0.0, 0.08, 0.1, 0.12, 0.15, 0.2):
                per_year = defaultdict(list)
                wins = defaultdict(list)
                for d in sorted({m[0] for m in meta}):
                    if d < "2022" or d not in reg:
                        continue
                    i = dates.index(d)
                    atr = st.mean(rng[x] for x in dates[i - 20:i])
                    plan = trv.decide(reg[d], p)[1]
                    sig = sc.signals(day[d], "REGIME_BO", atr, plan, 0, rnd) if plan == "BO" else \
                        sc.signals(day[d], "REGIME_MR", atr, plan, 0, rnd) if plan == "MR" else {}
                    sig = {t: dr for t, dr in sig.items() if (d, t) in pm and pm[(d, t)][0 if dr > 0 else 1] >= th}
                    tr = sc.run_day(day[d], sig, K * atr)
                    per_year[d[:4]].append(sum(tr))
                    wins[d[:4]] += tr
                print(f"  規則方向＋模型機率 ≥ {th:.2f}：" + "｜".join(
                    f"{yv} 每天 {st.mean(v):+.1f} 點、勝率 {sum(x > 0 for x in wins[yv]) / max(1, len(wins[yv])) * 100:.0f}%、{len(wins[yv]) / len(v):.1f} 筆"
                    for yv, v in sorted(per_year.items())))
    (DATA / "research" / "tx_ml.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    return 0


_EXIT_CACHE = {}


def exit_minute(bars, t, dirn, K, d, dates, rng):
    """t 收盤後進場的這筆在哪一分鐘出場（給「一次一口」用）"""
    key = (d, t, dirn, K)
    if key in _EXIT_CACHE:
        return _EXIT_CACHE[key]
    i = dates.index(d)
    s = K * st.mean(rng[x] for x in dates[i - 20:i])
    o, h, l, c, v = day_arrays(bars)
    e = o[t + 1]
    tp, sl = e + dirn * RR * s, e - dirn * s
    m_out = EXIT
    for m in range(t + 1, EXIT + 1):
        if (dirn > 0 and (l[m] <= sl or h[m] >= tp)) or (dirn < 0 and (h[m] >= sl or l[m] <= tp)):
            m_out = m
            break
    _EXIT_CACHE[key] = m_out
    return m_out


if __name__ == "__main__":
    sys.exit(main())
