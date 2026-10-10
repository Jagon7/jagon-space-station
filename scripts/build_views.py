#!/usr/bin/env python3
"""建置網站前產生前端用的靜態 JSON（public/data/），只用標準函式庫。"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_etf_views  # noqa: E402


def build_ranking():
    src, out = DATA_DIR / "ranking", ROOT / "public" / "data" / "ranking"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    dates = []
    for p in sorted(src.glob("*.json")):
        shutil.copy(p, out / p.name)
        dates.append(p.stem)
    (out / "index.json").write_text(json.dumps({"dates": dates}), encoding="utf-8")
    print(f"成交排行：{len(dates)} 天 → public/data/ranking")


def build_broker():
    """分點買賣超：每個分點一個檔（前端選分點才載入），index.json 列分點與日期。"""
    src, out = DATA_DIR / "broker", ROOT / "public" / "data" / "broker"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    days = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(src.glob("*.json"))]
    labels = []
    for d in days:
        for b in d["branches"]:
            if b not in labels:
                labels.append(b)
    dates = [d["date"] for d in days]
    for i, label in enumerate(labels):
        rows: dict[str, list] = {}
        names: dict[str, str] = {}
        for di, d in enumerate(days):
            for code, name, ba, sa, bs, ss in d["branches"].get(label, []):
                names[code] = name
                rows.setdefault(code, []).append([di, ba, sa, bs, ss])
        (out / f"{i}.json").write_text(json.dumps({"label": label, "dates": dates, "names": names, "rows": rows},
                                                  ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    covered = {label: [d["date"] for d in days if label in d["branches"]] for label in labels}
    (out / "index.json").write_text(json.dumps({"dates": dates, "branches": labels,
                                                "firstDate": {k: (v[0] if v else None) for k, v in covered.items()}},
                                               ensure_ascii=False), encoding="utf-8")
    print(f"分點：{len(labels)} 個分點、{len(dates)} 天 → public/data/broker")


INSIDER_CASE_MIN = 10_000_000   # 單月淨額至少 1000 萬才算進「歷史案例」
ROLE_ORDER = ["董事長", "副董事長", "總經理", "董事", "監察人", "大股東", "副總經理", "協理", "經理"]


def _role_rank(role: str) -> float:
    best = 99.0
    for r in role.split("、"):
        for i, k in enumerate(ROLE_ORDER):
            if r.startswith(k):
                best = min(best, i + (0.5 if ("配偶" in r or "他人" in r) else 0))
                break
    return best


def _who(rows: list, col: int) -> tuple[str, int]:
    """買（col=2）或賣（col=4）的人：職位最高者的職稱＋人數。"""
    ppl = [r for r in rows if r[col] > 0]
    if not ppl:
        return "", 0
    top = sorted(ppl, key=lambda r: (_role_rank(r[0]), -r[col]))[0]
    role = sorted(top[0].split("、"), key=_role_rank)[0]
    n = len({r[1] or r[0] for r in ppl})
    label = f"{role} 等 {n} 人" if n > 1 else (f"{role} {top[1]}" if top[1] and len(top[1]) <= 4 else role or top[1])
    return label, n


def _short_name(doc: dict, known: dict) -> str:
    code = doc.get("_code", "")
    if doc.get("a"):
        return doc["a"]
    if code in known:
        return known[code]
    n = doc.get("n") or code
    for suf in ("股份有限公司", "股份有限", "股份有", "股份"):
        if n.endswith(suf):
            return n[: -len(suf)]
    return n


def build_insider():
    """內部人持股異動 → public/data/insider/
    index.json：近期公告（事前申報轉讓、最新月異動）與歷史案例；<代號>.json：單一公司月別明細＋股價。
    金額 = 股數 × 當月平均收盤價（申報只有股數，沒有成交價）。"""
    src, out = DATA_DIR / "insider", ROOT / "public" / "data" / "insider"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    irb_months = sorted(p.stem for p in (src / "irb").glob("*.json"))
    latest = irb_months[-1] if irb_months else None

    # 簡稱：事前申報有簡稱；ETF 持股的股票名稱也是簡稱
    known: dict[str, str] = {}
    try:
        core = json.loads((ROOT / "public" / "data" / "etf" / "core.json").read_text(encoding="utf-8"))
        known.update({k: v for k, v in (core.get("names") or {}).items() if isinstance(v, str)})
    except (OSError, ValueError):
        pass
    transfers = []
    for p in sorted((src / "transfer").glob("*.json")):
        for r in json.loads(p.read_text(encoding="utf-8")):
            known[r[0]] = r[1]
            transfers.append([p.stem] + r)

    def load_px(code):
        f = src / "px" / f"{code}.json"
        return json.loads(f.read_text(encoding="utf-8"))["d"] if f.exists() else []

    cases, recent, names, last_close = [], [], {}, {}
    for p in sorted((src / "co").glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["_code"] = code = p.stem
        name = _short_name(doc, known)
        px = load_px(code)
        by_month: dict[str, list[float]] = {}
        for d, c in px:
            by_month.setdefault(d[:7], []).append(c)
        avg = {m: round(sum(v) / len(v), 2) for m, v in by_month.items()}
        months, stats = {}, []
        for ym, rows in sorted(doc.get("m", {}).items()):
            a = avg.get(ym)
            months[ym] = {"avg": a, "rows": rows}
            b, s = sum(r[2] for r in rows), sum(r[4] for r in rows)
            if b or s:
                stats.append((ym, b, s, a, rows))
        if not stats:
            continue
        names[code] = name
        if px:
            last_close[code] = px[-1][1]
        (out / p.name).write_text(json.dumps({"n": name, "mk": doc.get("mk"), "px": px, "m": months},
                                             ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        # 最新月異動
        for ym, b, s, a, rows in stats:
            if ym == latest:
                side = 1 if b >= s else -1
                who, n = _who(rows, 2 if side > 0 else 4)
                recent.append([code, name, b, s, round((b - s) * a) if a else None, a, who, n])

        # 歷史案例：同方向、金額夠大的連續月份（中間最多隔一個月）併成一個案例
        def mi(ym):
            return int(ym[:4]) * 12 + int(ym[5:]) - 1
        cur = None
        for ym, b, s, a, rows in stats:
            if not a:
                continue
            net = (b - s) * a
            if abs(net) < INSIDER_CASE_MIN:
                continue
            side = 1 if net > 0 else -1
            if cur and cur["side"] == side and mi(ym) - mi(cur["end"]) <= 2:
                cur["end"] = ym
                cur["net"] += net
                cur["sh"] += b - s
                cur["rows"] += rows
            else:
                if cur:
                    cases.append(cur)
                cur = {"code": code, "name": name, "side": side, "start": ym, "end": ym, "net": net, "sh": b - s, "rows": list(rows)}
        if cur:
            cases.append(cur)

    case_rows = []
    for c in cases:
        px = load_px(c["code"])
        avg_px = c["net"] / c["sh"] if c["sh"] else None
        who, n = _who(c["rows"], 2 if c["side"] > 0 else 4)
        # 案例結束後的股價表現：結束月底 → 3 個月後、→ 最新
        end_close = next((cl for d, cl in reversed(px) if d[:7] <= c["end"]), None)
        y, m = int(c["end"][:4]), int(c["end"][5:]) + 3
        after3_key = f"{y + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}"
        after3 = next((cl for d, cl in reversed(px) if d[:7] <= after3_key), None) if px and px[-1][0][:7] > after3_key else None
        now = px[-1][1] if px else None
        pct = (lambda a, b: round((b / a - 1) * 100, 1) if a and b else None)
        case_rows.append([c["code"], c["name"], c["side"], c["start"], c["end"], round(c["net"]),
                          round(avg_px, 2) if avg_px else None, who, n, pct(end_close, after3), pct(end_close, now)])
    case_rows.sort(key=lambda r: -abs(r[5]))

    for t in transfers:
        t.append(last_close.get(t[1]) or (load_px(t[1])[-1][1] if load_px(t[1]) else None))
    transfers.sort(key=lambda t: t[0], reverse=True)

    (out / "index.json").write_text(json.dumps({
        "latest": latest, "months": irb_months, "names": names,
        "recent": sorted(recent, key=lambda r: -abs(r[4] or 0)),
        "cases": case_rows,
        # [日期, 代號, 公司, 市場, 身分, 姓名, 方式, 一般交易股數, 每日上限, 受讓人, 目前持股, 預定轉讓, 轉讓後, 有效期間, 最新收盤]
        "transfers": transfers,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"內部人持股異動：{len(names)} 家、案例 {len(case_rows)}、事前申報 {len(transfers)} 筆、最新 {latest} → public/data/insider")


if __name__ == "__main__":
    build_etf_views.build()
    build_ranking()
    build_broker()
    build_insider()
