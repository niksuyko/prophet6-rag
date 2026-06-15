"""Regression check for the manual chunker: every hand-verified section in
manual_toc_expected.yaml must exist in chunks_manual.jsonl (as a section-name substring)
and contain its expected phrase. Exits nonzero on failure."""
import sys
from pathlib import Path

import yaml

from common import PROCESSED_DIR, read_jsonl

HERE = Path(__file__).parent


def main() -> None:
    expected = yaml.safe_load((HERE / "manual_toc_expected.yaml").read_text(encoding="utf-8"))
    chunks = read_jsonl(PROCESSED_DIR / "chunks_manual.jsonl")
    failures = []
    for item in expected:
        name, phrase = item["section"], item["expected_phrase"]
        matching = [c for c in chunks if name.lower() in (c["section"] or "").lower()]
        if not matching:
            failures.append(f"section not found: {name!r}")
        elif not any(phrase.lower() in c["text"].lower() for c in matching):
            failures.append(f"section {name!r} found but missing phrase {phrase!r}")
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"OK: all {len(expected)} hand-verified sections present with expected content")


if __name__ == "__main__":
    main()
