"""Render the cross-synth translation table into retrieval chunks (v2 Phase E, D-026).

One chunk per source synth from data/knowledge/synth_map.yaml. Caveat rows are rendered
prominently (anti-claims are first-class — the v1 bake-off judge once invented a ladder
filter; these chunks are where that error becomes impossible).

Usage: python -X utf8 src/process/chunk_translation.py
"""
import yaml

from common import PROCESSED_DIR, ROOT, make_chunk, write_jsonl

MAP_FILE = ROOT / "data" / "knowledge" / "synth_map.yaml"
SOURCE_URL = "data/knowledge/synth_map.yaml"


def render(key: str, e: dict) -> str:
    lines = [f"Translating the {key.replace('-', ' ').title()} "
             f"({', '.join(str(a) for a in e.get('aliases', []))}) "
             "to the Sequential Prophet-6."]
    lines.append(f"Source character: {e['character']}.")
    lines.append("How to realize it on the Prophet-6:")
    for r in e["p6_realization"]:
        lines.append(f"- {' '.join(r.split())}")
    if e.get("caveats"):
        lines.append("Important caveats (what the Prophet-6 does NOT do):")
        for c in e["caveats"]:
            lines.append(f"- {' '.join(c.split())}")
    lines.append("Sources: " + "; ".join(e.get("cite", [])))
    return "\n".join(lines)


def main() -> None:
    table = yaml.safe_load(MAP_FILE.read_text(encoding="utf-8"))
    chunks = []
    for key, e in table.items():
        c = make_chunk(chunk_id=f"translation::{key}", text=render(key, e),
                       source_type="translation", source_id=key,
                       source_url=SOURCE_URL, section=key)
        chunks.append(c)
    write_jsonl(PROCESSED_DIR / "chunks_translation.jsonl", chunks)
    print(f"chunks_translation.jsonl: {len(chunks)} chunks")
    print("\nsample:\n" + chunks[0]["text"][:600])


if __name__ == "__main__":
    main()
