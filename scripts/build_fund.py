"""
基礎情報頁的資料（data/fund → public/data/fund）：
  revenue.json + revenue/<代號>.json   月營收：最新月份排行（MoM、YoY、創新高、連續成長）與個股 36 個月
  income.json + income/<代號>.json     季報：最新一季單季 EPS、三率與年增，個股 12 季
  selfreport.json                      自結損益：最新月份／季度清單與個股近 24 期
  buyback.json                         庫藏股：執行中與近期，含最新股價
  events.json                          除權息、股東會、法說會（含殖利率試算）
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _w(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def pct(a, b):
    return round((a / b - 1) * 100, 2) if a is not None and b not in (None, 0) and b > 0 else None


def ratio(a, b):
    return round(a / b * 100, 2) if a is not None and b not in (None, 0) else None


def last_prices(data_dir: Path) -> dict[str, float]:
    files = sorted((data_dir / "daily").glob("20*.json"))
    for f in reversed(files):
        d = _load(f, {})
        if d.get("q"):
            return {c: v[5] for c, v in d["q"].items()}
    return {}


def build_revenue(src: Path, out: Path):
    files = sorted((src / "revenue").glob("*.json"))
    months = [(f.stem, _load(f, {})) for f in files]
    months = [(m, d) for m, d in months if len(d) > 500]
    if not months:
        return
    by: dict[str, dict] = {}
    for m, d in months:
        for c, v in d.items():
            by.setdefault(c, {})[m] = v
    latest, cur = months[-1]
    keys = [m for m, _ in months]
    prev_m = keys[-2] if len(keys) > 1 else None
    rows = []
    for c, v in cur.items():
        name, ind, mk, rev, ly, ytd, ytdly, note = v
        hist = by[c]
        prev = hist.get(prev_m, [None] * 4)[3] if prev_m else None
        past = [hist[m][3] for m in keys[:-1] if m in hist and hist[m][3] is not None]
        high = bool(past) and len(past) >= 12 and rev is not None and rev > max(past)
        # 連續年增月數
        streak = 0
        for m in reversed(keys):
            x = hist.get(m)
            if not x or x[3] is None or not x[4] or x[3] <= x[4]:
                break
            streak += 1
        rows.append([c, name, ind, mk, rev, pct(rev, prev), pct(rev, ly), pct(ytd, ytdly), 1 if high else 0, streak, len(past) + 1, note])
        _w(out / "revenue" / f"{c}.json", {"n": name, "h": [[m, hist[m][3], pct(hist[m][3], hist[m][4])] for m in keys if m in hist]})
    _w(out / "revenue.json", {"month": latest, "rows": rows})
    print(f"  月營收：{latest}、{len(rows)} 家")


def _quarter_key(y: int, q: int) -> str:
    return f"{y}Q{q}"


def build_income(src: Path, out: Path):
    files = sorted((src / "income").glob("*.json"))
    cum = {f.stem: _load(f, {}) for f in files}
    cum = {k: v for k, v in cum.items() if len(v) > 300}
    if not cum:
        return
    keys = sorted(cum, key=lambda k: (int(k[:4]), int(k[-1])))

    def single(c, k):
        """年初累計 → 單季：Qn − Q(n−1)；EPS 也相減（近似）"""
        y, q = int(k[:4]), int(k[-1])
        v = cum[k].get(c)
        if not v:
            return None
        if q == 1:
            return v[2:]
        p = cum.get(_quarter_key(y, q - 1), {}).get(c)
        if not p:
            return None
        return [(a - b) if a is not None and b is not None else None for a, b in zip(v[2:], p[2:])]

    latest = keys[-1]
    y, q = int(latest[:4]), int(latest[-1])
    prev_k = _quarter_key(y, q - 1) if q > 1 else _quarter_key(y - 1, 4)
    ly_k = _quarter_key(y - 1, q)
    rows = []
    for c, v in cum[latest].items():
        s = single(c, latest)
        if not s:
            continue
        rev, gp, op, pre, net, eps = s
        sp = single(c, prev_k) or [None] * 6
        sl = single(c, ly_k) or [None] * 6
        m = [ratio(gp, rev), ratio(op, rev), ratio(net, rev)]
        mp = [ratio(sp[1], sp[0]), ratio(sp[2], sp[0]), ratio(sp[4], sp[0])]
        three_up = all(a is not None and b is not None and a > b for a, b in zip(m, mp))
        ytd_ly = cum.get(ly_k, {}).get(c, [None] * 8)[7]
        rows.append([c, v[0], v[1], round(eps, 2) if eps is not None else None, round(sl[5], 2) if sl[5] is not None else None,
                     v[7], ytd_ly, *m, *mp, 1 if three_up else 0, pct(rev, sl[0])])
        hist = []
        for k in keys:
            x = single(c, k)
            if x:
                hist.append([k, x[0], ratio(x[1], x[0]), ratio(x[2], x[0]), ratio(x[4], x[0]), round(x[5], 2) if x[5] is not None else None])
        _w(out / "income" / f"{c}.json", {"n": v[0], "h": hist})
    _w(out / "income.json", {"quarter": latest, "rows": rows})
    print(f"  季報：{latest}、{len(rows)} 家")


def build_selfreport(src: Path, out: Path):
    files = sorted((src / "selfreport").glob("*.json"))
    monthly = {f.stem: _load(f, {}) for f in files if re.fullmatch(r"\d{4}-\d{2}", f.stem)}
    quarterly = {f.stem: _load(f, {}) for f in files if re.fullmatch(r"\d{4}Q\d", f.stem)}
    res = {}
    for kind, docs in (("m", monthly), ("q", quarterly)):
        keys = sorted(k for k, v in docs.items() if v)
        if not keys:
            continue
        latest = keys[-1]
        rows = []
        for c, v in docs[latest].items():
            name, mk, op, ytd_op, pre, ytd_pre, note = v
            ly = (f"{int(latest[:4]) - 1}{latest[4:]}")
            lyv = docs.get(ly, {}).get(c)
            hist = [[k, docs[k][c][4], docs[k][c][2]] for k in keys if c in docs[k]]
            rows.append([c, name, mk, op, ytd_op, pre, ytd_pre, lyv[4] if lyv else None, lyv[5] if lyv else None, note, hist])
        res[kind] = {"period": latest, "periods": keys, "rows": rows}
    _w(out / "selfreport.json", res)
    print(f"  自結損益：月 {res.get('m', {}).get('period')}、季 {res.get('q', {}).get('period')}")


def build_buyback(src: Path, out: Path, prices: dict):
    rows = _load(src / "buyback.json", []) or []
    out_rows = [r + [prices.get(r[0])] for r in rows]
    _w(out / "buyback.json", {"rows": out_rows})
    print(f"  庫藏股：{len(out_rows)} 筆")


def build_events(src: Path, out: Path, prices: dict):
    ev = _load(src / "events.json", {}) or {}
    for r in ev.get("exdiv", []):
        p = prices.get(r[1])
        r.append(p)
        r.append(round(r[5] / p * 100, 2) if p and r[5] else None)
    _w(out / "events.json", ev)
    print(f"  事件：{', '.join(f'{k} {len(v)}' for k, v in ev.items() if isinstance(v, list))}")


def build_stock_index(data_dir: Path, public_dir: Path):
    """個股查詢用：{代號: [名稱, 市場, 產業, 收盤, 漲跌]}"""
    idx: dict[str, list] = {}
    for f in reversed(sorted((data_dir / "daily").glob("20*.json"))):
        d = _load(f, {})
        if d.get("q"):
            for c, v in d["q"].items():
                idx[c] = [v[0], "上櫃" if v[1] else "上市", "", v[5], v[6]]
            idx["_date"] = d["date"]
            break
    revs = sorted((data_dir / "fund" / "revenue").glob("*.json"))
    if revs:
        for c, v in (_load(revs[-1], {}) or {}).items():
            if c in idx:
                idx[c][2] = v[1]
    _w(public_dir / "stocks.json", idx)


def build(data_dir: Path, public_dir: Path):
    src, out = data_dir / "fund", public_dir / "fund"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        print("基礎情報：沒有資料")
        return
    prices = last_prices(data_dir)
    build_stock_index(data_dir, public_dir)
    build_revenue(src, out)
    build_income(src, out)
    build_selfreport(src, out)
    build_buyback(src, out, prices)
    build_events(src, out, prices)
    print("基礎情報 → public/data/fund")
