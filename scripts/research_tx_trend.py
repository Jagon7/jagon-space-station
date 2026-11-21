#!/usr/bin/env python3
"""
台指期日盤：09:15 之後會「單邊走」還是「上下刷」？哪些 09:15 前就知道的資訊能預測

當天型態（09:15～13:30，期交所 1 分 K）：
  效率 eff = |收盤 − 09:15 價| ÷ (09:15 後最高 − 最低)；≥ 0.6 叫「單邊」，< 0.3 叫「來回刷」
  雙邊破 = 09:15 後先後突破開盤區間高點與低點（兩邊停損都會被掃）
  VWAP 穿越次數（09:15 後）
預測因子（09:15 前就知道）：開盤區間寬度、跳空、缺口回補、09:15 位置、開盤 30 分量能、
  前 1／5／20 天的效率（型態會不會延續）、前一天振幅、平均振幅、夜盤振幅與方向、
  美國重大事件、結算日、VIX、加權距 60 日高點、星期
2025-01-01 前建模、之後驗證（兩段方向一致才算有用）
輸出 data/research/tx_trend.json；用法：python scripts/research_tx_trend.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
SPLIT = "2025-01-01"


def yahoo(sym):
    p = DATA / "research" / "yahoo" / f"{sym}.json"
    return json.loads(p.read_text(encoding="utf-8"))["d"] if p.exists() else []


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    base = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    vix = yahoo("_VIX")
    tw = yahoo("_TWII")
    rows = []
    effs = []
    for d in sorted(base):
        b = day.get(d)
        if not b:
            continue
        orb = [b[m] for m in range(rr.OR_M) if m in b]
        post = [b[m] for m in range(rr.OR_M, rr.EXIT_M + 1) if m in b]
        if len(post) < 200 or not orb:
            continue
        orh, orl = max(x[1] for x in orb), min(x[2] for x in orb)
        p915 = orb[-1][3]
        hi, lo, cl = max(x[1] for x in post), min(x[2] for x in post), post[-1][3]
        eff = abs(cl - p915) / (hi - lo) if hi > lo else 0
        up = next((i for i, x in enumerate(post) if x[1] > orh), None)
        dn = next((i for i, x in enumerate(post) if x[2] < orl), None)
        two = up is not None and dn is not None
        # 09:15 後 VWAP 穿越次數
        vw = rr.vwap_path(b, rr.EXIT_M)
        cross = sum(1 for m in range(rr.OR_M + 1, rr.EXIT_M + 1) if b.get(m) and b.get(m - 1) and vw[m] and vw[m - 1]
                    and (b[m][3] - vw[m]) * (b[m - 1][3] - vw[m - 1]) < 0)
        r = dict(base[d])
        vx = [x for x in vix if x[0] < d]
        tk = [x for x in tw if x[0] < d][-60:]
        r.update({"effPost": round(eff, 3), "trend": eff >= 0.6, "chop": eff < 0.3, "two": two, "crossPost": cross,
                  "prev5Eff": round(st.mean(effs[-5:]), 3) if len(effs) >= 5 else None,
                  "prev20Eff": round(st.mean(effs[-20:]), 3) if len(effs) >= 20 else None,
                  "prevTwo5": None, "vix": vx[-1][4] if vx else None,
                  "dd60": round((tk[-1][4] / max(x[2] for x in tk) - 1) * 100, 2) if len(tk) >= 20 else None,
                  "dow": date.fromisoformat(d).weekday() + 1, "rangePost": hi - lo})
        rows.append(r)
        effs.append(eff)
    for i, r in enumerate(rows):
        r["prevTwo5"] = sum(x["two"] for x in rows[max(0, i - 5):i]) if i >= 5 else None
        r["prevChop"] = rows[i - 1]["chop"] if i else None
        r["prevTrend"] = rows[i - 1]["trend"] if i else None

    def summ(rs):
        if not rs:
            return None
        return {"n": len(rs), "trend": round(sum(r["trend"] for r in rs) / len(rs) * 100, 1),
                "chop": round(sum(r["chop"] for r in rs) / len(rs) * 100, 1),
                "two": round(sum(r["two"] for r in rs) / len(rs) * 100, 1),
                "eff": round(st.mean(r["effPost"] for r in rs), 3), "cross": round(st.mean(r["crossPost"] for r in rs), 1),
                "bo": round(st.mean(r["bo"] for r in rs), 1), "mr": round(st.mean(r["mr"] for r in rs), 1)}

    tr = [r for r in rows if r["date"] < SPLIT]
    te = [r for r in rows if r["date"] >= SPLIT]
    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "split": SPLIT, "all": summ(rows), "train": summ(tr), "test": summ(te),
           "features": {}, "flags": {}}
    print(f"{rows[0]['date']}～{rows[-1]['date']}：{len(rows)} 天（建模 {len(tr)}／驗證 {len(te)}）")
    for k, s in (("全部", out["all"]), ("建模", out["train"]), ("驗證", out["test"])):
        print(f"  {k}：單邊 {s['trend']}%、來回刷 {s['chop']}%、雙邊破 {s['two']}%、效率 {s['eff']}、VWAP 穿越 {s['cross']}")
    feats = [("orATR", "開盤區間寬度 ÷ 平均振幅"), ("absGapATR", "跳空大小 ÷ 平均振幅"), ("gapATR", "跳空方向（＋開高）"),
             ("pos915", "09:15 在開盤區間的位置（0 低～1 高）"), ("rvol30", "開盤 30 分量能 ÷ 20 日平均"), ("vwapCross30", "開盤 30 分 VWAP 穿越次數"),
             ("eff", "（不能用）"), ("prevEff", "前一天效率"), ("prev5Eff", "前 5 天平均效率"), ("prev20Eff", "前 20 天平均效率"),
             ("prevTwo5", "前 5 天雙邊破天數"), ("prevRangeATR", "前一天振幅 ÷ 平均振幅"), ("atrPct", "平均振幅 ÷ 指數 %"),
             ("nightRangeATR", "夜盤振幅 ÷ 平均振幅"), ("nightDir", "夜盤效率（單邊程度）"), ("vix", "VIX"), ("dd60", "加權距 60 日高點 %")]
    feats = [f for f in feats if f[0] != "eff"]
    print("\n三等分（低／中／高）：單邊% ／ 來回刷% ／ 雙邊破%；建模 → 驗證")
    for k, lab in feats:
        xs = sorted(r[k] for r in tr if r.get(k) is not None)
        if len(xs) < 100:
            continue
        c1, c2 = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        grp = lambda rs, a, b: [r for r in rs if r.get(k) is not None and a <= r[k] < b]  # noqa: E731
        cuts = [(-1e18, c1), (c1, c2), (c2, 1e18)]
        o = {"label": lab, "cut": [round(c1, 3), round(c2, 3)], "train": [summ(grp(tr, a, b)) for a, b in cuts], "test": [summ(grp(te, a, b)) for a, b in cuts]}
        # 一致性：高 − 低 的單邊率差，兩段同號
        dtr = o["train"][2]["trend"] - o["train"][0]["trend"]
        dte = o["test"][2]["trend"] - o["test"][0]["trend"] if o["test"][0] and o["test"][2] else None
        o["trendSpread"] = [round(dtr, 1), round(dte, 1) if dte is not None else None]
        o["chopSpread"] = [round(o["train"][2]["chop"] - o["train"][0]["chop"], 1),
                           round(o["test"][2]["chop"] - o["test"][0]["chop"], 1) if dte is not None else None]
        out["features"][k] = o
        f = lambda s: f"{s['trend']:4.0f}/{s['chop']:3.0f}/{s['two']:3.0f}" if s else "—"  # noqa: E731
        print(f"  {lab:28s} {' '.join(f(s) for s in o['train'])}  →  {' '.join(f(s) for s in o['test'])}   單邊差 {o['trendSpread']} 來回刷差 {o['chopSpread']}")
    print("\n是／否：")
    for k, lab in (("gapFilled30", "缺口 30 分內回補"), ("openOutside", "開在前一天高低點外"), ("nr7", "前一天是 7 日最小振幅"),
                   ("usEvent", "前一晚美國重大事件"), ("settle", "結算日"), ("prevChop", "前一天來回刷"), ("prevTrend", "前一天單邊")):
        o = {"label": lab, "train": [summ([r for r in tr if r.get(k) is v]) for v in (False, True)],
             "test": [summ([r for r in te if r.get(k) is v]) for v in (False, True)]}
        out["flags"][k] = o
        f = lambda s: f"{s['trend']:4.0f}/{s['chop']:3.0f}/{s['two']:3.0f}(n{s['n']})" if s else "—"  # noqa: E731
        print(f"  {lab:20s} 否 {f(o['train'][0])} 是 {f(o['train'][1])}  →  否 {f(o['test'][0])} 是 {f(o['test'][1])}")
    print("\n星期：")
    out["dow"] = {}
    for w in range(1, 6):
        out["dow"][w] = [summ([r for r in tr if r["dow"] == w]), summ([r for r in te if r["dow"] == w])]
        print(f"  週{w}", out["dow"][w][0]["trend"], out["dow"][w][0]["chop"], "→", out["dow"][w][1]["trend"], out["dow"][w][1]["chop"])
    (DATA / "research" / "tx_trend.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
