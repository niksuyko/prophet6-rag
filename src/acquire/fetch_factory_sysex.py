"""Download official Prophet-6 program banks + preset lists (v2 plan, Phase B step 2).

All files are hosted and freely distributed by Sequential on the public support pages
(licensing register, D-022: official + freely distributed; decoded parameter data is
private-corpus-only out of caution; preset-name lists are public documents).

Usage: python -X utf8 src/acquire/fetch_factory_sysex.py
"""
from util import RAW_DIR, polite_get, record, session

FILES = [
    ("https://sequential.com/wp-content/uploads/2015/07/P6-Factory-Programs-ReadMe.zip",
     "p6_factory_programs.zip", "official factory program banks (sysex) + readme"),
    ("https://sequential.com/wp-content/uploads/2015/06/Prophet-6-Factory-Presets.pdf",
     "p6_factory_presets_list.pdf", "official factory preset name/category list"),
    ("https://sequential.com/wp-content/uploads/2015/09/Prophet6_OMOM_Sounds.zip",
     "p6_omom_sounds.zip", "official bonus bank: OMOM sounds (sysex)"),
    ("https://sequential.com/wp-content/uploads/2015/09/OMOM-Prophet-6-Presets-List.pdf",
     "p6_omom_presets_list.pdf", "official OMOM preset name list"),
]


def main() -> None:
    out_dir = RAW_DIR / "patches"
    out_dir.mkdir(parents=True, exist_ok=True)
    sess = session()
    for url, filename, note in FILES:
        dest = out_dir / filename
        if dest.exists():
            print(f"skip (exists): {filename}")
            continue
        resp = polite_get(sess, url, min_interval=2.0)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        record(f"patches/{filename}", url, note=note)
        print(f"saved: {filename} ({len(resp.content)} bytes)")


if __name__ == "__main__":
    main()
