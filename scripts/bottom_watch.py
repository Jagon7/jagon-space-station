#!/usr/bin/env python3
"""
抄底訊號監控（scripts/research_bottom.py 回測的訊號）→ LINE

回檔中（加權距 60 日高點跌幅 ≥ 8%）每天推一次狀態；出現進場訊號時標明
  訊號 A「深跌＋美股大漲」：跌幅 ≥ 12%，且前一晚 S&P500 漲 ≥ 1.5% → 當天收盤進場（早上 08:40 就能知道）
  訊號 B「深跌＋VIX 回落＋止跌」：跌幅 ≥ 12%，當天收紅，VIX 比 10 日高點回落 ≥ 10% 且仍 ≥ 22 → 當天收盤進場（收盤後才確定）
  加分：年線（200 日均線）仍向上（回測 2018 以後這種情況 20 天勝率 100%、平均再跌 1～2%）
  不建議：深跌當天直接接刀（20 天內再破底機率 69～96%）
用法：python scripts/bottom_watch.py morning|evening [--dry-run]（morning 只看訊號 A；evening 看全部並推每日狀態）
"""
from __future__ import annotations

import json
import os
import statistics as st
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
STATE = DATA / "notify" / "bottom-sent.json"


def live_twii():
    """Yahoo 即時加權指數：(現價, 今天最高, 昨收)"""
    import requests
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII", params={"range": "1d", "interval": "1m"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30).json()["chart"]["result"][0]["meta"]
    return r["regularMarketPrice"], r.get("regularMarketDayHigh"), r.get("chartPreviousClose") or r.get("previousClose")


def intraday(mode: str, dry: bool, rows: list, ma200s: float) -> int:
    """訊號 B 盤中預告（13:20，收盤前還來得及進場）與收盤確認（13:40）"""
    now = datetime.now(TPE)
    today = now.date().isoformat()
    tw = json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]
    hist = [r for r in tw if r[0] < today][-59:]  # 不含今天的前 59 天
    if now.weekday() >= 5 and not dry and "--test" not in sys.argv:
        return 0
    px, day_hi, _ = live_twii()
    prev = hist[-1][4]  # 昨收用自己存的日線（Yahoo 即時資料的前收有時不對）
    hi60 = max([r[2] for r in hist] + [day_hi or px])
    dd = (px / hi60 - 1) * 100
    up = px > prev
    vix = json.loads((DATA / "research" / "yahoo" / "_VIX.json").read_text(encoding="utf-8"))["d"]
    vx = [r[4] for r in vix if r[0] < today][-10:]
    voff = (1 - vx[-1] / max(vx)) * 100
    ok = dd <= -12 and up and voff >= 10 and vx[-1] >= 22
    print(f"{mode}：加權 {px:,.0f}（昨收 {prev:,.0f}，{(px / prev - 1) * 100:+.2f}%）距 60 日高 {dd:.1f}%、VIX {vx[-1]:.1f} 回落 {voff:.0f}% → 訊號 B {'成立' if ok else '不成立'}")
    test = "--test" in sys.argv  # 測試推播：不管訊號成不成立都發一則【測試】，不記錄已發送
    if not ok and not dry and not test:
        return 0
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    key = f"{today}-B-{mode}"
    if key in state["sent"] and not dry and not test:
        return 0
    from line_flex import Msg
    import notify
    pre = mode == "preclose"
    head = ("🟢 抄底訊號 B 盤中成立（收盤前可進場）" if pre else "🟢 抄底訊號 B 收盤確認")
    if (dry or test) and not ok:
        head = "抄底訊號 B 卡片樣式（⚠️ 訊號實際未成立）"
    m = Msg(("【測試】" if dry or test else "") + head,
            f"{now:%m/%d %H:%M}・加權 {px:,.0f}（{(px / prev - 1) * 100:+.2f}%）", accent="#16A34A", url=f"{notify.SITE}/bottom/", button="開啟抄底雷達")
    m.kv("距 60 日高點", f"{dd:.1f}%")
    m.kv("今天", "收紅" if up else "收黑")
    m.kv("VIX", f"{vx[-1]:.1f}（比 10 日高點回落 {voff:.0f}%）")
    m.kv("年線", f"{'仍向上' if ma200s > 0 else '已向下（2008 型，訊號容易失效）'}（{ma200s:+.1f}%）")
    m.line("回測：20 天後平均 +2.2%／+5.5%（2005-17／2018-26），勝率 67%／71%；進場後平均再跌 4～5%" + ("" if not pre else "。13:30 收盤若翻黑就不成立"))
    m.note("建議：分批（先 1/3）、停損設在今天低點下方；工具以價平買權風險最小。只供參考，不構成投資建議。")
    if test:
        m.note(f"⚠️ 這是測試推播，訊號實際上{'成立' if ok else '沒有成立'}；正式推播只會在訊號成立時發出")
    print(m.text())
    if dry:
        return 0
    notify.send(m)
    if test:
        return 0
    state["sent"] = (state["sent"] + [key])[-80:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "evening"
    dry = "--dry-run" in sys.argv
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "fetch_research_data.py"), "--quick"], check=False, capture_output=True)
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "research_bottom.py")], check=False, capture_output=True)
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "research_bottom_multi.py")], check=False, capture_output=True)  # 網頁「抄底雷達」
    rows = json.loads((DATA / "research" / "bottom_rows.json").read_text(encoding="utf-8"))
    tw = json.loads((DATA / "research" / "yahoo" / "_TWII.json").read_text(encoding="utf-8"))["d"]
    c = [r[4] for r in tw]
    ma200s = (st.mean(c[-200:]) / st.mean(c[-260:-60]) - 1) * 100
    r = rows[-1]
    now = datetime.now(TPE)
    today = now.date().isoformat()
    if mode in ("preclose", "close"):
        return intraday(mode, dry, rows, ma200s)
    if mode == "morning":
        # 早上：用昨天收盤的跌幅＋昨晚美股
        if r["date"] >= today:
            r = rows[-2]
        spx = json.loads((DATA / "research" / "yahoo" / "_GSPC.json").read_text(encoding="utf-8"))["d"]
        spx_last = (spx[-1][4] / spx[-2][4] - 1) * 100
        sig_a = r["dd"] <= -12 and spx_last >= 1.5
        if not sig_a and not dry:
            print(f"早上沒有訊號 A（跌幅 {r['dd']:.1f}%、昨晚 S&P {spx_last:+.2f}%）")
            return 0
        sigs = [("A", f"深跌＋美股大漲：跌幅 {r['dd']:.1f}%、昨晚 S&P500 {spx_last:+.2f}%", sig_a)]
    else:
        if r["date"] != today and not dry:
            print(f"今天（{today}）的收盤資料還沒到（最新 {r['date']}）")
            return 0
        sig_a = r["dd"] <= -12 and (r["spx1"] or 0) >= 1.5
        sig_b = r["dd"] <= -12 and (r["vixOff"] or 0) >= 10 and (r["vix"] or 0) >= 22 and r["upDay"]
        if r["dd"] > -8 and not dry:
            print(f"沒有在回檔（跌幅 {r['dd']:.1f}%）")
            return 0
        sigs = [("A", f"深跌＋美股大漲（今早已知）：前一晚 S&P {r['spx1']:+.2f}%", sig_a),
                ("B", f"深跌＋VIX 回落＋止跌：今天{'收紅' if r['upDay'] else '收黑'}、VIX {r['vix']:.1f}（比 10 日高點回落 {r['vixOff'] or 0:.0f}%）", sig_b)]
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    key = f"{today}-{mode}"
    if key in state["sent"] and not dry:
        print("已推過")
        return 0
    from line_flex import Msg, sign_tone
    import notify
    fired = [s for s in sigs if s[2]]
    title = ("🟢 抄底訊號 A 成立（今天收盤前可進場）" if mode == "morning" else "🟢 抄底訊號出現") if fired else "🔴 還沒有抄底訊號"
    m = Msg(("【測試】" if dry else "") + title, f"{r['date'][5:7]}/{r['date'][8:10]} 收盤・加權距 60 日高點 {r['dd']:.1f}%",
            accent="#16A34A" if fired else "#DC2626", url=f"{notify.SITE}/", button="開啟網站")
    for code, txt, ok in sigs:
        m.kv(f"{'✅' if ok else '⬜'} 訊號 {code}", txt, color="#16A34A" if ok else None)
    m.kv("年線（200 日均線）", f"{'仍向上' if ma200s > 0 else '已向下'}（60 天前比 {ma200s:+.1f}%）", color="#16A34A" if ma200s > 0 else "#DC2626")
    m.section("目前狀態")
    m.kv("加權收盤", f"{r['close']:,.0f}（今天 {r['ret1']:+.2f}%）", color=sign_tone(r["ret1"]))
    m.kv("RSI14／20 日乖離", f"{r['rsi']:.0f}／{r['bias20']:+.1f}%")
    m.kv("VIX", f"{r['vix']:.1f}（10 日高點回落 {r['vixOff'] or 0:.0f}%）")
    if r.get("margin"):
        m.kv("大盤融資維持率", f"{r['margin']:.0f}%")
    m.kv("費半距 120 日高點", f"{r['soxDD']:.1f}%")
    m.section("回測（2005～2026，同一波只算第一次）")
    m.line("A：20 天後平均 +2.4%／+4.7%（2005-17／2018-26），勝率 70%／77%，進場後平均再跌 3.8%／2.3%")
    m.line("B：20 天後平均 +2.2%／+5.5%，勝率 67%／71%，進場後平均再跌 4.5%／3.6%")
    m.line("年線仍向上時 A：2018 後 7 次全賺，平均 +6.6%；深跌當天直接接刀：20 天內再破底機率 69～96%")
    m.note("2008 年金融海嘯（年線向下）時訊號連續失效、一路再跌 30%：進場仍要設停損（例如跌破訊號日低點），並控制部位。只供參考，不構成投資建議。")
    print(m.text())
    if dry:
        return 0
    notify.send(m)
    state["sent"] = (state["sent"] + [key])[-60:]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
