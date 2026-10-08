#!/usr/bin/env python3
"""
個股產業細分類：櫃買中心「產業價值鏈資訊平台」ic.tpex.org.tw。

每個產業（約 47 個）分上／中／下游 → 類別（例：IC設計）→ 細類（例：電源管理IC），
各列出上市、上櫃、興櫃公司；一檔股票可以屬於多個細類。

輸出 JSS_DATA_DIR/industry/chain.json：
    {"updatedAt", "industries": [{"id", "name", "nodes": [{"id", "name", "stream", "subs": [{"id", "name", "codes"}]}]}],
     "names": {code: name}}
沒有細類的類別，subs 只有一個與類別同名的項目。
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.environ.get("JSS_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUT = DATA_DIR / "industry" / "chain.json"
IC = "https://ic.tpex.org.tw/introduce.php"
TPE = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def text(s: str) -> str:
    return re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", s or "")))


def get(ind_id: str) -> str:
    for i in range(3):
        try:
            r = requests.get(IC, params={"ic": ind_id}, headers={"User-Agent": UA}, timeout=60)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"{ind_id} 抓取失敗")


def parse(page: str, names: dict[str, str]) -> list[dict]:
    # 類別在鏈圖中出現於哪個「上游／中游／下游」標題之後
    stream, cur = {}, ""
    for m in re.finditer(r'chain-title-panel">\s*([^<]+?)\s*<|id="ic_link_(\w+)"', page):
        if m.group(1):
            cur = m.group(1).strip()
        else:
            stream.setdefault(m.group(2), cur)
    sub_names = {k: re.sub(r"\(\d+家\)$", "", text(v)).lstrip("►▶")
                 for k, v in re.findall(r'id="sc_link_(\w+)"[^>]*>(.*?)</div>', page, re.S)}

    nodes = []
    for block in re.split(r'(?=<div id="companyList_)', page)[1:]:
        m = re.match(r'<div id="companyList_(\w+)" title="([^"]*)"', block)
        if not m:
            continue
        node_id, node_name = m.group(1), text(m.group(2))
        if any(n["id"] == node_id for n in nodes):  # 頁面上同一類別會出現兩次（不同版面）
            continue
        subs: dict[str, list[str]] = {}
        for part in re.split(r'(?=<table id="sc_company_)', block):
            tm = re.match(r'<table id="sc_company_(\w+)"', part)
            sid = tm.group(1) if tm else ""
            if sid.startswith("count_"):
                continue
            for code, name in re.findall(r'company_basic\.php\?stk_code=(\w+)"[^>]*title="([^"]*)"', part):
                names.setdefault(code, html.unescape(name).strip())
                lst = subs.setdefault(sid, [])
                if code not in lst:
                    lst.append(code)
        # 有細類時，類別本身那張表是全部公司的彙總，只保留沒被細類涵蓋的
        covered = {c for sid, cs in subs.items() if sid for c in cs}
        rest = [c for c in subs.get("", []) if c not in covered]
        out_subs = [{"id": sid, "name": sub_names.get(sid, sid), "codes": cs} for sid, cs in subs.items() if sid and cs]
        if rest:
            out_subs.insert(0, {"id": node_id, "name": node_name if not out_subs else f"{node_name}（其他）", "codes": rest})
        if out_subs:
            nodes.append({"id": node_id, "name": node_name, "stream": stream.get(node_id, ""), "subs": out_subs})
    return nodes


def main():
    first = get("D000")
    inds = []
    for v, name in re.findall(r"<option value='(\w+)'[^>]*>([^<]+)</option>", first):
        if v not in [i for i, _ in inds]:
            inds.append((v, name.strip()))
    names: dict[str, str] = {}
    industries, errors = [], []
    for ind_id, ind_name in inds:
        try:
            nodes = parse(first if ind_id == "D000" else get(ind_id), names)
            if nodes:
                industries.append({"id": ind_id, "name": ind_name, "nodes": nodes})
            else:
                errors.append(ind_name)
        except RuntimeError as e:
            errors.append(f"{ind_name}：{e}")
        time.sleep(0.8)
    n_subs = sum(len(n["subs"]) for i in industries for n in i["nodes"])
    if len(industries) < 30 or n_subs < 200:
        print(f"產業鏈只抓到 {len(industries)} 個產業、{n_subs} 個細類，保留上次結果")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updatedAt": datetime.now(TPE).strftime("%Y-%m-%d"), "industries": industries,
                               "names": names}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"產業鏈：{len(industries)} 個產業、{n_subs} 個細類、{len(names)} 檔公司"
          + (f"；失敗：{'、'.join(errors)}" if errors else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
