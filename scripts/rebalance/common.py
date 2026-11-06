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


def buffer_select(order: list, existing, n: int, top_in: int, out_after: int, max_repl: int | None,
                  keep_existing_when_over: int | None = None) -> tuple[list, list]:
    """
    臺灣指數公司 SmartBeta 指數的「緩衝區＋替換檔數上限」（00919、00929 編製規則 伍、一、2）：
      1. 排名 ≤ top_in 的直接納入；既有成分股排名 > out_after 刪除（不合格的既有成分股本來就不在 order 裡）。
      2. 排名 top_in+1 ~ out_after 為候選：既有成分股優先、再依排名補滿 n 檔（還不夠就往後依排名補）。
      3. 替換檔數（新納入檔數）超過 max_repl 時：依排名優先選取至多 n − max_repl 檔既有成分股，
         再以非既有成分股補滿 n 檔（00919 編製規則註 7；00929 未另訂，比照辦理）。
    order：已排序的合格股票；回傳 (最終成分股依排名, 處理說明)。
    """
    ex = set(existing)
    rank = {k: i for i, k in enumerate(order, 1)}
    notes = []
    final = [k for k in order if rank[k] <= top_in]
    cand = [k for k in order if top_in < rank[k] <= out_after]
    for k in [k for k in cand if k in ex] + [k for k in cand if k not in ex]:
        if len(final) >= n:
            break
        final.append(k)
    for k in order:
        if len(final) >= n:
            break
        if k not in final and (k not in ex or rank[k] <= out_after):
            final.append(k)
            notes.append(f"候選不足，依排名遞補 {k}")
    if len(final) > n:   # 前 top_in 名就超過 n 檔（top_in ≤ n 時不會發生）
        final = final[:n]
    repl = [k for k in final if k not in ex]
    if max_repl is not None and len(repl) > max_repl:
        keep = keep_existing_when_over if keep_existing_when_over is not None else n - max_repl
        olds = [k for k in order if k in ex][:keep]
        news = [k for k in order if k not in ex][: n - len(olds)]
        notes.append(f"替換 {len(repl)} 檔超過上限 {max_repl} 檔：改取既有成分股前 {len(olds)} 檔＋非既有成分股 {len(news)} 檔")
        final = sorted(olds + news, key=lambda k: rank[k])
    return sorted(final, key=lambda k: rank[k]), notes


def aum_plan_auto(aum_k: float, mult: float = 1.2, unit_k: float = 25_000_000) -> float:
    """預擬資產管理規模＝追蹤指數資產 × 1.2，無條件進位到新台幣 250 億元的倍數（千元）。"""
    return math.ceil(aum_k * mult / unit_k) * unit_k


def priority_include(final: list, order: list, existing, priority: set, max_repl: int) -> tuple[list, list]:
    """
    00929 編製規則註 3「12 月定審優先納入最近 4 季現金股利發放達 2 次以上之公司」（原試算表的做法）：
    合格且配息 ≥ 2 次的非成分股，不論排名都優先納入；替換檔數還沒到上限就擠掉排名最差的既有成分股，
    到上限了就擠掉排名最差、配息不到 2 次的新納入股。
    """
    ex = set(existing)
    rank = {k: i for i, k in enumerate(order, 1)}
    final, notes = list(final), []
    for x in [k for k in order if k in priority and k not in ex and k not in final]:
        repl = sum(1 for k in final if k not in ex)
        pool = ([k for k in final if k in ex] if repl < max_repl else
                [k for k in final if k not in ex and k not in priority])
        if not pool:
            break
        y = max(pool, key=lambda k: rank[k])
        final[final.index(y)] = x
        notes.append(f"配息頻率優先納入 {x}（排名 {rank[x]}），替換 {y}（排名 {rank[y]}）")
    return sorted(final, key=lambda k: rank[k]), notes


def xl(x):
    """Excel 比較數值時只看 15 位有效數字（1−0.9 會等於 0.1）；比較前先四捨五入。"""
    return x if is_na(x) else float(f"{x:.15g}")
