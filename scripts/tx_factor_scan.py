#!/usr/bin/env python3
"""
台指期 09:15 規則：每週自動找因子優化（只在證據夠強時才改，保持目前最有信心的規則為主體）

做法：現行規則（A 缺口回補→MR、B 窄區間→MR、C 開高不補→BO、D 其他→參數）不動；
  逐一嘗試「某分支裡，某個 09:15 前就知道的因子 > 或 < 門檻時，改成另一種做法（BO／MR／不做）」
  因子只用盤中 09:15 程式算得出來的（tx_regime_live.features）
採用門檻（全部都要過，避免幾百個組合裡撈到運氣）：
  1 全期（2020/3 起）每天平均至少多 MIN_GAIN 點，且逐日差異的 t 值 ≥ T_MIN
  2 2020-24、2025 後兩段都變好
  3 逐年滾動（門檻只用前幾年資料的分位數決定）2022 起各年合計變好，且至少 60% 的年份變好
  4 受影響的天數 ≥ 60（兩段各 ≥ 20）
  5 連續 PERSIST 週都通過才採用；已採用的如果 t < 1.5 或任一段變差就撤掉
  6 一次最多採用一條、最多同時 3 條
輸出 data/futures/regime_overrides.json（active＝已採用、pending＝觀察中、history）＋data/futures/factor_scan.json（本週全部候選）
有採用或撤掉時發 LINE
用法：python scripts/tx_factor_scan.py [--dry-run]
"""
from __future__ import annotations

import bisect
import json
import math
import os
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tx_regime_review as trv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
OUT = DATA / "futures" / "factor_scan.json"
SPLIT = "2025-01-01"
MIN_GAIN, T_MIN, PERSIST, MAX_ACTIVE = 1.5, 3.0, 3, 3
FACTORS = {
    "orATR": "開盤區間 ÷ 平均振幅", "gapATR": "跳空 ÷ 平均振幅（＋開高）", "absGapATR": "跳空幅度 ÷ 平均振幅", "vwapCross30": "開盤 30 分 VWAP 穿越次數",
    "rvol30": "開盤 30 分量能 ÷ 20 日平均", "pos915": "09:15 在開盤區間的位置（0 低～1 高）", "prevRangeATR": "前一天振幅 ÷ 平均振幅",
    "prevEff": "前一天效率（單邊程度）", "atrPct": "平均振幅 ÷ 指數 %", "atrPctl": "平均振幅在近 200 天的百分位",
    "nr7": "前一天是 7 日最小振幅", "openOutside": "開在前一天高低點外", "usEvent": "前一晚美國重大事件", "settle": "結算日", "bear": "加權在 60 日均線下（空頭）",
}
PLANS = ("BO", "MR", None)


def enrich(rows: list[dict]) -> None:
    """regime_rows 沒有的：平均振幅百分位、空頭（加權 < 60 日均線，用前一天收盤）"""
    for i, r in enumerate(rows):
        w = [x["atrPct"] for x in rows[max(0, i - 200):i] if x.get("atrPct") is not None]
        r["atrPctl"] = sum(v <= r["atrPct"] for v in w) / len(w) * 100 if len(w) >= 60 and r.get("atrPct") is not None else None
    tw = json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]
    td = [x[0] for x in tw]
    for r in rows:
        j = bisect.bisect_left(td, r["date"])
        c = [x[4] for x in tw[max(0, j - 60):j]]
        r["bear"] = (c[-1] < st.mean(c)) if len(c) == 60 else None
        for k in ("nr7", "openOutside", "usEvent", "settle", "bear"):
            if r.get(k) is not None:
                r[k] = float(bool(r[k]))


def tstat(d: list[float]) -> float:
    if len(d) < 3:
        return 0.0
    sd = st.pstdev(d)
    return st.mean(d) / (sd / math.sqrt(len(d))) if sd else 0.0


def evaluate(rows, P, o):
    """o 套在現行規則（含已採用的修正）上，回傳各項檢驗"""
    base = [trv.pnl(r, trv.decide(r, P)[1]) for r in rows]
    P2 = {**P, "overrides": [o] + [x for x in P.get("overrides") or [] if x is not o]}
    new = [trv.pnl(r, trv.decide(r, P2)[1]) for r in rows]
    diff = [b - a for a, b in zip(base, new)]
    hit = [i for i, r in enumerate(rows) if trv.base_decide(r, P)[0] == o["branch"] and trv.match(r, o)]
    h1 = [diff[i] for i, r in enumerate(rows) if r["date"] < SPLIT]
    h2 = [diff[i] for i, r in enumerate(rows) if r["date"] >= SPLIT]
    return {"gain": round(st.mean(diff), 2), "t": round(tstat(diff), 2), "h1": round(st.mean(h1), 2), "h2": round(st.mean(h2), 2),
            "n": len(hit), "n1": sum(1 for i in hit if rows[i]["date"] < SPLIT), "n2": sum(1 for i in hit if rows[i]["date"] >= SPLIT)}


def walk_forward(rows, P, branch, factor, op, q, plan):
    """門檻＝前幾年（該分支）因子值的 q 分位數；2022 起各年獨立評估"""
    years = sorted({r["date"][:4] for r in rows if r["date"] >= "2022"})
    res = []
    for y in years:
        prior = [r[factor] for r in rows if r["date"][:4] < y and r.get(factor) is not None and trv.base_decide(r, P)[0] == branch]
        if len(prior) < 40:
            continue
        th = sorted(prior)[int(len(prior) * q)]
        o = {"branch": branch, "factor": factor, "op": op, "th": th, "plan": plan}
        yr = [r for r in rows if r["date"][:4] == y]
        base = sum(trv.pnl(r, trv.decide(r, P)[1]) for r in yr)
        P2 = {**P, "overrides": [o] + list(P.get("overrides") or [])}
        new = sum(trv.pnl(r, trv.decide(r, P2)[1]) for r in yr)
        res.append((y, round(new - base)))
    return res


def main():
    dry = "--dry-run" in sys.argv
    rows = trv.load(DATA / "futures" / "regime_rows.json", [])
    enrich(rows)
    P = trv.params()["current"]
    state = trv.load(trv.OVERRIDES, {}) or {}
    active, pending, hist = state.get("active") or [], state.get("pending") or {}, state.get("history") or []
    now = datetime.now(TPE)
    cands = []
    for br in ("A", "B", "C", "D"):
        sub = [r for r in rows if trv.base_decide(r, P)[0] == br]
        cur_plan = trv.base_decide(sub[0], P)[1] if sub else None
        for f in FACTORS:
            vals = sorted(r[f] for r in sub if r.get(f) is not None)
            if len(vals) < 100:
                continue
            binary = set(vals) <= {0.0, 1.0}
            ths = [(0.5, 0.5)] if binary else [(vals[int(len(vals) * q)], q) for q in (0.25, 0.33, 0.5, 0.67, 0.75)]
            for th, q in ths:
                for op in (">", "<"):
                    if binary and op == "<":
                        continue
                    for plan in PLANS:
                        if plan == cur_plan:
                            continue
                        o = {"branch": br, "factor": f, "op": op, "th": round(th, 4), "plan": plan}
                        ev = evaluate(rows, P, o)
                        if ev["n"] < 30:
                            continue
                        c = {**o, "label": FACTORS[f], "q": q, **ev}
                        ok = ev["gain"] >= MIN_GAIN and ev["t"] >= T_MIN and ev["h1"] > 0 and ev["h2"] > 0 and ev["n"] >= 60 and ev["n1"] >= 20 and ev["n2"] >= 20
                        if ok:
                            wf = walk_forward(rows, P, br, f, op, q, plan)
                            c["wf"] = wf
                            ok = bool(wf) and sum(x[1] for x in wf) > 0 and sum(x[1] > 0 for x in wf) >= 0.6 * len(wf)
                        c["pass"] = ok
                        cands.append(c)
    cands.sort(key=lambda c: (-c["pass"], -c["t"]))
    key = lambda c: f"{c['branch']}|{c['factor']}|{c['op']}|{c['q']}|{c['plan']}"  # noqa: E731
    passed = {key(c): c for c in cands if c["pass"]}
    # 觀察中：連續通過的週數
    new_pending = {k: {"weeks": (pending.get(k, {}).get("weeks", 0) + 1), "since": pending.get(k, {}).get("since", now.date().isoformat())} for k in passed}
    changes = []
    # 已採用的重新檢驗
    keep = []
    for o in active:
        ev = evaluate(rows, {**P, "overrides": [x for x in active if x is not o]}, o)
        if ev["t"] < 1.5 or ev["h1"] <= 0 or ev["h2"] <= 0:
            changes.append(("撤掉", o, ev))
            hist.append({"date": now.date().isoformat(), "action": "remove", "rule": o, "eval": ev})
        else:
            o["eval"] = ev
            keep.append(o)
    active = keep
    # 採用：連續 PERSIST 週通過、t 最高的一條（同分支同因子不重複）
    if len(active) < MAX_ACTIVE:
        for k, c in sorted(passed.items(), key=lambda kv: -kv[1]["t"]):
            if new_pending[k]["weeks"] >= PERSIST and not any(o["branch"] == c["branch"] and o["factor"] == c["factor"] for o in active):
                o = {x: c[x] for x in ("branch", "factor", "op", "th", "plan", "label")}
                o.update({"adoptedAt": now.date().isoformat(), "eval": {x: c[x] for x in ("gain", "t", "h1", "h2", "n", "n1", "n2")}, "wf": c.get("wf")})
                active.append(o)
                changes.append(("採用", o, o["eval"]))
                hist.append({"date": now.date().isoformat(), "action": "adopt", "rule": o})
                new_pending.pop(k, None)
                break
    pl = lambda p: p or "不做"  # noqa: E731
    print(f"掃描 {len(cands)} 個候選（{rows[0]['date']}～{rows[-1]['date']}，{len(rows)} 天）；通過全部門檻 {len(passed)} 個；已採用 {len(active)} 條")
    for c in cands[:15]:
        print(f"  {'✅' if c['pass'] else '  '} 分支 {c['branch']}：{c['label']} {c['op']} {c['th']}（{int(c['q'] * 100)} 分位）→ {pl(c['plan'])}｜"
              f"每天 {c['gain']:+.2f} 點 t={c['t']:.2f}（{c['h1']:+.2f}／{c['h2']:+.2f}）影響 {c['n']} 天" + (f" 滾動 {c.get('wf')}" if c.get("wf") else "")
              + (f"｜連續 {new_pending.get(key(c), {}).get('weeks', '-')} 週" if c["pass"] else ""))
    for act, o, ev in changes:
        print(f"{act}：分支 {o['branch']} {o['label']} {o['op']} {o['th']} → {pl(o['plan'])}（每天 {ev['gain']:+.2f}、t={ev['t']}）")
    if dry:
        return 0
    OUT.write_text(json.dumps({"scannedAt": now.isoformat(timespec="minutes"), "n": len(cands), "passed": len(passed),
                               "rules": {"minGain": MIN_GAIN, "tMin": T_MIN, "persist": PERSIST, "maxActive": MAX_ACTIVE},
                               "top": cands[:40]}, ensure_ascii=False, indent=0), encoding="utf-8")
    trv.OVERRIDES.write_text(json.dumps({"updatedAt": now.isoformat(timespec="minutes"), "active": active, "pending": new_pending,
                                         "history": hist[-50:]}, ensure_ascii=False, indent=1), encoding="utf-8")
    if changes:
        from line_flex import Msg
        import notify
        m = Msg("🧪 台指期 09:15 規則：因子修正" + ("採用" if any(a == "採用" for a, _, _ in changes) else "撤掉"), f"{now:%m/%d} 每週因子掃描", accent="#7C3AED",
                url=f"{notify.SITE}/", button="開啟網站")
        for act, o, ev in changes:
            m.kv(f"{act}｜分支 {o['branch']}", f"{o['label']} {o['op']} {o['th']} → {pl(o['plan'])}")
            m.line(f"回測每天 {ev['gain']:+.2f} 點（t={ev['t']}，2020-24 {ev['h1']:+.2f}／2025 後 {ev['h2']:+.2f}），影響 {ev['n']} 天")
        m.note(f"門檻：每天至少多 {MIN_GAIN} 點、t ≥ {T_MIN}、兩段都變好、逐年滾動多數年份變好、連續 {PERSIST} 週通過。主體規則不變。")
        notify.send(m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
