"""One-off: why did these golden-target threads produce zero chunks?"""
import json
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "reddit"

for tid in ("1id23zb", "zrddtr", "11qxad0", "1201al8", "120oe2i", "f04bg5", "isv7ru", "1cjf7c4", "16jk0xb", "th2m70"):
    d = json.loads((RAW / f"{tid}.json").read_text(encoding="utf-8"))
    print("=" * 70)
    print(tid, d["method"], "| comments:", len(d["comments"]))
    for c in d["comments"][:4]:
        body = (c.get("body") or "").replace("\n", " ")
        print(f"  score={c.get('score')} len={len(body)}: {body[:110]}")
