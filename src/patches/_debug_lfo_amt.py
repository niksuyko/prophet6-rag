"""Debug lfo.initial_amount scaling: UI value -> encoded byte -> what factory patches use.
Symptom: UI 10 seems to come through HIGHER on the hardware."""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "ui"))
sys.path.insert(0, str(ROOT / "src" / "patches"))
from patch_schema import PARAMS, INIT_PATCH  # noqa
from decode_sysex import LAYOUT  # noqa
from encode_sysex import encode_edit_buffer  # noqa

p = PARAMS["lfo.initial_amount"]
print(f"schema lfo.initial_amount: type={p['type']} min={p['min']} max={p['max']} init={p['init']}")
# which dump offset?
off = next(o for o, (pid, _) in LAYOUT.items() if pid == "lfo.initial_amount")
foff = next(o for o, (pid, _) in LAYOUT.items() if pid == "lfo.frequency")
print(f"dump offset: initial_amount={off}, frequency={foff}")

# what byte does UI=10 encode to?
import decode_sysex
msg = encode_edit_buffer({**INIT_PATCH, "lfo.initial_amount": 10}, "T")
data = decode_sysex.unpack(bytes(msg)[4:-1])
print(f"UI lfo.initial_amount=10 -> encoded byte[{off}] = {data[off]}")

# distribution across factory patches (raw byte values from the .json 'raw' field)
vals = []
for f in glob.glob(str(ROOT / "data/patches/p6-*.json")):
    raw = json.load(open(f, encoding="utf-8")).get("raw", [])
    if len(raw) > off:
        vals.append(raw[off])
if vals:
    vals.sort()
    import collections
    print(f"\nfactory offset {off} (initial_amount): n={len(vals)} "
          f"min={vals[0]} max={vals[-1]} median={vals[len(vals)//2]}")
    print(f"  count >127: {sum(1 for v in vals if v > 127)}  "
          f"count >200: {sum(1 for v in vals if v > 200)}  ==255: {sum(1 for v in vals if v==255)}")
    # also lfo.frequency offset for comparison
    fvals = sorted(json.load(open(f, encoding="utf-8")).get("raw", [0]*200)[foff]
                   for f in glob.glob(str(ROOT / "data/patches/p6-*.json")))
    print(f"factory offset {foff} (frequency): min={fvals[0]} max={fvals[-1]} "
          f"count >127: {sum(1 for v in fvals if v>127)}")
