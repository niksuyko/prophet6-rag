"""Prophet-6 sysex program decoder (v2 plan, Phase B steps 1-2).

Message framing + packing are from the manual's Appendix C:
  Program Data Dump: F0 01 2D 02 <bank 0-9> <program 0-99> <1171 packed bytes> F7
  Packed MS-bit format: 8-byte packets; packet[0] bit i = MS bit of data byte i.

The 1024-byte INTERNAL layout is NOT the NRPN numbering (the appendix's table is the
MIDI parameter map only). The byte map below was reverse-engineered in this project
(decisions.md D-023) from three independent evidence sources:
  (1) per-offset value ranges across all 770 official factory/OMOM programs, matched
      against the NRPN table's known parameter ranges;
  (2) INIT 'Basic Program' anchor bytes (eclewlow/Prophet6SoundLibrarian constant,
      which also fixes the patch name at offset 107, length 20);
  (3) name-implied settings: 15/15 sync-named patches have [11]=1; 'FM Bass' shows
      osc2->freq1 Poly Mod at [78]/[79]; S&H-named patches have [62]=4 (random);
      square-named patches have [3]=[4]=254; bend-range histogram at [17] is the
      classic 2/7/12; slop at [106] is mostly-0-max-25.
Selector ORDER assumptions (glide/LFO-shape/arp-mode/key-mode/divide/dest orders,
shape<->PW osc pairing, FX A/B sync) follow NRPN/panel order and are flagged for the
hardware spot-check gate (Phase B step 6).

Usage: python -X utf8 src/patches/decode_sysex.py
"""
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "ui"))
from patch_schema import INIT_PATCH, PARAMS  # noqa: E402

RAW = ROOT / "data" / "raw" / "patches"
OUT = ROOT / "data" / "patches"

NAME_OFFSET, NAME_LEN = 107, 20

SHAPES = ["triangle", "tri-saw", "sawtooth", "saw-pulse", "pulse"]
SHAPE_BOUNDS = [32, 96, 159, 223]
FX_TYPES = ["off", "bbd-delay", "digital-delay", "chorus", "phaser-1", "phaser-2",
            "hall-reverb", "room-reverb", "plate-reverb", "spring-reverb",
            "flanger", "ring-mod", "phaser-3"]  # >=10 added by OS 1.6.7 (order assumed)
GLIDE_MODES = ["fixed-rate", "fixed-rate-legato", "fixed-time", "fixed-time-legato"]
LFO_SHAPES = ["triangle", "sawtooth", "rev-sawtooth", "square", "random"]
KEY_MODES = ["low", "high", "last", "low-retrig", "high-retrig", "last-retrig"]
ARP_MODES = ["up", "down", "up+down", "random", "assign"]
KEY_AMTS = ["off", "half", "full"]
UNISON_VOICES = ["1", "2", "3", "4", "5", "6", "chord"]
DIVIDES = ["half", "quarter", "8th", "8th-half-swing", "8th-full-swing", "8th-triplet",
           "16th", "16th-half-swing", "16th-full-swing", "16th-triplet"]


def shape_name(raw: int) -> str:
    for bound, name in zip(SHAPE_BOUNDS, SHAPES):
        if raw < bound:
            return name
    return SHAPES[-1]


def sel(options):
    return lambda v: options[min(v, len(options) - 1)]


def bipolar(v):
    return v - 127


# internal byte offset -> (schema_id, transform)   [D-023]
LAYOUT = {
    0: ("osc1.frequency", int), 1: ("osc2.frequency", int), 2: ("osc2.fine", bipolar),
    3: ("osc1.shape", shape_name), 4: ("osc2.shape", shape_name),
    5: ("osc1.pulse_width", int), 6: ("osc2.pulse_width", int),
    7: ("mixer.osc1", int), 8: ("mixer.osc2", int), 9: ("mixer.sub_octave", int),
    10: ("mixer.noise", int),
    11: ("osc1.sync", bool), 12: ("osc2.keyboard", bool), 13: ("osc2.low_freq", bool),
    14: ("misc.pan_spread", int), 15: ("glide.mode", sel(GLIDE_MODES)),
    16: ("glide.on", bool), 17: ("misc.pbend_range", int), 18: ("glide.rate", int),
    19: ("lpf.cutoff", int), 20: ("lpf.resonance", int),
    21: ("lpf.keyboard", sel(KEY_AMTS)), 22: ("lpf.velocity", bool),
    23: ("hpf.cutoff", int), 24: ("hpf.resonance", int),
    25: ("hpf.keyboard", sel(KEY_AMTS)), 26: ("hpf.velocity", bool),
    27: ("misc.program_volume", int),
    # 28: unknown (possibly a velocity-amount; kept raw-only)
    29: ("lpf.env_amount", bipolar), 30: ("hpf.env_amount", bipolar),
    31: ("aenv.env_amount", int),
    # 32-34: constants/reserved
    # envelopes are stored A-S-D-R, NOT the NRPN A-D-S-R numbering (D-031: confirmed by
    # hardware INIT capture — sustain sits at offset 36/40, decay at 37/41)
    35: ("fenv.attack", int), 36: ("fenv.sustain", int), 37: ("fenv.decay", int),
    38: ("fenv.release", int),
    39: ("aenv.attack", int), 40: ("aenv.sustain", int), 41: ("aenv.decay", int),
    42: ("aenv.release", int), 43: ("aenv.velocity", bool),
    44: ("fxa.type", sel(FX_TYPES[:6] + FX_TYPES[10:])),
    45: ("fxb.type", sel(FX_TYPES)),
    46: ("fxa.sync", bool), 47: ("fxb.sync", bool),
    48: ("fxa.mix", int), 49: ("fxb.mix", int),
    50: ("fxa.param1", int), 51: ("fxb.param1", int),
    52: ("fxa.param2", int), 53: ("fxb.param2", int),
    54: ("fx.on", bool),
    # 55: sequencer on/off (raw-only); 56/57: per-FX sync divide values (raw-only)
    58: ("dist.amount", int), 59: ("lfo.frequency", int),
    # 60: unknown {0,11} (raw-only)
    61: ("lfo.sync", bool), 62: ("lfo.shape", sel(LFO_SHAPES)),
    63: ("lfo.initial_amount", int),
    64: ("lfo.dest_freq1", bool), 65: ("lfo.dest_freq2", bool),
    66: ("lfo.dest_pw12", bool), 67: ("lfo.dest_amp", bool),
    68: ("lfo.dest_lp", bool), 69: ("lfo.dest_hp", bool),
    70: ("at.amount", bipolar),
    71: ("at.dest_freq1", bool), 72: ("at.dest_freq2", bool),
    73: ("at.dest_lp", bool), 74: ("at.dest_hp", bool),
    75: ("at.dest_amp", bool), 76: ("at.dest_lfo", bool),
    77: ("pmod.filt_env", bipolar), 78: ("pmod.osc2", bipolar),
    79: ("pmod.dest_freq1", bool), 80: ("pmod.dest_shape1", bool),
    81: ("pmod.dest_pw1", bool), 82: ("pmod.dest_lp", bool), 83: ("pmod.dest_hp", bool),
    84: ("unison.on", bool), 85: ("unison.voices", sel(UNISON_VOICES)),
    86: ("unison.key_mode", sel(KEY_MODES)),
    87: ("clock.bpm", int),
    # 88: reserved
    89: ("arp.mode", sel(ARP_MODES)), 90: ("arp.octaves", sel(["1", "2", "3"])),
    91: ("arp.on", bool), 92: ("clock.divide", sel(DIVIDES)),
    # 93-105: sequencer settings / unknown (raw-only)
    106: ("slop.amount", int),
}


def unpack(packed: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(packed), 8):
        chunk = packed[i:i + 8]
        ms = chunk[0]
        for j, b in enumerate(chunk[1:]):
            out.append(b | (((ms >> j) & 1) << 7))
    return bytes(out)


def pack(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 7):
        chunk = data[i:i + 7]
        ms = 0
        low = bytearray()
        for j, b in enumerate(chunk):
            ms |= ((b >> 7) & 1) << j
            low.append(b & 0x7F)
        out.append(ms)
        out.extend(low)
    return bytes(out)


def split_messages(blob: bytes) -> list[bytes]:
    msgs, start = [], None
    for i, b in enumerate(blob):
        if b == 0xF0:
            start = i
        elif b == 0xF7 and start is not None:
            msgs.append(blob[start:i + 1])
            start = None
    return msgs


def clamp_to_schema(pid: str, val):
    p = PARAMS[pid]
    if p["type"] in ("knob", "bipolar"):
        return max(p["min"], min(p["max"], int(val)))
    return val


def decode_message(msg: bytes) -> dict | None:
    if len(msg) < 8 or msg[1] != 0x01 or msg[2] != 0x2D:
        return None
    if msg[3] == 0x02:       # program dump with bank/program
        bank, prog, payload = msg[4], msg[5], msg[6:-1]
    elif msg[3] == 0x03:     # edit buffer
        bank, prog, payload = None, None, msg[4:-1]
    else:
        return None
    data = unpack(payload)
    if len(data) != 1024:
        raise ValueError(f"unpacked {len(data)} bytes, expected 1024")
    params = dict(INIT_PATCH)
    for off, (pid, fn) in LAYOUT.items():
        params[pid] = bool(data[off]) if fn is bool else clamp_to_schema(pid, fn(data[off]))
    name = bytes(data[NAME_OFFSET:NAME_OFFSET + NAME_LEN]).decode("ascii", "replace")
    name = name.strip("\x00 �").strip()
    return {"bank": bank, "program": prog, "name": name, "params": params,
            "raw": list(data[:128]), "_payload": payload, "_data": data}


def pdf_names(pdf_path: Path) -> list[str]:
    import fitz
    doc = fitz.open(pdf_path)
    text = "\n".join(p.get_text() for p in doc)
    doc.close()
    names, want = [], 0
    lines = [l.strip() for l in text.splitlines()]
    for i, line in enumerate(lines):
        if re.fullmatch(r"\d{3}", line) and int(line) == want % 1000 and int(line) == len(names):
            for nxt in lines[i + 1:i + 5]:
                if nxt and not re.fullmatch(r"\d{3}|BANK \d|\d{3}-\d{3}|[A-Z]{2}", nxt):
                    names.append(nxt)
                    break
            want += 1
    return names


def norm(s: str) -> str:
    s = re.sub(r"^p5 (\d+)$", r"prophet5preset\1", s.lower().strip())
    return re.sub(r"[^a-z0-9]", "", s.replace("’", "'"))


def names_match(sysex_name: str, pdf_name: str) -> bool:
    # OMOM sysex names embed author initials ("Tuba AB"); the PDF lists them separately
    bare = re.sub(r"\s+[A-Z]{2}$", "", sysex_name.strip())
    for cand in (sysex_name, bare):
        a, b = norm(cand), norm(pdf_name)
        # sysex names are hard-truncated at 20 chars; PDF may carry the full name
        if a and b and (a == b or (len(cand.strip()) >= 19 and b.startswith(a))):
            return True
    return False


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = [("factory", "p6_factory_programs.zip", "p6_factory_presets_list.pdf"),
               ("omom", "p6_omom_sounds.zip", "p6_omom_presets_list.pdf")]
    total, rt_fail, name_match, name_total, mismatches = 0, 0, 0, 0, []
    for source, zip_name, pdf_name in sources:
        with zipfile.ZipFile(RAW / zip_name) as z:
            syx_name = next(n for n in z.namelist()
                            if n.endswith(".syx") and not n.startswith("__MACOSX"))
            blob = z.read(syx_name)
        official = pdf_names(RAW / pdf_name)
        msgs = split_messages(blob)
        print(f"{source}: {len(msgs)} sysex messages, {len(official)} PDF names")
        for idx, msg in enumerate(msgs):
            d = decode_message(msg)
            if d is None:
                continue
            if pack(d["_data"]) != d["_payload"]:
                rt_fail += 1
                print(f"  ROUND-TRIP FAIL: {source} msg {idx}")
            slot = (d["bank"] * 100 + d["program"]) if d["bank"] is not None else idx
            pid = f"p6-{source}-{slot:03d}"
            if idx < len(official):
                name_total += 1
                if names_match(d["name"], official[idx]):
                    name_match += 1
                elif len(mismatches) < 15:
                    mismatches.append(f"{pid}: sysex={d['name']!r} pdf={official[idx]!r}")
            entry = {"id": pid, "source": source, "bank": d["bank"], "program": d["program"],
                     "name": d["name"], "params": d["params"], "raw": d["raw"]}
            (OUT / f"{pid}.json").write_text(json.dumps(entry, indent=1), encoding="utf-8")
            total += 1
    print(f"\ndecoded {total} programs -> {OUT}")
    print(f"round-trip failures: {rt_fail}")
    print(f"name validation vs official PDFs: {name_match}/{name_total} "
          f"({name_match / max(1, name_total):.1%})")
    for m in mismatches:
        print(f"  mismatch: {m}")


if __name__ == "__main__":
    main()
