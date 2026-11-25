#!/usr/bin/env python3
"""
盤勢判斷驗證：常見的盤後解讀（像 PTT 期貨板的「反彈第一天融資大增籌碼亂」「反彈量縮力道弱」「恐慌殺出拉下影」
「期現貨轉逆價差」「美元強、美債跌資金保守」）在加權指數上到底有沒有用

情境：加權指數離 60 日高點 ≥ 8% 的回檔中（另看全部日子）；看當天收盤後 5／10／20 個交易日的加權指數報酬
判斷（每個都分成「看空訊號成立」與「不成立」兩組比）：
  M1 反彈日融資大增：當天漲 ≥ 1.5% 且融資餘額增加（上市＋上櫃）在近一年回檔反彈日中屬前 1/3
  M2 反彈量縮：當天漲 ≥ 1% 且上市成交金額 < 近 20 日平均
  P1 恐慌下影：下影線 ≥ 當天振幅一半、振幅 ≥ 2%、盤中最低比昨收跌 ≥ 1.5%
  P2 逆價差：台指期近月收盤 − 加權指數收盤 < −0.3%（排除 6～9 月除息旺季，那時逆價差主要是除息造成的）
  D1 美元強、美債跌：美元指數 5 日漲 ≥ 1% 且美債 10 年殖利率 5 日升 ≥ 3%（前一晚收盤）
  T1 跌破 60 日低點後 5 天內反彈到跌破點附近（± 1.5%）又收在它下面（回測不過）
另外：回檔 ≥ 5% 中漲 ≥ 1.5% 的反彈日，依融資增減（佔餘額 %）、量能分三等份比較（M1 原定義事件太少）
統計：事件法——訊號連續出現只算第一天（相隔 ≥ 10 個交易日才算新事件），事件的平均報酬、上漲機率和同情境所有日子比，
     t＝（事件平均 − 全部平均）÷（事件標準差 ÷ √事件數）；事件少於 10 個不下結論
資料：data/research/yahoo（指數、美元、美債）、data/futures/day（台指期 1 分 K，2020 起）、data/research/market_hist.json（成交金額、融資，2012 起）
輸出 data/research/market_read.json；用法：python scripts/research_market_read.py
"""
from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
HZ = (5, 10, 20)


def yseries(name):
    j = json.loads((DATA / "research" / "yahoo" / f"{name}.json").read_text(encoding="utf-8"))["d"]
    return {r[0]: r for r in j}


def prev_val(ser: dict, keys: list, day: str, n: int = 0):
    k = bisect_left(keys, day) - 1 - n
    return ser[keys[k]][4] if k >= 0 else None


def main():
    tw = yseries("_TWII")
    days = sorted(d for d in tw if d >= "2012-01-01" and tw[d][4])
    c = [tw[d][4] for d in days]
    dxy, tnx = yseries("DX-Y.NYB"), yseries("_TNX")
    dk, tk = sorted(dxy), sorted(tnx)
    # 台指期近月收盤（data/futures/day：{日期: {"bars": [[分, 開, 高, 低, 收, 量], ...]}}）
    fut = {}
    for f in glob.glob(str(DATA / "futures" / "day" / "20*.json")):
        for d, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
            b = v.get("bars") if isinstance(v, dict) else None
            if b:
                fut[d] = b[-1][4]
    try:
        mh = json.loads((DATA / "research" / "market_hist.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        mh = {"turnover": {}, "margin": {}}
    tv, mg = mh.get("turnover", {}), mh.get("margin", {})
    rows = []
    for i, d in enumerate(days):
        if i < 60 or i + max(HZ) >= len(days):
            continue
        o, h, l, cl = tw[d][1], tw[d][2], tw[d][3], c[i]
        pc = c[i - 1]
        chg = (cl / pc - 1) * 100
        dd = (cl / max(c[i - 60:i + 1]) - 1) * 100
        fwd = {n: (c[i + n] / cl - 1) * 100 for n in HZ}
        rng = (h - l) / pc * 100
        r = {"d": d, "chg": chg, "dd": dd, "fwd": fwd}
        r["P1"] = rng >= 2 and (min(o, cl) - l) >= 0.5 * (h - l) and (l / pc - 1) * 100 <= -1.5
        if d in fut and d[5:7] not in ("06", "07", "08", "09"):
            r["P2"] = (fut[d] / cl - 1) * 100 < -0.3
        x0, x5 = prev_val(dxy, dk, d), prev_val(dxy, dk, d, 5)
        y0, y5 = prev_val(tnx, tk, d), prev_val(tnx, tk, d, 5)
        if x0 and x5 and y0 and y5:
            r["D1"] = (x0 / x5 - 1) * 100 >= 1 and (y0 / y5 - 1) * 100 >= 3
        low60 = min(c[i - 60:i - 5])
        brk = [k for k in range(i - 5, i) if c[k] < low60 <= c[k - 1]]
        r["T1"] = bool(brk) and abs(h / low60 - 1) * 100 <= 1.5 and cl < low60
        if d in tv:
            a20 = [tv[x] for x in days[i - 20:i] if x in tv]
            if len(a20) >= 15 and chg >= 1:
                r["M2"] = tv[d] < st.mean(a20)
        pd_ = days[i - 1]
        if chg >= 1.5 and d in mg and pd_ in mg and mg[d][0] is not None and mg[pd_][0] is not None:
            r["mgChg"] = (mg[d][0] + (mg[d][1] or 0)) - (mg[pd_][0] + (mg[pd_][1] or 0)) if mg[d][1] is not None and mg[pd_][1] is not None else mg[d][0] - mg[pd_][0]
        rows.append(r)
    # M1：反彈日融資增加屬前 1/3（門檻用該日之前一年的回檔反彈日決定）
    reb = [r for r in rows if "mgChg" in r and r["dd"] <= -8]
    for k, r in enumerate(reb):
        hist = [x["mgChg"] for x in reb[:k] if x["d"] >= f"{int(r['d'][:4]) - 2}{r['d'][4:]}"]
        if len(hist) >= 10:
            r["M1"] = r["mgChg"] >= sorted(hist)[2 * len(hist) // 3]
    names = {"M1": "反彈日融資大增（看空）", "M2": "反彈量縮（看空）", "P1": "恐慌下影（看多）", "P2": "期貨逆價差（看多：恐慌殺出）",
             "D1": "美元強＋美債跌（看空）", "T1": "跌破 60 日低點後回測不過（看空）"}
    out = {"horizons": HZ, "tests": {}}
    for scope, sf in (("回檔 ≥ 8% 中", lambda r: r["dd"] <= -8), ("全部日子", lambda r: True)):
        print(f"\n■ {scope}（加權指數之後 {HZ} 個交易日報酬 %；上漲機率；以月為單位的 t 值）")
        out["tests"][scope] = {}
        allr = [r for r in rows if sf(r)]
        base = {n: st.mean(r["fwd"][n] for r in allr) for n in HZ}
        bup = {n: sum(r["fwd"][n] > 0 for r in allr) / len(allr) * 100 for n in HZ}
        print("  全部（基準）：" + "、".join(f"{n} 天 {base[n]:+.2f}%（漲機率 {bup[n]:.0f}%）" for n in HZ))
        out["tests"][scope]["base"] = {"n": len(allr), "avg": {n: round(base[n], 2) for n in HZ}, "up": {n: round(bup[n], 1) for n in HZ}}
        for key, lab in names.items():
            rs = [r for r in rows if sf(r) and key in r]
            ev, last = [], -99
            idx = {d: k for k, d in enumerate(days)}
            for r in rs:
                if r[key]:
                    k = idx[r["d"]]
                    if k - last >= 10:
                        ev.append(r)
                    last = k
            if len(ev) < 10:
                print(f"  {lab}：事件 {len(ev)} 個，太少不下結論")
                out["tests"][scope][key] = {"label": lab, "events": len(ev)}
                continue
            line = {}
            for n in HZ:
                xs = [r["fwd"][n] for r in ev]
                m = st.mean(xs)
                t = (m - base[n]) / (st.stdev(xs) / len(xs) ** 0.5) if st.stdev(xs) else None
                line[n] = {"avg": round(m, 2), "up": round(sum(x > 0 for x in xs) / len(xs) * 100, 1), "t": round(t, 2) if t else None}
            out["tests"][scope][key] = {"label": lab, "events": len(ev), "h": line, "dates": [r["d"] for r in ev][-12:]}
            print(f"  {lab}：{len(ev)} 個事件（最近：{', '.join(r['d'] for r in ev[-4:])}）")
            print("     " + "、".join(f"{n} 天 {line[n]['avg']:+.2f}%（漲機率 {line[n]['up']:.0f}%，t={line[n]['t']:+.2f}）" for n in HZ))
    # 反彈日分組：回檔 ≥ 5% 中、當天漲 ≥ 1.5% 的日子，依「融資增減佔前一天融資餘額 %」與「成交金額 ÷ 20 日均量」分三等份
    print("\n■ 回檔 ≥ 5% 中、當天漲 ≥ 1.5% 的反彈日：依融資增減、量能分三等份（融資 2015/3 起，上市＋上櫃）")
    rb = []
    for r in rows:
        k = days.index(r["d"])
        p_ = days[k - 1]
        if r["dd"] > -5 or r["chg"] < 1.5 or r["d"] not in mg or p_ not in mg or None in mg[r["d"]] or None in mg[p_]:
            continue
        bal = mg[p_][0] + mg[p_][1]
        a20 = [tv[x] for x in days[k - 20:k] if x in tv]
        rb.append({**r, "dmp": (mg[r["d"]][0] + mg[r["d"]][1] - bal) / bal * 100, "tvr": tv[r["d"]] / st.mean(a20) if r["d"] in tv and a20 else None})
    out["rebound"] = {}
    for key, lab in (("dmp", "融資增減 % 餘額"), ("tvr", "量能（倍 20 日均量）")):
        xs = sorted(x[key] for x in rb if x[key] is not None)
        if len(xs) < 30:
            continue
        lo, hi = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        out["rebound"][key] = {}
        for g, gf in (("低", lambda v: v < lo), ("中", lambda v: lo <= v < hi), ("高", lambda v: v >= hi)):
            ys = [x for x in rb if x[key] is not None and gf(x[key])]
            o = {n: {"avg": round(st.mean(x["fwd"][n] for x in ys), 2), "up": round(sum(x["fwd"][n] > 0 for x in ys) / len(ys) * 100, 1)} for n in HZ}
            out["rebound"][key][g] = {"n": len(ys), "months": len({x["d"][:7] for x in ys}), "h": o}
            print(f"  {lab} {g}（{'<' if g == '低' else '≥'} {lo if g == '低' else hi if g == '高' else lo:+.2f}）{len(ys)} 天："
                  + "、".join(f"{n} 天 {o[n]['avg']:+.2f}%（漲 {o[n]['up']:.0f}%）" for n in HZ))
    (DATA / "research" / "market_read.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
