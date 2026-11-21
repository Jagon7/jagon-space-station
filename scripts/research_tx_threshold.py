#!/usr/bin/env python3
"""
台指期日盤：漲／跌多少該「賭回檔」、多少該「順勢加碼」——用 1 分 K 的事件研究找門檻

事件：09:15～12:30 之間，價格「第一次」漲到 起點 +X×ATR20（或跌到 −X×ATR20）的那一分鐘（每天每個門檻最多一次）
  起點有兩種：當天 08:45 開盤價、前一天日盤收盤（含跳空）
  ATR20＝前 20 天日盤 TR 平均；X＝0.25、0.4、0.5、0.6、0.75、1.0、1.25、1.5
結果（從事件那分鐘收盤起）：
  續強率   先再往同方向走 0.25 ATR、還是先反向 0.25 ATR（收盤前都沒碰到的不算）：> 50% 有利順勢、< 50% 有利逆勢
  順勢損益 到 60 分鐘後／到 13:30 收盤，順著方向的點數（扣 3 點）；逆勢損益＝ −順勢 − 6（兩邊都要付成本）
  最大逆向 順勢單在 13:30 前最多被反向拉多少（ATR）
盤勢分組：09:15 規則分支（A 缺口回補／B 窄區間／C 開高不補／D 其他）、開盤區間寬窄、跳空方向與事件方向同或反、
  事件時間（10:30 前／後）、大振幅預測（逐年滾動樣本外，2022 起）
兩段驗證：2020-24／2025 後，兩段方向一致才算數
輸出 data/research/tx_threshold.json；用法：python scripts/research_tx_threshold.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402
import tx_regime_review as trv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = 3.0
XS = [0.25, 0.4, 0.5, 0.6, 0.75, 1.0, 1.25, 1.5]
RACE = 0.25
FROM_M, LAST_M, EXIT = rr.OR_M, 225, rr.EXIT_M  # 09:15～12:30 觸發；13:30 出場


def events(px: list[tuple[int, float]], ref: float, atr: float):
    """px：[(分鐘, 收盤)]；回傳每個門檻、每個方向的事件"""
    out = []
    for x in XS:
        for sgn in (1, -1):
            lvl = ref + sgn * x * atr
            k = next((i for i, (m, p) in enumerate(px) if FROM_M <= m <= LAST_M and (p - lvl) * sgn >= 0), None)
            if k is None:
                continue
            # 開盤（09:15 前）就已經超過門檻的不算「第一次漲到」
            if any((p - lvl) * sgn >= 0 for m, p in px[:k] if m < FROM_M):
                continue
            m0, p0 = px[k]
            fut = px[k + 1:]
            up_l, dn_l = p0 + sgn * RACE * atr, p0 - sgn * RACE * atr
            race = None
            for _, p in fut:
                if (p - up_l) * sgn >= 0:
                    race = 1
                    break
                if (p - dn_l) * sgn <= 0:
                    race = 0
                    break
            p60 = next((p for m, p in fut if m >= m0 + 60), fut[-1][1] if fut else p0)
            pcl = fut[-1][1] if fut else p0
            mae = min([(p - p0) * sgn for _, p in fut] + [0]) / atr
            out.append({"x": x, "dir": sgn, "m": m0, "race": race, "t60": (p60 - p0) * sgn - COST, "tcl": (pcl - p0) * sgn - COST,
                        "f60": -(p60 - p0) * sgn - COST, "fcl": -(pcl - p0) * sgn - COST, "mae": mae})
    return out


def summ(es):
    if len(es) < 25:
        return None
    rc = [e["race"] for e in es if e["race"] is not None]
    return {"n": len(es), "cont": round(sum(rc) / len(rc) * 100, 1) if rc else None, "t60": round(st.mean(e["t60"] for e in es), 1),
            "tcl": round(st.mean(e["tcl"] for e in es), 1), "fcl": round(st.mean(e["fcl"] for e in es), 1),
            "winT": round(sum(e["tcl"] > 0 for e in es) / len(es) * 100, 1), "mae": round(st.median(e["mae"] for e in es), 2)}


def main():
    day = rr.load_dir(DATA / "futures" / "day")
    ds = sorted(d for d, b in day.items() if len(b) >= 250 and rr.OR_M in b)
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    P = trv.params()["current"]
    pred = {}
    try:
        import research_tx_range as rg
        pred = rg.walk(rg.rows_all(), rg.STRUCT + rg.PRE + rg.AT915)
    except Exception as e:  # noqa: BLE001
        print("大振幅預測失敗：", e)
    TR = {}
    for i in range(1, len(ds)):
        b, pb = day[ds[i]], day[ds[i - 1]]
        pc = pb[max(pb)][3]
        TR[ds[i]] = max(max(x[1] for x in b.values()), pc) - min(min(x[2] for x in b.values()), pc)
    ev = {"open": [], "prev": []}
    for i in range(21, len(ds)):
        d = ds[i]
        if d not in reg:
            continue
        b = day[d]
        pb = day[ds[i - 1]]
        atr = st.mean(TR[k] for k in ds[i - 20:i])
        px = [(m, b[m][3]) for m in sorted(b) if m <= EXIT]
        o, pc = b[min(b)][0], pb[max(pb)][3]
        g = reg[d]
        br = trv.decide(g, P)[0]
        for refn, ref in (("open", o), ("prev", pc)):
            for e in events(px, ref, atr):
                e.update({"date": d, "branch": br, "narrow": g["orATR"] <= 0.34, "gapSame": (o - pc) * e["dir"] > 0, "early": e["m"] <= 105,
                          "pred": pred.get(d, (None, None))[1]})
                ev[refn].append(e)
    parts = (("2020-24", lambda e: e["date"] < "2025-01-01"), ("2025 後", lambda e: e["date"] >= "2025-01-01"))
    out = {"from": ds[21], "to": ds[-1], "cost": COST, "race": RACE, "tables": {}}
    f = lambda s: (f"n{s['n']:4d} 續強{s['cont']:5.1f}% 順勢到收盤{s['tcl']:+6.1f}（60分{s['t60']:+6.1f}）逆勢到收盤{s['fcl']:+6.1f} 中位最大逆向{s['mae']:.2f}"  # noqa: E731
                   if s else "樣本不足")
    print(f"{ds[21]}～{ds[-1]}；ATR＝前 20 天日盤 TR 平均；點數已扣成本；續強＝先再延伸 {RACE} ATR 的比例")
    groups = [("全部", lambda e: True),
              ("開盤區間窄（≤0.34 ATR）", lambda e: e["narrow"]), ("開盤區間寬", lambda e: not e["narrow"]),
              ("跟跳空同方向（開高再漲／開低再跌）", lambda e: e["gapSame"]), ("跟跳空反方向（開高後跌／開低後漲）", lambda e: not e["gapSame"]),
              ("10:30 前觸發", lambda e: e["early"]), ("10:30 後觸發", lambda e: not e["early"]),
              ("分支 A 缺口 30 分內回補", lambda e: e["branch"] == "A"), ("分支 B 窄區間", lambda e: e["branch"] == "B"),
              ("分支 C 開高不補", lambda e: e["branch"] == "C"), ("分支 D 其他", lambda e: e["branch"] == "D"),
              ("大振幅預測 高 2/5（2022 起）", lambda e: e["pred"] is not None and e["pred"] >= 3),
              ("大振幅預測 低 2/5（2022 起）", lambda e: e["pred"] is not None and e["pred"] <= 1)]
    for refn, rlab in (("open", "從 08:45 開盤算"), ("prev", "從昨天收盤算（含跳空）")):
        out["tables"][refn] = {}
        for gname, gf in groups:
            out["tables"][refn][gname] = {}
            print(f"\n■ {rlab}｜{gname}")
            for x in XS:
                for sgn, sl in ((1, "漲"), (-1, "跌")):
                    row = []
                    for pn, pf in parts:
                        es = [e for e in ev[refn] if e["x"] == x and e["dir"] == sgn and gf(e) and pf(e)]
                        row.append(summ(es))
                    out["tables"][refn][gname][f"{sl}{x}"] = row
                    if row[0] or row[1]:
                        print(f"  {sl} {x:.2f} ATR｜2020-24 {f(row[0])}\n  {'':12s}｜2025 後 {f(row[1])}")
    (DATA / "research" / "tx_threshold.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
