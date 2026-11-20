#!/usr/bin/env python3
"""
台指期日盤：開盤前／09:15 前的資訊能不能預測當天走勢？

目標（台指期日盤 1 分 K，2020/3 起）：
  oc    開盤 08:45 → 收盤 13:45 漲跌（%）
  rest  09:15 → 收盤（%）（09:15 判斷之後還能賺的部分）
  boDay 當天突破（BO）比均值回歸（MR）好（scripts/research_tx_regime.py）
特徵（台灣時間 08:45 前都已知道）：
  夜盤：前一天日盤收盤 → 夜盤收盤（%）、夜盤振幅、夜盤最後一小時
  美股（前一晚收盤，台灣清晨 4～5 點）：S&P500、那斯達克、費半、台積電 ADR 漲跌；VIX 與變化
  日股、韓股：今天開盤（台灣 08:00）對前一天收盤的跳空（Yahoo 日線開盤價）
  事件：前一晚美國重大數據（CPI、非農、FOMC…）
  台指期開盤跳空（08:45 開盤 − 前一天日盤收盤）、跳空裡夜盤沒反映的部分
方法：2024/6 前建模、之後驗證；五分位表、相關係數、線性迴歸方向命中率
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
SPLIT = "2024-07-01"


def ydaily(sym):
    p = DATA / "research" / "yahoo" / f"{sym.replace('^', '_')}.json"
    return {r[0]: r for r in json.loads(p.read_text(encoding="utf-8"))["d"]} if p.exists() else {}


def load_bars(sub):
    out = {}
    for f in sorted((DATA / "futures" / sub).glob("20*.json")):
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            out[k] = {b[0]: b[1:] for b in v["bars"]}
    return out


def prev_key(sorted_keys, d):
    import bisect
    i = bisect.bisect_left(sorted_keys, d) - 1
    return sorted_keys[i] if i >= 0 else None


def main():
    day, night = load_bars("day"), load_bars("night")
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    us = {s: ydaily(s) for s in ("^GSPC", "^IXIC", "^SOX", "TSM", "^VIX")}
    asia = {s: ydaily(s) for s in ("^N225", "^KS11")}
    keys = {s: sorted(v) for s, v in {**us, **asia}.items()}
    ev = json.loads((DATA / "intel" / "us_events.json").read_text(encoding="utf-8")).get("events", [])
    ev_n = {}
    for e in ev:
        t = datetime.fromisoformat(e["t"])
        ev_n.setdefault((t.date() if t.hour >= 15 else t.date() - timedelta(days=1)).isoformat(), set()).add(e["key"])
    dates = sorted(d for d in day if len(day[d]) >= 250)
    nk = sorted(night)
    rows = []
    for i in range(1, len(dates)):
        d, p = dates[i], dates[i - 1]
        b, pb = day[d], day[p]
        pc = pb[max(pb)][3]
        o = b[min(b)][0]
        c = b[max(b)][3]
        p915 = next((b[m][3] for m in range(29, 20, -1) if m in b), None)
        n = night.get(prev_key(nk, d))
        if not n or prev_key(nk, d) < p:
            n = None
        f = {"date": d, "oc": (c / o - 1) * 100, "rest": (c / p915 - 1) * 100 if p915 else None,
             "gap": (o / pc - 1) * 100, "boDay": (reg.get(d) or {}).get("boDay")}
        if n:
            nc = n[max(n)][3]
            f["night"] = (nc / pc - 1) * 100
            f["nightRng"] = (max(x[1] for x in n.values()) - min(x[2] for x in n.values())) / pc * 100
            last = [n[m][3] for m in sorted(n) if m >= 780]
            f["nightLast"] = (nc / last[0] - 1) * 100 if last else None
            f["gapResid"] = (o / nc - 1) * 100
        for s, lab in (("^GSPC", "spx"), ("^IXIC", "ndx"), ("^SOX", "sox"), ("TSM", "tsm")):
            k = prev_key(keys[s], d)  # 美股前一個交易日（台灣日期 d 之前）
            k0 = prev_key(keys[s], k) if k else None
            if k and k0 and (date.fromisoformat(d) - date.fromisoformat(k)).days <= 4:
                f[lab] = (us[s][k][4] / us[s][k0][4] - 1) * 100
        k = prev_key(keys["^VIX"], d)
        if k:
            k0 = prev_key(keys["^VIX"], k)
            f["vix"] = us["^VIX"][k][4]
            f["vixChg"] = (us["^VIX"][k][4] / us["^VIX"][k0][4] - 1) * 100 if k0 else None
        for s, lab in (("^N225", "jpGap"), ("^KS11", "krGap")):
            if d in asia[s]:
                k0 = prev_key(keys[s], d)
                if k0 and asia[s][d][1] and asia[s][k0][4]:
                    g = (asia[s][d][1] / asia[s][k0][4] - 1) * 100
                    f[lab] = g if abs(g) > 1e-6 else None  # Yahoo 偶爾開盤價＝前收（沒資料），不用
        f["event"] = bool(ev_n.get(prev_key(nk, d) or ""))
        rows.append(f)
    feats = ["night", "nightRng", "nightLast", "spx", "ndx", "sox", "tsm", "vix", "vixChg", "jpGap", "krGap", "gap", "gapResid"]
    tr = [r for r in rows if r["date"] < SPLIT]
    te = [r for r in rows if r["date"] >= SPLIT]
    print(f"{len(rows)} 天（建模 {len(tr)}、驗證 {len(te)}）")
    print("\n相關係數（建模期／驗證期）")
    for k in feats:
        out = []
        for rs in (tr, te):
            for tgt in ("oc", "rest"):
                xs = [(r[k], r[tgt]) for r in rs if r.get(k) is not None and r.get(tgt) is not None]
                out.append(f"{tgt} {np.corrcoef([a for a, _ in xs], [b for _, b in xs])[0, 1]:+.3f}" if len(xs) > 30 else f"{tgt} —")
        print(f"  {k:10s} 建模 {out[0]}  {out[1]} | 驗證 {out[2]}  {out[3]}")
    # 五分位：對 oc 與 BO 日比例
    print("\n五分位（建模期切點）：當天 oc 平均、09:15 後 rest 平均、BO 日比例")
    for k in ("night", "gapResid", "sox", "tsm", "jpGap", "krGap", "vix", "vixChg", "nightLast"):
        xs = sorted(r[k] for r in tr if r.get(k) is not None)
        if len(xs) < 50:
            continue
        cuts = [xs[len(xs) * i // 5] for i in (1, 2, 3, 4)]
        for name, rs in (("建模", tr), ("驗證", te)):
            cells = []
            lo = -1e18
            for c in cuts + [1e18]:
                g = [r for r in rs if r.get(k) is not None and lo < r[k] <= c]
                lo = c
                if g:
                    bo = [r["boDay"] for r in g if r["boDay"] is not None]
                    cells.append(f"{st.mean(r['oc'] for r in g):+.2f}/{st.mean(r['rest'] for r in g if r['rest'] is not None):+.2f}/{sum(bo) / len(bo) * 100:.0f}%")
            print(f"  {k:9s} {name} " + " | ".join(cells))
    # 迴歸：預測 rest（09:15 之後）方向
    use = ["night", "spx", "sox", "tsm", "vixChg", "jpGap", "krGap", "gapResid"]
    def mat(rs):
        rs = [r for r in rs if all(r.get(k) is not None for k in use) and r.get("rest") is not None]
        X = np.array([[1.0] + [r[k] for k in use] for r in rs])
        y = np.array([r["rest"] for r in rs])
        y2 = np.array([r["oc"] for r in rs])
        return X, y, y2, rs
    for tgt in ("oc", "rest"):
        Xa, ya, ya2, _ = mat(tr)
        Xb, yb, yb2, rb = mat(te)
        yt, yv = (ya2, yb2) if tgt == "oc" else (ya, yb)
        beta = np.linalg.lstsq(Xa, yt, rcond=None)[0]
        pred = Xb @ beta
        hit = float(np.mean(np.sign(pred) == np.sign(yv)))
        strong = np.abs(pred) > np.percentile(np.abs(pred), 70)
        print(f"\n迴歸預測 {tgt}：係數 " + ", ".join(f"{k} {b:+.3f}" for k, b in zip(["常數"] + use, beta)))
        print(f"  驗證期方向命中 {hit * 100:.1f}%（n={len(yv)}），信心最高 30% 的日子命中 {np.mean(np.sign(pred[strong]) == np.sign(yv[strong])) * 100:.1f}%"
              f"、照方向做平均 {np.mean(np.sign(pred[strong]) * yv[strong]):+.3f}%／天")
        print(f"  驗證期 R² {1 - np.sum((yv - pred) ** 2) / np.sum((yv - yv.mean()) ** 2):+.3f}")
    (DATA / "research" / "tx_preopen_rows.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
