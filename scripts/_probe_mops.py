"""暫時用：看 IRB110 彙總表與 query6_1 欄位（確認後刪除）。"""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36",
     "Content-Type": "application/json", "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/"}
r = requests.post("https://mops.twse.com.tw/mops/api/query6_1", headers=H, timeout=60,
                  data=json.dumps({"companyId": "2330", "dataType": "2", "subsidiaryCompanyId": "", "year": "115", "month": "8"}))
res = r.json()["result"]
print("KEYS", list(res.keys()))
print("TITLES", json.dumps(res.get("titles"), ensure_ascii=False))
for mk in ["sii", "otc"]:
    u = f"https://siis.twse.com.tw/publish/{mk}/115IRB110_08.HTM"
    b = requests.get(u, headers={"User-Agent": H["User-Agent"]}, timeout=60).content
    print("=====", u, len(b), b[:200])
    for enc in ("utf-8", "cp950", "big5-hkscs"):
        try:
            s = b.decode(enc); print("enc", enc); break
        except UnicodeDecodeError:
            pass
    s = re.sub(r"[ \t\r]+", " ", s)
    print(s[:5000])
    print("...")
    print(s[len(s)//2: len(s)//2 + 3000])
    print("rows", s.count("<tr") + s.count("<TR"))
