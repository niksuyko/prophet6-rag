import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
from search import stratified_hybrid_search, dedupe_by_source, _lane

GOLDEN = {g["id"]: g for g in
          (json.loads(l) for l in (ROOT / "eval" / "golden_set.jsonl")
           .read_text(encoding="utf-8").splitlines() if l.strip())}

for qid in ("b2-q04", "b3-q01", "b3-q09"):
    g = GOLDEN[qid]
    print(f"\n=== {qid}: {g['query'][:70]}")
    print(f"targets: {g['expected_targets']}")
    pool = stratified_hybrid_search(g["query"], k=40)
    pool = dedupe_by_source(pool)
    for rank, c in enumerate(pool[:30]):
        tgt = ""
        for t in g["expected_targets"]:
            m = t["match"].lower()
            if (t["source_type"] == c["source_type"]
                    and (m in (c.get("section") or "").lower()
                         if t["source_type"] == "manual" else c["source_id"] == t["match"])):
                tgt = "  <<< TARGET"
        print(f"{rank:>3} [{_lane(c):>15}] {c['chunk_id'][:55]}{tgt}")
