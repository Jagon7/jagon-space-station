"""暫時用：探查自結損益、股東會日曆（確認後刪除）"""
import json, os, re, requests
os.makedirs("probe_out", exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"
S = requests.Session(); S.headers["User-Agent"] = UA
out = []
for f in ["t138sb01", "t138sb02_q1", "t138sb02_q2", "t108sb31new", "t100sb07_1"]:
    t = S.get(f"https://mops.twse.com.tw/mops/assets/{f}.js", timeout=60).text
    m = re.search(r"inputCode:.*?hideTheKey:\[[^\]]*\]", t, re.S)
    out.append(f"===== {f}\n{(m.group(0) if m else t[:2000])[:3000]}\n")
OV = "https://mopsov.twse.com.tw/mops/web/"
base = {"encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1", "isQuery": "Y"}
for name, api, data in [
    ("t138sb01_a", "ajax_t138sb01", {**base, "TYPEK": "sii", "year": "115", "month": "08"}),
    ("t138sb02_a", "ajax_t138sb02_q1", {**base, "TYPEK": "sii", "year": "115", "month": "08"}),
    ("t138sb02_b", "ajax_t138sb02", {**base, "TYPEK": "sii", "year": "115", "month": "08"}),
    ("t108sb31_a", "ajax_t108sb31new", {**base, "TYPEK": "sii", "year": "115", "month": "10"}),
]:
    try:
        r = S.post(OV + api, data=data, timeout=60)
        open(f"probe_out/{name}.html", "wb").write(r.content)
        out.append(f"{name} {r.status_code} {len(r.content)}")
    except Exception as e:
        out.append(f"{name} ERR {e}")
H = {"Content-Type": "application/json", "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/"}
for name, api, body in [
    ("api_t138sb02_q1", "t138sb02_q1", {"marketKind": "sii", "year": "115", "month": "8"}),
    ("api_t138sb01", "t138sb01", {"marketKind": "sii", "year": "115", "month": "8"}),
]:
    try:
        r = S.post("https://mops.twse.com.tw/mops/api/" + api, headers=H, data=json.dumps(body), timeout=60)
        open(f"probe_out/{name}.json", "wb").write(r.content)
        out.append(f"{name} {r.status_code} {r.text[:300]}")
    except Exception as e:
        out.append(f"{name} ERR {e}")
open("probe_out/summary.txt", "w").write("\n".join(out))
