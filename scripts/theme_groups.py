#!/usr/bin/env python3
"""
族群定義（盤中「強勢股鎖漲停 → 空族群最弱勢」用）：MoneyDJ 產業分類（data/industry/moneydj.json），比細產業寬一點
  1. 先套 MERGE：跨產業別、同一題材的細產業併成一個族群（例：記憶體＝DRAM、非揮發性記憶體、DRAM／FLASH／SRAM 記憶體 IC、
     記憶體模組、DRAM／FLASH 模組、記憶卡（IC）、SSD 控制 IC）
  2. 其他細產業：同一產業別裡成分股重疊度（交集／較小那組）≥ OVERLAP 的細產業併在一起（例：DRAM模組＋FLASH模組）
  3. 太大的總表細產業（如「IC設計」99 檔）不用；併完 3～MAX_N 檔才算族群；同名族群取檔數多的
用法：import theme_groups as tg; tg.groups() → {族群名: [代號...]}；python scripts/theme_groups.py 2408 印出某檔所屬族群
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
OVERLAP = 0.6
MIN_N, MAX_N = 3, 30
MERGE = {
    "記憶體": r"DRAM|FLASH|SRAM|記憶體|記憶卡|SSD控制",
}


def groups(data_dir: Path | None = None) -> dict:
    fp = (data_dir or DATA) / "industry" / "moneydj.json"
    if not fp.exists():
        return {}
    ind = json.loads(fp.read_text(encoding="utf-8"))["industries"]
    out, used = {}, set()
    for name, pat in MERGE.items():
        cs = set()
        for g in ind.values():
            for lid, l in g["leaves"].items():
                if re.search(pat, l["name"]):
                    cs |= set(l["codes"])
                    used.add(lid)
        out[name] = sorted(cs)
    for g in ind.values():
        leaves = [(lid, l["name"], set(l["codes"])) for lid, l in g["leaves"].items()
                  if lid not in used and MIN_N <= len(set(l["codes"])) <= MAX_N]
        parent = list(range(len(leaves)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i in range(len(leaves)):
            for j in range(i + 1, len(leaves)):
                a, b = leaves[i][2], leaves[j][2]
                if len(a & b) / min(len(a), len(b)) >= OVERLAP and len(a | b) <= MAX_N:
                    parent[find(i)] = find(j)
        comp = {}
        for i, x in enumerate(leaves):
            comp.setdefault(find(i), []).append(x)
        for xs in comp.values():
            cs = set().union(*(x[2] for x in xs))
            if not (MIN_N <= len(cs) <= MAX_N):
                continue
            name = min((x[1] for x in xs), key=len) if len(xs) > 1 else xs[0][1]
            if name not in out or len(out[name]) < len(cs):
                out[name] = sorted(cs)
    return out


if __name__ == "__main__":
    G = groups()
    print(f"{len(G)} 個族群；檔數分布：", sorted(len(v) for v in G.values())[::max(1, len(G) // 15)])
    for code in sys.argv[1:]:
        print(code, [g for g, cs in G.items() if code in cs])
    print("記憶體", G["記憶體"])
