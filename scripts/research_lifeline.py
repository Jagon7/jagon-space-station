#!/usr/bin/env python3
"""
「生命線」（今年所有人的平均成本＝年初起算的成交量加權均價 VWAP）與各種均線，能不能當抄底的支撐

線（都只用當天收盤以前的資料）：
  life     今年成本：今年第一個交易日起的 VWAP（典型價 (高+低+收)/3 × 成交量）
  life252  過去一年成本：最近 252 個交易日的 VWAP
  lifePrev 去年全年成本（去年 VWAP，今年固定不變）
  ma20／ma60（季線）／ma120（半年線）／ma240（年線）
檢驗 1　第一次回測支撐：前 10 天收盤都在線上，今天最低碰到線 +1% 以內 →
        之後 5／20／60 天報酬、20 天後還在線上的比例、20 天內收盤跌破線 3% 以上的比例；
        跟「線 ×0.95、×1.05」兩條假線（同樣事件定義）比，真的線要明顯比較好才算數
檢驗 2　放進抄底：加權距 60 日高點跌 ≥ 12% 的日子，依「收盤在線的上方／附近（±2%）／下方」分組看 20 天後報酬、
        之後再跌多少；以及抄底訊號 A／B（research_bottom）觸發時在線上還是線下
兩段驗證 2005-2017／2018-2026；台股為主，美日韓同樣算一次看是不是普遍現象
輸出 data/research/lifeline.json；用法：python scripts/research_lifeline.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
SPLIT = "2018-01-01"
LINES = [("life", "生命線（今年成本 VWAP）"), ("life252", "過去一年成本（252 日 VWAP）"), ("lifePrev", "去年全年成本"),
         ("ma20", "月線 MA20"), ("ma60", "季線 MA60"), ("ma120", "半年線 MA120"), ("ma240", "年線 MA240")]
MKTS = [("_TWII", "台股加權"), ("_GSPC", "美股 S&P500"), ("_N225", "日經"), ("_KS11", "韓股 KOSPI")]


def build(sym, path=None):
    d = json.loads(((path or DATA / "research" / "yahoo" / f"{sym}.json")).read_text(encoding="utf-8"))["d"]
    d = [r for r in d if r[4] and r[2] and r[3]]
    rows = []
    vols = []
    cum = {}
    prev_vwap = {}
    for i, r in enumerate(d):
        dt, o, h, l, c, v = r[0], r[1], r[2], r[3], r[4], r[5] or 0
        if not v:  # 少數天成交量缺：用前 20 天平均
            v = st.mean(vols[-20:]) if vols else 1
        vols.append(v)
        tp = (h + l + c) / 3
        y = dt[:4]
        if y not in cum:
            if cum:
                py = max(cum)
                prev_vwap[y] = cum[py][0] / cum[py][1]
            cum[y] = [0.0, 0.0, 0]
        cum[y][0] += tp * v
        cum[y][1] += v
        cum[y][2] += 1
        x = {"date": dt, "o": o, "h": h, "l": l, "c": c, "life": cum[y][0] / cum[y][1], "lifeN": cum[y][2], "lifePrev": prev_vwap.get(y)}
        if i >= 251:
            pv = sum(((d[k][2] + d[k][3] + d[k][4]) / 3) * (vols[k]) for k in range(i - 251, i + 1))
            x["life252"] = pv / sum(vols[i - 251:i + 1])
        for n in (20, 60, 120, 240):
            if i >= n - 1:
                x[f"ma{n}"] = st.mean(d[k][4] for k in range(i - n + 1, i + 1))
        rows.append(x)
    for i, x in enumerate(rows):
        hi60 = max(r["h"] for r in rows[max(0, i - 59):i + 1])
        x["dd"] = (x["c"] / hi60 - 1) * 100
        for n in (5, 20, 60):
            x[f"r{n}"] = (rows[i + n]["c"] / x["c"] - 1) * 100 if i + n < len(rows) else None
        fut = rows[i + 1:i + 21]
        x["mdd20"] = (min(r["l"] for r in fut) / x["c"] - 1) * 100 if len(fut) == 20 else None
    return rows


def touch_events(rows, key, mult=1.0):
    ev = []
    for i in range(10, len(rows) - 1):
        x = rows[i]
        lv = x.get(key)
        if lv is None or (key == "life" and x["lifeN"] < 20):  # 年初前 20 天今年成本還不穩，不算
            continue
        lv *= mult
        prev_ok = all(rows[k].get(key) and rows[k]["c"] > rows[k][key] * mult for k in range(i - 10, i))
        if not prev_ok or x["l"] > lv * 1.01:
            continue
        fut = rows[i + 1:i + 21]
        if len(fut) < 20:
            continue
        ev.append({"date": x["date"], "r5": x["r5"], "r20": x["r20"], "r60": x["r60"],
                   "hold": fut[-1]["c"] > (fut[-1].get(key) or lv) * mult,
                   "brk": any(r["c"] < (r.get(key) or lv) * mult * 0.97 for r in fut)})
    return ev


def s_ev(ev):
    if len(ev) < 8:
        return None
    r60 = [e["r60"] for e in ev if e["r60"] is not None]
    return {"n": len(ev), "r5": round(st.mean(e["r5"] for e in ev), 2), "r20": round(st.mean(e["r20"] for e in ev), 2),
            "win20": round(sum(e["r20"] > 0 for e in ev) / len(ev) * 100), "r60": round(st.mean(r60), 2) if r60 else None,
            "hold": round(sum(e["hold"] for e in ev) / len(ev) * 100), "brk": round(sum(e["brk"] for e in ev) / len(ev) * 100)}


def main():
    out = {"split": SPLIT, "markets": {}}
    for sym, mname in MKTS:
        rows = build(sym)
        res = {"touch": {}, "deep": {}, "base": {}}
        parts = (("前", lambda d: d < SPLIT), ("後", lambda d: d >= SPLIT))
        for pn, pf in parts:
            rr = [x for x in rows if pf(x["date"]) and x["r20"] is not None]
            res["base"][pn] = {"r20": round(st.mean(x["r20"] for x in rr), 2), "win20": round(sum(x["r20"] > 0 for x in rr) / len(rr) * 100)}
        print(f"\n========== {mname}（{rows[0]['date']}～{rows[-1]['date']}）　基準：任意一天 20 天後 "
              f"{res['base']['前']['r20']:+.2f}%（勝率 {res['base']['前']['win20']}%）／{res['base']['後']['r20']:+.2f}%（{res['base']['後']['win20']}%）")
        print("檢驗 1：第一次回測（前 10 天都在線上，今天最低碰到線）→ 20 天後報酬、勝率、20 天後仍在線上、20 天內跌破 3%；2005-17 ／ 2018-26")
        f = lambda s: f"n{s['n']:3d} 20天 {s['r20']:+5.2f}% 勝 {s['win20']:3d}% 守住 {s['hold']:3d}% 跌破 {s['brk']:3d}% 60天 {s['r60']:+5.2f}%" if s else "樣本不足"  # noqa: E731
        for key, lab in LINES:
            res["touch"][key] = {}
            for mult, ml in ((1.0, "真線"), (0.95, "假線 ×0.95"), (1.05, "假線 ×1.05")):
                ev = touch_events(rows, key, mult)
                v = [s_ev([e for e in ev if pf(e["date"])]) for _, pf in parts]
                res["touch"][key][ml] = v
                if mult == 1.0 or sym == "_TWII":
                    print(f"  {lab if mult == 1.0 else '':26s}{ml:9s}｜{f(v[0])}｜{f(v[1])}")
        # 檢驗 2：深跌（距 60 日高 ≥ 12%）時，在線上／附近／下方
        print("檢驗 2：深跌日（距 60 日高點 ≥ 12%）收盤在線上方／附近 ±2%／下方 → 20 天後報酬、勝率、之後 20 天最多再跌")
        deep = [x for x in rows if x["dd"] <= -12 and x["r20"] is not None and x["mdd20"] is not None]
        for key, lab in LINES:
            res["deep"][key] = {}
            line = f"  {lab:26s}"
            for pn, pf in parts:
                g = {}
                for gn, cond in (("上方", lambda x: x["c"] > x[key] * 1.02), ("附近", lambda x: abs(x["c"] / x[key] - 1) <= 0.02), ("下方", lambda x: x["c"] < x[key] * 0.98)):
                    s = [x for x in deep if pf(x["date"]) and x.get(key) and not (key == "life" and x["lifeN"] < 20) and cond(x)]
                    g[gn] = {"n": len(s), "r20": round(st.mean(x["r20"] for x in s), 2), "win": round(sum(x["r20"] > 0 for x in s) / len(s) * 100),
                             "mdd": round(st.mean(x["mdd20"] for x in s), 1)} if len(s) >= 10 else None
                res["deep"][key][pn] = g
                line += f"｜{pn} " + " ".join(f"{gn}{v['r20']:+.1f}%/{v['win']}%/再跌{v['mdd']}(n{v['n']})" if v else f"{gn}—" for gn, v in g.items())
            print(line)
        out["markets"][sym] = {"name": mname, **res}
        if sym == "_TWII":
            # 抄底訊號 A／B（research_bottom 的 bottom_rows）× 生命線／年線
            br = {r["date"]: r for r in json.loads((DATA / "research" / "bottom_rows.json").read_text(encoding="utf-8"))}
            byd = {x["date"]: x for x in rows}
            print("抄底訊號 A／B 觸發日（同一波只算第一次）× 收盤在線上／下：20 天後報酬、勝率")
            sig = []
            last = None
            for d in sorted(br):
                r = br[d]
                a = r["dd"] <= -12 and (r.get("spx1") or 0) >= 1.5
                b = r["dd"] <= -12 and (r.get("vixOff") or 0) >= 10 and (r.get("vix") or 0) >= 22 and r.get("upDay")
                if (a or b) and d in byd and byd[d]["r20"] is not None:
                    if last and (len([k for k in br if last < k <= d]) <= 20):
                        last = d
                        continue
                    last = d
                    sig.append(byd[d])
            out["markets"][sym]["signals"] = {}
            for key, lab in LINES:
                o = {}
                for gn, cond in (("線上", lambda x: x.get(key) and x["c"] >= x[key]), ("線下", lambda x: x.get(key) and x["c"] < x[key])):
                    s = [x for x in sig if cond(x)]
                    o[gn] = {"n": len(s), "r20": round(st.mean(x["r20"] for x in s), 2), "win": round(sum(x["r20"] > 0 for x in s) / len(s) * 100),
                             "mdd": round(st.mean(x["mdd20"] for x in s), 1), "dates": [x["date"] for x in s]} if s else None
                out["markets"][sym]["signals"][key] = o
                print(f"  {lab:26s} " + "  ".join(f"{gn} n{v['n']} 20天 {v['r20']:+.1f}% 勝 {v['win']}% 再跌 {v['mdd']}%" if v else f"{gn} —" for gn, v in o.items()))
            # 檢驗 3：跌破（前 20 天都在線上，今天收盤跌破）與站回（前 20 天都在線下，今天收盤站上）
            print("檢驗 3：第一次收盤跌破／站回 → 20／60 天報酬、勝率（2005-17 ／ 2018-26）")
            out["markets"][sym]["cross"] = {}
            for key, lab in LINES:
                o = {}
                for kind, cond in (("跌破", lambda i: rows[i]["c"] < rows[i][key] and all(rows[k].get(key) and rows[k]["c"] > rows[k][key] for k in range(i - 20, i))),
                                   ("站回", lambda i: rows[i]["c"] > rows[i][key] and all(rows[k].get(key) and rows[k]["c"] < rows[k][key] for k in range(i - 20, i)))):
                    ev = [rows[i] for i in range(21, len(rows)) if rows[i].get(key) and rows[i]["r20"] is not None
                          and not (key == "life" and rows[i]["lifeN"] < 20) and cond(i)]
                    v = []
                    for _, pf in parts:
                        e = [x for x in ev if pf(x["date"])]
                        r60 = [x["r60"] for x in e if x["r60"] is not None]
                        v.append({"n": len(e), "r20": round(st.mean(x["r20"] for x in e), 2), "win": round(sum(x["r20"] > 0 for x in e) / len(e) * 100),
                                  "r60": round(st.mean(r60), 2) if r60 else None} if len(e) >= 5 else None)
                    o[kind] = v
                out["markets"][sym]["cross"][key] = o
                g = lambda v: f"n{v['n']:2d} {v['r20']:+5.1f}%/{v['win']:3d}% 60天{v['r60']:+5.1f}%" if v and v["r60"] is not None else "—"  # noqa: E731
                print(f"  {lab:26s} 跌破 {g(o['跌破'][0])}｜{g(o['跌破'][1])}    站回 {g(o['站回'][0])}｜{g(o['站回'][1])}")
            # 檢驗 4：歷次 ≥15% 回檔的底部，離各條線多遠
            bm = json.loads((DATA / "research" / "bottom_multi.json").read_text(encoding="utf-8"))
            sw = [x for x in bm["swings"]["^TWII"]["list"] if x["drop"] <= -15]
            print("檢驗 4：歷次 ≥15% 回檔的最低點，收盤離各條線（%）")
            out["markets"][sym]["troughs"] = []
            for e in sw:
                x = byd.get(e["trough"])
                if not x:
                    continue
                dist = {k: round((x["c"] / x[k] - 1) * 100, 1) for k, _ in LINES if x.get(k)}
                out["markets"][sym]["troughs"].append({"trough": e["trough"], "drop": e["drop"], "dist": dist})
                print(f"  {e['trough']}（{e['drop']}%）" + " ".join(f"{k} {v:+.1f}" for k, v in dist.items()))
            ts = out["markets"][sym]["troughs"]
            med = {k: round(st.median(t["dist"][k] for t in ts if k in t["dist"]), 1) for k, _ in LINES}
            out["markets"][sym]["troughMedian"] = med
            print("  中位數：" + "、".join(f"{lab} {med[k]:+.1f}%" for k, lab in LINES))
            # 現在
            x = rows[-1]
            out["now"] = {"date": x["date"], "close": round(x["c"], 2), "lines": {k: round(x[k], 2) for k, _ in LINES if x.get(k)},
                          "dist": {k: round((x["c"] / x[k] - 1) * 100, 2) for k, _ in LINES if x.get(k)}}
            print("現在 " + x["date"] + f" 加權 {x['c']:,.0f}：" + "、".join(f"{lab} {x[k]:,.0f}（{(x['c'] / x[k] - 1) * 100:+.1f}%）" for k, lab in LINES if x.get(k)))
    # 個股：每檔上市股（data/research/yahoo_stocks，約 950 檔，2011 起）第一次回測各條線 → 20 天超額報酬（扣掉同期加權）
    sd = DATA / "research" / "yahoo_stocks"
    if sd.exists():
        tw = {x["date"]: x for x in build("_TWII")}
        print("\n========== 個股（第一次回測，20 天後 超額報酬＝個股 − 加權）2011-17 ／ 2018-26")
        agg = {}
        for f in sorted(sd.glob("*.json")):
            try:
                rows = build(None, f)
            except Exception:  # noqa: BLE001
                continue
            if len(rows) < 300:
                continue
            for key, _ in LINES:
                if key == "ma20":
                    continue
                for mult in (1.0, 0.95, 1.05):
                    for e in touch_events(rows, key, mult):
                        t = tw.get(e["date"])
                        if not t or t["r20"] is None:
                            continue
                        agg.setdefault((key, mult), []).append((e["date"], e["r20"] - t["r20"], e["hold"], e["brk"]))
        out["stocks"] = {}
        for key, lab in LINES:
            if key == "ma20":
                continue
            o = {}
            line = f"  {lab:26s}"
            for mult, ml in ((1.0, "真線"), (0.95, "×0.95"), (1.05, "×1.05")):
                ev = agg.get((key, mult), [])
                v = []
                for pn, pf in (("前", lambda d: d < SPLIT), ("後", lambda d: d >= SPLIT)):
                    e = [x for x in ev if pf(x[0])]
                    v.append({"n": len(e), "ex20": round(st.mean(x[1] for x in e), 2), "win": round(sum(x[1] > 0 for x in e) / len(e) * 100, 1),
                              "hold": round(sum(x[2] for x in e) / len(e) * 100, 1), "brk": round(sum(x[3] for x in e) / len(e) * 100, 1)} if e else None)
                o[ml] = v
                line += f"｜{ml} " + " ／ ".join(f"超額 {x['ex20']:+.2f}% 贏大盤 {x['win']}% 守住 {x['hold']}% 跌破 {x['brk']}% (n{x['n']})" if x else "—" for x in v)
            out["stocks"][key] = o
            print(line)
    (DATA / "research" / "lifeline.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
