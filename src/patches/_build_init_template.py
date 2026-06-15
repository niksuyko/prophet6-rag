"""One-time: build data/patches/init_template.json — the INIT 'Basic Program' carrier
(full 1024 data bytes) the encoder overwrites mapped offsets into (D-030).

Primary source: the eclewlow/Prophet6SoundLibrarian INIT_PATCH_BYTES constant (a real
P6 INIT program dump). Fallback if offline: a local factory patch with its sequencer
region blanked.

Usage: python -X utf8 src/patches/_build_init_template.py
"""
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "patches"))
from decode_sysex import split_messages, unpack  # noqa: E402

OUT = ROOT / "data" / "patches" / "init_template.json"
JAVA_URL = ("https://raw.githubusercontent.com/eclewlow/Prophet6SoundLibrarian/main/"
            "src/com/eclewlow/sequential/Prophet6SysexPatch.java")


def from_librarian() -> list[int]:
    java = urllib.request.urlopen(JAVA_URL, timeout=30).read().decode()
    const = java[java.index("INIT_PATCH_BYTES"):]
    const = const[:const.index("};")]
    sysex = bytes(int(h, 16) for h in re.findall(r"0x([0-9a-fA-F]{2})", const))
    data = unpack(sysex[6:-1])  # program dump: F0 01 2D 02 bank prog <packed> F7
    assert len(data) == 1024, len(data)
    return list(data)


def from_factory() -> list[int]:
    with zipfile.ZipFile(ROOT / "data/raw/patches/p6_factory_programs.zip") as z:
        blob = z.read(next(n for n in z.namelist()
                           if n.endswith(".syx") and not n.startswith("__MACOSX")))
    data = bytearray(unpack(split_messages(blob)[0][6:-1]))
    for i in range(128, 1024):  # blank sequencer region so the carrier is neutral
        data[i] = 0
    data[55] = 0  # seq on/off off
    return list(data)


def main() -> None:
    try:
        data = from_librarian()
        src = "librarian INIT"
    except Exception as e:
        print(f"librarian fetch failed ({e}); using factory carrier", flush=True)
        data = from_factory()
        src = "factory-000 (seq blanked)"
    OUT.write_text(json.dumps(data), encoding="utf-8")
    name = bytes(data[107:127]).decode("ascii", "replace")
    print(f"wrote {OUT.name} from {src}: {len(data)} bytes, name region {name!r}")


if __name__ == "__main__":
    main()
