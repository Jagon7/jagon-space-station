#!/usr/bin/env python3
"""
當沖（開盤放空、收盤回補）停損機制回測，重點：避免券差（漲停鎖死、收盤買不回來）

資料：data/research/dt_stop_bars.json.gz（fetch_dt_stop.py，永豐 1 分 K 壓成 5 分 K；價格是相對前一天收盤的萬分之一）
事件：data/research/dt_stop_events.json（前一天成交前 50 名、前一天漲停或 5 日漲 ≥ 10%；開高 0～4% 或前一天漲停又開高 4～9.5%）
停損規則（都在 09:00 開盤價放空；碰到停損價就以停損價回補，那根 5 分 K 開盤就跳過停損價則以開盤價回補；沒碰到就 13:30 收盤回補）：
  固定：漲到放空價 +2／3／4／5／7%
  結構：開盤後 15／30 分鐘內最高點再 +1%（之前用 +7% 保護）
  防漲停：漲到「前一天收盤 +8／8.5／9%」就回補（離漲停還有一段，買得到）
  時間：10:30 還在放空價之上就回補
  組合：固定 +5% 或 防漲停 +8.5% 先到的
券差風險：沒停損時，收盤前鎖漲停（13:25 後都在漲停）的比例；停損價高於漲停價（碰不到）時算成「收盤回補」
成本：0.24%（證交稅 0.15%＋手續費打折）
輸出 data/research/dt_stop.json；用法：python scripts/research_dt_stop.py
"""
from __future__ import annotations

import gzip
import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = 0.24
PARTS = (("2022-23", "2022", "2024"), ("2024", "2024", "2025"), ("2025-", "2025", "2100"))


def run(x: dict, rule) -> tuple[float, str]:
    """回傳（放空報酬 %, 出場原因）"""
    bars = [b for b in x["b"] if b]
    e = bars[0][0]  # 放空價（萬分之一，相對前一天收盤）
    to_pct = lambda p: -((1 + p / 1e4) / (1 + e / 1e4) - 1) * 100  # noqa: E731
    hi = -1e9
    for k, (o, h, l, c, v) in enumerate(bars):
        stop = rule(e, k, hi, x)
        if stop is not None and stop <= x["limBp"]:
            if k > 0 and o >= stop:
                return to_pct(o), "停損（跳空）"
            if h >= stop:
                return to_pct(stop), "停損"
        if rule.__name__ == "time" and k == 18 and c > e:  # 10:30
            return to_pct(c), "時間"
        hi = max(hi, h)
    return to_pct(bars[-1][3]), "收盤"


def mk_fixed(pct):
    def fixed(e, k, hi, x):
        return round(((1 + e / 1e4) * (1 + pct / 100) - 1) * 1e4)
    fixed.__name__ = f"fixed{pct}"
    return fixed


def mk_struct(mins):
    nb = mins // 5

    def struct(e, k, hi, x):
        if k < nb:
            return round(((1 + e / 1e4) * 1.07 - 1) * 1e4)
        h0 = max(b[1] for b in x["b"][:nb] if b)
        return round(((1 + h0 / 1e4) * 1.01 - 1) * 1e4)
    struct.__name__ = f"struct{mins}"
    return struct


def mk_guard(lvl):
    def guard(e, k, hi, x):
        return max(lvl * 100, e + 50)  # 前一天收盤 +lvl%（放空價本來就很高時，至少高 0.5%）
    guard.__name__ = f"guard{lvl}"
    return guard


def none(e, k, hi, x):
    return None


def time(e, k, hi, x):
    return round(((1 + e / 1e4) * 1.07 - 1) * 1e4)


def combo(e, k, hi, x):
    return min(round(((1 + e / 1e4) * 1.05 - 1) * 1e4), max(850, e + 50))


def main():
    ev = {f"{e[0]}|{e[1]}": e for e in json.loads((DATA / "research" / "dt_stop_events.json").read_text(encoding="utf-8"))}
    bars = json.loads(gzip.decompress((DATA / "research" / "dt_stop_bars.json.gz").read_bytes()))
    rows = []
    for k, x in bars.items():
        if not x or k not in ev or not x["b"] or not x["b"][0]:
            continue
        e = ev[k]
        if x["b"][0][0] >= x["limBp"] - 5:
            continue  # 開盤就漲停，放空放不了
        rows.append({"d": e[0], "c": e[1], "gap": e[4], "prevLim": e[5] >= 9.5, "x": x})
    print(f"事件 {len(rows)} 個（{min(r['d'] for r in rows)}～{max(r['d'] for r in rows)}）；每筆扣 {COST}%")
    groups = (("全部", lambda r: True), ("85g 型：開高 1～3%", lambda r: 1 <= r["gap"] < 3),
              ("開高 0～4%", lambda r: 0 <= r["gap"] < 4), ("前一天漲停、開高 4～9.5%", lambda r: r["gap"] >= 4))
    rules = [none, mk_fixed(2), mk_fixed(3), mk_fixed(4), mk_fixed(5), mk_fixed(7), mk_struct(15), mk_struct(30),
             mk_guard(8), mk_guard(8.5), mk_guard(9), time, combo]
    label = {"none": "不停損", "fixed2": "固定 +2%", "fixed3": "固定 +3%", "fixed4": "固定 +4%", "fixed5": "固定 +5%", "fixed7": "固定 +7%",
             "struct15": "前 15 分最高 +1%", "struct30": "前 30 分最高 +1%", "guard8": "防漲停：漲 8% 回補", "guard8.5": "防漲停：漲 8.5% 回補",
             "guard9": "防漲停：漲 9% 回補", "time": "10:30 還在放空價上就回補", "combo": "固定 +5% 或漲 8.5% 先到"}
    out = {"cost": COST, "n": len(rows), "groups": {}}
    for gname, gf in groups:
        rs = [r for r in rows if gf(r)]
        if len(rs) < 50:
            continue
        lock = sum(r["x"]["lockEnd"] for r in rs) / len(rs) * 100
        touch = sum(r["x"]["lim"] is not None for r in rs) / len(rs) * 100
        print(f"\n■ {gname}（{len(rs)} 筆）：盤中碰漲停 {touch:.1f}%、收盤鎖漲停（不停損會券差）{lock:.1f}%")
        out["groups"][gname] = {"n": len(rs), "touch": round(touch, 1), "lockEnd": round(lock, 1), "rules": {}}
        for rule in rules:
            res = [(r, *run(r["x"], rule)) for r in rs]
            pnl = [p - COST for _, p, _ in res]
            srt = sorted(pnl)
            stopped = sum(1 for _, _, why in res if why != "收盤") / len(res) * 100
            lk = sum(1 for r, _, why in res if why == "收盤" and r["x"]["lockEnd"]) / len(res) * 100
            per = []
            for _, a, b in PARTS:
                xs = [p - COST for r, p, _ in res if a <= r["d"] < b]
                per.append(round(st.mean(xs), 2) if len(xs) >= 30 else None)
            o = {"avg": round(st.mean(pnl), 2), "win": round(sum(p > 0 for p in pnl) / len(pnl) * 100, 1), "worst1": round(srt[len(srt) // 100], 2),
                 "min": round(srt[0], 2), "stopped": round(stopped, 1), "lockLeft": round(lk, 2), "parts": per}
            out["groups"][gname]["rules"][rule.__name__] = o
            print(f"  {label[rule.__name__]:22s} 平均 {o['avg']:+.2f}%  勝率 {o['win']:4.1f}%  最差 1% {o['worst1']:+6.2f}%  最大虧損 {o['min']:+6.2f}%"
                  f"  停損比例 {o['stopped']:4.1f}%  仍可能券差 {o['lockLeft']:.2f}%  各期 {per}")
    (DATA / "research" / "dt_stop.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
