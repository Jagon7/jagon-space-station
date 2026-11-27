#!/usr/bin/env python3
"""
盤中版當沖回測（1 分 K，data/research/intraday_1m，2024 起；永豐 kbars）

① 強勢股鎖漲停 → 立刻空同族群的弱勢股
  族群＝公開資訊觀測站產業別＋前 60 天日報酬相關 ≥ 0.5（走勢相似）
  偵測：強勢股「鎖漲停」＝某一分鐘整根 K 棒都在漲停價（最低＝漲停）；同族群取最早鎖住的那檔
  弱勢股（鎖住那一分鐘的收盤）：漲 +2%～+8%，而且鎖住前 10 分鐘內漲了 ≥ 0.5%（被帶上去）
  進場：下一分鐘開盤放空；出場：13:25 收盤（避開收盤集合競價）；停損：漲到前一天收盤 +9%
  另看：只做 12:00 前、被帶上去多少、族群鎖漲停家數、之後 15／30／60 分與收盤的路徑
  對照：同一批弱勢股「隔天開盤空、收盤補」（日線版策略）
② 盤中向上緩搓 → 放空
  5 分 K（由 1 分 K 合成），09:30～12:30 之間每根 5 分 K 收盤判斷：
    近 6 根（30 分鐘）累計漲 ≥ 1.5%、至少 5 根收漲、單根漲幅都 ≤ 0.6%（沒有急拉）、單根振幅都 ≤ 0.8%、還沒接近漲停（< +8%）
  每檔每天只算第一次；進場：下一根 5 分 K 開盤放空；出場：13:25 收盤；停損：漲到前一天收盤 +9%
  另看：停損改成「比進場價高 1%」、之後 15／30／60 分與收盤的路徑、收盤前有沒有再創當天新高、之後連續收黑的 5 分 K 根數
  對照：同一批股票任意時間點（每天固定 10:30）進場放空到收盤
成本 0.23%（當沖）；分兩段：2024、2025 起（資料只從 2024 開始）
輸出 data/research/intraday.json；用法：python scripts/research_intraday.py
"""
from __future__ import annotations

import glob
import gzip
import json
import math
import os
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(ROOT / "scripts"))
import research_new_high as nh  # noqa: E402
from fetch_dt_stop import tick_limit  # noqa: E402

COST = 0.23
END = 265          # 13:25
PARTS = (("2024", "2024", "2025"), ("2025+", "2025", "2100"))


def load_bars():
    out = {}
    for f in sorted(glob.glob(str(DATA / "research" / "intraday_1m" / "*.json.gz"))):
        for k, v in json.loads(gzip.decompress(Path(f).read_bytes())).items():
            if v:
                d, c = k.split("|")
                out.setdefault(d, {})[c] = {"pc": v[0], "m": {b[0]: b[1:] for b in v[1]}}
    return out


def px_at(m: dict, t: int, field: int = 3):
    """t 分鐘那根的 收(3)／開(0)；沒有就往前找最近一根的收盤"""
    if t in m:
        return m[t][field]
    ks = [k for k in m if k < t]
    return m[max(ks)][3] if ks else None


def short_path(m: dict, entry_t: int, stop_bp: int = 900):
    """entry_t 分鐘開盤放空，13:25 收盤回補；碰到 stop_bp（相對前一天收盤）停損。回傳（報酬 %, 停損了沒, 路徑 {15,30,60,close}）"""
    e = px_at(m, entry_t, 0)
    if e is None or e >= stop_bp:
        return None
    to = lambda p: ((1 + e / 1e4) - (1 + p / 1e4)) / (1 + e / 1e4) * 100  # noqa: E731
    path = {}
    for t in range(entry_t, END + 1):
        b = m.get(t)
        if not b:
            continue
        if b[1] >= stop_bp:
            return to(stop_bp) - COST, True, path
        for h in (15, 30, 60):
            if t == entry_t + h:
                path[h] = to(b[3])
    last = px_at(m, END)
    path["close"] = to(last)
    return to(last) - COST, False, path


def month_t(pairs):
    by = defaultdict(list)
    for mth, v in pairs:
        by[mth].append(v)
    xs = [st.mean(v) for v in by.values()]
    return round(st.mean(xs) / (st.stdev(xs) / math.sqrt(len(xs))), 2) if len(xs) > 2 and st.stdev(xs) else None


def report(name, ev, key="r"):
    res = {}
    for lab, a, b in PARTS:
        xs = [e for e in ev if a <= e["d"] < b and e.get(key) is not None]
        if xs:
            res[lab] = {"n": len(xs), "avg": round(st.mean(e[key] for e in xs), 3), "win": round(sum(e[key] > 0 for e in xs) / len(xs) * 100, 1),
                        "t": month_t([(e["d"][:7], e[key]) for e in xs])}
    print(f"  {name}：" + "｜".join(f"{lab} {v['avg']:+.2f}%（{v['n']} 筆，勝 {v['win']:.0f}%，t {v['t']}）" for lab, v in res.items()))
    return res


def main():
    bars = load_bars()
    print(f"1 分 K：{len(bars)} 天、{sum(len(v) for v in bars.values())} 個日期×股票")
    px, mk = nh.load()
    sec = nh.sector_map()
    S = {}
    for c, rows in px.items():
        d = [r[0] for r in rows]
        S[c] = {"d": d, "c": [r[4] for r in rows], "o": [r[1] for r in rows], "h": [r[2] for r in rows], "idx": {x: i for i, x in enumerate(d)}}
    out = {}

    # ---------- ① ----------
    ev1 = []
    for d, stocks in sorted(bars.items()):
        groups = defaultdict(list)
        for c in stocks:
            if sec.get(c) and c in S and d in S[c]["idx"]:
                groups[sec[c]].append(c)
        for g, mem in groups.items():
            locks = []
            for c in mem:
                m, pc = stocks[c]["m"], stocks[c]["pc"]
                lim = round((tick_limit(pc) / pc - 1) * 1e4)
                t = next((t for t in sorted(m) if m[t][2] >= lim - 1), None)   # 整根在漲停價
                if t is not None and t < END - 10:
                    locks.append((t, c))
            if not locks:
                continue
            locks.sort()
            T, lc = locks[0]
            li = S[lc]["idx"][d]
            if li < 61:
                continue
            lr = [S[lc]["c"][k] / S[lc]["c"][k - 1] - 1 for k in range(li - 60, li)]
            for c in mem:
                if c == lc or c in {x[1] for x in locks if x[0] <= T}:
                    continue
                i = S[c]["idx"][d]
                try:
                    if st.correlation(lr, [S[c]["c"][k] / S[c]["c"][k - 1] - 1 for k in range(i - 60, i)]) < 0.5:
                        continue
                except st.StatisticsError:
                    continue
                m = stocks[c]["m"]
                p_now, p_10 = px_at(m, T), px_at(m, T - 10)
                if p_now is None or p_10 is None or not (200 <= p_now < 800):
                    continue
                pulled = p_now - p_10
                if pulled < 50:
                    continue
                r = short_path(m, T + 1)
                if r is None:
                    continue
                nd = None
                if i + 1 < len(S[c]["d"]):
                    o1, c1, c0 = S[c]["o"][i + 1], S[c]["c"][i + 1], S[c]["c"][i]
                    if o1 < c0 * 1.09:
                        nd = (o1 - c1) / o1 * 100 - COST
                ev1.append({"d": d, "code": c, "leader": lc, "T": T, "pNow": p_now, "pulled": pulled, "nLock": sum(1 for x in locks if x[0] <= T + 30),
                            "r": r[0], "stopped": r[1], **{f"p{k}": v for k, v in r[2].items()}, "nextDay": nd})
    print(f"\n■ ① 強勢股鎖漲停 → 空同族群弱勢股：{len(ev1)} 筆")
    out["lockWeak"] = {"all": report("鎖漲停下一分鐘空、13:25 補", ev1)}
    out["lockWeak"]["nextDay"] = report("（對照）同一批弱勢股隔天開盤空、收盤補", ev1, "nextDay")
    for name, f in (("鎖漲停在 10:00 前", lambda e: e["T"] < 60), ("10:00～12:00", lambda e: 60 <= e["T"] < 180), ("12:00 後", lambda e: e["T"] >= 180),
                    ("弱勢股當下 +2～4%", lambda e: e["pNow"] < 400), ("弱勢股當下 +4～8%", lambda e: e["pNow"] >= 400),
                    ("前 10 分被帶上 ≥ 1.5%", lambda e: e["pulled"] >= 150), ("族群 30 分內 ≥ 2 檔鎖漲停", lambda e: e["nLock"] >= 2)):
        out["lockWeak"][name] = report(name, [e for e in ev1 if f(e)])
    for h in (15, 30, 60, "close"):
        xs = [e[f"p{h}"] for e in ev1 if e.get(f"p{h}") is not None]
        if xs:
            print(f"    進場後 {h} 分（未扣成本）：平均 {st.mean(xs):+.2f}%、賺的比例 {sum(x > 0 for x in xs) / len(xs) * 100:.0f}%")
    print(f"    碰到 +9% 停損：{sum(e['stopped'] for e in ev1) / max(1, len(ev1)) * 100:.1f}%")

    # ---------- ② ----------
    ev2, base = [], []
    for d, stocks in sorted(bars.items()):
        for c, v in stocks.items():
            m = v["m"]
            k5 = []
            for s in range(0, 270, 5):
                g = [m[t] for t in range(s, s + 5) if t in m]
                if g:
                    k5.append((s, g[0][0], max(x[1] for x in g), min(x[2] for x in g), g[-1][3]))
            if len(k5) < 40:
                continue
            r = short_path(m, 90)          # 對照：10:30 開盤空
            if r:
                base.append({"d": d, "r": r[0]})
            for j in range(6, len(k5) - 1):
                s = k5[j][0]
                if not (30 <= s <= 210):
                    continue
                w = k5[j - 5:j + 1]
                prev = k5[j - 6][4]
                rises = [w[0][4] - prev] + [w[x][4] - w[x - 1][4] for x in range(1, 6)]
                cum = w[-1][4] - prev
                if cum >= 150 and sum(x > 0 for x in rises) >= 5 and max(rises) <= 60 and max(b[2] - b[3] for b in w) <= 80 and w[-1][4] < 800:
                    entry = k5[j + 1][0]
                    r1 = short_path(m, entry)
                    if r1 is None:
                        break
                    e_px = px_at(m, entry, 0)
                    r2 = short_path(m, entry, stop_bp=e_px + 100 if e_px is not None else 900)
                    after = [b for b in k5 if b[0] >= entry]
                    run = 0
                    for b in after:
                        if b[4] < b[1]:
                            run += 1
                        else:
                            break
                    hi_before = max(b[2] for b in k5[:j + 1])
                    ev2.append({"d": d, "code": c, "t": entry, "r": r1[0], "stop1": r2[0] if r2 else None, "stopped": r1[1],
                                **{f"p{k}": vv for k, vv in r1[2].items()}, "newHigh": any(b[2] > hi_before for b in after if b[0] <= END),
                                "blackRun": run})
                    break
    print(f"\n■ ② 盤中向上緩搓 → 放空：{len(ev2)} 筆")
    out["grind"] = {"all": report("下一根 5 分 K 開盤空、13:25 補", ev2)}
    out["grind"]["stop1"] = report("停損改成比進場價高 1%", ev2, "stop1")
    out["grind"]["base"] = report("（對照）同一批股票 10:30 空、13:25 補", base)
    for name, f in (("10:30 前出現", lambda e: e["t"] < 90), ("10:30～12:00", lambda e: 90 <= e["t"] < 180), ("12:00 後", lambda e: e["t"] >= 180)):
        out["grind"][name] = report(name, [e for e in ev2 if f(e)])
    for h in (15, 30, 60, "close"):
        xs = [e[f"p{h}"] for e in ev2 if e.get(f"p{h}") is not None]
        if xs:
            print(f"    進場後 {h} 分（未扣成本）：平均 {st.mean(xs):+.2f}%、賺的比例 {sum(x > 0 for x in xs) / len(xs) * 100:.0f}%")
    if ev2:
        print(f"    收盤前再創當天新高：{sum(e['newHigh'] for e in ev2) / len(ev2) * 100:.0f}%；之後連續收黑的 5 分 K："
              + "、".join(f"{k} 根 {sum(e['blackRun'] == k for e in ev2) / len(ev2) * 100:.0f}%" for k in range(0, 5))
              + f"、≥5 根 {sum(e['blackRun'] >= 5 for e in ev2) / len(ev2) * 100:.0f}%")
    (DATA / "research" / "intraday.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
