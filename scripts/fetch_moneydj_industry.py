#!/usr/bin/env python3
"""
MoneyDJ 產業分類（公開頁面）→ data/industry/moneydj.json
  產業別（約 120 個，如「IC設計」）→ 細產業（約 1000 個，如「DRAM記憶體IC」）→ 成分股代號
  主頁 https://www.moneydj.com/Z/ZH/ZHA/ZHA.djhtm；細產業頁 /z/zh/zha/zh00.djhtm?a=Cxxxxxx
  每頁間隔 0.6 秒；用法：python scripts/fetch_moneydj_industry.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
BASE = "https://www.moneydj.com"
UA = {"User-Agent": "Mozilla/5.0 (research; industry classification)"}


def get(url: str) -> str:
    for k in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.content.decode("big5", errors="ignore")
        except requests.RequestException:
            pass
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"fetch failed {url}")


def main() -> int:
    html = get(BASE + "/Z/ZH/ZHA/ZHA.djhtm")
    # 每一列：<td class="t3t1[_rev]"><a ...a=MID>產業別</a></td> <td ...><table> 細產業 ... </table>
    rows = re.split(r'<tr>\s*<td class="t3t1(?:_rev)?"><a href="/z/zh/zha/zh00\.djhtm\?a=', html)[1:]
    out, seen = {}, set()
    for r in rows:
        m = re.match(r'(\w+)">([^<]+)</a>', r)
        if not m:
            continue
        mid, mname = m.groups()
        body = r[m.end(): r.find("</table>")]
        leaves = re.findall(r'zh00\.djhtm\?a=(\w+)">([^<]+)</a>', body)
        out[mid] = {"name": mname.strip(), "leaves": {lid: {"name": ln.strip()} for lid, ln in leaves}}
    n = 0
    for mid, g in out.items():
        for lid, leaf in g["leaves"].items():
            if lid in seen:
                leaf["codes"] = None   # 同一細產業掛在多個產業別下，只抓一次
                continue
            seen.add(lid)
            page = get(f"{BASE}/z/zh/zha/zh00.djhtm?a={lid}")
            leaf["codes"] = sorted(set(re.findall(r"Link2Stk\('AS(\w+)'\)", page)))
            n += 1
            time.sleep(0.6)
            if n % 100 == 0:
                print(n, file=sys.stderr)
    for g in out.values():   # 補回重複細產業的成分股
        for lid, leaf in g["leaves"].items():
            if leaf["codes"] is None:
                leaf["codes"] = next(x["leaves"][lid]["codes"] for x in out.values()
                                     if lid in x["leaves"] and x["leaves"][lid]["codes"] is not None)
    res = {"updatedAt": time.strftime("%Y-%m-%d"), "source": BASE + "/Z/ZH/ZHA/ZHA.djhtm", "industries": out}
    (DATA / "industry" / "moneydj.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"產業別 {len(out)}、細產業 {sum(len(g['leaves']) for g in out.values())}、抓 {n} 頁")
    return 0


if __name__ == "__main__":
    sys.exit(main())
