"""
除權息黑K監控 → public/data/exdiv.json
  upcoming 未來 14 天要除息的股票：現金股利、殖利率、近 20 日均成交金額、有沒有個股期、自營商近 10 日淨買賣、能不能現沖先賣
           符合＝殖利率 ≥ 4% 且日均成交 ≥ 5000 萬；有個股期的最好放空（除息前後融券常暫停）
  active   除息日已過、還在持有期（除息日起 4 個交易日）的部位：除息日開盤放空到最新收盤的報酬
  done     近期已出場（持滿 4 天）的結果
  backtest data/strategy/exdiv_bt.json（scripts/backtest_exdiv.py 產生的 5 年回測）
"""
from __future__ import annotations

import json
import statistics as st
from datetime import date, datetime, timedelta
from pathlib import Path

from build_strategy import TPE, _load, next_trading_day

MIN_YIELD, MIN_VAL, HOLD, AHEAD = 4.0, 5e7, 4, 14


def build(data_dir: Path, public_dir: Path):
    ev = (_load(data_dir / "fund" / "events.json", {}) or {}).get("exdiv", [])
    days = []
    for f in sorted((data_dir / "daily").glob("20*.json"))[-60:]:
        doc = _load(f, {})
        if doc.get("q"):
            days.append((doc.get("date", f.stem), doc["q"]))
    if not days:
        return
    dates = [d for d, _ in days]
    pos = {d: i for i, d in enumerate(dates)}
    last, q = days[-1]
    holidays = set((_load(data_dir / "calendar.json", {}) or {}).get("holidays", []))
    nxt = next_trading_day(last, holidays)
    sf = set((_load(data_dir / "strategy" / "stockfutures.json", {}) or {}).get("codes", []))
    dtd = (_load(data_dir / "strategy" / "daytrade.json", {}) or {}).get("days", {})
    nox = set((dtd.get(last) or {}).get("x", []))
    insti = {}
    for f in sorted((data_dir / "insti").glob("20*.json"))[-10:]:
        insti[f.stem] = _load(f, {}) or {}

    def avgval(code):
        v = [(qq.get(code) or [0] * 9)[8] or 0 for _, qq in days[-20:]]
        return st.mean(v) if v else 0

    def dealer10(code):
        return sum((d.get(code) or [0] * 6)[4] for d in insti.values())

    upcoming, active, done = [], [], []
    horizon = (date.fromisoformat(last) + timedelta(days=AHEAD)).isoformat()
    seen = set()
    for r in sorted(ev, key=lambda r: r[0]):
        d, code, name, mk, kind, cash = r[0], r[1], r[2], r[3], r[4], r[5]
        if not cash or not (len(code) == 4 and code.isdigit()) or (d, code) in seen:
            continue
        seen.add((d, code))
        qq = q.get(code)
        if d > last and d <= horizon and qq:
            px = qq[5]
            y = cash / px * 100 if px else None
            val = avgval(code)
            ok = y is not None and y >= MIN_YIELD and val >= MIN_VAL
            upcoming.append({"date": d, "code": code, "name": name, "mk": mk, "kind": kind, "cash": round(cash, 3), "close": px,
                             "y": round(y, 2) if y else None, "valYi": round(val / 1e8, 2), "sf": code in sf, "dealer": dealer10(code),
                             "noShort": code in nox, "ok": ok, "tomorrow": d == nxt})
        elif d <= last and d in pos:
            i = pos[d]
            o = (days[i][1].get(code) or [None] * 9)[2]
            if not o:
                continue
            px0 = (days[i - 1][1].get(code) or [None] * 9)[5] if i > 0 else None
            y = cash / px0 * 100 if px0 else None
            if y is None or y < MIN_YIELD or avgval(code) < MIN_VAL:
                continue
            k = min(len(dates) - 1, i + HOLD - 1)
            cl = (days[k][1].get(code) or [None] * 9)[5]
            if not cl:
                continue
            row = {"date": d, "code": code, "name": name, "y": round(y, 2), "sf": code in sf, "entry": o, "last": cl,
                   "ret": round(-(cl / o - 1) * 100, 2), "day": k - i + 1,
                   "blacks": sum(1 for j in range(i, k + 1) if (days[j][1].get(code) or [0] * 9)[5] < (days[j][1].get(code) or [0] * 9)[2])}
            (done if k - i + 1 >= HOLD else active).append(row)
    # 持有中的部位：預計回補日＝除息日起第 4 個交易日
    for a in active:
        d = a["date"]
        for _ in range(HOLD - 1):
            d = next_trading_day(d, holidays)
        a["exit"] = d
    upcoming.sort(key=lambda x: (x["date"], -(x["y"] or 0)))
    done.sort(key=lambda x: x["date"], reverse=True)
    bt = _load(data_dir / "strategy" / "exdiv_bt.json", {}) or {}
    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "asof": last, "next": nxt, "minYield": MIN_YIELD, "hold": HOLD,
           "upcoming": upcoming, "active": active, "done": done[:60], "backtest": bt}
    (public_dir / "exdiv.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"除權息黑K：未來 {AHEAD} 天 {len(upcoming)} 檔（符合 {sum(u['ok'] for u in upcoming)}）、持有中 {len(active)}、近期出場 {len(done)}")
