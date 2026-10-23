"""
市場風險監控 → public/data/risk.json
  來源：data/intel/risk.json（Yahoo：VIX、VVIX、VIX9D、VIX3M、SKEW、MOVE、美元指數；FRED：高收益／投資級債利差、10Y−2Y、金融壓力指數）
        data/futures/daily.json（台指選擇權 P/C、外資台指期淨部位）、public/data/chips/futures.json（散戶小台多空比）
  CDS（信用違約交換）沒有免費公開資料：整體信用用 ICE BofA 公司債利差（OAS）代替，高收益債利差和 CDX HY 走勢高度一致；
  個別科技廠用 CreditGrades 模型的「股價隱含 CDS」：股價、EWMA 波動度、每股負債（Yahoo 季報總負債 ÷ 流通股數）
  → 5 年 CDS 利差估計（Oracle 約 190～210bp，和新聞報導的實際 CDS 相近）；低負債公司模型值接近 0，只看變化
  5 日上升 ≥ 75bp，或上升 ≥ 25bp 且 ≥ 25%（而且目前 ≥ 50bp）列入警示
  每個指標：最新值、1 日／5 日／20 日變化、近一年百分位、依門檻分「正常／警戒／危險」
  風險溫度（0～100，越高越緊張）：每個核心指標取「絕對水準分數」和「近一年百分位」各半，再平均；每天回算近一年走勢
    絕對水準分數：平靜值 0 分、警戒門檻 50 分、危險門檻 80 分、再超過一段到 100 分，中間線性內插
    只用百分位的話，平靜的一年裡稍微變動就會被當成高風險，所以加上絕對水準
"""
from __future__ import annotations

import bisect
import json
import math
from math import exp, log, sqrt
from datetime import datetime
from pathlib import Path

from build_strategy import TPE, _load

# id, 名稱, 分組, 公式, 單位, 小數, 風險方向(+1 越高越危險), 門檻(平靜, 警戒, 危險), 納入風險溫度, 說明
SPECS = [
    ("vix", "VIX 恐慌指數", "波動率", ("^VIX",), "", 2, 1, (13, 20, 30), True,
     "S&P 500 選擇權推算的未來 30 天預期波動。20 以上市場開始緊張，30 以上屬於恐慌。"),
    ("vvix", "VVIX", "波動率", ("^VVIX",), "", 1, 1, (85, 115, 135), True,
     "VIX 本身的波動率：市場花多少錢買「VIX 急跳」的保險。偏高代表大家擔心突發事件。"),
    ("vixts", "VIX 期限結構", "波動率", ("^VIX", "/", "^VIX3M"), "", 3, 1, (0.85, 0.95, 1.0), True,
     "近月 VIX ÷ 3 個月 VIX。正常小於 1（遠期較貴）；大於 1 是「逆價差」，代表短期恐慌高過長期，常出現在急跌時。"),
    ("vix9d", "VIX9D／VIX", "波動率", ("^VIX9D", "/", "^VIX"), "", 3, 1, (0.85, 1.0, 1.15), False,
     "未來 9 天波動 ÷ 30 天波動。大於 1 代表市場擔心的是眼前幾天（事件、財報、數據公布）。"),
    ("skew", "SKEW 尾端風險", "波動率", ("^SKEW",), "", 1, 1, (130, 150, 160), False,
     "深度價外賣權的相對價格，反映對「黑天鵝大跌」的避險需求。偏高不代表馬上跌，但代表法人在買保險。"),
    ("move", "MOVE 債市波動", "利率與美元", ("^MOVE",), "", 1, 1, (75, 110, 130), True,
     "美國公債選擇權的隱含波動（債市版 VIX）。利率劇烈波動時通常會外溢到股市。"),
    ("hy", "高收益債利差", "信用", ("BAMLH0A0HYM2",), "bp", 0, 1, (280, 400, 500), True,
     "ICE BofA 美國高收益公司債對公債的利差（OAS），可視為 CDS 信用違約交換利差的替代：利差擴大代表市場要求更高的違約風險補償。"),
    ("ig", "投資級債利差", "信用", ("BAMLC0A0CM",), "bp", 0, 1, (80, 130, 160), True,
     "ICE BofA 美國投資級公司債利差（OAS）。投資級也開始擴大，代表信用緊縮擴散到體質較好的公司。"),
    ("stlfsi", "金融壓力指數", "信用", ("STLFSI4",), "", 2, 1, (-1, 0, 1), True,
     "聖路易聯準銀行金融壓力指數（每週）：0 是長期平均，大於 0 代表壓力高於平均。"),
    ("curve", "10Y−2Y 利差", "利率與美元", ("T10Y2Y",), "%", 2, -1, (1, 0, -0.5), False,
     "10 年期減 2 年期美債殖利率。轉負（殖利率倒掛）常被視為衰退前兆；倒掛後重新轉正的階段也常伴隨景氣轉弱。"),
    ("dxy", "美元指數 20 日變化", "利率與美元", ("DX-Y.NYB", "chg20"), "%", 2, 1, (-2, 2, 4), True,
     "美元指數近 20 個交易日的漲跌。美元快速走強通常代表資金回流美國，對台股等新興市場不利。"),
]
TW_SPECS = [
    ("pcoi", "台指選擇權 P/C（未平倉）", "pcOI", "%", 1,
     "賣權未平倉 ÷ 買權未平倉。台股習慣解讀：大於 100 表示賣權賣方（看不跌）多、支撐較強；明顯下滑代表下檔支撐變弱。"),
    ("txf", "外資台指期淨部位", "txfF", "口", 0, "外資在台指期的淨多（正）／淨空（負）口數，空單快速增加是避險或看空的訊號。"),
    ("retail", "散戶小台多空比", "retail", "%", 1, "散戶在小台指的多空比。散戶越偏多，反向來看越需要留意。"),
]
CORE = [s[0] for s in SPECS if s[8]]
CDS_NAMES = {"ORCL": "Oracle", "CRWV": "CoreWeave", "NBIS": "Nebius", "INTC": "Intel", "SMCI": "Super Micro", "DELL": "Dell",
             "MU": "美光", "AMD": "AMD", "AVGO": "Broadcom", "META": "Meta", "MSFT": "Microsoft", "GOOGL": "Alphabet",
             "AMZN": "Amazon", "NVDA": "NVIDIA"}
VOL_WIN = 60          # 至少要有 60 天價格才開始算
EWMA = 0.97           # 股價波動度的指數加權衰減
CDS_JUMP_BP = 25      # 5 日上升至少 25bp
CDS_JUMP_PCT = 25     # 而且至少上升 25%
CDS_JUMP_BIG = 75     # 或 5 日上升 75bp 以上（本來就高的公司，百分比不會太大）
CDS_MIN = 50          # 只看 50bp 以上的（低負債公司模型值接近 0，百分比變化沒有意義）


def _phi(x: float) -> float:
    return 0.5 * math.erfc(-x / sqrt(2))


def creditgrades(S: float, D: float, sig_s: float, r: float = 0.04, T: float = 5, Lbar: float = 0.5, lam: float = 0.3, R: float = 0.5):
    """CreditGrades（RiskMetrics, 2002）股價隱含 5 年 CDS 利差（bp）
    S 股價、D 每股負債、sig_s 股價年化波動、Lbar 違約時債權平均回收門檻、lam 其不確定性、R 回收率"""
    if S <= 0 or D <= 0 or sig_s <= 0:
        return 0.0
    LD = Lbar * D
    d = (S + LD) / LD * exp(lam ** 2)
    sig = sig_s * S / (S + LD)

    def P(t):
        A = sqrt(sig ** 2 * t + lam ** 2)
        return _phi(-A / 2 + log(d) / A) - d * _phi(-A / 2 - log(d) / A)

    xi = lam ** 2 / sig ** 2
    z = sqrt(0.25 + 2 * r / sig ** 2)

    def G(u):
        v = sig * sqrt(u)
        return d ** (z + 0.5) * _phi(-log(d) / v - z * v) + d ** (-z + 0.5) * _phi(-log(d) / v + z * v)

    try:
        H = exp(r * xi) * (G(T + xi) - G(xi))
        P0, PT = P(0), P(T)
        den = P0 - PT * exp(-r * T) - H
        return max(0.0, r * (1 - R) * (1 - P0 + H) / den * 1e4) if den > 0 else 0.0
    except (OverflowError, ValueError, ZeroDivisionError):
        return 0.0


def _asof(rows: list, d: str):
    """財報時間序列中「d 當天以前最新」的一筆（都比 d 晚就用最早一筆）"""
    v = None
    for x, val in rows:
        if x <= d:
            v = val
    return v if v is not None else (rows[0][1] if rows else None)


def credit_block(raw: dict, fund: dict) -> list:
    tnx = dict(raw.get("^TNX", []))
    out = []
    for sym, name in CDS_NAMES.items():
        px, f = raw.get(sym) or [], fund.get(sym) or {}
        if len(px) < VOL_WIN + 30 or not f.get("debt") or not f.get("shares"):
            continue
        # 波動度用 EWMA（衰減 0.97，約 23 天半衰期），單日報酬先截在 ±8%：
        # 一般滾動視窗遇到單日暴漲暴跌，會在 60 天後突然掉出視窗造成斷崖；大漲也不該讓違約風險暴增
        var, vs = None, []
        for i in range(1, len(px)):
            x = max(-0.08, min(0.08, log(px[i][1] / px[i - 1][1])))
            var = x * x if var is None else EWMA * var + (1 - EWMA) * x * x
            vs.append(sqrt(var * 252))
        ser = []
        for i in range(max(VOL_WIN, len(px) - HIST), len(px)):
            d, S = px[i]
            vol = vs[i - 1]
            debt, sh = _asof(f["debt"], d), _asof(f["shares"], d)
            if not debt or not sh:
                continue
            r = (tnx.get(d) or 4.0) / 100
            ser.append([d, round(creditgrades(S, debt / sh, vol, r), 1), vol])
        if len(ser) < 25:
            continue
        vals = [x[1] for x in ser]
        v = vals[-1]
        D = _asof(f["debt"], ser[-1][0]) / _asof(f["shares"], ser[-1][0])
        S = px[-1][1]
        out.append({"sym": sym, "name": name, "date": ser[-1][0], "value": v, "chg1": round(v - vals[-2], 1),
                    "chg5": round(v - vals[-6], 1), "chg20": round(v - vals[-21], 1) if len(vals) > 20 else None,
                    "v5": vals[-6], "pct": _pct(vals[-252:], v), "price": S, "vol": round(ser[-1][2] * 100, 1),
                    "lev": round(0.5 * D / (S + 0.5 * D) * 100, 1), "debtB": round(_asof(f["debt"], ser[-1][0]) / 1e9, 1),
                    "spark": [[d, x] for d, x, _ in ser]})
    out.sort(key=lambda x: -x["value"])
    return out


def cds_jumps(credit: list) -> list:
    return [c for c in credit if c["value"] >= CDS_MIN and (c["chg5"] >= CDS_JUMP_BIG or
            (c["chg5"] >= CDS_JUMP_BP and c["v5"] > 0 and c["chg5"] / c["v5"] * 100 >= CDS_JUMP_PCT))]
HIST = 260


def _series(raw: dict, f: tuple) -> list:
    if len(f) == 3 and f[1] == "/":
        a, b = dict(raw.get(f[0], [])), dict(raw.get(f[2], []))
        return [[d, round(a[d] / b[d], 4)] for d in sorted(a) if d in b and b[d]]
    s = raw.get(f[0], [])
    if len(f) == 2 and f[1] == "chg20":
        return [[s[i][0], round((s[i][1] / s[i - 20][1] - 1) * 100, 3)] for i in range(20, len(s)) if s[i - 20][1]]
    return [list(x) for x in s]


def _pct(hist: list, v: float) -> float:
    xs = sorted(hist)
    return round(bisect.bisect_left(xs, v) / len(xs) * 100, 1) if xs else 50.0


def _absolute(v: float, direction: int, th: tuple) -> float:
    calm, warn, bad = (x * direction for x in th)
    v *= direction
    for lo, hi, a, b in ((calm, warn, 0, 50), (warn, bad, 50, 80), (bad, bad + (bad - warn), 80, 100)):
        if v <= hi:
            return max(0.0, a + (v - lo) / (hi - lo) * (b - a)) if v >= lo else (0.0 if a == 0 else a)
    return 100.0


def _score(v: float, p: float, direction: int, th: tuple) -> float:
    return round((_absolute(v, direction, th) + (p if direction > 0 else 100 - p)) / 2, 1)


def _level(v: float, direction: int, th: tuple) -> str:
    _, warn, bad = th
    if direction > 0:
        return "危險" if v >= bad else "警戒" if v >= warn else "正常"
    return "危險" if v <= bad else "警戒" if v <= warn else "正常"


def _temp_label(t: float) -> str:
    return "高" if t >= 75 else "偏高" if t >= 55 else "中性" if t >= 30 else "低"


def build(data_dir: Path, public_dir: Path):
    raw = (_load(data_dir / "intel" / "risk.json", {}) or {}).get("series", {})
    if "^VIX" not in raw:
        print("風險監控：還沒有資料，略過")
        return
    inds, ser = [], {}
    for sid, name, group, f, unit, dec, dirn, th, core, desc in SPECS:
        s = _series(raw, f)
        if unit == "bp":
            s = [[d, round(v * 100, 1)] for d, v in s]
        if len(s) < 30:
            continue
        ser[sid] = s
        vals = [v for _, v in s]
        v = vals[-1]
        ago = lambda n: vals[-1 - n] if len(vals) > n else None  # noqa: E731
        p = _pct(vals[-252:], v)
        inds.append({"id": sid, "name": name, "group": group, "unit": unit, "dec": dec, "dir": dirn, "th": list(th[1:]), "calm": th[0], "core": core,
                     "desc": desc, "date": s[-1][0], "value": round(v, dec + 1), "chg1": None if ago(1) is None else round(v - ago(1), dec + 1),
                     "chg5": None if ago(5) is None else round(v - ago(5), dec + 1), "chg20": None if ago(20) is None else round(v - ago(20), dec + 1),
                     "pct": p if dirn > 0 else round(100 - p, 1), "level": _level(v, dirn, th), "score": _score(v, p, dirn, th),
                     "spark": [[d, x] for d, x in s[-HIST:]]})

    # 風險溫度：每天用各核心指標「到當天為止近一年」的百分位平均（遇到沒有資料的日子用最近一筆）
    days = [d for d, _ in raw["^VIX"]][-HIST:]
    temp = []
    for d in days:
        ps = []
        for sid in CORE:
            s = ser.get(sid)
            if not s:
                continue
            ds = [x[0] for x in s]
            i = bisect.bisect_right(ds, d) - 1
            if i < 20:
                continue
            window = [x[1] for x in s[max(0, i - 251):i + 1]]
            spec = next(x for x in SPECS if x[0] == sid)
            ps.append(_score(s[i][1], _pct(window, s[i][1]), spec[6], spec[7]))
        if len(ps) >= 5:
            temp.append([d, round(sum(ps) / len(ps), 1)])
    t_now = temp[-1][1] if temp else None

    # 台股端
    tw = []
    fut = (_load(public_dir / "chips" / "futures.json", {}) or {})
    cols, rows = fut.get("cols") or [], fut.get("rows") or []
    for sid, name, col, unit, dec, desc in TW_SPECS:
        if col not in cols:
            continue
        k = cols.index(col)
        s = [[r[0], r[k]] for r in rows if r[k] is not None]
        if len(s) < 5:
            continue
        vals = [v for _, v in s]
        tw.append({"id": sid, "name": name, "unit": unit, "dec": dec, "desc": desc, "date": s[-1][0], "value": vals[-1],
                   "chg1": round(vals[-1] - vals[-2], dec + 1), "chg5": round(vals[-1] - vals[-6], dec + 1) if len(vals) > 5 else None,
                   "pct": _pct(vals[-252:], vals[-1]), "spark": s[-HIST:]})

    alerts = [f"{i['name']} {i['value']:,.{i['dec']}f}{'bp' if i['unit'] == 'bp' else ''}（{i['level']}）" for i in inds if i["level"] != "正常"]
    hy = next((i for i in inds if i["id"] == "hy"), None)
    if hy and hy["chg20"] is not None and hy["chg20"] >= 50:
        alerts.append(f"高收益債利差 20 日擴大 {hy['chg20']:.0f}bp")
    vix = next((i for i in inds if i["id"] == "vix"), None)
    if vix and vix["chg1"] is not None and vix["value"] - vix["chg1"] > 0 and vix["chg1"] / (vix["value"] - vix["chg1"]) >= 0.2:
        alerts.append(f"VIX 單日大漲 {vix['chg1'] / (vix['value'] - vix['chg1']) * 100:.0f}%")
    credit = credit_block(raw, (_load(data_dir / "intel" / "risk.json", {}) or {}).get("fund", {}))
    jumps = cds_jumps(credit)
    for c in jumps:
        alerts.append(f"{c['name']} 股價隱含 CDS 5 日 +{c['chg5']:.0f}bp（{c['v5']:.0f} → {c['value']:.0f}bp）")
    out = {"updatedAt": datetime.now(TPE).isoformat(timespec="minutes"), "asof": raw["^VIX"][-1][0],
           "credit": credit, "cdsJumps": [c["sym"] for c in jumps],
           "temp": t_now, "tempLabel": _temp_label(t_now) if t_now is not None else None,
           "temp5": temp[-6][1] if len(temp) > 5 else None, "tempHist": temp, "alerts": alerts,
           "indicators": inds, "tw": tw}
    (public_dir / "risk.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"風險監控：{out['asof']} 溫度 {t_now}（{out['tempLabel']}），{len(inds)} 項指標、{len(alerts)} 項警示")
