"""暫時用：找 MOPS 內部人持股異動事後申報的 API（確認後刪除）。"""
import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36",
     "Content-Type": "application/json", "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/"}
BASE = "https://mops.twse.com.tw"
for f in ["query6_1.js", "IRB110.js"]:
    t = requests.get(f"{BASE}/mops/assets/{f}", headers=H, timeout=60).text
    print("=====", f, len(t))
    print(t[:6000])
    for m in re.finditer(r"api|apiName|/web/|post\(|fetch", t):
        print("  >>", t[max(0, m.start()-200):m.start()+300].replace("\n", " "))
# 常見呼叫方式猜測
for path, body in [
    ("/mops/api/query6_1", {"companyId": "2330", "year": "115", "month": "9"}),
    ("/mops/api/query6_1", {"companyId": "2330", "dataType": "2", "year": "115", "month": "9"}),
    ("/mops/api/IRB110", {"year": "115", "month": "8", "marketKind": "sii"}),
]:
    try:
        r = requests.post(BASE + path, headers=H, data=json.dumps(body), timeout=60)
        print("POST", path, body, r.status_code, r.text[:3000])
    except Exception as e:
        print("ERR", path, e)
