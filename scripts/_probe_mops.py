"""暫時用：在 Actions 上找 MOPS 內部人持股異動的 API（確認後刪除）。"""
import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"}
r = requests.get("https://mops.twse.com.tw/mops/", headers=H, timeout=60)
print("index", r.status_code, len(r.text))
js = sorted(set(re.findall(r'(?:src|href)="([^"]+\.js)"', r.text)))
print(js)
for path in js:
    url = path if path.startswith("http") else "https://mops.twse.com.tw/mops/" + path.lstrip("./")
    t = requests.get(url, headers=H, timeout=60).text
    print("js", url, len(t))
    for kw in ["持股異動", "事後申報", "轉讓", "持股餘額"]:
        for m in re.finditer(kw, t):
            print(kw, "::", t[max(0, m.start()-200):m.start()+120].replace("\n", " "))
            break
