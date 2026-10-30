#!/usr/bin/env python3
"""
盤中即時資金流（永豐 Shioaji 行情，只訂閱報價、不會下單；金鑰只開「行情／資料＋正式環境」權限）

每個交易日 08:45 由 GitHub Actions 啟動（.github/workflows/flow-live.yml），跑到 13:35：
  1. 用前一個交易日成交金額前 200 名（永豐單一連線訂閱上限 200 檔）訂閱逐筆成交
  2. 每筆成交依內外盤分類：外盤（成交在賣價，主動買）、內盤（成交在買價，主動賣），累計金額
     中途才開始訂閱的股票，用永豐提供的累計外盤／內盤張數 × 均價補回之前的部分
  3. 每 60 秒按產業彙整「外盤 − 內盤」＝主動買賣淨額，連同每 15 分鐘切片，寫成 flow.json 推到 live 分支（網頁每分鐘讀）
  4. 收盤後把當天完整結果存到 main 的 data/flow/YYYY-MM-DD.json
用法：python scripts/flow_live.py [--until 13:35] [--interval 60] [--no-push]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
TPE = timezone(timedelta(hours=8))
TOP = 200
SLICE_MIN = 15
LIVE_DIR = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "flow-live"


def log(*a):
    print(f"[{datetime.now(TPE):%H:%M:%S}]", *a, flush=True)


def universe():
    daily = sorted((DATA / "daily").glob("20*.json"))
    q = json.loads(daily[-1].read_text(encoding="utf-8"))["q"]
    codes = sorted((c for c in q if len(c) == 4 and c.isdigit() and c[0] != "0" and q[c][8]), key=lambda c: -q[c][8])
    total = sum(q[c][8] for c in codes)
    top = codes[:TOP]
    sec = {}
    for name, rows in (json.loads((DATA / "sector-stocks.json").read_text(encoding="utf-8")).get("data") or {}).items():
        for r in rows:
            sec.setdefault(r["code"], name)
    cover = sum(q[c][8] for c in top) / total if total else None
    return top, {c: q[c][0] for c in top}, {c: sec.get(c, "其他") for c in top}, cover


class Flow:
    def __init__(self, names, sectors):
        self.names, self.sectors = names, sectors
        self.lock = threading.Lock()
        self.s: dict[str, dict] = {}
        self.slices: list[tuple[str, dict]] = []  # (切片開始時間, 各產業截至切片結束的累計淨額)

    def on_tick(self, _exchange, t):
        if getattr(t, "simtrade", False) or getattr(t, "intraday_odd", False):
            return  # 試撮、盤中零股不算
        code = t.code
        with self.lock:
            st = self.s.get(code)
            if st is None:
                # 第一次收到：用累計外盤／內盤張數 × 均價補回訂閱前的部分（扣掉這一筆，下面再加）
                avg = float(t.avg_price or t.close or 0)
                v = float(t.volume or 0)
                ask = float(getattr(t, "trade_ask_vol_sum", 0) or 0) - (v if t.tick_type == 1 else 0)
                bid = float(getattr(t, "trade_bid_vol_sum", 0) or 0) - (v if t.tick_type == 2 else 0)
                st = self.s[code] = {"out": max(ask, 0) * 1000 * avg, "in": max(bid, 0) * 1000 * avg}
            amt = float(t.amount or 0)
            if t.tick_type == 1:
                st["out"] += amt
            elif t.tick_type == 2:
                st["in"] += amt
            st.update(close=float(t.close), chg=float(t.pct_chg or 0), amt=float(t.total_amount or 0), ts=t.datetime.strftime("%H:%M:%S"))

    def by_sector(self):
        out: dict[str, dict] = {}
        for code, st in self.s.items():
            g = out.setdefault(self.sectors[code], {"out": 0.0, "in": 0.0, "amt": 0.0, "n": 0})
            g["out"] += st["out"]
            g["in"] += st["in"]
            g["amt"] += st.get("amt", 0)
            g["n"] += 1
        return out

    def snapshot(self, cover, status):
        with self.lock:
            secs = self.by_sector()
            stocks = [{"code": c, "name": self.names[c], "sector": self.sectors[c], "close": st.get("close"), "chg": round(st.get("chg", 0), 2),
                       "amt": round(st.get("amt", 0) / 1e8, 2), "out": round(st["out"] / 1e8, 2), "in": round(st["in"] / 1e8, 2),
                       "net": round((st["out"] - st["in"]) / 1e8, 2)} for c, st in self.s.items()]
            slices = list(self.slices)
        labels = [s[0] for s in slices]
        sectors = []
        for name, g in secs.items():
            cum = [s[1].get(name, 0.0) for s in slices]
            sl = [round((cum[i] - (cum[i - 1] if i else 0)) / 1e8, 2) for i in range(len(cum))]
            sectors.append({"name": name, "net": round((g["out"] - g["in"]) / 1e8, 2), "out": round(g["out"] / 1e8, 2), "in": round(g["in"] / 1e8, 2),
                            "amt": round(g["amt"] / 1e8, 2), "n": g["n"], "slices": sl})
        sectors.sort(key=lambda x: -x["net"])
        stocks.sort(key=lambda x: -x["net"])
        tot_out, tot_in = sum(g["out"] for g in secs.values()), sum(g["in"] for g in secs.values())
        return {"updatedAt": datetime.now(TPE).isoformat(timespec="seconds"), "date": datetime.now(TPE).date().isoformat(), "status": status,
                "n": len(stocks), "cover": round(cover * 100, 1) if cover else None, "sliceMin": SLICE_MIN, "slices": labels,
                "total": {"net": round((tot_out - tot_in) / 1e8, 2), "out": round(tot_out / 1e8, 2), "in": round(tot_in / 1e8, 2)},
                "sectors": sectors, "stocks": stocks}

    def close_slice(self, label):
        with self.lock:
            self.slices.append((label, {k: v["out"] - v["in"] for k, v in self.by_sector().items()}))


def publish(doc, push: bool):
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    (LIVE_DIR / "flow.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if not push:
        return
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        return
    g = ["git", "-C", str(LIVE_DIR)]
    if not (LIVE_DIR / ".git").exists():
        subprocess.run(g + ["init", "-q", "-b", "live"], check=True)
        subprocess.run(g + ["config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(g + ["config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
    # live 分支只留一個 commit（每次覆蓋），不讓 repo 越長越大
    subprocess.run(g + ["checkout", "-q", "--orphan", "tmp"], capture_output=True)
    subprocess.run(g + ["add", "flow.json"], check=True)
    subprocess.run(g + ["commit", "-q", "-m", f"flow {doc['updatedAt']}"], capture_output=True)
    r = subprocess.run(g + ["push", "-q", "-f", f"https://x-access-token:{token}@github.com/{repo}.git", "HEAD:live"], capture_output=True, text=True)
    if r.returncode:
        log("推送 live 分支失敗：", r.stderr.strip()[-200:])
    subprocess.run(g + ["branch", "-D", "live"], capture_output=True)
    subprocess.run(g + ["branch", "-m", "live"], capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="13:35")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    today = datetime.now(TPE).date()
    hol = set(json.loads((DATA / "calendar.json").read_text(encoding="utf-8")).get("holidays", [])) if (DATA / "calendar.json").exists() else set()
    if today.weekday() >= 5 or today.isoformat() in hol:
        log("今天休市")
        return 0
    import shioaji as sj

    codes, names, sectors, cover = universe()
    log(f"訂閱成交金額前 {len(codes)} 名，約占全市場成交 {cover * 100:.0f}%")
    flow = Flow(names, sectors)
    api = sj.Shioaji()
    api.login(api_key=os.environ["SHIOAJI_API_KEY"], secret_key=os.environ["SHIOAJI_SECRET_KEY"], subscribe_trade=False)
    api.set_on_tick_stk_v1_callback(flow.on_tick)
    for _ in range(120):  # 等登入後背景下載的商品檔
        try:
            if api.Contracts.Stocks["2330"] is not None:
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    ok = 0
    for c in codes:
        try:
            api.subscribe(api.Contracts.Stocks[c], quote_type=sj.QuoteType.Tick, version=sj.QuoteVersion.v1)
            ok += 1
        except Exception as e:  # noqa: BLE001
            log(f"{c} 訂閱失敗：{e}")
    log(f"已訂閱 {ok} 檔")

    hh, mm = map(int, a.until.split(":"))
    end = datetime.now(TPE).replace(hour=hh, minute=mm, second=0, microsecond=0)
    open_t = datetime.now(TPE).replace(hour=9, minute=0, second=0, microsecond=0)
    next_slice = open_t
    while next_slice + timedelta(minutes=SLICE_MIN) <= datetime.now(TPE):
        next_slice += timedelta(minutes=SLICE_MIN)  # 中途啟動：之前的切片併到第一個
    while True:
        now = datetime.now(TPE)
        while now >= next_slice + timedelta(minutes=SLICE_MIN) and next_slice < open_t.replace(hour=13, minute=30):
            flow.close_slice(next_slice.strftime("%H:%M"))
            next_slice += timedelta(minutes=SLICE_MIN)
        done = now >= end
        doc = flow.snapshot(cover, "closed" if done else ("live" if now >= open_t else "pre"))
        publish(doc, not a.no_push)
        log(f"{len(flow.s)} 檔有成交，總淨額 {doc['total']['net']:+.1f} 億")
        if done:
            break
        time.sleep(a.interval)
    if next_slice < open_t.replace(hour=13, minute=30):
        flow.close_slice(next_slice.strftime("%H:%M"))
    doc = flow.snapshot(cover, "closed")
    publish(doc, not a.no_push)
    out = DATA / "flow" / f"{doc['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.copy(out, DATA / "flow" / "latest.json")
    log(f"收盤：{out}")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)  # 不等 shioaji 背景連線關閉
