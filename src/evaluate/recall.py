"""Retrieval recall@k eval harness.

Usage: python src/evaluate/recall.py <run_label> [k] [mode] [golden_file]
For each golden query, retrieve top-k and check whether ANY expected target matches a
retrieved chunk (matching rules: decisions.md D-006). Writes a timestamped JSON to
eval/results/ and prints the per-bucket table. The human interprets the table; this
script never editorializes.

v2: optional 4th arg selects the golden file (default eval/golden_set.jsonl — the v1
41 queries, which double as the regression tripwire; pass eval/golden_set_v2.jsonl for
the v2 set).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
from search import retrieve  # noqa: E402

GOLDEN = ROOT / "eval" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"


def target_matches(chunk: dict, target: dict) -> bool:
    st, m = target["source_type"], target["match"]
    if chunk["source_type"] != st:
        return False
    if st == "manual":
        return m.lower() in (chunk.get("section") or "").lower()
    return chunk.get("source_id") == m


def query_hit(retrieved: list[dict], targets: list[dict]) -> dict | None:
    for chunk in retrieved:
        for t in targets:
            if target_matches(chunk, t):
                return {"chunk_id": chunk["chunk_id"], "target": t}
    return None


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "unlabeled"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    mode = sys.argv[3] if len(sys.argv) > 3 else "vector"
    golden_path = Path(sys.argv[4]) if len(sys.argv) > 4 else GOLDEN
    golden = [json.loads(l) for l in
              golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    per_query = []
    for entry in golden:
        retrieved = retrieve(entry["query"], k, mode=mode)
        hit = query_hit(retrieved, entry["expected_targets"])
        per_query.append({
            "id": entry["id"], "bucket": entry["bucket"], "hit": hit is not None,
            "matched": hit, "top_chunks": [c["chunk_id"] for c in retrieved],
        })
        print(("HIT " if hit else "MISS") + f" {entry['id']}: {entry['query'][:70]}")

    buckets = sorted({e["bucket"] for e in golden})
    table = {}
    for b in buckets:
        qs = [q for q in per_query if q["bucket"] == b]
        table[f"bucket_{b}"] = {"n": len(qs), "hits": sum(q["hit"] for q in qs),
                                "recall": round(sum(q["hit"] for q in qs) / len(qs), 3)}
    overall = round(sum(q["hit"] for q in per_query) / len(per_query), 3)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = {"run": label, "k": k, "mode": mode, "timestamp": ts, "overall_recall": overall,
           "per_bucket": table, "per_query": per_query}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{ts}_recall_{label}.json"
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"\nrecall@{k} ({label})")
    for name, row in table.items():
        print(f"  {name}: {row['hits']}/{row['n']} = {row['recall']}")
    print(f"  overall: {overall}")
    print(f"saved -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
