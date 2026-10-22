"""
週轉率排行與「高週轉隔日黑K」回測 → public/data/turnover.json
  週轉率＝當日成交股數 ÷ 已發行普通股數（data/strategy/shares.json，用最新股數回算歷史，增減資前後會有小誤差）
  假設：週轉率越高代表當沖與短線籌碼越多，隔天容易開高走低（收黑K）
  回測：每天收盤依週轉率排序，看「隔天」的
    黑K率（收盤 < 開盤）、開→收報酬（＝開盤放空、收盤回補的毛報酬取負號）、收→收報酬、開盤跳空
  分組：前 10／20／50 名、十分位，以及前 20 名（成交金額 ≥ 1 億）依當天走勢再細分
  當沖比＝現股當沖成交股數 ÷ 成交股數（data/strategy/daytrade.json），驗證「週轉率高＝當沖多」，並另外依當沖比分組回測
  漲停判斷：收盤價 ≥ 前一日收盤 ×1.1 依升降單位無條件捨去的價格
  排除：ETF 等非普通股、隔天處置中的股票（處置股當沖受限）
  alert：今天週轉率前 20 名（成交 ≥ 1 億）且收漲停的股票，排除隔天處置、今天暫停先賣後買的，給 LINE 推播用
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime
from pathlib import Path

from build_strategy import STOCK, TPE, _load, limit_up, next_trading_day

COST_FULL = 0.435  # 當沖：證交稅 0.15%（當沖減半）＋手續費 0.1425%×2
COST_DISC = 0.23   # 手續費 2.8 折：0.15% ＋ 0.1425%×0.28×2
HIST_DAYS = 20


def build(data_dir: Path, public_dir: Path):
    shares = (_load(data_dir / "strategy" / "shares.json", {}) or {}).get("shares", {})
    if len(shares) < 1000:
        print("週轉率：發行股數資料不足，略過")
        return
    days = []
    for f in sorted((data_dir / "daily").glob("20*.json")):
        doc = _load(f, {})
        if doc.get("q"):
            days.append((doc.get("date", f.stem), doc["q"]))
    if len(days) < 2:
        return
    holidays = set((_load(data_dir / "calendar.json", {}) or {}).get("holidays", []))
    disp: dict[str, list] = {}
    for c, a, b in (_load(data_dir / "strategy" / "disposition.json", {}) or {}).get("items", []):
        disp.setdefault(c, []).append((a, b))

    dtd = (_load(data_dir / "strategy" / "daytrade.json", {}) or {}).get("days", {})

    def dt_of(d):
        x = dtd.get(d) or {}
        if "tw" not in x or "tp" not in x:
            return None, set()
        return {**x["tw"], **x["tp"]}, set(x.get("x", []))

    def disposed(c, d):
        return any(a <= d <= b for a, b in disp.get(c, []))

    def rank(q, d):
        dt, _ = dt_of(d)
        rows = []
        for c, v in q.items():
            if not STOCK.fullmatch(c) or c not in shares:
                continue
            o, cl, chg, vol, val = v[2], v[5], v[6], v[7], v[8]
            if not cl or not vol:
                continue
            prev = cl - chg if chg is not None else None
            rows.append({"code": c, "name": v[0], "mk": "上櫃" if v[1] else "上市", "open": o, "close": cl,
                         "ret": round(chg / prev * 100, 2) if prev else None, "lots": vol,
                         "limit": bool(prev and cl >= limit_up(prev) - 1e-6),
                         "dt": round(min(100.0, dt.get(c, 0) / (vol * 1000) * 100), 1) if dt is not None else None,
                         "valueYi": round((val or 0) / 1e8, 2), "turnover": round(vol * 1000 / shares[c] * 100, 2)})
        rows.sort(key=lambda r: -r["turnover"])
        return rows

    groups: dict[str, dict] = {}
    order: list[str] = []

    def add(k, x, d):
        if k not in groups:
            groups[k] = {"o2c": [], "blk": 0, "c2c": [], "gap": [], "days": {}}
            order.append(k)
        g = groups[k]
        g["o2c"].append(x[0]); g["blk"] += x[1]; g["c2c"].append(x[2]); g["gap"].append(x[3])
        g["days"].setdefault(d, []).append(x[0])

    hist = []
    corr = []

    def spearman(a, b):
        def rk(x):
            o = sorted(range(len(x)), key=lambda i: x[i])
            r = [0.0] * len(x)
            for k, i in enumerate(o):
                r[i] = k
            return r
        ra, rb = rk(a), rk(b)
        return st.correlation(ra, rb) if len(a) > 2 else None

    for t in range(len(days) - 1):
        d, q = days[t]
        d2, q2 = days[t + 1]
        rows = []
        for r in rank(q, d):
            n = q2.get(r["code"])
            if not n or not n[2] or not n[5] or disposed(r["code"], d2):
                continue
            r = {**r, "nx": ((n[5] / n[2] - 1) * 100, n[5] < n[2], (n[5] / r["close"] - 1) * 100, (n[2] / r["close"] - 1) * 100)}
            rows.append(r)
        if not rows:
            continue
        N = len(rows)
        for i, r in enumerate(rows):
            add("全部股票", r["nx"], d)
            if i < 10:
                add("前 10 名", r["nx"], d)
            if i < 20:
                add("前 20 名", r["nx"], d)
            if i < 50:
                add("前 50 名", r["nx"], d)
        for k in range(10):
            for r in rows[k * N // 10:(k + 1) * N // 10]:
                add(f"第 {k + 1} 組", r["nx"], d)
        dts = [r for r in rows if r["dt"] is not None]
        if len(dts) > 100:
            corr.append(spearman([r["turnover"] for r in dts], [r["dt"] for r in dts]))
            bydt = sorted(dts, key=lambda r: -r["dt"])
            M = len(bydt)
            for k in range(10):
                for r in bydt[k * M // 10:(k + 1) * M // 10]:
                    add(f"當沖第 {k + 1} 組", r["nx"], d)
            for r in [r for r in rows[:20] if r["dt"] is not None]:
                add("週轉前 20 名・當沖比 ≥ 50%" if r["dt"] >= 50 else "週轉前 20 名・當沖比 < 50%", r["nx"], d)
        liq = [r for r in rows if r["valueYi"] >= 1][:20]
        for r in liq:
            add("前 20 名（成交 ≥ 1 億）", r["nx"], d)
            if r["limit"]:
                add("　└ 當天漲停", r["nx"], d)
            elif (r["ret"] or 0) >= 5:
                add("　└ 當天漲 5% 以上（未漲停）", r["nx"], d)
            elif r["close"] > r["open"]:
                add("　└ 當天收紅、漲不到 5%", r["nx"], d)
            else:
                add("　└ 當天收黑或平盤", r["nx"], d)
        hist.append({"date": d, "next": d2, "picks": [{"code": r["code"], "name": r["name"], "turnover": r["turnover"], "ret": r["ret"],
                                                         "o2c": round(r["nx"][0], 2), "black": r["nx"][1], "gap": round(r["nx"][3], 2),
                                                          "limit": r["limit"], "dt": r["dt"]}
                                                        for r in liq]})

    def stat(k):
        g = groups[k]
        n = len(g["o2c"])
        o2c = st.mean(g["o2c"])
        daily = [st.mean(v) for v in g["days"].values()]
        return {"group": k, "n": n, "days": len(daily), "black": round(g["blk"] / n * 100, 1), "o2c": round(o2c, 2),
                "c2c": round(st.mean(g["c2c"]), 2), "gap": round(st.mean(g["gap"]), 2),
                "shortNet": round(-o2c - COST_FULL, 2), "shortNetDisc": round(-o2c - COST_DISC, 2),
                "dayWin": round(sum(1 for x in daily if x < 0) / len(daily) * 100, 1)}

    d0, q0 = days[-1]
    today = rank(q0, d0)
    nxt = next_trading_day(d0, holidays)
    _, nox = dt_of(d0)
    for r in today:
        r["disposed"] = disposed(r["code"], d0) or disposed(r["code"], nxt)
        r["noShort"] = r["code"] in nox
    alert = [r for r in [r for r in today if r["valueYi"] >= 1][:20] if r["limit"] and not r["disposed"] and not r["noShort"]]
    corr = [x for x in corr if x is not None]
    out = {
        "asof": d0, "next": nxt, "updatedAt": datetime.now(TPE).isoformat(timespec="minutes"),
        "from": days[0][0], "costFull": COST_FULL, "costDisc": COST_DISC,
        "today": today[:300], "count": len(today),
        "stats": [stat(k) for k in order if not k.startswith(("第", "當沖第", "週轉前"))],
        "deciles": [stat(f"第 {k} 組") for k in range(1, 11) if f"第 {k} 組" in groups],
        "dtDeciles": [stat(f"當沖第 {k} 組") for k in range(1, 11) if f"當沖第 {k} 組" in groups],
        "dtSplit": [stat(k) for k in ("週轉前 20 名・當沖比 ≥ 50%", "週轉前 20 名・當沖比 < 50%") if k in groups],
        "dtReady": dt_of(d0)[0] is not None,
        "corr": round(st.mean(corr), 2) if corr else None, "corrDays": len(corr),
        "alert": [{k: r[k] for k in ("code", "name", "mk", "close", "ret", "turnover", "dt", "valueYi")} for r in alert],
        "history": list(reversed(hist[-HIST_DAYS:])),
    }
    (public_dir / "turnover.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"週轉率：{d0} 共 {len(today)} 檔，回測 {len(hist)} 天")
