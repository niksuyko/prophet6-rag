import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
from search import retrieve

q = "Patch similar to Nangs by Tame Impala"
for c in retrieve(q, 8, mode="strat+div"):
    print(f"[{c['source_type']:>12}] {c['chunk_id'][:60]}")
    print("   ", c["text"][:200].replace("\n", " "))

# also: does the corpus mention Nangs / Tame Impala at all, and what do those
# chunks say about LFO rate/amount specifically?
print("\n--- corpus chunks mentioning nangs/tame impala ---")
hits = 0
for line in (ROOT / "data/chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines():
    c = json.loads(line)
    t = c["text"].lower()
    if "nangs" in t or "tame impala" in t:
        hits += 1
        if hits <= 6:
            print(f"[{c['source_type']:>12}] {c['chunk_id'][:60]}")
            for kw in ("lfo", "rate", "wobble", "filter mod", "hz", "amount", "speed"):
                idx = t.find(kw)
                if idx >= 0:
                    print(f"     …{c['text'][max(0,idx-60):idx+90]!r}")
                    break
print(f"total mentions: {hits}")
