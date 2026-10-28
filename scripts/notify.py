#!/usr/bin/env python3
"""
每日推播：把自選股訊號與市場重點送到 Telegram／Discord／LINE。

要先執行 build_views.py（產生 public/data/*），本程式只讀那些 JSON。
自選股清單：config/watchlist.txt（逗號或換行分隔的股票代號，可從網站「自選股」頁複製）。
推播管道（在 GitHub repo 的 Settings → Secrets and variables → Actions 設定，有設哪個就發哪個）：
  Telegram：TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
  Discord ：DISCORD_WEBHOOK_URL
  LINE    ：LINE_CHANNEL_TOKEN、LINE_USER_ID（Messaging API push message）
用法：python scripts/notify.py [--dry-run] [--check] [--insider-alert] [--preview]
  LINE 用 Flex 卡片（排版在 scripts/line_flex.py），Telegram／Discord 用同內容的純文字
  --exdiv-alert：除權息黑K（明天除息的放空候選、明天要回補的部位；沒有就不發）
  --risk-alert：市場風險警示（新條件成立才推，夜間 23:00～07:30 不推；記在 data/notify/risk-alerted.json）
  --morning：盤前快報（台指期夜盤＋富台指、美股主要指數、市場風險、類股龍頭與台股預估），週一到五 08:00；加 --preview 立刻發一張預覽
             夜盤抓不到時用富台指（optratw.com 背後的第三方 API）換算，再不行用美股 EWT
  --etf-alert：每日 ETF 持股變化摘要（主動 ETF 合計買賣超、新建倉／出清、被動 ETF 成分異動、資金流向），週一到五 20:00
  --preview：不管有沒有推過，把每日戰報、策略、高週轉三張卡片各發一次（測試排版用）
  --strategy-alert：兩個十日波段策略明日進場名單與到期出場提醒（資料到齊才發，每個交易日一次）
  --turnover-alert：週轉率前 20 名且收漲停的隔日開高走低觀察名單（每個交易日一次；沒有符合的股票就不發）
  --intel-alert：新券商報告，已推過的記在 data/notify/intel-alerted.json（國際類股改由 --morning 盤前快報統一發）
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

from line_flex import FLAT, Msg, sign_tone

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public" / "data"
SITE = (os.environ.get("SITE_URL") or "https://jagon7.github.io/jagon-space-station").rstrip("/")  # 搬到 Cloudflare 後在 repo variables 設 SITE_URL


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


MAINT_LOW, RATIO_HI = 130, 50


def wan(v) -> str:
    """萬元 → 「+1.23 億」或「-850 萬」"""
    if v is None:
        return "—"
    return f"{v / 1e4:+.2f} 億" if abs(v) >= 1e4 else f"{v:+,.0f} 萬"


def compose() -> Msg:
    sig = load("signals.json", {}) or {}
    day = sig.get("date") or "—"
    m = Msg("📡 Jagon 每日戰報", day, accent="#4f8cff", url=f"{SITE}/short/", button="開啟券差偵察")

    atm = (load("market/atmosphere.json", {}) or {}).get("days") or []
    if atm:
        a = atm[-1]
        m.section("大盤")
        if a.get("ix") and a.get("ixPct") is not None:
            m.kv("加權指數", f"{a['ix']:,.0f}（{a['ixPct']:+.2f}%）", color=sign_tone(a["ixPct"]))
        m.kv("市場氣氛", f"{a.get('score')} {a.get('label')}")
        m.kv("漲停／跌停", f"{a['lu']}／{a['ld']}")

    ins = load("chips/insti.json", {}) or {}
    if ins.get("market"):
        r = ins["market"][-1]
        f, t, d = r[1:4]
        official = len(r) >= 8 and r[7] == 1
        m.section("三大法人（上市）" if official else "三大法人（估算）")
        for k, v in (("外資", f), ("投信", t), ("自營商", d)):
            m.kv(k, yi(v), color=sign_tone(v))
        if official and r[4] is not None:
            m.line(f"上櫃：外資 {yi(r[4])}、投信 {yi(r[5])}、自營 {yi(r[6])}", color=FLAT)

    fut = (load("chips/futures.json", {}) or {}).get("rows") or []
    if fut and fut[-1][2] is not None:
        r = fut[-1]
        prev = fut[-2] if len(fut) > 1 else None
        chg = f"（{r[2] - prev[2]:+,.0f}）" if prev and prev[2] is not None else ""
        m.section("期貨")
        m.kv("外資台指淨部位", f"{r[2]:+,.0f} 口{chg}", color=sign_tone(r[2]))
        if r[7] is not None:
            m.kv("散戶小台多空比", f"{r[7]:+.1f}%", color=sign_tone(r[7]))

    short = load("market/short.json", {}) or {}
    sc = short.get("cols") or []
    srow = {r[0]: dict(zip(sc, r)) for r in short.get("rows", [])}

    def margin_line(r: dict) -> str:
        parts = [f"融資 {r['mBal']:,} 張（{r['mChg']:+,}・{wan(r.get('mAmt'))}）"]
        if r.get("maint") is not None:
            parts.append(f"維持率 {r['maint']:.0f}%{'⚠' if r['maint'] < MAINT_LOW else ''}")
        if r.get("use") is not None:
            parts.append(f"使用率 {r['use']:.1f}%")
        if r.get("ratio") is not None:
            parts.append(f"券資比 {r['ratio']:.1f}%{'⚠' if r['ratio'] > RATIO_HI else ''}")
        return "・".join(parts)

    wl = watchlist()
    if wl:
        m.section("⭐ 自選股", f"{len(wl)} 檔")
        m.cols("收盤", "漲跌")
        quotes = sig.get("quotes", {})
        mark = lambda d: "▲" if d > 0 else "▼" if d < 0 else "・"  # noqa: E731
        for c in wl:
            q = quotes.get(c)
            items = sig.get("sig", {}).get(c, [])
            sub = "\n".join(f"{mark(d)} {cat}｜{text}" for cat, text, d in items[:6]) or "沒有特別訊號"
            if c in srow and srow[c].get("mBal") is not None:
                sub += "\n💰 " + margin_line(srow[c])
            if q and q[2] is not None:
                m.stock(q[0], c, f"{q[1]}", f"{q[2]:+.2f}%", color=sign_tone(q[2]), sub=sub)
            else:
                m.stock(c, "", sub=sub)

    # 融資風險：維持率 < 130%（追繳、可能斷頭）、券資比 > 50%（空單重、易軋空）；只看融資 500 張以上的普通股
    stocks = [r for c, r in srow.items() if re.fullmatch(r"[1-9]\d{3}", c) and (r.get("mBal") or 0) >= 500]
    low = sorted([r for r in stocks if r.get("maint") is not None and r["maint"] < MAINT_LOW], key=lambda r: r["maint"])
    if low:
        m.section(f"⚠ 融資維持率 < {MAINT_LOW}%", f"{len(low)} 檔")
        m.cols("融資增減", "維持率")
        for r in low[:10]:
            m.stock(r["name"], r["code"], wan(r.get("mAmt")), f"{r['maint']:.0f}%", color="#E5484D",
                    sub=f"融資 {r['mBal']:,} 張・使用率 {r['use'] or 0:.1f}%・券資比 {r['ratio'] or 0:.1f}%・近 20 日 {r['chg20'] or 0:+.1f}%")
        if len(low) > 10:
            m.note(f"還有 {len(low) - 10} 檔，見網站券差偵察")
    hi = sorted([r for r in stocks if (r.get("ratio") or 0) > RATIO_HI], key=lambda r: -r["ratio"])
    if hi:
        m.section(f"⚠ 券資比 > {RATIO_HI}%", f"{len(hi)} 檔")
        m.cols("融資增減", "券資比")
        for r in hi[:10]:
            m.stock(r["name"], r["code"], wan(r.get("mAmt")), f"{r['ratio']:.0f}%", color="#D97706",
                    sub=f"融券 {r['sBal']:,} 張（{r['sChg']:+,}）・融資 {r['mBal']:,} 張・維持率 {r['maint'] or 0:.0f}%・近 5 日 {r['chg5'] or 0:+.1f}%")
        if len(hi) > 10:
            m.note(f"還有 {len(hi) - 10} 檔，見網站券差偵察")
    if low or hi:
        m.note("融資維持率為估算（以融資新增日均價推算平均成本，上市融資 6 成、上櫃 5 成）；只列融資 500 張以上")

    m.section("🔎 今日重點")
    short = load("market/short.json", {}) or {}
    sq = [r for r in short.get("rows", []) if re.fullmatch(r"[1-9]\d{3}", r[0]) and (r[12] or 0) >= 10 and r[8] >= 300 and (r[4] or 0) > 0]
    sq.sort(key=lambda r: -(r[12] or 0))
    if sq:
        m.kv("軋空候選", "、".join(f"{r[1]}({r[12]}%)" for r in sq[:5]))
    rows = ins.get("rows") or []
    ts = sorted([r for r in rows if (r[21] or 0) >= 3 and re.fullmatch(r"[1-9]\d{3}", r[0])], key=lambda r: -(r[21] or 0))
    if ts:
        m.kv("投信連買", "、".join(f"{r[1]}({r[21]}天)" for r in ts[:6]))
    nd = load("market/nextday.json", {}) or {}
    lu = [r for r in nd.get("rows", []) if r[0] == day]
    if lu:
        multi = sorted([r for r in lu if r[6] >= 2], key=lambda r: -r[6])
        m.kv(f"漲停 {len(lu)} 檔", ("連板：" + "、".join(f"{r[2]}({r[6]})" for r in multi[:5])) if multi else "沒有連板")
    ev = load("fund/events.json", {}) or {}
    tmr = [(date.today() + timedelta(days=i)).isoformat() for i in (1, 2, 3)]
    nxt = next((d for d in tmr if any(r[0] == d for r in ev.get("exdiv", []))), None)
    if nxt:
        ex = [r for r in ev["exdiv"] if r[0] == nxt]
        m.kv(f"{nxt[5:].replace('-', '/')} 除權息", "、".join(f"{r[2]}{f'({r[5]}元)' if r[5] else ''}" for r in ex[:8]) + (f" 等 {len(ex)} 家" if len(ex) > 8 else ""))
    return m


def send(msg) -> int:
    """msg 可以是純文字或 Msg；LINE 用 Flex 卡片（失敗就退回純文字），其他管道用文字"""
    text = msg if isinstance(msg, str) else msg.text()
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
        def push(message):
            return requests.post("https://api.line.me/v2/bot/message/push", timeout=30,
                                 headers={"Authorization": f"Bearer {ltok}"}, json={"to": luser, "messages": [message]})
        r = None
        if not isinstance(msg, str):
            r = push(msg.flex())
            print("LINE flex", r.status_code, r.text[:300])
        if r is None or r.status_code != 200:
            r = push({"type": "text", "text": text[:4900]})
            print("LINE text", r.status_code, r.text[:200])
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
            # 保底推播只在早上做（補前一個交易日）；GitHub 排程常延後好幾小時，下午才跑的話日期會換成今天、內容卻還是昨天的
            morning = datetime.now(timezone(timedelta(hours=8))).hour < 13
            f.write(f"ready={'true' if ready else 'false'}\ndate={day}\nfallback={'true' if morning else 'false'}\n")
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

    m = Msg("🚨 內部人大額異動", "金額 ≥ 1 億", accent="#f59e0b", url=f"{SITE}/insider/", button="開啟內部人頁")
    # 1) 事前申報轉讓：同一天同一家合計（只算會賣出的方式）
    # 只看最近 14 天的申報：transfers 保留 120 天，比已推紀錄的保存期長，不限制的話舊申報會被當成新的
    recent_from = (date.today() - timedelta(days=14)).isoformat()
    new = [t for t in transfers if t[0] >= recent_from and key(t) not in seen]
    agg: dict[tuple, dict] = {}
    for t in new:
        if not any(x in (t[6] or "") for x in SALE_METHODS):
            continue
        a = agg.setdefault((t[0], t[1]), {"name": t[2], "amt": 0.0, "who": [], "how": set()})
        a["amt"] += (t[11] or 0) * (t[14] or 0)
        a["who"].append(re.sub(r"本人$", "", t[4] or ""))
        a["how"].add(re.sub(r"\(.*?\)", "", t[6]))
    hits = sorted(((k, v) for k, v in agg.items() if v["amt"] >= ALERT_MIN), key=lambda x: -x[1]["amt"])
    if hits:
        m.section("事前申報轉讓", f"{len(hits)} 家")
        m.cols("申報日", "預估金額")
        for (d, code), v in hits:
            who = v["who"][0] + (f" 等 {len(v['who'])} 人" if len(v["who"]) > 1 else "")
            m.stock(v["name"], code, d[5:].replace("-", "/"), yi_abs(v["amt"]), up=False, sub=f"{'、'.join(sorted(v['how']))}｜{who}")
        m.note("金額＝預定轉讓股數 × 最新收盤價；申報後 1 個月內可轉讓")

    # 2) 每月內部人實際買賣（每月 15 日前後公布上個月），新月份出來時推一次
    if month and month != state.get("month"):
        big = [r for r in recent if r[4] is not None and abs(r[4]) >= ALERT_MIN]
        buys = sorted([r for r in big if r[4] > 0], key=lambda r: -r[4])
        sells = sorted([r for r in big if r[4] < 0], key=lambda r: r[4])
        if big:
            m.section(f"{int(month[5:])} 月實際買賣", f"買 {len(buys)}・賣 {len(sells)}")
            for r in buys[:8]:
                m.stock(r[1], r[0], "淨買", yi_abs(r[4]), up=True, sub=r[6])
            for r in sells[:8]:
                m.stock(r[1], r[0], "淨賣", yi_abs(-r[4]), up=False, sub=r[6])
            if len(buys) > 8 or len(sells) > 8:
                m.note("完整名單見網站")
        state["month"] = month

    if not m.empty():
        print(m.text())
        if not dry and not send(m):
            print("\n（沒有設定任何推播管道，只印出內容）")
    else:
        print("沒有新的內部人大額異動")
    if not dry:
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        state["keys"] = sorted(k for k in seen | {key(t) for t in transfers} if k >= cutoff)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


STRATEGY_STATE = ROOT / "data" / "notify" / "strategy-alerted.json"


def strategy_alert(dry: bool, force: bool = False) -> int:
    st = load("strategy.json", {}) or {}
    asof, nxt = st.get("asof"), st.get("next")
    day = last_trading_day()
    got = {k: (load(f, {}) or {}).get("date") for k, f in (("行情", "market/screener.json"), ("法人", "chips/insti.json"))}
    if not force and (asof != day or any(v != day for v in got.values())):
        print(f"策略資料還沒到齊（策略 {asof}、行情 {got['行情']}、法人 {got['法人']}，應為 {day}）")
        return 0
    try:
        state = json.loads(STRATEGY_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    if asof in state["sent"] and not force:
        print(f"{asof} 的策略名單已推過")
        return 0
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731
    s1, s2 = st["s1"], st["s2"]
    m = Msg(("【預覽】" if force else "") + "📈 十日波段策略", f"{md(nxt)} 進場名單・{md(asof)} 收盤資料", accent="#4f8cff", url=f"{SITE}/strategy/", button="開啟策略頁")
    m.section("出量做多", f"{len(s1['picks'])} 檔")
    if s1["picks"]:
        m.cols("收盤", "近 5 日")
    for p in s1["picks"][:12]:
        m.stock(p["name"], p["code"], f"{p['close']:g}", f"{p['ret5']:+.1f}%", color=sign_tone(p["ret5"]),
                sub=f"放量Z {p['zvol']:.1f}・{p['days']}/5 日放量・量穩Z {p['tz']:.2f}")
    if len(s1["picks"]) > 12:
        m.note(f"還有 {len(s1['picks']) - 12} 檔，見網站")
    if not s1["picks"]:
        m.line("沒有符合條件的股票", color=FLAT)
    m.section("輿情籌碼", f"{len(s2['picks'])} 檔")
    if s2["picks"]:
        m.cols("收盤", "籌碼Z")
    for p in s2["picks"][:10]:
        news = (p["news"][0][:40] + ("…" if len(p["news"][0]) > 40 else "")) if p.get("news") else ""
        m.stock(p["name"], p["code"], f"{p['close']:g}", f"{p['chipZ']:.2f}", color="#D97706", sub=news)
    if not s2["picks"]:
        m.line("沒有符合條件的股票", color=FLAT)
    ex = [h for s in (s1, s2) for h in s["holding"] if h.get("exitDate") == nxt and h.get("ret") is not None]
    if ex:
        m.section(f"⏰ {md(nxt)} 開盤出場", f"{len(ex)} 檔")
        m.cols("進場日", "目前報酬")
        for h in sorted(ex, key=lambda h: -h["ret"])[:15]:
            m.stock(h["name"], h["code"], md(h["date"]), f"{h['ret']:+.1f}%", color=sign_tone(h["ret"]))
        if len(ex) > 15:
            m.note(f"還有 {len(ex) - 15} 檔，見網站")
    m.note(f"進場：{md(nxt)} 收盤前半小時，收盤鎖漲停不進場；持有 10 個交易日後開盤出場。")
    text = m.text()
    print(text)
    if force:
        return 0 if dry else (send(m) and 0)
    if not dry:
        if not send(m):
            print("（沒有設定任何推播管道，只印出內容）")
        state["sent"] = sorted(set(state["sent"]) | {asof})[-60:]
        STRATEGY_STATE.parent.mkdir(parents=True, exist_ok=True)
        STRATEGY_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


TURNOVER_STATE = ROOT / "data" / "notify" / "turnover-alerted.json"


def turnover_alert(dry: bool, force: bool = False) -> int:
    tv = load("turnover.json", {}) or {}
    asof, nxt = tv.get("asof"), tv.get("next")
    day = last_trading_day()
    if asof != day and not force:
        print(f"週轉率資料還沒更新（{asof}，應為 {day}）")
        return 0
    now = datetime.now(timezone(timedelta(hours=8)))
    if not force and not tv.get("dtReady") and now.date().isoformat() == asof and now.hour < 21:
        print("當沖資料還沒到（要用來排除暫停先賣後買的股票），晚點再發")
        return 0
    try:
        state = json.loads(TURNOVER_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    if asof in state["sent"] and not force:
        print(f"{asof} 的高週轉漲停名單已推過")
        return 0
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731
    al = tv.get("alert") or []
    ref = next((s for s in tv.get("stats", []) if s["group"].strip().endswith("當天漲停")), None)
    m = Msg(("【預覽】" if force else "") + "🔻 高週轉＋漲停", f"{md(nxt)} 開高走低觀察名單・{md(asof)} 收盤", accent="#16A34A", url=f"{SITE}/turnover/", button="開啟週轉率頁")
    m.section("觀察名單", f"{len(al)} 檔")
    if al:
        m.cols("收盤", "週轉率")
    for r in al:
        dt = f"當沖 {r['dt']:.0f}%・" if r.get("dt") is not None else ""
        m.stock(r["name"], r["code"], f"{r['close']:g}", f"{r['turnover']:.1f}%", color="#D97706", sub=f"{dt}成交 {r['valueYi']:g} 億・今天漲停")
    if not al:
        m.line("今天週轉率前 20 名沒有收漲停的股票", color=FLAT)
    if ref:
        m.section("歷史回測", f"{ref['n']} 筆")
        m.kv("隔天平均開盤", f"{ref['gap']:+.2f}%", color=sign_tone(ref["gap"]))
        m.kv("隔天開盤→收盤", f"{ref['o2c']:+.2f}%", color=sign_tone(ref["o2c"]))
        m.kv("隔天收黑K機率", f"{ref['black']:.0f}%")
        m.kv("開盤空收盤補（全額成本）", f"{ref['shortNet']:+.2f}%", color=sign_tone(ref["shortNet"]))
        m.kv("手續費 2.8 折", f"{ref['shortNetDisc']:+.2f}%", color=sign_tone(ref["shortNetDisc"]))
    m.note("已排除隔天處置、暫停先賣後買的股票。做法：開盤放空、收盤回補；開盤若沒開高或直接開低，優勢較小。")
    text = m.text()
    print(text)
    if force:
        return 0 if dry else (send(m) and 0)
    late = now.date().isoformat() > nxt or (now.date().isoformat() == nxt and now.hour >= 9)
    if late:
        print(f"已經過了 {md(nxt)} 開盤，不再推播")
    if not dry:
        if al and not late and not send(m):
            print("（沒有設定任何推播管道，只印出內容）")
        state["sent"] = sorted(set(state["sent"]) | {asof})[-60:]
        TURNOVER_STATE.parent.mkdir(parents=True, exist_ok=True)
        TURNOVER_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


MORNING_STATE = ROOT / "data" / "notify" / "morning-sent.json"
TPE_TZ = timezone(timedelta(hours=8))
WEEK = "一二三四五六日"


def _holidays() -> set:
    try:
        return set(json.loads((ROOT / "data" / "calendar.json").read_text(encoding="utf-8")).get("holidays", []))
    except (OSError, ValueError):
        return set()


def prev_trading_day(d: date) -> date:
    hol = _holidays()
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in hol:
        d -= timedelta(days=1)
    return d


def night_futures() -> dict | None:
    """期交所 MIS：台指期盤後（夜盤）近月行情；MarketType 1＝盤後時段"""
    try:
        r = requests.post("https://mis.taifex.com.tw/futures/api/getQuoteList", timeout=20, json={
            "MarketType": "1", "SymbolType": "F", "KindID": "1", "CID": "TXF", "ExpireMonth": "", "RowSize": "全部",
            "PageNo": "", "SortColumn": "", "AscDesc": "A"})
        rows = r.json()["RtData"]["QuoteList"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        print("期交所夜盤抓不到：", e)
        return None
    f = lambda x: float(x) if x not in (None, "") else None  # noqa: E731
    spot = next((x for x in rows if x["SymbolID"] == "TXF-P"), {})
    fut = [x for x in rows if x["SymbolID"].startswith("TXF") and x["SymbolID"].endswith("-M") and f(x.get("CLastPrice"))]
    if not fut:
        return None
    x = fut[0]
    return {"name": x["DispCName"].replace("臺", "台"), "date": x["CDate"], "time": x.get("CTime") or "", "last": f(x["CLastPrice"]),
            "ref": f(x["CRefPrice"]), "diff": f(x["CDiff"]), "rate": f(x["CDiffRate"]), "high": f(x["CHighPrice"]),
            "low": f(x["CLowPrice"]), "vol": int(f(x["CTotalVolume"]) or 0), "spot": f(spot.get("CRefPrice"))}


FTW_API = "https://script.google.com/macros/s/AKfycbzU4dONVYjC2b3aRVCGp0djYmEVFo4j3MLt_V_S9BZKaYUATLw_X3Z3uIkJhle9F09vaQ/exec"


def ftw_quote() -> dict | None:
    """富台指（新加坡交易所 FTSE 台灣指數期貨）：借用 optratw.com 網頁背後的公開行情 API（第三方、非官方，可能隨時失效）"""
    try:
        data = requests.get(FTW_API, timeout=30).json().get("data") or []
        x = next(x for x in data if "富台" in (x.get("name") or "") or "TWN" in (x.get("name") or ""))
        return {"price": float(x["price"]), "pct": float(str(x["percent"]).rstrip("%"))}
    except (requests.RequestException, ValueError, KeyError, TypeError, StopIteration):
        return None


def ewt_proxy() -> dict | None:
    """沒有夜盤資料時的替代：美股 iShares MSCI 台灣 ETF（EWT）前一晚漲跌"""
    try:
        res = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/EWT", params={"range": "5d", "interval": "1d"},
                           headers={"User-Agent": "Mozilla/5.0"}, timeout=20).json()["chart"]["result"][0]
        cl = [c for c in res["indicators"]["quote"][0]["close"] if c]
        d = datetime.fromtimestamp(res["timestamp"][-1], timezone.utc).date().isoformat()
        return {"close": cl[-1], "chg": (cl[-1] / cl[-2] - 1) * 100, "date": d}
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        return None


def morning_brief(dry: bool, force: bool = False) -> int:
    now = datetime.now(TPE_TZ)
    today = now.date()
    if today.weekday() >= 5 and not force:
        print("週末不發盤前快報")
        return 0
    try:
        state = json.loads(MORNING_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    if today.isoformat() in state["sent"] and not force:
        print("今天的盤前快報已發過")
        return 0
    if now.hour * 60 + now.minute > 9 * 60 + 30 and not force:
        print("已經超過 09:30，不發盤前快報")
        return 0
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731
    intl = load("intel/intl.json", {}) or {}
    quotes = {q["sym"]: q for g in intl.get("groups", []) for q in g.get("quotes", [])}
    us = intl.get("usDate") or ""
    closed = today.isoformat() in _holidays()
    m = Msg(("【預覽】" if force else "") + "🌅 盤前快報", f"{md(today.isoformat())}（週{WEEK[today.weekday()]}）・美股 {md(us) if us else '—'} 收盤"
            + ("・今天台股休市" if closed else ""), accent="#f59e0b", url=f"{SITE}/global/", button="開啟國際類股連動")

    # 1) 台指期夜盤；抓不到就用富台指換算，再不行用 EWT
    nf = night_futures()
    ftw = ftw_quote()
    want = prev_trading_day(today).strftime("%Y%m%d")
    if nf and nf["date"] == want:
        m.section("台指期夜盤", f"{nf['name'].replace('台指期', '台指期 ')}・{md(nf['date'][:4] + '-' + nf['date'][4:6] + '-' + nf['date'][6:])} 夜盤")
        m.kv("夜盤收盤", f"{nf['last']:,.0f}（{nf['diff']:+,.0f}，{nf['rate']:+.2f}%）", color=sign_tone(nf["diff"]))
        if nf["spot"]:
            gap = nf["last"] - nf["spot"]
            m.kv("對加權指數收盤", f"{gap:+,.0f} 點（{gap / nf['spot'] * 100:+.2f}%）", color=sign_tone(gap))
        if nf["high"] and nf["low"]:
            m.kv("夜盤高／低", f"{nf['high']:,.0f}／{nf['low']:,.0f}")
        m.kv("成交量", f"{nf['vol']:,} 口")
        if ftw:
            m.kv("富台指", f"{ftw['price']:,.2f}（{ftw['pct']:+.2f}%）", color=sign_tone(ftw["pct"]))
    else:
        atm = (load("market/atmosphere.json", {}) or {}).get("days") or []
        ix = (nf or {}).get("spot") or (atm[-1].get("ix") if atm else None)
        ewt = None if ftw else ewt_proxy()
        if ftw:
            m.section("台指期預估（富台指換算）")
            m.kv("富台指", f"{ftw['price']:,.2f}（{ftw['pct']:+.2f}%）", color=sign_tone(ftw["pct"]))
            if ix:
                est = ix * (1 + ftw["pct"] / 100)
                m.kv("換算加權指數", f"{est:,.0f}（{est - ix:+,.0f} 點）", color=sign_tone(ftw["pct"]))
            m.note("期交所夜盤資料暫時抓不到，改用富台指漲跌幅換算，僅供參考")
        else:
            m.section("台股夜間參考（EWT 換算）")
            if ewt:
                m.kv(f"EWT 台灣 ETF（{md(ewt['date'])}）", f"{ewt['chg']:+.2f}%", color=sign_tone(ewt["chg"]))
                if ix:
                    est = ix * (1 + ewt["chg"] / 100)
                    m.kv("換算加權指數", f"{est:,.0f}（{est - ix:+,.0f} 點）", color=sign_tone(ewt["chg"]))
            m.note("期交所夜盤與富台指都抓不到，改用美股 EWT 的漲跌換算，僅供參考")

    # 2) 美股主要指數
    m.section("美股主要指數")
    for sym, name in (("^DJI", "道瓊"), ("^GSPC", "S&P 500"), ("^IXIC", "那斯達克"), ("^SOX", "費城半導體"), ("TSM", "台積電 ADR"), ("TWD=X", "美元兌台幣")):
        q = quotes.get(sym)
        if q:
            fmt = f"{q['close']:,.2f}" if q["close"] < 100 else f"{q['close']:,.0f}"
            m.kv(name, f"{fmt}（{q['chg']:+.2f}%）", color=sign_tone(q["chg"]) if sym != "TWD=X" else "#0F172A")

    # 3) 市場風險
    rk = load("risk.json", {}) or {}
    if rk.get("temp") is not None:
        m.section("市場風險", f"溫度 {rk['temp']:.0f}・{rk['tempLabel']}")
        lv = {"正常": "#0F172A", "警戒": "#D97706", "危險": "#E5484D"}
        for i in rk.get("indicators", []):
            if i["id"] not in ("vix", "vvix", "vixts", "move", "hy"):
                continue
            unit = " bp" if i["unit"] == "bp" else ""
            chg = i["chg20"] if i["id"] == "hy" else i["chg1"]
            tag = "（20日 " if i["id"] == "hy" else "（"
            val = f"{i['value']:,.{i['dec']}f}{unit}" + ("" if chg is None else f"{tag}{chg:+,.{i['dec']}f}）")
            m.kv(i["name"] + ("" if i["level"] == "正常" else f"・{i['level']}"), val, color=lv[i["level"]])
        cr = [c for c in rk.get("credit", []) if c["value"] >= 50][:5]
        if cr:
            m.kv("科技廠隱含 CDS（5 日）", "、".join(f"{c['sym']} {c['value']:.0f}({c['chg5']:+.0f})" for c in cr))
        for x in rk.get("alerts", [])[:5]:
            m.line(f"⚠ {x}", color="#D97706")

    # 4) 類股龍頭與台股預估反應：龍頭漲跌幅大的優先
    NAME = {"^SOX": "費半", "CL=F": "原油", "HG=F": "銅", "GC=F": "黃金", "SI=F": "白銀", "BDI": "BDI", "SCFI": "SCFI"}
    rows = []
    for g in intl.get("groups", []):
        if g["name"] in ("美股大盤", "美元兌台幣", "費城半導體"):
            continue
        q = next((x for x in g.get("quotes", []) if x["sym"] == g.get("lead")), None) or (g.get("quotes") or [None])[0]
        if q and q.get("chg") is not None:
            rows.append((g, q))
    rows.sort(key=lambda x: -abs(x[1]["chg"]))
    if rows:
        m.section("類股龍頭 → 台股預估", f"美股 {md(us)}" if us else "")
        m.cols("收盤", "漲跌")
        for g, q in rows[:9]:
            react = [x for x in (q.get("react") or []) if abs(x.get("exp") or 0) >= 0.3][:4]
            sub = ("台股：" + "、".join(f"{x['name']} {x['exp']:+.1f}%" for x in react)) if react else \
                ("相關：" + "、".join(x["name"] for x in g.get("members", [])[:4]) if g.get("members") else "")
            if q.get("date") and us and q["date"] != us:
                sub = f"（{md(q['date'])}）" + sub
            close = f"{q['close']:,.2f}" if q["close"] < 1000 else f"{q['close']:,.0f}"
            m.stock(g["name"], NAME.get(q["sym"], q["sym"]), close, f"{q['chg']:+.2f}%", color=sign_tone(q["chg"]), sub=sub)
        m.note("台股預估＝β × 龍頭漲跌（過去約半年的隔日連動），只列預估 ±0.3% 以上的股票，僅供參考")

    # 4) 85g 開高走低觀察：熱門股今天漲停或前 5 日漲 ≥ 10%，開盤落在開高 0～4% 的價位就是候選
    g85 = load("85g.json", {}) or {}
    cand = [c for c in g85.get("cand", []) if not c.get("noShort")]
    if cand and not closed:
        m.section("85g 開高走低觀察", f"{len(cand)} 檔")
        m.cols("近 5 日", "開在這裡就留意")
        for c in sorted(cand, key=lambda c: -(c["p5"] or 0))[:6]:
            m.stock(c["name"], c["code"], f"{c['p5']:+.1f}%", f"{c['lo']:g}～{c['hi']:g}", color="#D97706", sub=c.get("sector") or "")
        m.note("開高 0～4%：09～10 點趁衝高分批賣，中午後低檔分批買回；一路創高就停損、不加碼，開漲停不碰")

    print(m.text())
    if dry:
        return 0
    if not force:
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now < target:
            wait = (target - now).total_seconds()
            print(f"等到 08:00 再發（{wait / 60:.0f} 分鐘）")
            import time
            time.sleep(wait)
    if not send(m):
        print("（沒有設定任何推播管道，只印出內容）")
    if not force:
        state["sent"] = sorted(set(state["sent"]) | {today.isoformat()})[-60:]
        MORNING_STATE.parent.mkdir(parents=True, exist_ok=True)
        MORNING_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


EXDIV_STATE = ROOT / "data" / "notify" / "exdiv-alerted.json"


def exdiv_alert(dry: bool, force: bool = False) -> int:
    """除權息黑K：明天除息、符合條件（殖利率 ≥ 4%、日均成交 ≥ 5000 萬、總公司分點近 30 天淨買超 ≥ 2%）的放空候選，以及明天該回補的部位；沒有就不發"""
    ex = load("exdiv.json", {}) or {}
    asof, nxt = ex.get("asof"), ex.get("next")
    if asof != last_trading_day() and not force:
        print(f"除權息資料還沒更新（{asof}）")
        return 0
    try:
        state = json.loads(EXDIV_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    if asof in state["sent"] and not force:
        print(f"{asof} 的除權息黑K已推過")
        return 0
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731
    cand = [u for u in ex.get("upcoming", []) if u["tomorrow"] and u["ok"]]
    cover = [a for a in ex.get("active", []) if a.get("exit") == nxt]
    soon = [u for u in ex.get("upcoming", []) if u["ok"] and not u["tomorrow"]][:8]
    if not cand and not cover and not force:
        print("明天沒有除息候選、也沒有要回補的部位")
        if not dry:
            state["sent"] = sorted(set(state["sent"]) | {asof})[-60:]
            EXDIV_STATE.parent.mkdir(parents=True, exist_ok=True)
            EXDIV_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
        return 0
    btd = ex.get("backtest") or {}
    bt = next((g for g in btd.get("hqGroups", []) if "總公司淨買 ≥" in g["group"] and "有個股期" in g["group"]), None) \
        or next((g for g in btd.get("groups", []) if "有個股期" in g["group"] and "4%" in g["group"]), None)
    m = Msg(("【預覽】" if force else "") + "📉 除權息黑K", f"{md(nxt)} 除息日開盤放空・持有 {ex.get('hold', 4)} 天", accent="#E5484D",
            url=f"{SITE}/exdiv/", button="開啟除權息黑K")
    m.section(f"{md(nxt)} 除息放空候選", f"{len(cand)} 檔")
    if cand:
        m.cols("現金股利", "殖利率")
        for u in sorted(cand, key=lambda u: -(u["y"] or 0)):
            hq = f"總公司 30 日 {u['hq']:+.1f}%（{u['hqLots']:+,} 張）" if u.get("hq") is not None else ""
            tags = "・".join(x for x in (hq, "有個股期" if u["sf"] else "無個股期", "可現沖先賣" if not u["noShort"] else "暫停先賣後買",
                                         f"日均 {u['valYi']:g} 億") if x)
            m.stock(u["name"], u["code"], f"{u['cash']:g} 元", f"{u['y']:.2f}%", color="#D97706", sub=tags)
    else:
        m.line("明天沒有符合條件的除息股", color="#64748B")
    if cover:
        m.section(f"⏰ {md(nxt)} 收盤回補", f"{len(cover)} 檔")
        m.cols("除息日", "目前損益")
        for a in cover:
            m.stock(a["name"], a["code"], md(a["date"]), f"{a['ret']:+.2f}%", color=sign_tone(a["ret"]))
    if soon:
        m.section("之後兩週的候選")
        for u in soon:
            m.stock(u["name"], u["code"], md(u["date"]), f"{u['y']:.2f}%", color="#D97706")
    if bt:
        m.note(f"回測（{bt['n']} 次，{bt['group']}）：放空 4 天平均 {bt['avg']:+.2f}%、勝率 {bt['win']:.0f}%，扣個股期成本 {bt['netFut']:+.2f}%")
    print(m.text())
    if not dry:
        if not send(m):
            print("（沒有設定任何推播管道，只印出內容）")
        if not force:
            state["sent"] = sorted(set(state["sent"]) | {asof})[-60:]
            EXDIV_STATE.parent.mkdir(parents=True, exist_ok=True)
            EXDIV_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


ETF_STATE = ROOT / "data" / "notify" / "etf-sent.json"


def etf_alert(dry: bool, force: bool = False) -> int:
    """每日 ETF 持股變化摘要（週一到五 20:00）：主動 ETF 合計買賣超（扣除申購贖回）、新建倉／出清、
    各主動 ETF 最大動作、被動 ETF 成分異動、ETF 資金流入流出。同一份持股日期只發一次"""
    core = load("etf/core.json", {}) or {}
    act = load("etf/active.json", {}) or {}
    aum = load("etf/aum.json", {}) or {}
    etfs = core.get("etfs", [])
    names = {c: n.rstrip("*") for c, n in {**core.get("names", {}), **act.get("names", {})}.items()}
    now = datetime.now(TPE_TZ)
    if now.weekday() >= 5 and not force:
        print("週末不發 ETF 摘要")
        return 0
    if now.hour * 60 + now.minute > 22 * 60 + 30 and not force:
        print("已經超過 22:30，不發 ETF 摘要")
        return 0
    ev = {int(k): v[-1] for k, v in act.get("events", {}).items() if v}
    if not ev:
        print("沒有主動式 ETF 持股資料")
        return 0
    day = max(e[0] for e in ev.values())
    try:
        state = json.loads(ETF_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    if day in state["sent"] and not force:
        print(f"{day} 的 ETF 持股變化已推過（新的持股還沒公布）")
        return 0
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731
    short = lambda i: re.sub(r"^主動", "", etfs[i]["n"])  # noqa: E731
    wl = set(watchlist())

    # 主動 ETF：同一天的變化加總（扣除申購贖回後的股數 × 收盤價）
    agg: dict[str, dict] = {}
    per = []
    today_ev = {i: e for i, e in ev.items() if e[0] == day}
    for i, (d, pd, ratio, rows) in today_ev.items():
        moves = []
        for code, raw, adj, px in rows:
            # 原始股數沒變的只是申購贖回造成的比例差（持股還沒跟著調整），不算買賣；小於 500 萬也略過
            if not px or not raw or not adj or abs(adj * px) < 5e6:
                continue
            v = adj * px / 1e8
            a = agg.setdefault(code, {"v": 0.0, "buy": [], "sell": [], "new": [], "out": []})
            a["v"] += v
            (a["buy"] if v > 0 else a["sell"]).append(i)
            moves.append((code, v))
        moves.sort(key=lambda x: -abs(x[1]))
        if moves:
            per.append((i, moves))
    # 新建倉／出清：看原始股數從 0 變有、從有變 0
    chg = {i: rows for i, rows in core.get("changes", [])}
    for i in today_ev:
        for code, ps, cs, pw, cw, val in chg.get(i, []):
            if code in agg:
                if not ps and cs:
                    agg[code]["new"].append(i)
                elif ps and not cs:
                    agg[code]["out"].append(i)
    buys = sorted((x for x in agg.items() if x[1]["v"] >= 0.05), key=lambda x: -x[1]["v"])[:8]
    sells = sorted((x for x in agg.items() if x[1]["v"] <= -0.05), key=lambda x: x[1]["v"])[:8]
    m = Msg(("【預覽】" if force else "") + "📊 ETF 持股變化", f"{md(day)} 持股・主動 ETF {len(today_ev)} 檔有更新", accent="#8B5CF6",
            url=f"{SITE}/etf-flow/", button="開啟 ETF 頁")

    def ws(ids):
        return "、".join(etfs[i]["c"] for i in ids[:4]) + (f" 等 {len(ids)} 檔" if len(ids) > 4 else "")

    m.section("主動 ETF 合計買超", "扣除申購贖回")
    if buys:
        m.cols("買／賣檔數", "金額")
        for code, a in buys:
            tag = ("新建倉：" + ws(a["new"]) + "・") if a["new"] else ""
            m.stock(names.get(code, code), code, f"{len(a['buy'])}／{len(a['sell'])}", f"+{a['v']:.2f} 億", color=sign_tone(1), sub=tag + "買：" + ws(a["buy"]), star=code in wl)
    else:
        m.line("沒有明顯買超", color=FLAT)
    m.section("主動 ETF 合計賣超", "扣除申購贖回")
    if sells:
        m.cols("買／賣檔數", "金額")
        for code, a in sells:
            tag = ("出清：" + ws(a["out"]) + "・") if a["out"] else ""
            m.stock(names.get(code, code), code, f"{len(a['buy'])}／{len(a['sell'])}", f"{a['v']:.2f} 億", color=sign_tone(-1), sub=tag + "賣：" + ws(a["sell"]), star=code in wl)
    else:
        m.line("沒有明顯賣超", color=FLAT)
    # 其他新建倉／出清（不在上面兩張表裡的）
    shown = {c for c, _ in buys + sells}
    newo = [(c, a) for c, a in agg.items() if c not in shown and (a["new"] or a["out"])]
    if newo:
        m.section("其他新建倉／出清")
        for c, a in sorted(newo, key=lambda x: -abs(x[1]["v"]))[:6]:
            txt = "・".join(x for x in (("新建倉 " + ws(a["new"])) if a["new"] else "", ("出清 " + ws(a["out"])) if a["out"] else "") if x)
            m.line(f"{'★' if c in wl else ''}{names.get(c, c)} {c}：{txt}（{a['v']:+.2f} 億）", color=sign_tone(a["v"]))
    # 各主動 ETF 最大動作（依規模）
    per.sort(key=lambda x: -(etfs[x[0]].get("aum") or 0))
    if per:
        m.section("各主動 ETF 最大動作", f"前 {min(8, len(per))} 大")
        for i, moves in per[:8]:
            b = [x for x in moves if x[1] > 0][:2]
            sl = [x for x in moves if x[1] < 0][:2]
            txt = "　".join(x for x in ("買 " + "、".join(f"{names.get(c, c)} {v:+.1f}億" for c, v in b) if b else "",
                                         "賣 " + "、".join(f"{names.get(c, c)} {v:+.1f}億" for c, v in sl) if sl else "") if x)
            m.stock(etfs[i]["c"], short(i), "", f"{(etfs[i].get('aum') or 0) / 1e8:,.0f} 億", color=FLAT, sub=txt)
    # 被動 ETF：成分股新增／刪除（同一天）
    pas = []
    for i, rows in chg.items():
        if etfs[i]["k"] != "P" or etfs[i]["d"] != day:
            continue
        add = [r[0] for r in rows if not r[1] and r[2]]
        rm = [r[0] for r in rows if r[1] and not r[2]]
        if add or rm:
            pas.append((i, add, rm))
    if pas:
        m.section("被動 ETF 成分異動")
        for i, add, rm in sorted(pas, key=lambda x: -(etfs[x[0]].get("aum") or 0))[:6]:
            txt = "・".join(x for x in (("納入 " + "、".join(names.get(c, c) for c in add[:5])) if add else "",
                                         ("刪除 " + "、".join(names.get(c, c) for c in rm[:5])) if rm else "") if x)
            m.stock(etfs[i]["c"], etfs[i]["n"], "", "", color=FLAT, sub=txt)
    # 資金流入流出（申購贖回金額）
    rows = [r for r in aum.get("rows", []) if r[7]]
    if rows and aum.get("date"):
        m.section(f"ETF 資金流向（{md(aum['date'])}）")
        for lab, rs in (("流入", sorted(rows, key=lambda r: -r[7])[:4]), ("流出", sorted(rows, key=lambda r: r[7])[:3])):
            rs = [r for r in rs if (r[7] > 0) == (lab == "流入")]
            if rs:
                m.kv(lab, "、".join(f"{r[0]} {r[7] / 1e8:+.0f}億" for r in rs), color=sign_tone(rs[0][7]))
    m.note("主動 ETF 金額＝股數變化（已扣除申購贖回造成的等比例增減）× 收盤價；★＝自選股")
    print(m.text())
    if dry:
        return 0
    if not force:
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now < target:
            import time
            print(f"等到 20:00 再發（{(target - now).total_seconds() / 60:.0f} 分鐘）")
            time.sleep((target - now).total_seconds())
    if not send(m):
        print("（沒有設定任何推播管道，只印出內容）")
    if not force:
        state["sent"] = sorted(set(state["sent"]) | {day})[-60:]
        ETF_STATE.parent.mkdir(parents=True, exist_ok=True)
        ETF_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


RISK_STATE = ROOT / "data" / "notify" / "risk-alerted.json"


def risk_triggers(rk: dict) -> dict:
    """目前成立的風險條件：key → 說明。條件消失後再出現會重新提醒"""
    out = {}
    if rk.get("tempLabel") in ("偏高", "高"):
        out[f"temp:{rk['tempLabel']}"] = f"風險溫度 {rk['temp']:.0f}，進入「{rk['tempLabel']}」"
    for i in rk.get("indicators", []):
        if i["level"] != "正常" and i.get("core"):
            unit = "bp" if i["unit"] == "bp" else ""
            out[f"{i['id']}:{i['level']}"] = f"{i['name']} {i['value']:,.{i['dec']}f}{unit}，達{i['level']}門檻"
    hy = next((i for i in rk.get("indicators", []) if i["id"] == "hy"), None)
    if hy and (hy.get("chg20") or 0) >= 50:
        out["hy:widen"] = f"高收益債利差 20 日擴大 {hy['chg20']:.0f}bp"
    vix = next((i for i in rk.get("indicators", []) if i["id"] == "vix"), None)
    if vix and vix.get("chg1") and vix["value"] - vix["chg1"] > 0 and vix["chg1"] / (vix["value"] - vix["chg1"]) >= 0.2:
        out[f"vix:jump:{vix['date']}"] = f"VIX 單日大漲 {vix['chg1'] / (vix['value'] - vix['chg1']) * 100:.0f}%（{vix['value']:.1f}）"
    for c in rk.get("credit", []):
        if c["sym"] in rk.get("cdsJumps", []):
            out[f"cds:{c['sym']}"] = f"{c['name']} 股價隱含 CDS 5 日 +{c['chg5']:.0f}bp（{c['v5']:.0f} → {c['value']:.0f}bp）"
    return out


def risk_alert(dry: bool, force: bool = False) -> int:
    """市場風險警示：有新的風險條件成立就推（夜間 23:00～07:30 不推，留到早上）"""
    rk = load("risk.json", {}) or {}
    if rk.get("temp") is None:
        print("沒有風險資料")
        return 0
    now = datetime.now(TPE_TZ)
    quiet = now.hour >= 23 or now.hour * 60 + now.minute < 7 * 60 + 30
    try:
        state = json.loads(RISK_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = None
    cur = risk_triggers(rk)
    if state is None and not force:  # 第一次執行：現有條件當作已提醒
        state = {"active": sorted(cur)}
        if not dry:
            RISK_STATE.parent.mkdir(parents=True, exist_ok=True)
            RISK_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
        print("第一次執行，記錄目前條件：", list(cur))
        return 0
    new = [k for k in cur if force or k not in set((state or {}).get("active", []))]
    if not new:
        print("沒有新的風險警示")
    elif quiet and not force:
        print("夜間不推播，留到早上：", new)
        return 0
    md = lambda d: f"{int(d[5:7])}/{int(d[8:10])}"  # noqa: E731
    if new:
        t = rk["temp"]
        m = Msg(("【預覽】" if force else "") + "🚨 市場風險警示", f"美股 {md(rk['asof'])} 收盤・風險溫度 {t:.0f}（{rk['tempLabel']}）",
                accent="#E5484D", url=f"{SITE}/risk/", button="開啟市場風險監控")
        m.section("新觸發", f"{len(new)} 項")
        for k in new:
            m.line(f"⚠ {cur[k]}", color="#E5484D", bold=True)
        others = [v for k, v in cur.items() if k not in new]
        if others:
            m.section("持續中")
            for v in others[:6]:
                m.line(f"・{v}", color="#D97706")
        moved = sorted((c for c in rk.get("credit", []) if c["value"] >= 50), key=lambda c: -c["chg5"])[:6]
        if moved:
            m.section("科技廠股價隱含 CDS")
            m.cols("5 日變化", "目前")
            for c in moved:
                m.stock(c["name"], c["sym"], f"{c['chg5']:+.0f}bp", f"{c['value']:.0f}bp", color=sign_tone(c["chg5"]))
        m.note("股價隱含 CDS 由 CreditGrades 模型以股價、波動度與負債估算，非市場實際 CDS 報價；只看變化方向與幅度")
        print(m.text())
        if not dry and not send(m):
            print("（沒有設定任何推播管道，只印出內容）")
    if not dry and not force:
        state = {"active": sorted(cur)}
        RISK_STATE.parent.mkdir(parents=True, exist_ok=True)
        RISK_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


INTEL_STATE = ROOT / "data" / "notify" / "intel-alerted.json"


def intel_alert(dry: bool) -> int:
    try:
        state = json.loads(INTEL_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = None
    rep = load("intel/reports.json", {}) or {}
    rows = rep.get("rows") or []
    first = state is None
    if first:  # 第一次執行：現有的都當作推過，避免一次灌爆
        state = {"reports": [r[13] for r in rows]}
    seen = set(state["reports"])
    wl = set(watchlist())
    msgs = []

    # 1) 新券商報告（FactSet 共識只推自選股的）
    new = [r for r in rows if r[13] not in seen and (r[9] == "broker" or r[1] in wl)]
    if new:
        m = Msg("📑 新券商報告", f"{len(new)} 份", accent="#8b5cf6", url=f"{SITE}/reports/", button="開啟券商報告")
        m.cols("券商", "目標價")
        for r in new[:12]:
            d, code, name, broker, rating, tgt, prev, up = r[:8]
            chg = "" if prev is None else ("維持" if prev == tgt else f"{'調升' if tgt > prev else '調降'}（前次 {prev:g}）")
            info = "・".join(x for x in (f"潛在 {up:+.1f}%" if up is not None else "", chg, rating or "") if x)
            hl = (r[11][0][:70] + ("…" if len(r[11][0]) > 70 else "")) if r[11] else ""
            color = sign_tone(tgt - prev) if prev is not None and prev != tgt else "#0F172A"
            m.stock(name, code, broker[:6], f"{tgt:g}", color=color, star=code in wl, sub="\n".join(x for x in (info, hl) if x))
        if len(new) > 12:
            m.note(f"還有 {len(new) - 12} 份，見網站")
        msgs.append(m)

    # 國際類股大波動不另外推：統一由 08:00 盤前快報（--morning）涵蓋

    for m in msgs:
        print(m.text() + "\n")
        if not dry and not first and not send(m):
            print("（沒有設定任何推播管道，只印出內容）")
    if not msgs:
        print("沒有新的券商報告")
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
    ap.add_argument("--strategy-alert", action="store_true")
    ap.add_argument("--turnover-alert", action="store_true")
    ap.add_argument("--exdiv-alert", action="store_true", help="除權息黑K：明天除息的放空候選與明天要回補的部位")
    ap.add_argument("--risk-alert", action="store_true", help="市場風險警示：風險溫度偏高、指標達警戒／危險、VIX 暴漲、信用利差擴大、科技廠隱含 CDS 跳升")
    ap.add_argument("--etf-alert", action="store_true", help="每日 ETF 持股變化摘要（週一到五 20:00；加 --preview 立刻發預覽）")
    ap.add_argument("--morning", action="store_true", help="盤前快報：台指期夜盤、美股主要指數、類股龍頭與台股預估（08:00 發）")
    ap.add_argument("--preview", action="store_true", help="不管有沒有推過，把每日戰報、策略、高週轉三張卡片各發一次（測試排版用）")
    a = ap.parse_args()
    if a.check:
        return check()
    if a.insider_alert:
        return insider_alert(a.dry_run)
    if a.intel_alert:
        return intel_alert(a.dry_run)
    if a.strategy_alert:
        return strategy_alert(a.dry_run)
    if a.turnover_alert:
        return turnover_alert(a.dry_run)
    if a.morning:
        return morning_brief(a.dry_run, force=a.preview)
    if a.etf_alert:
        return etf_alert(a.dry_run, force=a.preview)
    if a.exdiv_alert:
        return exdiv_alert(a.dry_run, force=a.preview)
    if a.risk_alert:
        return risk_alert(a.dry_run, force=a.preview)
    if a.preview:
        msg = compose()
        msg.title = "【預覽】" + msg.title
        print(msg.text())
        if not a.dry_run:
            send(msg)
        strategy_alert(a.dry_run, force=True)
        turnover_alert(a.dry_run, force=True)
        return 0
    msg = compose()
    print(msg.text())
    if a.dry_run:
        return 0
    if not send(msg):
        print("\n（沒有設定任何推播管道，只印出內容。設定方式見本檔開頭說明。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
