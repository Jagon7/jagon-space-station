"""暫時用：自結損益參數（確認後刪除）"""
import os, re, requests
os.makedirs("probe_out", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0 Safari/537.36"
OV = "https://mopsov.twse.com.tw/mops/web/ajax_t138sb01"
out = []
for i, data in enumerate([
    {"encodeURIComponent": "1", "firstin": "1", "step": "1", "first": "1", "CK1": "1", "CK2": "1", "YM1": "11508"},
    {"encodeURIComponent": "1", "firstin": "1", "step": "1", "first": "1", "CK1": "1", "CK2": "1", "YM1": "115/08"},
    {"encodeURIComponent": "1", "firstin": "1", "step": "1", "first": "1", "CK1": "2", "CK2": "1", "YM1": "11508"},
    {"encodeURIComponent": "1", "firstin": "1", "step": "1", "first": "1", "CK1": "1", "CK2": "3", "YM3": "11502"},
    {"encodeURIComponent": "1", "firstin": "1", "step": "1", "first": "1", "CK1": "1", "CK2": "1", "YM1": "11507"},
]):
    r = S.post(OV, data=data, headers={"Referer": "https://mopsov.twse.com.tw/mops/web/t138sb01"}, timeout=60)
    s = re.sub(r"<script.*?</script>", "", r.content.decode("utf-8", "replace"), flags=re.S)
    open(f"probe_out/a{i}.html", "w").write(s)
    t = re.sub(r"(&nbsp;|\s)+", " ", re.sub(r"<[^>]+>", " ", s))
    out.append(f"===== {data} {r.status_code} tr={s.count('<tr')}\n{t[:1500]}")
open("probe_out/summary.txt", "w").write("\n".join(out))
