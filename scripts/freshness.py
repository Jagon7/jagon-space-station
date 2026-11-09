#!/usr/bin/env python3
"""
資料新鮮度檢查：每個資料源的最新日期，對照「今天應該有的交易日」，落後就列出來

每天晚上所有排程跑完後（Cloudflare 23:10）執行：
  - 寫 data/freshness.json（網站「資料健檢」頁顯示）
  - 有任何一項落後 → LINE 通知（同一天同樣的落後項目只通知一次）
用法：python scripts/freshness.py [--alert] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
STATE = DATA / "notify" / "freshness-alerted.json"


def load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def last_file(d: str) -> str | None:
    fs = sorted(p.stem for p in (DATA / d).glob("20*.json")) if (DATA / d).exists() else []
    return fs[-1] if fs else None


def trading_days_back(today: date, hol: set[str], n: int = 10) -> list[str]:
    out, d = [], today
    while len(out) < n:
        if d.weekday() < 5 and d.isoformat() not in hol:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out


def checks(now: datetime) -> tuple[str, list[dict]]:
    hol = set(load(DATA / "calendar.json", {}).get("holidays", []))
    tdays = trading_days_back(now.date(), hol)
    today_trading = tdays[0] == now.date().isoformat()
    mins = now.hour * 60 + now.minute

    def expect(ready: str) -> str:
        """這項資料在今天 ready 時刻之後才算應該有今天的；之前看前一個交易日"""
        h, m = map(int, ready.split(":"))
        return tdays[0] if today_trading and mins >= h * 60 + m else (tdays[1] if today_trading else tdays[0])

    daily = sorted((DATA / "daily").glob("20*.json"))
    dq = dm = dmamt = None
    for p in reversed(daily[-5:]):
        d = load(p, {})
        dq = dq or (d.get("date") if d.get("q") else None)
        dm = dm or (d.get("date") if d.get("m") else None)
        dmamt = dmamt or (d.get("date") if (d.get("off") or {}).get("twse", {}).get("mAmt") else None)

    # 主動式 ETF 每日持股：抓到今天的檔數
    act = [p for p in (DATA / "etf" / "holdings").glob("*A.json")]
    act_dates = [((load(p, {}) or {}).get("snapshots") or [{}])[-1].get("date") for p in act]
    act_latest = max([d for d in act_dates if d] or [None]) if act_dates else None
    ac = load(DATA / "etf" / "active_cost.json", {}) or {}
    ac_asof = max([e.get("asof") for e in (ac.get("etfs") or {}).values()] or [None])
    of = load(DATA / "orderflow" / "features.json", {}) or {}
    sent = lambda f: (load(DATA / "notify" / f, {}) or {}).get("sent", [])  # noqa: E731
    fut = load(DATA / "futures" / "daily.json", {}) or {}
    fut_last = max(fut) if isinstance(fut, dict) and fut else max(re.findall(r"20\d\d-\d\d-\d\d", json.dumps(fut)) or [None])

    items = [
        # (類別, 名稱, 最新日期, 何時之後該有今天)
        ("行情", "收盤行情（上市＋上櫃）", dq, "15:30"),
        ("行情", "成交排行", last_file("ranking"), "15:30"),
        ("籌碼", "三大法人", last_file("insti"), "18:30"),
        ("籌碼", "期貨籌碼", fut_last, "18:30"),
        ("籌碼", "個股融資融券", dm, "21:50"),
        ("籌碼", "官方融資金額（大盤維持率）", dmamt, "21:50"),
        ("籌碼", "分點買賣超", last_file("broker"), "20:30"),
        ("盤中", "即時資金流（收盤存檔）", last_file("flow"), "13:45"),
        ("訂單流", "逐筆訂單流特徵", max(of.get("days") or {"": 0}) or None, "15:00"),
        ("ETF", f"主動式 ETF 持股（{sum(d == act_latest for d in act_dates)}/{len(act)} 檔到 {act_latest or '—'}）", act_latest, "21:40"),
        ("ETF", "主動 ETF 建倉成本（停損監控）", ac_asof, "22:40"),
        ("通知", "盤前快報", (sent("morning-sent.json") or [None])[-1], "08:10"),
        ("通知", "85g 當沖標的", (sent("g85-sent.json") or [None])[-1], "08:40"),
        ("通知", "ETF 持股變化", (sent("etf-sent.json") or [None])[-1], "20:10"),
        ("通知", "分點大額進出", (sent("broker-sent.json") or [None])[-1], "20:10"),
        ("通知", "主動 ETF 停損＋融資斷頭", (sent("active-sent.json") or [None])[-1], "22:50"),
    ]
    rows = []
    for cat, name, latest, ready in items:
        exp = expect(ready)
        lag = None
        if latest:
            lag = sum(1 for d in tdays if latest < d <= exp)
        rows.append({"cat": cat, "name": name, "latest": latest, "expected": exp, "ready": ready, "lag": lag,
                     "ok": latest is not None and latest >= exp})
    return tdays[0], rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    now = datetime.now(TPE)
    day, rows = checks(now)
    bad = [r for r in rows if not r["ok"]]
    doc = {"checkedAt": now.isoformat(timespec="minutes"), "tradingDay": day, "rows": rows}
    (DATA / "freshness.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(("✅" if r["ok"] else "❌"), r["cat"], r["name"], r["latest"], "應有", r["expected"])
    if not a.alert or not bad:
        return 0
    state = load(STATE, {}) or {}
    key = now.date().isoformat() + "|" + "|".join(sorted(r["name"] for r in bad))
    if key in state.get("keys", []) and not a.dry_run:
        print("同樣的落後項目今天已通知過")
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from line_flex import Msg
    import notify
    m = Msg("⚠️ 資料沒有更新到最新", f"{now:%m/%d %H:%M} 檢查・{len(bad)} 項落後", accent="#E5484D",
            url=f"{notify.SITE}/health/", button="開啟資料健檢")
    for r in bad:
        m.kv(f"{r['cat']}｜{r['name']}", f"最新 {r['latest'] or '沒有'}，應有 {r['expected']}", color="#E5484D")
    m.note("各排程會自動重試；持續落後代表來源網站沒公布或程式出錯，需要檢查")
    print(m.text())
    if a.dry_run:
        return 0
    notify.send(m)
    state["keys"] = (state.get("keys", []) + [key])[-30:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
