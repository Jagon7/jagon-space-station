#!/usr/bin/env python3
"""
匯率（美元／台幣）、美元指數、美債殖利率能不能幫忙推估台指期日盤走勢

資料：Yahoo TWD=X（美元兌台幣，數字變大＝台幣貶值）、DX-Y.NYB（美元指數）、^TNX（美國 10 年期殖利率）
  Yahoo 外匯日線以格林威治時間切日，日期 < 今天的那根在台灣時間 08:00 前就收完 → 08:45 開盤前一定已知（沒有偷看）
因子：前一天台幣漲跌%（＋＝貶）、幅度（絕對值）、5／20 日累積、相對 20 日波動的倍數（z）、20 日匯率波動、
  美元指數漲跌、美債殖利率變動（bp）
目標：① 大振幅（09:15 後振幅 ≥ 1 ATR20）② 單邊／來回刷 ③ 方向（09:15→13:30 漲或跌、開盤跳空方向）
驗證：2020-24／2025 後兩段各算 AUC；模型逐年滾動（research_tx_range），比較加不加匯率的差別
輸出 data/research/tx_fx.json；用法：python scripts/research_tx_fx.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_range as rg  # noqa: E402
import research_tx_regime as rr  # noqa: E402
import research_tx_structure as rs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
FX = ["fx1", "aFx1", "fx5", "fx20", "fxZ", "fxVol", "dxy1", "aDxy1", "tnx1", "aTnx1"]
LABEL = {"fx1": "前一天台幣漲跌%（＋＝貶）", "aFx1": "前一天台幣變動幅度", "fx5": "台幣 5 日累積（＋＝貶）", "fx20": "台幣 20 日累積（＋＝貶）",
         "fxZ": "前一天台幣變動 ÷ 20 日波動（倍數，絕對值）", "fxVol": "台幣 20 日波動", "dxy1": "美元指數漲跌%", "aDxy1": "美元指數變動幅度",
         "tnx1": "美債 10 年殖利率變動（bp）", "aTnx1": "美債殖利率變動幅度"}


def series(sym):
    return [(r[0], r[4]) for r in json.loads((DATA / "research" / "yahoo" / f"{sym}.json").read_text(encoding="utf-8"))["d"] if r[4]]


def main():
    rows = rg.rows_all()
    day = rr.load_dir(DATA / "futures" / "day")
    fx, dx, tn = series("TWD=X"), series("DX-Y.NYB"), series("_TNX")
    for r in rows:
        d = r["date"]
        f = [c for t, c in fx if t < d][-21:]
        x = [c for t, c in dx if t < d][-2:]
        n = [c for t, c in tn if t < d][-2:]
        ch = [(f[i] / f[i - 1] - 1) * 100 for i in range(1, len(f))]
        vol = st.pstdev(ch) if len(ch) >= 10 else None
        r.update({"fx1": ch[-1] if ch else None, "aFx1": abs(ch[-1]) if ch else None,
                  "fx5": (f[-1] / f[-6] - 1) * 100 if len(f) >= 6 else None, "fx20": (f[-1] / f[0] - 1) * 100 if len(f) >= 21 else None,
                  "fxVol": vol, "fxZ": abs(ch[-1]) / vol if ch and vol else None,
                  "dxy1": (x[-1] / x[-2] - 1) * 100 if len(x) == 2 else None, "aDxy1": abs(x[-1] / x[-2] - 1) * 100 if len(x) == 2 else None,
                  "tnx1": (n[-1] - n[-2]) * 100 if len(n) == 2 else None, "aTnx1": abs(n[-1] - n[-2]) * 100 if len(n) == 2 else None})
        b = day[d]
        p915 = b[rr.OR_M - 1][3] if rr.OR_M - 1 in b else b[min(b)][0]
        last = b[max(m for m in b if m <= rr.EXIT_M)][3]
        r["upPost"] = last > p915
    # 跳空方向：開盤 vs 前一天日盤收盤
    ds = sorted(day)
    close = {d: day[d][max(day[d])][3] for d in ds}
    for r in rows:
        k = ds.index(r["date"])
        r["gapUp"] = day[r["date"]][min(day[r["date"]])][0] > close[ds[k - 1]] if k else None

    parts = (("2020-24", [r for r in rows if r["date"] < "2025-01-01"]), ("2025 後", [r for r in rows if r["date"] >= "2025-01-01"]))
    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "single": {}, "buckets": {}, "model": {}}
    print(f"{rows[0]['date']}～{rows[-1]['date']}：{len(rows)} 天")
    tg = (("big", "大振幅"), ("trend", "單邊"), ("chop", "來回刷"), ("upPost", "09:15 後收漲"), ("gapUp", "開高"))
    print("\n單一因子 AUC（2020-24／2025 後）；0.5＝沒用，> 0.5＝數值越大越容易發生，< 0.5＝反向")
    print(f"  {'':30s}" + "".join(f"{lab:>16s}" for _, lab in tg))
    for k in FX:
        o = {}
        line = f"  {LABEL[k]:30s}"
        for t, lab in tg:
            a = []
            for _, part in parts:
                v = [(r[k], bool(r[t])) for r in part if r.get(k) is not None and r.get(t) is not None]
                a.append(rs.auc([y for _, y in v], [x for x, _ in v]))
            o[t] = [round(a[0], 3), round(a[1], 3)]
            ok = (a[0] - .5) * (a[1] - .5) > 0 and min(abs(a[0] - .5), abs(a[1] - .5)) >= 0.03
            line += f"   {a[0]:.2f}／{a[1]:.2f}{'✓' if ok else ' '}"
        out["single"][k] = {"label": LABEL[k], "auc": o}
        print(line)
    # 台幣大貶／大升（前一天變動 ≥ 20 日波動 1.5 倍）的日子
    print("\n前一天台幣大幅變動（≥ 1.5 倍 20 日波動）的隔天：大振幅%／單邊%／09:15 後收漲%／開高%／BO／MR（每天點數）")
    for lab, cond in (("台幣大貶", lambda r: r["fx1"] is not None and r["fxVol"] and r["fx1"] >= 1.5 * r["fxVol"]),
                      ("台幣大升", lambda r: r["fx1"] is not None and r["fxVol"] and r["fx1"] <= -1.5 * r["fxVol"]),
                      ("其他", lambda r: r["fx1"] is not None and r["fxVol"] and abs(r["fx1"]) < 1.5 * r["fxVol"])):
        o = []
        for pn, part in parts:
            s = [r for r in part if cond(r)]
            v = {"n": len(s), "big": round(sum(r["big"] for r in s) / len(s) * 100, 1), "trend": round(sum(r["trend"] for r in s) / len(s) * 100, 1),
                 "up": round(sum(r["upPost"] for r in s) / len(s) * 100, 1), "gapUp": round(sum(bool(r["gapUp"]) for r in s) / len(s) * 100, 1),
                 "bo": round(st.mean(r["bo"] for r in s), 1), "mr": round(st.mean(r["mr"] for r in s), 1)} if s else None
            o.append(v)
        out["buckets"][lab] = o
        f = lambda v: f"n{v['n']:3d} {v['big']:4.0f}/{v['trend']:3.0f}/{v['up']:3.0f}/{v['gapUp']:3.0f} BO{v['bo']:+6.1f} MR{v['mr']:+6.1f}" if v else "—"  # noqa: E731
        print(f"  {lab:6s} 2020-24 {f(o[0])}   2025 後 {f(o[1])}")
    # 模型：加不加匯率（逐年滾動，2022 起樣本外）
    print("\n大振幅模型（逐年滾動，2022～2026 樣本外）：加入匯率前後")
    oos = [r for r in rows if r["date"] >= "2022-01-01"]
    for nm, keys in (("開盤前（結構＋盤前）", rg.STRUCT + rg.PRE), ("開盤前＋匯率", rg.STRUCT + rg.PRE + FX),
                     ("09:15 全部", rg.STRUCT + rg.PRE + rg.AT915), ("09:15 全部＋匯率", rg.STRUCT + rg.PRE + rg.AT915 + FX)):
        pr = rg.walk(rows, keys)
        s = [r for r in oos if r["date"] in pr]
        a = rs.auc([r["big"] for r in s], [pr[r["date"]][0] for r in s])
        top = [r for r in s if pr[r["date"]][1] == 4]
        bot = [r for r in s if pr[r["date"]][1] == 0]
        out["model"][nm] = {"auc": round(a, 3), "top": round(sum(r["big"] for r in top) / len(top) * 100, 1), "bot": round(sum(r["big"] for r in bot) / len(bot) * 100, 1)}
        print(f"  {nm:16s} AUC {a:.3f}；預測最高 1/5 大振幅 {out['model'][nm]['top']}%、最低 1/5 {out['model'][nm]['bot']}%")
    # 交易：台幣大幅變動（任一方向）的隔天，現行規則裡的 BO 改成不做／改 MR
    print("\n交易回測（現行規則；台幣前一天變動 ≥ 1.5 倍 20 日波動的隔天調整）每天平均點數 2020-24／2025 後（總點數）")
    out["trade"] = {}
    bigfx = lambda r: r["fx1"] is not None and r["fxVol"] and abs(r["fx1"]) >= 1.5 * r["fxVol"]  # noqa: E731
    for nm, f in (("現行規則", lambda r: r["rule"]), ("大變動日 BO 改不做", lambda r: 0 if bigfx(r) and r["plan"] == "BO" else r["rule"]),
                  ("大變動日 BO 改 MR", lambda r: r["mr"] if bigfx(r) and r["plan"] == "BO" else r["rule"]),
                  ("大變動日全部不做", lambda r: 0 if bigfx(r) else r["rule"])):
        v = [round(st.mean(f(r) for r in part), 1) for _, part in parts]
        tot = round(sum(f(r) for r in rows))
        out["trade"][nm] = {"avg": v, "total": tot}
        print(f"  {nm:16s} {v[0]:+6.1f}／{v[1]:+6.1f}（總 {tot:+,} 點）")
    for pn, part in parts:
        s_ = [r for r in part if bigfx(r)]
        print(f"  {pn} 大變動日 {len(s_)} 天：現行規則 {st.mean(r['rule'] for r in s_):+.1f}，其中規則做 BO 的 {sum(r['plan'] == 'BO' for r in s_)} 天平均 BO "
              f"{st.mean([r['bo'] for r in s_ if r['plan'] == 'BO'] or [0]):+.1f}、MR {st.mean([r['mr'] for r in s_ if r['plan'] == 'BO'] or [0]):+.1f}")
    (DATA / "research" / "tx_fx.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
