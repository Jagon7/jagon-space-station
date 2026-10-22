"""
週轉率排行與「高週轉隔日黑K」回測 → public/data/turnover.json
  週轉率＝當日成交股數 ÷ 已發行普通股數（data/strategy/shares.json，用最新股數回算歷史，增減資前後會有小誤差）
  假設：週轉率越高代表當沖與短線籌碼越多，隔天容易開高走低（收黑K）
  回測：每天收盤依週轉率排序，看「隔天」的
    黑K率（收盤 < 開盤）、開→收報酬（＝開盤放空、收盤回補的毛報酬取負號）、收→收報酬、開盤跳空
  分組：前 10／20／50 名、十分位，以及前 20 名（成交金額 ≥ 1 億）依當天走勢再細分
  排除：ETF 等非普通股、隔天處置中的股票（處置股當沖受限）
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime
from pathlib import Path

from build_strategy import STOCK, TPE, _load, next_trading_day

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

    def disposed(c, d):
        return any(a <= d <= b for a, b in disp.get(c, []))

    def rank(q):
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
    for t in range(len(days) - 1):
        d, q = days[t]
        d2, q2 = days[t + 1]
        rows = []
        for r in rank(q):
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
        liq = [r for r in rows if r["valueYi"] >= 1][:20]
        for r in liq:
            add("前 20 名（成交 ≥ 1 億）", r["nx"], d)
            if (r["ret"] or 0) >= 9.5:
                add("　└ 當天漲停", r["nx"], d)
            elif (r["ret"] or 0) >= 5:
                add("　└ 當天漲 5% 以上（未漲停）", r["nx"], d)
            elif r["close"] > r["open"]:
                add("　└ 當天收紅、漲不到 5%", r["nx"], d)
            else:
                add("　└ 當天收黑或平盤", r["nx"], d)
        hist.append({"date": d, "next": d2, "picks": [{"code": r["code"], "name": r["name"], "turnover": r["turnover"], "ret": r["ret"],
                                                         "o2c": round(r["nx"][0], 2), "black": r["nx"][1], "gap": round(r["nx"][3], 2)}
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
    today = rank(q0)
    for r in today:
        r["disposed"] = disposed(r["code"], d0)
    nxt = next_trading_day(d0, holidays)
    out = {
        "asof": d0, "next": nxt, "updatedAt": datetime.now(TPE).isoformat(timespec="minutes"),
        "from": days[0][0], "costFull": COST_FULL, "costDisc": COST_DISC,
        "today": today[:300], "count": len(today),
        "stats": [stat(k) for k in order if not k.startswith("第")],
        "deciles": [stat(f"第 {k} 組") for k in range(1, 11) if f"第 {k} 組" in groups],
        "history": list(reversed(hist[-HIST_DAYS:])),
    }
    (public_dir / "turnover.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"週轉率：{d0} 共 {len(today)} 檔，回測 {len(hist)} 天")
