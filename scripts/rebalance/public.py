"""
把 fetch_rebalance.py 等抓下來的公開資料整理成計算程式用的 bundle（欄位跟 verify_tej.load_919 一樣）。

對應原本 TEJ 工作表：
  股價／市值        → raw/px（收盤）× raw/basic（發行股數）
  成交值            → raw/px 每日成交金額（千元，無條件捨去）；近 6 月＝M-5 月 1 日起，近 1 月＝一個月內
  董監持股          → raw/insider（董事＋經理人＋大股東，依姓名去重）
  ROE新／EPS        → raw/fin（彙總報表＋OpenAPI 最新）或 data/fund/income
  月營收            → data/fund/revenue
  現金股利_平攤     → raw/div（除權息公告，依股利所屬期間）＋ raw/div_board.json（上市董事會已決議）
                      ＋ raw/div_board_otc.json（上櫃董事會已決議，股利分派情形）
  ETF 原始權重／AUM → data/etf/holdings
  換手量            → 成交股數 − 當沖股數（data/strategy/daytrade.json）
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

from .common import NA, add_months, safe_median


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Public:
    def __init__(self, data_dir: Path):
        self.d = Path(data_dir)
        self.raw = self.d / "rebalance" / "raw"

    # ---------- 行情 ----------
    def px_days(self) -> list[str]:
        own = {p.stem for p in (self.raw / "px").glob("20*.json")}
        repo = {p.stem for p in (self.d / "daily").glob("20*.json")}
        return sorted(own | repo)

    def px(self, day: str) -> dict:
        """{代號: [收盤, 成交股數, 成交金額(千元，無條件捨去), 市場, 漲跌]}；自己的完整行情優先，沒有才用 data/daily。"""
        p = self.raw / "px" / f"{day}.json"
        if p.exists():
            return _read(p, {})
        q = _read(self.d / "daily" / f"{day}.json", {}).get("q", {})
        return {c: [v[5], (v[7] or 0) * 1000, math.floor((v[8] or 0) / 1000), "OTC" if v[1] == 1 else "TSE", v[6]]
                for c, v in q.items()}

    def latest_insider(self) -> dict:
        files = sorted((self.raw / "insider").glob("20*.json"))
        return _read(files[-1], {}) if files else {}

    def basic(self) -> dict:
        return _read(self.raw / "basic.json", {}).get("d", {})

    # ---------- 財報（單季） ----------
    def fin_cum(self) -> dict:
        """{季: {代號: {ni, nip, eps, eq, eqp, assets, cap}}}（累計數）"""
        out = {}
        for p in (self.d / "fund" / "income").glob("20*Q*.json"):
            doc = _read(p, {})
            out[p.stem] = {c: {"nip": v[6], "ni": v[6], "eps": v[7]} for c, v in doc.items()}
        for p in (self.raw / "fin").glob("20*Q*.json"):
            doc = _read(p, {})
            q = out.setdefault(p.stem, {})
            for c, v in doc.items():
                q.setdefault(c, {}).update({k: x for k, x in v.items() if x is not None})
        # OpenAPI 的單季數（ni_q／nip_q／eps_q）：彙總表的累計數還沒有時，用前一季累計 + 單季
        for qk in sorted(out):
            y, n = int(qk[:4]), int(qk[-1])
            prev = out.get(f"{y}Q{n - 1}", {}) if n > 1 else {}
            for c, v in out[qk].items():
                for f in ("ni", "nip", "eps"):
                    if v.get(f) is None and v.get(f + "_q") is not None:
                        if n == 1:
                            v[f] = v[f + "_q"]
                        elif prev.get(c, {}).get(f) is not None:
                            v[f] = prev[c][f] + v[f + "_q"]
        return out

    @staticmethod
    def single_quarter(cum: dict, field: str) -> dict:
        """累計 → 單季：Q1＝累計；Qn＝累計n − 累計n-1。"""
        out = defaultdict(dict)
        for q in sorted(cum):
            y, n = int(q[:4]), int(q[-1])
            for c, v in cum[q].items():
                x = v.get(field)
                if x is None:
                    continue
                if n == 1:
                    out[c][q] = x
                else:
                    prev = cum.get(f"{y}Q{n - 1}", {}).get(c, {}).get(field)
                    if prev is not None:
                        out[c][q] = x - prev
        return out

    def revenue(self) -> dict:
        out = defaultdict(dict)
        for p in (self.d / "fund" / "revenue").glob("20*.json"):
            for c, v in _read(p, {}).items():
                if v[3] is not None:
                    out[c][p.stem] = v[3]
        return out

    def dividends(self) -> dict:
        """
        {代號: {(所屬年度, 'Q1'..'Q4'): 每股現金股利}}。
        同一期別常有兩則公告：除息（現金）和除權（股票，現金欄 0），要分開看；
        現金股利取「有除息日或現金 > 0」的公告中最後一則（更正公告會蓋掉舊的）。
        """
        cash_ann, seen = {}, set()
        for p in sorted((self.raw / "div").glob("20*.json")):
            for c, y, q, cash, _stock, exd, _exr, ann, *_ in _read(p, []):
                k = (c, y, q)
                seen.add(k)
                if (cash or exd) and (k not in cash_ann or (ann or "") >= cash_ann[k][1]):
                    cash_ann[k] = (cash or 0.0, ann or "")
        latest = {k: v for k, v in cash_ann.items()}
        for k in seen - set(latest):            # 只有配股、沒有現金
            latest[k] = (0.0, "")
        for c, y, q, cash, *_ in _read(self.raw / "div_board.json", []):
            latest.setdefault((c, y, q), (cash, ""))
        # 上櫃：股利分派情形（董事會已決議、還沒有除息公告的期別才補；同期別多筆取董事會日最晚的）
        otc = {}
        for ent in _read(self.raw / "div_board_otc.json", {}).values():
            for c, y, q, cash, _st, board, *_ in ent.get("r", []):
                k = (c, y, q)
                if k not in otc or str(board) >= otc[k][1]:
                    otc[k] = (cash, str(board))
        for k, (cash, _) in otc.items():
            latest.setdefault(k, (cash, ""))
        out = defaultdict(dict)
        for (c, y, q), (cash, _) in latest.items():
            out[c][(y, q)] = cash
        return out

    def exdiv_dates(self) -> dict:
        out = defaultdict(list)
        for p in sorted((self.raw / "div").glob("20*.json")):
            for c, y, q, cash, _s, exd, *_ in _read(p, []):
                if exd and cash:
                    out[c].append((exd, y, q, cash))
        return out

    def etf(self, code: str) -> dict:
        doc = _read(self.d / "etf" / "holdings" / f"{code}.json", {})
        snaps = doc.get("snapshots") or []
        if not snaps:
            return {"weights": {}, "aum": None, "date": None, "shares": {}}
        s = snaps[-1]
        return {"weights": {h[0]: h[3] for h in s["h"] if len(h[0]) == 4 and h[0].isdigit()},
                "shares": {h[0]: h[2] for h in s["h"] if len(h[0]) == 4 and h[0].isdigit()},
                "aum": (s.get("aum") or 0) / 1000, "date": s.get("date")}

    def daytrade(self, day: str) -> dict:
        own = self.raw / "daytrade" / f"{day}.json"
        if own.exists():
            return _read(own, {})
        doc = _read(self.d / "strategy" / "daytrade.json", {})
        d = (doc.get("days") or doc).get(day) or {}
        return {**(d.get("tw") or {}), **(d.get("tp") or {})}

    # ---------- bundle ----------
    def bundle(self, asof: str | None = None, etfs=("00919",)) -> dict:
        days = self.px_days()
        if asof is None:
            asof = days[-1]
        days = [d for d in days if d <= asof]
        a = date.fromisoformat(asof)
        start6 = add_months(a.replace(day=1), -5).isoformat()
        start1 = add_months(a, -1).isoformat()
        win6 = [d for d in days if d >= start6]
        win1 = [d for d in days if d > start1]
        px = {d: self.px(d) for d in win6}
        today = px[asof]
        basic = self.basic()
        names = {c: v["n"] for c, v in basic.items()}
        close, mcap, universe = {}, {}, []
        for c, v in today.items():
            close[c] = v[0]
            info = basic.get(c)
            if info and info.get("sh") and v[0]:
                mcap[c] = round(v[0] * info["sh"] / 1e6)
            nm = names.get(c, "")
            if info and not info.get("alt") and not nm.endswith("DR"):
                universe.append(c)
        universe.sort()

        def series(win):
            out = defaultdict(list)
            for d in win:
                for c, v in px[d].items():
                    out[c].append(v[2] or 0)
            return out

        s6, s1 = series(win6), series(win1)
        tv6 = {c: math.floor(sum(v) / len(v)) for c, v in s6.items() if v}
        tv1 = {c: math.floor(sum(v) / len(v)) for c, v in s1.items() if v}
        med6 = {c: safe_median(v) for c, v in s6.items()}
        dt = self.daytrade(asof)
        turnover1 = {c: ((v[1] or 0) - (dt.get(c) or 0)) / 1000 for c, v in today.items()}

        cum = self.fin_cum()
        ni = self.single_quarter(cum, "ni")
        eps = self.single_quarter(cum, "eps")
        equity = defaultdict(dict)
        for q, doc in cum.items():
            for c, v in doc.items():
                if v.get("eq") is not None:
                    equity[c][q] = v["eq"]
        return {
            "asof": asof, "names": names, "universe": universe, "close": close, "mcap": mcap,
            "insider": self.latest_insider(), "tv6m_avg": tv6, "tv1m_avg": tv1, "tv6m_median": med6,
            "turnover1": turnover1, "ni": dict(ni), "equity": dict(equity), "eps": dict(eps),
            "rev": dict(self.revenue()), "div": dict(self.dividends()),
            "etf": {e: self.etf(e) for e in etfs}, "windows": {"6m": [win6[0], win6[-1], len(win6)],
                                                                 "1m": [win1[0], win1[-1], len(win1)]},
        }

    # ---------- FTSE（0050／0051／0056）額外欄位 ----------
    def ftse_extras(self, b: dict, cfg: dict) -> dict:
        """
        cfg: calc_date（本次計算日）、liq_end（年度流動性最後一個月 YYYY-MM）、ibes_csv、iw_csv
        """
        from statistics import median as _med
        basic = self.basic()
        asof = b["asof"]
        b["mkt"] = {c: ("TIB" if v["n"].endswith("-創") else v["mk"]) for c, v in basic.items()}
        b["alt"] = {c: v.get("alt", 0) for c, v in basic.items()}
        b["listing"] = {c: (f"{v['list'][:4]}-{v['list'][4:6]}-{v['list'][6:8]}" if len(v.get("list", "")) == 8 else None)
                        for c, v in basic.items()}
        files = sorted((self.raw / "foreign").glob("20*.json"))
        fdoc = _read(files[-1], {}) if files else {}
        b["foreign"] = {c: {"fol": (v[3] or 0) / 100, "headroom": ((v[1] or 0) / v[3]) if v[3] else NA}
                        for c, v in fdoc.items()}
        b["iw_override"] = _read_csv_map(cfg.get("iw_csv"), lambda r: float(r[1]))
        b["ibes"] = _read_csv_map(cfg.get("ibes_csv"), lambda r: {"dps1": float(r[1]), "dps2": float(r[2]),
                                                                   "brokers": int(float(r[3])) if len(r) > 3 else 2})
        # 5 日加權換手量：(T×5 + T-1×4 + … + T-4×1) / 15（成交量扣當沖，千股）
        days = [d for d in self.px_days() if d <= asof][-5:]
        acc = defaultdict(float)
        for i, d in enumerate(reversed(days)):
            p, dt = self.px(d), self.daytrade(d)
            for c, v in p.items():
                acc[c] += ((v[1] or 0) - (dt.get(c) or 0)) / 1000 * (5 - i)
        b["turnover5"] = {c: v / 15 for c, v in acc.items()}
        # 六個月總報酬、六個月前市場別（以本次計算日往前 6 個月的第一個交易日為起點）
        calc = date.fromisoformat(cfg.get("calc_date") or asof)
        start = add_months(calc, -6).isoformat()
        all_days = [d for d in self.px_days() if start <= d <= asof]
        if all_days:
            p0, p1 = self.px(all_days[0]), self.px(all_days[-1])
            # Dividend+ 規則 4.2.6：累積總報酬（含現金股利、股票股利），每日 (P_T×(1+s)+D_T)/P_{T-1} 連乘
            #   = (期末價/期初價) × Π 除權息日 (P_T×(1+s)+D_T)/P_T
            adj = defaultdict(lambda: 1.0)
            ev = defaultdict(lambda: [0.0, 0.0])   # (代號, 日期) → [現金, 股票股利率]
            for f in sorted((self.raw / "div").glob("20*.json")):
                for c, _y, _q, cash, stock, exd, exr, *_rest in _read(f, []):
                    if exd and all_days[0] < exd <= all_days[-1] and cash:
                        ev[(c, exd)][0] += cash
                    if exr and all_days[0] < exr <= all_days[-1] and stock:
                        ev[(c, exr)][1] += stock / 10        # 面額 10 元
            for (c, d), (cash, srate) in ev.items():
                p = self.px(d).get(c)
                if p and p[0]:
                    adj[c] *= (p[0] * (1 + srate) + cash) / p[0]
            b["ltr"] = {c: (p1[c][0] / v[0]) * adj[c] - 1 for c, v in p0.items() if c in p1 and v[0] and p1[c][0]}
            b["mkt_6m_ago"] = {c: v[3] for c, v in p0.items()}
        else:
            b["ltr"], b["mkt_6m_ago"] = {}, {}
        # 權益資產比：最近一季（有今年第三季就用，否則第二季）
        cum = self.fin_cum()
        qs = sorted(cum)
        b["eta"] = {}
        for q in reversed(qs[-2:]):
            for c, v in cum[q].items():
                if c in b["eta"] or not v.get("assets"):
                    continue
                pref = (basic.get(c, {}).get("pref") or 0) * 10 / 1000          # 特別股股本（千元，面額 10 元）
                # 規則 4.2.7：Total Shareholders' Equity = 特別股股本 + 普通股股東權益（歸屬母公司權益）
                common = v.get("eqp") if v.get("eqp") is not None else v.get("eq")
                b["eta"][c] = (((common or 0) + pref) / v["assets"], (v.get("cap") or 0) / v["assets"])
        # 上一會計年度有沒有發現金股利（0056「定期審核前之會計年度股利」）
        Y = int(asof[:4])
        b["fy_div"] = {c: sum(x for (y, q), x in d.items() if y == Y - 1) for c, d in b["div"].items()}
        # 年度流動性：每月日成交量中位數（股），T 月 = liq_end，往前 12 個月
        end = cfg.get("liq_end")
        if end:
            ey, em = int(end[:4]), int(end[5:7])
            months = []
            for i in range(12):
                y, m = ey, em - i
                while m <= 0:
                    y, m = y - 1, m + 12
                months.append(f"{y}-{m:02d}")
            vols = defaultdict(lambda: defaultdict(list))
            for d in self.px_days():
                if d[:7] in months:
                    for c, v in self.px(d).items():
                        vols[c][d[:7]].append(v[1] or 0)
            b["month_medians"] = {c: [(_med(v[m]) if v.get(m) else NA) for m in months] for c, v in vols.items()}
            b["month_days"] = {c: [len(v.get(m, [])) for m in months] for c, v in vols.items()}
        b["shares"] = {c: v.get("sh") for c, v in basic.items()}
        return b


def _read_csv_map(path, conv):
    import csv
    if not path or not Path(path).exists():
        return {}
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            if r and r[0].strip().isdigit():
                try:
                    out[r[0].strip()] = conv(r)
                except (ValueError, IndexError):
                    pass
    return out


def may_extras(pub: "Public", b: dict, Y: int) -> dict:
    """
    00919 5 月定審需要的額外欄位（原表 6 月版「估」「毛利率估EPS」「股利頻率」「最近一次除息日」「配息」）：
      payout       {代號: {年度: 現金股利 ÷ 全年 EPS ×100}}（配發率 %）
      eps_annual   {代號: {年度: 全年 EPS}}
      net_margin_avg 近 12 季單季稅後淨利率平均
      shares_k     發行股數（千股）
      freq         配息頻率：近兩年有第 1／3 季股利 → 每季；有上半年（Q2）→ 每半年；否則每年
                   （原表用公開資訊觀測站公司基本資料的「盈餘分派頻率」，這裡由股利紀錄推得）
      last_exdiv   最近一次（含已公告未來）除息日
      quarterly_zero 季配息且今年第 1 季現金股利為 0
    """
    cum = pub.fin_cum()
    basic = pub.basic()
    b["shares_k"] = {c: (v.get("sh") or 0) / 1000 for c, v in basic.items() if v.get("sh")}
    b["eps_annual"], b["payout"] = defaultdict(dict), defaultdict(dict)
    for y in range(Y - 4, Y):
        for c, v in cum.get(f"{y}Q4", {}).items():
            if v.get("eps") is not None:
                b["eps_annual"][c][y] = v["eps"]
    for c, d in b["div"].items():
        for y in range(Y - 4, Y):
            cash = [x for (yy, _q), x in d.items() if yy == y]
            e = b["eps_annual"].get(c, {}).get(y)
            if cash and e and e > 0:
                b["payout"][c][y] = sum(cash) / e * 100
    # 單季稅後淨利率（data/fund/income：[名稱, 市場, 營收, 毛利, 營業利益, 稅前, 母公司淨利, EPS]，累計數）
    rev_cum = {}
    for p in (pub.d / "fund" / "income").glob("20*Q*.json"):
        rev_cum[p.stem] = {c: v[2] for c, v in _read(p, {}).items() if v[2]}
    ni_cum = {q: {c: v.get("ni") for c, v in doc.items()} for q, doc in cum.items()}
    margins = defaultdict(list)
    for y in range(Y - 3, Y):
        for n in range(1, 5):
            q, pq = f"{y}Q{n}", f"{y}Q{n - 1}"
            for c, r in rev_cum.get(q, {}).items():
                ni = (ni_cum.get(q) or {}).get(c)
                if ni is None:
                    continue
                if n > 1:
                    r0, n0 = rev_cum.get(pq, {}).get(c), (ni_cum.get(pq) or {}).get(c)
                    if r0 is None or n0 is None:
                        continue
                    r, ni = r - r0, ni - n0
                if r:
                    margins[c].append(ni / r)
    b["net_margin_avg"] = {c: sum(v) / len(v) for c, v in margins.items() if v}
    b["fin_selfreport_eps"] = {}
    b["freq"] = {}
    for c in b["universe"]:
        qs = {q for (y, q) in b["div"].get(c, {}) if y >= Y - 2}
        b["freq"][c] = "每季" if ({"Q1", "Q3"} & qs) else ("每半年" if "Q2" in qs else "每年")
    b["last_exdiv"] = {}
    for c, evs in pub.exdiv_dates().items():
        b["last_exdiv"][c] = max(e[0] for e in evs)
    b["quarterly_zero"] = {c for c in b["universe"] if b["freq"].get(c) == "每季"
                           and b["div"].get(c, {}).get((Y, "Q1")) == 0}
    return b
