"""Yield audit for the >=1-comment expansion (D-033): how much USABLE content did it add,
and at what quality, before we commit to merge + reindex."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
reddit = [json.loads(l) for l in
          (ROOT / "data/processed/chunks_reddit.jsonl").read_text(encoding="utf-8").splitlines()]
sr_ids = {json.loads(l)["id"] for l in
          (ROOT / "data/raw/synthrecipes/submissions.jsonl").read_text(encoding="utf-8").splitlines()}

sr = [c for c in reddit if c["source_id"] in sr_ids]          # synthrecipes (the recipe corpus)
p6 = [c for c in reddit if c["source_id"] not in sr_ids]       # v1 P6-subreddit
print(f"total reddit chunks: {len(reddit)}  |  synthrecipes: {len(sr)}  P6-subreddit: {len(p6)}")


def dist(name, chunks):
    n = len(chunks)
    if not n:
        return
    sc = [c.get("score") for c in chunks]
    have = [s for s in sc if isinstance(s, int)]
    hi = sum(1 for s in have if s >= 3)
    low = sum(1 for s in have if s is not None and s < 3)
    none = sum(1 for s in sc if not isinstance(s, int))
    toks = [c["n_tokens"] for c in chunks]
    print(f"\n{name} ({n} chunks):")
    print(f"  score >=3 (trustworthy): {hi} ({100*hi/n:.0f}%)")
    print(f"  score <3:                {low} ({100*low/n:.0f}%)")
    print(f"  score missing (passed on length-fallback only): {none} ({100*none/n:.0f}%)")
    print(f"  median tokens: {sorted(toks)[n//2]}")
    uniq = len(set(c['source_id'] for c in chunks))
    print(f"  from {uniq} distinct threads ({n/uniq:.1f} chunks/thread)")


dist("synthrecipes (recipe corpus)", sr)
dist("P6-subreddit (v1)", p6)

# corpus composition if merged
others = {"patch": 766, "article": 607, "manual": 92, "official_kb": 12,
          "translation": 15, "video": 52}
total = len(reddit) + sum(others.values())
print(f"\nif merged, corpus ~= {total} chunks; reddit would be {100*len(reddit)/total:.0f}% of it")
print(f"  (before this wave reddit was 4689 of 6233 = 75%)")
