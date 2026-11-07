#!/usr/bin/env python3
"""
訂單流研究：回補歷史逐筆成交（永豐 Shioaji api.ticks；只查行情、不下單）

每檔每天的逐筆成交 → 5 分鐘 bar：主動買（外盤）／主動賣（內盤）的張數與金額、大單（單筆 ≥ BIG 元）主動買賣金額
  內外盤：用永豐的 tick_type（1 外盤、2 內盤）；沒有標記的用成交價對照當下委買委賣價判斷
  13:30 收盤集合競價那一筆另外記（不分內外盤）
原始 bar 存 --cache（Actions cache，資料量大不進 repo）：<cache>/<日期>.json {代號: [[bar 時間, 買張, 賣張, 買金額, 賣金額, 大單買金額, 大單賣金額, 收盤價, 筆數], ...], "_auction": {代號: [張, 價]}}
每天的彙總特徵存 data/orderflow/features.json（研究與網頁用）
永豐每天有流量上限（usage），剩不到 --reserve MB 就停，下次接著補
用法：python scripts/orderflow_ticks.py [--days 120] [--top 100] [--minutes 120] [--cache 目錄]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
BAR_MIN = 5
BIG = 5_000_000  # 單筆 ≥ 500 萬元算大單


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def universe(top: int) -> list[str]:
    """最近 20 個交易日平均成交金額前 top 名的個股（不含 ETF）"""
    files = sorted((DATA / "daily").glob("20*.json"))[-20:]
    tot: dict[str, float] = {}
    for f in files:
        for c, v in load(f, {}).get("q", {}).items():
            if len(c) == 4 and not c.startswith("0") and v and v[8]:
                tot[c] = tot.get(c, 0) + v[8]
    return sorted(tot, key=lambda c: -tot[c])[:top]


def trading_days(n: int) -> list[str]:
    """最近 n 個交易日（新到舊）：每日檔有的日子，加上更早的平日扣掉休市日"""
    known = sorted(p.stem for p in (DATA / "daily").glob("20*.json"))
    hol = set(load(DATA / "calendar.json", {}).get("holidays", []))
    today = datetime.now(TPE)
    out = [d for d in known if d < today.date().isoformat() or today.hour >= 14]
    d = date.fromisoformat(known[0]) if known else today.date()
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in hol:
            out.insert(0, d.isoformat())
    return sorted(out, reverse=True)[:n]


def to_bars(t) -> tuple[list, list | None]:
    bars: dict[int, list] = {}
    auction = None
    for ts, px, vol, bp, ap, tt in zip(t.ts, t.close, t.volume, t.bid_price, t.ask_price, t.tick_type):
        tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)  # 永豐的 ts 是台灣時間當成 UTC 的奈秒
        mins = tm.hour * 60 + tm.minute
        if mins >= 13 * 60 + 30:
            if mins < 13 * 60 + 35:  # 13:30 收盤集合競價；14:00～14:30 盤後定價交易不算
                auction = [(auction[0] if auction else 0) + vol, px]
            continue
        if mins < 9 * 60:
            continue
        k = (mins - 9 * 60) // BAR_MIN
        b = bars.setdefault(k, [k, 0, 0, 0.0, 0.0, 0.0, 0.0, px, 0])
        side = tt if tt in (1, 2) else (1 if ap and px >= ap else 2 if bp and px <= bp else 0)
        amt = px * vol * 1000
        if side == 1:
            b[1] += vol
            b[3] += amt
            if amt >= BIG:
                b[5] += amt
        elif side == 2:
            b[2] += vol
            b[4] += amt
            if amt >= BIG:
                b[6] += amt
        b[7] = px
        b[8] += 1
    out = []
    for k in sorted(bars):
        b = bars[k]
        out.append([b[0], b[1], b[2], round(b[3]), round(b[4]), round(b[5]), round(b[6]), b[7], b[8]])
    return out, auction


def features(bars: list, auction) -> list:
    """[總成交金額, 主動淨額比, 大單淨額比, 開盤 30 分淨額比, 尾盤 30 分淨額比, 開盤 30 分後價格, 13:25 價格, 收盤價]"""
    def ratio(rows):
        b, s = sum(r[3] for r in rows), sum(r[4] for r in rows)
        return round((b - s) / (b + s), 4) if b + s else None
    amt = sum(r[3] + r[4] for r in bars)
    big = sum(r[5] - r[6] for r in bars)
    first = [r for r in bars if r[0] < 30 // BAR_MIN]
    last = [r for r in bars if r[0] >= (270 - 30) // BAR_MIN]
    p30 = first[-1][7] if first else None
    plast = bars[-1][7] if bars else None
    close = auction[1] if auction else plast
    return [round(amt), ratio(bars), round(big / amt, 4) if amt else None, ratio(first), ratio(last), p30, plast, close]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--minutes", type=float, default=120)
    ap.add_argument("--reserve", type=float, default=30, help="永豐流量剩不到這麼多 MB 就停")
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "jss-orderflow"))
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)

    import shioaji as sj
    api = sj.Shioaji()
    api.login(api_key=os.environ["SHIOAJI_API_KEY"], secret_key=os.environ["SHIOAJI_SECRET_KEY"], subscribe_trade=False)
    for _ in range(120):
        try:
            if api.Contracts.Stocks["2330"] is not None:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)

    def usage():
        u = api.usage()
        return u.bytes, u.limit_bytes, u.remaining_bytes

    used0, limit, remain = usage()
    log(f"永豐流量：已用 {used0 / 1e6:.0f} MB／上限 {limit / 1e6:.0f} MB，剩 {remain / 1e6:.0f} MB")
    codes = universe(a.top)
    days = trading_days(a.days)
    log(f"標的 {len(codes)} 檔、{len(days)} 個交易日（{days[-1]} ～ {days[0]}）")

    feat_path = DATA / "orderflow" / "features.json"
    feat = load(feat_path, {"codes": [], "days": {}})
    stop = False
    checked = False
    for d in days:
        f = cache / f"{d}.json"
        doc = load(f, {"_auction": {}})
        if doc.get("_holiday"):
            continue
        todo = [c for c in codes if c not in doc]
        if not todo:
            continue
        b0 = usage()[0]
        n0 = len(doc)
        for c in todo:
            if time.time() > deadline:
                log("時間到，下次接著補")
                stop = True
                break
            try:
                t = api.ticks(contract=api.Contracts.Stocks[c], date=d)
            except Exception as e:  # noqa: BLE001
                log(f"{d} {c} 失敗：{e}")
                continue
            if c == todo[0] and not t.ts and c == codes[0]:
                log(f"{d} 沒有成交資料（休市）")
                doc = {"_holiday": True}
                break
            if not checked and t.ts:
                checked = True
                f0, f1 = (datetime.fromtimestamp(x / 1e9, timezone.utc).strftime("%H:%M:%S") for x in (t.ts[0], t.ts[-1]))
                log(f"時間檢查 {d} {c}：第一筆 {f0}、最後一筆 {f1}，共 {len(t.ts)} 筆，tick_type 分布 "
                    f"{ {k: t.tick_type.count(k) for k in set(t.tick_type)} }")
            bars, auc = to_bars(t)
            doc[c] = bars
            if auc:
                doc["_auction"][c] = auc
            feat["days"].setdefault(d, {})[c] = features(bars, auc)
        f.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        b1, _, remain = usage()
        got = len(doc) - n0
        log(f"{d}：{got} 檔，用掉 {(b1 - b0) / 1e6:.1f} MB（每檔約 {(b1 - b0) / max(got, 1) / 1e6:.2f} MB），剩 {remain / 1e6:.0f} MB")
        if stop or remain < a.reserve * 1e6:
            if remain < a.reserve * 1e6:
                log("永豐流量快用完，明天接著補")
            break
    feat["codes"] = sorted(set(feat.get("codes", [])) | set(codes))
    feat["days"] = dict(sorted(feat["days"].items()))
    feat["updatedAt"] = datetime.now(TPE).isoformat(timespec="minutes")
    feat["fields"] = ["amt", "net", "bigNet", "open30Net", "last30Net", "p0930", "p1325", "close"]
    feat_path.parent.mkdir(parents=True, exist_ok=True)
    feat_path.write_text(json.dumps(feat, separators=(",", ":")), encoding="utf-8")
    log(f"特徵：{len(feat['days'])} 天")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
