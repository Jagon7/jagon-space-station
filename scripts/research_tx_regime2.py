#!/usr/bin/env python3
"""
台指期日盤型態研究（二）：依開盤跳空、波動 regime、期現貨價差、上市／上櫃強弱，決定 BO／MR／突破門檻

使用者假設：
  ① 開平（跳空小）→ 相對波動低，雜訊多，突破要加門檻（OR 外再多走一段才算突破）
  ② 開很遠 → 向上或向下突破的機率比較高，BO 有利
  ③ 要分很多 regime：開盤 %、昨日波動、近 N 日波動、昨日日內 TR、近 N 日 TR……
  ④ 和 TSE／OTC 的價差是關鍵
做法（09:15 決策，跟線上規則同一時間點）：
  結果：BO（原本，OR 一破就進）、BO+k（OR 外再走 k × OR 寬度才進，k＝0.1／0.2／0.3／0.5）、MR（09:15～09:29 碰邊界逆勢，線上規則）
  因子：跳空 %／ATR、昨日振幅、昨日 TR（含跳空）、ATR5÷ATR20、近 20 日報酬波動、近 3 日振幅÷ATR20、夜盤振幅與方向、
       夜盤收盤到日盤開盤的缺口、OR 寬度、VWAP 穿越、量能、09:15 位置、跳空回補、
       期現貨價差（09:15 台指期 − 加權指數，減前一天平均）、現貨開盤跳空、09:15 類股齊漲齊跌比例、
       上市／上櫃：前一天上櫃等權 − 0050、開盤前「大型股贏」機率（scripts/research_size_rotation.py 逐年滾動樣本外）、前一晚費半
  驗證：分組門檻只用 2020-22 決定；看 2020-22／2023-24／2025+ 三段方向是否一致；月份群聚 t 值
  另外：① 依跳空分組的最佳突破門檻 ② 跳空 × 波動 regime 的 2D 分組（2020-22 選做法，後兩段驗證）
       ③ LightGBM 逐年滾動（預測 BO、MR 損益，選大的；2022 起樣本外），都和線上規則（tx_regime_review.decide）比
輸出 data/research/tx_regime2.json；用法：python scripts/research_tx_regime2.py
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_tx_regime as rr  # noqa: E402
import tx_regime_review as trv  # noqa: E402

KS = (0.0, 0.1, 0.2, 0.3, 0.5)
PARTS = (("2020-22", "2020", "2023"), ("2023-24", "2023", "2025"), ("2025+", "2025", "2100"))
TRAIN_END = "2023"


def sim_bo(bars: dict, orh: float, orl: float, off: float):
    """OR 外再走 off 點才進場（第一個被觸發的方向），停損在 OR 另一側，13:30 出場；沒觸發＝0"""
    pos = None
    last = None
    for m in range(rr.OR_M, rr.EXIT_M + 1):
        b = bars.get(m)
        if not b:
            continue
        o, h, lo, c = b[0], b[1], b[2], b[3]
        last = c
        if pos is None:
            if h > orh + off:
                pos = (1, max(o, orh + off), orl)
            elif lo < orl - off:
                pos = (-1, min(o, orl - off), orh)
            if pos is None:
                continue
            d, ent, stop = pos
            # 進場那根 K 棒如果也碰到停損（極少），當作停損
            if (d > 0 and lo <= stop) or (d < 0 and h >= stop):
                return (stop - ent) * d - rr.COST
            continue
        d, ent, stop = pos
        if (d > 0 and lo <= stop) or (d < 0 and h >= stop):
            return (stop - ent) * d - rr.COST
    if pos and last is not None:
        return (last - pos[1]) * pos[0] - rr.COST
    return 0.0


def yser(name):
    j = json.loads((DATA / "research" / "yahoo" / f"{name}.json").read_text(encoding="utf-8"))["d"]
    return {r[0]: r[4] for r in j if r[4]}


def build_rows():
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    day = rr.load_dir(DATA / "futures" / "day")
    night = rr.load_dir(DATA / "futures" / "night")
    idx = {}
    for f in sorted((DATA / "market" / "index1m").glob("20*.json")):
        idx.update(json.loads(f.read_text(encoding="utf-8")))
    # 上市／上櫃（研究版，日線）
    size = {}
    try:
        import numpy as np
        import research_size_rotation as rs
        days_, agg, _, tsmc = rs.build()
        srows = rs.features(days_, agg, tsmc)
        keys = list(srows[0]["f"]) + list(srows[0]["pre"])
        p = rs.walk(srows, keys, "gbm")
        for i, x in enumerate(srows):
            size[x["n"]] = {"rel1": x["f"]["rel1"], "rel5": x["f"]["rel5"], "pLarge": None if np.isnan(p[i]) else 1 - p[i], "sox": x["pre"]["sox"]}
    except Exception as e:  # noqa: BLE001
        print("上市櫃因子略過：", e)
    dates = sorted(d for d, b in day.items() if len(b) >= 250 and rr.OR_M in b)
    hist, rows = [], []
    prev_basis = None
    for d in dates:
        bars = day[d]
        ms = sorted(bars)
        o = bars[ms[0]][0]
        hi = max(b[1] for b in bars.values())
        lo = min(b[2] for b in bars.values())
        cl = bars[ms[-1]][3]
        # 期現貨價差（今天全天平均，給明天用）
        basis_today = None
        if d in idx:
            t = idx[d]["t"]
            bs = [bars[k + 15][3] - t[k] for k in range(min(271, len(t))) if bars.get(k + 15) and t[k]]
            basis_today = st.mean(bs) if len(bs) >= 200 else None
        r = reg.get(d)
        if len(hist) >= 21 and r:
            pc = hist[-1]["c"]
            atr20 = st.mean(h["h"] - h["l"] for h in hist[-20:])
            atr5 = st.mean(h["h"] - h["l"] for h in hist[-5:])
            prev = hist[-1]
            ptr = max(prev["h"], hist[-2]["c"]) - min(prev["l"], hist[-2]["c"])
            rets = [hist[k]["c"] / hist[k - 1]["c"] - 1 for k in range(len(hist) - 20, len(hist))]
            orb = [bars[m] for m in range(rr.OR_M) if m in bars]
            orh, orl = max(b[1] for b in orb), min(b[2] for b in orb)
            w = orh - orl
            nk = max((k for k in night if k < d), default=None)
            nb = night.get(nk) if nk and (date.fromisoformat(d) - date.fromisoformat(nk)).days <= 4 else None
            n_close = nb[max(nb)][3] if nb else None
            f = {k: r.get(k) for k in ("gapATR", "absGapATR", "prevRangeATR", "prevEff", "atrPct", "nightRangeATR", "nightDir", "orATR",
                                       "vwapCross30", "rvol30", "pos915")}
            f.update({
                "gapFilled30": int(bool(r.get("gapFilled30"))), "openOutside": int(bool(r.get("openOutside"))),
                "gapPct": (o / pc - 1) * 100, "absGapPct": abs(o / pc - 1) * 100,
                "prevTR_ATR": ptr / atr20, "atr5_20": atr5 / atr20, "rv20": st.pstdev(rets) * 100,
                "rng3_ATR": st.mean(h["h"] - h["l"] for h in hist[-3:]) / atr20,
                "nightGapATR": (o - n_close) / atr20 if n_close else None,
                "orPct": w / o * 100,
            })
            if d in idx and prev_basis is not None:
                t = idx[d]["t"]
                b915 = bars.get(30)
                if b915 and t[15]:
                    f["basisDev"] = (b915[3] - t[15] - prev_basis["avg"]) / t[15] * 100
                if t[0] and prev_basis.get("close"):
                    f["spotGap"] = (t[0] / prev_basis["close"] - 1) * 100
                    f["futSpotGapDiff"] = f["gapPct"] - f["spotGap"]   # 期貨跳空 − 現貨跳空
                s_now, s_prev = idx[d]["s"], idx[prev_basis["d"]]["s"]
                mkt = t[15] / prev_basis["close"] - 1 if prev_basis["close"] and t[15] else 0
                same = tot = 0
                for name, v in s_now.items():
                    pv = (s_prev.get(name) or [None] * 5)[4]
                    if len(v) > 1 and v[1] and pv:
                        tot += 1
                        same += (v[1] / pv - 1) * mkt > 0
                f["breadth915"] = same / tot if tot else None
            sz = size.get(d) or {}
            f.update({"rel1": sz.get("rel1"), "rel5": sz.get("rel5"), "pLarge": sz.get("pLarge"), "sox": sz.get("sox")})
            res = {"bo": r["bo"], "mr": r["mr"]}
            for k in KS[1:]:
                res[f"bo{k}"] = sim_bo(bars, orh, orl, k * w)
            live = trv.decide(r, trv.params()["current"])[1]
            res["live"] = trv.pnl(r, live)
            rows.append({"d": d, "f": f, "y": res, "liveAct": live})
        hist.append({"d": d, "o": o, "h": hi, "l": lo, "c": cl})
        if d in idx:
            t = idx[d]["t"]
            prev_basis = {"d": d, "avg": basis_today, "close": next((x for x in reversed(t) if x), None)} if basis_today is not None else None
    return rows


def month_t(pairs):
    by = defaultdict(list)
    for m, v in pairs:
        by[m].append(v)
    xs = [st.mean(v) for v in by.values()]
    return round(st.mean(xs) / (st.stdev(xs) / math.sqrt(len(xs))), 2) if len(xs) > 2 and st.stdev(xs) else None


def avg(xs):
    return round(st.mean(xs), 1) if xs else None


def part_rows(rows, a, b):
    return [r for r in rows if a <= r["d"] < b]


def main():
    rows = build_rows()
    print(f"{rows[0]['d']}～{rows[-1]['d']}，{len(rows)} 天；每筆扣 {rr.COST} 點")
    out = {"n": len(rows), "from": rows[0]["d"], "to": rows[-1]["d"]}
    # 基準
    print("\n■ 基準（每天平均點數）")
    base = {}
    for lab, a, b in PARTS:
        rs = part_rows(rows, a, b)
        base[lab] = {k: avg([r["y"][k] for r in rs]) for k in ("bo", "bo0.1", "bo0.2", "bo0.3", "bo0.5", "mr", "live")}
        print(f"  {lab}（{len(rs)} 天）：" + "  ".join(f"{k} {v:+.1f}" for k, v in base[lab].items()))
    out["base"] = base
    # ① 假設：依 |跳空|／ATR 分三組，突破門檻 k 怎麼選
    train = [r for r in rows if r["d"] < TRAIN_END]
    print("\n■ ① 跳空大小 × 突破門檻（OR 外再走 k × OR 寬度才進場）；分組門檻用 2020-22")
    out["gapK"] = {}
    for feat in ("absGapATR", "absGapPct"):
        xs = sorted(r["f"][feat] for r in train if r["f"].get(feat) is not None)
        c1, c2 = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        out["gapK"][feat] = {"cut": [c1, c2]}
        print(f"  {feat}（門檻 {c1:.2f}／{c2:.2f}）")
        for g, gf in (("小", lambda v: v <= c1), ("中", lambda v: c1 < v <= c2), ("大", lambda v: v > c2)):
            line = {}
            for lab, a, b in PARTS:
                rs = [r for r in part_rows(rows, a, b) if r["f"].get(feat) is not None and gf(r["f"][feat])]
                line[lab] = {"n": len(rs), **{("bo" if k == 0 else f"bo{k}"): avg([r["y"]["bo" if k == 0 else f"bo{k}"] for r in rs]) for k in KS},
                             "mr": avg([r["y"]["mr"] for r in rs])}
            out["gapK"][feat][g] = line
            print(f"    跳空{g}：" + "｜".join(f"{lab} n{v['n']} BO {v['bo']:+.1f} +0.1 {v['bo0.1']:+.1f} +0.2 {v['bo0.2']:+.1f} +0.3 {v['bo0.3']:+.1f} +0.5 {v['bo0.5']:+.1f} MR {v['mr']:+.1f}"
                                          for lab, v in line.items()))
    # ② 單因子掃描：三分位（2020-22 決定），看 BO−MR 差異在三段是否同方向
    print("\n■ ② 單因子：低／高三分位的（BO − MR）平均點數，三段同方向且月份群聚 t 夠大的才標 ✓")
    feats = sorted({k for r in rows for k in r["f"]})
    out["single"] = {}
    for k in feats:
        xs = sorted(r["f"][k] for r in train if r["f"].get(k) is not None)
        if len(xs) < 150 or xs[len(xs) // 3] == xs[2 * len(xs) // 3]:
            continue
        c1, c2 = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        res = {}
        for lab, a, b in PARTS:
            rs = [r for r in part_rows(rows, a, b) if r["f"].get(k) is not None]
            lo_ = [r for r in rs if r["f"][k] <= c1]
            hi_ = [r for r in rs if r["f"][k] > c2]
            d_lo = [r["y"]["bo"] - r["y"]["mr"] for r in lo_]
            d_hi = [r["y"]["bo"] - r["y"]["mr"] for r in hi_]
            if len(d_lo) < 15 or len(d_hi) < 15:
                continue
            by = defaultdict(lambda: {"lo": [], "hi": []})
            for r in lo_:
                by[r["d"][:7]]["lo"].append(r["y"]["bo"] - r["y"]["mr"])
            for r in hi_:
                by[r["d"][:7]]["hi"].append(r["y"]["bo"] - r["y"]["mr"])
            t = month_t([(m, st.mean(v["hi"]) - st.mean(v["lo"])) for m, v in by.items() if v["hi"] and v["lo"]])
            res[lab] = {"lo": avg(d_lo), "hi": avg(d_hi), "loBO": avg([r["y"]["bo"] for r in lo_]), "hiBO": avg([r["y"]["bo"] for r in hi_]),
                        "loMR": avg([r["y"]["mr"] for r in lo_]), "hiMR": avg([r["y"]["mr"] for r in hi_]), "t": t, "n": [len(lo_), len(hi_)]}
        if len(res) < 3:
            continue
        sgn = [math.copysign(1, v["hi"] - v["lo"]) for v in res.values()]
        ok = len(set(sgn)) == 1 and all(v["t"] is not None and abs(v["t"]) >= 1.5 for v in res.values())
        out["single"][k] = {"cut": [c1, c2], "parts": res, "consistent": ok}
        print(f"  {'✓' if ok else ' '} {k:14s} 門檻 {c1:7.3f}／{c2:7.3f}：" + "｜".join(
            f"{lab} 低 {v['lo']:+6.1f}（BO {v['loBO']:+.0f} MR {v['loMR']:+.0f}）高 {v['hi']:+6.1f}（BO {v['hiBO']:+.0f} MR {v['hiMR']:+.0f}）t {v['t']}" for lab, v in res.items()))
    # ③ 2D regime：跳空 × 波動（ATR5÷ATR20）、跳空 × 期現貨價差、跳空 × 上市櫃；2020-22 選做法，後兩段驗證
    print("\n■ ③ 2D 分組：每格用 2020-22 選做法（BO、BO+k、MR、不做），看後兩段；和線上規則比")
    acts = ["bo"] + [f"bo{k}" for k in KS[1:]] + ["mr", "none"]
    out["grid"] = {}
    for fa, fb in (("absGapATR", "atr5_20"), ("absGapATR", "prevTR_ATR"), ("absGapATR", "orATR"), ("absGapATR", "basisDev"),
                   ("absGapATR", "pLarge"), ("absGapATR", "rel1"), ("gapATR", "nightGapATR"), ("orATR", "atr5_20")):
        def cuts(k):
            xs = sorted(r["f"][k] for r in train if r["f"].get(k) is not None)
            return (xs[len(xs) // 3], xs[2 * len(xs) // 3]) if len(xs) > 100 else None
        ca, cb = cuts(fa), cuts(fb)
        if not ca or not cb:
            continue
        cell = lambda r: (sum(r["f"][fa] > c for c in ca), sum(r["f"][fb] > c for c in cb)) if r["f"].get(fa) is not None and r["f"].get(fb) is not None else None  # noqa: E731
        choice = {}
        for c in {cell(r) for r in train} - {None}:
            rs = [r for r in train if cell(r) == c]
            sc = {a: st.mean(r["y"][a] if a != "none" else 0.0 for r in rs) for a in acts}
            choice[c] = max(sc, key=sc.get)
        res = {}
        for lab, a, b in PARTS:
            rs = [r for r in part_rows(rows, a, b) if cell(r) is not None and cell(r) in choice]
            got = [r["y"][choice[cell(r)]] if choice[cell(r)] != "none" else 0.0 for r in rs]
            live = [r["y"]["live"] for r in rs]
            diff = [(r["d"][:7], g - lv) for r, g, lv in zip(rs, got, live)]
            res[lab] = {"n": len(rs), "grid": avg(got), "live": avg(live), "t": month_t(diff)}
        out["grid"][f"{fa}×{fb}"] = {"choice": {f"{k[0]}{k[1]}": v for k, v in sorted(choice.items())}, "parts": res}
        print(f"  {fa} × {fb}：做法 " + " ".join(f"{k[0]}{k[1]}:{v}" for k, v in sorted(choice.items())))
        print("     " + "｜".join(f"{lab} 分組 {v['grid']:+.1f} vs 線上 {v['live']:+.1f}（t {v['t']}）" for lab, v in res.items()))
    # ④ LightGBM 逐年滾動
    print("\n■ ④ LightGBM 逐年滾動：預測 BO、MR 損益，選比較大的（都 < 0 就不做）")
    try:
        import lightgbm as lgb
        import numpy as np
        X = np.array([[np.nan if r["f"].get(k) is None else r["f"][k] for k in feats] for r in rows], float)
        yb = np.array([r["y"]["bo"] for r in rows])
        ym = np.array([r["y"]["mr"] for r in rows])
        yrs = np.array([int(r["d"][:4]) for r in rows])
        pb, pm = np.full(len(rows), np.nan), np.full(len(rows), np.nan)
        for Y in range(2022, yrs.max() + 1):
            tr, te = yrs < Y, yrs == Y
            kw = dict(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=40, subsample=0.8, subsample_freq=1,
                      colsample_bytree=0.8, verbose=-1, random_state=0)
            pb[te] = lgb.LGBMRegressor(**kw).fit(X[tr], yb[tr]).predict(X[te])
            pm[te] = lgb.LGBMRegressor(**kw).fit(X[tr], ym[tr]).predict(X[te])
        out["gbm"] = {}
        for lab, a, b in (("2022", "2022", "2023"), ("2023-24", "2023", "2025"), ("2025+", "2025", "2100")):
            ii = [i for i, r in enumerate(rows) if a <= r["d"] < b and not np.isnan(pb[i])]
            got = [(yb[i] if pb[i] >= pm[i] else ym[i]) if max(pb[i], pm[i]) > 0 else 0.0 for i in ii]
            live = [rows[i]["y"]["live"] for i in ii]
            t = month_t([(rows[i]["d"][:7], g - lv) for i, g, lv in zip(ii, got, live)])
            out["gbm"][lab] = {"n": len(ii), "gbm": avg(got), "live": avg(live), "t": t}
            print(f"  {lab}：模型 {avg(got):+.1f} vs 線上 {avg(live):+.1f}（{len(ii)} 天，t {t}）")
        m = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=40, verbose=-1, random_state=0).fit(X, yb - ym)
        imp = sorted(zip(feats, m.feature_importances_), key=lambda x: -x[1])[:12]
        out["gbmImportance"] = imp
        print("  BO−MR 模型重要因子：" + "、".join(f"{k}({v})" for k, v in imp))
    except ImportError:
        print("  沒裝 lightgbm，略過")
    (DATA / "research" / "tx_regime2.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
