#!/usr/bin/env python3
"""
兩個新的放空策略回測（日線；data/research/yahoo_adj，2011 起，還原權息；只有現在還掛牌的 → 有存活者偏差，對放空是保守的）

① 空族群弱勢：同族群裡強勢股漲停，走勢相似的弱勢股被帶上去 → 放空弱勢股
  族群＝公開資訊觀測站產業別，再要求「走勢相似」：前 60 天日報酬相關係數 ≥ 0.5
  事件（第 t 天）：族群裡有股票收漲停（漲 ≥ 9.5% 且收在最高）＝強勢股；
    同族群、相似的股票當天漲 +2%～+9%（被帶上去、沒漲停）、成交 ≥ 5000 萬＝弱勢股
  做法：A 隔天（t+1）開盤空、收盤補（當沖）；B t 收盤空、t+1 開盤補（隔夜）；C t 收盤空、拿 5 天
  氣氛分組：族群當天漲停家數、族群當天上漲比例、強勢股是不是連續漲停、弱勢股隔天開盤跳空方向
② 向上緩搓：連 5 天大多小漲、波動小的慢慢墊高 → 之後是一路黑K，還是跌一下又繼續漲？
  事件（第 t 天收盤）：近 5 天至少 4 天收漲、每天漲跌都在 −1%～+3%、5 天累計 +4%～+12%、
    5 天平均振幅 ≤ 3%、5 天平均成交 ≥ 1 億；前 5 天內已經是事件的不重複算
  看：隔天開盤空、收盤補（當沖）與隔天收黑K機率、從隔天起連續黑K天數、
      之後 1／3／5／10／20 天報酬、10 天內最大跌幅、20 天內有沒有再創新高；和「所有符合成交門檻的日子」比
共同：當沖成本 0.23%，隔夜／多日 0.47%；停損 +9%（漲到前一天收盤 +9% 就回補）；三段 2012-18／2019-22／2023+；t＝月份群聚
輸出 data/research/dt_new.json；用法：python scripts/research_dt_new.py
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_new_high as nh  # noqa: E402

DT_COST, SW_COST = 0.23, 0.47
PARTS = (("2012-18", "2012", "2019"), ("2019-22", "2019", "2023"), ("2023+", "2023", "2100"))


def month_t(pairs):
    by = defaultdict(list)
    for m, v in pairs:
        by[m].append(v)
    xs = [st.mean(v) for v in by.values()]
    return round(st.mean(xs) / (st.stdev(xs) / math.sqrt(len(xs))), 2) if len(xs) > 2 and st.stdev(xs) else None


def short_dt(o, h, c, pc):
    """隔天開盤空、收盤補，漲到前一天收盤 +9% 停損"""
    stop = pc * 1.09
    if o >= stop:
        return None
    ex = stop if h >= stop else c
    return (o - ex) / o * 100 - DT_COST


def summ(xs):
    if not xs:
        return None
    return {"n": len(xs), "avg": round(st.mean(xs), 3), "win": round(sum(x > 0 for x in xs) / len(xs) * 100, 1)}


def by_part(ev, key):
    out = {}
    for lab, a, b in PARTS:
        xs = [e for e in ev if a <= e["d"] < b and e.get(key) is not None]
        s = summ([e[key] for e in xs])
        if s:
            s["t"] = month_t([(e["d"][:7], e[key]) for e in xs])
        out[lab] = s
    return out


def fmt(res):
    return "｜".join(f"{lab} {v['avg']:+.2f}%（{v['n']} 筆，勝 {v['win']:.0f}%，t {v['t']}）" if v else f"{lab} —" for lab, v in res.items())


def main():
    px, mk = nh.load()
    sec = nh.sector_map()
    # 每檔：日期索引、報酬
    S = {}
    for c, rows in px.items():
        if not sec.get(c):
            continue
        d = [r[0] for r in rows]
        S[c] = {"d": d, "idx": {x: i for i, x in enumerate(d)}, "o": [r[1] for r in rows], "h": [r[2] for r in rows], "l": [r[3] for r in rows],
                "c": [r[4] for r in rows], "tv": [r[6] for r in rows]}
    by_day = defaultdict(list)
    for c, s in S.items():
        for i in range(61, len(s["d"]) - 6):
            by_day[s["d"][i]].append((c, i))
    out = {}

    # ---------- ① 空族群弱勢 ----------
    ev1 = []
    for d, xs in by_day.items():
        if d < "2012":
            continue
        groups = defaultdict(list)
        for c, i in xs:
            s = S[c]
            r = s["c"][i] / s["c"][i - 1] - 1
            if abs(r) > 0.11:
                continue   # 壞資料
            groups[sec[c]].append((c, i, r))
        for g, mem in groups.items():
            leaders = [(c, i) for c, i, r in mem if r >= 0.095 and S[c]["c"][i] >= S[c]["h"][i] * 0.999]
            if not leaders:
                continue
            n_lu = len(leaders)
            breadth = sum(r > 0 for _, _, r in mem) / len(mem)
            for lc, li in leaders[:3]:
                L = S[lc]
                lr = [L["c"][k] / L["c"][k - 1] - 1 for k in range(li - 60, li)]
                streak = L["c"][li - 1] / L["c"][li - 2] - 1 >= 0.095
                for c, i, r in mem:
                    if c == lc or not (0.02 <= r < 0.09) or S[c]["tv"][i] < 5e7:
                        continue
                    s = S[c]
                    pr = [s["c"][k] / s["c"][k - 1] - 1 for k in range(i - 60, i)]
                    try:
                        cor = st.correlation(lr, pr)
                    except st.StatisticsError:
                        continue
                    if cor < 0.5:
                        continue
                    o1, h1, c1 = s["o"][i + 1], s["h"][i + 1], s["c"][i + 1]
                    e = {"d": d, "code": c, "leader": lc, "group": g, "ret": r * 100, "corr": cor, "nLU": n_lu, "breadth": breadth, "streak": streak,
                         "gap1": (o1 / s["c"][i] - 1) * 100,
                         "A": short_dt(o1, h1, c1, s["c"][i]),
                         "B": (s["c"][i] - o1) / s["c"][i] * 100 - SW_COST,
                         "C": (s["c"][i] - s["c"][i + 5]) / s["c"][i] * 100 - SW_COST}
                    ev1.append(e)
                break   # 同一個弱勢股同一天只算一次（用第一檔強勢股）
    # 同一天同一檔只留一次
    seen, uniq = set(), []
    for e in ev1:
        k = (e["d"], e["code"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    ev1 = uniq
    print(f"■ ① 空族群弱勢：{len(ev1)} 個事件（弱勢股；放空報酬，正＝賺）")
    out["groupWeak"] = {}
    for key, lab in (("A", "隔天開盤空、收盤補（當沖）"), ("B", "當天收盤空、隔天開盤補"), ("C", "當天收盤空、拿 5 天")):
        res = by_part(ev1, key)
        out["groupWeak"][key] = res
        print(f"  {lab}：{fmt(res)}")
    print("  氣氛分組（A 當沖）：")
    out["groupWeakSplit"] = {}
    for name, f in (("族群只有 1 檔漲停", lambda e: e["nLU"] == 1), ("族群 2 檔漲停", lambda e: e["nLU"] == 2), ("族群 ≥ 3 檔漲停", lambda e: e["nLU"] >= 3),
                    ("族群上漲比例 < 60%", lambda e: e["breadth"] < 0.6), ("族群上漲比例 ≥ 80%", lambda e: e["breadth"] >= 0.8),
                    ("強勢股連續漲停", lambda e: e["streak"]), ("強勢股第一根漲停", lambda e: not e["streak"]),
                    ("弱勢股當天 +2～5%", lambda e: e["ret"] < 5), ("弱勢股當天 +5～9%", lambda e: e["ret"] >= 5),
                    ("隔天開低", lambda e: e["gap1"] < 0), ("隔天開高 0～3%", lambda e: 0 <= e["gap1"] < 3), ("隔天開高 ≥ 3%", lambda e: e["gap1"] >= 3)):
        res = by_part([e for e in ev1 if f(e)], "A")
        out["groupWeakSplit"][name] = res
        print(f"    {name:14s}：{fmt(res)}")

    print("  隔天開高 0～3%（掛昨收價限價賣，開低不成交）再依氣氛細分：")
    g03 = [e for e in ev1 if 0 <= e["gap1"] < 3]
    out["groupWeakGap03"] = {}
    for name, f in (("全部", lambda e: True), ("族群上漲比例 < 80%", lambda e: e["breadth"] < 0.8), ("族群上漲比例 ≥ 80%", lambda e: e["breadth"] >= 0.8),
                    ("族群 1～2 檔漲停", lambda e: e["nLU"] <= 2), ("族群 ≥ 3 檔漲停", lambda e: e["nLU"] >= 3),
                    ("強勢股連續漲停", lambda e: e["streak"]), ("強勢股第一根漲停", lambda e: not e["streak"])):
        res = by_part([e for e in g03 if f(e)], "A")
        out["groupWeakGap03"][name] = res
        print(f"    {name:14s}：{fmt(res)}")

    # ---------- ② 向上緩搓 ----------
    ev2, base = [], []
    last_ev = {}
    for c, s in S.items():
        cl, o, h, l, tv = s["c"], s["o"], s["h"], s["l"], s["tv"]
        for i in range(6, len(cl) - 21):
            d = s["d"][i]
            if d < "2012":
                continue
            rs = [cl[k] / cl[k - 1] - 1 for k in range(i - 4, i + 1)]
            if any(abs(x) > 0.11 for x in rs) or st.mean(tv[i - 4:i + 1]) < 1e8:
                continue
            nxt = {"A": short_dt(o[i + 1], h[i + 1], cl[i + 1], cl[i]), "black": cl[i + 1] < o[i + 1]}
            for n in (1, 3, 5, 10, 20):
                nxt[f"r{n}"] = (cl[i + n] / cl[i] - 1) * 100
            nxt["dd10"] = (min(l[i + 1:i + 11]) / cl[i] - 1) * 100
            nxt["newHigh20"] = max(h[i + 1:i + 21]) > max(h[i - 4:i + 1])
            k, run = i + 1, 0
            while k < len(cl) and cl[k] < o[k] and run < 10:
                run += 1
                k += 1
            nxt["blackRun"] = run
            if i % 3 == 0:
                base.append({"d": d, **nxt})
            ups = sum(x > 0 for x in rs)
            cum = cl[i] / cl[i - 5] - 1
            rng = st.mean((h[k] - l[k]) / cl[k - 1] for k in range(i - 4, i + 1))
            if ups >= 4 and all(-0.01 <= x <= 0.03 for x in rs) and 0.04 <= cum <= 0.12 and rng <= 0.03:
                if last_ev.get(c, -99) >= i - 5:
                    last_ev[c] = i
                    continue
                last_ev[c] = i
                ev2.append({"d": d, "code": c, **nxt})
                for k in range(i + 1, i + 4):   # 3 天內第一根黑K收盤買進
                    if cl[k] < o[k]:
                        ev2[-1]["L5"] = (cl[k + 5] / cl[k] - 1) * 100 - SW_COST
                        ev2[-1]["L10"] = (cl[k + 10] / cl[k] - 1) * 100 - SW_COST
                        ev2[-1]["Ld"] = s["d"][k]
                        break
    print(f"\n■ ② 向上緩搓：{len(ev2)} 個事件；對照＝所有日均成交 ≥ 1 億的日子（抽樣 {len(base)}）")
    out["grind"] = {"n": len(ev2)}
    res = by_part(ev2, "A")
    out["grind"]["A"] = res
    print(f"  隔天開盤空、收盤補（當沖）：{fmt(res)}")
    print(f"  （對照）所有日子隔天當沖空：{fmt(by_part(base, 'A'))}")
    for lab, a, b in PARTS:
        e = [x for x in ev2 if a <= x["d"] < b]
        z = [x for x in base if a <= x["d"] < b]
        if not e:
            continue
        line = {
            "黑K率": (sum(x["black"] for x in e) / len(e) * 100, sum(x["black"] for x in z) / len(z) * 100),
            "連續黑K≥2天": (sum(x["blackRun"] >= 2 for x in e) / len(e) * 100, sum(x["blackRun"] >= 2 for x in z) / len(z) * 100),
            "連續黑K≥3天": (sum(x["blackRun"] >= 3 for x in e) / len(e) * 100, sum(x["blackRun"] >= 3 for x in z) / len(z) * 100),
            **{f"{n}天報酬": (st.mean(x[f"r{n}"] for x in e), st.mean(x[f"r{n}"] for x in z)) for n in (1, 3, 5, 10, 20)},
            "10天內最大跌幅": (st.mean(x["dd10"] for x in e), st.mean(x["dd10"] for x in z)),
            "20天內再創新高": (sum(x["newHigh20"] for x in e) / len(e) * 100, sum(x["newHigh20"] for x in z) / len(z) * 100),
        }
        out["grind"][lab] = {k: [round(v[0], 2), round(v[1], 2)] for k, v in line.items()}
        print(f"  {lab}（{len(e)} 筆）：" + "、".join(f"{k} {v[0]:.1f} vs {v[1]:.1f}" for k, v in line.items()))
    for n in (1, 3, 5, 10, 20):
        res = by_part([{**x, "s": -x[f"r{n}"] - (DT_COST if n == 0 else SW_COST)} for x in ev2], "s")
        out["grind"][f"short{n}"] = res
        print(f"  收盤空、拿 {n:2d} 天：{fmt(res)}")
    for n in (5, 10):
        res = by_part([x for x in ev2 if x.get(f"L{n}") is not None], f"L{n}")
        out["grind"][f"long{n}"] = res
        print(f"  做多：緩搓後 3 天內第一根黑K收盤買、拿 {n:2d} 天：{fmt(res)}")
    # 對照：任意一天收盤買、拿 5／10 天（扣同樣成本）
    for n in (5, 10):
        res = by_part([{**x, "b": x[f"r{n}"] - SW_COST} for x in base], "b")
        print(f"  （對照）任意一天收盤買、拿 {n:2d} 天：{fmt(res)}")
    (DATA / "research" / "dt_new.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
