"""Debug for KNOWN_ISSUES ISSUE-1: schema INIT defaults are ungrounded (amp envelope).
Confirms it's not the encoder/decoder (round-trip is byte-perfect) but the hand-authored
INIT_PATCH values. Run: python -X utf8 src/patches/_debug_aenv.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "patches"))
sys.path.insert(0, str(ROOT / "src" / "ui"))
from patch_schema import INIT_PATCH, PARAMS  # noqa
from decode_sysex import decode_message, unpack, LAYOUT  # noqa
from encode_sysex import encode_edit_buffer  # noqa

# 1. What does the raw INIT template carrier decode to (before we overwrite anything)?
tmpl = bytes(json.loads((ROOT / "data/patches/init_template.json").read_text()))
print("=== raw INIT template carrier, amp-env offsets ===")
for off, (pid, fn) in sorted(LAYOUT.items()):
    if pid.startswith("aenv") or pid.startswith("fenv"):
        print(f"  offset {off:>3} {pid:<16} raw={tmpl[off]:>3}  schema_init={INIT_PATCH[pid]}")

# 2. Encode schema INIT -> decode it back -> compare amp env
msg = encode_edit_buffer(INIT_PATCH, "INIT")
back = decode_message(bytes(msg))["params"]
print("\n=== encode(INIT) -> decode round-trip, full diff vs schema INIT ===")
diffs = {k: (INIT_PATCH[k], back[k]) for k in INIT_PATCH if INIT_PATCH[k] != back[k]}
print("diffs:", diffs or "NONE")

print("\n=== amp envelope specifically (schema INIT vs round-tripped) ===")
for pid in ("aenv.env_amount", "aenv.attack", "aenv.decay", "aenv.sustain",
            "aenv.release", "aenv.velocity"):
    print(f"  {pid:<18} schema={INIT_PATCH[pid]:<5} roundtrip={back[pid]}")

# 3. How ungrounded is our schema INIT? Decode the raw carrier fully and diff EVERY param.
carrier = decode_message(b"\xf0\x01\x2d\x03" + __import__("encode_sysex").pack(tmpl) + b"\xf7")["params"]
print("\n=== schema INIT vs the real-program carrier, ALL differing params ===")
for pid in sorted(INIT_PATCH):
    if INIT_PATCH[pid] != carrier[pid]:
        print(f"  {pid:<20} schema_init={INIT_PATCH[pid]!s:<8} carrier={carrier[pid]}")
