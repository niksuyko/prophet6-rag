"""Grounded Q&A CLI with inline citations (decisions.md D-012).

Usage: python src/generate/ask.py "what does slop do?" [--mode hybrid] [--k 5] [--model ...]
Requires ANTHROPIC_API_KEY.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
import load_env  # noqa: E402,F401  (side effect: populates ANTHROPIC_API_KEY from .env)
from search import retrieve  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-4-6"

SYSTEM = """You answer questions about the Sequential Prophet-6 synthesizer.

Rules:
1. Answer ONLY from the context chunks provided. Do not use outside knowledge for factual
   claims about the Prophet-6, other synths, or procedures.
2. Cite the chunk label inline after each claim, e.g. [Manual - Slop] or [reddit:1id23zb].
   Every factual claim needs at least one citation.
3. If the chunks do not contain enough information to answer, say plainly:
   "My corpus doesn't cover this." Then briefly note any related information the chunks DO
   contain. Never improvise an answer.
4. Community answers (reddit) are experiences and opinions — attribute them as such when
   they conflict with the manual."""


def chunk_label(c: dict) -> str:
    if c["source_type"] == "manual":
        return f"Manual - {c['section']}"
    if c["source_type"] == "reddit":
        return f"reddit:{c['source_id']}"
    return f"{c['source_type']}:{c['source_id']}"


def build_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        parts.append(f"<chunk label=\"{chunk_label(c)}\" url=\"{c['source_url']}\">\n"
                     f"{c['text']}\n</chunk>")
    return "\n\n".join(parts)


def answer(question: str, mode: str = "strat+div", k: int = 5,
           model: str = DEFAULT_MODEL) -> tuple[str, list[dict]]:
    import anthropic
    chunks = retrieve(question, k, mode=mode)
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model, max_tokens=1200, temperature=0.2, system=SYSTEM,
        messages=[{"role": "user",
                   "content": f"Context chunks:\n\n{build_context(chunks)}\n\n"
                              f"Question: {question}"}])
    return msg.content[0].text, chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--mode", default="strat+div")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    text, chunks = answer(args.question, args.mode, args.k, args.model)
    print(text)
    print("\n--- sources ---")
    for c in chunks:
        print(f"[{chunk_label(c)}] {c['source_url']}")


if __name__ == "__main__":
    main()
