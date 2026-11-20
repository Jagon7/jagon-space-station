#!/usr/bin/env python3
"""
抄底工具比較：同樣的抄底訊號，用台指期、台指買權（TXO call）、個股期貨，哪個效果最好？

訊號（scripts/research_bottom.py 的組合，2008 起，選擇權歷史從期交所下載）：
  深跌＋美股大漲、深跌＋VIX 回落＋止跌（兩段期間都有效）、接刀（深跌當天直接買，對照）
進場：訊號日收盤；出場：5／10／20 個交易日後收盤
  台指期   報酬＝加權指數漲跌（%，名目本金）；保證金約為名目的 MARGIN_TX → 「保證金報酬」＝漲跌 ÷ MARGIN_TX，
           持有期間最低點的虧損 ÷ MARGIN_TX 超過 MAINT 就會被追繳
  買權     期交所 TXO 結算價：距到期 ≥ 14 天的最近月份，價平（履約價最接近收盤）與價外 3%；權利金就是最大虧損
           若到期日早於出場日，用到期日加權收盤估結算價值 max(0, S − K)
  個股期貨 9 檔權值股（台積電、聯發科、鴻海、台達電、廣達、聯電、日月光、大立光、長榮）個別報酬，保證金約 MARGIN_SF
輸出 data/research/dip_instruments.json
"""
from __future__ import annotations

import csv
import io
import json
import os
import statistics as st
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
CACHE = DATA / "research" / "txo"
MARGIN_TX, MARGIN_SF, MAINT = 0.075, 0.135, 0.25  # 保證金佔名目；虧掉保證金 25% 就要補（原始→維持約 75%）
STOCKS = ["2330.TW", "2454.TW", "2317.TW", "2308.TW", "2382.TW", "2303.TW", "3711.TW", "3008.TW", "2603.TW"]
HOLD = (5, 10, 20)


def yd(sym):
    return json.loads((DATA / "research" / "yahoo" / f"{sym.replace('^', '_')}.json").read_text(encoding="utf-8"))["d"]


def third_wed(y, m):
    d = date(y, m, 1)
    return d + timedelta(days=(2 - d.weekday()) % 7 + 14)


def txo(d0: date, d1: date) -> list:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{d0}.csv"
    if f.exists() and f.stat().st_size > 1000:
        raw = f.read_text(encoding="utf-8")
    else:
        raw = ""
        for i in range(4):
            try:
                r = requests.post("https://www.taifex.com.tw/cht/3/optDataDown", headers={"User-Agent": "Mozilla/5.0"}, timeout=60,
                                  data={"down_type": "1", "commodity_id": "TXO", "queryStartDate": d0.strftime("%Y/%m/%d"), "queryEndDate": d1.strftime("%Y/%m/%d")})
                if r.status_code == 200 and len(r.content) > 1000:
                    raw = r.content.decode("big5", errors="ignore")
                    break
            except requests.RequestException:
                pass
            time.sleep(15 * (i + 1))
        if raw:
            f.write_text(raw, encoding="utf-8")
        time.sleep(8)  # 期交所連續下載太快會回錯誤
    out = []
    for row in csv.reader(io.StringIO(raw)):
        if len(row) < 18 or row[4].strip() != "買權" or row[17].strip() != "一般":
            continue
        mon = row[2].strip()
        if not mon.isdigit():
            continue  # 週選擇權
        try:
            out.append((row[0].strip().replace("/", "-"), mon, float(row[3]), float(row[10]) if row[10].strip() not in ("-", "") else None))
        except ValueError:
            continue
    return out


def main():
    rows = json.loads((DATA / "research" / "bottom_rows.json").read_text(encoding="utf-8"))
    tw = [r for r in yd("^TWII") if r[4]]
    tdates = [r[0] for r in tw]
    tclose = {r[0]: r[4] for r in tw}
    tlow = {r[0]: r[3] for r in tw}
    stocks = {s: {r[0]: r[4] for r in yd(s) if r[4]} for s in STOCKS}
    sig = {
        "深跌＋美股大漲": lambda r: r["dd"] <= -12 and (r["spx1"] or 0) >= 1.5,
        "深跌＋VIX 回落＋止跌": lambda r: r["dd"] <= -12 and (r["vixOff"] or 0) >= 10 and (r["vix"] or 0) >= 22 and r["upDay"],
        "接刀：深跌當天直接買": lambda r: r["dd"] <= -12 and not r["upDay"],
    }
    res = {}
    for name, f in sig.items():
        picks, last = [], -99
        for i, r in enumerate(rows):
            if r["date"] < "2008-01-01" or "r20" not in r or not f(r) or i - last < 20:
                continue
            picks.append(r)
            last = i
        trades = []
        for p in picks:
            d = p["date"]
            i = tdates.index(d)
            if i + max(HOLD) >= len(tdates):
                continue
            s0 = tclose[d]
            d0 = date.fromisoformat(d)
            opts = txo(d0, d0 + timedelta(days=31))
            # 到期月份：第三個星期三距訊號日 ≥ 14 天的最近月份
            exps = sorted({o[1] for o in opts})
            mon = next((m for m in exps if (third_wed(int(m[:4]), int(m[4:])) - d0).days >= 14), None)
            t = {"date": d, "dd": round(p["dd"], 1), "s0": s0}
            for n in HOLD:
                dn = tdates[i + n]
                t[f"fut{n}"] = (tclose[dn] / s0 - 1) * 100
                t[f"futLow{n}"] = (min(tlow[x] for x in tdates[i + 1:i + n + 1]) / s0 - 1) * 100
                sr = [(stocks[s][dn] / stocks[s][d] - 1) * 100 for s in STOCKS if d in stocks[s] and dn in stocks[s]]
                t[f"sf{n}"] = st.mean(sr) if sr else None
                t[f"sfBest{n}"] = max(sr) if sr else None
                t[f"sfWorst{n}"] = min(sr) if sr else None
            if mon:
                exp = third_wed(int(mon[:4]), int(mon[4:])).isoformat()
                strikes = sorted({o[2] for o in opts if o[1] == mon and o[0] == d and o[3]})
                for lab, target in (("atm", s0), ("otm", s0 * 1.03)):
                    if not strikes:
                        break
                    k = min(strikes, key=lambda x: abs(x - target))
                    px = {o[0]: o[3] for o in opts if o[1] == mon and o[2] == k and o[3]}
                    if not px.get(d):
                        continue
                    t[f"{lab}K"] = k
                    t[f"{lab}Px"] = px[d]
                    for n in HOLD:
                        dn = tdates[i + n]
                        if dn in px:
                            val = px[dn]
                        elif dn > exp:
                            se = max((x for x in tdates if x <= exp), default=None)
                            val = max(0.0, tclose[se] - k) if se else None
                        else:
                            val = None
                        t[f"{lab}{n}"] = (val / px[d] - 1) * 100 if val is not None else None
            trades.append(t)
        res[name] = trades

    def line(xs, lab):
        xs = [x for x in xs if x is not None]
        if not xs:
            return f"{lab} —"
        return f"{lab} 平均 {st.mean(xs):+7.1f}% 中位 {st.median(xs):+7.1f}% 勝率 {sum(x > 0 for x in xs) / len(xs) * 100:3.0f}% 最差 {min(xs):+7.1f}%"
    out = {"margin": {"tx": MARGIN_TX, "sf": MARGIN_SF}, "signals": {}}
    for name, ts in res.items():
        print(f"\n=== {name}（{len(ts)} 次，{', '.join(t['date'] for t in ts)}）")
        out["signals"][name] = ts
        for n in HOLD:
            print(f" 持有 {n} 天")
            print("   " + line([t[f"fut{n}"] for t in ts], "台指期（名目）  "))
            print("   " + line([t[f"fut{n}"] / MARGIN_TX for t in ts], "台指期（保證金）"))
            print(f"     期間被追繳（最低點虧損 > 保證金 {MAINT * 100:.0f}%）：{sum(1 for t in ts if -t[f'futLow{n}'] / 100 / MARGIN_TX > MAINT)}/{len(ts)} 次")
            print("   " + line([t.get(f"atm{n}") for t in ts], "價平買權        "))
            print("   " + line([t.get(f"otm{n}") for t in ts], "價外 3% 買權    "))
            print("   " + line([t[f"sf{n}"] for t in ts], "個股期（名目）  "))
            print("   " + line([t[f"sf{n}"] / MARGIN_SF for t in ts if t[f"sf{n}"] is not None], "個股期（保證金）"))
            print("   " + line([t[f"sfBest{n}"] for t in ts], "  最強那檔（事後）"))
    (DATA / "research" / "dip_instruments.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
