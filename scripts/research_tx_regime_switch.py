#!/usr/bin/env python3
"""
分盤勢換打法：盤整盤用逆勢、突破盤用順勢，有沒有用？要怎麼事先分辨？

每天四種打法的損益（大台點數，已扣成本）：
  BO／MR   現行 09:15 開盤區間突破／回歸各一筆（research_tx_regime）
  A／B     逆勢加碼／順勢加碼（research_tx_scale，格 0.3 ATR、1 口）
理論上限：事後知道當天哪個好（oracle），代表「分辨得出盤勢」最多值多少
實際分辨方法（只用前一天以前、或 09:15 以前就知道的資訊）：
  打法延續：最近 N 天（5／10／20／60）哪個打法賺比較多，今天就用它
  近期盤勢：前 5／20 天平均效率（單邊程度）、ADX14、20 日效率比、ATR5÷ATR20（波動擴張）
  大環境：加權在 60 日均線上／下、VIX 高低
  當天：開盤區間寬窄、大振幅預測（樣本外）、現行 09:15 規則
  門檻都用 2020-24 的中位數決定（不偷看 2025 後）
比較：2020-24／2025 後每天平均，兩段都比「只用一種」好才算有效
輸出 data/research/tx_regime_switch.json；用法：python scripts/research_tx_regime_switch.py
"""
from __future__ import annotations

import bisect
import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402
import research_tx_scale as sc  # noqa: E402
import research_tx_structure as rs  # noqa: E402
import tx_regime_review as trv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
SPLIT = "2025-01-01"


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    ds = sorted(d for d, b in day.items() if len(b) >= 250 and sc.START in b)
    TR = {}
    for i in range(1, len(ds)):
        b, pb = day[ds[i]], day[ds[i - 1]]
        pc = pb[max(pb)][3]
        TR[ds[i]] = max(max(x[1] for x in b.values()), pc) - min(min(x[2] for x in b.values()), pc)
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    struct = {r["date"]: r for r in rs.build_rows()}
    P = trv.params()["current"]
    tw = json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]
    twd = [r[0] for r in tw]
    vix = {r[0]: r[4] for r in json.loads((DATA / "research" / "yahoo" / "_VIX.json").read_text(encoding="utf-8"))["d"]}
    vk = sorted(vix)
    pred = {}
    try:
        import research_tx_range as rg
        pred = rg.walk(rg.rows_all(), rg.STRUCT + rg.PRE + rg.AT915)
    except Exception as e:  # noqa: BLE001
        print("大振幅預測失敗", e)
    rows = []
    for i in range(21, len(ds)):
        d = ds[i]
        if d not in reg or d not in struct:
            continue
        b = day[d]
        px = [b[m][3] for m in range(sc.START, sc.EXIT + 1) if m in b]
        if len(px) < 200:
            continue
        atr = st.mean(TR[k] for k in ds[i - 20:i])
        A = sc.fade(px, 0.3 * atr, 1)[0]
        B = sc.trend(px, 0.3 * atr, 1)[0]
        j = bisect.bisect_left(twd, d)
        c60 = [r[4] for r in tw[j - 60:j]]
        k = bisect.bisect_left(vk, d)
        g, s = reg[d], struct[d]
        rows.append({"date": d, "BO": g["bo"], "MR": g["mr"], "A": A, "B": B, "rule": trv.pnl(g, trv.decide(g, P)[1]), "plan": trv.decide(g, P)[1],
                     "effToday": s["eff"], "prevEff": s["prevEff"], "adx": s["adx"], "er20": s["er20"], "atr5_20": s["atr5_20"], "orATR": s["orATR"],
                     "bull": c60[-1] > st.mean(c60) if len(c60) == 60 else None, "vix": vix[vk[k - 1]] if k else None,
                     "pred": pred.get(d, (None, None))[1]})
    for i, r in enumerate(rows):
        r["prev5Eff"] = st.mean(x["effToday"] for x in rows[max(0, i - 5):i]) if i >= 5 else None
        r["prev20Eff"] = st.mean(x["effToday"] for x in rows[max(0, i - 20):i]) if i >= 20 else None
    tr = [r for r in rows if r["date"] < SPLIT]
    med = lambda k: st.median(r[k] for r in tr if r.get(k) is not None)  # noqa: E731
    parts = (("2020-24", lambda r: r["date"] < SPLIT), ("2025 後", lambda r: r["date"] >= SPLIT))
    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "pairs": {}}
    print(f"{rows[0]['date']}～{rows[-1]['date']}：{len(rows)} 天；每天平均點數（2020-24／2025 後）")
    for pair, (T, M), tl, ml in (("BO／MR（09:15 一筆）", ("BO", "MR"), "BO", "MR"), ("順勢加碼／逆勢加碼", ("B", "A"), "順勢", "逆勢")):
        res = {}

        def ev(name, pick, rows_=rows):
            v = []
            for _, pf in parts:
                xs = [r[T] if pick(r, i_) == "T" else r[M] if pick(r, i_) == "M" else 0.0 for i_, r in enumerate(rows_) if pf(r)]
                v.append(round(st.mean(xs), 1))
            tot = round(sum(r[T] if pick(r, i_) == "T" else r[M] if pick(r, i_) == "M" else 0.0 for i_, r in enumerate(rows_)))
            res[name] = {"h1": v[0], "h2": v[1], "total": tot}
            return v

        idx = {r["date"]: i for i, r in enumerate(rows)}
        cands = [
            (f"只做{tl}", lambda r, i: "T"), (f"只做{ml}", lambda r, i: "M"),
            ("理論上限：事後挑當天較好的", lambda r, i: "T" if r[T] > r[M] else "M"),
            ("理論上限：事後知道當天單邊（效率≥0.6）→順勢，否則逆勢", lambda r, i: "T" if r["effToday"] >= 0.6 else "M"),
        ]
        for n in (5, 10, 20, 60):
            def trail(r, i, n=n):
                if i < n:
                    return None
                w = rows[i - n:i]
                return "T" if sum(x[T] for x in w) > sum(x[M] for x in w) else "M"
            cands.append((f"打法延續：最近 {n} 天誰賺多就用誰", trail))
        for k, lab, hiT in (("prevEff", "前一天效率高→順勢", True), ("prev5Eff", "前 5 天平均效率高→順勢", True), ("prev20Eff", "前 20 天平均效率高→順勢", True),
                            ("adx", "ADX 高→順勢", True), ("er20", "20 日效率比高→順勢", True), ("atr5_20", "波動擴張（ATR5÷ATR20 高）→順勢", True),
                            ("vix", "VIX 高→順勢", True), ("orATR", "開盤區間寬→順勢", True)):
            m = med(k)
            cands.append((f"{lab}（門檻 {m:.2f}）", lambda r, i, k=k, m=m: None if r.get(k) is None else ("T" if r[k] > m else "M")))
        cands.append(("空頭（60 日均線下）→順勢，多頭→逆勢", lambda r, i: None if r["bull"] is None else ("M" if r["bull"] else "T")))
        cands.append(("大振幅預測高 2/5→順勢、低 2/5→逆勢（2022 起樣本外）", lambda r, i: None if r["pred"] is None else ("T" if r["pred"] >= 3 else "M" if r["pred"] <= 1 else "0")))
        if T == "BO":
            cands.append(("現行 09:15 規則", lambda r, i: "T" if r["plan"] == "BO" else "M" if r["plan"] == "MR" else "0"))
        print(f"\n■ {pair}")
        for name, f in cands:
            def pick(r, i, f=f):
                v = f(r, idx[r["date"]])
                return v if v in ("T", "M", "0") else "0"
            v = ev(name, pick)
            print(f"  {name:44s} {v[0]:+7.1f}／{v[1]:+7.1f}")
        out["pairs"][pair] = res
    (DATA / "research" / "tx_regime_switch.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
