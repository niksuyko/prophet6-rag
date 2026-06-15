"""A/B the patch-quality judge across two corpora (expanded vs reverted) — settle whether
the recipe expansion helps PATCH CREATION on the metric that measures it (D-033 judge),
not recall@5. Run once per index (swap data/index between runs); compare judge means.

Usage:
  python -X utf8 eval/_patch_ab.py <label>     # scores the fixed query set on the LIVE index
Needs ANTHROPIC_API_KEY (generation + judge).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from patch_quality import _gen, load_rubrics, score_query  # noqa: E402

# Queries chosen where the expansion demonstrably added relevant content (Tame Impala:
# 82 threads in the full set, 57 expansion-only) plus general recipe asks + cross-synth.
QUERIES = [
    "Patch similar to Nangs by Tame Impala",
    "Tame Impala Let It Happen lead synth",
    "Tame Impala The Less I Know The Better bass",
    "warm Juno-style chorus pad with slow movement",
    "acid squelchy 303-style bass",
    "Boards of Canada warm detuned nostalgic pad",
    "bright plucky arpeggio synth",
    "huge detuned supersaw trance lead",
]


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "live"
    rubrics = load_rubrics()
    rows = []
    for q in QUERIES:
        patch = _gen(q)
        row = score_query(q, patch, rubrics)
        # how much of this patch is grounded in retrieved corpus vs general synthesis?
        cited = sum(1 for c in patch["changes"] if not c["source"].lower().startswith("general"))
        row["cited"] = cited
        row["cited_ratio"] = round(cited / max(1, len(patch["changes"])), 2)
        rows.append(row)
        print(f"  judge {row['judge']}/5  cite {row['cited_ratio']:.0%}  "
              f"{q[:42]:42s}  — {row['judge_verdict'][:60]}")
    jmean = round(sum(r["judge"] for r in rows) / len(rows), 2)
    cmean = round(sum(r["cited_ratio"] for r in rows) / len(rows), 2)
    rtmean = round(sum(r["roundtrip"] for r in rows) / len(rows), 3)
    print(f"\n[{label}] judge mean {jmean}/5 | cite mean {cmean:.0%} | roundtrip mean {rtmean}")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (ROOT / "eval" / "results" / f"{ts}_patch_ab_{label}.json").write_text(
        json.dumps({"label": label, "judge_mean": jmean, "cite_mean": cmean,
                    "roundtrip_mean": rtmean, "rows": rows}, indent=1), encoding="utf-8")
    print(f"saved -> eval/results/{ts}_patch_ab_{label}.json")


if __name__ == "__main__":
    main()
