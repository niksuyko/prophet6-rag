"""Render decoded patches (data/patches/*.json) into retrieval chunks (v2 Phase B step 3).

Each patch becomes one chunk whose text is a prose rendering of its non-INIT settings,
written with sound-design vocabulary so recipe queries can find it via BM25 + embeddings.
Every adjective is derived from parameter values (honest rendering — no invented traits);
the structured params stay in data/patches/, the chunk carries the searchable surface.

The category and trait tags are also what the Phase-F coverage report counts.

Usage: python -X utf8 src/process/chunk_patches.py
"""
import json
import sys
from pathlib import Path

from common import PROCESSED_DIR, ROOT, make_chunk, write_jsonl

sys.path.insert(0, str(ROOT / "src" / "ui"))
from patch_schema import INIT_PATCH  # noqa: E402

PATCH_DIR = ROOT / "data" / "patches"
SOURCE_URL = "https://sequential.com/support/download/prophet-6-sounds/"

NAME_CATEGORIES = [  # (category, name keywords)
    ("bass", ["bass", "reese", "sub ", "acid", "303"]),
    ("pad", ["pad", "wash", "atmos", "ambient", "drift", "cloud"]),
    ("strings", ["string", "solina", "arco", "orch", "cello", "violin"]),
    ("brass", ["brass", "horn", "stab", "fanfare", "tuba", "trump"]),
    ("keys", ["organ", "piano", "pno", "clav", "key", "wurli", "rhodes", "tine",
              "harpsi", "bell", "celest", "marimba", "kalimba", "vibra"]),
    ("lead", ["lead", "solo", "sync l", "whistle", "flute", "voice", "vox", "choir"]),
    ("pluck", ["pluck", "koto", "harp", "pizz", "plink", "ploink", "plonk"]),
    ("percussion", ["drum", "kick", "snare", "hat", "tom", "perc", "block", "zap",
                    "clap", "tympani", "tempani"]),
    ("arp_seq", ["arp", "seq", "pulsator", "ostinato"]),
    ("fx_drone", ["drone", "riser", "sweep", "noise", "sfx", "alarm", "siren",
                  "texture", "wind", "space", "ufo", "alien"]),
]


def category_of(name: str, p: dict) -> str:
    low = name.lower()
    for cat, kws in NAME_CATEGORIES:
        if any(k in low for k in kws):
            return cat
    # param heuristics when the name is abstract
    if p["arp.on"]:
        return "arp_seq"
    if p["aenv.attack"] > 70 and p["aenv.sustain"] > 80:
        return "pad"
    if p["aenv.sustain"] < 25 and p["aenv.decay"] < 70:
        return "pluck"
    if p["unison.on"] and p["osc1.frequency"] <= 24:
        return "bass"
    return "lead"


def traits_of(p: dict) -> list[str]:
    t = []
    if p["lpf.cutoff"] < 100 and not p["dist.amount"]:
        t.append("warm")
    if p["dist.amount"] > 40 or p["lpf.resonance"] > 190 or p["osc1.sync"]:
        t.append("aggressive")
    if p["slop.amount"] > 8 or p["fxa.type"] == "bbd-delay" or p["fxb.type"] == "bbd-delay":
        t.append("vintage")
    if p["osc1.sync"] or (p["hpf.cutoff"] > 40 and p["lpf.cutoff"] > 140):
        t.append("glassy")
    if (p["lfo.initial_amount"] > 30 or abs(p["pmod.filt_env"]) > 25
            or abs(p["pmod.osc2"]) > 25 or p["lfo.dest_pw12"]):
        t.append("evolving")
    if p["unison.on"] or abs(p["osc2.fine"]) > 8 or p["mixer.sub_octave"] > 60:
        t.append("fat")
    if (not p["fx.on"] and p["slop.amount"] == 0 and not p["dist.amount"]
            and "aggressive" not in t and "vintage" not in t):
        t.append("clean")
    return t


def _osc_desc(p: dict, n: int) -> str:
    shape = p[f"osc{n}.shape"]
    bits = [shape]
    if shape in ("pulse", "saw-pulse"):
        pw = p[f"osc{n}.pulse_width"]
        if abs(pw - 127) < 12:
            bits.append("square-ish width")
        else:
            bits.append("narrow pulse" if pw < 64 or pw > 190 else "off-center pulse width")
    if n == 2:
        fine = p["osc2.fine"]
        if abs(fine) > 4:
            bits.append(f"detuned {fine:+d}")
        if p["osc2.low_freq"]:
            bits.append("in low-frequency mode (extra LFO source)")
        if not p["osc2.keyboard"]:
            bits.append("keyboard tracking off (drone/fixed pitch)")
    return f"osc {n} {', '.join(bits)}"


def render(entry: dict) -> str:
    p = entry["params"]
    name, source = entry["name"], entry["source"]
    cat = category_of(name, p)
    traits = traits_of(p)
    lines = []
    bank_name = "factory bank" if source == "factory" else "official OMOM bonus bank"
    lines.append(f"Prophet-6 {bank_name} patch \"{name}\" (preset {entry['id'].split('-')[-1]}). "
                 f"Category: {cat.replace('_', '/')}."
                 + (f" Character: {', '.join(traits)}." if traits else ""))
    if entry["id"].startswith("p6-factory-4"):
        lines.append("Part of the factory Prophet-5 recreation bank: classic Prophet-5 "
                     "presets recreated on the Prophet-6.")

    mix = [(label, p[f"mixer.{key}"]) for label, key in
           [("osc 1", "osc1"), ("osc 2", "osc2"), ("sub octave", "sub_octave"),
            ("noise", "noise")] if p[f"mixer.{key}"] > 5]
    osc_bits = [_osc_desc(p, n) for n in (1, 2)
                if p[f"mixer.osc{n}"] > 5 or (n == 2 and (abs(p["pmod.osc2"]) > 10))]
    if p["osc1.sync"]:
        osc_bits.append("oscillator hard sync ON (osc 1 synced to osc 2)")
    interval = p["osc2.frequency"] - p["osc1.frequency"]
    if interval and p["mixer.osc2"] > 5:
        osc_bits.append(f"oscillators {abs(interval)} semitones apart")
    osc_text = "; ".join(osc_bits) if osc_bits else \
        "oscillator levels down (noise/sub or filter self-oscillation provides the tone)"
    mix_text = ", ".join(f"{l} {v}" for l, v in mix) if mix else "all levels at zero"
    lines.append(f"Oscillators: {osc_text}. Mixer: {mix_text}.")

    f = []
    cut = p["lpf.cutoff"]
    f.append("low-pass cutoff " + ("wide open" if cut > 150 else
             f"{cut}/164" + (" (dark)" if cut < 60 else "")))
    if p["lpf.resonance"] > 20:
        f.append(f"resonance {p['lpf.resonance']}/255"
                 + (" (near self-oscillation)" if p["lpf.resonance"] > 200 else ""))
    if p["lpf.env_amount"]:
        f.append(f"filter env amount {p['lpf.env_amount']:+d}")
    if p["lpf.velocity"]:
        f.append("velocity to filter")
    if p["lpf.keyboard"] != "off":
        f.append(f"keyboard tracking {p['lpf.keyboard']}")
    if p["hpf.cutoff"] > 5:
        f.append(f"high-pass cutoff {p['hpf.cutoff']} (thins low end)")
    lines.append("Filters: " + ", ".join(f) + ".")

    fe = (f"filter env A{p['fenv.attack']} D{p['fenv.decay']} "
          f"S{p['fenv.sustain']} R{p['fenv.release']}")
    ae = (f"amp env A{p['aenv.attack']} D{p['aenv.decay']} "
          f"S{p['aenv.sustain']} R{p['aenv.release']}")
    env_words = []
    if p["aenv.attack"] > 70:
        env_words.append("slow swelling attack")
    elif p["aenv.attack"] < 5 and p["aenv.sustain"] < 30:
        env_words.append("percussive envelope")
    if p["aenv.release"] > 90:
        env_words.append("long release tail")
    lines.append("Envelopes: " + fe + "; " + ae
                 + ("; " + ", ".join(env_words) if env_words else "") + ".")

    m = []
    if p["lfo.initial_amount"] > 5 or any(p[f"lfo.dest_{d}"] for d in
                                          ("freq1", "freq2", "pw12", "amp", "lp", "hp")):
        dests = [d for d in ("freq1", "freq2", "pw12", "amp", "lp", "hp")
                 if p[f"lfo.dest_{d}"]]
        m.append(f"LFO {p['lfo.shape']} (rate {p['lfo.frequency']}, "
                 f"amount {p['lfo.initial_amount']}) to {'+'.join(dests) or 'mod wheel only'}"
                 + (" — PWM movement" if "pw12" in dests else ""))
    if abs(p["pmod.filt_env"]) > 10 or abs(p["pmod.osc2"]) > 10:
        dests = [d for d in ("freq1", "shape1", "pw1", "lp", "hp")
                 if p[f"pmod.dest_{d}"]]
        m.append(f"Poly Mod filt-env {p['pmod.filt_env']:+d} / osc2 {p['pmod.osc2']:+d} "
                 f"to {'+'.join(dests) or 'none'}"
                 + (" — FM character" if abs(p["pmod.osc2"]) > 60 and "freq1" in dests else ""))
    if abs(p["at.amount"]) > 10:
        dests = [d for d in ("freq1", "freq2", "lp", "hp", "amp", "lfo")
                 if p[f"at.dest_{d}"]]
        m.append(f"aftertouch {p['at.amount']:+d} to {'+'.join(dests) or 'none'}")
    if m:
        lines.append("Modulation: " + "; ".join(m) + ".")

    extra = []
    if p["unison.on"]:
        voices = ("chord-memory mode" if p["unison.voices"] == "chord"
                  else f"{p['unison.voices']} voices")
        extra.append(f"unison ON ({voices}, {p['unison.key_mode']} priority)")
    if p["slop.amount"] > 2:
        extra.append(f"slop {p['slop.amount']} (vintage oscillator drift)")
    if p["dist.amount"] > 5:
        extra.append(f"distortion {p['dist.amount']}")
    if p["glide.on"] and p["glide.rate"] > 0:
        extra.append(f"glide/portamento rate {p['glide.rate']} ({p['glide.mode']})")
    if p["misc.pan_spread"] > 20:
        extra.append(f"pan spread {p['misc.pan_spread']} (wide stereo)")
    if p["arp.on"]:
        extra.append(f"arpeggiator ON ({p['arp.mode']}, {p['arp.octaves']} oct, "
                     f"{p['clock.bpm']} BPM)")
    if p["fx.on"]:
        for slot in ("fxa", "fxb"):
            if p[f"{slot}.type"] != "off" and p[f"{slot}.mix"] > 0:
                extra.append(f"effect {slot[-1].upper()}: {p[f'{slot}.type']} "
                             f"(mix {p[f'{slot}.mix']})")
    if extra:
        lines.append("Performance/effects: " + "; ".join(extra) + ".")
    return "\n".join(lines)


def main() -> None:
    chunks = []
    for f in sorted(PATCH_DIR.glob("p6-*.json")):
        entry = json.loads(f.read_text(encoding="utf-8"))
        text = render(entry)
        c = make_chunk(chunk_id=f"patch::{entry['id']}", text=text, source_type="patch",
                       source_id=entry["id"], source_url=SOURCE_URL,
                       section=entry["name"])
        if "prophet-6" not in c["synths_mentioned"]:
            c["synths_mentioned"].append("prophet-6")
        chunks.append(c)
    write_jsonl(PROCESSED_DIR / "chunks_patches.jsonl", chunks)
    print(f"chunks_patches.jsonl: {len(chunks)} chunks "
          f"(mean {sum(c['n_tokens'] for c in chunks) // len(chunks)} tokens)")
    print("\nsample rendering:\n" + chunks[5]["text"])


if __name__ == "__main__":
    main()
