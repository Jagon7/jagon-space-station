"""
被動式 ETF 每次換股（指數調整）從開始到大致完成花了幾個交易日，由歷史持股推算。

資料：每日持股（data/etf/holdings，約半年）＋ 長期歷史持股（data/etf/history，fetch_etf_history.py 抓的一年多，
平常每 5 個交易日一份、成分股有變動的前後逐日）。

做法：
  1. 相鄰兩份持股的成分股有增減的日子視為「異動日」，相隔 MERGE_DAYS 天內的異動日併成同一次換股。
  2. 換股前一份 P 到換股後：新增股（P 沒有、事後有）、刪除股（P 有、事後沒有）。
  3. 申購贖回會讓所有持股等比例增減，所以用「沒有參與換股的股票」股數中位數變化率 r 校正：
       刪除股進度 = 1 - 持股 / (P 時持股 × r)
       新增股進度 = (持股 / r) / (最終持股 / r_final)
  4. 開始 = 第一份有任何進度的持股；完成 = 每檔進度 ≥ 85% 且平均 ≥ 97%（零星殘股不算）。
     換股期間如果不是逐日都有持股（只有粗掃的資料），不算時長。
  5. 生效日：指數審核日程中追蹤該 ETF 的指數、最接近開始日的一次；日程沒有的，
     富時合編（臺灣50、中型100、臺灣高股息）與 MSCI 依固定規則推估（標示 effEst）。
     天數與期間以交易日計（所有 ETF 有持股的日子合起來當交易日曆）。
"""
from __future__ import annotations

import bisect
import json
from datetime import date, timedelta
from pathlib import Path
from statistics import median

MERGE_DAYS = 14       # 異動日相隔幾個日曆天內算同一次換股（有些 ETF 先買新增股、一週後才賣刪除股）
LOOKBACK_DAYS = 12    # 開始可能早於第一個異動日（先減碼刪除股），往前找幾天
DONE_EACH = 0.85
DONE_ALL = 0.97
DENSE_GAP = 4         # 換股期間相鄰兩份持股最多相隔幾個日曆天才算逐日資料（含週末）

FTSE_TWSE = ("臺灣50", "台灣50", "中型100", "臺灣高股息", "台灣高股息")


def _ratio(m_t, m_p, stable):
    rs = [m_t[c] / m_p[c] for c in stable if m_p.get(c) and m_t.get(c)]
    return median(rs) if rs else 1.0


def _d(s: str) -> date:
    return date.fromisoformat(s)


def detect(dates: list[str], maps: list[dict]) -> list[dict]:
    n = len(maps)
    change = [i for i in range(1, n) if set(maps[i]) != set(maps[i - 1])]
    clusters: list[list[int]] = []
    for i in change:
        if clusters and (_d(dates[i]) - _d(dates[clusters[-1][-1]])).days <= MERGE_DAYS:
            clusters[-1].append(i)
        else:
            clusters.append([i])

    events = []
    for cl in clusters:
        p, q = cl[0] - 1, cl[-1]
        before, after = set(maps[p]), set(maps[q])
        adds, dels = sorted(after - before), sorted(before - after)
        if not adds and not dels:
            continue
        stable = (before & after) - set(adds) - set(dels)
        fin = q
        while fin + 1 < n and (_d(dates[fin + 1]) - _d(dates[q])).days <= 5:
            fin += 1
        r_fin = _ratio(maps[fin], maps[p], stable)
        lo = p
        while lo > 0 and (_d(dates[p]) - _d(dates[lo - 1])).days <= LOOKBACK_DAYS:
            lo -= 1
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
        # 開始前一份到完成之間要逐日都有資料，時長才可信
        s0 = max(start - 1, 0)
        last = end if end is not None else fin
        dense = all((_d(dates[i + 1]) - _d(dates[i])).days <= DENSE_GAP for i in range(s0, last))
        events.append({
            "start": dates[start], "end": dates[end] if end is not None else None,
            "dense": dense, "add": adds, "del": dels,
            "kind": "regular" if len(adds) + len(dels) >= 3 else "adhoc",
        })
    return events


def _third_friday_monday(y: int, m: int) -> date:
    d = date(y, m, 1)
    fridays = [d + timedelta(days=i) for i in range(31) if (d + timedelta(days=i)).month == m
               and (d + timedelta(days=i)).weekday() == 4]
    return fridays[2] + timedelta(days=3)


def _first_weekday(y: int, m: int) -> date:
    d = date(y, m, 1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def estimated_effective(index_name: str, years: range) -> list[str]:
    """富時合編：3、6、9、12 月第三個週五收盤後調整（次一交易日生效）；MSCI：2、5、8、11 月底調整（3、6、9、12 月初生效）。"""
    months = (3, 6, 9, 12)
    if any(k in index_name for k in FTSE_TWSE):
        return [_third_friday_monday(y, m).isoformat() for y in years for m in months]
    if "MSCI" in index_name.upper():
        return [_first_weekday(y, m).isoformat() for y in years for m in months]
    return []


def _load_history(hist_dir: Path, code: str) -> dict[str, dict]:
    try:
        doc = json.loads((hist_dir / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {d: {c: s for c, s in rows} for d, rows in doc.get("snaps", {}).items()}


def build(docs: list[dict], schedule: dict, hist_dir: Path | None = None) -> dict:
    eff_by_etf: dict[str, list[str]] = {}
    for r in schedule.get("rows", []):
        for code in r.get("etfs", []):
            eff_by_etf.setdefault(code, []).append(r["effective"])
    index_of = schedule.get("etfIndex", {})

    merged: dict[str, dict[str, dict]] = {}
    for d in docs:
        if d["kind"] != "passive":
            continue
        snaps = _load_history(hist_dir, d["code"]) if hist_dir else {}
        for s in d["snapshots"]:
            snaps[s["date"]] = {h[0]: (h[2] or 0) for h in s["h"] if " " not in h[0]}
        merged[d["code"]] = snaps
    # 交易日曆：任何一檔 ETF 有持股的日子
    calendar = sorted({day for snaps in merged.values() for day in snaps})

    def tdays(a: str, b: str) -> int:
        return bisect.bisect_left(calendar, b) - bisect.bisect_left(calendar, a)

    out = []
    for d in docs:
        if d["kind"] != "passive":
            continue
        snaps = merged[d["code"]]
        dates = sorted(snaps)
        events = detect(dates, [snaps[x] for x in dates]) if len(dates) >= 5 else []
        index_name = index_of.get(d["code"], "")
        years = range(int(dates[0][:4]), int(dates[-1][:4]) + 2) if dates else range(0)
        official = eff_by_etf.get(d["code"], [])
        estimated = [x for x in estimated_effective(index_name, years) if x not in official]
        for e in events:
            if e.pop("dense"):
                e["days"] = tdays(e["start"], e["end"]) + 1 if e["end"] else None
            else:
                e["days"] = None
                e["coarse"] = True
            near = lambda xs: [x for x in xs if abs((_d(x) - _d(e["start"])).days) <= 15]  # noqa: E731
            cands, est = near(official), False
            if not cands:
                cands, est = near(estimated), True
            if cands and not e.get("coarse"):
                eff = min(cands, key=lambda x: abs((_d(x) - _d(e["start"])).days))
                e["eff"] = eff
                if est:
                    e["effEst"] = True
                e["relStart"] = tdays(eff, e["start"])
                e["relEnd"] = tdays(eff, e["end"]) if e["end"] else None
        out.append({"c": d["code"], "n": d["name"], "i": d["issuer"], "index": index_name,
                    "hist": len(dates), "first": dates[0] if dates else None, "events": events})
    return {"etfs": out}
