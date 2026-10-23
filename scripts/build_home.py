"""
首頁摘要 → public/data/home.json（小檔，首頁 build 時直接讀）
  把散在各頁的「今天最重要的東西」整理在一起：
  pulse   大盤脈搏：加權指數、市場氣氛、風險溫度、VIX、外資現貨／期貨、漲跌停
  alerts  需要注意的警示（紅＝危險、橘＝警戒），每則附連結
  actions 明日行動：波段策略進場與出場、高週轉＋漲停觀察、國際類股龍頭與台股預估
要在其他 build_*.py 之後跑（讀它們的輸出）
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from build_strategy import TPE, _load

STOCK = re.compile(r"[1-9]\d{3}")


def build(data_dir: Path, public_dir: Path):
    P = lambda rel: _load(public_dir / rel, {}) or {}  # noqa: E731
    atm = (P("market/atmosphere.json").get("days") or [{}])[-1]
    ins = P("chips/insti.json")
    fut = P("chips/futures.json").get("rows") or []
    risk = P("risk.json")
    strat = P("strategy.json")
    tv = P("turnover.json")
    intl = P("intel/intl.json")
    short = P("market/short.json")
    rep = P("intel/reports.json")

    # ── 大盤脈搏 ──
    vix = next((i for i in risk.get("indicators", []) if i["id"] == "vix"), None)
    m = (ins.get("market") or [None])[-1]
    f0, f1 = (fut[-1] if fut else None), (fut[-2] if len(fut) > 1 else None)
    pulse = {
        "date": atm.get("d"), "ix": atm.get("ix"), "ixPct": atm.get("ixPct"), "adv": atm.get("adv"), "dec": atm.get("dec"),
        "lu": atm.get("lu"), "ld": atm.get("ld"), "mood": atm.get("score"), "moodLabel": atm.get("label"),
        "temp": risk.get("temp"), "tempLabel": risk.get("tempLabel"), "temp5": risk.get("temp5"), "riskDate": risk.get("asof"),
        "vix": vix and vix["value"], "vixChg": vix and vix["chg1"],
        "foreign": m and m[1], "trust": m and m[2], "dealer": m and m[3], "instiOfficial": bool(m and len(m) >= 8 and m[7] == 1),
        "futF": f0 and f0[2], "futFChg": (f0[2] - f1[2]) if f0 and f1 and f0[2] is not None and f1[2] is not None else None,
    }

    # ── 警示 ──
    alerts = []
    for a in risk.get("alerts", []):
        alerts.append({"level": "red" if "危險" in a or "CDS" in a else "amber", "text": a, "href": "/risk"})
    if risk.get("tempLabel") in ("偏高", "高"):
        alerts.insert(0, {"level": "red" if risk["tempLabel"] == "高" else "amber", "text": f"市場風險溫度 {risk['temp']:.0f}（{risk['tempLabel']}）", "href": "/risk"})
    cols = short.get("cols") or []
    rows = [dict(zip(cols, r)) for r in short.get("rows", []) if STOCK.fullmatch(r[0])]
    low = sorted([r for r in rows if r.get("maint") is not None and r["maint"] < 130 and (r.get("mBal") or 0) >= 500], key=lambda r: r["maint"])
    if low:
        alerts.append({"level": "red", "text": f"融資維持率 < 130%：{len(low)} 檔（{'、'.join(r['name'] for r in low[:3])}…）", "href": "/short"})
    hi = sorted([r for r in rows if (r.get("ratio") or 0) > 50 and (r.get("mBal") or 0) >= 500], key=lambda r: -r["ratio"])
    if hi:
        alerts.append({"level": "amber", "text": f"券資比 > 50%：{len(hi)} 檔（{'、'.join(r['name'] for r in hi[:3])}）", "href": "/short"})
    disp = (_load(data_dir / "disposition.json", {}) or {}).get("data") or []
    if disp:
        alerts.append({"level": "amber", "text": f"處置中 {len(disp)} 檔", "href": "/disposition"})
    # 內部人近 7 天大額申報轉讓（≥1 億）
    ii = P("insider/index.json")
    since = (date.today() - timedelta(days=7)).isoformat()
    big: dict[str, float] = {}
    names = {}
    for t in ii.get("transfers", []):
        if t[0] >= since and any(k in (t[6] or "") for k in ("一般交易", "鉅額", "盤後", "洽特定人")):
            big[t[1]] = big.get(t[1], 0) + (t[11] or 0) * (t[14] or 0)
            names[t[1]] = t[2]
    big = {c: v for c, v in big.items() if v >= 1e8}
    if big:
        top = sorted(big, key=lambda c: -big[c])[:3]
        alerts.append({"level": "amber", "text": f"內部人大額申報轉讓（近 7 天 ≥1 億）：{len(big)} 家（{'、'.join(names[c] for c in top)}）", "href": "/insider"})
    ex = P("exdiv.json")
    cand = [u for u in ex.get("upcoming", []) if u.get("ok")]
    if cand:
        tm = [u["name"] for u in cand if u.get("tomorrow")]
        alerts.append({"level": "info", "text": f"除權息黑K：未來兩週候選 {len(cand)} 檔" + (f"，明天除息 {'、'.join(tm)}" if tm else ""), "href": "/exdiv"})
    rd = rep.get("date")
    nrep = [r for r in rep.get("rows", []) if r[0] == rd and r[9] == "broker"]
    if nrep:
        alerts.append({"level": "info", "text": f"{int(rd[5:7])}/{int(rd[8:10])} 新券商報告 {len(nrep)} 份", "href": "/reports"})

    # ── 明日行動 ──
    s1, s2 = strat.get("s1") or {}, strat.get("s2") or {}
    nxt = strat.get("next")
    exits = [h for s in (s1, s2) for h in s.get("holding", []) if h.get("exitDate") == nxt]
    strategy = {"asof": strat.get("asof"), "next": nxt,
                "s1": [{"code": p["code"], "name": p["name"], "v": p["ret5"]} for p in s1.get("picks", [])[:8]], "s1n": len(s1.get("picks", [])),
                "s2": [{"code": p["code"], "name": p["name"], "v": p.get("chipZ")} for p in s2.get("picks", [])[:5]], "s2n": len(s2.get("picks", [])),
                "exits": len(exits), "exitAvg": round(sum(h["ret"] for h in exits if h.get("ret") is not None) / len(exits), 2) if exits else None}
    ref = next((s for s in tv.get("stats", []) if s["group"].strip().endswith("當天漲停")), None)
    turnover = {"asof": tv.get("asof"), "next": tv.get("next"),
                "list": [{"code": r["code"], "name": r["name"], "t": r["turnover"], "dt": r.get("dt")} for r in tv.get("alert", [])],
                "o2c": ref and ref["o2c"], "black": ref and ref["black"],
                "top": [{"code": r["code"], "name": r["name"], "t": r["turnover"]} for r in (tv.get("today") or [])[:5]]}
    groups = []
    for g in intl.get("groups", []):
        if g["name"] in ("美股大盤", "美元兌台幣"):
            continue
        q = next((x for x in g.get("quotes", []) if x["sym"] == g.get("lead")), None) or (g.get("quotes") or [None])[0]
        if q and q.get("chg") is not None:
            react = [{"name": x["name"], "exp": x["exp"]} for x in (q.get("react") or []) if abs(x.get("exp") or 0) >= 0.3][:3]
            groups.append({"name": g["name"], "sym": q["sym"], "chg": q["chg"], "react": react})
    groups.sort(key=lambda x: -abs(x["chg"]))
    us = {q["sym"]: q for g in intl.get("groups", []) for q in g.get("quotes", []) if q["sym"] in ("^SOX", "^IXIC", "^GSPC", "TSM")}
    global_ = {"date": intl.get("usDate"), "idx": [{"name": n, "chg": us[s]["chg"]} for s, n in (("^GSPC", "S&P"), ("^IXIC", "那指"), ("^SOX", "費半"), ("TSM", "TSM ADR")) if s in us],
               "groups": groups[:5]}

    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "pulse": pulse, "alerts": alerts,
           "strategy": strategy, "turnover": turnover, "global": global_}
    (public_dir / "home.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"首頁摘要：{len(alerts)} 則警示、波段 {strategy['s1n']}+{strategy['s2n']} 檔、高週轉觀察 {len(turnover['list'])} 檔")
