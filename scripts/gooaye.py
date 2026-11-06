#!/usr/bin/env python3
"""
股癌（Gooaye）每集重點 → LINE

流程：抓 SoundOn RSS 最新一集 → 沒發過就下載音檔 → faster-whisper 語音轉文字 → Claude 整理重點與提到的個股
     → 台股個股對照網站的融資維持率、主動 ETF DD → LINE 卡片；重點存在 data/gooaye/<集數>.json（逐字稿不存）
發過的集數記在 data/notify/gooaye-sent.json
用法：python scripts/gooaye.py [--preview]（不管有沒有發過，重做最新一集並發預覽、不記錄）[--dry-run]
需要：pip install faster-whisper anthropic requests imageio-ffmpeg（或系統有 ffmpeg）；環境變數 ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from line_flex import FLAT, Msg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("JSS_DATA_DIR", ROOT / "data"))
FEED = "https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml"
APPLE = "https://podcasts.apple.com/tw/podcast/gooaye-%E8%82%A1%E7%99%8C/id1500839292"
STATE = DATA / "notify" / "gooaye-sent.json"
OUT = DATA / "gooaye"
MODEL = os.environ.get("GOOAYE_MODEL", "claude-sonnet-5-5")
WHISPER = os.environ.get("GOOAYE_WHISPER", "small")
PROMPT_HINT = "以下是台股、美股投資節目《股癌》的繁體中文逐字稿：台積電、輝達、聯發科、融資、ETF、財報、法說會、本益比。"
STANCE_COLOR = {"看多": "#E5484D", "偏多": "#E5484D", "看空": "#16A34A", "偏空": "#16A34A"}


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def latest() -> dict:
    r = requests.get(FEED, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    it = next(ET.fromstring(r.content).iter("item"))
    title = it.findtext("title") or ""
    m = re.match(r"\s*(EP\s*\d+)", title, re.I)
    dur = next((ch.text for ch in it if ch.tag.endswith("duration")), None)
    pub = parsedate_to_datetime(it.findtext("pubDate")) + timedelta(hours=8)
    return {"guid": it.findtext("guid") or title, "title": title.strip(), "ep": m.group(1).replace(" ", "").upper() if m else title[:12],
            "date": pub.strftime("%Y-%m-%d"), "time": pub.strftime("%H:%M"), "audio": it.find("enclosure").attrib["url"],
            "minutes": round(int(dur) / 60) if dur and dur.isdigit() else None, "link": it.findtext("link") or APPLE}


def transcribe(audio_url: str) -> str:
    import numpy as np
    from faster_whisper import WhisperModel
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = Path(tmp) / "ep.mp3"
        with requests.get(audio_url, stream=True, timeout=300, headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            with open(mp3, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        log(f"音檔 {mp3.stat().st_size / 1e6:.0f} MB，開始轉文字（{WHISPER}）")
        ff = shutil.which("ffmpeg")
        if not ff:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        pcm = subprocess.run([ff, "-v", "quiet", "-i", str(mp3), "-ar", "16000", "-ac", "1", "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    model = WhisperModel(WHISPER, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    t = time.time()
    segs, _ = model.transcribe(audio, language="zh", beam_size=1, vad_filter=True, initial_prompt=PROMPT_HINT)
    text = "".join(s.text for s in segs)
    log(f"轉文字完成：{len(text)} 字，{(time.time() - t) / 60:.1f} 分鐘")
    return text


SYSTEM = "你是台股投資研究助理，只輸出一個 JSON 物件，不加 markdown 或任何說明文字。"
ASK = """以下是投資 Podcast《股癌》{ep}（{date}）的語音辨識逐字稿。辨識有錯字（例如 Palantir 被聽成 Pentium、利空出盡被聽成力空出境），請依上下文修正股票名稱、英文術語。
節目通常前段是生活閒聊、中間有業配廣告（不要整理廣告）、後段是聽眾 QA。

請整理成 JSON，全部用繁體中文：
{{
  "headline": "一句話總結本集最重要的觀點（30 字內）",
  "market": ["盤勢觀點，3～5 點，每點 40 字內，保留具體數字"],
  "strategy": ["操作策略、部位與心態，2～4 點，每點 40 字內"],
  "stocks": [{{"name": "股票名稱", "code": "台股填 4～6 碼代號，美股填 ticker，不確定就空字串", "market": "台股或美股",
              "stance": "看多／偏多／中性／偏空／看空／僅提及 其中之一", "why": "他的理由，40 字內，保留數字"}}],
  "themes": ["產業或主題觀點，2～4 點，每點 40 字內"],
  "qa": ["聽眾問答重點，每題一句，最多 4 題"],
  "life": "開頭生活閒聊一句話（20 字內，沒有就空字串）"
}}
個股只列真的有討論的（不要列只是順口提到的），依討論份量排序，最多 10 檔；台股代號請盡量填正確。主持人立場以他自己的話為準，沒表態就填「中性」或「僅提及」。

逐字稿：
{text}"""


def summarize(ep: dict, text: str) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(model=MODEL, max_tokens=4000, system=SYSTEM,
                                  messages=[{"role": "user", "content": ASK.format(ep=ep["ep"], date=ep["date"], text=text)}])
    out = resp.content[0].text.strip()
    for cand in (out, re.sub(r"```(?:json)?\s*|\s*```", "", out), (re.search(r"\{[\s\S]+\}", out) or [None])[0]):
        try:
            return json.loads(cand)
        except (TypeError, ValueError):
            continue
    raise RuntimeError(f"Claude 回傳無法解析：{out[:300]}")


def tw_context() -> tuple[dict, dict, dict]:
    """(最新收盤 {代號: [名稱, 市場, ...]}, 融資 {代號: row}, 主動 ETF {代號: 彙總})"""
    import build_active_dd
    import build_margin
    daily = sorted((DATA / "daily").glob("20*.json"))
    q = json.loads(daily[-1].read_text(encoding="utf-8")).get("q", {}) if daily else {}
    mg, ad = {}, {}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            build_margin.build(DATA, Path(tmp))
            mg = {r["code"]: r for r in json.loads((Path(tmp) / "margin.json").read_text(encoding="utf-8"))["rows"]}
    except Exception as e:  # noqa: BLE001
        log("融資資料略過：", e)
    try:
        ad = {a["code"]: a for a in (build_active_dd.compute(DATA) or {}).get("stocks", [])}
    except Exception as e:  # noqa: BLE001
        log("主動 ETF 資料略過：", e)
    return q, mg, ad


def compose(ep: dict, s: dict, preview: bool) -> Msg:
    import notify
    q, mg, ad = tw_context()
    wl = set(notify.watchlist())
    sub = f"{int(ep['date'][5:7])}/{int(ep['date'][8:10])} {ep['time']}" + (f"・{ep['minutes']} 分鐘" if ep.get("minutes") else "")
    m = Msg(("【預覽】" if preview else "") + f"🎙️ 股癌 {ep['ep']} 重點", sub, accent="#8B5CF6", url=ep["link"], button="收聽這一集")
    if s.get("headline"):
        m.line(s["headline"], bold=True)
    for key, label in (("market", "盤勢觀點"), ("strategy", "操作策略")):
        if s.get(key):
            m.section(label)
            for x in s[key]:
                m.line(f"・{x}")
    stocks = s.get("stocks") or []
    if stocks:
        m.section("個股觀點", f"{len(stocks)} 檔")
        for x in stocks:
            code = (x.get("code") or "").strip().upper()
            name = x.get("name") or code
            extra = []
            if x.get("market") == "台股" and code in q:
                name = q[code][0] or name
                r = mg.get(code)
                if r:
                    extra.append(f"融資維持率 {r['maint']:.0f}%" + (f"（{int(r['force'][5:7])}/{int(r['force'][8:10])} 斷頭）" if r.get("force") else ""))
                a = ad.get(code)
                if a and a.get("warn"):
                    extra.append(f"主動 ETF {a['warn']}/{a['n']} 檔套 -30% 以下")
            why = x.get("why") or ""
            m.stock(name, code, "", x.get("stance") or "", color=STANCE_COLOR.get(x.get("stance") or "", FLAT), star=code in wl,
                    sub=why + ("｜" + "・".join(extra) if extra else ""))
    if s.get("themes"):
        m.section("產業主題")
        for x in s["themes"]:
            m.line(f"・{x}")
    if s.get("qa"):
        m.section("聽眾 QA")
        for x in s["qa"]:
            m.line(f"・{x}")
    m.note("AI 依節目語音轉文字後整理，可能有辨識錯誤；為主持人個人觀點，非投資建議。台股附上網站的推估融資維持率與主動 ETF 套牢狀況")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ep = latest()
    log(f"最新一集：{ep['title']}（{ep['date']} {ep['time']}）")
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"sent": []}
    if ep["guid"] in state["sent"] and not a.preview:
        log("這集已經發過")
        return 0
    cache = OUT / f"{ep['ep']}.json"
    doc = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
    if not doc or doc.get("guid") != ep["guid"]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            log("沒有設定 ANTHROPIC_API_KEY，無法整理重點")
            return 1
        text = transcribe(ep["audio"])
        s = summarize(ep, text)
        doc = {**{k: ep[k] for k in ("guid", "ep", "title", "date", "time", "minutes", "link")}, "summary": s}
        OUT.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    msg = compose(ep, doc["summary"], a.preview)
    print(msg.text())
    if a.dry_run:
        return 0
    import notify
    if not notify.send(msg):
        log("（沒有設定任何推播管道，只印出內容）")
    if not a.preview:
        state["sent"] = (state["sent"] + [ep["guid"]])[-50:]
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
