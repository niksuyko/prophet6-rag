"""Draw a random sample of chunks for the mandatory human QA loop (plan Phase 2 step 5).

Usage: python src/process/sample_chunks.py [n] [seed]
Writes eval/chunk_qa_sample_<seed>.md — the human answers, per chunk:
"Would this passage make sense to a stranger with zero context?"
"""
import random
import sys

from common import CHUNKS_FILE, ROOT, read_jsonl


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    chunks = read_jsonl(CHUNKS_FILE)
    sample = random.Random(seed).sample(chunks, min(n, len(chunks)))
    out = ROOT / "eval" / f"chunk_qa_sample_{seed}.md"
    lines = [
        f"# Chunk QA sample (n={len(sample)}, seed={seed})",
        "",
        "For each chunk, mark PASS/FAIL on the stranger test: *would this passage make",
        "sense to someone with zero context?* Note the failure mode (truncated / missing",
        "context / boilerplate / garbage / wrong section label) on FAIL.",
        "",
    ]
    for i, c in enumerate(sample, 1):
        lines += [
            f"## {i}. `{c['chunk_id']}`",
            f"- source: {c['source_type']} | section: {c['section']} | score: {c['score']} "
            f"| tokens: {c['n_tokens']} | synths: {', '.join(c['synths_mentioned']) or '-'}",
            f"- url: {c['source_url']}",
            "- **verdict: [ ] PASS / [ ] FAIL — notes:**",
            "",
            "```",
            c["text"],
            "```",
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(sample)} chunks)")


if __name__ == "__main__":
    main()
