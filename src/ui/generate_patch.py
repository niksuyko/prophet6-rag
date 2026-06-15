"""Text -> Prophet-6 patch generation (decisions.md D-020).

Pipeline: retrieve corpus chunks for the sound description (production hybrid+div mode),
then ask the LLM for a JSON patch constrained to the front-panel schema in patch_schema.py.
Values are validated/clamped server-side before reaching the panel UI.

Grounding contract (looser than ask.py, by design): patch design is a creative task, so
the model may use general subtractive-synthesis practice — but every change must say WHERE
it came from: a chunk label (e.g. "Manual - Slop", "reddit:11hzzll") when a retrieved chunk
motivated it, or the literal string "general synthesis" otherwise. The UI surfaces this
distinction so corpus-grounded moves are visually separable from the model's own judgment.

Usage: python src/ui/generate_patch.py "fat juno-style brass"
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "retrieve"))
import load_env  # noqa: E402,F401  (side effect: ANTHROPIC_API_KEY from .env)
from search import retrieve  # noqa: E402

from patch_schema import INIT_PATCH, schema_for_prompt, validate_changes  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a Sequential Prophet-6 sound designer. Given a sound description and
context chunks retrieved from a Prophet-6 knowledge corpus (official manual + community
threads), you program a patch starting from the INIT state.

Rules:
1. Output ONLY a JSON object, no markdown fences, no prose outside it:
   {
     "patch_name": "<short evocative name>",
     "summary": "<2-3 sentences: the sound-design idea behind the patch>",
     "changes": [
       {"param": "<schema id>", "value": <number|string|boolean>,
        "why": "<one sentence: what this move contributes to the requested sound>",
        "source": "<chunk label like 'Manual - Slop' or 'reddit:abc123' if a retrieved
                    chunk motivated this setting, else exactly 'general synthesis'>"}
     ],
     "playing_tip": "<one sentence on how to play/perform it, or ''>"
   }
2. List ONLY parameters that differ from INIT. Every change must use an exact schema id
   and respect its range/options.
3. Prefer settings supported by the context chunks; cite their labels in "source". When
   REAL PATCH examples are provided, adapt from them where they fit the request and cite
   "patch:<id>" for every setting taken or adapted from one. Use "general synthesis"
   honestly for everything else — do not fake citations.
4. Make a complete, playable patch: if nothing would make sound (mixer all down) or the
   amp envelope contradicts the request, fix it. Remember interactions noted in the hints
   (e.g. glide needs both the switch on and rate > 0; pulse width is only audible on pulse
   shapes; effects need fx.on plus a mix above 0).
5. Aim for 10-25 changes — enough to fully realize the sound, no gratuitous moves."""


def chunk_label(c: dict) -> str:
    if c["source_type"] == "manual":
        return f"Manual - {c['section']}"
    if c["source_type"] == "reddit":
        return f"reddit:{c['source_id']}"
    return f"{c['source_type']}:{c['source_id']}"


def _nondefault(params: dict) -> dict:
    from patch_schema import INIT_PATCH
    return {k: v for k, v in params.items() if v != INIT_PATCH[k]}


def real_patch_block(chunks: list[dict], max_patches: int = 3) -> str:
    """Full structured params for retrieved patch chunks (v2 D-024 retrieve-and-adapt),
    plus one parameter-space neighbor of the best hit for breadth."""
    import json as _json
    from pathlib import Path
    patch_dir = ROOT / "data" / "patches"
    ids = [c["source_id"] for c in chunks if c["source_type"] == "patch"][:max_patches]
    entries = []
    for pid in ids:
        p = patch_dir / f"{pid}.json"
        if p.exists():
            entries.append(_json.loads(p.read_text(encoding="utf-8")))
    if entries:
        try:
            sys.path.insert(0, str(ROOT / "src" / "patches"))
            from similar import similar_patches
            for n in similar_patches(entries[0]["params"], k=1,
                                     exclude_id=entries[0]["id"]):
                if n["id"] not in {e["id"] for e in entries}:
                    entries.append({"id": n["id"], "name": n["name"],
                                    "params": n["params"]})
        except Exception:
            pass  # neighbor expansion is best-effort
    if not entries:
        return ""
    parts = ["These are REAL Prophet-6 patches (factory/official banks) retrieved for "
             "this request — settings shown as deviations from INIT. Adapt from them "
             "when relevant; cite as patch:<id>."]
    for e in entries:
        parts.append(f"<patch id=\"{e['id']}\" name=\"{e['name']}\">\n"
                     f"{_json.dumps(_nondefault(e['params']))}\n</patch>")
    return "\n\n".join(parts)


def build_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"<chunk label=\"{chunk_label(c)}\">\n{c['text']}\n</chunk>" for c in chunks)


def _salvage_truncated(text: str) -> dict:
    """Recover a patch from output cut off mid-JSON (e.g. max_tokens hit): keep the name and
    every COMPLETE change object, drop the truncated tail. Fail-safe over fail-total (D-032)."""
    name = (re.search(r'"patch_name"\s*:\s*"([^"]*)"', text) or [None, "Untitled"])[1]
    summary = (re.search(r'"summary"\s*:\s*"([^"]*)"', text) or [None, ""])[1]
    arr = text[text.find('"changes"'):] if '"changes"' in text else ""
    changes = []
    for obj in re.findall(r"\{[^{}]*\}", arr):  # change objects are flat (no nesting)
        try:
            o = json.loads(obj)
        except json.JSONDecodeError:
            continue
        if "param" in o:
            changes.append(o)
    return {"patch_name": name, "summary": summary, "changes": changes, "playing_tip": ""}


def _extract_json(text: str) -> dict:
    """Parse the model's JSON, tolerating stray fences/prose, and salvaging truncated output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return _salvage_truncated(text)


def generate_patch(query: str, mode: str = "patch+div", k: int = 8,
                   model: str = DEFAULT_MODEL, grounding: str = "adapt") -> dict:
    """grounding='adapt' (production, D-024): retrieved patch chunks contribute their
    full structured params and the model adapts real patches. grounding='pure': v1
    behavior (text chunks only) — kept for the measured A/B."""
    import anthropic
    chunks = retrieve(query, k, mode=mode)
    patch_block = real_patch_block(chunks) if grounding == "adapt" else ""
    user = (f"Parameter schema (the only valid ids/ranges):\n\n{schema_for_prompt()}\n\n"
            + (f"{patch_block}\n\n" if patch_block else "")
            + f"Context chunks:\n\n{build_context(chunks)}\n\n"
            f"Sound description: {query}")
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=4096, temperature=0.4,
                                 system=SYSTEM,
                                 messages=[{"role": "user", "content": user}])
    raw = _extract_json(msg.content[0].text)
    changes, problems = validate_changes(raw.get("changes", []))
    patch_name = str(raw.get("patch_name", "Untitled"))
    resolved = {**INIT_PATCH, **{c["param"]: c["value"] for c in changes}}
    return {
        "query": query,
        "patch_name": patch_name,
        "summary": str(raw.get("summary", "")),
        "playing_tip": str(raw.get("playing_tip", "")),
        "changes": changes,
        "problems": problems,
        "grounding": grounding,
        "retrieved": [{"label": chunk_label(c), "url": c["source_url"]} for c in chunks],
        "init": INIT_PATCH,
        # MIDI-out (D-030): edit-buffer sysex of the resolved patch; client sends it
        # when the MIDI toggle is on. Computed here so the browser stays a dumb pipe.
        "sysex": _sysex_for(resolved, patch_name),
    }


def _sysex_for(resolved: dict, name: str) -> list | None:
    try:
        sys.path.insert(0, str(ROOT / "src" / "patches"))
        from encode_sysex import encode_edit_buffer
        return encode_edit_buffer(resolved, name)
    except Exception:
        return None  # MIDI is a bonus; never let encoding break generation


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "warm Juno-style chorus pad"
    print(json.dumps(generate_patch(q), indent=2))
