"""Reference-free patch-quality eval (decisions.md D-033) — three layers, ZERO hand-authored patches.

Why this exists: recall@5 measures *retrieval* (did a relevant chunk surface), not whether the
generated PATCH realizes the request. For the patch-creation mission that gap is the whole game
(see the "Nangs" case: recall@5 scores a HIT while the served chunks can't build the sound).
Authoring a gold patch per query doesn't scale and bakes in one builder's opinion, so every layer
here derives its ground truth automatically or needs no reference at all:

  A. RUBRIC    — auto-harvested from the curated cross-synth table (data/knowledge/synth_map.yaml).
                 Each synth's `p6_realization` lines name schema params; we extract them into
                 checkable assertions and score a patch's partial satisfaction. Covers
                 "Juno/Minimoog/..."-class queries. Auto-derived -> provisional, same ratification
                 status as the table itself (D-026). Cannot score a query no table entry names.
  B. JUDGE     — reference-free LLM judge: "does this patch plausibly achieve the description?"
                 Works on ANY query, including famous-song asks like Nangs. CAVEAT: the judge
                 cannot HEAR — it reasons over parameters, so it needs the same human spot-check
                 every judge in this project got (D-013).
  C. ROUNDTRIP — cycle consistency: render the generated patch to prose deterministically (reuses
                 chunk_patches.render — no API, no cheating), embed it and the query with the SAME
                 bge model, report cosine. Free and infinitely scalable. CAVEAT (the Part III
                 lesson): proves CONSISTENCY, not correctness — a cheap gross-failure tripwire, not
                 a quality certificate.

A metric only earns its place if it SEPARATES a matched patch from a mismatched one. `--selftest`
scores each query against its own patch and against the other queries' patches; a useful metric
makes the matched (diagonal) score beat the mismatched (off-diagonal) by a margin, reported as
numbers. If a layer can't separate them, it is noise and should not be trusted.

Usage:
  python -X utf8 eval/patch_quality.py --selftest             # discrimination validation (needs API)
  python -X utf8 eval/patch_quality.py "warm juno pad" "..."  # score specific queries (needs API)
  python -X utf8 eval/patch_quality.py --golden [file] [n]    # score a golden-set sample (needs API)
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("src", "src/ui", "src/retrieve", "src/process"):
    sys.path.insert(0, str(ROOT / sub))
import load_env  # noqa: E402,F401  (side effect: ANTHROPIC_API_KEY from .env)

from patch_schema import INIT_PATCH, PARAMS  # noqa: E402
from chunk_patches import render as render_patch  # noqa: E402  (deterministic patch->prose)

RESULTS_DIR = ROOT / "eval" / "results"
SYNTH_MAP = ROOT / "data" / "knowledge" / "synth_map.yaml"
JUDGE_MODEL = "claude-sonnet-4-6"


def resolve_full(changes: list[dict]) -> dict:
    """INIT + change list -> full 82-param state."""
    return {**INIT_PATCH, **{c["param"]: c["value"] for c in changes if c["param"] in PARAMS}}


# --------------------------------------------------------------------------------------
# Layer C — round-trip consistency (deterministic, free)
# --------------------------------------------------------------------------------------
def describe_patch(resolved: dict, name: str = "Generated") -> str:
    """Deterministic prose readout of a resolved patch, reusing the SAME renderer that
    produced the corpus's patch chunks. No API, no cheating (it never sees the query)."""
    entry = {"id": "gen-000", "name": name or "Generated", "source": "factory",
             "params": resolved}
    text = render_patch(entry)
    # drop the "factory bank patch ..." provenance preamble; keep Category/Character + facts
    return re.sub(r'^Prophet-6 [^.]*patch "[^"]*" \(preset \d+\)\. ', "", text)


def roundtrip_score(query: str, resolved: dict, name: str = "") -> float:
    """cosine( embed(query) , embed(deterministic description of the patch) ).
    Query side gets the BGE retrieval prefix; the description is embedded as a document,
    matching how corpus chunks were embedded."""
    from search import embed_query, _model
    desc = describe_patch(resolved, name)
    q = embed_query(query)
    d = _model().encode([desc], normalize_embeddings=True)[0]
    return float(q @ d)


# --------------------------------------------------------------------------------------
# Layer A — rubric auto-harvested from the cross-synth translation table
# --------------------------------------------------------------------------------------
_DIR_HIGH = re.compile(r"\b(high|full|max|maxed|up|generous|heavy|wide|strong|deep)\b", re.I)
_DIR_LOW = re.compile(r"\b(low|min|off|down|short|small|subtle|barely|restraint|0-5|0-\d)\b", re.I)
_PID = re.compile(r"([a-z]+\.[a-z0-9_]+)", re.I)
_EQ = re.compile(r"([a-z]+\.[a-z0-9_]+)\s*=\s*([a-z0-9\-]+)", re.I)


def _extract_asserts(line: str) -> list[tuple]:
    """Pull checkable assertions out of one p6_realization line. Honest auto-extraction:
    only fires on explicit schema param ids (`fxa.type=chorus`, `(lfo.dest_pw12)`,
    `mixer.sub_octave high`). Prose without a param id yields nothing — reported, not faked."""
    out, seen = [], set()
    for pid, val in _EQ.findall(line):
        if pid in PARAMS and pid not in seen:
            out.append(("eq", pid, val.lower())); seen.add(pid)
    for pid in _PID.findall(line):
        if pid not in PARAMS or pid in seen:
            continue
        seen.add(pid)
        p = PARAMS[pid]
        if p["type"] == "toggle":
            out.append(("true", pid, None))
        elif p["type"] in ("knob", "bipolar"):
            if _DIR_HIGH.search(line):
                out.append(("high", pid, None))
            elif _DIR_LOW.search(line):
                out.append(("low", pid, None))
            else:
                out.append(("active", pid, None))
        else:  # select named without '=' -> just expect it moved off INIT
            out.append(("active", pid, None))
    return out


def load_rubrics() -> dict:
    import yaml
    data = yaml.safe_load(SYNTH_MAP.read_text(encoding="utf-8"))
    rubrics = {}
    for synth, e in data.items():
        if not isinstance(e, dict):
            continue
        asserts = []
        for line in e.get("p6_realization", []) or []:
            asserts += _extract_asserts(str(line))
        rubrics[synth] = {
            "aliases": [synth] + [str(a).lower() for a in e.get("aliases", []) or []],
            "asserts": asserts,
            "character": e.get("character", ""),
        }
    return rubrics


def match_rubric(query: str, rubrics: dict) -> str | None:
    """Which table entry (if any) does this query name? Substring match on aliases.
    Returns None for queries no curated synth covers (e.g. 'Nangs') — an honest miss."""
    q = query.lower()
    for synth, r in rubrics.items():
        if any(re.search(r"\b" + re.escape(a) + r"\b", q) for a in r["aliases"]):
            return synth
    return None


def _check_assert(a: tuple, params: dict) -> bool:
    kind, pid, val = a
    cur, p, init = params[pid], PARAMS[pid], INIT_PATCH[pid]
    if kind == "eq":
        return str(cur).lower() == val
    if kind == "true":
        return cur is True
    if p["type"] in ("knob", "bipolar"):
        rng = p["max"] - p["min"]
        if kind == "high":
            return cur >= p["min"] + 0.55 * rng
        if kind == "low":
            return cur <= p["min"] + 0.45 * rng
        return cur != init  # "active"
    return cur != init


def rubric_score(resolved: dict, asserts: list[tuple]) -> tuple:
    if not asserts:
        return None, []
    detail = [(f"{a[0]} {a[1]}" + (f"={a[2]}" if a[2] else ""), _check_assert(a, resolved))
              for a in asserts]
    return round(sum(ok for _, ok in detail) / len(detail), 3), detail


# --------------------------------------------------------------------------------------
# Layer B — reference-free LLM judge
# --------------------------------------------------------------------------------------
JUDGE_SYS = (
    "You are an expert Prophet-6 sound designer grading whether a generated patch realizes a "
    "requested sound. You CANNOT hear it; reason ONLY from the parameter settings and standard "
    "subtractive-synthesis knowledge. Be skeptical and concrete — reward patches whose moves "
    "actually produce the requested character, penalize ones that contradict it or miss the "
    "defining move. Output a single JSON object, no prose outside it.")


def judge_score(query: str, patch: dict, model: str = JUDGE_MODEL) -> dict:
    import anthropic
    from generate_patch import _extract_json
    resolved = resolve_full(patch["changes"])
    moves = [{"param": c["param"], "value": c["value"]} for c in patch["changes"]]
    user = (
        f'Requested sound: "{query}"\n\n'
        f'Generated patch — deviations from INIT (param: value):\n{json.dumps(moves)}\n\n'
        f'Deterministic readout of the resulting patch:\n{describe_patch(resolved, patch.get("patch_name", ""))}\n\n'
        'Does this patch plausibly achieve the requested sound on a Prophet-6?\n'
        'Output JSON: {"score": <int 1-5, 5=excellent match, 3=partial, 1=contradicts>, '
        '"verdict": "<one sentence>", "missing": ["<defining move absent or wrong>", ...]}')
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=600, temperature=0,
                                 system=JUDGE_SYS,
                                 messages=[{"role": "user", "content": user}])
    try:
        out = _extract_json(msg.content[0].text)
        out["score"] = int(out.get("score", 0))
    except Exception as e:  # noqa: BLE001
        out = {"score": 0, "verdict": f"[judge parse error: {e}]", "missing": []}
    return out


# --------------------------------------------------------------------------------------
# Scoring a query + driver
# --------------------------------------------------------------------------------------
def score_query(query: str, patch: dict, rubrics: dict, do_judge: bool = True) -> dict:
    resolved = resolve_full(patch["changes"])
    synth = match_rubric(query, rubrics)
    rub, rub_detail = rubric_score(resolved, rubrics[synth]["asserts"]) if synth else (None, [])
    row = {
        "query": query,
        "patch_name": patch.get("patch_name", ""),
        "n_changes": len(patch["changes"]),
        "roundtrip": round(roundtrip_score(query, resolved, patch.get("patch_name", "")), 3),
        "rubric_synth": synth,
        "rubric": rub,
    }
    if do_judge:
        j = judge_score(query, patch)
        row["judge"] = j["score"]
        row["judge_verdict"] = j.get("verdict", "")
        row["judge_missing"] = j.get("missing", [])
    return row


def _gen(query: str, grounding: str = "adapt") -> dict:
    from generate_patch import generate_patch
    return generate_patch(query, grounding=grounding)


def selftest() -> None:
    """Discrimination validation: do the metrics separate a matched patch from a mismatched one?
    Generate a patch for each probe query, then score every query against every patch. A useful
    metric makes the diagonal (matched) beat the off-diagonal (mismatched)."""
    rubrics = load_rubrics()
    probes = [
        "warm Juno-style chorus pad with slow movement",
        "aggressive bright hard-sync lead",
        "deep punchy sub bass, short percussive pluck",
    ]
    print("generating one patch per probe query (adapt mode)...\n")
    patches = [_gen(q) for q in probes]

    # roundtrip matrix (free) + judge matrix (API)
    rt = [[roundtrip_score(q, resolve_full(p["changes"]), p.get("patch_name", ""))
           for p in patches] for q in probes]
    jd = [[judge_score(q, p)["score"] for p in patches] for q in probes]

    def show(name, M):
        print(f"=== {name} matrix (rows=query, cols=patch-built-for) ===")
        print("            " + "  ".join(f"P{j}" for j in range(len(probes))))
        for i, row in enumerate(M):
            print(f"Q{i} " + "  ".join(f"{v:5.2f}" for v in row)
                  + ("   <- " + probes[i][:34]))
        diag = [M[i][i] for i in range(len(M))]
        off = [M[i][j] for i in range(len(M)) for j in range(len(M)) if i != j]
        dm, om = sum(diag) / len(diag), sum(off) / len(off)
        sep = dm - om
        print(f"  matched(diag) mean={dm:.2f}  mismatched(off) mean={om:.2f}  "
              f"separation={sep:+.2f}  -> {'DISCRIMINATES' if sep > 0 else 'NO SIGNAL'}\n")
        return dm, om, sep

    print()
    rt_stats = show("ROUNDTRIP (cosine)", rt)
    jd_stats = show("JUDGE (1-5)", jd)

    # rubric: does the Juno patch satisfy the Juno rubric better than the others do?
    juno = load_rubrics()["juno"]["asserts"]
    print("=== RUBRIC (Juno) — fraction of Juno's auto-harvested asserts satisfied ===")
    print(f"  Juno rubric asserts ({len(juno)}): "
          + ", ".join(f"{a[0]} {a[1]}" + (f'={a[2]}' if a[2] else '') for a in juno))
    rub_vals = []
    for i, p in enumerate(patches):
        s, _ = rubric_score(resolve_full(p["changes"]), juno)
        rub_vals.append(s)
        print(f"  P{i} ({probes[i][:34]:34s}): {s}")
    sep_r = (rub_vals[0] or 0) - max([v for v in rub_vals[1:] if v is not None] or [0])
    print(f"  juno-patch vs best-other separation = {sep_r:+.2f} -> "
          f"{'DISCRIMINATES' if sep_r > 0 else 'NO SIGNAL'}\n")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {"kind": "selftest", "timestamp": ts, "probes": probes,
           "roundtrip_matrix": rt, "judge_matrix": jd,
           "roundtrip_sep": rt_stats[2], "judge_sep": jd_stats[2], "rubric_juno": rub_vals}
    (RESULTS_DIR / f"{ts}_patch_quality_selftest.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    verdict = ("PASS: all layers discriminate" if rt_stats[2] > 0 and jd_stats[2] > 0 and sep_r > 0
               else "PARTIAL: see per-layer separation above")
    print(f"SELFTEST {verdict}")
    print(f"saved -> eval/results/{ts}_patch_quality_selftest.json")


def run_queries(queries: list[str]) -> None:
    rubrics = load_rubrics()
    rows = []
    for q in queries:
        print(f"\n>>> {q}")
        patch = _gen(q)
        row = score_query(q, patch, rubrics)
        rows.append(row)
        print(f"    name      : {row['patch_name']}  ({row['n_changes']} changes)")
        print(f"    roundtrip : {row['roundtrip']}")
        print(f"    rubric    : {row['rubric']} (synth={row['rubric_synth']})")
        print(f"    judge     : {row['judge']}/5 — {row['judge_verdict']}")
        if row["judge_missing"]:
            print(f"    missing   : {row['judge_missing']}")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{ts}_patch_quality_run.json").write_text(
        json.dumps({"timestamp": ts, "rows": rows}, indent=1), encoding="utf-8")
    print(f"\nsaved -> eval/results/{ts}_patch_quality_run.json")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "--selftest":
        selftest()
    elif args[0] == "--golden":
        golden_path = Path(args[1]) if len(args) > 1 and not args[1].isdigit() \
            else ROOT / "eval" / "golden_set_v2.jsonl"
        n = int(next((a for a in args[1:] if a.isdigit()), 8))
        golden = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines()
                  if l.strip()]
        run_queries([g["query"] for g in golden if g["bucket"] in (2, 3)][:n])
    else:
        run_queries(args)


if __name__ == "__main__":
    main()
