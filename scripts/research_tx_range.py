#!/usr/bin/env python3
"""
台指期日盤「大振幅」預測與交易回測

大振幅：09:15～13:30 的最高 − 最低 ≥ 1 × ATR20（ATR20＝前 20 個交易日日盤 TR 的平均，TR＝max(高, 昨收) − min(低, 昨收)）
因子：
  結構（research_tx_structure）：TR／ATR、NR4／NR7、ADX、效率比、布林帶寬、20 日標準差、開盤是否突破前 N 日高低…
  盤前（research_tx_preopen 的每日資料）：前一晚 S&P／那斯達克／費半／台積 ADR 漲跌幅（取絕對值）、VIX、VIX 變動、
        夜盤振幅、日韓開盤跳空（08:00 已知）、美國重大事件、結算日
  09:15：開盤區間 ÷ ATR、開盤 30 分量能 ÷ 20 日平均、VWAP 穿越次數
驗證：逐年往前滾動（walk-forward）：預測 Y 年時只用 Y 年以前的資料訓練，2022～2026 全部是樣本外
交易回測（大台點數，扣 3 點）：現行 BO／MR 規則 vs 依預測振幅調整（低振幅日不做、高振幅日改做 BO…）
輸出 data/research/tx_range.json；用法：python scripts/research_tx_range.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_structure as rs  # noqa: E402
import tx_regime_review as trv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))

STRUCT = ["tr1", "atr5_20", "atr10_60", "adx", "er10", "er20", "streak", "pos20", "bwPct", "clv", "clvExt", "prevEff", "absGap", "sd20",
          "trDown3", "nr4", "nr7", "inside", "out1", "out5", "out20"]
PRE = ["aSpx", "aSox", "aTsm", "vix", "vixChg", "aVixChg", "nightRng", "aJp", "aKr", "event", "settle"]
AT915 = ["orATR", "orTR1", "rvol30", "vwapCross30"]
LABEL = {"tr1": "前一天 TR ÷ ATR20", "atr5_20": "ATR5 ÷ ATR20", "atr10_60": "ATR10 ÷ ATR60", "adx": "ADX14", "er10": "10 日效率比", "er20": "20 日效率比",
         "streak": "連續同方向天數", "pos20": "收盤在 20 日區間位置", "bwPct": "布林帶寬百分位", "clv": "前一天收在區間位置", "clvExt": "前一天收在極端",
         "prevEff": "前一天效率", "absGap": "跳空 ÷ ATR", "sd20": "20 日收盤標準差 ÷ ATR", "trDown3": "TR 連 3 天遞減", "nr4": "NR4", "nr7": "NR7",
         "inside": "內包日", "out1": "開在前一天高低外", "out5": "開在前 5 日高低外", "out20": "開在前 20 日高低外",
         "aSpx": "前一晚 S&P 漲跌幅（絕對值）", "aSox": "前一晚費半漲跌幅（絕對值）", "aTsm": "前一晚台積 ADR 漲跌幅（絕對值）", "vix": "VIX",
         "vixChg": "VIX 變動 %", "aVixChg": "VIX 變動幅度（絕對值）", "nightRng": "夜盤振幅 %", "aJp": "日股開盤跳空（絕對值）", "aKr": "韓股開盤跳空（絕對值）",
         "event": "前一晚美國重大事件", "settle": "結算日", "orATR": "開盤區間 ÷ ATR", "orTR1": "開盤區間 ÷ 前一天 TR", "rvol30": "開盤 30 分量能 ÷ 20 日平均",
         "vwapCross30": "開盤 30 分 VWAP 穿越次數"}


def rows_all():
    rows = rs.build_rows()
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    pre = {r["date"]: r for r in json.loads((DATA / "research" / "tx_preopen_rows.json").read_text(encoding="utf-8"))}
    p = trv.params()["current"]
    out = []
    for r in rows:
        g, q = reg.get(r["date"]), pre.get(r["date"])
        if not g or not q:
            continue
        x = dict(r)
        x.update({"bo": g["bo"], "mr": g["mr"], "rule": trv.pnl(g, trv.decide(g, p)[1]), "plan": trv.decide(g, p)[1],
                  "rvol30": g.get("rvol30"), "vwapCross30": g.get("vwapCross30"), "settle": float(bool(g.get("settle"))),
                  "aSpx": abs(q["spx"]) if q.get("spx") is not None else None, "aSox": abs(q["sox"]) if q.get("sox") is not None else None,
                  "aTsm": abs(q["tsm"]) if q.get("tsm") is not None else None, "vix": q.get("vix"), "vixChg": q.get("vixChg"),
                  "aVixChg": abs(q["vixChg"]) if q.get("vixChg") is not None else None, "nightRng": q.get("nightRng"),
                  "aJp": abs(q["jpGap"]) if q.get("jpGap") is not None else None, "aKr": abs(q["krGap"]) if q.get("krGap") is not None else None,
                  "event": float(bool(q.get("event"))), "big": r["rngPost"] >= 1})
        out.append(x)
    return out


def fill(X, med):
    X = X.copy()
    m = np.isnan(X)
    X[m] = np.take(med, np.where(m)[1])
    return X


def walk(rows, keys, start=2022):
    """逐年滾動：預測 Y 年只用之前的資料訓練；回傳 {日期: 機率}"""
    pred = {}
    for y in range(start, int(rows[-1]["date"][:4]) + 1):
        tr = [r for r in rows if int(r["date"][:4]) < y]
        te = [r for r in rows if int(r["date"][:4]) == y]
        if not te or len(tr) < 300:
            continue
        Xtr = np.array([[np.nan if r.get(k) is None else float(r[k]) for k in keys] for r in tr])
        Xte = np.array([[np.nan if r.get(k) is None else float(r[k]) for k in keys] for r in te])
        med = np.nanmedian(Xtr, 0)
        Xtr, Xte = fill(Xtr, med), fill(Xte, med)
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        w, b = rs.logit((Xtr - mu) / sd, np.array([r["big"] for r in tr], float), lam=5.0)
        ptr = 1 / (1 + np.exp(-(((Xtr - mu) / sd) @ w + b)))
        pte = 1 / (1 + np.exp(-(((Xte - mu) / sd) @ w + b)))
        qs = np.quantile(ptr, [0.2, 0.4, 0.6, 0.8])  # 分位用訓練期的，避免偷看
        for r, pv in zip(te, pte):
            pred[r["date"]] = (float(pv), int(np.searchsorted(qs, pv)))
    return pred


def main():
    rows = rows_all()
    oos = [r for r in rows if r["date"] >= "2022-01-01"]
    base = sum(r["big"] for r in rows) / len(rows) * 100
    print(f"{rows[0]['date']}～{rows[-1]['date']}：{len(rows)} 天；大振幅（09:15 後振幅 ≥ 1 ATR20）佔 {base:.1f}%")
    print(f"  09:15 後振幅：中位數 {st.median(r['rngPost'] for r in rows):.2f} ATR，大振幅日平均 {st.mean(r['rngPost'] for r in rows if r['big']):.2f} ATR")
    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "base": round(base, 1), "single": {}, "models": {}, "trade": {}}
    # 單一因子：兩段（2020-2024／2025 後）各自的 AUC（> 0.5＝數值越大越容易大振幅）
    print("\n單一因子 AUC（2020-24／2025 後；0.5＝沒用，離 0.5 越遠越有用，< 0.5＝反向）")
    sing = []
    for k in STRUCT + PRE + AT915:
        a = []
        for part in ([r for r in rows if r["date"] < "2025-01-01"], [r for r in rows if r["date"] >= "2025-01-01"]):
            v = [(r[k], r["big"]) for r in part if r.get(k) is not None]
            a.append(rs.auc([y for _, y in v], [x for x, _ in v]) if v else None)
        sing.append((k, a))
        out["single"][k] = {"label": LABEL[k], "auc": [round(x, 3) if x is not None else None for x in a]}
    for k, a in sorted(sing, key=lambda x: -abs(((x[1][0] or .5) + (x[1][1] or .5)) / 2 - 0.5)):
        same = (a[0] - .5) * (a[1] - .5) > 0
        print(f"  {LABEL[k]:24s} {a[0]:.3f}／{a[1]:.3f} {'✓ 兩段同方向' if same and min(abs(a[0] - .5), abs(a[1] - .5)) >= 0.03 else ''}")
    # 模型：逐年滾動，2022 起全部樣本外
    print("\n模型（逐年滾動，2022～2026 全部樣本外）")
    preds = {}
    for nm, keys in (("結構（開盤前）", STRUCT), ("結構＋盤前資訊（08:45 前）", STRUCT + PRE), ("全部（09:15）", STRUCT + PRE + AT915)):
        pr = walk(rows, keys)
        preds[nm] = pr
        rr_ = [r for r in oos if r["date"] in pr]
        y = [r["big"] for r in rr_]
        a = rs.auc(y, [pr[r["date"]][0] for r in rr_])
        byq = []
        for qi in range(5):
            s = [r for r in rr_ if pr[r["date"]][1] == qi]
            byq.append({"n": len(s), "big": round(sum(r["big"] for r in s) / len(s) * 100, 1) if s else None,
                        "rng": round(st.mean(r["rngPost"] for r in s), 2) if s else None,
                        "bo": round(st.mean(r["bo"] for r in s), 1) if s else None, "mr": round(st.mean(r["mr"] for r in s), 1) if s else None,
                        "rule": round(st.mean(r["rule"] for r in s), 1) if s else None})
        out["models"][nm] = {"auc": round(a, 3), "byQuintile": byq}
        print(f"  {nm}：AUC {a:.3f}")
        for qi, s in enumerate(byq):
            print(f"    預測第 {qi + 1} 組（低→高） n={s['n']:3d} 大振幅 {s['big']:4.1f}% 振幅 {s['rng']:.2f}ATR  BO {s['bo']:+6.1f} MR {s['mr']:+6.1f} 現行規則 {s['rule']:+6.1f}")
    # 交易回測：用「全部（09:15）」與「08:45 前」兩種預測
    print("\n交易回測（2022～2026 樣本外，每天大台一口，扣 3 點；括號：2022-24／2025 後 每天平均點數）")
    for nm in ("結構＋盤前資訊（08:45 前）", "全部（09:15）"):
        pr = preds[nm]
        rr_ = [r for r in oos if r["date"] in pr]
        strat = {
            "現行規則": lambda r, q: r["rule"],
            "現行規則，預測最低 1/5 不做": lambda r, q: 0 if q == 0 else r["rule"],
            "現行規則，預測最低 2/5 不做": lambda r, q: 0 if q <= 1 else r["rule"],
            "現行規則，預測最高 1/5 改做 BO": lambda r, q: r["bo"] if q == 4 else r["rule"],
            "現行規則，最低 1/5 不做＋最高 1/5 改 BO": lambda r, q: 0 if q == 0 else r["bo"] if q == 4 else r["rule"],
            "只在預測最高 2/5 做 BO": lambda r, q: r["bo"] if q >= 3 else 0,
            "低振幅做 MR、高振幅做 BO（中間不做）": lambda r, q: r["mr"] if q <= 1 else r["bo"] if q >= 3 else 0,
            "每天都 BO": lambda r, q: r["bo"],
        }
        out["trade"][nm] = {}
        print(f"  ── 用「{nm}」預測")
        for sn, f in strat.items():
            xs = [f(r, pr[r["date"]][1]) for r in rr_]
            h1 = [f(r, pr[r["date"]][1]) for r in rr_ if r["date"] < "2025-01-01"]
            h2 = [f(r, pr[r["date"]][1]) for r in rr_ if r["date"] >= "2025-01-01"]
            tr_n = sum(1 for x in xs if x != 0)
            eq, pk, mdd = 0.0, 0.0, 0.0
            for x in xs:
                eq += x
                pk = max(pk, eq)
                mdd = min(mdd, eq - pk)
            o = {"avg": round(st.mean(xs), 1), "h1": round(st.mean(h1), 1), "h2": round(st.mean(h2), 1), "total": round(sum(xs)), "trades": tr_n,
                 "perTrade": round(sum(xs) / tr_n, 1) if tr_n else None, "mdd": round(mdd)}
            out["trade"][nm][sn] = o
            print(f"    {sn:28s} 每天 {o['avg']:+6.1f}（{o['h1']:+6.1f}／{o['h2']:+6.1f}）總 {o['total']:+7,} 點  交易 {tr_n} 天、每筆 {o['perTrade']:+6.1f}、最大回落 {o['mdd']:,}")
    (DATA / "research" / "tx_range.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
