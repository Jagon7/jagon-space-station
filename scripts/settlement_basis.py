"""
結算策略：股票期貨每天的「整日平均折溢價」（永豐 Shioaji 1 分 K，只查行情）

每天 09:05～13:24 之間，股期近月每一根有成交的 1 分 K：折溢價＝期貨收盤 ÷ 當下現貨價（現貨 1 分 K 收盤，沒成交沿用前一筆）− 1
當天的折溢價＝這些分鐘的簡單平均（只用期貨有成交的分鐘，避免冷門股期用很久以前的舊價格）
結果 data/settlement/basis_day.json {"window": 區間, "days": {日期: {股票代號: [整日平均折溢價, 期貨有成交的分鐘數]}}}（區間改了就全部重算）；由 orderflow_ticks.py 登入後呼叫 run()
1 分 K 一次查整段期間，流量很小
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

TPE = timezone(timedelta(hours=8))
T0, T1 = 9 * 60 + 5, 13 * 60 + 24  # 計算區間 09:05～13:24（避開開盤前幾分鐘與收盤前的集合競價）
WINDOW = "09:05-13:24"


def _bars(k) -> dict[str, dict[int, tuple[float, float]]]:
    """1 分 K → {日期: {分鐘: (收盤, 量)}}；永豐的 ts 是台灣時間當成 UTC 的奈秒"""
    out: dict[str, dict[int, tuple[float, float]]] = {}
    for ts, c, v in zip(k.ts, k.Close, k.Volume):
        tm = datetime.fromtimestamp(ts / 1e9, timezone.utc)
        m = tm.hour * 60 + tm.minute
        if 9 * 60 <= m <= T1 and c:  # 09:00 起都留著，給 09:05 前的現貨價沿用
            out.setdefault(tm.date().isoformat(), {})[m] = (float(c), float(v or 0))
    return out


def day_basis(fut: dict[int, tuple[float, float]], stk: dict[int, tuple[float, float]]):
    """一天的整日平均折溢價：期貨有成交的分鐘 ÷ 當下現貨價（沿用前一筆）"""
    xs, last = [], None
    for m in range(9 * 60, T1 + 1):
        if m in stk:
            last = stk[m][0]
        f = fut.get(m)
        if m >= T0 and f and f[1] > 0 and last:
            xs.append(f[0] / last - 1)
    return (round(sum(xs) / len(xs), 5), len(xs)) if xs else None


def run(api, data: Path, deadline: float, log=print) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fetch_settlement as fs

    hol = fs.holidays()
    now = datetime.now(TPE)
    today = now.date()
    # 跟 build_settlement 一樣：最後一個已收盤交易日的「隔天」屬於哪一期（結算日收盤後就換下一期）
    start, sday, month = fs.period((today if now.hour >= 14 else today - timedelta(days=1)) + timedelta(days=1), hol)
    end = min(today if now.hour >= 14 else today - timedelta(days=1), sday)
    contracts = json.loads((data / "settlement" / "contracts.json").read_text(encoding="utf-8"))["contracts"]
    big = {k: v[0] for k, v in contracts.items() if v[1] == 2000}  # 契約代號 → 股票代號（只用 2,000 股的大型股期）
    path = data / "settlement" / "basis_day.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    doc = raw.get("days", {}) if raw.get("window") == WINDOW else {}

    # 永豐的股期合約：類別代號（例如 CDF）＋交割月份（格式可能是 202611 或 2026/11，統一成純數字比對）
    fut = {}
    try:
        root = api.Contracts.Futures
        for cat in list(root):
            if isinstance(cat, str):
                cat = root[cat]
            try:
                items = list(cat)
            except TypeError:
                items = [cat]
            for c in items:
                if isinstance(c, str):
                    c = cat[c]
                code = str(getattr(c, "code", "") or "")
                dm = "".join(ch for ch in str(getattr(c, "delivery_month", "") or "") if ch.isdigit())
                cg = str(getattr(c, "category", "") or "") or code[:3]
                if code.endswith(("R1", "R2")) or dm != month:
                    continue
                k = cg[:-1] if cg.endswith("F") else ""
                if k in big and k not in fut:
                    fut[k] = c
    except Exception as e:  # noqa: BLE001
        log(f"折溢價：讀取期貨合約失敗 {e}")
        return 0
    log(f"折溢價：{month} 近月股期 {len(fut)} 個，期間 {start} ～ {end}")

    # 實際有開盤的日子（每日行情檔）：颱風假等臨時休市不在 calendar 裡，用這個跳過
    trading = {p.stem for p in (data / "daily").glob("20*.json")}
    known_last = max(trading) if trading else ""
    # 每檔從本期還沒算過的最早一天查到 end（已算過的日子不重查：end 只會是已收盤的日子，算過就是定案）
    n = 0
    for k, c in fut.items():
        if time.time() > deadline:
            log("折溢價：時間到，下次接著補")
            break
        stock = big[k]
        have = [d for d in doc if start.isoformat() <= d <= end.isoformat() and stock in doc[d]]
        s0 = start
        while s0 <= end and (s0.isoformat() in have or s0.weekday() >= 5 or s0.isoformat() in hol
                             or (s0.isoformat() < known_last and s0.isoformat() not in trading)):
            s0 += timedelta(days=1)
        if s0 > end:
            continue
        try:
            kf = api.kbars(contract=c, start=s0.isoformat(), end=end.isoformat())
            ks = api.kbars(contract=api.Contracts.Stocks[stock], start=s0.isoformat(), end=end.isoformat())
        except Exception as e:  # noqa: BLE001
            log(f"折溢價：{k}/{stock} 失敗 {e}")
            continue
        bf, bs = _bars(kf), _bars(ks)
        for d, sm in bs.items():
            r = day_basis(bf.get(d, {}), sm)
            # 期貨整天沒成交記 [None, 0]：算過了、下次不重查（網頁那天改用期交所結算價估）
            doc.setdefault(d, {})[stock] = list(r) if r else [None, 0]
        n += 1
    doc = {d: v for d, v in sorted(doc.items()) if v}
    path.write_text(json.dumps({"window": WINDOW, "days": doc}, separators=(",", ":")), encoding="utf-8")
    log(f"折溢價：本次 {n} 檔；" + "、".join(f"{d[5:]} {sum(x[0] is not None for x in v.values())}" for d, v in doc.items() if d >= start.isoformat()))
    return n


def main() -> int:
    """單獨執行（結算每日更新 workflow）：登入永豐（只查行情）→ 補本期整日平均折溢價"""
    import os
    data = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    log = lambda *a: print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)  # noqa: E731
    if not os.environ.get("SHIOAJI_API_KEY"):
        log("沒有永豐金鑰，略過折溢價（網頁會用期交所結算價估）")
        return 0
    import shioaji as sj
    api = sj.Shioaji()
    api.login(api_key=os.environ["SHIOAJI_API_KEY"], secret_key=os.environ["SHIOAJI_SECRET_KEY"], subscribe_trade=False)
    for _ in range(120):
        try:
            if api.Contracts.Stocks["2330"] is not None:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    run(api, data, time.time() + 15 * 60, log=log)
    return 0


if __name__ == "__main__":
    import os as _os
    rc = main()
    sys.stdout.flush()
    _os._exit(rc)
