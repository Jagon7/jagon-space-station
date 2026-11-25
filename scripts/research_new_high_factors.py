#!/usr/bin/env python3
"""
新高法因子掃描：在「影片完整版」進場（放量長紅突破一年新高的龍頭、3 天內收黑／十字、大盤 > MA60）之上，
測哪些因子能把好壞交易分開（看拿 10 天的報酬，買點收盤買；已扣 0.47%）

因子（全部用買點當天收盤前就知道的資料；美股、匯率、債市用買點「前一天」的收盤，避免偷看）：
  大盤／風險：加權指數離 MA60、20 日漲跌、離一年高點；VIX 水準與 5 日變化；HYG/LQD（信用風險偏好）對 50 日線；
             S&P 500、費半 SOX 對 50 日線與 20 日漲跌；美元指數、台幣、美債 10 年殖利率 20 日變化
  氣氛／廣度：全市場站上 20 日線的比例、當天創一年新高的家數、近 5 天放量突破的家數
  上市／上櫃：上櫃平均 20 日漲幅減上市平均（資金偏好中小型股？）、這檔是上市或上櫃
  國際類股：電子類（半導體、電腦週邊、電子零組件…）看費半趨勢，其他類看 S&P 500
  法人：外資＋投信（及各自）從突破日到買點的合計買超，佔同期間成交量 %（data/research/new_high_inst.json）
  個股：突破日漲幅、量倍數、突破前 20 天漲幅、突破幅度（離前高多少）、距離上一次創高幾天、
        買點那天跌多少、買點是突破後第幾天、成交額排名、突破日上影線、離 120 日線多遠
判斷：每個因子分三等份（門檻用 2012-18 的資料定，再拿去看 2019-22、2023 後，避免用未來資料挑門檻），
     三段都是「好的一組 > 差的一組」才算穩定；最後把穩定的因子組合，看 2019 後的樣本外表現
輸出 data/research/new_high_factors.json；用法：python scripts/research_new_high_factors.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_new_high as nh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = nh.COST
HOLD = 10
PARTS = (("2012-18", "2012", "2019"), ("2019-22", "2019", "2023"), ("2023-", "2023", "2100"))
TECH = ("半導體", "電腦", "電子零組件", "光電", "通信網路", "電子通路", "資訊服務", "其他電子")


def series(name):
    j = json.loads((DATA / "research" / "yahoo" / f"{name}.json").read_text(encoding="utf-8"))["d"]
    return [r[0] for r in j], [r[4] for r in j]


class Prev:
    """美股等外部序列：取「早於某天」的最後一筆（台股買點當天收盤時，美股只收到前一天）"""

    def __init__(self, name):
        self.d, self.c = series(name)

    def at(self, day):
        k = bisect_left(self.d, day) - 1  # 早於 day 的最後一筆
        return k if k >= 0 else None

    def val(self, day):
        k = self.at(day)
        return self.c[k] if k is not None else None

    def chg(self, day, n):
        k = self.at(day)
        return (self.c[k] / self.c[k - n] - 1) * 100 if k is not None and k >= n else None

    def vs_ma(self, day, n):
        k = self.at(day)
        if k is None or k < n:
            return None
        return (self.c[k] / (sum(self.c[k - n + 1:k + 1]) / n) - 1) * 100


def prior_max(cl, n=250):
    """pm[i] = max(cl[i-n:i])（單調佇列，O(N)）"""
    from collections import deque
    q, pm = deque(), [None] * len(cl)
    for i in range(len(cl)):
        while q and q[0] <= i - n - 1:
            q.popleft()
        pm[i] = cl[q[0]] if q and i >= n else None
        while q and cl[q[-1]] <= cl[i]:
            q.pop()
        q.append(i)
    return pm


def main():
    px, mk = nh.load()
    sec = nh.sector_map()
    feats, top = nh.build(px)
    mkt = nh.twii()
    td, tc = series("_TWII")
    ti = {d: i for i, d in enumerate(td)}
    vix, hyg, lqd, spx, sox = Prev("_VIX"), Prev("HYG"), Prev("LQD"), Prev("_GSPC"), Prev("_SOX")
    dxy, twd, tnx = Prev("DX-Y.NYB"), Prev("TWD=X"), Prev("_TNX")
    # 信用風險偏好：HYG/LQD 比值對 50 日線
    hl_d = sorted(set(hyg.d) & set(lqd.d))
    hd, ld = dict(zip(hyg.d, hyg.c)), dict(zip(lqd.d, lqd.c))
    hl = Prev.__new__(Prev)
    hl.d, hl.c = hl_d, [hd[d] / ld[d] for d in hl_d]
    # 全市場廣度：每天站上 20 日線比例、創一年新高家數；上市／上櫃平均 20 日漲幅
    above, newhi, otc20, tse20 = defaultdict(lambda: [0, 0]), defaultdict(int), defaultdict(list), defaultdict(list)
    for c, f in feats.items():
        cl = f["c"]
        f["pm"] = pm = prior_max(cl)
        s20 = sum(cl[:20])
        for i in range(250, len(cl)):
            s20 = sum(cl[i - 19:i + 1]) if i == 250 else s20 + cl[i] - cl[i - 20]
            if i in f["bad"]:
                continue
            d = f["d"][i]
            above[d][0] += cl[i] > s20 / 20
            above[d][1] += 1
            if cl[i] > pm[i]:
                newhi[d] += 1
            (otc20 if mk[c] else tse20)[d].append(cl[i] / cl[i - 20] - 1)
    # 突破事件（只看放量長紅；龍頭、大盤濾網都記下來）
    peers = defaultdict(list)
    for c, f in feats.items():
        s = sec.get(c)
        if s:
            for i in range(250, len(f["d"])):
                if c in top.get(f["d"][i], ()):
                    peers[(f["d"][i], s)].append((f["c"][i] / f["c"][i - 20] - 1, c))
    strong_days = defaultdict(int)
    events = []
    for c, f in feats.items():
        d, o, h, l, cl, v = f["d"], f["o"], f["h"], f["l"], f["c"], f["v"]
        pm = f["pm"]
        his = [k for k in range(250, len(d)) if cl[k] > pm[k]]
        for i in range(250, len(d) - HOLD - 2):
            prior = pm[i]
            if i in f["bad"] or c not in top.get(d[i], ()) or cl[i] <= prior or cl[i] <= nh.ma(cl, i, 120):
                continue
            chg = (cl[i] / cl[i - 1] - 1) * 100
            av20 = nh.ma(v, i - 1, 20)
            if not (chg >= 4 and av20 and v[i] >= 2 * av20):
                continue
            strong_days[d[i]] += 1
            s = sec.get(c)
            ps = peers.get((d[i], s)) if s else None
            # 距離上一次創一年新高幾天（往回找）
            kk = bisect_left(his, i) - 1
            gap = (i - his[kk]) if kk >= 0 and i >= 500 else (250 if i >= 500 else None)
            events.append({"c": c, "i": i, "d": d[i], "prior": prior, "leader": bool(ps) and max(ps)[1] == c, "mkt": mkt.get(d[i]),
                           "chg": chg, "volX": v[i] / av20, "pre20": (cl[i - 1] / cl[i - 21] - 1) * 100, "brk": (cl[i] / prior - 1) * 100,
                           "gap": gap, "shadow": (h[i] - cl[i]) / (h[i] - l[i]) if h[i] > l[i] else 0, "ext120": (cl[i] / nh.ma(cl, i, 120) - 1) * 100,
                           "sector": s or ""})
    # 買點
    trades, seen = [], set()
    for e in sorted(events, key=lambda e: e["d"]):
        f = feats[e["c"]]
        o, cl, i = f["o"], f["c"], e["i"]
        for k in (1, 2, 3):
            b = i + k
            if b in f["bad"] or cl[b] < e["prior"]:
                break
            m5 = nh.ma(cl, b, 5)
            if (cl[b] <= o[b] or abs(cl[b] / o[b] - 1) <= 0.003) and m5 and cl[b] > m5:
                key = (e["c"], b, e["leader"], e["mkt"])
                if key in seen:
                    break
                seen.add(key)
                bd = f["d"][b]
                r = (cl[b + HOLD] / cl[b] - 1) * 100 - COST
                rn = (cl[b + HOLD + 1] / o[b + 1] - 1) * 100 - COST if b + HOLD + 1 < len(cl) else None
                j = ti.get(bd)
                tw = {}
                if j is not None and j >= 250:
                    tw = {"tw_ma60": (tc[j] / (sum(tc[j - 59:j + 1]) / 60) - 1) * 100, "tw_ret20": (tc[j] / tc[j - 20] - 1) * 100,
                          "tw_dd": (tc[j] / max(tc[j - 250:j + 1]) - 1) * 100}
                ab = above.get(bd)
                ot, ts = otc20.get(bd), tse20.get(bd)
                tech = any(x in e["sector"] for x in TECH)
                strong5 = sum(strong_days.get(x, 0) for x in f["d"][max(0, b - 4):b + 1])
                trades.append({**{x: e[x] for x in ("c", "d", "leader", "mkt", "chg", "volX", "pre20", "brk", "gap", "shadow", "ext120")},
                               "buy": bd, "r": r, "rn": rn, "k": k, "pbDrop": (cl[b] / cl[b - 1] - 1) * 100, "otc": mk[e["c"]], "tech": tech, **tw,
                               "vix": vix.val(bd), "vix5": vix.chg(bd, 5), "credit": hl.vs_ma(bd, 50),
                               "spx_ma50": spx.vs_ma(bd, 50), "spx20": spx.chg(bd, 20), "sox_ma50": sox.vs_ma(bd, 50), "sox20": sox.chg(bd, 20),
                               "intl": (sox.vs_ma(bd, 50) if tech else spx.vs_ma(bd, 50)),
                               "dxy20": dxy.chg(bd, 20), "twd20": twd.chg(bd, 20), "tnx20": tnx.chg(bd, 20),
                               "breadth": ab[0] / ab[1] * 100 if ab and ab[1] else None, "newhi": newhi.get(bd, 0),
                               "strong5": strong5, "otc_tse": (st.mean(ot) - st.mean(ts)) * 100 if ot and ts else None})
                break
    # 三大法人（外資＋投信）：突破日到買點合計買超，佔這段期間成交量的 %（data/research/new_high_inst.json，fetch_t86_hist.py）
    try:
        inst = json.loads((DATA / "research" / "new_high_inst.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        inst = {}
    for t in trades:
        f = feats[t["c"]]
        ds = f["d"][f["idx"][t["d"]]:f["idx"][t["buy"]] + 1]
        xs = [inst.get(x, {}).get(t["c"], "缺") for x in ds]
        if any(x == "缺" or x is None for x in xs):
            continue
        vol = sum(f["v"][f["idx"][x]] for x in ds) or 1
        t["inst"] = sum(a + b for a, b in xs) / vol * 100
        t["trust"] = sum(b for _, b in xs) / vol * 100
        t["foreign"] = sum(a for a, _ in xs) / vol * 100
    print(f"有法人資料的買點：{sum('inst' in t for t in trades)}／{len(trades)}")
    base = [t for t in trades if t["leader"] and t["mkt"]]
    print(f"影片完整版買點 {len(base)} 筆（不限大盤／龍頭的放量突破買點共 {len(trades)} 筆）；拿 {HOLD} 天、收盤買、已扣 {COST}%")

    def part(ts, a, b):
        return [t for t in ts if a <= t["buy"] < b]

    def stat(ts, key="r"):
        xs = [t[key] for t in ts if t.get(key) is not None]
        return (round(st.mean(xs), 2), len(xs)) if len(xs) >= 15 else (None, len(xs))

    allp = [stat(part(base, a, b)) for _, a, b in PARTS]
    print("全部（基準）     " + "｜".join(f"{n}: {m:+.2f}%（{k}）" for (n, _, _), (m, k) in zip(PARTS, allp)))
    FACTORS = [
        ("tw_ma60", "加權指數離 60 日線 %"), ("tw_ret20", "加權指數 20 日漲跌 %"), ("tw_dd", "加權指數離一年高點 %"),
        ("vix", "VIX（前一晚）"), ("vix5", "VIX 5 日變化 %"), ("credit", "HYG/LQD 對 50 日線 %（信用風險偏好）"),
        ("spx_ma50", "S&P 500 離 50 日線 %"), ("spx20", "S&P 500 20 日漲跌 %"), ("sox_ma50", "費半離 50 日線 %"), ("sox20", "費半 20 日漲跌 %"),
        ("intl", "國際同類（電子看費半、其他看 S&P）離 50 日線 %"),
        ("dxy20", "美元指數 20 日變化 %"), ("twd20", "美元兌台幣 20 日變化 %（正＝台幣貶）"), ("tnx20", "美債 10 年殖利率 20 日變化 %"),
        ("breadth", "全市場站上 20 日線比例 %"), ("newhi", "當天創一年新高家數"), ("strong5", "近 5 天放量突破家數（前 50 名）"),
        ("otc_tse", "上櫃減上市 20 日平均漲幅 %"), ("otc", "上櫃（1）／上市（0）"),
        ("chg", "突破日漲幅 %"), ("volX", "突破日量倍數"), ("pre20", "突破前 20 天漲幅 %"), ("brk", "突破幅度（離前高）%"),
        ("gap", "距上次創一年新高天數"), ("shadow", "突破日上影線比例"), ("ext120", "離 120 日線 %"),
        ("pbDrop", "買點當天漲跌 %"), ("k", "買點是突破後第幾天"),
        ("inst", "外資＋投信買超佔成交量 %（突破到買點）"), ("foreign", "外資買超佔成交量 %"), ("trust", "投信買超佔成交量 %"),
    ]
    out = {"n": len(base), "base": allp, "factors": {}}
    stable = []
    print("\n因子（三等份門檻用 2012-18 定）：低／中／高 三組在三段的平均報酬；✓＝三段都同方向（高組 > 低組或相反）")
    for key, lab in FACTORS:
        tr = sorted(t[key] for t in part(base, "2012", "2019") if t.get(key) is not None)
        if len(tr) < 60:
            continue
        if key in ("otc", "k"):
            cuts = (0.5, 1.5) if key == "otc" else (1.5, 2.5)
        else:
            cuts = (tr[len(tr) // 3], tr[2 * len(tr) // 3])
        grp = lambda t, ct=cuts, kk=key: None if t.get(kk) is None else (0 if t[kk] < ct[0] else 1 if t[kk] < ct[1] else 2)  # noqa: E731
        rows = []
        for _, a, b in PARTS:
            ps = part(base, a, b)
            rows.append([stat([t for t in ps if grp(t) == g]) for g in range(3)])
        diffs = [r[2][0] - r[0][0] if r[2][0] is not None and r[0][0] is not None else None for r in rows]
        ok = all(x is not None for x in diffs) and (all(x > 0.5 for x in diffs) or all(x < -0.5 for x in diffs))
        out["factors"][key] = {"label": lab, "cuts": [round(x, 3) for x in cuts], "rows": rows, "diff": diffs, "stable": ok}
        cs = f"{cuts[0]:.2f}/{cuts[1]:.2f}"
        print(f"{'✓' if ok else ' '} {lab}（門檻 {cs}）")
        for (n, _, _), r, dfx in zip(PARTS, rows, diffs):
            print(f"     {n:8s} " + "  ".join(f"{('低', '中', '高')[g]} {m:+5.2f}%（{k:3d}）" if m is not None else f"{('低', '中', '高')[g]}   — （{k:3d}）"
                                          for g, (m, k) in enumerate(r)) + (f"  高−低 {dfx:+.2f}" if dfx is not None else ""))
        if ok:
            stable.append((key, cuts, 1 if diffs[0] > 0 else -1, lab))
    # 大盤濾網的替代：不加 MA60，改用其他風險指標，看哪個最好（龍頭、放量突破的全部買點）
    print("\n大盤濾網比較（龍頭＋放量突破，不同的「可以做」條件）：")
    lead = [t for t in trades if t["leader"]]
    filt = [("不加濾網", lambda t: True), ("加權 > MA60（影片版）", lambda t: t["mkt"]),
            ("加權 > MA60 且 VIX < 25", lambda t: t["mkt"] and (t["vix"] or 99) < 25),
            ("加權 > MA60 且 HYG/LQD > 50 日線", lambda t: t["mkt"] and (t["credit"] or -1) > 0),
            ("加權 > MA60 且費半 > 50 日線", lambda t: t["mkt"] and (t["sox_ma50"] or -1) > 0),
            ("加權 > MA60 且廣度 > 50%", lambda t: t["mkt"] and (t["breadth"] or 0) > 50),
            ("VIX < 20（不看加權）", lambda t: (t["vix"] or 99) < 20)]
    out["filters"] = {}
    for lab, fn in filt:
        r = [stat(part([t for t in lead if fn(t)], a, b)) for _, a, b in PARTS]
        out["filters"][lab] = r
        print(f"  {lab:28s} " + "｜".join(f"{n}: {m:+.2f}%（{k}）" if m is not None else f"{n}: —（{k}）" for (n, _, _), (m, k) in zip(PARTS, r)))
    # 穩定因子組合：每個穩定因子「落在差的那一組」扣 1 分，0 分＝都不在差組
    print(f"\n穩定因子 {len(stable)} 個：{[s[3] for s in stable]}")
    if stable:
        def bad(t):
            n = 0
            for key, cuts, sgn, _ in stable:
                x = t.get(key)
                if x is None:
                    continue
                if (sgn > 0 and x < cuts[0]) or (sgn < 0 and x >= cuts[1]):
                    n += 1
            return n
        out["combo"] = {}
        for lab, fn in (("基準", lambda t: True), ("沒有落在任何差組", lambda t: bad(t) == 0), ("最多 1 個差組", lambda t: bad(t) <= 1),
                        ("2 個以上差組", lambda t: bad(t) >= 2)):
            r = [stat(part([t for t in base if fn(t)], a, b)) for _, a, b in PARTS]
            rn = [stat(part([t for t in base if fn(t)], a, b), "rn") for _, a, b in PARTS]
            out["combo"][lab] = {"close": r, "nextOpen": rn}
            print(f"  {lab:14s} 收盤買 " + "｜".join(f"{n}: {m:+.2f}%（{k}）" if m is not None else f"{n}: —（{k}）" for (n, _, _), (m, k) in zip(PARTS, r))
                  + "  隔天開盤買 " + "｜".join(f"{m:+.2f}%" if m is not None else "—" for m, _ in rn))
    # 嚴格檢查 1：逐年「好組 − 差組」，以及以月為單位的 t 值（同一個月的交易高度相關，不能當獨立樣本）
    print("\n逐年檢查（好組 − 差組，%；t 值用每月平均差算）：")
    out["yearly"] = {}
    for key, cuts, sgn, lab in stable:
        ys, mon = {}, defaultdict(lambda: [[], []])
        for t in base:
            x = t.get(key)
            if x is None:
                continue
            g = 1 if (x >= cuts[1] if sgn > 0 else x < cuts[0]) else 0 if (x < cuts[0] if sgn > 0 else x >= cuts[1]) else None
            if g is None:
                continue
            mon[t["buy"][:7]][g].append(t["r"])
        yd = defaultdict(list)
        diffs = []
        for m_, (bad_, good) in sorted(mon.items()):
            if bad_ and good:
                dd = st.mean(good) - st.mean(bad_)
                diffs.append(dd)
                yd[m_[:4]].append(dd)
        ys = {y: round(st.mean(v), 1) for y, v in sorted(yd.items())}
        tv = st.mean(diffs) / (st.stdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 2 else 0
        pos = sum(v > 0 for v in ys.values())
        out["yearly"][key] = {"years": ys, "t": round(tv, 2), "months": len(diffs)}
        print(f"  {lab}：t={tv:.2f}（{len(diffs)} 個月同時有好壞兩組）・{pos}/{len(ys)} 年好組較好・{ys}")
    # 因子之間的相關
    keys = [k for k, *_ in stable]
    print("\n穩定因子相關係數：")
    for i_, a_ in enumerate(keys):
        for b_ in keys[i_ + 1:]:
            pr = [(t[a_], t[b_]) for t in base if t.get(a_) is not None and t.get(b_) is not None]
            xa, xb = [p_[0] for p_ in pr], [p_[1] for p_ in pr]
            ma_, mb_ = st.mean(xa), st.mean(xb)
            cv = sum((p_[0] - ma_) * (p_[1] - mb_) for p_ in pr) / len(pr)
            print(f"  {a_} × {b_}：{cv / (st.pstdev(xa) * st.pstdev(xb)):+.2f}")
    # 嚴格檢查 2：只用 2012-18 挑因子（高低組差 ≥ 1% 且月 t ≥ 2），拿去 2019 後驗證
    print("\n只用 2012-18 挑因子 → 2019 後驗證：")
    pick = []
    for key, lab in FACTORS:
        fx = out["factors"].get(key)
        if not fx or key in ("otc", "k", "gap", "shadow"):
            continue
        cuts = fx["cuts"]
        d0 = fx["diff"][0]
        if d0 is None or abs(d0) < 1:
            continue
        sgn = 1 if d0 > 0 else -1
        mon = defaultdict(lambda: [[], []])
        for t in part(base, "2012", "2019"):
            x = t.get(key)
            if x is None:
                continue
            g = 1 if (x >= cuts[1] if sgn > 0 else x < cuts[0]) else 0 if (x < cuts[0] if sgn > 0 else x >= cuts[1]) else None
            if g is not None:
                mon[t["buy"][:7]][g].append(t["r"])
        diffs = [st.mean(gd) - st.mean(bd_) for bd_, gd in mon.values() if bd_ and gd]
        tv = st.mean(diffs) / (st.stdev(diffs) / len(diffs) ** 0.5) if len(diffs) > 2 else 0
        later = fx["diff"][1:]
        print(f"  {'選' if tv >= 2 else '  '} {lab}：2012-18 差 {d0:+.2f}（t={tv:.2f}）→ 2019-22 {later[0] if later[0] is None else f'{later[0]:+.2f}'}、"
              f"2023- {later[1] if later[1] is None else f'{later[1]:+.2f}'}" + ("（方向相同）" if tv >= 2 and all(x is not None and x * sgn > 0 for x in later) else ""))
        if tv >= 2:
            pick.append((key, cuts, sgn, lab))
    if pick:
        def bad2(t):
            return sum(1 for key, cuts, sgn, _ in pick if t.get(key) is not None and ((sgn > 0 and t[key] < cuts[0]) or (sgn < 0 and t[key] >= cuts[1])))
        out["walkForward"] = {"picked": [p_[3] for p_ in pick]}
        for lab, fn in (("基準", lambda t: True), ("沒有落在差組", lambda t: bad2(t) == 0), ("有落在差組", lambda t: bad2(t) > 0)):
            r = [stat(part([t for t in base if fn(t)], a, b)) for _, a, b in PARTS]
            out["walkForward"][lab] = r
            print(f"  {lab:10s} " + "｜".join(f"{n}: {m:+.2f}%（{k}）" if m is not None else f"{n}: —（{k}）" for (n, _, _), (m, k) in zip(PARTS, r)))
    (DATA / "research" / "new_high_factors.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
