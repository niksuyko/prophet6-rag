"""Programmatic defect scan over all patch chunks (Phase B QA gate artifact, D-021
provisional). Catches systematic renderer bugs; a random 5 are printed for eyeballing."""
import random
import re

from common import PROCESSED_DIR, read_jsonl

chunks = read_jsonl(PROCESSED_DIR / "chunks_patches.jsonl")
defects = []
for c in chunks:
    t = c["text"]
    if re.search(r"(Oscillators|Mixer|Filters|Envelopes|Modulation):\s*[.;]?\s*(\n|$)", t):
        defects.append((c["chunk_id"], "empty section"))
    if "Mixer: ." in t or ": ;" in t or " ; " in t:
        defects.append((c["chunk_id"], "empty list artifact"))
    if c["n_tokens"] < 40:
        defects.append((c["chunk_id"], f"too short ({c['n_tokens']} tokens)"))
    if not c["section"]:
        defects.append((c["chunk_id"], "missing name"))
    if re.search(r"\b0 semitones apart", t):
        defects.append((c["chunk_id"], "zero-interval text"))
    if t.count("Category:") != 1:
        defects.append((c["chunk_id"], "category line count"))

print(f"{len(chunks)} chunks scanned, {len(defects)} defects")
for cid, why in defects[:20]:
    print(f"  {cid}: {why}")

rng = random.Random(7)
print("\n--- 5 random renderings for eyeball ---")
for c in rng.sample(chunks, 5):
    print("=" * 70)
    print(c["text"])
