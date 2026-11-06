#!/usr/bin/env python3
"""
比對「公開資料版」與「TEJ 試算表」的輸入資料（逐檔、逐欄位），列出一致率與差最多的股票。
用法：python -m scripts.rebalance.compare_inputs path/to/919___2612.xlsx [資料目錄]
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import etf919
from .public import Public
from .verify_tej import load_919


def rate(name, a: dict, b: dict, tol=0.005, show=5):
    keys = [k for k in b if b[k] is not None]
    both = [k for k in keys if a.get(k) is not None]
    ok = [k for k in both if abs(a[k] - b[k]) <= tol * max(1.0, abs(b[k]))]
    bad = sorted((k for k in both if k not in ok), key=lambda k: -abs(a[k] - b[k]) / max(1.0, abs(b[k])))
    print(f"{name:<14} TEJ {len(keys):>5} 檔｜公開有值 {len(both):>5}｜一致 {len(ok):>5}（{len(ok) / max(len(both), 1):.1%}）"
          + (f"｜差最多：{', '.join(f'{k} {a[k]:.4g}/{b[k]:.4g}' for k in bad[:show])}" if bad else ""))


def main():
    xlsx = sys.argv[1]
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[2] / "data"
    t, _ = load_919(xlsx)
    p = Public(data).bundle(t["asof"])
    print(f"資料日 {t['asof']}；公開版 6 月窗 {p['windows']['6m']}、1 月窗 {p['windows']['1m']}")
    rate("收盤價", p["close"], t["close"], 1e-9)
    rate("市值(百萬)", p["mcap"], t["mcap"], 0.0005)
    rate("董監持股%", p["insider"], t["insider"], 0.02)
    rate("近6月均值", p["tv6m_avg"], t["tv6m_avg"], 1e-9)
    rate("近1月均值", p["tv1m_avg"], t["tv1m_avg"], 1e-9)
    rate("6月中位數", p["tv6m_median"], t["tv6m_median"], 1e-9)
    rate("換手量", p["turnover1"], t["turnover1"], 0.01)
    Y = int(t["asof"][:4])
    for q in (f"{Y}Q2", f"{Y}Q1", f"{Y - 1}Q4", f"{Y - 1}Q3"):
        rate(f"EPS {q}", {k: v.get(q) for k, v in p["eps"].items()}, {k: v.get(q) for k, v in t["eps"].items()}, 0.02)
    g_p = {k: etf919.eps_growth(p["eps"].get(k, {}), p["rev"].get(k, {}), Y)[0] for k in t["eps"]}
    g_t = {k: etf919.eps_growth(t["eps"].get(k, {}), t["rev"].get(k, {}), Y)[0] for k in t["eps"]}
    rate("EPS成長率", {k: (v if v != "" else None) for k, v in g_p.items()}, {k: (v if v != "" else None) for k, v in g_t.items()}, 0.02)
    for m in (f"{Y}-09", f"{Y}-08", f"{Y}-07"):
        rate(f"營收 {m}", {k: v.get(m) for k, v in p["rev"].items()}, {k: v.get(m) for k, v in t["rev"].items()}, 1e-6)
    d_p = {k: etf919.four_q_dividend(p["div"].get(k, {}), Y)[0] for k in t["div"]}
    d_t = {k: etf919.four_q_dividend(t["div"].get(k, {}), Y)[0] for k in t["div"]}
    rate("近四季股利", d_p, d_t, 0.01)
    e = p["etf"]["00919"]
    print(f"00919 持股：公開版 {e['date']} {len(e['weights'])} 檔、AUM {e['aum']:,.0f} 千元；TEJ {len(t['etf']['00919']['weights'])} 檔、AUM {t['etf']['00919']['aum']:,.0f}")


if __name__ == "__main__":
    main()
