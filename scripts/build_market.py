"""
從 data/daily（每日全市場行情＋融資券＋借券）算出三個頁面要的資料 → public/data/market/
  atmosphere.json  氣氛評估：每天的漲跌家數、漲跌停、站上月線比例、創 20 日新高低、成交值、融資增減，合成 0~100 氣氛分數
  nextday.json     隔日追蹤：每天漲停股隔天的開盤、最高、最低、收盤、3 日後表現
  short.json       券差偵察：最新一天各股融資券、券資比、借券賣出與股價變化；short/<代號>.json 為近 60 天明細
"""
from __future__ import annotations

import json
import math
import re
import shutil
from bisect import bisect_left
from pathlib import Path

STOCK = re.compile(r"[1-9]\d{3}")  # 普通股（排除 ETF 00 開頭）


def tick(p: float) -> float:
    return 0.01 if p < 10 else 0.05 if p < 50 else 0.1 if p < 100 else 0.5 if p < 500 else 1 if p < 1000 else 5


def limit_prices(prev: float) -> tuple[float, float]:
    up_raw, dn_raw = prev * 1.1, prev * 0.9
    t = tick(up_raw)
    up = math.floor(up_raw / t + 1e-6) * t
    t = tick(dn_raw)
    dn = math.ceil(dn_raw / t - 1e-6) * t
    return round(up, 2), round(dn, 2)


def pct(a, b):
    return round((b / a - 1) * 100, 2) if a and b else None


def _rank(xs: list, x) -> float:
    """x 在 xs 中的百分位（0~100）"""
    if x is None:
        return 50.0
    s = sorted(v for v in xs if v is not None)
    if len(s) < 5:
        return 50.0
    return bisect_left(s, x) / (len(s) - 1) * 100 if len(s) > 1 else 50.0


def label(score: float) -> str:
    return "過熱" if score >= 80 else "偏多" if score >= 60 else "中性" if score >= 40 else "偏空" if score >= 20 else "冰點"


def build(data_dir: Path, out_dir: Path):
    src = data_dir / "daily"
    out = out_dir / "market"
    shutil.rmtree(out, ignore_errors=True)
    (out / "short").mkdir(parents=True, exist_ok=True)
    days = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(src.glob("20*.json"))]
    days = [d for d in days if d.get("q")]
    if not days:
        print("每日行情：沒有資料")
        return
    names: dict[str, str] = {}
    closes: dict[str, list] = {}  # 代號 → 每天收盤（None＝沒交易）
    n = len(days)
    for i, d in enumerate(days):
        for c, v in d["q"].items():
            names[c] = v[0]
            closes.setdefault(c, [None] * n)[i] = v[5]

    # ── 每天：漲跌停、廣度 ─────────────────────────────
    limit_up: list[set] = []
    rows_atm = []
    for i, d in enumerate(days):
        adv = dec = unch = lu = ld = nh = nl = above = tot20 = 0
        value = 0.0
        lus = set()
        for c, v in d["q"].items():
            if not STOCK.fullmatch(c):
                continue
            close, chg = v[5], v[6] or 0
            value += v[8] or 0
            prev = close - chg
            if chg > 0:
                adv += 1
            elif chg < 0:
                dec += 1
            else:
                unch += 1
            if prev > 0 and v[7] > 0:
                up, dn = limit_prices(prev)
                if chg > 0 and close >= up - 1e-6:
                    lu += 1
                    lus.add(c)
                elif chg < 0 and close <= dn + 1e-6:
                    ld += 1
            hist = [x for x in closes[c][max(0, i - 19): i + 1] if x]
            if len(hist) >= 20:
                tot20 += 1
                if close > sum(hist) / len(hist):
                    above += 1
                prior = hist[:-1]
                if close > max(prior):
                    nh += 1
                elif close < min(prior):
                    nl += 1
        limit_up.append(lus)
        mchg = sum(x[1] for x in d.get("m", {}).values())
        mbal = sum(x[0] for x in d.get("m", {}).values())
        sbal = sum(x[2] for x in d.get("m", {}).values())
        ix = d.get("ix") or [None, None]
        rows_atm.append({"d": d["date"], "ix": ix[0], "ixPct": ix[1], "adv": adv, "dec": dec, "unch": unch,
                         "lu": lu, "ld": ld, "above20": round(above / tot20 * 100, 1) if tot20 else None,
                         "nh": nh if tot20 else None, "nl": nl if tot20 else None,
                         "value": round(value / 1e8), "mBal": mbal or None, "mChg": mchg if d.get("m") else None,
                         "sBal": sbal or None})
    # 氣氛分數：各指標在這段期間的百分位平均
    vals = {
        "breadth": [r["adv"] / max(1, r["adv"] + r["dec"]) for r in rows_atm],
        "limits": [r["lu"] - r["ld"] for r in rows_atm],
        "trend": [r["above20"] for r in rows_atm],
        "highs": [(r["nh"] - r["nl"]) if r["nh"] is not None else None for r in rows_atm],
        "turnover": [],
        "margin": [r["mChg"] for r in rows_atm],
    }
    for i, r in enumerate(rows_atm):
        prev = [x["value"] for x in rows_atm[max(0, i - 20): i]]
        vals["turnover"].append(r["value"] / (sum(prev) / len(prev)) if prev else None)
    for i, r in enumerate(rows_atm):
        parts = {k: round(_rank(v, v[i])) for k, v in vals.items() if v[i] is not None}
        r["parts"] = parts
        r["score"] = round(sum(parts.values()) / len(parts)) if parts else None
        r["label"] = label(r["score"]) if r["score"] is not None else None
    (out / "atmosphere.json").write_text(json.dumps({"days": rows_atm}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ── 隔日追蹤 ─────────────────────────────────────
    nd_rows = []
    for i, d in enumerate(days):
        for c in sorted(limit_up[i]):
            v = d["q"][c]
            streak = 1
            while i - streak >= 0 and c in limit_up[i - streak]:
                streak += 1
            one = v[2] == v[3] == v[4] == v[5]
            row = [d["date"], c, v[0], v[1], v[5], round((v[8] or 0) / 1e8, 2), streak, 1 if one else 0]
            if i + 1 < n and c in days[i + 1]["q"]:
                w = days[i + 1]["q"][c]
                row += [pct(v[5], w[2]), pct(v[5], w[3]), pct(v[5], w[4]), pct(v[5], w[5]), 1 if c in limit_up[i + 1] else 0]
                row.append(pct(v[5], days[i + 3]["q"].get(c, [None] * 6)[5]) if i + 3 < n else None)
            else:
                row += [None, None, None, None, None, None]
            nd_rows.append(row)
    (out / "nextday.json").write_text(json.dumps({
        "cols": ["date", "code", "name", "mkt", "close", "valueYi", "streak", "oneWord", "open", "high", "low", "close1", "limit1", "close3"],
        "rows": nd_rows, "days": [d["date"] for d in days]}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ── 券差偵察 ─────────────────────────────────────
    last = days[-1]
    m_days = [d for d in days if d.get("m")]
    lastm = m_days[-1] if m_days else last
    li = days.index(lastm)

    def back(k, code, field):  # k 天前的融資券欄位
        j = len(m_days) - 1 - k
        return m_days[j]["m"].get(code, [None] * 5)[field] if j >= 0 else None

    def sbl(dd, code):
        x = dd.get("s", {}).get(code)
        return x[3] if x else 0

    short_rows = []
    for c, mv in lastm.get("m", {}).items():
        q = lastm["q"].get(c)
        if not q:
            continue
        mb, mchg, sb, schg, offset = mv
        cl = closes[c]
        vol5 = [days[j]["q"].get(c, [0] * 8)[7] for j in range(max(0, li - 4), li + 1)]
        avgvol = sum(vol5) / len(vol5) if vol5 else 0
        s5 = back(5, c, 2)
        s20 = back(20, c, 2)
        b_now = sbl(lastm, c)
        b5 = sbl(m_days[-6], c) if len(m_days) >= 6 else None
        short_rows.append([
            c, names.get(c, ""), q[1], q[5], pct(cl[li - 5], q[5]) if li >= 5 else None, pct(cl[li - 20], q[5]) if li >= 20 else None,
            mb, mchg, sb, schg, (sb - s5) if s5 is not None else None, (sb - s20) if s20 is not None else None,
            round(sb / mb * 100, 1) if mb else None, round(sb / avgvol, 1) if avgvol else None, offset,
            b_now, (b_now - b5) if b5 is not None else None, round(avgvol),
        ])
        # 個股近 60 天
        hist = []
        for d in m_days[-60:]:
            x = d["m"].get(c)
            qq = d["q"].get(c)
            if x and qq:
                hist.append([d["date"], qq[5], x[0], x[2], sbl(d, c)])
        if sb or b_now:
            (out / "short" / f"{c}.json").write_text(json.dumps({"n": names.get(c), "h": hist}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "short.json").write_text(json.dumps({
        "date": lastm["date"],
        "cols": ["code", "name", "mkt", "close", "chg5", "chg20", "mBal", "mChg", "sBal", "sChg", "sChg5", "sChg20",
                 "ratio", "cover", "offset", "sbl", "sblChg5", "vol5"],
        "rows": short_rows}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"每日行情：{n} 天（{days[0]['date']} ~ {days[-1]['date']}）、隔日追蹤 {len(nd_rows)} 筆、券差 {len(short_rows)} 檔 → public/data/market")
