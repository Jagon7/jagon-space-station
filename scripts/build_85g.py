"""
85g 策略（開高走低當沖）→ public/data/85g.json
  cand     明日觀察名單：今天成交金額前 50 名、前 5 日漲 ≥ 10% 的熱門股（明天開高 1.5～6% 就是 A 打法的標的），
           附族群、開高 1.5%／6% 的價位、今天是否暫停先賣後買
  hot      今天成交金額前 50 名（指數大跌開低時 B 打法從這裡挑）
  recent   近 60 天每天符合 A 條件（前一日前 50 名、前 5 日漲 ≥ 10%、開高 1.5～6%）的股票，開盤賣、收盤買回的結果
  trades   85g 公開對帳單的逐筆解析（data/strategy/85g_trades.json，含當天 5 分 K）
  backtest data/strategy/85g_bt.json（scripts/backtest_85g.py）
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime
from pathlib import Path

from build_strategy import TPE, _load, next_trading_day

TOP, GAP_LO, GAP_HI, RUN5, COST = 50, 1.5, 6.0, 10.0, 0.24


def build(data_dir: Path, public_dir: Path):
    days = []
    for f in sorted((data_dir / "daily").glob("20*.json"))[-66:]:
        doc = _load(f, {})
        if doc.get("q"):
            days.append((doc.get("date", f.stem), doc["q"]))
    if len(days) < 7:
        return
    last, q = days[-1]
    holidays = set((_load(data_dir / "calendar.json", {}) or {}).get("holidays", []))
    sec = {}
    for name, rows in ((_load(data_dir / "sector-stocks.json", {}) or {}).get("data") or {}).items():
        for r in rows:
            sec.setdefault(r["code"], name)
    dtd = (_load(data_dir / "strategy" / "daytrade.json", {}) or {}).get("days", {})
    nox = set((dtd.get(last) or {}).get("x", []))

    def top(qq):
        return sorted((c for c in qq if len(c) == 4 and c.isdigit() and c[0] != "0" and qq[c][5]), key=lambda c: -(qq[c][8] or 0))[:TOP]

    def chg(qa, qb, c):
        a, b = (qa.get(c) or [0] * 9)[5], (qb.get(c) or [0] * 9)[5]
        return (a / b - 1) * 100 if a and b else None

    hot, cand = [], []
    for i, c in enumerate(top(q)):
        r = q[c]
        p5 = chg(q, days[-6][1], c)
        row = {"code": c, "name": r[0], "mk": "上櫃" if r[1] else "上市", "close": r[5], "chg": chg(q, days[-2][1], c), "p5": p5,
               "valYi": round((r[8] or 0) / 1e8, 1), "rank": i + 1, "sector": sec.get(c), "noShort": c in nox}
        hot.append(row)
        if p5 is not None and p5 >= RUN5:
            cand.append({**row, "lo": round(r[5] * (1 + GAP_LO / 100), 2), "hi": round(r[5] * (1 + GAP_HI / 100), 2)})
    recent = []
    for i in range(6, len(days)):
        d, qq = days[i]
        qp, q5 = days[i - 1][1], days[i - 6][1]
        for c in top(qp):
            r = qq.get(c)
            p5 = chg(qp, q5, c)
            if not r or not r[2] or not r[5] or p5 is None or p5 < RUN5:
                continue
            gap = (r[2] / qp[c][5] - 1) * 100
            if GAP_LO <= gap < GAP_HI:
                recent.append({"date": d, "code": c, "name": r[0], "gap": round(gap, 2), "p5": round(p5, 1), "open": r[2], "high": r[3], "close": r[5],
                               "ret": round(-(r[5] / r[2] - 1) * 100, 2), "openHigh": r[3] <= r[2] * 1.002, "sector": sec.get(c)})
    recent.sort(key=lambda x: (x["date"], -x["gap"]), reverse=True)
    rr = [x["ret"] for x in recent]
    summary = {"n": len(rr), "avg": round(st.mean(rr), 2) if rr else None, "win": round(sum(x > 0 for x in rr) / len(rr) * 100, 1) if rr else None,
               "net": round(st.mean(rr) - COST, 2) if rr else None, "days": len({x["date"] for x in recent}), "from": days[6][0], "to": last}
    tr = _load(data_dir / "strategy" / "85g_trades.json", {}) or {}
    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "asof": last, "next": next_trading_day(last, holidays),
           "rule": {"top": TOP, "gap": [GAP_LO, GAP_HI], "run5": RUN5, "cost": COST}, "cand": cand, "hot": hot, "recent": recent[:200], "summary": summary,
           "trades": tr, "backtest": _load(data_dir / "strategy" / "85g_bt.json", {}) or {}}
    (public_dir / "85g.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"85g：明日觀察 {len(cand)} 檔、近 {summary['days']} 天 A 訊號 {summary['n']} 筆（平均 {summary['avg']}%）")
