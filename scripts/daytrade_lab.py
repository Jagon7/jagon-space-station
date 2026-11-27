#!/usr/bin/env python3
"""
當沖策略實驗室：每天盤後復盤＋每週自動調參

三個「隔天開盤放空、收盤回補」的當沖策略：
  g85     85g 開高走低：前一天成交金額前 TOP 名、前一天漲停或前 5 日漲 ≥ RUN5%，隔天開高 GAP_LO～GAP_HI% 才做
  tvLimit 高週轉＋漲停：週轉率前 TOP 名（成交 ≥ MINVAL 億）且收漲停
  dtFade  高當沖比＋開高走低：成交 ≥ MINVAL 億、當沖比 ≥ DT_MIN%、收黑K、漲跌 ≥ MIN_RET%
  （都排除隔天處置、暫停先賣後買；開盤跌停放不了空不算；gapMin／gapMax＝隔天開盤跳空要在這個範圍才做，−99／99＝不限）

data/strategy/daytrade_params.json  目前參數＋調整紀錄（build_85g／build_turnover 讀這裡）
data/strategy/daytrade_journal.json 每天推薦的標的（推播前記下）與隔天實際結果
用法：
  python scripts/daytrade_lab.py record   # 從 public/data 的 turnover.json／85g.json 記下明天的推薦（開盤前都可覆蓋）
  python scripts/daytrade_lab.py review   # 有收盤行情的交易日：算每檔開盤空、收盤補的結果
  python scripts/daytrade_lab.py tune     # 用近 TUNE_DAYS 個交易日回測參數組合，明顯比較好才換（每週六）
"""
from __future__ import annotations

import itertools
import json
import os
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_strategy import STOCK, TPE, _load, limit_up  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
PUB = ROOT / "public" / "data"
PARAMS = DATA / "strategy" / "daytrade_params.json"
JOURNAL = DATA / "strategy" / "daytrade_journal.json"
COST = 0.23  # 當沖：證交稅 0.15% ＋ 手續費 2.8 折來回
TUNE_DAYS = 120
NAMES = {"g85": "85g 開高走低", "tvLimit": "高週轉＋漲停", "dtFade": "高當沖比＋開高走低", "gWeak": "空族群弱勢"}
DEFAULT = {
    "g85": {"top": 100, "gapLo": 0.0, "gapHi": 4.0, "run5": 10.0},
    "tvLimit": {"top": 20, "minVal": 1.0, "gapMin": -99.0, "gapMax": 99.0},
    "dtFade": {"dtMin": 60.0, "minVal": 1.0, "minRet": 0.0, "gapMin": -99.0, "gapMax": 99.0},
    "gWeak": {"gapMin": 0.0, "gapMax": 99.0},   # 空族群弱勢（build_group_weak.py）：開平以上才做；不自動調參
}
GRID = {
    "g85": {"top": [50, 100], "gapLo": [0.0, 0.5, 1.0], "gapHi": [3.0, 4.0, 5.0, 6.0], "run5": [8.0, 10.0, 15.0]},
    "tvLimit": {"top": [10, 20, 30], "minVal": [1.0, 3.0, 5.0], "gapMin": [-99.0, 0.0], "gapMax": [3.0, 5.0, 99.0]},
    "dtFade": {"dtMin": [50.0, 55.0, 60.0, 65.0, 70.0], "minVal": [1.0, 3.0], "minRet": [-2.0, 0.0, 2.0], "gapMin": [-99.0, 0.0], "gapMax": [3.0, 5.0, 99.0]},
}
MIN_N = {"g85": 80, "tvLimit": 80, "dtFade": 80}  # 新參數至少要有這麼多筆，而且有訊號的天數不能少於原本的一半（避免名單變太稀）
MIN_GAIN = 0.10  # 新參數的平均淨報酬至少要好 0.10 個百分點才換


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def params() -> dict:
    p = _load(PARAMS, {}) or {}
    cur = {k: {**v, **(p.get("current") or {}).get(k, {})} for k, v in DEFAULT.items()}
    return {"current": cur, "history": p.get("history") or [], "tunedAt": p.get("tunedAt"), "eval": p.get("eval") or {}}


def triggered(strat: str, p: dict, gap: float) -> bool:
    """隔天開盤跳空 gap（%）時這筆會不會做：開跌停放不了空；85g 要落在區間；其他看 gapMin"""
    if gap <= -9.5:
        return False
    if strat == "g85":
        return p["gapLo"] <= gap < p["gapHi"]
    return p.get("gapMin", -99.0) <= gap < p.get("gapMax", 99.0)


# ---------------- 訊號（回測用；跟 build_85g／build_turnover 同一套規則） ----------------

class Market:
    def __init__(self):
        self.days = []
        for f in sorted((DATA / "daily").glob("20*.json")):
            d = _load(f, {})
            if d.get("q"):
                self.days.append((d.get("date", f.stem), d["q"]))
        self.shares = (_load(DATA / "strategy" / "shares.json", {}) or {}).get("shares", {})
        self.dt = (_load(DATA / "strategy" / "daytrade.json", {}) or {}).get("days", {})
        self.disp: dict[str, list] = {}
        for c, a, b in (_load(DATA / "strategy" / "disposition.json", {}) or {}).get("items", []):
            self.disp.setdefault(c, []).append((a, b))

    def disposed(self, c, d):
        return any(a <= d <= b for a, b in self.disp.get(c, []))

    def nox(self, d):
        return set((self.dt.get(d) or {}).get("x", []))

    def dtr(self, d):
        x = self.dt.get(d) or {}
        if "tw" not in x or "tp" not in x:
            return None
        return {**x["tw"], **x["tp"]}

    def signals(self, strat: str, p: dict, i: int) -> list[str]:
        """第 i 天收盤後，明天（i+1）要做的股票"""
        d, q = self.days[i]
        nx = self.nox(d)
        if strat == "g85":
            if i < 5:
                return []
            q1, q5 = self.days[i - 1][1], self.days[i - 5][1]
            top = sorted((c for c in q if STOCK.fullmatch(c) and q[c][5]), key=lambda c: -(q[c][8] or 0))[:int(p["top"])]
            out = []
            for c in top:
                cl, b1, b5 = q[c][5], (q1.get(c) or [0] * 6)[5], (q5.get(c) or [0] * 6)[5]
                if not b1 or not b5:
                    continue
                if ((cl / b1 - 1) * 100 >= 9.5 or (cl / b5 - 1) * 100 >= p["run5"]) and c not in nx:
                    out.append(c)
            return out
        dt = self.dtr(d)
        rows = []
        for c, v in q.items():
            if not STOCK.fullmatch(c) or c not in self.shares or not v[5] or not v[7] or v[6] is None:
                continue
            prev = v[5] - v[6]
            rows.append((c, v, prev))
        if strat == "tvLimit":
            rows = [r for r in rows if (r[1][8] or 0) / 1e8 >= p["minVal"]]
            rows.sort(key=lambda r: -(r[1][7] * 1000 / self.shares[r[0]]))
            return [c for c, v, prev in rows[:int(p["top"])] if prev and v[5] >= limit_up(prev) - 1e-6 and c not in nx]
        if strat == "dtFade":
            if dt is None:
                return []
            out = []
            for c, v, prev in rows:
                r = min(100.0, dt.get(c, 0) / (v[7] * 1000) * 100)
                ret = (v[6] / prev * 100) if prev else 0
                if (v[8] or 0) / 1e8 >= p["minVal"] and r >= p["dtMin"] and v[2] and v[5] < v[2] and ret >= p["minRet"] and c not in nx:
                    out.append(c)
            return out
        return []

    def trade(self, strat: str, p: dict, i: int, c: str):
        """第 i+1 天的結果：開盤跳空、是否觸發、開盤空收盤補的報酬（%，未扣成本）"""
        d0, q0 = self.days[i]
        d1, q1 = self.days[i + 1]
        r = q1.get(c)
        if not r or not r[2] or not r[5] or self.disposed(c, d1):
            return None
        gap = (r[2] / q0[c][5] - 1) * 100
        trig = triggered(strat, p, gap)
        return {"gap": gap, "trig": trig, "ret": -(r[5] / r[2] - 1) * 100}


def evaluate(m: Market, strat: str, p: dict, lo: int, hi: int) -> dict:
    rets, by_day = [], {}
    for i in range(lo, hi):
        for c in m.signals(strat, p, i):
            t = m.trade(strat, p, i, c)
            if t and t["trig"]:
                rets.append(t["ret"])
                by_day.setdefault(i, []).append(t["ret"])
    if not rets:
        return {"n": 0}
    half = (lo + hi) // 2
    a = [x for i, v in by_day.items() if i < half for x in v]
    b = [x for i, v in by_day.items() if i >= half for x in v]
    net = st.mean(rets) - COST
    return {"n": len(rets), "days": len(by_day), "avg": round(st.mean(rets), 3), "net": round(net, 3),
            "win": round(sum(x > 0 for x in rets) / len(rets) * 100, 1),
            "h1": round(st.mean(a) - COST, 3) if a else None, "h2": round(st.mean(b) - COST, 3) if b else None,
            "sd": round(st.pstdev(rets), 3)}


def tune():
    m = Market()
    P = params()
    hi = len(m.days) - 1
    lo = max(5, hi - TUNE_DAYS)
    now = datetime.now(TPE)
    ev_all = {}
    for strat, grid in GRID.items():
        cur = P["current"][strat]
        base = evaluate(m, strat, cur, lo, hi)
        best, best_p = base, cur
        tried = 0
        for combo in itertools.product(*grid.values()):
            p = dict(zip(grid.keys(), combo))
            if strat == "g85" and p["gapLo"] >= p["gapHi"]:
                continue
            tried += 1
            r = evaluate(m, strat, p, lo, hi)
            # 條件：樣本夠、前後半段都賺、前後半段都比目前參數好、整體好至少 MIN_GAIN（避免只是剛好配到這段行情）
            if (r["n"] >= MIN_N[strat] and r["days"] >= 0.5 * (base.get("days") or 0) and (r["h1"] or -9) > 0 and (r["h2"] or -9) > 0
                    and (r["h1"] or -9) > (base.get("h1") or -9) and (r["h2"] or -9) > (base.get("h2") or -9)
                    and r["net"] > (best.get("net") or -9) + (MIN_GAIN if best is base else 0)):
                best, best_p = r, p
        ev_all[strat] = {"current": base, "best": best, "tried": tried, "from": m.days[lo][0], "to": m.days[hi][0]}
        if best_p is not cur and best_p != cur:
            P["history"].append({"date": now.date().isoformat(), "strategy": strat, "from": cur, "to": best_p,
                                 "reason": f"近 {hi - lo} 個交易日：淨報酬 {base.get('net')}% → {best['net']}%（{best['n']} 筆，前後半段 {best['h1']}%／{best['h2']}%）"})
            P["current"][strat] = best_p
            log(f"{NAMES[strat]}：參數 {cur} → {best_p}（淨 {base.get('net')} → {best['net']}）")
        else:
            log(f"{NAMES[strat]}：維持 {cur}（淨 {base.get('net')}%，{base.get('n')} 筆；試了 {tried} 組沒有明顯更好的）")
    PARAMS.write_text(json.dumps({"current": P["current"], "tunedAt": now.isoformat(timespec="minutes"), "eval": ev_all,
                                  "history": P["history"][-50:]}, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- 每天的推薦紀錄與復盤 ----------------

def record():
    """把 public/data 裡明天的推薦記下來（就是推播用的那份）；開盤後就不再改"""
    j = _load(JOURNAL, {}) or {}
    now = datetime.now(TPE)
    tv = _load(PUB / "turnover.json", {}) or {}
    g = _load(PUB / "85g.json", {}) or {}
    P = params()["current"]
    add = {}
    if tv.get("next") and tv.get("dtReady"):
        add.setdefault(tv["next"], {})["tvLimit"] = [{"code": r["code"], "name": r["name"], "ref": r["close"]} for r in tv.get("alert") or []]
        add[tv["next"]]["dtFade"] = [{"code": r["code"], "name": r["name"], "ref": r["close"]} for r in tv.get("dtAlert") or []]
    gw = _load(PUB / "group_weak.json", {}) or {}
    if gw.get("next"):
        add.setdefault(gw["next"], {})["gWeak"] = [{"code": c["code"], "name": c["name"], "ref": c["close"]} for c in gw.get("cand", [])]
    if g.get("next"):
        add.setdefault(g["next"], {})["g85"] = [{"code": c["code"], "name": c["name"], "ref": c["close"]}
                                               for c in sorted((c for c in g.get("cand", []) if not c.get("noShort")), key=lambda c: c.get("rank") or 999)[:10]]
    for d, v in add.items():
        if d < now.date().isoformat() or (d == now.date().isoformat() and now.hour >= 9):
            continue  # 已經開盤：推薦定案，不改
        day = j.setdefault(d, {"picks": {}, "params": {}})
        for k, picks in v.items():
            day["picks"][k] = picks
            day["params"][k] = P.get(k, DEFAULT[k])
        log(f"記錄 {d} 推薦：" + "、".join(f"{NAMES[k]} {len(x)} 檔" for k, x in v.items()))
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(dict(sorted(j.items())[-250:]), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def review() -> list[str]:
    """有收盤行情的推薦日 → 算結果；回傳這次新復盤的日期"""
    j = _load(JOURNAL, {}) or {}
    done = []
    for d, day in j.items():
        if day.get("result"):
            continue
        q = (_load(DATA / "daily" / f"{d}.json", {}) or {}).get("q")
        if not q:
            continue
        res = {}
        for k, picks in day["picks"].items():
            p = day["params"].get(k) or DEFAULT[k]
            rows = []
            for x in picks:
                r = q.get(x["code"])
                if not r or not r[2] or not r[5]:
                    rows.append({**x, "status": "沒有成交"})
                    continue
                gap = (r[2] / x["ref"] - 1) * 100
                trig = triggered(k, p, gap)
                ret = -(r[5] / r[2] - 1) * 100
                rows.append({**x, "open": r[2], "high": r[3], "low": r[4], "close": r[5], "gap": round(gap, 2), "trig": trig,
                             "ret": round(ret, 2), "net": round(ret - COST, 2), "mae": round((r[3] / r[2] - 1) * 100, 2),
                             "status": ("開跌停放不了空" if gap <= -9.5 else "未觸發（開盤條件不符）" if not trig else "賺" if ret - COST > 0 else "賠")})
            res[k] = rows
        day["result"] = res
        day["reviewedAt"] = datetime.now(TPE).isoformat(timespec="minutes")
        done.append(d)
        log(f"復盤 {d}：" + "；".join(f"{NAMES[k]} " + "、".join(f"{r['name']} {r.get('net', 0):+.2f}%" for r in v if r.get("trig")) for k, v in res.items()))
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return done


def live_stats(j: dict, k: str, last: int = 20) -> dict:
    """實盤紀錄（推播過的標的）最近 last 個交易日的結果"""
    days = [d for d in sorted(j) if (j[d].get("result") or {}).get(k) is not None][-last:]
    xs = [r["net"] for d in days for r in j[d]["result"][k] if r.get("trig") and r.get("net") is not None]
    return {"days": len(days), "n": len(xs), "avg": round(st.mean(xs), 2) if xs else None,
            "win": round(sum(x > 0 for x in xs) / len(xs) * 100, 1) if xs else None, "sum": round(sum(xs), 2) if xs else None}


def backfill(n: int = 20):
    """沒有實盤紀錄的最近 n 個交易日：用當時的預設規則重建推薦（標記 sim），讓復盤一開始就有對照"""
    m = Market()
    j = _load(JOURNAL, {}) or {}
    P = DEFAULT
    for i in range(max(5, len(m.days) - 1 - n), len(m.days) - 1):
        d1 = m.days[i + 1][0]
        if d1 in j:
            continue
        q0 = m.days[i][1]
        day = {"picks": {}, "params": {}, "sim": True}
        for k in ("g85", "tvLimit", "dtFade"):
            codes = m.signals(k, P[k], i)
            if k == "g85":
                codes = sorted(codes, key=lambda c: -(q0[c][8] or 0))[:10]
            if k == "dtFade":
                codes = sorted(codes, key=lambda c: -(q0[c][8] or 0))[:10]
            day["picks"][k] = [{"code": c, "name": q0[c][0], "ref": q0[c][5]} for c in codes]
            day["params"][k] = P[k]
        j[d1] = day
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(dict(sorted(j.items())), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    review()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "review"
    if cmd == "backfill":
        backfill()
    if cmd == "record":
        record()
    elif cmd == "review":
        review()
    elif cmd == "tune":
        tune()
    return 0


if __name__ == "__main__":
    sys.exit(main())
