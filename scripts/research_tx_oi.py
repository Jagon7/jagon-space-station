#!/usr/bin/env python3
"""
選擇權未平倉大的履約價，會不會「吸住」或「擋住」台指（機構控盤的誘因）

資料：TXO 每日各履約價未平倉（scripts/fetch_txo_oi.py）、加權指數盤中 1 分（data/market/index1m，2020/8 起）、期交所台指期日盤 1 分 K
一律用「前一天收盤後」的未平倉（開盤前就知道），看最近一個到期的合約（週選或月選）

檢驗 1　結算日磁吸（pinning）
  結算價＝結算日收盤前 30 分鐘（13:00～13:30）加權指數的平均
  對照「最大痛點」（買方總價值最小、賣方最賺的履約價）、「最大未平倉履約價」：
  09:15 時離它多遠 → 結算價離它多遠，距離縮小的比例；跟「非結算日」同一時間、同樣算法比較（非結算日不該有磁吸）
  另外用「最近的整數百點」當安慰劑（任何價格都會離某個百點很近）
檢驗 2　壓力與支撐
  09:15 後，上方 0～1.5 ATR 內每個履約價：當天（到 13:30）有沒有被突破；
  在同樣距離下比較「買權未平倉最大」與「其他履約價」的突破率（賣權未平倉＝下方支撐，同理）
  如果大未平倉真的有人在守，同距離下應該明顯比較難突破
輸出 data/research/tx_oi.json；用法：python scripts/research_tx_oi.py
"""
from __future__ import annotations

import calendar
import json
import os
import statistics as st
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_regime as rr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))


def nth_weekday(y, m, wd, n):
    c = calendar.Calendar()
    days = [d for d in c.itermonthdates(y, m) if d.month == m and d.weekday() == wd]
    return days[n - 1] if n <= len(days) else None


def expiry(code: str, tdays: list[str]) -> str | None:
    """到期別 → 結算日（遇休市延到下一個交易日）"""
    try:
        y, m = int(code[:4]), int(code[4:6])
    except ValueError:
        return None
    if len(code) == 6:
        d = nth_weekday(y, m, 2, 3)
    elif code[6] == "W":
        d = nth_weekday(y, m, 2, int(code[7:]))
    elif code[6] == "F":
        d = nth_weekday(y, m, 4, int(code[7:]))
    else:
        return None
    if d is None:
        return None
    s = d.isoformat()
    nxt = [t for t in tdays if t >= s]
    return nxt[0] if nxt else s


def max_pain(chain: dict) -> float | None:
    ks = sorted(int(k) for k in chain)
    if len(ks) < 5:
        return None
    best, bk = None, None
    for s in ks:
        pay = sum(v[0] * max(0, s - int(k)) + v[1] * max(0, int(k) - s) for k, v in chain.items())
        if best is None or pay < best:
            best, bk = pay, s
    return bk


def main():
    oi = {}
    for f in sorted((DATA / "research" / "txo_oi").glob("20*.json")):
        oi.update(json.loads(f.read_text(encoding="utf-8")))
    idx = {}
    for f in sorted((DATA / "market" / "index1m").glob("20*.json")):
        idx.update(json.loads(f.read_text(encoding="utf-8")))
    tdays = sorted(set(oi) | set(idx))
    day = rr.load_dir(DATA / "futures" / "day")
    fd = sorted(day)
    # ATR20（期貨日盤 TR）
    TR = {}
    for i in range(1, len(fd)):
        b, pb = day[fd[i]], day[fd[i - 1]]
        pc = pb[max(pb)][3]
        TR[fd[i]] = max(max(x[1] for x in b.values()), pc) - min(min(x[2] for x in b.values()), pc)
    trk = sorted(TR)
    rows, touch = [], []
    od = sorted(oi)
    for d in sorted(idx):
        t = idx[d].get("t") or []
        if len(t) < 271 or None in (t[15], t[-1]) or d not in TR:
            continue
        pv = [x for x in od if x < d]
        if not pv:
            continue
        ch_all = oi[pv[-1]]  # 前一天收盤後的未平倉
        # 最近一個到期（結算日 ≥ 今天）
        exps = sorted(((expiry(c, tdays), c) for c in ch_all), key=lambda x: (x[0] or "9999"))
        exps = [e for e in exps if e[0] and e[0] >= d]
        if not exps:
            continue
        ed, code = exps[0]
        chain = {k: v for k, v in ch_all[code].items() if v[0] or v[1]}
        if len(chain) < 10:
            continue
        j = trk.index(d)
        if j < 20:
            continue
        atr = st.mean(TR[k] for k in trk[j - 20:j])
        p915 = t[15]
        post = [x for x in t[15:] if x]
        settle = st.mean(x for x in t[241:271] if x)
        mp = max_pain(chain)
        kc = max(chain, key=lambda k: chain[k][0])
        kp = max(chain, key=lambda k: chain[k][1])
        kt = max(chain, key=lambda k: chain[k][0] + chain[k][1])
        r100 = round(p915 / 100) * 100
        isexp = ed == d
        r = {"date": d, "exp": isexp, "code": code, "monthly": len(code) == 6, "atr": atr, "p915": p915, "settle": settle, "close": t[-1],
             "mp": mp, "kCall": int(kc), "kPut": int(kp), "kTot": int(kt), "r100": r100, "oiTot": sum(v[0] + v[1] for v in chain.values())}
        for nm, k in (("mp", mp), ("kTot", int(kt)), ("r100", r100)):
            d0, d1 = abs(p915 - k) / atr, abs(settle - k) / atr
            r[f"{nm}D0"], r[f"{nm}D1"] = d0, d1
        rows.append(r)
        # 檢驗 2：上方／下方 0～1.5 ATR 內的履約價
        hi, lo = max(post), min(post)
        tot_c = sum(v[0] for v in chain.values()) or 1
        tot_p = sum(v[1] for v in chain.values()) or 1
        ups = [(int(k), v[0]) for k, v in chain.items() if 0 < int(k) - p915 <= 1.5 * atr and int(k) % 100 == 0]
        dns = [(int(k), v[1]) for k, v in chain.items() if 0 < p915 - int(k) <= 1.5 * atr and int(k) % 100 == 0]
        for side, lst, tot in (("call", ups, tot_c), ("put", dns, tot_p)):
            if len(lst) < 3:
                continue
            top = max(lst, key=lambda x: x[1])[0]
            for k, v in lst:
                dist = abs(k - p915) / atr
                crossed = hi > k if side == "call" else lo < k
                touch.append({"date": d, "side": side, "dist": dist, "top": k == top, "share": v / tot, "crossed": crossed, "exp": isexp,
                              "fin": (t[-1] > k) if side == "call" else (t[-1] < k)})
    out = {"from": rows[0]["date"], "to": rows[-1]["date"], "n": len(rows), "pin": {}, "wall": {}}
    print(f"{rows[0]['date']}～{rows[-1]['date']}：{len(rows)} 天（結算日 {sum(r['exp'] for r in rows)} 天，其中月結算 {sum(r['exp'] and r['monthly'] for r in rows)}）")
    # 檢驗 1
    print("\n檢驗 1：結算日磁吸——09:15 到結算價（13:00～13:30 平均），離目標的距離（ATR）")
    for grp, cond in (("月結算日", lambda r: r["exp"] and r["monthly"]), ("週結算日", lambda r: r["exp"] and not r["monthly"]),
                      ("非結算日", lambda r: not r["exp"])):
        s = [r for r in rows if cond(r)]
        if not s:
            continue
        o = {"n": len(s)}
        line = f"  {grp}（{len(s)} 天）"
        for nm, lab in (("mp", "最大痛點"), ("kTot", "最大未平倉"), ("r100", "整數百點(安慰劑)")):
            near = [r for r in s if r[f"{nm}D0"] <= 1.0]  # 09:15 時已在 1 ATR 內
            if not near:
                continue
            closer = sum(r[f"{nm}D1"] < r[f"{nm}D0"] for r in near) / len(near) * 100
            within = sum(r[f"{nm}D1"] <= 0.1 for r in near) / len(near) * 100  # 結算價落在目標 ±0.1 ATR
            o[nm] = {"n": len(near), "d0": round(st.median(r[f"{nm}D0"] for r in near), 3), "d1": round(st.median(r[f"{nm}D1"] for r in near), 3),
                     "closer": round(closer, 1), "within": round(within, 1)}
            line += f"\n    {lab:14s} n{len(near):4d} 距離中位數 {o[nm]['d0']:.2f} → {o[nm]['d1']:.2f} ATR，變近 {closer:.0f}%，最後落在 ±0.1 ATR 內 {within:.0f}%"
        out["pin"][grp] = o
        print(line)
    # 檢驗 2
    print("\n檢驗 2：壓力／支撐——同樣距離下，未平倉最大的履約價 vs 其他履約價，09:15 後被突破的比例")
    for side, lab in (("call", "上方（買權未平倉＝壓力）"), ("put", "下方（賣權未平倉＝支撐）")):
        print(f"  {lab}")
        o = []
        for a, b in ((0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0), (1.0, 1.5)):
            for nm, flt in (("全部日", lambda x: True), ("結算日", lambda x: x["exp"])):
                s = [x for x in touch if x["side"] == side and a < x["dist"] <= b and flt(x)]
                t1 = [x for x in s if x["top"]]
                t0 = [x for x in s if not x["top"]]
                if len(t1) < 15 or len(t0) < 15:
                    continue
                c1 = sum(x["crossed"] for x in t1) / len(t1) * 100
                c0 = sum(x["crossed"] for x in t0) / len(t0) * 100
                f1 = sum(x["fin"] for x in t1) / len(t1) * 100
                f0 = sum(x["fin"] for x in t0) / len(t0) * 100
                o.append({"dist": [a, b], "grp": nm, "nTop": len(t1), "nOther": len(t0), "crossTop": round(c1, 1), "crossOther": round(c0, 1),
                          "finTop": round(f1, 1), "finOther": round(f0, 1)})
                print(f"    距離 {a:.2f}～{b:.2f} ATR {nm}：最大未平倉 突破 {c1:4.0f}%（收在外 {f1:3.0f}%，n{len(t1)}） vs 其他 {c0:4.0f}%（{f0:3.0f}%，n{len(t0)}）")
        out["wall"][side] = o
    (DATA / "research" / "tx_oi.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
