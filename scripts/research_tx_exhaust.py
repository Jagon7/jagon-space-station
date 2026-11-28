#!/usr/bin/env python3
"""
台指期當沖：開盤「頂部反轉」（量縮衰竭）——參考 Umar Ashraf 早盤頂部反轉（SPY：開盤後價往上、每 5 分鐘成交量一路遞減 → 做空）
資料：data/futures/day（近月 1 分 K，2020/3 起；research_tx_regime.load_dir 已清錯誤成交、結算日 13:29 平倉）
5 分 K（由 1 分 K 合成，08:45 起第 0 根）；只看開盤後 WINDOW 根內（預設 09:45 前）
頂部反轉（做空）：
  ① 拉升：盤中最高比開盤高 ≥ RISE×ATR20
  ② 量縮：創高的那段上漲（連續創新高的 5 分 K，至少 MIN_UP 根）成交量逐根遞減（VOL 規則：mono＝每根都比前一根少；
     ratio＝最後一根創高的量 ≤ 前面最大量 × 0.6）；none＝不看量（對照）
  ③ 轉弱：之後第一根「收盤跌破前一根 5 分 K 最低」的 5 分 K → 下一分鐘開盤放空
  停損：當天最高 + 1 點；停利：2 × 風險（2:1）或 VWAP 或開盤價；13:30 平倉；每天每方向最多 1 筆
底部反轉（做多）＝鏡像（開盤後殺低、量縮、收盤站上前一根最高）
停損太大（> MAX_R×ATR20）不做；成本 3 點；三段 2020-22／2023-24／2025+
輸出 data/research/tx_exhaust.json；用法：python scripts/research_tx_exhaust.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402

DATA = rr.DATA
COST = 3.0
EXIT = 284          # 13:29
PARTS = (("2020-22", "2020", "2023"), ("2023-24", "2023", "2025"), ("2025+", "2025", "2100"))


def five(bars: dict):
    out = []
    for k in range(0, 60):
        ms = [bars[m] for m in range(k * 5, k * 5 + 5) if m in bars]
        if not ms:
            out.append(None)
            continue
        out.append([ms[0][0], max(b[1] for b in ms), min(b[2] for b in ms), ms[-1][3], sum(b[4] for b in ms), k * 5 + 4])
    return out


def find(bars, atr, side, window, rise, vol_rule, min_up):
    """回傳（進場分鐘, 停損價）或 None；side=-1 頂部反轉做空、+1 底部反轉做多"""
    f = five(bars)
    if not f[0]:
        return None
    op = f[0][0]
    ext_i, ext = None, None
    run = []   # 目前這段連續創新極值的 5 分 K
    best = []
    for i in range(window):
        b = f[i]
        if not b:
            continue
        x = b[1] if side < 0 else b[2]
        new = ext is None or (x > ext if side < 0 else x < ext)
        if new:
            if ext_i is not None and ext_i == i - 1 and run:
                run.append(i)
            else:
                run = [i]
            ext, ext_i = x, i
            best = list(run)
            continue
        if i == 0:
            continue
        prev = f[i - 1]
        if not prev:
            continue
        broke = b[3] < prev[2] if side < 0 else b[3] > prev[1]
        if not broke:
            continue
        move = (ext - op) if side < 0 else (op - ext)
        if move < rise * atr or len(best) < min_up:
            continue
        vols = [f[k][4] for k in best]
        if vol_rule == "mono" and not all(vols[k] < vols[k - 1] for k in range(1, len(vols))):
            continue
        if vol_rule == "ratio" and not vols[-1] <= max(vols[:-1]) * 0.6:
            continue
        return b[5] + 1, ext + (1 if side < 0 else -1)
    return None


def trade(bars, ent_m, stop, side, target, vw):
    if ent_m not in bars:
        ks = [m for m in bars if m >= ent_m]
        if not ks:
            return None
        ent_m = min(ks)
    e = bars[ent_m][0]
    risk = (stop - e) if side < 0 else (e - stop)
    if risk <= 0:
        return None
    if target == "2R":
        tp = e - 2 * risk if side < 0 else e + 2 * risk
    elif target == "open":
        tp = bars[min(bars)][0]
    else:
        tp = None
    for m in sorted(bars):
        if m < ent_m or m > EXIT:
            continue
        o, h, lo, c = bars[m][:4]
        if (h >= stop) if side < 0 else (lo <= stop):
            return -risk - COST, risk, "sl"
        t = tp
        if target == "vwap":
            t = vw[m - 1] if m >= 1 and vw[m - 1] else None
        if t is not None and ((lo <= t) if side < 0 else (h >= t)) and ((t < e) if side < 0 else (t > e)):
            return abs(e - t) - COST, risk, "tp"
        if m == EXIT:
            return ((e - c) if side < 0 else (c - e)) - COST, risk, "time"
    last = bars[max(m for m in bars if m <= EXIT)][3]
    return ((e - last) if side < 0 else (last - e)) - COST, risk, "time"


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    dates = sorted(d for d, b in day.items() if len(b) >= 250)
    hist, atr = [], {}
    for d in dates:
        b = day[d]
        if len(hist) >= 20:
            atr[d] = st.mean(hist[-20:])
        hist.append(max(x[1] for x in b.values()) - min(x[2] for x in b.values()))
    dates = [d for d in dates if d in atr]
    vws = {d: rr.vwap_path(day[d], EXIT) for d in dates}
    print(f"{dates[0]}～{dates[-1]}，{len(dates)} 天；每筆扣 {COST:g} 點")
    out = []
    for side, sname in ((-1, "頂部反轉空"), (1, "底部反轉多")):
        for window in (6, 12, 18):
            for rise in (0.15, 0.3):
                for vol_rule in ("mono", "ratio", "none"):
                    for min_up in (2, 3):
                        for target in ("2R", "vwap", "open", "close"):
                            line = {}
                            for lab, a, b in PARTS:
                                pts, rs, n_days = [], [], 0
                                for d in dates:
                                    if not (a <= d < b):
                                        continue
                                    n_days += 1
                                    s = find(day[d], atr[d], side, window, rise, vol_rule, min_up)
                                    if not s:
                                        continue
                                    r = trade(day[d], s[0], s[1], side, target, vws[d])
                                    if not r or r[1] > 0.5 * atr[d]:
                                        continue
                                    pts.append(r[0])
                                    rs.append(r[0] / r[1])
                                if pts:
                                    line[lab] = {"n": len(pts), "freq": round(len(pts) / n_days * 100), "avg": round(st.mean(pts), 1),
                                                 "win": round(sum(x > 0 for x in pts) / len(pts) * 100), "R": round(st.mean(rs), 2),
                                                 "sum": round(sum(pts))}
                            out.append({"side": sname, "window": window, "rise": rise, "vol": vol_rule, "minUp": min_up, "target": target, "parts": line})
    (DATA / "research" / "tx_exhaust.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    fmt = lambda p: "｜".join(f"{k} {v['avg']:+.1f}點（{v['n']}筆 {v['freq']}%天，勝{v['win']}%，{v['R']:+.2f}R）" for k, v in p.items())  # noqa: E731
    for o in out:
        if o["minUp"] == 2 and o["rise"] == 0.15 and o["target"] in ("2R", "close"):
            print(f"{o['side']} 前{o['window'] * 5}分 量{o['vol']:5s} 目標{o['target']:5s}：{fmt(o['parts'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
