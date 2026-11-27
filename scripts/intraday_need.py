#!/usr/bin/env python3
"""
盤中 1 分 K 研究要抓哪些「日期 × 股票」→ data/research/intraday_need.json [[日期, 代號, 前一天收盤(原始價)], ...]
  ① 空族群弱勢（盤中版）：當天收盤鎖漲停的股票（強勢股），加上同產業、前 60 天日報酬相關 ≥ 0.5、
     當天最高漲 ≥ +3%、成交 ≥ 5000 萬的股票（弱勢股候選）
  ② 向上緩搓（盤中版）：前一天成交金額前 TOP2 名（開盤前就知道的熱門股）
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
    out = sorted([[d, c, pc] for (d, c), pc in need.items()], reverse=True)
    (DATA / "research" / "intraday_need.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{FROM} 起：共 {len(out)} 個日期×股票（熱門股 {n2}、族群弱勢另外加 {n1}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
