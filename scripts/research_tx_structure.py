#!/usr/bin/env python3
"""
台指期日盤：用 TR（真實波幅）、前 N 日 TR 與其他價格結構，能不能預測當天會「單邊」還是「上下刷」

日線來自期交所 1 分 K 合成的日盤（08:45～13:45）開高低收，TR＝max(高, 昨收) − min(低, 昨收)
結構因子（開盤前／09:15 前就知道）：
  波動壓縮／擴張：TR1／ATR20、ATR5／ATR20、ATR10／ATR60、前 3 天 TR 是否遞減、NR4、NR7、內包日、連 2 天內包
  趨勢強度：ADX14、10／20 日效率比（Kaufman ER）、連續同方向天數、收盤在 20 日區間的位置、布林帶寬百分位
  前一天型態：收盤在當日區間的位置（CLV）、前一天日盤效率
  開盤位置：開在前 1／5／20 日高低點之外（突破開盤）、跳空 ÷ ATR
  09:15：開盤區間 ÷ ATR、開盤區間 ÷ 前一天 TR
目標（09:15～13:30）：單邊（效率 ≥ 0.6）、來回刷（< 0.3）、雙邊破（09:15 後先後破開盤區間高低）、
  另外看「振幅大小」：09:15 後振幅 ÷ ATR（波動群聚，可能比較能預測）
每個因子分三等分比較，2025 前建模、之後驗證；最後把全部因子丟進邏輯迴歸，用樣本外 AUC 看合起來能預測多少
（AUC 0.5＝跟丟銅板一樣，0.6 算弱，0.7 以上才算有用）
輸出 data/research/tx_structure.json；用法：python scripts/research_tx_structure.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
SPLIT = "2025-01-01"


def adx(H, L, C, n=14):
    """Wilder ADX；回傳每天的 ADX（前面不足的是 None）"""
    out = [None] * len(C)
    tr, pdm, mdm = [], [], []
    for i in range(1, len(C)):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if up > dn and up > 0 else 0)
        mdm.append(dn if dn > up and dn > 0 else 0)
        tr.append(max(H[i], C[i - 1]) - min(L[i], C[i - 1]))
    if len(tr) < 2 * n:
        return out
    atr, p, m = sum(tr[:n]), sum(pdm[:n]), sum(mdm[:n])
    dxs = []
    for i in range(n, len(tr)):
        atr, p, m = atr - atr / n + tr[i], p - p / n + pdm[i], m - m / n + mdm[i]
        pdi, mdi = 100 * p / atr, 100 * m / atr
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0)
        if len(dxs) == n:
            a = st.mean(dxs)
            out[i + 1] = a
        elif len(dxs) > n:
            a = (a * (n - 1) + dxs[-1]) / n
            out[i + 1] = a
    return out


def auc(y, s):
    y, s = np.asarray(y), np.asarray(s)
    o = np.argsort(s)
    rk = np.empty(len(s))
    rk[o] = np.arange(1, len(s) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return float((rk[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else None


def logit(X, y, lam=1.0, it=3000, lr=0.1):
    w = np.zeros(X.shape[1])
    b = 0.0
    for _ in range(it):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / len(y) + lam * w / len(y))
        b -= lr * g.mean()
    return w, b


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    dates = sorted(d for d, b in day.items() if len(b) >= 250 and rr.OR_M in b)
    O, H, L, C, E = [], [], [], [], []
    for d in dates:
        b = day[d]
        ms = sorted(b)
        O.append(b[ms[0]][0]); H.append(max(x[1] for x in b.values())); L.append(min(x[2] for x in b.values())); C.append(b[ms[-1]][3])
        E.append(abs(C[-1] - O[-1]) / (H[-1] - L[-1]) if H[-1] > L[-1] else 0)
    TR = [H[0] - L[0]] + [max(H[i], C[i - 1]) - min(L[i], C[i - 1]) for i in range(1, len(C))]
    ADX = adx(H, L, C)
    rows = []
    for i in range(61, len(dates)):
        d = dates[i]
        b = day[d]
        p = i - 1  # 前一天
        atr20 = st.mean(TR[i - 20:i])
        atr5, atr10, atr60 = st.mean(TR[i - 5:i]), st.mean(TR[i - 10:i]), st.mean(TR[i - 60:i])
        rng = [H[k] - L[k] for k in range(i - 7, i)]
        er = lambda n: abs(C[p] - C[p - n]) / sum(abs(C[k] - C[k - 1]) for k in range(p - n + 1, p + 1))  # noqa: E731
        sgn = [np.sign(C[k] - C[k - 1]) for k in range(p - 9, p + 1)]
        streak = 1
        for k in range(len(sgn) - 2, -1, -1):
            if sgn[k] == sgn[-1] and sgn[k] != 0:
                streak += 1
            else:
                break
        h20, l20 = max(H[i - 20:i]), min(L[i - 20:i])
        sd20 = st.pstdev(C[i - 20:i])
        bw = [st.pstdev(C[k - 20:k]) / st.mean(C[k - 20:k]) for k in range(i - 40, i + 1)]
        orb = [b[m] for m in range(rr.OR_M) if m in b]
        orh, orl = max(x[1] for x in orb), min(x[2] for x in orb)
        post = [b[m] for m in range(rr.OR_M, rr.EXIT_M + 1) if m in b]
        p915 = orb[-1][3]
        ph, pl, pc = max(x[1] for x in post), min(x[2] for x in post), post[-1][3]
        eff = abs(pc - p915) / (ph - pl) if ph > pl else 0
        up = any(x[1] > orh for x in post)
        dn = any(x[2] < orl for x in post)
        o = O[i]
        f = {
            "date": d,
            "tr1": TR[p] / atr20, "atr5_20": atr5 / atr20, "atr10_60": atr10 / atr60,
            "trDown3": float(TR[p] < TR[p - 1] < TR[p - 2]),
            "nr4": float(H[p] - L[p] <= min(rng[-4:])), "nr7": float(H[p] - L[p] <= min(rng)),
            "inside": float(H[p] <= H[p - 1] and L[p] >= L[p - 1]),
            "inside2": float(H[p] <= H[p - 1] and L[p] >= L[p - 1] and H[p - 1] <= H[p - 2] and L[p - 1] >= L[p - 2]),
            "adx": ADX[p], "er10": er(10), "er20": er(20), "streak": streak,
            "pos20": (C[p] - l20) / (h20 - l20) if h20 > l20 else 0.5,
            "bwPct": sum(x <= bw[-2] for x in bw[:-1]) / len(bw[:-1]),
            "clv": (C[p] - L[p]) / (H[p] - L[p]) if H[p] > L[p] else 0.5,
            "clvExt": abs((C[p] - L[p]) / (H[p] - L[p]) - 0.5) * 2 if H[p] > L[p] else 0,
            "prevEff": E[p],
            "out1": float(o > H[p] or o < L[p]), "out5": float(o > max(H[i - 5:i]) or o < min(L[i - 5:i])),
            "out20": float(o > h20 or o < l20),
            "absGap": abs(o - C[p]) / atr20, "sd20": sd20 / atr20,
            "orATR": (orh - orl) / atr20, "orTR1": (orh - orl) / TR[p] if TR[p] else 1,
            # 目標
            "eff": eff, "trend": eff >= 0.6, "chop": eff < 0.3, "two": up and dn, "rngPost": (ph - pl) / atr20,
        }
        if f["adx"] is None:
            continue
        rows.append(f)
    tr = [r for r in rows if r["date"] < SPLIT]
    te = [r for r in rows if r["date"] >= SPLIT]
    feats = [("tr1", "前一天 TR ÷ ATR20"), ("atr5_20", "ATR5 ÷ ATR20（短期壓縮）"), ("atr10_60", "ATR10 ÷ ATR60"),
             ("adx", "ADX14（趨勢強度）"), ("er10", "10 日效率比"), ("er20", "20 日效率比"), ("streak", "連續同方向天數"),
             ("pos20", "收盤在 20 日區間位置"), ("bwPct", "布林帶寬百分位（40 日）"), ("clv", "前一天收在區間位置"),
             ("clvExt", "前一天收在極端（高或低）"), ("prevEff", "前一天日盤效率"), ("absGap", "跳空 ÷ ATR"), ("sd20", "20 日標準差 ÷ ATR"),
             ("orATR", "開盤區間 ÷ ATR"), ("orTR1", "開盤區間 ÷ 前一天 TR")]
    flags = [("trDown3", "TR 連 3 天遞減"), ("nr4", "NR4"), ("nr7", "NR7"), ("inside", "內包日"), ("inside2", "連 2 天內包"),
             ("out1", "開在前一天高低外"), ("out5", "開在前 5 日高低外"), ("out20", "開在前 20 日高低外")]

    def summ(rs):
        if not rs:
            return None
        return {"n": len(rs), "trend": round(sum(r["trend"] for r in rs) / len(rs) * 100, 1), "chop": round(sum(r["chop"] for r in rs) / len(rs) * 100, 1),
                "two": round(sum(r["two"] for r in rs) / len(rs) * 100, 1), "eff": round(st.mean(r["eff"] for r in rs), 3),
                "rng": round(st.mean(r["rngPost"] for r in rs), 3)}

    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "split": SPLIT, "train": summ(tr), "test": summ(te), "features": {}, "flags": {}, "model": {}}
    print(f"{rows[0]['date']}～{rows[-1]['date']}：建模 {len(tr)}／驗證 {len(te)} 天")
    print(f"  基準 建模 單邊 {out['train']['trend']}% 來回刷 {out['train']['chop']}% 雙邊破 {out['train']['two']}% 振幅 {out['train']['rng']}ATR"
          f" ／ 驗證 {out['test']['trend']}% {out['test']['chop']}% {out['test']['two']}% {out['test']['rng']}ATR")
    print("\n三等分 低／中／高：單邊%/來回刷%/雙邊破%/09:15後振幅(ATR)；建模 → 驗證")
    fm = lambda s: f"{s['trend']:3.0f}/{s['chop']:3.0f}/{s['two']:3.0f}/{s['rng']:.2f}"  # noqa: E731
    for k, lab in feats:
        xs = sorted(r[k] for r in tr)
        c1, c2 = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        cuts = [(-1e18, c1), (c1, c2), (c2, 1e18)]
        if c1 == c2:
            cuts = [(-1e18, c1), (c1, c1 + 1e-12), (c1 + 1e-12, 1e18)]
        g = lambda rs, a, b: [r for r in rs if a <= r[k] < b]  # noqa: E731
        o = {"label": lab, "cut": [round(c1, 3), round(c2, 3)], "train": [summ(g(tr, a, b)) for a, b in cuts], "test": [summ(g(te, a, b)) for a, b in cuts]}
        out["features"][k] = o
        print(f"  {lab:24s} {'  '.join(fm(s) if s else '—' for s in o['train'])}  →  {'  '.join(fm(s) if s else '—' for s in o['test'])}")
    print("\n是／否：")
    for k, lab in flags:
        o = {"label": lab, "train": [summ([r for r in tr if r[k] == v]) for v in (0.0, 1.0)], "test": [summ([r for r in te if r[k] == v]) for v in (0.0, 1.0)]}
        out["flags"][k] = o
        print(f"  {lab:16s} 否 {fm(o['train'][0])} 是 {fm(o['train'][1]) if o['train'][1] else '—'}(n{o['train'][1]['n'] if o['train'][1] else 0})"
              f"  →  否 {fm(o['test'][0])} 是 {fm(o['test'][1]) if o['test'][1] else '—'}(n{o['test'][1]['n'] if o['test'][1] else 0})")
    # 全部因子合起來：邏輯迴歸（標準化、L2），樣本外 AUC；09:15 前（開盤前）和 09:15（含開盤區間）兩種
    keys_pre = [k for k, _ in feats if k not in ("orATR", "orTR1")] + [k for k, _ in flags]
    keys_915 = keys_pre + ["orATR", "orTR1"]
    print("\n全部因子合起來（邏輯迴歸，2025 前訓練、之後測）：樣本外 AUC（0.5＝丟銅板）")
    for tgt, lab in (("trend", "單邊"), ("chop", "來回刷"), ("two", "雙邊破"), ("big", "大振幅（09:15 後振幅 ≥ 1 ATR）")):
        out["model"][tgt] = {}
        for nm, keys in (("開盤前", keys_pre), ("09:15", keys_915)):
            Xtr = np.array([[r[k] for k in keys] for r in tr], float)
            Xte = np.array([[r[k] for k in keys] for r in te], float)
            mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
            Xtr, Xte = (Xtr - mu) / sd, (Xte - mu) / sd
            yv = (lambda r: r["rngPost"] >= 1) if tgt == "big" else (lambda r: bool(r[tgt]))
            ytr = np.array([yv(r) for r in tr], float)
            yte = np.array([yv(r) for r in te], float)
            w, b0 = logit(Xtr, ytr, lam=5.0)
            a_tr, a_te = auc(ytr, Xtr @ w + b0), auc(yte, Xte @ w + b0)
            pte = 1 / (1 + np.exp(-(Xte @ w + b0)))
            q = np.quantile(pte, [1 / 5, 4 / 5])
            lo_hit, hi_hit = yte[pte <= q[0]].mean() * 100, yte[pte >= q[1]].mean() * 100
            top = sorted(zip(keys, w), key=lambda x: -abs(x[1]))[:5]
            out["model"][tgt][nm] = {"aucTrain": round(a_tr, 3), "aucTest": round(a_te, 3), "base": round(yte.mean() * 100, 1),
                                     "low20": round(lo_hit, 1), "high20": round(hi_hit, 1), "top": [[k, round(float(v), 3)] for k, v in top]}
            print(f"  {lab:20s} {nm:4s} AUC 建模 {a_tr:.3f}／驗證 {a_te:.3f}；驗證期 模型最低 1/5 發生率 {lo_hit:.0f}% vs 最高 1/5 {hi_hit:.0f}%（平均 {yte.mean() * 100:.0f}%）"
                  f"；權重最大：{'、'.join(f'{k}{v:+.2f}' for k, v in top[:3])}")
    (DATA / "research" / "tx_structure.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
