#!/usr/bin/env python3
"""
每日推播：把自選股訊號與市場重點送到 Telegram／Discord／LINE。

要先執行 build_views.py（產生 public/data/*），本程式只讀那些 JSON。
自選股清單：config/watchlist.txt（逗號或換行分隔的股票代號，可從網站「自選股」頁複製）。
推播管道（在 GitHub repo 的 Settings → Secrets and variables → Actions 設定，有設哪個就發哪個）：
  Telegram：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
  Discord ：DISCORD_WEBHOOK_URL
  LINE    ：LINE_CHANNEL_TOKEN、LINE_USER_ID（Messaging API push message）
用法：python scripts/notify.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
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
        _, f, t, d = ins["market"][-1]
        lines.append(f"法人：外資 {yi(f)}、投信 {yi(t)}、自營 {yi(d)}")

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    text = compose()
    print(text)
    if a.dry_run:
        return 0
    if not send(text):
        print("\n（沒有設定任何推播管道，只印出內容。設定方式見本檔開頭說明。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
