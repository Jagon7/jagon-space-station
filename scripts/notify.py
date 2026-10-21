#!/usr/bin/env python3
"""
每日推播：把自選股訊號與市場重點送到 Telegram／Discord／LINE。

要先執行 build_views.py（產生 public/data/*），本程式只讀那些 JSON。
自選股清單：config/watchlist.txt（逗號或換行分隔的股票代號，可從網站「自選股」頁複製）。
推播管道（在 GitHub repo 的 Settings → Secrets and variables → Actions 設定，有設哪個就發哪個）：
  Telegram：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
  Discord ：DISCORD_WEBHOOK_URL
  LINE    ：LINE_CHANNEL_TOKEN、LINE_USER_ID（Messaging API push message）
用法：python scripts/notify.py [--dry-run] [--check] [--insider-alert]
  --intel-alert：新券商報告、美股類股大波動（開盤前提醒台股可能反應的股票），已推過的記在 data/notify/intel-alerted.json
  --insider-alert：內部人大額異動快訊（≥1 億），每次資料更新後都跑，沒推過的才推（記錄在 data/notify/insider-alerted.json）
  --check：只檢查最近一個交易日的行情、法人、融資券是否都到齊，結果寫到 GITHUB_OUTPUT（ready、date）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public" / "data"
SITE = "https://jagon7.github.io/jagon-space-station"


def load(rel: str, default=None):
    try:
        return json.loads((PUB / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def watchlist() -> list[str]:
    p = ROOT / "config" / "watchlist.txt"
    if not p.exists():
        return []
    text = re.sub(r"#.*", "", p.read_text(encoding="utf-8"))
    return [c for c in re.split(r"[\s,，]+", text) if re.fullmatch(r"[0-9A-Z]{4,6}", c)]


def yi(v):
    return f"{'+' if v > 0 else ''}{v:.0f}億" if abs(v) >= 10 else f"{'+' if v > 0 else ''}{v:.1f}億"


def compose() -> str:
    sig = load("signals.json", {}) or {}
    day = sig.get("date") or "—"
    lines = [f"📡 Jagon 每日戰報 {day}"]

    atm = (load("market/atmosphere.json", {}) or {}).get("days") or []
    if atm:
        a = atm[-1]
        ix = f"加權 {a['ix']:,.0f}（{a['ixPct']:+.2f}%）・" if a.get("ix") and a.get("ixPct") is not None else ""
        lines.append(f"{ix}氣氛 {a.get('score')} {a.get('label')}・漲停 {a['lu']} 跌停 {a['ld']}")

    ins = load("chips/insti.json", {}) or {}
    if ins.get("market"):
        m = ins["market"][-1]
        f, t, d = m[1:4]
        if len(m) >= 8 and m[7] == 1:
            otc = f"（上櫃 外資 {yi(m[4])}、投信 {yi(m[5])}、自營 {yi(m[6])}）" if m[4] is not None else ""
            lines.append(f"法人（上市）：外資 {yi(f)}、投信 {yi(t)}、自營 {yi(d)}{otc}")
        else:
            lines.append(f"法人（估算）：外資 {yi(f)}、投信 {yi(t)}、自營 {yi(d)}")

    fut = (load("chips/futures.json", {}) or {}).get("rows") or []
    if fut:
        r = fut[-1]
        prev = fut[-2] if len(fut) > 1 else None
        chg = f"（{r[2] - prev[2]:+,.0f}）" if prev and r[2] is not None and prev[2] is not None else ""
        retail = f"、散戶小台 {r[7]:+.1f}%" if r[7] is not None else ""
        lines.append(f"期貨：外資台指淨 {r[2]:+,.0f} 口{chg}{retail}" if r[2] is not None else "")

    # 自選股
    wl = watchlist()
    if wl:
        lines.append("")
        lines.append("⭐ 自選股")
        quotes = sig.get("quotes", {})
        for c in wl:
            q = quotes.get(c)
            head = f"{q[0]} {c} {q[1]}（{q[2]:+.2f}%）" if q and q[2] is not None else f"{c}"
            items = sig.get("sig", {}).get(c, [])
            mark = lambda d: "🔺" if d > 0 else "🔻" if d < 0 else "・"  # noqa: E731
            lines.append(f"{head}" + ("" if items else "：沒有特別訊號"))
            for cat, text, d in items[:6]:
                lines.append(f"  {mark(d)}{cat}｜{text}")

    # 市場重點
    lines.append("")
    lines.append("🔎 今日重點")
    short = load("market/short.json", {}) or {}
    sq = [r for r in short.get("rows", []) if re.fullmatch(r"[1-9]\d{3}", r[0]) and (r[12] or 0) >= 10 and r[8] >= 300 and (r[4] or 0) > 0]
    sq.sort(key=lambda r: -(r[12] or 0))
    if sq:
        lines.append("軋空候選：" + "、".join(f"{r[1]}({r[12]}%)" for r in sq[:5]))
    rows = ins.get("rows") or []
    ts = sorted([r for r in rows if (r[21] or 0) >= 3 and re.fullmatch(r"[1-9]\d{3}", r[0])], key=lambda r: -(r[21] or 0))
    if ts:
        lines.append("投信連買：" + "、".join(f"{r[1]}({r[21]}天)" for r in ts[:6]))
    nd = load("market/nextday.json", {}) or {}
    lu = [r for r in nd.get("rows", []) if r[0] == day]
    if lu:
        multi = [r for r in lu if r[6] >= 2]
        lines.append(f"漲停 {len(lu)} 檔" + (f"，連板：{'、'.join(f'{r[2]}({r[6]})' for r in sorted(multi, key=lambda r: -r[6])[:5])}" if multi else ""))
    ev = load("fund/events.json", {}) or {}
    tmr = [(date.today() + timedelta(days=i)).isoformat() for i in (1, 2, 3)]
    nxt = next((d for d in tmr if any(r[0] == d for r in ev.get("exdiv", []))), None)
    if nxt:
        ex = [r for r in ev["exdiv"] if r[0] == nxt]
        lines.append(f"{nxt[5:].replace('-', '/')} 除權息：" + "、".join(f"{r[2]}{f'({r[5]}元)' if r[5] else ''}" for r in ex[:8]) + (f" 等 {len(ex)} 家" if len(ex) > 8 else ""))
    lines.append("")
    lines.append(f"{SITE}/watchlist/")
    return "\n".join(x for x in lines if x is not None)


def send(text: str) -> int:
    sent = 0
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        for i in range(0, len(text), 3800):
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[i:i + 3800], "disable_web_page_preview": True}, timeout=30)
            print("Telegram", r.status_code, r.text[:200])
        sent += 1
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if hook:
        for i in range(0, len(text), 1900):
            r = requests.post(hook, json={"content": text[i:i + 1900]}, timeout=30)
            print("Discord", r.status_code)
        sent += 1
    ltok, luser = os.environ.get("LINE_CHANNEL_TOKEN"), os.environ.get("LINE_USER_ID")
    if ltok and luser:
        r = requests.post("https://api.line.me/v2/bot/message/push", timeout=30,
                          headers={"Authorization": f"Bearer {ltok}"},
                          json={"to": luser, "messages": [{"type": "text", "text": text[:4900]}]})
        print("LINE", r.status_code, r.text[:200])
        sent += 1
    return sent


def last_trading_day() -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    d = now.date() if now.hour >= 15 else now.date() - timedelta(days=1)
    try:
        hol = set(json.loads((ROOT / "data" / "calendar.json").read_text(encoding="utf-8")).get("holidays", []))
    except (OSError, ValueError):
        hol = set()
    while d.weekday() >= 5 or d.isoformat() in hol:
        d -= timedelta(days=1)
    return d.isoformat()


def check() -> int:
    """行情（技術選股）、三大法人、融資券都是同一個最近交易日，才算資料到齊"""
    day = last_trading_day()
    got = {k: (load(f, {}) or {}).get("date") for k, f in
           (("行情", "market/screener.json"), ("法人", "chips/insti.json"), ("融資券", "market/short.json"))}
    ready = all(v == day for v in got.values())
    print(f"最近交易日 {day}：" + "、".join(f"{k} {v or '—'}" for k, v in got.items()) + ("（到齊）" if ready else "（還沒到齊）"))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"ready={'true' if ready else 'false'}\ndate={day}\n")
    return 0


ALERT_MIN = 1e8
# 會在市場上（或直接對特定人）賣出的轉讓方式；贈與、信託不算買賣
SALE_METHODS = ("一般交易", "鉅額", "盤後", "洽特定人", "私募")
STATE = ROOT / "data" / "notify" / "insider-alerted.json"


def yi_abs(v: float) -> str:
    return f"{v / 1e8:.1f} 億" if v < 1e10 else f"{v / 1e8:.0f} 億"


def insider_alert(dry: bool) -> int:
    ins = load("insider/index.json", {}) or {}
    transfers, recent, month = ins.get("transfers", []), ins.get("recent", []), ins.get("latest")
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = None
    key = lambda t: f"{t[0]}|{t[1]}|{t[5]}|{t[11]}"  # noqa: E731  申報日|代號|申報人|股數
    day = last_trading_day()
    if state is None:  # 第一次執行：只推最近一個交易日的，更早的當作已推過，避免一次灌爆
        state = {"keys": [key(t) for t in transfers if t[0] < day], "month": month}
    seen = set(state["keys"])

    lines: list[str] = []
    # 1) 事前申報轉讓：同一天同一家合計（只算會賣出的方式）
    # 只看最近 14 天的申報：transfers 保留 120 天，比已推紀錄的保存期長，不限制的話舊申報會被當成新的
    recent_from = (date.today() - timedelta(days=14)).isoformat()
    new = [t for t in transfers if t[0] >= recent_from and key(t) not in seen]
    agg: dict[tuple, dict] = {}
    for t in new:
        if not any(m in (t[6] or "") for m in SALE_METHODS):
            continue
        a = agg.setdefault((t[0], t[1]), {"name": t[2], "amt": 0.0, "who": [], "how": set()})
        a["amt"] += (t[11] or 0) * (t[14] or 0)
        a["who"].append(re.sub(r"本人$", "", t[4] or ""))
        a["how"].add(re.sub(r"\(.*?\)", "", t[6]))
    hits = sorted(((k, v) for k, v in agg.items() if v["amt"] >= ALERT_MIN), key=lambda x: -x[1]["amt"])
    if hits:
        lines.append(f"🚨 內部人大額申報轉讓（≥1 億，{len(hits)} 家）")
        for (d, code), v in hits:
            who = v["who"][0] + (f" 等 {len(v['who'])} 人" if len(v["who"]) > 1 else "")
            lines.append(f"🔻{v['name']} {code}：{yi_abs(v['amt'])}｜{'、'.join(sorted(v['how']))}｜{who}｜申報 {d[5:].replace('-', '/')}")
        lines.append("（金額＝預定轉讓股數 × 最新收盤價；申報後 1 個月內可轉讓）")

    # 2) 每月內部人實際買賣（每月 15 日前後公布上個月），新月份出來時推一次
    if month and month != state.get("month"):
        big = [r for r in recent if r[4] is not None and abs(r[4]) >= ALERT_MIN]
        buys = sorted([r for r in big if r[4] > 0], key=lambda r: -r[4])
        sells = sorted([r for r in big if r[4] < 0], key=lambda r: r[4])
        if big:
            if lines:
                lines.append("")
            lines.append(f"🚨 {int(month[5:])} 月內部人實際買賣 ≥1 億：買 {len(buys)} 家、賣 {len(sells)} 家")
            for r in buys[:8]:
                lines.append(f"🔺{r[1]} {r[0]}：淨買 {yi_abs(r[4])}｜{r[6]}")
            for r in sells[:8]:
                lines.append(f"🔻{r[1]} {r[0]}：淨賣 {yi_abs(-r[4])}｜{r[6]}")
            if len(buys) > 8 or len(sells) > 8:
                lines.append("…完整名單見網站")
        state["month"] = month

    if lines:
        lines += ["", f"{SITE}/insider/"]
        text = "\n".join(lines)
        print(text)
        if not dry and not send(text):
            print("\n（沒有設定任何推播管道，只印出內容）")
    else:
        print("沒有新的內部人大額異動")
    if not dry:
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        state["keys"] = sorted(k for k in seen | {key(t) for t in transfers} if k >= cutoff)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


INTEL_STATE = ROOT / "data" / "notify" / "intel-alerted.json"


def intel_alert(dry: bool) -> int:
    try:
        state = json.loads(INTEL_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = None
    rep = load("intel/reports.json", {}) or {}
    rows = rep.get("rows") or []
    intl = load("intel/intl.json", {}) or {}
    first = state is None
    if first:  # 第一次執行：現有的都當作推過，避免一次灌爆
        state = {"reports": [r[13] for r in rows], "us": [f"{q['sym']}:{q['date']}" for g in intl.get("groups", []) for q in g.get("quotes", [])]}
    seen = set(state["reports"])
    wl = set(watchlist())
    msgs = []

    # 1) 新券商報告（FactSet 共識只推自選股的）
    new = [r for r in rows if r[13] not in seen and (r[9] == "broker" or r[1] in wl)]
    if new:
        lines = [f"📑 新券商報告（{len(new)} 份）"]
        for r in new[:12]:
            d, code, name, broker, rating, tgt, prev, up = r[:8]
            chg = "" if prev is None else ("維持" if prev == tgt else f"{'調升' if tgt > prev else '調降'}（前次 {prev:g}）")
            lines.append(f"{'⭐' if code in wl else '🔹'}{name} {code}｜{broker} 目標價 {tgt:g}{f'（潛在 {up:+.1f}%）' if up is not None else ''} {chg}{'｜' + rating if rating else ''}")
            if r[11]:
                p = r[11][0]
                lines.append(f"   {p[:70]}{'…' if len(p) > 70 else ''}")
        if len(new) > 12:
            lines.append(f"…還有 {len(new) - 12} 份")
        lines.append(f"{SITE}/reports/")
        msgs.append("\n".join(lines))

    # 2) 國際類股／指數大波動（美股、貴金屬、BDI、SCFI…）：每個指數每個日期只推一次，
    #    只在台股還能反應時推（指數日期之後的第一個台股交易日 13:30 前）
    tpe = timezone(timedelta(hours=8))
    now = datetime.now(tpe)
    done = set(state["us"])
    hit_groups = []
    for g in intl.get("groups", []):
        trig = []
        for q in g.get("quotes", []):
            key = f"{q['sym']}:{q['date']}"
            if not q.get("alert") or key in done:
                continue
            d = date.fromisoformat(q["date"]) + timedelta(days=1)
            while d.weekday() >= 5:
                d += timedelta(days=1)
            if now < datetime(d.year, d.month, d.day, 13, 30, tzinfo=tpe):
                trig.append(q)
            done.add(key)
        if trig:
            hit_groups.append((g, trig))
    if hit_groups:
        NAME = {"^SOX": "費半", "^IXIC": "那指", "^GSPC": "S&P", "^DJI": "道瓊", "CL=F": "原油", "HG=F": "銅", "GC=F": "黃金",
                "SI=F": "白銀", "PL=F": "白金", "^XAU": "費城金銀指數", "^HUI": "金蟲指數", "BDI": "BDI 散裝指數",
                "SCFI": "SCFI 貨櫃運價", "TWD=X": "美元兌台幣"}
        nm = lambda q: NAME.get(q["sym"], q["sym"])  # noqa: E731
        lines = ["🌏 國際類股大波動：" + "、".join(f"{nm(q)} {q['chg']:+.2f}%{'（週）' if q.get('weekly') else ''}" for _, t in hit_groups for q in t)]
        for g, trig in hit_groups:
            lines.append(f"【{g['name']}】" + "、".join(f"{nm(q)} {q['chg']:+.2f}%（{q['date'][5:].replace('-', '/')}）" for q in trig))
            # 用觸發的那個指數自己的 β；變動最大的觸發指數優先
            q_top = max(trig, key=lambda q: abs(q["chg"]))
            react = [m for m in (q_top.get("react") or []) if abs(m.get("exp") or 0) >= 0.3][:8]
            members = [m["name"] for m in g.get("members", [])[:8]]
            if react:
                lines.append("  開盤留意：" + "、".join(f"{m['name']} {m['exp']:+.1f}%" for m in react))
            elif members:
                lines.append("  相關台股：" + "、".join(members))
        lines.append("（預估＝β × 指數漲跌，依過去約半年的隔日連動推算，僅供參考）")
        lines.append(f"{SITE}/global/")
        msgs.append("\n".join(lines))
    state["us"] = sorted(done)[-300:]

    for text in msgs:
        print(text + "\n")
        if not dry and not first and not send(text):
            print("（沒有設定任何推播管道，只印出內容）")
    if not msgs:
        print("沒有新的券商報告或國際類股大波動")
    if not dry:
        state["reports"] = sorted(seen | {r[13] for r in rows})[-3000:]
        INTEL_STATE.parent.mkdir(parents=True, exist_ok=True)
        INTEL_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--insider-alert", action="store_true")
    ap.add_argument("--intel-alert", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()
    if a.insider_alert:
        return insider_alert(a.dry_run)
    if a.intel_alert:
        return intel_alert(a.dry_run)
    text = compose()
    print(text)
    if a.dry_run:
        return 0
    if not send(text):
        print("\n（沒有設定任何推播管道，只印出內容。設定方式見本檔開頭說明。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
