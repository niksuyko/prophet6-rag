"""Append bucket-5 'recreate' probe entries to golden_set_v2.jsonl (v2 Phase A step 3 /
Phase B). Each names a real factory/OMOM patch; param_targets drive eval/patch_accuracy.py
(C6) and expected_targets make the patch chunk itself the retrieval target.

Queries are phrased as a player would ask, not as file lookups. Run AFTER
build_golden_v2.py (which rewrites the file).

Usage: python -X utf8 src/evaluate/append_b5.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "golden_set_v2.jsonl"

# (patch id, query phrased like a real ask, category note)
PROBES = [
    ("p6-factory-000", "classic poly brass stab like the Prophet-6 factory 'Brassed Off' preset", "brass"),
    ("p6-factory-002", "thick low analog brass patch", "brass"),
    ("p6-factory-004", "dark octave bass on the Prophet 6", "bass"),
    ("p6-factory-005", "warm evolving pad with slow attack and PWM movement", "pad"),
    ("p6-factory-007", "deep hard-sync lead patch", "lead"),
    ("p6-factory-013", "thick low strings, ensemble style", "strings"),
    ("p6-factory-017", "slow sample-and-hold pad with random filter movement", "pad"),
    ("p6-factory-022", "old school house organ sound", "keys"),
    ("p6-factory-024", "solid round synth bass", "bass"),
    ("p6-factory-031", "hi-hat percussion sound from noise", "percussion"),
    ("p6-factory-055", "classic string synth ensemble patch", "strings"),
    ("p6-factory-059", "housey chord stab", "keys"),
    ("p6-factory-061", "airy bell tones", "keys"),
    ("p6-factory-086", "vintage solid bass like an old Prophet", "bass"),
    ("p6-factory-148", "FM-style bass using poly mod", "bass"),
    ("p6-omom-014", "church organ on an analog poly", "keys"),
    ("p6-omom-017", "moon choir vocal pad", "pad"),
    ("p6-omom-149", "screaming sync lead for solos", "lead"),
]


def main() -> None:
    existing = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines()
                if l.strip()] if OUT.exists() else []
    existing = [e for e in existing if e["bucket"] != 5]  # idempotent re-append
    entries = []
    for i, (pid, query, note) in enumerate(PROBES, 1):
        ref = json.loads((ROOT / "data" / "patches" / f"{pid}.json")
                         .read_text(encoding="utf-8"))
        entries.append({
            "id": f"v2-b5-q{i:02d}", "query": query, "bucket": 5,
            "expected_targets": [{"source_type": "patch", "match": pid}],
            "param_targets": [pid],
            "phrasing": "synthetic recreate-probe (D-022); names imply the reference patch",
            "notes": f"category={note} ref_name={ref['name']!r}",
        })
    with OUT.open("w", encoding="utf-8") as f:
        for e in existing + entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"golden_set_v2.jsonl: {len(existing)} existing + {len(entries)} B5 probes")


if __name__ == "__main__":
    main()
