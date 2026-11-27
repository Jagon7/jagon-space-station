#!/usr/bin/env python3
"""
盤中 1 分 K 研究要抓哪些「日期 × 股票」→ data/research/intraday_need.json [[日期, 代號, 前一天收盤(原始價)], ...]
  ① 空族群弱勢（盤中版）：當天收盤鎖漲停的股票（強勢股），加上同產業、前 60 天日報酬相關 ≥ 0.5、
     當天最高漲 ≥ +3%、成交 ≥ 5000 萬的股票（弱勢股候選）
  ② 向上緩搓（盤中版）：前一天成交金額前 TOP2 名（開盤前就知道的熱門股）
  ③ 各當沖策略的「交易日」（第 t 天收盤選出、t+1 天開盤空）：用 1 分 K 算 +7.5% 停損的實際成交價
     85g（前一天成交前 50、漲停或 5 日漲 ≥ 8%）、高週轉＋漲停（週轉前 20、成交 ≥ 1 億）、高當沖比＋黑K收漲、
     空族群弱勢（日線版）、散戶擁擠（週轉前 50 且當沖比 ≥ 50%）
期間：FROM 起（永豐 1 分 K 歷史）；用 data/research/yahoo_adj 日線
用法：python scripts/intraday_need.py
"""
from __future__ import annotations

import json
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

FROM = "2024-01-01"
TOP2 = 20


def add_strategy_days(need: dict) -> int:
    """③ 各當沖策略的交易日（t+1）；前一天收盤（原始價）當基準"""
    import research_crowd_short as cs
    rows = [r for r in cs.rows_all() if r["n"] >= FROM]
    byd = defaultdict(list)
    for r in rows:
        byd[r["d"]].append(r)
    raw = {}
    for f in (DATA / "research" / "yahoo_adj").glob("*.json"):
        j = json.loads(f.read_text(encoding="utf-8"))
        raw[j["code"]] = {r[0]: r[4] for r in j["d"]}
    n = 0
    for d, xs in byd.items():
        vr = {r["code"]: k for k, r in enumerate(sorted(xs, key=lambda r: -r["val"]), 1)}
        tr = {r["code"]: k for k, r in enumerate(sorted((r for r in xs if r["turn"]), key=lambda r: -r["turn"]), 1)}
        for r in xs:
            c = r["code"]
            g85 = vr[c] <= 50 and (r["limit"] or r["r5"] >= 8)
            tvl = tr.get(c, 999) <= 20 and r["limit"]
            dtf = r["dt"] is not None and r["dt"] >= 60 and r["black"] and r["ret"] >= 0
            crowd = tr.get(c, 999) <= 50 and r["dt"] is not None and r["dt"] >= 50
            if (g85 or tvl or dtf or crowd) and raw.get(c, {}).get(d):
                k = (r["n"], c)
                if k not in need:
                    n += 1
                need[k] = raw[c][d]
    return n


def main():
    px, mk = nh.load()
    sec = nh.sector_map()
    raw = {}
    for f in (DATA / "research" / "yahoo_adj").glob("*.json"):
        j = json.loads(f.read_text(encoding="utf-8"))
        raw[j["code"]] = {r[0]: r for r in j["d"]}
    S = {}
    for c, rows in px.items():
        d = [r[0] for r in rows]
        S[c] = {"d": d, "c": [r[4] for r in rows], "tv": [r[6] for r in rows], "idx": {x: i for i, x in enumerate(d)}}
    by_day = defaultdict(list)
    for c, s in S.items():
        for i in range(61, len(s["d"])):
            if s["d"][i] >= FROM:
                by_day[s["d"][i]].append((c, i))
    need = {}
    n1 = n2 = 0
    for d, xs in sorted(by_day.items()):
        # ② 前一天成交金額前 TOP2
        prev_tv = sorted(((S[c]["tv"][i - 1], c) for c, i in xs), reverse=True)[:TOP2]
        for _, c in prev_tv:
            r0 = raw[c].get(S[c]["d"][S[c]["idx"][d] - 1])
            if r0:
                need[(d, c)] = r0[4]
                n2 += 1
        # ① 盤中碰漲停的強勢股＋相似弱勢股
        groups = defaultdict(list)
        for c, i in xs:
            r, r0 = raw[c].get(d), raw[c].get(S[c]["d"][i - 1])
            if not r or not r0 or not r0[4] or not sec.get(c):
                continue
            groups[sec[c]].append((c, i, r, r0[4]))
        for g, mem in groups.items():
            # 強勢股：收盤鎖住漲停（只用收盤還鎖著的 → 盤中鎖過又打開的日子不在內，對放空弱勢股是保守的）
            leaders = [(c, i) for c, i, r, pc in mem if r[4] >= tick_limit(pc) - 1e-6 and r[4] >= r[2] - 1e-6]
            if not leaders:
                continue
            for lc, li in leaders[:3]:
                L = S[lc]
                lr = [L["c"][k] / L["c"][k - 1] - 1 for k in range(li - 60, li)]
                need[(d, lc)] = raw[lc][L["d"][li - 1]][4]
                for c, i, r, pc in mem:
                    if c == lc or r[2] / pc - 1 < 0.03 or S[c]["tv"][i] < 5e7:
                        continue
                    s = S[c]
                    try:
                        if st.correlation(lr, [s["c"][k] / s["c"][k - 1] - 1 for k in range(i - 60, i)]) < 0.5:
                            continue
                    except st.StatisticsError:
                        continue
                    if (d, c) not in need:
                        n1 += 1
                    need[(d, c)] = pc
                    if i + 1 < len(s["d"]) and 0.02 <= r[4] / pc - 1 < 0.09:   # 日線版：隔天開盤空 → 隔天的 1 分 K
                        need[(s["d"][i + 1], c)] = r[4]
    n3 = add_strategy_days(need)
    out = sorted([[d, c, pc] for (d, c), pc in need.items()], reverse=True)
    print(f"當沖策略交易日另外加 {n3}")
    (DATA / "research" / "intraday_need.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{FROM} 起：共 {len(out)} 個日期×股票（熱門股 {n2}、族群弱勢另外加 {n1}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
