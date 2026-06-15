"""Blind A/B: patch-grounded ('adapt', D-024) vs v1 pure-LLM ('pure') patch generation
(v2 plan, Phase B step 7). Judge sees the query + both patches' parameter moves
(citations stripped, order randomized per query) and picks the better realization.

Usage: python -X utf8 src/evaluate/patch_ab.py <label> [n_queries] [golden_file]
Requires ANTHROPIC_API_KEY.
"""
import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "ui"))
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
import load_env  # noqa: E402,F401

JUDGE_MODEL = "claude-sonnet-4-6"
JUDGE_SYSTEM = """You judge Prophet-6 synthesizer patches. Given a sound request and two
candidate patches (parameter settings with brief rationales), decide which patch would
better realize the requested sound on a real Prophet-6.

Judge on: (1) would it actually make the requested sound (signal-path correctness:
something audible, envelopes/filters/mod consistent with the request); (2) completeness
(captures the character, movement, performance details); (3) musical credibility of the
specific values. Output ONLY JSON: {"winner": "A"|"B", "reason": "<one sentence>"}"""


def patch_text(result: dict) -> str:
    lines = [f"name: {result['patch_name']}", f"idea: {result['summary']}"]
    for c in sorted(result["changes"], key=lambda c: c["param"]):
        lines.append(f"  {c['param']} = {c['value']}  ({c['why']})")  # source stripped
    return "\n".join(lines)


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "v2"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    golden_path = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "eval" / "golden_set_v2.jsonl"
    from generate_patch import generate_patch
    import anthropic
    client = anthropic.Anthropic()

    golden = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines()
              if l.strip()]
    queries = [g for g in golden if g["bucket"] == 2][:n]
    rng = random.Random(42)
    wins = {"adapt": 0, "pure": 0}
    rows = []
    for i, g in enumerate(queries, 1):
        try:
            adapt = generate_patch(g["query"], grounding="adapt")
            pure = generate_patch(g["query"], grounding="pure")
        except Exception as e:
            print(f"{g['id']}: generation failed ({e}); skipped")
            continue
        flip = rng.random() < 0.5
        a, b = (pure, adapt) if flip else (adapt, pure)
        msg = client.messages.create(
            model=JUDGE_MODEL, max_tokens=300, temperature=0.0, system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content":
                       f"Sound request: {g['query']}\n\n=== Patch A ===\n{patch_text(a)}"
                       f"\n\n=== Patch B ===\n{patch_text(b)}"}])
        try:
            verdict = json.loads(msg.content[0].text.strip().strip("`json \n"))
        except json.JSONDecodeError:
            print(f"{g['id']}: judge output unparseable; skipped")
            continue
        winner_mode = ("pure" if verdict["winner"] == "A" else "adapt") if flip else \
                      ("adapt" if verdict["winner"] == "A" else "pure")
        wins[winner_mode] += 1
        n_patch_cited = sum(1 for c in adapt["changes"] if c["source"].startswith("patch"))
        rows.append({"id": g["id"], "query": g["query"], "winner": winner_mode,
                     "reason": verdict["reason"], "flip": flip,
                     "adapt_patch_citations": n_patch_cited,
                     "adapt_changes": len(adapt["changes"]),
                     "pure_changes": len(pure["changes"])})
        print(f"[{i}/{len(queries)}] {g['id']}: {winner_mode}  ({verdict['reason'][:80]})")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = {"run": label, "timestamp": ts, "n": len(rows), "wins": wins,
           "judge": JUDGE_MODEL, "per_query": rows}
    out_path = ROOT / "eval" / "results" / f"{ts}_patch_ab_{label}.json"
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nadapt {wins['adapt']} — pure {wins['pure']}  (n={len(rows)})")
    print(f"saved -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
