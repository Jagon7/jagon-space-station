#!/usr/bin/env python3
"""
搶反彈選股：「主動式 ETF 已經賣光」＋「融資少（散戶已斷頭）」的股票，是不是更容易反彈？

資料：主動式 ETF 每日持股（data/etf/holdings/*A.json，2026/5 起）、每日行情與融資（data/daily）、發行股數（data/strategy/shares.json）
回檔：2026 年加權跌幅 ≥ 15% 的兩波——6/22→7/30（−16.4%）、10/06→11/06（−20.3%，到現在只過了 10 個交易日，只看 10 天）
  只用「波段高點那天已經上市」的主動式 ETF（之後才上市的會一直買進，干擾判斷）
每檔股票（上市櫃普通股，低點當天成交 ≥ 5000 萬）：
  主動式 ETF 持股：高點 → 低點的股數變化
    從沒持有／全部賣光（高點有、低點 0）／砍一半以上／還抱著（砍不到一半或加碼）
  融資：低點融資 ÷ 股本（融資使用率）、高點 → 低點融資增減 %
  個股跌幅（高點 → 低點收盤）
結果：低點收盤 → 10 天、20 天後報酬；並在「跌幅相近」（三等分）的股票裡比較，排除跌越深彈越多
輸出 data/research/rebound_active.json；用法：python scripts/research_rebound_active.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
EPS = [("2026-06-22", "2026-07-30"), ("2026-10-06", "2026-11-06")]


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main():
    days = sorted(p.stem for p in (DATA / "daily").glob("20*.json"))
    dq = {}

    def q(d):
        if d not in dq:
            dq[d] = load(DATA / "daily" / f"{d}.json", {}) or {}
        return dq[d]

    shares = (load(DATA / "strategy" / "shares.json", {}) or {}).get("shares", {})
    etfs = []
    for f in sorted((DATA / "etf" / "holdings").glob("*A.json")):
        j = load(f, {}) or {}
        snaps = sorted(j.get("snapshots") or [], key=lambda s: s["date"])
        if snaps:
            etfs.append((j.get("code"), snaps))

    def held(snaps, d):
        s = [x for x in snaps if x["date"] <= d]
        return {h[0]: h[2] or 0 for h in s[-1]["h"]} if s else None

    out = {"episodes": {}}
    allr = []
    for P, T in EPS:
        live = [(c, sn) for c, sn in etfs if sn[0]["date"] <= P]
        hP, hT = {}, {}
        for c, sn in live:
            for k, v in (held(sn, P) or {}).items():
                hP[k] = hP.get(k, 0) + v
            for k, v in (held(sn, T) or {}).items():
                hT[k] = hT.get(k, 0) + v
        ti = days.index(T)
        fut = {n: days[ti + n] for n in (5, 10, 20) if ti + n < len(days)}
        qP, qT = q(P), q(T)
        rows = []
        for c, v in (qT.get("q") or {}).items():
            if not (len(c) == 4 and c.isdigit() and c[0] != "0") or not v[5] or (v[8] or 0) < 5e7 or c not in (qP.get("q") or {}):
                continue
            pP = qP["q"][c][5]
            if not pP:
                continue
            r = {"ep": T, "code": c, "name": v[0], "drop": (v[5] / pP - 1) * 100}
            for n, d in fut.items():
                x = ((q(d).get("q") or {}).get(c) or [None] * 6)[5]
                r[f"r{n}"] = (x / v[5] - 1) * 100 if x else None
            a, b = hP.get(c, 0), hT.get(c, 0)
            r["aeP"], r["aeT"] = a, b
            r["ae"] = "從沒持有" if a == 0 and b == 0 else "全部賣光" if a > 0 and b == 0 else "砍一半以上" if a > 0 and b <= a * 0.5 else "還抱著" if a > 0 else "低點前新買進"
            r["aeShare"] = b / shares[c] * 100 if shares.get(c) else None
            mT = ((qT.get("m") or {}).get(c) or [None])[0]
            mP = ((qP.get("m") or {}).get(c) or [None])[0]
            r["marginUse"] = mT * 1000 / shares[c] * 100 if mT is not None and shares.get(c) else None
            r["marginChg"] = (mT / mP - 1) * 100 if mT is not None and mP and mP > 50 else None
            rows.append(r)
        allr += rows
        tgt = "r20" if "r20" in rows[0] else "r10"
        print(f"\n■ {P} → {T}：{len(rows)} 檔，高點時已上市的主動式 ETF {len(live)} 檔；看 {tgt}（低點收盤 → {tgt[1:]} 天後）")
        ep = {"P": P, "T": T, "etfs": len(live), "n": len(rows), "tgt": tgt, "groups": {}, "ctrl": {}, "margin": {}}
        # 依跌幅三等分（控制跌幅）
        srt = sorted(rows, key=lambda r: r["drop"])
        n3 = len(srt) // 3
        terc = {r["code"]: (0 if i < n3 else 1 if i < 2 * n3 else 2) for i, r in enumerate(srt)}
        base = st.mean(r[tgt] for r in rows if r.get(tgt) is not None)
        print(f"  全部平均 {base:+.1f}%")
        for g in ("從沒持有", "全部賣光", "砍一半以上", "還抱著", "低點前新買進"):
            s = [r for r in rows if r["ae"] == g and r.get(tgt) is not None]
            if len(s) < 5:
                continue
            # 控制跌幅：每組在各跌幅三等分內的平均，減掉該三等分的全體平均，再平均
            adj = []
            for t in (0, 1, 2):
                tt = [r[tgt] for r in rows if terc[r["code"]] == t and r.get(tgt) is not None]
                gg = [r[tgt] for r in s if terc[r["code"]] == t]
                if gg and tt:
                    adj += [x - st.mean(tt) for x in gg]
            o = {"n": len(s), "ret": round(st.mean(r[tgt] for r in s), 1), "win": round(sum(r[tgt] > 0 for r in s) / len(s) * 100),
                 "drop": round(st.mean(r["drop"] for r in s), 1), "adj": round(st.mean(adj), 1) if adj else None}
            ep["groups"][g] = o
            print(f"  主動式 ETF {g:6s} n{o['n']:4d} 平均 {o['ret']:+5.1f}%（勝率 {o['win']}%），個股跌幅 {o['drop']:+.1f}%，跌幅相近的比較 {o['adj']:+.1f}%")
        # 融資：使用率高低 × 高點→低點減少多寡（各取中位數切）
        mm = [r for r in rows if r.get("marginUse") is not None and r.get("marginChg") is not None and r.get(tgt) is not None]
        if len(mm) > 40:
            mu, mc = st.median(r["marginUse"] for r in mm), st.median(r["marginChg"] for r in mm)
            print(f"  融資（中位數：使用率 {mu:.2f}%、高點→低點 {mc:+.0f}%）：")
            for lab, f in (("融資多＋沒砍", lambda r: r["marginUse"] >= mu and r["marginChg"] >= mc), ("融資多＋砍很多", lambda r: r["marginUse"] >= mu and r["marginChg"] < mc),
                           ("融資少＋沒砍", lambda r: r["marginUse"] < mu and r["marginChg"] >= mc), ("融資少＋砍很多（已斷頭）", lambda r: r["marginUse"] < mu and r["marginChg"] < mc)):
                s = [r for r in mm if f(r)]
                adj = []
                for t in (0, 1, 2):
                    tt = [r[tgt] for r in mm if terc[r["code"]] == t]
                    adj += [r[tgt] - st.mean(tt) for r in s if terc[r["code"]] == t]
                o = {"n": len(s), "ret": round(st.mean(r[tgt] for r in s), 1), "drop": round(st.mean(r["drop"] for r in s), 1), "adj": round(st.mean(adj), 1)}
                ep["margin"][lab] = o
                print(f"    {lab:14s} n{o['n']:4d} 平均 {o['ret']:+5.1f}%，跌幅 {o['drop']:+.1f}%，跌幅相近的比較 {o['adj']:+.1f}%")
            # 使用者的組合：主動式 ETF 已賣光（或從沒持有）＋融資少
            print("  組合：")
            for lab, f in (("ETF 賣光＋融資少", lambda r: r["ae"] == "全部賣光" and r["marginUse"] < mu),
                           ("ETF 賣光＋融資多", lambda r: r["ae"] == "全部賣光" and r["marginUse"] >= mu),
                           ("ETF 還抱著＋融資少", lambda r: r["ae"] == "還抱著" and r["marginUse"] < mu),
                           ("ETF 還抱著＋融資多", lambda r: r["ae"] == "還抱著" and r["marginUse"] >= mu),
                           ("ETF 從沒持有＋融資多", lambda r: r["ae"] == "從沒持有" and r["marginUse"] >= mu)):
                s = [r for r in mm if f(r)]
                if len(s) < 5:
                    print(f"    {lab:14s} n{len(s)}（太少）")
                    continue
                adj = []
                for t in (0, 1, 2):
                    tt = [r[tgt] for r in mm if terc[r["code"]] == t]
                    adj += [r[tgt] - st.mean(tt) for r in s if terc[r["code"]] == t]
                o = {"n": len(s), "ret": round(st.mean(r[tgt] for r in s), 1), "adj": round(st.mean(adj), 1)}
                ep["margin"][lab] = o
                print(f"    {lab:14s} n{o['n']:4d} 平均 {o['ret']:+5.1f}%，跌幅相近的比較 {o['adj']:+.1f}%")
        out["episodes"][T] = ep
    # 長期驗證（2012 起 9 次 ≥15% 回檔，research_rebound_stocks 的個股特徵）：融資多寡 × 高點→低點融資砍多少、投信低點前 10 天賣超
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        dump = Path(td) / "rows.json"
        subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "research_rebound_stocks.py")], env={**os.environ, "REBOUND_DUMP": str(dump)},
                       check=False, capture_output=True)
        rows9 = [r for r in load(dump, []) if r.get("r20") is not None] if dump.exists() else []
    if rows9:
        eps9 = sorted({r["ep"] for r in rows9})
        med = {T: {k: st.median(r[k] for r in rows9 if r["ep"] == T and r.get(k) is not None) for k in ("marginUse", "marginChg", "trust10")} for T in eps9}
        print("\n■ 長期驗證：2012 起 9 次低點，跌幅相近的股票裡比較 20 天反彈（各波中位數切高低）")
        out["long"] = {}
        for lab, f in (("融資多＋沒砍", lambda r: r["marginUse"] >= med[r["ep"]]["marginUse"] and r["marginChg"] >= med[r["ep"]]["marginChg"]),
                       ("融資多＋砍很多", lambda r: r["marginUse"] >= med[r["ep"]]["marginUse"] and r["marginChg"] < med[r["ep"]]["marginChg"]),
                       ("融資少＋沒砍", lambda r: r["marginUse"] < med[r["ep"]]["marginUse"] and r["marginChg"] >= med[r["ep"]]["marginChg"]),
                       ("融資少＋砍很多（已斷頭）", lambda r: r["marginUse"] < med[r["ep"]]["marginUse"] and r["marginChg"] < med[r["ep"]]["marginChg"]),
                       ("投信低點前賣超", lambda r: r["trust10"] < med[r["ep"]]["trust10"]),
                       ("投信賣超＋融資少", lambda r: r["trust10"] < med[r["ep"]]["trust10"] and r["marginUse"] < med[r["ep"]]["marginUse"]),
                       ("投信賣超＋融資多", lambda r: r["trust10"] < med[r["ep"]]["trust10"] and r["marginUse"] >= med[r["ep"]]["marginUse"])):
            per = []
            for T in eps9:
                rs = sorted([r for r in rows9 if r["ep"] == T and None not in (r.get("marginUse"), r.get("marginChg"), r.get("trust10"))], key=lambda r: r["drop"])
                n3 = len(rs) // 3
                adj = []
                for g in (rs[:n3], rs[n3:2 * n3], rs[2 * n3:]):
                    m = st.mean(r["r20"] for r in g)
                    adj += [r["r20"] - m for r in g if f(r)]
                if adj:
                    per.append([T, round(st.mean(adj), 2), len(adj)])
            o = {"avg": round(st.mean(x[1] for x in per), 2), "pos": sum(x[1] > 0 for x in per), "n": len(per), "by": per}
            out["long"][lab] = o
            print(f"  {lab:14s} {o['avg']:+.1f}%（{o['pos']}/{o['n']} 波為正）")
    (DATA / "research" / "rebound_active.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
