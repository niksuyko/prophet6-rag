import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
subs = {s["id"]: (s.get("num_comments") or 0) for s in
        (json.loads(l) for l in (ROOT / "data/raw/synthrecipes/submissions.jsonl")
         .read_text(encoding="utf-8").splitlines())}
full = [json.loads(l) for l in
        (ROOT / "data/processed/chunks_reddit.full.jsonl").read_text(encoding="utf-8").splitlines()]
sr = [c for c in full if c["source_id"] in subs]
ge3 = [c for c in sr if subs[c["source_id"]] >= 3]
sc3 = [c for c in ge3 if isinstance(c.get("score"), int) and c["score"] >= 3]
threads = len(set(c["source_id"] for c in ge3))

print("current live synthrecipes recipe lane (top-600): ~3,754 chunks")
print(f"all >=3-comment threads would yield: {len(ge3)} chunks from {threads} threads")
print(f"  of those, score>=3 (trustworthy): {len(sc3)}")
print(f"  recipe lane would grow ~3,754 -> {len(ge3)}  ({len(ge3)/3754:.1f}x)")
print(f"  (for comparison, the score-gated >=1 test that FAILED added 8,070; "
      f"v1 tripwire fell 0.902->0.829 at that volume)")
