"""Does the >=1 expansion actually carry more relevant content for a query like
'Nangs by Tame Impala'? Compare full set vs the current (reverted) live corpus."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
full = [json.loads(l) for l in
        (ROOT / "data/processed/chunks_reddit.full.jsonl").read_text(encoding="utf-8").splitlines()]
live_ids = {json.loads(l)["source_id"] for l in
            (ROOT / "data/chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines()}

pat = re.compile(r"tame impala|nangs|kevin parker|let it happen|borderline", re.I)
hits = [c for c in full if pat.search(c["text"])]
threads = {}
for c in hits:
    threads.setdefault(c["source_id"], []).append(c)

print(f"chunks mentioning Tame Impala / Nangs etc. in the FULL expanded set: {len(hits)} "
      f"across {len(threads)} threads")
in_live = sum(1 for t in threads if t in live_ids)
print(f"  threads already in the CURRENT live corpus: {in_live}")
print(f"  threads ONLY in the expansion (lost on revert): {len(threads) - in_live}")
print("\nper thread (id | #chunks | in live? | best score | sample):")
for tid, cs in sorted(threads.items(), key=lambda kv: -len(kv[1])):
    sc = max((c.get("score") or -99) for c in cs)
    samp = next((c["text"] for c in cs), "")[:70].replace("\n", " ")
    print(f"  {tid} | {len(cs):>2} | {'LIVE' if tid in live_ids else 'expansion-only':>14} "
          f"| score {sc:>4} | {samp}")
