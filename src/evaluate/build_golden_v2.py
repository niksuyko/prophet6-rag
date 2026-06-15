"""Build the golden set v2 draft from real r/synthrecipes phrasings (v2 plan, Phase A).

Selection: recipe-shaped, answerable threads (comments >= 3, score >= 3, descriptive
title), classified into coverage-matrix cells by keyword; sampled to spread across cells;
cross-synth asks become bucket 3. Output is a DRAFT for curation — the builder gate
(provisional per D-021) is a human pass over eval/golden_set_v2.jsonl before it's final.

Usage: python -X utf8 src/evaluate/build_golden_v2.py [n_b2] [n_b3]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUBS = ROOT / "data" / "raw" / "synthrecipes" / "submissions.jsonl"
OUT = ROOT / "eval" / "golden_set_v2.jsonl"

FAMILY_KW = {
    "bass": r"\bbass(?:line)?\b|\breese\b|\bsub\b|\b303\b|\bacid\b",
    "lead": r"\blead\b|\bsolo\b|\bsync lead\b",
    "pad": r"\bpad\b|\bambient\b|\bwash\b|\batmosphere\b",
    "strings": r"\bstrings?\b|\bsolina\b|\bensemble\b|\borchestr",
    "brass": r"\bbrass\b|\bhorns?\b|\bstabs?\b",
    "keys": r"\bkeys?\b|\borgan\b|\bpiano\b|\bclav\b|\brhodes\b|\bwurli|\bbells?\b|\be-?piano\b",
    "pluck": r"\bplucks?\b|\bkarplus\b|\bkoto\b|\bharp\b",
    "percussion": r"\bkick\b|\bsnare\b|\bhi-?hats?\b|\btoms?\b|\bdrums?\b|\bperc(?:ussion)?\b|\bzap\b",
    "fx_drone": r"\bdrone\b|\briser\b|\btexture\b|\bsound design\b|\bsfx\b|\bnoise\b|\bsweep\b",
    "arp_seq": r"\barp(?:eggio|eggiator)?\b|\bsequence\b|\bsequencer\b|\bostinato\b",
}
CHARACTER_KW = {
    "warm": r"\bwarm\b|\bmellow\b|\bsoft\b|\bsmooth\b|\bround\b",
    "aggressive": r"\baggressive\b|\bhard\b|\bdistort|\bgritty\b|\bdirty\b|\bscream|\bharsh\b",
    "vintage": r"\bvintage\b|\bretro\b|\b[6789]0s\b|\banalog(?:ue)? feel\b|\bold school\b",
    "glassy": r"\bglass|\bbell-?like\b|\bshimmer|\bcrystal|\bdigital\b|\bfm\b",
    "evolving": r"\bevolv|\bmovement\b|\bmorph|\bslowly\b|\bmotion\b|\bbreathing\b|\bpwm\b",
    "fat": r"\bfat\b|\bthick\b|\bhuge\b|\bmassive\b|\bwide\b|\bunison\b|\bbig\b",
    "clean": r"\bclean\b|\bprecise\b|\btight\b|\bmodern\b|\bcrisp\b",
    "emulative": r"\bsound like\b|\brecreate\b|\bemulate\b|\bsimilar to\b|\bhow (?:did|does|do)\b.*\bget\b",
}
CROSS_SYNTH = (r"\bjuno\b|\bjupiter\b|\bmoog\b|\bminimoog\b|\bdx-?7\b|\bob-?\d|\boberheim\b|"
               r"\bcs-?80\b|\bsh-?101\b|\btb-?303\b|\bprophet[- ]?5\b|\bpoly ?six\b|\bms-?20\b|"
               r"\bjx-?\d|\bd-?50\b|\bm1\b|\barp odyssey\b|\bpolymoog\b|\bvirus\b|\bmicrokorg\b")
BAD_TITLE = (r"^\s*(how (?:do|would|to) (?:i|you) )?(re)?(make|create|get) (this|that)\b|"
             r"\[(deleted|removed)\]|^help\b|\bthis sound\??$|\bsounds? in (this|the) (song|track)\b")


def classify(text: str, kw_map: dict) -> list[str]:
    return [name for name, pat in kw_map.items() if re.search(pat, text, re.I)]


def main() -> None:
    n_b2 = int(sys.argv[1]) if len(sys.argv) > 1 else 55
    n_b3 = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    subs = [json.loads(l) for l in SUBS.read_text(encoding="utf-8").splitlines()]
    # reachability filter (D-015 applied at authoring time): only threads whose
    # answers actually survived chunking can be targets
    chunks_file = ROOT / "data" / "chunks" / "chunks.jsonl"
    if chunks_file.exists():
        reachable = {json.loads(l)["source_id"] for l in
                     chunks_file.read_text(encoding="utf-8").splitlines()}
        subs = [s for s in subs if s["id"] in reachable]
        print(f"{len(subs)} submissions have chunked answers in the corpus")
    cands = []
    for s in subs:
        title = (s["title"] or "").strip()
        if (s.get("num_comments") or 0) < 3 or (s.get("score") or 0) < 3:
            continue
        if len(title) < 22 or re.search(BAD_TITLE, title, re.I):
            continue
        if not re.search(r"how|recipe|recreate|make|create|patch|achiev|emulat|sound", title, re.I):
            continue
        blob = title + " " + (s.get("link_flair_text") or "")
        fams = classify(blob, FAMILY_KW)
        chars = classify(blob, CHARACTER_KW)
        if not fams:
            continue
        cands.append({"id": s["id"], "title": title, "score": s["score"],
                      "comments": s["num_comments"], "fams": fams, "chars": chars,
                      "cross": bool(re.search(CROSS_SYNTH, blob, re.I))})
    print(f"{len(cands)} candidates from {len(subs)} submissions")

    # spread selection across (family, character) cells, highest engagement first
    cands.sort(key=lambda c: -(c["score"] + 2 * c["comments"]))
    cell_count: dict[tuple, int] = {}
    chosen_b2, chosen_b3 = [], []

    def cell_load(c):
        cells = [(f, ch) for f in c["fams"] for ch in (c["chars"] or ["(none)"])]
        return min(cell_count.get(cell, 0) for cell in cells), cells

    for is_cross, bucket_list, target_n in ((True, chosen_b3, n_b3), (False, chosen_b2, n_b2)):
        pool = [c for c in cands if c["cross"] == is_cross]
        while pool and len(bucket_list) < target_n:
            pool.sort(key=lambda c: cell_load(c)[0])
            pick = pool.pop(0)
            bucket_list.append(pick)
            for cell in cell_load(pick)[1]:
                cell_count[cell] = cell_count.get(cell, 0) + 1

    with OUT.open("w", encoding="utf-8") as f:
        for i, c in enumerate(chosen_b2, 1):
            f.write(json.dumps({
                "id": f"v2-b2-q{i:02d}", "query": c["title"], "bucket": 2,
                "expected_targets": [{"source_type": "reddit", "match": c["id"]}],
                "phrasing": "verbatim r/synthrecipes title",
                "notes": f"families={','.join(c['fams'])} chars={','.join(c['chars']) or '-'}"
            }) + "\n")
        for i, c in enumerate(chosen_b3, 1):
            f.write(json.dumps({
                "id": f"v2-b3-q{i:02d}", "query": c["title"], "bucket": 3,
                "expected_targets": [{"source_type": "reddit", "match": c["id"]}],
                "phrasing": "verbatim r/synthrecipes title (cross-synth)",
                "notes": f"families={','.join(c['fams'])} chars={','.join(c['chars']) or '-'}"
            }) + "\n")
    print(f"wrote {len(chosen_b2)} B2 + {len(chosen_b3)} B3 -> {OUT}")
    print("cells covered:", len(cell_count))


if __name__ == "__main__":
    main()
