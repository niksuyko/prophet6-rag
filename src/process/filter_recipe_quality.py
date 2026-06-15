"""Option-B quality gate for the >=1-comment expansion (decisions.md D-035).

The full re-chunk produces ~23k synthrecipes Q+A chunks, 65% of them below our score
threshold (they passed only on the length fallback). The yield audit (D-035) showed that
merging all of them would make reddit 94% of the corpus and bury the structured content.
This gate keeps only the SCORE-QUALIFIED synthrecipes chunks (score >= 3) and leaves the
v1 P6-subreddit chunks untouched. Reversible: the full set is backed up to
chunks_reddit.full.jsonl, and re-running chunk_reddit.py regenerates it (then re-run this).

Usage: python -X utf8 src/process/filter_recipe_quality.py [min_score]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REDDIT = ROOT / "data" / "processed" / "chunks_reddit.jsonl"
BACKUP = ROOT / "data" / "processed" / "chunks_reddit.full.jsonl"
SUBS = ROOT / "data" / "raw" / "synthrecipes" / "submissions.jsonl"


def main() -> None:
    min_score = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    sr_ids = {json.loads(l)["id"] for l in SUBS.read_text(encoding="utf-8").splitlines()}
    chunks = [json.loads(l) for l in REDDIT.read_text(encoding="utf-8").splitlines()]
    if not BACKUP.exists():                      # preserve the full set once
        BACKUP.write_text("\n".join(json.dumps(c) for c in chunks) + "\n", encoding="utf-8")

    kept, dropped = [], 0
    for c in chunks:
        is_sr = c["source_id"] in sr_ids
        if is_sr and not (isinstance(c.get("score"), int) and c["score"] >= min_score):
            dropped += 1
            continue
        kept.append(c)
    REDDIT.write_text("\n".join(json.dumps(c) for c in kept) + "\n", encoding="utf-8")
    sr_kept = sum(1 for c in kept if c["source_id"] in sr_ids)
    print(f"recipe-quality gate (score >= {min_score} for synthrecipes):")
    print(f"  in:  {len(chunks)} reddit chunks")
    print(f"  out: {len(kept)} reddit chunks ({sr_kept} synthrecipes, "
          f"{len(kept) - sr_kept} P6-subreddit); dropped {dropped} low-score synthrecipes")
    print(f"  full set backed up -> {BACKUP.name}")


if __name__ == "__main__":
    main()
