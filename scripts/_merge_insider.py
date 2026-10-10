"""暫時用：合併平行回補的結果（確認後刪除）。用法：python _merge_insider.py 分片目錄..."""
import json, sys, shutil
from pathlib import Path
dst = Path("data/insider")
for d in sys.argv[1:]:
    src = Path(d)
    for f in (src / "irb").glob("*.json"):
        if not (dst / "irb" / f.name).exists():
            shutil.copy(f, dst / "irb" / f.name)
    for f in (src / "co").glob("*.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        t = dst / "co" / f.name
        base = json.loads(t.read_text(encoding="utf-8")) if t.exists() else {"m": {}}
        for k, v in doc.items():
            if k != "m":
                base[k] = v
        base["m"].update(doc.get("m", {}))
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(json.dumps(base, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("merged", len(sys.argv) - 1)
