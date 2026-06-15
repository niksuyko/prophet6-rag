"""Faithfulness eval: LLM-as-judge, claim-level (decisions.md D-013).

Usage: python src/evaluate/faithfulness.py <run_label> [--mode hybrid] [--k 5]
For each golden query: generate a RAG answer, then a judge labels every factual claim
supported / unsupported / contradicted by the retrieved chunks. Writes per-query verdicts
to eval/results/ and a 15-verdict spot-check file for mandatory human validation.
"""
import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "generate"))
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
from ask import DEFAULT_MODEL, answer, build_context  # noqa: E402

GOLDEN = ROOT / "eval" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
SPOTCHECK_N = 15

JUDGE_SYSTEM = """You are a strict fact-checking judge. You receive context chunks, a question,
and an answer that was supposed to be written ONLY from those chunks.

Extract every factual claim from the answer (a claim = a checkable statement about the
synth, a procedure, a parameter, another instrument, or community experience). For each
claim, label it:
- "supported": directly backed by a chunk
- "unsupported": not present in any chunk
- "contradicted": a chunk says otherwise

If the answer is a refusal ("corpus doesn't cover this") with no factual claims, return an
empty claims list. Respond with JSON only:
{"claims": [{"claim": "...", "verdict": "supported|unsupported|contradicted", "evidence": "chunk label or null"}]}"""


def judge_answer(client, model, question, chunks, answer_text) -> dict:
    msg = client.messages.create(
        model=model, max_tokens=2000, temperature=0,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content":
                   f"Context chunks:\n\n{build_context(chunks)}\n\n"
                   f"Question: {question}\n\nAnswer to check:\n{answer_text}\n\nJSON:"}])
    text = msg.content[0].text.strip()
    text = text[text.find("{"):text.rfind("}") + 1]
    return json.loads(text)


def main() -> None:
    import anthropic
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--golden", default=None)
    ap.add_argument("--mode", default="hybrid+div")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    client = anthropic.Anthropic()
    golden_path = Path(args.golden) if args.golden else GOLDEN  # v2: optional golden file
    golden = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    results = []
    for entry in golden:
        ans, chunks = answer(entry["query"], args.mode, args.k, args.model)
        verdict = None
        for _attempt in range(2):  # v2: judge JSON occasionally malformed — retry once
            try:
                verdict = judge_answer(client, args.model, entry["query"], chunks, ans)
                break
            except (json.JSONDecodeError, KeyError) as e:
                print(f"judge parse failure on {entry['id']} ({e}); "
                      f"{'retrying' if _attempt == 0 else 'SKIPPED'}", flush=True)
        if verdict is None:
            continue
        claims = verdict.get("claims", [])
        bad = [c for c in claims if c["verdict"] != "supported"]
        results.append({"id": entry["id"], "bucket": entry["bucket"], "query": entry["query"],
                        "answer": ans, "claims": claims, "faithful": not bad,
                        "n_claims": len(claims), "n_unsupported": len(bad)})
        print(f"{'ok  ' if not bad else 'BAD '} {entry['id']}: {len(claims)} claims, {len(bad)} unsupported")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    buckets = sorted({r["bucket"] for r in results})
    table = {f"bucket_{b}": {
        "n": len([r for r in results if r["bucket"] == b]),
        "faithful": len([r for r in results if r["bucket"] == b and r["faithful"]]),
    } for b in buckets}
    out = {"run": args.label, "mode": args.mode, "model": args.model, "timestamp": ts,
           "overall_faithful_pct": round(100 * sum(r["faithful"] for r in results) / len(results), 1),
           "per_bucket": table, "per_query": results}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{ts}_faithfulness_{args.label}.json"
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nfaithful: {out['overall_faithful_pct']}%  -> {out_path.relative_to(ROOT)}")

    # mandatory human spot-check sample (decisions.md D-013)
    sample = random.Random(7).sample(results, min(SPOTCHECK_N, len(results)))
    lines = ["# Judge spot-check â€” validate these verdicts by hand", ""]
    for r in sample:
        lines += [f"## {r['id']} â€” judge says {'FAITHFUL' if r['faithful'] else 'UNFAITHFUL'}",
                  f"**Q:** {r['query']}", "", f"**Answer:**\n{r['answer']}", "",
                  "**Judge claims table:**"]
        lines += [f"- [{c['verdict']}] {c['claim']} (evidence: {c.get('evidence')})"
                  for c in r["claims"]] or ["- (no claims â€” refusal)"]
        lines += ["", "**Your verdict (agree/disagree + why):** ", "", "---", ""]
    spot = ROOT / "eval" / f"judge_spotcheck_{args.label}.md"
    spot.write_text("\n".join(lines), encoding="utf-8")
    print(f"spot-check file -> {spot.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
