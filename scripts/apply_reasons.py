#!/usr/bin/env python3
"""
從 stdin 讀取 Claude 輸出的 JSON，把原因寫入 limit-up.json
用法：echo '{"3034":"原因"}' | python3 apply_reasons.py
"""
import json, re, sys, pathlib

text = sys.stdin.read().strip()
if not text:
    print("⚠ 沒有收到原因 JSON")
    sys.exit(0)

# 嘗試依序解析
reasons: dict[str, str] = {}
candidates = [
    text,
    re.sub(r"```(?:json)?\s*|\s*```", "", text).strip(),
]
m = re.search(r"\{[\s\S]+\}", text)
if m:
    candidates.append(m.group())

for c in candidates:
    try:
        reasons = json.loads(c)
        break
    except Exception:
        continue

if not reasons:
    print(f"⚠ 無法解析 JSON，原始輸出前 200 字：{text[:200]}")
    sys.exit(0)

p = pathlib.Path.home() / "Desktop/jagon-space-station/data/limit-up.json"
data = json.loads(p.read_text(encoding="utf-8"))
count = 0
for s in data["data"]:
    if s["code"] in reasons:
        s["reason"] = reasons[s["code"]]
        count += 1

p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✓ 已更新 {count} 檔漲停原因")
