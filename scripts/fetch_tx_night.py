#!/usr/bin/env python3
"""
台指期（大台 TX）夜盤 1 分 K 歷史

來源：
  taifex   期交所「前 30 個交易日期貨每筆成交資料」（Daily_YYYY_MM_DD.zip），每天自動存，30 天後期交所就刪了
  shioaji  永豐 api.kbars（TXFR1 近月連續，只查行情、不下單），回補更早的夜盤
夜盤：前一天 15:00 ～ 隔天 05:00；以「夜盤開始的日期」當 key（11/13 晚上 → 2026-11-13）
分鐘序號 m＝（時刻 − 15:00）的分鐘數，0 ＝ 15:00～15:01，839 ＝ 04:59～05:00，840 ＝ 05:00 收盤那一刻的成交
存 data/futures/night/<YYYY-MM>.json {夜盤日期: {"src", "contract", "bars": [[m, 開, 高, 低, 收, 口數], ...]}}
用法：
  python scripts/fetch_tx_night.py --taifex                         # 補最近 30 個交易日（期交所）
  python scripts/fetch_tx_night.py --shioaji --since 2018-01-01      # 永豐回補（先探測最早有資料的年份）
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA / "futures" / "night"
TPE = timezone(timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0"}


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def night_min(hh: int, mm: int) -> int | None:
    """時刻 → 夜盤分鐘序號；不是夜盤時段回 None"""
    t = hh * 60 + mm
    if t >= 15 * 60:
        return t - 15 * 60
    if t <= 5 * 60:
        return t + 9 * 60
    return None


def load_month(ym: str) -> dict:
    try:
        return json.loads((OUT / f"{ym}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(nights: dict[str, dict], overwrite_src: tuple[str, ...] = ()):
    """合併寫入月檔；已有期交所（逐筆）資料的夜盤不會被永豐覆蓋"""
    by: dict[str, dict] = {}
    for d, v in nights.items():
        by.setdefault(d[:7], {})[d] = v
    OUT.mkdir(parents=True, exist_ok=True)
    for ym, add in by.items():
        doc = load_month(ym)
        for d, v in add.items():
            old = doc.get(d)
            if old and old.get("src") == "taifex" and v["src"] != "taifex" and "taifex" not in overwrite_src:
                continue
            doc[d] = v
        for v in doc.values():  # 台指期價格都是整數點，存整數省空間
            v["bars"] = [[int(x) if float(x).is_integer() else x for x in b] for b in v["bars"]]
        (OUT / f"{ym}.json").write_text(json.dumps(dict(sorted(doc.items())), separators=(",", ":")), encoding="utf-8")


# ---------------- 期交所逐筆 ----------------

def taifex_day(d: date) -> dict[str, dict]:
    """某交易日的逐筆檔 → 裡面那一段夜盤（前一個交易日晚上）的 1 分 K"""
    import requests
    url = f"https://www.taifex.com.tw/file/taifex/Dailydownload/DailydownloadCSV/Daily_{d:%Y_%m_%d}.zip"
    r = requests.get(url, headers=UA, timeout=120)
    if r.status_code != 200 or r.content[:2] != b"PK":
        return {}
    z = zipfile.ZipFile(io.BytesIO(r.content))
    raw = z.read(z.namelist()[0]).decode("big5", errors="ignore")
    # 夜盤日期 → 契約 → 分鐘 → [開, 高, 低, 收, 量]
    acc: dict[str, dict[str, dict[int, list]]] = {}
    for row in csv.reader(io.StringIO(raw)):
        if len(row) < 6 or row[1].strip() != "TX":
            continue
        mon = row[2].strip()
        if "/" in mon or not mon.isdigit():  # 價差單、週選之類的不要
            continue
        t = row[3].strip().zfill(6)
        m = night_min(int(t[:2]), int(t[2:4]))
        if m is None:
            continue
        dd = datetime.strptime(row[0].strip(), "%Y%m%d").date()
        nd = dd if m < 9 * 60 else dd - timedelta(days=1)  # 00:00～05:00 屬於前一天晚上開始的夜盤
        # 週一凌晨不會有；週六凌晨（週五夜盤）會是 dd - 1 ＝ 週五，正確
        try:
            px, q = float(row[4]), int(float(row[5]))
        except ValueError:
            continue
        q //= 2  # 成交數量（B+S）是買賣合計
        b = acc.setdefault(nd.isoformat(), {}).setdefault(mon, {}).get(m)
        if b is None:
            acc[nd.isoformat()][mon][m] = [px, px, px, px, q]
        else:
            b[1] = max(b[1], px); b[2] = min(b[2], px); b[3] = px; b[4] += q
    out = {}
    for nd, by_mon in acc.items():
        mon = max(by_mon, key=lambda k: sum(x[4] for x in by_mon[k].values()))  # 成交量最大的月份＝近月（結算週會換到次月）
        bars = [[m, *by_mon[mon][m]] for m in sorted(by_mon[mon])]
        if len(bars) > 30:
            out[nd] = {"src": "taifex", "contract": mon, "bars": bars}
    return out


def run_taifex(days: int = 35):
    hol = set((json.loads((DATA / "calendar.json").read_text(encoding="utf-8")) or {}).get("holidays", [])) if (DATA / "calendar.json").exists() else set()
    today = datetime.now(TPE).date()
    have = set()
    for f in OUT.glob("20*.json") if OUT.exists() else []:
        have |= {d for d, v in load_month(f.stem).items() if v.get("src") == "taifex"}
    got = {}
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5 or d.isoformat() in hol:
            continue
        # 這個交易日的檔案裡是「前一個交易日晚上」的夜盤；已經存過就不重抓
        prev = d - timedelta(days=1)
        while prev.weekday() >= 5 or prev.isoformat() in hol:
            prev -= timedelta(days=1)
        if prev.isoformat() in have:
            continue
        try:
            res = taifex_day(d)
        except Exception as e:  # noqa: BLE001
            log(f"{d} 下載失敗：{e}")
            continue
        if res:
            for nd, v in res.items():
                log(f"期交所 {d} 檔 → 夜盤 {nd}：{v['contract']} {len(v['bars'])} 根，{sum(b[5] for b in v['bars']):,} 口")
            got.update(res)
        time.sleep(2)
    save(got, overwrite_src=("taifex",))
    log(f"期交所：新增 {len(got)} 個夜盤")


# ---------------- 永豐 1 分 K ----------------

def sj_login():
    import shioaji as sj
    api = sj.Shioaji()
    api.login(api_key=os.environ["SHIOAJI_API_KEY"], secret_key=os.environ["SHIOAJI_SECRET_KEY"], subscribe_trade=False)
    for _ in range(120):
        try:
            if api.Contracts.Futures.TXF is not None:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    return api


def sj_nights(api, c, s: date, e: date) -> tuple[dict, dict]:
    """永豐 1 分 K → {夜盤日期: bars}，以及時間戳記的診斷資訊"""
    k = api.kbars(contract=c, start=s.isoformat(), end=e.isoformat())
    acc: dict[str, dict[int, list]] = {}
    mins = []
    for ts, o, h, lo, cl, v in zip(k.ts, k.Open, k.High, k.Low, k.Close, k.Volume):
        tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)  # 永豐的 ts 是台灣時間當成 UTC
        m = night_min(tm.hour, tm.minute)
        if m is None:
            continue
        nd = tm.date() if m < 9 * 60 else tm.date() - timedelta(days=1)
        acc.setdefault(nd.isoformat(), {})[m] = [float(o), float(h), float(lo), float(cl), int(v)]
        mins.append(m)
    diag = {"bars": len(k.ts), "nightBars": len(mins), "minM": min(mins) if mins else None, "maxM": max(mins) if mins else None,
            "first": datetime.fromtimestamp(k.ts[0] / 1e9, timezone.utc).strftime("%Y-%m-%d %H:%M") if k.ts else None}
    return acc, diag


def run_shioaji(since: str, minutes: float):
    deadline = time.time() + minutes * 60
    api = sj_login()
    c = api.Contracts.Futures.TXF.TXFR1
    log(f"合約：{getattr(c, 'code', '')} {getattr(c, 'name', '')}")
    have = set()
    for f in OUT.glob("20*.json") if OUT.exists() else []:
        have |= {d for d, v in load_month(f.stem).items() if v.get("src") == "shioaji"}
    # 探測（第一次才做）：每年 1 月第二週有沒有資料
    for y in (range(2017, datetime.now(TPE).year + 1) if not have else []):
        try:
            _, dg = sj_nights(api, c, date(y, 1, 9), date(y, 1, 13))
            log(f"探測 {y}/01：{dg}")
        except Exception as e:  # noqa: BLE001
            log(f"探測 {y}/01 失敗：{e}")
    u = api.usage()
    log(f"永豐流量：已用 {u.bytes / 1e6:.0f} MB／上限 {u.limit_bytes / 1e6:.0f} MB")
    # 回補：每次查一個月，從最新往回；已有的夜盤不重查
    for f in OUT.glob("20*.json") if OUT.exists() else []:
        have |= set(load_month(f.stem))
    shift = None
    cur = datetime.now(TPE).date().replace(day=1)
    stop = date.fromisoformat(since)
    total = 0
    while cur >= stop and time.time() < deadline:
        e = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if sum(1 for d in have if d.startswith(cur.isoformat()[:7])) >= 15:
            cur = (cur - timedelta(days=1)).replace(day=1)
            continue
        try:
            acc, dg = sj_nights(api, c, cur, e + timedelta(days=1))
        except Exception as ex:  # noqa: BLE001
            log(f"{cur:%Y-%m} 失敗：{ex}")
            break
        if not acc:
            log(f"{cur:%Y-%m}：沒有夜盤資料，停止（{dg}）")
            break
        if shift is None:
            # 永豐 K 棒時間如果是「結束時間」（第一根在 15:01），往前移 1 分鐘對齊期交所（開始時間）
            shift = 1 if dg["minM"] == 1 else 0
            log(f"K 棒時間對齊：{'結束時間，往前移 1 分' if shift else '開始時間'}（{dg}）")
        got = {}
        for nd, bars in acc.items():
            if nd in have or not (cur.isoformat()[:7] <= nd[:7] <= e.isoformat()[:7]):
                continue
            got[nd] = {"src": "shioaji", "contract": "TXFR1", "bars": [[m - shift, *bars[m]] for m in sorted(bars)]}
        save(got)
        have |= set(got)
        total += len(got)
        u = api.usage()
        log(f"{cur:%Y-%m}：{len(got)} 個夜盤（剩 {u.remaining_bytes / 1e6:.0f} MB）")
        if u.remaining_bytes < 30e6:
            log("永豐流量快用完，下次接著補")
            break
        cur = (cur - timedelta(days=1)).replace(day=1)
    log(f"永豐：新增 {total} 個夜盤")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taifex", action="store_true")
    ap.add_argument("--shioaji", action="store_true")
    ap.add_argument("--since", default="2017-05-15", help="永豐回補到哪天（夜盤 2017/5/15 開始）")
    ap.add_argument("--minutes", type=float, default=20)
    a = ap.parse_args()
    if a.taifex:
        run_taifex()
    if a.shioaji:
        if not os.environ.get("SHIOAJI_API_KEY"):
            log("沒有永豐金鑰，略過")
        else:
            run_shioaji(a.since, a.minutes)
    n = sum(len(load_month(f.stem)) for f in OUT.glob("20*.json")) if OUT.exists() else 0
    log(f"夜盤資料共 {n} 晚")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
