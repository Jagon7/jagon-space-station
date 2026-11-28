#!/usr/bin/env python3
"""
盤中「向上暫緩撮合」（瞬間價格穩定措施：試算價比前一筆漲 ≥ 3.5% → 暫停 2 分鐘再撮合）開出來後放空
資料：data/research/intraday_1m（1 分 K，2025/6 起，熱門股／策略日；樣本有偏差）
偵測（1 分 K 沒有暫緩撮合旗標，用形狀推）：
  前 10 分鐘每分鐘都有成交（流動性夠，排除處置股每 2／5 分鐘撮合一次）→ 接著 1～2 分鐘完全沒成交
  → 恢復那根開盤比停頓前最後收盤漲 ≥ 1.5%（試算漲 3.5% 才暫緩，2 分鐘後實際開出來常常縮小）
  09:05～13:00、恢復那根開盤還沒到漲停
進場：A 恢復那根開盤（暫緩期間掛單、跟著開出來那一筆成交）；B 再下一分鐘開盤
出場：13:25；停損：漲到前一天收盤 +7.5%（所有當沖策略共用）
分組：開出來漲幅（相對昨收）、時段、跳幅、當天後來有沒有漲停、開出來那根收黑／收紅
成本 0.23%；輸出 data/research/halt.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_intraday as ri  # noqa: E402
from build_strategy import tick  # noqa: E402,F401


JUMP = 1.5


def limit_bp(pc: float) -> int:
    return round((ri.tick_limit(pc) / pc - 1) * 1e4)


def main() -> int:
    bars = ri.load_bars()
    ev = []
    for d, stocks in sorted(bars.items()):
        for c, s in stocks.items():
            m, pc = s["m"], s["pc"]
            lim = limit_bp(pc)
            ts = sorted(m)
            for t in ts:
                if not (5 <= t <= 240) or t not in m:
                    continue
                if not all(k in m for k in range(t - 10, t + 1)):
                    continue
                nxt = next((k for k in ts if k > t), None)
                if nxt is None or not (2 <= nxt - t <= 3):
                    continue
                c0 = m[t][3]
                o1 = m[nxt][0]
                jump = ((1 + o1 / 1e4) / (1 + c0 / 1e4) - 1) * 100
                if jump < JUMP or o1 >= lim:
                    continue
                rA = ri.short_path(m, nxt)
                rB = ri.short_path(m, nxt + 1)
                if rA is None:
                    continue
                hi_after = max(b[1] for k, b in m.items() if k >= nxt)
                ev.append({"d": d, "code": c, "T": nxt, "jump": jump, "lvl": o1 / 100, "r": rA[0], "stopped": rA[1],
                           "rB": rB[0] if rB else None, "p15": rA[2].get(15), "p30": rA[2].get(30), "p60": rA[2].get(60),
                           "lim": hi_after >= lim, "red": m[nxt][3] > m[nxt][0], "black": m[nxt][3] < m[nxt][0],
                           "closeBelow": ri.px_at(m, ri.END) < o1})
                break   # 每檔每天只算第一次
    print(f"■ 向上暫緩撮合（推定）開出來放空：{len(ev)} 筆，碰 +7.5% 停損 {sum(e['stopped'] for e in ev) / max(len(ev), 1) * 100:.0f}%，"
          f"收盤低於開出價 {sum(e['closeBelow'] for e in ev) / max(len(ev), 1) * 100:.0f}%，當天後來漲停 {sum(e['lim'] for e in ev) / max(len(ev), 1) * 100:.0f}%")
    out = {"n": len(ev), "A": ri.report("A 開出來那一筆空、13:25 補", ev), "B": ri.report("B 再下一分鐘開盤空", ev, "rB")}
    groups = (("跳 ≥ 3.5%", lambda e: e["jump"] >= 3.5), ("跳 2～3.5%", lambda e: e["jump"] < 3.5),
              ("開出來時漲 < +3%", lambda e: e["lvl"] < 3), ("開出來時漲 +3～+6%", lambda e: 3 <= e["lvl"] < 6),
              ("開出來時漲 ≥ +6%", lambda e: e["lvl"] >= 6),
              ("09:30 前", lambda e: e["T"] < 30), ("09:30～11:00", lambda e: 30 <= e["T"] < 120), ("11:00 後", lambda e: e["T"] >= 120),
              ("開出來那根收黑", lambda e: e["black"]), ("開出來那根收紅", lambda e: e["red"]))
    for name, f in groups:
        sub = [e for e in ev if f(e)]
        out[name] = ri.report(name, sub)
        if sub:
            out[name + "B"] = ri.report(name + "（B）", sub, "rB")
    for h in ("p15", "p30", "p60"):
        xs = [e[h] for e in ev if e.get(h) is not None]
        if xs:
            print(f"    開出來後 {h[1:]} 分（未扣成本）：平均 {sum(xs) / len(xs):+.2f}%，賺錢 {sum(x > 0 for x in xs) / len(xs) * 100:.0f}%")
    (ri.DATA / "research" / "halt.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
