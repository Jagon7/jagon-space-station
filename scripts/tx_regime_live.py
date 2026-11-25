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


def live_features(hist: dict, past: list[str], bars: dict, today: str, atr: float, op: float, w: float, gap: float) -> dict:
    """tx_factor_scan 用的因子（定義同 research_tx_regime／tx_factor_scan），09:15 就算得出來"""
    import bisect
    import statistics as st_
    import research_tx_regime as rr
    f = {}
    try:
        pv = hist[past[-1]]
        ph, pl, pc, po = max(b[2] for b in pv), min(b[3] for b in pv), pv[-1][4], pv[0][1]
        orb = [bars[m] for m in sorted(bars) if m < OR_M]
        orh, orl = max(b[1] for b in orb), min(b[2] for b in orb)
        f["absGapATR"] = abs(gap) / atr
        f["prevRangeATR"] = (ph - pl) / atr
        f["prevEff"] = abs(pc - po) / (ph - pl) if ph > pl else 0
        f["atrPct"] = atr / pc * 100
        rng = [max(b[2] for b in hist[d]) - min(b[3] for b in hist[d]) for d in past[-7:]]
        f["nr7"] = float((ph - pl) <= min(rng))
        f["openOutside"] = float(op > ph or op < pl)
        f["pos915"] = (orb[-1][3] - orl) / (orh - orl) if orh > orl else 0.5
        vw = rr.vwap_path(bars, OR_M - 1)
        f["vwapCross30"] = sum(1 for m in range(1, OR_M) if bars.get(m) and bars.get(m - 1) and vw[m] and vw[m - 1]
                               and (bars[m][3] - vw[m]) * (bars[m - 1][3] - vw[m - 1]) < 0)
        orv = [sum(b[5] for b in hist[d] if b[0] < OR_M) for d in past[-20:]]
        f["rvol30"] = sum(b[4] for b in orb) / st_.mean(orv) if orv and st_.mean(orv) else None
        alld = sorted(d for d in hist if d < today)
        pcts = []
        for i in range(max(20, len(alld) - 200), len(alld)):
            a = st_.mean(max(b[2] for b in hist[d]) - min(b[3] for b in hist[d]) for d in alld[i - 20:i])
            pcts.append(a / hist[alld[i - 1]][-1][4] * 100)
        f["atrPctl"] = sum(v <= f["atrPct"] for v in pcts) / len(pcts) * 100 if len(pcts) >= 60 else None
        d0 = datetime.fromisoformat(today)
        f["settle"] = float(d0.weekday() == 2 and 15 <= d0.day <= 21)
        ev = json.loads((DATA / "intel" / "us_events.json").read_text(encoding="utf-8")).get("events", [])
        nights = set()
        for e in ev:
            t = datetime.fromisoformat(e["t"])
            nights.add((t.date() if t.hour >= 15 else t.date() - timedelta(days=1)).isoformat())
        f["usEvent"] = float(past[-1] in nights)
        tw = json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]
        j = bisect.bisect_left([x[0] for x in tw], today)
        c = [x[4] for x in tw[max(0, j - 60):j]]
        f["bear"] = float(c[-1] < st_.mean(c)) if len(c) == 60 else None
    except Exception as e:  # noqa: BLE001
        log(f"因子計算失敗（不影響主規則）：{e}")
    return f


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
    feat = {"gapFilled30": filled, "orATR": w / atr, "gapATR": gap / atr}
    if P.get("overrides"):
        feat.update(live_features(hist, past, bars, today, atr, op, w, gap))
    br0, plan0 = trr.base_decide(feat, P)
    br, plan = trr.decide(feat, P)
    ov = next((o for o in P.get("overrides") or [] if o["branch"] == br and trr.match(feat, o)), None)
    if filled:
        why = f"前 30 分鐘回補了跳空（碰到昨收 {prev_close:,.0f}）"
    elif br == "B":
        why = f"沒回補，但開盤區間很窄（{w:,.0f} 點 ≤ 平均振幅 {atr:,.0f} 的 {NARROW_ * 100:.0f}%）→ 不要追突破"
    elif br == "C":
        why = f"開高 {gap:+,.0f} 點沒回補、區間不窄（{w:,.0f} 點）"
    else:
        why = f"{'開低' if gap <= 0 else '開高不多'} {gap:+,.0f} 點沒回補、區間不窄（{w:,.0f} 點）" + ("→ 回測沒有方向" if plan0 is None else f"→ 依回測做 {plan0}")

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
    if ov:
        m.line(f"🧪 因子修正：{ov['label']} {ov['op']} {ov['th']}（今天 {feat.get(ov['factor']):.2f}）→ 原本 {plan0 or '不做'} 改成 {plan or '不做'}")
    m.section("開盤區間（08:45～09:15）")
    m.kv("高點", f"{orh:,.0f}")
    m.kv("低點", f"{orl:,.0f}")
    m.kv("寬度", f"{w:,.0f} 點（平均振幅 {atr:,.0f} 的 {w / atr * 100:.0f}%）")
    m.kv("開盤／昨收", f"{op:,.0f}／{prev_close:,.0f}（{gap:+,.0f}）")
    m.kv("09:15 價", f"{p915:,.0f}")
    if plan == "MR":
        m.section("MR 做法（09:15～09:30 先碰到哪邊做哪邊，一天一筆）")
        m.kv("先碰高點→放空", f"{orh:,.0f}・停損 {orh + 0.5 * w:,.0f}・目標 {(orh + orl) / 2:,.0f}")
        m.kv("先碰低點→做多", f"{orl:,.0f}・停損 {orl - 0.5 * w:,.0f}・目標 {(orh + orl) / 2:,.0f}")
        m.line("⏱ 09:30 前兩邊都沒碰到就不做（之後才碰到的回測是虧的）；停利或停損後就收手，另一邊再被碰到也不做；13:30 前沒到目標或停損就平倉")
    elif plan == "BO":
        m.section("BO 做法（09:15 後先突破哪邊做哪邊，一天一筆）")
        m.kv("突破高點做多", f"{orh:,.0f}・停損 {orl:,.0f}・抱到 13:30")
        m.kv("跌破低點做空", f"{orl:,.0f}・停損 {orh:,.0f}・抱到 13:30")
    if dev_txt:
        m.kv("參考", dev_txt)
    dtxt = {"MR": "做 MR", "BO": "做 BO", None: "不做"}[P.get("dPlan")]
    m.note(f"規則：A 缺口回補／B 窄區間做 MR、C 開高不補做 BO、D {dtxt}（每週六自動調參、每週掃描因子，證據夠強才修正）；"
           "回測 2020-24 與 2025 後都贏過固定只做一種。單日仍可能失準，停損要守。只查行情，不會下單。")
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
                "orATR": round(w / atr, 3), "gapATR": round(gap / atr, 3), "filled": filled, "params": P, "basis": dev_txt,
                "override": ov, "feat": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in feat.items()} if ov else None}
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=0), encoding="utf-8")
    state["sent"] = (state["sent"] + [today])[-60:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
