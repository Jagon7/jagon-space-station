"""暫時用：在 Actions 上找 MOPS 內部人持股異動的 API（確認後刪除）。"""
import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"}
BASE = "https://mops.twse.com.tw"
seen, queue, texts = set(), ["/mops/assets/index.js"], {}
while queue and len(seen) < 120:
    p = queue.pop()
    if p in seen:
        continue
    seen.add(p)
    try:
        t = requests.get(BASE + p, headers=H, timeout=60).text
    except Exception as e:
        print("ERR", p, e); continue
    texts[p] = t
    for m in re.findall(r'["\'`](\.{0,2}/?(?:mops/)?assets/[\w\-.]+\.js)["\'`]', t) + re.findall(r'["\'`]\./([\w\-.]+\.js)["\'`]', t):
        q = m if m.startswith("/mops/") else "/mops/assets/" + m.split("/")[-1]
        if q not in seen:
            queue.append(q)
print("files", len(texts), sum(len(t) for t in texts.values()))
for kw in ["持股異動", "事後申報", "轉讓事前", "持股餘額", "股權異動"]:
    n = 0
    for p, t in texts.items():
        for m in re.finditer(kw, t):
            print(kw, p, "::", t[max(0, m.start()-250):m.start()+150].replace("\n", " "))
            n += 1
            if n >= 6: break
        if n >= 6: break
