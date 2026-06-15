"""Fetch the complete Sound on Sound Synth Secrets series (v2 plan, Phase C step 1).

Slugs enumerated from SoS's own series index (soundonsound.com/synthesizers/synth-secrets,
pages 0-3, crawled 2026-06-12). Same raw-HTML treatment as the v1 article pipeline; the
v1 chunker (chunk_articles.py) handles SoS HTML already. Licensing register (D-025):
publicly served by the publisher, fetched politely from the source, raw HTML stored
privately like every v1 article.

Usage: python -X utf8 src/acquire/fetch_synthsecrets.py
"""
from util import RAW_DIR, polite_get, record, session

SLUGS = [
    "whats-sound", "secret-big-red-button", "modifiers-controllers",
    "filters-phase-relationships", "further-filters", "responses-resonance",
    "envelopes-gates-triggers", "more-about-envelopes", "introduction-vcas",
    "modulation", "amplitude-modulation", "introduction-frequency-modulation",
    "more-frequency-modulation", "introduction-additive-synthesis",
    "introducing-polyphony", "priorities-triggers", "duophony",
    "polyphony-digital-synths", "introduction-esps-vocoders", "formant-synthesis",
    "sample-hold-sample-rate-converters-1", "sample-hold-sample-rate-converters-2",
    "creative-synthesis-delays", "more-creative-synthesis-delays",
    "analogue-digital-effects", "springs-plates-buckets-physical-modelling",
    "synthesizing-strings-pwm-string-sounds", "synthesizing-strings-string-machines",
    "synthesizing-bowed-strings-violin-family", "practical-bowed-string-synthesis",
    "practical-bowed-string-synthesis-continued", "articulation-bowed-string-synthesis",
    "synthesizing-plucked-strings", "theoretical-acoustic-guitar-patch",
    "final-attempt-synthesize-guitars", "synthesizing-brass-instruments",
    "brass-synthesis-minimoog", "roland-sh101-arp-axxe-brass-synthesis",
    "synthesizing-wind-instruments", "synthesizing-simple-flutes",
    "practical-flute-synthesis", "synthesizing-pan-pipes", "physics-percussion",
    "synthesizing-percussion", "synthesizing-drums-bass-drum",
    "practical-bass-drum-synthesis", "synthesizing-drums-snare-drum",
    "practical-snare-drum-synthesis", "analysing-metallic-percussion",
    "synthesizing-realistic-cymbals", "practical-cymbal-synthesis",
    "synthesizing-cowbells-claves", "practical-percussion-synthesis-timpani",
    "synthesizing-bells", "synthesizing-tonewheel-organs-part-1",
    "synthesizing-tonewheel-organs-part-2", "synthesizing-hammond-organ-effects",
    "synthesizing-rest-hammond-organ-part-1", "synthesizing-rest-hammond-organ-part-2",
    "synthesizing-pianos", "synthesizing-acoustic-piano-roland-jx10",
    "synthesizing-acoustic-pianos-roland-jx10-1102",
    "synthesizing-acoustic-pianos-roland-jx10-part-3",
    "synth-secrets-all-63-parts-sound-on-sound",
]
BASE = "https://www.soundonsound.com/techniques/"


def main() -> None:
    out_dir = RAW_DIR / "articles"
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = session()
    fetched = skipped = failed = 0
    for slug in SLUGS:
        dest = out_dir / f"sos_{slug}.html"
        if dest.exists():
            skipped += 1
            continue
        resp = polite_get(sess, BASE + slug, min_interval=2.0)
        if resp.status_code != 200:
            print(f"FAIL [{resp.status_code}]: {slug}", flush=True)
            failed += 1
            continue
        dest.write_bytes(resp.content)
        record(f"articles/sos_{slug}.html", BASE + slug, note="Synth Secrets series (v2 C)")
        fetched += 1
        print(f"saved: {slug}", flush=True)
    print(f"\nfetched {fetched}, skipped {skipped}, failed {failed} of {len(SLUGS)}")


if __name__ == "__main__":
    main()
