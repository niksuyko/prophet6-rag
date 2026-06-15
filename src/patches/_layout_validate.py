"""Validate candidate byte-layout assignments via name-implied settings + histograms."""
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "patches"))
from decode_sysex import split_messages, unpack

progs = {}  # name -> data
order = []
for zname, src in (("p6_factory_programs.zip", "factory"), ("p6_omom_sounds.zip", "omom")):
    with zipfile.ZipFile(ROOT / "data/raw/patches" / zname) as z:
        blob = z.read(next(n for n in z.namelist()
                           if n.endswith(".syx") and not n.startswith("__MACOSX")))
    for msg in split_messages(blob):
        if msg[3] != 0x02:
            continue
        d = unpack(msg[6:-1])
        name = bytes(d[107:127]).decode("ascii", "replace").strip()
        key = f"{src}:{msg[4] * 100 + msg[5]:03d} {name}"
        progs[key] = d
        order.append(key)

def show(key_sub, offs):
    for k, d in progs.items():
        if key_sub.lower() in k.lower():
            print(f"  {k}: " + " ".join(f"[{o}]={d[o]}" for o in offs))

print("== sync-named patches (expect [11]=1 if 11=osc1.sync; [13]=osc2.low_freq)")
for n in ("Sync", "ZizzWub"):
    show(n, [11, 12, 13])
print("== unison-named (expect [84]=1, [85] voices)")
for n in ("In Unison", "Monster Mass", "Thick Low"):
    show(n, [84, 85, 86])
print("== noise-heavy names (expect [10] high)")
for n in ("Hi Hat", "Noiz Toyz", "Surf"):
    show(n, [7, 8, 9, 10])
print("== wide/pan names (expect [14] high if 14=pan_spread)")
for n in ("WideAndFurry", "WideMetalDrone", "Galactic Pad"):
    show(n, [14, 27, 31])
print("== arp-named (expect [91]=1; Random Arp -> [89]=3?)")
for n in ("Droid Arp", "Random Arp", "Baila Italo Arp", "ReedyArpeggio"):
    show(n, [89, 90, 91, 92, 87])
print("== S&H / random LFO names (expect [62]=4)")
for n in ("S&H", "Random Analog", "Quivering"):
    show(n, [59, 61, 62, 63, 64, 65, 66, 67, 68, 69])
print("== FM names (expect [78]!=127, [79]=1)")
for n in ("FM Bass", "FM Asteroids", "Terrormin"):
    show(n, [77, 78, 79, 80, 81, 82, 83])
print("== pad names: env blocks [35-42] (long attack somewhere)")
for n in ("Sadness Pad", "Evoque Pad", "Strong Pad", "Hold Me Pad"):
    show(n, list(range(35, 43)))
print("== pluck/perc names (short attack, low sustain)")
for n in ("Portage Plucks", "Snappy", "DampWoodblock", "Plucko"):
    show(n, list(range(35, 43)))
print("== glide-named (expect [16]=1, [18]>0)")
for n in ("Glide Belly", "Rezoglide", "Galloping"):
    show(n, [15, 16, 17, 18])
print("== distortion-named (expect [58] high)")
for n in ("ScumSlinger", "Dist Octaves", "ClarinetOverdrive", "Sizzled"):
    show(n, [58])
print("== effects-heavy names: fx block 44-57")
for n in ("Organ on Tape", "Old Record", "PhazeDrizzle", "Dolby Bass"):
    show(n, list(range(44, 58)))

print("\n== histograms of ambiguous offsets")
for off in (2, 14, 17, 27, 31, 54, 55, 56, 57, 60, 98, 105, 106):
    c = Counter(d[off] for d in progs.values())
    top = ", ".join(f"{v}:{n}" for v, n in c.most_common(8))
    print(f"  [{off:>3}] {top}")
