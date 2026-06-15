"""Provenance-ratio probe (v2 success criterion 2): across a fixed query sample, what
fraction of patch-designer changes cite corpus sources (patch/manual/reddit/article/
video/translation badges) vs "general synthesis"?

Usage: python -X utf8 src/evaluate/provenance_probe.py <label> [n] [golden_file]
Requires ANTHROPIC_API_KEY. Reuses each generation's change list only (no judging).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "ui"))
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
import load_env  # noqa: E402,F401


def classify(source: str) -> str:
    s = source.lower()
    for tag in ("patch", "manual", "reddit", "article", "video", "translation",
                "official_kb"):
        if s.startswith(tag):
            return tag
    return "general"


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "v2"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    golden_path = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "eval" / "golden_set_v2.jsonl"
    from generate_patch import generate_patch

    golden = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines()
              if l.strip()]
    queries = [g for g in golden if g["bucket"] in (2, 3)][:n]
    counts: dict[str, int] = {}
    per_query = []
    for i, g in enumerate(queries, 1):
        try:
            res = generate_patch(g["query"])
        except Exception as e:
            print(f"{g['id']}: failed ({e})")
            continue
        tags = [classify(c["source"]) for c in res["changes"]]
        for t in tags:
            counts[t] = counts.get(t, 0) + 1
        cited = sum(1 for t in tags if t != "general")
        per_query.append({"id": g["id"], "n_changes": len(tags), "cited": cited})
        print(f"[{i}/{len(queries)}] {g['id']}: {cited}/{len(tags)} cited", flush=True)

    total = sum(counts.values())
    cited_total = total - counts.get("general", 0)
    ratio = round(cited_total / total, 3) if total else None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = {"run": label, "timestamp": ts, "n_queries": len(per_query),
           "total_changes": total, "cited": cited_total, "cited_ratio": ratio,
           "by_source": counts, "per_query": per_query}
    path = ROOT / "eval" / "results" / f"{ts}_provenance_{label}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\ncited ratio: {ratio} ({cited_total}/{total})  by source: {counts}")
    print(f"saved -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
