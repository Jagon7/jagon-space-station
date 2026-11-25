#!/usr/bin/env python3
"""
「新高法」短線策略回測（影片：投機實驗室，韓股；這裡改成台股上市股）

影片規則 → 這裡的實作：
  1 選股：當天成交額前 50 名（去掉 ETF）、類股裡的龍頭、股價刷新一年來最高價、站上 120 日線、跌勢裡不碰
       → 成交額（收盤 × 成交量）全市場前 50；收盤 > 前 250 天最高收盤（突破壓力線）；收盤 > MA120；
         龍頭＝同產業裡（同樣在前 50 名的股票）近 20 天漲幅第一（另測不限龍頭）；
         大盤濾網：加權指數收盤 > MA60（另測不加）
  2 等買點：突破那天要「衝上來有力」（放量長紅：漲 ≥ 4% 且量 ≥ 20 日均量 2 倍；磨上去的不算）；
       之後 1～3 天內出現「上升陰線或十字星」（收 ≤ 開，或 |收−開| ≤ 0.3%）、收盤仍在 5 日線上、
       沒跌回突破前的高點之下 → 當天收盤買（收盤前買）
       機構在買：歷史資料不足，回測不加（每日掃描時再看三大法人）
  3 賣出：買進隔天收盤沒漲（≤ 買價）→ 隔天收盤停損；否則一直拿，收盤跌破 5 日線就賣；
       或高檔爆出 ≥ 5 倍 20 日均量 → 當天收盤賣；最多拿 60 天
       另測：固定拿 5／10 天、不做隔天停損改用 10／20 日線出場（＋跌破突破日低點停損）
  基準：成交額前 50、站上 MA120、大盤 > MA60 的任一天收盤買（每 3 天抽一次）拿 10 天
  資金模擬：同時最多 3 檔、每檔 1/3 資金
  成本：手續費 0.1425% × 2 × 6 折＋證交稅 0.3% ≈ 0.47%
  比較組：突破當天收盤直接買（不等陰線）、陰線但不限龍頭／不加大盤濾網、固定拿 5／10 天
三大法人：data/research/new_high_inst.json（--need 列出要的日期，Actions 上 fetch_t86_hist.py 抓）
資料：data/research/yahoo_stocks（Yahoo 上市股日線 2011 起，約 950 檔；上櫃股不在內、下市股缺 → 有存活者偏差）
輸出 data/research/new_high.json；用法：python scripts/research_new_high.py
"""
from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = 0.47
TOPN = 50


def load():
    px = {}
    for f in glob.glob(str(DATA / "research" / "yahoo_stocks" / "*.json")):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        rows = [r for r in j["d"] if r[4] and r[1] and r[5] is not None]
        if len(rows) > 300:
            px[j["code"]] = rows
    return px


def sector_map():
    try:
        d = json.loads((DATA / "sector-stocks.json").read_text(encoding="utf-8"))["data"]
    except (OSError, ValueError, KeyError):
        return {}
    return {s["code"]: sec for sec, ls in d.items() for s in ls}


def ma(v, i, n):
    return sum(v[i - n + 1:i + 1]) / n if i >= n - 1 else None


def build(px):
    """每檔每天的指標；回傳 {code: dict of lists}，以及每天成交額前 50 名"""
    feats, by_day = {}, defaultdict(list)
    for c, rows in px.items():
        d = [r[0] for r in rows]
        o, h, l, cl, v = ([r[k] for r in rows] for k in (1, 2, 3, 4, 5))
        bad = set()
        for i in range(1, len(rows)):  # Yahoo 偶有錯價：單日 > 11% 視為壞資料（台股漲跌幅 10%）
            if abs(cl[i] / cl[i - 1] - 1) > 0.11:
                bad.update(range(i, min(len(rows), i + 2)))
        f = {"d": d, "o": o, "h": h, "l": l, "c": cl, "v": v, "bad": bad, "idx": {x: i for i, x in enumerate(d)}}
        feats[c] = f
        for i in range(250, len(rows)):
            by_day[d[i]].append((cl[i] * v[i], c))
    top = {day: {c for _, c in sorted(xs, reverse=True)[:TOPN]} for day, xs in by_day.items()}
    return feats, top


def twii():
    j = json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]
    c = [r[4] for r in j]
    return {r[0]: (c[i] > ma(c, i, 60)) if i >= 60 else None for i, r in enumerate(j)}


def simulate(f, i_buy, hold=None, next_stop=True, exit_ma=5, stop_px=None):
    """從 i_buy 收盤買進，回傳 (賣出 index, 報酬 %)
    next_stop：隔天收盤沒漲就停損（影片）；exit_ma：收盤跌破幾日線出場；stop_px：收盤跌破這個價位就停損"""
    c, v = f["c"], f["v"]
    buy = c[i_buy]
    n = len(c)
    if hold:
        j = min(n - 1, i_buy + hold)
        return j, (c[j] / buy - 1) * 100 - COST
    for j in range(i_buy + 1, min(n, i_buy + 61)):
        if next_stop and j == i_buy + 1 and c[j] <= buy:
            return j, (c[j] / buy - 1) * 100 - COST  # 隔天沒漲：停損
        if stop_px and c[j] < stop_px:
            return j, (c[j] / buy - 1) * 100 - COST
        m5 = ma(c, j, exit_ma)
        av20 = ma(v, j - 1, 20)
        if m5 and c[j] < m5:
            return j, (c[j] / buy - 1) * 100 - COST
        if av20 and v[j] >= 5 * av20 and c[j] > buy:
            return j, (c[j] / buy - 1) * 100 - COST  # 高檔爆量
    j = min(n - 1, i_buy + 60)
    return j, (c[j] / buy - 1) * 100 - COST


def main():
    px = load()
    sec = sector_map()
    feats, top = build(px)
    mkt = twii()
    days = sorted(top)
    # 1 突破日
    events = []
    for c, f in feats.items():
        d, o, h, l, cl, v = f["d"], f["o"], f["h"], f["l"], f["c"], f["v"]
        for i in range(250, len(d) - 2):
            if i in f["bad"] or c not in top.get(d[i], ()):
                continue
            prior_hi = max(cl[i - 250:i])
            if cl[i] <= prior_hi or cl[i] <= ma(cl, i, 120):
                continue
            chg = (cl[i] / cl[i - 1] - 1) * 100
            av20 = ma(v, i - 1, 20)
            strong = chg >= 4 and av20 and v[i] >= 2 * av20
            ret20 = cl[i] / cl[i - 20] - 1
            events.append({"c": c, "i": i, "d": d[i], "strong": bool(strong), "prior": prior_hi, "ret20": ret20, "mkt": mkt.get(d[i])})
    # 龍頭：同一天、同產業、在前 50 名而且也在突破／強勢的股票裡近 20 天漲幅第一
    peers = defaultdict(list)
    for c, f in feats.items():
        s = sec.get(c)
        if not s:
            continue
        for i in range(250, len(f["d"])):
            if c in top.get(f["d"][i], ()):
                peers[(f["d"][i], s)].append((f["c"][i] / f["c"][i - 20] - 1, c))
    for e in events:
        s = sec.get(e["c"])
        ps = peers.get((e["d"], s)) if s else None
        e["leader"] = bool(ps) and max(ps)[1] == e["c"]
    # 2 買點：突破後 1～3 天的上升陰線／十字星
    trades = defaultdict(list)
    seen = set()
    for e in sorted(events, key=lambda e: e["d"]):
        f = feats[e["c"]]
        o, cl = f["o"], f["c"]
        i = e["i"]
        base = {"c": e["c"], "d": e["d"], "strong": e["strong"], "leader": e["leader"], "mkt": e["mkt"]}
        # 比較組：突破當天收盤買
        if (e["c"], i) not in seen:
            j, r = simulate(f, i)
            trades["breakout_close"].append({**base, "r": r, "days": j - i})
        for k in (1, 2, 3):
            b = i + k
            if b >= len(cl) - 1 or b in f["bad"]:
                break
            if cl[b] < e["prior"]:
                break  # 跌回壓力線之下
            down_or_doji = cl[b] <= o[b] or abs(cl[b] / o[b] - 1) <= 0.003
            m5 = ma(cl, b, 5)
            if down_or_doji and m5 and cl[b] > m5:
                key = (e["c"], b)
                if key in seen:
                    break
                seen.add(key)
                j, r = simulate(f, b)
                t = {**base, "buy": f["d"][b], "r": r, "days": j - b, "stopNext": j == b + 1, "sell": f["d"][j]}
                trades["pullback"].append(t)
                for hd in (5, 10):
                    jh = min(len(cl) - 1, b + hd)
                    trades[f"pullback_hold{hd}"].append({**t, "r": simulate(f, b, hold=hd)[1], "days": hd, "sell": f["d"][jh]})
                for nm, kw in (("exit_ma5_nostop", {"next_stop": False}), ("exit_ma10_nostop", {"next_stop": False, "exit_ma": 10}),
                               ("exit_ma10_stopBreakLow", {"next_stop": False, "exit_ma": 10, "stop_px": f["l"][i]}),
                               ("exit_ma20_stopBreakLow", {"next_stop": False, "exit_ma": 20, "stop_px": f["l"][i]})):
                    j2, r2 = simulate(f, b, **kw)
                    trades[nm].append({**t, "r": r2, "days": j2 - b, "sell": f["d"][j2]})
                break

    for c, f in feats.items():
        cl = f["c"]
        for i in range(250, len(cl) - 11, 3):  # 每 3 天抽一次，避免太多重疊
            if i in f["bad"] or c not in top.get(f["d"][i], ()) or cl[i] <= ma(cl, i, 120):
                continue
            t = {"c": c, "d": f["d"][i], "strong": True, "leader": True, "mkt": mkt.get(f["d"][i]), "days": 10}
            trades["baseline_top50_ma120_hold10"].append({**t, "r": (cl[i + 10] / cl[i] - 1) * 100 - COST})
            j, r = simulate(f, i, next_stop=False, exit_ma=10)
            trades["baseline_top50_ma120_exit_ma10"].append({**t, "r": r, "days": j - i})

    # 三大法人（外資＋投信）：突破日到買進日合計買超股數
    # 要用的（日期, 代號）寫進 data/research/new_high_need.json，GitHub Actions 上跑 fetch_t86_hist.py 抓（證交所擋雲端以外的連線較少）
    # → data/research/new_high_inst.json {日期: {代號: [外資, 投信]}}
    need = defaultdict(set)
    for t in trades["pullback"]:
        if t["strong"]:
            f = feats[t["c"]]
            for x in f["d"][f["idx"][t["d"]]:f["idx"][t["buy"]] + 1]:
                need[x].add(t["c"])
    if "--need" in sys.argv:
        (DATA / "research" / "new_high_need.json").write_text(json.dumps({d: sorted(v) for d, v in sorted(need.items())}, separators=(",", ":")), encoding="utf-8")
        print(f"寫出 {len(need)} 天")
        return 0
    try:
        t86 = json.loads((DATA / "research" / "new_high_inst.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        t86 = {}
    print(f"三大法人資料：{sum(d in t86 for d in need)}／{len(need)} 天")
    for ts in trades.values():
        for t in ts:
            if "buy" not in t:
                continue
            f = feats[t["c"]]
            ds = f["d"][f["idx"][t["d"]]:f["idx"][t["buy"]] + 1]
            if not all(d in t86 for d in ds):
                t["inst"] = None
                continue
            x = [t86[d].get(t["c"]) or [0, 0] for d in ds]
            ft = sum((a or 0) + (b or 0) for a, b in x)
            t["inst"] = ft > 0
            t["instBuyDay"] = ((x[-1][0] or 0) + (x[-1][1] or 0)) > 0
            t["trust"] = sum(b or 0 for _, b in x) > 0

    def summ(ts):
        if len(ts) < 15:
            return {"n": len(ts)}
        rs = [t["r"] for t in ts]
        w = [x for x in rs if x > 0]
        ls = [x for x in rs if x <= 0]
        return {"n": len(ts), "win": round(len(w) / len(rs) * 100, 1), "avg": round(st.mean(rs), 2), "med": round(st.median(rs), 2),
                "avgWin": round(st.mean(w), 2) if w else None, "avgLoss": round(st.mean(ls), 2) if ls else None,
                "pf": round(sum(w) / -sum(ls), 2) if ls and sum(ls) else None, "days": round(st.mean(t.get("days", 0) for t in ts), 1)}

    parts = (("2012-18", lambda t: t["d"] < "2019-01-01"), ("2019-22", lambda t: "2019-01-01" <= t["d"] < "2023-01-01"),
             ("2023-", lambda t: t["d"] >= "2023-01-01"), ("全部", lambda t: True))
    filters = (("影片完整版（放量長紅＋龍頭＋大盤 > MA60）", lambda t: t["strong"] and t["leader"] and t["mkt"]),
               ("放量長紅＋大盤濾網（不限龍頭）", lambda t: t["strong"] and t["mkt"]),
               ("放量長紅（不限龍頭、不看大盤）", lambda t: t["strong"]),
               ("放量長紅＋龍頭（不看大盤）", lambda t: t["strong"] and t["leader"]),
               ("非放量長紅（磨上去的）＋大盤濾網", lambda t: not t["strong"] and t["mkt"]),
               ("放量長紅、大盤 < MA60", lambda t: t["strong"] and t["mkt"] is False),
               ("影片完整版＋法人（外資＋投信）突破到買進合計買超", lambda t: t["strong"] and t["leader"] and t["mkt"] and t.get("inst") is True),
               ("影片完整版＋法人合計賣超", lambda t: t["strong"] and t["leader"] and t["mkt"] and t.get("inst") is False),
               ("影片完整版＋買進當天法人買超", lambda t: t["strong"] and t["leader"] and t["mkt"] and t.get("instBuyDay") is True),
               ("影片完整版＋買進當天法人賣超", lambda t: t["strong"] and t["leader"] and t["mkt"] and t.get("instBuyDay") is False),
               ("影片完整版＋投信合計買超", lambda t: t["strong"] and t["leader"] and t["mkt"] and t.get("trust") is True),
               ("放量長紅＋大盤＋法人合計買超（不限龍頭）", lambda t: t["strong"] and t["mkt"] and t.get("inst") is True),
               ("放量長紅＋大盤＋法人合計賣超（不限龍頭）", lambda t: t["strong"] and t["mkt"] and t.get("inst") is False))
    out = {"cost": COST, "universe": len(feats), "range": [days[0], days[-1]], "groups": {}}
    fmt = lambda s: (f"n{s['n']:4d} 勝率 {s['win']:4.1f}% 平均 {s['avg']:+5.2f}% 中位 {s['med']:+5.2f}% 賺 {s['avgWin']:+.1f}/賠 {s['avgLoss']:+.1f} PF {s['pf']} 天數 {s['days']}"  # noqa: E731
                     if "win" in s else f"n{s['n']}（樣本不足）")
    print(f"上市股 {len(feats)} 檔，{days[0]}～{days[-1]}；成交額前 {TOPN}；每筆扣 {COST}%")
    for strat in ("pullback", "breakout_close", "pullback_hold5", "pullback_hold10", "exit_ma5_nostop", "exit_ma10_nostop",
                  "exit_ma10_stopBreakLow", "exit_ma20_stopBreakLow", "baseline_top50_ma120_hold10", "baseline_top50_ma120_exit_ma10"):
        print(f"\n■ {strat}")
        out["groups"][strat] = {}
        for fl, fn in filters:
            row = {}
            print(f"  {fl}")
            for pn, pf in parts:
                s = summ([t for t in trades[strat] if fn(t) and pf(t)])
                row[pn] = s
                print(f"     {pn:8s} {fmt(s)}")
            out["groups"][strat][fl] = row
    print("\n資金模擬（影片完整版進場；同時最多 3 檔、每檔 1/3 資金；額滿就跳過新訊號；同一天多檔依代號順序）")
    tw = {r[0]: r[4] for r in json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]}
    out["portfolio"] = {}
    for strat in ("pullback", "pullback_hold10", "exit_ma10_nostop", "exit_ma20_stopBreakLow"):
        ts = sorted([t for t in trades[strat] if t["strong"] and t["leader"] and t["mkt"]], key=lambda t: (t["buy"], t["c"]))
        eq, held, curve = 1.0, [], {}
        for t in ts:
            held = [h for h in held if h["sell"] > t["buy"]]
            if len(held) >= 3:
                continue
            held.append(t)
            eq *= 1 + t["r"] / 100 / 3
            curve[t["sell"]] = eq
        # 依賣出日排序算最大回落（近似：以平倉時點記帳）
        pk, mdd = 1.0, 0.0
        ys = {}
        for d in sorted(curve):
            pk = max(pk, curve[d])
            mdd = min(mdd, curve[d] / pk - 1)
            ys[d[:4]] = curve[d]
        yrs = sorted(ys)
        prev, yr = 1.0, {}
        for y in yrs:
            yr[y] = round((ys[y] / prev - 1) * 100, 1)
            prev = ys[y]
        cagr = (eq ** (1 / max(1, (int(yrs[-1]) - int(yrs[0]) + 1))) - 1) * 100 if yrs else 0
        out["portfolio"][strat] = {"final": round(eq, 2), "cagr": round(cagr, 1), "mdd": round(mdd * 100, 1), "years": yr}
        print(f"  {strat:24s} 期末 {eq:.2f} 倍、年化 {cagr:+.1f}%、最大回落 {mdd * 100:.1f}%｜各年 {yr}")
    t0 = [d for d in sorted(tw) if d >= "2012-01-05"]
    print(f"  加權指數（不含息） {tw[t0[-1]] / tw[t0[0]]:.2f} 倍")
    pb = [t for t in trades["pullback"] if t["strong"] and t["mkt"]]
    nx = [t for t in pb if t["stopNext"]]
    print(f"\n隔天就停損的比例（放量長紅＋大盤濾網）：{len(nx) / max(1, len(pb)) * 100:.0f}%")
    out["recent"] = sorted([t for t in trades["pullback"] if t["strong"]], key=lambda t: t["buy"])[-30:]
    (DATA / "research" / "new_high.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
