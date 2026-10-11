"""
每檔股票今天在全站觸發的訊號（自選股頁、每日推播共用）→ public/data/signals.json
從其他頁已產生的 public/data/* 讀資料，所以要在其他 build 之後執行。
  {"date": 行情日, "quotes": {代號: [名稱, 收盤, 漲跌%]}, "sig": {代號: [[分類, 文字, 方向(1多/-1空/0中性)], ...]}}
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build(public_dir: Path):
    pub = public_dir
    sig: dict[str, list] = {}
    add = lambda c, cat, text, d=0: sig.setdefault(c, []).append([cat, text, d])  # noqa: E731
    quotes = {}

    scr = _load(pub / "market" / "screener.json", {}) or {}
    names = scr.get("signals", [])
    label = {"ma20up": "站上月線", "ma60up": "站上季線", "bull": "均線多頭排列", "volx2": "爆量", "high_all": "創半年新高",
             "high60": "創 60 日新高", "breakout": "突破整理", "ma60down": "跌破季線", "low60": "創 60 日新低"}
    for r in scr.get("rows", []):
        quotes[r[0]] = [r[1], r[3], r[4]]
        for i in r[13]:
            k = names[i]
            if k in ("bull",):  # 多頭排列太常見，推播時只當參考
                continue
            add(r[0], "技術", label.get(k, k), -1 if k in ("ma60down", "low60") else 1)
    day = scr.get("date")

    nd = _load(pub / "market" / "nextday.json", {}) or {}
    for r in nd.get("rows", []):
        if r[0] == day:
            add(r[1], "漲停", f"漲停{f'（{r[6]} 連板）' if r[6] > 1 else ''}", 1)

    ins = _load(pub / "chips" / "insti.json", {}) or {}
    for r in ins.get("rows", []):
        c, p = r[0], r[3] or 0
        f1, t1 = r[4] or 0, r[5] or 0
        fs, ts = r[20] or 0, r[21] or 0
        if ts >= 3:
            add(c, "法人", f"投信連買 {ts} 天", 1)
        elif ts <= -3:
            add(c, "法人", f"投信連賣 {-ts} 天", -1)
        if fs >= 5:
            add(c, "法人", f"外資連買 {fs} 天", 1)
        elif fs <= -5:
            add(c, "法人", f"外資連賣 {-fs} 天", -1)
        amt = f1 * p * 1000 / 1e8
        if abs(amt) >= 5:
            add(c, "法人", f"外資{'買' if amt > 0 else '賣'}超 {abs(amt):.1f} 億", 1 if amt > 0 else -1)

    sh = _load(pub / "market" / "short.json", {}) or {}
    for r in sh.get("rows", []):
        c, ratio, s5 = r[0], r[12], r[10]
        if ratio and ratio >= 30 and r[8] >= 300:
            add(c, "籌碼", f"券資比 {ratio}%", 0)
        if s5 and r[8] and s5 >= max(500, r[8] * 0.3):
            add(c, "籌碼", f"融券 5 日增 {s5:,} 張", -1)

    rev = _load(pub / "fund" / "revenue.json", {}) or {}
    for r in rev.get("rows", []):
        if r[8]:
            add(r[0], "營收", f"{rev['month'][5:].lstrip('0')} 月創新高（年增 {r[6]:+.1f}%）" if r[6] is not None else "創新高", 1)
        elif r[6] is not None and r[6] <= -30:
            add(r[0], "營收", f"{rev['month'][5:].lstrip('0')} 月年減 {abs(r[6]):.0f}%", -1)

    insider = _load(pub / "insider" / "index.json", {}) or {}
    recent = (date.today() - timedelta(days=7)).isoformat()
    seen = set()
    for t in insider.get("transfers", []):
        if t[0] >= recent and t[1] not in seen:
            seen.add(t[1])
            add(t[1], "內部人", f"申報轉讓（{t[0][5:].replace('-', '/')}，{t[6].split('(')[0].strip()}）", -1)

    core = _load(pub / "etf" / "core.json", {}) or {}
    etf_amt: dict[str, list] = {}
    for _, rows in core.get("changes", []):
        for code, *_x, amt in rows:
            etf_amt.setdefault(code, []).append(amt or 0)
    for c, xs in etf_amt.items():
        tot = sum(xs)
        if abs(tot) >= 1:
            add(c, "ETF", f"{'加碼' if tot > 0 else '減碼'} {abs(tot):.1f} 億（{len([x for x in xs if (x > 0) == (tot > 0)])} 檔 ETF）", 1 if tot > 0 else -1)

    ev = _load(pub / "fund" / "events.json", {}) or {}
    today, week = date.today().isoformat(), (date.today() + timedelta(days=7)).isoformat()
    for r in ev.get("exdiv", []):
        if today <= r[0] <= week:
            add(r[1], "事件", f"{r[0][5:].replace('-', '/')} 除{'息' if r[5] else '權'}{f' {r[5]} 元' if r[5] else ''}", 0)
    for r in ev.get("agm", []):
        if today <= r[0] <= week:
            add(r[1], "事件", f"{r[0][5:].replace('-', '/')} 股東{r[4] or '會'}", 0)
    for r in ev.get("conf", []):
        if today <= r[0] <= week:
            add(r[1], "事件", f"{r[0][5:].replace('-', '/')} 法說會", 0)

    bb = _load(pub / "fund" / "buyback.json", {}) or {}
    for r in bb.get("rows", []):
        if r[10] != "Y" and r[4] == "3":
            add(r[0], "庫藏股", "實施庫藏股護盤中", 1)

    hd = _load(pub / "chips" / "holders.json", {}) or {}
    for r in hd.get("rows", []):
        if r[4] is not None and abs(r[4]) >= 1:
            add(r[0], "大戶", f"千張大戶週{'增' if r[4] > 0 else '減'} {abs(r[4]):.2f}%", 1 if r[4] > 0 else -1)

    out = {"date": day, "quotes": quotes, "sig": sig}
    (pub / "signals.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"訊號彙整：{len(sig)} 檔有訊號 → public/data/signals.json")
