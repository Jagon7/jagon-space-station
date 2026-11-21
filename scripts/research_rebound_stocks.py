#!/usr/bin/env python3
"""
抄底個股研究：大回檔低點之後，哪些股票反彈最強？為什麼？

資料：scripts/fetch_rebound_data.py 抓的證交所個股行情與籌碼（2012 起台股跌幅 ≥ 15% 的回檔）
每一波以加權低點日 T 收盤為基準（事後才知道是低點；另外算 T+5 進場，代表「確認止跌後才進場」）
母體：上市普通股，T 日成交金額 ≥ 5000 萬
報酬：R5、R20、R60（T 收盤 → T+n 收盤）、L20（T+5 → T+20，晚一點進場）
特徵（T 日當時可知）：
  跌幅       波段高點 → T 的個股跌幅；相對大盤（beta 概念）
  外資／投信／自營  T−9～T 這 10 天買賣超 ÷ 這 10 天成交量（籌碼）
  融資增減   波段高點 → T 融資餘額變化（散戶去槓桿）；融資使用率＝融資餘額 ÷ 發行股數（散戶多寡；用當時的發行股數，證交所 MI_QFIIS）
  外資持股比率（T 日）
  市值、股價、成交金額、低點前 5 天跌幅（急殺）
  產業（目前分類）、有沒有個股期貨（目前清單）
  T+1～T+5 外資／投信買賣超（止跌後誰先進場）→ 用來解釋 L20
方法：每一波內把股票依特徵分五組，看最高組 − 最低組的反彈差；看各波方向是否一致（越一致越可信）
輸出 data/research/rebound_stocks.json
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
R = DATA / "research" / "rebound"


_LINES: dict = {}


def lines_at(code: str, d: str):
    """個股在 d 收盤時離各條線多遠（%）：生命線（今年 VWAP）、252 日 VWAP、季線、半年線、年線（Yahoo 日線，data/research/yahoo_stocks）"""
    if code not in _LINES:
        p = DATA / "research" / "yahoo_stocks" / f"{code}.json"
        try:
            rows = [r for r in json.loads(p.read_text(encoding="utf-8"))["d"] if r[4] and r[2] and r[3]]
        except (OSError, ValueError):
            rows = []
        _LINES[code] = rows
    rows = _LINES[code]
    i = next((k for k in range(len(rows) - 1, -1, -1) if rows[k][0] <= d), None)
    if i is None or rows[i][0] != d:  # 當天沒有 Yahoo 資料（停牌等）
        return {}
    c = rows[i][4]
    tp = lambda r: (r[2] + r[3] + r[4]) / 3 * (r[5] or 0)  # noqa: E731
    ytd = [r for r in rows[:i + 1] if r[0][:4] == d[:4]]
    out = {}
    if len(ytd) >= 20 and sum(r[5] or 0 for r in ytd):
        out["lifeDist"] = (c / (sum(tp(r) for r in ytd) / sum(r[5] or 0 for r in ytd)) - 1) * 100
    if i >= 251:
        w = rows[i - 251:i + 1]
        vv = sum(r[5] or 0 for r in w)
        if vv:
            out["life252Dist"] = (c / (sum(tp(r) for r in w) / vv) - 1) * 100
    for n in (60, 120, 240):
        if i >= n - 1:
            out[f"ma{n}Dist"] = (c / st.mean(r[4] for r in rows[i - n + 1:i + 1]) - 1) * 100
    return out


def load(kind, d):
    p = R / f"{kind}_{d.replace('-', '')}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    eps = json.loads((R / "episodes.json").read_text(encoding="utf-8"))
    tw = [r[0] for r in json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]]
    twc = {r[0]: r[4] for r in json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]}
    shares = (json.loads((DATA / "strategy" / "shares.json").read_text(encoding="utf-8")) or {}).get("shares", {})
    sec = {}
    for name, rows in (json.loads((DATA / "sector-stocks.json").read_text(encoding="utf-8")).get("data") or {}).items():
        for r in rows:
            sec.setdefault(r["code"], name)
    ssf = {v[0] for v in (json.loads((DATA / "settlement" / "contracts.json").read_text(encoding="utf-8")).get("contracts") or {}).values()}
    allrows = []
    for e in eps:
        T = e["trough"]
        t = tw.index(T)
        pre = [tw[k] for k in range(t - 9, t + 1)]
        post = [tw[k] for k in range(t + 1, t + 6) if k < len(tw)]
        qT, qP = load("q", T), load("q", e["peak"])
        if not qT or not qP:
            print(f"{T} 資料不齊，略過")
            continue
        qn = {n: load("q", tw[t + n]) if t + n < len(tw) else {} for n in (5, 20, 60)}
        q5b = load("q", tw[t - 5])
        qd = {d: load("q", d) for d in pre}
        td = {d: load("t", d) for d in pre + post}
        mP, mT, fT = load("m", e["peak"]), load("m", T), load("f", T)
        idx_drop = (twc[T] / twc[e["peak"]] - 1) * 100
        n_ok = 0
        for c, v in qT.items():
            if not (len(c) == 4 and c.isdigit() and c[0] != "0") or not v[1] or not v[3] or v[3] < 5e7 or c not in qP or not qP[c][1]:
                continue
            px = v[1]
            r = {"ep": T, "code": c, "name": v[0], "sector": sec.get(c, "其他"), "ssf": c in ssf, "px": px, "value": v[3] / 1e8}
            for n in (5, 20, 60):
                x = (qn[n].get(c) or [None, None])[1]
                r[f"r{n}"] = (x / px - 1) * 100 if x else None
            x5, x20 = (qn[5].get(c) or [None, None])[1], (qn[20].get(c) or [None, None])[1]
            r["l20"] = (x20 / x5 - 1) * 100 if x5 and x20 else None
            r["drop"] = (px / qP[c][1] - 1) * 100
            r["relDrop"] = r["drop"] - idx_drop
            r["beta"] = r["drop"] / idx_drop if idx_drop else None
            b5 = (q5b.get(c) or [None, None])[1]
            r["last5"] = (px / b5 - 1) * 100 if b5 else None
            vol10 = sum((qd[d].get(c) or [None, None, 0])[2] or 0 for d in pre)
            for k, lab in ((0, "fgn"), (1, "trust"), (2, "dealer")):
                net = sum(((td[d].get(c) or [0, 0, 0])[k] or 0) for d in pre)
                r[f"{lab}10"] = net / vol10 * 100 if vol10 else None
                netp = sum(((td[d].get(c) or [0, 0, 0])[k] or 0) for d in post)
                r[f"{lab}Post5"] = netp / vol10 * 100 if vol10 else None
            mp, mt = (mP.get(c) or [None])[0], (mT.get(c) or [None])[0]
            r["marginChg"] = (mt / mp - 1) * 100 if mp and mt and mp > 50 else None
            fv = fT.get(c)
            fv = fv if isinstance(fv, list) else [fv, None]  # [外資持股%, 當時發行股數]
            sh_c = fv[1] or shares.get(c)  # 用當時的發行股數（證交所 MI_QFIIS）；沒有才用目前股數
            r["fgnHold"] = fv[0]
            r["marginUse"] = mt * 1000 / sh_c * 100 if mt is not None and sh_c else None
            r["mcap"] = px * sh_c / 1e8 if sh_c else None
            r.update(lines_at(c, T))
            allrows.append(r)
            n_ok += 1
        print(f"{T}（大盤 {idx_drop:.1f}%）：{n_ok} 檔")
    feats = [("drop", "個股跌幅（越負＝跌越深）"), ("relDrop", "相對大盤跌幅"), ("beta", "跌幅 ÷ 大盤跌幅"), ("last5", "低點前 5 天跌幅（急殺）"),
             ("fgn10", "低點前 10 天外資買賣超 ÷ 成交量"), ("trust10", "低點前 10 天投信買賣超 ÷ 成交量"), ("dealer10", "低點前 10 天自營商買賣超 ÷ 成交量"),
             ("marginChg", "融資增減（高點→低點，越負＝散戶砍越多）"), ("marginUse", "融資使用率（融資 ÷ 股本，散戶槓桿多寡）"),
             ("fgnHold", "外資持股比率"), ("mcap", "市值"), ("px", "股價"), ("value", "低點當天成交金額"),
             ("fgnPost5", "低點後 5 天外資買賣超（止跌後誰進場）"), ("trustPost5", "低點後 5 天投信買賣超"),
             ("lifeDist", "離生命線（今年成本 VWAP）%"), ("life252Dist", "離過去一年成本（252 日 VWAP）%"),
             ("ma60Dist", "離季線 %"), ("ma120Dist", "離半年線 %"), ("ma240Dist", "離年線 %")]
    # 只列已經過完 20 個交易日、有 T+20 行情的波段（還在進行中的回檔，低點可能還沒到，不能當成一次「低點」）
    done = {T for T in {r["ep"] for r in allrows} if any(r.get("r20") is not None for r in allrows if r["ep"] == T)}
    out = {"episodes": [e for e in eps if e["trough"] in done], "features": {}, "sectors": {}, "ssf": {}, "top": {},
           "pending": [e["trough"] for e in eps if e["trough"] not in done]}
    for k, lab in feats:
        res = {"label": lab, "eps": {}}
        for tgt in ("r20", "r60", "l20"):
            spreads = []
            for T in sorted({r["ep"] for r in allrows}):
                rs = sorted([r for r in allrows if r["ep"] == T and r.get(k) is not None and r.get(tgt) is not None], key=lambda r: r[k])
                if len(rs) < 50:
                    continue
                n = len(rs) // 5
                lo, hi = st.mean(r[tgt] for r in rs[:n]), st.mean(r[tgt] for r in rs[-n:])
                spreads.append((T, round(hi - lo, 2), round(lo, 2), round(hi, 2)))
            if spreads:
                res[tgt] = {"avg": round(st.mean(s[1] for s in spreads), 2), "pos": sum(1 for s in spreads if s[1] > 0), "n": len(spreads),
                            "lo": round(st.mean(s[2] for s in spreads), 2), "hi": round(st.mean(s[3] for s in spreads), 2), "by": spreads}
        # 控制跌幅：每一波先依個股跌幅分三組，組內再依特徵分高低兩半比較（排除「跌越深彈越多」的影響）
        diffs = []
        for T in sorted({r["ep"] for r in allrows}):
            rs = sorted([r for r in allrows if r["ep"] == T and r.get(k) is not None and r.get("r20") is not None], key=lambda r: r["drop"])
            n3 = len(rs) // 3
            for g in (rs[:n3], rs[n3:2 * n3], rs[2 * n3:]):
                g = sorted(g, key=lambda r: r[k])
                h = len(g) // 2
                if h >= 10:
                    diffs.append(st.mean(r["r20"] for r in g[h:]) - st.mean(r["r20"] for r in g[:h]))
        if diffs and k not in ("drop", "relDrop", "beta"):
            res["ctrl"] = {"avg": round(st.mean(diffs), 2), "pos": sum(1 for x in diffs if x > 0), "n": len(diffs)}
        if "r20" not in res:  # 沒有資料（例如 GitHub 上沒有個股日線）：沿用上次的結果
            try:
                old = json.loads((DATA / "research" / "rebound_stocks.json").read_text(encoding="utf-8"))["features"].get(k)
            except (OSError, ValueError, KeyError):
                old = None
            if old:
                out["features"][k] = old
            continue
        out["features"][k] = res
    # 產業
    by = {}
    for r in allrows:
        if r.get("r20") is None:
            continue
        by.setdefault(r["sector"], []).append(r)
    for s, rs in by.items():
        eps_rel = []
        for T in {r["ep"] for r in rs}:
            mkt = st.mean(x["r20"] for x in allrows if x["ep"] == T and x.get("r20") is not None)
            g = [r["r20"] for r in rs if r["ep"] == T]
            if len(g) >= 3:
                eps_rel.append(st.mean(g) - mkt)
        if len(eps_rel) >= 4:
            out["sectors"][s] = {"n": len(rs), "excess20": round(st.mean(eps_rel), 2), "pos": sum(1 for x in eps_rel if x > 0), "eps": len(eps_rel)}
    # 有沒有個股期
    for flag in (True, False):
        rs = [r for r in allrows if r["ssf"] == flag and r.get("r20") is not None]
        out["ssf"]["有個股期" if flag else "沒有個股期"] = {"n": len(rs), "r20": round(st.mean(r["r20"] for r in rs), 2), "r60": round(st.mean(r["r60"] for r in rs if r.get("r60") is not None), 2),
                                                        "win20": round(sum(r["r20"] > 0 for r in rs) / len(rs) * 100)}
    # 各波反彈前 15 名
    for T in sorted(done):
        rs = sorted([r for r in allrows if r["ep"] == T and r.get("r20") is not None], key=lambda r: -r["r20"])[:15]
        out["top"][T] = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k in ("code", "name", "sector", "ssf", "r20", "r60", "drop", "fgn10", "trust10", "marginChg", "marginUse", "fgnHold", "mcap")} for r in rs]
    # 重複上榜：各波前 10% 出現最多次的股票
    cnt = {}
    for T in sorted({r["ep"] for r in allrows}):
        rs = sorted([r for r in allrows if r["ep"] == T and r.get("r20") is not None], key=lambda r: -r["r20"])
        for r in rs[:max(1, len(rs) // 10)]:
            cnt.setdefault(r["code"], [r["name"], r["sector"], r["ssf"], 0])[3] += 1
    out["repeat"] = sorted([[c, *v] for c, v in cnt.items() if v[3] >= 3], key=lambda x: -x[4])[:30]
    # 現在的候選：近 60 個交易日從高點跌最深、融資使用率最高（兩者都在前 1/3），成交 ≥ 5000 萬；上櫃也列（研究只用上市驗證）
    days = sorted(p.stem for p in (DATA / "daily").glob("20*.json"))[-60:]
    dq = {d: (json.loads((DATA / "daily" / f"{d}.json").read_text(encoding="utf-8")) or {}) for d in days}
    last = dq[days[-1]]
    cands = []
    for c, v in (last.get("q") or {}).items():
        if not (len(c) == 4 and c.isdigit() and c[0] != "0") or not v[5] or (v[8] or 0) < 5e7 or not shares.get(c):
            continue
        hi = max(((dq[d].get("q") or {}).get(c) or [0] * 6)[5] or 0 for d in days)
        mg = ((last.get("m") or {}).get(c) or [None])[0]
        if not hi or mg is None:
            continue
        cands.append({"code": c, "name": v[0], "mk": "上櫃" if v[1] else "上市", "sector": sec.get(c, "其他"), "ssf": c in ssf, "close": v[5],
                      "drop": round((v[5] / hi - 1) * 100, 1), "marginUse": round(mg * 1000 / shares[c] * 100, 2), "value": round(v[8] / 1e8, 1)})
    if cands:
        d3 = sorted(x["drop"] for x in cands)[len(cands) // 3]
        m3 = sorted(x["marginUse"] for x in cands)[len(cands) * 2 // 3]
        pick = [x for x in cands if x["drop"] <= d3 and x["marginUse"] >= m3]
        good = {k for k, v in out["sectors"].items() if v["excess20"] > 0 and v["pos"] >= v["eps"] * 0.6}
        for x in pick:
            x["goodSector"] = x["sector"] in good
        out["now"] = {"date": days[-1], "cut": {"drop": d3, "marginUse": m3},
                      "list": sorted(pick, key=lambda x: (not x["goodSector"], not x["ssf"], x["drop"]))[:60]}
        print(f"\n現在候選（{days[-1]}，跌幅 ≤ {d3}%、融資使用率 ≥ {m3}%）：{len(pick)} 檔，例如",
              "、".join(f"{x['name']}{x['code']}（{x['drop']}%／{x['marginUse']}%）" for x in out["now"]["list"][:12]))
    (DATA / "research" / "rebound_stocks.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("\n特徵：最高 1/5 − 最低 1/5 的反彈差（R20 低點起 20 天／L20 T+5 起 15 天／R60）；後面是各波方向一致的次數")
    for k, v in out["features"].items():
        a, b, c = v.get("r20", {}), v.get("l20", {}), v.get("r60", {})
        print(f"  {v['label']:34s} R20 {a.get('avg', 0):+6.2f}（{a.get('pos')}/{a.get('n')}）  L20 {b.get('avg', 0):+6.2f}（{b.get('pos')}/{b.get('n')}）  R60 {c.get('avg', 0):+6.2f}（{c.get('pos')}/{c.get('n')}）")
    print("\n產業：20 天超額報酬（平均、贏大盤的次數）")
    for s, v in sorted(out["sectors"].items(), key=lambda x: -x[1]["excess20"]):
        print(f"  {s:8s} {v['excess20']:+6.2f}%（{v['pos']}/{v['eps']} 波）n={v['n']}")
    print("\n個股期", out["ssf"])
    print("\n多次上榜（各波反彈前 10%）", out["repeat"][:20])
    return 0


if __name__ == "__main__":
    sys.exit(main())
