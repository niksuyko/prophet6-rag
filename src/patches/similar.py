"""Parameter-space nearest-neighbor search over decoded patches (v2 Phase B step 4).

NumPy over normalized parameter vectors — same transparency rationale as the v1 vector
store (D-009). Knobs scale to 0..1, bipolars center on 0 (half-weight per side), toggles
are 0/1, selects are ordinal-scaled. Sound-defining sections weigh more than performance
settings so "nearest" means "sounds similar", not "same BPM".

Usage: python -X utf8 src/patches/similar.py p6-factory-005
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "ui"))
from patch_schema import PARAMS  # noqa: E402

PATCH_DIR = ROOT / "data" / "patches"

WEIGHTS = {  # by schema id prefix; sound-defining > performance
    "osc1.": 2.0, "osc2.": 2.0, "mixer.": 1.5, "lpf.": 2.0, "hpf.": 1.0,
    "fenv.": 1.5, "aenv.": 1.5, "lfo.": 1.0, "pmod.": 1.0, "at.": 0.3,
    "fxa.": 0.7, "fxb.": 0.7, "fx.": 0.7, "dist.": 1.0, "slop.": 0.5,
    "unison.": 1.0, "glide.": 0.3, "arp.": 0.2, "clock.": 0.1, "misc.": 0.2,
}
ORDER = sorted(PARAMS)


def weight(pid: str) -> float:
    return next((w for pre, w in WEIGHTS.items() if pid.startswith(pre)), 1.0)


def params_vector(params: dict) -> np.ndarray:
    vec = []
    for pid in ORDER:
        p, v = PARAMS[pid], params[pid]
        if p["type"] in ("knob", "bipolar"):
            x = (v - p["min"]) / (p["max"] - p["min"])
        elif p["type"] == "toggle":
            x = 1.0 if v else 0.0
        else:
            x = p["options"].index(v) / max(1, len(p["options"]) - 1)
        vec.append(x * weight(pid))
    return np.array(vec, dtype=np.float32)


@lru_cache(maxsize=1)
def _index():
    entries = [json.loads(f.read_text(encoding="utf-8"))
               for f in sorted(PATCH_DIR.glob("p6-*.json"))]
    mat = np.stack([params_vector(e["params"]) for e in entries])
    return entries, mat


def similar_patches(params: dict, k: int = 5, exclude_id: str | None = None) -> list[dict]:
    entries, mat = _index()
    q = params_vector(params)
    d = np.linalg.norm(mat - q, axis=1)
    out = []
    for i in np.argsort(d):
        e = entries[i]
        if e["id"] == exclude_id:
            continue
        out.append({"id": e["id"], "name": e["name"], "distance": float(d[i]),
                    "params": e["params"]})
        if len(out) >= k:
            break
    return out


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "p6-factory-005"
    ref = json.loads((PATCH_DIR / f"{pid}.json").read_text(encoding="utf-8"))
    print(f"nearest to {pid} \"{ref['name']}\":")
    for s in similar_patches(ref["params"], k=6, exclude_id=pid):
        print(f"  {s['distance']:6.2f}  {s['id']}  {s['name']}")
