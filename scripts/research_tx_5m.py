#!/usr/bin/env python3
"""
台指期日盤短打研究：① 每 N 分鐘一個區間、訊號同向續抱／反向就平倉反手（一直在場的 stop-and-reverse）
                    ② 晚一點判斷：開盤區間改成 08:45～10:00 再做 BO／MR

① 訊號（每根 N 分 K 收盤時判斷，下一根開盤進出；N＝1／3／5／10／15，主看 5）
  MOM   這根 K 收紅做多、收黑做空（動能）
  REV   反過來（這根收紅做空）：檢查是不是其實均值回歸比較好
  BRK   收盤突破前一根高點做多、跌破前一根低點做空，都沒有就維持原部位
  VWAP  收盤在當天 VWAP 上做多、下做空
  EMA   收盤在 6 根 EMA 上做多、下做空
  MOM2  連兩根同色才翻，否則維持
  另外：只在線上規則判定 BO 的日子做順勢訊號、MR 日做 REV
  進場從 09:00（第一根 N 分 K 收盤）開始，13:30 全部平倉；成本：每邊 1.5 點（一買一賣＝3 點，反手＝平倉＋新倉＝3 點）
①b VWAP 加帶寬：收盤要超過 VWAP ± k × ATR20 才翻向（k＝0～0.3），減少來回洗
② 10:00 判斷：OR＝08:45～10:00；BO＝之後第一次突破 OR 進場、停損 OR 另一側；MR＝10:00～10:15 第一次碰邊界逆勢、目標中點、
   停損 OR 外 0.5 寬度；13:30 出場；和 09:15 版本、線上規則比；也看「開低→MR、開高→BO」在 10:00 版本是否仍成立
三段：2020-22／2023-24／2025+；每筆扣 3 點
輸出 data/research/tx_5m.json；用法：python scripts/research_tx_5m.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_tx_regime as rr  # noqa: E402
import tx_regime_review as trv  # noqa: E402

SIDE = 1.5
PARTS = (("2020-22", "2020", "2023"), ("2023-24", "2023", "2025"), ("2025+", "2025", "2100"))
START, END = 15, 285   # 09:00、13:30（分鐘，08:45＝0）


def nbars(bars: dict, n: int):
    """1 分 K → N 分 K（從 08:45 起切），[(起始分, 開, 高, 低, 收, 量)]"""
    out = []
    for s in range(0, END, n):
        xs = [bars[m] for m in range(s, s + n) if m in bars]
        if xs:
            out.append((s, xs[0][0], max(x[1] for x in xs), min(x[2] for x in xs), xs[-1][3], sum(x[4] for x in xs)))
    return out


def run_sar(bars: dict, n: int, sig: str):
    """回傳（當天損益點數，交易次數）"""
    k = nbars(bars, n)
    pos, ent, pnl, trades = 0, 0.0, 0.0, 0
    pv = vol = 0.0
    ema = None
    alpha = 2 / (6 + 1)
    prev = None
    last_col = []
    want = 0
    for i, (s, o, h, lo, c, v) in enumerate(k):
        # 先在這根開盤執行上一根給的訊號（want 在上一輪迴圈算好）
        if i > 0 and want != pos and s < END:
            if pos:
                pnl += (o - ent) * pos - SIDE
            if want:
                ent = o
                pnl -= SIDE
                trades += 1
            pos = want
        pv += (h + lo + c) / 3 * v
        vol += v
        ema = c if ema is None else alpha * c + (1 - alpha) * ema
        col = 1 if c > o else -1 if c < o else 0
        last_col = (last_col + [col])[-2:]
        want = pos
        if s + n - 1 >= START:   # 09:00 之後的 K 棒才給訊號
            if sig == "MOM":
                want = col or pos
            elif sig == "REV":
                want = -col or pos
            elif sig == "BRK":
                if prev and c > prev[2]:
                    want = 1
                elif prev and c < prev[3]:
                    want = -1
            elif sig == "VWAP":
                want = 1 if vol and c > pv / vol else -1
            elif sig == "EMA":
                want = 1 if c > ema else -1
            elif sig == "MOM2":
                if len(last_col) == 2 and last_col[0] == last_col[1] != 0:
                    want = last_col[0]
        if s + n >= END:
            break
        prev = (s, o, h, lo, c)
    # 13:30 平倉
    if pos:
        last = bars.get(END) or bars[max(m for m in bars if m <= END)]
        pnl += (last[3] - ent) * pos - SIDE
    return pnl, trades


def run_vwap_band(bars: dict, n: int, band: float):
    k = nbars(bars, n)
    pos, ent, pnl, trades, want = 0, 0.0, 0.0, 0, 0
    pv = vol = 0.0
    for i, (s, o, h, lo, c, v) in enumerate(k):
        if i > 0 and want != pos:
            if pos:
                pnl += (o - ent) * pos - SIDE
            if want:
                ent = o
                pnl -= SIDE
                trades += 1
            pos = want
        pv += (h + lo + c) / 3 * v
        vol += v
        vw = pv / vol if vol else c
        if s + n - 1 >= START:
            if c > vw + band:
                want = 1
            elif c < vw - band:
                want = -1
        if s + n >= END:
            break
    if pos:
        last = bars.get(END) or bars[max(m for m in bars if m <= END)]
        pnl += (last[3] - ent) * pos - SIDE
    return pnl, trades


def or_trade(bars: dict, or_m: int, mr_win: int = 15):
    orb = [bars[m] for m in range(or_m) if m in bars]
    orh, orl = max(b[1] for b in orb), min(b[2] for b in orb)
    w, mid = orh - orl, (orh + orl) / 2
    bo = mr = None
    bpos = mpos = None
    last = None
    for m in range(or_m, END + 1):
        b = bars.get(m)
        if not b:
            continue
        o, h, lo, c = b[0], b[1], b[2], b[3]
        last = c
        if bo is None and bpos is None:
            if h > orh:
                bpos = (1, max(o, orh), orl)
            elif lo < orl:
                bpos = (-1, min(o, orl), orh)
        elif bo is None and bpos:
            d, e, sp = bpos
            if (d > 0 and lo <= sp) or (d < 0 and h >= sp):
                bo = (sp - e) * d
        if mr is None and mpos is None and m < or_m + mr_win:
            if h >= orh:
                mpos = (-1, max(o, orh), orh + 0.5 * w, mid)
            elif lo <= orl:
                mpos = (1, min(o, orl), orl - 0.5 * w, mid)
        elif mr is None and mpos:
            d, e, sp, tg = mpos
            if (d > 0 and lo <= sp) or (d < 0 and h >= sp):
                mr = (sp - e) * d
            elif (d > 0 and h >= tg) or (d < 0 and lo <= tg):
                mr = (tg - e) * d
    if bo is None and bpos and last is not None:
        bo = (last - bpos[1]) * bpos[0]
    if mr is None and mpos and last is not None:
        mr = (last - mpos[1]) * mpos[0]
    return (bo - rr.COST if bo is not None else 0.0), (mr - rr.COST if mr is not None else 0.0)


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    p = trv.params()["current"]
    dates = sorted(d for d, b in day.items() if len(b) >= 250 and d in reg)
    out = {"sar": {}, "or1000": {}}
    print(f"{dates[0]}～{dates[-1]}，{len(dates)} 天；每邊 {SIDE} 點")
    print("\n■ ① N 分鐘 stop-and-reverse（每天平均點數／每天交易筆數）")
    for n in (5, 1, 3, 10, 15):
        for sig in ("MOM", "REV", "BRK", "VWAP", "EMA", "MOM2"):
            res = {d: run_sar(day[d], n, sig) for d in dates}
            line = {}
            for lab, a, b in PARTS:
                xs = [res[d] for d in dates if a <= d < b]
                line[lab] = {"avg": round(st.mean(x[0] for x in xs), 1), "trades": round(st.mean(x[1] for x in xs), 1),
                             "gross": round(st.mean(x[0] + x[1] * 2 * SIDE for x in xs), 1),
                             "win": round(sum(x[0] > 0 for x in xs) / len(xs) * 100, 1)}
            # 依線上規則：BO 日做順勢訊號、MR 日做 REV
            out["sar"][f"{n}m/{sig}"] = line
            print(f"  {n:2d} 分 {sig:5s}：" + "｜".join(f"{lab} {v['avg']:+7.1f}（未扣成本 {v['gross']:+6.1f}，{v['trades']:.0f} 筆，賺的天 {v['win']:.0f}%）" for lab, v in line.items()))
        if n != 5:
            continue
        # 5 分：照線上規則分 BO／MR 日
        for sig in ("MOM", "BRK", "VWAP", "EMA"):
            line = {}
            for lab, a, b in PARTS:
                xs = []
                for d in dates:
                    if not (a <= d < b):
                        continue
                    plan = trv.decide(reg[d], p)[1]
                    if plan == "BO":
                        xs.append(run_sar(day[d], 5, sig)[0])
                    elif plan == "MR":
                        xs.append(run_sar(day[d], 5, "REV")[0])
                    else:
                        xs.append(0.0)
                line[lab] = round(st.mean(xs), 1)
            out["sar"][f"5m/regime-{sig}"] = line
            print(f"  5 分 線上規則分日（BO 日 {sig}、MR 日 REV）：" + "｜".join(f"{lab} {v:+.1f}" for lab, v in line.items()))
    print("\n■ ①b VWAP 加帶寬（超過 VWAP ± k × ATR20 才翻向）")
    hist, atr = [], {}
    for d in sorted(day):
        b = day[d]
        if len(b) < 250:
            continue
        if len(hist) >= 20:
            atr[d] = st.mean(hist[-20:])
        hist.append(max(x[1] for x in b.values()) - min(x[2] for x in b.values()))
    out["vwapBand"] = {}
    for n in (5, 15):
        for kb in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3):
            line = {}
            for lab, a, b in PARTS:
                xs = [run_vwap_band(day[d], n, kb * atr[d]) for d in dates if a <= d < b and d in atr]
                line[lab] = {"avg": round(st.mean(x[0] for x in xs), 1), "trades": round(st.mean(x[1] for x in xs), 1)}
            out["vwapBand"][f"{n}m/{kb}"] = line
            print(f"  {n:2d} 分 帶寬 {kb:.2f}×ATR：" + "｜".join(f"{lab} {v['avg']:+.1f}（{v['trades']:.1f} 筆）" for lab, v in line.items()))
    print("\n■ ② 10:00 才判斷（OR＝08:45～10:00）vs 09:15（每天平均點數）")
    for lab, a, b in PARTS:
        ds = [d for d in dates if a <= d < b]
        r10 = {d: or_trade(day[d], 75) for d in ds}
        r915 = {d: (reg[d]["bo"], reg[d]["mr"]) for d in ds}
        live = [trv.pnl(reg[d], trv.decide(reg[d], p)[1]) for d in ds]
        rule10 = [r10[d][0] if reg[d]["gapATR"] > p["cGap"] and not reg[d]["gapFilled30"] else r10[d][1] for d in ds]
        rule10b = [r10[d][1] if reg[d]["gapATR"] < 0 else r10[d][0] for d in ds]
        dn = [d for d in ds if reg[d]["gapATR"] < 0]
        up = [d for d in ds if reg[d]["gapATR"] > 0]
        o = {"bo915": st.mean(x[0] for x in r915.values()), "mr915": st.mean(x[1] for x in r915.values()),
             "bo1000": st.mean(x[0] for x in r10.values()), "mr1000": st.mean(x[1] for x in r10.values()),
             "live915": st.mean(live), "rule1000": st.mean(rule10), "gapRule1000": st.mean(rule10b),
             "down_bo1000": st.mean(r10[d][0] for d in dn), "down_mr1000": st.mean(r10[d][1] for d in dn),
             "up_bo1000": st.mean(r10[d][0] for d in up), "up_mr1000": st.mean(r10[d][1] for d in up)}
        out["or1000"][lab] = {k: round(v, 1) for k, v in o.items()}
        print(f"  {lab}（{len(ds)} 天）：09:15 BO {o['bo915']:+.1f} MR {o['mr915']:+.1f} 線上 {o['live915']:+.1f}｜10:00 BO {o['bo1000']:+.1f} MR {o['mr1000']:+.1f}"
              f"｜10:00 套線上規則 {o['rule1000']:+.1f}、開低 MR 開高 BO {o['gapRule1000']:+.1f}"
              f"｜開低：BO {o['down_bo1000']:+.1f} MR {o['down_mr1000']:+.1f}；開高：BO {o['up_bo1000']:+.1f} MR {o['up_mr1000']:+.1f}")
    (DATA / "research" / "tx_5m.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
