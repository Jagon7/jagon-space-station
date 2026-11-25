#!/usr/bin/env python3
"""
台指期「假突破反手」回測：往上突破做多 → 拉回（突破失敗）就停損 → 反手放空賭它回到區間（往下同理）

時段同 research_tx_multi（日盤、夜盤美股段；夜盤前段也列出）；OR＝開盤區間，w＝寬度，mid＝中點
突破：價格突破 OR 高點做多（跌破低點做空），只做第一次突破
「突破失敗」的判斷（三種）：
  F_MID  拉回到 OR 中點
  F_Q    拉回到 OR 高點下方 1/4 寬度（往下對稱）
  F_IN5  5 分 K 收回 OR 裡面（用那根收盤價）
反手（假突破放空，往下對稱）：停損＝突破後到反手前的最高點；目標三種：
  T_MID  OR 中點（F_MID 的話中點已到，改用 OR 低點）
  T_LOW  OR 另一側（低點）
  T_END  抱到時段結束
比較：BO 原版（停損 OR 另一側，不反手）、BO 停損改用「失敗判斷」但不反手；以及反手那一筆本身賺不賺
每筆扣 3 點；同一根 1 分 K 同時碰到停損與目標算停損；分三段 2020-22／2023-24／2025 後
日盤另外只看現行 09:15 判斷是 BO 的日子
輸出 data/research/tx_fail_bo.json；用法：python scripts/research_tx_fail_bo.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_tx_multi as M  # noqa: E402
import tx_regime_review as rv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
COST = 3.0
PARTS = M.PARTS


def sim(bars, orh, orl, start, end, fail, tgt_kind, flip=True):
    """回傳 (第一筆損益, 反手那筆損益或 None)"""
    w, mid = orh - orl, (orh + orl) / 2
    d = ent = None
    ext = None
    first = second = None
    pos2 = None
    last = None
    for m in range(start, end + 1):
        b = bars.get(m)
        if not b:
            continue
        o, h, lo, c = b[0], b[1], b[2], b[3]
        last = c
        if d is None:
            if h > orh:
                d, ent, ext = 1, max(o, orh), h
            elif lo < orl:
                d, ent, ext = -1, min(o, orl), lo
            else:
                continue
        if first is None:
            ext = max(ext, h) if d > 0 else min(ext, lo)
            # 原版停損：OR 另一側
            if fail == "ORIG":
                if (d > 0 and lo <= orl) or (d < 0 and h >= orh):
                    first = (orl - ent) if d > 0 else (ent - orh)
                    first -= COST
                    return first, None
                continue
            px = None
            if fail == "F_MID":
                lvl = mid
                if (d > 0 and lo <= lvl) or (d < 0 and h >= lvl):
                    px = min(o, lvl) if d > 0 else max(o, lvl)
            elif fail == "F_Q":
                lvl = orh - 0.25 * w if d > 0 else orl + 0.25 * w
                if (d > 0 and lo <= lvl) or (d < 0 and h >= lvl):
                    px = min(o, lvl) if d > 0 else max(o, lvl)
            elif fail == "F_IN5":
                if (m - start) % 5 == 4 and ((d > 0 and c < orh) or (d < 0 and c > orl)):
                    px = c
                # 5 分 K 收回之前就跌到另一側：視同停損在另一側
                elif (d > 0 and lo <= orl) or (d < 0 and h >= orh):
                    px = orl if d > 0 else orh
            if px is None:
                continue
            first = (px - ent) * d - COST
            if not flip:
                return first, None
            # 反手：方向 −d，進場 px，停損＝突破後極值，目標
            if tgt_kind == "T_MID":
                tg = mid if fail != "F_MID" else (orl if d > 0 else orh)
            elif tgt_kind == "T_LOW":
                tg = orl if d > 0 else orh
            else:
                tg = None
            stop2 = ext + (1 if d > 0 else -1)
            pos2 = (-d, px, stop2, tg)
            continue
        dd, e2, s2, t2 = pos2
        if (dd > 0 and lo <= s2) or (dd < 0 and h >= s2):
            return first, (s2 - e2) * dd - COST
        if t2 is not None and ((dd > 0 and h >= t2) or (dd < 0 and lo <= t2)):
            return first, (t2 - e2) * dd - COST
    if d is None:
        return None, None
    if first is None:
        return (last - ent) * d - COST, None
    if pos2 is None:
        return first, None
    return first, (last - pos2[1]) * pos2[0] - COST


def main():
    S = M.sessions()
    rows_r = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    p = rv.params()["current"]
    out = {"cost": COST}
    configs = [("BO 原版（停損 OR 另一側，不反手）", "ORIG", None, False)]
    for f, fl in (("F_MID", "拉回中點"), ("F_Q", "拉回 1/4 寬度"), ("F_IN5", "5 分 K 收回區間")):
        configs.append((f"BO 停損改「{fl}」、不反手", f, None, False))
        for t, tl in (("T_MID", "目標中點（中點停損的用另一側）"), ("T_LOW", "目標區間另一側"), ("T_END", "抱到收盤")):
            configs.append((f"「{fl}」停損後反手，{tl}", f, t, True))
    for sn, items in S.items():
        for scope in (("全部日子", None), ("09:15 判斷是 BO 的日子", "BO")) if sn == "日盤" else (("全部日子", None),):
            print(f"\n■ {sn}・{scope[0]}")
            out.setdefault(sn, {})[scope[0]] = {}
            for lab, f, t, flip in configs:
                recs = []
                for d, b, s0, s1, end in items:
                    if scope[1] and (d not in rows_r or rv.decide(rows_r[d], p)[1] != scope[1]):
                        continue
                    orb = [b[m] for m in range(s0, s1) if m in b]
                    if len(orb) < 20:
                        continue
                    orh, orl = max(x[1] for x in orb), min(x[2] for x in orb)
                    a1, a2 = sim(b, orh, orl, s1, end, f, t, flip)
                    if a1 is None:
                        continue
                    recs.append((d, a1, a2))
                row = {}
                seg = []
                for pn, a, z in PARTS:
                    xs = [r for r in recs if a <= r[0] < z]
                    if not xs:
                        continue
                    tot = [r[1] + (r[2] or 0) for r in xs]
                    sec = [r[2] for r in xs if r[2] is not None]
                    row[pn] = {"days": len(xs), "avg": round(st.mean(tot), 1), "flipN": len(sec), "flipAvg": round(st.mean(sec), 1) if sec else None,
                               "flipWin": round(sum(x > 0 for x in sec) / len(sec) * 100, 1) if sec else None}
                    seg.append(f"{pn} 每天 {row[pn]['avg']:+6.1f}" + (f"（反手 {len(sec)} 次、平均 {row[pn]['flipAvg']:+.1f}、勝率 {row[pn]['flipWin']:.0f}%）" if sec else ""))
                out[sn][scope[0]][lab] = row
                print(f"  {lab}")
                print("     " + "｜".join(seg))
    (DATA / "research" / "tx_fail_bo.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
