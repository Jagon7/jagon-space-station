#!/usr/bin/env python3
"""
台指期 × 期貨選擇權籌碼：外資期貨部位、散戶多空比、P/C 比、外資選擇權 → 預測夜盤、隔天跳空、隔天日盤、BO／MR

資料：data/research/futures_hist.json（fetch_futures_hist.py；期交所三大法人資料只能抓近 3 年 → 2023/12 起；P/C、未平倉、收盤 2020 起）、
      data/futures/day、night（台指期 1 分 K）、data/futures/regime_rows.json（BO／MR 損益）
因子（第 t 天 15:00 後就知道）：
  外資台指期淨口數（水準）、當日變化、5 日變化；散戶多空比＝−（三大法人小台淨額）÷ 小台總未平倉（散戶站多的比例）；
  P/C 未平倉比；外資選擇權買權淨額、賣權淨額（千元）
目標：當晚夜盤（13:45 → 隔天 05:00）、隔天日盤開盤跳空（對 13:45）、隔天日盤（開→收）、隔天 BO／MR 損益
統計：三分位（門檻用前半段）高組 − 低組；兩段（外資等 2023/12 起：前半／後半；P/C 2020 起：2020-22／2023-24／2025+）同方向才算；
      另外用迴歸控制「當天台指日盤漲跌」（動能），看籌碼還有沒有額外的預測力
結果（2026/11）：沒有一個因子兩段同方向且控制動能後顯著。最接近的是 P/C 未平倉比高 → 隔天日盤偏漲（三段都同方向，
  但各段 t 只有 1.1～1.4，控制後 t 2.0）；外資期貨部位、散戶多空比、外資選擇權在前後兩段方向不一致或不顯著
輸出 data/research/tx_chips.json；用法：python scripts/research_tx_chips.py
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_tx_regime as rr  # noqa: E402


def px(bars: dict, m: int):
    ks = [k for k in bars if k <= m]
    return bars[max(ks)][3] if ks else None


def ols_t(y, X):
    X = np.column_stack([np.ones(len(y))] + X)
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    s2 = e @ e / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return b[1:], b[1:] / se[1:]


def main():
    fh = json.loads((DATA / "research" / "futures_hist.json").read_text(encoding="utf-8"))
    day = rr.load_dir(DATA / "futures" / "day")
    night = rr.load_dir(DATA / "futures" / "night")
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    td = sorted(d for d in day if len(day[d]) >= 250)
    ks = sorted(fh)
    rows = []
    for i, d in enumerate(ks):
        if d not in td:
            continue
        k = td.index(d)
        if k + 1 >= len(td):
            continue
        x = fh[d]
        b, nb = day[d], day[td[k + 1]]
        o0, c0 = b[min(b)][0], px(b, 299)
        f = {"pcOI": (x.get("pc") or [None, None])[1]}
        txf = (x.get("txf") or {}).get("f")
        if txf:
            f["fNet"] = txf[0]
            p1 = (fh.get(ks[i - 1]) or {}).get("txf", {}).get("f") if i >= 1 else None
            p5 = (fh.get(ks[i - 5]) or {}).get("txf", {}).get("f") if i >= 5 else None
            f["fD1"] = txf[0] - p1[0] if p1 else None
            f["fD5"] = txf[0] - p5[0] if p5 else None
        mtx, oi = x.get("mtx") or {}, x.get("mtxOI")
        if mtx and oi and all(w in mtx for w in ("d", "t", "f")):
            f["retail"] = -sum(mtx[w][0] for w in ("d", "t", "f")) / oi * 100
        txo = (x.get("txo") or {}).get("f") or {}
        if txo.get("c") and txo.get("p"):
            f["fCall"], f["fPut"] = txo["c"][1], txo["p"][1]
        y = {"night": None, "gap": (nb[min(nb)][0] / c0 - 1) * 100, "next": (px(nb, 299) / nb[min(nb)][0] - 1) * 100}
        n = night.get(d)
        if n:
            y["night"] = (n[max(n)][3] / c0 - 1) * 100
        r = reg.get(td[k + 1])
        if r:
            y["bo"], y["mr"] = r["bo"], r["mr"]
        rows.append({"d": d, "f": f, "y": y, "ret": (c0 / o0 - 1) * 100})
    print(f"{rows[0]['d']}～{rows[-1]['d']}，{len(rows)} 天；外資部位有資料 {sum(1 for r in rows if 'fNet' in r['f'])} 天")
    out = {"tests": []}
    feats = ["fNet", "fD1", "fD5", "retail", "fCall", "fPut", "pcOI"]
    for fk in feats:
        xs = [r for r in rows if r["f"].get(fk) is not None]
        if len(xs) < 100:
            continue
        if fk == "pcOI":
            parts = (("2020-22", "2020", "2023"), ("2023-24", "2023", "2025"), ("2025+", "2025", "2100"))
            train = [r for r in xs if r["d"] < "2023"]
        else:
            mid = xs[len(xs) // 2]["d"]
            parts = (("前半", "0000", mid), ("後半", mid, "9999"))
            train = [r for r in xs if r["d"] < mid]
        v = sorted(r["f"][fk] for r in train)
        c1, c2 = v[len(v) // 3], v[2 * len(v) // 3]
        for yk in ("night", "gap", "next", "bo", "mr"):
            res = {}
            for lab, a, b in parts:
                g = [r for r in xs if a <= r["d"] < b and r["y"].get(yk) is not None]
                lo = [r["y"][yk] for r in g if r["f"][fk] <= c1]
                hi = [r["y"][yk] for r in g if r["f"][fk] > c2]
                if len(lo) < 10 or len(hi) < 10:
                    continue
                diff = st.mean(hi) - st.mean(lo)
                se = math.sqrt(st.variance(hi) / len(hi) + st.variance(lo) / len(lo))
                res[lab] = {"lo": round(st.mean(lo), 3), "hi": round(st.mean(hi), 3), "t": round(diff / se, 2) if se else None}
            g = [r for r in xs if r["y"].get(yk) is not None]
            yv = np.array([r["y"][yk] for r in g])
            bcoef, tt = ols_t(yv, [np.array([r["f"][fk] for r in g]), np.array([r["ret"] for r in g])])
            ok = len(res) == len(parts) and len({math.copysign(1, v_["hi"] - v_["lo"]) for v_ in res.values()}) == 1 \
                and all(abs(v_["t"] or 0) >= 1.5 for v_ in res.values()) and abs(tt[0]) >= 2
            out["tests"].append({"factor": fk, "target": yk, "cut": [c1, c2], "parts": res, "tCtrl": round(float(tt[0]), 2),
                                 "tMom": round(float(tt[1]), 2), "consistent": ok})
            unit = "點" if yk in ("bo", "mr") else "%"
            print(f"{'✓' if ok else ' '} {fk:7s} → {yk:5s}：" + "｜".join(f"{lab} 低 {v_['lo']:+.3f} 高 {v_['hi']:+.3f}{unit}（t {v_['t']}）" for lab, v_ in res.items())
                  + f"｜控制當天漲跌後 t {tt[0]:.2f}（動能 t {tt[1]:.2f}）")
    (DATA / "research" / "tx_chips.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
