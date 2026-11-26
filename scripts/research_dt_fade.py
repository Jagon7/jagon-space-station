#!/usr/bin/env python3
"""
「高當沖比＋開高走低」長期回測，並檢驗大小型股預測過濾（scripts/research_size_rotation.py 的逐年滾動樣本外預測）

規則（同 build_turnover.py 的 dtAlert）：當天成交 ≥ 1 億、當沖比（當沖股數 ÷ 成交股數）≥ 60%、收黑K（收 < 開）但仍收漲（≥ 昨收）
  → 隔天開盤放空、收盤回補；開跌停不做；漲到昨收 +9% 停損（防券差）；成本 0.23%
  另看當沖比 ≥ 50%／70%、不限收漲
資料：data/research/dt_hist（fetch_dt_hist.py，2014 起）、data/research/yahoo_adj（日線）
  沒有歷史處置股清單 → 沒排除處置股（線上版有排除）
分組：當天開盤前的「大型股贏」機率，低／中／高門檻用 data/strategy/size_model.json（2023 起樣本外的 1/3、2/3 分位）
期間：2016-18／2019-22／2023+；t＝月份群聚（每月「中高組 − 低組」）
輸出 data/research/dt_fade.json；用法：python scripts/research_dt_fade.py
"""
from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_size_rotation as r  # noqa: E402

PARTS = (("2014-15", "2014", "2016"), ("2016-18", "2016", "2019"), ("2019-22", "2019", "2023"), ("2023+", "2023", "2100"))


def main():
    dt = {}
    for f in glob.glob(str(DATA / "research" / "dt_hist" / "20*.json")):
        for d, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
            if v.get("tw") or v.get("tp"):
                dt[d] = {**(v.get("tw") or {}), **(v.get("tp") or {})}
    print(f"當沖歷史 {len(dt)} 天（{min(dt)}～{max(dt)}）")
    days, agg, day, tsmc = r.build()
    rows = r.features(days, agg, tsmc)
    keys = list(rows[0]["f"]) + list(rows[0]["pre"])
    p = r.walk(rows, keys, "gbm")
    pl = {x["n"]: 1 - p[i] for i, x in enumerate(rows) if not np.isnan(p[i])}
    model = json.loads((DATA / "strategy" / "size_model.json").read_text(encoding="utf-8"))
    tier = lambda v: "低" if v < model["lo"] else "高" if v >= model["hi"] else "中"  # noqa: E731
    # 原始成交量（股）：yahoo_adj 的 v；day[d][c] = (市場, 開, 高, 收, 昨收, 成交額, 5日前, 昨成交額) 都是還原價
    vol = defaultdict(dict)
    for f in glob.glob(str(DATA / "research" / "yahoo_adj" / "*.json")):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        for x in j["d"]:
            if x[0] in dt and x[5]:
                vol[x[0]][j["code"]] = x[5]
    variants = {"當沖比 ≥ 60%、黑K 收漲（線上規則）": (60, True), "當沖比 ≥ 50%、黑K 收漲": (50, True),
                "當沖比 ≥ 70%、黑K 收漲": (70, True), "當沖比 ≥ 60%、黑K（不限漲跌）": (60, False)}
    out = {}
    for name, (dmin, need_up) in variants.items():
        ev = []
        for i in range(len(days) - 1):
            d, n = days[i], days[i + 1]
            if d not in dt:
                continue
            X, Y = day[d], day.get(n, {})
            for c, sh in dt[d].items():
                x = X.get(c)
                v = vol[d].get(c)
                if not x or not v or x[5] < 1e8 or sh / v * 100 < dmin:
                    continue
                if not x[3] < x[1] or (need_up and x[3] < x[4]):
                    continue
                y = Y.get(c)
                if not y:
                    continue
                o, h, a, pa = y[1], y[2], y[3], y[4]
                if o <= pa * 0.905:
                    continue
                ex = pa * 1.09 if h >= pa * 1.09 and o < pa * 1.09 else a
                ev.append((n, (o - ex) / o * 100 - r.COST))
        res = {}
        print(f"\n■ {name}：{len(ev)} 筆")
        for lab, a, b in PARTS:
            xs = [e for e in ev if a <= e[0] < b]
            if not xs:
                continue
            g = defaultdict(list)
            pairs = defaultdict(lambda: {"低": [], "其他": []})
            for d, x in xs:
                if d in pl:
                    k = tier(pl[d])
                    g[k].append(x)
                    pairs[d[:7]]["低" if k == "低" else "其他"].append(x)
            t, nm = r.month_t([(m, st.mean(v["其他"]) - st.mean(v["低"])) for m, v in pairs.items() if v["其他"] and v["低"]])
            f = lambda v: {"n": len(v), "avg": round(st.mean(v), 3), "win": round(sum(x > 0 for x in v) / len(v) * 100, 1)} if v else None  # noqa: E731
            res[lab] = {"all": f([x for _, x in xs]), **{k: f(g[k]) for k in ("低", "中", "高")}, "t": round(t, 2) if t else None, "months": nm}
            s = lambda k: f"{res[lab][k]['avg']:+.2f}%（{res[lab][k]['n']}，勝 {res[lab][k]['win']:.0f}%）" if res[lab][k] else "—"  # noqa: E731
            print(f"  {lab}: 全部 {s('all')}｜低 {s('低')}／中 {s('中')}／高 {s('高')}  t(其他−低)={res[lab]['t']}")
        out[name] = res
    (DATA / "research" / "dt_fade.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
