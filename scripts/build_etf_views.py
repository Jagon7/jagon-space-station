#!/usr/bin/env python3
"""
把 data/etf/ 的原始持股、規模、收盤價整理成 ETF 頁用的 JSON（建置網站前執行，只用標準函式庫）。

輸出到 public/data/etf/：
    core.json    ETF 清單、個股被哪些 ETF 持有、每檔 ETF 與前一份持股的增減
    active.json  主動式 ETF 最近 ACTIVE_EVENTS 次持股變化（原始、扣除申購贖回）
    aum.json     全體上市櫃 ETF 規模、資金流入排行
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data")) / "etf"
OUT_DIR = ROOT / "public" / "data" / "etf"
ACTIVE_EVENTS = 20
FLOW_DAYS = 5


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(name: str, obj):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def is_tw(code: str) -> bool:
    return " " not in code


class Prices:
    def __init__(self, doc):
        self.names: dict[str, str] = doc.get("names", {})
        self.days: dict[str, dict[str, float]] = doc.get("days", {})
        self.dates = sorted(self.days)

    def close(self, code: str, day: str | None = None):
        """day 當天（或之前最近一天）的收盤價；沒有就用最新。"""
        if day:
            for d in reversed(self.dates):
                if d <= day and code in self.days[d]:
                    return self.days[d][code]
        for d in reversed(self.dates):
            if code in self.days[d]:
                return self.days[d][code]
        return None

    @property
    def latest(self):
        return self.dates[-1] if self.dates else None


def units_lookup(aum_doc):
    """{etf: {date: units}}，從證交所淨值揭露。"""
    out: dict[str, dict[str, float]] = {}
    for day, rows in aum_doc.get("days", {}).items():
        for code, r in rows.items():
            out.setdefault(code, {})[day] = r[1]
    return out


def load_etfs():
    etfs = []
    for p in sorted((DATA_DIR / "holdings").glob("*.json")):
        doc = read_json(p, None)
        if doc and doc.get("snapshots"):
            etfs.append(doc)
    # 主動式放後面、各自依規模（沒有規模的放最後）
    return etfs


def diff_rows(prev, curr):
    """[[stock, name, prevShares, currShares, prevW, currW]]，只列有變動的。"""
    p = {h[0]: h for h in prev["h"]}
    c = {h[0]: h for h in curr["h"]}
    out = []
    for code in set(p) | set(c):
        ps = (p.get(code) or [None, None, 0, 0])[2] or 0
        cs = (c.get(code) or [None, None, 0, 0])[2] or 0
        if ps == cs:
            continue
        name = (c.get(code) or p.get(code))[1]
        out.append([code, name, ps, cs, (p.get(code) or [0, 0, 0, None])[3], (c.get(code) or [0, 0, 0, None])[3]])
    return out


def round_or_none(v, n=2):
    return None if v is None else round(v, n)


def build():
    prices = Prices(read_json(DATA_DIR / "prices.json", {}))
    aum_doc = read_json(DATA_DIR / "aum.json", {})
    units_by = units_lookup(aum_doc)
    status = read_json(DATA_DIR / "status.json", {}).get("etfs", {})
    docs = load_etfs()

    aum_days = sorted(aum_doc.get("days", {}))
    latest_aum = aum_doc["days"][aum_days[-1]] if aum_days else {}

    def stock_name(code, fallback):
        return prices.names.get(code) or fallback

    # ── ETF 清單 ────────────────────────────────────────────
    def etf_aum(doc):
        s = doc["snapshots"][-1]
        if doc["code"] in latest_aum:
            r = latest_aum[doc["code"]]
            return r[1] * r[3]
        return s.get("aum") or 0

    docs.sort(key=lambda d: (d["kind"] == "active", -etf_aum(d)))
    etfs = []
    for d in docs:
        s = d["snapshots"]
        st = status.get(d["code"], {})
        etfs.append({
            "c": d["code"], "n": d["name"], "i": d["issuer"], "k": "A" if d["kind"] == "active" else "P",
            "d": s[-1]["date"], "pd": s[-2]["date"] if len(s) > 1 else None,
            "aum": round(etf_aum(d)), "cnt": len(s[-1]["h"]),
            "ok": st.get("ok", True), "hist": len(s),
        })

    # ── 個股被哪些 ETF 持有 ────────────────────────────────
    holders: dict[str, list] = {}
    names: dict[str, str] = {}
    changes = []
    for idx, d in enumerate(docs):
        snaps = d["snapshots"]
        curr = snaps[-1]
        prev = snaps[-2] if len(snaps) > 1 else None
        prev_map = {h[0]: h[2] or 0 for h in prev["h"]} if prev else None
        for code, name, shares, weight in curr["h"]:
            names.setdefault(code, stock_name(code, name))
            close = prices.close(code, curr["date"]) if is_tw(code) else None
            value = shares * close / 1e8 if close and shares else None
            diff = (shares or 0) - prev_map.get(code, 0) if prev_map is not None else None
            holders.setdefault(code, []).append([idx, shares, weight, round_or_none(value, 4), diff])
        if prev:
            rows = []
            for code, name, ps, cs, pw, cw in diff_rows(prev, curr):
                names.setdefault(code, stock_name(code, name))
                close = prices.close(code, curr["date"]) if is_tw(code) else None
                val = (cs - ps) * close / 1e8 if close else None
                rows.append([code, ps, cs, pw, cw, round_or_none(val, 4)])
                if code not in {h[0] for h in curr["h"]}:  # 剔除的股票也要查得到
                    holders.setdefault(code, []).append([idx, 0, 0, 0, -ps])
            rows.sort(key=lambda r: -abs(r[5] or 0))
            changes.append([idx, rows])

    close_map = {c: prices.close(c) for c in names if is_tw(c)}
    write_json("core.json", {
        "priceDate": prices.latest, "etfs": etfs, "names": names,
        "close": {k: v for k, v in close_map.items() if v},
        "holders": holders, "changes": changes,
    })

    # ── 主動式：最近幾次變化 ─────────────────────────────────
    events = {}
    for idx, d in enumerate(docs):
        if d["kind"] != "active":
            continue
        snaps = d["snapshots"]
        units = units_by.get(d["code"], {})
        out = []
        for prev, curr in list(zip(snaps, snaps[1:]))[-ACTIVE_EVENTS:]:
            u0 = prev.get("units") or units.get(prev["date"])
            u1 = curr.get("units") or units.get(curr["date"])
            ratio = u1 / u0 if u0 and u1 else 1.0
            pmap = {h[0]: h[2] or 0 for h in prev["h"]}
            cmap = {h[0]: h[2] or 0 for h in curr["h"]}
            rows = []
            for code in set(pmap) | set(cmap):
                if not is_tw(code):
                    continue
                ps, cs = pmap.get(code, 0), cmap.get(code, 0)
                raw = cs - ps
                adj = round(cs - ps * ratio)
                if raw == 0 and adj == 0:
                    continue
                names.setdefault(code, stock_name(code, code))
                rows.append([code, raw, adj, prices.close(code, curr["date"])])
            out.append([curr["date"], prev["date"], round(ratio, 6), rows])
        events[idx] = out
    write_json("active.json", {"events": events, "names": names})

    # ── 全體 ETF 規模 ───────────────────────────────────────
    types = aum_doc.get("types", {})
    tracked = {d["code"] for d in docs}
    rows = []
    if aum_days:
        today, prev_day = aum_days[-1], (aum_days[-2] if len(aum_days) > 1 else None)
        recent = aum_days[-FLOW_DAYS:]
        for code, r in latest_aum.items():
            name, units, du, nav, prem = r
            aum = units * nav
            flow5 = sum(aum_doc["days"][dd][code][2] * aum_doc["days"][dd][code][3]
                        for dd in recent if code in aum_doc["days"][dd])
            prev_r = aum_doc["days"][prev_day].get(code) if prev_day else None
            daum = aum - prev_r[1] * prev_r[3] if prev_r else None
            rows.append([code, prices.names.get(code) or short_name(name), categorize(code, types.get(code, "")),
                         round(aum), nav, units, du, round(du * nav), round(flow5), round_or_none(daum, 0),
                         prem, code in tracked])
        rows.sort(key=lambda r: -r[3])
        write_json("aum.json", {"date": today, "prev": prev_day, "nFlow": len(recent), "rows": rows})
    else:
        write_json("aum.json", {"date": None, "prev": None, "nFlow": 0, "rows": []})

    print(f"ETF 頁資料：{len(etfs)} 檔 ETF、{len(holders)} 檔個股、{len(changes)} 檔有前一份、"
          f"AUM {len(rows)} 檔 → {OUT_DIR.relative_to(ROOT)}")


def short_name(full: str) -> str:
    for cut in ("證券投資信託基金", "指數股票型", "ETF"):
        i = full.find(cut)
        if i > 0:
            full = full[:i]
    return full


def categorize(code: str, fund_type: str) -> str:
    t = fund_type or ""
    suffix = code[-1] if code[-1].isalpha() else ""
    if "槓桿" in t or "反向" in t or suffix in ("L", "R"):
        return "槓桿反向"
    if "期貨" in t or suffix == "U":
        return "期貨商品"
    if "主動" in t or suffix in ("A", "D"):
        return "主動式"
    if "債" in t or suffix == "B":
        return "債券"
    if "國外" in t or "跨國" in t or "海外" in t:
        return "國外股票"
    return "國內股票"


if __name__ == "__main__":
    build()
    sys.exit(0)
