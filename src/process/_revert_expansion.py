"""Revert the >=1-comment expansion (D-035 FAIL): rebuild the pre-expansion reddit chunk
set = v1 P6-subreddit threads + the top-600-by-engagement synthrecipes threads (the exact
selection fetch_synthrecipes_threads.py made before the experiment). Filters the backed-up
full set; does not refetch."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FULL = ROOT / "data" / "processed" / "chunks_reddit.full.jsonl"
OUT = ROOT / "data" / "processed" / "chunks_reddit.jsonl"
SUBS = ROOT / "data" / "raw" / "synthrecipes" / "submissions.jsonl"
GOLDEN_FILES = [ROOT / "eval" / "golden_set.jsonl", ROOT / "eval" / "golden_set_v2.jsonl"]

subs = [json.loads(l) for l in SUBS.read_text(encoding="utf-8").splitlines()]
sr_ids = {s["id"] for s in subs}

# replicate the pre-expansion selection: golden-targeted + top-600 by (score + 2*comments)
must = set()
for gf in GOLDEN_FILES:  # protect BOTH v1 and v2 golden reddit targets
    for line in gf.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        for t in json.loads(line).get("expected_targets", []):
            if t["source_type"] == "reddit":
                must.add(t["match"])
ranked = sorted((s for s in subs if (s.get("num_comments") or 0) >= 3),
                key=lambda s: -((s.get("score") or 0) + 2 * (s.get("num_comments") or 0)))
top600 = {s["id"] for s in ranked[:600]}
keep_sr = must | top600

full = [json.loads(l) for l in FULL.read_text(encoding="utf-8").splitlines()]
kept = [c for c in full
        if (c["source_id"] not in sr_ids)          # v1 P6-subreddit threads
        or (c["source_id"] in keep_sr)]            # pre-expansion synthrecipes selection
OUT.write_text("\n".join(json.dumps(c) for c in kept) + "\n", encoding="utf-8")
sr_kept = sum(1 for c in kept if c["source_id"] in sr_ids)
print(f"reverted reddit chunks: {len(kept)} ({sr_kept} synthrecipes top-600, "
      f"{len(kept) - sr_kept} P6-subreddit) from {len(full)} full")
