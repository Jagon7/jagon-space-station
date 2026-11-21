#!/usr/bin/env python3
"""
權值股（台積電等）與類股同步性，能不能推估台指期日盤 09:15 之後的走勢

開盤前（日線，Yahoo）：
  adrGap   台積 ADR 隱含台積電跳空：TSM 前一晚收盤 ×（台幣匯率）÷ 5 對比 2330 前一天收盤 −1（%）
  adrChg   ADR 溢價變化：TSM 前一晚漲跌 − 2330 前一天漲跌
  hwUp     12 檔權值股前一天上漲比例；hwDisp 權值股前一天漲跌幅標準差（分歧）
  tsmcRel5 台積電 5 日漲跌 − 加權 5 日漲跌（台積電是否領漲）
09:15（永豐類股指數盤中資料 data/market/index1m，2020/8 起）：
  semiRel   半導體類指數（台積電佔大多數）09:15 漲跌% − 加權 09:15 漲跌%（相對前一天收盤）
  semiOpen  半導體 09:00→09:15 的漲跌 − 加權同期（開盤後誰在帶）
  breadth   37 個類股 09:15 跟加權同方向的比例（0.5＝一半一半，1＝全部同方向）
  breadth0  09:00→09:15 跟加權同方向的類股比例
  disp      類股 09:15 漲跌% 的標準差 ÷ 加權平均振幅%（分歧程度）
  elecFin   電子工業 − 金融保險 09:15 漲跌%（資金在電子還是金融）
目標：大振幅、單邊、來回刷、雙邊破、09:15 後收漲；BO／MR 損益
輸出 data/research/tx_heavy.json；用法：python scripts/research_tx_heavy.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_range as rg  # noqa: E402
import research_tx_structure as rs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
HW = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2382.TW", "3711.TW", "2303.TW", "2881.TW", "2891.TW", "2412.TW", "3008.TW", "2603.TW"]
PRE_H = ["adrGap", "aAdrGap", "adrChg", "hwUp", "hwDisp", "tsmcRel5"]
AT_H = ["semiRel", "aSemiRel", "semiOpen", "semiAgree", "breadth", "breadth0", "disp", "elecFin", "aElecFin"]
LABEL = {"adrGap": "ADR 隱含台積電跳空 %（溢價 − 20 日平均溢價）", "aAdrGap": "ADR 隱含跳空幅度", "adrChg": "ADR 溢價變化", "hwUp": "權值股前一天上漲比例",
         "hwDisp": "權值股前一天分歧（標準差）", "tsmcRel5": "台積電 5 日相對加權", "semiRel": "09:15 半導體相對加權 %",
         "aSemiRel": "09:15 半導體相對加權（絕對值）", "semiOpen": "09:00→09:15 半導體相對加權", "semiAgree": "半導體與加權 09:15 同方向",
         "breadth": "09:15 類股同方向比例", "breadth0": "09:00→09:15 類股同方向比例", "disp": "09:15 類股分歧 ÷ 平均振幅",
         "elecFin": "09:15 電子 − 金融 %", "aElecFin": "09:15 電子 − 金融（絕對值）"}


def ycl(sym):
    return {r[0]: r[4] for r in json.loads((DATA / "research" / "yahoo" / f"{sym}.json").read_text(encoding="utf-8"))["d"] if r[4]}


def prev(series: dict, d: str, n: int = 1):
    ks = [k for k in series if k < d]
    ks.sort()
    return [series[k] for k in ks[-n:]] if len(ks) >= n else None


def main():
    rows = rg.rows_all()
    tsm, fx, tw = ycl("TSM"), ycl("TWD=X"), ycl("_TWII")
    hw = {s: ycl(s) for s in HW}
    hwk = {s: sorted(v) for s, v in hw.items()}
    twk = sorted(tw)
    idx = {}
    for f in sorted((DATA / "market" / "index1m").glob("20*.json")):
        idx.update(json.loads(f.read_text(encoding="utf-8")))
    idk = sorted(idx)
    import bisect
    for r in rows:
        d = r["date"]
        # 開盤前
        i = bisect.bisect_left(hwk["2330.TW"], d)
        t2 = [k for k in sorted(tsm) if k < d][-2:]
        fxv = prev(fx, d)
        if i >= 6 and len(t2) == 2 and fxv:
            c0, c1 = hw["2330.TW"][hwk["2330.TW"][i - 1]], hw["2330.TW"][hwk["2330.TW"][i - 2]]
            # ADR 長期有 10～20% 溢價：今天的溢價 − 前 20 天平均溢價＝ADR 隱含的台積電跳空
            prem = []
            for kk in hwk["2330.TW"][max(0, i - 21):i]:
                tv, fv = prev(tsm, kk + "~"), prev(fx, kk + "~")  # 當天（含）以前最近的 ADR 與匯率
                if tv and fv:
                    prem.append((tv[0] * fv[0] / 5 / hw["2330.TW"][kk] - 1) * 100)
            now_p = (tsm[t2[-1]] * fxv[0] / 5 / c0 - 1) * 100  # ADR 1 股＝5 股台積電
            r["adrGap"] = now_p - st.mean(prem[:-1]) if len(prem) >= 10 else None
            r["aAdrGap"] = abs(r["adrGap"]) if r["adrGap"] is not None else None
            r["adrChg"] = (tsm[t2[-1]] / tsm[t2[-2]] - 1) * 100 - (c0 / c1 - 1) * 100
            c5 = hw["2330.TW"][hwk["2330.TW"][i - 6]]
            j = bisect.bisect_left(twk, d)
            r["tsmcRel5"] = (c0 / c5 - 1) * 100 - (tw[twk[j - 1]] / tw[twk[j - 6]] - 1) * 100 if j >= 6 else None
        rets = []
        for s in HW:
            k = bisect.bisect_left(hwk[s], d)
            if k >= 2:
                rets.append((hw[s][hwk[s][k - 1]] / hw[s][hwk[s][k - 2]] - 1) * 100)
        if len(rets) >= 10:
            r["hwUp"] = sum(x > 0 for x in rets) / len(rets)
            r["hwDisp"] = st.pstdev(rets)
        # 09:15 類股
        k = bisect.bisect_left(idk, d)
        if d in idx and k >= 1 and idk[k - 1] in idx:
            today, yest = idx[d], idx[idk[k - 1]]
            t = today["t"]
            ylast = [x for x in (yest["t"] or []) if x]
            if len(t) >= 16 and t[0] and t[15] and ylast:
                pc = ylast[-1]
                tw915 = (t[15] / pc - 1) * 100
                tw0 = (t[15] / t[0] - 1) * 100
                sec915, sec0 = {}, {}
                for nm, v in today["s"].items():
                    pv = (yest["s"].get(nm) or [None] * 5)[-1]
                    if v and len(v) >= 2 and v[1] and pv:
                        sec915[nm] = (v[1] / pv - 1) * 100
                        sec0[nm] = (v[1] / v[0] - 1) * 100 if v[0] else 0
                if len(sec915) >= 25 and "半導體類指數" in sec915:
                    r["semiRel"] = sec915["半導體類指數"] - tw915
                    r["aSemiRel"] = abs(r["semiRel"])
                    r["semiOpen"] = sec0["半導體類指數"] - tw0
                    r["semiAgree"] = float(sec915["半導體類指數"] * tw915 > 0)
                    r["breadth"] = sum(1 for x in sec915.values() if x * tw915 > 0) / len(sec915)
                    r["breadth0"] = sum(1 for x in sec0.values() if x * tw0 > 0) / len(sec0)
                    r["disp"] = st.pstdev(sec915.values()) / (r["atrPctRaw"] if r.get("atrPctRaw") else 1)
                    if "電子工業類指數" in sec915 and "金融保險類指數" in sec915:
                        r["elecFin"] = sec915["電子工業類指數"] - sec915["金融保險類指數"]
                        r["aElecFin"] = abs(r["elecFin"])
                    r["tw915"] = tw915
    # 方向目標：09:15 後收漲
    import research_tx_regime as rr
    day = rr.load_dir(DATA / "futures" / "day")
    for r in rows:
        b = day[r["date"]]
        r["upPost"] = b[max(m for m in b if m <= rr.EXIT_M)][3] > b[rr.OR_M - 1][3] if rr.OR_M - 1 in b else None
        # 09:15 後是否延續 09:15 前（開盤到 09:15）的方向
        r["contPost"] = ((b[max(m for m in b if m <= rr.EXIT_M)][3] - b[rr.OR_M - 1][3]) * (b[rr.OR_M - 1][3] - b[min(b)][0]) > 0) if rr.OR_M - 1 in b else None
    parts = (("2020-24", [r for r in rows if r["date"] < "2025-01-01"]), ("2025 後", [r for r in rows if r["date"] >= "2025-01-01"]))
    tg = (("big", "大振幅"), ("trend", "單邊"), ("chop", "來回刷"), ("two", "雙邊破"), ("upPost", "09:15後收漲"), ("contPost", "延續開盤方向"))
    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "single": {}, "buckets": {}, "model": {}}
    n_idx = sum(1 for r in rows if r.get("breadth") is not None)
    print(f"{rows[0]['date']}～{rows[-1]['date']}：{len(rows)} 天（有 09:15 類股資料 {n_idx} 天）")
    print("\n單一因子 AUC（2020-24／2025 後）；✓＝兩段同方向且都離 0.5 ≥ 0.03")
    print(f"  {'':28s}" + "".join(f"{lab:>14s}" for _, lab in tg))
    for k in PRE_H + AT_H:
        o, line = {}, f"  {LABEL[k]:28s}"
        for t, _ in tg:
            a = []
            for _, part in parts:
                v = [(r[k], bool(r[t])) for r in part if r.get(k) is not None and r.get(t) is not None]
                a.append(rs.auc([y for _, y in v], [x for x, _ in v]) if len(v) > 50 else None)
            o[t] = [round(x, 3) if x is not None else None for x in a]
            ok = None not in a and (a[0] - .5) * (a[1] - .5) > 0 and min(abs(a[0] - .5), abs(a[1] - .5)) >= 0.03
            line += f"  {a[0] or 0:.2f}／{a[1] or 0:.2f}{'✓' if ok else ' '}"
        out["single"][k] = {"label": LABEL[k], "auc": o}
        print(line)
    # 類股同方向比例三等分（使用者的假設：全部同方向 → BO）
    print("\n09:15 類股同方向比例 三等分：單邊%／來回刷%／雙邊破%／延續開盤方向%／BO／MR（每天點數）")
    for k in ("breadth", "breadth0", "disp", "aSemiRel", "aAdrGap"):
        xs = sorted(r[k] for r in parts[0][1] if r.get(k) is not None)
        c1, c2 = xs[len(xs) // 3], xs[2 * len(xs) // 3]
        o = []
        for pn, part in parts:
            row = []
            for a, b in ((-1e9, c1), (c1, c2), (c2, 1e9)):
                s = [r for r in part if r.get(k) is not None and a <= r[k] < b]
                row.append({"n": len(s), "trend": round(sum(r["trend"] for r in s) / len(s) * 100), "chop": round(sum(r["chop"] for r in s) / len(s) * 100),
                            "two": round(sum(r["two"] for r in s) / len(s) * 100), "cont": round(sum(bool(r["contPost"]) for r in s) / len(s) * 100),
                            "bo": round(st.mean(r["bo"] for r in s), 1), "mr": round(st.mean(r["mr"] for r in s), 1)} if s else None)
            o.append(row)
        out["buckets"][k] = {"label": LABEL[k], "cut": [round(c1, 3), round(c2, 3)], "parts": o}
        print(f"  {LABEL[k]}（切點 {c1:.2f}／{c2:.2f}）")
        for (pn, _), row in zip(parts, o):
            print(f"    {pn}: " + " | ".join(f"n{s['n']} {s['trend']}/{s['chop']}/{s['two']}/{s['cont']} BO{s['bo']:+.0f} MR{s['mr']:+.0f}" for s in row if s))
    # 模型：加入權值股／類股（逐年滾動樣本外，大振幅）
    print("\n大振幅模型（逐年滾動，2022 起樣本外）")
    oos = [r for r in rows if r["date"] >= "2022-01-01"]
    for nm, keys in (("09:15 全部（原本）", rg.STRUCT + rg.PRE + rg.AT915), ("＋權值股（開盤前）", rg.STRUCT + rg.PRE + rg.AT915 + PRE_H),
                     ("＋權值股＋09:15 類股", rg.STRUCT + rg.PRE + rg.AT915 + PRE_H + AT_H)):
        pr = rg.walk(rows, keys)
        s = [r for r in oos if r["date"] in pr]
        a = rs.auc([r["big"] for r in s], [pr[r["date"]][0] for r in s])
        out["model"][nm] = round(a, 3)
        print(f"  {nm:18s} AUC {a:.3f}")
    (DATA / "research" / "tx_heavy.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
