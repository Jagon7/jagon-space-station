"""
換股預估共用工具：照 Excel 原本的算法（RANK、MEDIAN、IFS 回傳 #N/A、權重上限分輪重分配），
讓公開資料版跟原本 TEJ 試算表算出一樣的數字。

股票一律用代號（字串）當 key；名稱另外放。
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median

NA = None  # Excel 的 #N/A／空白，一律用 None 表示


def is_na(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def xsum(vals):
    """Excel SUM：任何一格是 #N/A 結果就是 #N/A；空白當 0。"""
    s = 0.0
    for v in vals:
        if is_na(v):
            return NA
        s += v
    return s


def rank_desc(values: dict) -> dict:
    """Excel RANK(x, 範圍)（由大到小，同值同名次，空白不算）。"""
    nums = sorted((v for v in values.values() if not is_na(v)), reverse=True)
    first = {}
    for i, v in enumerate(nums, 1):
        first.setdefault(v, i)
    return {k: (first[v] if not is_na(v) else NA) for k, v in values.items()}


def rank_asc(values: dict) -> dict:
    nums = sorted(v for v in values.values() if not is_na(v))
    first = {}
    for i, v in enumerate(nums, 1):
        first.setdefault(v, i)
    return {k: (first[v] if not is_na(v) else NA) for k, v in values.items()}


def safe_median(vals):
    vals = [v for v in vals if not is_na(v)]
    return median(vals) if vals else NA


def mean(vals):
    vals = [v for v in vals if not is_na(v)]
    return sum(vals) / len(vals) if vals else NA


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def quarter_end(q: str) -> date:
    y, n = int(q[:4]), int(q[-1])
    return {1: date(y, 3, 31), 2: date(y, 6, 30), 3: date(y, 9, 30), 4: date(y, 12, 31)}[n]


def prev_quarter(q: str, k: int = 1) -> str:
    y, n = int(q[:4]), int(q[-1])
    for _ in range(k):
        y, n = (y, n - 1) if n > 1 else (y - 1, 4)
    return f"{y}Q{n}"


def cap_redistribute(w: dict, cap: dict, rounds: int) -> dict:
    """
    試算表的「過關／超過%／可重分配標的當前比重／重分配比例／重分配後權重」做 rounds 輪：
      過關 = 權重 ≤ 上限
      沒過關的砍到上限，超過的部分依「還沒到上限的股票目前權重」比例分給它們；
      剛好等於上限的也固定在上限。
    每一輪都照原表的寫法（只看上一輪的權重），所以輪數不夠時結果會跟原表一樣「還沒收斂」。
    """
    cur = dict(w)
    for _ in range(rounds):
        ok = {k: (not is_na(cur[k]) and cur[k] <= cap[k]) for k in cur}
        over = sum(cur[k] - cap[k] for k in cur if not ok[k])
        room = {k: (cur[k] if ok[k] and cur[k] < cap[k] else 0.0) for k in cur}
        tot = sum(room.values())
        nxt = {}
        for k in cur:
            if not ok[k] or cur[k] == cap[k]:
                nxt[k] = cap[k]
            else:
                share = room[k] / tot if tot else float("nan")
                nxt[k] = room[k] + over * share
        cur = nxt
    return cur


def apply_floor(w: dict, floor: float) -> dict:
    """試算表的「下限過關／低於%／可重分配標的當前比重／重分配比例／重分配後權重」（一輪）。"""
    low = {k: (floor - v if v < floor else 0.0) for k, v in w.items()}
    room = {k: (v if v > floor else 0.0) for k, v in w.items()}
    tot = sum(room.values())
    short = sum(low.values())
    out = {}
    for k, v in w.items():
        share = room[k] / tot if tot else 0.0
        out[k] = floor if share == 0 else v - share * short
    return out


def trade_impact(new_w: dict, old_w: dict, aum_yuan: float, price: dict, turnover_lots: dict) -> list[dict]:
    """
    權重調整 → 預估影響金額（元）→ 預估張數 → 除以換手量（千股＝張）得到預估影響倍數。
    """
    rows = []
    for k in set(new_w) | set(old_w):
        dw = (new_w.get(k) or 0.0) - (old_w.get(k) or 0.0)
        amt = dw * aum_yuan
        px = price.get(k)
        lots = amt / (px * 1000) if px else NA
        tv = turnover_lots.get(k)
        mult = lots / tv if (not is_na(lots) and tv) else NA
        rows.append({"code": k, "dw": dw, "amount": amt, "price": px, "lots": lots,
                     "turnover": tv, "multiple": mult, "new": new_w.get(k, 0.0), "old": old_w.get(k, 0.0)})
    rows.sort(key=lambda r: -(r["multiple"] if not is_na(r["multiple"]) else -1e18))
    return rows
