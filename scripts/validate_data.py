#!/usr/bin/env python3
"""
資料數值驗證：不只看「有沒有更新」，還要確認數字對不對

做法：同一個數字用兩個獨立來源或兩種算法對照，或用定義上必然成立的關係檢查
  行情   加權指數（證交所）vs Yahoo ^TWII 收盤；指數漲跌% vs 前一天指數；個股 收盤−前一天收盤 ＝ 漲跌；
         開高低收順序；漲跌幅不超過漲跌停（新上市／除權息除外，容許少數）；上市／上櫃檔數
  融資   個股融資餘額加總 vs 交易所公布的大盤融資餘額；今天餘額−昨天餘額 ＝ 增減；餘額 ≤ 融資限額
  法人   外資＋投信＋自營 ＝ 合計
  股數   發行股數檔數；週轉率、融資÷股本不可能 > 100%（超過代表股數錯）
  期貨   台指期價格 vs 加權指數（價差 ±5% 內）
  國際   Yahoo 各市場日線：日期遞增不重複、沒有空值、單日漲跌 > 25% 列出
  研究   抄底雷達的跌幅／RSI 用 Yahoo 原始資料重算一次對照；抄底選股候選的跌幅／融資使用率用每日行情重算；
         數值範圍（跌幅 −100～0%、融資使用率 0～100%）
結果寫 data/validation.json（網站「資料健檢」頁），有錯誤就發 LINE（同一天同樣的錯誤只通知一次）
用法：python scripts/validate_data.py [--alert] [--dry-run]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
STATE = DATA / "notify" / "validation-alerted.json"
RES: list[dict] = []


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def res(cat: str, name: str, level: str, detail: str):
    """level：ok／warn（可能正常，例如除權息）／error（數字錯了）"""
    RES.append({"cat": cat, "name": name, "level": level, "detail": detail})


def check_daily():
    fs = sorted(glob.glob(str(DATA / "daily" / "20*.json")))[-6:]
    days = [(Path(f).stem, load(f, {}) or {}) for f in fs]
    days = [(d, j) for d, j in days if j.get("q")]
    if len(days) < 2:
        res("行情", "每日行情", "error", "最近沒有每日行情檔")
        return
    yh = {r[0]: r[4] for r in (load(DATA / "research" / "yahoo" / "_TWII.json", {}) or {}).get("d", [])}
    for (dp, a), (d, b) in zip(days, days[1:]):
        q, qa = b["q"], a["q"]
        tw = sum(1 for v in q.values() if v[1] == 0)
        otc = len(q) - tw
        res("行情", f"{d} 檔數", "ok" if tw >= 1000 and otc >= 700 else "error", f"上市 {tw}、上櫃 {otc}")
        # 加權指數：證交所 vs Yahoo、漲跌% vs 前一天
        ix, ixa = (b.get("ix") or [None])[0], (a.get("ix") or [None])[0]
        if ix and yh.get(d):
            diff = (yh[d] / ix - 1) * 100
            res("行情", f"{d} 加權指數（證交所 vs Yahoo）", "ok" if abs(diff) < 0.05 else "error", f"{ix:,.2f} vs {yh[d]:,.2f}（差 {diff:+.3f}%）")
        if ix and ixa and len(b["ix"]) > 1 and b["ix"][1] is not None:
            calc = (ix / ixa - 1) * 100
            res("行情", f"{d} 加權漲跌%", "ok" if abs(calc - b["ix"][1]) < 0.02 else "error", f"公布 {b['ix'][1]:+.2f}%，前一天指數算出 {calc:+.2f}%")
        # 個股：收盤−昨收＝漲跌、開高低收順序、漲跌停範圍
        n = bad = order = over = 0
        ex = []
        for c, v in q.items():
            o, h, l, cl, chg = v[2], v[3], v[4], v[5], v[6]
            if not cl:
                continue
            if h and l and o and not (l <= o <= h and l <= cl <= h and l > 0):
                order += 1
                ex.append(f"{c} 開高低收順序不對")
            p = (qa.get(c) or [None] * 6)[5]
            if p and chg is not None:
                n += 1
                if abs(cl - p - chg) > max(0.011, p * 0.0005):
                    bad += 1  # 除權息、減資、分割當天會不一致
                if abs(chg) / p > 0.105 and len(c) == 4 and c.isdigit():
                    over += 1
                    ex.append(f"{c} 漲跌 {chg / p * 100:+.1f}%")
        r = bad / n if n else 1
        res("行情", f"{d} 個股收盤−昨收＝漲跌", "ok" if r < 0.03 else "warn" if r < 0.08 else "error", f"{bad}/{n} 檔不一致（除權息、減資當天會不一致）")
        res("行情", f"{d} 開高低收／漲跌停", "ok" if order == 0 and over <= 3 else "warn" if order + over <= 10 else "error",
            f"順序錯 {order} 檔、漲跌超過 10% {over} 檔" + (f"：{'、'.join(ex[:5])}" if ex else ""))
        # 融資：個股加總 vs 官方大盤、今昨差＝增減、≤ 限額
        m, ma, off = b.get("m") or {}, a.get("m") or {}, b.get("off") or {}
        if m:
            for mk, key in ((0, "twse"), (1, "tpex")):
                tot = sum((m[c][0] or 0) for c in m if c in q and q[c][1] == mk)
                ofb = (off.get(key) or {}).get("mBal")
                if ofb:
                    diff = (tot / ofb - 1) * 100
                    res("融資", f"{d} {'上市' if mk == 0 else '上櫃'}融資餘額（個股加總 vs 官方）", "ok" if abs(diff) < 1 else "warn" if abs(diff) < 3 else "error",
                        f"{tot:,} vs {ofb:,} 張（差 {diff:+.2f}%）")
            n = bad = lim = 0
            for c, v in m.items():
                if c in ma and v[1] is not None and ma[c][0] is not None and v[0] is not None:
                    n += 1
                    bad += abs(v[0] - ma[c][0] - v[1]) > 1
                if len(v) > 8 and v[8] and v[0] and v[0] > v[8] * 1.001:
                    lim += 1
            r = bad / n if n else 1
            res("融資", f"{d} 個股融資 今天−昨天＝增減", "ok" if r < 0.01 else "warn" if r < 0.05 else "error", f"{bad}/{n} 檔不一致")
            if lim:
                res("融資", f"{d} 融資餘額超過限額", "warn", f"{lim} 檔")
        # 法人：外資＋投信＋自營＝合計
        ins = load(DATA / "insti" / f"{d}.json")
        if isinstance(ins, dict):
            ins = {c: v for c, v in ins.items() if isinstance(v, list) and len(v) >= 6}
            n = sum(1 for v in ins.values() if all(isinstance(x, (int, float)) for x in v[2:6]))
            bad = [c for c, v in ins.items() if all(isinstance(x, (int, float)) for x in v[2:6]) and abs(v[2] + v[3] + v[4] - v[5]) > 1]
            res("法人", f"{d} 外資＋投信＋自營＝合計", "ok" if not bad else "error", f"{len(bad)}/{n} 檔不一致" + (f"：{'、'.join(bad[:5])}" if bad else ""))
    # 發行股數：週轉率、融資÷股本
    sh = (load(DATA / "strategy" / "shares.json", {}) or {}).get("shares", {})
    d, b = days[-1]
    res("股數", "發行股數檔數", "ok" if len(sh) > 1800 else "error", f"{len(sh)} 檔（{(load(DATA / 'strategy' / 'shares.json', {}) or {}).get('updatedAt', '')[:10]}）")
    bad = [c for c, v in b["q"].items() if sh.get(c) and v[7] and v[7] * 1000 / sh[c] > 3]  # 當沖爆量時週轉率可以 > 100%
    bad += [c for c, v in (b.get("m") or {}).items() if sh.get(c) and v[0] and v[0] * 1000 / sh[c] > 1]
    res("股數", f"{d} 週轉率／融資÷股本 ≤ 100%", "ok" if not bad else "warn" if len(bad) <= 3 else "error",
        f"{len(bad)} 檔超過（股數可能錯）" + (f"：{'、'.join(sorted(set(bad))[:5])}" if bad else ""))
    # 期貨價格 vs 加權
    fut = load(DATA / "futures" / "daily.json", {}) or {}
    for dd in sorted(fut)[-3:]:
        px = (fut[dd] or {}).get("px")
        if px and yh.get(dd):
            g = (px / yh[dd] - 1) * 100
            res("期貨", f"{dd} 台指期 vs 加權", "ok" if abs(g) < 5 else "error", f"{px:,.0f} vs {yh[dd]:,.0f}（價差 {g:+.2f}%）")


def check_yahoo():
    for p in sorted((DATA / "research" / "yahoo").glob("*.json")):
        d = (load(p, {}) or {}).get("d") or []
        if not d:
            res("國際", p.stem, "error", "沒有資料")
            continue
        dates = [r[0] for r in d]
        dup = len(dates) - len(set(dates))
        order = sum(1 for a, b in zip(dates, dates[1:]) if b <= a)
        nulls = sum(1 for r in d[-300:] if any(x is None for x in r[1:5]))
        hl = sum(1 for r in d[-300:] if None not in r[1:5] and not (r[3] <= min(r[1], r[4]) + 1e-6 and r[2] >= max(r[1], r[4]) - 1e-6))
        big = 9 if p.stem == "_VIX" else 0.25  # VIX 單日暴漲是常態，另外用 CBOE 官方資料逐日對照
        jump = [f"{b[0]} {(b[4] / a[4] - 1) * 100:+.0f}%" for a, b in zip(d[-300:], d[-299:]) if a[4] and b[4] and abs(b[4] / a[4] - 1) > big]
        lv = "error" if dup or order or nulls else "warn" if jump or (hl > 3 and "=X" not in p.stem) else "ok"  # 匯率的高低點 Yahoo 常不含收盤
        res("國際", f"Yahoo {p.stem}（到 {dates[-1]}）", lv,
            f"重複 {dup}、順序錯 {order}、近 300 天空值 {nulls}、高低不合 {hl}" + (f"、單日 >25%：{'、'.join(jump[:3])}" if jump else ""))


def check_vix_cboe():
    """VIX：Yahoo vs CBOE 官方歷史檔（最近 20 天收盤）"""
    import csv
    import io
    import requests
    txt = requests.get("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", timeout=60).text
    cb = {}
    for r in csv.DictReader(io.StringIO(txt)):
        m, d, y = r["DATE"].split("/")
        cb[f"{y}-{m}-{d}"] = float(r["CLOSE"])
    yv = (load(DATA / "research" / "yahoo" / "_VIX.json", {}) or {}).get("d") or []
    bad = [f"{r[0]} {r[4]:.2f} vs {cb[r[0]]:.2f}" for r in yv[-20:] if r[0] in cb and abs(r[4] - cb[r[0]]) > 0.02]
    n = sum(1 for r in yv[-20:] if r[0] in cb)
    res("國際", "VIX（Yahoo vs CBOE 官方）", "ok" if n >= 15 and not bad else "error", f"近 20 天 {n} 天可對照，{len(bad)} 天不一致" + (f"：{'、'.join(bad[:3])}" if bad else ""))


def check_journals():
    """台指期策略、當沖復盤：用原始行情重算最近 5 天的結果"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import research_tx_regime as rr
    j = load(DATA / "futures" / "regime_journal.json", {}) or {}
    day = rr.load_dir(DATA / "futures" / "day")   # 和 tx_regime_review 同一套（清錯誤成交、結算日 13:29 平倉）
    fut = load(DATA / "futures" / "daily.json", {}) or {}
    for d in sorted(j)[-5:]:
        e = j[d]
        b = day.get(d)
        if not b or not e.get("result"):
            continue
        r = e["result"]
        bo, mr, _, _ = rr.simulate(b, e["orh"], e["orl"], None if d >= rr.MR_LAST_FROM else rr.EXIT_M)  # 規則修改前的紀錄用舊規則重算
        orb = [b[m] for m in range(rr.OR_M) if m in b]
        orh, orl = max(x[1] for x in orb), min(x[2] for x in orb)
        px = (fut.get(d) or {}).get("px")
        errs = []
        if abs(bo - r["bo"]) > 0.6 or abs(mr - r["mr"]) > 0.6:
            errs.append(f"BO/MR {r['bo']}/{r['mr']} vs 重算 {bo:.1f}/{mr:.1f}")
        if abs(orh - e["orh"]) > 3 or abs(orl - e["orl"]) > 3:  # 09:15 即時（永豐）vs 盤後期交所逐筆，容許幾點差
            errs.append(f"開盤區間 {e['orl']}～{e['orh']} vs 期交所 {orl}～{orh}")
        if px and abs(r["close"] - px) > 2:
            errs.append(f"收盤 {r['close']} vs 期交所日報 {px}")
        res("復盤", f"{d} 台指期策略（重算對照）", "ok" if not errs else "error", "全部一致" if not errs else "；".join(errs))
    j = load(DATA / "strategy" / "daytrade_journal.json", {}) or {}
    for d in [d for d in sorted(j) if j[d].get("result")][-5:]:
        q = (load(DATA / "daily" / f"{d}.json", {}) or {}).get("q") or {}
        n, errs = 0, []
        for k, rows in j[d]["result"].items():
            for x in rows:
                v = q.get(x["code"])
                if x.get("ret") is None or not v:
                    continue
                n += 1
                ret = -(v[5] / v[2] - 1) * 100
                gap = (v[2] / x["ref"] - 1) * 100
                if abs(x["open"] - v[2]) > 1e-6 or abs(x["close"] - v[5]) > 1e-6 or abs(ret - x["ret"]) > 0.011 or abs(gap - x["gap"]) > 0.011:
                    errs.append(f"{x['name']} 開 {x['open']}/{v[2]} 收 {x['close']}/{v[5]} 報酬 {x['ret']}/{ret:.2f}")
        # 推薦時的參考價＝前一天收盤
        prev = sorted(p.stem for p in (DATA / "daily").glob("20*.json") if p.stem < d)
        pq = (load(DATA / "daily" / f"{prev[-1]}.json", {}) or {}).get("q") or {} if prev else {}
        for k, rows in j[d]["picks"].items():
            for x in rows:
                pc = (pq.get(x["code"]) or [None] * 6)[5]
                if pc and abs(pc - x["ref"]) > 1e-6:
                    errs.append(f"{x['name']} 參考價 {x['ref']} vs 前一天收盤 {pc}")
        res("復盤", f"{d} 當沖復盤（{n} 檔重算對照）", "ok" if not errs else "error", "全部一致" if not errs else "、".join(errs[:3]))


def rsi(c, n=14):
    g = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    l_ = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = st.mean(g[:n]), st.mean(l_[:n])
    for i in range(n, len(g)):
        ag, al = (ag * (n - 1) + g[i]) / n, (al * (n - 1) + l_[i]) / n
    return 100 - 100 / (1 + ag / al) if al else 100


def check_research():
    tw = (load(DATA / "research" / "yahoo" / "_TWII.json", {}) or {}).get("d") or []
    rows = load(DATA / "research" / "bottom_rows.json", []) or []
    if rows and tw:
        r = rows[-1]
        k = next((i for i, x in enumerate(tw) if x[0] == r["date"]), None)
        if k is None:
            res("研究", "抄底雷達最新一筆", "error", f"{r['date']} 不在 Yahoo 日線裡")
        else:
            hi = max(x[2] for x in tw[max(0, k - 59):k + 1])
            dd = (tw[k][4] / hi - 1) * 100
            c = [x[4] for x in tw[:k + 1]]
            rr = rsi(c)
            ok = abs(dd - r["dd"]) < 0.05 and abs(r["close"] - tw[k][4]) < 0.01 and abs(rr - r["rsi"]) < 1
            res("研究", f"抄底雷達 {r['date']}（重算對照）", "ok" if ok else "error",
                f"跌幅 {r['dd']:.2f}% vs 重算 {dd:.2f}%、RSI {r['rsi']:.1f} vs {rr:.1f}、收盤 {r['close']:,.2f} vs {tw[k][4]:,.2f}")
        bad = [x["date"] for x in rows[-300:] if not (-100 < x["dd"] <= 0.0001 and 0 <= x["rsi"] <= 100)]
        res("研究", "抄底雷達數值範圍（近 300 天）", "ok" if not bad else "error", f"{len(bad)} 天超出範圍" + (f"：{'、'.join(bad[:3])}" if bad else ""))
    rb = load(DATA / "research" / "rebound_stocks.json", {}) or {}
    now = rb.get("now") or {}
    if now.get("list"):
        sh = (load(DATA / "strategy" / "shares.json", {}) or {}).get("shares", {})
        fs = sorted(glob.glob(str(DATA / "daily" / "20*.json")))
        days = [Path(f).stem for f in fs if Path(f).stem <= now["date"]][-60:]
        dq = {d: load(DATA / "daily" / f"{d}.json", {}) or {} for d in days}
        last = dq.get(now["date"]) or {}
        bad = []
        for x in now["list"]:
            c = x["code"]
            v = (last.get("q") or {}).get(c)
            mg = ((last.get("m") or {}).get(c) or [None])[0]
            if not v or mg is None or not sh.get(c):
                bad.append(f"{c} 找不到原始資料")
                continue
            hi = max(((dq[d].get("q") or {}).get(c) or [0] * 6)[5] or 0 for d in days)
            drop, mu = (v[5] / hi - 1) * 100, mg * 1000 / sh[c] * 100
            if abs(drop - x["drop"]) > 0.11 or abs(mu - x["marginUse"]) > 0.011 or not (-100 < x["drop"] <= 0 and 0 <= x["marginUse"] <= 100):
                bad.append(f"{c} 跌幅 {x['drop']} vs {drop:.1f}、融資 {x['marginUse']} vs {mu:.2f}")
        res("研究", f"抄底選股候選 {now['date']}（{len(now['list'])} 檔重算對照）", "ok" if not bad else "error",
            "全部一致" if not bad else "、".join(bad[:4]))
    for T, rs in (rb.get("top") or {}).items():
        bad = [r["code"] for r in rs if r.get("marginUse") is not None and not 0 <= r["marginUse"] <= 100
               or r.get("drop") is not None and not r["drop"] > -100]  # 逆勢上漲的股票跌幅會是正的
        if bad:
            res("研究", f"抄底選股 {T} 數值範圍", "error", "、".join(bad[:5]))
    set_ = load(DATA / "settlement.json") or load(ROOT / "public" / "data" / "settlement.json")
    if isinstance(set_, dict):
        rows = set_.get("rows") or set_.get("list") or []
        b = [r for r in rows if isinstance(r, dict) and isinstance(r.get("basis"), (int, float)) and abs(r["basis"]) > 20]
        if rows:
            res("研究", "結算策略折溢價範圍（±20% 內）", "ok" if not b else "error", f"{len(b)}/{len(rows)} 檔超出")


def check_flow():
    """即時資金流盤後驗證（validate_flow.py）：最新一天個股主動淨額跟逐筆完整資料對照"""
    v = load(DATA / "flow" / "validation.json", {}) or {}
    days = sorted((v.get("days") or {}))
    if not days:
        return
    d = days[-1]
    r = v["days"][d]
    msg = f"{d}：{r['n']} 檔相關 {r['corr']}、方向一致 {r['sign']}%、合計 即時 {r['liveNet']:+} vs 逐筆 {r['tickNet']:+} 億"
    if r["v"] >= 2 and r["corr"] is not None and (r["corr"] < 0.5 or r["sign"] < 65):
        res("資金流", "即時資金流 vs 逐筆", "error", msg)
    elif r["level"] == "warn":
        res("資金流", "即時資金流 vs 逐筆", "warn", msg)
    else:
        res("資金流", "即時資金流 vs 逐筆", "ok", msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    now = datetime.now(TPE)
    for f in (check_daily, check_yahoo, check_vix_cboe, check_research, check_journals, check_flow):
        try:
            f()
        except Exception as e:  # noqa: BLE001  檢查程式本身出錯也要報出來
            res("系統", f.__name__, "error", f"檢查程式出錯：{type(e).__name__}: {e}")
    doc = {"checkedAt": now.isoformat(timespec="minutes"), "rows": RES}
    if not a.dry_run:
        (DATA / "validation.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}
    for r in RES:
        print(icon[r["level"]], r["cat"], r["name"], "—", r["detail"])
    bad = [r for r in RES if r["level"] == "error"]
    print(f"\n{len(RES)} 項：錯誤 {len(bad)}、注意 {sum(r['level'] == 'warn' for r in RES)}")
    if not a.alert or not bad:
        return 0
    state = load(STATE, {}) or {}
    key = now.date().isoformat() + "|" + "|".join(sorted(r["name"] for r in bad))
    if key in state.get("keys", []) and not a.dry_run:
        print("同樣的錯誤今天已通知過")
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from line_flex import Msg
    import notify
    m = Msg("❌ 資料數值檢查有錯", f"{now:%m/%d %H:%M} 檢查・{len(bad)} 項不一致", accent="#E5484D", url=f"{notify.SITE}/health/", button="開啟資料健檢")
    for r in bad[:12]:
        m.kv(f"{r['cat']}｜{r['name']}", r["detail"][:120], color="#E5484D")
    m.note("同一個數字用兩個來源或兩種算法對照不一致；在修正前相關的研究、推播數字可能有誤")
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
