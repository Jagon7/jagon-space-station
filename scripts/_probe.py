"""暫時用：探查基礎情報頁的資料來源（確認後刪除）"""
import json, os, re, requests
os.makedirs("probe_out", exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"
S = requests.Session(); S.headers["User-Agent"] = UA
def save(name, content):
    open(f"probe_out/{name}", "wb" if isinstance(content, bytes) else "w").write(content)
def tryget(name, url, **kw):
    try:
        r = S.get(url, timeout=60, **kw); save(name, r.content); print(name, r.status_code, len(r.content))
    except Exception as e: print(name, "ERR", e)
def trypost(name, url, data=None, json_=None, headers=None):
    try:
        r = S.post(url, data=data, json=json_, headers=headers or {}, timeout=60); save(name, r.content); print(name, r.status_code, len(r.content))
    except Exception as e: print(name, "ERR", e)
# 1. TWSE openapi 清單
tryget("twse_swagger.json", "https://openapi.twse.com.tw/v1/swagger.json")
# 2. MOPS 新版路由名稱
t = S.get("https://mops.twse.com.tw/mops/assets/index.js", timeout=60).text
routes = re.findall(r'path:`\$\{p\}/([\w]+)`,name:"([^"]+)"', t)
save("mops_routes.json", json.dumps(routes, ensure_ascii=False, indent=0))
print("routes", len(routes))
OV = "https://mopsov.twse.com.tw/"
# 3. 月營收（舊版靜態檔）
tryget("rev_sii.html", OV + "nas/t21/sii/t21sc03_115_9_0.html")
tryget("rev_otc.html", OV + "nas/t21/otc/t21sc03_115_9_0.html")
# 4. 綜合損益表彙總
base = {"encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1", "isQuery": "Y"}
trypost("t163sb04.html", OV + "mops/web/ajax_t163sb04", data={**base, "TYPEK": "sii", "year": "115", "season": "02"})
# 5. 庫藏股
trypost("t35sc09.html", OV + "mops/web/ajax_t35sc09", data={**base, "TYPEK": "sii", "d1": "1150901", "d2": "1151010", "RD": "1"})
# 6. 法說會
trypost("t100sb02_1.html", OV + "mops/web/ajax_t100sb02_1", data={**base, "TYPEK": "sii", "year": "115", "month": "10"})
# 7. 除權息預告
tryget("twt48u.json", "https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json")
# 8. openapi 最新月營收、EPS
tryget("t187ap05_L.json", "https://openapi.twse.com.tw/v1/opendata/t187ap05_L")
tryget("t187ap14_L.json", "https://openapi.twse.com.tw/v1/opendata/t187ap14_L")
