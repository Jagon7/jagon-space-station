"""
結算策略：股票期貨每天 13:24 的折溢價（永豐 Shioaji 歷史逐筆，只查行情）

對照 Excel「折溢價raw」：每天收盤前（約 13:24）股期近月與現貨的買賣報價，折溢價＝期貨 ÷ 現貨 − 1
這裡用 13:20～13:24 最後一筆逐筆的委買委賣中價：(期貨買＋期貨賣) ÷ (現貨買＋現貨賣) − 1
結果 data/settlement/basis.json {日期: {股票代號: 折溢價}}；由 orderflow_ticks.py 登入後呼叫 run()
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TPE = timezone(timedelta(hours=8))


def _last_mid(t, cutoff_min: int = 13 * 60 + 24):
    """逐筆裡 13:24 以前（含）最後一筆的委買委賣中價；沒有就用這段最後一筆"""
    best = None
    for ts, bp, ap in zip(t.ts, t.bid_price, t.ask_price):
        tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)
        if bp and ap and bp > 0 and ap > 0:
            if tm.hour * 60 + tm.minute <= cutoff_min or best is None:
                best = (bp + ap) / 2
    return best


def run(api, data: Path, deadline: float, log=print) -> int:
    import shioaji as sj
    sys_path = Path(__file__).resolve().parent
    import sys
    sys.path.insert(0, str(sys_path))
    import fetch_settlement as fs

    hol = fs.holidays()
    today = datetime.now(TPE).date()
    start, sday, month = fs.period(today if datetime.now(TPE).hour >= 14 else today - timedelta(days=1), hol)
    contracts = json.loads((data / "settlement" / "contracts.json").read_text(encoding="utf-8"))["contracts"]
    big = {k: v[0] for k, v in contracts.items() if v[1] == 2000}  # 契約代號 → 股票代號（只用 2,000 股的大型股期）
    path = data / "settlement" / "basis.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}

    # 永豐的股期合約：類別代號（例如 CDF）＋交割月份
    fut = {}
    try:
        for cat in api.Contracts.Futures:
            for c in cat:
                code = getattr(c, "code", "")
                if code.endswith(("R1", "R2")) or getattr(c, "delivery_month", "") != month:
                    continue
                k = getattr(c, "category", "")[:-1] if getattr(c, "category", "").endswith("F") else ""
                if k in big:
                    fut[k] = c
    except Exception as e:  # noqa: BLE001
        log(f"折溢價：讀取期貨合約失敗 {e}")
        return 0
    log(f"折溢價：{month} 近月股期 {len(fut)} 個（共 {len(big)} 個大型股期契約）")

    d = start
    days = []
    while d <= min(today, sday):
        if d.weekday() < 5 and d.isoformat() not in hol and (d < today or datetime.now(TPE).hour >= 14):
            days.append(d)
        d += timedelta(days=1)
    n = 0
    for d in days:
        ds = d.isoformat()
        got = doc.setdefault(ds, {})
        lt_f = data / "settlement" / "lt" / f"{ds}.json"
        oi = json.loads(lt_f.read_text(encoding="utf-8"))["rows"] if lt_f.exists() else {}
        todo = [k for k in fut if big[k] not in got and (not oi or (oi.get(k) or [0])[0] > 0)]
        for k in todo:
            if time.time() > deadline:
                log("折溢價：時間到，下次接著補")
                path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
                return n
            stock = big[k]
            try:
                rng = dict(date=ds, query_type=sj.TicksQueryType.RangeTime, time_start="13:20:00", time_end="13:25:00")
                tf = api.ticks(contract=fut[k], **rng)
                tsk = api.ticks(contract=api.Contracts.Stocks[stock], **rng)
                mf, ms = _last_mid(tf), _last_mid(tsk)
            except Exception as e:  # noqa: BLE001
                log(f"折溢價：{ds} {k}/{stock} 失敗 {e}")
                continue
            got[stock] = round(mf / ms - 1, 5) if mf and ms else None
            n += 1
        log(f"折溢價：{ds} {sum(v is not None for v in got.values())} 檔")
    path.write_text(json.dumps(dict(sorted(doc.items())), separators=(",", ":")), encoding="utf-8")
    return n
