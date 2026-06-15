"""Patch-level parameter accuracy (v2 plan, Phase A step 3) — the text-domain proxy
for the deferred audio eval.

Metric definition (stated before Phase B code exists, per the Phase-A milestone):
  For a golden entry with `param_targets: [<patch_id>, ...]` (reference patches in
  data/patches/<id>.json), generate a patch for the query and resolve it to a full
  82-parameter state (INIT + changes). Against EACH reference patch:
    - knob/bipolar params agree when |gen - ref| <= tolerance, where tolerance is
      ±10 on a 0..127 span, scaled to the param's actual range:
      tol = max(1, round((max - min) * 10 / 127))
    - toggle/select params agree only on exact match.
  The entry's score is the best reference (max agreement). Two numbers are reported:
    - overall agreement: across all 82 params (context: rewards correct restraint)
    - active agreement (PRIMARY): across only the params where the reference differs
      from INIT — i.e., the parameters that actually constitute the recipe.
  Reported overall + per panel section group (oscillators / mixer / filters /
  envelopes / modulation / effects / performance).

Usage: python -X utf8 eval/patch_accuracy.py <run_label> [golden_file]
(defaults to eval/golden_set_v2.jsonl entries that carry param_targets)
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "ui"))
from patch_schema import INIT_PATCH, PARAMS  # noqa: E402

PATCH_DIR = ROOT / "data" / "patches"
RESULTS_DIR = ROOT / "eval" / "results"

SECTION_GROUPS = {
    "oscillators": ("osc1.", "osc2.", "slop."),
    "mixer": ("mixer.",),
    "filters": ("lpf.", "hpf."),
    "envelopes": ("fenv.", "aenv."),
    "modulation": ("lfo.", "pmod.", "at."),
    "effects": ("fx.", "fxa.", "fxb.", "dist."),
    "performance": ("glide.", "unison.", "arp.", "clock.", "misc."),
}


def group_of(pid: str) -> str:
    for g, prefixes in SECTION_GROUPS.items():
        if pid.startswith(prefixes):
            return g
    return "other"


def tolerance(pid: str) -> int:
    p = PARAMS[pid]
    if p["type"] in ("knob", "bipolar"):
        return max(1, round((p["max"] - p["min"]) * 10 / 127))
    return 0


def params_agree(pid: str, a, b) -> bool:
    if PARAMS[pid]["type"] in ("knob", "bipolar"):
        return abs(int(a) - int(b)) <= tolerance(pid)
    return a == b


def resolve_full(changes: list[dict]) -> dict:
    state = dict(INIT_PATCH)
    for c in changes:
        if c["param"] in state:
            state[c["param"]] = c["value"]
    return state


def score_against(gen: dict, ref: dict) -> dict:
    """Agreement of a resolved generated patch vs one reference patch."""
    active = [pid for pid in PARAMS if ref.get(pid, INIT_PATCH[pid]) != INIT_PATCH[pid]]
    rows = {}
    for scope, pids in (("overall", list(PARAMS)), ("active", active)):
        agree = [pid for pid in pids if params_agree(pid, gen[pid], ref.get(pid, INIT_PATCH[pid]))]
        by_group: dict[str, list] = {}
        for pid in pids:
            by_group.setdefault(group_of(pid), []).append(
                params_agree(pid, gen[pid], ref.get(pid, INIT_PATCH[pid])))
        rows[scope] = {
            "n": len(pids), "agree": len(agree),
            "pct": round(len(agree) / len(pids), 3) if pids else None,
            "by_group": {g: round(sum(v) / len(v), 3) for g, v in sorted(by_group.items())},
        }
    return rows


def load_reference(patch_id: str) -> dict:
    return json.loads((PATCH_DIR / f"{patch_id}.json").read_text(encoding="utf-8"))["params"]


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "unlabeled"
    golden_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "eval" / "golden_set_v2.jsonl"
    sys.path.insert(0, str(ROOT / "src" / "ui"))
    from generate_patch import generate_patch

    golden = [json.loads(l) for l in golden_path.read_text(encoding="utf-8").splitlines()
              if l.strip()]
    probes = [g for g in golden if g.get("param_targets")]
    if not probes:
        sys.exit("no golden entries with param_targets — Phase B not ingested yet?")

    per_query = []
    for g in probes:
        gen = resolve_full(generate_patch(g["query"])["changes"])
        best = None
        for pid in g["param_targets"]:
            s = score_against(gen, load_reference(pid))
            if best is None or (s["active"]["pct"] or 0) > (best["active"]["pct"] or 0):
                best, best_ref = s, pid
        per_query.append({"id": g["id"], "query": g["query"], "best_ref": best_ref, **best})
        print(f"{g['id']}: active {best['active']['agree']}/{best['active']['n']} "
              f"= {best['active']['pct']}  (overall {best['overall']['pct']})  ref={best_ref}")

    def mean(key):  # noqa: E306
        vals = [q[key]["pct"] for q in per_query if q[key]["pct"] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = {"run": label, "timestamp": ts, "n_queries": len(per_query),
           "mean_active_agreement": mean("active"),
           "mean_overall_agreement": mean("overall"), "per_query": per_query}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{ts}_patch_accuracy_{label}.json"
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nmean active agreement:  {out['mean_active_agreement']}")
    print(f"mean overall agreement: {out['mean_overall_agreement']}")
    print(f"saved -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
