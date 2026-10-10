"""暫時用：把 MOPS 內部人資料原始回應存下來（確認後刪除）。"""
import json, os, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36",
     "Content-Type": "application/json", "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/"}
os.makedirs("probe_out", exist_ok=True)
for co in ["2330", "2454", "3008", "6669"]:
    r = requests.post("https://mops.twse.com.tw/mops/api/query6_1", headers=H, timeout=60,
                      data=json.dumps({"companyId": co, "dataType": "2", "subsidiaryCompanyId": "", "year": "115", "month": "8"}))
    open(f"probe_out/q61_{co}.json", "wb").write(r.content)
for mk in ["sii", "otc"]:
    for f in ["IRB110", "IRB140", "IRB150"]:
        r = requests.post("https://mops.twse.com.tw/mops/api/redirectToIRB", headers=H, timeout=60,
                          data=json.dumps({"marketKind": mk, "year": "115", "month": "08", "fileNoOfIRB": f}))
        try:
            u = r.json()["result"]["url"]
        except Exception:
            print("no url", mk, f, r.text[:200]); continue
        b = requests.get(u, headers={"User-Agent": H["User-Agent"]}, timeout=60).content
        open(f"probe_out/{mk}_{f}.htm", "wb").write(b)
        print(mk, f, u, len(b))
# 內部人持股轉讓日報表（事前申報，有預定轉讓方式與價格?）
for api, body in [("t56sb21_q1", {"companyId": "2330", "year": "115", "month": "8"})]:
    r = requests.post("https://mops.twse.com.tw/mops/api/" + api, headers=H, timeout=60, data=json.dumps(body))
    open(f"probe_out/{api}.json", "wb").write(r.content)
