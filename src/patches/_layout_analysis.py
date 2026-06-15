"""Reverse-engineer the P6 program-data byte layout (offsets 0..106 + post-name).

Evidence: per-offset value stats across 770 factory/OMOM programs, plus the known
INIT 'Basic Program' bytes from the eclewlow librarian (packed sysex constant).
"""
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "patches"))
from decode_sysex import split_messages, unpack

JAVA_URL = ("https://raw.githubusercontent.com/eclewlow/Prophet6SoundLibrarian/main/"
            "src/com/eclewlow/sequential/Prophet6SysexPatch.java")

# --- load all programs
programs = []
for zname in ("p6_factory_programs.zip", "p6_omom_sounds.zip"):
    with zipfile.ZipFile(ROOT / "data/raw/patches" / zname) as z:
        blob = z.read(next(n for n in z.namelist()
                           if n.endswith(".syx") and not n.startswith("__MACOSX")))
    for msg in split_messages(blob):
        if msg[3] == 0x02:
            programs.append(unpack(msg[6:-1]))
print(f"{len(programs)} programs")

# --- INIT basic program from the librarian constant
java = urllib.request.urlopen(JAVA_URL, timeout=30).read().decode()
const = java[java.index("INIT_PATCH_BYTES"):]
const = const[:const.index("};")]
init_sysex = bytes(int(h, 16) for h in re.findall(r"0x([0-9a-fA-F]{2})", const))
init = unpack(init_sysex[6:-1])
print(f"init unpacked: {len(init)} bytes, name @107: {bytes(init[107:127])}")

# --- per-offset stats
print(f"\n{'off':>4} {'min':>4} {'max':>4} {'#dst':>4} {'init':>4}  notes")
for off in list(range(0, 107)) + list(range(127, 168)):
    vals = [p[off] for p in programs]
    lo, hi, nd = min(vals), max(vals), len(set(vals))
    flag = ""
    if hi <= 1:
        flag = "toggle?"
    elif hi <= 6:
        flag = f"select(0-{hi})?"
    elif lo >= 30 and hi <= 250 and lo > 20:
        flag = "bpm?"
    print(f"{off:>4} {lo:>4} {hi:>4} {nd:>4} {init[off]:>4}  {flag}")
