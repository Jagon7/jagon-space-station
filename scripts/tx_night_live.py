#!/usr/bin/env python3
"""
台指期夜盤即時訊號：美股開盤後 30 分鐘的區間（OR）突破一筆（停損後反手為選擇性），推 LINE（永豐只查行情、不下單）

回測（scripts/research_tx_multi.py，2020/3～2026/11，每筆扣 3 點）：
  夜盤美股段 OR＝美股開盤後 30 分鐘（夏令 21:30～22:00、冬令 22:30～23:00）
  突破高點做多、跌破低點做空，停損放 OR 另一側；05:00 出場
  一筆：2020-22／2023-24／2025 後每天平均 +6.2／+7.2／+5.6 點（三段都賺）
  停損後反手（最多 3 筆）：+5.9／+9.2／+13.5；反手那幾筆本身 −0.7／+5.7／+22.1，2020-22 沒加分 → 列為選擇性
  停損後改做均值回歸：三段都虧（−5.4／−9.9／−19.0），不要做
  夜盤前段（15:00～美股開盤）各種打法都是虧的，所以不發
用法：
  python scripts/tx_night_live.py [--dry-run] [--now]   # 21:50 啟動，等到 OR 結束（22:00 或 23:00）後判斷並推送
  python scripts/tx_night_live.py review                # 隔天傍晚（夜盤資料進來後）算昨晚實際結果，寫進 journal
資料：永豐 TXFR1 1 分 K；journal：data/futures/night_journal.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_tx_multi import run, us_dst  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
JOURNAL = DATA / "futures" / "night_journal.json"


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def night_bars(api, c, day: str, shift: int = 1) -> dict:
    """今天 15:00 之後的夜盤 1 分 K → {分鐘（15:00＝0）: [開, 高, 低, 收, 量]}；永豐 K 棒時間是結束時間，往前移 1 分"""
    k = api.kbars(contract=c, start=day, end=(date.fromisoformat(day) + timedelta(days=1)).isoformat())
    out = {}
    for ts, o, h, lo, cl, v in zip(k.ts, k.Open, k.High, k.Low, k.Close, k.Volume):
        tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)
        t = tm.hour * 60 + tm.minute - shift
        if tm.date().isoformat() == day and t >= 15 * 60:
            out[t - 15 * 60] = [float(o), float(h), float(lo), float(cl), int(v)]
        elif tm.date().isoformat() > day and t <= 5 * 60:
            out[t + 9 * 60] = [float(o), float(h), float(lo), float(cl), int(v)]
    return out


def review() -> int:
    """data/futures/night 有昨晚資料後，算每個還沒有結果的訊號（05:00 與 02:00 出場）"""
    j = load(JOURNAL, {})
    months = {}
    n = 0
    for d, e in sorted(j.items()):
        if e.get("result"):
            continue
        ym = d[:7]
        if ym not in months:
            months[ym] = load(DATA / "futures" / "night" / f"{ym}.json", {})
        v = months[ym].get(d)
        if not v or len(v.get("bars") or []) < 600:
            continue
        bars = {b[0]: b[1:] for b in v["bars"]}
        res = {}
        for ex, lab in ((839, "0500"), (660, "0200")):
            ts = run(bars, e["orh"], e["orl"], e["start"], ex, "BO_SAR")
            res[lab] = round(ts[0][0]) if ts else 0  # 一筆（第一筆）
            res["sar" + lab] = round(sum(t[0] for t in ts))  # 含停損反手
            res["n" + lab] = len(ts)
        e["result"] = res
        n += 1
        log(f"{d}：一筆 05:00 出場 {res['0500']:+} 點、含反手 {res['sar0500']:+} 點（{res['n0500']} 筆）；02:00 出場 {res['0200']:+} 點")
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=0), encoding="utf-8")
    log(f"復盤 {n} 晚")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="signal")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", action="store_true")
    a = ap.parse_args()
    if a.mode == "review":
        return review()
    now = datetime.now(TPE)
    today = now.date().isoformat()
    j = load(JOURNAL, {})
    if today in j and not a.dry_run:
        log("今晚已經發過")
        return 0
    us = 390 if us_dst(now.date()) else 450  # 美股開盤距 15:00 的分鐘數
    start = us + 30
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
        target = now.replace(hour=15, minute=0, second=25, microsecond=0) + timedelta(minutes=start)
        log(f"等到 {target:%H:%M:%S}（美股開盤 {(15 * 60 + us) // 60}:{(15 * 60 + us) % 60:02d} 後 30 分鐘）")
        while datetime.now(TPE) < target:
            time.sleep(5)
    bars = {}
    for _ in range(12):
        bars = night_bars(api, c, today)
        have = [m for m in bars if us <= m < start]
        if len(have) >= 27 or a.now:
            break
        log(f"美股段前 30 分鐘 K 棒只有 {len(have)} 根，等一下再抓")
        time.sleep(20)
    orb = [bars[m] for m in range(us, start) if m in bars]
    if len(orb) < 10:
        log(f"抓不到今晚的 1 分 K（{len(orb)} 根），可能休市")
        return 0
    orh, orl = max(b[1] for b in orb), min(b[2] for b in orb)
    w = orh - orl
    last = bars[max(bars)][3]
    # 昨晚結果（隔天 17:40 復盤寫進來的）
    prev = [(d, e["result"]) for d, e in sorted(j.items()) if d < today and e.get("result")]
    recent = [r["0500"] for _, r in prev[-20:]]
    j[today] = {"us": us, "start": start, "orh": orh, "orl": orl, "w": w, "last": last}
    from line_flex import Msg
    import notify
    hh = lambda m: f"{(15 * 60 + m) // 60 % 24:02d}:{(15 * 60 + m) % 60:02d}"  # noqa: E731
    m = Msg(("【測試】" if a.dry_run else "") + "🌙 台指期夜盤：美股段突破", f"{now:%m/%d} {hh(start)} 判斷・區間 {hh(us)}～{hh(start)}",
            accent="#7C3AED", url=f"{notify.SITE}/", button="開啟網站")
    m.section(f"美股開盤後 30 分鐘區間（{hh(us)}～{hh(start)}）")
    m.kv("高點", f"{orh:,.0f}")
    m.kv("低點", f"{orl:,.0f}")
    m.kv("寬度", f"{w:,.0f} 點")
    m.kv("目前", f"{last:,.0f}")
    m.section("做法：先突破哪邊做哪邊，一筆")
    m.kv("突破高點做多", f"{orh:,.0f}・停損 {orl:,.0f}")
    m.kv("跌破低點做空", f"{orl:,.0f}・停損 {orh:,.0f}")
    m.line("選擇性：被停損可在停損價反手做另一邊（停損放原本進場那一側），最多 3 筆；回測 2023 後有加分、2020-22 打平")
    m.line("❌ 停損後不要改做均值回歸（回測三段都虧）")
    m.line("05:00 收盤前平倉（回測最好）；不想熬夜可在 02:00 平倉，回測少賺約 15%")
    m.line("判斷時價格如果已經在區間外，回測是當下就進場（照突破方向）")
    if prev:
        d0, r0 = prev[-1]
        m.kv(f"上一晚（{d0[5:]}）", f"一筆 {r0['0500']:+,} 點・含反手 {r0.get('sar0500', r0['0500']):+,} 點・02:00 出場 {r0['0200']:+,}")
    if len(recent) >= 5:
        m.kv(f"近 {len(recent)} 晚", f"合計 {sum(recent):+,} 點、賺的 {sum(x > 0 for x in recent)} 晚")
    m.note("回測 2020/3～2026/11（每筆扣 3 點）：一筆每晚平均 2020-22 +6.2、2023-24 +7.2、2025 後 +5.6 點；勝率約四成五，常連虧，"
           "最大累計回落約 3,500 點。夜盤前段（美股開盤前）各種打法都虧，不發。只查行情，不會下單。")
    print(m.text())
    if a.dry_run:
        return 0
    if not notify.send(m):
        print("（沒有設定任何推播管道，只印出內容）")
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
