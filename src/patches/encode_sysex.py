"""Prophet-6 patch -> sysex edit-buffer dump (v2 plan, Phase G / decisions.md D-030).

Inverse of decode_sysex.LAYOUT. Starts from the INIT 'Basic Program' carrier
(data/patches/init_template.json — supplies the ~944 bytes we don't model: name,
sequencer, reserved/constant), overwrites the ~80 mapped offsets from a resolved panel
state, writes the patch name, packs, and frames as an edit-buffer dump:
    F0 01 2D 03 <1171 packed bytes> F7   (1176 bytes total)

Edit-buffer (0x03) loads into the current edit buffer and plays immediately; it never
overwrites a saved program. Self-consistency: decode(encode(p)) == p (see selftest()).

Usage: python -X utf8 src/patches/encode_sysex.py   # runs the self-consistency test
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "patches"))
sys.path.insert(0, str(ROOT / "src" / "ui"))
from patch_schema import INIT_PATCH  # noqa: E402
from decode_sysex import (  # noqa: E402
    ARP_MODES, DIVIDES, FX_TYPES, GLIDE_MODES, KEY_AMTS, KEY_MODES, LAYOUT, LFO_SHAPES,
    NAME_LEN, NAME_OFFSET, SHAPES, UNISON_VOICES, bipolar, pack, shape_name)

TEMPLATE_FILE = ROOT / "data" / "patches" / "init_template.json"

# representative raw byte per shape band (each lands strictly inside decode's SHAPE_BOUNDS
# [32,96,159,223], so decode(encode(name)) == name exactly)
SHAPE_REPR = {"triangle": 16, "tri-saw": 64, "sawtooth": 127, "saw-pulse": 191,
              "pulse": 254}

# option list per select offset — must mirror decode_sysex.LAYOUT exactly
SELECT_OPTIONS = {
    15: GLIDE_MODES, 21: KEY_AMTS, 25: KEY_AMTS,
    44: FX_TYPES[:6] + FX_TYPES[10:], 45: FX_TYPES,
    62: LFO_SHAPES, 85: UNISON_VOICES, 86: KEY_MODES,
    89: ARP_MODES, 90: ["1", "2", "3"], 92: DIVIDES,
}


@lru_cache(maxsize=1)
def _template() -> bytes:
    data = bytes(json.loads(TEMPLATE_FILE.read_text(encoding="utf-8")))
    if len(data) != 1024:
        raise ValueError(f"init template is {len(data)} bytes, expected 1024")
    return data


def _encode_value(off: int, fn, value) -> int:
    if fn is bool:
        return 1 if value else 0
    if fn is int:
        return max(0, min(255, int(value)))
    if fn is bipolar:
        return max(0, min(255, int(value) + 127))
    if fn is shape_name:
        return SHAPE_REPR.get(value, 0)
    opts = SELECT_OPTIONS[off]                # sel(...) closure
    return opts.index(value) if value in opts else 0  # unknown -> first option; never crash the dump


def encode_edit_buffer(params: dict, name: str = "") -> list[int]:
    """Resolved panel state (all schema ids) -> edit-buffer sysex byte list."""
    data = bytearray(_template())
    for off, (pid, fn) in LAYOUT.items():
        data[off] = _encode_value(off, fn, params[pid])
    nm = (name or "").encode("ascii", "replace")[:NAME_LEN].ljust(NAME_LEN, b" ")
    data[NAME_OFFSET:NAME_OFFSET + NAME_LEN] = nm
    return [0xF0, 0x01, 0x2D, 0x03, *pack(bytes(data)), 0xF7]


def selftest() -> None:
    """decode(encode(p)) == p for INIT + all decoded factory/OMOM patches."""
    from decode_sysex import decode_message
    cases = [("INIT", INIT_PATCH)]
    for f in sorted((ROOT / "data" / "patches").glob("p6-*.json")):
        e = json.loads(f.read_text(encoding="utf-8"))
        cases.append((e["id"], e["params"]))

    msg = encode_edit_buffer(INIT_PATCH, "Test")
    assert len(msg) == 1176, f"framing length {len(msg)} != 1176"
    assert msg[:4] == [0xF0, 0x01, 0x2D, 0x03] and msg[-1] == 0xF7, "bad framing"

    fails = 0
    for cid, params in cases:
        round = decode_message(bytes(encode_edit_buffer(params)))["params"]
        diffs = {k: (params[k], round[k]) for k in params if params[k] != round[k]}
        if diffs:
            fails += 1
            if fails <= 8:
                print(f"  MISMATCH {cid}: {diffs}")
    print(f"self-consistency: {len(cases) - fails}/{len(cases)} patches "
          f"round-trip exactly (framing 1176 bytes OK)")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    selftest()
