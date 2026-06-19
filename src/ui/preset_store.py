"""Save / load user presets for the Studio.

Presets live in data/presets/<slug>.json = {id, name, params, ts}. data/ is gitignored, so
presets stay local to the machine — the same no-external-store approach as captured_dump.json
(D-030/D-031). Saved params are sanitized against the schema so a preset is always loadable.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRESET_DIR = (ROOT / "data" / "presets").resolve()
sys.path.insert(0, str(ROOT / "src" / "ui"))
from patch_schema import INIT_PATCH, PARAMS  # noqa: E402


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower()).strip("-")
    return s[:48] or "preset"


def _safe_path(pid: str) -> Path:
    """Resolve a preset id to a file inside PRESET_DIR (slug strips any traversal)."""
    p = (PRESET_DIR / f"{_slug(pid)}.json").resolve()
    if p.parent != PRESET_DIR:
        raise ValueError(f"invalid preset id: {pid!r}")
    return p


def _sanitize(params: dict) -> dict:
    """Coerce an arbitrary param dict to a full, schema-valid set: drop unknown keys, clamp
    knobs, validate selects, fall back to INIT for anything missing or malformed."""
    params = params or {}
    clean = {}
    for pid, p in PARAMS.items():
        v = params.get(pid, INIT_PATCH[pid])
        try:
            if p["type"] in ("knob", "bipolar"):
                v = max(p["min"], min(p["max"], int(round(float(v)))))
            elif p["type"] == "toggle":
                v = v.strip().lower() in ("true", "on", "yes", "1") if isinstance(v, str) else bool(v)
            else:  # select
                sv = str(v).strip().lower()
                v = next((o for o in p["options"] if o.lower() == sv), INIT_PATCH[pid])
        except (TypeError, ValueError):
            v = INIT_PATCH[pid]
        clean[pid] = v
    return clean


def _sysex(params: dict, name: str):
    """Edit-buffer sysex for the preset so loading can also push to hardware (best-effort)."""
    try:
        sys.path.insert(0, str(ROOT / "src" / "patches"))
        from encode_sysex import encode_edit_buffer
        return encode_edit_buffer(params, name)
    except Exception:
        return None


def save(name: str, params: dict) -> dict:
    name = str(name or "").strip()
    if not name:
        raise ValueError("preset needs a name")
    slug = _slug(name)
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"id": slug, "name": name, "params": _sanitize(params),
           "ts": datetime.now().strftime("%Y%m%d-%H%M%S")}
    _safe_path(slug).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return {"ok": True, "id": slug, "name": name}


def list_presets() -> list:
    if not PRESET_DIR.exists():
        return []
    out = []
    for f in PRESET_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue  # skip a corrupt/half-written file
        out.append({"id": d.get("id", f.stem), "name": d.get("name", f.stem), "ts": d.get("ts", "")})
    out.sort(key=lambda r: r["ts"], reverse=True)
    return out


def load(pid: str) -> dict | None:
    p = _safe_path(pid)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    params = _sanitize(d.get("params"))
    return {"id": d.get("id"), "name": d.get("name"), "params": params,
            "sysex": _sysex(params, d.get("name", ""))}


def delete(pid: str) -> dict:
    p = _safe_path(pid)
    if p.exists():
        p.unlink()
    return {"ok": True, "id": _slug(pid)}
