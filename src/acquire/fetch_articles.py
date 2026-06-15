"""Download Tier-3 emulation-target articles (the classic sounds the P6 is asked to imitate)
into data/raw/articles/. Saved as raw HTML; text extraction happens in the process stage.
"""
from util import RAW_DIR, polite_get, record, session

ARTICLES = [
    # (url, slug, emulation_target)
    ("https://www.soundonsound.com/techniques/synthesizing-strings-pwm-string-sounds",
     "sos_synth_secrets_47_pwm_strings", "string/pad synthesis"),
    ("https://www.soundonsound.com/techniques/synthesizing-strings-string-machines",
     "sos_synth_secrets_46_string_machines", "ensemble strings / string machines"),
    ("https://www.soundonsound.com/techniques/synthesizing-brass-instruments",
     "sos_synth_secrets_25_brass_theory", "brass synthesis theory (OB-style)"),
    ("https://www.soundonsound.com/techniques/brass-synthesis-minimoog",
     "sos_synth_secrets_26_minimoog_brass", "analog brass patch construction"),
    ("https://www.soundonsound.com/techniques/roland-sh101-arp-axxe-brass-synthesis",
     "sos_synth_secrets_27_sh101_brass", "brass on minimal architectures"),
    ("https://www.soundonsound.com/techniques/more-creative-synthesis-delays",
     "sos_synth_secrets_62_chorus_ensemble", "chorus/ensemble effects (Juno/Solina)"),
    ("https://www.soundonsound.com/techniques/creative-synthesis-delays",
     "sos_synth_secrets_61_delays", "delay/chorus fundamentals"),
    ("https://www.soundonsound.com/techniques/creating-usable-synth-bass",
     "sos_creating_usable_synth_bass", "synth bass construction"),
    ("https://www.florian-anwander.de/roland_string_choruses/",
     "anwander_roland_choruses", "Juno/Roland BBD chorus circuit analysis"),
    ("https://rolandcorp.com.au/blog/roland-icon-series-juno-106-synthesizer",
     "roland_icon_juno106", "Juno-106 character / chorus"),
    ("https://www.musicradar.com/tuition/tech/how-to-make-a-van-halen-jump-style-synth-sound-213604",
     "musicradar_jump_ob_brass", "Oberheim OB-Xa brass (Jump)"),
    ("https://www.musicradar.com/how-to/minimoog-analogue-bass",
     "musicradar_minimoog_bass", "classic Moog bass patch"),
    ("https://www.musicradar.com/how-to/recreate-thriller-synth-minimoog",
     "musicradar_thriller_bass", "Thriller Moog bass patch"),
    ("https://www.synthtopia.com/content/2020/12/14/sequential-prophet-5-vs-prophet-6-the-definitive-comparison/",
     "synthtopia_p5_vs_p6_definitive", "Prophet-5 vs Prophet-6 differences"),
    ("https://www.synthtopia.com/content/2020/11/30/prophet-5-prophet-10-rev4-vs-prophet-6-blind-comparison/",
     "synthtopia_p5_vs_p6_blind", "Prophet-5 vs Prophet-6 blind A/B"),
    ("https://www.syntorial.com/preset-recipe/van-halen-jump-brass/",
     "syntorial_jump_brass", "Oberheim brass recipe"),
]


def main() -> None:
    out_dir = RAW_DIR / "articles"
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = session()
    failures = []
    for url, slug, target in ARTICLES:
        dest = out_dir / f"{slug}.html"
        if dest.exists():
            print(f"skip (exists): {slug}")
            continue
        try:
            resp = polite_get(sess, url, min_interval=2.0)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001 - log and continue, partial corpus is fine
            failures.append((slug, str(e)))
            print(f"FAILED: {slug}: {e}")
            continue
        dest.write_text(resp.text, encoding="utf-8")
        record(f"articles/{slug}.html", url, emulation_target=target)
        print(f"saved: {slug} ({len(resp.text)} chars)")
    if failures:
        print(f"\n{len(failures)} failures: {[f[0] for f in failures]}")


if __name__ == "__main__":
    main()
