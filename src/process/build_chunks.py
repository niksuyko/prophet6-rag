"""Merge per-source chunk files, dedupe, and write the contract file data/chunks/chunks.jsonl.

Dedupe (decisions.md D-009): exact duplicates by normalized-text hash, then near-duplicates
by 8-gram shingle Jaccard > 0.85 within the same source_type (crossposted reddit answers,
re-published article passages). The higher-scored / earlier chunk wins.
"""
import hashlib
import re

from common import CHUNKS_FILE, PROCESSED_DIR, read_jsonl, write_jsonl

SOURCES = ["chunks_manual.jsonl", "chunks_reddit.jsonl", "chunks_articles.jsonl",
           "chunks_patches.jsonl", "chunks_translation.jsonl", "chunks_video.jsonl"]
JACCARD_THRESHOLD = 0.85


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower())


def shingles(text: str, n: int = 8) -> set:
    words = norm(text).split()
    return {" ".join(words[i:i + n]) for i in range(max(1, len(words) - n + 1))}


def main() -> None:
    chunks = []
    for name in SOURCES:
        path = PROCESSED_DIR / name
        if path.exists():
            rows = read_jsonl(path)
            chunks.extend(rows)
            print(f"{name}: {len(rows)}")
        else:
            print(f"{name}: MISSING, skipped")

    # exact dedupe: by chunk_id (pullpush can return the same comment twice, e.g.
    # pre-/post-edit copies whose text differs) and by normalized text
    seen, seen_ids, exact = {}, set(), 0
    deduped = []
    for c in sorted(chunks, key=lambda c: -(c.get("score") or 0)):
        h = hashlib.sha1(norm(c["text"]).encode()).hexdigest()
        if h in seen or c["chunk_id"] in seen_ids:
            exact += 1
            continue
        seen[h] = True
        seen_ids.add(c["chunk_id"])
        deduped.append(c)

    # near dedupe within source_type
    near_dropped = set()
    by_type: dict[str, list[int]] = {}
    sh = [shingles(c["text"]) for c in deduped]
    for i, c in enumerate(deduped):
        by_type.setdefault(c["source_type"], []).append(i)
    for idxs in by_type.values():
        for a in range(len(idxs)):
            i = idxs[a]
            if i in near_dropped or not sh[i]:
                continue
            for b in range(a + 1, len(idxs)):
                j = idxs[b]
                if j in near_dropped or not sh[j]:
                    continue
                if 0.5 < len(sh[i]) / max(len(sh[j]), 1) < 2.0:
                    inter = len(sh[i] & sh[j])
                    if inter / (len(sh[i]) + len(sh[j]) - inter) > JACCARD_THRESHOLD:
                        near_dropped.add(j)

    final = [c for k, c in enumerate(deduped) if k not in near_dropped]
    # stable order: by source then id, so diffs between runs are meaningful
    final.sort(key=lambda c: (c["source_type"], c["chunk_id"]))
    write_jsonl(CHUNKS_FILE, final)

    counts = {}
    for c in final:
        counts[c["source_type"]] = counts.get(c["source_type"], 0) + 1
    print(f"\ndropped: {exact} exact dupes, {len(near_dropped)} near dupes")
    print(f"chunks.jsonl: {len(final)} chunks {counts}")


if __name__ == "__main__":
    main()
