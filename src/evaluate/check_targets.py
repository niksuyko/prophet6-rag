"""Eval-integrity check: every golden-set entry must have at least one expected target
that actually exists in chunks.jsonl. Run after any re-chunk; exits nonzero on violations.
(recall@5 presumes the answer is indexable — see decisions.md D-005.)

v2 (plan Phase A step 4): also checks eval/golden_set_v2.jsonl when present, and
validates `param_targets` (reference patch ids must exist in data/patches/ — the
D-015 lesson extended to structured-patch targets). Non-manual target types match
on chunk source_id generically, so patch/video/translation chunk types are covered
without further edits.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GOLDEN_FILES = [ROOT / "eval" / "golden_set.jsonl",
                ROOT / "eval" / "golden_set_v2.jsonl"]


def main() -> None:
    chunks = [json.loads(l) for l in
              (ROOT / "data" / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    ids = {c["source_id"] for c in chunks}
    sections = " || ".join((c["section"] or "") for c in chunks
                           if c["source_type"] == "manual").lower()
    patch_dir = ROOT / "data" / "patches"
    bad = 0
    total = 0
    for golden_path in GOLDEN_FILES:
        if not golden_path.exists():
            continue
        golden = [json.loads(l) for l in
                  golden_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        total += len(golden)
        for g in golden:
            reachable = []
            for t in g.get("expected_targets", []):
                if t["source_type"] == "manual":
                    reachable.append(t["match"].lower() in sections)
                else:
                    reachable.append(t["match"] in ids)
            if g.get("expected_targets") and not any(reachable):
                print(f"UNREACHABLE: {g['id']} ({golden_path.name}) — no expected target "
                      f"exists in chunks.jsonl: {g['expected_targets']}")
                bad += 1
            elif g.get("expected_targets") and not all(reachable):
                missing = [t["match"] for t, r in zip(g["expected_targets"], reachable) if not r]
                print(f"partial:     {g['id']} — missing {missing} (ok, others reachable)")
            for pid in g.get("param_targets", []):
                if not (patch_dir / f"{pid}.json").exists():
                    print(f"MISSING PATCH: {g['id']} ({golden_path.name}) — param_target "
                          f"{pid!r} not in data/patches/")
                    bad += 1
    if bad:
        sys.exit(1)
    print(f"OK: all {total} golden entries have at least one reachable target")


if __name__ == "__main__":
    main()
