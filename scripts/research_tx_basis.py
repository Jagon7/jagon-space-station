#!/usr/bin/env python3
"""
台指期價差（期貨 − 加權指數）與盤中廣度：①能不能分辨突破盤 ②價差太大／太逆時做價差收斂有沒有賺

假設（使用者）：台指要突破，股票一定齊漲齊跌 → 價差穩定；價差太大 → 空台指多現貨（台積、0050）；價差太逆 → 多台指空現貨
資料：data/futures/day（台指期日盤 1 分 K）、data/market/index1m（加權指數每分鐘、類股指數幾個時間點）、data/futures/regime_rows.json（BO／MR 結果）
價差 b(t)＝台指期 1 分 K 收盤 − 同一分鐘加權指數（現貨 09:00 開盤，比期貨晚 15 分鐘）
  b 的「正常水準」會隨除息旺季、距結算天數變動 → 用「偏離」＝ b − 前一交易日全天平均 b
指標（09:15 可知）：偏離、09:00～09:15 價差的標準差（穩不穩）、類股齊漲齊跌比例（09:15 對昨收跟大盤同方向的類股比例）
套利回測：偏離超過門檻 → 期貨反向、現貨順向，13:30 平倉，損益＝價差收斂點數（未扣現貨成本，另列 0050 當沖成本約 0.25%）
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))


def load_dir(d: Path, conv=None) -> dict:
    out = {}
    for f in sorted(d.glob("20*.json")) if d.exists() else []:
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            out[k] = conv(v) if conv else v
    return out


def main():
    day = load_dir(DATA / "futures" / "day", lambda v: {b[0]: b[1:] for b in v["bars"]})
    idx = load_dir(DATA / "market" / "index1m")
    reg = {r["date"]: r for r in json.loads((DATA / "futures" / "regime_rows.json").read_text(encoding="utf-8"))}
    dates = sorted(d for d in idx if d in day)
    rows = []
    prev = None
    for d in dates:
        t, bars = idx[d]["t"], day[d]

        def basis(k):
            b = bars.get(k + 15)
            return b[3] - t[k] if b and t[k] else None
        bs = [basis(k) for k in range(271)]
        valid = [x for x in bs if x is not None]
        if len(valid) < 200:
            prev = None
            continue
        avg = st.mean(valid)
        if prev is not None and bs[15] is not None:
            early = [x for x in bs[0:16] if x is not None]
            px = t[15]
            dev = bs[15] - prev["avg"]
            # 類股齊漲齊跌：09:15 對昨天 13:30
            s_now, s_prev = idx[d]["s"], idx[prev["d"]]["s"]
            mkt = t[15] / prev["close"] - 1 if prev["close"] else 0
            same = tot = 0
            for name, v in s_now.items():
                p = (s_prev.get(name) or [None] * 5)[4]
                if v[1] and p:
                    tot += 1
                    same += (v[1] / p - 1) * mkt > 0
            # 套利：09:15 進場，13:30（指數最後一分鐘、期貨同一分鐘）出場；損益＝(進場偏離方向) × (b915 − b1330)
            b_exit = bs[270] if bs[270] is not None else valid[-1]
            r = reg.get(d) or {}
            rows.append({"date": d, "px": px, "dev": dev, "devPct": dev / px * 100, "sd": st.pstdev(early), "sdPct": st.pstdev(early) / px * 100,
                         "breadth": same / tot if tot else None, "mkt": mkt * 100, "conv": bs[15] - b_exit,
                         "bo": r.get("bo"), "mr": r.get("mr"), "boDay": r.get("boDay"), "eff": r.get("eff")})
        prev = {"d": d, "avg": avg, "close": t[270] or t[-1]}

    def summ(rs, key=None):
        rs = [r for r in rs if r["bo"] is not None]
        if not rs:
            return "n=0"
        return (f"n={len(rs):4d} BO日 {sum(r['boDay'] for r in rs) / len(rs) * 100:4.1f}% BO {st.mean(r['bo'] for r in rs):+6.1f} MR {st.mean(r['mr'] for r in rs):+6.1f} "
                f"效率 {st.mean(r['eff'] for r in rs):.2f}")
    print(f"共 {len(rows)} 天：{rows[0]['date']} ～ {rows[-1]['date']}" if rows else "沒有資料")
    for k, lab in (("sdPct", "前 15 分鐘價差波動（%）"), ("breadth", "類股同方向比例"), ("devPct", "價差偏離（%）")):
        xs = sorted(r[k] for r in rows if r[k] is not None)
        if len(xs) < 30:
            continue
        cuts = [xs[len(xs) * i // 5] for i in (1, 2, 3, 4)]
        print(f"\n{lab} 五分位切點 {[round(c, 4) for c in cuts]}")
        lo = -1e9
        for i, c in enumerate(cuts + [1e9]):
            g = [r for r in rows if r[k] is not None and lo < r[k] <= c]
            print(f"  第 {i + 1} 組：{summ(g)}")
            lo = c
    # 齊漲齊跌＋價差穩定
    sd_med = st.median(r["sdPct"] for r in rows)
    print("\n組合：")
    for lab, f in (("類股 ≥ 85% 同方向＋價差穩（波動 < 中位數）", lambda r: (r["breadth"] or 0) >= 0.85 and r["sdPct"] < sd_med),
                   ("類股 ≥ 85% 同方向", lambda r: (r["breadth"] or 0) >= 0.85),
                   ("類股 < 60% 同方向", lambda r: (r["breadth"] or 1) < 0.6),
                   ("價差穩", lambda r: r["sdPct"] < sd_med), ("價差不穩", lambda r: r["sdPct"] >= sd_med)):
        print(f"  {lab}：{summ([r for r in rows if f(r)])}")
    print("\n價差收斂套利（09:15 進場、13:30 出場，損益點數未扣現貨成本；0050 當沖成本約 0.25%）")
    for th in (0.1, 0.2, 0.3, 0.5):
        for side, f in (("太大→空期多現", lambda r: r["devPct"] > th), ("太逆→多期空現", lambda r: r["devPct"] < -th)):
            g = [r for r in rows if f(r)]
            if not g:
                continue
            pnl = [(r["conv"] if r["dev"] > 0 else -r["conv"]) for r in g]
            pct = [p / r["px"] * 100 for p, r in zip(pnl, g)]
            print(f"  偏離 > {th}% {side}：n={len(g):3d} 平均收斂 {st.mean(pnl):+6.1f} 點（{st.mean(pct):+.3f}%）勝率 {sum(p > 0 for p in pnl) / len(pnl) * 100:.0f}%，扣 3 點期貨＋0.25% 現貨後 {st.mean(pct) - 0.25 - 3 / st.mean(r['px'] for r in g) * 100:+.3f}%")
    (DATA / "futures" / "basis_rows.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
