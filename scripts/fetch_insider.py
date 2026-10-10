#!/usr/bin/env python3
"""
內部人（董監事、經理人、大股東）持股異動：每月每人買賣多少股，給「內部人持股異動」頁畫圖。

資料來源（公開資訊觀測站，GitHub Actions 上才連得到）：
  1. IRB110「董事、監察人、經理人及百分之十以上大股東股權異動彙總表」：每月一份、全市場每家公司一列
     （董監增加/減少股數、經理人與大股東持股）。用來挑出「這個月內部人有異動」的公司，
     沒異動的公司就不用逐家查。
  2. query6_1「內部人持股異動事後申報表」：單一公司、單一月份，每位內部人
     本月增加/減少（集中市場、其它原因）與月底持股。
  3. 「持股轉讓日報表」（事前申報）：內部人預定轉讓（一般交易、洽特定人、贈與、信託…），每天一份。
  4. 股價（畫圖、估算金額用）：Yahoo Finance 日線。

申報期限是次月 15 日前，所以最新只到上個月（甚至上上個月）。
每次執行：先補最新月份，再往回補到 MONTHS 個月前，查過的不重查；有時間上限，沒補完的下次接著補。

輸出 JSS_DATA_DIR/insider/：
  irb/<YYYY-MM>.json   {代號: [名稱, 市場, 董監增加, 董監減少, 經理人持股, 大股東持股]}
  transfer/<YYYY-MM-DD>.json  [[代號, 公司, 市場, 身分, 姓名, 轉讓方式, 一般交易股數, 每日上限, 受讓人, 目前持股, 預定轉讓股數, 轉讓後持股, 有效期間], ...]
  co/<代號>.json       {"n": 名稱, "a": 簡稱, "mk": sii|otc, "m": {"YYYY-MM": [[身分, 姓名, 集中買, 其它增, 集中賣, 其它減, 月底持股], ...]}}
                       （該月查過但沒有人異動 → 空陣列）
  px/<代號>.json       {"t": 抓取日, "d": [[YYYY-MM-DD, 收盤], ...]}  近 2 年
用法：python scripts/fetch_insider.py [--months 24] [--minutes 25] [代號 ...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "insider"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
API = "https://mops.twse.com.tw/mops/api/"
MONTHS = 24
DELAY = 0.6
PRICE_REFRESH_DAYS = 3

S = requests.Session()
S.headers.update({"User-Agent": UA})
JH = {"Content-Type": "application/json", "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/"}


def log(msg: str):
    print(f"[{datetime.now(TPE):%H:%M:%S}] {msg}", flush=True)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def post(api: str, body: dict) -> dict:
    for i in range(4):
        try:
            r = S.post(API + api, headers=JH, data=json.dumps(body), timeout=60)
            if r.status_code == 200 and r.text.startswith("{"):
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"{api} {body} 查詢失敗")


def num(s: str) -> int:
    s = s.replace(",", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return 0


# ---------- IRB110 全市場彙總 ----------

def fetch_irb(ym: str) -> dict | None:
    """→ {代號: [名稱, 市場, 董監增加, 董監減少, 經理人持股, 大股東持股]}；該月還沒公布回 None。"""
    y, m = int(ym[:4]) - 1911, ym[5:]
    out = {}
    for mk in ("sii", "otc"):
        res = post("redirectToIRB", {"marketKind": mk, "year": str(y), "month": m, "fileNoOfIRB": "IRB110"})
        url = (res.get("result") or {}).get("url") if res.get("code") == 200 else None
        if not url:
            return None
        r = S.get(url, timeout=60)
        page = r.content.decode("big5hkscs", errors="replace")
        rows = re.findall(r"<TR><TD>([0-9A-Z]{4,6})(.*?)</TD>(.*?)</TR>", page, re.S)
        if r.status_code != 200 or not rows:
            return None
        for code, name, rest in rows:
            v = [num(x) for x in re.findall(r"ALIGN=RIGHT>\s*([\d,.\-]+)", rest)]
            if len(v) >= 7:
                # 實收資本額, 董監增加, 董監減少, 董監持股, 持股%, 經理人持股, 大股東持股
                out[code] = [name.strip(), mk, v[1], v[2], v[5], v[6]]
        time.sleep(DELAY)
    return out


# ---------- query6_1 單一公司 ----------

ROLE_SHORT = [("本人之配偶及未成年子女", "配偶"), ("之配偶及未成年子女", "配偶"), ("利用他人名義持有者", "他人名義"), ("本人", "")]


def short_role(s: str) -> str:
    for a, b in ROLE_SHORT:
        s = s.replace(a, b)
    return s


def fetch_company(code: str, ym: str) -> tuple[list, str] | None:
    y, m = int(ym[:4]) - 1911, int(ym[5:])
    res = post("query6_1", {"companyId": code, "dataType": "2", "subsidiaryCompanyId": "", "year": str(y), "month": str(m)})
    if res.get("code") != 200 or not res.get("result"):
        return None
    rows: dict[tuple, list] = {}
    for d in res["result"].get("data") or []:
        if len(d) < 19 or d[2] != "普通股":
            continue
        # 0 身分 1 姓名 2 種類 3 選任時 4 上月持股 5~7 信託/設質/私募
        # 8~12 本月增加：集中、其它、私募、信託、設質；13~17 本月減少：集中、其它、私募、信託、解質；18 本月持股
        bm, bo, sm, so, hold = num(d[8]), num(d[9]), num(d[13]), num(d[14]), num(d[18])
        if not (bm or bo or sm or so):
            continue
        role, name = short_role(d[0].strip()), d[1].strip()
        key = (name or role, bm, bo, sm, so, hold)  # 同一人兼多職會重複列，合併身分
        if key in rows:
            if role not in rows[key][0].split("、"):
                rows[key][0] += "、" + role
        else:
            rows[key] = [role, name, bm, bo, sm, so, hold]
    return list(rows.values()), (res["result"].get("companyAbbreviation") or "").strip()


# ---------- 持股轉讓日報表（事前申報） ----------

OV = "https://mopsov.twse.com.tw/mops/web/"
TRANSFER_DAYS = 120


def fetch_transfers(day: date) -> list:
    out = []
    y, m, d = day.year - 1911, f"{day.month:02d}", f"{day.day:02d}"
    for report, mk in (("SY", "sii"), ("OY", "otc")):
        r = None
        for i in range(3):
            try:
                r = S.post(OV + "ajax_t56sb12", timeout=60, headers={"Referer": OV + "t56sb12_q1"},
                           data={"step": "2", "year": str(y), "month": m, "day": d, "report": report, "firstin": "true"})
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(5 * (i + 1))
        if r is None or r.status_code != 200:
            raise RuntimeError(f"轉讓日報表 {day} {report} 查詢失敗")
        page = r.content.decode("utf-8", errors="replace")
        if "hasBorder" not in page and "查無" not in page and "無資料" not in page:
            raise RuntimeError(f"轉讓日報表 {day} {report} 格式不符")
        for tr in re.findall(r"<tr class='(?:odd|even)'>(.*?)</tr>", page, re.S):
            cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip() for c in re.split(r"<td[^>]*>", tr)[1:]]
            cells = [re.sub(r"\s+", " ", c) for c in cells]
            if len(cells) < 17 or not re.fullmatch(r"[0-9A-Z]{4,6}", cells[2]):
                continue
            out.append([cells[2], cells[3], mk, cells[4], cells[5], cells[6], num(cells[7]), num(cells[8]), cells[9],
                        num(cells[10]), num(cells[12]), num(cells[14]), cells[16].replace(" ", "")])
        time.sleep(DELAY)
    return out


# ---------- 股價 ----------

def fetch_price(code: str, mk: str) -> list | None:
    sym = f"{code}.{'TW' if mk == 'sii' else 'TWO'}"
    for host in ("query1", "query2"):
        try:
            r = S.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                      params={"range": "2y", "interval": "1d"}, timeout=30)
            res = r.json()["chart"]["result"][0]
            ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
            return [[datetime.fromtimestamp(t, TPE).date().isoformat(), round(c, 2)] for t, c in zip(ts, cl) if c]
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return None


def month_list(n: int) -> list[str]:
    d = datetime.now(TPE).date().replace(day=1)
    out = []
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
        out.append(d.strftime("%Y-%m"))
    return out  # 新到舊，從上個月開始


def prev_month(ym: str) -> str:
    d = date(int(ym[:4]), int(ym[5:]), 1) - timedelta(days=1)
    return d.strftime("%Y-%m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--months", type=int, default=MONTHS)
    ap.add_argument("--minutes", type=float, default=25)
    a = ap.parse_args()
    deadline = time.time() + a.minutes * 60

    # 1. 每月彙總表：最近 2 個月每次重抓（可能還在更新），更早的抓過就不重抓
    months = month_list(a.months + 1)
    irb: dict[str, dict] = {}
    for i, ym in enumerate(months):
        path = OUT / "irb" / f"{ym}.json"
        cached = read_json(path, None)
        if cached is not None and i >= 2:
            irb[ym] = cached
            continue
        try:
            doc = fetch_irb(ym)
        except RuntimeError as e:
            log(f"✗ {ym} 彙總表：{e}")
            doc = None
        if doc:
            write_json(path, doc)
            irb[ym] = doc
        elif cached is not None:
            irb[ym] = cached
    avail = [ym for ym in months[:a.months] if ym in irb]
    log(f"彙總表：{len(avail)} 個月（最新 {avail[0] if avail else '—'}）")

    # 2. 有異動的公司逐家查
    cos: dict[str, dict] = {}

    def co(code: str) -> dict:
        if code not in cos:
            cos[code] = read_json(OUT / "co" / f"{code}.json", {"m": {}})
        return cos[code]

    todo = []
    for ym in avail:
        cur, prev = irb[ym], irb.get(prev_month(ym))
        for code, (name, mk, inc, dec, mgr, big) in cur.items():
            if a.codes and code not in a.codes:
                continue
            p = prev.get(code) if prev else None
            if inc or dec or p is None or p[4] != mgr or p[5] != big:
                if ym not in co(code)["m"]:
                    todo.append((ym, code, name, mk))
    log(f"待查：{len(todo)} 筆（公司×月）")
    done = 0
    dirty = set()
    for ym, code, name, mk in todo:
        if time.time() > deadline:
            break
        try:
            rows = fetch_company(code, ym)
        except RuntimeError as e:
            log(f"✗ {code} {ym}：{e}")
            continue
        finally:
            time.sleep(DELAY)
        if rows is None:
            continue
        rows, abbr = rows
        doc = co(code)
        doc["n"], doc["mk"] = name, mk
        if abbr:
            doc["a"] = abbr
        doc["m"][ym] = rows
        dirty.add(code)
        done += 1
        if done % 200 == 0:
            for c in dirty:
                write_json(OUT / "co" / f"{c}.json", cos[c])
            dirty.clear()
            log(f"  已查 {done}/{len(todo)}")
    for c in dirty:
        write_json(OUT / "co" / f"{c}.json", cos[c])
    log(f"本次查了 {done} 筆，剩 {len(todo) - done} 筆")

    # 3. 持股轉讓事前申報：最近 TRANSFER_DAYS 天每個平日一份，最近 3 天每次重抓
    today = datetime.now(TPE).date()
    tdir = OUT / "transfer"
    n_t = 0
    for i in range(TRANSFER_DAYS):
        day = today - timedelta(days=i)
        path = tdir / f"{day.isoformat()}.json"
        if day.weekday() >= 5 or (path.exists() and i >= 3):
            continue
        if time.time() > deadline + 600:
            break
        try:
            rows = fetch_transfers(day)
        except RuntimeError as e:
            log(f"✗ {e}")
            continue
        write_json(path, rows)
        n_t += 1
    for old in sorted(tdir.glob("*.json"))[:-TRANSFER_DAYS]:
        old.unlink()
    log(f"轉讓事前申報：更新 {n_t} 天")

    # 4. 股價：有集中市場買賣、或最近有事前申報的公司
    want: dict[str, str] = {}
    for p in sorted((OUT / "co").glob("*.json")):
        doc = read_json(p, {})
        if any(r[2] or r[4] for rows in doc.get("m", {}).values() for r in rows):
            want[p.stem] = doc.get("mk", "sii")
    for p in tdir.glob("*.json"):
        for r in read_json(p, []):
            want.setdefault(r[0], r[2])
    n_px = 0
    for code, mk in sorted(want.items()):
        if time.time() > deadline + 900:
            break
        pp = OUT / "px" / f"{code}.json"
        old = read_json(pp, None)
        if old and (today - date.fromisoformat(old["t"])).days < PRICE_REFRESH_DAYS:
            continue
        px = fetch_price(code, mk)
        if px:
            write_json(pp, {"t": today.isoformat(), "d": px})
            n_px += 1
        time.sleep(0.3)
    log(f"股價更新 {n_px} 檔（共 {len(want)} 檔）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
