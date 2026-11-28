"""
融資融券總覽 → public/data/chips/margin-flow.json（融資頁「每日融資餘額」「全市場」「個股排行」）

資料：data/daily/*.json
  off.twse／off.tpex：交易所公布的融資金額（mAmt、mAmtPrev，元）、融資／融券張數（mBal、mPrev、sBal、sPrev）
  m：{代號: [融資餘額, 融資增減, 融券餘額, 融券增減, 資券相抵, 融資買進, 融資賣出, 現金償還, 融資限額]}（張）
  q：{代號: [名稱, 市場, 開, 高, 低, 收, 漲跌, 成交張數, 成交金額]}；ix：[加權指數, 漲跌%]
長期：data/research/market_hist.json（融資金額 2012 起，億，上市／上櫃）、data/research/yahoo/_TWII.json、2330.TW.json
內容：
  daily   近 60 個交易日：上市／上櫃／合計 融資增減與餘額（億，官方金額）、融資／融券張數增減（上市＋上櫃）、
          扣除 ETF（0 開頭代號）的融資增減、融券增減、融券餘額（張）、加權指數漲跌 %
  level   融資水位＝融資餘額 ÷ 總市值（收盤 × 現在股數，普通股）：上市含台積電、上市不含台積電、上櫃；
          上市用加權指數推回歷史市值，算近 5 年百分位；上櫃只有每日資料期間（約半年）
  usage   融資使用率＝融資餘額 ÷ 融資限額；券資比＝融券 ÷ 融資（全市場，張）；每日資料期間的百分位
  periods 近 5／20／60／120 日：融資增減（億）、增加天數、融券增減（張）、加權指數漲跌
  extremes 近 250 個交易日單日融資增減最多／最少各 5 天（附加權指數點數）
  chart   近 250 個交易日融資餘額（億，上市＋上櫃）、加權指數、每日增減
  rank    個股排行：單日／5 日／20 日 × 融資增加、融資減少、融券增加、融券減少（各前 100），使用率最高、券資比最高（融資 ≥ 1,000 張）
          欄位：收盤、期間股價漲跌、融資餘額、增減（張、億＝張 × 收盤）、使用率、券資比、判讀、近 20 日融資餘額
          判讀（期間股價門檻 ±3%）：追價＝資增價漲、攤平＝資增價跌、洗籌＝資減價漲、斷頭＝資減價跌
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime
from pathlib import Path

from build_strategy import TPE, _load

N_DAILY, N_RANK = 60, 100


def _pct_rank(xs: list[float], v: float) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(x <= v for x in xs) / len(xs) * 100) if xs else None


def build(data_dir: Path, public_dir: Path):
    docs = []
    for f in sorted((data_dir / "daily").glob("20*.json")):
        d = _load(f, {}) or {}
        if d.get("m") and d.get("q") and d.get("off"):
            docs.append(d)
    if len(docs) < 25:
        return
    sh = (_load(data_dir / "strategy" / "shares.json", {}) or {}).get("shares", {})
    is_stock = lambda c: len(c) == 4 and c.isdigit() and c[0] != "0"  # noqa: E731

    # ---------- 每日表 ----------
    daily = []
    for i, d in enumerate(docs):
        tw, tp = d["off"].get("twse") or {}, d["off"].get("tpex") or {}
        if "mAmt" not in tw or "mAmt" not in tp:
            continue
        m = d["m"]
        prev_m = docs[i - 1]["m"] if i else {}
        ex_dm = sum(v[1] for c, v in m.items() if not c.startswith("0") and v and v[1] is not None)
        ex_ds = sum(v[3] for c, v in m.items() if not c.startswith("0") and v and v[3] is not None)
        ex_sb = sum(v[2] for c, v in m.items() if not c.startswith("0") and v and v[2] is not None)
        ix = d.get("ix") or [None, None]
        row = {"d": d["date"], "twChg": round((tw["mAmt"] - tw["mAmtPrev"]) / 1e8, 2), "tw": round(tw["mAmt"] / 1e8, 2),
               "otcChg": round((tp["mAmt"] - tp["mAmtPrev"]) / 1e8, 2), "otc": round(tp["mAmt"] / 1e8, 2),
               "mLots": (tw["mBal"] - tw["mPrev"]) + (tp["mBal"] - tp["mPrev"]), "sLots": (tw["sBal"] - tw["sPrev"]) + (tp["sBal"] - tp["sPrev"]),
               "exM": ex_dm, "exS": ex_ds, "exSBal": ex_sb, "ix": ix[0], "ixPct": ix[1],
               "mBal": tw["mBal"] + tp["mBal"], "sBal": tw["sBal"] + tp["sBal"]}
        row["totChg"] = round(row["twChg"] + row["otcChg"], 2)
        row["tot"] = round(row["tw"] + row["otc"], 2)
        lim = sum(v[8] for v in m.values() if v and len(v) > 8 and v[8])
        row["usage"] = round(sum(v[0] for c, v in m.items() if v and len(v) > 8 and v[8]) / lim * 100, 2) if lim else None
        row["ratio"] = round(row["sBal"] / row["mBal"] * 100, 2) if row["mBal"] else None
        # 融資水位：融資金額 ÷ 普通股總市值
        q = d["q"]
        cap = {0: 0.0, 1: 0.0}
        for c, v in q.items():
            if is_stock(c) and v[5] and sh.get(c):
                cap[v[1]] += v[5] * sh[c]
        t = q.get("2330")
        tsmc = t[5] * sh.get("2330", 0) if t and t[5] else 0
        row["lvTw"] = round(tw["mAmt"] / cap[0] * 100, 3) if cap[0] else None
        row["lvTwEx"] = round(tw["mAmt"] / (cap[0] - tsmc) * 100, 3) if cap[0] > tsmc else None
        row["lvOtc"] = round(tp["mAmt"] / cap[1] * 100, 3) if cap[1] else None
        row["capTw"] = cap[0]
        daily.append(row)
    last = daily[-1]

    # ---------- 長期序列：market_hist（2012 起，億）＋ 每日資料 ----------
    mh = (_load(data_dir / "research" / "market_hist.json", {}) or {}).get("margin", {})
    hist = {k: (v[0], v[1]) for k, v in mh.items() if v and v[0] is not None and v[1] is not None}
    for r in daily:
        hist[r["d"]] = (r["tw"], r["otc"])
    tw_ix = {r[0]: r[4] for r in (_load(data_dir / "research" / "yahoo" / "_TWII.json", {}) or {}).get("d", []) if r[4]}
    ts = {r[0]: r[4] for r in (_load(data_dir / "research" / "yahoo" / "2330.TW.json", {}) or {}).get("d", []) if r[4]}
    for r in daily:
        if r["ix"]:
            tw_ix[r["d"]] = r["ix"]
    hd = sorted(d for d in hist if d in tw_ix)
    # 上市市值用加權指數等比例推回（假設指數與市值同比例；新上市、增資會有小誤差）
    k_cap = last["capTw"] / last["ix"] if last["ix"] else None
    tsmc_sh = sh.get("2330", 0)
    lv_hist = []
    for d in hd:
        if not k_cap:
            break
        cap = tw_ix[d] * k_cap
        tc = ts.get(d, 0) * tsmc_sh
        lv_hist.append((d, hist[d][0] * 1e8 / cap * 100, hist[d][0] * 1e8 / (cap - tc) * 100 if cap > tc and tc else None))
    five = [x for x in lv_hist if x[0] >= f"{int(last['d'][:4]) - 5}{last['d'][4:]}"]
    level = {
        "tw": {"now": last["lvTw"], "pct5y": _pct_rank([x[1] for x in five], lv_hist[-1][1]) if five else None,
               "max5y": round(max(x[1] for x in five), 3) if five else None},
        "twEx": {"now": last["lvTwEx"], "pct5y": _pct_rank([x[2] for x in five], lv_hist[-1][2]) if five and lv_hist[-1][2] else None,
                 "max5y": round(max(x[2] for x in five if x[2]), 3) if five else None},
        "otc": {"now": last["lvOtc"], "pctShort": _pct_rank([r["lvOtc"] for r in daily], last["lvOtc"]), "since": daily[0]["d"]},
        "mLotsTw": (docs[-1]["off"]["twse"]["mBal"]), "amt": last["tot"],
    }
    usage = {"usage": last["usage"], "usagePct": _pct_rank([r["usage"] for r in daily], last["usage"]),
             "ratio": last["ratio"], "ratioPct": _pct_rank([r["ratio"] for r in daily], last["ratio"]), "since": daily[0]["d"],
             "sBal": last["sBal"], "mBal": last["mBal"]}

    # ---------- 期間統計 ----------
    periods = []
    for n in (5, 20, 60, 120):
        xs = daily[-n:] if len(daily) >= n else None
        if xs is None:
            continue
        base = daily[-n - 1]["ix"] if len(daily) > n else None
        periods.append({"n": n, "mChg": round(sum(r["totChg"] for r in xs), 1), "upDays": sum(r["totChg"] > 0 for r in xs),
                        "sLots": sum(r["sLots"] for r in xs), "ixPct": round((last["ix"] / base - 1) * 100, 1) if base and last["ix"] else None})

    # ---------- 近 250 日極端值、走勢圖 ----------
    seq = [(d, hist[d][0] + hist[d][1]) for d in sorted(hist)]
    chg = [(seq[i][0], seq[i][1] - seq[i - 1][1]) for i in range(1, len(seq))]
    last250 = chg[-250:]
    ixd = sorted(tw_ix)

    def ix_pts(d):
        k = ixd.index(d) if d in tw_ix else None
        return round(tw_ix[d] - tw_ix[ixd[k - 1]]) if k else None
    extremes = {"up": [[d, round(v, 1), ix_pts(d)] for d, v in sorted(last250, key=lambda x: -x[1])[:5]],
                "down": [[d, round(v, 1), ix_pts(d)] for d, v in sorted(last250, key=lambda x: x[1])[:5]]}
    chart = [[d, round(v, 1), round(tw_ix[d]) if d in tw_ix else None, round(c, 1)] for (d, v), (_, c) in zip(seq[-250:], [(None, 0)] + chg[-249:])]

    # ---------- 個股排行 ----------
    q = docs[-1]["q"]
    mm = [x["m"] for x in docs]

    def series(c, n=21):
        return [(x.get(c) or [None])[0] for x in mm[-n:]]

    def close_n(c, n):
        if len(docs) <= n:
            return None
        v = docs[-1 - n]["q"].get(c)
        return v[5] if v and v[5] else None
    rank = {}
    base_rows = {}
    for c, v in mm[-1].items():
        qq = q.get(c)
        if not v or not qq or not qq[5] or v[0] is None:
            continue
        base_rows[c] = {"code": c, "name": qq[0], "mk": "上櫃" if qq[1] else "上市", "etf": c.startswith("0"), "close": qq[5],
                        "bal": v[0], "sBal": v[2], "usage": round(v[0] / v[8] * 100, 1) if len(v) > 8 and v[8] else None,
                        "ratio": round(v[2] / v[0] * 100, 1) if v[0] else None, "spark": series(c)}
    for n in (1, 5, 20):
        rows = []
        for c, r in base_rows.items():
            if len(mm) <= n:
                continue
            p = mm[-1 - n].get(c)
            if not p or p[0] is None:
                continue
            dm, ds = r["bal"] - p[0], (r["sBal"] or 0) - (p[2] or 0)
            pc = close_n(c, n)
            px = round((r["close"] / pc - 1) * 100, 2) if pc else None
            tag = None
            if px is not None and dm:
                tag = ("追價" if px >= 3 else "攤平" if px <= -3 else None) if dm > 0 else ("洗籌" if px >= 3 else "斷頭" if px <= -3 else None)
            rows.append({**{k: r[k] for k in ("code", "name", "mk", "etf", "close", "bal", "sBal", "usage", "ratio", "spark")},
                         "px": px, "dm": dm, "dmAmt": round(dm * r["close"] * 1000 / 1e8, 2), "ds": ds, "tag": tag})
        # 依金額排序（張數會讓低價 ETF 排在前面）；個股、ETF 各取前 N_RANK，網頁可切換含不含 ETF
        def top(pred, key):
            st_ = sorted((r for r in rows if pred(r) and not r["etf"]), key=key)[:N_RANK]
            et_ = sorted((r for r in rows if pred(r) and r["etf"]), key=key)[:N_RANK // 2]
            return sorted(st_ + et_, key=key)
        rank[str(n)] = {
            "mUp": top(lambda r: r["dm"] > 0, lambda r: -r["dmAmt"]),
            "mDown": top(lambda r: r["dm"] < 0, lambda r: r["dmAmt"]),
            "sUp": top(lambda r: r["ds"] > 0, lambda r: -r["ds"] * r["close"]),
            "sDown": top(lambda r: r["ds"] < 0, lambda r: r["ds"] * r["close"]),
        }
    big = [r for r in base_rows.values() if r["bal"] >= 1000]
    rank["usage"] = sorted((r for r in big if r["usage"] is not None), key=lambda r: -r["usage"])[:N_RANK]
    rank["ratio"] = sorted((r for r in big if r["ratio"] is not None), key=lambda r: -r["ratio"])[:N_RANK]
    nd = daily[-N_DAILY:]
    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "date": last["d"],
           "daily": [{k: r[k] for k in ("d", "twChg", "tw", "otcChg", "otc", "totChg", "tot", "mLots", "sLots", "exM", "exS", "exSBal", "ixPct")} for r in reversed(nd)],
           "sum5": round(sum(r["totChg"] for r in daily[-5:]), 2), "sum20": round(sum(r["totChg"] for r in daily[-20:]), 2),
           "level": level, "usage": usage, "periods": periods, "extremes": extremes, "chart": chart, "rank": rank,
           "counts": {"usage50": sum(1 for r in base_rows.values() if r["usage"] and r["usage"] >= 50),
                      "usage30": sum(1 for r in base_rows.values() if r["usage"] and r["usage"] >= 30),
                      "ratio30": sum(1 for r in big if r["ratio"] and r["ratio"] >= 30)}}
    p = public_dir / "chips" / "margin-flow.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"融資融券總覽：{last['d']}，合計融資 {last['tot']:,.0f} 億（{last['totChg']:+.2f}）、近 5 日 {out['sum5']:+.1f}、近 20 日 {out['sum20']:+.1f} 億")
