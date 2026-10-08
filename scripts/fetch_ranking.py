#!/usr/bin/env python3
"""
每日成交金額排行的原始資料：上市櫃個股與 ETF 當日收盤行情，一天一個檔。

輸出 JSS_DATA_DIR/ranking/<YYYY-MM-DD>.json（保留最近 KEEP_DAYS 個交易日）：
    {"date", "cols": [...], "rows": [[code, name, market, close, changePct, value, volume, sector]]}
族群取自同一次 fetch_data.py 產生的 sector-stocks.json。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_quotes as Q  # noqa: E402

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT_DIR = DATA_DIR / "ranking"
KEEP_DAYS = 20


def sector_map() -> dict[str, str]:
    try:
        doc = json.loads((DATA_DIR / "sector-stocks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {s["code"]: name for name, stocks in doc.get("data", {}).items() for s in stocks}


def main():
    day, quotes = Q.fetch_quotes()
    if not quotes:
        print("成交排行：證交所與櫃買都抓不到，略過")
        return 0
    if not any(q["market"] == "上市" for q in quotes):
        print("成交排行：缺上市資料，略過（避免存成不完整的一天）")
        return 0
    sectors = sector_map()
    rows = [[q["code"], q["name"], q["market"], q["close"], q["changePct"], q["value"], q["volume"],
             "ETF" if q["code"].startswith("00") else sectors.get(q["code"], "")]
            for q in quotes if q["value"]]
    rows.sort(key=lambda r: -r[5])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{day}.json").write_text(json.dumps(
        {"date": day, "cols": ["code", "name", "market", "close", "changePct", "value", "volume", "sector"], "rows": rows},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for old in sorted(OUT_DIR.glob("*.json"))[:-KEEP_DAYS]:
        old.unlink()
    print(f"成交排行：{day} 共 {len(rows)} 檔，成交金額 {sum(r[5] for r in rows) / 1e8:,.0f} 億")
    return 0


if __name__ == "__main__":
    sys.exit(main())
