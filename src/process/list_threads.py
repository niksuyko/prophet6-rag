"""One-off: list all fetched threads with comment counts, for golden-set repair."""
import json
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "reddit"

rows = []
for f in sorted(RAW.glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    title = (d["submission"].get("title") or d.get("title_hint") or "")[:75]
    nc = len(d.get("comments", []))
    good = sum(1 for c in d["comments"]
               if len((c.get("body") or "")) > 100)
    rows.append((d.get("bucket_hint"), d["id"], nc, good, title))

for hint in (1, 2, 3, 4, "t3", None):
    print(f"\n=== bucket_hint {hint} ===")
    for h, tid, nc, good, title in rows:
        if h == hint and good > 0:
            print(f"  {tid:9} c={nc:3} good={good:2} {title}")
