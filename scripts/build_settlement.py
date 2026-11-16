"""
結算策略（股票期貨月結算控盤）→ public/data/settlement.json；算法照 Excel「結算策略」總表

本期＝上次結算日隔天 ～ 本次結算日（每月第三個星期三，遇休市順延）
每檔有股票期貨（即將結算月份全市場未沖銷 > 0）的股票：
  自營買賣超張數／金額(M)：本期每天自營商買賣超（data/insti）加總；金額＝每天張數 × 1000 × 當天收盤
  換手量（12:30 後 ×27%）＝ 近 10 日平均成交量（張）×（1 − 當沖比）× 27%；當沖比＝最新一天現股當沖股數 ÷ 成交股數
  市場期貨未平倉合約＝大期 OI ＋ 小期 OI ÷ 20（期交所大額交易人表，最新一天、即將結算月份）
  前十大特法 買／賣方未沖銷價值＝(大期口數 × 2000 ＋ 小期口數 × 100) × 收盤價
  自營商庫存倍數＝自營買賣超張數 ÷ 換手量
  未平倉倍數（市場）＝市場期貨未平倉合約 × 2 ÷ 換手量；特法多／空＝特法買／賣方價值 ÷ 1000 ÷ 收盤 ÷ 換手量
  平均折溢價：本期每天「整日平均折溢價」的平均（永豐 1 分 K：期貨有成交的每分鐘 ÷ 當下現貨 − 1 取平均；沒有的日子用期交所結算價 ÷ 現貨收盤估）
  方向：折溢價（溢／折）、期貨未平倉（特法多方價值 > 空方＝多）、自營商庫存（買超＝多）；
        同向＝（溢、空、多）或（折、多、空）→ 套利部位結算時會反向平倉
  控盤金額(M)＝ −（（特法空方價值 − 特法多方價值）÷ 10⁶ ＋ 自營買賣超金額）；控盤張數＝控盤金額 × 10⁶ ÷（收盤 × 1000）
  控盤倍數＝控盤張數 ÷ 換手量（負＝結算時賣壓／往下控，正＝往上拉）
  Amihud（參考）＝ ln（近 20 日 |報酬率| ÷ 換手量 的平均）
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

from build_strategy import TPE, _load


def build(data_dir: Path, public_dir: Path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fetch_settlement as fs

    sdir = data_dir / "settlement"
    contracts = (_load(sdir / "contracts.json", {}) or {}).get("contracts") or {}
    lts = sorted((sdir / "lt").glob("20*.json")) if (sdir / "lt").exists() else []
    if not contracts or not lts:
        return
    daily = [d for d in (_load(p, {}) for p in sorted((data_dir / "daily").glob("20*.json"))) if d.get("q")]
    if not daily:
        return
    hol = fs.holidays()
    last = daily[-1]
    q = last["q"]
    start, sday, month = fs.period(date.fromisoformat(last["date"]), hol)
    lt = _load(lts[-1], {}) or {}
    if lt.get("month") != month:  # 最新的大額交易人資料要是本期（即將結算月份）
        lt = next(((_load(p, {}) or {}) for p in reversed(lts) if (_load(p, {}) or {}).get("month") == month), {})
    rows_lt = lt.get("rows") or {}
    pdays = [d for d in daily if start.isoformat() <= d["date"] <= last["date"]]
    insti = {d["date"]: _load(data_dir / "insti" / f"{d['date']}.json", {}) or {} for d in pdays}
    dt_all = (_load(data_dir / "strategy" / "daytrade.json", {}) or {}).get("days") or {}
    dtd = dt_all.get(last["date"]) or {}
    basis = _load(sdir / "basis_day.json", {}) or {}
    lt_by_day = {p.stem: (_load(p, {}) or {}).get("rows") or {} for p in lts if start.isoformat() <= p.stem <= last["date"]}
    black = set((_load(sdir / "blacklist.json", {}) or {}).get("codes") or [])  # 手動黑名單（Excel 的「黑名單」欄）
    disp = {r.get("code") for r in ((_load(data_dir / "disposition.json", {}) or {}).get("data") or []) if isinstance(r, dict)}

    by_stock: dict[str, dict] = {}
    for k, (stock, unit, name) in contracts.items():
        by_stock.setdefault(stock, {"name": name})["big" if unit == 2000 else "small" if unit == 100 else "other"] = k

    out = []
    for stock, ks in by_stock.items():
        kb, ksm = ks.get("big"), ks.get("small")
        b = rows_lt.get(kb) or [0, 0, 0, 0, 0, None, None]
        s = rows_lt.get(ksm) or [0, 0, 0, 0, 0, None, None]
        M, N = b[0], s[0]
        v = q.get(stock)
        if not M or not v or not v[5]:
            continue
        px = v[5]
        sh = sum((insti[d["date"]].get(stock) or [0] * 5)[4] or 0 for d in pdays)
        amt = sum(((insti[d["date"]].get(stock) or [0] * 5)[4] or 0) * 1000 * ((d["q"].get(stock) or [0] * 6)[5] or 0) for d in pdays) / 1e6
        vols = [(d["q"].get(stock) or [0] * 8)[7] or 0 for d in daily[-10:]]
        vol10 = sum(vols) / len(vols)
        dts = (dtd.get("tw") or {}).get(stock) or (dtd.get("tp") or {}).get(stock)
        dtr = dts / (v[7] * 1000) * 100 if dts and v[7] else 0.0
        turn = vol10 * (100 - dtr) / 100 * 0.27
        oi = M + N / 20
        bval = (b[3] * 2000 + s[3] * 100) * px
        sval = (b[4] * 2000 + s[4] * 100) * px
        big_share = M / (M + N / 20) if M + N else 1
        bshare = (b[3] / M if M else None) if big_share > 0.5 else (s[3] / N if N else None)
        sshare = (b[4] / M if M else None) if big_share > 0.5 else (s[4] / N if N else None)
        # 折溢價：永豐 1 分 K 整日平均為主，缺的日子用期交所結算價估
        bs, src = [], {"day": 0, "settle": 0}
        for d in pdays:
            x = ((basis.get(d["date"]) or {}).get(stock) or [None])[0]
            if x is None:
                fsp = (lt_by_day.get(d["date"], {}).get(kb) or [None] * 6)[5]
                c0 = (d["q"].get(stock) or [0] * 6)[5]
                if fsp and c0:
                    x = fsp / c0 - 1
                    src["settle"] += 1
            else:
                src["day"] += 1
            if x is not None:
                bs.append(x)
        avg_b = sum(bs) / len(bs) if bs else None
        ctrl = -((sval - bval) / 1e6 + amt)
        ctrl_sh = ctrl * 1e6 / (px * 1000)
        # Amihud：近 20 日 |報酬| ÷ 換手量（當天成交量 ×（1 − 當沖比））
        am = []
        for i in range(max(1, len(daily) - 20), len(daily)):
            c1, c0 = (daily[i]["q"].get(stock) or [0] * 8), (daily[i - 1]["q"].get(stock) or [0] * 8)
            dd = dt_all.get(daily[i]["date"]) or {}
            dsh = (dd.get("tw") or {}).get(stock) or (dd.get("tp") or {}).get(stock) or 0
            tv = (c1[7] or 0) - dsh / 1000
            if c1[5] and c0[5] and tv > 0:
                am.append(abs(c1[5] / c0[5] - 1) / tv)
        amihud = math.log(sum(am) / len(am)) if am and sum(am) > 0 else None
        dirs = ("溢" if (avg_b or 0) > 0 else "折", "多" if bval > sval else "空", "多" if amt > 0 else "空")
        out.append({
            "code": stock, "name": v[0] or ks["name"], "close": px, "disp": stock in disp, "black": stock in black,
            "dSh": sh, "dAmt": round(amt, 2), "vol10": round(vol10), "dtr": round(dtr, 2), "turn": round(turn, 1),
            "oi": round(oi, 2), "oiBig": M, "oiSmall": N, "bVal": round(bval), "sVal": round(sval),
            "bShare": round(bshare, 4) if bshare is not None else None, "sShare": round(sshare, 4) if sshare is not None else None,
            "invX": round(sh / turn, 3) if turn else None, "oiX": round(oi * 2 / turn, 3) if turn else None,
            "bX": round(bval / turn / 1000 / px, 3) if turn else None, "sX": round(sval / turn / 1000 / px, 3) if turn else None,
            "basis": round(avg_b, 5) if avg_b is not None else None, "basisSrc": src,
            "dir": dirs, "same": dirs in (("溢", "空", "多"), ("折", "多", "空")),
            "ctrl": round(ctrl, 2), "ctrlSh": round(ctrl_sh), "ctrlX": round(ctrl_sh / turn, 3) if turn else None,
            "amihud": round(amihud, 2) if amihud is not None else None,
        })
    out.sort(key=lambda r: (r["ctrlX"] is None, r["ctrlX"] or 0))
    left, x = 0, date.fromisoformat(last["date"])
    while x < sday:
        x = date.fromordinal(x.toordinal() + 1)
        left += x.weekday() < 5 and x.isoformat() not in hol
    doc = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "date": last["date"], "ltDate": lts[-1].stem,
           "month": month, "start": start.isoformat(), "settle": sday.isoformat(), "daysLeft": left, "days": len(pdays),
           "basisDays": sum(1 for d in pdays if basis.get(d["date"])), "rows": out}
    (public_dir / "settlement.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"結算策略：{month} 結算 {sday}（本期 {start} 起 {len(pdays)} 天），{len(out)} 檔股期標的，"
          f"整日平均折溢價 {doc['basisDays']} 天")
