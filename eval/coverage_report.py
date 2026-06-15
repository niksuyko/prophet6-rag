"""Coverage report: families x characters with per-cell independent-source counts
(v2 plan success criterion 4: >= 90% of non-excluded cells backed by >= 3 sources).

A source = unique source_id (thread, article, patch, translation entry). Patch chunks
declare their category/character lines explicitly (chunk_patches.py); other chunks are
keyword-classified with the same vocabularies the golden-set builder uses.

Usage: python -X utf8 eval/coverage_report.py [--write]
"""
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "evaluate"))
from build_golden_v2 import CHARACTER_KW, FAMILY_KW  # noqa: E402

MATRIX = yaml.safe_load((ROOT / "eval" / "coverage_matrix.yaml").read_text(encoding="utf-8"))
FAMILIES = list(MATRIX["families"])
CHARACTERS = list(MATRIX["characters"])
EXCLUDED = {tuple(c) for c in MATRIX.get("excluded_cells", [])}


def classify(chunk: dict) -> tuple[set, set]:
    text = chunk["text"]
    if chunk["source_type"] == "patch":
        fams, chars = set(), set()
        m = re.search(r"Category: ([a-z/_]+)\.", text)
        if m:
            fams.add(m.group(1).replace("/", "_"))
        m = re.search(r"Character: ([a-z, ]+)\.", text)
        if m:
            chars.update(t.strip() for t in m.group(1).split(","))
        return fams & set(FAMILIES), chars & set(CHARACTERS)
    blob = text[:1200]
    fams = {f for f, pat in FAMILY_KW.items() if re.search(pat, blob, re.I)}
    chars = {c for c, pat in CHARACTER_KW.items() if re.search(pat, blob, re.I)}
    return fams, chars


def main() -> None:
    chunks = [json.loads(l) for l in
              (ROOT / "data" / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    cell_sources: dict[tuple, set] = {}
    for c in chunks:
        fams, chars = classify(c)
        for f in fams:
            for ch in chars:
                cell_sources.setdefault((f, ch), set()).add(c["source_id"])

    cells = [(f, ch) for f in FAMILIES for ch in CHARACTERS if (f, ch) not in EXCLUDED]
    ok = sum(1 for cell in cells if len(cell_sources.get(cell, ())) >= 3)
    pct = ok / len(cells)

    colw = max(len(c) for c in CHARACTERS) + 1
    header = " " * 12 + "".join(f"{c[:colw - 1]:>{colw}}" for c in CHARACTERS)
    print(header)
    for f in FAMILIES:
        row = f"{f:<12}"
        for ch in CHARACTERS:
            if (f, ch) in EXCLUDED:
                row += f"{'--':>{colw}}"
            else:
                row += f"{len(cell_sources.get((f, ch), ())):>{colw}}"
        print(row)
    print(f"\ncells >= 3 sources: {ok}/{len(cells)} = {pct:.1%} (criterion: >= 90%)")
    gaps = sorted((cell for cell in cells if len(cell_sources.get(cell, ())) < 3),
                  key=lambda cell: len(cell_sources.get(cell, ())))
    print(f"gap cells ({len(gaps)}):")
    for f, ch in gaps:
        print(f"  {f} x {ch}: {len(cell_sources.get((f, ch), ()))}")
    if "--write" in sys.argv:
        out = {"pct_cells_3plus": round(pct, 3), "ok": ok, "total": len(cells),
               "cells": {f"{f}|{ch}": len(cell_sources.get((f, ch), ()))
                         for f, ch in cells}}
        path = ROOT / "eval" / "results" / "coverage_report.json"
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"saved -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
