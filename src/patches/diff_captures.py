"""Byte-diff two captured P6 dumps to resolve the FX byte-map (ISSUE-3 / D-023).

Each capture saved by the dashboard's MIDI Capture button stores the raw 1024-byte internal
layout under "bytes". This prints every offset whose value differs between two captures,
annotated with the decode LAYOUT label when known — so capturing the SAME patch with one
thing toggled isolates exactly which byte controls it.

Recipes:
  * Find the real master fx.on byte: capture a patch with FX clearly ON, then the same patch
    with FX OFF; diff. The offset that flips is the true fx.on (LAYOUT currently guesses 54).
  * Rebuild the FX-type enum order: capture a patch with FX B = plate reverb, then = flanger
    (etc.); diff. Offset 45 (fxb.type) will hold each effect's real hardware byte value.

Usage:
  python -X utf8 src/patches/diff_captures.py <A.json> <B.json>
  (each path may be absolute, or just a filename inside data/patches/)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH_DIR = ROOT / "data" / "patches"
sys.path.insert(0, str(ROOT / "src" / "patches"))
from decode_sysex import LAYOUT  # noqa: E402


def _resolve(arg: str) -> Path:
    p = Path(arg)
    return p if p.exists() else PATCH_DIR / arg


def _load(path: Path):
    if not path.exists():
        sys.exit(f"not found: {path}")
    d = json.loads(path.read_text(encoding="utf-8"))
    b = d.get("bytes") or d.get("raw")  # captures store "bytes" (1024); factory files store "raw" (128)
    if not b:
        sys.exit(f"{path.name}: no raw bytes — re-capture with the updated server (older "
                 f"captures and factory p6-*.json files predate raw-byte logging).")
    return d, b


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: diff_captures.py <captureA.json> <captureB.json>")
    pa, pb = _resolve(sys.argv[1]), _resolve(sys.argv[2])
    da, a = _load(pa)
    db, b = _load(pb)
    print(f"A: {pa.name}  name={da.get('name')!r}  ({len(a)} bytes)")
    print(f"B: {pb.name}  name={db.get('name')!r}  ({len(b)} bytes)")
    n = min(len(a), len(b))
    diffs = [(off, a[off], b[off]) for off in range(n) if a[off] != b[off]]
    print(f"\n{len(diffs)} differing byte offset(s):")
    print(f"  {'off':>4}  {'A':>4}  {'B':>4}   param")
    print(f"  {'-'*4}  {'-'*4}  {'-'*4}   {'-'*20}")
    for off, va, vb in diffs:
        label = LAYOUT[off][0] if off in LAYOUT else "(unmapped)"
        print(f"  {off:>4}  {va:>4}  {vb:>4}   {label}")
    if len(a) != len(b):
        print(f"\nNOTE: byte lengths differ ({len(a)} vs {len(b)}); compared the first {n}.")
    if not diffs:
        print("  (identical over the compared range)")


if __name__ == "__main__":
    main()
