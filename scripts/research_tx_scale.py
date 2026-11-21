#!/usr/bin/env python3
"""
台指期日盤當沖：「逆勢加碼」vs「順勢加碼」回測（大台一口＝1 點 200 元，每口來回扣 3 點）

共同設定：09:15 的價格當起點；每格＝step × ATR20（前 20 天日盤 TR 平均）；最多 N 口；13:30 收盤全部平倉
  用每分鐘收盤判斷與成交（不用盤中最高最低，避免高估）；09:15～13:25 才進場
A 逆勢加碼（漲多空、跌多買）
  離起點 +1 格放空 1 口，每再漲 1 格加空 1 口（最多 N 口）；跌回「平均成本 − 0.5 格」全部停利；
  漲到第 N+1 格停損（全部出場）；出場後以當時價格當新起點重來。下跌對稱做多
B 順勢加碼（漲多買、跌多空）
  離起點 +1 格做多 1 口，每再漲 1 格加 1 口（最多 N 口）；從進場後最高點回落 1 格全部出場（移動停損）；
  出場後以當時價格當新起點重來。下跌對稱做空
C 混合：依前面研究可預測的東西選打法
  C1 開盤區間窄（≤ 0.34 ATR，兩邊都被掃的機率約六成）→ A，其他 → B
  C2 大振幅模型（research_tx_range 逐年滾動、樣本外）預測最高 2/5 → B，最低 2/5 → A，中間不做
  C3 現行 09:15 規則（tx_regime_review.decide）說 MR → A、BO → B、不做 → 不做
輸出 data/research/tx_scale.json；用法：python scripts/research_tx_scale.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = 3.0
START, LAST_IN, EXIT = rr.OR_M - 1, 280, rr.EXIT_M  # 09:14 收盤＝09:15 起點；13:25 後不進場；13:30 平倉


def fade(px: list[float], g: float, n: int):
    """A：逆勢加碼；回傳 (當天點數, 交易口數, 最大持倉時的浮虧)"""
    pnl, lots, worst = 0.0, 0, 0.0
    anchor = px[0]
    pos = []  # 每口進場價（正＝多、負＝空，用 side 記方向）
    side = 0
    for i, p in enumerate(px[1:], 1):
        if pos:
            avg = st.mean(pos)
            fl = (p - avg) * side * len(pos)
            worst = min(worst, fl)
            tgt = avg + side * 0.5 * g  # 往有利方向回 0.5 格（多單：成本 +0.5 格；空單：成本 −0.5 格）停利
            stop = anchor + side * -1 * (n + 1) * g  # 第 N+1 格停損（side=−1 空單：起點 +(N+1) 格）
            hit_tp = (p <= tgt) if side < 0 else (p >= tgt)
            hit_sl = (p >= stop) if side < 0 else (p <= stop)
            if hit_tp or hit_sl or i == len(px) - 1:
                pnl += fl - COST * len(pos)
                lots += len(pos)
                pos, side, anchor = [], 0, p
                continue
            # 加碼：再往不利方向 1 格
            if len(pos) < n and i <= LAST_IN - START and ((p - anchor) * -side >= (len(pos) + 1) * g):
                pos.append(p)
            continue
        if i > LAST_IN - START:
            continue
        if p - anchor >= g:
            side, pos = -1, [p]
        elif anchor - p >= g:
            side, pos = 1, [p]
    return pnl, lots, worst


def trend(px: list[float], g: float, n: int):
    """B：順勢加碼＋移動停損"""
    pnl, lots, worst = 0.0, 0, 0.0
    anchor = px[0]
    pos, side, ext = [], 0, None
    for i, p in enumerate(px[1:], 1):
        if pos:
            ext = max(ext, p) if side > 0 else min(ext, p)
            fl = (p - st.mean(pos)) * side * len(pos)
            worst = min(worst, fl)
            if (ext - p) * side >= g or i == len(px) - 1:
                pnl += fl - COST * len(pos)
                lots += len(pos)
                pos, side, anchor, ext = [], 0, p, None
                continue
            if len(pos) < n and i <= LAST_IN - START and (p - anchor) * side >= (len(pos) + 1) * g:
                pos.append(p)
            continue
        if i > LAST_IN - START:
            continue
        if p - anchor >= g:
            side, pos, ext = 1, [p], p
        elif anchor - p >= g:
            side, pos, ext = -1, [p], p
    return pnl, lots, worst


def stats(xs: list[float]) -> dict:
    eq = pk = mdd = 0.0
    for x in xs:
        eq += x
        pk = max(pk, eq)
        mdd = min(mdd, eq - pk)
    return {"n": len(xs), "avg": round(st.mean(xs), 1), "total": round(sum(xs)), "win": round(sum(x > 0 for x in xs) / len(xs) * 100, 1),
            "worst": round(min(xs)), "best": round(max(xs)), "mdd": round(mdd),
            "p5": round(sorted(xs)[len(xs) // 20])}


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    ds = sorted(d for d, b in day.items() if len(b) >= 250 and START in b)
    tr = {}
    for i in range(1, len(ds)):
        b, pb = day[ds[i]], day[ds[i - 1]]
        pc = pb[max(pb)][3]
        tr[ds[i]] = max(max(x[1] for x in b.values()), pc) - min(min(x[2] for x in b.values()), pc)
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    import tx_regime_review as trv
    P = trv.params()["current"]
    days = []
    for i in range(21, len(ds)):
        d = ds[i]
        b = day[d]
        px = [b[m][3] for m in range(START, EXIT + 1) if m in b]
        if len(px) < 200 or d not in reg:
            continue
        atr = st.mean(tr[k] for k in ds[i - 20:i])
        days.append({"date": d, "px": px, "atr": atr, "orATR": reg[d]["orATR"], "plan": trv.decide(reg[d], P)[1]})
    # 大振幅預測（樣本外，2022 起）
    pred = {}
    try:
        import research_tx_range as rg
        rows = rg.rows_all()
        pred = rg.walk(rows, rg.STRUCT + rg.PRE + rg.AT915)
    except Exception as e:  # noqa: BLE001
        print("大振幅預測失敗：", e)
    parts = (("2020-24", lambda d: d < "2025-01-01"), ("2025 後", lambda d: d >= "2025-01-01"))
    out = {"from": days[0]["date"], "to": days[-1]["date"], "cost": COST, "grid": [], "hybrid": {}}
    print(f"{days[0]['date']}～{days[-1]['date']}：{len(days)} 天；每口來回扣 {COST} 點；數字＝每天點數（大台 1 點＝200 元）")
    print("\n格寬 step（ATR 倍數）× 最多口數 N：每天平均（2020-24／2025 後）、勝率、最差一天、最大回落、最差 5% 的一天")
    res = {}
    for step in (0.1, 0.15, 0.2, 0.3, 0.4):
        for n in (1, 2, 3, 4):
            for nm, fn in (("A 逆勢加碼", fade), ("B 順勢加碼", trend)):
                r = [(d["date"],) + fn(d["px"], step * d["atr"], n) for d in days]
                res[(nm, step, n)] = {x[0]: x[1] for x in r}
                xs = [x[1] for x in r]
                h = [st.mean([x[1] for x in r if f(x[0])]) for _, f in parts]
                s = stats(xs)
                s.update({"name": nm, "step": step, "N": n, "h1": round(h[0], 1), "h2": round(h[1], 1), "lots": round(st.mean(x[2] for x in r), 1),
                          "worstFloat": round(min(x[3] for x in r))})
                out["grid"].append(s)
    for nm in ("A 逆勢加碼", "B 順勢加碼"):
        print(f"\n  {nm}")
        for s in [g for g in out["grid"] if g["name"] == nm]:
            print(f"    格 {s['step']:.2f} ATR × 最多 {s['N']} 口：每天 {s['avg']:+6.1f}（{s['h1']:+6.1f}／{s['h2']:+6.1f}）勝率 {s['win']:4.1f}% "
                  f"最差一天 {s['worst']:+6,} 最大回落 {s['mdd']:+7,} 最差 5% {s['p5']:+5,} 每天 {s['lots']} 口")
    # 混合：用各自表現最穩的一組格寬（兩段都 > 0 或最好）
    def best(nm):
        c = [g for g in out["grid"] if g["name"] == nm]
        return max(c, key=lambda g: min(g["h1"], g["h2"]))
    ba, bb = best("A 逆勢加碼"), best("B 順勢加碼")
    print(f"\n混合用的參數：A 格 {ba['step']}×{ba['N']} 口、B 格 {bb['step']}×{bb['N']} 口（各自兩段中較差那段最好的組合）")
    A, B = res[("A 逆勢加碼", ba["step"], ba["N"])], res[("B 順勢加碼", bb["step"], bb["N"])]
    hyb = {
        "只做 A": lambda d: A[d["date"]],
        "只做 B": lambda d: B[d["date"]],
        "C1 開盤區間窄 → A，其他 → B": lambda d: A[d["date"]] if d["orATR"] <= 0.34 else B[d["date"]],
        "C1' 開盤區間窄 → A，其他不做": lambda d: A[d["date"]] if d["orATR"] <= 0.34 else 0.0,
        "C3 現行 09:15 規則：MR → A、BO → B": lambda d: A[d["date"]] if d["plan"] == "MR" else B[d["date"]] if d["plan"] == "BO" else 0.0,
    }
    if pred:
        hyb["C2 大振幅預測 高 2/5 → B、低 2/5 → A"] = lambda d: (B[d["date"]] if pred[d["date"]][1] >= 3 else A[d["date"]] if pred[d["date"]][1] <= 1 else 0.0) if d["date"] in pred else None
        hyb["C2' 大振幅預測 高 2/5 → B，其他不做"] = lambda d: (B[d["date"]] if pred[d["date"]][1] >= 3 else 0.0) if d["date"] in pred else None
    print("\n混合打法（2022 起，大振幅預測只有樣本外才公平）：每天平均（2022-24／2025 後）")
    for nm, f in hyb.items():
        v = [(d["date"], f(d)) for d in days if d["date"] >= "2022-01-01"]
        v = [(dd, x) for dd, x in v if x is not None]
        xs = [x for _, x in v]
        s = stats(xs)
        s["h1"] = round(st.mean([x for dd, x in v if dd < "2025-01-01"]), 1)
        s["h2"] = round(st.mean([x for dd, x in v if dd >= "2025-01-01"]), 1)
        out["hybrid"][nm] = s
        print(f"  {nm:34s} 每天 {s['avg']:+6.1f}（{s['h1']:+6.1f}／{s['h2']:+6.1f}）總 {s['total']:+8,} 勝率 {s['win']}% 最差一天 {s['worst']:+,} 最大回落 {s['mdd']:+,}")
    (DATA / "research" / "tx_scale.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
