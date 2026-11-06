#!/usr/bin/env python3
"""
ETF 換股預估（00919、0050、0051、0056、00929）：用 fetch_rebalance.py 等抓的公開資料，
照原本 TEJ 試算表的算法每天重算，輸出：

  data/rebalance/pred/<ETF>.json   預估納入／剔除、權重、交易衝擊、篩選明細（網站用）
  data/rebalance/pred/<ETF>.xlsx   計算過程（母體篩選、排序、權重分配、預估影響張數），對照原試算表用
  data/rebalance/pred/index.json   各檔更新時間與摘要

參數在 config/rebalance.json（審核日期、預擬規模、人工覆寫）。
用法：python scripts/build_rebalance_pred.py [--asof YYYY-MM-DD] [00919 ftse 00929]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.rebalance import etf919, etf929, ftse  # noqa: E402
from scripts.rebalance.public import Public  # noqa: E402

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OUT = DATA_DIR / "rebalance" / "pred"
TPE = timezone(timedelta(hours=8))


def clean(v):
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 10)
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    return v


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def sheet(wb, title, rows: list[dict], cols: list[tuple[str, str]]):
    ws = wb.create_sheet(title[:31])
    ws.append([h for _, h in cols])
    for r in rows:
        ws.append([clean(r.get(k)) if not isinstance(r.get(k), (dict, list)) else json.dumps(r.get(k), ensure_ascii=False)
                   for k, _ in cols])
    ws.freeze_panes = "A2"
    for i, (_, h) in enumerate(cols, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(9, min(22, len(h) * 2 + 2))
    return ws


def impact_rows(res_impact, names):
    return [{**r, "name": names.get(r["code"], "")} for r in res_impact]


IMPACT_COLS = [("code", "代號"), ("name", "名稱"), ("old", "原有權重"), ("new", "預估權重"), ("dw", "權重調整"),
               ("amount", "預估影響金額(元)"), ("price", "收盤價"), ("lots", "預估張數"), ("turnover", "換手量(張)"),
               ("multiple", "預估影響倍數")]


def trading_days_of_month(y: int, m: int) -> list[str]:
    from datetime import date as _d, timedelta as _td
    hol = set(json.loads((DATA_DIR / "calendar.json").read_text(encoding="utf-8")).get("holidays", [])) \
        if (DATA_DIR / "calendar.json").exists() else set()
    d, out = _d(y, m, 1), []
    while d.month == m:
        if d.weekday() < 5 and d.isoformat() not in hol:
            out.append(d.isoformat())
        d += _td(days=1)
    return out


def may_effective_date(y: int) -> str:
    """00919 編製規則：5 月第 17 個交易日為審核基準日，間隔 5 個交易日後生效（例：2026 → 6/3）。"""
    days = trading_days_of_month(y, 5) + trading_days_of_month(y, 6)
    return days[16 + 6]


def readiness(pub: Public, need: dict) -> list[str]:
    """回傳缺少的資料（空 list ＝ 資料齊全）。need: px_from（行情要從哪天起）、div_years、fin_quarters、pe_days、foreign。"""
    miss = []
    own = sorted(p.stem for p in (pub.raw / "px").glob("20*.json"))
    if need.get("px_from") and (not own or own[0] > need["px_from"]):
        miss.append(f"每日行情（需要 {need['px_from']} 起，目前 {own[0] if own else '無'} 起）")
    for y in need.get("div_years", []):
        if not (pub.raw / "div" / f"{y}.json").exists():
            miss.append(f"{y} 年除權息公告")
    for q in need.get("fin_quarters", []):
        doc = pub.raw / "fin" / f"{q}.json"
        n = len(json.loads(doc.read_text(encoding="utf-8"))) if doc.exists() else 0
        if n < 1500 and not (pub.d / "fund" / "income" / f"{q}.json").exists():
            miss.append(f"{q} 財報")
    if need.get("pe_days"):
        n = len(list((pub.raw / "pe").glob("20*.json")))
        if n < need["pe_days"]:
            miss.append(f"歷史本益比（{n}/{need['pe_days']} 天）")
    if need.get("foreign") and not list((pub.raw / "foreign").glob("20*.json")):
        miss.append("外資持股")
    if not list((pub.raw / "insider").glob("20*.json")):
        miss.append("董監持股")
    return miss


def summary(code, adds, dels, names, weights, impact, notes=(), extra=None):
    """資料還沒補齊時（extra["missing"] 有東西）不公布納入／剔除，避免誤導。"""
    if (extra or {}).get("missing"):
        return {"etf": code, "add": [], "del": [], "ready": False, "notes": ["資料補齊中，暫不預估"] + list(notes),
                **(extra or {})}
    imp = {r["code"]: r for r in impact}
    row = lambda k: {"code": k, "name": names.get(k, ""), "w": weights.get(k), "lots": imp.get(k, {}).get("lots"),  # noqa: E731
                     "mult": imp.get(k, {}).get("multiple")}
    return {"etf": code, "add": [row(k) for k in adds], "del": [{**row(k), "w": 0} for k in dels], "ready": True,
            "notes": list(notes), **(extra or {})}


def run_919(pub: Public, cfg: dict, asof: str | None):
    import openpyxl
    b = pub.bundle(asof, etfs=("00919",))
    Y = cfg["year"] if isinstance(cfg.get("year"), int) else int(b["asof"][:4])
    cfg = {**cfg, "year": Y}
    # 1~6 月預估 5 月定審（股利率、除息排除），7~12 月預估 12 月定審（預估股利率、至多換 8 檔）
    review = cfg.get("review")
    if review in (None, "auto"):
        review = "5月" if int(b["asof"][5:7]) <= 6 else "12月"
    miss = readiness(pub, {"px_from": b["windows"]["6m"][0], "div_years": [Y - 1, Y],
                           "fin_quarters": [f"{Y}Q2", f"{Y}Q1", f"{Y - 1}Q4"]})
    if review == "5月":
        from scripts.rebalance.public import may_extras
        b = may_extras(pub, b, Y)
        may = {k: v for k, v in (cfg.get("may") or {}).items() if v not in (None, "auto")}
        if "eff_date" not in may:
            may["eff_date"] = may_effective_date(Y)
        res = etf919.compute_may(b, {**cfg, **may})
        miss += [m for m in readiness(pub, {"fin_quarters": [f"{Y - 1}Q4", f"{Y - 1}Q3"],
                                             "div_years": [Y - 3, Y - 2]}) if m not in miss]
    else:
        res = etf919.compute(b, cfg)
    names = b["names"]
    uni = list(res["universe"].values())
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheet(wb, "919條件篩選(全版)", sorted(uni, key=lambda r: r["code"]), [
        ("code", "代號"), ("name", "名稱"), ("ff_ok", "自由流通係數條件"), ("price", "股價"), ("mcap", "市值(百萬)"),
        ("mcap_rank", "市值排名(自由流通過關者)"), ("top300", "市值前300大"), ("exist", "既有成分股"),
        ("tv6m", "近6月日均成交(千)"), ("tv1m", "近1月日均成交(千)"), ("tv_min", "min"), ("liq_ok", "成交金額過關"),
        ("roe", "近四季ROE"), ("roe_ok", "ROE>0"), ("ff", "自由流通量"), ("ff10", "自由流通≥10%"), ("pass", "篩選通過"),
        ("q3_open", "Q3股利開了沒"), ("div4q", "近四季現金股利"), ("yield", "股利率"), ("eps_q3", "Q3 EPS"),
        ("eps_g", "累積前三季EPS成長率"), ("est_yield", "預估股利率")])
    sheet(wb, "預估股利率排序", res["ranked"], [("rank", "排名"), ("code", "代號"), ("name", "名稱"),
                                          ("est_yield", "預估股利率"), ("exist", "既有成分股"), ("mcap_rank", "市值排名"),
                                          ("q3_open", "Q3開了沒")])
    sheet(wb, "權重", res["weights"]["rows"], [("code", "代號"), ("name", "名稱"), ("yield", "股利率"),
                                             ("yield_share", "股利率比重"), ("tv_median", "近6月日成交中位數"),
                                             ("band", "股利率區間"), ("raw", "流動量調整權重"), ("issue_mcap", "發行市值(千)"),
                                             ("ff_mcap", "自由流通市值(千)"), ("cap", "投資上限"), ("capped", "重分配後"),
                                             ("final", "預估權重")])
    sheet(wb, "預估影響", impact_rows(res["impact"], names), IMPACT_COLS)
    OUT.mkdir(parents=True, exist_ok=True)
    wb.save(OUT / "00919.xlsx")
    s = summary("00919", res["add"], res["del"], names, res["weights"]["final"], res["impact"], res["notes"],
                {"mcap_threshold": res["mcap_threshold"], "windows": b["windows"], "missing": miss,
                 "review": review})
    write_json(OUT / "00919.json", {**s, "asof": b["asof"], "ranked": res["ranked"][:80],
                                    "weights": res["weights"]["rows"], "impact": impact_rows(res["impact"], names),
                                    "config": res["config"]})
    return s


def run_ftse(pub: Public, cfg: dict, asof: str | None):
    import openpyxl
    cfg = {**cfg, "ibes_csv": str(ROOT / cfg["ibes_csv"]) if cfg.get("ibes_csv") else None,
           "iw_csv": str(ROOT / cfg["iw_csv"]) if cfg.get("iw_csv") else None}
    b = pub.bundle(asof, etfs=("0050", "0051", "0056"))
    b = pub.ftse_extras(b, cfg)
    cfg = {**cfg, "official": cfg.get("official", True)}
    Y = int(b["asof"][:4])
    ly, lm = int(cfg["liq_end"][:4]), int(cfg["liq_end"][5:7])
    start = f"{ly - 1 if lm < 12 else ly}-{(lm % 12) + 1:02d}-01"
    miss = readiness(pub, {"px_from": min(start, b["windows"]["6m"][0]), "div_years": [Y - 1, Y],
                           "fin_quarters": [f"{Y}Q2"], "foreign": True})
    res = ftse.compute(b, cfg)
    names = b["names"]
    out = []
    for code in ("0050", "0051", "0056"):
        r = res[code]
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        sheet(wb, "母體(data)", sorted(res["universe"].values(), key=lambda x: x["code"]), [
            ("code", "代號"), ("name", "名稱"), ("class", "分類(1=50,2=51)"), ("mcap", "市值(百萬)"), ("ff", "公眾流通量"),
            ("fol", "外資上限"), ("headroom", "外資尚可投資比"), ("iw", "IW"), ("ff_ok", "公眾流通量審核"),
            ("fol_ok", "外資持股上限審核"), ("annual_liq", "年度流動性"), ("new_liq", "新資格"), ("listed", "上市日"),
            ("list_ok", "新上市審核"), ("alt", "變更交易"), ("eligible", "母體")])
        sheet(wb, "市值排名", res["ranked"], [("rank", "排名"), ("code", "代號"), ("name", "名稱"), ("mcap", "市值(百萬)"),
                                          ("in50", "0050既有"), ("in51", "0051既有")])
        if code == "0056":
            sheet(wb, "0056_6月", sorted(r["rows"].values(), key=lambda x: x["code"]), [
                ("code", "代號"), ("name", "名稱"), ("exist", "既有成分股"), ("nonky", "非KY"), ("yield", "預估股利率"),
                ("yield_src", "預估股利來源"), ("brokers", "分析師家數"), ("tv6m", "近6月日均成交(千)"),
                ("liq_ok", "流動性審核"), ("mkt6m", "六個月前市場別"), ("ltr", "六個月總報酬"), ("ltr_ok", "LTR審核"),
                ("eta", "權益/資產"), ("cseta", "普通股本/資產"), ("asset_ok", "資產審核"), ("fy_div", "上一會計年度股利"),
                ("div_ok", "股利資格"), ("broker_ok", "分析師門檻"), ("pass", "通過")])
            sheet(wb, "股利率排序", r["ranked"], [("rank", "排名"), ("code", "代號"), ("name", "名稱"), ("yield", "股利率"),
                                             ("yield_src", "來源"), ("exist", "既有成分股")])
            sheet(wb, "權重", r["weight_rows"], [("code", "代號"), ("yield", "股利率"), ("raw", "股利率比重"),
                                               ("cap", "投資上限"), ("final", "預估權重")])
        else:
            sheet(wb, "權重", [{"code": k, "name": names.get(k, ""), "final": v} for k, v in r["weights"].items()],
                  [("code", "代號"), ("name", "名稱"), ("final", "預估權重")])
        sheet(wb, "預估影響", impact_rows(r["impact"], names), IMPACT_COLS)
        OUT.mkdir(parents=True, exist_ok=True)
        wb.save(OUT / f"{code}.xlsx")
        notes = []
        if code == "0056" and not b.get("ibes"):
            notes.append("沒有 IBES 授權資料：預估股利率用公開資料（近四季現金股利 × (1+累積EPS成長率)）替代")
        if not b.get("iw_override"):
            notes.append("沒有 FTSE 授權資料：公眾流通量用 1 − 董監持股（公開資料）")
        notes += [f"條件剔除 {k}" for k in r.get("cond_del", [])]
        notes += [f"遞補納入 {k}" for k in r.get("fill", [])] + [f"超額剔除 {k}" for k in r.get("over", [])]
        s = summary(code, r["add"], r["del"], names, r["weights"], r["impact"], notes, {"missing": miss})
        write_json(OUT / f"{code}.json", {**s, "asof": b["asof"],
                                          "ranked": (r["ranked"] if code == "0056" else res["ranked"])[:200],
                                          "weights": [{"code": k, "name": names.get(k, ""), "w": v} for k, v in r["weights"].items()],
                                          "impact": impact_rows(r["impact"], names), "config": res["config"]})
        out.append(s)
    return out


def run_929(pub: Public, cfg: dict, asof: str | None):
    import openpyxl
    b = pub.bundle(asof, etfs=("00929",))
    b = etf929.extras(pub, b, cfg)
    Y = cfg.get("year", int(b["asof"][:4]))
    miss = readiness(pub, {"px_from": cfg.get("prev2_cutoff"), "div_years": list(range(Y - 6, Y + 1)),
                           "fin_quarters": [f"{y}Q{q}" for y in (Y, Y - 1, Y - 2) for q in (1, 2)] + [f"{Y - 1}Q3", f"{Y - 2}Q3"],
                           "pe_days": 1150})
    res = etf929.compute(b, cfg)
    names = b["names"]
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheet(wb, "條件篩選(全版)", sorted(res["universe"].values(), key=lambda x: x["code"]), [
        ("code", "代號"), ("name", "名稱"), ("ff_ok", "自由流通係數過關"), ("price", "股價"), ("mcap", "市值(百萬)"),
        ("not_full", "非全額交割"), ("ff", "自由流通係數"), ("ff10", "≥10%"), ("tv12", "近12月成交金額(千)"),
        ("tv1", "近1月成交金額(千)"), ("top20_12m", "12月排名前20%"), ("ffturn_ok", "自由流通週轉率"), ("cond1", "條件一"),
        ("cond2", "條件二(1月前80%)"), ("top200", "市值前200"), ("liq_ok", "流動性審核"), ("vol", "波動度"),
        ("vol_ok", "波動度90%低"), ("avg_yield", "平均股息殖利率"), ("yield_ok", "殖利率90%高"), ("cv", "5年股利變異係數"),
        ("cv_ok", "變異係數90%低"), ("pe5", "5年平均本益比"), ("pe3", "近3月平均本益比"), ("pe_diff", "差額"),
        ("pe_ok", "差額90%高"), ("roe_ok", "ROE皆為正"), ("passes", "過關數"), ("yield", "股利率"), ("freq", "配息頻率")])
    sheet(wb, "股利率排序", res["ranked"], [("rank", "排名"), ("code", "代號"), ("name", "名稱"), ("yield", "股利率"),
                                       ("exist", "既有成分股"), ("freq", "配息頻率")])
    sheet(wb, "權重預估", res["weights"]["rows"], [("code", "代號"), ("name", "名稱"), ("yield", "股利率"),
                                               ("raw", "股利率比重"), ("cap", "上限"), ("final", "預估權重")])
    sheet(wb, "預估影響", impact_rows(res["impact"], names), IMPACT_COLS)
    OUT.mkdir(parents=True, exist_ok=True)
    wb.save(OUT / "00929.xlsx")
    s = summary("00929", res["add"], res["del"], names, res["weights"]["final"], res["impact"], res["notes"],
                {"thresholds": res["thresholds"], "missing": miss})
    write_json(OUT / "00929.json", {**s, "asof": b["asof"], "ranked": res["ranked"][:100],
                                    "weights": res["weights"]["rows"], "impact": impact_rows(res["impact"], names),
                                    "config": res["config"]})
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof")
    ap.add_argument("jobs", nargs="*")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "config" / "rebalance.json").read_text(encoding="utf-8"))
    pub = Public(DATA_DIR)
    idx = json.loads((OUT / "index.json").read_text(encoding="utf-8")) if (OUT / "index.json").exists() else {}
    jobs = {"00919": lambda: [run_919(pub, cfg["00919"], a.asof)], "ftse": lambda: run_ftse(pub, cfg["ftse"], a.asof),
            "00929": lambda: [run_929(pub, cfg["00929"], a.asof)]}
    failed = 0
    for name in a.jobs or list(jobs):
        try:
            for s in jobs[name]():
                idx[s["etf"]] = {"updatedAt": datetime.now(TPE).strftime("%Y-%m-%dT%H:%M+08:00"), "ready": s["ready"],
                                 "missing": s.get("missing", []),
                                 "add": [x["code"] for x in s["add"]], "del": [x["code"] for x in s["del"]]}
                if not s["ready"]:
                    print(f"{s['etf']}：資料補齊中，缺 {s.get('missing')}")
                else:
                    print(f"{s['etf']}：納入 {[x['code'] + ' ' + x['name'] for x in s['add']]}，"
                          f"剔除 {[x['code'] + ' ' + x['name'] for x in s['del']]}")
        except Exception:  # 一檔失敗不影響其他
            failed += 1
            print(f"✗ {name}：\n{traceback.format_exc()}")
    write_json(OUT / "index.json", idx)
    return 1 if failed and failed == len(a.jobs or jobs) else 0


if __name__ == "__main__":
    sys.exit(main())
