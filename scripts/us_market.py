"""
美股（NYSE）休市日與提早收盤日（規則推算，不用抓網路）

休市：元旦、馬丁路德金紀念日（1 月第 3 個週一）、總統日（2 月第 3 個週一）、耶穌受難日（復活節前的週五）、
     陣亡將士紀念日（5 月最後一個週一）、六月節（6/19，2022 起）、獨立紀念日（7/4）、勞動節（9 月第 1 個週一）、
     感恩節（11 月第 4 個週四）、聖誕節（12/25）
     固定日期遇週六提前到週五、遇週日延到週一（元旦遇週六不提前：前一年 12/31 照常開市）
提早收盤（美東 13:00＝台灣冬令 02:00、夏令 01:00）：獨立紀念日前一天（7/3 是平日且不是休市日）、感恩節隔天、聖誕夜（12/24 是平日）
日期都是美國當地日期；台股「當天晚上」的夜盤美股段對應同一個美國日期
"""
from __future__ import annotations

from datetime import date, timedelta


def _nth_weekday(y, m, wd, n):
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y, m, wd):
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mo = (h + l_ - 7 * m + 114) // 31
    da = (h + l_ - 7 * m + 114) % 31 + 1
    return date(y, mo, da)


def _observed(d: date, new_year: bool = False):
    if d.weekday() == 5:
        return None if new_year else d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


# 臨時休市（颶風、國葬）；之後有新的要手動加
SPECIAL = {date(2012, 10, 29): "颶風珊迪", date(2012, 10, 30): "颶風珊迪", date(2018, 12, 5): "老布希國葬", date(2025, 1, 9): "卡特國葬"}


def holidays(y: int) -> dict:
    out = {d: n for d, n in SPECIAL.items() if d.year == y}

    def add(d, name, new_year=False):
        o = _observed(d, new_year)
        if o:
            out[o] = name
    add(date(y, 1, 1), "元旦", new_year=True)
    out[_nth_weekday(y, 1, 0, 3)] = "馬丁路德金紀念日"
    out[_nth_weekday(y, 2, 0, 3)] = "總統日"
    out[_easter(y) - timedelta(days=2)] = "耶穌受難日"
    out[_last_weekday(y, 5, 0)] = "陣亡將士紀念日"
    if y >= 2022:
        add(date(y, 6, 19), "六月節")
    add(date(y, 7, 4), "獨立紀念日")
    out[_nth_weekday(y, 9, 0, 1)] = "勞動節"
    out[_nth_weekday(y, 11, 3, 4)] = "感恩節"
    add(date(y, 12, 25), "聖誕節")
    return out


def early_closes(y: int) -> dict:
    hol = holidays(y)
    out = {}
    j3 = date(y, 7, 3)
    if j3.weekday() < 5 and j3 not in hol:
        out[j3] = "獨立紀念日前夕"
    out[_nth_weekday(y, 11, 3, 4) + timedelta(days=1)] = "感恩節隔天"
    x = date(y, 12, 24)
    if x.weekday() < 5 and x not in hol:
        out[x] = "聖誕夜"
    return out


def dst(d: date) -> bool:
    """美國夏令時間：3 月第二個週日～11 月第一個週日"""
    return _nth_weekday(d.year, 3, 6, 2) <= d < _nth_weekday(d.year, 11, 6, 1)


def tw_close_hour(d: date) -> int:
    """提早收盤（美東 13:00）換成台灣時間的小時"""
    return 1 if dst(d) else 2


def status(d: date):
    """('closed', 名稱)、('early', 名稱)、週末 ('weekend', '')；正常開市回傳 None"""
    if d.weekday() >= 5:
        return ("weekend", "")
    h = holidays(d.year)
    if d in h:
        return ("closed", h[d])
    e = early_closes(d.year)
    if d in e:
        return ("early", e[d])
    return None


if __name__ == "__main__":
    import sys
    y = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    for d, n in sorted({**holidays(y), **{k: v + "（提早收盤）" for k, v in early_closes(y).items()}}.items()):
        print(d, "一二三四五六日"[d.weekday()], n)
