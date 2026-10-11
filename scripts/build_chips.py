"""
籌碼頁資料 → public/data/chips/
  insti.json + insti/<代號>.json   三大法人：各股 1/5/20/60 日買賣超、連續買超天數，全市場每日買賣超金額
  futures.json                     期貨選擇權籌碼：台指期／小台法人未平倉、選擇權買賣權、P/C ratio、散戶小台多空比
  holders.json + holders/<代號>.json  集保大戶持股：千張大戶比例與週變化
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

STOCK = re.compile(r"[1-9]\d{3}")


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _w(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _closes(data_dir: Path) -> dict[str, dict[str, float]]:
    out = {}
    for f in sorted((data_dir / "daily").glob("20*.json"))[-70:]:
        d = _load(f, {})
        out[d.get("date", f.stem)] = {c: v[5] for c, v in d.get("q", {}).items()}
    return out


def build_insti(data_dir: Path, out: Path, closes: dict):
    files = sorted((data_dir / "insti").glob("20*.json"))[-60:]
    days = [(f.stem, _load(f, {})) for f in files]
    days = [(d, x) for d, x in days if len(x) > 500]
    if not days:
        return
    dates = [d for d, _ in days]
    last_close = closes.get(dates[-1]) or (list(closes.values())[-1] if closes else {})
    names: dict[str, tuple[str, int]] = {}
    series: dict[str, list] = {}
    market = []
    for i, (d, x) in enumerate(days):
        cl = closes.get(d, last_close)
        tot = [0.0, 0.0, 0.0]
        for c, v in x.items():
            if c.startswith("_"):
                continue
            names[c] = (v[0], v[1])
            series.setdefault(c, [None] * len(days))[i] = v[2:6]
            p = cl.get(c)
            if p and STOCK.fullmatch(c):
                for k in range(3):
                    tot[k] += v[2 + k] * p * 1000 / 1e8
        market.append([d, *(round(t, 1) for t in tot)])

    def win(s, n, k):
        vals = [x[k] for x in s[-n:] if x]
        return sum(vals) if vals else 0

    def streak(s, k):
        n = 0
        for x in reversed(s):
            if not x or x[k] <= 0:
                break
            n += 1
        if n == 0:
            for x in reversed(s):
                if not x or x[k] >= 0:
                    break
                n -= 1
        return n

    rows = []
    for c, s in series.items():
        if not s[-1]:
            continue
        p = last_close.get(c)
        rows.append([c, names[c][0], names[c][1], p,
                     *s[-1], *(win(s, 5, k) for k in range(4)), *(win(s, 20, k) for k in range(4)), *(win(s, 60, k) for k in range(4)),
                     streak(s, 0), streak(s, 1)])
        _w(out / "insti" / f"{c}.json", [[dates[i], *(s[i] or [None] * 4), (closes.get(dates[i]) or {}).get(c)] for i in range(len(dates))])
    _w(out / "insti.json", {"date": dates[-1], "days": len(dates), "market": market, "rows": rows})
    print(f"  三大法人：{len(dates)} 天、{len(rows)} 檔")


def build_futures(data_dir: Path, out: Path):
    db = _load(data_dir / "futures" / "daily.json", {}) or {}
    rows = []
    for d in sorted(db):
        x = db[d]
        txf, mtx, txo = x.get("txf", {}), x.get("mtx", {}), x.get("txo", {})
        inst_mtx = sum((mtx.get(k) or [0])[0] or 0 for k in "ftd") if mtx else None
        retail = round(-inst_mtx / x["mtxOI"] * 100, 2) if mtx and x.get("mtxOI") else None
        g = lambda o, k, i=0: (o.get(k) or [None, None])[i]  # noqa: E731
        rows.append([d, x.get("px"), g(txf, "f"), g(txf, "t"), g(txf, "d"), g(txf, "f", 1),
                     g(mtx, "f"), retail,
                     (txo.get("f", {}).get("c") or [None, None])[1], (txo.get("f", {}).get("p") or [None, None])[1],
                     *(x.get("pc") or [None, None])])
    _w(out / "futures.json", {"cols": ["date", "px", "txfF", "txfT", "txfD", "txfFAmt", "mtxF", "retail", "txoFCallAmt", "txoFPutAmt", "pcVol", "pcOI"], "rows": rows})
    print(f"  期貨籌碼：{len(rows)} 天")


def build_holders(data_dir: Path, out: Path, names: dict):
    files = sorted((data_dir / "holders").glob("20*.json"))
    weeks = [(f.stem, _load(f, {})) for f in files]
    weeks = [(d, x) for d, x in weeks if x]
    if not weeks:
        return
    latest_d, latest = weeks[-1]
    rows = []
    for c, v in latest.items():
        if not STOCK.fullmatch(c):
            continue
        hist = [(d, x[c]) for d, x in weeks if c in x]
        prev1 = hist[-2][1] if len(hist) >= 2 else None
        prev4 = hist[-5][1] if len(hist) >= 5 else (hist[0][1] if len(hist) >= 2 else None)
        diff = lambda a, b, k: round(a[k] - b[k], 2) if b else None  # noqa: E731
        rows.append([c, names.get(c, ""), v[0], v[1], diff(v, prev1, 1), diff(v, prev4, 1), v[2], v[3], diff(v, prev4, 3),
                     (v[0] - prev4[0]) if prev4 else None, len(hist)])
        if len(hist) >= 2:
            _w(out / "holders" / f"{c}.json", [[d, *x[:4]] for d, x in hist])
    _w(out / "holders.json", {"week": latest_d, "weeks": [d for d, _ in weeks], "rows": rows})
    print(f"  集保大戶：{len(weeks)} 週、{len(rows)} 檔")


def build(data_dir: Path, public_dir: Path):
    out = public_dir / "chips"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    closes = _closes(data_dir)
    names = {}
    for f in sorted((data_dir / "daily").glob("20*.json"))[-1:]:
        names = {c: v[0] for c, v in (_load(f, {}) or {}).get("q", {}).items()}
    build_insti(data_dir, out, closes)
    build_futures(data_dir, out)
    build_holders(data_dir, out, names)
    print("籌碼 → public/data/chips")
