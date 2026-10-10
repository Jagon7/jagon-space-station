"""暫時用：試 MOPS 內部人持股異動事後申報 API 參數（確認後刪除）。"""
import json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36",
     "Content-Type": "application/json", "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/"}
BASE = "https://mops.twse.com.tw/mops/api/"
tries = [
    ("query6_1", {"companyId": "2330", "dataType": "1", "subsidiaryCompanyId": "", "year": "", "month": ""}),
    ("query6_1", {"companyId": "2330", "dataType": "2", "subsidiaryCompanyId": "", "year": "115", "month": "8"}),
    ("query6_1", {"companyId": "2330", "dataType": "2", "subsidiaryCompanyId": "", "year": "115", "month": "all"}),
    ("query6_1", {"companyId": "2330", "dataType": "2", "year": "115", "month": "08"}),
    ("query6_1", {"companyId": "2330", "dataType": 1}),
    ("redirectToIRB", {"marketKind": "sii", "year": "115", "month": "08", "fileNoOfIRB": "IRB110"}),
]
for api, body in tries:
    try:
        r = requests.post(BASE + api, headers=H, data=json.dumps(body), timeout=60)
        print("POST", api, body, r.status_code, r.text[:4000])
    except Exception as e:
        print("ERR", api, e)
    print()
