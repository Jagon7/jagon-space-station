"""
被動式 ETF 每次換股（指數調整）從開始到大致完成花了幾個交易日，由歷史持股推算。

做法：
  1. 相鄰兩份持股的成分股有增減的日子視為「異動日」，間隔不超過 GAP 份的異動日併成同一次換股。
  2. 換股前一份 P 到換股後：新增股（P 沒有、事後有）、刪除股（P 有、事後沒有）。
  3. 申購贖回會讓所有持股等比例增減，所以用「沒有參與換股的股票」股數中位數變化率 r 校正：
       刪除股進度 = 1 - 持股 / (P 時持股 × r)
       新增股進度 = (持股 / r) / (最終持股 / r_final)
  4. 開始 = 第一份有任何進度的持股；完成 = 每檔進度 ≥ 85% 且平均 ≥ 97%（零星殘股不算）。
  5. 生效日取指數審核日程中、追蹤該 ETF 的指數最接近開始日的一次；期間以交易日（持股份數）計，相對生效日。
"""
from __future__ import annotations

from datetime import date
from statistics import median

GAP = 6               # 異動日相隔幾份以內算同一次換股
DONE_EACH = 0.85
DONE_ALL = 0.97


def _tw(code: str) -> bool:
    return " " not in code


def _maps(snaps):
    return [{h[0]: (h[2] or 0) for h in s["h"] if _tw(h[0])} for s in snaps]


def _ratio(m_t, m_p, stable):
    rs = [m_t[c] / m_p[c] for c in stable if m_p.get(c) and m_t.get(c)]
    return median(rs) if rs else 1.0


def detect(snaps: list[dict]) -> list[dict]:
    maps = _maps(snaps)
    n = len(maps)
    change_days = [i for i in range(1, n) if set(maps[i]) != set(maps[i - 1])]
    clusters = []
    for i in change_days:
        if clusters and i - clusters[-1][-1] <= GAP:
            clusters[-1].append(i)
        else:
            clusters.append([i])

    events = []
    for cl in clusters:
        p = cl[0] - 1
        q = cl[-1]
        before, after = set(maps[p]), set(maps[q])
        adds, dels = sorted(after - before), sorted(before - after)
        if not adds and not dels:
            continue
        stable = (before & after) - set(adds) - set(dels)
        fin = min(q + 3, n - 1)
        r_fin = _ratio(maps[fin], maps[p], stable)
        # 換股可能在第一個成分股異動日之前就開始（先減碼刪除股），往前找最多 GAP 份
        lo = max(0, p - GAP)
        start = end = None
        for t in range(lo + 1, fin + 1):
            r = _ratio(maps[t], maps[p], stable) or 1.0
            prog = []
            for c in dels:
                base = maps[p].get(c, 0) or maps[lo].get(c, 0)
                if base:
                    prog.append(min(1.0, max(0.0, 1 - maps[t].get(c, 0) / (base * r))))
            for c in adds:
                final = maps[fin].get(c, 0) / r_fin if r_fin else 0
                prog.append(min(1.0, max(0.0, (maps[t].get(c, 0) / r) / final)) if final else 1.0)
            if not prog:
                continue
            if start is None and max(prog) > 0.05:
                start = t
            if start is not None and min(prog) >= DONE_EACH and sum(prog) / len(prog) >= DONE_ALL:
                end = t
                break
        if start is None:
            continue
        events.append({
            "start": snaps[start]["date"], "end": snaps[end]["date"] if end is not None else None,
            "days": (end - start + 1) if end is not None else None, "iStart": start, "iEnd": end,
            "add": adds, "del": dels, "kind": "regular" if len(adds) + len(dels) >= 3 else "adhoc",
        })
    return events


def _rel(dates: list[str], target: str, d: str) -> int:
    """d 相對 target 的交易日差（以該 ETF 有持股的日子計）。"""
    import bisect
    it = bisect.bisect_left(dates, target)
    idx = bisect.bisect_left(dates, d)
    return idx - it


def build(docs: list[dict], schedule: dict) -> dict:
    eff_by_etf: dict[str, list[str]] = {}
    for r in schedule.get("rows", []):
        for code in r.get("etfs", []):
            eff_by_etf.setdefault(code, []).append(r["effective"])
    index_of = schedule.get("etfIndex", {})

    out = []
    for d in docs:
        if d["kind"] != "passive":
            continue
        snaps = d["snapshots"]
        dates = [s["date"] for s in snaps]
        events = detect(snaps) if len(snaps) >= 5 else []
        for e in events:
            cands = [x for x in eff_by_etf.get(d["code"], [])
                     if abs((date.fromisoformat(x) - date.fromisoformat(e["start"])).days) <= 15]
            if cands:
                eff = min(cands, key=lambda x: abs((date.fromisoformat(x) - date.fromisoformat(e["start"])).days))
                e["eff"] = eff
                e["relStart"] = _rel(dates, eff, e["start"])
                e["relEnd"] = _rel(dates, eff, e["end"]) if e["end"] else None
            e.pop("iStart", None)
            e.pop("iEnd", None)
        out.append({"c": d["code"], "n": d["name"], "i": d["issuer"], "index": index_of.get(d["code"], ""),
                    "hist": len(snaps), "first": dates[0] if dates else None, "events": events})
    return {"etfs": out}
