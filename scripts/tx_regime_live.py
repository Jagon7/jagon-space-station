#!/usr/bin/env python3
"""
台指期當日型態即時訊號：09:15 用前 30 分鐘 1 分 K 判斷今天做突破（BO）還是均值回歸（MR），推 LINE

規則（scripts/research_tx_regime.py 回測，2020/3～2026/11）：
  A 前 30 分鐘碰到昨收（回補跳空） → MR
  B 沒回補、開盤區間寬度 ≤ 0.34 × 近 20 日平均振幅 → MR（不要追突破）
  C 沒回補、區間不窄、開高 → BO
  D 開低沒回補、區間不窄 → 不做
參考：09:15 價差偏離（期貨 − 加權指數，相對前一天平均）
資料：永豐 TXFR1 1 分 K（只查行情、不下單）；昨收、平均振幅用 data/futures/day
用法：python scripts/tx_regime_live.py [--dry-run] [--now]（--now 不等 09:15，直接用目前資料）
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
OR_M, NARROW = 30, 0.34
JOURNAL = DATA / "futures" / "regime_journal.json"
STATE = DATA / "notify" / "tx-regime-sent.json"


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def history():
    days = {}
    for f in sorted((DATA / "futures" / "day").glob("20*.json")):
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            days[k] = v["bars"]
    return days


def bars_today(api, c, shift: int, today: str):
    k = api.kbars(contract=c, start=today, end=today)
    out = {}
    for ts, o, h, lo, cl, v in zip(k.ts, k.Open, k.High, k.Low, k.Close, k.Volume):
        tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)
        if tm.date().isoformat() != today:
            continue
        m = tm.hour * 60 + tm.minute - (8 * 60 + 45) - shift
        if 0 <= m <= 300:
            out[m] = [float(o), float(h), float(lo), float(cl), int(v)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", action="store_true")
    a = ap.parse_args()
    now = datetime.now(TPE)
    today = now.date().isoformat()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    if today in state["sent"] and not a.dry_run:
        log("今天已經發過")
        return 0
    hist = history()
    past = sorted(d for d in hist if d < today)[-20:]
    if len(past) < 20:
        log("歷史日盤資料不足")
        return 0
    prev = hist[past[-1]]
    prev_close = prev[-1][4]
    atr = st.mean(max(b[2] for b in hist[d]) - min(b[3] for b in hist[d]) for d in past)

    import shioaji as sj
    api = sj.Shioaji()
    api.login(api_key=os.environ["SHIOAJI_API_KEY"], secret_key=os.environ["SHIOAJI_SECRET_KEY"], subscribe_trade=False)
    for _ in range(120):
        try:
            if api.Contracts.Futures.TXF.TXFR1 is not None:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    c = api.Contracts.Futures.TXF.TXFR1
    if not a.now:
        target = now.replace(hour=9, minute=15, second=25, microsecond=0)
        while datetime.now(TPE) < target:
            time.sleep(5)
    bars = {}
    for i in range(12):
        bars = bars_today(api, c, 1, today)  # 永豐 K 棒時間是結束時間（回補時確認過），往前移 1 分
        have = [m for m in bars if m < OR_M]
        if len(have) >= OR_M - 3 or a.now:
            break
        log(f"前 30 分鐘 K 棒只有 {len(have)} 根，等一下再抓")
        time.sleep(20)
    orb = [bars[m] for m in sorted(bars) if m < OR_M]
    if len(orb) < 10:
        log(f"抓不到今天的 1 分 K（{len(orb)} 根）")
        return 1
    op = orb[0][0]
    orh, orl = max(b[1] for b in orb), min(b[2] for b in orb)
    p915 = orb[-1][3]
    w = orh - orl
    filled = any(b[2] <= prev_close <= b[1] for b in orb)
    gap = op - prev_close
    import tx_regime_review as trr
    P = trr.params()["current"]
    NARROW_ = P["narrow"]
    br, plan = trr.decide({"gapFilled30": filled, "orATR": w / atr, "gapATR": gap / atr}, P)
    if filled:
        br, plan = "A", "MR"
        why = f"前 30 分鐘回補了跳空（碰到昨收 {prev_close:,.0f}）"
    elif br == "B":
        why = f"沒回補，但開盤區間很窄（{w:,.0f} 點 ≤ 平均振幅 {atr:,.0f} 的 {NARROW_ * 100:.0f}%）→ 不要追突破"
    elif br == "C":
        why = f"開高 {gap:+,.0f} 點沒回補、區間不窄（{w:,.0f} 點）"
    else:
        why = f"{'開低' if gap <= 0 else '開高不多'} {gap:+,.0f} 點沒回補、區間不窄（{w:,.0f} 點）" + ("→ 回測沒有方向" if plan is None else f"→ 依回測做 {plan}")

    # 參考：價差偏離（09:15 期貨 − 加權，相對前一天全天平均）
    dev_txt = None
    try:
        tse = api.Contracts.Indexs.TSE
        items = [tse[x] if isinstance(x, str) else x for x in tse]
        ix = next((x for x in items if str(getattr(x, "name", "")) in ("發行量加權股價指數", "加權指數", "臺灣加權指數")), None)
        if ix is not None:
            k = api.kbars(contract=ix, start=today, end=today)
            ib = {}
            for ts, cl in zip(k.ts, k.Close):
                tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)
                if tm.date().isoformat() == today:
                    ib[(tm.hour - 9) * 60 + tm.minute - 1] = float(cl)
            k915 = max((m for m in ib if m <= 14), default=None)
            idx = json.loads((DATA / "market" / "index1m" / f"{past[-1][:7]}.json").read_text(encoding="utf-8")).get(past[-1])
            if k915 is not None and idx:
                pb = {b[0]: b[4] for b in prev}
                prev_basis = [pb[m + 15] - t for m, t in enumerate(idx["t"]) if t and (m + 15) in pb]
                basis = p915 - ib[k915]
                dev = (basis - st.mean(prev_basis)) / ib[k915] * 100
                hint = ("偏正（回測最適合 BO）" if 0.01 < dev <= 0.13 else "正價差過頭（回測偏 MR）" if dev > 0.13
                        else "偏逆" if dev < -0.08 else "正常")
                dev_txt = f"價差 {basis:+,.0f} 點，比昨天平均 {dev:+.2f}% → {hint}"
    except Exception as e:  # noqa: BLE001
        log(f"價差計算失敗：{e}")

    from line_flex import Msg
    import notify
    title = {"MR": "均值回歸（MR）" + ("・不追突破" if br == "B" else ""), "BO": "突破（BO）", None: "今天不做"}[plan]
    m = Msg(("【測試】" if a.dry_run else "") + f"📈 台指期今日型態：{title}", f"{now:%m/%d} 09:15 判斷・分支 {br}", accent="#DC2626" if plan == "BO" else "#2563EB" if plan else "#64748B",
            url=f"{notify.SITE}/", button="開啟網站")
    m.line(why)
    m.section("開盤區間（08:45～09:15）")
    m.kv("高點", f"{orh:,.0f}")
    m.kv("低點", f"{orl:,.0f}")
    m.kv("寬度", f"{w:,.0f} 點（平均振幅 {atr:,.0f} 的 {w / atr * 100:.0f}%）")
    m.kv("開盤／昨收", f"{op:,.0f}／{prev_close:,.0f}（{gap:+,.0f}）")
    m.kv("09:15 價", f"{p915:,.0f}")
    if plan == "MR":
        m.section("MR 做法（09:15 後一筆）")
        m.kv("碰高點放空", f"{orh:,.0f}・停損 {orh + 0.5 * w:,.0f}・目標 {(orh + orl) / 2:,.0f}")
        m.kv("碰低點做多", f"{orl:,.0f}・停損 {orl - 0.5 * w:,.0f}・目標 {(orh + orl) / 2:,.0f}")
    elif plan == "BO":
        m.section("BO 做法（09:15 後一筆）")
        m.kv("突破高點做多", f"{orh:,.0f}・停損 {orl:,.0f}・抱到 13:30")
        m.kv("跌破低點做空", f"{orl:,.0f}・停損 {orh:,.0f}・抱到 13:30")
    if dev_txt:
        m.kv("參考", dev_txt)
    m.note("回測（2020/3～2026/11）：A／B 做 MR、C 做 BO、D 不做，兩段期間都贏過固定只做一種；單日仍可能失準（例如 11/19 回補後一路噴），停損要守。只查行情，不會下單。")
    print(m.text())
    if a.dry_run:
        return 0
    if not notify.send(m):
        log("沒有推播管道")
    try:
        j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        j = {}
    j[today] = {"branch": br, "plan": plan, "orh": orh, "orl": orl, "open": op, "prevClose": prev_close, "p915": p915, "atr": round(atr, 1),
                "orATR": round(w / atr, 3), "gapATR": round(gap / atr, 3), "filled": filled, "params": P, "basis": dev_txt}
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=0), encoding="utf-8")
    state["sent"] = (state["sent"] + [today])[-60:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
