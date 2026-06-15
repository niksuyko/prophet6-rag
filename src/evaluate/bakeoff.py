"""RAG vs base-model bake-off: blind pairwise judging (decisions.md D-014).

Usage: python src/evaluate/bakeoff.py <run_label> [--mode hybrid] [--k 5]
Every golden query is answered two ways â€” base model (no retrieval) and the full RAG
pipeline. A blind judge (position-randomized, citations stripped) picks the better answer
for a Prophet-6 owner. Reports RAG win/tie/loss per bucket.
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "generate"))
from ask import DEFAULT_MODEL, answer  # noqa: E402

GOLDEN = ROOT / "eval" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"

BASE_SYSTEM = ("You are a knowledgeable synthesizer expert. Answer the user's question about "
               "the Sequential Prophet-6 as helpfully and accurately as you can.")

JUDGE_SYSTEM = """You judge two answers to the same question about the Sequential Prophet-6
synthesizer. Pick the answer that would serve a Prophet-6 owner better, weighing factual
correctness first, then practical usefulness. If genuinely comparable, answer "tie".
Respond with JSON only: {"winner": "A"|"B"|"tie", "reason": "<one sentence>"}"""


def strip_citations(text: str) -> str:
    text = re.sub(r"\[(Manual|reddit|article|official_kb)[^\]]*\]", "", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def base_answer(client, model: str, question: str) -> str:
    msg = client.messages.create(model=model, max_tokens=1200, temperature=0.2,
                                 system=BASE_SYSTEM,
                                 messages=[{"role": "user", "content": question}])
    return msg.content[0].text


def judge_pair(client, model: str, question: str, a: str, b: str) -> dict:
    msg = client.messages.create(
        model=model, max_tokens=300, temperature=0, system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content":
                   f"Question: {question}\n\nAnswer A:\n{a}\n\nAnswer B:\n{b}\n\nJSON:"}])
    text = msg.content[0].text.strip()
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


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
    rng = random.Random(42)
    golden_path = Path(args.golden) if args.golden else GOLDEN  # v2: optional golden file
    golden = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    results = []
    for entry in golden:
        rag, _ = answer(entry["query"], args.mode, args.k, args.model)
        base = base_answer(client, args.model, entry["query"])
        rag_blind = strip_citations(rag)
        rag_is_a = rng.random() < 0.5
        a, b = (rag_blind, base) if rag_is_a else (base, rag_blind)
        verdict = judge_pair(client, args.model, entry["query"], a, b)
        w = verdict.get("winner", "tie")
        outcome = "tie" if w == "tie" else ("rag" if (w == "A") == rag_is_a else "base")
        results.append({"id": entry["id"], "bucket": entry["bucket"], "query": entry["query"],
                        "rag_answer": rag, "base_answer": base, "rag_was_A": rag_is_a,
                        "judge": verdict, "outcome": outcome})
        print(f"{outcome.upper():4} {entry['id']}: {verdict.get('reason','')[:80]}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    buckets = sorted({r["bucket"] for r in results})
    table = {}
    for bkt in buckets:
        rows = [r for r in results if r["bucket"] == bkt]
        table[f"bucket_{bkt}"] = {o: len([r for r in rows if r["outcome"] == o])
                                  for o in ("rag", "tie", "base")} | {"n": len(rows)}
    out = {"run": args.label, "mode": args.mode, "model": args.model, "timestamp": ts,
           "totals": {o: len([r for r in results if r["outcome"] == o])
                      for o in ("rag", "tie", "base")},
           "per_bucket": table, "per_query": results}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{ts}_bakeoff_{args.label}.json"
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\ntotals: {out['totals']}  -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
