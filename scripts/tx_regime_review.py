#!/usr/bin/env python3
"""
台指期當日型態（BO／MR）：盤後復盤＋每週自動調參

  review  每天 09:15 推過的訊號（data/futures/regime_journal.json）→ 用當天日盤 1 分 K 算 BO、MR 的實際損益，
          判斷對不對（該做的那個比另一個好）、推 LINE「台指期復盤」
  tune    重跑 research_tx_regime 的每日資料，近 TUNE_DAYS 個交易日回測參數格點；
          前後半段都比現行好、整體每天至少多 MIN_GAIN 點才換 → data/futures/regime_params.json（tx_regime_live.py 讀）
參數：narrow（開盤區間 ≤ 幾倍平均振幅算窄 → MR）、cGap（開高超過幾倍平均振幅才算 C → BO）、dPlan（D：開低沒回補要做什麼）
用法：python scripts/tx_regime_review.py review|tune [--dry-run]
"""
from __future__ import annotations

import itertools
import json
import os
import statistics as st
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
JOURNAL = DATA / "futures" / "regime_journal.json"
PARAMS = DATA / "futures" / "regime_params.json"
STATE = DATA / "notify" / "tx-regime-review-sent.json"
DEFAULT = {"narrow": 0.34, "cGap": 0.0, "dPlan": None}
GRID = {"narrow": [0.25, 0.30, 0.34, 0.40, 0.45], "cGap": [0.0, 0.1, 0.2, 0.35], "dPlan": [None, "BO", "MR"]}
TUNE_DAYS, MIN_GAIN = 500, 1.0  # 近 500 個交易日（約 2 年）；每天平均至少多 1 點


def load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


OVERRIDES = DATA / "futures" / "regime_overrides.json"  # 每週因子掃描（tx_factor_scan.py）通過嚴格驗證後採用的修正


def params() -> dict:
    p = load(PARAMS, {})
    cur = {**DEFAULT, **(p.get("current") or {})}
    cur.pop("overrides", None)
    cur["overrides"] = (load(OVERRIDES, {}) or {}).get("active") or []
    return {"current": cur, "history": p.get("history") or [], "eval": p.get("eval"), "tunedAt": p.get("tunedAt")}


def match(r: dict, o: dict) -> bool:
    v = r.get(o["factor"])
    if v is None:
        return False
    v = float(v)
    return v > o["th"] if o["op"] == ">" else v < o["th"]


def base_decide(r: dict, p: dict):
    """r：gapFilled30、orATR、gapATR → (分支, 做法)"""
    if r["gapFilled30"]:
        return "A", "MR"
    if r["orATR"] <= p["narrow"]:
        return "B", "MR"
    if r["gapATR"] > p["cGap"]:
        return "C", "BO"
    return "D", p.get("dPlan")


def decide(r: dict, p: dict):
    """基本規則，再套用已採用的因子修正（同分支第一個符合的生效）"""
    br, plan = base_decide(r, p)
    for o in p.get("overrides") or []:
        if o["branch"] == br and match(r, o):
            return br, o["plan"]
    return br, plan


def pnl(r: dict, plan):
    return r["bo"] if plan == "BO" else r["mr"] if plan == "MR" else 0.0


def evaluate(rows, p):
    xs = [pnl(r, decide(r, p)[1]) for r in rows]
    h = len(xs) // 2
    return {"n": len(xs), "avg": round(st.mean(xs), 2), "h1": round(st.mean(xs[:h]), 2), "h2": round(st.mean(xs[h:]), 2),
            "trades": sum(1 for r in rows if decide(r, p)[1]), "win": round(sum(x > 0 for x in xs if x) / max(1, sum(1 for x in xs if x)) * 100, 1)}


def tune():
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "research_tx_regime.py")], check=False, capture_output=True)
    rows = load(DATA / "futures" / "regime_rows.json", [])[-TUNE_DAYS:]
    P = params()
    P["current"].pop("overrides", None)  # 基本參數調參不含因子修正（修正另外由 tx_factor_scan 驗證）
    cur = P["current"]
    base = evaluate(rows, cur)
    best, best_p = base, cur
    for combo in itertools.product(*GRID.values()):
        p = dict(zip(GRID.keys(), combo))
        e = evaluate(rows, p)
        if e["h1"] > base["h1"] and e["h2"] > base["h2"] and e["avg"] >= best["avg"] + (MIN_GAIN if best is base else 0) and e["trades"] >= 0.5 * base["trades"]:
            best, best_p = e, p
    now = datetime.now(TPE)
    if best_p != cur:
        P["history"].append({"date": now.date().isoformat(), "from": cur, "to": best_p,
                             "reason": f"近 {len(rows)} 個交易日：每天平均 {base['avg']} → {best['avg']} 點（前後半段 {best['h1']}／{best['h2']}）"})
        print(f"調參：{cur} → {best_p}（{base['avg']} → {best['avg']}）")
    else:
        print(f"維持 {cur}（每天平均 {base['avg']} 點，前後半段 {base['h1']}／{base['h2']}）")
    PARAMS.write_text(json.dumps({"current": best_p, "tunedAt": now.isoformat(timespec="minutes"), "eval": {"current": base, "best": best, "from": rows[0]["date"], "to": rows[-1]["date"]},
                                  "history": P["history"][-30:]}, ensure_ascii=False, indent=1), encoding="utf-8")


def review(dry: bool):
    import research_tx_regime as rr
    j = load(JOURNAL, {})
    day = {}
    for f in sorted((DATA / "futures" / "day").glob("20*.json")):
        for k, v in load(f, {}).items():
            day[k] = {b[0]: b[1:] for b in v["bars"]}
    new = []
    for d, e in sorted(j.items()):
        if e.get("result") or d not in day or len(day[d]) < 250:
            continue
        bo, mr, _, _ = rr.simulate(day[d], e["orh"], e["orl"])
        b = day[d]
        close = b[max(b)][3]
        e["result"] = {"bo": round(bo, 1), "mr": round(mr, 1), "pnl": round(pnl({"bo": bo, "mr": mr}, e.get("plan")), 1),
                       "best": "BO" if bo > mr else "MR", "close": close, "hi": max(x[1] for x in b.values()), "lo": min(x[2] for x in b.values()),
                       "right": (e.get("plan") is None and max(bo, mr) <= 0) or (e.get("plan") == ("BO" if bo > mr else "MR") and max(bo, mr) > 0)}
        new.append(d)
    if not dry:
        JOURNAL.write_text(json.dumps(j, ensure_ascii=False, indent=0), encoding="utf-8")
    if not new:
        print("沒有新的可復盤日")
        return 0
    d = new[-1]
    e = j[d]
    r = e["result"]
    st_ = load(STATE, {"sent": []})
    if d in st_["sent"] and not dry:
        return 0
    from line_flex import Msg, sign_tone
    import notify
    live = [j[k]["result"]["pnl"] for k in sorted(j) if j[k].get("result")][-20:]
    right = [j[k]["result"]["right"] for k in sorted(j) if j[k].get("result")][-20:]
    name = {"BO": "突破（BO）", "MR": "均值回歸（MR）", None: "不做"}
    m = Msg(("【測試】" if dry else "") + "📋 台指期復盤", f"{d[5:7]}/{d[8:10]}・09:15 判斷分支 {e['branch']}：{name[e.get('plan')]}",
            accent="#0F766E", url=f"{notify.SITE}/", button="開啟網站")
    m.kv("今天實際", f"高 {r['hi']:,.0f}／低 {r['lo']:,.0f}／收 {r['close']:,.0f}")
    m.kv("BO 一筆", f"{r['bo']:+,.0f} 點", color=sign_tone(r["bo"]))
    m.kv("MR 一筆", f"{r['mr']:+,.0f} 點", color=sign_tone(r["mr"]))
    m.kv("照訊號做", f"{r['pnl']:+,.0f} 點（{'✅ 判斷正確' if r['right'] else '❌ 判斷錯誤'}，今天較好的是 {r['best']}）", color=sign_tone(r["pnl"]))
    if live:
        m.kv(f"近 {len(live)} 天實績", f"累計 {sum(live):+,.0f} 點・平均 {st.mean(live):+,.0f}・判斷正確 {sum(right)}/{len(right)}", color=sign_tone(sum(live)))
    P = params()
    if P["history"] and P["history"][-1]["date"] >= (date.fromisoformat(d) - timedelta(days=7)).isoformat():
        h = P["history"][-1]
        m.kv(f"🔧 {h['date'][5:]} 調參", "、".join(f"{k} {h['from'].get(k)}→{v}" for k, v in h["to"].items() if h["from"].get(k) != v))
    m.note("每筆扣 3 點成本、13:30 出場；判斷正確＝做的那個策略比另一個好而且有賺（不做的日子兩個都賠才算對）。每週六用近 2 年資料回測檢討參數。")
    print(m.text())
    if dry:
        return 0
    notify.send(m)
    st_["sent"] = (st_["sent"] + [d])[-60:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st_, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "review"
    dry = "--dry-run" in sys.argv
    if cmd == "tune":
        tune()
        return 0
    return review(dry)


if __name__ == "__main__":
    sys.exit(main())
